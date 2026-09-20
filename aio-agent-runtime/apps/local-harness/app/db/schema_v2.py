"""Schema snapshot v2. v1 is kept immutable for deterministic migrations."""

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.dialects.postgresql import JSONB

from . import schema_v1 as v1

metadata = MetaData(naming_convention=v1.metadata.naming_convention)
for original in v1.metadata.tables.values():
    original.to_metadata(metadata)

organizations = metadata.tables["aio_organizations"]
users = metadata.tables["aio_users"]
memberships = metadata.tables["aio_memberships"]
login_attempts = metadata.tables["aio_login_attempts"]
auth_sessions = metadata.tables["aio_auth_sessions"]
resources = metadata.tables["aio_resources"]
grants = metadata.tables["aio_grants"]
projects = metadata.tables["aio_projects"]
agent_versions = metadata.tables["aio_agent_versions"]
sessions = metadata.tables["aio_sessions"]
budgets = metadata.tables["aio_budgets"]
manifest_snapshots = metadata.tables["aio_manifest_snapshots"]
runs = metadata.tables["aio_runs"]
messages = metadata.tables["aio_messages"]
jobs = metadata.tables["aio_jobs"]
events = metadata.tables["aio_run_events"]
checkpoints = metadata.tables["aio_checkpoints"]
invocations = metadata.tables["aio_invocations"]
approvals = metadata.tables["aio_approvals"]
dispatches = metadata.tables["aio_dispatches"]
idempotency_keys = metadata.tables["aio_idempotency_keys"]
reservations = metadata.tables["aio_reservations"]
ledger = metadata.tables["aio_usage_ledger"]
sandbox_leases = metadata.tables["aio_sandbox_leases"]
blockers = metadata.tables["aio_workspace_blockers"]
outbox = metadata.tables["aio_outbox"]
audit = metadata.tables["aio_audit_events"]

# Columns added by 0002. They are not added to schema_v1.
runs.append_column(Column("checkpoint_seq", BigInteger, nullable=False, server_default="0"))
jobs.append_column(Column("attempt_count", Integer, nullable=False, server_default="0"))
jobs.append_column(Column("recovery_count", Integer, nullable=False, server_default="0"))
invocations.append_column(Column("arguments", JSONB))
invocations.append_column(Column("definition_digest", String(64)))
dispatches.append_column(Column("operation_key", String(128)))
dispatches.append_column(Column("sent_at", DateTime(timezone=True)))
dispatches.append_column(Column("finished_at", DateTime(timezone=True)))
dispatches.append_column(Column("outcome_digest", String(64)))
blockers.append_column(Column("resolved_by", Uuid))
blockers.append_column(Column("resolution", JSONB))


def identity_columns():
    return [
        Column("org_id", Uuid, nullable=False),
        Column("id", Uuid, primary_key=True),
        ForeignKeyConstraint(["org_id"], ["aio_organizations.id"]),
        UniqueConstraint("org_id", "id"),
    ]


def tenant_fk(column, target):
    return ForeignKeyConstraint(["org_id", column], [f"{target}.org_id", f"{target}.id"])


tool_versions = Table(
    "aio_tool_versions",
    metadata,
    *identity_columns(),
    Column("name", String(64), nullable=False),
    Column("driver", String(64), nullable=False),
    Column("risk", String(8), nullable=False),
    Column("input_schema", JSONB, nullable=False),
    Column("config", JSONB, nullable=False),
    Column("digest", String(64), nullable=False),
    Column("published", v1.Boolean, nullable=False, server_default=text("false")),
    tenant_fk("id", "aio_resources"),
    v1.stamp(),
    CheckConstraint("risk IN ('R0','R1','R2')", name="risk"),
)
model_configs = Table(
    "aio_model_configs",
    metadata,
    *identity_columns(),
    Column("provider", String(64), nullable=False),
    Column("model", String(128), nullable=False),
    Column("config", JSONB, nullable=False),
    Column("digest", String(64), nullable=False),
    Column("published", v1.Boolean, nullable=False, server_default=text("false")),
    tenant_fk("id", "aio_resources"),
    v1.stamp(),
)
model_calls = Table(
    "aio_model_calls",
    metadata,
    *identity_columns(),
    Column("run_id", Uuid, nullable=False),
    Column("generation", BigInteger, nullable=False),
    Column("logical_call_id", String(128), nullable=False),
    Column("model_config_id", Uuid, nullable=False),
    Column("request_digest", String(64), nullable=False),
    Column("state", String(24), nullable=False),
    Column("max_charge", Numeric(20, 6), nullable=False),
    Column("actual_charge", Numeric(20, 6)),
    Column("usage", JSONB),
    Column("response", JSONB),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    tenant_fk("run_id", "aio_runs"),
    tenant_fk("model_config_id", "aio_model_configs"),
    UniqueConstraint("org_id", "run_id", "logical_call_id"),
    v1.stamp(),
    CheckConstraint("state IN ('prepared','started','succeeded','failed','unknown')", name="state"),
    CheckConstraint("max_charge >= 0 AND (actual_charge IS NULL OR actual_charge >= 0)", name="charge"),
)

Index(
    "uq_aio_dispatch_active",
    dispatches.c.org_id,
    dispatches.c.invocation_id,
    unique=True,
    postgresql_where=dispatches.c.state.in_(["prepared", "dispatching", "unknown"]),
)
Index(
    "uq_aio_unresolved_blocker",
    blockers.c.org_id,
    blockers.c.run_id,
    unique=True,
    postgresql_where=blockers.c.resolved_at.is_(None),
)
BOOTSTRAP_TABLES = v1.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
