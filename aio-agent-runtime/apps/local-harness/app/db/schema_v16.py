"""Schema v16: emergency kill switches (GOV-04). Organization-scoped; no global/platform scope."""

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKeyConstraint, Index, Integer, MetaData, String, Table,
    UniqueConstraint, Uuid, text,
)

from . import schema_v15 as v15

metadata = MetaData(naming_convention=v15.metadata.naming_convention)
for original in v15.metadata.tables.values():
    original.to_metadata(metadata)
for name, original in vars(v15).items():
    if isinstance(original, Table):
        globals()[name] = metadata.tables[original.name]

ARCHIVE_KIND = v15.ARCHIVE_KIND
SCOPES = ("organization", "user", "tool", "model", "agent", "execution_class")
EXECUTION_CLASSES = ("python", "mcp", "knowledge", "skill")
REASONS = ("SECURITY_INCIDENT", "DATA_EXPOSURE", "COST_RUNAWAY", "PROVIDER_INCIDENT", "OPERATOR_REQUEST")
RELEASE_COLUMNS = ("released_by", "released_at", "release_evidence_digest", "revision")

kill_switches = Table(
    "aio_kill_switches",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("scope", String(24), nullable=False),
    Column("target_id", Uuid),
    Column("execution_class", String(24)),
    Column("reason_code", String(32), nullable=False),
    Column("note_digest", String(64), nullable=False),
    Column("activated_by", Uuid, nullable=False),
    Column("activated_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("expires_at", DateTime(timezone=True)),
    Column("released_by", Uuid),
    Column("released_at", DateTime(timezone=True)),
    Column("release_evidence_digest", String(64)),
    Column("revision", Integer, nullable=False, server_default="0"),
    UniqueConstraint("org_id", "id"),
    ForeignKeyConstraint(["org_id"], ["aio_organizations.id"]),
    CheckConstraint("scope IN (" + ", ".join(f"'{v}'" for v in SCOPES) + ")", name="scope"),
    CheckConstraint(
        "(scope = 'organization' AND target_id IS NULL AND execution_class IS NULL)"
        " OR (scope IN ('user', 'tool', 'model', 'agent') AND target_id IS NOT NULL AND execution_class IS NULL)"
        " OR (scope = 'execution_class' AND target_id IS NULL AND execution_class IN ("
        + ", ".join(f"'{v}'" for v in EXECUTION_CLASSES) + "))",
        name="target",
    ),
    CheckConstraint("reason_code IN (" + ", ".join(f"'{v}'" for v in REASONS) + ")", name="reason"),
    CheckConstraint("note_digest ~ '^[0-9a-f]{64}$'", name="note_digest"),
    CheckConstraint(
        "(released_by IS NULL AND released_at IS NULL AND release_evidence_digest IS NULL)"
        " OR (released_by IS NOT NULL AND released_at IS NOT NULL AND release_evidence_digest ~ '^[0-9a-f]{64}$')",
        name="release",
    ),
    # Two-person rule enforced by the database, not only the service.
    CheckConstraint("released_by IS NULL OR released_by <> activated_by", name="separation"),
    CheckConstraint("expires_at IS NULL OR expires_at > activated_at", name="expiry"),
    CheckConstraint("revision >= 0", name="revision"),
)
Index("ix_aio_kill_switches_open", kill_switches.c.org_id, postgresql_where=kill_switches.c.released_at.is_(None))

# Audit facts about a switch name their own subject kind. v14's CHECK is replaced, still NOT VALID.
audit = metadata.tables["aio_audit_events"]
RESOURCE_KIND_CHECK = "ck_aio_audit_events_resource_kind"
RESOURCE_KIND_EXPRESSION = v15.v14.AUDIT_CHECKS["resource_kind"].replace("'embedding_call')", "'embedding_call', 'kill_switch')")
for constraint in list(audit.constraints):
    if getattr(constraint, "name", None) in {RESOURCE_KIND_CHECK, "resource_kind"}:
        audit.constraints.discard(constraint)
audit.append_constraint(CheckConstraint(RESOURCE_KIND_EXPRESSION, name="resource_kind", postgresql_not_valid=True))

BOOTSTRAP_TABLES = v15.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
