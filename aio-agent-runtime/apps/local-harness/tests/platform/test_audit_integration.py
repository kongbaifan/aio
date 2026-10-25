"""Real PostgreSQL evidence for v14 audit facts: immutability, fail-closed dispatch, scoped reads."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import secrets
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
import pytest
from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.admin.service import AdminService
from app.api.v2.application import create_platform_app
from app.auth.principal import Principal
from app.auth.service import AuthService, csrf_token
from app.db import schema as s
from app.db import schema_v13
from app.db.engine import SCHEMA_REVISION
from app.db.provisioning import provision_identity
from app.observability import audit
from app.observability import redaction as m
from app.platform_errors import PlatformConfigurationError, PlatformError
from test_execution_integration import EffectSink, SyntheticModelFactory, claim, commit_tool_turn, current, worker
from test_execution_integration import scenario as scenario  # noqa: F401 - fixture re-export

MARKER = "synthetic-audit-outage-marker"


def alembic_config(url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["database_url"] = url
    return config


@contextmanager
def audit_outage(admin, org: UUID, action: str):
    """A real DB-level INSERT failure for ONE tenant/action, not a Python mock of the writer."""
    UUID(str(org))  # literal below is a verified UUID, never caller text
    name = "aio_test_audit_outage_" + secrets.token_hex(4)
    with admin.begin() as c:
        c.execute(text(
            f"CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            f"RAISE EXCEPTION '{MARKER}'; END $$"
        ))
        c.execute(text(
            f"CREATE TRIGGER {name} BEFORE INSERT ON aio_audit_events FOR EACH ROW "
            f"WHEN (NEW.org_id = '{org}'::uuid AND NEW.action = '{action}') EXECUTE FUNCTION {name}()"
        ))
    try:
        yield
    finally:
        with admin.begin() as c:
            c.execute(text(f"DROP TRIGGER IF EXISTS {name} ON aio_audit_events"))
            c.execute(text(f"DROP FUNCTION IF EXISTS {name}()"))


def assert_sanitized_outage(error):
    assert error.value.code == "AUDIT_SINK_UNAVAILABLE" and error.value.status == 503
    assert error.value.__cause__ is None and error.value.__suppress_context__
    assert MARKER not in str(error.value) and MARKER not in repr(error.value)


def audit_rows(t, *conditions, principal=None):
    with t["admin"].connect() as c:
        return [
            dict(row) for row in c.execute(
                select(s.audit).where(s.audit.c.org_id == (principal or t["alice"]).org_id, *conditions)
                .order_by(s.audit.c.created_at, s.audit.c.id)
            ).mappings()
        ]


@pytest.fixture
def v13_database(postgres):
    _, parent, _ = postgres
    name = "aio_audit_upgrade_" + secrets.token_hex(6)
    with parent.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        with c.connection.driver_connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = parent.url.set(database=name).render_as_string(hide_password=False)
    command.upgrade(alembic_config(url), "0013_shared_budgets")
    engine = create_engine(url, hide_parameters=True)
    try:
        yield engine, url
    finally:
        engine.dispose()
        with parent.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            with c.connection.driver_connection.cursor() as cursor:
                cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def test_v14_upgrade_marks_history_legacy_and_refuses_a_lossy_downgrade(v13_database):
    engine, url = v13_database
    org, legacy = uuid4(), uuid4()
    with engine.begin() as c:
        c.execute(insert(schema_v13.organizations).values(id=org, name="Legacy audit tenant"))
        c.execute(insert(schema_v13.audit).values(
            org_id=org, id=legacy, actor_id=uuid4(), action="member.update", resource_id=uuid4(),
            outcome="updated", metadata={"active": True, "role": "member", "free": "historical text"},
        ))
        before = dict(c.execute(select(schema_v13.audit).where(schema_v13.audit.c.id == legacy)).mappings().one())
    command.upgrade(alembic_config(url), "head")
    with engine.begin() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == SCHEMA_REVISION
        after = dict(c.execute(select(s.audit).where(s.audit.c.id == legacy)).mappings().one())
        assert {k: after[k] for k in before} == before  # no historical field rewritten
        assert after["metadata_schema"] == "legacy"
        assert all(after[k] is None for k in ("trace_id", "resource_kind", "decision", "reason_code",
                                              "policy_revision", "subject_revision", "risk_class"))
        # NOT VALID kept history intact, yet a NEW free-form row is rejected.
        with pytest.raises(IntegrityError), c.begin_nested():
            c.execute(insert(s.audit).values(
                org_id=org, id=uuid4(), actor_id=uuid4(), action="member.update", outcome="updated",
                metadata={"free": "text"}, metadata_schema="legacy",
            ))
    # Only legacy facts: downgrade is allowed and restores the v13 shape.
    command.downgrade(alembic_config(url), "0013_shared_budgets")
    command.upgrade(alembic_config(url), "head")
    with engine.begin() as c:
        c.execute(insert(s.audit).values(
            org_id=org, id=uuid4(), actor_id=uuid4(), action="project.create", resource_id=uuid4(),
            outcome="created", metadata={}, metadata_schema="project.create:v1",
        ))
    with pytest.raises(RuntimeError, match="structured audit facts"):
        command.downgrade(alembic_config(url), "0013_shared_budgets")
    with engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == SCHEMA_REVISION
        assert c.execute(select(func.count()).select_from(s.audit)).scalar_one() == 2


@pytest.mark.parametrize("statement", [
    "UPDATE aio_audit_events SET outcome = 'rewritten'",
    "UPDATE aio_audit_events SET metadata = '{}'::jsonb",
    "DELETE FROM aio_audit_events",
    "UPDATE aio_outbox SET payload = '{}'::jsonb",
    "UPDATE aio_outbox SET kind = 'rewritten'",
    "UPDATE aio_outbox SET aggregate_id = org_id",
    "DELETE FROM aio_outbox",
])
def test_runtime_role_cannot_rewrite_audit_facts_or_outbox_payloads(tenant, statement):
    t = tenant
    with pytest.raises(ProgrammingError) as error:
        with t["db"].transaction(t["alice"]) as c:
            c.execute(text(statement))
    assert error.value.orig.sqlstate == "42501"  # insufficient_privilege, not an RLS zero-row no-op


def test_runtime_role_may_only_touch_delivery_bookkeeping_and_startup_rejects_drift(tenant):
    t = tenant
    with t["db"].transaction(t["alice"]) as c:
        c.execute(text(
            "UPDATE aio_outbox SET attempts = attempts, next_attempt_at = next_attempt_at, "
            "last_error_code = last_error_code, lease_owner = lease_owner, leased_until = leased_until, "
            "delivered_at = delivered_at"
        ))
    role = t["db"].engine.url.username
    with t["admin"].begin() as c:
        c.execute(text(f'GRANT UPDATE (outcome) ON aio_audit_events TO "{role}"'))
    try:
        with pytest.raises(PlatformConfigurationError, match="immutable"):
            t["db"].verify_runtime_role()
    finally:
        with t["admin"].begin() as c:
            c.execute(text(f'REVOKE UPDATE (outcome) ON aio_audit_events FROM "{role}"'))
    t["db"].verify_runtime_role()


VALID_ROW = {"action": "project.create", "outcome": "created", "metadata": {}, "metadata_schema": "project.create:v1"}


@pytest.mark.parametrize("change", [
    {},
    {"metadata_schema": "legacy"},
    {"metadata_schema": "member.update:v1"},
    {"metadata": []},
    {"metadata": {"blob": secrets.token_hex(3000)}},
    {"trace_id": "0" * 32},
    {"trace_id": "A" * 32},
    {"decision": "maybe"},
    {"risk_class": "R9"},
    {"resource_kind": "secret"},
    {"policy_revision": -1},
], ids=lambda change: ",".join(change) or "control")
def test_database_rejects_unstructured_or_oversized_audit_rows_even_for_the_owner(tenant, change):
    t = tenant
    values = {**VALID_ROW, **change, "org_id": t["org"], "id": uuid4(), "actor_id": t["alice"].user_id}
    if not change:
        with t["admin"].begin() as c:
            c.execute(insert(s.audit).values(**values))
        return
    with pytest.raises(IntegrityError):
        with t["admin"].begin() as c:
            c.execute(insert(s.audit).values(**values))


def test_audit_outage_before_dispatch_leaves_no_permit_and_no_effect(scenario):
    t = scenario()
    h = claim(t)
    seq, inv = commit_tool_turn(t, h)
    with audit_outage(t["admin"], t["org"], "tool.dispatch_prepared"):
        with pytest.raises(PlatformError) as error:
            t["store"].prepare_dispatch(h, seq, inv["id"])
    assert_sanitized_outage(error)
    assert current(t, s.dispatches) == []
    dispatch = t["store"].prepare_dispatch(h, seq, inv["id"])
    with audit_outage(t["admin"], t["org"], "tool.dispatch_consumed"):
        with pytest.raises(PlatformError) as error:
            t["store"].consume_dispatch(h, dispatch["id"])
    assert_sanitized_outage(error)
    # The send step rolled back as a whole: still consumable, never "dispatching", no start event.
    assert [d["state"] for d in current(t, s.dispatches)] == ["prepared"]
    assert not [e for e in current(t, s.events) if e["kind"] == "tool.started"]
    permit = t["store"].consume_dispatch(h, dispatch["id"])
    assert permit.id == dispatch["id"]
    facts = audit_rows(t, s.audit.c.resource_id == inv["id"])
    assert [f["action"] for f in facts] == ["tool.planned", "tool.dispatch_prepared", "tool.dispatch_consumed"]


def test_worker_under_a_consume_audit_outage_never_reaches_the_external_sink(scenario):
    t = scenario()
    sink = EffectSink()
    with audit_outage(t["admin"], t["org"], "tool.dispatch_consumed"):
        outcome = asyncio.run(worker(t, SyntheticModelFactory(), sink).run_once())
    assert sink.requests == [] and sink.operations == {}
    # Provably never sent (not "dispatching"/"unknown"), so no reconciliation blocker is needed.
    assert outcome["state"] == "failed" and current(t, s.runs)[0]["state"] == "failed"
    assert [d["state"] for d in current(t, s.dispatches)] == ["not_sent"]
    assert current(t, s.blockers) == []
    assert not audit_rows(t, s.audit.c.action == "tool.dispatch_consumed")


@pytest.mark.parametrize("forgery", ["skipped", "different_receipt"])
def test_permit_requires_its_own_fresh_audit_receipt(scenario, monkeypatch, forgery):
    """Negative control for require_recorded: removing/misdirecting the write must fail closed."""
    t = scenario()
    h = claim(t)
    seq, inv = commit_tool_turn(t, h)
    dispatch = t["store"].prepare_dispatch(h, seq, inv["id"])
    real = audit.record

    def forged(c, p, action, *args, **kwargs):
        if action != "tool.dispatch_consumed":
            return real(c, p, action, *args, **kwargs)
        if forgery == "skipped":
            return kwargs["event_id"]
        return real(c, p, action, *args, **{**kwargs, "event_id": uuid4()})

    monkeypatch.setattr(audit, "record", forged)
    with pytest.raises(PlatformError) as error:
        t["store"].consume_dispatch(h, dispatch["id"])
    assert error.value.code == "AUDIT_SINK_UNAVAILABLE"
    assert [d["state"] for d in current(t, s.dispatches)] == ["prepared"]
    assert not audit_rows(t, s.audit.c.action == "tool.dispatch_consumed")


def identity(t, role, org=None):
    org, uid = org or t["org"], uuid4()
    with t["admin"].begin() as c:
        provision_identity(
            c, org_id=org, user_id=uid, issuer=t["settings"].oidc_issuer, subject=str(uid),
            display_name="Synthetic " + role, role=role,
        )
    return Principal(org, uid, 0)


def test_audit_reads_are_role_limited_self_recorded_and_fail_closed(tenant):
    t = tenant
    service = AdminService(t["db"], t["settings"])
    operator, auditor = identity(t, "operator"), identity(t, "auditor")
    for denied in (operator, t["alice"]):
        with pytest.raises(PlatformError) as error:
            service.audit_events(denied)
        assert error.value.status == 403
    assert not audit_rows(t, s.audit.c.action == "audit.read")
    first = service.audit_events(auditor, 5)
    assert 0 < len(first) <= 5 and all("metadata" not in row for row in first)
    [read] = audit_rows(t, s.audit.c.action == "audit.read")
    assert (read["actor_id"], read["resource_id"], read["resource_kind"]) == (auditor.user_id, t["org"], "organization")
    assert read["metadata"] == {
        "scope": "organization", "row_count": len(first), "limit": 5, "since": None, "until": None,
        "before_created_at": None, "before_id": None,
    }
    with audit_outage(t["admin"], t["org"], "audit.read"):
        with pytest.raises(PlatformError) as error:
            service.audit_events(auditor, 5)
    assert_sanitized_outage(error)
    assert len(audit_rows(t, s.audit.c.action == "audit.read")) == 1


def test_audit_pages_are_tenant_scoped_complete_and_index_ordered(tenant):
    t = tenant
    service = AdminService(t["db"], t["settings"])
    auditor = identity(t, "auditor")
    for index in range(23):
        t["service"].create_project(t["alice"], f"Audit page fixture {index}")
    with t["admin"].connect() as c:
        until = c.execute(text("SELECT clock_timestamp()")).scalar_one()
    expected = {r["id"] for r in audit_rows(t, s.audit.c.created_at < until)}
    seen, cursor = [], {}
    while True:
        page = service.audit_events(auditor, 7, until=until, **cursor)
        seen += [row["id"] for row in page]
        if len(page) < 7:
            break
        cursor = {"before_created_at": page[-1]["created_at"], "before_id": page[-1]["id"]}
    assert len(seen) == len(set(seen)) and set(seen) == expected and len(expected) > 23
    outsider_admin = identity(t, "auditor", org=t["outsider"].org_id)
    assert not {row["id"] for row in service.audit_events(outsider_admin, 200)} & expected
    with t["db"].transaction(auditor) as c:
        c.execute(text("SET LOCAL enable_seqscan = off"))
        plan = c.execute(text(
            "EXPLAIN (FORMAT JSON) SELECT id FROM aio_audit_events WHERE org_id = :org "
            "ORDER BY created_at DESC, id LIMIT 7"
        ), {"org": t["org"]}).scalar_one()
    rendered = json.dumps(plan)
    assert "ix_aio_audit_org_created_id" in rendered and '"Sort"' not in rendered


def test_a_real_approved_run_records_closed_decision_facts_without_content(scenario):
    t = scenario("R2")
    factory, sink = SyntheticModelFactory(), EffectSink()
    asyncio.run(worker(t, factory, sink).run_once())
    a = current(t, s.approvals)[0]
    t["service"].decide_approval(t["bob"], a["id"], a["revision"], a["action_digest"], "approve")
    assert asyncio.run(worker(t, factory, sink, "replacement-worker").run_once())["state"] == "succeeded"
    facts = audit_rows(t, s.audit.c.run_id == t["run_id"])
    by_action = {f["action"]: f for f in facts}
    assert {"run.create", "model.prepared", "tool.planned", "approval.decide", "tool.dispatch_prepared",
            "tool.dispatch_consumed", "tool.result", "run.finalized"} <= set(by_action)
    for fact in facts:
        assert fact["metadata_schema"] == fact["action"] + ":v1"
        assert fact["metadata"] == audit.CONTRACTS[fact["action"]].metadata.model_validate(fact["metadata"]).model_dump(
            mode="json"
        )
    planned = by_action["tool.planned"]
    assert (planned["decision"], planned["reason_code"], planned["risk_class"]) == (
        "approval_required", "APPROVAL_REQUIRED", "R2"
    )
    assert planned["metadata"]["action_digest"] == a["action_digest"]
    decided = by_action["approval.decide"]
    assert decided["actor_id"] == t["bob"].user_id and decided["outcome"] == "approved"
    assert decided["metadata"]["requested_by"] == str(t["alice"].user_id)
    assert by_action["tool.result"]["metadata"]["dispatch_outcome"] == "succeeded"
    serialized = json.dumps([f["metadata"] for f in facts])
    for content in ("capture and answer", "Verified answer", '"value"', "captured"):
        assert content not in serialized


def test_http_audit_facts_carry_the_server_trace_not_a_client_header(tenant):
    t = tenant
    settings = replace(t["settings"], database_url=t["db"].engine.url.render_as_string(hide_password=False))
    auth = AuthService(t["db"], settings)
    token, _ = auth.create_session(t["org"], settings.oidc_issuer, str(t["alice"].user_id))
    spoofed = "f" * 32
    headers = {
        "Origin": settings.public_origin, "X-CSRF-Token": csrf_token(token),
        "traceparent": f"00-{spoofed}-{'1' * 16}-01", "X-Request-ID": str(UUID(spoofed)),
    }
    with TestClient(create_platform_app(settings, database=t["db"]), base_url=settings.public_origin) as client:
        client.cookies.set(settings.session_cookie, token)
        response = client.post("/api/v2/projects", json={"name": "Traced project"}, headers=headers)
    assert response.status_code == 201
    [fact] = audit_rows(t, s.audit.c.resource_id == UUID(response.json()["id"]))
    assert fact["trace_id"] == UUID(response.headers["x-request-id"]).hex != spoofed


def test_reconciliation_is_audited_fail_closed_and_binds_only_an_evidence_digest(scenario):
    t = scenario()
    asyncio.run(worker(t, sink=EffectSink(lose_response=True)).run_once())
    with t["admin"].begin() as c:
        c.execute(insert(s.grants).values(
            id=uuid4(), org_id=t["org"], resource_id=t["run_id"], subject_id=t["bob"].user_id, action="run.reconcile"
        ))
    run = current(t, s.runs)[0]
    evidence = "ticket/INC-4711 synthetic free-text note"
    with audit_outage(t["admin"], t["org"], "run.reconcile"):
        with pytest.raises(PlatformError) as error:
            t["store"].reconcile(t["bob"], t["run_id"], run["revision"], "confirmed_success", evidence)
    assert_sanitized_outage(error)
    assert current(t, s.runs)[0]["state"] == "recovery_required"
    assert current(t, s.blockers)[0]["resolved_at"] is None
    t["store"].reconcile(t["bob"], t["run_id"], run["revision"], "confirmed_success", evidence)
    [fact] = audit_rows(t, s.audit.c.action == "run.reconcile")
    assert fact["actor_id"] == t["bob"].user_id and fact["risk_class"] == "R0"
    assert fact["metadata"]["conclusion"] == "confirmed_success" and fact["metadata"]["resolved_invocations"] == 1
    assert len(fact["metadata"]["evidence_digest"]) == 64 and "INC-4711" not in json.dumps(fact["metadata"])


def test_audit_http_is_role_limited_contentless_and_rejects_partial_cursors(tenant):
    t = tenant
    settings = replace(t["settings"], database_url=t["db"].engine.url.render_as_string(hide_password=False))
    auth = AuthService(t["db"], settings)
    operator, auditor = identity(t, "operator"), identity(t, "auditor")
    with TestClient(create_platform_app(settings, database=t["db"]), base_url=settings.public_origin) as client:
        def as_user(p):
            token, _ = auth.create_session(t["org"], settings.oidc_issuer, str(p.user_id))
            client.cookies.set(settings.session_cookie, token)

        as_user(operator)
        denied = client.get("/api/v2/admin/audit")
        assert denied.status_code == 403 and denied.json()["error"]["code"] == "ADMIN_FORBIDDEN"
        assert str(t["alice"].user_id) not in denied.text
        as_user(auditor)
        ok = client.get("/api/v2/admin/audit", params={"limit": 3})
        assert ok.status_code == 200 and 0 < len(ok.json()["items"]) <= 3
        assert all("metadata" not in item for item in ok.json()["items"])
        partial = client.get("/api/v2/admin/audit", params={"before_id": str(uuid4())})
        assert partial.status_code == 422 and partial.json()["error"]["code"] == "AUDIT_QUERY_INVALID"
        naive = client.get("/api/v2/admin/audit", params={"since": "2026-01-01T00:00:00"})
        assert naive.status_code == 422
    reads = audit_rows(t, s.audit.c.action == "audit.read")
    assert [r["actor_id"] for r in reads] == [auditor.user_id] and reads[0]["trace_id"] is not None


def test_writer_refuses_a_principal_outside_the_scoped_transaction(tenant):
    t = tenant
    with pytest.raises(PlatformError) as error:
        with t["db"].transaction(t["alice"]) as c:
            audit.record(c, t["outsider"], "project.create", uuid4(), "created", m.EmptyMetadata())
    assert error.value.code == "AUDIT_SINK_UNAVAILABLE"
    assert audit_rows(t, principal=t["outsider"]) == []
