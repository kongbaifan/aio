"""Fenced archive import queue and exact Manager authority. No archive parsing on this host."""

import base64
from contextlib import contextmanager
from datetime import timedelta, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select, update, or_, null

from ..admin.service import AdminService
from ..auth.principal import Principal
from ..db import schema as s
from ..platform_errors import PlatformError
from ..policy.repository import current_facts, db_now, lock_resource_rows, require_resource
from ..runtime.actions import canonical_digest, strict_json
from ..workspaces.exports import prepare_export
from .archive_commands import archive_code, archive_receipt
from .archive_contracts import IMPORT_DEADLINE_SECONDS, MAX_PACKAGE_BYTES, SCAN_TIMEOUT_SECONDS
from .archive_service import TERMINAL_IMPORTS
from .contracts import SkillCreate


class SkillArchiveJobs:
    def __init__(self, service):
        self.service, self.db, self.settings = service, service.db, service.settings

    @staticmethod
    def principal(row):
        return Principal(
            row["org_id"],
            row["requested_by"],
            row["membership_revision"],
            service_actor_id=row["lease_owner"] or "skill-import",
        )

    def actor(self, c, row):
        p = self.principal(row)
        current_facts(c, p, lock=True)
        if AdminService.role(c, p) != "org_admin":
            raise PlatformError("ADMIN_FORBIDDEN", "Archive author no longer has publication privileges", 403)
        require_resource(c, p, row["id"], "skill_import.update")
        if row["purge_requested"] or row["archive_purged"]:
            raise PlatformError("SKILL_IMPORT_CANCELLED", "This Skill archive import was cancelled", 409)
        scanner = self.service.enabled()
        if scanner["id"] != row["scanner_profile"] or scanner["image_digest"] != row["scanner_image"]:
            raise PlatformError("SKILL_IMPORT_PROFILE_UNAVAILABLE", "The archive scanner approval changed", 403)
        self.service.profile(row["execution_profile"], row["execution_image"])
        if row["request_digest"] != canonical_digest("aio-skill-import-request-v1", row["request"]):
            raise PlatformError("SKILL_IMPORT_INTENT_CHANGED", "Immutable archive metadata changed", 409)
        return p

    @contextmanager
    def owned(self, handle, *, active=True):
        org, id = handle["org_id"], handle["id"]
        with self.db.scoped(org, UUID(int=0)) as c:
            # These jobs have small bounded local blob/catalog writes as well
            # as cleanup; take the storage/administration order from the start.
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == org).with_for_update()).one()
            lock_resource_rows(c, org, [id])
            row = self.service.row(c, org, id, lock=True)
            now = db_now(c)
            if row["generation"] != handle["generation"] or row["lease_owner"] != handle["lease_owner"]:
                raise PlatformError("STALE_GENERATION", "Skill import lease changed", 409)
            if active:
                if (
                    row["state"] != "leased"
                    or not row["lease_expires_at"]
                    or row["lease_expires_at"] <= now
                    or row["deadline_at"] <= now
                ):
                    raise PlatformError("STALE_GENERATION", "Skill import is not actively leased", 409)
                self.actor(c, row)
            yield c, row, now

    @staticmethod
    def change(c, row, now, **values):
        values.update(revision=row["revision"] + 1, updated_at=now)
        c.execute(
            update(s.skill_imports)
            .where(s.skill_imports.c.org_id == row["org_id"], s.skill_imports.c.id == row["id"])
            .values(**values)
        )
        return {**row, **values}

    def claim(self, org, worker):
        with self.db.scoped(org, UUID(int=0)) as c:
            ids = (
                c.execute(
                    select(s.skill_imports.c.id)
                    .where(
                        s.skill_imports.c.org_id == org,
                        s.skill_imports.c.state == "queued",
                    )
                    .order_by(s.skill_imports.c.created_at)
                    .limit(20)
                )
                .scalars()
                .all()
            )
        for id in ids:
            with self.db.scoped(org, UUID(int=0)) as c:
                c.execute(select(s.organizations.c.id).where(s.organizations.c.id == org).with_for_update()).one()
                lock_resource_rows(c, org, [id])
                row = self.service.row(c, org, id, lock=True)
                if row["state"] != "queued":
                    continue
                now = db_now(c)
                try:
                    self.actor(c, row)
                    if row["queue_expires_at"] <= now or not row["uploaded_at"]:
                        raise PlatformError("SKILL_IMPORT_EXPIRED", "Skill archive expired before scanning", 409)
                except PlatformError as error:
                    self.change(c, row, now, state="rejected", error_code=error.code, finished_at=now)
                    continue
                return self.change(
                    c,
                    row,
                    now,
                    state="leased",
                    lease_owner=worker,
                    generation=row["generation"] + 1,
                    lease_expires_at=now + timedelta(seconds=self.settings.lease_seconds),
                    deadline_at=now + timedelta(seconds=IMPORT_DEADLINE_SECONDS),
                )
        return None

    def prepare(self, handle):
        with self.owned(handle) as (_, row, __):
            sha, size = row["archive_sha256"], row["archive_size"]
        raw = self.service.blobs.get(handle["org_id"], sha, size)
        with self.owned(handle) as (c, row, now):
            if row["spec"] is not None:
                return row
            profile = self.service.profile(row["scanner_profile"], row["scanner_image"])
            spec = {
                "schema_version": 1,
                "binding_id": str(uuid4()),
                "org_id": str(row["org_id"]),
                "run_id": str(row["id"]),
                "generation": row["generation"],
                "target_slot": "skill/archive-import",
                "profile_id": row["scanner_profile"],
                "image_digest": row["scanner_image"],
                "deadline": row["deadline_at"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "inputs": [
                    {"path": "archive.bin", "sha256": sha, "content_b64": base64.b64encode(raw).decode("ascii")}
                ],
            }
            command = {
                "dispatch_id": str(uuid4()),
                "code": archive_code(row["request"]),
                "timeout_seconds": min(SCAN_TIMEOUT_SECONDS, profile.get("max_timeout_seconds", 120)),
            }
            return self.change(
                c,
                row,
                now,
                spec=spec,
                spec_digest=canonical_digest("aio-cell-spec-v1", spec),
                command=command,
                cleanup_state="pending",
                manager_acknowledged=False,
            )

    def pulse(self, handle):
        with self.owned(handle) as (c, row, now):
            self.change(
                c,
                row,
                now,
                lease_expires_at=min(row["deadline_at"], now + timedelta(seconds=self.settings.lease_seconds)),
            )

    def authorize(self, operation, payload):
        spec = payload.get("spec")
        try:
            org, id = UUID(spec["org_id"]), UUID(spec["run_id"])
        except (KeyError, TypeError, ValueError):
            raise PlatformError("MANAGER_ACTION_DENIED", "Archive execution scope is invalid", 403) from None
        with self.db.scoped(org, UUID(int=0)) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == org).with_for_update(read=True)).one()
            lock_resource_rows(c, org, [id])
            row = self.service.row(c, org, id, lock=True)
            if (
                spec.get("target_slot") != "skill/archive-import"
                or not row["spec_digest"]
                or row["spec_digest"] != canonical_digest("aio-cell-spec-v1", spec)
            ):
                raise PlatformError("MANAGER_ACTION_DENIED", "Archive cell does not match its frozen intention", 403)
            if operation in {"stop", "status"}:
                return
            if operation == "acknowledge":
                if row["cleanup_state"] != "confirmed":
                    raise PlatformError(
                        "CLEANUP_UNCONFIRMED", "Archive payload cannot be purged before cleanup confirmation", 409
                    )
                return
            now = db_now(c)
            if (
                row["state"] != "leased"
                or row["generation"] != spec["generation"]
                or row["lease_expires_at"] <= now
                or row["deadline_at"] <= now
            ):
                raise PlatformError("MANAGER_ACTION_DENIED", "Archive execution lease is obsolete", 403)
            self.actor(c, row)
            if operation in {"ensure", "alive"}:
                return
            if operation == "finalize" and row["scan_receipt"] and row["candidate"] is None:
                return
            command = row["command"]
            if (
                operation != "execute"
                or row["scan_receipt"] is not None
                or not command
                or (
                    payload.get("dispatch_id") != command["dispatch_id"]
                    or payload.get("code") != command["code"]
                    or payload.get("language") != "python"
                    or type(payload.get("timeout_seconds")) is not int
                    or payload["timeout_seconds"] != command["timeout_seconds"]
                )
            ):
                raise PlatformError(
                    "MANAGER_ACTION_DENIED", "Only the frozen isolated archive scanner can execute", 403
                )

    def scanned(self, handle, response):
        with self.owned(handle) as (c, row, now):
            if (
                response.get("binding_id") != row["spec"]["binding_id"]
                or response.get("dispatch_id") != row["command"]["dispatch_id"]
            ):
                raise PlatformError("MANAGER_RESPONSE_INVALID", "Archive response belongs to a different command", 502)
            receipt = archive_receipt(response, row["archive_sha256"])
            if row["scan_receipt"] is not None and row["scan_receipt"] != receipt:
                raise PlatformError("SKILL_IMPORT_RESULT_CHANGED", "The scan receipt changed", 409)
            self.change(c, row, now, scan_receipt=receipt)

    def candidate(self, handle, response):
        # Only bounded JSON from a stopped cell is decoded here, never the raw archive.
        files, _ = prepare_export(response.get("files"))
        if len(files) != 1 or files[0]["path"] != "package.json" or files[0]["bytes"] > MAX_PACKAGE_BYTES:
            raise PlatformError(
                "SKILL_IMPORT_RESULT_INVALID", "Archive scanner must export one bounded package file", 422
            )
        try:
            package = SkillCreate.model_validate(
                {
                    "package": strict_json(files[0]["data"], max_bytes=MAX_PACKAGE_BYTES),
                    "sandbox_profile": handle["execution_profile"],
                }
            ).package
        except ValidationError:
            raise PlatformError(
                "SKILL_IMPORT_PACKAGE_INVALID", "The archive does not describe a valid text Skill package", 422
            ) from None
        with self.owned(handle) as (c, row, now):
            receipt = row["scan_receipt"]
            if (
                not receipt
                or response.get("state") != "destroyed"
                or response.get("binding_id") != row["spec"]["binding_id"]
                or response.get("spec_digest") != row["spec_digest"]
            ):
                raise PlatformError(
                    "MANAGER_RESPONSE_INVALID", "Archive export did not confirm its retired writer", 502
                )
            if (
                files[0]["sha256"] != receipt["package_sha256"]
                or files[0]["bytes"] != receipt["package_bytes"]
                or len(package.files) != receipt["files"]
            ):
                raise PlatformError(
                    "SKILL_IMPORT_RESULT_INVALID", "Archive package bytes differ from the scan receipt", 422
                )
            self.change(
                c,
                row,
                now,
                candidate=package.normalized(),
                candidate_digest=package.digest(),
                cleanup_state="confirmed",
            )

    def stopping(self, handle, error):
        with self.owned(handle, active=False) as (c, row, now):
            if row["state"] in TERMINAL_IMPORTS:
                return row
            if row["state"] not in {"leased", "stopping"}:
                raise PlatformError("STALE_GENERATION", "Import is not executing or cleaning up", 409)
            error = row["error_code"] or error
            if error is None:
                try:
                    self.actor(c, row)
                    if row["candidate"] is None or row["cleanup_state"] != "confirmed":
                        raise PlatformError(
                            "SKILL_IMPORT_INCOMPLETE", "No complete isolated archive result is available", 409
                        )
                except PlatformError as failure:
                    error = failure.code
            return self.change(
                c,
                row,
                now,
                state="stopping",
                error_code=error,
                lease_expires_at=now + timedelta(seconds=self.settings.lease_seconds),
            )

    def stopped(self, handle, response):
        with self.owned(handle, active=False) as (c, row, now):
            spec = handle.get("spec")
            if (
                row["state"] != "stopping"
                or spec is None
                or row["spec_digest"] != canonical_digest("aio-cell-spec-v1", spec)
                or response.get("state") != "destroyed"
                or response.get("binding_id") != spec["binding_id"]
            ):
                raise PlatformError(
                    "CLEANUP_UNCONFIRMED", "Archive cleanup was not confirmed for its exact binding", 409
                )
            return self.change(c, row, now, cleanup_state="confirmed")

    def acknowledged(self, handle, response):
        with self.owned(handle, active=False) as (c, row, now):
            spec = handle.get("spec")
            if (
                row["cleanup_state"] != "confirmed"
                or spec is None
                or row["spec_digest"] != canonical_digest("aio-cell-spec-v1", spec)
                or response.get("state") != "acknowledged"
                or response.get("binding_id") != spec["binding_id"]
            ):
                raise PlatformError("CLEANUP_UNCONFIRMED", "Archive payload acknowledgement was not confirmed", 409)
            return self.change(c, row, now, manager_acknowledged=True, spec=null(), command=null())

    def finish(self, handle):
        with self.owned(handle, active=False) as (c, row, now):
            if row["state"] in TERMINAL_IMPORTS:
                return self.service.metadata(row)
            if row["state"] != "stopping" or row["cleanup_state"] != "confirmed" or not row["manager_acknowledged"]:
                raise PlatformError(
                    "CLEANUP_UNCONFIRMED", "Import must confirm both execution and payload cleanup", 409
                )
            error, skill = row["error_code"], None
            if error is None:
                try:
                    p = self.actor(c, row)
                    if row["candidate"] is None:
                        raise PlatformError("SKILL_IMPORT_INCOMPLETE", "Import has no verified package", 409)
                    body = SkillCreate(package=row["candidate"], sandbox_profile=row["execution_profile"])
                    if body.package.digest() != row["candidate_digest"]:
                        raise PlatformError("SKILL_IMPORT_RESULT_CHANGED", "The immutable candidate changed", 409)
                    with c.begin_nested():
                        skill = self.service.skills.create_draft(c, p, body, expected_image=row["execution_image"])
                except (ValidationError, PlatformError) as failure:
                    error = failure.code if isinstance(failure, PlatformError) else "SKILL_IMPORT_PACKAGE_INVALID"
            state = "imported" if skill else "cancelled" if row["purge_requested"] else "rejected"
            final = self.change(
                c,
                row,
                now,
                state=state,
                skill_id=skill["id"] if skill else None,
                error_code=error,
                finished_at=now,
                candidate=null(),
                lease_expires_at=now,
            )
            self.service.admin.audit(
                c,
                self.principal(row),
                "skill.archive.finish",
                row["id"],
                state,
                {"skill_id": str(skill["id"])} if skill else {},
            )
            # Re-read converts SQL NULL sentinels to normal Python values.
            return self.service.metadata(self.service.row(c, row["org_id"], final["id"]))

    def recover(self, org, worker):
        with self.db.scoped(org, UUID(int=0)) as c:
            now = db_now(c)
            ids = (
                c.execute(
                    select(s.skill_imports.c.id)
                    .where(
                        s.skill_imports.c.org_id == org,
                        or_(
                            s.skill_imports.c.state.in_(["leased", "stopping"])
                            & (
                                (s.skill_imports.c.lease_expires_at <= now)
                                | ((s.skill_imports.c.state == "leased") & (s.skill_imports.c.deadline_at <= now))
                            ),
                            s.skill_imports.c.state.in_(["awaiting_upload", "uploading", "queued"])
                            & (s.skill_imports.c.queue_expires_at <= now),
                        ),
                    )
                    .order_by(s.skill_imports.c.created_at)
                    .limit(20)
                )
                .scalars()
                .all()
            )
        for id in ids:
            with self.db.scoped(org, UUID(int=0)) as c:
                c.execute(select(s.organizations.c.id).where(s.organizations.c.id == org).with_for_update()).one()
                lock_resource_rows(c, org, [id])
                row = self.service.row(c, org, id, lock=True)
                now = db_now(c)
                if row["state"] in {"awaiting_upload", "uploading", "queued"}:
                    if row["queue_expires_at"] <= now:
                        self.change(
                            c,
                            row,
                            now,
                            state="cancelled",
                            purge_requested=True,
                            error_code="SKILL_IMPORT_EXPIRED",
                            finished_at=now,
                        )
                    continue
                if row["state"] not in {"leased", "stopping"}:
                    continue
                if row["lease_expires_at"] > now and (row["state"] == "stopping" or row["deadline_at"] > now):
                    continue
                error = row["error_code"]
                if row["state"] == "leased" or row["candidate"] is None:
                    error = error or "SKILL_IMPORT_INTERRUPTED"
                return self.change(
                    c,
                    row,
                    now,
                    state="stopping",
                    generation=row["generation"] + 1,
                    lease_owner=worker,
                    lease_expires_at=now + timedelta(seconds=self.settings.lease_seconds),
                    error_code=error,
                )
        return None
