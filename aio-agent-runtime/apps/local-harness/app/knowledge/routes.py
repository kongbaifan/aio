import asyncio
from urllib.parse import quote
from uuid import UUID

from fastapi import Depends, Request
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select, update

from ..api.v2.contracts import RequestContract
from ..db import schema as s
from ..platform_errors import PlatformError
from ..policy.repository import current_facts, db_now
from .catalog import current_document
from .contracts import (
    KnowledgeCreate,
    DocumentCreate,
    DocumentVisibility,
    KnowledgeSearch,
    EmbeddingCreate,
    EmbeddingReconciliation,
)


class DocumentDelete(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)


class IngestionRetry(RequestContract):
    expected_generation: int = Field(ge=0, strict=True)


def register_knowledge_routes(app, service, retrieval, jobs, billing, principal):
    @app.get("/api/v2/knowledge/options")
    async def options(identity=Depends(principal)):
        return {
            "parser_profiles": list(service.settings.document_profiles),
            "formats": ["txt", "md", "csv", "pdf", "docx", "xlsx"],
        }

    @app.get("/api/v2/knowledge")
    async def bases(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(service.list, identity)}

    @app.post("/api/v2/knowledge", status_code=201)
    async def create(body: KnowledgeCreate, identity=Depends(principal)):
        return await asyncio.to_thread(service.create, identity, body)

    @app.get("/api/v2/knowledge/{knowledge_id}")
    async def detail(knowledge_id: UUID, identity=Depends(principal)):
        return await asyncio.to_thread(service.detail, identity, knowledge_id)

    @app.get("/api/v2/knowledge/{knowledge_id}/documents")
    async def documents(knowledge_id: UUID, identity=Depends(principal)):
        return {"items": await asyncio.to_thread(service.documents, identity, knowledge_id)}

    @app.post("/api/v2/knowledge/{knowledge_id}/documents", status_code=201)
    async def upload_slot(knowledge_id: UUID, body: DocumentCreate, identity=Depends(principal)):
        return await asyncio.to_thread(service.prepare_upload, identity, knowledge_id, body)

    @app.put("/api/v2/knowledge/uploads/{version_id}/content")
    async def upload(version_id: UUID, request: Request, identity=Depends(principal)):
        data = await request.body()
        return await asyncio.to_thread(service.upload, identity, version_id, data)

    @app.patch("/api/v2/knowledge/documents/{document_id}/visibility")
    async def visibility(document_id: UUID, body: DocumentVisibility, identity=Depends(principal)):
        return await asyncio.to_thread(service.visibility, identity, document_id, body)

    @app.delete("/api/v2/knowledge/documents/{document_id}")
    async def remove(document_id: UUID, body: DocumentDelete, identity=Depends(principal)):
        return await asyncio.to_thread(service.delete_document, identity, document_id, body.expected_revision)

    @app.get("/api/v2/knowledge/versions/{version_id}/download")
    async def download(version_id: UUID, identity=Depends(principal)):
        metadata, data = await asyncio.to_thread(service.download, identity, version_id)
        return Response(
            data,
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(metadata["filename"], safe="")},
        )

    @app.post("/api/v2/knowledge/{knowledge_id}/search")
    async def search(knowledge_id: UUID, body: KnowledgeSearch, identity=Depends(principal)):
        return await retrieval.search(identity, knowledge_id, body.query, "preview:" + str(body.request_id), body.limit)

    @app.get("/api/v2/knowledge/citations/{citation_id}")
    async def citation(citation_id: UUID, identity=Depends(principal)):
        return await asyncio.to_thread(retrieval.get_citation, identity, citation_id)

    @app.get("/api/v2/embedding-models")
    async def embedding_models(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(service.embedding_models, identity)}

    @app.post("/api/v2/admin/embedding-models", status_code=201)
    async def create_embedding(body: EmbeddingCreate, identity=Depends(principal)):
        return await asyncio.to_thread(service.create_embedding_model, identity, body)

    def job_info(p, id):
        with service.db.transaction(p) as c:
            current_facts(c, p)
            row = (
                c.execute(
                    select(s.knowledge_jobs).where(s.knowledge_jobs.c.org_id == p.org_id, s.knowledge_jobs.c.id == id)
                )
                .mappings()
                .first()
            )
            if row is None or row["requested_by"] != p.user_id:
                raise PlatformError("RESOURCE_NOT_FOUND", "Ingestion status is private", 404)
            return {
                key: row[key]
                for key in (
                    "id",
                    "version_id",
                    "state",
                    "phase",
                    "generation",
                    "cleanup_state",
                    "export_acknowledged",
                    "error_code",
                    "created_at",
                    "finished_at",
                )
            }

    @app.get("/api/v2/knowledge/jobs/{job_id}")
    async def job(job_id: UUID, identity=Depends(principal)):
        return await asyncio.to_thread(job_info, identity, job_id)

    def retry(p, id, expected):
        with service.write(p) as c:
            job = (
                c.execute(
                    select(s.knowledge_jobs)
                    .where(s.knowledge_jobs.c.org_id == p.org_id, s.knowledge_jobs.c.id == id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if job is None or job["requested_by"] != p.user_id or job["generation"] != expected:
                raise PlatformError("REVISION_CONFLICT", "Ingestion retry state changed", 409)
            version = (
                c.execute(
                    select(s.knowledge_versions).where(
                        s.knowledge_versions.c.org_id == p.org_id, s.knowledge_versions.c.id == job["version_id"]
                    )
                )
                .mappings()
                .one()
            )
            current_document(c, p, version["document_id"], write=True)
            if (
                job["state"] != "failed"
                or job["cleanup_state"] != "confirmed"
                or (job["spec"] and not job["export_acknowledged"])
            ):
                raise PlatformError(
                    "INGESTION_RETRY_BLOCKED", "Resolve unknown results and confirm parser cleanup first", 409
                )
            if c.execute(
                select(s.embedding_calls.c.id).where(
                    s.embedding_calls.c.org_id == p.org_id,
                    s.embedding_calls.c.job_id == id,
                    s.embedding_calls.c.state.in_(["started", "unknown", "resolved"]),
                )
            ).first():
                raise PlatformError(
                    "EMBEDDING_RETRY_BLOCKED", "A billed/unknown embedding request cannot be blindly repeated", 409
                )
            c.execute(
                update(s.knowledge_jobs)
                .where(s.knowledge_jobs.c.id == id)
                .values(
                    state="queued",
                    queued_at=db_now(c),
                    spec=None if job["phase"] == "parse" else job["spec"],
                    spec_digest=None if job["phase"] == "parse" else job["spec_digest"],
                    deadline_at=None,
                    error_code=None,
                    result_sha256=None if job["phase"] == "parse" else job["result_sha256"],
                    export_acknowledged=False if job["phase"] == "parse" else True,
                    cleanup_state="not_required" if job["phase"] == "parse" else "confirmed",
                    membership_revision=p.membership_revision,
                )
            )
            c.execute(
                update(s.knowledge_versions)
                .where(s.knowledge_versions.c.id == version["id"])
                .values(state="queued" if job["phase"] == "parse" else "indexing")
            )
            return {"id": id, "state": "queued"}

    @app.post("/api/v2/knowledge/jobs/{job_id}/retry", status_code=202)
    async def retry_job(job_id: UUID, body: IngestionRetry, identity=Depends(principal)):
        return await asyncio.to_thread(retry, identity, job_id, body.expected_generation)

    @app.get("/api/v2/admin/embedding-calls")
    async def embedding_usage(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(billing.pending, identity)}

    @app.post("/api/v2/admin/embedding-calls/{call_id}/reconcile")
    async def reconcile(call_id: UUID, body: EmbeddingReconciliation, identity=Depends(principal)):
        return await asyncio.to_thread(billing.reconcile, identity, call_id, body.amount, body.evidence_ref)
