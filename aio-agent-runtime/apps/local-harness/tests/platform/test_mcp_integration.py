"""Real PostgreSQL + private gateway authority/credential journal; upstream data/model explicitly synthetic."""

import asyncio
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text

from app.admin.contracts import GrantCreate
from app.connections.contracts import ConnectionCreate, CredentialPrepare, CredentialUpload, DiscoveryCreate
from app.connections.driver import MCPDriver
from app.platform_errors import PlatformError
from app.runtime.worker import DurableWorker, ToolDrivers
from app.db import schema as s
from connector_fixtures import TOKEN_A, TOKEN_B, TOKEN_D, ModelFactory, connect, create_run, publish


def worker(t, factory=None, id="mcp-worker"):
    return DurableWorker(
        t["store"], t["org"], id, factory or ModelFactory(), ToolDrivers({"mcp.http": MCPDriver(t["connector_client"])})
    )


def test_same_agent_uses_each_users_own_credential_without_sharing_creator_token(mcp_platform):
    t = mcp_platform

    async def run():
        server, alice_connection, agent = await publish(t)
        bob_connection = await connect(t, t["bob"], server, TOKEN_B)
        alice_run = create_run(t, t["alice"], agent)
        bob_run = create_run(t, t["bob"], agent)
        # A non-blocking poll may legitimately find shared Agent resources busy.
        # Exercise the real persistent workers, not an assumption that each
        # run_once call must claim. The upstream barrier requires both users'
        # actual RPCs to overlap, and the result/effect assertions stay strict.
        t["upstream"].call_barrier = asyncio.Barrier(2)
        workers = [worker(t, id="worker-a"), worker(t, id="worker-b")]
        tasks = [asyncio.create_task(item.serve(poll_seconds=0.01)) for item in workers]
        try:
            async with asyncio.timeout(15):
                while True:
                    a, b = await asyncio.gather(
                        asyncio.to_thread(t["service"].get_run, t["alice"], alice_run["run_id"]),
                        asyncio.to_thread(t["service"].get_run, t["bob"], bob_run["run_id"]),
                    )
                    if all(
                        item["state"] in {"succeeded", "failed", "timed_out", "cancelled", "recovery_required"}
                        for item in (a, b)
                    ):
                        break
                    await asyncio.sleep(0.01)
            assert a["state"] == b["state"] == "succeeded", [(item["state"], item["error_code"]) for item in (a, b)]
        finally:
            for item in workers:
                item.stopping.set()
            outcomes = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=10)
            assert all(item is None for item in outcomes)
        assert sorted(t["upstream"].effects) == ["alice-upstream-data", "bob-upstream-data"]
        answer_a = t["service"].get_run(t["alice"], alice_run["run_id"])["result"]["answer"]
        answer_b = t["service"].get_run(t["bob"], bob_run["run_id"])["result"]["answer"]
        assert "alice-upstream-data" in answer_a and "bob-upstream-data" not in answer_a
        assert "bob-upstream-data" in answer_b and "alice-upstream-data" not in answer_b
        assert TOKEN_A not in answer_a and TOKEN_B not in answer_b
        for p, connection in [(t["alice"], alice_connection), (t["bob"], bob_connection)]:
            rows = t["connections"].list_connections(p)
            assert [r["id"] for r in rows] == [connection["id"]]
        with pytest.raises(PlatformError):
            create_run(t, t["bob"], agent, bindings={str(server["id"]): str(alice_connection["id"])})
        with t["db"].transaction(t["alice"]) as c:
            bindings = c.execute(select(s.mcp_bindings)).mappings().all()
            assert TOKEN_A not in str(bindings) and TOKEN_B not in str(bindings)
            assert c.execute(
                text("SELECT relforcerowsecurity FROM pg_class WHERE relname='aio_mcp_connections'")
            ).scalar_one()

    asyncio.run(run())


def test_personal_credentials_cannot_be_shared_even_by_admin_grants(mcp_platform):
    t = mcp_platform

    async def run():
        server, connection, agent = await publish(t)
        with pytest.raises(PlatformError) as blocked:
            t["administration"].set_grants(
                t["alice"],
                connection["id"],
                GrantCreate(subject_type="user", subject_id=t["bob"].user_id, actions=("connection.use",)),
            )
        assert blocked.value.code == "PERSONAL_CREDENTIAL_SHARING_DENIED"
        # Defense in depth: even a manually inserted bad grant cannot make a different user borrow a personal token.
        with t["admin"].begin() as c:
            c.execute(
                insert(s.grants).values(
                    org_id=t["org"],
                    id=uuid4(),
                    resource_id=connection["id"],
                    subject_id=t["bob"].user_id,
                    action="connection.use",
                )
            )
        with pytest.raises(PlatformError):
            create_run(t, t["bob"], agent, bindings={str(server["id"]): str(connection["id"])})
        assert t["upstream"].effects == []

    asyncio.run(run())


def test_manual_credential_identity_change_invalidates_queued_run_snapshot(mcp_platform):
    t = mcp_platform

    async def run():
        server, connection, agent = await publish(t)
        pending = create_run(t, t["alice"], agent)
        prepared = t["connections"].prepare_credential(
            t["alice"],
            connection["id"],
            CredentialPrepare(expected_revision=connection["resource_revision"], request_id=uuid4()),
        )
        changed = await t["connections"].upload_credential(
            t["alice"], connection["id"], prepared["binding_id"], CredentialUpload(secret=TOKEN_B)
        )
        assert changed["credential_revision"] == 2
        outcome = await worker(t).run_once()
        assert outcome["state"] != "succeeded"
        assert t["upstream"].effects == []
        with pytest.raises(PlatformError):
            t["service"].get_run(t["alice"], pending["run_id"])
        assert await t["connections"].cleanup(t["org"]) == 1

    asyncio.run(run())


def test_revocation_blocks_run_events_and_history_and_retires_gateway_ciphertext(mcp_platform):
    t = mcp_platform

    async def run():
        server, connection, agent = await publish(t)
        run = create_run(t, t["alice"], agent)
        assert (await worker(t).run_once())["state"] == "succeeded"
        t["connections"].mark_revoked(t["alice"], connection["id"])
        for read in [
            lambda: t["service"].get_run(t["alice"], run["run_id"]),
            lambda: t["service"].read_events(t["alice"], run["run_id"], 0),
        ]:
            with pytest.raises(PlatformError):
                read()
        history = t["service"].session_detail(t["alice"], run["session_id"])
        assert history["messages"][-1]["content"]["redacted"]
        assert await t["connections"].cleanup(t["org"]) == 1
        with sqlite3.connect(t["vault"].path) as c:
            assert not any(row[0] for row in c.execute("SELECT active FROM credentials"))

    asyncio.run(run())


def test_remote_schema_change_never_automatically_expands_published_tool(mcp_platform):
    t = mcp_platform

    async def run():
        server, connection, agent = await publish(t)
        t["upstream"].description = "new unreviewed tool guidance"
        run = create_run(t, t["alice"], agent)
        result = await worker(t).run_once()
        assert t["upstream"].effects == []
        assert result["state"] != "recovery_required", result
        with t["db"].transaction(t["alice"]) as c:
            inv = c.execute(select(s.invocations).where(s.invocations.c.run_id == run["run_id"])).mappings().one()
            assert inv["state"] == "failed"

    asyncio.run(run())


def test_lost_mcp_response_requires_reconciliation_not_a_second_upstream_call(mcp_platform):
    t = mcp_platform

    async def run():
        server, connection, agent = await publish(t)
        t["upstream"].lost = True
        run = create_run(t, t["alice"], agent)
        result = await worker(t).run_once()
        assert result["state"] == "recovery_required", result
        assert len(t["upstream"].effects) == 1
        assert await worker(t, id="replacement-worker").run_once() is None
        assert len(t["upstream"].effects) == 1
        assert t["service"].get_run(t["alice"], run["run_id"])["state"] == "recovery_required"

    asyncio.run(run())


def test_explicit_department_identity_is_shared_without_revealing_owner_personal_connection(mcp_platform):
    t = mcp_platform

    async def run():
        server, personal, agent = await publish(t)
        department = t["administration"].create_department(t["alice"], "MCP department")
        t["administration"].set_department_member(t["alice"], department["id"], t["bob"].user_id, "member")
        from dataclasses import replace

        with t["admin"].connect() as c:
            rev = c.execute(
                select(s.memberships.c.revision).where(
                    s.memberships.c.org_id == t["org"], s.memberships.c.user_id == t["bob"].user_id
                )
            ).scalar_one()
        bob = replace(t["bob"], membership_revision=rev)
        shared = await connect(t, t["alice"], server, TOKEN_D, department=department["id"])
        run = create_run(t, bob, agent)
        assert (await worker(t).run_once())["state"] == "succeeded"
        assert "department-upstream-data" in t["service"].get_run(bob, run["run_id"])["result"]["answer"]
        assert [r["id"] for r in t["connections"].list_connections(bob)] == [shared["id"]]
        assert personal["id"] != shared["id"]

    asyncio.run(run())


def test_discovery_replay_uses_saved_snapshot_not_another_identity_or_call(mcp_platform):
    t = mcp_platform

    async def run():
        server, connection, agent = await publish(t)
        request = DiscoveryCreate(request_id=uuid4())
        first = await t["connections"].discover(t["alice"], connection["id"], request)
        second = await t["connections"].discover(t["alice"], connection["id"], request)
        assert first == second
        with pytest.raises(PlatformError):
            await t["connections"].discover(t["bob"], connection["id"], request)

    asyncio.run(run())


def test_credential_storage_alone_never_marks_a_connection_authenticated(mcp_platform):
    t = mcp_platform

    async def run():
        server, original, agent = await publish(t)
        connection = t["connections"].create_connection(
            t["alice"], ConnectionCreate(server_id=server["id"], name="Wrong upstream identity")
        )
        prepared = t["connections"].prepare_credential(
            t["alice"], connection["id"], CredentialPrepare(expected_revision=0, request_id=uuid4())
        )
        stored = await t["connections"].upload_credential(
            t["alice"],
            connection["id"],
            prepared["binding_id"],
            CredentialUpload(secret="synthetic-wrong-upstream-token"),
        )
        assert stored["state"] == "pending"
        with pytest.raises(PlatformError):
            create_run(t, t["alice"], agent, bindings={str(server["id"]): str(connection["id"])})
        with pytest.raises(PlatformError) as rejected:
            await t["connections"].discover(t["alice"], connection["id"], DiscoveryCreate(request_id=uuid4()))
        assert rejected.value.code == "MCP_AUTH_REQUIRED"
        rows = {row["id"]: row for row in t["connections"].list_connections(t["alice"])}
        assert rows[connection["id"]]["state"] == "reauth_required"
        assert rows[original["id"]]["state"] == "active"

    asyncio.run(run())
