"""Schema snapshot v10: session-bound OAuth intents, not plaintext external tokens."""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
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
from . import schema_v9 as v9

metadata = MetaData(naming_convention=v9.metadata.naming_convention)
for original in v9.metadata.tables.values():
    original.to_metadata(metadata)
for name, original in vars(v9).items():
    if isinstance(original, Table):
        globals()[name] = metadata.tables[original.name]

metadata.tables["aio_mcp_bindings"].append_column(
    Column("auth_kind", String(16), nullable=False, server_default="opaque")
)
metadata.tables["aio_mcp_bindings"].append_column(Column("remote_revocation", String(32)))
metadata.tables["aio_mcp_bindings"].append_constraint(
    UniqueConstraint("org_id", "connection_id", "id", name="uq_aio_mcp_oauth_binding")
)
metadata.tables["aio_mcp_connections"].append_column(Column("authorization", JSONB(none_as_null=True)))
metadata.tables["aio_mcp_connections"].append_column(Column("credential_cleanup", String(32)))
metadata.tables["aio_auth_sessions"].append_constraint(
    UniqueConstraint("org_id", "user_id", "id", name="uq_aio_oauth_auth_session")
)
mcp_oauth_attempts = Table(
    "aio_mcp_oauth_attempts",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("connection_id", Uuid, nullable=False),
    Column("binding_id", Uuid, nullable=False),
    Column("requested_by", Uuid, nullable=False),
    Column("auth_session_id", Uuid, nullable=False),
    Column("membership_revision", Integer, nullable=False),
    Column("request_id", Uuid, nullable=False),
    Column("state", String(24), nullable=False, server_default="preparing"),
    Column("state_hash", String(64)),
    Column("code_hash", String(64)),
    Column("response_issuer", String(2048)),
    Column("error_code", String(64)),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    UniqueConstraint("org_id", "id"),
    UniqueConstraint("org_id", "binding_id"),
    UniqueConstraint("org_id", "requested_by", "request_id"),
    UniqueConstraint("org_id", "state_hash"),
    ForeignKeyConstraint(
        ["org_id", "connection_id", "binding_id"],
        ["aio_mcp_bindings.org_id", "aio_mcp_bindings.connection_id", "aio_mcp_bindings.id"],
    ),
    ForeignKeyConstraint(
        ["org_id", "requested_by", "auth_session_id"],
        ["aio_auth_sessions.org_id", "aio_auth_sessions.user_id", "aio_auth_sessions.id"],
    ),
    CheckConstraint("state IN ('preparing','authorizing','exchanging','completed','failed','cancelled')", name="state"),
)
Index(
    "ix_aio_mcp_oauth_expiry", mcp_oauth_attempts.c.org_id, mcp_oauth_attempts.c.state, mcp_oauth_attempts.c.expires_at
)
BOOTSTRAP_TABLES = v9.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
