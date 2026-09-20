"""Actual compute isolation and artifact provenance for data returned through the private MCP gateway."""

import asyncio
from dataclasses import replace
from decimal import Decimal
import json
import os
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.admin.contracts import AgentCreate, GrantCreate
from app.db import schema as s
from app.db.provisioning import provision_tool
from app.execution.coordinator import SandboxCoordinator
from app.execution.sandbox_client import ManagerClient, SandboxPythonDriver
from app.connections.driver import MCPDriver
from app.platform_errors import PlatformError
from app.runtime.contracts import ModelTurn, PlannedCall
from app.runtime.execution import ExecutionStore
from app.runtime.worker import DurableWorker, ToolDrivers
from app.workspaces.service import ArtifactService
from app.workspaces.storage import BlobStore
from connector_fixtures import create_run, publish, TOKEN_A


def test_mcp_credentials_never_enter_compute_and_data_provenance_cannot_be_shared_away(
    mcp_platform, tmp_path, monkeypatch
):
    image = os.environ.get("AIO_TEST_COMPUTE_IMAGE")
    if not image:
        pytest.skip("Real MCP/compute boundary requires AIO_TEST_COMPUTE_IMAGE")
    from aio_sandbox_manager.api import create_app
    from aio_sandbox_manager.contracts import Profile
    from aio_sandbox_manager.docker_backend import DockerBackend
    from aio_sandbox_manager.journal import Journal
    from aio_sandbox_manager.service import SandboxManager

    t = mcp_platform
    monkeypatch.setenv("CONNECTOR_VAULT_KEY", "synthetic-host-only-key-canary")
    monkeypatch.setenv("CONNECTOR_SERVICE_TOKEN", t["settings"].connector_token)
    settings = replace(t["settings"], artifact_root=(tmp_path / "artifacts").resolve())
    store = ExecutionStore(t["db"], settings)
    artifacts = ArtifactService(t["db"], BlobStore(settings.artifact_root))
    coordinator = SandboxCoordinator(store, artifacts)
    journal = Journal((tmp_path / "compute-manager").resolve())

    class Guard:
        def validate(self, operation, payload):
            coordinator.authorize(operation, payload)

    manager = SandboxManager(journal, DockerBackend(journal.installation_id), {"test": Profile("test", image)}, Guard())
    token = "synthetic-separate-compute-manager-" + "m" * 40
    app = create_app(manager, token, manage_lifecycle=False)

    class Model:
        max_charge = Decimal("0.020000")

        def charge(self, turn):
            return Decimal("0.001000")

        async def stream(self, messages, tools):
            results = [message for message in messages if message["role"] == "tool"]
            if not results:
                call = PlannedCall(id="mcp-data", name="company_lookup", arguments={"query": "mine"})
            elif len(results) == 1:
                source = json.loads(results[0]["content"])["structured_content"]["subject"]
                code = (
                    "import os,socket\nfrom pathlib import Path\n"
                    "assert os.getuid()==10001\n"
                    "assert not os.environ.get('CONNECTOR_VAULT_KEY')\n"
                    "assert not os.environ.get('CONNECTOR_SERVICE_TOKEN')\n"
                    "assert not Path('/var/run/docker.sock').exists()\n"
                    "s=socket.socket();s.settimeout(0.1)\n"
                    "try:\n s.connect(('1.1.1.1',443))\n"
                    "except OSError:\n pass\n"
                    "else:\n raise RuntimeError('compute gained credential network access')\n"
                    "finally:\n s.close()\n"
                    f"Path('mcp-derived.txt').write_text({source!r})\n"
                )
                call = PlannedCall(id="compute-data", name="python_compute", arguments={"code": code})
            else:
                yield ModelTurn(
                    content="Isolated data processing completed", finish_reason="stop", input_tokens=10, output_tokens=5
                )
                return
            yield ModelTurn(tool_calls=(call,), finish_reason="tool_calls", input_tokens=10, output_tokens=5)

        async def close(self):
            pass

    class Factory:
        def create(self, definition):
            return Model()

    async def run():
        server, connection, original_agent = await publish(t)
        with t["admin"].begin() as c:
            model = c.execute(
                select(s.agent_versions.c.manifest).where(s.agent_versions.c.id == original_agent["id"])
            ).scalar_one()["model"]
            tool = provision_tool(
                c,
                org_id=t["org"],
                owner_id=t["alice"].user_id,
                name="python_compute",
                driver="sandbox.python",
                risk="R1",
                input_schema={
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                    "additionalProperties": False,
                },
                config={
                    "sandbox_profile": "test",
                    "image_digest": image,
                    "network_profile_id": "none",
                    "timeout_seconds": 10,
                },
            )
        agent = t["administration"].create_agent(
            t["alice"],
            AgentCreate(
                name="MCP and isolated compute",
                version="1",
                instruction="Use only authorized connections and isolated compute",
                model_id=UUID(model["id"]),
                tool_ids=(UUID(tool["id"]),),
                mcp_server_ids=(server["id"],),
                run_budget=Decimal("0.1"),
                max_rounds=4,
            ),
        )
        run = create_run(t, t["alice"], agent)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as http:
            driver = SandboxPythonDriver(coordinator, ManagerClient("http://127.0.0.1:9009", token, client=http))
            result = await DurableWorker(
                store,
                t["org"],
                "mcp-compute-worker",
                Factory(),
                ToolDrivers({"mcp.http": MCPDriver(t["connector_client"]), "sandbox.python": driver}),
            ).run_once()
        assert result["state"] == "succeeded", result
        info = t["service"].get_run(t["alice"], run["run_id"])
        file = next(item for item in info["result"]["artifacts"] if item["path"] == "mcp-derived.txt")
        meta, data = artifacts.download(t["alice"], UUID(file["artifact_id"]))
        assert data == b"alice-upstream-data" and TOKEN_A.encode() not in data
        with t["db"].transaction(t["alice"]) as c:
            row = artifacts.require_artifact(c, t["alice"], meta["id"])
            assert row["mcp_source_refs"] == [{"connection_id": str(connection["id"]), "credential_revision": 1}]
        t["administration"].set_grants(
            t["alice"],
            meta["project_id"],
            GrantCreate(subject_type="user", subject_id=t["bob"].user_id, actions=("project.read",)),
        )
        t["administration"].set_grants(
            t["alice"],
            meta["id"],
            GrantCreate(
                subject_type="user", subject_id=t["bob"].user_id, actions=("artifact.read", "artifact.download")
            ),
        )
        with pytest.raises(PlatformError):
            artifacts.download(t["bob"], meta["id"])
        t["connections"].mark_revoked(t["alice"], connection["id"])
        with pytest.raises(PlatformError):
            artifacts.download(t["alice"], meta["id"])

    try:
        asyncio.run(run())
    finally:
        manager.close()
