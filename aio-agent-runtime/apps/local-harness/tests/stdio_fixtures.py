"""Real isolated MCP stdio, gateway and PostgreSQL authority; synthetic upstream identity data only."""

import asyncio
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import secrets

import httpx
import pytest
from sqlalchemy import update

from app.admin.service import AdminService
from app.connections.authority import ConnectorAuthority
from app.connections.client import ConnectorClient
from app.connections.service import ConnectionService
from app.connections.stdio import StdioAuthority
from app.connections.stdio_settings import stdio_policy
from app.db import schema as s
from app.runtime.execution import ExecutionStore
from app.runtime.service import PlatformService


@pytest.fixture
def stdio_platform(tenant, tmp_path, request):
    image = os.environ.get("AIO_TEST_STDIO_IMAGE")
    if not image:
        pytest.skip("Stdio integration requires AIO_TEST_STDIO_IMAGE")
    from aio_sandbox_manager.api import create_app as manager_app
    from aio_sandbox_manager.contracts import ManagerError
    from aio_sandbox_manager.docker_backend import DockerBackend
    from aio_sandbox_manager.journal import Journal
    from aio_sandbox_manager.service import SandboxManager
    from aio_sandbox_manager.stdio_contracts import StdioProfile
    from aio_sandbox_manager.stdio_service import StdioManager
    from aio_connector_gateway.api import create_app
    from aio_connector_gateway.contracts import Endpoint, GatewayError
    from aio_connector_gateway.service import ConnectorGateway
    from aio_connector_gateway.stdio_client import StdioManagerClient
    from aio_connector_gateway.vault import Vault

    t = dict(tenant)
    with t["admin"].begin() as c:
        c.execute(
            update(s.memberships)
            .where(s.memberships.c.org_id == t["org"], s.memberships.c.user_id == t["alice"].user_id)
            .values(role="org_admin")
        )
    root = Path(__file__).resolve().parents[3]
    profile = StdioProfile(
        id="stdio-reference",
        image_digest=image,
        executable="/usr/local/bin/python",
        arguments=("-I", "-u", "/opt/mcp/example_server.py"),
        dependency_digest=hashlib.sha256(
            (root / "services/mcp-stdio-runtime/requirements.lock").read_bytes()
        ).hexdigest(),
        credential_env="MCP_ACCESS_TOKEN",
        input_policy=getattr(request, "param", "none"),
    )
    public = {
        "profile_id": profile.id,
        "image_digest": image,
        "template_digest": profile.template_digest,
        "credential_env": profile.credential_env,
        "network_profile": "none",
    }
    if profile.input_policy != "none":
        public["input_policy"] = profile.input_policy
    endpoint = Endpoint(
        "local-mcp",
        "stdio://" + profile.id,
        frozenset({"identity", "isolation_facts", "read_private", "list_attachments", "read_attachment"}),
        transport="stdio",
        stdio=public,
    )
    settings = replace(
        t["settings"],
        artifact_root=(tmp_path / "private-artifacts").resolve(),
        connector_url="http://127.0.0.1:9292",
        connector_token="stdio-gateway-" + ("g" * 40),
        connector_control_token="stdio-authority-" + ("a" * 40),
        connector_profiles=(
            {
                "id": endpoint.id,
                "url": endpoint.url,
                "digest": endpoint.digest,
                "transport": "stdio",
                "stdio": stdio_policy(public, endpoint.url, "bearer"),
                "authentication": "bearer",
                "read_tools": sorted(endpoint.read_tools),
                "timeout_seconds": 30,
            },
        ),
    )
    store = ExecutionStore(t["db"], settings)
    holder = {}
    t["manager_denials"] = []

    class ManagerGuard:
        def validate(self, operation, payload):
            try:
                holder["stdio"].authorize(operation, payload)
            except Exception as error:
                original = getattr(error, "orig", None)
                t["manager_denials"].append({"operation": operation, "code": getattr(error, "code", type(error).__name__), "sqlstate": getattr(original, "sqlstate", None), "database_error": type(original).__name__ if original else None, "statement": str(getattr(error, "statement", ""))[:180]})
                raise ManagerError("CONTROL_AUTHORIZATION_DENIED", "Synthetic control check failed", 403) from None

    journal = Journal((tmp_path / "stdio-manager").resolve())
    manager = SandboxManager(journal, DockerBackend(journal.installation_id), {}, ManagerGuard())
    executor = StdioManager(manager, {profile.id: profile})
    manager_token = "stdio-manager-" + ("m" * 40)
    app_manager = manager_app(
        manager, "compute-not-stdio-" + ("c" * 40), manage_lifecycle=False, stdio_token=manager_token
    )
    manager_http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app_manager), base_url="http://manager.test")
    transport = StdioManagerClient("http://127.0.0.1:9099", manager_token, test_mode=True, http_client=manager_http)

    class GatewayGuard:
        async def validate(self, operation, payload):
            try:
                await asyncio.to_thread(holder["connector"].authorize, operation, payload)
            except Exception:
                raise GatewayError("CONTROL_AUTHORIZATION_DENIED", 403, not_sent=True) from None

        async def stdio(self, operation, payload):
            try:
                if operation == "prepare":
                    context = payload["context"]
                    result = await asyncio.to_thread(holder["stdio"].prepare, context["operation"], context["payload"])
                elif operation == "inputs":
                    result = await asyncio.to_thread(holder["stdio"].inputs.load, payload)
                else:
                    result = await asyncio.to_thread(holder["stdio"].cleanup, payload)
                return {"allowed": True, **result}
            except Exception:
                raise GatewayError("STDIO_AUTHORITY_DENIED", 403, not_sent=True) from None

    vault = Vault((tmp_path / "credential-vault").resolve(), secrets.token_bytes(32))
    gateway = ConnectorGateway(vault, {endpoint.id: endpoint}, GatewayGuard(), stdio_manager=transport)
    gateway_app = create_app(gateway, settings.connector_token, manage_lifecycle=False)
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway_app), base_url=settings.connector_url)
    client = ConnectorClient(settings.connector_url, settings.connector_token, client=http)
    connections = ConnectionService(t["db"], settings, client)
    connector = ConnectorAuthority(store, connections)
    stdio = StdioAuthority(connector)
    holder.update(connector=connector, stdio=stdio)
    t.update(
        settings=settings,
        store=store,
        service=PlatformService(t["db"], settings),
        connections=connections,
        administration=AdminService(t["db"], settings),
        connector_client=client,
        gateway=gateway,
        gateway_app=gateway_app,
        manager=manager,
        executor=executor,
        stdio_authority=stdio,
        endpoint=endpoint,
        stdio_profile=profile,
        vault=vault,
        artifacts=store.workspace.artifacts,
    )
    try:
        yield t
    finally:
        manager.close()
        asyncio.run(manager_http.aclose())
        asyncio.run(http.aclose())
        vault.close()
