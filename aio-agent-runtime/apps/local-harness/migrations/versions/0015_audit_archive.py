"""Audit archive delivery: scoped pending index and an outbox entry for every structured v14 fact."""

from alembic import op
from sqlalchemy import text

from app.db import schema_v15 as s
from app.db.migration_guard import require_unblinded_tenant_read

revision = "0015_audit_archive"
down_revision = "0014_audit_records"
branch_labels = None
depends_on = None

INDEX = "ix_aio_outbox_audit_pending"


def upgrade():
    c = op.get_bind()
    require_unblinded_tenant_read(c, "structured audit facts written under v14 would never be archived")
    next(index for index in s.outbox.indexes if index.name == INDEX).create(c)
    # Legacy rows carry free-form metadata with no closed contract, so they are not archived.
    # NOT EXISTS keeps a downgrade/upgrade cycle from enqueueing a fact twice.
    c.execute(text(
        "INSERT INTO aio_outbox (org_id, id, aggregate_id, kind, payload) "
        "SELECT a.org_id, gen_random_uuid(), a.id, 'audit.archive', '{}'::jsonb FROM aio_audit_events a "
        "WHERE a.metadata_schema <> 'legacy' AND NOT EXISTS ("
        "SELECT 1 FROM aio_outbox o WHERE o.org_id = a.org_id AND o.kind = 'audit.archive' "
        "AND o.aggregate_id = a.id)"
    ))


def downgrade():
    # Delivery entries are copies of append-only facts; v14 code ignores them, so they are kept.
    op.drop_index(INDEX, table_name=s.outbox.name)
