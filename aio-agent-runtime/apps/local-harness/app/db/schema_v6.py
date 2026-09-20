"""Schema snapshot v6: shared MCP definitions, private credential bindings and connection provenance."""

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from . import schema_v5 as v5

metadata = MetaData(naming_convention=v5.metadata.naming_convention)
for original in v5.metadata.tables.values():
    original.to_metadata(metadata)
for name, original in vars(v5).items():
    if isinstance(original, Table):
        globals()[name] = metadata.tables[original.name]

for name in ("aio_runs", "aio_artifacts"):
    metadata.tables[name].append_column(
        Column("mcp_source_refs", JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    )

mcp_servers = Table(
    "aio_mcp_servers",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("version", String(64), nullable=False),
    Column("endpoint_id", String(64), nullable=False),
    Column("endpoint_digest", String(64), nullable=False),
    Column("state", String(24), nullable=False, server_default="draft"),
    Column("revision", Integer, nullable=False, server_default="0"),
    Column("definition", JSONB),
    Column("digest", String(64)),
    Column("published_tools", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("discovery_id", Uuid),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    UniqueConstraint("org_id", "id"),
    UniqueConstraint("org_id", "name", "version"),
    ForeignKeyConstraint(["org_id", "id"], ["aio_resources.org_id", "aio_resources.id"]),
    CheckConstraint("state IN ('draft','published')", name="state"),
)
mcp_connections = Table(
    "aio_mcp_connections",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("server_id", Uuid, nullable=False),
    Column("name", String(100), nullable=False),
    Column("scope", String(24), nullable=False),
    Column("department_id", Uuid),
    Column("state", String(24), nullable=False, server_default="pending"),
    Column("credential_ref", Uuid),
    Column("credential_revision", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    UniqueConstraint("org_id", "id"),
    ForeignKeyConstraint(["org_id", "id"], ["aio_resources.org_id", "aio_resources.id"]),
    ForeignKeyConstraint(["org_id", "server_id"], ["aio_mcp_servers.org_id", "aio_mcp_servers.id"]),
    ForeignKeyConstraint(["org_id", "department_id"], ["aio_departments.org_id", "aio_departments.id"]),
    ForeignKeyConstraint(
        ["org_id", "id", "credential_revision", "credential_ref"],
        [
            "aio_mcp_bindings.org_id",
            "aio_mcp_bindings.connection_id",
            "aio_mcp_bindings.revision",
            "aio_mcp_bindings.id",
        ],
        name="fk_aio_mcp_connection_current_binding",
        use_alter=True,
        deferrable=True,
        initially="DEFERRED",
    ),
    CheckConstraint(
        "(scope='personal' AND department_id IS NULL) OR (scope='department' AND department_id IS NOT NULL)",
        name="scope",
    ),
    CheckConstraint("state IN ('pending','active','reauth_required','revoked')", name="state"),
)
mcp_bindings = Table(
    "aio_mcp_bindings",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("connection_id", Uuid, nullable=False),
    Column("revision", Integer, nullable=False),
    Column("endpoint_id", String(64), nullable=False),
    Column("endpoint_digest", String(64), nullable=False),
    Column("ticket_id", Uuid, nullable=False),
    Column("requested_by", Uuid, nullable=False),
    Column("membership_revision", Integer, nullable=False),
    Column("state", String(24), nullable=False, server_default="pending"),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    UniqueConstraint("org_id", "id"),
    UniqueConstraint("org_id", "ticket_id"),
    UniqueConstraint("org_id", "connection_id", "revision"),
    UniqueConstraint("org_id", "connection_id", "revision", "id"),
    ForeignKeyConstraint(["org_id", "connection_id"], ["aio_mcp_connections.org_id", "aio_mcp_connections.id"]),
    ForeignKeyConstraint(["org_id", "requested_by"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
    CheckConstraint("revision > 0", name="revision"),
    CheckConstraint("state IN ('pending','active','retiring','revoked')", name="state"),
)
mcp_discoveries = Table(
    "aio_mcp_discoveries",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("connection_id", Uuid, nullable=False),
    Column("binding_id", Uuid, nullable=False),
    Column("requested_by", Uuid, nullable=False),
    Column("membership_revision", Integer, nullable=False),
    Column("state", String(24), nullable=False, server_default="running"),
    Column("spec", JSONB, nullable=False),
    Column("result", JSONB),
    Column("result_bytes", Integer, nullable=False, server_default="0"),
    Column("error_code", String(64)),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    UniqueConstraint("org_id", "id"),
    ForeignKeyConstraint(["org_id", "connection_id"], ["aio_mcp_connections.org_id", "aio_mcp_connections.id"]),
    ForeignKeyConstraint(["org_id", "binding_id"], ["aio_mcp_bindings.org_id", "aio_mcp_bindings.id"]),
    ForeignKeyConstraint(["org_id", "requested_by"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
    CheckConstraint("state IN ('running','ready','failed')", name="state"),
    CheckConstraint("result_bytes BETWEEN 0 AND 1048576", name="result_bytes"),
)
BOOTSTRAP_TABLES = v5.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
