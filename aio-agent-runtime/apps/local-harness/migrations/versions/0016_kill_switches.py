"""Emergency kill switches. Schema only; no existing rows are read or rewritten."""

from alembic import op

from app.db import schema_v16 as s

revision = "0016_kill_switches"
down_revision = "0015_audit_archive"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    s.kill_switches.create(c)
    predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
    op.execute('ALTER TABLE "aio_kill_switches" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "aio_kill_switches" FORCE ROW LEVEL SECURITY')
    op.execute(f'CREATE POLICY tenant_scope ON "aio_kill_switches" USING ({predicate}) WITH CHECK ({predicate})')
    op.drop_constraint(op.f(s.RESOURCE_KIND_CHECK), "aio_audit_events", type_="check")
    op.create_check_constraint(
        op.f(s.RESOURCE_KIND_CHECK), "aio_audit_events", s.RESOURCE_KIND_EXPRESSION, postgresql_not_valid=True
    )


def downgrade():
    # Refuse to drop live emergency state: a downgrade must not silently re-enable a blocked capability.
    c = op.get_bind()
    from sqlalchemy import text

    if c.execute(text("SELECT row_security_active('aio_kill_switches'::regclass)")).scalar_one():
        raise RuntimeError("Kill switch downgrade requires an identity exempt from row level security")
    if c.execute(text("SELECT EXISTS(SELECT 1 FROM aio_kill_switches WHERE released_at IS NULL)")).scalar_one():
        raise RuntimeError("Cannot downgrade while an unreleased kill switch exists")
    if c.execute(text("SELECT EXISTS(SELECT 1 FROM aio_audit_events WHERE resource_kind = 'kill_switch')")).scalar_one():
        raise RuntimeError("Cannot downgrade while kill switch audit facts exist")
    op.drop_constraint(op.f(s.RESOURCE_KIND_CHECK), "aio_audit_events", type_="check")
    op.create_check_constraint(
        op.f(s.RESOURCE_KIND_CHECK), "aio_audit_events", s.v15.v14.AUDIT_CHECKS["resource_kind"], postgresql_not_valid=True
    )
    op.drop_table("aio_kill_switches")
