"""Idempotent manager lifecycle with bounded persistent outcomes and hard deadlines."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Protocol

from .contracts import CellSpec, ExecuteRequest, ManagerError, Profile, digest
from .docker_backend import DockerBackend
from .journal import Journal


class AuthorizationGuard(Protocol):
    def validate(self, operation: str, payload: dict) -> None: ...


class SandboxManager:
    def __init__(
        self,
        journal: Journal,
        backend: DockerBackend,
        profiles: dict[str, Profile],
        guard: AuthorizationGuard,
        *,
        max_cells: int = 8,
        max_memory_bytes: int = 2 * 1024 * 1024 * 1024,
        max_nano_cpus: int = 4_000_000_000,
        runtime_keys: dict | None = None,
        allow_test_runtimes: bool = False,
    ):
        self.journal, self.backend, self.profiles, self.guard = journal, backend, dict(profiles), guard
        self.max_cells, self.max_memory_bytes, self.max_nano_cpus = max_cells, max_memory_bytes, max_nano_cpus
        self.runtime_keys = dict(runtime_keys or {})
        self.allow_test_runtimes = allow_test_runtimes
        self._stop = threading.Event()
        self._reaper = None
        with self.journal.connect() as c:
            c.execute("UPDATE commands SET state='unknown' WHERE state='started'")
            c.execute(
                "UPDATE cells SET state='quarantined',busy=0 WHERE busy=1 OR state IN ('provisioning','exporting')"
            )

    def _profile(self, spec: CellSpec) -> Profile:
        stdio = getattr(self, "stdio", None)
        if stdio and spec.profile_id in stdio.profiles and getattr(spec, "kind", None) != "mcp_stdio":
            raise ManagerError(
                "PROFILE_NOT_APPROVED", "Credential-bearing profiles cannot be used as general compute", 403
            )
        profile = self.profiles.get(spec.profile_id)
        if profile is None or profile.image_digest != spec.image_digest:
            raise ManagerError("PROFILE_NOT_APPROVED", "Execution requires an operator-approved image/profile", 403)
        if profile.runtime_approval is not None:
            from aio_runtime_policy import verify_approval, RuntimePolicyError

            try:
                verify_approval(
                    profile.runtime_approval,
                    profile.image_digest,
                    self.runtime_keys,
                    allow_test=self.allow_test_runtimes,
                )
            except RuntimePolicyError:
                raise ManagerError(
                    "RUNTIME_APPROVAL_DENIED", "Dependency runtime approval is no longer valid", 403
                ) from None
        return profile

    @staticmethod
    def _active_deadline(spec):
        remaining = (spec.deadline - datetime.now(timezone.utc)).total_seconds()
        if not 0 < remaining <= 3600:
            raise ManagerError("CELL_EXPIRED", "Cell deadline is expired or outside the maximum lease", 409)

    @staticmethod
    def _retained_bytes(c):
        cells = c.execute(
            "SELECT coalesce(sum(length(cast(spec_json AS BLOB))+coalesce(length(cast(export_json AS BLOB)),0)),0) FROM cells"
        ).fetchone()[0]
        commands = c.execute("SELECT coalesce(sum(length(cast(result_json AS BLOB))),0) FROM commands").fetchone()[0]
        return cells + commands

    def ensure(self, spec: CellSpec) -> dict:
        profile = self._profile(spec)
        self._active_deadline(spec)
        self.guard.validate("ensure", {"spec": spec.model_dump(mode="json")})
        with self.journal.connect() as c:
            row = c.execute("SELECT * FROM cells WHERE binding_id=?", (str(spec.binding_id),)).fetchone()
            if row:
                if row["spec_digest"] != spec.spec_digest:
                    raise ManagerError(
                        "CELL_SPEC_CONFLICT", "Existing binding identifies a different immutable spec", 409
                    )
                if row["state"] == "provisioning" or row["busy"]:
                    raise ManagerError("CELL_BUSY", "Cell allocation or execution is already in progress", 409)
                if row["state"] != "ready":
                    raise ManagerError("CELL_NOT_ACTIVE", "Binding is not available for reuse", 409)
            else:
                if (
                    self._retained_bytes(c) + len(spec.model_dump_json().encode("utf-8")) + profile.artifact_bytes * 2
                    > 128 * 1024 * 1024
                ):
                    raise ManagerError(
                        "MANAGER_STORAGE_QUOTA", "Retained execution data has reached its storage budget", 429
                    )
                if c.execute("SELECT count(*) FROM cells").fetchone()[0] >= 10000:
                    raise ManagerError("MANAGER_HISTORY_QUOTA", "Manager history requires retention cleanup", 429)
                active = c.execute("SELECT profile FROM cells WHERE state NOT IN ('destroyed','exported')").fetchall()
                if any(r["profile"] not in self.profiles for r in active):
                    raise ManagerError(
                        "PROFILE_STILL_IN_USE", "Retired profile resources must be reclaimed before allocation", 503
                    )
                memory = sum(self.profiles[r["profile"]].memory_bytes for r in active if r["profile"] in self.profiles)
                cpu = sum(self.profiles[r["profile"]].nano_cpus for r in active if r["profile"] in self.profiles)
                if (
                    len(active) >= self.max_cells
                    or memory + profile.memory_bytes > self.max_memory_bytes
                    or cpu + profile.nano_cpus > self.max_nano_cpus
                ):
                    raise ManagerError(
                        "CELL_CAPACITY_EXCEEDED", "No isolated execution capacity is currently available", 429
                    )
                c.execute(
                    "INSERT INTO cells(binding_id,org_id,run_id,generation,slot,profile,spec_digest,spec_json,state,deadline,busy) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,1)",
                    (
                        str(spec.binding_id),
                        str(spec.org_id),
                        str(spec.run_id),
                        spec.generation,
                        spec.target_slot,
                        spec.profile_id,
                        spec.spec_digest,
                        spec.model_dump_json(),
                        "provisioning",
                        spec.deadline.timestamp(),
                    ),
                )
        if row:
            existing = self.backend.checked(spec, row["container_id"])
            if existing is None or existing.status != "running":
                raise ManagerError("CELL_LOST", "Do not recreate a cell whose process/filesystem state was lost", 409)
            self.backend.verify(existing, profile)
            self.backend.workspace_volume(spec, profile)
            return {
                "binding_id": str(spec.binding_id),
                "container_id": existing.id,
                "state": "ready",
                "spec_digest": spec.spec_digest,
            }
        container = None
        try:
            container = self.backend.create(spec, profile)
            with self.journal.connect() as c:
                c.execute(
                    "UPDATE cells SET container_id=?,state='ready',busy=0 WHERE binding_id=? AND state='provisioning'",
                    (container.id, str(spec.binding_id)),
                )
            return {
                "binding_id": str(spec.binding_id),
                "container_id": container.id,
                "state": "ready",
                "spec_digest": spec.spec_digest,
            }
        except Exception:
            try:
                self.backend.destroy(spec, container.id if container else None)
            except Exception:
                with self.journal.connect() as c:
                    c.execute(
                        "UPDATE cells SET state='quarantined',error_code='PROVISION_FAILED' WHERE binding_id=?",
                        (str(spec.binding_id),),
                    )
            else:
                with self.journal.connect() as c:
                    c.execute(
                        "UPDATE cells SET state='destroyed',error_code='PROVISION_FAILED' WHERE binding_id=?",
                        (str(spec.binding_id),),
                    )
            raise

    def execute(self, request: ExecuteRequest) -> dict:
        spec = request.spec
        profile = self._profile(spec)
        self._active_deadline(spec)
        payload = request.model_dump(mode="json")
        self.guard.validate("execute", payload)
        row = self.journal.cell(spec.binding_id)
        if row is None or row["spec_digest"] != spec.spec_digest:
            raise ManagerError("CELL_NOT_FOUND", "Binding has not been prepared by this manager", 404)
        request_hash = digest("aio-cell-command-v1", payload)
        with self.journal.connect() as c:
            prior = c.execute("SELECT * FROM commands WHERE dispatch_id=?", (str(request.dispatch_id),)).fetchone()
            if prior:
                if prior["binding_id"] != str(spec.binding_id) or prior["request_digest"] != request_hash:
                    raise ManagerError("COMMAND_CONFLICT", "Dispatch ID identifies different execution contents", 409)
                if prior["state"] == "done":
                    return json.loads(prior["result_json"])
                raise ManagerError(
                    "EXECUTION_OUTCOME_UNKNOWN", "A previous execution may already have started; do not repeat it", 409
                )
            claimed = c.execute(
                "UPDATE cells SET busy=1 WHERE binding_id=? AND state='ready' AND busy=0", (str(spec.binding_id),)
            ).rowcount
            if not claimed:
                raise ManagerError("CELL_BUSY", "Cell is not ready for another concurrent command", 409)
            c.execute(
                "INSERT INTO commands(dispatch_id,binding_id,request_digest,state) VALUES (?,?,?,'started')",
                (str(request.dispatch_id), str(spec.binding_id), request_hash),
            )
        last_auth = 0.0

        def cancelled():
            nonlocal last_auth
            current = self.journal.cell(spec.binding_id)
            if self._stop.is_set() or not current or current["state"] != "ready":
                return True
            now = time.monotonic()
            if now - last_auth >= 1.0:
                last_auth = now
                try:
                    self.guard.validate("execute", payload)
                except Exception:
                    return True
            return False

        try:
            result = self.backend.execute(request, profile, row["container_id"], cancelled)
            if result.get("error_code"):
                self.backend.destroy(spec, row["container_id"])
            result = {**result, "binding_id": str(spec.binding_id), "dispatch_id": str(request.dispatch_id)}
            with self.journal.connect() as c:
                if (
                    self._retained_bytes(c) + len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
                    > 128 * 1024 * 1024
                ):
                    raise ManagerError("MANAGER_STORAGE_QUOTA", "Command result retention is full", 429)
                c.execute(
                    "UPDATE commands SET state='done',result_json=? WHERE dispatch_id=?",
                    (json.dumps(result, ensure_ascii=False), str(request.dispatch_id)),
                )
                if result.get("error_code"):
                    c.execute(
                        "UPDATE cells SET state='destroyed',busy=0,spec_json='' WHERE binding_id=?",
                        (str(spec.binding_id),),
                    )
                else:
                    c.execute("UPDATE cells SET busy=0 WHERE binding_id=?", (str(spec.binding_id),))
            return result
        except Exception:
            with self.journal.connect() as c:
                c.execute("UPDATE commands SET state='unknown' WHERE dispatch_id=?", (str(request.dispatch_id),))
                c.execute("UPDATE cells SET state='quarantined',busy=0 WHERE binding_id=?", (str(spec.binding_id),))
            try:
                self.backend.destroy(spec, row["container_id"])
            except Exception:
                pass
            raise

    def finalize(self, spec: CellSpec) -> dict:
        return self._export(spec, "finalize")

    def checkpoint(self, spec: CellSpec) -> dict:
        return self._export(spec, "checkpoint")

    def _export(self, spec: CellSpec, operation: str) -> dict:
        profile = self._profile(spec)
        self.guard.validate(operation, {"spec": spec.model_dump(mode="json")})
        with self.journal.connect() as c:
            row = c.execute("SELECT * FROM cells WHERE binding_id=?", (str(spec.binding_id),)).fetchone()
            if row is None or row["spec_digest"] != spec.spec_digest:
                raise ManagerError("CELL_NOT_FOUND", "Cell does not match this binding", 404)
            if (row["export_json"] is not None or row["export_operation"] is not None) and (
                row["export_operation"] or "finalize"
            ) != operation:
                raise ManagerError(
                    "EXPORT_PURPOSE_CONFLICT", "An export cannot be repurposed for another control action", 409
                )
            if row["state"] == "exported":
                if not row["export_json"]:
                    raise ManagerError("EXPORT_EXPIRED", "Finalized output is no longer retained", 410)
                return json.loads(row["export_json"])
            if row["export_json"] is None:
                claimed = c.execute(
                    "UPDATE cells SET busy=1,state='exporting',export_operation=? WHERE binding_id=? AND state='ready' AND busy=0",
                    (operation, str(spec.binding_id)),
                ).rowcount
                if not claimed:
                    raise ManagerError("CELL_BUSY", "Cell cannot be finalized during execution", 409)
        try:
            if row["export_json"]:
                result = json.loads(row["export_json"])
            else:
                files = self.backend.export_files(spec, profile, row["container_id"])
                result = {
                    "binding_id": str(spec.binding_id),
                    "spec_digest": spec.spec_digest,
                    "files": files,
                    "state": "destroyed",
                }
                with self.journal.connect() as c:
                    retained = self._retained_bytes(c)
                    if retained + len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 128 * 1024 * 1024:
                        raise ManagerError(
                            "EXPORT_STORAGE_QUOTA", "Manager retained exports reached their capacity limit", 429
                        )
                    c.execute(
                        "UPDATE cells SET export_json=? WHERE binding_id=?",
                        (json.dumps(result, ensure_ascii=False), str(spec.binding_id)),
                    )
            self.backend.destroy(spec, row["container_id"])
            with self.journal.connect() as c:
                c.execute(
                    "UPDATE cells SET state='exported',busy=0,spec_json='' WHERE binding_id=?", (str(spec.binding_id),)
                )
            return result
        except Exception:
            try:
                self.backend.destroy(spec, row["container_id"])
            except Exception:
                state = "quarantined"
            else:
                state = "destroyed"
            with self.journal.connect() as c:
                c.execute(
                    "UPDATE cells SET state=?,busy=0,error_code=? WHERE binding_id=?",
                    (state, "EXPORT_FAILED", str(spec.binding_id)),
                )
            raise

    def acknowledge(self, spec: CellSpec) -> dict:
        self.guard.validate("acknowledge", {"spec": spec.model_dump(mode="json")})
        with self.journal.connect() as c:
            row = c.execute("SELECT * FROM cells WHERE binding_id=?", (str(spec.binding_id),)).fetchone()
            if row is None:
                return {"binding_id": str(spec.binding_id), "state": "acknowledged"}
            if row["spec_digest"] != spec.spec_digest or row["state"] not in {"exported", "destroyed"}:
                raise ManagerError("CELL_NOT_RETIRED", "Only externally retired execution payloads can be purged", 409)
            c.execute("UPDATE cells SET export_json=NULL,spec_json='' WHERE binding_id=?", (str(spec.binding_id),))
            c.execute("UPDATE commands SET result_json=NULL WHERE binding_id=?", (str(spec.binding_id),))
        return {"binding_id": str(spec.binding_id), "state": "acknowledged"}

    def stop(self, spec: CellSpec) -> dict:
        self.guard.validate("stop", {"spec": spec.model_dump(mode="json")})
        row = self.journal.cell(spec.binding_id)
        if row and row["spec_digest"] != spec.spec_digest:
            raise ManagerError("CELL_SPEC_CONFLICT", "Binding spec changed", 409)
        self.backend.destroy(spec, row["container_id"] if row else None)
        if row:
            with self.journal.connect() as c:
                c.execute(
                    "UPDATE cells SET state=CASE WHEN export_json IS NOT NULL THEN 'exported' ELSE 'destroyed' END,busy=0 WHERE binding_id=?",
                    (str(spec.binding_id),),
                )
        return {"binding_id": str(spec.binding_id), "state": "destroyed"}

    def status(self, spec: CellSpec) -> dict:
        self.guard.validate("status", {"spec": spec.model_dump(mode="json")})
        row = self.journal.cell(spec.binding_id)
        if not row or row["spec_digest"] != spec.spec_digest:
            raise ManagerError("CELL_NOT_FOUND", "Cell is not known to this manager", 404)
        actual = self.backend.checked(spec, row["container_id"])
        return {
            "binding_id": str(spec.binding_id),
            "state": row["state"],
            "runtime_present": actual is not None,
            "container_id": row["container_id"],
        }

    def reap(self):
        from .stdio_contracts import decode_spec

        now = time.time()
        for row in self.journal.cells():
            if row["state"] in {"destroyed", "exported"}:
                continue
            spec = decode_spec(row["spec_json"])
            must_stop = row["deadline"] <= now or row["state"] == "quarantined"
            if not must_stop:
                try:
                    self.guard.validate("alive", {"spec": spec.model_dump(mode="json")})
                except Exception:
                    must_stop = True
            if must_stop:
                try:
                    self.backend.destroy(spec, row["container_id"])
                except Exception:
                    continue
                with self.journal.connect() as c:
                    c.execute(
                        "UPDATE cells SET state=CASE WHEN export_json IS NOT NULL THEN 'exported' ELSE 'destroyed' END,busy=0 WHERE binding_id=?",
                        (row["binding_id"],),
                    )
                if getattr(spec, "kind", None) == "mcp_stdio" and getattr(self, "stdio", None):
                    try:
                        self.stdio.after_stop(spec)
                    except Exception:
                        pass
        # Reclaim bounded export/command payloads after a day. Identifiers remain to prevent accidental reuse.
        with self.journal.connect() as c:
            if getattr(self, "stdio", None):
                c.execute(
                    "DELETE FROM stdio_rpcs WHERE binding_id IN (SELECT binding_id FROM cells WHERE deadline<? AND state IN ('destroyed','exported'))",
                    (now - 7 * 86400,),
                )
            c.execute("UPDATE cells SET export_json=NULL WHERE state='exported' AND deadline<?", (now - 86400,))
            c.execute(
                "UPDATE commands SET result_json=NULL,state='expired' WHERE binding_id IN "
                "(SELECT binding_id FROM cells WHERE deadline<?)",
                (now - 86400,),
            )

        with self.journal.connect() as c:
            c.execute(
                "DELETE FROM commands WHERE binding_id IN (SELECT binding_id FROM cells WHERE deadline<? AND state IN ('destroyed','exported'))",
                (now - 7 * 86400,),
            )
            c.execute("DELETE FROM cells WHERE deadline<? AND state IN ('destroyed','exported')", (now - 7 * 86400,))
        if getattr(self, "stdio", None):
            self.stdio.reap()

    def start_reaper(self):
        if self._reaper is not None:
            return

        def run():
            while not self._stop.wait(1):
                try:
                    self.reap()
                except Exception:
                    pass  # Retries retain capacity; no claim that cleanup succeeded.

        self._reaper = threading.Thread(target=run, daemon=True)
        self._reaper.start()

    def close(self):
        from .stdio_contracts import decode_spec

        self._stop.set()
        if self._reaper:
            self._reaper.join(timeout=3)
        if getattr(self, "stdio", None):
            self.stdio.close()
        for row in self.journal.cells():
            if row["state"] not in {"destroyed", "exported"}:
                spec = decode_spec(row["spec_json"])
                try:
                    self.backend.destroy(spec, row["container_id"])
                except Exception:
                    continue
                with self.journal.connect() as c:
                    c.execute(
                        "UPDATE cells SET state='destroyed',busy=0,spec_json='' WHERE binding_id=?",
                        (row["binding_id"],),
                    )
        self.backend.close()
        close_guard = getattr(self.guard, "close", None)
        if close_guard:
            close_guard()
        self.journal.close()
