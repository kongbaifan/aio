"""Shared budget projections, preserving existing personal charges and outstanding holds.

Run in a maintenance window with old writers stopped. Current department membership
is used ONLY for outstanding migration holds, never to invent historical attribution.
"""

from collections import defaultdict
from decimal import Decimal
from uuid import uuid4

from alembic import op
from sqlalchemy import func, insert, select, update
from app.db import schema_v13 as s
from app.db.migration_guard import require_unblinded_tenant_read

revision = "0013_shared_budgets"
down_revision = "0012_skill_imports"
branch_labels = None
depends_on = None

BLINDED = (
    "would record zero opening consumption for every organization and leave every outstanding "
    "hold without any shared charge scope"
)


def _reconcile(c, organizations, expected_consumed, expected_holds):
    """Prove the projection that was WRITTEN reconciles against the source facts.

    The pre-flight guard proves this identity MAY read every row; these checks prove it DID.
    Each one is compared against a total accumulated from the source tables during the loop,
    so a partially visible read cannot satisfy them by matching one empty set against another.
    """
    pools = c.execute(select(s.budget_pools)).mappings().all()
    organization_pools = {row["org_id"]: row for row in pools if row["department_id"] is None}
    if sorted(map(str, organization_pools)) != sorted(map(str, organizations)):
        raise RuntimeError(
            "Shared budget projection did not record exactly one organization pool per organization; "
            "refusing to commit a partial projection of existing charge facts"
        )
    # Independent of the loop's own reads: every organization that exists must be projected.
    # This bites when the source read itself was filtered, where projected == read == empty.
    count = c.execute(select(func.count()).select_from(s.organizations)).scalar_one()
    if count != len(organization_pools):
        raise RuntimeError(
            f"Shared budget projection recorded {len(organization_pools)} organization pools for {count} "
            "organizations; refusing to commit a projection that silently omits existing charge facts"
        )
    opening = sum((row["opening_consumed"] for row in organization_pools.values()), Decimal(0))
    consumed = c.execute(select(func.coalesce(func.sum(s.budgets.c.consumed), 0))).scalar_one()
    if opening != consumed or opening != expected_consumed:
        raise RuntimeError(
            f"Shared budget projection recorded {opening} opening consumption against {consumed} of existing "
            f"personal consumption ({expected_consumed} observed while projecting); refusing to commit a "
            "projection that would silently forgive or duplicate spend already charged"
        )
    # Every outstanding hold must carry a charge scope on its organization pool, at its original
    # amount. A pool projected without its allocations leaves holds unscoped and uncapped.
    allocations = defaultdict(lambda: defaultdict(lambda: Decimal(0)))
    for row in c.execute(select(s.budget_allocations)).mappings():
        if row["origin"] != "migration_hold":
            raise RuntimeError("Shared budget projection recorded a non-migration allocation")
        subject = ("run", row["run_id"]) if row["run_id"] is not None else ("embedding", row["embedding_call_id"])
        allocations[row["pool_id"]][subject] += row["reserved"]
    for org, pool in organization_pools.items():
        scoped, holds = allocations[pool["id"]], expected_holds[org]
        if scoped != holds:
            raise RuntimeError(
                f"Shared budget projection scoped {len(scoped)} outstanding holds onto the organization pool "
                f"for {org} but {len(holds)} were observed in the existing charge facts; refusing to commit a "
                "projection that would leave an outstanding hold with no shared charge scope"
            )
        if pool["reserved"] != sum(holds.values(), Decimal(0)):
            raise RuntimeError(
                f"Shared budget projection recorded {pool['reserved']} reserved on the organization pool for "
                f"{org} against {sum(holds.values(), Decimal(0))} of outstanding holds; refusing to commit"
            )
    for row in pools:
        if row["department_id"] is None:
            continue
        scoped = allocations[row["id"]]
        # A department pool with no allocation is an invented scope that would cap real spend.
        if not scoped:
            raise RuntimeError(
                f"Shared budget projection created a department pool {row['department_id']} with no allocation; "
                "refusing to commit a scope that no existing charge fact supports"
            )
        if row["reserved"] != sum(scoped.values(), Decimal(0)):
            raise RuntimeError(
                f"Shared budget projection recorded {row['reserved']} reserved on the department pool for "
                f"{row['department_id']} against {sum(scoped.values(), Decimal(0))} of scoped holds; refusing to "
                "commit a projection whose department scope does not match its own allocations"
            )
        # Department scope exists only for outstanding holds; v12 recorded no departmental history.
        if row["opening_consumed"] != 0 or row["consumed"] != 0:
            raise RuntimeError(
                f"Shared budget projection recorded {row['consumed']} consumption on the department pool for "
                f"{row['department_id']}; refusing to invent historical departmental attribution"
            )


def upgrade():
    c = op.get_bind()
    require_unblinded_tenant_read(c, BLINDED)
    for table in (s.budget_pools, s.budget_allocations):
        table.create(c)
        predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
        op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')
    organizations = c.execute(select(s.organizations.c.id)).scalars().all()
    expected_consumed, expected_holds = Decimal(0), {}
    for org in organizations:
        budgets = c.execute(select(s.budgets).where(s.budgets.c.org_id == org)).mappings().all()
        if any(budget["currency"] != "USD" for budget in budgets):
            raise RuntimeError("Shared budget migration does not convert non-USD charge facts")
        holds = []
        for row in c.execute(
            select(s.reservations).where(
                s.reservations.c.org_id == org, s.reservations.c.state.in_(["reserved", "held_unknown"])
            )
        ).mappings():
            holds.append((row["budget_id"], row["amount"], {"run_id": row["run_id"]}))
        for row in c.execute(
            select(s.embedding_calls).where(
                s.embedding_calls.c.org_id == org,
                s.embedding_calls.c.standalone_reserved.is_(True),
                (s.embedding_calls.c.actual_charge.is_(None) | (s.embedding_calls.c.state == "not_sent")),
            )
        ).mappings():
            holds.append(
                (
                    row["budget_id"],
                    Decimal(0) if row["state"] == "not_sent" else row["max_charge"],
                    {"embedding_call_id": row["id"]},
                )
            )
        totals = defaultdict(lambda: Decimal(0))
        for budget_id, amount, _ in holds:
            totals[budget_id] += amount
        if any(budget["reserved"] != totals[budget["id"]] for budget in budgets):
            raise RuntimeError("Shared budget migration requires reconciliation of existing unmatched reservations")
        consumed = sum((row["consumed"] for row in budgets), Decimal(0))
        expected_consumed += consumed
        # Accumulated exactly the way _reconcile accumulates the rows it wrote, so the two
        # are directly comparable: same subject labels, same per-subject summation.
        expected_holds[org] = observed = defaultdict(lambda: Decimal(0))
        for _, amount, subject in holds:
            kind = "run" if "run_id" in subject else "embedding"
            observed[(kind, next(iter(subject.values())))] += amount
        organization_pool = uuid4()
        c.execute(
            insert(s.budget_pools).values(
                id=organization_pool, org_id=org, consumed=consumed, opening_consumed=consumed
            )
        )
        departments = {}
        owners = {row["id"]: row["owner_id"] for row in budgets}
        for budget_id, amount, subject in holds:
            ids = [organization_pool]
            memberships = c.execute(
                select(s.department_memberships.c.department_id)
                .join(
                    s.departments,
                    (s.departments.c.org_id == s.department_memberships.c.org_id)
                    & (s.departments.c.id == s.department_memberships.c.department_id),
                )
                .where(
                    s.department_memberships.c.org_id == org,
                    s.department_memberships.c.user_id == owners[budget_id],
                    s.departments.c.active.is_(True),
                )
            ).scalars()
            for department in memberships:
                if department not in departments:
                    departments[department] = uuid4()
                    c.execute(
                        insert(s.budget_pools).values(id=departments[department], org_id=org, department_id=department)
                    )
                ids.append(departments[department])
            for pool in ids:
                c.execute(
                    insert(s.budget_allocations).values(
                        id=uuid4(), org_id=org, pool_id=pool, reserved=amount, origin="migration_hold", **subject
                    )
                )
                c.execute(
                    update(s.budget_pools)
                    .where(s.budget_pools.c.id == pool)
                    .values(reserved=s.budget_pools.c.reserved + amount)
                )
    _reconcile(c, organizations, expected_consumed, expected_holds)


def downgrade():
    raise RuntimeError("Destructive budget projection downgrade is not supported; retain all charge facts")
