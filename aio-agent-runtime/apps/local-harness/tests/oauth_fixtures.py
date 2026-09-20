"""Real platform/gateway stores and authority, explicitly synthetic OAuth issuer/MCP responses."""

import asyncio
from dataclasses import replace
from pathlib import Path
import secrets
import sys

import httpx
import pytest
from sqlalchemy import update

from app.auth.service import AuthService
from app.connections.authority import ConnectorAuthority
from app.connections.client import ConnectorClient
from app.connections.oauth_service import OAuthService
from app.connections.oauth_settings import public_oauth
from app.connections.service import ConnectionService
from app.db import schema as s
from app.runtime.execution import ExecutionStore

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts/platform"))
from oauth_fixture import OAuthFixture


@pytest.fixture
def oauth_platform(tenant, tmp_path):
    from aio_connector_gateway.api import create_app
    from aio_connector_gateway.contracts import Endpoint, GatewayError
    from aio_connector_gateway.oauth_http import OAuthHTTP
    from aio_connector_gateway.protocol import MCPClient
    from aio_connector_gateway.service import ConnectorGateway
    from aio_connector_gateway.vault import Vault

    t = dict(tenant)
    with t["admin"].begin() as c:
        c.execute(
            update(s.memberships)
            .where(s.memberships.c.org_id == t["org"], s.memberships.c.user_id == t["alice"].user_id)
            .values(role="org_admin")
        )
    upstream = OAuthFixture(platform=t["settings"].public_origin)
    ep = Endpoint(
        upstream.endpoint_id,
        upstream.origin + "/mcp",
        frozenset({"lookup_identity"}),
        authentication="oauth2",
        oauth=upstream.policy(),
        test_mode=True,
    )
    profile = {
        "id": ep.id,
        "url": ep.url,
        "authentication": "oauth2",
        "digest": ep.digest,
        "read_tools": ["lookup_identity"],
        "timeout_seconds": 30,
        "oauth": public_oauth(upstream.policy(), ep.id, ep.url, False),
    }
    settings = replace(
        t["settings"],
        connector_url="http://127.0.0.1:9292",
        connector_token="oauth-gateway-" + "g" * 40,
        connector_control_token="oauth-control-" + "c" * 40,
        connector_profiles=(profile,),
    )
    auth = AuthService(t["db"], settings)
    alice_token, alice = auth.create_session(t["org"], settings.oidc_issuer, str(t["alice"].user_id))
    bob_token, bob = auth.create_session(t["org"], settings.oidc_issuer, str(t["bob"].user_id))
    store = ExecutionStore(t["db"], settings)
    vault = Vault((tmp_path / "oauth-gateway").resolve(), secrets.token_bytes(32))
    holder = {}

    class Guard:
        async def validate(self, operation, payload):
            try:
                await asyncio.to_thread(holder["authority"].authorize, operation, payload)
            except Exception:
                raise GatewayError("CONTROL_AUTHORIZATION_DENIED", 403, not_sent=True) from None

    def oauth_http(endpoint):
        return OAuthHTTP(
            endpoint,
            client_factory=lambda target: httpx.AsyncClient(
                transport=httpx.MockTransport(upstream.handle), follow_redirects=False
            ),
        )

    gateway = ConnectorGateway(
        vault,
        {ep.id: ep},
        Guard(),
        client_factory=lambda endpoint, token: MCPClient(
            endpoint, token, http_client=httpx.AsyncClient(transport=httpx.MockTransport(upstream.handle))
        ),
        oauth_http_factory=oauth_http,
    )
    app = create_app(gateway, settings.connector_token, manage_lifecycle=False)
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=settings.connector_url)
    client = ConnectorClient(settings.connector_url, settings.connector_token, client=http)
    service = ConnectionService(t["db"], settings, client)
    authority = ConnectorAuthority(store, service)
    holder["authority"] = authority
    t.update(
        settings=settings,
        auth=auth,
        alice=alice,
        bob=bob,
        alice_token=alice_token,
        bob_token=bob_token,
        gateway=gateway,
        vault=vault,
        upstream=upstream,
        connector_client=client,
        connections=service,
        oauth=OAuthService(service),
        authority=authority,
        store=store,
    )
    try:
        yield t
    finally:
        asyncio.run(http.aclose())
        vault.close()
