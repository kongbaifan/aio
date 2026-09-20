"""Schema snapshot v9: private immutable filesystem handoffs, not process adoption."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
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
from . import schema_v8 as v8

metadata = MetaData(naming_convention=v8.metadata.naming_convention)
for original in v8.metadata.tables.values():
    original.to_metadata(metadata)
for name, original in vars(v8).items():
    if isinstance(original, Table):
        globals()[name] = metadata.tables[original.name]

metadata.tables["aio_runs"].append_constraint(
    UniqueConstraint("org_id", "id", "project_id", name="uq_aio_runs_workspace_scope")
)
metadata.tables["aio_sandbox_leases"].append_constraint(
    UniqueConstraint("org_id", "run_id", "id", name="uq_aio_sandbox_checkpoint_scope")
)
workspace_checkpoints = Table(
    "aio_workspace_checkpoints",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("run_id", Uuid, nullable=False),
    Column("project_id", Uuid, nullable=False),
    Column("generation", BigInteger, nullable=False),
    Column("checkpoint_seq", BigInteger, nullable=False),
    Column("checkpoint_digest", String(64), nullable=False),
    Column("sandbox_lease_id", Uuid, nullable=False),
    Column("invocation_id", Uuid, nullable=False),
    Column("base_version", BigInteger, nullable=False),
    Column("profile_id", String(128), nullable=False),
    Column("image_digest", String(80), nullable=False),
    Column("spec_digest", String(64), nullable=False),
    Column("binding_digest", String(64), nullable=False),
    Column("state", String(24), nullable=False, server_default="preparing"),
    Column("manifest", JSONB(none_as_null=True)),
    Column("manifest_digest", String(64)),
    Column("reserved_bytes", BigInteger, nullable=False),
    Column("provenance_source_ids", JSONB, nullable=False),
    Column("capability_source_ids", JSONB, nullable=False),
    Column("capability_read_source_ids", JSONB, nullable=False),
    Column("mcp_source_refs", JSONB, nullable=False),
    Column("knowledge_source_refs", JSONB, nullable=False),
    Column("manager_acknowledged", Boolean, nullable=False, server_default=text("false")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("ready_at", DateTime(timezone=True)),
    Column("purged_at", DateTime(timezone=True)),
    UniqueConstraint("org_id", "id"),
    UniqueConstraint("org_id", "run_id", "generation"),
    UniqueConstraint("org_id", "run_id", "project_id", "id"),
    ForeignKeyConstraint(["org_id", "run_id", "project_id"], ["aio_runs.org_id", "aio_runs.id", "aio_runs.project_id"]),
    ForeignKeyConstraint(
        ["org_id", "run_id", "checkpoint_seq"],
        ["aio_checkpoints.org_id", "aio_checkpoints.run_id", "aio_checkpoints.seq"],
    ),
    ForeignKeyConstraint(
        ["org_id", "run_id", "sandbox_lease_id"],
        ["aio_sandbox_leases.org_id", "aio_sandbox_leases.run_id", "aio_sandbox_leases.id"],
    ),
    ForeignKeyConstraint(["org_id", "invocation_id"], ["aio_invocations.org_id", "aio_invocations.id"]),
    CheckConstraint("state IN ('preparing','bound','ready','retiring','purged')", name="state"),
    CheckConstraint("generation > 0 AND checkpoint_seq > 0 AND base_version >= 0", name="cursor"),
    CheckConstraint("reserved_bytes BETWEEN 0 AND 8388608", name="storage"),
    CheckConstraint("(manifest IS NULL) = (manifest_digest IS NULL)", name="manifest_binding"),
    CheckConstraint("manifest IS NULL OR jsonb_typeof(manifest) = 'array'", name="manifest_array"),
    CheckConstraint("state != 'ready' OR manifest IS NOT NULL", name="ready_manifest"),
    CheckConstraint("state != 'purged' OR reserved_bytes = 0", name="purged_storage"),
)
metadata.tables["aio_workspace_leases"].append_column(Column("resume_checkpoint_id", Uuid))
Index(
    "ix_aio_workspace_checkpoint_maintenance",
    workspace_checkpoints.c.org_id,
    workspace_checkpoints.c.state,
    workspace_checkpoints.c.manager_acknowledged,
    workspace_checkpoints.c.created_at,
)
Index(
    "ix_aio_workspace_checkpoint_holds",
    workspace_checkpoints.c.org_id,
    workspace_checkpoints.c.project_id,
    postgresql_where=workspace_checkpoints.c.reserved_bytes > 0,
)
metadata.tables["aio_workspace_leases"].append_constraint(
    ForeignKeyConstraint(
        ["org_id", "run_id", "project_id", "resume_checkpoint_id"],
        [
            "aio_workspace_checkpoints.org_id",
            "aio_workspace_checkpoints.run_id",
            "aio_workspace_checkpoints.project_id",
            "aio_workspace_checkpoints.id",
        ],
        name="fk_aio_workspace_resume_checkpoint",
    )
)
BOOTSTRAP_TABLES = v8.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
