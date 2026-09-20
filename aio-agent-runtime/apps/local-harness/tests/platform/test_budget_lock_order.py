"""Real PostgreSQL concurrency regressions for the shared-budget L3 lock prefix.

The documented order is organization pool -> department pool -> personal budget ->
Run / receipt / allocations. Nothing in this codebase uses advisory locks; the order
exists only because `app/billing/budgets.py` emits row-level `FOR UPDATE` in a fixed
sequence. These tests therefore hold exactly one row of that prefix and inspect what a
blocked caller already owns, and they contrast the production sequence with an inverted
control written inline here (production code is never patched).
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
from functools import partial
import queue
import threading
from threading import Barrier, BrokenBarrierError
import time

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from app.db import schema as s
from app.platform_errors import PlatformError
from test_administration import administration as administration
from test_shared_budgets import assert_projection, create, department, private_session, rows


def _sqlstate(error):
    return getattr(getattr(error, "orig", None), "sqlstate", None) or "unknown"


def _pool_rows(t):
    return {row["department_id"]: row for row in rows(t, s.budget_pools)}


def _pool_query(t, department_id):
    scope = (
        s.budget_pools.c.department_id.is_(None)
        if department_id is None
        else s.budget_pools.c.department_id == department_id
    )
    return select(s.budget_pools.c.id).where(s.budget_pools.c.org_id == t["org"], scope)


def _personal_query(t):
    return select(s.budgets.c.id).where(
        s.budgets.c.org_id == t["org"], s.budgets.c.owner_id == t["alice"].user_id, s.budgets.c.currency == "USD"
    )


def _lock_pool(c, org_id, pool_id):
    return c.execute(
        select(s.budget_pools.c.id)
        .where(s.budget_pools.c.org_id == org_id, s.budget_pools.c.id == pool_id)
        .with_for_update()
    ).scalar_one()


def _probe(t, query):
    """Return None when nobody holds the row, or the refusal SQLSTATE when somebody does."""
    try:
        with t["db"].transaction(t["alice"]) as probe:
            probe.execute(query.with_for_update(nowait=True)).one()
    except OperationalError as error:
        return _sqlstate(error)
    return None


def _wait_for_lock(t, pid, future):
    """Observe the real backend entering a Lock wait; no fixed sleep decides the timing."""
    deadline = time.monotonic() + 2
    with t["admin"].connect() as observer:
        while True:
            observer.execute(text("SELECT pg_stat_clear_snapshot()"))
            waiting = observer.execute(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid"), {"pid": pid}
            ).scalar_one_or_none()
            if waiting == "Lock":
                return
            if future.done():
                future.result()
                raise AssertionError("The budget prefix never waited for the held department pool")
            if time.monotonic() >= deadline:
                raise AssertionError("The budget prefix did not reach an observable lock wait")
            time.sleep(0.01)


def _observed_prefix(t, monkeypatch, held_pool_id, callback):
    """Hold ONLY the department pool, then report which later prefix rows the blocked caller owns."""
    pids = queue.Queue()
    original = t["db"].scoped

    @contextmanager
    def traced(org_id, user_id):
        with original(org_id, user_id) as connection:
            if threading.current_thread().name.startswith("budget-prefix"):
                pids.put(connection.connection.driver_connection.info.backend_pid)
            yield connection

    monkeypatch.setattr(t["db"], "scoped", traced)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="budget-prefix")
    try:
        with t["db"].transaction(t["alice"]) as holder:
            _lock_pool(holder, t["org"], held_pool_id)
            future = executor.submit(callback)
            _wait_for_lock(t, pids.get(timeout=5), future)
            observed = {
                "organization_pool": _probe(t, _pool_query(t, None)),
                "personal_budget": _probe(t, _personal_query(t)),
            }
        return observed, future.result(timeout=10)
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


def _race(t, actors):
    """Run one admission per actor with a real thread barrier; never abort the map on refusal."""
    barrier = Barrier(len(actors))

    def enter(index):
        principal, item = actors[index]
        barrier.wait(timeout=10)
        try:
            return create(t, principal, item)
        except PlatformError as error:
            return error.code
        except OperationalError as error:
            return "sqlstate:" + _sqlstate(error)

    with ThreadPoolExecutor(max_workers=len(actors)) as executor:
        return list(executor.map(enter, range(len(actors))))


def _control_ensure(c, org_id, department_ids=(), *, lock_pools=True, organization_first=True):
    """SCRATCH CONTROL ONLY. A deliberately wrong prefix, injected by monkeypatch, never on disk."""
    from uuid import uuid4

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    c.execute(pg_insert(s.budget_pools).values(id=uuid4(), org_id=org_id).on_conflict_do_nothing())
    ids = sorted(set(department_ids))
    for department_id in ids:
        c.execute(
            pg_insert(s.budget_pools)
            .values(id=uuid4(), org_id=org_id, department_id=department_id)
            .on_conflict_do_nothing()
        )
    organization_q = select(s.budget_pools).where(
        s.budget_pools.c.org_id == org_id, s.budget_pools.c.department_id.is_(None)
    )
    departments_q = (
        select(s.budget_pools)
        .where(s.budget_pools.c.org_id == org_id, s.budget_pools.c.department_id.in_(ids))
        .order_by(s.budget_pools.c.id)
    )
    if lock_pools:
        organization_q, departments_q = organization_q.with_for_update(), departments_q.with_for_update()
    if organization_first:
        organization = c.execute(organization_q).mappings().one()
        departments = c.execute(departments_q).mappings().all()
    else:
        departments = c.execute(departments_q).mappings().all()
        organization = c.execute(organization_q).mappings().one()
    return [organization, *departments]


# Negative control: each wrong prefix leaves a signature the canonical one cannot.
#   inverted_pools  - the department pool is awaited FIRST, so the organization pool is
#                     still free and a probe acquires it (None instead of 55P03).
#   no_pool_locks   - no pool row is locked at all, so the caller runs straight through
#                     to the personal budget and holds that instead (55P03 there too).
# The canonical signature is exactly {organization_pool: 55P03, personal_budget: None},
# and neither perturbation can produce it.
CANONICAL_PREFIX = {"organization_pool": "55P03", "personal_budget": None}
WRONG_PREFIX_SIGNATURES = {
    "inverted_pools": {"organization_pool": None, "personal_budget": None},
    "no_pool_locks": {"organization_pool": "55P03", "personal_budget": "55P03"},
}


@pytest.mark.parametrize("perturbation", sorted(WRONG_PREFIX_SIGNATURES))
def test_CONTROL_wrong_prefix_is_rejected(administration, monkeypatch, perturbation):
    import app.billing.budgets as budgets

    t = administration
    dept = department(t, t["alice"])
    t["administration"].set_shared_budget(t["org_admin"], dept, None, 0)
    pools = _pool_rows(t)
    monkeypatch.setattr(
        budgets,
        "ensure",
        partial(
            _control_ensure,
            lock_pools=perturbation != "no_pool_locks",
            organization_first=perturbation != "inverted_pools",
        ),
    )
    item = private_session(t, t["alice"])
    callback = partial(create, t, t["alice"], item)
    observed, _ = _observed_prefix(t, monkeypatch, pools[dept]["id"], callback)
    assert observed == WRONG_PREFIX_SIGNATURES[perturbation]
    # The point of the control: a wrong prefix cannot look like the production one.
    assert observed != CANONICAL_PREFIX


@pytest.mark.parametrize("path", ["admission", "settlement"])
def test_pool_prefix_owns_the_organization_pool_before_department_and_personal_rows(administration, monkeypatch, path):
    """The blocked caller must already hold the organization pool and not yet the personal budget."""
    t = administration
    dept = department(t, t["alice"])
    # Both pool rows must exist and be committed, otherwise the caller would lock its own new row.
    t["administration"].set_shared_budget(t["org_admin"], dept, None, 0)
    pools = _pool_rows(t)
    if path == "admission":
        item = private_session(t, t["alice"])
        callback = partial(create, t, t["alice"], item)
    else:
        run = create(t, t["alice"], private_session(t, t["alice"]))
        callback = partial(t["service"].cancel_run, t["alice"], run["run_id"])
    observed, result = _observed_prefix(t, monkeypatch, pools[dept]["id"], callback)
    # 55P03 proves the organization pool is already held while the department pool is awaited;
    # None proves the personal budget is still untouched, i.e. pools come first.
    assert observed == CANONICAL_PREFIX
    settled = _pool_rows(t)
    if path == "admission":
        assert result["state"] == "queued"
        assert settled[None]["reserved"] == settled[dept]["reserved"] == Decimal("0.1")
    else:
        assert result["state"] == "cancelled"
        assert settled[None]["reserved"] == settled[dept]["reserved"] == Decimal(0)
    assert_projection(t)


def test_cross_department_admissions_serialize_on_the_shared_organization_pool(administration):
    """Two capped-but-disjoint departments still contend for the last organization allowance."""
    t = administration
    left, right = department(t, t["alice"]), department(t, t["bob"])
    for scope in (left, right):
        t["administration"].set_shared_budget(t["org_admin"], scope, Decimal("1"), 0)
    t["administration"].set_shared_budget(t["org_admin"], None, Decimal("0.1"), 0)
    actors = [(t["alice"], private_session(t, t["alice"])), (t["bob"], private_session(t, t["bob"]))]
    result = _race(t, actors)
    assert sum(isinstance(item, dict) for item in result) == 1
    assert "SHARED_BUDGET_EXCEEDED" in result
    assert not [item for item in result if isinstance(item, str) and item.startswith("sqlstate:")]
    pools = _pool_rows(t)
    # The single admitted charge constrains the organization AND its own department;
    # the overlapping projections are never summed into 0.2.
    assert pools[None]["reserved"] == Decimal("0.1")
    assert sum(pools[scope]["reserved"] for scope in (left, right) if scope in pools) == Decimal("0.1")
    assert len(rows(t, s.runs)) == len(rows(t, s.jobs)) == 1
    assert_projection(t)


def test_multi_department_member_race_takes_every_binding_or_none(administration):
    """A three-department member racing a one-department member leaves no partial admission."""
    t = administration
    first, shared, third = (department(t, t["alice"]) for _ in range(3))
    with t["admin"].begin() as c:
        c.execute(
            s.department_memberships.insert().values(org_id=t["org"], department_id=shared, user_id=t["bob"].user_id)
        )
    t["administration"].set_shared_budget(t["org_admin"], shared, Decimal("0.1"), 0)
    actors = [(t["alice"], private_session(t, t["alice"])), (t["bob"], private_session(t, t["bob"]))]
    result = _race(t, actors)
    assert sum(isinstance(item, dict) for item in result) == 1
    assert "SHARED_BUDGET_EXCEEDED" in result
    assert not [item for item in result if isinstance(item, str) and item.startswith("sqlstate:")]
    runs, allocations = rows(t, s.runs), rows(t, s.budget_allocations)
    assert len(runs) == 1 and {row["run_id"] for row in allocations} == {runs[0]["id"]}
    # Alice binds organization + three departments, Bob organization + the shared one.
    assert len(allocations) == (4 if isinstance(result[0], dict) else 2)
    assert len(allocations) == len({row["pool_id"] for row in allocations})
    pools = _pool_rows(t)
    assert pools[None]["reserved"] == pools[shared]["reserved"] == Decimal("0.1")
    if not isinstance(result[0], dict):
        # The refused multi-department actor left nothing behind in its other scopes.
        assert all(pools[scope]["reserved"] == Decimal(0) for scope in (first, third) if scope in pools)
    assert_projection(t)


@pytest.mark.parametrize("order", ["canonical", "inverted"])
def test_only_the_inverted_pool_order_can_deadlock_two_concurrent_prefixes(administration, order):
    """Negative control: the same two rows deadlock under the wrong order and cannot under production order."""
    t = administration
    dept = department(t, t["alice"])
    t["administration"].set_shared_budget(t["org_admin"], dept, None, 0)
    pools = _pool_rows(t)
    organization, department_pool = pools[None]["id"], pools[dept]["id"]
    canonical = [organization, department_pool]
    sequences = [canonical, canonical if order == "canonical" else [department_pool, organization]]
    # Under the canonical order no peer can hold a different first pool lock, so the
    # gate must break; under the inverted order both hold one and then want the other.
    gate = 1.5 if order == "canonical" else 5
    barrier = Barrier(2)

    def act(index):
        try:
            with t["db"].transaction(t["alice"]) as c:
                _lock_pool(c, t["org"], sequences[index][0])
                barrier.wait(timeout=gate)
                _lock_pool(c, t["org"], sequences[index][1])
            return "committed"
        except BrokenBarrierError:
            return "barrier-broken"
        except OperationalError as error:
            return _sqlstate(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        result = list(executor.map(act, (0, 1)))
    if order == "inverted":
        assert "40P01" in result, result
    else:
        assert "40P01" not in result and "barrier-broken" in result, result


def test_admission_and_settlement_overlap_without_deadlock_or_lock_timeout(administration):
    """Real for_actor/reserve admission against real lock_subject/change settlement on shared pools."""
    t = administration
    dept = department(t, t["alice"], t["bob"])
    t["administration"].set_shared_budget(t["org_admin"], dept, None, 0)
    observed = []
    for _ in range(3):
        run = create(t, t["alice"], private_session(t, t["alice"]))
        item = private_session(t, t["bob"])
        barrier = Barrier(2)

        def settle(run_id=run["run_id"]):
            barrier.wait(timeout=10)
            try:
                return t["service"].cancel_run(t["alice"], run_id)["state"]
            except PlatformError as error:
                return error.code
            except OperationalError as error:
                # 40P01 and connection failures are never swallowed as "busy" anywhere in this path.
                return "sqlstate:" + _sqlstate(error)

        def admit(session_item=item):
            barrier.wait(timeout=10)
            try:
                return create(t, t["bob"], session_item)["state"]
            except PlatformError as error:
                return error.code
            except OperationalError as error:
                return "sqlstate:" + _sqlstate(error)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(settle), executor.submit(admit)]
            observed.append(sorted(future.result(timeout=30) for future in futures))
    assert observed == [["cancelled", "queued"]] * 3
    pools = _pool_rows(t)
    assert pools[None]["reserved"] == pools[dept]["reserved"] == Decimal("0.3")
    assert_projection(t)
