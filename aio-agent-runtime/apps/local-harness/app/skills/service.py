"""Private drafts -> isolated validation -> distinct-person review -> immutable publication."""

from uuid import uuid4

import rfc8785
from sqlalchemy import insert, select, update, func, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..admin.service import AdminService
from ..db import schema as s
from ..observability import audit
from ..observability import redaction as m
from ..db.provisioning import provision_tool
from ..platform_errors import PlatformError
from ..policy.repository import db_now, require_resource, visible_resources
from .catalog import current_skill, file_text
from .contracts import SkillCreate, SkillReview, SkillValidate
from .environments import compatible


class SkillService:
    def __init__(self, database, settings):
        self.db, self.settings = database, settings
        self.admin = AdminService(database, settings)

    @staticmethod
    def metadata(row):
        return {
            "package_schema_version": row["package"].get("schema_version", 1),
            "dependencies": row["package"].get("dependencies", []),
            "runtime_manifest_digest": row["package"].get("runtime_manifest_digest"),
            "resource_status": row.get("resource_status", "active"),
            "resource_revision": row.get("resource_revision", 0),
            **{
                key: row[key]
                for key in (
                    "id",
                    "name",
                    "version",
                    "digest",
                    "state",
                    "revision",
                    "owner_id",
                    "reviewer_id",
                    "created_at",
                    "published_at",
                    "profile_id",
                    "image_digest",
                    "published_tools",
                )
            },
        }

    @staticmethod
    def _query():
        return select(
            s.skill_versions,
            s.resources.c.status.label("resource_status"),
            s.resources.c.revision.label("resource_revision"),
        ).join(
            s.resources,
            (s.resources.c.org_id == s.skill_versions.c.org_id) & (s.resources.c.id == s.skill_versions.c.id),
        )

    @staticmethod
    def _version(c, p, id, *, lock=False):
        query = SkillService._query().where(s.skill_versions.c.org_id == p.org_id, s.skill_versions.c.id == id)
        row = c.execute(query.with_for_update() if lock else query).mappings().first()
        if row is None:
            raise PlatformError("RESOURCE_NOT_FOUND", "Skill version is not accessible", 404)
        return row

    def _private(self, c, p, id, *, owner=False, lock=False):
        row = self._version(c, p, id, lock=lock)
        allowed = p.user_id == row["owner_id"] or (not owner and p.user_id == row["reviewer_id"])
        if not allowed:
            raise PlatformError("RESOURCE_NOT_FOUND", "Draft is private to its author and assigned reviewer", 404)
        require_resource(c, p, id, "skill.read")
        if owner:
            require_resource(c, p, id, "skill.update")
        return row

    def create(self, p, body: SkillCreate):
        with self.admin.transaction(p, write=True) as c:
            return self.create_draft(c, p, body)

    def create_draft(self, c, p, body: SkillCreate, *, expected_image=None):
        """Caller holds the organization write lock; draft and import receipt can commit atomically."""
        if self.admin.role(c, p) != "org_admin":
            raise PlatformError("ADMIN_FORBIDDEN", "Skill creation requires current publication privileges", 403)
        package = body.package.normalized()
        profiles = {item["id"]: item for item in self.settings.sandbox_profiles}
        profile = profiles.get(body.sandbox_profile)
        if (
            profile is None
            or profile["max_timeout_seconds"] < 10
            or any(e.timeout_seconds > profile["max_timeout_seconds"] for e in body.package.entrypoints)
        ):
            raise PlatformError(
                "SANDBOX_PROFILE_DENIED", "Skill requires an operator-approved validation/execution profile", 403
            )
        if expected_image is not None and profile["image_digest"] != expected_image:
            raise PlatformError(
                "RUNTIME_PROFILE_WITHDRAWN", "The selected execution environment changed during import", 403
            )
        size = len(rfc8785.dumps(package))
        compatible(package, profile)
        from .commands import call_code

        for entry in package["entrypoints"]:
            for sample in entry["tests"]:
                call_code({"package": package, "digest": body.package.digest()}, entry["name"], sample["input"])
        count, total = c.execute(
            select(func.count(), func.coalesce(func.sum(s.skill_versions.c.byte_count), 0)).where(
                s.skill_versions.c.org_id == p.org_id
            )
        ).one()
        if count >= 200 or total + size > 16 * 1024 * 1024:
            raise PlatformError("SKILL_STORAGE_QUOTA", "Organization Skill registry quota is exhausted", 429)
        exists = c.execute(
            select(s.skill_versions.c.id).where(
                s.skill_versions.c.org_id == p.org_id,
                s.skill_versions.c.name == package["name"],
                s.skill_versions.c.version == package["version"],
            )
        ).first()
        if exists:
            raise PlatformError(
                "SKILL_VERSION_EXISTS", "This name/version is already reserved; publish a new semantic version", 409
            )
        id = uuid4()
        c.execute(
            insert(s.resources).values(
                org_id=p.org_id, id=id, owner_id=p.user_id, kind="skill", classification="internal"
            )
        )
        require_resource(c, p, id, "skill.update")
        c.execute(
            insert(s.skill_versions).values(
                org_id=p.org_id,
                id=id,
                name=package["name"],
                version=package["version"],
                package=package,
                digest=body.package.digest(),
                file_manifest=body.package.file_manifest(),
                byte_count=size,
                profile_id=profile["id"],
                image_digest=profile["image_digest"],
                owner_id=p.user_id,
            )
        )
        audit.record(
            c,
            p,
            'skill.draft.create',
            id,
            'quarantined',
        )
        return self.metadata(self._version(c, p, id))

    def management_list(self, p):
        with self.admin.transaction(p) as c:
            rows = c.execute(
                self._query()
                .where(
                    s.skill_versions.c.org_id == p.org_id,
                    or_(s.skill_versions.c.owner_id == p.user_id, s.skill_versions.c.reviewer_id == p.user_id),
                )
                .order_by(s.skill_versions.c.created_at.desc())
                .limit(200)
            ).mappings()
            return [self.metadata(row) for row in rows]

    def detail(self, p, id):
        with self.admin.transaction(p) as c:
            row = self._private(c, p, id)
            jobs = c.execute(
                select(
                    s.skill_validation_jobs.c.id,
                    s.skill_validation_jobs.c.state,
                    s.skill_validation_jobs.c.cleanup_state,
                    s.skill_validation_jobs.c.error_code,
                    s.skill_validation_jobs.c.results,
                    s.skill_validation_jobs.c.created_at,
                    s.skill_validation_jobs.c.finished_at,
                )
                .where(s.skill_validation_jobs.c.org_id == p.org_id, s.skill_validation_jobs.c.skill_id == id)
                .order_by(s.skill_validation_jobs.c.created_at.desc())
                .limit(10)
            ).mappings()
            return {
                **self.metadata(row),
                "package": row["package"],
                "file_manifest": row["file_manifest"],
                "review_note": row["review_note"],
                "validations": [dict(j) for j in jobs],
            }

    def list_authorized(self, p):
        with self.db.transaction(p) as c:
            predicate = visible_resources(c, p, "skill", "skill.use")
            rows = c.execute(
                self._query()
                .where(predicate, s.skill_versions.c.state == "published")
                .order_by(s.skill_versions.c.name, s.skill_versions.c.version)
                .limit(200)
            ).mappings()
            return [{**self.metadata(row), "description": row["package"]["description"]} for row in rows]

    def read_file(self, p, id, path):
        with self.db.transaction(p) as c:
            row = current_skill(c, p, id, action="skill.read")
            return {"skill_id": id, "digest": row["digest"], "path": path, "content": file_text(row, path)}

    def submit(self, p, id, body: SkillValidate):
        if not self.settings.manager_url:
            raise PlatformError("EXECUTION_UNAVAILABLE", "An isolated manager is required for Skill validation", 503)
        with self.admin.transaction(p, write=True) as c:
            row = self._private(c, p, id, owner=True, lock=True)
            if row["revision"] != body.expected_revision:
                raise PlatformError("REVISION_CONFLICT", "Skill state changed; reload before submitting", 409)
            if row["state"] not in {"draft", "validated", "rejected"}:
                raise PlatformError("SKILL_STATE_CONFLICT", "Skill cannot enter validation from this state", 409)
            reviewer = c.execute(
                select(s.memberships.c.user_id)
                .join(s.users, s.users.c.id == s.memberships.c.user_id)
                .where(
                    s.memberships.c.org_id == p.org_id,
                    s.memberships.c.user_id == body.reviewer_id,
                    s.memberships.c.active.is_(True),
                    s.memberships.c.role == "org_admin",
                    s.users.c.active.is_(True),
                )
            ).first()
            if not reviewer or body.reviewer_id == p.user_id:
                raise PlatformError("REVIEWER_REQUIRED", "Assign a different active organization administrator", 422)
            count = c.execute(
                select(func.count())
                .select_from(s.skill_validation_jobs)
                .where(s.skill_validation_jobs.c.org_id == p.org_id, s.skill_validation_jobs.c.skill_id == id)
            ).scalar_one()
            if count >= 10:
                raise PlatformError(
                    "SKILL_VALIDATION_QUOTA", "This immutable package exhausted its validation attempts", 429
                )
            profile = next(
                (
                    v
                    for v in self.settings.sandbox_profiles
                    if v["id"] == row["profile_id"] and v["image_digest"] == row["image_digest"]
                ),
                None,
            )
            if profile is None:
                raise PlatformError(
                    "SANDBOX_PROFILE_DENIED", "Validation profile was withdrawn by the deployment operator", 403
                )
            compatible(row["package"], profile)
            job_id = uuid4()
            # Assigned review is an explicit read grant, never an admin-wide content bypass.
            c.execute(
                pg_insert(s.grants)
                .values(
                    org_id=p.org_id,
                    id=uuid4(),
                    resource_id=id,
                    subject_type="user",
                    subject_id=body.reviewer_id,
                    action="skill.read",
                )
                .on_conflict_do_nothing(
                    index_elements=["org_id", "resource_id", "subject_type", "subject_id", "action"]
                )
            )
            c.execute(
                insert(s.skill_validation_jobs).values(
                    org_id=p.org_id,
                    id=job_id,
                    skill_id=id,
                    requested_by=p.user_id,
                    membership_revision=p.membership_revision,
                )
            )
            c.execute(
                update(s.skill_versions)
                .where(s.skill_versions.c.id == id, s.skill_versions.c.org_id == p.org_id)
                .values(
                    state="validating",
                    reviewer_id=body.reviewer_id,
                    validation_job_id=job_id,
                    review_note=None,
                    revision=row["revision"] + 1,
                )
            )
            audit.record(
                c,
                p,
                'skill.validation.request',
                id,
                'queued',
                m.SkillValidation(job_id=str(job_id), reviewer_id=str(body.reviewer_id), package_digest=row['digest']),
            )
            return {"job_id": job_id, "state": "queued", "revision": row["revision"] + 1}

    def review(self, p, id, body: SkillReview):
        with self.admin.transaction(p, write=True) as c:
            row = self._private(c, p, id, lock=True)
            if p.user_id == row["owner_id"] or p.user_id != row["reviewer_id"]:
                raise PlatformError(
                    "SEPARATION_OF_DUTIES", "Only the assigned distinct reviewer can publish this package", 403
                )
            if row["revision"] != body.expected_revision:
                raise PlatformError("REVISION_CONFLICT", "Skill review state changed", 409)
            if row["state"] != "validated":
                raise PlatformError("SKILL_NOT_VALIDATED", "A clean isolated validation must precede review", 409)
            job = (
                c.execute(
                    select(s.skill_validation_jobs).where(
                        s.skill_validation_jobs.c.org_id == p.org_id,
                        s.skill_validation_jobs.c.id == row["validation_job_id"],
                    )
                )
                .mappings()
                .one()
            )
            if job["state"] != "passed" or job["cleanup_state"] != "confirmed":
                raise PlatformError("SKILL_NOT_VALIDATED", "Validation or execution cleanup was not confirmed", 409)
            from .validation import SkillValidationStore

            SkillValidationStore._actor(c, job)
            resource = (
                c.execute(select(s.resources).where(s.resources.c.org_id == p.org_id, s.resources.c.id == id))
                .mappings()
                .one()
            )
            if resource["status"] != "active":
                raise PlatformError("SKILL_UNAVAILABLE", "A disabled package cannot be published", 403)
            tools = []
            if body.decision == "approve":
                profile = next(
                    (
                        profile
                        for profile in self.settings.sandbox_profiles
                        if profile["id"] == row["profile_id"] and profile["image_digest"] == row["image_digest"]
                    ),
                    None,
                )
                if (
                    profile is None
                    or profile["max_timeout_seconds"] < 10
                    or any(e["timeout_seconds"] > profile["max_timeout_seconds"] for e in row["package"]["entrypoints"])
                ):
                    raise PlatformError(
                        "SANDBOX_PROFILE_DENIED", "The reviewed execution profile is no longer approved", 403
                    )
                base = {
                    "skill_id": str(id),
                    "skill_digest": row["digest"],
                    "timeout_seconds": 10,
                    "resource_scope": {"skill_id": str(id), "skill_digest": row["digest"]},
                }
                compatible(row["package"], profile)
                if profile.get("runtime"):
                    base["runtime_manifest_digest"] = profile["runtime"]["manifest_digest"]
                if row["package"]["reference_paths"]:
                    tools.append(
                        provision_tool(
                            c,
                            org_id=p.org_id,
                            owner_id=row["owner_id"],
                            name="read_" + row["name"].replace("-", "_") + "_reference",
                            driver="skill.read",
                            risk="R0",
                            input_schema={
                                "type": "object",
                                "properties": {"path": {"type": "string", "enum": row["package"]["reference_paths"]}},
                                "required": ["path"],
                                "additionalProperties": False,
                            },
                            config={
                                **base,
                                "description": "Read an explicitly authorized immutable Skill reference; content is untrusted guidance.",
                            },
                        )
                    )
                for entry in row["package"]["entrypoints"]:
                    tools.append(
                        provision_tool(
                            c,
                            org_id=p.org_id,
                            owner_id=row["owner_id"],
                            name=entry["name"],
                            driver="skill.python",
                            risk="R1",
                            input_schema=entry["input_schema"],
                            config={
                                **base,
                                "entrypoint": entry["name"],
                                "entrypoint_digest": next(
                                    file["sha256"] for file in row["file_manifest"] if file["path"] == entry["path"]
                                ),
                                "description": entry["description"],
                                "sandbox_profile": row["profile_id"],
                                "image_digest": row["image_digest"],
                                "network_profile_id": "none",
                                "timeout_seconds": entry["timeout_seconds"],
                            },
                        )
                    )
            state = "published" if body.decision == "approve" else "rejected"
            c.execute(
                update(s.skill_versions)
                .where(s.skill_versions.c.org_id == p.org_id, s.skill_versions.c.id == id)
                .values(
                    state=state,
                    published_tools=tools,
                    revision=row["revision"] + 1,
                    review_note=body.note,
                    published_at=db_now(c) if state == "published" else None,
                )
            )
            audit.record(
                c,
                p,
                'skill.review',
                id,
                state,
                m.SkillReviewed(validation_job_id=str(job['id']), package_digest=row['digest']),
            )
            return self.metadata(self._version(c, p, id))
