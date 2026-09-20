"""Versioned remote MCP definitions, private connections/bindings and result provenance."""

from alembic import op
from sqlalchemy import Column, text
from sqlalchemy.dialects.postgresql import JSONB
from app.db import schema_v6 as s

revision = "0006_mcp"
down_revision = "0005_skills"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("aio_runs", "aio_artifacts"):
        op.add_column(name, Column("mcp_source_refs", JSONB, nullable=False, server_default=text("'[]'::jsonb")))
    for table in (s.mcp_servers, s.mcp_connections, s.mcp_bindings, s.mcp_discoveries):
        table.create(op.get_bind())
        predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
        op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')
    op.create_foreign_key(
        "fk_aio_mcp_connection_current_binding",
        "aio_mcp_connections",
        "aio_mcp_bindings",
        ["org_id", "id", "credential_revision", "credential_ref"],
        ["org_id", "connection_id", "revision", "id"],
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade():
    raise RuntimeError("Destructive MCP credential/provenance downgrade is not supported")
