"""Current ACL before retrieval/citation/context use. Dataset sharing does not expose restricted documents."""

from uuid import UUID

from sqlalchemy import and_, false, or_, select

from ..db import schema as s
from ..platform_errors import PlatformError
from ..policy.repository import current_facts, require_resource, visible_resources
from ..runtime.actions import canonical_digest


def current_knowledge(c, p, id, action="knowledge.search"):
    require_resource(c, p, id, action)
    row = (
        c.execute(select(s.knowledge_bases).where(s.knowledge_bases.c.org_id == p.org_id, s.knowledge_bases.c.id == id))
        .mappings()
        .first()
    )
    if row is None:
        raise PlatformError("RESOURCE_NOT_FOUND", "Knowledge base is not accessible", 404)
    return dict(row)


def current_embedding(c, p, id):
    require_resource(c, p, id, "embedding_model.use")
    row = (
        c.execute(
            select(s.embedding_models).where(s.embedding_models.c.org_id == p.org_id, s.embedding_models.c.id == id)
        )
        .mappings()
        .first()
    )
    if row is None or row["digest"] != canonical_digest(
        "aio-embedding-model-v1", {"model": row["model"], "config": row["config"]}
    ):
        raise PlatformError("EMBEDDING_MODEL_UNAVAILABLE", "Embedding model version is unavailable", 403)
    return dict(row)


def document_query():
    return select(
        s.knowledge_documents,
        s.resources.c.owner_id,
        s.resources.c.revision,
        s.resources.c.status.label("resource_status"),
        s.resources.c.classification,
    ).join(
        s.resources,
        (s.resources.c.org_id == s.knowledge_documents.c.org_id) & (s.resources.c.id == s.knowledge_documents.c.id),
    )


def document_predicate(c, p, knowledge_id):
    facts = current_facts(c, p)
    if "document.read" in facts.denied_actions:
        return false()
    direct = visible_resources(c, p, "document", "document.read")
    return and_(
        s.knowledge_documents.c.org_id == p.org_id,
        s.knowledge_documents.c.knowledge_id == knowledge_id,
        s.knowledge_documents.c.state == "active",
        s.resources.c.kind == "document",
        s.resources.c.status == "active",
        s.resources.c.classification.in_(facts.allowed_classifications),
        or_(s.knowledge_documents.c.visibility == "inherited", direct),
    )


def current_document(c, p, id, *, write=False, lock=False):
    query = document_query().where(s.knowledge_documents.c.org_id == p.org_id, s.knowledge_documents.c.id == id)
    row = c.execute(query.with_for_update() if lock else query).mappings().first()
    if row is None or row["state"] != "active":
        raise PlatformError("RESOURCE_NOT_FOUND", "Document is not available", 404)
    current_knowledge(c, p, row["knowledge_id"], "knowledge.update" if write else "knowledge.search")
    facts = current_facts(c, p)
    if write:
        require_resource(c, p, id, "document.update", facts=facts)
    elif row["visibility"] != "inherited":
        require_resource(c, p, id, "document.read", facts=facts)
    elif (
        row["resource_status"] != "active"
        or row["classification"] not in facts.allowed_classifications
        or "document.read" in facts.denied_actions
    ):
        raise PlatformError("DOCUMENT_ACCESS_DENIED", "Document policy does not permit access", 403)
    return dict(row)


def current_version(c, p, id, *, ready=True, write=False):
    row = (
        c.execute(
            select(s.knowledge_versions).where(
                s.knowledge_versions.c.org_id == p.org_id, s.knowledge_versions.c.id == id
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise PlatformError("RESOURCE_NOT_FOUND", "Document version is not available", 404)
    document = current_document(c, p, row["document_id"], write=write)
    if row["state"] == "deleted" or (ready and (row["state"] != "ready" or document["current_version_id"] != id)):
        raise PlatformError("KNOWLEDGE_SOURCE_CHANGED", "Document version was removed, replaced or is not ready", 403)
    return dict(row), document


def readable_versions(c, p, knowledge_id):
    current_knowledge(c, p, knowledge_id)
    rows = (
        c.execute(
            select(s.knowledge_versions.c.id)
            .select_from(s.knowledge_documents)
            .join(
                s.resources,
                (s.resources.c.org_id == s.knowledge_documents.c.org_id)
                & (s.resources.c.id == s.knowledge_documents.c.id),
            )
            .join(
                s.knowledge_versions,
                (s.knowledge_versions.c.org_id == s.knowledge_documents.c.org_id)
                & (s.knowledge_versions.c.id == s.knowledge_documents.c.current_version_id),
            )
            .where(document_predicate(c, p, knowledge_id), s.knowledge_versions.c.state == "ready")
            .order_by(s.knowledge_versions.c.id)
            .limit(257)
        )
        .scalars()
        .all()
    )
    if len(rows) > 256:
        raise PlatformError("KNOWLEDGE_SCOPE_LIMIT", "Knowledge scope exceeds the bounded exact-retrieval limit", 409)
    return list(rows)


def snapshot(c, p, manifest):
    result = []
    for item in manifest.get("knowledge", []):
        row = current_knowledge(c, p, UUID(item["id"]))
        model = current_embedding(c, p, row["embedding_model_id"]) if row["embedding_model_id"] else None
        result.append(
            {
                "id": str(row["id"]),
                "index_revision": row["index_revision"],
                "version_ids": [str(id) for id in readable_versions(c, p, row["id"])],
                "embedding_model": {"id": str(model["id"]), "digest": model["digest"]} if model else None,
            }
        )
    if len(result) > 8:
        raise PlatformError("KNOWLEDGE_SCOPE_LIMIT", "Too many knowledge bases in this Agent", 409)
    return result


def merge_sources(*groups):
    pairs = {(str(item["document_id"]), str(item["version_id"])) for group in groups for item in group}
    if len(pairs) > 64:
        raise PlatformError("SOURCE_POLICY_LIMIT", "Too many independent document sources", 409)
    return [{"document_id": doc, "version_id": version} for doc, version in sorted(pairs)]


def require_sources(c, p, refs):
    if not isinstance(refs, list) or len(refs) > 64:
        raise PlatformError("SOURCE_POLICY_INVALID", "Document provenance is invalid", 409)
    for ref in refs:
        try:
            id, document_id = UUID(ref["version_id"]), UUID(ref["document_id"])
        except (KeyError, TypeError, ValueError, AttributeError):
            raise PlatformError("SOURCE_POLICY_INVALID", "Document source identity is invalid", 409) from None
        version, _ = current_version(c, p, id)
        if version["document_id"] != document_id:
            raise PlatformError("SOURCE_POLICY_INVALID", "Document source does not match its version", 409)
