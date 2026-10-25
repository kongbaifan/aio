"""Typed append-only audit records; no historical facts are rewritten."""

from alembic import op
from sqlalchemy import DefaultClause, text
from app.db import schema_v14 as s

revision = "0014_audit_records"
down_revision = "0013_shared_budgets"
branch_labels = None
depends_on = None


def upgrade():
    for table, columns in ((s.audit, s.AUDIT_COLUMNS), (s.outbox, s.OUTBOX_COLUMNS)):
        for name in columns:
            column = table.c[name]._copy()
            if name == "metadata_schema":
                # The temporary constant default marks existing rows without guessing their semantics.
                column.server_default = DefaultClause("legacy")
            op.add_column(table.name, column)
    op.alter_column(s.audit.name, "metadata_schema", server_default=None)
    for table, checks in ((s.audit, s.AUDIT_CHECKS), (s.outbox, s.OUTBOX_CHECKS)):
        for name, expression in checks.items():
            op.create_check_constraint(
                op.f(f"ck_{table.name}_{name}"), table.name, expression,
                **({"postgresql_not_valid": True} if table is s.audit else {}),
            )
    for table, name in ((s.audit, "ix_aio_audit_org_created_id"), (s.outbox, "ix_aio_outbox_pending")):
        next(index for index in table.indexes if index.name == name).create(op.get_bind())


def downgrade():
    c = op.get_bind()
    # A scoped/zero-row RLS view is not evidence that other tenants have no v14 facts.
    if c.execute(text("SELECT row_security_active('aio_audit_events'::regclass)")).scalar_one():
        raise RuntimeError("Audit downgrade requires an identity exempt from row level security")
    if c.execute(text("SELECT EXISTS(SELECT 1 FROM aio_audit_events WHERE metadata_schema <> 'legacy')")).scalar_one():
        raise RuntimeError("Cannot downgrade while structured audit facts exist")
    for table, name in ((s.audit, "ix_aio_audit_org_created_id"), (s.outbox, "ix_aio_outbox_pending")):
        op.drop_index(name, table_name=table.name)
    for table, checks in ((s.audit, s.AUDIT_CHECKS), (s.outbox, s.OUTBOX_CHECKS)):
        for name in checks:
            op.drop_constraint(op.f(f"ck_{table.name}_{name}"), table.name, type_="check")
    for table, columns in ((s.audit, s.AUDIT_COLUMNS), (s.outbox, s.OUTBOX_COLUMNS)):
        for name in reversed(columns):
            op.drop_column(table.name, name)
