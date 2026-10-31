"""Real PostgreSQL evidence for emergency kill switches (GOV-04 / GOVTEST-06)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import secrets
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.admin.contracts import KillSwitchCreate, KillSwitchRelease
from app.admin.service import AdminService
from app.api.v2.application import create_platform_app
from app.auth.service import AuthService, csrf_token
from app.db import schema as s
from app.db.engine import Database
from app.platform_errors import PlatformError
from app.runtime.actions import canonical_digest
from test_audit_integration import audit_rows, identity
from test_execution_integration import EffectSink, SyntheticModelFactory, claim, commit_tool_turn, current, worker
from test_execution_integration import scenario as scenario  # noqa: F401 - fixture re-export


def admins(t):
    return AdminService(t["db"], t["settings"]), identity(t, "org_admin"), identity(t, "org_admin")


def activate(t, admin, who, scope, **kw):
    body = KillSwitchCreate(scope=scope, reason_code="SECURITY_INCIDENT", note="synthetic incident ticket", **kw)
    return admin.activate_kill_switch(who, body)


def new_run(t):
    with t["admin"].connect() as c:  # each accepted Run advances the session revision
        revision = c.execute(select(s.resources.c.revision).where(s.resources.c.id == t["execution_session"])).scalar_one()
    return t["service"].create_run(t["alice"], t["execution_session"],
                                   {**t["request"], "expected_session_revision": revision}, secrets.token_hex(16))


def run_state(t, run_id):
    with t["admin"].connect() as c:
        return c.execute(select(s.runs.c.state, s.runs.c.error_code).where(s.runs.c.id == run_id)).one()


def test_organization_switch_blocks_new_work_but_not_reads_cancel_or_release(scenario):
    t = scenario()
    admin, first, second = admins(t)
    result = activate(t, admin, first, "organization")
    assert result["stopped_runs"] == 1  # the fixture's queued Run
    with pytest.raises(PlatformError) as error:
        new_run(t)
    assert (error.value.code, error.value.status) == ("KILL_SWITCH_ACTIVE", 403)
    assert t["service"].get_run(t["alice"], t["run_id"])["state"] == "cancelled"  # reads still work
    assert t["service"].list_sessions(t["alice"])
    with pytest.raises(PlatformError) as error:  # two-person release
        admin.release_kill_switch(first, result["id"], KillSwitchRelease(expected_revision=0, evidence="INC-1 closed"))
    assert error.value.code == "SEPARATION_OF_DUTIES"
    admin.release_kill_switch(second, result["id"], KillSwitchRelease(expected_revision=0, evidence="INC-1 closed"))
    assert new_run(t)["state"] == "queued"
    assert run_state(t, t["run_id"]).state == "cancelled"  # release never revives what the switch stopped
    [on, off] = audit_rows(t, s.audit.c.action.in_(["kill_switch.activate", "kill_switch.release"]))
    assert (on["actor_id"], on["outcome"], on["metadata"]["scope"]) == (first.user_id, "active", "organization")
    assert (off["actor_id"], off["metadata"]["activated_by"]) == (second.user_id, str(first.user_id))
    assert "synthetic incident" not in str(on["metadata"]) and "INC-1" not in str(off["metadata"])


def test_queued_run_is_cancelled_and_refunded(scenario):
    t = scenario()
    admin, first, _ = admins(t)
    activate(t, admin, first, "tool", target_id=t["tool_definition"]["id"])
    assert tuple(run_state(t, t["run_id"])) == ("cancelled", "KILL_SWITCH_ACTIVE")
    assert current(t, s.reservations)[0]["state"] != "reserved"
    assert current(t, s.budgets, s.budgets.c.owner_id == t["alice"].user_id)[0]["reserved"] == 0
    assert not current(t, s.model_calls)
    with pytest.raises(PlatformError) as error:  # admission refuses before any paid model turn
        new_run(t)
    assert error.value.code == "KILL_SWITCH_ACTIVE"


def test_waiting_approval_run_is_cancelled_and_its_approval_cannot_be_decided(scenario):
    t = scenario("R2")
    sink = EffectSink()
    assert asyncio.run(worker(t, SyntheticModelFactory(), sink).run_once())["state"] == "waiting_approval"
    approval = current(t, s.approvals)[0]
    admin, first, _ = admins(t)
    activate(t, admin, first, "user", target_id=t["alice"].user_id)
    assert run_state(t, t["run_id"]).state == "cancelled"
    assert current(t, s.approvals)[0]["state"] != "pending"
    with pytest.raises(PlatformError):
        t["service"].decide_approval(t["bob"], approval["id"], approval["revision"], approval["action_digest"], "approve")
    assert sink.requests == []


def write_switch_without_sweep(t, scope, target=None):
    """A switch row as if the sweep had crashed: only the authoritative state may stop work."""
    with t["admin"].begin() as c:
        c.execute(insert(s.kill_switches).values(
            org_id=t["org"], id=uuid4(), scope=scope, target_id=target,
            reason_code="SECURITY_INCIDENT", note_digest="0" * 64, activated_by=uuid4()))


def test_approval_decision_is_refused_by_the_switch_itself(scenario):
    t = scenario("R2")
    sink = EffectSink()
    assert asyncio.run(worker(t, SyntheticModelFactory(), sink).run_once())["state"] == "waiting_approval"
    approval = current(t, s.approvals)[0]
    write_switch_without_sweep(t, "organization")
    with pytest.raises(PlatformError) as error:
        t["service"].decide_approval(t["bob"], approval["id"], approval["revision"], approval["action_digest"], "approve")
    assert error.value.code == "KILL_SWITCH_ACTIVE"
    assert current(t, s.approvals)[0]["state"] == "pending" and sink.requests == []


def test_sent_but_unknown_effect_is_kept_for_reconciliation_not_called_unsent(scenario):
    t = scenario()
    h = claim(t)
    seq, inv = commit_tool_turn(t, h)
    dispatch = t["store"].prepare_dispatch(h, seq, inv["id"])
    t["store"].consume_dispatch(h, dispatch["id"])  # the external call may have happened
    admin, first, _ = admins(t)
    activate(t, admin, first, "organization")
    assert tuple(run_state(t, t["run_id"])) == ("recovery_required", "KILL_SWITCH_ACTIVE")
    assert [d["state"] for d in current(t, s.dispatches)] == ["unknown"]
    assert current(t, s.blockers) and current(t, s.blockers)[0]["resolved_at"] is None
    with pytest.raises(PlatformError):  # the old worker cannot report it as completed afterwards
        t["store"].complete_dispatch(h, seq, dispatch["id"], {"captured": 7})


def test_an_old_worker_is_denied_by_authoritative_state_even_if_the_sweep_never_ran(scenario):
    t = scenario()
    h = claim(t)  # claimed before the switch
    with t["admin"].begin() as c:  # a switch written without any sweep or notification
        c.execute(insert(s.kill_switches).values(
            org_id=t["org"], id=uuid4(), scope="model", target_id=t["model_definition"]["id"],
            reason_code="PROVIDER_INCIDENT", note_digest="0" * 64, activated_by=uuid4()))
    # A separate Database/ExecutionStore instance: nothing is shared in-process, only PG.
    other_instance = Database(t["db"].engine.url.render_as_string(hide_password=False))
    try:
        from app.runtime.execution import ExecutionStore

        store = ExecutionStore(other_instance, t["settings"])
        seq = store.load(h)["run"]["checkpoint_seq"]
        with pytest.raises(PlatformError) as error:
            store.prepare_model_call(h, seq, canonical_digest("test-request", {"turn": 1}), Decimal("0.02"))
        assert error.value.code == "KILL_SWITCH_ACTIVE"
    finally:
        other_instance.dispose()
    assert not current(t, s.model_calls)


def test_expiry_readmits_new_work_without_reviving_stopped_runs(scenario):
    t = scenario()
    admin, first, _ = admins(t)
    result = activate(t, admin, first, "organization", expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))
    assert run_state(t, t["run_id"]).state == "cancelled"
    with t["admin"].begin() as c:  # time passes (constraint requires expiry > activation)
        c.execute(update(s.kill_switches).where(s.kill_switches.c.id == result["id"]).values(
            activated_at=text("clock_timestamp() - interval '2 hours'"),
            expires_at=text("clock_timestamp() - interval '1 second'")))
    assert new_run(t)["state"] == "queued"
    assert run_state(t, t["run_id"]).state == "cancelled"


def test_activation_and_admission_race_never_leaves_an_admitted_run_running(scenario):
    t = scenario()
    admin, first, _ = admins(t)
    barrier = Barrier(2, timeout=30)

    def admit():
        barrier.wait()
        try:
            return new_run(t)["run_id"]
        except PlatformError as error:
            return error.code

    def switch():
        barrier.wait()
        return activate(t, admin, first, "organization")

    with ThreadPoolExecutor(2) as pool:
        futures = pool.submit(admit), pool.submit(switch)
        admitted, _ = (f.result(timeout=60) for f in futures)
    if not isinstance(admitted, str):  # admitted before the switch committed: the sweep must have stopped it
        assert run_state(t, admitted).state == "cancelled"
    else:
        assert admitted == "KILL_SWITCH_ACTIVE"


def test_database_and_roles_enforce_switch_integrity(scenario):
    t = scenario()
    admin, first, _ = admins(t)
    for role in ("member", "operator", "auditor"):
        with pytest.raises(PlatformError) as error:
            activate(t, admin, identity(t, role), "organization")
        assert error.value.status == 403
    assert admin.kill_switches(identity(t, "auditor")) == []
    with pytest.raises(PlatformError) as error:
        activate(t, admin, first, "user", target_id=first.user_id)
    assert error.value.code == "KILL_SWITCH_INVALID"
    result = activate(t, admin, first, "tool", target_id=t["tool_definition"]["id"])
    with pytest.raises(PlatformError) as error:
        activate(t, admin, first, "tool", target_id=t["tool_definition"]["id"])
    assert error.value.code == "KILL_SWITCH_EXISTS"
    with pytest.raises(IntegrityError):  # the two-person rule holds even for the table owner
        with t["admin"].begin() as c:
            c.execute(update(s.kill_switches).where(s.kill_switches.c.id == result["id"]).values(
                released_by=first.user_id, released_at=text("clock_timestamp()"), release_evidence_digest="0" * 64))
    for statement in ("DELETE FROM aio_kill_switches", "UPDATE aio_kill_switches SET scope = 'user'",
                      "UPDATE aio_kill_switches SET activated_by = org_id"):
        with pytest.raises(ProgrammingError) as error:
            with t["db"].transaction(t["alice"]) as c:
                c.execute(text(statement))
        assert error.value.orig.sqlstate == "42501"


def test_http_activation_requires_admin_csrf_and_hides_the_note(scenario):
    t = scenario()
    _, first, _ = admins(t)
    settings = replace(t["settings"], database_url=t["db"].engine.url.render_as_string(hide_password=False))
    auth = AuthService(t["db"], settings)
    body = {"scope": "organization", "reason_code": "OPERATOR_REQUEST", "note": "synthetic private note"}
    with TestClient(create_platform_app(settings, database=t["db"]), base_url=settings.public_origin) as client:
        for who, expected in ((t["alice"], 403), (first, 201)):
            token, _ = auth.create_session(t["org"], settings.oidc_issuer, str(who.user_id))
            client.cookies.set(settings.session_cookie, token)
            headers = {"Origin": settings.public_origin, "X-CSRF-Token": csrf_token(token)}
            assert client.post("/api/v2/admin/kill-switches", json=body).status_code == 403  # no CSRF
            assert client.post("/api/v2/admin/kill-switches", json=body, headers=headers).status_code == expected
        listed = client.get("/api/v2/admin/kill-switches").json()["items"]
    assert len(listed) == 1 and listed[0]["active"] and "synthetic private note" not in str(listed)
