"""Schema snapshot v12: immutable private Skill archive intentions and fenced import jobs."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from . import schema_v11 as v11

metadata = MetaData(naming_convention=v11.metadata.naming_convention)
for original in v11.metadata.tables.values():
    original.to_metadata(metadata)
for name, original in vars(v11).items():
    if isinstance(original, Table):
        globals()[name] = metadata.tables[original.name]

skill_imports = Table(
    "aio_skill_imports",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("requested_by", Uuid, nullable=False),
    Column("membership_revision", Integer, nullable=False),
    Column("request_id", Uuid, nullable=False),
    Column("request_digest", String(64), nullable=False),
    Column("request", JSONB, nullable=False),
    Column("archive_sha256", String(64), nullable=False),
    Column("archive_size", BigInteger, nullable=False),
    Column("reserved_bytes", BigInteger, nullable=False),
    Column("upload_bound", Boolean, nullable=False, server_default=text("false")),
    Column("uploaded_at", DateTime(timezone=True)),
    Column("queue_expires_at", DateTime(timezone=True), nullable=False),
    Column("state", String(24), nullable=False, server_default="awaiting_upload"),
    Column("revision", Integer, nullable=False, server_default="0"),
    Column("scanner_profile", String(64), nullable=False),
    Column("scanner_image", String(128), nullable=False),
    Column("execution_profile", String(64), nullable=False),
    Column("execution_image", String(128), nullable=False),
    Column("generation", Integer, nullable=False, server_default="0"),
    Column("lease_owner", String(128)),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column("deadline_at", DateTime(timezone=True)),
    Column("spec", JSONB),
    Column("spec_digest", String(64)),
    Column("command", JSONB),
    Column("scan_receipt", JSONB),
    Column("candidate", JSONB),
    Column("candidate_digest", String(64)),
    Column("cleanup_state", String(24), nullable=False, server_default="confirmed"),
    Column("manager_acknowledged", Boolean, nullable=False, server_default=text("true")),
    Column("error_code", String(64)),
    Column("purge_requested", Boolean, nullable=False, server_default=text("false")),
    Column("archive_purged", Boolean, nullable=False, server_default=text("false")),
    Column("skill_id", Uuid),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("finished_at", DateTime(timezone=True)),
    UniqueConstraint("org_id", "id"),
    UniqueConstraint("org_id", "requested_by", "request_id"),
    ForeignKeyConstraint(["org_id", "id"], ["aio_resources.org_id", "aio_resources.id"]),
    ForeignKeyConstraint(["org_id", "requested_by"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
    ForeignKeyConstraint(["org_id", "skill_id"], ["aio_skill_versions.org_id", "aio_skill_versions.id"]),
    CheckConstraint(
        "state IN ('awaiting_upload','uploading','queued','leased','stopping','imported','rejected','cancelled')",
        name="state",
    ),
    CheckConstraint("cleanup_state IN ('pending','confirmed')", name="cleanup"),
    CheckConstraint(
        "archive_size > 0 AND archive_size <= 2097152 AND reserved_bytes >= 0 AND reserved_bytes <= archive_size",
        name="sizes",
    ),
    CheckConstraint("generation >= 0 AND revision >= 0 AND membership_revision >= 0", name="revisions"),
    CheckConstraint("state <> 'imported' OR skill_id IS NOT NULL", name="imported_skill"),
    CheckConstraint(
        "NOT archive_purged OR (reserved_bytes=0 AND cleanup_state='confirmed' AND manager_acknowledged)",
        name="purge_confirmed",
    ),
)
Index("ix_aio_skill_import_queue", skill_imports.c.org_id, skill_imports.c.state, skill_imports.c.created_at)
Index("ix_aio_skill_import_blob", skill_imports.c.org_id, skill_imports.c.archive_sha256)
BOOTSTRAP_TABLES = v11.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
