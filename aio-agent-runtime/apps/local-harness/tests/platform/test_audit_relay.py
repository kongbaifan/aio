"""Real PostgreSQL evidence for audit archive delivery (GOV-02 Slice B).

The archive is a FAKE sink honouring the adapter contract; no SIEM/object archive is deployed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, text, update

from app.db import schema as s
from app.db import schema_v13
from app.observability import audit
from app.observability.archive import ArchiveDeliveryError, AuditRelay
from app.platform_errors import PlatformError
from test_audit_integration import alembic_config, audit_outage
from test_audit_integration import v13_database as v13_database  # noqa: F401 - fixture re-export
from test_execution_integration import EffectSink, SyntheticModelFactory, worker
from test_execution_integration import scenario as scenario  # noqa: F401 - fixture re-export

MARKER = "synthetic-archive-response-marker"


class MemorySink:
    """Contract-consistent fake: dedupes on idempotency_key, as any real adapter must."""

    def __init__(self, script=(), log=None):
        self.script, self.log = list(script), log if log is not None else []
        self.stored = {}

    async def deliver(self, record):
        self.log.append(record.idempotency_key)
        step = self.script.pop(0) if self.script else None
        if step == "timeout":
            await asyncio.sleep(5)
        elif isinstance(step, BaseException):
            raise step
        self.stored.setdefault(record.idempotency_key, record)


def relay(t, sink, owner="relay-a", **kwargs):
    return AuditRelay(t["db"], t["org"], owner, sink, timeout_seconds=0.2, lease_seconds=30, **kwargs)


def entries(t, *conditions, org=None):
    with t["admin"].connect() as c:
        return [dict(r) for r in c.execute(
            select(s.outbox).where(s.outbox.c.org_id == (org or t["org"]), s.outbox.c.kind == audit.ARCHIVE_KIND,
                                   *conditions).order_by(s.outbox.c.created_at, s.outbox.c.id)
        ).mappings()]


def facts(t, org=None):
    with t["admin"].connect() as c:
        return set(c.execute(select(s.audit.c.id).where(
            s.audit.c.org_id == (org or t["org"]), s.audit.c.metadata_schema != "legacy"
        )).scalars())


def make_due(t):
    with t["admin"].begin() as c:
        c.execute(update(s.outbox).where(s.outbox.c.org_id == t["org"]).values(
            next_attempt_at=text("clock_timestamp() - interval '1 second'")
        ))


def test_every_committed_fact_has_exactly_one_delivery_entry_and_rollback_has_none(tenant):
    t = tenant
    assert sorted(e["aggregate_id"] for e in entries(t)) == sorted(facts(t)) and facts(t)
    before = len(entries(t))
    with pytest.raises(RuntimeError):
        with t["db"].transaction(t["alice"]) as c:
            audit.record(c, t["alice"], "project.create", uuid4(), "created")
            raise RuntimeError("business step failed after the fact")
    with audit_outage(t["admin"], t["org"], "project.create"):
        with pytest.raises(PlatformError) as error:
            t["service"].create_project(t["alice"], "Never created")
    assert error.value.code == "AUDIT_SINK_UNAVAILABLE"
    assert len(entries(t)) == before and all(e["payload"] == {} for e in entries(t))


def test_relay_delivers_each_closed_fact_once_and_marks_it_delivered(tenant):
    t = tenant
    project = t["service"].create_project(t["alice"], "Synthetic confidential project name")["id"]
    sink = MemorySink()
    result = asyncio.run(relay(t, sink).run_once())
    assert result == {"claimed": len(facts(t)), "delivered": len(facts(t)), "failed": 0, "lost_lease": 0}
    assert {r.audit_id for r in sink.stored.values()} == facts(t)
    assert all(e["delivered_at"] and e["attempts"] == 1 and e["lease_owner"] is None and e["leased_until"] is None
               and e["last_error_code"] is None for e in entries(t))
    assert asyncio.run(relay(t, sink).run_once())["claimed"] == 0
    created = next(r for r in sink.stored.values() if r.resource_id == project)
    assert (created.action, created.outcome, created.metadata_schema) == ("project.create", "created", "project.create:v1")
    assert "confidential" not in json.dumps([r.model_dump(mode="json") for r in sink.stored.values()])
    assert relay(t, sink).backlog() == {
        "state": "ok", "code": None, "pending": 0, "retrying": 0, "oldest_pending_seconds": 0, "errors": {}
    }


def test_failed_deliveries_back_off_with_stable_codes_until_success(tenant):
    t = tenant
    asyncio.run(relay(t, MemorySink()).run_once())
    t["service"].create_project(t["alice"], "Retry fixture")
    sink = MemorySink([ArchiveDeliveryError("ARCHIVE_UNAVAILABLE"), "timeout", RuntimeError(MARKER), None])
    expected = [("ARCHIVE_UNAVAILABLE", 5), ("ARCHIVE_TIMEOUT", 10), ("ARCHIVE_DELIVERY_FAILED", 20)]
    for attempt, (code, delay) in enumerate(expected, start=1):
        assert asyncio.run(relay(t, sink).run_once())["failed"] == 1
        [entry] = entries(t, s.outbox.c.delivered_at.is_(None))
        with t["admin"].connect() as c:
            wait = c.execute(select(func.date_part("epoch", s.outbox.c.next_attempt_at - func.clock_timestamp())).where(
                s.outbox.c.id == entry["id"])).scalar_one()
        assert (entry["attempts"], entry["last_error_code"]) == (attempt, code) and delay - 2 < wait <= delay
        assert entry["lease_owner"] is None and MARKER not in json.dumps(entry, default=str)
        assert asyncio.run(relay(t, sink).run_once())["claimed"] == 0  # not due yet: no hot retry loop
        make_due(t)
    assert asyncio.run(relay(t, sink).run_once())["delivered"] == 1
    [entry] = entries(t, s.outbox.c.id == entry["id"])
    assert entry["attempts"] == 4 and entry["delivered_at"] and entry["last_error_code"] is None
    assert len(sink.stored) == 1 and len(sink.log) == 4


def test_concurrent_relays_skip_locked_rows_and_deliver_each_fact_once(tenant):
    t = tenant
    for index in range(12):
        t["service"].create_project(t["alice"], f"Concurrent fixture {index}")
    a, b = relay(t, MemorySink(), "relay-a", batch_size=5), relay(t, MemorySink(), "relay-b", batch_size=5)
    with t["db"].scoped(t["org"], t["alice"].user_id) as held:
        first = {claim.outbox_id for claim in a.claim(held)}  # still locked: transaction not committed
        second = {claim.outbox_id for claim in b._claim()}
        assert len(first) == len(second) == 5 and not first & second
    shared = []
    sinks = [MemorySink(log=shared), MemorySink(log=shared)]
    make_due(t)
    with t["admin"].begin() as c:
        c.execute(update(s.outbox).where(s.outbox.c.org_id == t["org"]).values(lease_owner=None, leased_until=None))

    async def drain():
        relays = [relay(t, sinks[0], "relay-c", batch_size=3), relay(t, sinks[1], "relay-d", batch_size=3)]
        while True:
            results = await asyncio.gather(*(r.run_once() for r in relays))
            if not any(r["claimed"] for r in results):
                return

    asyncio.run(drain())
    assert sorted(shared) == sorted(set(shared)) and len(shared) == len(facts(t))
    assert all(e["delivered_at"] and e["attempts"] == 1 for e in entries(t))


def test_expired_lease_is_taken_over_and_the_stale_relay_changes_nothing(tenant):
    t = tenant
    a, sink = relay(t, MemorySink(), "relay-a"), MemorySink()
    stale = a._claim()  # relay A leases, then "crashes" before sending
    assert stale and asyncio.run(relay(t, sink, "relay-b").run_once())["claimed"] == 0
    with t["admin"].begin() as c:
        c.execute(update(s.outbox).where(s.outbox.c.org_id == t["org"]).values(
            leased_until=text("clock_timestamp() - interval '1 second'")))
    b = relay(t, sink, "relay-b")
    taken = b._claim()  # B now holds the lease and has not finished yet
    assert {claim.outbox_id for claim in taken} == {claim.outbox_id for claim in stale}
    held = entries(t)
    assert not a.finish(stale[0].outbox_id, None) and not a.finish(stale[0].outbox_id, "ARCHIVE_UNAVAILABLE")
    assert entries(t) == held and all(e["lease_owner"] == "relay-b" and e["delivered_at"] is None for e in held)
    for claim in taken:
        asyncio.run(sink.deliver(claim.record))
        assert b.finish(claim.outbox_id, None)
    snapshot = entries(t)
    assert not a.finish(stale[0].outbox_id, None) and entries(t) == snapshot
    # A resend after takeover carries the same key, so an idempotent archive stores it once.
    assert stale[0].record.idempotency_key in sink.stored and len(sink.stored) == len(stale)


def test_claim_locks_only_outbox_rows_and_send_holds_no_connection(tenant):
    t = tenant
    business = ("aio_runs", "aio_organizations", "aio_budget_pools", "aio_budgets", "aio_jobs", "aio_resources")
    with t["db"].scoped(t["org"], t["alice"].user_id) as c:
        assert relay(t, MemorySink()).claim(c)
        locked = set(c.execute(text(
            "SELECT DISTINCT c.relname FROM pg_locks l JOIN pg_class c ON c.oid = l.relation "
            "WHERE l.pid = pg_backend_pid() AND c.relkind = 'r'"
        )).scalars())
    assert "aio_outbox" in locked and not locked & set(business)
    make_due(t)
    with t["admin"].begin() as c:
        c.execute(update(s.outbox).where(s.outbox.c.org_id == t["org"]).values(lease_owner=None, leased_until=None))
    observed = []

    class Probe(MemorySink):
        async def deliver(self, record):
            observed.append(t["db"].engine.pool.checkedout())
            await super().deliver(record)

    asyncio.run(relay(t, Probe()).run_once())
    assert observed and set(observed) == {0}


def test_archive_outage_never_blocks_business_and_is_reported_only_as_backlog(scenario):
    t = scenario()
    down = MemorySink([ArchiveDeliveryError("ARCHIVE_UNAVAILABLE")] * 100)
    archive = relay(t, down, backlog_alert_seconds=0)
    asyncio.run(archive.run_once())
    sink = EffectSink()
    outcome = asyncio.run(worker(t, SyntheticModelFactory(), sink).run_once())
    assert outcome["state"] == "succeeded" and len(sink.operations) == 1  # authorized dispatch still ran
    run = t["service"].get_run(t["alice"], t["run_id"])
    sessions = t["service"].list_sessions(t["alice"])
    events, _ = t["service"].read_events(t["alice"], t["run_id"], 0)  # SSE replay source
    assert events and events[-1]["kind"] == "run.completed"
    assert "AUDIT_ARCHIVE" not in json.dumps([run, sessions, events], default=str)
    status = archive.backlog()
    assert status["code"] == "AUDIT_ARCHIVE_BACKLOG" and status["pending"] == len(facts(t))
    assert status["retrying"] >= 1 and status["errors"] == {"ARCHIVE_UNAVAILABLE": status["retrying"]}
    # Recovery delivers everything that accumulated; nothing written during the outage is lost.
    make_due(t)
    healthy = MemorySink()
    while asyncio.run(relay(t, healthy).run_once())["claimed"]:
        make_due(t)
    assert {r.audit_id for r in healthy.stored.values()} == facts(t)
    assert relay(t, healthy, backlog_alert_seconds=0).backlog()["state"] == "ok"
    serialized = json.dumps([r.model_dump(mode="json") for r in healthy.stored.values()])
    for content in ("capture and answer", "Verified answer", '"value"'):
        assert content not in serialized


def test_an_entry_without_a_projectable_fact_is_never_sent(tenant):
    t = tenant
    asyncio.run(relay(t, MemorySink()).run_once())
    with t["admin"].begin() as c:
        c.execute(insert(s.outbox).values(
            org_id=t["org"], id=uuid4(), aggregate_id=uuid4(), kind=audit.ARCHIVE_KIND, payload={}))
    sink = MemorySink()
    assert asyncio.run(relay(t, sink).run_once())["failed"] == 1 and sink.log == []
    [entry] = entries(t, s.outbox.c.delivered_at.is_(None))
    assert entry["last_error_code"] == "ARCHIVE_RECORD_INVALID" and entry["attempts"] == 1


def test_relay_is_tenant_scoped(tenant):
    t = tenant
    t["service"].create_project(t["outsider"], "Other tenant project")
    other = entries(t, org=t["outsider"].org_id)
    sink = MemorySink()
    asyncio.run(relay(t, sink).run_once())
    assert other and {r.org_id for r in sink.stored.values()} == {t["org"]}
    assert entries(t, org=t["outsider"].org_id) == other  # untouched: no lease, attempt or delivery


def test_claim_query_uses_the_scoped_pending_index_without_a_sort(tenant):
    t = tenant
    statement = relay(t, MemorySink()).due().compile(dialect=t["db"].engine.dialect)
    with t["db"].scoped(t["org"], t["alice"].user_id) as c:
        c.execute(text("SET LOCAL enable_seqscan = off"))
        plan = c.exec_driver_sql("EXPLAIN (FORMAT JSON) " + str(statement), statement.params).scalar_one()
    rendered = json.dumps(plan)
    assert "ix_aio_outbox_audit_pending" in rendered and '"Sort"' not in rendered


def test_serve_alerts_on_backlog_without_leaking_sink_text_and_stops(tenant, caplog):
    t = tenant
    stopping = asyncio.Event()

    async def run():
        task = asyncio.create_task(
            relay(t, MemorySink([RuntimeError(MARKER)] * 10), backlog_alert_seconds=0).serve(stopping, poll_seconds=0.05)
        )
        await asyncio.sleep(0.5)
        stopping.set()
        await asyncio.wait_for(task, 2)

    with caplog.at_level(logging.WARNING, logger="app.observability.archive"):
        asyncio.run(run())
    messages = [r.getMessage() for r in caplog.records if r.name == "app.observability.archive"]
    assert any(msg.startswith("AUDIT_ARCHIVE_BACKLOG") for msg in messages)
    assert not any(MARKER in msg for msg in messages)


def test_v15_enqueues_v14_structured_facts_once_and_never_legacy_rows(v13_database):
    from alembic import command

    engine, url = v13_database
    org, legacy = uuid4(), uuid4()
    with engine.begin() as c:  # v13 shape: no metadata_schema column yet
        c.execute(insert(schema_v13.organizations).values(id=org, name="Archive backfill tenant"))
        c.execute(insert(schema_v13.audit).values(
            org_id=org, id=legacy, actor_id=uuid4(), action="member.update", outcome="updated", metadata={"free": "x"},
        ))
    command.upgrade(alembic_config(url), "0014_audit_records")
    structured = uuid4()
    with engine.begin() as c:  # the v14 writer had no outbox entry
        c.execute(insert(s.audit).values(
            org_id=org, id=structured, actor_id=uuid4(), action="project.create", resource_id=uuid4(),
            outcome="created", metadata={}, metadata_schema="project.create:v1",
        ))
    for target in ("head", "0014_audit_records", "head"):
        (command.upgrade if target == "head" else command.downgrade)(alembic_config(url), target)
    with engine.connect() as c:
        pointers = c.execute(select(s.outbox.c.aggregate_id).where(s.outbox.c.kind == audit.ARCHIVE_KIND)).scalars().all()
        indexes = set(c.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'aio_outbox'")).scalars())
    assert pointers == [structured] and "ix_aio_outbox_audit_pending" in indexes
