"""ACL-filtered exact pgvector + bilingual lexical retrieval with server-minted citations."""

import asyncio
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select, update

from ..db import schema as s
from ..platform_errors import PlatformError
from ..policy.repository import current_facts, require_resource
from ..runtime.actions import canonical_digest
from .catalog import (
    current_embedding,
    current_knowledge,
    current_version,
    document_predicate,
    merge_sources,
    readable_versions,
)
from .text import terms


class KnowledgeRetrieval:
    def __init__(self, database, execution, embedder=None):
        self.db, self.execution, self.embedder = database, execution, embedder

    def prepare(self, p, knowledge_id, query, key, limit, handle=None):
        if not isinstance(query, str) or not query.strip() or len(query.encode()) > 8192 or not 1 <= limit <= 10:
            raise PlatformError("INVALID_QUERY", "Knowledge query is outside its bounded contract", 422)
        if handle:
            with self.execution.locked(handle) as (c, run, job, now, facts):
                manifest = self.execution._manifest(c, run)
                matches = [
                    item for item in manifest.get("knowledge_snapshot", []) if item.get("id") == str(knowledge_id)
                ]
                if len(matches) != 1:
                    raise PlatformError(
                        "KNOWLEDGE_SCOPE_DENIED", "Knowledge base is not in this Run's fixed scope", 403
                    )
                allowed = set(matches[0]["version_ids"])
                versions = [id for id in readable_versions(c, p, knowledge_id) if str(id) in allowed]
                return self._insert_query(c, p, knowledge_id, query, key, limit, versions, run, handle)
        with self.db.transaction(p) as c:
            current_facts(c, p)
            versions = readable_versions(c, p, knowledge_id)
            return self._insert_query(c, p, knowledge_id, query, key, limit, versions)

    @staticmethod
    def _insert_query(c, p, knowledge_id, query, key, limit, versions, run=None, handle=None):
        kb = current_knowledge(c, p, knowledge_id)
        # Interactive browser preview is explicitly lexical; only durable Worker Runs send embedding requests.
        model = current_embedding(c, p, kb["embedding_model_id"]) if kb["embedding_model_id"] and run else None
        hashed = canonical_digest(
            "aio-knowledge-query-v1", {"knowledge_id": str(knowledge_id), "query": query, "limit": limit}
        )
        prior = (
            c.execute(
                select(s.knowledge_queries).where(
                    s.knowledge_queries.c.org_id == p.org_id,
                    s.knowledge_queries.c.requested_by == p.user_id,
                    s.knowledge_queries.c.request_key == key,
                )
            )
            .mappings()
            .first()
        )
        if prior:
            if prior["query_digest"] != hashed or prior["run_id"] != (run["id"] if run else None):
                raise PlatformError("IDEMPOTENCY_CONFLICT", "Query key belongs to another search intention", 409)
            return {**dict(prior), "embedding_model_id": model["id"] if model else None}
        count = c.execute(
            select(func.count())
            .select_from(s.knowledge_queries)
            .where(s.knowledge_queries.c.org_id == p.org_id, s.knowledge_queries.c.requested_by == p.user_id)
        ).scalar_one()
        if count >= 5000:
            raise PlatformError("KNOWLEDGE_QUERY_QUOTA", "Query/citation retention quota is exhausted", 429)
        id = uuid4()
        row = {
            "org_id": p.org_id,
            "id": id,
            "knowledge_id": knowledge_id,
            "requested_by": p.user_id,
            "membership_revision": p.membership_revision,
            "run_id": run["id"] if run else None,
            "generation": handle.generation if handle else None,
            "request_key": key,
            "query_digest": hashed,
            "query": query,
            "top_k": limit,
            "version_ids": [str(id) for id in versions],
            "state": "embedding" if model and versions else "preparing",
            "result_ids": [],
        }
        c.execute(insert(s.knowledge_queries).values(**row))
        return {**row, "embedding_model_id": model["id"] if model else None}

    @staticmethod
    def _base(c, p, query):
        current_knowledge(c, p, query["knowledge_id"])
        return (
            select(
                s.knowledge_chunks,
                s.knowledge_documents.c.id.label("document_id"),
                s.knowledge_documents.c.title,
                s.knowledge_versions.c.number,
            )
            .select_from(s.knowledge_chunks)
            .join(
                s.knowledge_versions,
                (s.knowledge_versions.c.org_id == s.knowledge_chunks.c.org_id)
                & (s.knowledge_versions.c.id == s.knowledge_chunks.c.version_id),
            )
            .join(
                s.knowledge_documents,
                (s.knowledge_documents.c.org_id == s.knowledge_versions.c.org_id)
                & (s.knowledge_documents.c.id == s.knowledge_versions.c.document_id)
                & (s.knowledge_documents.c.current_version_id == s.knowledge_versions.c.id),
            )
            .join(
                s.resources,
                (s.resources.c.org_id == s.knowledge_documents.c.org_id)
                & (s.resources.c.id == s.knowledge_documents.c.id),
            )
            .where(
                document_predicate(c, p, query["knowledge_id"]),
                s.knowledge_versions.c.state == "ready",
                s.knowledge_chunks.c.version_id.in_([UUID(id) for id in query["version_ids"]]),
            )
        )

    def rank(self, p, id):
        with self.db.transaction(p) as c:
            query = (
                c.execute(
                    select(s.knowledge_queries).where(
                        s.knowledge_queries.c.org_id == p.org_id, s.knowledge_queries.c.id == id
                    )
                )
                .mappings()
                .one()
            )
            if query["requested_by"] != p.user_id:
                raise PlatformError("RESOURCE_NOT_FOUND", "Query is private", 404)
            kb = current_knowledge(c, p, query["knowledge_id"])
            if query["state"] == "embedding" and query["query_vector"] is None:
                raise PlatformError(
                    "EMBEDDING_RESULT_UNAVAILABLE", "Hybrid query did not retain an authorized embedding result", 409
                )
            base = self._base(c, p, query)
            query_terms = terms(query["query"])
            lexical, dense = [], []
            if query_terms:
                word = func.unnest(s.knowledge_chunks.c.terms).table_valued("word").render_derived(name="query_words")
                score = (
                    select(func.count())
                    .select_from(word)
                    .where(word.c.word.in_(query_terms))
                    .correlate(s.knowledge_chunks)
                    .scalar_subquery()
                )
                lexical = (
                    c.execute(
                        base.add_columns(score.label("score"))
                        .where(s.knowledge_chunks.c.terms.overlap(query_terms))
                        .order_by(score.desc(), s.knowledge_chunks.c.id)
                        .limit(80)
                    )
                    .mappings()
                    .all()
                )
            if query["query_vector"] is not None:
                model = current_embedding(c, p, kb["embedding_model_id"])
                distance = s.knowledge_chunks.c.embedding.cosine_distance(query["query_vector"])
                dense = (
                    c.execute(
                        base.where(
                            s.knowledge_chunks.c.embedding.is_not(None),
                            s.knowledge_chunks.c.embedding_model_id == model["id"],
                        )
                        .order_by(distance, s.knowledge_chunks.c.id)
                        .limit(80)
                    )
                    .mappings()
                    .all()
                )
            scores, rows = {}, {}
            for branch in (lexical, dense):
                for rank, row in enumerate(branch, 1):
                    scores[row["id"]] = scores.get(row["id"], 0) + 1 / (60 + rank)
                    rows[row["id"]] = dict(row)
            ordered = sorted(scores, key=lambda id: (-scores[id], str(id)))[: query["top_k"]]
            # Text and vectors are selected only after current SQL ACL and frozen version intersection.
            return [
                {
                    key: rows[id][key]
                    for key in ("id", "version_id", "document_id", "title", "number", "content", "location", "digest")
                }
                for id in ordered
            ]

    def save(self, p, query_id, matches, handle=None):
        if handle:
            with self.execution.locked(handle) as (c, run, job, now, facts):
                return self._save(c, p, query_id, matches, run)
        with self.db.transaction(p) as c:
            current_facts(c, p)
            return self._save(c, p, query_id, matches)

    @staticmethod
    def _save(c, p, query_id, matches, run=None):
        query = (
            c.execute(
                select(s.knowledge_queries)
                .where(s.knowledge_queries.c.org_id == p.org_id, s.knowledge_queries.c.id == query_id)
                .with_for_update()
            )
            .mappings()
            .one()
        )
        if query["requested_by"] != p.user_id or query["run_id"] != (run["id"] if run else None):
            raise PlatformError("RESOURCE_NOT_FOUND", "Query scope is invalid", 404)
        if query["state"] == "completed":
            return
        sources, citations = [], []
        for number, match in enumerate(matches, 1):
            version, document = current_version(c, p, match["version_id"])
            if str(version["id"]) not in query["version_ids"] or version["document_id"] != match["document_id"]:
                raise PlatformError("KNOWLEDGE_SCOPE_DENIED", "Result is not in the fixed query scope", 403)
            id = uuid4()
            c.execute(
                insert(s.knowledge_citations).values(
                    org_id=p.org_id,
                    id=id,
                    query_id=query_id,
                    chunk_id=match["id"],
                    version_id=version["id"],
                    ordinal=number,
                )
            )
            citations.append(str(id))
            sources.append({"document_id": str(document["id"]), "version_id": str(version["id"])})
        if run:
            merged = merge_sources(run["knowledge_source_refs"], sources)
            c.execute(
                update(s.runs)
                .where(s.runs.c.org_id == p.org_id, s.runs.c.id == run["id"])
                .values(knowledge_source_refs=merged)
            )
        c.execute(
            update(s.knowledge_queries)
            .where(s.knowledge_queries.c.org_id == p.org_id, s.knowledge_queries.c.id == query_id)
            .values(state="completed", result_ids=citations)
        )

    @staticmethod
    def citation(c, p, id):
        row = (
            c.execute(
                select(
                    s.knowledge_citations,
                    s.knowledge_queries.c.requested_by,
                    s.knowledge_queries.c.run_id,
                    s.knowledge_chunks.c.content,
                    s.knowledge_chunks.c.location,
                )
                .join(
                    s.knowledge_queries,
                    (s.knowledge_queries.c.org_id == s.knowledge_citations.c.org_id)
                    & (s.knowledge_queries.c.id == s.knowledge_citations.c.query_id),
                )
                .join(
                    s.knowledge_chunks,
                    (s.knowledge_chunks.c.org_id == s.knowledge_citations.c.org_id)
                    & (s.knowledge_chunks.c.id == s.knowledge_citations.c.chunk_id),
                )
                .where(s.knowledge_citations.c.org_id == p.org_id, s.knowledge_citations.c.id == id)
            )
            .mappings()
            .first()
        )
        if row is None or row["requested_by"] != p.user_id:
            raise PlatformError("RESOURCE_NOT_FOUND", "Citation is not accessible", 404)
        if row["run_id"]:
            require_resource(c, p, row["run_id"], "run.read")
        version, document = current_version(c, p, row["version_id"])
        return {
            "id": str(row["id"]),
            "label": "K-" + row["id"].hex[:12],
            "document_id": str(document["id"]),
            "version_id": str(version["id"]),
            "title": document["title"],
            "filename": version["filename"],
            "version": version["number"],
            "location": row["location"],
            "text": row["content"],
            "download_url": "/api/v2/knowledge/versions/" + str(version["id"]) + "/download",
        }

    def result(self, p, query_id):
        with self.db.transaction(p) as c:
            query = (
                c.execute(
                    select(s.knowledge_queries).where(
                        s.knowledge_queries.c.org_id == p.org_id, s.knowledge_queries.c.id == query_id
                    )
                )
                .mappings()
                .one()
            )
            if query["requested_by"] != p.user_id or query["state"] != "completed":
                raise PlatformError("KNOWLEDGE_QUERY_INCOMPLETE", "Query is not ready for this identity", 409)
            current_knowledge(c, p, query["knowledge_id"])
            matches = [self.citation(c, p, UUID(id)) for id in query["result_ids"]]
            return {
                "query_id": str(query_id),
                "matches": matches,
                "answerable": bool(matches),
                "retrieval_mode": "hybrid" if query["query_vector"] is not None else "lexical",
                "untrusted_reference_data": True,
                "guidance": "仅使用实际片段作为证据；无结果时说明资料不足，不编造引用。",
            }

    def get_citation(self, p, id):
        with self.db.transaction(p) as c:
            current_facts(c, p)
            return self.citation(c, p, id)

    async def search(self, p, knowledge_id, query, key, limit=5, handle=None):
        row = await asyncio.to_thread(self.prepare, p, knowledge_id, query, key, limit, handle)
        if row["state"] != "completed":
            if row["embedding_model_id"] and row["version_ids"]:
                if self.embedder is None:
                    raise PlatformError(
                        "EMBEDDING_UNAVAILABLE", "An approved embedding client is required for hybrid retrieval", 503
                    )
                await self.embedder.query(p, row["id"], query, handle)
            matches = await asyncio.to_thread(self.rank, p, row["id"])
            await asyncio.to_thread(self.save, p, row["id"], matches, handle)
        return await asyncio.to_thread(self.result, p, row["id"])

    @staticmethod
    def run_references(c, p, run_id):
        ids = c.execute(
            select(s.knowledge_citations.c.id)
            .join(
                s.knowledge_queries,
                (s.knowledge_queries.c.org_id == s.knowledge_citations.c.org_id)
                & (s.knowledge_queries.c.id == s.knowledge_citations.c.query_id),
            )
            .where(s.knowledge_queries.c.org_id == p.org_id, s.knowledge_queries.c.run_id == run_id)
            .order_by(s.knowledge_citations.c.created_at, s.knowledge_citations.c.id)
            .limit(64)
        ).scalars()
        return [
            {key: value for key, value in KnowledgeRetrieval.citation(c, p, id).items() if key != "text"} for id in ids
        ]


class KnowledgeDriver:
    def __init__(self, retrieval):
        self.retrieval = retrieval

    async def execute(self, permit):
        return await self.retrieval.search(
            permit.handle.principal,
            UUID(permit.config["knowledge_id"]),
            permit.arguments["query"],
            "run:" + permit.operation_key,
            5,
            permit.handle,
        )
