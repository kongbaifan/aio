"""Raw ASGI body bounds and unambiguous JSON before FastAPI parsing; SSE is not buffered."""

from uuid import uuid4
import re
import hmac

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from ...platform_errors import PlatformError
from ...observability.audit import trace_scope
from ...runtime.actions import strict_json


class RequestBoundary:
    def __init__(
        self,
        app,
        max_bytes: int,
        max_upload_bytes: int = 8 * 1024 * 1024,
        control_token: str | None = None,
        connector_token: str | None = None,
    ):
        self.connector_token = connector_token
        self.app, self.max_bytes, self.max_upload_bytes, self.control_token = (
            app,
            max_bytes,
            max_upload_bytes,
            control_token,
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            # No raw legacy terminal WebSocket is mounted in platform mode.
            await self.app(scope, receive, send)
            return
        request_id = uuid4()
        with trace_scope(request_id.hex):
            await self.http(scope, receive, send, str(request_id))

    async def http(self, scope, receive, send, request_id):
        scope.setdefault("state", {})["request_id"] = request_id

        async def secured_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-request-id", request_id.encode("ascii")),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                        (b"content-security-policy", b"default-src 'self'; object-src 'none'; frame-ancestors 'none'"),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        if scope["method"] not in {"POST", "PUT", "PATCH", "DELETE"}:
            await self.app(scope, receive, secured_send)
            return
        try:
            headers = Headers(scope=scope)
            binary_upload = scope["method"] == "PUT" and re.fullmatch(
                r"/api/v2/(?:uploads|knowledge/uploads|admin/skill-imports)/[0-9a-fA-F-]{36}/content", scope["path"]
            )
            internal = scope["path"] == "/internal/v1/sandbox/authorize"
            connector_internal = scope["path"] in {"/internal/v1/connectors/authorize", "/internal/v1/connectors/stdio"}
            if connector_internal:
                supplied = headers.get("x-connector-token", "")
                if not self.connector_token or not hmac.compare_digest(
                    supplied.encode("utf-8"), self.connector_token.encode("ascii")
                ):
                    raise PlatformError(
                        "UNAUTHORIZED_SERVICE", "A verified connector service identity is required", 401
                    )
            if internal:
                supplied = headers.get("x-manager-token", "")
                if not self.control_token or not hmac.compare_digest(
                    supplied.encode("utf-8"), self.control_token.encode("ascii")
                ):
                    raise PlatformError("UNAUTHORIZED_SERVICE", "A verified manager service identity is required", 401)
            max_bytes = (
                14 * 1024 * 1024
                if internal
                else 2 * 1024 * 1024
                if connector_internal
                else self.max_upload_bytes
                if binary_upload
                else self.max_bytes
            )
            if binary_upload and scope["path"].startswith("/api/v2/admin/skill-imports/"):
                from ...skills.archive_contracts import MAX_ARCHIVE_BYTES

                max_bytes = min(max_bytes, MAX_ARCHIVE_BYTES)
            length = headers.get("content-length")
            if length is not None and (len(length) > 20 or not length.isascii() or not length.isdecimal()):
                raise PlatformError("INVALID_REQUEST", "Content length is invalid", 400)
            if length is not None and int(length) > max_bytes:
                raise PlatformError("PAYLOAD_TOO_LARGE", "Request exceeds the size limit", 413)
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                if message["type"] != "http.request":
                    continue
                body.extend(message.get("body", b""))
                if len(body) > max_bytes:
                    raise PlatformError("PAYLOAD_TOO_LARGE", "Request exceeds the size limit", 413)
                if not message.get("more_body", False):
                    break
            if body:
                expected = "application/octet-stream" if binary_upload else "application/json"
                if headers.get("content-type", "").split(";", 1)[0].lower() != expected:
                    raise PlatformError("UNSUPPORTED_MEDIA_TYPE", "Request content type is not supported", 415)
                if not binary_upload:
                    strict_json(bytes(body), max_bytes=max_bytes)
            sent = False

            async def replay_receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay_receive, secured_send)
        except PlatformError as exc:
            response = JSONResponse(
                status_code=exc.status,
                content={
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "request_id": request_id,
                        "retryable": exc.retryable,
                    }
                },
            )
            await response(scope, receive, secured_send)
