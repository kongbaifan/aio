"""Short-transaction shared budget locks, fixed scope bindings and exact projections.

Callers establish organization/resource authority BEFORE this L3 lock prefix, and
take the personal budget/Run/receipt locks AFTER it. No external I/O occurs here.
"""

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import case, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import schema as s
from ..platform_errors import PlatformError

ZERO = Decimal(0)
# NUMERIC(20,6) pool/allocation columns, narrowed to the management contract's 16 significant digits.
MAX_AMOUNT = Decimal(10) ** 10


def _ordered(query):
    return query.order_by(case((s.budget_pools.c.department_id.is_(None), 0), else_=1), s.budget_pools.c.id)


def _amount(value):
    # NUMERIC would round a finer value into the column instead of refusing it, so reject here.
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value < 0
        or value > MAX_AMOUNT
        or value.as_tuple().exponent < -6
    ):
        raise PlatformError("INVALID_REQUEST", "Shared charge requires a finite exact amount within bounds", 422)
    return value


def _subject(org_id, *, run_id=None, embedding_call_id=None):
    if (run_id is None) == (embedding_call_id is None):
        raise ValueError("Exactly one fixed charge subject is required")
    return (
        s.budget_allocations.c.org_id == org_id,
        s.budget_allocations.c.run_id == run_id
        if run_id is not None
        else s.budget_allocations.c.embedding_call_id == embedding_call_id,
    )


def ensure(c, org_id, department_ids=()):
    # Organization scope is always acquired first, including when no extra cap is enabled.
    c.execute(pg_insert(s.budget_pools).values(id=uuid4(), org_id=org_id).on_conflict_do_nothing())
    organization = (
        c.execute(
            select(s.budget_pools)
            .where(s.budget_pools.c.org_id == org_id, s.budget_pools.c.department_id.is_(None))
            .with_for_update()
        )
        .mappings()
        .one()
    )
    ids = sorted(set(department_ids))
    for department_id in ids:
        c.execute(
            pg_insert(s.budget_pools)
            .values(id=uuid4(), org_id=org_id, department_id=department_id)
            .on_conflict_do_nothing()
        )
    departments = (
        c.execute(
            _ordered(
                select(s.budget_pools).where(s.budget_pools.c.org_id == org_id, s.budget_pools.c.department_id.in_(ids))
            ).with_for_update()
        )
        .mappings()
        .all()
    )
    return [organization, *departments]


def for_actor(c, principal):
    ids = c.execute(
        select(s.department_memberships.c.department_id)
        .join(
            s.departments,
            (s.departments.c.org_id == s.department_memberships.c.org_id)
            & (s.departments.c.id == s.department_memberships.c.department_id),
        )
        .where(
            s.department_memberships.c.org_id == principal.org_id,
            s.department_memberships.c.user_id == principal.user_id,
            s.departments.c.active.is_(True),
        )
    ).scalars()
    return ensure(c, principal.org_id, ids)


def lock_subject(c, org_id, *, run_id=None, embedding_call_id=None):
    # Bindings are immutable; locating them does not take a later-layer lock.
    ids = select(s.budget_allocations.c.pool_id).where(
        *_subject(org_id, run_id=run_id, embedding_call_id=embedding_call_id)
    )
    return (
        c.execute(
            _ordered(
                select(s.budget_pools).where(s.budget_pools.c.org_id == org_id, s.budget_pools.c.id.in_(ids))
            ).with_for_update()
        )
        .mappings()
        .all()
    )


def check(pools, additional=ZERO):
    if not pools:
        raise PlatformError("BUDGET_INTEGRITY_ERROR", "Paid operation has no fixed shared charge scope", 409)
    for pool in pools:
        if pool["hard_limit"] is not None and pool["reserved"] + pool["consumed"] + additional > pool["hard_limit"]:
            scope = "Department" if pool["department_id"] else "Organization"
            raise PlatformError("SHARED_BUDGET_EXCEEDED", f"{scope} budget cannot admit another paid operation", 429)


def reserve(c, org_id, pools, amount, *, run_id=None, embedding_call_id=None):
    _subject(org_id, run_id=run_id, embedding_call_id=embedding_call_id)
    amount = _amount(amount)
    if not pools or any(pool["org_id"] != org_id for pool in pools):
        raise PlatformError("BUDGET_INTEGRITY_ERROR", "Charge scopes are not bound", 409)
    check(pools, amount)
    for pool in pools:
        c.execute(
            insert(s.budget_allocations).values(
                org_id=org_id,
                id=uuid4(),
                pool_id=pool["id"],
                run_id=run_id,
                embedding_call_id=embedding_call_id,
                reserved=amount,
            )
        )
        c.execute(
            update(s.budget_pools)
            .where(s.budget_pools.c.org_id == org_id, s.budget_pools.c.id == pool["id"])
            .values(reserved=s.budget_pools.c.reserved + amount)
        )


def change(c, org_id, *, release=ZERO, charge=ZERO, add=ZERO, run_id=None, embedding_call_id=None):
    """Project an already-fenced personal accounting transition, not another usage fact."""
    for value in (release, charge, add):
        _amount(value)
    # Take the canonical pool prefix here rather than trusting every caller to hold it:
    # raw allocation pool_id order can invert organization-before-department.
    pools = [pool["id"] for pool in lock_subject(c, org_id, run_id=run_id, embedding_call_id=embedding_call_id)]
    rows = (
        c.execute(
            select(s.budget_allocations)
            .where(*_subject(org_id, run_id=run_id, embedding_call_id=embedding_call_id))
            .with_for_update()
        )
        .mappings()
        .all()
    )
    if not rows or any(row["reserved"] < release for row in rows):
        raise PlatformError("BUDGET_INTEGRITY_ERROR", "Shared charge hold requires reconciliation", 409)
    order = {pool: index for index, pool in enumerate(pools)}
    if any(row["pool_id"] not in order for row in rows):
        raise PlatformError("BUDGET_INTEGRITY_ERROR", "Shared charge scope is not locked", 409)
    for row in sorted(rows, key=lambda row: order[row["pool_id"]]):
        changed = c.execute(
            update(s.budget_pools)
            .where(
                s.budget_pools.c.org_id == org_id,
                s.budget_pools.c.id == row["pool_id"],
                s.budget_pools.c.reserved >= release,
            )
            .values(reserved=s.budget_pools.c.reserved - release + add, consumed=s.budget_pools.c.consumed + charge)
        ).rowcount
        if changed != 1:
            raise PlatformError("BUDGET_INTEGRITY_ERROR", "Shared pool hold requires reconciliation", 409)
        c.execute(
            update(s.budget_allocations)
            .where(s.budget_allocations.c.org_id == org_id, s.budget_allocations.c.id == row["id"])
            .values(reserved=row["reserved"] - release + add, consumed=row["consumed"] + charge)
        )


def embedding_subject(call):
    return {"run_id": call["run_id"]} if call["run_id"] else {"embedding_call_id": call["id"]}
