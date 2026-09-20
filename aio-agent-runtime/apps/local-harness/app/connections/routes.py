import asyncio
from uuid import UUID

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode

from ..platform_errors import PlatformError
from .oauth_service import OAuthService

from .contracts import (
    ConnectionCreate,
    CredentialPrepare,
    CredentialUpload,
    DiscoveryCreate,
    ServerCreate,
    ServerPublish,
)


def register_connection_routes(app, service, principal):
    oauth = OAuthService(service)

    @app.post("/api/v2/connections/{connection_id}/oauth", status_code=201)
    async def oauth_start(connection_id: UUID, body: CredentialPrepare, identity=Depends(principal)):
        return await oauth.start(identity, connection_id, body)

    @app.get("/auth/mcp/callback/{endpoint_id}")
    async def oauth_callback(endpoint_id: str, request: Request):
        # Always strip the authorization code from the browser URL, including failed/login-expired callbacks.
        try:
            identity = await principal(request)
            query = request.query_params
            if any(len(query.getlist(key)) != 1 for key in query.keys()):
                raise PlatformError("OAUTH_CALLBACK_INVALID", "OAuth callback has duplicate parameters", 422)
            result = await oauth.callback(
                identity, endpoint_id, query.get("state"), query.get("code"), query.get("error"), query.get("iss")
            )
            if not result.get("flow_id"):
                target = {"oauth": "authorized", "connection": str(result["connection_id"])}
            else:
                # OAuth storage alone is not a successful MCP connection. Verify actual initialize/discovery.
                await service.discover(identity, result["connection_id"], DiscoveryCreate(request_id=result["flow_id"]))
                target = {"oauth": "connected", "connection": str(result["connection_id"])}
        except PlatformError as error:
            target = {
                "oauth_error": error.code
                if error.code.isascii() and error.code.replace("_", "").isalnum()
                else "OAUTH_CALLBACK_FAILED"
            }
        except Exception:
            target = {"oauth_error": "OAUTH_CALLBACK_FAILED"}
        return RedirectResponse("/app/connections?" + urlencode(target), status_code=303)

    @app.get("/api/v2/mcp/servers")
    async def servers(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(service.list_servers, identity)}

    @app.get("/api/v2/admin/mcp/servers")
    async def managed_servers(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(service.list_servers, identity, management=True)}

    @app.post("/api/v2/admin/mcp/servers", status_code=201)
    async def create_server(body: ServerCreate, identity=Depends(principal)):
        return await asyncio.to_thread(service.create_server, identity, body)

    @app.post("/api/v2/admin/mcp/servers/{server_id}/publish")
    async def publish_server(server_id: UUID, body: ServerPublish, identity=Depends(principal)):
        return await asyncio.to_thread(service.publish, identity, server_id, body)

    @app.get("/api/v2/connections")
    async def connections(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(service.list_connections, identity)}

    @app.post("/api/v2/connections", status_code=201)
    async def create_connection(body: ConnectionCreate, identity=Depends(principal)):
        return await asyncio.to_thread(service.create_connection, identity, body)

    @app.post("/api/v2/connections/{connection_id}/credentials", status_code=201)
    async def prepare(connection_id: UUID, body: CredentialPrepare, identity=Depends(principal)):
        return await asyncio.to_thread(service.prepare_credential, identity, connection_id, body)

    @app.put("/api/v2/connections/{connection_id}/credentials/{binding_id}")
    async def upload(connection_id: UUID, binding_id: UUID, body: CredentialUpload, identity=Depends(principal)):
        return await service.upload_credential(identity, connection_id, binding_id, body)

    @app.post("/api/v2/connections/{connection_id}/discover")
    async def discover(connection_id: UUID, body: DiscoveryCreate, identity=Depends(principal)):
        return await service.discover(identity, connection_id, body)

    @app.delete("/api/v2/connections/{connection_id}")
    async def revoke(connection_id: UUID, identity=Depends(principal)):
        result = await asyncio.to_thread(service.mark_revoked, identity, connection_id)
        # Revocation is durable before remote credential cleanup. Worker maintenance retries cleanup.
        return result
