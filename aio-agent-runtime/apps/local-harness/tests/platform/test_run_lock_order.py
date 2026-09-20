"""Real PG queue/control mutations must not invert the Worker's resource lock order."""

from datetime import datetime, timedelta, timezone
from functools import partial
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.exc import OperationalError

from app.auth.principal import Principal
from app.db import schema as s
from app.runtime.contracts import WorkHandle
from app.runtime.execution import ExecutionStore
import app.runtime.service as service_module
import app.policy.repository as locks
from lock_fixtures import resource_before_run, organization_before_resource
from test_postgres_integration import action, body, create_run, running


def second_run(t):
    session = t["service"].create_session(t["alice"], t["project"], t["agent"], "Second queued session")["id"]
    return t["service"].create_run(t["alice"], session, body(t), "lock-order-" + uuid4().hex)["run_id"]


@pytest.mark.parametrize("held", ["resource", "run", "job"])
def test_queued_claim_skips_locked_candidate_without_owning_later_locks(tenant, monkeypatch, held):
    t = tenant
    first = create_run(t)["run_id"]
    second = second_run(t)
    table = {"resource": s.resources, "run": s.runs, "job": s.jobs}[held]
    field = table.c.run_id if held == "job" else table.c.id
    prefix = service_module.try_lock_run_resources
    inspected = []

    def checked_prefix(connection, org, run_id):
        if run_id == second:
            # The OUTER claim transaction is still alive here. A skipped
            # candidate must release even its non-contended resource/Run locks.
            with t["admin"].begin() as observer:
                observer.execute(
                    select(s.resources.c.id).where(s.resources.c.id == t["session"]).with_for_update(nowait=True)
                ).one()
                if held == "job":
                    observer.execute(select(s.runs.c.id).where(s.runs.c.id == first).with_for_update(nowait=True)).one()
            inspected.append(True)
        return prefix(connection, org, run_id)

    monkeypatch.setattr(service_module, "try_lock_run_resources", checked_prefix)
    with t["db"].transaction(t["alice"]) as holder:
        holder.execute(select(table.c.id).where(table.c.org_id == t["org"], field == first).with_for_update()).one()
        # There is no sleep or synthetic transaction mock. Old Run-first claiming
        # times out on a held resource/job instead of proceeding to the next Run.
        claimed = t["service"].claim_next(t["org"], "independent-claim")
        assert claimed["id"] == second and claimed["generation"] == 1
        assert holder.execute(select(s.runs.c.state).where(s.runs.c.id == first)).scalar_one() == "queued"
        holder.execute(select(s.resources.c.id).where(s.resources.c.id == first).with_for_update(nowait=True)).one()
    assert t["service"].claim_next(t["org"], "next-claim")["id"] == first
    assert inspected == [True]


def test_queue_claim_never_owns_resources_while_organization_is_busy(tenant):
    t = tenant
    run_id = create_run(t)["run_id"]
    with t["db"].transaction(t["alice"]) as holder:
        holder.execute(select(s.organizations.c.id).where(s.organizations.c.id == t["org"]).with_for_update()).one()
        assert t["service"].claim_next(t["org"], "busy-organization") is None
        assert holder.execute(select(s.runs.c.generation).where(s.runs.c.id == run_id)).scalar_one() == 0
    assert t["service"].claim_next(t["org"], "available-organization")["id"] == run_id


@pytest.mark.parametrize("change", ["cancel", "delay", "expire"])
def test_claim_rechecks_current_eligibility_after_nonlocking_candidate_scan(tenant, monkeypatch, change):
    t = tenant
    first = create_run(t)["run_id"]
    second = second_run(t)
    prefix = service_module.try_lock_run_resources

    def changed(connection, org, run_id):
        if run_id == first:
            if change == "cancel":
                t["service"].cancel_run(t["alice"], first)
            else:
                with t["admin"].begin() as writer:
                    if change == "delay":
                        writer.execute(
                            update(s.jobs)
                            .where(s.jobs.c.run_id == first)
                            .values(not_before=datetime.now(timezone.utc) + timedelta(seconds=60))
                        )
                    else:
                        writer.execute(
                            update(s.runs)
                            .where(s.runs.c.id == first)
                            .values(queue_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
                        )
        return prefix(connection, org, run_id)

    monkeypatch.setattr(service_module, "try_lock_run_resources", changed)
    assert t["service"].claim_next(t["org"], "fresh-eligibility")["id"] == second
    with t["db"].transaction(t["alice"]) as connection:
        assert connection.execute(select(s.runs.c.generation).where(s.runs.c.id == first)).scalar_one() == 0


@pytest.mark.parametrize("operation", ["cancel", "transition", "plan", "approve"])
def test_run_mutation_receipts_obey_resource_before_run_order(tenant, monkeypatch, operation):
    t = tenant
    if operation == "cancel":
        run_id = create_run(t)["run_id"]
        callback = partial(t["service"].cancel_run, t["alice"], run_id)
        expected = "cancelled"
    elif operation == "transition":
        run_id = create_run(t)["run_id"]
        claimed = t["service"].claim_next(t["org"], "transition-worker")
        callback = partial(t["service"].transition_run, t["alice"], run_id, claimed["generation"], "running")
        expected = "running"
    else:
        run = running(t)
        run_id = run["id"]
        spec = action(t, run)
        if operation == "plan":
            callback = partial(t["service"].plan_invocation, t["alice"], run_id, run["generation"], spec)
            expected = "waiting_approval"
        else:
            planned = t["service"].plan_invocation(t["alice"], run_id, run["generation"], spec)
            with t["admin"].begin() as connection:
                connection.execute(
                    insert(s.grants).values(
                        org_id=t["org"],
                        id=uuid4(),
                        resource_id=planned["approval_id"],
                        subject_id=t["bob"].user_id,
                        action="approval.decide",
                    )
                )
            callback = partial(
                t["service"].decide_approval, t["bob"], planned["approval_id"], 0, spec.digest, "approve"
            )
            expected = "approved"
    result = resource_before_run(t, monkeypatch, run_id, callback)
    assert result["state"] == expected


@pytest.mark.parametrize("revoked", [False, True])
def test_system_stop_locks_organization_before_resources_without_reauthorizing_actor(tenant, monkeypatch, revoked):
    t = tenant
    run_id = create_run(t)["run_id"]
    run = t["service"].claim_next(t["org"], "system-stop")
    handle = WorkHandle(
        Principal(t["org"], t["alice"].user_id, 0, service_actor_id="system-stop"),
        run_id,
        run["generation"],
        "system-stop",
        run["deadline_at"],
    )
    if revoked:
        with t["admin"].begin() as writer:
            writer.execute(update(s.organizations).where(s.organizations.c.id == t["org"]).values(active=False))
    store = ExecutionStore(t["db"], t["settings"])
    result = organization_before_resource(t, monkeypatch, run_id, partial(store.abort, handle, "SYNTHETIC_STOP"))
    assert result["state"] == "failed"


@pytest.mark.parametrize("sqlstate", ["40P01", "08006"])
def test_queue_prefix_does_not_hide_deadlocks_or_infrastructure_errors(tenant, monkeypatch, sqlstate):
    t = tenant
    run_id = create_run(t)["run_id"]
    cause = RuntimeError("synthetic database failure")
    cause.sqlstate = sqlstate
    original = OperationalError("synthetic statement", {}, cause, hide_parameters=True)

    def fail(*args):
        raise original

    monkeypatch.setattr(locks, "_resource_lock_query", fail)
    with t["db"].transaction(t["alice"]) as connection:
        with pytest.raises(OperationalError) as raised:
            locks.try_lock_run_resources(connection, t["org"], run_id)
        assert raised.value is original
        with t["admin"].begin() as observer:
            observer.execute(
                select(s.organizations.c.id).where(s.organizations.c.id == t["org"]).with_for_update(nowait=True)
            ).one()


def test_missing_queue_candidate_releases_prefix_locks_inside_outer_transaction(tenant):
    t = tenant
    with t["db"].transaction(t["alice"]) as connection:
        assert locks.try_lock_run_resources(connection, t["org"], uuid4()) is False
        with t["admin"].begin() as observer:
            observer.execute(
                select(s.organizations.c.id).where(s.organizations.c.id == t["org"]).with_for_update(nowait=True)
            ).one()
