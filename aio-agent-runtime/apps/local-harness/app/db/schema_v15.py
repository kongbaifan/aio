"""Schema v15: a pending index scoped to audit archive delivery, separate from other outbox kinds."""

from sqlalchemy import Index, MetaData, Table, text

from . import schema_v14 as v14

metadata = MetaData(naming_convention=v14.metadata.naming_convention)
for original in v14.metadata.tables.values():
    original.to_metadata(metadata)
for name, original in vars(v14).items():
    if isinstance(original, Table):
        globals()[name] = metadata.tables[original.name]

audit = metadata.tables["aio_audit_events"]
outbox = metadata.tables["aio_outbox"]

ARCHIVE_KIND = "audit.archive"
# Other kinds (run.event.available, ...) have no consumer yet and stay pending; the v14 pending index
# would make every relay claim scan past them. Literal predicate: migration snapshots never import app code.
Index(
    "ix_aio_outbox_audit_pending", outbox.c.org_id, outbox.c.next_attempt_at, outbox.c.id,
    postgresql_where=text("delivered_at IS NULL AND kind = 'audit.archive'"),
)

BOOTSTRAP_TABLES = v14.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
