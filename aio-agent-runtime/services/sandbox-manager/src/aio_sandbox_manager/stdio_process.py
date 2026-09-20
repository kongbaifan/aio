"""Bounded JSON-line MCP over Docker exec stdin/stdout, never a host subprocess.

The fixed bootstrap receives its own minimum-scope credential over stdin, not
Docker Config.Env/Cmd, a host file or the manager journal. All child output is
untrusted and kept only in bounded memory. Physical lifecycle is checked outside.
"""

import json
import queue
import socket
import struct
import threading
import time

import rfc8785

from .contracts import ManagerError

BOOTSTRAP = """import json,os,sys
b=bytearray()
while len(b)<=32768:
 c=os.read(0,1)
 if not c: raise SystemExit(2)
 if c==b'\\n': break
 b.extend(c)
else: raise SystemExit(2)
v=json.loads(b)
os.write(1,b'__AIO_STDIO_READY__\\n')
os.execve(v['argv'][0],v['argv'],v['env'])
"""


def strict_message(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    def tree(value, depth=0):
        if depth > 32 or (type(value) is int and abs(value) > 9007199254740991):
            raise ValueError
        if isinstance(value, dict):
            for item in value.values():
                tree(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                tree(item, depth + 1)

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
        )
        tree(value)
        rfc8785.dumps(value)
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
            raise ValueError
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError, rfc8785.CanonicalizationError):
        raise ManagerError("STDIO_PROTOCOL_INVALID", "MCP stdout must contain bounded JSON-RPC lines", 502) from None


class DockerStdioProcess:
    def __init__(self, backend, spec, profile, container_id, credential):
        self.backend, self.spec, self.profile = backend, spec, profile
        self.closed = threading.Event()
        self.messages = queue.Queue(maxsize=32)
        self.error = None
        self.stdout = bytearray()
        self.total, self.stderr = 0, 0
        self._rpc_lock = threading.Lock()
        self.initialized = False
        self.initial_result = None
        self._bootstrap = False
        self.socket = None
        self.thread = None
        environment = {
            "HOME": "/home/runner",
            "TMPDIR": "/tmp",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }
        if profile.credential_env:
            if not credential:
                raise ManagerError(
                    "STDIO_CREDENTIAL_REQUIRED", "This approved template requires its scoped credential", 403
                )
            environment[profile.credential_env] = credential
        elif credential:
            raise ManagerError("STDIO_CREDENTIAL_DENIED", "This template does not accept credentials", 403)
        config = {"argv": [profile.executable, *profile.arguments], "env": environment}
        payload = rfc8785.dumps(config) + b"\n"
        if len(payload) > 32768:
            raise ManagerError(
                "STDIO_BOOTSTRAP_TOO_LARGE", "Template and scoped credential exceed the input bound", 413
            )
        execution = backend.client.api.exec_create(
            container_id,
            cmd=["python", "-I", "-u", "-c", BOOTSTRAP],
            stdin=True,
            stdout=True,
            stderr=True,
            tty=False,
            user="10001:10001",
            workdir="/workspace",
            environment={"HOME": "/home/runner", "TMPDIR": "/tmp", "PYTHONUNBUFFERED": "1", "LANG": "C.UTF-8"},
        )
        self.exec_id = execution["Id"]
        try:
            self.socket = backend.client.api.exec_start(self.exec_id, socket=True)
            self.sock = getattr(self.socket, "_sock", self.socket)
            self.sock.settimeout(1)
            self.send(config)
            self.thread = threading.Thread(target=self._reader, daemon=True)
            self.thread.start()
            ready = self._next(min(10, profile.max_timeout_seconds))
            if ready != {"_bootstrap": True}:
                raise ManagerError("STDIO_START_FAILED", "Isolated MCP bootstrap did not become ready", 502)
        except BaseException:
            self.close()
            raise

    def _read(self, size):
        data = bytearray()
        while len(data) < size and not self.closed.is_set():
            if time.time() >= self.spec.deadline.timestamp():
                raise ManagerError("STDIO_DEADLINE_EXCEEDED", "MCP execution deadline expired", 409)
            try:
                part = self.sock.recv(min(8192, size - len(data)))
            except (socket.timeout, TimeoutError):
                continue
            if not part:
                raise ManagerError("STDIO_PROCESS_EXITED", "Isolated MCP process exited", 502)
            data.extend(part)
        if len(data) != size:
            raise ManagerError("STDIO_PROCESS_CLOSED", "Isolated MCP stream is closed", 409)
        return bytes(data)

    def _emit(self, value):
        try:
            self.messages.put_nowait(value)
        except queue.Full:
            raise ManagerError("STDIO_OUTPUT_LIMIT", "MCP output queue exceeded its bound", 413) from None

    def _reader(self):
        try:
            while not self.closed.is_set():
                header = self._read(8)
                channel, size = header[0], struct.unpack(">I", header[4:])[0]
                if channel not in {1, 2} or header[1:4] != b"\0\0\0" or size > self.profile.session_output_bytes:
                    raise ManagerError("STDIO_FRAME_INVALID", "Docker stdio frame is invalid or too large", 502)
                self.total += size + 8
                if self.total > self.profile.session_output_bytes:
                    raise ManagerError("STDIO_OUTPUT_LIMIT", "MCP session output exceeded its bound", 413)
                while size:
                    data = self._read(min(size, 8192))
                    size -= len(data)
                    if channel == 2:
                        self.stderr += len(data)
                        if self.stderr > self.profile.stderr_bytes:
                            raise ManagerError("STDIO_STDERR_LIMIT", "MCP stderr exceeded its separate bound", 413)
                        continue  # Diagnostics are not protocol and may contain secrets; never journal or echo them.
                    self.stdout.extend(data)
                    while b"\n" in self.stdout:
                        line, _, rest = self.stdout.partition(b"\n")
                        self.stdout = bytearray(rest)
                        if not self._bootstrap:
                            if line != b"__AIO_STDIO_READY__":
                                raise ManagerError("STDIO_START_FAILED", "Unexpected bootstrap output", 502)
                            self._bootstrap = True
                            self._emit({"_bootstrap": True})
                            continue
                        if len(line) > self.profile.frame_bytes:
                            raise ManagerError("STDIO_OUTPUT_LIMIT", "MCP line exceeded its frame bound", 413)
                        self._emit(strict_message(bytes(line).rstrip(b"\r")))
                    if len(self.stdout) > self.profile.frame_bytes:
                        raise ManagerError("STDIO_OUTPUT_LIMIT", "MCP line exceeded its frame bound", 413)
        except BaseException as exc:
            self.error = (
                exc
                if isinstance(exc, ManagerError)
                else ManagerError("STDIO_STREAM_FAILED", "Isolated stdio stream failed", 502)
            )
            self.closed.set()

    def _next(self, timeout):
        deadline = min(
            time.monotonic() + timeout, time.monotonic() + max(0, self.spec.deadline.timestamp() - time.time())
        )
        while True:
            if self.error:
                raise self.error
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ManagerError("STDIO_RPC_TIMEOUT", "MCP did not return within the allowed timeout", 504)
            try:
                return self.messages.get(timeout=min(0.1, remaining))
            except queue.Empty:
                if self.closed.is_set():
                    raise self.error or ManagerError("STDIO_PROCESS_CLOSED", "Isolated MCP stream is closed", 409)

    def send(self, value):
        if self.closed.is_set():
            raise self.error or ManagerError("STDIO_PROCESS_CLOSED", "Isolated MCP process is closed", 409)
        payload = rfc8785.dumps(value) + b"\n"
        if len(payload) > 131072:
            raise ManagerError("STDIO_INPUT_LIMIT", "MCP request exceeds its bound", 413)
        done = threading.Event()
        error = []

        def write():
            try:
                self.sock.sendall(payload)
            except Exception:
                error.append(True)
            finally:
                done.set()

        writer = threading.Thread(target=write, daemon=True)
        writer.start()
        remaining = min(5, max(0.001, self.spec.deadline.timestamp() - time.time()))
        if not done.wait(remaining) or error:
            self.closed.set()
            raise ManagerError("STDIO_SEND_UNKNOWN", "MCP request delivery could not be confirmed", 502)

    def rpc(self, method, params, id, timeout):
        with self._rpc_lock:
            if method == "initialize" and self.initialized:
                return {**self.initial_result, "id": id}
            if method == "notifications/initialized" and self.initialized:
                return None
            if method not in {"initialize", "notifications/initialized"} and not self.initialized:
                raise ManagerError("STDIO_NOT_INITIALIZED", "MCP must initialize before tool requests", 409)
            message = {"jsonrpc": "2.0", "method": method, "params": params}
            if not method.startswith("notifications/"):
                message["id"] = id
            self.send(message)
            if method == "notifications/initialized":
                self.initialized = True
                return None
            deadline = time.monotonic() + timeout
            count = 0
            while True:
                item = self._next(max(0.001, deadline - time.monotonic()))
                count += 1
                if count > 64:
                    raise ManagerError("STDIO_MESSAGE_LIMIT", "Too many unsolicited MCP messages", 413)
                if "method" in item:
                    if "id" in item:
                        self.send(
                            {
                                "jsonrpc": "2.0",
                                "id": item["id"],
                                "error": {"code": -32601, "message": "Server-initiated operations are not enabled"},
                            }
                        )
                    continue
                if item.get("id") != id or ("result" in item) == ("error" in item):
                    raise ManagerError(
                        "STDIO_PROTOCOL_INVALID", "MCP response does not match the committed request", 502
                    )
                if method == "initialize":
                    self.initial_result = item
                return item

    def close(self):
        self.closed.set()
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)
