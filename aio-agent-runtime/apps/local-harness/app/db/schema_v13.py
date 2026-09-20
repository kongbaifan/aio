"""Schema v13: shared budget projections and immutable charge-scope bindings."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    text,
)

from . import schema_v12 as v12

metadata = MetaData(naming_convention=v12.metadata.naming_convention)
for original in v12.metadata.tables.values():
    original.to_metadata(metadata)
for name, original in vars(v12).items():
    if isinstance(original, Table):
        globals()[name] = metadata.tables[original.name]

budget_pools = Table(
    "aio_budget_pools",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("department_id", Uuid),
    Column("currency", String(3), nullable=False, server_default="USD"),
    Column("hard_limit", Numeric(20, 6)),
    Column("reserved", Numeric(20, 6), nullable=False, server_default="0"),
    Column("consumed", Numeric(20, 6), nullable=False, server_default="0"),
    Column("opening_consumed", Numeric(20, 6), nullable=False, server_default="0"),
    Column("revision", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    UniqueConstraint("org_id", "id"),
    UniqueConstraint("org_id", "department_id", "currency"),
    ForeignKeyConstraint(["org_id"], ["aio_organizations.id"]),
    ForeignKeyConstraint(["org_id", "department_id"], ["aio_departments.org_id", "aio_departments.id"]),
    CheckConstraint("currency = 'USD'", name="currency"),
    CheckConstraint("hard_limit IS NULL OR hard_limit >= 0", name="limit"),
    CheckConstraint(
        "reserved >= 0 AND consumed >= opening_consumed AND opening_consumed >= 0 AND revision >= 0", name="amounts"
    ),
)
Index(
    "uq_aio_budget_pool_organization",
    budget_pools.c.org_id,
    budget_pools.c.currency,
    unique=True,
    postgresql_where=budget_pools.c.department_id.is_(None),
)

budget_allocations = Table(
    "aio_budget_allocations",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("pool_id", Uuid, nullable=False),
    Column("run_id", Uuid),
    Column("embedding_call_id", Uuid),
    Column("reserved", Numeric(20, 6), nullable=False),
    Column("consumed", Numeric(20, 6), nullable=False, server_default="0"),
    Column("origin", String(24), nullable=False, server_default="admission"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    UniqueConstraint("org_id", "id"),
    UniqueConstraint("org_id", "pool_id", "run_id"),
    UniqueConstraint("org_id", "pool_id", "embedding_call_id"),
    ForeignKeyConstraint(["org_id", "pool_id"], ["aio_budget_pools.org_id", "aio_budget_pools.id"]),
    ForeignKeyConstraint(["org_id", "run_id"], ["aio_runs.org_id", "aio_runs.id"]),
    ForeignKeyConstraint(["org_id", "embedding_call_id"], ["aio_embedding_calls.org_id", "aio_embedding_calls.id"]),
    CheckConstraint("(run_id IS NULL) <> (embedding_call_id IS NULL)", name="subject"),
    CheckConstraint("reserved >= 0 AND consumed >= 0", name="amounts"),
    CheckConstraint("origin IN ('admission', 'migration_hold')", name="origin"),
)
Index("ix_aio_budget_allocation_run", budget_allocations.c.org_id, budget_allocations.c.run_id)
Index("ix_aio_budget_allocation_embedding", budget_allocations.c.org_id, budget_allocations.c.embedding_call_id)

BOOTSTRAP_TABLES = v12.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
