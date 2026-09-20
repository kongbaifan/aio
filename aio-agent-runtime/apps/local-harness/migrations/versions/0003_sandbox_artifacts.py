"""Persist narrow sandbox specs and private artifact/workspace publication records."""

from alembic import op
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from app.db import schema_v3 as s

revision = "0003_sandbox_artifacts"
down_revision = "0002_execution"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("aio_sandbox_leases", Column("spec", JSONB))
    from sqlalchemy import text

    op.add_column(
        "aio_runs", Column("provenance_source_ids", JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    )
    from sqlalchemy import BigInteger

    op.add_column(
        "aio_organizations", Column("storage_limit_bytes", BigInteger, nullable=False, server_default="1073741824")
    )
    op.add_column("aio_projects", Column("storage_limit_bytes", BigInteger, nullable=False, server_default="268435456"))
    for table in (s.artifacts, s.upload_slots, s.workspace_leases, s.workspace_versions):
        table.create(op.get_bind())
        predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
        op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')


def downgrade():
    raise RuntimeError("Destructive platform downgrade is disabled; use a reviewed recovery plan")
