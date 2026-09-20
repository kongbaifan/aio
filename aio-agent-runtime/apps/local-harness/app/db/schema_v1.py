"""Immutable migration v1 schema. Later schema changes require a new migration.

Global bootstrap tables hold only verified identity/session lookup state. Every
org-scoped business table uses FORCE RLS; GUC identity is a trusted-app contract,
not protection against a stolen DB credential executing arbitrary SQL.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
    }
)


def uuid_id() -> Column:
    return Column("id", Uuid, primary_key=True)


def stamp(name: str = "created_at") -> Column:
    return Column(name, DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))


def org_column(*, primary_key: bool = False) -> Column:
    return Column("org_id", Uuid, ForeignKey("aio_organizations.id"), nullable=False, primary_key=primary_key)


def revision() -> Column:
    return Column("revision", BigInteger, nullable=False, server_default="0")


def tenant_unique() -> UniqueConstraint:
    return UniqueConstraint("org_id", "id")


def tenant_fk(column: str, table: str, **kw) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["org_id", column], [f"{table}.org_id", f"{table}.id"], **kw)


organizations = Table(
    "aio_organizations",
    metadata,
    uuid_id(),
    Column("name", String(200), nullable=False),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("policy_revision", BigInteger, nullable=False, server_default="0"),
    Column("allowed_classifications", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("denied_actions", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    stamp(),
)
users = Table(
    "aio_users",
    metadata,
    uuid_id(),
    Column("issuer", Text, nullable=False),
    Column("subject", String(255), nullable=False),
    Column("display_name", String(200), nullable=False),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    UniqueConstraint("issuer", "subject"),
    stamp(),
)
memberships = Table(
    "aio_memberships",
    metadata,
    org_column(primary_key=True),
    Column("user_id", Uuid, ForeignKey("aio_users.id"), primary_key=True),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("role", String(32), nullable=False, server_default="member"),
    revision(),
    UniqueConstraint("org_id", "user_id"),
    CheckConstraint("role IN ('member','org_admin','operator','auditor')", name="role"),
)
login_attempts = Table(
    "aio_login_attempts",
    metadata,
    Column("state_hash", String(64), primary_key=True),
    Column("binding_hash", String(64), nullable=False),
    Column("org_id", Uuid, nullable=False),
    Column("nonce_hash", String(64), nullable=False),
    Column("code_verifier", String(128), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True)),
    stamp(),
)
auth_sessions = Table(
    "aio_auth_sessions",
    metadata,
    uuid_id(),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("org_id", Uuid, ForeignKey("aio_organizations.id"), nullable=False),
    Column("user_id", Uuid, ForeignKey("aio_users.id"), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    stamp(),
)
resources = Table(
    "aio_resources",
    metadata,
    org_column(),
    uuid_id(),
    Column("kind", String(32), nullable=False),
    Column("owner_id", Uuid, nullable=False),
    Column("status", String(24), nullable=False, server_default="active"),
    Column("classification", String(32), nullable=False, server_default="internal"),
    revision(),
    stamp(),
    tenant_unique(),
    ForeignKeyConstraint(["org_id", "owner_id"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
)
grants = Table(
    "aio_grants",
    metadata,
    org_column(),
    uuid_id(),
    Column("resource_id", Uuid, nullable=False),
    Column("subject_id", Uuid, nullable=False),
    Column("subject_type", String(24), nullable=False, server_default="user"),
    Column("action", String(64), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    tenant_fk("resource_id", "aio_resources"),
    tenant_unique(),
    CheckConstraint("subject_type = 'user'", name="subject_type"),
    ForeignKeyConstraint(["org_id", "subject_id"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
    UniqueConstraint("org_id", "resource_id", "subject_type", "subject_id", "action"),
    stamp(),
)
projects = Table(
    "aio_projects",
    metadata,
    org_column(),
    uuid_id(),
    Column("name", String(200), nullable=False),
    Column("head_version", BigInteger, nullable=False, server_default="0"),
    tenant_fk("id", "aio_resources"),
    tenant_unique(),
    stamp(),
)
agent_versions = Table(
    "aio_agent_versions",
    metadata,
    org_column(),
    uuid_id(),
    Column("name", String(200), nullable=False),
    Column("version", String(64), nullable=False),
    Column("engine", String(64), nullable=False),
    Column("model_config_id", Uuid),
    Column("manifest", JSONB, nullable=False),
    Column("digest", String(64), nullable=False),
    Column("instruction", Text, nullable=False),
    Column("published", Boolean, nullable=False, server_default=text("false")),
    tenant_fk("id", "aio_resources"),
    tenant_unique(),
    stamp(),
)
sessions = Table(
    "aio_sessions",
    metadata,
    org_column(),
    uuid_id(),
    Column("project_id", Uuid, nullable=False),
    Column("agent_version_id", Uuid, nullable=False),
    Column("title", String(200), nullable=False),
    Column("message_seq", BigInteger, nullable=False, server_default="0"),
    tenant_fk("id", "aio_resources"),
    tenant_fk("project_id", "aio_projects"),
    tenant_fk("agent_version_id", "aio_agent_versions"),
    tenant_unique(),
    UniqueConstraint("org_id", "id", "project_id"),
    stamp(),
    stamp("updated_at"),
)
budgets = Table(
    "aio_budgets",
    metadata,
    org_column(),
    uuid_id(),
    Column("owner_id", Uuid, nullable=False),
    Column("currency", String(3), nullable=False, server_default="USD"),
    Column("hard_limit", Numeric(20, 6), nullable=False),
    Column("reserved", Numeric(20, 6), nullable=False, server_default="0"),
    Column("consumed", Numeric(20, 6), nullable=False, server_default="0"),
    tenant_unique(),
    UniqueConstraint("org_id", "owner_id", "currency"),
    ForeignKeyConstraint(["org_id", "owner_id"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
    CheckConstraint("hard_limit >= 0 AND reserved >= 0 AND consumed >= 0", name="nonnegative"),
)
manifest_snapshots = Table(
    "aio_manifest_snapshots",
    metadata,
    org_column(),
    uuid_id(),
    Column("run_id", Uuid, nullable=False),
    Column("content", JSONB, nullable=False),
    Column("digest", String(64), nullable=False),
    tenant_unique(),
    tenant_fk("run_id", "aio_runs", deferrable=True, initially="DEFERRED", use_alter=True),
    stamp(),
)
runs = Table(
    "aio_runs",
    metadata,
    org_column(),
    uuid_id(),
    Column("session_id", Uuid, nullable=False),
    Column("project_id", Uuid, nullable=False),
    Column("actor_id", Uuid, nullable=False),
    Column("agent_version_id", Uuid, nullable=False),
    Column("manifest_snapshot_id", Uuid, nullable=False),
    Column("budget_id", Uuid, nullable=False),
    Column("state", String(32), nullable=False, server_default="queued"),
    revision(),
    Column("generation", BigInteger, nullable=False, server_default="0"),
    Column("attempt_id", Uuid),
    Column("next_event_seq", BigInteger, nullable=False, server_default="0"),
    Column("input", JSONB, nullable=False),
    Column("result", JSONB),
    Column("error_code", String(64)),
    Column("cleanup_state", String(24), nullable=False, server_default="not_allocated"),
    Column("queue_expires_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("deadline_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    tenant_unique(),
    tenant_fk("id", "aio_resources"),
    tenant_fk("agent_version_id", "aio_agent_versions"),
    tenant_fk("manifest_snapshot_id", "aio_manifest_snapshots"),
    tenant_fk("budget_id", "aio_budgets"),
    ForeignKeyConstraint(
        ["org_id", "session_id", "project_id"], ["aio_sessions.org_id", "aio_sessions.id", "aio_sessions.project_id"]
    ),
    ForeignKeyConstraint(["org_id", "actor_id"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
    CheckConstraint(
        "state IN ('queued','preparing','running','waiting_approval','persisting','cancel_requested',"
        "'recovery_required','succeeded','failed','cancelled','timed_out')",
        name="state",
    ),
    CheckConstraint("generation >= 0 AND next_event_seq >= 0 AND revision >= 0", name="counters"),
    stamp(),
)
Index(
    "uq_aio_session_unresolved",
    runs.c.org_id,
    runs.c.session_id,
    unique=True,
    postgresql_where=runs.c.state.in_(
        ["queued", "preparing", "running", "waiting_approval", "persisting", "cancel_requested", "recovery_required"]
    ),
)
messages = Table(
    "aio_messages",
    metadata,
    org_column(),
    uuid_id(),
    Column("session_id", Uuid, nullable=False),
    Column("run_id", Uuid, nullable=False),
    Column("seq", BigInteger, nullable=False),
    Column("role", String(24), nullable=False),
    Column("content", JSONB, nullable=False),
    tenant_unique(),
    tenant_fk("session_id", "aio_sessions"),
    tenant_fk("run_id", "aio_runs"),
    UniqueConstraint("org_id", "session_id", "seq"),
    stamp(),
)
jobs = Table(
    "aio_jobs",
    metadata,
    org_column(),
    uuid_id(),
    Column("run_id", Uuid, nullable=False),
    Column("state", String(32), nullable=False, server_default="queued"),
    Column("lease_owner", String(128)),
    Column("lease_version", BigInteger, nullable=False, server_default="0"),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column("not_before", DateTime(timezone=True), nullable=False),
    tenant_fk("run_id", "aio_runs"),
    UniqueConstraint("org_id", "run_id"),
    tenant_unique(),
    stamp(),
)
Index("ix_aio_jobs_claim", jobs.c.state, jobs.c.not_before)
events = Table(
    "aio_run_events",
    metadata,
    org_column(),
    Column("run_id", Uuid, primary_key=True),
    Column("seq", BigInteger, primary_key=True),
    Column("kind", String(64), nullable=False),
    Column("schema_version", Integer, nullable=False, server_default="1"),
    Column("payload", JSONB, nullable=False),
    tenant_fk("run_id", "aio_runs"),
    stamp(),
)
checkpoints = Table(
    "aio_checkpoints",
    metadata,
    org_column(),
    uuid_id(),
    Column("run_id", Uuid, nullable=False),
    Column("seq", BigInteger, nullable=False),
    Column("generation", BigInteger, nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("restartability", String(32), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("digest", String(64), nullable=False),
    tenant_fk("run_id", "aio_runs"),
    tenant_unique(),
    UniqueConstraint("org_id", "run_id", "seq"),
    stamp(),
)
invocations = Table(
    "aio_invocations",
    metadata,
    org_column(),
    uuid_id(),
    Column("run_id", Uuid, nullable=False),
    Column("logical_call_id", String(128), nullable=False),
    Column("action", JSONB, nullable=False),
    Column("action_digest", String(64), nullable=False),
    Column("state", String(32), nullable=False),
    Column("risk_class", String(16), nullable=False),
    Column("external_operation_key", String(128), nullable=False),
    Column("result", JSONB),
    revision(),
    tenant_fk("run_id", "aio_runs"),
    tenant_unique(),
    UniqueConstraint("org_id", "run_id", "logical_call_id"),
    stamp(),
)
approvals = Table(
    "aio_approvals",
    metadata,
    org_column(),
    uuid_id(),
    Column("invocation_id", Uuid, nullable=False),
    Column("action_digest", String(64), nullable=False),
    Column("state", String(24), nullable=False, server_default="pending"),
    Column("requested_by", Uuid, nullable=False),
    Column("decided_by", Uuid),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("decided_at", DateTime(timezone=True)),
    Column("requires_different_actor", Boolean, nullable=False, server_default=text("true")),
    revision(),
    tenant_fk("id", "aio_resources"),
    tenant_fk("invocation_id", "aio_invocations"),
    tenant_unique(),
    CheckConstraint("state IN ('pending','approved','rejected','expired','invalidated','cancelled')", name="state"),
    stamp(),
)
Index(
    "uq_aio_pending_approval",
    approvals.c.org_id,
    approvals.c.invocation_id,
    unique=True,
    postgresql_where=approvals.c.state == "pending",
)
dispatches = Table(
    "aio_dispatches",
    metadata,
    org_column(),
    uuid_id(),
    Column("invocation_id", Uuid, nullable=False),
    Column("generation", BigInteger, nullable=False),
    Column("target_slot", String(128), nullable=False),
    Column("state", String(24), nullable=False),
    Column("result", JSONB),
    tenant_fk("invocation_id", "aio_invocations"),
    tenant_unique(),
    stamp(),
)
idempotency_keys = Table(
    "aio_idempotency_keys",
    metadata,
    org_column(primary_key=True),
    Column("actor_id", Uuid, primary_key=True),
    Column("operation", String(128), primary_key=True),
    Column("key_hash", String(64), primary_key=True),
    Column("request_hash", String(64), nullable=False),
    Column("run_id", Uuid),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    tenant_fk("run_id", "aio_runs"),
    stamp(),
)
reservations = Table(
    "aio_reservations",
    metadata,
    org_column(),
    uuid_id(),
    Column("budget_id", Uuid, nullable=False),
    Column("run_id", Uuid, nullable=False),
    Column("amount", Numeric(20, 6), nullable=False),
    Column("state", String(24), nullable=False, server_default="reserved"),
    tenant_fk("budget_id", "aio_budgets"),
    tenant_fk("run_id", "aio_runs"),
    tenant_unique(),
    UniqueConstraint("org_id", "run_id"),
    CheckConstraint("amount >= 0", name="amount"),
    stamp(),
)
ledger = Table(
    "aio_usage_ledger",
    metadata,
    org_column(),
    uuid_id(),
    Column("run_id", Uuid, nullable=False),
    Column("budget_id", Uuid, nullable=False),
    Column("producer", String(128), nullable=False),
    Column("usage_key", String(128), nullable=False),
    Column("status", String(24), nullable=False),
    Column("amount", Numeric(20, 6)),
    Column("currency", String(3), nullable=False),
    Column("price_version", String(128), nullable=False),
    tenant_fk("run_id", "aio_runs"),
    tenant_fk("budget_id", "aio_budgets"),
    tenant_unique(),
    UniqueConstraint("org_id", "producer", "usage_key"),
    stamp(),
)
sandbox_leases = Table(
    "aio_sandbox_leases",
    metadata,
    org_column(),
    uuid_id(),
    Column("run_id", Uuid, nullable=False),
    Column("generation", BigInteger, nullable=False),
    Column("target_slot", String(128), nullable=False),
    Column("role", String(24), nullable=False),
    Column("profile_id", String(128), nullable=False),
    Column("image_digest", String(80), nullable=False),
    Column("spec_digest", String(64), nullable=False),
    Column("backend_id", String(128)),
    Column("state", String(32), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    tenant_fk("run_id", "aio_runs"),
    tenant_unique(),
    UniqueConstraint("org_id", "run_id", "generation", "target_slot"),
    stamp(),
)
blockers = Table(
    "aio_workspace_blockers",
    metadata,
    org_column(),
    uuid_id(),
    Column("project_id", Uuid, nullable=False),
    Column("run_id", Uuid, nullable=False),
    Column("reason", String(64), nullable=False),
    Column("resolved_at", DateTime(timezone=True)),
    tenant_fk("project_id", "aio_projects"),
    tenant_fk("run_id", "aio_runs"),
    tenant_unique(),
    stamp(),
)
outbox = Table(
    "aio_outbox",
    metadata,
    org_column(),
    uuid_id(),
    Column("aggregate_id", Uuid, nullable=False),
    Column("kind", String(64), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("delivered_at", DateTime(timezone=True)),
    Column("attempts", Integer, nullable=False, server_default="0"),
    tenant_unique(),
    stamp(),
)
audit = Table(
    "aio_audit_events",
    metadata,
    org_column(),
    uuid_id(),
    Column("actor_id", Uuid, nullable=False),
    Column("service_actor_id", String(128)),
    Column("run_id", Uuid),
    Column("action", String(64), nullable=False),
    Column("resource_id", Uuid),
    Column("outcome", String(64), nullable=False),
    Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    tenant_unique(),
    stamp(),
)

BOOTSTRAP_TABLES = frozenset({users.name, login_attempts.name, auth_sessions.name})
TENANT_TABLES = tuple(table for table in metadata.tables.values() if table.name not in BOOTSTRAP_TABLES)
