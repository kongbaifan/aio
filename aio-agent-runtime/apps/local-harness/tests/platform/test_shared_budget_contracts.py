from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Select, Update

from app.admin.contracts import SharedBudgetUpdate
from app.billing import budgets
from app.db import schema_v12, schema_v13
from app.platform_errors import PlatformError

# 冻结 v12 快照的表名集合：仅比较数量无法发现改名，而改名会让已发布的 0012
# 迁移与该快照不再对应。新增作用域只允许出现在 v13。
V12_TABLES = (
    "aio_agent_versions",
    "aio_approvals",
    "aio_artifacts",
    "aio_audit_events",
    "aio_auth_sessions",
    "aio_budgets",
    "aio_checkpoints",
    "aio_department_grants",
    "aio_department_memberships",
    "aio_departments",
    "aio_dispatches",
    "aio_embedding_calls",
    "aio_embedding_ledger",
    "aio_embedding_models",
    "aio_grants",
    "aio_idempotency_keys",
    "aio_invocations",
    "aio_jobs",
    "aio_knowledge_bases",
    "aio_knowledge_chunks",
    "aio_knowledge_citations",
    "aio_knowledge_documents",
    "aio_knowledge_jobs",
    "aio_knowledge_queries",
    "aio_knowledge_versions",
    "aio_login_attempts",
    "aio_manifest_snapshots",
    "aio_mcp_bindings",
    "aio_mcp_connections",
    "aio_mcp_discoveries",
    "aio_mcp_oauth_attempts",
    "aio_mcp_servers",
    "aio_mcp_stdio_leases",
    "aio_memberships",
    "aio_messages",
    "aio_model_calls",
    "aio_model_configs",
    "aio_organizations",
    "aio_outbox",
    "aio_projects",
    "aio_reservations",
    "aio_resources",
    "aio_run_events",
    "aio_run_steps",
    "aio_run_teams",
    "aio_runs",
    "aio_sandbox_leases",
    "aio_sessions",
    "aio_skill_imports",
    "aio_skill_validation_jobs",
    "aio_skill_versions",
    "aio_tool_versions",
    "aio_upload_slots",
    "aio_usage_ledger",
    "aio_users",
    "aio_workspace_blockers",
    "aio_workspace_checkpoints",
    "aio_workspace_leases",
    "aio_workspace_versions",
)

ORG = uuid4()


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-0.1", "0.0000001", "1000000.000001"])
def test_budget_limits_reject_nonfinite_overflow_and_extra_precision(value):
    with pytest.raises(ValidationError):
        SharedBudgetUpdate(expected_revision=0, hard_limit=value)


@pytest.mark.parametrize("value", ["0", "0.000001", "1000000", None])
def test_budget_limits_accept_exact_boundary_and_explicit_cap_removal(value):
    body = SharedBudgetUpdate(expected_revision=0, hard_limit=value)
    assert body.hard_limit == (Decimal(value) if value is not None else None)


def test_limit_revision_is_required_strict_and_cannot_mutate_projection_fields():
    for body in (
        {"hard_limit": "1"},
        {"expected_revision": True, "hard_limit": "1"},
        {"expected_revision": 0},
        {"expected_revision": 0, "hard_limit": "1", "consumed": 0},
    ):
        with pytest.raises(ValidationError):
            SharedBudgetUpdate(**body)


class _Recorder:
    """Collect the statements a budget helper issues, without a database.

    Lock order and amount admission are decided in Python before any SQL runs, so
    they are assertable here; real projection/concurrency stays in the PG suite.
    """

    def __init__(self, allocations=(), pools=()):
        self.allocations, self.pools, self.statements = list(allocations), list(pools), []

    def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return _Result(self, statement)

    def table(self, statement):
        if isinstance(statement, Update):
            return statement.table.name
        if isinstance(statement, Select):
            return statement.get_final_froms()[0].name
        return getattr(getattr(statement, "table", None), "name", None)

    @property
    def locked(self):
        # Ordered names of the tables this call actually took a FOR UPDATE row lock on.
        return [
            self.table(item)
            for item in self.statements
            if isinstance(item, Select) and item._for_update_arg is not None
        ]

    @property
    def written(self):
        return [self.table(item) for item in self.statements if isinstance(item, Update)]

    def first_lock(self, name):
        """Absolute statement position of the first row lock on `name`, or None."""
        for position, item in enumerate(self.statements):
            if isinstance(item, Select) and item._for_update_arg is not None and self.table(item) == name:
                return position
        return None

    def first_write(self, name):
        for position, item in enumerate(self.statements):
            if isinstance(item, Update) and self.table(item) == name:
                return position
        return None


class _Result:
    def __init__(self, recorder, statement):
        self.recorder, self.statement = recorder, statement
        self.rowcount = 1

    def mappings(self):
        return self

    def all(self):
        name = self.recorder.table(self.statement)
        return self.recorder.allocations if name == "aio_budget_allocations" else self.recorder.pools

    def one(self):
        return self.all()[0]

    def first(self):
        rows = self.all()
        return rows[0] if rows else None

    def scalars(self):
        return self

    def _pool_ids(self):
        return [pool["id"] for pool in self.recorder.pools]


def _pool(department_id=None, pool_id=None, **extra):
    return {
        "org_id": ORG,
        "id": pool_id or uuid4(),
        "department_id": department_id,
        "hard_limit": None,
        "reserved": Decimal(0),
        "consumed": Decimal(0),
        **extra,
    }


def _allocation(pool_id, run_id, reserved=Decimal("1.000000")):
    return {
        "org_id": ORG,
        "id": uuid4(),
        "pool_id": pool_id,
        "run_id": run_id,
        "embedding_call_id": None,
        "reserved": reserved,
        "consumed": Decimal(0),
    }


def _inverted_pools():
    """An organization pool whose UUID sorts AFTER its department pool's UUID.

    Raw `pool_id` order would then visit the department first, inverting the
    canonical organization-first prefix that `ensure`/`lock_subject` establish.
    """
    while True:
        organization, department = uuid4(), uuid4()
        if str(department) < str(organization):
            return _pool(pool_id=organization), _pool(uuid4(), pool_id=department)


def test_change_locks_the_pool_prefix_before_it_updates_any_pool_row():
    """`change` must not reach the caps table without having taken a pool row lock.

    Relying on callers to hold the prefix is a lock-order inversion waiting for the
    first caller that forgets it.
    """
    organization, department = _inverted_pools()
    run_id = uuid4()
    c = _Recorder(
        allocations=[_allocation(department["id"], run_id), _allocation(organization["id"], run_id)],
        pools=[organization, department],
    )
    budgets.change(c, ORG, run_id=run_id, release=Decimal("1"))
    lock, write = c.first_lock("aio_budget_pools"), c.first_write("aio_budget_pools")
    assert lock is not None, "change() updated pool caps without ever locking a pool row"
    # Compare absolute statement positions: separate lock/write lists cannot show ordering.
    assert lock < write, "the pool row must be locked before it is updated"


def test_change_projects_pools_in_canonical_organization_first_order():
    """Raw pool_id order can disagree with the organization-first comparator."""
    organization, department = _inverted_pools()
    run_id = uuid4()
    c = _Recorder(
        allocations=[_allocation(department["id"], run_id), _allocation(organization["id"], run_id)],
        pools=[organization, department],
    )
    budgets.change(c, ORG, run_id=run_id, release=Decimal("1"))
    touched = [
        item.compile().params["id_1"]
        for item in c.statements
        if isinstance(item, Update) and item.table.name == "aio_budget_pools"
    ]
    assert touched == [organization["id"], department["id"]], "pool updates must run the organization pool first"


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity"])
def test_reserve_refuses_nonfinite_amounts_instead_of_binding_them(amount):
    """NUMERIC(20,6) has no NaN/Infinity money semantics; refuse before the insert."""
    pools = [_pool()]
    c = _Recorder(pools=pools)
    with pytest.raises(PlatformError) as error:
        budgets.reserve(c, ORG, pools, Decimal(amount), run_id=uuid4())
    assert error.value.status == 422
    assert not c.statements, "a rejected amount must not reach the database"


@pytest.mark.parametrize("amount", ["0.0000001", "0.1234567", "1E-7", "1.0000001"])
def test_reserve_refuses_over_precise_amounts_postgres_would_silently_round(amount):
    """A 7th decimal is silently rounded into NUMERIC(20,6); for money that must be refused."""
    pools = [_pool()]
    c = _Recorder(pools=pools)
    with pytest.raises(PlatformError) as error:
        budgets.reserve(c, ORG, pools, Decimal(amount), run_id=uuid4())
    assert error.value.status == 422
    assert not c.statements


def test_reserve_refuses_a_negative_amount():
    pools = [_pool()]
    c = _Recorder(pools=pools)
    with pytest.raises(PlatformError):
        budgets.reserve(c, ORG, pools, Decimal("-0.000001"), run_id=uuid4())
    assert not c.statements


@pytest.mark.parametrize("amount", ["0", "0.002", "0.020000", "0.1", "0.100000", "1.000000"])
def test_reserve_still_admits_the_exact_amounts_existing_callers_pass(amount):
    """Guard against over-tightening: these are the live admission/embedding amounts."""
    pools = [_pool()]
    c = _Recorder(pools=pools)
    budgets.reserve(c, ORG, pools, Decimal(amount), run_id=uuid4())
    assert c.written == ["aio_budget_pools"]


def test_v12_snapshot_remains_immutable_and_new_scopes_are_tenant_tables():
    assert sorted(schema_v12.metadata.tables) == sorted(V12_TABLES)
    assert len(schema_v12.metadata.tables) == len(V12_TABLES) == 59
    assert sorted(schema_v13.metadata.tables) == sorted((*V12_TABLES, "aio_budget_pools", "aio_budget_allocations"))
    assert len(schema_v13.metadata.tables) == 61
    for table in (schema_v13.budget_pools, schema_v13.budget_allocations):
        assert table in schema_v13.TENANT_TABLES
        assert table.name not in schema_v13.BOOTSTRAP_TABLES
        assert table.name not in schema_v12.metadata.tables
        # 新作用域必须带 org_id，迁移里的 RLS 谓词正是按该列比较。
        assert "org_id" in table.c
