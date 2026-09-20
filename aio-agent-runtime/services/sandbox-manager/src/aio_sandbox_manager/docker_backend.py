"""Docker is used only by the isolated manager, never by the Agent control process.

No host mounts, sockets, env passthrough, privileged mode or configurable commands
are accepted. Each managed compute cell uses a fixed read-only image, private
quota-limited tmpfs, non-root identity, isolated PID namespace and no network.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import queue
import tarfile
import threading
import time
from datetime import datetime, timezone
from typing import Callable
from weakref import WeakValueDictionary

import docker
from docker.errors import APIError, NotFound

from .contracts import CellSpec, ExecuteRequest, ManagerError, Profile, safe_relative

CLEANUP_CONFIRM_SECONDS = 5.0


class DockerBackend:
    def __init__(self, installation_id: str, *, client=None):
        self.installation_id = installation_id
        self._cleanup_locks = WeakValueDictionary()
        self._cleanup_mutex = threading.Lock()
        self.client = client or docker.from_env(timeout=15)
        info = self.client.info()
        if info.get("OSType") != "linux":
            raise ManagerError("RUNTIME_UNSUPPORTED", "Compute isolation requires a Linux Docker engine", 503)
        self.host_info = {
            k: info.get(k) for k in ("OSType", "ServerVersion", "KernelVersion", "CgroupVersion", "SecurityOptions")
        }

    def name(self, spec: CellSpec) -> str:
        return f"aio-cell-{self.installation_id[:12]}-{spec.binding_id.hex}"

    def labels(self, spec):
        labels = {
            "aio.manager": self.installation_id,
            "aio.binding": str(spec.binding_id),
            "aio.org": str(spec.org_id),
            "aio.run": str(spec.run_id),
            "aio.generation": str(spec.generation),
            "aio.spec": spec.spec_digest,
            "aio.role": "mcp_stdio" if getattr(spec, "kind", None) == "mcp_stdio" else "compute",
        }
        verification = os.environ.get("AIO_VERIFICATION_RUN_ID")
        if verification:
            labels["aio.verification-run"] = verification
        return labels

    def checked(self, spec: CellSpec, container_id: str | None):
        try:
            container = self.client.containers.get(container_id or self.name(spec))
            container.reload()
        except NotFound:
            return None
        labels = container.attrs.get("Config", {}).get("Labels", {})
        if any(labels.get(k) != v for k, v in self.labels(spec).items()):
            raise ManagerError("RESOURCE_OWNERSHIP_MISMATCH", "Refusing to operate on an unrelated container", 409)
        if container_id and container.id != container_id:
            raise ManagerError("RESOURCE_ID_MISMATCH", "Container identity changed", 409)
        return container

    def volume_name(self, spec: CellSpec) -> str:
        return self.name(spec) + "-workspace"

    def workspace_volume(self, spec: CellSpec, profile: Profile):
        options = {
            "type": "tmpfs",
            "device": "tmpfs",
            "o": f"rw,nosuid,nodev,size={profile.workspace_bytes},nr_inodes={profile.workspace_inodes},mode=0700,uid=10001,gid=10001",
        }
        try:
            volume = self.client.volumes.get(self.volume_name(spec))
        except NotFound:
            volume = self.client.volumes.create(
                name=self.volume_name(spec), driver="local", driver_opts=options, labels=self.labels(spec)
            )
        volume.reload()
        if volume.attrs.get("Options") != options or any(
            volume.attrs.get("Labels", {}).get(k) != v for k, v in self.labels(spec).items()
        ):
            raise ManagerError(
                "VOLUME_OWNERSHIP_MISMATCH", "Workspace volume must match the owned hard-quota specification", 409
            )
        return volume

    def create(self, spec: CellSpec, profile: Profile):
        existing = self.checked(spec, None)
        if existing:
            self.verify(existing, profile)
            if existing.status == "created":
                existing.start()
            return existing
        image = self.client.images.get(profile.image_digest)
        if image.id != profile.image_digest:
            raise ManagerError("IMAGE_MISMATCH", "Runtime image did not match its pinned identity", 503)
        self.verify_runtime_labels(image.attrs.get("Config", {}), profile)
        if profile.runtime_approval is not None and image.attrs.get("Architecture") != "amd64":
            raise ManagerError("RUNTIME_PLATFORM_MISMATCH", "This runtime requires its approved Linux amd64 image", 403)

        def tmpfs(size, inodes):
            return f"rw,nosuid,nodev,size={size},nr_inodes={inodes},mode=0700,uid=10001,gid=10001"

        volume = self.workspace_volume(spec, profile)
        container = self.client.containers.create(
            image=profile.image_digest,
            name=self.name(spec),
            labels=self.labels(spec),
            command=[
                "/usr/local/bin/python",
                "-I",
                "-S",
                "-u",
                "-c",
                "import sys,time;time.sleep(float(sys.argv[1]))",
                str(max(0.1, (spec.deadline - datetime.now(timezone.utc)).total_seconds())),
            ],
            # A different non-root UID owns PID1/timer. Untrusted UID10001 cannot stop or extend the watchdog.
            user="10000:10000",
            working_dir="/",
            read_only=True,
            network_mode="none",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            privileged=False,
            mem_limit=profile.memory_bytes,
            memswap_limit=profile.memory_bytes,
            nano_cpus=profile.nano_cpus,
            pids_limit=profile.pids,
            shm_size=4 * 1024 * 1024,
            mounts=[docker.types.Mount(target="/workspace", source=volume.name, type="volume", no_copy=True)],
            tmpfs={
                "/home/runner": tmpfs(profile.home_bytes, 1024),
                "/tmp": tmpfs(profile.temp_bytes, 1024),
            },
            environment={
                "HOME": "/home/runner",
                "TMPDIR": "/tmp",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONIOENCODING": "utf-8",
                "LANG": "C.UTF-8",
            },
            init=True,
            detach=True,
            stdin_open=False,
            tty=False,
            restart_policy={"Name": "no"},
            log_config=docker.types.LogConfig(type="none"),
            ulimits=[
                docker.types.Ulimit(name="nofile", soft=256, hard=256),
                docker.types.Ulimit(name="core", soft=0, hard=0),
            ],
        )
        container.start()
        self.verify(container, profile)
        if spec.inputs:
            self._populate_inputs(container, profile, spec.inputs)
        return container

    def initialize_stdio_inputs(self, spec, profile, container_id, inputs):
        """Called only before the MCP process is spawned, never as a live file-write API."""
        if getattr(spec, "kind", None) != "mcp_stdio" or spec.schema_version != 2:
            raise ManagerError("STDIO_INPUTS_NOT_ALLOWED", "Input initialization requires its own fixed spec", 403)
        container = self.checked(spec, container_id)
        if container is None or container.status != "running":
            raise ManagerError("CELL_LOST", "Stdio input target is no longer available", 409)
        self.verify(container, profile)
        self._populate_inputs(container, profile, inputs)

    @staticmethod
    def _populate_inputs(container, profile, inputs):
        # This is a trusted tar writer over individually checked raw bytes, not a user archive parser.
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w") as archive:
            seen_dirs = set()
            for item in inputs:
                data = item.bytes()
                path = safe_relative(item.path)
                parts = path.split("/")
                for index in range(1, len(parts)):
                    directory = "/".join(parts[:index])
                    if directory not in seen_dirs:
                        info = tarfile.TarInfo(directory)
                        info.type = tarfile.DIRTYPE
                        info.mode = 0o700
                        info.uid = 10001
                        info.gid = 10001
                        archive.addfile(info)
                        seen_dirs.add(directory)
                info = tarfile.TarInfo(path)
                info.size = len(data)
                info.mode = 0o600
                info.uid = 10001
                info.gid = 10001
                archive.addfile(info, io.BytesIO(data))
        if len(payload.getvalue()) > profile.workspace_bytes:
            raise ManagerError("INPUT_QUOTA_EXCEEDED", "Inputs exceed the workspace quota", 413)
        if not container.put_archive("/workspace", payload.getvalue()):
            raise ManagerError("INPUT_IMPORT_UNCONFIRMED", "Input transfer was not confirmed by Docker", 503)

    @staticmethod
    def verify_runtime_labels(config, profile):
        labels = config.get("Labels", {}) or {}
        declared = labels.get("aio.runtime.manifest_digest")
        if profile.runtime_approval is None:
            if declared:
                raise ManagerError(
                    "RUNTIME_APPROVAL_REQUIRED", "Dependency images require explicit signed admission", 403
                )
            return
        from aio_runtime_policy import RuntimeApproval

        approval = RuntimeApproval.model_validate(profile.runtime_approval)
        if (
            declared != approval.manifest.digest
            or labels.get("aio.runtime.install_path") != "/opt/aio-deps"
            or config.get("Entrypoint")
        ):
            raise ManagerError("RUNTIME_IMAGE_MISMATCH", "Runtime image metadata does not match its approval", 403)

    @staticmethod
    def verify(container, profile: Profile):
        container.reload()
        attrs = container.attrs
        DockerBackend.verify_runtime_labels(attrs.get("Config", {}), profile)
        host = attrs["HostConfig"]
        config = attrs["Config"]
        if (
            config.get("User") != "10000:10000"
            or not host.get("ReadonlyRootfs")
            or host.get("NetworkMode") != "none"
            or host.get("Privileged")
            or host.get("Binds")
            or host.get("PidMode") in {"host", "container"}
            or host.get("Memory") != profile.memory_bytes
            or host.get("MemorySwap") != profile.memory_bytes
            or host.get("PidsLimit") != profile.pids
            or host.get("NanoCpus") != profile.nano_cpus
            or "ALL" not in host.get("CapDrop", [])
            or not any(v.startswith("no-new-privileges") for v in host.get("SecurityOpt", []))
            or attrs.get("Image") != profile.image_digest
        ):
            raise ManagerError(
                "ISOLATION_PROFILE_INVALID", "Actual container configuration does not meet the approved profile", 503
            )
        for path, size in [
            ("/home/runner", profile.home_bytes),
            ("/tmp", profile.temp_bytes),
        ]:
            options = host.get("Tmpfs", {}).get(path, "")
            if f"size={size}" not in options or "nr_inodes=" not in options:
                raise ManagerError("QUOTA_NOT_ENFORCED", "Writable paths must have hard tmpfs size/inode bounds", 503)
        workspace = [m for m in attrs.get("Mounts", []) if m.get("Destination") == "/workspace"]
        if len(workspace) != 1 or workspace[0].get("Type") != "volume" or not workspace[0].get("RW"):
            raise ManagerError("QUOTA_NOT_ENFORCED", "Workspace must be a dedicated hard-quota volume", 503)
        if any(m.get("Type") == "bind" for m in attrs.get("Mounts", [])):
            raise ManagerError("HOST_MOUNT_FORBIDDEN", "Host paths must never be mounted into compute cells", 503)

    def execute(
        self, request: ExecuteRequest, profile: Profile, container_id: str, cancelled: Callable[[], bool]
    ) -> dict:
        spec = request.spec
        container = self.checked(spec, container_id)
        if container is None or container.status != "running":
            raise ManagerError("CELL_NOT_RUNNING", "Execution cell is not active", 409)
        self.verify(container, profile)
        remaining = (spec.deadline - datetime.now(timezone.utc)).total_seconds()
        timeout = min(request.timeout_seconds, profile.max_timeout_seconds, remaining)
        if timeout <= 0:
            raise ManagerError("CELL_EXPIRED", "Execution deadline expired", 409)
        # Code remains untrusted input to Python inside the cell; it is never evaluated by the manager.
        command = ["/usr/local/bin/python", "-I", "-u", "-c", request.code]
        if profile.runtime_approval is not None:
            # No site/.pth startup hooks; only the approved read-only dependency directory is appended.
            command = [
                "/usr/local/bin/python",
                "-I",
                "-S",
                "-u",
                "-c",
                "import sys\nsys.path.append('/opt/aio-deps')\n" + request.code,
            ]
        execution = self.client.api.exec_create(
            container.id,
            cmd=command,
            user="10001:10001",
            workdir="/workspace",
            stdout=True,
            stderr=True,
            stdin=False,
            tty=False,
            environment={
                "HOME": "/home/runner",
                "TMPDIR": "/tmp",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        events = queue.Queue(maxsize=8)
        reader_stop = threading.Event()

        def enqueue(value):
            while not reader_stop.is_set():
                try:
                    events.put(value, timeout=0.1)
                    return
                except queue.Full:
                    pass

        def reader():
            stream = None
            try:
                stream = self.client.api.exec_start(execution["Id"], stream=True, demux=True)
                for stdout, stderr in stream:
                    for name, data in [("stdout", stdout), ("stderr", stderr)]:
                        if data:
                            # A single daemon frame is split before entering the bounded queue.
                            for i in range(0, len(data), 8192):
                                enqueue((name, data[i : i + 8192]))
                    if reader_stop.is_set():
                        break
            except Exception:
                enqueue(("reader_error", b""))
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
                enqueue(("eof", b""))

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        deadline = time.monotonic() + timeout
        collected = {"stdout": bytearray(), "stderr": bytearray()}
        total = 0
        reason = None
        try:
            while True:
                if cancelled():
                    reason = "EXECUTION_CANCELLED"
                    break
                if time.monotonic() >= deadline:
                    reason = "EXECUTION_TIMEOUT"
                    break
                try:
                    kind, data = events.get(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
                except queue.Empty:
                    continue
                if kind == "eof":
                    break
                if kind == "reader_error":
                    reason = "EXECUTION_CHANNEL_FAILED"
                    break
                allowed = max(0, profile.output_bytes - total)
                collected[kind].extend(data[:allowed])
                total += len(data)
                if total > profile.output_bytes:
                    reason = "OUTPUT_LIMIT_EXCEEDED"
                    break
            if reason:
                # Release the bounded output queue before waiting for container termination.
                # Otherwise the exec reader can block on queue.put while Docker waits for the attached pipe to drain.
                reader_stop.set()
                self.stop(spec, container.id)
            try:
                status = self.client.api.exec_inspect(execution["Id"])
            except APIError:
                status = {"ExitCode": None, "Running": False}
            if not reason and status.get("Running"):
                reason = "EXECUTION_STATE_UNKNOWN"
                self.stop(spec, container.id)
            return {
                "stdout": bytes(collected["stdout"]).decode("utf-8", errors="replace"),
                "stderr": bytes(collected["stderr"]).decode("utf-8", errors="replace"),
                "exit_code": status.get("ExitCode"),
                "error_code": reason,
                "truncated": total > profile.output_bytes,
                "execution_id": execution["Id"],
            }
        finally:
            reader_stop.set()
            thread.join(timeout=2)

    def export_files(self, spec: CellSpec, profile: Profile, container_id: str) -> list[dict]:
        container = self.checked(spec, container_id)
        if container is None or container.status != "running":
            raise ManagerError("CELL_NOT_RUNNING", "Cannot collect an inactive workspace", 409)
        container.pause()
        container.reload()
        if not container.attrs["State"].get("Paused"):
            raise ManagerError("WRITER_NOT_FROZEN", "Workspace writer must be externally frozen before collection", 503)
        # Docker daemon reads the frozen filesystem; no user-provided script reports paths or hashes.
        stream, stat = container.get_archive("/workspace")
        archive_bytes = io.BytesIO()
        size = 0
        archive_limit = min(
            profile.workspace_bytes + 4 * 1024 * 1024,
            profile.artifact_bytes + min(profile.workspace_inodes, 8192) * 1024 + 2 * 1024 * 1024,
        )
        try:
            for chunk in stream:
                size += len(chunk)
                if size > archive_limit:
                    raise ManagerError(
                        "EXPORT_QUOTA_EXCEEDED", "Workspace archive exceeds its bounded collector budget", 413
                    )
                archive_bytes.write(chunk)
        finally:
            stream.close()
        archive_bytes.seek(0)
        files = []
        total = 0
        members = 0
        names = set()
        try:
            with tarfile.open(fileobj=archive_bytes, mode="r:") as archive:
                for member in archive:
                    members += 1
                    if members > profile.workspace_inodes:
                        raise ManagerError("EXPORT_QUOTA_EXCEEDED", "Too many workspace entries", 413)
                    name = member.name.rstrip("/")
                    if name == "workspace" and member.isdir():
                        continue
                    if not name.startswith("workspace/"):
                        raise ManagerError("UNSAFE_ARTIFACT", "Archive escaped its workspace root", 409)
                    path = safe_relative(name[len("workspace/") :])
                    if member.isdir():
                        continue
                    if not member.isfile() or member.issym() or member.islnk() or member.size < 0:
                        raise ManagerError("UNSAFE_ARTIFACT", "Links and special files cannot be published", 409)
                    if path in names:
                        raise ManagerError("UNSAFE_ARTIFACT", "Duplicate artifact paths are invalid", 409)
                    names.add(path)
                    total += member.size
                    if total > profile.artifact_bytes or len(files) >= profile.artifact_files:
                        raise ManagerError("ARTIFACT_QUOTA_EXCEEDED", "Generated files exceed the artifact quota", 413)
                    source = archive.extractfile(member)
                    if source is None:
                        raise ValueError
                    data = source.read(member.size + 1)
                    if len(data) != member.size:
                        raise ValueError
                    # Temporary dependency/profile material must not become normal business artifacts.
                    if any(
                        part in {".venv", "node_modules", "__pycache__", ".cache", ".ssh"} for part in path.split("/")
                    ):
                        continue
                    if path.split("/")[-1].startswith(".env"):
                        raise ManagerError("UNSAFE_ARTIFACT", "Credential-shaped files cannot be published", 409)
                    files.append(
                        {
                            "path": path,
                            "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "content_b64": base64.b64encode(data).decode("ascii"),
                        }
                    )
        except (ValueError, tarfile.TarError):
            raise ManagerError("UNSAFE_ARTIFACT", "Workspace archive failed safe validation", 409) from None
        return files

    def stop(self, spec: CellSpec, container_id: str | None):
        with self._cleanup_lock(spec.binding_id):
            self._stop_owned(spec, container_id)

    def _cleanup_lock(self, binding_id):
        # Only cleanup operations share this per-binding lock. It must never be
        # held by execution, RPCs, exports or another binding's lifecycle.
        with self._cleanup_mutex:
            lock = self._cleanup_locks.get(binding_id)
            if lock is None:
                lock = threading.RLock()
                self._cleanup_locks[binding_id] = lock
            return lock

    def _stop_owned(self, spec: CellSpec, container_id: str | None):
        container = self.checked(spec, container_id)
        if container is None:
            return
        if container.attrs["State"].get("Paused"):
            try:
                container.unpause()
            except APIError:
                try:
                    container.reload()
                except NotFound:
                    return
                if container.attrs["State"].get("Paused"):
                    raise
        try:
            container.kill()
        except APIError:
            try:
                container.reload()
            except NotFound:
                return
            if container.attrs["State"].get("Running"):
                raise
        deadline = time.monotonic() + 5
        while True:
            try:
                container.reload()
            except NotFound:
                return
            if not container.attrs["State"].get("Running"):
                return
            if time.monotonic() >= deadline:
                raise ManagerError("STOP_UNCONFIRMED", "Container termination could not be confirmed", 503)
            time.sleep(0.05)

    def destroy(self, spec: CellSpec, container_id: str | None):
        with self._cleanup_lock(spec.binding_id):
            self._destroy_owned(spec, container_id)

    def _confirm_removal_conflict(self, spec, container_id, error):
        # Do not retry DELETE. A daemon/other cleanup actor can be removing an
        # already stopped object; only owned 'removing' -> absent is accepted.
        deadline = time.monotonic() + CLEANUP_CONFIRM_SECONDS
        while True:
            current = self.checked(spec, container_id)
            if current is None:
                return
            state = current.attrs.get("State", {})
            if state.get("Running") or state.get("Status") != "removing":
                raise error
            if time.monotonic() >= deadline:
                raise ManagerError("CLEANUP_UNCONFIRMED", "Container removal is still in progress", 503)
            time.sleep(0.05)

    def _destroy_owned(self, spec: CellSpec, container_id: str | None):
        container = self.checked(spec, container_id)
        if container is not None:
            self.stop(spec, container.id)
            try:
                container.remove(force=True, v=True)
            except NotFound:
                pass  # A concurrent owned cleanup may win; absence must still be verified below.
            except APIError as error:
                if error.status_code != 409:
                    raise
                self._confirm_removal_conflict(spec, container.id, error)
            if self.checked(spec, container.id) is not None:
                raise ManagerError("CLEANUP_UNCONFIRMED", "Container deletion could not be confirmed", 503)
        try:
            volume = self.client.volumes.get(self.volume_name(spec))
        except NotFound:
            return
        if any(volume.attrs.get("Labels", {}).get(k) != v for k, v in self.labels(spec).items()):
            raise ManagerError("VOLUME_OWNERSHIP_MISMATCH", "Refusing to remove another task's volume", 409)
        try:
            volume.remove(force=False)
        except NotFound:
            pass  # Never turn an arbitrary Docker failure into success, or skip the absence check.
        try:
            self.client.volumes.get(self.volume_name(spec))
        except NotFound:
            return
        raise ManagerError("CLEANUP_UNCONFIRMED", "Workspace volume deletion could not be confirmed", 503)

    def close(self):
        self.client.close()
