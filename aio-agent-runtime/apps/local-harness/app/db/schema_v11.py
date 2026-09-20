"""Schema snapshot v11: generation- and identity-scoped stdio process leases."""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    CheckConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from . import schema_v10 as v10

metadata = MetaData(naming_convention=v10.metadata.naming_convention)
for original in v10.metadata.tables.values():
    original.to_metadata(metadata)
for name, original in vars(v10).items():
    if isinstance(original, Table):
        globals()[name] = metadata.tables[original.name]

mcp_stdio_leases = Table(
    "aio_mcp_stdio_leases",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("run_id", Uuid),
    Column("discovery_id", Uuid),
    Column("generation", Integer, nullable=False),
    Column("connection_id", Uuid, nullable=False),
    Column("credential_ref", Uuid, nullable=False),
    Column("credential_revision", Integer, nullable=False),
    Column("requested_by", Uuid, nullable=False),
    Column("membership_revision", Integer, nullable=False),
    Column("spec", JSONB, nullable=False),
    Column("spec_digest", String(64), nullable=False),
    Column("state", String(24), nullable=False, server_default="preparing"),
    Column("manager_id", String(64)),
    Column("backend_id", String(128)),
    Column("close_reason", String(24)),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    UniqueConstraint("org_id", "id"),
    UniqueConstraint("org_id", "run_id", "generation", "connection_id"),
    UniqueConstraint("org_id", "discovery_id"),
    ForeignKeyConstraint(["org_id", "run_id"], ["aio_runs.org_id", "aio_runs.id"]),
    ForeignKeyConstraint(["org_id", "discovery_id"], ["aio_mcp_discoveries.org_id", "aio_mcp_discoveries.id"]),
    ForeignKeyConstraint(
        ["org_id", "connection_id", "credential_revision", "credential_ref"],
        [
            "aio_mcp_bindings.org_id",
            "aio_mcp_bindings.connection_id",
            "aio_mcp_bindings.revision",
            "aio_mcp_bindings.id",
        ],
    ),
    ForeignKeyConstraint(["org_id", "requested_by"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
    CheckConstraint("(run_id IS NOT NULL)::int + (discovery_id IS NOT NULL)::int = 1", name="target"),
    CheckConstraint("state IN ('preparing','ready','stopping','destroyed','lost')", name="state"),
    CheckConstraint("generation > 0", name="generation"),
)
Index("ix_aio_stdio_lifecycle", mcp_stdio_leases.c.org_id, mcp_stdio_leases.c.state, mcp_stdio_leases.c.expires_at)
BOOTSTRAP_TABLES = v10.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
