"""Same-Run plans, fenced step cursors and model/tool attribution."""

from alembic import op
from sqlalchemy import Column, String, Uuid
from app.db import schema_v8 as s

revision = "0008_team"
down_revision = "0007_knowledge"
branch_labels = None
depends_on = None


def upgrade():
    for table in (s.run_teams, s.run_steps):
        table.create(op.get_bind())
        predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
        op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')
    for name in ("aio_model_calls", "aio_invocations"):
        op.add_column(name, Column("team_step_id", Uuid))
        op.create_foreign_key(
            "fk_" + name + "_team_step",
            name,
            "aio_run_steps",
            ["org_id", "run_id", "team_step_id"],
            ["org_id", "run_id", "id"],
        )
    op.add_column("aio_model_calls", Column("team_stage", String(24)))
    op.create_check_constraint(
        "team_binding",
        "aio_model_calls",
        "(team_stage IS NULL AND team_step_id IS NULL) OR "
        "(team_stage IS NOT NULL AND ((team_stage IN ('planning','synthesis') AND team_step_id IS NULL) OR "
        "(team_stage = 'step' AND team_step_id IS NOT NULL)))",
    )


def downgrade():
    raise RuntimeError("Destructive team/checkpoint attribution downgrade is not supported")
