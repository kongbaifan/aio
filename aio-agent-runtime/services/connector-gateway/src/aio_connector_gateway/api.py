"""Private machine-to-machine API. No arbitrary URL, shell, module, token-read or proxy endpoint."""

import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .contracts import CallRequest, CredentialPut, CredentialRevoke, DiscoverRequest, GatewayError, strict_json
from .oauth_contracts import OAuthBegin, OAuthExchange


def failure(code, status, not_sent=False):
    return JSONResponse(
        {"error": {"code": code, "not_sent": not_sent}},
        status_code=status,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


class Boundary:
    def __init__(self, app, token):
        self.app, self.token = app, token.encode("ascii")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        if scope["path"] != "/healthz" and not hmac.compare_digest(
            headers.get(b"authorization", b""), b"Bearer " + self.token
        ):
            await failure("UNAUTHORIZED_GATEWAY", 401, True)(scope, receive, send)
            return
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            data = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                data.extend(message.get("body", b""))
                if len(data) > 2 * 1024 * 1024:
                    await failure("REQUEST_TOO_LARGE", 413, True)(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break
            try:
                if headers.get(b"content-type", b"").split(b";", 1)[0] != b"application/json":
                    raise GatewayError("INVALID_REQUEST")
                strict_json(bytes(data), 2 * 1024 * 1024)
            except GatewayError:
                await failure("INVALID_REQUEST", 422, True)(scope, receive, send)
                return
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(data), "more_body": False}
                return await receive()

            await self.app(scope, replay, send)
        else:
            await self.app(scope, receive, send)


def create_app(gateway, token, *, manage_lifecycle=True):
    if len(token) < 32 or not token.isascii() or any(ord(c) <= 32 for c in token):
        raise ValueError("Provide a dedicated gateway service credential")

    @asynccontextmanager
    async def lifespan(app):
        yield
        if manage_lifecycle:
            if gateway.stdio_manager:
                await gateway.stdio_manager.close()
            await gateway.authority.close()
            gateway.vault.close()

    app = FastAPI(
        title="Private AIO Connector Gateway", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(Boundary, token=token)

    @app.exception_handler(GatewayError)
    async def gateway_error(request, error):
        return failure(error.code, error.status, error.not_sent)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, error):
        return failure("INVALID_REQUEST", 422, True)

    @app.get("/healthz")
    async def health():
        return {"status": "ok", "service": "connector-gateway"}

    @app.post("/v1/credentials/put")
    async def put(body: CredentialPut):
        return await gateway.put(body)

    @app.post("/v1/credentials/revoke")
    async def revoke(body: CredentialRevoke):
        return await gateway.revoke(body)

    @app.post("/v1/mcp/discover")
    async def discover(body: DiscoverRequest):
        return await gateway.discover(body)

    @app.post("/v1/mcp/call")
    async def call(body: CallRequest):
        return await gateway.call(body)

    @app.post("/v1/mcp/status")
    async def status(body: CallRequest):
        return await gateway.status(body)

    @app.post("/v1/oauth/start")
    async def oauth_start(body: OAuthBegin):
        return await gateway.oauth_begin(body)

    @app.post("/v1/oauth/exchange")
    async def oauth_exchange(body: OAuthExchange):
        return await gateway.oauth_exchange(body)

    @app.post("/v1/stdio/cleanup")
    async def stdio_cleanup(body: dict):
        return await gateway.stdio_cleanup(body)

    return app
