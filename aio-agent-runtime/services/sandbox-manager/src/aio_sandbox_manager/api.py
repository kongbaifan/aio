"""Private manager HTTP surface. Deploy only on the trusted execution management network."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from docker.errors import DockerException

from .contracts import ControlRequest, ExecuteRequest, ManagerError, Profile
from .docker_backend import DockerBackend
from .journal import Journal
from .service import SandboxManager
from .stdio_contracts import StdioOpen, StdioRPC, StdioControl


class RemoteGuard:
    def __init__(self, url: str, token: str, *, test_mode: bool = False, client=None):
        parsed = urlsplit(url)
        if (
            parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not parsed.hostname
            or (
                parsed.scheme != "https"
                and not (test_mode and parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})
            )
        ):
            raise ValueError("Control authority must be an approved HTTPS endpoint")
        if len(token) < 32:
            raise ValueError("A strong control-service credential is required")
        self.url, self.token = url.rstrip("/") + "/internal/v1/sandbox/authorize", token
        self.client = client or httpx.Client(timeout=3, follow_redirects=False, trust_env=False)

    def validate(self, operation: str, payload: dict) -> None:
        try:
            with self.client.stream(
                "POST", self.url, json={"operation": operation, **payload}, headers={"X-Manager-Token": self.token}
            ) as response:
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 8192:
                        raise ValueError
                if response.status_code != 200 or json.loads(data).get("allowed") is not True:
                    raise ValueError
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            raise ManagerError(
                "CONTROL_AUTHORIZATION_DENIED", "Current control-plane authorization is required", 403
            ) from None

    def close(self):
        self.client.close()


class Boundary:
    def __init__(self, app, token: str, stdio_token: str | None = None):
        self.app, self.token = app, token
        self.stdio_token = stdio_token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope["headers"]}
        supplied = headers.get(b"authorization", b"")
        expected = self.stdio_token if scope["path"].startswith("/v1/stdio/") else self.token
        if scope["path"] != "/healthz" and (
            not expected or not hmac.compare_digest(supplied, b"Bearer " + expected.encode("ascii"))
        ):
            await JSONResponse({"error": {"code": "UNAUTHORIZED"}}, status_code=401)(scope, receive, send)
            return
        if scope["method"] == "POST":
            data = bytearray()
            while True:
                msg = await receive()
                if msg["type"] == "http.disconnect":
                    return
                data.extend(msg.get("body", b""))
                if len(data) > 14 * 1024 * 1024:
                    await JSONResponse({"error": {"code": "PAYLOAD_TOO_LARGE"}}, status_code=413)(scope, receive, send)
                    return
                if not msg.get("more_body", False):
                    break

            def unique(pairs):
                d = {}
                for key, value in pairs:
                    if key in d:
                        raise ValueError
                    d[key] = value
                return d

            try:
                if headers.get(b"content-type", b"").split(b";", 1)[0] != b"application/json":
                    raise ValueError
                json.loads(
                    data.decode("utf-8"),
                    object_pairs_hook=unique,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
                )
            except (ValueError, UnicodeError, RecursionError):
                await JSONResponse({"error": {"code": "INVALID_REQUEST"}}, status_code=422)(scope, receive, send)
                return
            sent = False

            async def replay():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": bytes(data), "more_body": False}
                return await receive()

            await self.app(scope, replay, send)
        else:
            await self.app(scope, receive, send)


def create_app(manager: SandboxManager, token: str, *, manage_lifecycle=True, stdio_token=None) -> FastAPI:
    if not token.isascii() or len(token) < 32:
        raise ValueError("Manager authentication requires a strong ASCII credential")
    if getattr(manager, "stdio", None) and (
        not stdio_token or stdio_token == token or not stdio_token.isascii() or len(stdio_token) < 32
    ):
        raise ValueError("Stdio requires a distinct strong Gateway -> Manager service credential")

    @asynccontextmanager
    async def lifespan(app):
        if manage_lifecycle:
            manager.start_reaper()
        try:
            yield
        finally:
            if manage_lifecycle:
                await asyncio.to_thread(manager.close)

    app = FastAPI(
        title="AIO Sandbox Manager", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.add_middleware(Boundary, token=token, stdio_token=stdio_token)

    @app.exception_handler(ManagerError)
    async def error(request: Request, exc: ManagerError):
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        return JSONResponse(
            {"error": {"code": "INVALID_REQUEST", "message": "Request does not match the fixed manager protocol"}},
            status_code=422,
        )

    @app.exception_handler(DockerException)
    async def runtime_failed(request: Request, exc: DockerException):
        return JSONResponse(
            {
                "error": {
                    "code": "RUNTIME_UNAVAILABLE",
                    "message": "The isolated runtime could not complete this operation",
                }
            },
            status_code=503,
        )

    @app.get("/healthz")
    def health():
        return {"status": "ok", "service": "aio-sandbox-manager"}

    @app.post("/v1/cells/ensure")
    def ensure(body: ControlRequest):
        return manager.ensure(body.spec)

    @app.post("/v1/cells/execute")
    def execute(body: ExecuteRequest):
        return manager.execute(body)

    @app.post("/v1/cells/finalize")
    def finalize(body: ControlRequest):
        return manager.finalize(body.spec)

    @app.post("/v1/cells/checkpoint")
    def checkpoint(body: ControlRequest):
        return manager.checkpoint(body.spec)

    @app.post("/v1/cells/stop")
    def stop(body: ControlRequest):
        return manager.stop(body.spec)

    @app.post("/v1/cells/status")
    def status(body: ControlRequest):
        return manager.status(body.spec)

    @app.post("/v1/cells/acknowledge")
    def acknowledge(body: ControlRequest):
        return manager.acknowledge(body.spec)

    def stdio():
        service = getattr(manager, "stdio", None)
        if service is None:
            raise ManagerError("STDIO_UNAVAILABLE", "No dedicated MCP stdio executor is configured", 503)
        return service

    @app.post("/v1/stdio/open")
    def open_stdio(body: StdioOpen):
        return stdio().open(body)

    @app.post("/v1/stdio/rpc")
    def rpc_stdio(body: StdioRPC):
        return stdio().rpc(body)

    @app.post("/v1/stdio/stop")
    def stop_stdio(body: StdioControl):
        return stdio().stop(body.spec)

    return app


def from_environment():
    root = Path(os.environ["SANDBOX_MANAGER_STATE_ROOT"])
    token = os.environ["SANDBOX_MANAGER_TOKEN"]
    config_path = Path(os.environ["SANDBOX_MANAGER_PROFILES"])
    if not config_path.is_absolute():
        raise ValueError("Profiles path must be operator-controlled and absolute")
    content = config_path.read_bytes()
    if len(content) > 1024 * 1024:
        raise ValueError("Profile catalog is too large")
    raw = json.loads(content)
    profiles = {p["id"]: Profile(**p) for p in raw["profiles"]}
    if not profiles or len(profiles) > 16 or len(profiles) != len(raw["profiles"]):
        raise ValueError("Profiles must have unique IDs")
    journal = Journal(root)
    guard = RemoteGuard(
        os.environ["SANDBOX_CONTROL_URL"],
        os.environ["SANDBOX_CONTROL_TOKEN"],
        test_mode=os.environ.get("SANDBOX_MANAGER_MODE") == "test",
    )
    backend = DockerBackend(journal.installation_id)
    from aio_runtime_policy import load_trust_keys

    manager = SandboxManager(
        journal,
        backend,
        profiles,
        guard,
        runtime_keys=load_trust_keys(os.environ.get("SANDBOX_RUNTIME_TRUST_KEYS")),
        allow_test_runtimes=os.environ.get("SANDBOX_MANAGER_MODE") == "test",
    )
    stdio_token = None
    if os.environ.get("SANDBOX_STDIO_PROFILES"):
        from .stdio_contracts import StdioProfile
        from .stdio_service import StdioManager

        path = Path(os.environ["SANDBOX_STDIO_PROFILES"])
        if not path.is_absolute() or path.stat().st_size > 65536:
            raise ValueError("Stdio templates require a bounded explicit operator catalog")
        values = json.loads(path.read_text(encoding="utf-8"))["profiles"]
        stdio_profiles = {value["id"]: StdioProfile.model_validate(value) for value in values}
        if not 1 <= len(stdio_profiles) <= 8 or len(stdio_profiles) != len(values):
            raise ValueError("Stdio template IDs must be unique and bounded")
        StdioManager(manager, stdio_profiles)
        stdio_token = os.environ["SANDBOX_CONNECTOR_TOKEN"]
    return create_app(manager, token, stdio_token=stdio_token)
