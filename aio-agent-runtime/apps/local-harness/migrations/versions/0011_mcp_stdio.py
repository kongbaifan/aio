"""Private stdio process bindings; no credential values, commands or transcripts in PG."""

from alembic import op
from app.db import schema_v11 as s

revision = "0011_mcp_stdio"
down_revision = "0010_mcp_oauth"
branch_labels = None
depends_on = None


def upgrade():
    table = s.mcp_stdio_leases
    table.create(op.get_bind())
    predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
    op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')


def downgrade():
    raise RuntimeError("Destructive stdio lifecycle downgrade is not supported")
