"""Durable validation queue with exact command authority and fail-closed cleanup recovery."""

import base64
import hashlib
from contextlib import contextmanager
from datetime import timedelta, timezone
from uuid import UUID, uuid4

import rfc8785
from sqlalchemy import select, update, or_

from ..admin.service import AdminService
from ..auth.principal import Principal
from ..db import schema as s
from ..platform_errors import PlatformError
from ..policy.repository import current_facts, db_now, require_resource
from ..runtime.actions import canonical_digest
from .commands import SCAN_CODE, call_code, entrypoint, result_value
from .contracts import package_digest
from .environments import runtime_check_code, runtime_report


class SkillValidationStore:
    def __init__(self, database, settings):
        self.db, self.settings = database, settings

    @staticmethod
    def _actor(c, job):
        p = Principal(
            job["org_id"], job["requested_by"], job["membership_revision"], service_actor_id=job["lease_owner"]
        )
        current_facts(c, p)
        if AdminService.role(c, p) != "org_admin":
            raise PlatformError("ADMIN_FORBIDDEN", "Skill author no longer has publication privileges", 403)
        require_resource(c, p, job["skill_id"], "skill.update")
        return p

    @staticmethod
    def _skill(c, job):
        row = (
            c.execute(
                select(s.skill_versions).where(
                    s.skill_versions.c.org_id == job["org_id"], s.skill_versions.c.id == job["skill_id"]
                )
            )
            .mappings()
            .one()
        )
        if (
            row["state"] != "validating"
            or row["validation_job_id"] != job["id"]
            or row["digest"] != package_digest(row["package"])
        ):
            raise PlatformError(
                "SKILL_VALIDATION_OBSOLETE", "Validation no longer belongs to this immutable package", 409
            )
        return dict(row)

    @contextmanager
    def owned(self, handle, *, active=True):
        with self.db.scoped(handle["org_id"], handle["requested_by"]) as c:
            job = (
                c.execute(
                    select(s.skill_validation_jobs)
                    .where(
                        s.skill_validation_jobs.c.org_id == handle["org_id"],
                        s.skill_validation_jobs.c.id == handle["id"],
                    )
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            now = db_now(c)
            if job["lease_owner"] != handle["lease_owner"] or job["generation"] != handle["generation"]:
                raise PlatformError("STALE_GENERATION", "Skill validation lease has changed", 409)
            if active:
                if job["state"] != "leased" or job["lease_expires_at"] <= now or job["deadline_at"] <= now:
                    raise PlatformError("STALE_GENERATION", "Skill validation lease expired", 409)
                self._actor(c, job)
                self._skill(c, job)
            yield c, dict(job), now

    def claim(self, org_id, worker_id):
        with self.db.scoped(org_id, UUID(int=0)) as c:
            now = db_now(c)
            row = (
                c.execute(
                    select(s.skill_validation_jobs)
                    .where(s.skill_validation_jobs.c.org_id == org_id, s.skill_validation_jobs.c.state == "queued")
                    .order_by(s.skill_validation_jobs.c.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            job = dict(row)
            job["lease_owner"] = worker_id
            try:
                self._actor(c, job)
                skill = self._skill(c, job)
                if job["created_at"] + timedelta(seconds=self.settings.queue_ttl_seconds) <= now:
                    raise PlatformError("QUEUE_DEADLINE_EXCEEDED", "Validation expired in queue", 409)
            except PlatformError as exc:
                self._finish(c, job, now, False, True, exc.code)
                return None
            deadline = now + timedelta(seconds=180)
            package = rfc8785.dumps(skill["package"])
            spec = {
                "schema_version": 1,
                "binding_id": str(uuid4()),
                "org_id": str(org_id),
                "run_id": str(job["id"]),
                "generation": job["generation"],
                "target_slot": "skill/validation",
                "profile_id": skill["profile_id"],
                "image_digest": skill["image_digest"],
                "deadline": deadline.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "inputs": [
                    {
                        "path": "package.json",
                        "sha256": hashlib.sha256(package).hexdigest(),
                        "content_b64": base64.b64encode(package).decode("ascii"),
                    }
                ],
            }
            commands = [{"dispatch_id": str(uuid4()), "kind": "scan", "code": SCAN_CODE, "timeout_seconds": 10}]
            if skill["package"].get("schema_version") == 2:
                commands.insert(
                    0,
                    {
                        "dispatch_id": str(uuid4()),
                        "kind": "runtime",
                        "code": runtime_check_code(skill["package"]),
                        "timeout_seconds": 10,
                    },
                )
            for e in skill["package"]["entrypoints"]:
                for index, sample in enumerate(e["tests"]):
                    commands.append(
                        {
                            "dispatch_id": str(uuid4()),
                            "kind": "test",
                            "entrypoint": e["name"],
                            "case": index,
                            "code": call_code(skill, e["name"], sample["input"]),
                            "timeout_seconds": e["timeout_seconds"],
                        }
                    )
            values = dict(
                state="leased",
                lease_owner=worker_id,
                deadline_at=deadline,
                lease_expires_at=min(deadline, now + timedelta(seconds=self.settings.lease_seconds)),
                spec=spec,
                commands=commands,
                cleanup_state="pending",
            )
            c.execute(update(s.skill_validation_jobs).where(s.skill_validation_jobs.c.id == job["id"]).values(**values))
            return {**job, **values}

    def pulse(self, handle):
        with self.owned(handle) as (c, job, now):
            c.execute(
                update(s.skill_validation_jobs)
                .where(s.skill_validation_jobs.c.id == job["id"])
                .values(lease_expires_at=min(job["deadline_at"], now + timedelta(seconds=self.settings.lease_seconds)))
            )

    def authorize(self, operation, payload):
        if operation not in {"ensure", "execute", "alive", "stop", "status"}:
            raise PlatformError(
                "MANAGER_ACTION_DENIED", "Skill validation cannot export or execute arbitrary actions", 403
            )
        try:
            spec = payload["spec"]
            org, id = UUID(spec["org_id"]), UUID(spec["run_id"])
        except (KeyError, ValueError, TypeError):
            raise PlatformError("MANAGER_ACTION_DENIED", "Invalid Skill validation identity", 403) from None
        with self.db.scoped(org, UUID(int=0)) as c:
            job = (
                c.execute(
                    select(s.skill_validation_jobs).where(
                        s.skill_validation_jobs.c.org_id == org, s.skill_validation_jobs.c.id == id
                    )
                )
                .mappings()
                .first()
            )
            if (
                job is None
                or not job["spec"]
                or canonical_digest("aio-cell-spec-v1", spec) != canonical_digest("aio-cell-spec-v1", job["spec"])
            ):
                raise PlatformError("MANAGER_ACTION_DENIED", "Skill cell is not bound by the platform", 403)
            if operation in {"stop", "status"}:
                return
            now = db_now(c)
            if (
                job["state"] != "leased"
                or job["generation"] != spec["generation"]
                or job["lease_expires_at"] <= now
                or job["deadline_at"] <= now
            ):
                raise PlatformError("MANAGER_ACTION_DENIED", "Skill validation lease is obsolete", 403)
            self._actor(c, job)
            skill = self._skill(c, job)
            if skill["package"].get("schema_version") == 2:
                from ..execution.runtime_policy import require_runtime

                require_runtime(
                    self.settings,
                    skill["profile_id"],
                    skill["image_digest"],
                    skill["package"]["runtime_manifest_digest"],
                )
            if operation in {"ensure", "alive"}:
                return
            commands = job["commands"]
            index = len(job["results"])
            if index >= len(commands):
                raise PlatformError("MANAGER_ACTION_DENIED", "Validation has no remaining command", 403)
            command = commands[index]
            if (
                payload.get("dispatch_id") != command["dispatch_id"]
                or payload.get("code") != command["code"]
                or payload.get("language") != "python"
                or type(payload.get("timeout_seconds")) is not int
                or payload["timeout_seconds"] != command["timeout_seconds"]
            ):
                raise PlatformError(
                    "MANAGER_ACTION_DENIED", "Validation command differs from its frozen intention", 403
                )

    def record(self, handle, index, response):
        with self.owned(handle) as (c, job, now):
            if index != len(job["results"]) or index >= len(job["commands"]):
                raise PlatformError("STALE_GENERATION", "Validation checkpoint is not current", 409)
            command = job["commands"][index]
            if (
                response.get("binding_id") != job["spec"]["binding_id"]
                or response.get("dispatch_id") != command["dispatch_id"]
            ):
                raise PlatformError("MANAGER_RESPONSE_INVALID", "Validation result belongs to a different command", 502)
            skill = self._skill(c, job)
            value = result_value(response)
            if command["kind"] == "runtime":
                if value != runtime_report(skill["package"]):
                    raise PlatformError(
                        "SKILL_RUNTIME_CHECK_FAILED", "Runtime probe did not confirm the locked dependencies", 422
                    )
                receipt = {"kind": "runtime", "passed": True, "report": value}
            elif command["kind"] == "scan":
                expected = {
                    "schema_version": 1,
                    "files": len(skill["package"]["files"]),
                    "python_files": sum(f["path"].endswith(".py") for f in skill["package"]["files"]),
                    "entrypoints": len(skill["package"]["entrypoints"]),
                    "checks": ["bounded-text-package", "python-ast", "entrypoint-signature", "credential-patterns"],
                }
                if value != expected:
                    raise PlatformError("SKILL_SCAN_INVALID", "Scanner did not return the expected package report", 422)
                receipt = {"kind": "scan", "passed": True, "report": value}
            else:
                e = entrypoint(skill, command["entrypoint"])
                value = result_value(response, output_schema=e["output_schema"])
                # Canonical comparison distinguishes booleans from integers and pins exact test expectations.
                if canonical_digest("aio-skill-test-result-v1", value) != canonical_digest(
                    "aio-skill-test-result-v1", e["tests"][command["case"]]["expected"]
                ):
                    raise PlatformError(
                        "SKILL_TEST_MISMATCH", "Skill result did not match its reviewed synthetic test", 422
                    )
                receipt = {
                    "kind": "test",
                    "entrypoint": e["name"],
                    "case": command["case"],
                    "passed": True,
                    "result_digest": canonical_digest("aio-skill-test-result-v1", value),
                }
            c.execute(
                update(s.skill_validation_jobs)
                .where(s.skill_validation_jobs.c.id == job["id"])
                .values(results=[*job["results"], receipt])
            )

    def stopping(self, handle, error_code):
        with self.owned(handle, active=False) as (c, job, now):
            if job["state"] not in {"leased", "stopping"}:
                raise PlatformError("STALE_GENERATION", "Validation is already terminal", 409)
            if error_code is None:
                try:
                    self._actor(c, job)
                    self._skill(c, job)
                    if (
                        job["lease_expires_at"] <= now
                        or job["deadline_at"] <= now
                        or len(job["results"]) != len(job["commands"])
                    ):
                        raise PlatformError("VALIDATION_INCOMPLETE", "Validation was not fully confirmed", 409)
                except PlatformError as exc:
                    error_code = exc.code
            c.execute(
                update(s.skill_validation_jobs)
                .where(s.skill_validation_jobs.c.id == job["id"])
                .values(state="stopping", error_code=error_code)
            )
            return job["spec"]

    @staticmethod
    def _finish(c, job, now, success, cleaned, error_code):
        state = "passed" if success and cleaned else "failed" if cleaned else "stopping"
        c.execute(
            update(s.skill_validation_jobs)
            .where(s.skill_validation_jobs.c.org_id == job["org_id"], s.skill_validation_jobs.c.id == job["id"])
            .values(
                state=state,
                cleanup_state="confirmed" if cleaned else "pending",
                error_code=error_code,
                finished_at=now if cleaned else None,
                lease_expires_at=now,
            )
        )
        if cleaned:
            c.execute(
                update(s.skill_versions)
                .where(
                    s.skill_versions.c.org_id == job["org_id"],
                    s.skill_versions.c.id == job["skill_id"],
                    s.skill_versions.c.validation_job_id == job["id"],
                    s.skill_versions.c.state == "validating",
                )
                .values(state="validated" if success else "rejected", revision=s.skill_versions.c.revision + 1)
            )

    def finish(self, handle, response):
        with self.owned(handle, active=False) as (c, job, now):
            if job["state"] != "stopping":
                raise PlatformError("STALE_GENERATION", "Validation must enter cleanup before finishing", 409)
            if response.get("binding_id") != job["spec"]["binding_id"] or response.get("state") != "destroyed":
                raise PlatformError("CLEANUP_UNCONFIRMED", "Validation cell cleanup was not confirmed", 503)
            error = job["error_code"]
            if error is None:
                try:
                    self._actor(c, job)
                    self._skill(c, job)
                    if len(job["results"]) != len(job["commands"]) or not job["commands"]:
                        raise PlatformError("VALIDATION_INCOMPLETE", "Validation results are incomplete", 409)
                except PlatformError as exc:
                    error = exc.code
            self._finish(c, job, now, error is None, True, error)
            return {"id": job["id"], "state": "passed" if error is None else "failed", "cleanup_state": "confirmed"}

    def recover_one(self, org_id, worker_id):
        with self.db.scoped(org_id, UUID(int=0)) as c:
            now = db_now(c)
            job = (
                c.execute(
                    select(s.skill_validation_jobs)
                    .where(
                        s.skill_validation_jobs.c.org_id == org_id,
                        s.skill_validation_jobs.c.state.in_(["leased", "stopping"]),
                        or_(
                            s.skill_validation_jobs.c.lease_expires_at <= now,
                            (s.skill_validation_jobs.c.state == "leased")
                            & (s.skill_validation_jobs.c.deadline_at <= now),
                        ),
                    )
                    .order_by(s.skill_validation_jobs.c.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .first()
            )
            if job is None:
                return None
            values = dict(
                state="stopping",
                generation=job["generation"] + 1,
                lease_owner=worker_id,
                lease_expires_at=now + timedelta(seconds=self.settings.lease_seconds),
                error_code=job["error_code"] or "VALIDATION_INTERRUPTED",
            )
            c.execute(update(s.skill_validation_jobs).where(s.skill_validation_jobs.c.id == job["id"]).values(**values))
            return {**dict(job), **values}
