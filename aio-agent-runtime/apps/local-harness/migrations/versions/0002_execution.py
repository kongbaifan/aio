"""Durable execution, model-call accounting and versioned tool definitions."""

from alembic import op
from sqlalchemy import Column
from app.db import schema_v2 as s

revision = "0002_execution"
down_revision = "0001_platform"
branch_labels = None
depends_on = None


def upgrade():
    column = s.metadata.tables["aio_runs"].c.checkpoint_seq
    op.add_column(
        "aio_runs", Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default)
    )
    column = s.metadata.tables["aio_jobs"].c.attempt_count
    op.add_column(
        "aio_jobs", Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default)
    )
    column = s.metadata.tables["aio_invocations"].c.arguments
    op.add_column(
        "aio_invocations",
        Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default),
    )
    column = s.metadata.tables["aio_invocations"].c.definition_digest
    op.add_column(
        "aio_invocations",
        Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default),
    )
    column = s.metadata.tables["aio_dispatches"].c.operation_key
    op.add_column(
        "aio_dispatches",
        Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default),
    )
    column = s.metadata.tables["aio_dispatches"].c.sent_at
    op.add_column(
        "aio_dispatches",
        Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default),
    )
    column = s.metadata.tables["aio_dispatches"].c.finished_at
    op.add_column(
        "aio_dispatches",
        Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default),
    )
    column = s.metadata.tables["aio_dispatches"].c.outcome_digest
    op.add_column(
        "aio_dispatches",
        Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default),
    )
    column = s.metadata.tables["aio_workspace_blockers"].c.resolved_by
    op.add_column(
        "aio_workspace_blockers",
        Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default),
    )
    column = s.metadata.tables["aio_workspace_blockers"].c.resolution
    op.add_column(
        "aio_workspace_blockers",
        Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default),
    )
    column = s.jobs.c.recovery_count
    op.add_column(
        "aio_jobs", Column(column.name, column.type, nullable=column.nullable, server_default=column.server_default)
    )
    for table in (s.tool_versions, s.model_configs, s.model_calls):
        table.create(op.get_bind())
        predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
        op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')
    for table in (s.dispatches, s.blockers):
        for index in table.indexes:
            if index.name in {"uq_aio_dispatch_active", "uq_aio_unresolved_blocker"}:
                index.create(op.get_bind())


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; use a reviewed forward-fix or recovery procedure")
