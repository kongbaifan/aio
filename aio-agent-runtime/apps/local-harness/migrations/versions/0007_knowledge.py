"""Isolated knowledge ingestion, current document ACL, pgvector retrieval and embedding receipts."""

from alembic import op
from sqlalchemy import Column, text
from sqlalchemy.dialects.postgresql import JSONB
from app.db import schema_v7 as s

revision = "0007_knowledge"
down_revision = "0006_mcp"
branch_labels = None
depends_on = None


def upgrade():
    # Must be installed by the migration operator; runtime cannot install extensions.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for name in ("aio_runs", "aio_artifacts"):
        op.add_column(name, Column("knowledge_source_refs", JSONB, nullable=False, server_default=text("'[]'::jsonb")))
    tables = (
        s.embedding_models,
        s.knowledge_bases,
        s.knowledge_documents,
        s.knowledge_versions,
        s.knowledge_jobs,
        s.knowledge_chunks,
        s.knowledge_queries,
        s.knowledge_citations,
        s.embedding_calls,
        s.embedding_ledger,
    )
    for table in tables:
        table.create(op.get_bind())
        predicate = "org_id = NULLIF(current_setting('aio.org_id', true), '')::uuid"
        op.execute(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table.name}" FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY tenant_scope ON "{table.name}" USING ({predicate}) WITH CHECK ({predicate})')
    op.create_foreign_key(
        "fk_aio_knowledge_document_version",
        "aio_knowledge_documents",
        "aio_knowledge_versions",
        ["org_id", "id", "current_version_id"],
        ["org_id", "document_id", "id"],
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade():
    raise RuntimeError("Destructive knowledge/provenance downgrade is not supported")
