"""Manager-only credential-bearing MCP process owner; no transcripts/secrets in the journal."""

import threading
import time
from weakref import WeakValueDictionary

from .contracts import ManagerError, digest
from .stdio_process import DockerStdioProcess
from .stdio_inputs import initial_files


class StdioManager:
    def __init__(self, core, profiles):
        self.core, self.profiles = core, dict(profiles)
        self.sessions = {}
        self._locks = WeakValueDictionary()
        self._mutex = threading.Lock()
        for id, profile in self.profiles.items():
            if id in core.profiles and core.profiles[id] != profile.resources():
                raise ValueError("Stdio and compute profiles must not collide")
            core.profiles[id] = profile.resources()
        core.stdio = self
        with core.journal.connect() as c:
            c.executescript("""CREATE TABLE IF NOT EXISTS stdio_rpcs(
                request_id TEXT PRIMARY KEY,binding_id TEXT NOT NULL,request_digest TEXT NOT NULL,
                state TEXT NOT NULL,result_digest TEXT,error_code TEXT,
                FOREIGN KEY(binding_id) REFERENCES cells(binding_id));""")
            c.execute("UPDATE stdio_rpcs SET state='unknown',error_code='STDIO_MANAGER_RESTARTED' WHERE state='sent'")
            # An old socket/process session is not silently adopted after a manager restart.
            c.execute(
                "UPDATE cells SET state='quarantined',busy=0 WHERE slot LIKE 'connector/stdio/%' AND state NOT IN ('destroyed','exported')"
            )

    def lock(self, id):
        with self._mutex:
            return self._locks.setdefault(str(id), threading.RLock())

    def profile(self, spec):
        profile = self.profiles.get(spec.profile_id)
        if (
            profile is None
            or profile.image_digest != spec.image_digest
            or profile.template_digest != spec.template_digest
            or (spec.schema_version == 2) != (profile.input_policy == "run_attachments")
        ):
            raise ManagerError(
                "STDIO_TEMPLATE_NOT_APPROVED", "MCP startup requires a fixed approved image/template", 403
            )
        return profile

    def open(self, request):
        spec = request.spec
        with self.lock(spec.binding_id):
            profile = self.profile(spec)
            self.core._active_deadline(spec)
            payload = {**request.authority(), "manager_id": self.core.journal.installation_id}
            self.core.guard.validate("stdio.claim", payload)
            existing = self.sessions.get(str(spec.binding_id))
            if existing:
                if existing.closed.is_set():
                    raise ManagerError("STDIO_SESSION_LOST", "A lost process cannot be silently restarted", 409)
                if request.input_files:
                    raise ManagerError(
                        "STDIO_INPUT_REINJECTION_DENIED", "An active process cannot reimport inputs", 409
                    )
                self.core.ensure(spec)
                return {
                    "binding_id": str(spec.binding_id),
                    "spec_digest": spec.spec_digest,
                    "state": "ready",
                    "manager_id": self.core.journal.installation_id,
                }
            prior = self.core.journal.cell(spec.binding_id)
            if prior:
                raise ManagerError("STDIO_SESSION_LOST", "The original MCP process handle is no longer available", 409)
            inputs = initial_files(spec, request.input_files)
            secret = request.credential.get_secret_value()
            if bool(secret) != bool(profile.credential_env):
                raise ManagerError(
                    "STDIO_CREDENTIAL_POLICY", "MCP credential injection must match its approved template", 403
                )
            image = self.core.backend.client.images.get(spec.image_digest)
            if image.attrs.get("Config", {}).get("Entrypoint"):
                raise ManagerError("STDIO_IMAGE_ENTRYPOINT_DENIED", "The fixed watchdog must be the first process", 403)
            if (
                image.attrs.get("Config", {}).get("Labels", {}).get("aio.mcp.dependency_digest")
                != profile.dependency_digest
            ):
                raise ManagerError(
                    "STDIO_DEPENDENCY_MISMATCH", "Image dependency declaration does not match its fixed template", 403
                )
            result = self.core.ensure(spec)
            process = None
            try:
                if inputs:
                    self.core.backend.initialize_stdio_inputs(spec, profile.resources(), result["container_id"], inputs)
                    self.core.guard.validate("alive", {"spec": spec.model_dump(mode="json")})
                process = DockerStdioProcess(self.core.backend, spec, profile, result["container_id"], secret)
                self.sessions[str(spec.binding_id)] = process
                self.core.guard.validate(
                    "stdio.ready",
                    {
                        "spec": spec.model_dump(mode="json"),
                        "manager_id": self.core.journal.installation_id,
                        "backend_id": result["container_id"],
                    },
                )
            except BaseException:
                try:
                    self.core.stop(spec)
                finally:
                    if process:
                        process.close()
                raise
            return {**result, "manager_id": self.core.journal.installation_id}

    def rpc(self, request):
        spec = request.spec
        profile = self.profile(spec)
        self.core._active_deadline(spec)
        if request.timeout_seconds > profile.max_timeout_seconds:
            raise ManagerError("STDIO_TIMEOUT_POLICY", "RPC timeout exceeds its approved template", 403)
        payload = request.model_dump(mode="json")
        self.core.guard.validate("stdio.rpc", {**payload, "manager_id": self.core.journal.installation_id})
        process = self.sessions.get(str(spec.binding_id))
        if process is None or process.closed.is_set():
            raise (
                process.error
                if process and process.error
                else ManagerError("STDIO_SESSION_LOST", "MCP process is unavailable; do not recreate state", 409)
            )
        fingerprint = digest("aio-stdio-rpc-v1", payload)
        with self.core.journal.connect() as c:
            old = c.execute("SELECT * FROM stdio_rpcs WHERE request_id=?", (str(request.request_id),)).fetchone()
            if old:
                if old["request_digest"] != fingerprint or old["binding_id"] != str(spec.binding_id):
                    raise ManagerError("STDIO_REQUEST_CONFLICT", "RPC identity refers to different content", 409)
                # Results may contain credentials. They are only cached encrypted by the Gateway.
                raise ManagerError("STDIO_RPC_ALREADY_SENT", "This MCP RPC cannot be replayed from the manager", 409)
            if c.execute("SELECT count(*) FROM stdio_rpcs").fetchone()[0] >= 100000:
                raise ManagerError("STDIO_HISTORY_QUOTA", "MCP dispatch metadata retention is full", 429)
            c.execute(
                "INSERT INTO stdio_rpcs(request_id,binding_id,request_digest,state) VALUES (?,?,?,'sent')",
                (str(request.request_id), str(spec.binding_id), fingerprint),
            )
        try:
            response = process.rpc(request.method, request.params, str(request.request_id), request.timeout_seconds)
            self.core.guard.validate("stdio.rpc", {**payload, "manager_id": self.core.journal.installation_id})
            with self.core.journal.connect() as c:
                c.execute(
                    "UPDATE stdio_rpcs SET state='completed',result_digest=? WHERE request_id=?",
                    (digest("aio-stdio-result-v1", response), str(request.request_id)),
                )
            return {"binding_id": str(spec.binding_id), "request_id": str(request.request_id), "response": response}
        except BaseException as exc:
            code = exc.code if isinstance(exc, ManagerError) else "STDIO_OUTCOME_UNKNOWN"
            with self.core.journal.connect() as c:
                c.execute(
                    "UPDATE stdio_rpcs SET state='unknown',error_code=? WHERE request_id=?",
                    (code, str(request.request_id)),
                )
            try:
                self.stop(spec)
            except Exception:
                pass
            if isinstance(exc, ManagerError):
                raise
            raise ManagerError("STDIO_OUTCOME_UNKNOWN", "MCP RPC outcome requires reconciliation", 502) from None

    def stop(self, spec):
        with self.lock(spec.binding_id):
            self.core.guard.validate(
                "stdio.stop", {"spec": spec.model_dump(mode="json"), "manager_id": self.core.journal.installation_id}
            )
            result = self.core.stop(spec)
            self.after_stop(spec)
            return result

    def after_stop(self, spec):
        process = self.sessions.pop(str(spec.binding_id), None)
        if process:
            process.close()
        self.core.guard.validate(
            "stdio.stopped", {"spec": spec.model_dump(mode="json"), "manager_id": self.core.journal.installation_id}
        )

    def reap(self):
        for id, process in list(self.sessions.items()):
            row = self.core.journal.cell(process.spec.binding_id)
            if (
                process.closed.is_set()
                or row is None
                or row["state"] == "destroyed"
                or process.spec.deadline.timestamp() <= time.time()
            ):
                try:
                    self.stop(process.spec)
                except Exception:
                    pass

    def close(self):
        for process in list(self.sessions.values()):
            try:
                self.stop(process.spec)
            except Exception:
                process.close()
