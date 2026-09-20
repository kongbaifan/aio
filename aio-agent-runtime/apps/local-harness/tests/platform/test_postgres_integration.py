"""Real PostgreSQL and RLS tests; absent DB is reported as a skip, never a fake pass.

Use scripts/platform/test_postgres.py for an isolated automatically cleaned DB.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import secrets
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from app.api.v2.application import create_platform_app
from app.auth.service import AuthService, csrf_token
from app.db import schema as s
from app.db.engine import Database, SCHEMA_REVISION
from app.platform_errors import PlatformConfigurationError, PlatformError
from app.runtime.actions import ActionSpec
from app.runtime.service import PlatformService


def body(t, message="Synthetic message", revision=0):
    return {
        "message": message,
        "agent_version_id": str(t["agent"]),
        "expected_session_revision": revision,
        "input_artifact_ids": [],
        "mode": "single",
    }


def create_run(t, **kwargs):
    return t["service"].create_run(t["alice"], t["session"], body(t, **kwargs), secrets.token_hex(16))


def running(t):
    run = create_run(t)
    claimed = t["service"].claim_next(t["org"], "worker-tests")
    assert claimed["id"] == run["run_id"]
    t["service"].transition_run(t["alice"], claimed["id"], claimed["generation"], "running")
    return claimed


def action(t, run, **changes):
    payload = dict(
        org_id=t["org"],
        actor_user_id=t["alice"].user_id,
        run_id=run["id"],
        logical_call_id="write-1",
        tool_version_id=t["tool"],
        arguments_sha256="1" * 64,
        resource_scope_digest="2" * 64,
        network_profile_id="none",
        data_policy_revision=0,
        approval_policy_id="business-review",
        not_after=datetime.now(timezone.utc) + timedelta(seconds=120),
    )
    payload.update(changes)
    return ActionSpec(**payload)


def test_migration_is_repeatable_and_production_role_is_not_admin(postgres):
    db, admin, raw = postgres
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["database_url"] = raw
    command.upgrade(config, "head")
    db.verify_runtime_role()
    privileged = Database(raw)
    try:
        with pytest.raises(PlatformConfigurationError):
            privileged.verify_runtime_role()
    finally:
        privileged.dispose()
    with admin.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == SCHEMA_REVISION


def test_cross_org_row_filter_and_transaction_pool_cleanup(tenant):
    t = tenant
    with t["db"].transaction(t["alice"]) as c:
        assert t["project"] in c.execute(select(s.projects.c.id)).scalars().all()
    with pytest.raises(RuntimeError):
        with t["db"].transaction(t["alice"]) as c:
            c.execute(text("SELECT 1"))
            raise RuntimeError("force rollback")
    with t["db"].transaction(t["outsider"]) as c:
        assert t["project"] not in c.execute(select(s.projects.c.id)).scalars().all()
    with t["db"].bootstrap() as c:
        assert c.execute(select(s.projects.c.id)).all() == []
        assert c.execute(text("SELECT current_setting('aio.org_id', true)")).scalar_one() == ""


def test_cross_org_foreign_key_rejected_even_by_privileged_fixture(tenant):
    t = tenant
    with pytest.raises(IntegrityError):
        with t["admin"].begin() as c:
            c.execute(
                insert(s.resources).values(
                    org_id=t["outsider"].org_id, id=uuid4(), kind="project", owner_id=t["alice"].user_id
                )
            )


def test_private_session_is_not_in_other_users_list_and_direct_read_denied(tenant):
    t = tenant
    assert len(t["service"].list_sessions(t["alice"])) == 1
    assert t["service"].list_sessions(t["bob"]) == []
    for p in (t["bob"], t["outsider"]):
        with pytest.raises(PlatformError) as exc:
            t["service"].session_detail(p, t["session"])
        assert exc.value.status == 404


def test_project_shared_does_not_share_private_conversation(tenant):
    t = tenant
    with t["admin"].begin() as c:
        c.execute(
            insert(s.grants).values(
                org_id=t["org"],
                id=uuid4(),
                resource_id=t["project"],
                subject_id=t["bob"].user_id,
                action="project.read",
            )
        )
    assert len(t["service"].list_projects(t["bob"])) == 1
    assert t["service"].list_sessions(t["bob"]) == []


def test_atomic_run_commit_and_idempotent_replay(tenant):
    t = tenant
    key = secrets.token_hex(16)
    one = t["service"].create_run(t["alice"], t["session"], body(t), key)
    two = t["service"].create_run(t["alice"], t["session"], body(t), key)
    assert one == two
    with t["db"].transaction(t["alice"]) as c:
        for table in (s.runs, s.messages, s.jobs, s.manifest_snapshots, s.reservations):
            assert (
                c.execute(select(func.count()).select_from(table).where(table.c.org_id == t["org"])).scalar_one() == 1
            )
        assert c.execute(
            select(s.budgets.c.reserved).where(s.budgets.c.owner_id == t["alice"].user_id)
        ).scalar_one() == Decimal("0.1")
        assert c.execute(select(s.events.c.seq).where(s.events.c.run_id == one["run_id"])).scalars().all() == [1]
    with pytest.raises(PlatformError) as exc:
        t["service"].create_run(t["alice"], t["session"], body(t, message="different"), key)
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"


def test_concurrent_identical_requests_have_one_run(tenant):
    t = tenant
    key = secrets.token_hex(16)
    barrier = Barrier(2)

    def request():
        barrier.wait(timeout=5)
        return t["service"].create_run(t["alice"], t["session"], body(t), key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result(timeout=15) for f in [pool.submit(request), pool.submit(request)]]
    assert results[0]["run_id"] == results[1]["run_id"]
    with t["db"].transaction(t["alice"]) as c:
        assert c.execute(select(func.count()).select_from(s.runs).where(s.runs.c.org_id == t["org"])).scalar_one() == 1


def test_two_sessions_cannot_overspend_last_budget(tenant):
    t = tenant
    other_session = t["service"].create_session(t["alice"], t["project"], t["agent"], "another")["id"]
    with t["admin"].begin() as c:
        c.execute(
            update(s.budgets)
            .where(s.budgets.c.org_id == t["org"], s.budgets.c.owner_id == t["alice"].user_id)
            .values(hard_limit=Decimal("0.1"))
        )
    barrier = Barrier(2)

    def request(sid):
        barrier.wait(timeout=5)
        try:
            return t["service"].create_run(t["alice"], sid, body(t), secrets.token_hex(16))["state"]
        except PlatformError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(request, sid) for sid in [t["session"], other_session]]
        states = [f.result(timeout=15) for f in futures]
    assert sorted(states) == ["QUOTA_EXCEEDED", "queued"]
    with t["db"].transaction(t["alice"]) as c:
        assert (
            c.execute(select(func.count()).select_from(s.messages).where(s.messages.c.org_id == t["org"])).scalar_one()
            == 1
        )


def test_membership_revocation_prevents_idempotency_replay(tenant):
    t = tenant
    key = secrets.token_hex(16)
    t["service"].create_run(t["alice"], t["session"], body(t), key)
    with t["admin"].begin() as c:
        c.execute(
            update(s.memberships)
            .where(s.memberships.c.org_id == t["org"], s.memberships.c.user_id == t["alice"].user_id)
            .values(active=False, revision=1)
        )
    with pytest.raises(PlatformError) as exc:
        t["service"].create_run(t["alice"], t["session"], body(t), key)
    assert exc.value.status == 401


def test_cancel_queued_releases_budget_exactly_once(tenant):
    t = tenant
    run = create_run(t)
    for _ in range(2):
        assert t["service"].cancel_run(t["alice"], run["run_id"])["state"] == "cancelled"
    with t["db"].transaction(t["alice"]) as c:
        assert (
            c.execute(select(s.budgets.c.reserved).where(s.budgets.c.owner_id == t["alice"].user_id)).scalar_one() == 0
        )
        assert (
            c.execute(select(s.reservations.c.state).where(s.reservations.c.run_id == run["run_id"])).scalar_one()
            == "released"
        )


def test_two_workers_claim_only_once_and_stale_generation_rejected(tenant):
    t = tenant
    run = create_run(t)
    barrier = Barrier(2)

    def claim(worker):
        barrier.wait(timeout=5)
        return t["service"].claim_next(t["org"], worker)

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = [f.result(timeout=15) for f in [pool.submit(claim, "worker-a"), pool.submit(claim, "worker-b")]]
    assert sum(v is not None for v in values) == 1
    with pytest.raises(PlatformError) as exc:
        t["service"].transition_run(t["alice"], run["run_id"], 2, "running")
    assert exc.value.code == "STALE_GENERATION"


def test_expired_lease_cannot_be_heartbeated_or_execute(tenant):
    t = tenant
    run = running(t)
    with t["admin"].begin() as c:
        c.execute(
            update(s.jobs)
            .where(s.jobs.c.run_id == run["id"])
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    with pytest.raises(PlatformError):
        t["service"].heartbeat(t["org"], run["id"], run["generation"], "worker-tests")
    with pytest.raises(PlatformError):
        t["service"].plan_invocation(t["alice"], run["id"], run["generation"], action(t, run))


def test_persistent_approval_and_separation_of_duties(tenant):
    t = tenant
    run = running(t)
    spec = action(t, run)
    planned = t["service"].plan_invocation(t["alice"], run["id"], run["generation"], spec)
    with t["admin"].begin() as c:
        for uid in (t["alice"].user_id, t["bob"].user_id):
            c.execute(
                insert(s.grants).values(
                    org_id=t["org"],
                    id=uuid4(),
                    resource_id=planned["approval_id"],
                    subject_id=uid,
                    action="approval.decide",
                )
            )
    with pytest.raises(PlatformError) as exc:
        t["service"].decide_approval(t["alice"], planned["approval_id"], 0, spec.digest, "approve")
    assert exc.value.code == "SEPARATION_OF_DUTIES"
    # New service instance has no in-memory Futures; approval is durable.
    other = PlatformService(t["db"], t["settings"])
    decided = other.decide_approval(t["bob"], planned["approval_id"], 0, spec.digest, "approve")
    assert decided["state"] == "approved"
    assert other.decide_approval(t["bob"], planned["approval_id"], 0, spec.digest, "approve") == decided
    assert t["service"].get_run(t["alice"], run["id"])["state"] == "running"


def test_changed_action_and_approval_expiry_do_not_execute(tenant):
    t = tenant
    run = running(t)
    spec = action(t, run)
    planned = t["service"].plan_invocation(t["alice"], run["id"], run["generation"], spec)
    with t["admin"].begin() as c:
        c.execute(
            insert(s.grants).values(
                org_id=t["org"],
                id=uuid4(),
                resource_id=planned["approval_id"],
                subject_id=t["bob"].user_id,
                action="approval.decide",
            )
        )
    with pytest.raises(PlatformError) as exc:
        t["service"].decide_approval(t["bob"], planned["approval_id"], 0, "0" * 64, "approve")
    assert exc.value.code == "ACTION_CHANGED"
    with t["admin"].begin() as c:
        c.execute(
            update(s.approvals)
            .where(s.approvals.c.id == planned["approval_id"])
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    with pytest.raises(PlatformError) as exc:
        t["service"].decide_approval(t["bob"], planned["approval_id"], 0, spec.digest, "approve")
    assert exc.value.status == 410
    with t["db"].transaction(t["alice"]) as c:
        assert (
            c.execute(select(s.approvals.c.state).where(s.approvals.c.id == planned["approval_id"])).scalar_one()
            == "expired"
        )
        assert (
            c.execute(
                select(func.count()).select_from(s.dispatches).where(s.dispatches.c.org_id == t["org"])
            ).scalar_one()
            == 0
        )


def test_login_state_binding_one_time_and_logout_does_not_cancel_run(tenant):
    t = tenant
    auth = AuthService(t["db"], t["settings"])
    start = auth.begin_login(t["org"])
    with pytest.raises(PlatformError):
        auth.consume_login(start.state, "wrong-binding-but-long-enough-for-input")
    attempt = auth.consume_login(start.state, start.binding)
    assert attempt.org_id == t["org"]
    with pytest.raises(PlatformError):
        auth.consume_login(start.state, start.binding)
    token, identity = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["alice"].user_id))
    assert auth.authenticate(token).user_id == t["alice"].user_id
    run = create_run(t)
    auth.logout(identity)
    with pytest.raises(PlatformError):
        auth.authenticate(token)
    assert t["service"].get_run(t["alice"], run["run_id"])["state"] == "queued"


def test_http_enforces_auth_csrf_strict_json_and_hides_legacy_routes(tenant):
    t = tenant
    settings = replace(t["settings"], database_url=t["db"].engine.url.render_as_string(hide_password=False))
    auth = AuthService(t["db"], settings)
    token, _ = auth.create_session(t["org"], settings.oidc_issuer, str(t["alice"].user_id))
    app = create_platform_app(settings, database=t["db"])
    with TestClient(app, base_url=settings.public_origin) as client:
        assert client.get("/api/v2/sessions").status_code == 401
        client.cookies.set(settings.session_cookie, token)
        headers = {"Origin": settings.public_origin, "X-CSRF-Token": csrf_token(token)}
        assert client.get("/api/v2/me").status_code == 200
        assert client.post("/api/v2/projects", json={"name": "p"}).status_code == 403
        assert client.post("/api/v2/projects", json={"name": "p"}, headers=headers).status_code == 201
        duplicate = client.post(
            "/api/v2/projects",
            content='{"name":"a","name":"b"}',
            headers={**headers, "Content-Type": "application/json"},
        )
        assert duplicate.status_code == 422
        assert (
            client.post("/api/v2/projects", json={"name": "p", "org_id": str(uuid4())}, headers=headers).status_code
            == 422
        )
        for path in ["/api/chat", "/api/chat/stream", "/api/files", "/api/config", "/docs", "/openapi.json"]:
            assert client.get(path).status_code == 404
        assert client.get("/readyz").status_code == 200
        assert client.get("/api/v2/me").headers["cache-control"] == "no-store"


def test_http_event_replay_after_task_is_terminal(tenant):
    t = tenant
    run = create_run(t)
    t["service"].cancel_run(t["alice"], run["run_id"])
    auth = AuthService(t["db"], t["settings"])
    token, _ = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["alice"].user_id))
    app = create_platform_app(t["settings"], database=t["db"])
    with TestClient(app, base_url=t["settings"].public_origin) as client:
        client.cookies.set(t["settings"].session_cookie, token)
        response = client.get(f"/api/v2/runs/{run['run_id']}/events", headers={"Last-Event-ID": f"{run['run_id']}:1"})
        assert response.status_code == 200
        assert "event: run.cancelled" in response.text
        assert "event: run.queued" not in response.text
        conflict = client.get(
            f"/api/v2/runs/{run['run_id']}/events?after_seq=0", headers={"Last-Event-ID": f"{run['run_id']}:1"}
        )
        assert conflict.status_code == 409


def test_revoked_project_is_not_visible_through_owned_session(tenant):
    t = tenant
    with t["admin"].begin() as c:
        c.execute(update(s.resources).where(s.resources.c.id == t["project"]).values(status="disabled"))
    assert t["service"].list_sessions(t["alice"]) == []
    with pytest.raises(PlatformError):
        t["service"].session_detail(t["alice"], t["session"])


def test_pending_action_replay_and_current_agent_revocation(tenant):
    t = tenant
    run = running(t)
    spec = action(t, run)
    first = t["service"].plan_invocation(t["alice"], run["id"], run["generation"], spec)
    second = t["service"].plan_invocation(t["alice"], run["id"], run["generation"], spec)
    assert first["invocation_id"] == second["invocation_id"]
    with pytest.raises(PlatformError):
        changed = spec.model_copy(update={"entrypoint_digest": "9" * 64})
        t["service"].plan_invocation(t["alice"], run["id"], run["generation"], changed)
    with t["admin"].begin() as c:
        c.execute(update(s.resources).where(s.resources.c.id == t["agent"]).values(status="disabled"))
    with pytest.raises(PlatformError):
        t["service"].plan_invocation(t["alice"], run["id"], run["generation"], spec)


def test_oidc_callback_sets_cookie_and_replay_is_rejected(tenant):
    import json
    from urllib.parse import parse_qs, urlsplit

    import httpx
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from app.auth.oidc import OIDCClient

    t = tenant
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="callback-key", alg="RS256", use="sig")
    state = {}

    def identity_provider(request):
        if request.url.path == "/keys":
            return httpx.Response(200, json={"keys": [jwk]})
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {
                "iss": t["settings"].oidc_issuer,
                "sub": str(t["alice"].user_id),
                "aud": t["settings"].oidc_client_id,
                "nonce": state["nonce"],
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
            },
            key,
            algorithm="RS256",
            headers={"kid": "callback-key"},
        )
        assert "code_verifier" in parse_qs(request.content.decode())
        return httpx.Response(200, json={"id_token": token})

    oidc = OIDCClient(t["settings"], client=httpx.AsyncClient(transport=httpx.MockTransport(identity_provider)))
    app = create_platform_app(t["settings"], database=t["db"], oidc_client=oidc)
    with TestClient(app, base_url=t["settings"].public_origin) as client:
        redirect = client.get("/auth/login", params={"org_id": str(t["org"])}, follow_redirects=False)
        assert redirect.status_code == 303
        params = parse_qs(urlsplit(redirect.headers["location"]).query)
        state["nonce"] = params["nonce"][0]
        query = {"state": params["state"][0], "code": "synthetic-code"}
        response = client.get("/auth/callback", params=query, follow_redirects=False)
        assert response.status_code == 303
        assert "HttpOnly" in response.headers["set-cookie"]
        assert client.get("/api/v2/me").json()["user_id"] == str(t["alice"].user_id)
        assert client.get("/auth/callback", params=query, follow_redirects=False).status_code == 401
