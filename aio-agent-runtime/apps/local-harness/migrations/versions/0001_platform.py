"""Platform v1: tenant-scoped durable identity, run, approval and execution facts.

This migration intentionally does not create application login roles/passwords.
Provisioning grants access only after the operator names a dedicated runtime role.
"""

from alembic import op

from app.db.schema_v1 import TENANT_TABLES, metadata

revision = "0001_platform"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    metadata.create_all(connection)
    for table in TENANT_TABLES:
        # Names and policy expressions are immutable migration constants, never user input.
        column = "id" if table.name == "aio_organizations" else "org_id"
        predicate = f"{column} = NULLIF(current_setting('aio.org_id', true), '')::uuid"
        op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')


def downgrade() -> None:
    raise RuntimeError(
        "Destructive platform downgrade is disabled; restore/forward-fix requires an explicit data recovery plan"
    )
