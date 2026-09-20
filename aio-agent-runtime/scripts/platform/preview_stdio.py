"""Finite preview: actual container stdio execution with synthetic credential identities."""

from decimal import Decimal
from uuid import UUID, uuid4

TOKENS = {
    "admin": "synthetic-stdio-admin-credential",
    "alice": "synthetic-stdio-alice-credential",
    "bob": "synthetic-stdio-bob-credential",
}


async def seed(database, settings, principal, model_id, departments):
    from app.admin.service import AdminService
    from app.admin.contracts import AgentCreate, GrantCreate
    from app.connections.client import ConnectorClient
    from app.connections.service import ConnectionService
    from app.connections.contracts import (
        ServerCreate,
        ConnectionCreate,
        CredentialPrepare,
        CredentialUpload,
        DiscoveryCreate,
        ServerPublish,
        ToolSelection,
    )
    from app.platform_settings import DeploymentMode

    if settings.mode is not DeploymentMode.TEST:
        raise RuntimeError("Reference stdio fixtures require a finite test deployment")
    client = ConnectorClient(settings.connector_url, settings.connector_token)
    service = ConnectionService(database, settings, client)
    try:
        server = service.create_server(
            principal, ServerCreate(name="隔离 stdio MCP", version="1", endpoint_id="company-stdio")
        )
        connection = service.create_connection(
            principal, ConnectionCreate(server_id=server["id"], name="管理员 stdio 合成身份")
        )
        prepared = service.prepare_credential(
            principal, connection["id"], CredentialPrepare(expected_revision=0, request_id=uuid4())
        )
        await service.upload_credential(
            principal, connection["id"], prepared["binding_id"], CredentialUpload(secret=TOKENS["admin"])
        )
        found = await service.discover(principal, connection["id"], DiscoveryCreate(request_id=uuid4()))
        server = service.publish(
            principal,
            server["id"],
            ServerPublish(
                expected_revision=0,
                discovery_id=found["id"],
                tools=(
                    ToolSelection(remote_name="identity", alias="stdio_identity"),
                    ToolSelection(remote_name="read_attachment", alias="stdio_read_attachment"),
                ),
                acknowledge_readonly_credentials=True,
            ),
        )
        admin = AdminService(database, settings)
        agent = admin.create_agent(
            principal,
            AgentCreate(
                name="隔离进程资料助手",
                version="1",
                instruction="使用专属无网 stdio MCP 进程读取合成身份摘要；只有模板和本次任务均允许时才可读取所选附件。",
                model_id=UUID(str(model_id)),
                mcp_server_ids=(server["id"],),
                run_budget=Decimal(".1"),
                max_rounds=4,
            ),
        )
        for department in departments:
            admin.set_grants(
                principal,
                agent["id"],
                GrantCreate(
                    subject_type="department",
                    subject_id=department,
                    actions=("agent.read", "agent.use"),
                    include_dependencies=True,
                ),
            )
        return {"agent_id": str(agent["id"]), "server_id": str(server["id"])}
    finally:
        await client.close()
