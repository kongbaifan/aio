"""Private filesystem checkpoints for safe generation handoff at approval boundaries."""

from alembic import op
from sqlalchemy import Column, Uuid
from app.db import schema_v9 as s

revision = "0009_workspace_handoff"
down_revision = "0008_team"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_aio_runs_workspace_scope", "aio_runs", ["org_id", "id", "project_id"])
    op.create_unique_constraint("uq_aio_sandbox_checkpoint_scope", "aio_sandbox_leases", ["org_id", "run_id", "id"])
    table = s.workspace_checkpoints
    table.create(op.get_bind())
    predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
    op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')
    op.add_column("aio_workspace_leases", Column("resume_checkpoint_id", Uuid))
    op.create_foreign_key(
        "fk_aio_workspace_resume_checkpoint",
        "aio_workspace_leases",
        table.name,
        ["org_id", "run_id", "project_id", "resume_checkpoint_id"],
        ["org_id", "run_id", "project_id", "id"],
    )


def downgrade():
    raise RuntimeError("Destructive workspace checkpoint downgrade is not supported")
