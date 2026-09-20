"""Schema snapshot v3: scoped artifacts and workspace publication, plus execution specs."""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from . import schema_v2 as v2

metadata = MetaData(naming_convention=v2.metadata.naming_convention)
for original in v2.metadata.tables.values():
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

sandbox_leases.append_column(Column("spec", JSONB))
runs.append_column(Column("provenance_source_ids", JSONB, nullable=False, server_default=text("'[]'::jsonb")))
organizations.append_column(Column("storage_limit_bytes", BigInteger, nullable=False, server_default="1073741824"))
projects.append_column(Column("storage_limit_bytes", BigInteger, nullable=False, server_default="268435456"))
artifacts = Table(
    "aio_artifacts",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("project_id", Uuid, nullable=False),
    Column("run_id", Uuid),
    Column("path", String(512), nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("bytes", BigInteger, nullable=False),
    Column("media_type", String(128), nullable=False),
    Column("state", String(24), nullable=False),
    Column("kind", String(24), nullable=False),
    Column("source_refs", JSONB, nullable=False),
    Column("scan_state", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    UniqueConstraint("org_id", "id"),
    ForeignKeyConstraint(["org_id", "id"], ["aio_resources.org_id", "aio_resources.id"]),
    ForeignKeyConstraint(["org_id", "project_id"], ["aio_projects.org_id", "aio_projects.id"]),
    ForeignKeyConstraint(["org_id", "run_id"], ["aio_runs.org_id", "aio_runs.id"]),
)
Index(
    "uq_aio_run_artifact_path",
    artifacts.c.org_id,
    artifacts.c.run_id,
    artifacts.c.path,
    unique=True,
    postgresql_where=artifacts.c.run_id.is_not(None),
)
upload_slots = Table(
    "aio_upload_slots",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, nullable=False),
    Column("project_id", Uuid, nullable=False),
    Column("path", String(512), nullable=False),
    Column("max_bytes", BigInteger, nullable=False),
    Column("state", String(24), nullable=False),
    Column("artifact_id", Uuid),
    Column("content_sha256", String(64)),
    Column("content_bytes", BigInteger),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("org_id", "id"),
    ForeignKeyConstraint(["org_id", "user_id"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
    ForeignKeyConstraint(["org_id", "project_id"], ["aio_projects.org_id", "aio_projects.id"]),
    ForeignKeyConstraint(["org_id", "artifact_id"], ["aio_artifacts.org_id", "aio_artifacts.id"]),
)
workspace_leases = Table(
    "aio_workspace_leases",
    metadata,
    Column("org_id", Uuid, primary_key=True),
    Column("project_id", Uuid, primary_key=True),
    Column("run_id", Uuid, nullable=False),
    Column("generation", BigInteger, nullable=False),
    Column("base_version", BigInteger, nullable=False),
    Column("storage_reserved_bytes", BigInteger, nullable=False, server_default="0"),
    Column("export_manifest", JSONB),
    Column("state", String(24), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(["org_id", "project_id"], ["aio_projects.org_id", "aio_projects.id"]),
    ForeignKeyConstraint(["org_id", "run_id"], ["aio_runs.org_id", "aio_runs.id"]),
)
workspace_versions = Table(
    "aio_workspace_versions",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("project_id", Uuid, nullable=False),
    Column("version", BigInteger, nullable=False),
    Column("parent_version", BigInteger, nullable=False),
    Column("run_id", Uuid, nullable=False),
    Column("manifest", JSONB, nullable=False),
    Column("digest", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    UniqueConstraint("org_id", "id"),
    UniqueConstraint("org_id", "project_id", "version"),
    ForeignKeyConstraint(["org_id", "project_id"], ["aio_projects.org_id", "aio_projects.id"]),
    ForeignKeyConstraint(["org_id", "run_id"], ["aio_runs.org_id", "aio_runs.id"]),
)
BOOTSTRAP_TABLES = v2.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
