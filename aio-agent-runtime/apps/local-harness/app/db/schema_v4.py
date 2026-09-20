"""Schema snapshot v4: explicit department grants and organization-scoped member names."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKeyConstraint,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    text,
    CheckConstraint,
)
from . import schema_v3 as v3

metadata = MetaData(naming_convention=v3.metadata.naming_convention)
for original in v3.metadata.tables.values():
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
tool_versions = metadata.tables["aio_tool_versions"]
model_configs = metadata.tables["aio_model_configs"]
model_calls = metadata.tables["aio_model_calls"]
artifacts = metadata.tables["aio_artifacts"]
upload_slots = metadata.tables["aio_upload_slots"]
workspace_leases = metadata.tables["aio_workspace_leases"]
workspace_versions = metadata.tables["aio_workspace_versions"]

memberships.append_column(Column("display_name", String(200)))
departments = Table(
    "aio_departments",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    UniqueConstraint("org_id", "id"),
    UniqueConstraint("org_id", "name"),
    ForeignKeyConstraint(["org_id"], ["aio_organizations.id"]),
)
department_memberships = Table(
    "aio_department_memberships",
    metadata,
    Column("org_id", Uuid, primary_key=True),
    Column("department_id", Uuid, primary_key=True),
    Column("user_id", Uuid, primary_key=True),
    Column("role", String(24), nullable=False, server_default="member"),
    ForeignKeyConstraint(["org_id", "department_id"], ["aio_departments.org_id", "aio_departments.id"]),
    ForeignKeyConstraint(["org_id", "user_id"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
    CheckConstraint("role IN ('member','manager')", name="role"),
)
department_grants = Table(
    "aio_department_grants",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("resource_id", Uuid, nullable=False),
    Column("department_id", Uuid, nullable=False),
    Column("action", String(64), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    UniqueConstraint("org_id", "id"),
    UniqueConstraint("org_id", "resource_id", "department_id", "action"),
    ForeignKeyConstraint(["org_id", "resource_id"], ["aio_resources.org_id", "aio_resources.id"]),
    ForeignKeyConstraint(["org_id", "department_id"], ["aio_departments.org_id", "aio_departments.id"]),
)
BOOTSTRAP_TABLES = v3.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
