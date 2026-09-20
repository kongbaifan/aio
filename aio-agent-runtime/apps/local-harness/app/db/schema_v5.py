"""Schema snapshot v5: immutable Skill packages, durable isolated validation, capability provenance."""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    CheckConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from . import schema_v4 as v4

metadata = MetaData(naming_convention=v4.metadata.naming_convention)
for original in v4.metadata.tables.values():
    original.to_metadata(metadata)
for name, original in vars(v4).items():
    if isinstance(original, Table):
        globals()[name] = metadata.tables[original.name]

for table_name in ("aio_runs", "aio_artifacts"):
    metadata.tables[table_name].append_column(
        Column("capability_source_ids", JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    )
    metadata.tables[table_name].append_column(
        Column("capability_read_source_ids", JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    )

skill_versions = Table(
    "aio_skill_versions",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("name", String(64), nullable=False),
    Column("version", String(64), nullable=False),
    Column("digest", String(64), nullable=False),
    Column("package", JSONB, nullable=False),
    Column("file_manifest", JSONB, nullable=False),
    Column("byte_count", Integer, nullable=False),
    Column("profile_id", String(64), nullable=False),
    Column("image_digest", String(71), nullable=False),
    Column("owner_id", Uuid, nullable=False),
    Column("reviewer_id", Uuid),
    Column("state", String(24), nullable=False, server_default="draft"),
    Column("revision", Integer, nullable=False, server_default="0"),
    Column("review_note", String(1000)),
    Column("validation_job_id", Uuid),
    Column("published_tools", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("published_at", DateTime(timezone=True)),
    UniqueConstraint("org_id", "id"),
    UniqueConstraint("org_id", "name", "version"),
    ForeignKeyConstraint(["org_id", "id"], ["aio_resources.org_id", "aio_resources.id"]),
    ForeignKeyConstraint(["org_id", "owner_id"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
    ForeignKeyConstraint(["org_id", "reviewer_id"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
    CheckConstraint("state IN ('draft','validating','validated','rejected','published')", name="state"),
    CheckConstraint("byte_count BETWEEN 1 AND 262144", name="byte_count"),
)

skill_validation_jobs = Table(
    "aio_skill_validation_jobs",
    metadata,
    Column("org_id", Uuid, nullable=False),
    Column("id", Uuid, primary_key=True),
    Column("skill_id", Uuid, nullable=False),
    Column("requested_by", Uuid, nullable=False),
    Column("membership_revision", Integer, nullable=False),
    Column("generation", Integer, nullable=False, server_default="1"),
    Column("state", String(24), nullable=False, server_default="queued"),
    Column("lease_owner", String(128)),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column("deadline_at", DateTime(timezone=True)),
    Column("spec", JSONB),
    Column("commands", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("results", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("cleanup_state", String(24), nullable=False, server_default="not_required"),
    Column("error_code", String(64)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("finished_at", DateTime(timezone=True)),
    UniqueConstraint("org_id", "id"),
    ForeignKeyConstraint(["org_id", "skill_id"], ["aio_skill_versions.org_id", "aio_skill_versions.id"]),
    ForeignKeyConstraint(["org_id", "requested_by"], ["aio_memberships.org_id", "aio_memberships.user_id"]),
    CheckConstraint("state IN ('queued','leased','stopping','passed','failed')", name="state"),
    CheckConstraint("cleanup_state IN ('not_required','pending','confirmed')", name="cleanup_state"),
)
Index(
    "uq_aio_skill_validation_active",
    skill_validation_jobs.c.org_id,
    skill_validation_jobs.c.skill_id,
    unique=True,
    postgresql_where=skill_validation_jobs.c.state.in_(["queued", "leased", "stopping"]),
)

BOOTSTRAP_TABLES = v4.BOOTSTRAP_TABLES
TENANT_TABLES = tuple(t for t in metadata.tables.values() if t.name not in BOOTSTRAP_TABLES)
