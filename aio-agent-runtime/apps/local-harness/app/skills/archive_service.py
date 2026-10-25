"""Private immutable archive quarantine; no decompression or user-code execution here."""

from datetime import timedelta
import hashlib
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select, update, null

from ..admin.service import AdminService
from ..db import schema as s
from ..observability import audit
from ..platform_errors import PlatformError
from ..policy.repository import db_now, lock_resource_rows, require_resource, visible_resources
from ..runtime.actions import canonical_digest
from ..workspaces.references import blob_referenced
from ..workspaces.service import ArtifactService
from ..workspaces.storage import BlobStore
from .archive_contracts import MAX_ARCHIVE_BYTES, MAX_IMPORTS, MAX_QUARANTINE_BYTES, SkillArchivePrepare
from .service import SkillService


TERMINAL_IMPORTS = frozenset({"imported", "rejected", "cancelled"})


def allocated(c, org):
    return c.execute(
        select(func.coalesce(func.sum(s.skill_imports.c.reserved_bytes), 0)).where(s.skill_imports.c.org_id == org)
    ).scalar_one()


class SkillArchiveService:
    def __init__(self, database, settings, blobs=None):
        self.db, self.settings = database, settings
        self.blobs = blobs or (BlobStore(settings.artifact_root) if settings.artifact_root else None)
        self.admin = AdminService(database, settings)
        self.skills = SkillService(database, settings)

    def profile(self, id, image=None):
        item = next((v for v in getattr(self.settings, "sandbox_profiles", ()) if v["id"] == id), None)
        if (
            item is None
            or item.get("max_timeout_seconds", 120) < 10
            or (image is not None and item["image_digest"] != image)
        ):
            raise PlatformError(
                "SKILL_IMPORT_PROFILE_UNAVAILABLE", "The approved Skill import environment is unavailable", 403
            )
        return item

    def enabled(self):
        id = getattr(self.settings, "skill_import_profile", None)
        if self.blobs is None or not self.settings.manager_url or id is None:
            raise PlatformError(
                "SKILL_IMPORT_UNAVAILABLE", "An approved archive scanner and private storage must be configured", 503
            )
        return self.profile(id)

    def configuration(self, p):
        with self.admin.transaction(p):
            try:
                self.enabled()
                available = True
            except PlatformError:
                available = False
            return {
                "available": available,
                "formats": ["zip", "tar", "tar.gz"],
                "max_bytes": MAX_ARCHIVE_BYTES,
                "modes": ["manifest", "native_instruction_only"],
                "automatically_published": False,
            }

    @staticmethod
    def row(c, org, id, *, lock=False):
        query = select(s.skill_imports).where(s.skill_imports.c.org_id == org, s.skill_imports.c.id == id)
        result = c.execute(query.with_for_update() if lock else query).mappings().first()
        if result is None:
            raise PlatformError("RESOURCE_NOT_FOUND", "Skill import is not accessible", 404)
        return dict(result)

    def private(self, c, p, id, *, write=False):
        if write:
            lock_resource_rows(c, p.org_id, [id])
        row = self.row(c, p.org_id, id, lock=write)
        if row["requested_by"] != p.user_id:
            raise PlatformError("RESOURCE_NOT_FOUND", "Skill archive quarantine is private to its author", 404)
        require_resource(c, p, id, "skill_import.update" if write else "skill_import.read")
        return row

    @staticmethod
    def metadata(row):
        return {
            **{
                k: row[k]
                for k in (
                    "id",
                    "request_id",
                    "state",
                    "revision",
                    "archive_sha256",
                    "archive_size",
                    "uploaded_at",
                    "queue_expires_at",
                    "cleanup_state",
                    "manager_acknowledged",
                    "error_code",
                    "purge_requested",
                    "archive_purged",
                    "skill_id",
                    "created_at",
                    "finished_at",
                )
            },
            "archive_format": row["request"]["archive_format"],
            "mode": "native_instruction_only" if row["request"].get("native") else "manifest",
            "execution_profile": row["execution_profile"],
            "scan_report": row["scan_receipt"],
            "automatically_published": False,
        }

    def prepare(self, p, body: SkillArchivePrepare):
        scanner = self.enabled()
        execution = self.profile(body.sandbox_profile)
        request = body.model_dump(mode="json")
        digest = canonical_digest("aio-skill-import-request-v1", request)
        with self.admin.transaction(p, write=True) as c:
            old = (
                c.execute(
                    select(s.skill_imports).where(
                        s.skill_imports.c.org_id == p.org_id,
                        s.skill_imports.c.requested_by == p.user_id,
                        s.skill_imports.c.request_id == body.request_id,
                    )
                )
                .mappings()
                .first()
            )
            if old:
                if old["request_digest"] != digest:
                    raise PlatformError(
                        "IDEMPOTENCY_CONFLICT", "This upload identity is bound to different archive metadata", 409
                    )
                return self.metadata(self.private(c, p, old["id"]))
            count = c.execute(
                select(func.count())
                .select_from(s.skill_imports)
                .where(
                    s.skill_imports.c.org_id == p.org_id,
                    s.skill_imports.c.archive_purged.is_(False),
                )
            ).scalar_one()
            if count >= MAX_IMPORTS or allocated(c, p.org_id) + body.bytes > MAX_QUARANTINE_BYTES:
                raise PlatformError("SKILL_IMPORT_QUOTA", "Skill archive quarantine quota is exhausted", 429)
            ArtifactService.check_storage_quota(c, p.org_id, None, body.bytes)
            id = uuid4()
            c.execute(
                insert(s.resources).values(
                    org_id=p.org_id, id=id, owner_id=p.user_id, kind="skill_import", classification="internal"
                )
            )
            require_resource(c, p, id, "skill_import.update")
            c.execute(
                insert(s.skill_imports).values(
                    org_id=p.org_id,
                    id=id,
                    requested_by=p.user_id,
                    membership_revision=p.membership_revision,
                    request_id=body.request_id,
                    request_digest=digest,
                    request=request,
                    archive_sha256=body.sha256,
                    archive_size=body.bytes,
                    reserved_bytes=body.bytes,
                    queue_expires_at=db_now(c) + timedelta(seconds=self.settings.queue_ttl_seconds),
                    scanner_profile=scanner["id"],
                    scanner_image=scanner["image_digest"],
                    execution_profile=execution["id"],
                    execution_image=execution["image_digest"],
                )
            )
            audit.record(
                c,
                p,
                'skill.archive.prepare',
                id,
                'quarantined',
            )
            return self.metadata(self.row(c, p.org_id, id))

    def upload(self, p, id, data):
        self.enabled()
        if not isinstance(data, bytes) or len(data) > MAX_ARCHIVE_BYTES:
            raise PlatformError("PAYLOAD_TOO_LARGE", "Skill archive exceeds its fixed upload bound", 413)
        sha = hashlib.sha256(data).hexdigest()
        with self.admin.transaction(p, write=True) as c:
            row = self.private(c, p, id, write=True)
            if len(data) != row["archive_size"] or sha != row["archive_sha256"]:
                raise PlatformError(
                    "ARCHIVE_UPLOAD_MISMATCH", "Archive bytes do not match the immutable upload intention", 409
                )
            if row["purge_requested"] or row["archive_purged"]:
                raise PlatformError("SKILL_IMPORT_RETIRED", "This archive upload is retired", 409)
            if row["uploaded_at"]:
                return self.metadata(row)
            if row["state"] not in {"awaiting_upload", "uploading"} or row["queue_expires_at"] <= db_now(c):
                raise PlatformError("SKILL_IMPORT_EXPIRED", "Archive upload is no longer available", 409)
            c.execute(
                update(s.skill_imports)
                .where(s.skill_imports.c.id == id)
                .values(
                    state="uploading",
                    upload_bound=True,
                    revision=s.skill_imports.c.revision + 1,
                    updated_at=db_now(c),
                )
            )
        # Expected bytes/hold are durable first. Bounded local writes share the
        # organization storage lock with GC, so cancellation cannot resurrect a blob.
        with self.admin.transaction(p, write=True) as c:
            row = self.private(c, p, id, write=True)
            if row["purge_requested"] or row["archive_purged"] or row["state"] != "uploading":
                if row["uploaded_at"] and not row["purge_requested"]:
                    return self.metadata(row)
                raise PlatformError("SKILL_IMPORT_RETIRED", "Archive upload changed before storage completion", 409)
            if row["membership_revision"] != p.membership_revision:
                raise PlatformError(
                    "IDENTITY_REVISION_CHANGED", "Archive author permissions changed; start a fresh import", 409
                )
            self.blobs.put(p.org_id, data)
            now = db_now(c)
            c.execute(
                update(s.skill_imports)
                .where(s.skill_imports.c.id == id)
                .values(
                    state="queued",
                    uploaded_at=now,
                    updated_at=now,
                    revision=s.skill_imports.c.revision + 1,
                )
            )
            audit.record(
                c,
                p,
                'skill.archive.upload',
                id,
                'queued',
            )
            return self.metadata(self.row(c, p.org_id, id))

    def list(self, p):
        with self.admin.transaction(p) as c:
            predicate = visible_resources(c, p, "skill_import", "skill_import.read")
            rows = c.execute(
                select(s.skill_imports)
                .join(
                    s.resources,
                    (s.resources.c.org_id == s.skill_imports.c.org_id) & (s.resources.c.id == s.skill_imports.c.id),
                )
                .where(
                    s.skill_imports.c.org_id == p.org_id,
                    s.skill_imports.c.requested_by == p.user_id,
                    predicate,
                )
                .order_by(s.skill_imports.c.created_at.desc())
                .limit(100)
            ).mappings()
            return [self.metadata(row) for row in rows]

    def detail(self, p, id):
        with self.admin.transaction(p) as c:
            return self.metadata(self.private(c, p, id))

    def download(self, p, id):
        if self.blobs is None:
            raise PlatformError("SKILL_IMPORT_UNAVAILABLE", "Private archive storage is not configured", 503)
        with self.admin.transaction(p) as c:
            row = self.private(c, p, id)
            if not row["uploaded_at"] or row["archive_purged"] or row["purge_requested"]:
                raise PlatformError("RESOURCE_NOT_FOUND", "Original archive is not available", 404)
        data = self.blobs.get(p.org_id, row["archive_sha256"], row["archive_size"])
        with self.admin.transaction(p) as c:
            current = self.private(c, p, id)
            if (
                current["archive_purged"]
                or current["purge_requested"]
                or current["archive_sha256"] != row["archive_sha256"]
            ):
                raise PlatformError("RESOURCE_NOT_FOUND", "Original archive was retired", 404)
        return self.metadata(current), data

    def delete(self, p, id, revision):
        with self.admin.transaction(p, write=True) as c:
            row = self.private(c, p, id, write=True)
            if row["purge_requested"]:
                return self.metadata(row)
            if row["revision"] != revision:
                raise PlatformError(
                    "REVISION_CONFLICT", "Skill import changed; reload before deleting its raw archive", 409
                )
            values = {"purge_requested": True, "revision": row["revision"] + 1, "updated_at": db_now(c)}
            if row["state"] in {"awaiting_upload", "uploading", "queued"}:
                values.update(state="cancelled", error_code="SKILL_IMPORT_CANCELLED", finished_at=db_now(c))
            c.execute(update(s.skill_imports).where(s.skill_imports.c.id == id).values(**values))
            audit.record(
                c,
                p,
                'skill.archive.delete',
                id,
                'requested',
            )
            return self.metadata(self.row(c, p.org_id, id))

    def gc(self, org, limit=20):
        if self.blobs is None:
            return []
        with self.db.scoped(org, UUID(int=0)) as c:
            ids = (
                c.execute(
                    select(s.skill_imports.c.id)
                    .where(
                        s.skill_imports.c.org_id == org,
                        s.skill_imports.c.purge_requested.is_(True),
                        s.skill_imports.c.archive_purged.is_(False),
                        s.skill_imports.c.state.in_(TERMINAL_IMPORTS),
                        s.skill_imports.c.cleanup_state == "confirmed",
                        s.skill_imports.c.manager_acknowledged.is_(True),
                    )
                    .order_by(s.skill_imports.c.created_at)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
        purged = []
        for id in ids:
            with self.db.scoped(org, UUID(int=0)) as c:
                c.execute(select(s.organizations.c.id).where(s.organizations.c.id == org).with_for_update()).one()
                lock_resource_rows(c, org, [id])
                row = self.row(c, org, id, lock=True)
                if (
                    not row["purge_requested"]
                    or row["archive_purged"]
                    or row["state"] not in TERMINAL_IMPORTS
                    or row["cleanup_state"] != "confirmed"
                    or not row["manager_acknowledged"]
                ):
                    continue
                if not blob_referenced(c, org, row["archive_sha256"], excluding_import=id):
                    self.blobs.remove(org, row["archive_sha256"])
                c.execute(
                    update(s.skill_imports)
                    .where(s.skill_imports.c.id == id)
                    .values(
                        archive_purged=True,
                        reserved_bytes=0,
                        spec=null(),
                        candidate=null(),
                        command=null(),
                        revision=row["revision"] + 1,
                        updated_at=db_now(c),
                    )
                )
                purged.append(id)
        return purged
