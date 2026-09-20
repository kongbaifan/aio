import asyncio
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import insert, select, update

from app.admin.contracts import GrantCreate
from app.api.v2.application import create_platform_app
from app.auth.service import csrf_token
from app.connections.contracts import (
    ConnectionCreate,
    CredentialPrepare,
    DiscoveryCreate,
    ServerCreate,
    ServerPublish,
    ToolSelection,
)
from app.platform_errors import PlatformError
from app.db import schema as s


def create(t, p=None, server=None):
    p = p or t["alice"]
    if server is None:
        server = t["connections"].create_server(
            p, ServerCreate(name="OAuth MCP", version="1", endpoint_id=t["upstream"].endpoint_id)
        )
    conn = t["connections"].create_connection(p, ConnectionCreate(server_id=server["id"], name="Own OAuth identity"))
    return server, conn


async def begin(t, conn, p=None):
    p = p or t["alice"]
    return await t["oauth"].start(
        p, conn["id"], CredentialPrepare(expected_revision=conn["resource_revision"], request_id=uuid4())
    )


def response(t, started, subject="alice"):
    return parse_qs(
        urlsplit(t["upstream"].authorize(parse_qs(urlsplit(started["authorization_url"]).query), subject)).query
    )


async def finish(t, query, p=None):
    return await t["oauth"].callback(
        p or t["alice"], t["upstream"].endpoint_id, query["state"][0], query["code"][0], issuer=query["iss"][0]
    )


def test_oauth_grant_activation_discovery_and_session_bound_replay(oauth_platform):
    t = oauth_platform
    server, conn = create(t)

    async def run():
        started = await begin(t, conn)
        callback = response(t, started)
        result = await finish(t, callback)
        assert result["connection_id"] == conn["id"]
        await finish(t, callback)
        assert len([request for request in t["upstream"].requests if request.url.path == "/oauth/token"]) == 1
        current = t["connections"].list_connections(t["alice"])[0]
        assert current["state"] == "pending" and current["authorization"]["subject"] == "alice"
        discovery = await t["connections"].discover(t["alice"], conn["id"], DiscoveryCreate(request_id=uuid4()))
        assert discovery["state"] == "ready"
        assert t["connections"].list_connections(t["alice"])[0]["state"] == "active"
        with t["db"].transaction(t["alice"]) as c:
            attempt = c.execute(select(s.mcp_oauth_attempts)).mappings().one()
            assert attempt["state"] == "completed" and attempt["auth_session_id"] == t["alice"].auth_session_id
            assert "code_verifier" not in attempt and "access_token" not in attempt

    asyncio.run(run())


@pytest.mark.parametrize("case", ["other_user", "new_session", "logged_out", "wrong_issuer", "changed_code", "expired"])
def test_invalid_callback_never_redeems_code_or_borrows_another_account(oauth_platform, case):
    t = oauth_platform
    _, conn = create(t)

    async def run():
        started = await begin(t, conn)
        callback = response(t, started)
        p = t["alice"]
        if case == "other_user":
            p = t["bob"]
        elif case == "new_session":
            _, p = t["auth"].create_session(t["org"], t["settings"].oidc_issuer, str(t["alice"].user_id))
        elif case == "logged_out":
            t["auth"].logout(p)
        elif case == "wrong_issuer":
            callback["iss"] = ["https://unapproved.example"]
        elif case == "changed_code":
            await finish(t, callback)
            callback["code"] = ["another-authorization-code"]
        else:
            with t["admin"].begin() as c:
                c.execute(
                    update(s.mcp_oauth_attempts)
                    .where(s.mcp_oauth_attempts.c.org_id == t["org"])
                    .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
                )
        before = len([r for r in t["upstream"].requests if r.url.path == "/oauth/token"])
        with pytest.raises(PlatformError):
            await finish(t, callback, p)
        assert len([r for r in t["upstream"].requests if r.url.path == "/oauth/token"]) == before

    asyncio.run(run())


def test_expired_access_refreshes_same_binding_and_bad_refresh_requests_reauth(oauth_platform):
    t = oauth_platform
    _, conn = create(t)

    async def run():
        await finish(t, response(t, await begin(t, conn)))
        await t["connections"].discover(t["alice"], conn["id"], DiscoveryCreate(request_id=uuid4()))
        before = t["connections"].list_connections(t["alice"])[0]
        with t["vault"].connect() as c:
            c.execute("UPDATE oauth_grants SET expires_at=0")
        await t["connections"].discover(t["alice"], conn["id"], DiscoveryCreate(request_id=uuid4()))
        after = t["connections"].list_connections(t["alice"])[0]
        assert before["credential_revision"] == after["credential_revision"] == 1 and t["upstream"].refreshes == 1
        with t["vault"].connect() as c:
            c.execute("UPDATE oauth_grants SET expires_at=0")
        t["upstream"].fail_refresh = True
        with pytest.raises(PlatformError):
            await t["connections"].discover(t["alice"], conn["id"], DiscoveryCreate(request_id=uuid4()))
        assert t["connections"].list_connections(t["alice"])[0]["state"] == "reauth_required"

    asyncio.run(run())


def test_disconnect_revokes_upstream_and_never_transfers_identity_to_new_binding(oauth_platform):
    t = oauth_platform
    _, conn = create(t)

    async def run():
        await finish(t, response(t, await begin(t, conn)))
        t["connections"].mark_revoked(t["alice"], conn["id"])
        assert await t["connections"].cleanup(t["org"]) == 1
        assert not t["upstream"].access_tokens and not t["upstream"].refresh_tokens
        current = t["connections"].list_connections(t["alice"])[0]
        assert current["state"] == "revoked" and current["credential_cleanup"] == "confirmed"

    asyncio.run(run())


def test_http_oauth_requires_csrf_strips_codes_and_verifies_actual_mcp(oauth_platform):
    t = oauth_platform
    _, conn = create(t)
    app = create_platform_app(t["settings"], database=t["db"], connector_client=t["connector_client"])

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=t["settings"].public_origin, follow_redirects=False
        ) as client:
            client.cookies.set(t["settings"].session_cookie, t["alice_token"])
            body = {"expected_revision": 0, "request_id": str(uuid4())}
            path = f"/api/v2/connections/{conn['id']}/oauth"
            assert (await client.post(path, json=body)).status_code == 403
            headers = {"Origin": t["settings"].public_origin, "X-CSRF-Token": csrf_token(t["alice_token"])}
            started = await client.post(path, json=body, headers=headers)
            assert started.status_code == 201, started.text
            assert "access_token" not in started.text and "refresh_token" not in started.text
            callback = t["upstream"].authorize(parse_qs(urlsplit(started.json()["authorization_url"]).query), "alice")
            result = await client.get(callback)
            assert result.status_code == 303 and "oauth=connected" in result.headers["location"]
            assert "code=" not in result.headers["location"] and result.headers["referrer-policy"] == "no-referrer"
            assert t["connections"].list_connections(t["alice"])[0]["state"] == "active"
            # A duplicate callback never redeems the same authorization code again.
            assert (await client.get(callback)).status_code == 303
            assert len([r for r in t["upstream"].requests if r.url.path == "/oauth/token"]) == 1

    asyncio.run(run())


def test_shared_definition_keeps_two_oauth_accounts_separate_through_worker_calls(oauth_platform):
    from decimal import Decimal
    from app.admin.contracts import AgentCreate
    from app.admin.service import AdminService
    from app.db.provisioning import provision_model
    from app.connections.driver import MCPDriver
    from app.runtime.worker import DurableWorker, ToolDrivers
    from connector_fixtures import create_run, ModelFactory

    t = oauth_platform
    server, alice_connection = create(t)
    admin = AdminService(t["db"], t["settings"])

    async def run():
        await finish(t, response(t, await begin(t, alice_connection), "alice"))
        discovered = await t["connections"].discover(
            t["alice"], alice_connection["id"], DiscoveryCreate(request_id=uuid4())
        )
        published = t["connections"].publish(
            t["alice"],
            server["id"],
            ServerPublish(
                expected_revision=0,
                discovery_id=discovered["id"],
                tools=(ToolSelection(remote_name="lookup_identity", alias="company_lookup"),),
                acknowledge_readonly_credentials=True,
            ),
        )
        admin.set_grants(
            t["alice"],
            published["id"],
            GrantCreate(
                subject_type="user", subject_id=t["bob"].user_id, actions=("mcp_server.read", "mcp_server.use")
            ),
        )
        _, bob_connection = create(t, t["bob"], published)
        await finish(t, response(t, await begin(t, bob_connection, t["bob"]), "bob"), t["bob"])
        await t["connections"].discover(t["bob"], bob_connection["id"], DiscoveryCreate(request_id=uuid4()))
        with t["admin"].begin() as c:
            model = provision_model(
                c,
                org_id=t["org"],
                owner_id=t["alice"].user_id,
                provider="synthetic",
                model="synthetic",
                config={"max_call_charge": "0.020000"},
            )
        agent = admin.create_agent(
            t["alice"],
            AgentCreate(
                name="OAuth identity test",
                version="1",
                instruction="Use the current OAuth identity",
                model_id=UUID(model["id"]),
                mcp_server_ids=(published["id"],),
                run_budget=Decimal(".1"),
                max_rounds=3,
            ),
        )
        admin.set_grants(
            t["alice"],
            agent["id"],
            GrantCreate(
                subject_type="user",
                subject_id=t["bob"].user_id,
                actions=("agent.read", "agent.use"),
                include_dependencies=True,
            ),
        )
        a = create_run(t, t["alice"], agent)
        b = create_run(t, t["bob"], agent)
        for worker_id in ("oauth-worker-a", "oauth-worker-b"):
            worker = DurableWorker(
                t["store"],
                t["org"],
                worker_id,
                ModelFactory(),
                ToolDrivers({"mcp.http": MCPDriver(t["connector_client"])}),
            )
            assert (await worker.run_once())["state"] == "succeeded"
        text_a = t["service"].get_run(t["alice"], a["run_id"])["result"]["answer"]
        text_b = t["service"].get_run(t["bob"], b["run_id"])["result"]["answer"]
        assert "alice" in text_a and "bob" not in text_a
        assert "bob" in text_b and "alice" not in text_b
        # Even a bad generic grant cannot let Bob redeem or use Alice's personal connection.
        with t["admin"].begin() as c:
            c.execute(
                insert(s.grants).values(
                    org_id=t["org"],
                    id=uuid4(),
                    resource_id=alice_connection["id"],
                    subject_id=t["bob"].user_id,
                    action="connection.use",
                )
            )
        with pytest.raises(PlatformError):
            create_run(t, t["bob"], agent, bindings={str(server["id"]): str(alice_connection["id"])})

    asyncio.run(run())
