"""Department membership and explicit group-scoped resource grants."""

from alembic import op
from sqlalchemy import Column, String
from app.db import schema_v4 as s

revision = "0004_departments"
down_revision = "0003_sandbox_artifacts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("aio_memberships", Column("display_name", String(200)))
    for table in (s.departments, s.department_memberships, s.department_grants):
        table.create(op.get_bind())
        predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
        op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; preserve authorization facts in a reviewed recovery")
