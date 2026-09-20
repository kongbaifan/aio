"""Immutable Skill versions, isolated validation jobs and inherited capability sources."""

from alembic import op
from sqlalchemy import Column, text
from sqlalchemy.dialects.postgresql import JSONB
from app.db import schema_v5 as s

revision = "0005_skills"
down_revision = "0004_departments"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("aio_runs", "aio_artifacts"):
        op.add_column(name, Column("capability_source_ids", JSONB, nullable=False, server_default=text("'[]'::jsonb")))
        op.add_column(
            name, Column("capability_read_source_ids", JSONB, nullable=False, server_default=text("'[]'::jsonb"))
        )
    for table in (s.skill_versions, s.skill_validation_jobs):
        table.create(op.get_bind())
        predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
        op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')


def downgrade():
    raise RuntimeError("Destructive Skill/provenance downgrade is not supported")
