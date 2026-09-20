import asyncio
from decimal import Decimal
import hashlib
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update

from app.admin.contracts import AgentCreate, GrantCreate
from app.connections.contracts import ServerCreate, DiscoveryCreate, ServerPublish, ToolSelection
from app.connections.driver import MCPDriver
from app.db import schema as s
from app.db.provisioning import provision_model
from app.platform_errors import PlatformError
from app.runtime.contracts import ModelTurn, PlannedCall
from app.runtime.worker import DurableWorker, ToolDrivers
from connector_fixtures import connect, create_run, TOKEN_A, TOKEN_B
from lock_fixtures import resource_before_run


async def published(t, remote_name="identity"):
    service, p = t["connections"], t["alice"]
    server = service.create_server(
        p, ServerCreate(name="Isolated stdio MCP", version="1", endpoint_id=t["endpoint"].id)
    )
    connection = await connect(t, p, server, TOKEN_A)
    found = await service.discover(p, connection["id"], DiscoveryCreate(request_id=uuid4()))
    server = service.publish(
        p,
        server["id"],
        ServerPublish(
            expected_revision=0,
            discovery_id=found["id"],
            tools=(ToolSelection(remote_name=remote_name, alias="company_lookup"),),
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
            name="Stdio agent",
            version="1",
            instruction="Use only the current scoped connection",
            model_id=UUID(model["id"]),
            mcp_server_ids=(server["id"],),
            run_budget=Decimal(".1"),
            max_rounds=4,
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


class Model:
    max_charge = Decimal(".020000")

    def charge(self, turn):
        return Decimal(".001000")

    async def stream(self, messages, tools):
        prior = [item for item in messages if item["role"] == "tool"]
        if len(prior) < 2:
            yield ModelTurn(
                tool_calls=(
                    PlannedCall(id="provider-call", name="company_lookup", arguments={"query": "my identity"}),
                ),
                finish_reason="tool_calls",
                input_tokens=10,
                output_tokens=2,
            )
        else:
            yield ModelTurn(content=prior[-1]["content"], finish_reason="stop", input_tokens=10, output_tokens=5)

    async def close(self):
        pass


class Models:
    def create(self, definition):
        return Model()


def worker(t, id="stdio-worker"):
    driver = MCPDriver(t["connector_client"])
    return DurableWorker(t["store"], t["org"], id, Models(), ToolDrivers({"mcp.stdio": driver, "mcp.http": driver}))


def test_real_gateway_to_stdio_two_users_and_run_scoped_session_lifecycle(stdio_platform):
    t = stdio_platform

    async def run():
        server, connection, agent = await published(t)
        bob = await connect(t, t["bob"], server, TOKEN_B)
        a = create_run(t, t["alice"], agent)
        b = create_run(t, t["bob"], agent)
        result_a = await worker(t, "worker-a").run_once()
        result_b = await worker(t, "worker-b").run_once()
        assert result_a["state"] == result_b["state"] == "succeeded", (result_a, result_b)
        answer_a = t["service"].get_run(t["alice"], a["run_id"])["result"]["answer"]
        answer_b = t["service"].get_run(t["bob"], b["run_id"])["result"]["answer"]
        assert hashlib.sha256(TOKEN_A.encode()).hexdigest() in answer_a
        assert hashlib.sha256(TOKEN_B.encode()).hexdigest() in answer_b
        assert TOKEN_A not in answer_a and TOKEN_B not in answer_b
        for text in (answer_a, answer_b):
            value = json.loads(text)
            data = value.get("structured_content") or json.loads(value["content"][0]["text"])
            assert data["calls"] == 2
        with t["db"].transaction(t["alice"]) as c:
            leases = (
                c.execute(select(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.run_id.in_([a["run_id"], b["run_id"]])))
                .mappings()
                .all()
            )
            assert len(leases) == 2 and all(
                row["state"] == "destroyed" and row["close_reason"] == "requested" for row in leases
            )
            assert len({row["backend_id"] for row in leases}) == 2
            invs = (
                c.execute(select(s.invocations).where(s.invocations.c.run_id.in_([a["run_id"], b["run_id"]])))
                .mappings()
                .all()
            )
            assert len(invs) == 4 and all(row["state"] == "succeeded" for row in invs)
        assert not t["manager"].backend.client.containers.list(
            all=True, filters={"label": "aio.manager=" + t["manager"].journal.installation_id}
        )
        assert connection["id"] != bob["id"]

    asyncio.run(run())


def test_stdio_template_or_credential_scope_cannot_be_forged(stdio_platform):
    t = stdio_platform

    async def run():
        server, connection, agent = await published(t)
        run = create_run(t, t["alice"], agent)
        result = await worker(t).run_once()
        assert result["state"] == "succeeded", result
        with t["db"].transaction(t["alice"]) as c:
            lease = (
                c.execute(select(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.run_id == run["run_id"]))
                .mappings()
                .one()
            )
        for field, value in [
            ("generation", lease["generation"] + 1),
            ("credential_ref", str(uuid4())),
            ("profile_id", "host-shell"),
            ("target_id", str(uuid4())),
        ]:
            with pytest.raises(PlatformError):
                t["stdio_authority"].authorize("alive", {"spec": {**lease["spec"], field: value}})
        with pytest.raises(PlatformError):
            create_run(t, t["bob"], agent, bindings={str(server["id"]): str(connection["id"])})

    asyncio.run(run())


def test_stdio_lost_process_is_not_replayed_after_a_worker_loss(stdio_platform):
    t = stdio_platform

    async def run():
        server, connection, agent = await published(t)
        created = create_run(t, t["alice"], agent)
        original = t["store"].complete_dispatch

        class Crash(BaseException):
            pass

        def completed(*args, **kwargs):
            original(*args, **kwargs)
            raise Crash()

        t["store"].complete_dispatch = completed
        with pytest.raises(Crash):
            await worker(t).run_once()
        t["store"].complete_dispatch = original
        with t["db"].transaction(t["alice"]) as c:
            lease = (
                c.execute(select(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.run_id == created["run_id"]))
                .mappings()
                .one()
            )
        from aio_sandbox_manager.stdio_contracts import StdioSpec

        t["executor"].stop(StdioSpec.model_validate(lease["spec"]))
        with t["admin"].begin() as c:
            from datetime import datetime, timedelta, timezone

            c.execute(
                update(s.jobs)
                .where(s.jobs.c.run_id == created["run_id"])
                .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )
        t["store"].recover_due(t["org"])
        state = t["service"].get_run(t["alice"], created["run_id"])
        assert state["state"] == "recovery_required"
        assert await worker(t, "replacement").run_once() is None

    asyncio.run(run())


@pytest.mark.parametrize("revoked", [False, True])
def test_stdio_stop_receipt_locks_resources_before_run_to_avoid_worker_deadlock(stdio_platform, monkeypatch, revoked):
    """Observe a real blocked PG backend, not a timing guess; the heartbeat's next Run lock must be free."""
    t = stdio_platform

    async def prepare_receipt():
        _, _, agent = await published(t)
        created = create_run(t, t["alice"], agent)
        original = t["store"].complete_dispatch

        class Crash(BaseException):
            pass

        def completed(*args, **kwargs):
            original(*args, **kwargs)
            raise Crash()

        monkeypatch.setattr(t["store"], "complete_dispatch", completed)
        with pytest.raises(Crash):
            await worker(t).run_once()
        monkeypatch.setattr(t["store"], "complete_dispatch", original)
        with t["db"].transaction(t["alice"]) as c:
            lease = (
                c.execute(select(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.run_id == created["run_id"]))
                .mappings()
                .one()
            )
        result = t["stdio_authority"].cleanup(
            {"org_id": str(t["org"]), "run_id": str(created["run_id"]), "generation": lease["generation"]}
        )
        assert result["specs"] == [lease["spec"]]
        from aio_sandbox_manager.stdio_contracts import decode_spec

        spec = decode_spec(json.dumps(lease["spec"]))
        # Actually stop the owned process, leaving only its authoritative PG receipt pending.
        assert t["manager"].stop(spec)["state"] == "destroyed"
        assert t["manager"].backend.checked(spec, None) is None
        return created["run_id"], lease["spec"]

    run_id, spec = asyncio.run(prepare_receipt())
    if revoked:
        # Structural cleanup is still allowed after organization/actor business access is disabled.
        with t["admin"].begin() as c:
            c.execute(update(s.organizations).where(s.organizations.c.id == t["org"]).values(active=False))
    resource_before_run(
        t,
        monkeypatch,
        run_id,
        lambda: t["stdio_authority"].authorize(
            "stdio.stopped", {"spec": spec, "manager_id": t["manager"].journal.installation_id}
        ),
    )
    with t["db"].transaction(t["alice"]) as c:
        lease = c.execute(select(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.run_id == run_id)).mappings().one()
        assert lease["state"] == "destroyed" and lease["close_reason"] == "requested"
