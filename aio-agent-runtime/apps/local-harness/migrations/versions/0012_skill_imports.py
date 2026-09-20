"""Private Skill archive quarantine, import lease fencing and cleanup evidence."""

from alembic import op
from app.db import schema_v12 as s

revision = "0012_skill_imports"
down_revision = "0011_mcp_stdio"
branch_labels = None
depends_on = None


def upgrade():
    table = s.skill_imports
    table.create(op.get_bind())
    predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
    op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')


def downgrade():
    raise RuntimeError("Destructive Skill quarantine downgrade is not supported")
