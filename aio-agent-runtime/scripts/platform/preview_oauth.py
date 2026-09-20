"""Seed only the finite synthetic OAuth preview using the real gateway authorization flow."""

from decimal import Decimal
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4


async def seed(database, settings, org, fixture, model_id, departments):
    from app.auth.service import AuthService
    from app.admin.service import AdminService
    from app.admin.contracts import AgentCreate, GrantCreate
    from app.connections.client import ConnectorClient
    from app.connections.service import ConnectionService
    from app.connections.oauth_service import OAuthService
    from app.connections.contracts import (
        ServerCreate,
        ConnectionCreate,
        CredentialPrepare,
        DiscoveryCreate,
        ServerPublish,
        ToolSelection,
    )
    from app.platform_settings import DeploymentMode

    if settings.mode is not DeploymentMode.TEST:
        raise RuntimeError("Synthetic OAuth seeding is not a production account bootstrap")
    _, p = AuthService(database, settings).create_session(org, settings.oidc_issuer, "admin")
    client = ConnectorClient(settings.connector_url, settings.connector_token)
    service = ConnectionService(database, settings, client)
    try:
        server = service.create_server(
            p, ServerCreate(name="OAuth 资料 MCP", version="1.0.0", endpoint_id=fixture.endpoint_id)
        )
        connection = service.create_connection(
            p, ConnectionCreate(server_id=server["id"], name="管理员合成 OAuth 身份")
        )
        oauth = OAuthService(service)
        started = await oauth.start(p, connection["id"], CredentialPrepare(expected_revision=0, request_id=uuid4()))
        callback = parse_qs(
            urlsplit(fixture.authorize(parse_qs(urlsplit(started["authorization_url"]).query), "admin")).query
        )
        await oauth.callback(
            p, fixture.endpoint_id, callback["state"][0], callback["code"][0], issuer=callback["iss"][0]
        )
        found = await service.discover(p, connection["id"], DiscoveryCreate(request_id=uuid4()))
        server = service.publish(
            p,
            server["id"],
            ServerPublish(
                expected_revision=0,
                discovery_id=found["id"],
                tools=(ToolSelection(remote_name="lookup_identity", alias="mcp_identity"),),
                acknowledge_readonly_credentials=True,
            ),
        )
        admin = AdminService(database, settings)
        agent = admin.create_agent(
            p,
            AgentCreate(
                name="OAuth 身份资料助手",
                version="1.0",
                instruction="仅用当前用户的授权连接读取合成资料。",
                model_id=UUID(str(model_id)),
                mcp_server_ids=(server["id"],),
                run_budget=Decimal(".1"),
                max_rounds=4,
            ),
        )
        for department in departments:
            admin.set_grants(
                p,
                agent["id"],
                GrantCreate(
                    subject_type="department",
                    subject_id=department,
                    actions=("agent.read", "agent.use"),
                    include_dependencies=True,
                ),
            )
        return {"server_id": str(server["id"]), "agent_id": str(agent["id"])}
    finally:
        await client.close()
