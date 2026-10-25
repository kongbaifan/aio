"""Schema v14: immutable typed audit facts and separate delivery bookkeeping."""

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, Index, MetaData, String, Table, text

from . import schema_v13 as v13

metadata = MetaData(naming_convention=v13.metadata.naming_convention)
for original in v13.metadata.tables.values():
    original.to_metadata(metadata)
for name, original in vars(v13).items():
    if isinstance(original, Table):
        globals()[name] = metadata.tables[original.name]

audit = metadata.tables["aio_audit_events"]
outbox = metadata.tables["aio_outbox"]

AUDIT_COLUMNS = (
    "trace_id", "resource_kind", "decision", "reason_code", "policy_revision", "subject_revision",
    "risk_class", "metadata_schema",
)
for column in (
    Column("trace_id", String(64)),
    Column("resource_kind", String(32)),
    Column("decision", String(24)),
    Column("reason_code", String(64)),
    Column("policy_revision", BigInteger),
    Column("subject_revision", BigInteger),
    Column("risk_class", String(16)),
    Column("metadata_schema", String(64), nullable=False),
):
    audit.append_column(column)

AUDIT_CHECKS = {
    # DDL strings pass through text(): an unescaped ":v1" is a bind parameter and is rendered as NULL.
    "structured_metadata": "metadata_schema = action || '\\:v1' AND metadata_schema <> 'legacy'",
    "metadata_bound": "jsonb_typeof(metadata) = 'object' AND pg_column_size(metadata) <= 4096",
    "trace": "trace_id ~ '^[0-9a-f]{32}$' AND trace_id <> repeat('0', 32)",
    "decision": "decision IN ('allow', 'deny', 'approval_required')",
    "risk_class": "risk_class IN ('R0', 'R1', 'R2')",
    "revisions": "(policy_revision IS NULL OR policy_revision >= 0) AND (subject_revision IS NULL OR subject_revision >= 0)",
    "resource_kind": "resource_kind IN ('approval', 'tool', 'model', 'project', 'session', 'run', 'artifact', 'agent', "
    "'connection', 'mcp_server', 'knowledge', 'document', 'embedding_model', 'skill', 'skill_import', "
    "'organization', 'member', 'department', 'budget', 'invocation', 'model_call', 'embedding_call')",
}
for name, expression in AUDIT_CHECKS.items():
    # NOT VALID preserves historical free metadata without exempting ANY new insert.
    audit.append_constraint(CheckConstraint(expression, name=name, postgresql_not_valid=True))
Index("ix_aio_audit_org_created_id", audit.c.org_id, audit.c.created_at.desc(), audit.c.id)

OUTBOX_COLUMNS = ("next_attempt_at", "last_error_code", "lease_owner", "leased_until")
for column in (
    Column("next_attempt_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("last_error_code", String(64)),
    Column("lease_owner", String(128)),
    Column("leased_until", DateTime(timezone=True)),
):
    outbox.append_column(column)
OUTBOX_CHECKS = {
    "attempts": "attempts >= 0",
    "delivered_error": "last_error_code IS NULL OR delivered_at IS NULL",
}
for name, expression in OUTBOX_CHECKS.items():
    outbox.append_constraint(CheckConstraint(expression, name=name))
Index(
    "ix_aio_outbox_pending", outbox.c.org_id, outbox.c.next_attempt_at,
    postgresql_where=outbox.c.delivered_at.is_(None),
)

BOOTSTRAP_TABLES = v13.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
