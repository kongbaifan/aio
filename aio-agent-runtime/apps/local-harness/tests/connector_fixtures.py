"""Synthetic upstream data with the actual private gateway and PostgreSQL control authority."""

import asyncio
from dataclasses import replace
from decimal import Decimal
import json
import secrets
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import update

from app.admin.contracts import AgentCreate, GrantCreate
from app.admin.service import AdminService
from app.connections.authority import ConnectorAuthority
from app.connections.client import ConnectorClient
from app.connections.contracts import (
    ConnectionCreate,
    CredentialPrepare,
    CredentialUpload,
    DiscoveryCreate,
    ServerCreate,
    ServerPublish,
    ToolSelection,
)
from app.connections.service import ConnectionService
from app.db import schema as s
from app.db.provisioning import provision_model
from app.runtime.contracts import ModelTurn, PlannedCall
from app.runtime.execution import ExecutionStore
from app.runtime.service import PlatformService

TOKEN_A = "synthetic-personal-alice-token"
TOKEN_B = "synthetic-personal-bob-token"
TOKEN_D = "synthetic-department-service-token"


class Stream(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value

    async def __aiter__(self):
        yield self.value


class Upstream:
    def __init__(self):
        self.effects = []
        self.lost = False
        self.call_barrier = None
        self.description = "Read the identity of the synthetic upstream credential"

    async def handle(self, request):
        headers = {"Content-Type": "application/json"}
        if request.headers.get("Authorization") not in {"Bearer " + token for token in (TOKEN_A, TOKEN_B, TOKEN_D)}:
            return httpx.Response(401, headers=headers, stream=Stream(b'{"error":"synthetic_auth_required"}'))
        status = 200
        if request.method == "DELETE":
            return httpx.Response(204, stream=Stream(b""))
        body = json.loads(request.content)
        method = body.get("method")
        if method == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "synthetic-company-mcp", "version": "1"},
            }
            headers["Mcp-Session-Id"] = uuid4().hex
        elif method == "notifications/initialized":
            status, result = 202, None
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "lookup_identity",
                        "description": self.description,
                        "inputSchema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    }
                ]
            }
        else:
            assert method == "tools/call"
            token = request.headers["Authorization"].removeprefix("Bearer ")
            subject = {
                TOKEN_A: "alice-upstream-data",
                TOKEN_B: "bob-upstream-data",
                TOKEN_D: "department-upstream-data",
            }[token]
            self.effects.append(subject)
            if self.call_barrier is not None:
                await asyncio.wait_for(self.call_barrier.wait(), timeout=10)
            if self.lost:
                raise httpx.ReadError("Synthetic lost response after upstream RPC", request=request)
            result = {"content": [{"type": "text", "text": subject}], "structuredContent": {"subject": subject}}
        data = (
            json.dumps({"jsonrpc": "2.0", "id": body.get("id"), "result": result}).encode()
            if result is not None
            else b""
        )
        return httpx.Response(status, headers=headers, stream=Stream(data))


@pytest.fixture
def mcp_platform(tenant, tmp_path):
    from aio_connector_gateway.api import create_app
    from aio_connector_gateway.contracts import Endpoint, GatewayError
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
    ep = Endpoint("company", "http://127.0.0.1:9191/mcp", frozenset({"lookup_identity"}), test_mode=True)
    settings = replace(
        t["settings"],
        connector_url="http://127.0.0.1:9292",
        connector_token="synthetic-gateway-" + "g" * 40,
        connector_control_token="synthetic-authority-" + "c" * 40,
        connector_profiles=(
            {
                "id": ep.id,
                "url": ep.url,
                "digest": ep.digest,
                "authentication": ep.authentication,
                "read_tools": ["lookup_identity"],
                "timeout_seconds": 30,
            },
        ),
    )
    store = ExecutionStore(t["db"], settings)
    upstream = Upstream()
    vault = Vault((tmp_path / "private-gateway").resolve(), secrets.token_bytes(32))
    holder = {}

    class Guard:
        async def validate(self, operation, payload):
            try:
                await asyncio.to_thread(holder["authority"].authorize, operation, payload)
            except Exception:
                raise GatewayError("CONTROL_AUTHORIZATION_DENIED", 403, not_sent=True) from None

    def factory(endpoint, token):
        result = MCPClient(
            endpoint, token, http_client=httpx.AsyncClient(transport=httpx.MockTransport(upstream.handle))
        )
        result._owned = True
        return result

    gateway = ConnectorGateway(vault, {ep.id: ep}, Guard(), client_factory=factory)
    app = create_app(gateway, settings.connector_token, manage_lifecycle=False)
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app))
    client = ConnectorClient(settings.connector_url, settings.connector_token, client=http)
    service = ConnectionService(t["db"], settings, client)
    holder["authority"] = ConnectorAuthority(store, service)
    t.update(
        settings=settings,
        connections=service,
        store=store,
        service=PlatformService(t["db"], settings),
        administration=AdminService(t["db"], settings),
        connector_client=client,
        connector_http=http,
        gateway=gateway,
        gateway_app=app,
        authority=holder["authority"],
        vault=vault,
        upstream=upstream,
    )
    try:
        yield t
    finally:
        asyncio.run(http.aclose())
        vault.close()


async def connect(t, p, server, token, *, department=None):
    service = t["connections"]
    conn = service.create_connection(
        p,
        ConnectionCreate(
            server_id=server["id"],
            name="Synthetic authorized connection",
            scope="department" if department else "personal",
            department_id=department,
        ),
    )
    prepared = service.prepare_credential(
        p, conn["id"], CredentialPrepare(expected_revision=conn["resource_revision"], request_id=uuid4())
    )
    await service.upload_credential(p, conn["id"], prepared["binding_id"], CredentialUpload(secret=token))
    await service.discover(p, conn["id"], DiscoveryCreate(request_id=uuid4()))
    return next(row for row in service.list_connections(p) if row["id"] == conn["id"])


async def publish(t):
    service, p = t["connections"], t["alice"]
    server = service.create_server(p, ServerCreate(name="Shared company MCP", version="1.0.0", endpoint_id="company"))
    connection = await connect(t, p, server, TOKEN_A)
    discovered = await service.discover(p, connection["id"], DiscoveryCreate(request_id=uuid4()))
    server = service.publish(
        p,
        server["id"],
        ServerPublish(
            expected_revision=0,
            discovery_id=discovered["id"],
            tools=(ToolSelection(remote_name="lookup_identity", alias="company_lookup"),),
            acknowledge_readonly_credentials=True,
        ),
    )
    with t["admin"].begin() as c:
        model = provision_model(
            c,
            org_id=t["org"],
            owner_id=p.user_id,
            provider="synthetic",
            model="synthetic",
            config={"max_call_charge": "0.020000"},
        )
    agent = t["administration"].create_agent(
        p,
        AgentCreate(
            name="Shared MCP Agent",
            version="1",
            instruction="Use authorized tools only",
            model_id=UUID(model["id"]),
            mcp_server_ids=(server["id"],),
            run_budget=Decimal("0.1"),
            max_rounds=3,
        ),
    )
    t["administration"].set_grants(
        p,
        agent["id"],
        GrantCreate(
            subject_type="user",
            subject_id=t["bob"].user_id,
            actions=("agent.read", "agent.use"),
            include_dependencies=True,
        ),
    )
    return server, connection, agent


def create_run(t, p, agent, *, bindings=None):
    project = t["service"].create_project(p, "Private MCP work")
    session = t["service"].create_session(p, project["id"], agent["id"], "MCP identity isolation")
    run = t["service"].create_run(
        p,
        session["id"],
        {
            "message": "read my data",
            "agent_version_id": str(agent["id"]),
            "expected_session_revision": 0,
            "mode": "single",
            "input_artifact_ids": [],
            "connection_bindings": bindings or {},
        },
        "mcp-run-" + uuid4().hex,
    )
    return {**run, "session_id": session["id"]}


class Model:
    max_charge = Decimal("0.020000")

    def __init__(self, factory):
        self.factory = factory

    def charge(self, turn):
        return Decimal("0.001000")

    async def stream(self, messages, tools):
        self.factory.messages = messages
        data = [m for m in messages if m["role"] == "tool"]
        if data:
            yield ModelTurn(content=data[-1]["content"], finish_reason="stop", input_tokens=10, output_tokens=5)
        else:
            yield ModelTurn(
                tool_calls=(PlannedCall(id="provider-call", name="company_lookup", arguments={"query": "my data"}),),
                finish_reason="tool_calls",
                input_tokens=10,
                output_tokens=5,
            )

    async def close(self):
        pass


class ModelFactory:
    def __init__(self):
        self.messages = []

    def create(self, definition):
        return Model(self)
