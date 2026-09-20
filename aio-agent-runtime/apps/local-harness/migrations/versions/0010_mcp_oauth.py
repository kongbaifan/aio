"""MCP OAuth intents tied to the initiating platform browser session."""

from alembic import op
from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import JSONB
from app.db import schema_v10 as s

revision = "0010_mcp_oauth"
down_revision = "0009_workspace_handoff"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("aio_mcp_bindings", Column("auth_kind", String(16), nullable=False, server_default="opaque"))
    op.add_column("aio_mcp_bindings", Column("remote_revocation", String(32)))
    op.add_column("aio_mcp_connections", Column("authorization", JSONB(none_as_null=True)))
    op.add_column("aio_mcp_connections", Column("credential_cleanup", String(32)))
    op.create_unique_constraint("uq_aio_mcp_oauth_binding", "aio_mcp_bindings", ["org_id", "connection_id", "id"])
    op.create_unique_constraint("uq_aio_oauth_auth_session", "aio_auth_sessions", ["org_id", "user_id", "id"])
    table = s.mcp_oauth_attempts
    table.create(op.get_bind())
    predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
    op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')


def downgrade():
    raise RuntimeError("Destructive OAuth intent downgrade is not supported")
