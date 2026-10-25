"""Durable isolated parsing with lease fencing, current source policy and atomic index publication."""

import base64
from contextlib import contextmanager
from datetime import timedelta, timezone
import hashlib
from uuid import UUID, uuid4

import rfc8785
from sqlalchemy import delete, insert, select, update, or_

from ..auth.principal import Principal
from ..db import schema as s
from ..observability import audit
from ..observability import redaction as m
from ..platform_errors import PlatformError
from ..policy.repository import db_now
from ..runtime.actions import canonical_digest, strict_json
from ..runtime.contracts import bounded_json
from .catalog import current_document, current_embedding, current_knowledge
from .text import terms

PARSER_COMMAND = "import runpy; runpy.run_module('aio_document_parser', run_name='__main__')"
PARSER_TIMEOUT = 60


class KnowledgeJobs:
    def __init__(self, database, settings, knowledge):
        self.db, self.settings, self.knowledge = database, settings, knowledge

    @staticmethod
    def principal(job):
        return Principal(
            job["org_id"],
            job["requested_by"],
            job["membership_revision"],
            service_actor_id=job["lease_owner"] or "knowledge-worker",
        )

    def source(self, c, job):
        p = self.principal(job)
        version = (
            c.execute(
                select(s.knowledge_versions).where(
                    s.knowledge_versions.c.org_id == job["org_id"], s.knowledge_versions.c.id == job["version_id"]
                )
            )
            .mappings()
            .one()
        )
        document = current_document(c, p, version["document_id"], write=True)
        kb = current_knowledge(c, p, version["knowledge_id"], "knowledge.update")
        if version["state"] not in {"queued", "parsing", "indexing"} or version["upload_state"] != "stored":
            raise PlatformError("DOCUMENT_SOURCE_CHANGED", "Document is not available for this ingestion", 403)
        if version["embedding_model_id"]:
            current_embedding(c, p, version["embedding_model_id"])
        return dict(version), document, kb

    @contextmanager
    def owned(self, handle, *, active=True):
        with self.db.scoped(handle["org_id"], handle["requested_by"]) as c:
            c.execute(
                select(s.organizations.c.id).where(s.organizations.c.id == handle["org_id"]).with_for_update()
            ).one()
            job = (
                c.execute(
                    select(s.knowledge_jobs)
                    .where(s.knowledge_jobs.c.org_id == handle["org_id"], s.knowledge_jobs.c.id == handle["id"])
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            now = db_now(c)
            if job["generation"] != handle["generation"] or job["lease_owner"] != handle["lease_owner"]:
                raise PlatformError("STALE_GENERATION", "Knowledge ingestion lease changed", 409)
            if active:
                if job["state"] != "leased" or job["lease_expires_at"] <= now or job["deadline_at"] <= now:
                    raise PlatformError("STALE_GENERATION", "Knowledge ingestion lease expired", 409)
                self.source(c, job)
            yield c, dict(job), now

    def claim(self, org, worker):
        with self.db.scoped(org, UUID(int=0)) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == org).with_for_update()).one()
            row = (
                c.execute(
                    select(s.knowledge_jobs)
                    .where(s.knowledge_jobs.c.org_id == org, s.knowledge_jobs.c.state == "queued")
                    .order_by(s.knowledge_jobs.c.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            job, now = dict(row), db_now(c)
            try:
                version, _, _ = self.source(c, job)
                if job["queued_at"] + timedelta(seconds=self.settings.queue_ttl_seconds) <= now:
                    raise PlatformError("QUEUE_DEADLINE_EXCEEDED", "Document expired in ingestion queue", 409)
                if job["deadline_at"] and job["deadline_at"] <= now:
                    raise PlatformError("INGESTION_DEADLINE_EXCEEDED", "Ingestion deadline expired", 409)
            except PlatformError as exc:
                self._failed(c, job, now, exc.code, cleaned=True)
                return None
            deadline = job["deadline_at"] or now + timedelta(seconds=300)
            values = {
                "generation": job["generation"] + 1,
                "lease_owner": worker,
                "state": "leased",
                "lease_expires_at": min(deadline, now + timedelta(seconds=self.settings.lease_seconds)),
                "deadline_at": deadline,
            }
            c.execute(update(s.knowledge_jobs).where(s.knowledge_jobs.c.id == job["id"]).values(**values))
            c.execute(
                update(s.knowledge_versions)
                .where(s.knowledge_versions.c.id == version["id"])
                .values(state="parsing" if job["phase"] == "parse" else "indexing")
            )
            return {**job, **values}

    def prepare(self, handle):
        with self.owned(handle) as (c, job, now):
            if job["spec"]:
                return job
            version, _, kb = self.source(c, job)
        data = self.knowledge.blobs.get(handle["org_id"], version["source_sha256"], version["source_bytes"])
        request = rfc8785.dumps(
            {"schema_version": 1, "format": version["format"], "source_sha256": version["source_sha256"]}
        )
        spec = {
            "schema_version": 1,
            "binding_id": str(uuid4()),
            "org_id": str(handle["org_id"]),
            "run_id": str(handle["id"]),
            "generation": handle["generation"],
            "target_slot": "knowledge/ingestion",
            "profile_id": kb["profile_id"],
            "image_digest": kb["image_digest"],
            "deadline": handle["deadline_at"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "inputs": [
                {
                    "path": "document.bin",
                    "sha256": version["source_sha256"],
                    "content_b64": base64.b64encode(data).decode(),
                },
                {
                    "path": "parse-request.json",
                    "sha256": hashlib.sha256(request).hexdigest(),
                    "content_b64": base64.b64encode(request).decode(),
                },
            ],
        }
        size = len(rfc8785.dumps(spec))
        with self.owned(handle) as (c, job, now):
            if job["spec"]:
                return job
            self.knowledge.quota(c, self.principal(job), kb, size)
            values = {
                "spec": spec,
                "spec_digest": canonical_digest("aio-cell-spec-v1", spec),
                "binding_id": UUID(spec["binding_id"]),
                "dispatch_id": uuid4(),
                "cleanup_state": "pending",
                "storage_reserved_bytes": size,
            }
            c.execute(update(s.knowledge_jobs).where(s.knowledge_jobs.c.id == job["id"]).values(**values))
            return {**job, **values}

    def pulse(self, handle):
        with self.owned(handle) as (c, job, now):
            c.execute(
                update(s.knowledge_jobs)
                .where(s.knowledge_jobs.c.id == job["id"])
                .values(lease_expires_at=min(job["deadline_at"], now + timedelta(seconds=self.settings.lease_seconds)))
            )

    def authorize(self, operation, payload):
        try:
            spec = payload["spec"]
            org, id = UUID(spec["org_id"]), UUID(spec["run_id"])
        except (KeyError, ValueError, TypeError):
            raise PlatformError("PARSER_ACTION_DENIED", "Parser identity is invalid", 403) from None
        with self.db.scoped(org, UUID(int=0)) as c:
            job = (
                c.execute(select(s.knowledge_jobs).where(s.knowledge_jobs.c.org_id == org, s.knowledge_jobs.c.id == id))
                .mappings()
                .first()
            )
            if job is None or job["spec_digest"] != canonical_digest("aio-cell-spec-v1", spec):
                raise PlatformError("PARSER_ACTION_DENIED", "Parser spec is not bound by the platform", 403)
            if operation in {"stop", "status"}:
                return
            if operation == "acknowledge":
                if job["cleanup_state"] != "confirmed":
                    raise PlatformError("PARSER_ACTION_DENIED", "Parser cleanup must precede payload retirement", 403)
                return
            now = db_now(c)
            if (
                job["generation"] != spec["generation"]
                or job["state"] != "leased"
                or job["lease_expires_at"] <= now
                or job["deadline_at"] <= now
            ):
                raise PlatformError("PARSER_ACTION_DENIED", "Parser lease is not current", 403)
            _, _, kb = self.source(c, job)
            self.knowledge.parser_profile(kb["profile_id"], kb["image_digest"])
            if operation in {"ensure", "alive"}:
                return
            if operation == "finalize" and job["result_sha256"]:
                return
            if (
                operation == "execute"
                and job["phase"] == "parse"
                and payload.get("code") == PARSER_COMMAND
                and payload.get("language") == "python"
                and payload.get("dispatch_id") == str(job["dispatch_id"])
                and type(payload.get("timeout_seconds")) is int
                and payload["timeout_seconds"] == PARSER_TIMEOUT
            ):
                return
            raise PlatformError("PARSER_ACTION_DENIED", "Command is outside the fixed parser intention", 403)

    def parsed(self, handle, response):
        with self.owned(handle) as (c, job, now):
            if response.get("binding_id") != str(job["binding_id"]) or response.get("dispatch_id") != str(
                job["dispatch_id"]
            ):
                raise PlatformError("PARSER_RESPONSE_INVALID", "Parser response belongs to a different job", 502)
            report = strict_json(str(response.get("stdout", "")).strip().encode(), max_bytes=8192)
            if (
                response.get("error_code")
                or response.get("exit_code") != 0
                or response.get("truncated")
                or not isinstance(report, dict)
                or report.get("status") != "parsed"
            ):
                code = (
                    report.get("code", "DOCUMENT_PARSE_FAILED") if isinstance(report, dict) else "DOCUMENT_PARSE_FAILED"
                )
                if (
                    not isinstance(code, str)
                    or not code.startswith("DOCUMENT_")
                    or not code.replace("_", "").isalnum()
                    or len(code) > 64
                ):
                    code = "DOCUMENT_PARSE_FAILED"
                raise PlatformError(code, "Document did not pass isolated parsing", 422)
            sha, size = report.get("sha256"), report.get("bytes")
            if not isinstance(sha, str) or len(sha) != 64 or type(size) is not int or not 1 <= size <= 2 * 1024 * 1024:
                raise PlatformError("PARSER_RESPONSE_INVALID", "Parser output metadata is invalid", 502)
            c.execute(
                update(s.knowledge_jobs)
                .where(s.knowledge_jobs.c.id == job["id"])
                .values(result_sha256=sha, result_bytes=size)
            )

    def stage(self, handle, response):
        with self.owned(handle) as (c, job, now):
            version, _, kb = self.source(c, job)
            if (
                response.get("state") != "destroyed"
                or response.get("binding_id") != str(job["binding_id"])
                or response.get("spec_digest") != job["spec_digest"]
            ):
                raise PlatformError("PARSER_CLEANUP_UNCONFIRMED", "Parser writer was not confirmed stopped", 503)
            files = response.get("files", [])
            matches = [file for file in files if file.get("path") == "parsed-document.json"]
            if len(matches) != 1:
                raise PlatformError("PARSER_RESPONSE_INVALID", "Exactly one fixed parser output is required", 502)
            try:
                raw = base64.b64decode(matches[0]["content_b64"], validate=True)
            except (ValueError, KeyError, TypeError):
                raise PlatformError("PARSER_RESPONSE_INVALID", "Parser output encoding is invalid", 502) from None
            if len(raw) != job["result_bytes"] or hashlib.sha256(raw).hexdigest() != job["result_sha256"]:
                raise PlatformError("PARSER_RESPONSE_INVALID", "Parser output checksum does not match its receipt", 502)
            content = strict_json(raw, max_bytes=2 * 1024 * 1024)
            if (
                content.get("schema_version") != 1
                or content.get("parser_version") != "document-parser-v1"
                or content.get("source_sha256") != version["source_sha256"]
                or content.get("format") != version["format"]
                or not isinstance(content.get("chunks"), list)
                or not 1 <= len(content["chunks"]) <= 512
            ):
                raise PlatformError("PARSER_RESPONSE_INVALID", "Parser report differs from the submitted source", 502)
            model = (
                current_embedding(c, self.principal(job), version["embedding_model_id"])
                if version["embedding_model_id"]
                else None
            )
            prepared, total = [], 0
            for ordinal, chunk in enumerate(content["chunks"]):
                text = chunk.get("text")
                location = chunk.get("location")
                if (
                    chunk.get("ordinal") != ordinal
                    or not isinstance(text, str)
                    or not 1 <= len(text.encode()) <= 4096
                    or not isinstance(location, dict)
                    or location.get("kind") not in {"lines", "csv_row", "paragraph", "spreadsheet_row", "page"}
                ):
                    raise PlatformError("PARSER_RESPONSE_INVALID", "Document chunks violate the bounded contract", 502)
                location = bounded_json(location, 2048)
                sha = hashlib.sha256(text.encode()).hexdigest()
                if chunk.get("sha256") != sha:
                    raise PlatformError("PARSER_RESPONSE_INVALID", "Document chunk failed checksum validation", 502)
                index_bytes = (
                    len(text.encode())
                    + len(rfc8785.dumps(location))
                    + (model["config"]["dimensions"] * 4 if model else 0)
                )
                total += index_bytes
                prepared.append(
                    {
                        "org_id": job["org_id"],
                        "id": uuid4(),
                        "version_id": version["id"],
                        "ordinal": ordinal,
                        "content": text,
                        "location": location,
                        "digest": sha,
                        "terms": terms(text),
                        "bytes": len(text.encode()),
                        "embedding_model_id": version["embedding_model_id"],
                    }
                )
            if total > version["storage_reserved_bytes"]:
                raise PlatformError("STORAGE_QUOTA_EXCEEDED", "Parser/index output exceeds its reserved quota", 429)
            c.execute(
                delete(s.knowledge_chunks).where(
                    s.knowledge_chunks.c.org_id == job["org_id"], s.knowledge_chunks.c.version_id == version["id"]
                )
            )
            c.execute(insert(s.knowledge_chunks), prepared)
            warnings = bounded_json(content.get("warnings", []), 4096)
            c.execute(
                update(s.knowledge_versions)
                .where(s.knowledge_versions.c.id == version["id"])
                .values(
                    state="indexing",
                    index_bytes=total,
                    storage_reserved_bytes=0,
                    parser_version=content["parser_version"],
                    warnings=warnings,
                )
            )
            c.execute(
                update(s.knowledge_jobs)
                .where(s.knowledge_jobs.c.id == job["id"])
                .values(phase="embed", cleanup_state="confirmed")
            )

    def acknowledged(self, handle, response):
        with self.owned(handle, active=False) as (c, job, now):
            if (
                response.get("state") != "acknowledged"
                or response.get("binding_id") != str(job["binding_id"])
                or job["cleanup_state"] != "confirmed"
            ):
                raise PlatformError("PARSER_CLEANUP_UNCONFIRMED", "Parser retained data was not acknowledged", 503)
            spec = {**job["spec"], "inputs": []} if job["spec"] else None
            c.execute(
                update(s.knowledge_jobs)
                .where(s.knowledge_jobs.c.id == job["id"])
                .values(export_acknowledged=True, storage_reserved_bytes=0, spec=spec)
            )

    def finish(self, handle):
        with self.owned(handle) as (c, job, now):
            version, document, kb = self.source(c, job)
            if job["cleanup_state"] != "confirmed" or not job["export_acknowledged"]:
                raise PlatformError(
                    "PARSER_CLEANUP_UNCONFIRMED", "Index publication requires confirmed parser cleanup", 503
                )
            chunks = (
                c.execute(
                    select(s.knowledge_chunks.c.id, s.knowledge_chunks.c.digest, s.knowledge_chunks.c.embedding)
                    .where(
                        s.knowledge_chunks.c.org_id == job["org_id"], s.knowledge_chunks.c.version_id == version["id"]
                    )
                    .order_by(s.knowledge_chunks.c.ordinal)
                )
                .mappings()
                .all()
            )
            if not chunks or (version["embedding_model_id"] and any(row["embedding"] is None for row in chunks)):
                raise PlatformError("KNOWLEDGE_INDEX_INCOMPLETE", "Required index vectors are missing", 409)
            index_digest = canonical_digest(
                "aio-knowledge-index-v1",
                {
                    "source": version["source_sha256"],
                    "chunks": [row["digest"] for row in chunks],
                    "embedding_model_id": str(version["embedding_model_id"]) if version["embedding_model_id"] else None,
                },
            )
            c.execute(
                update(s.knowledge_versions)
                .where(s.knowledge_versions.c.id == version["id"])
                .values(state="ready", index_digest=index_digest)
            )
            c.execute(
                update(s.knowledge_documents)
                .where(s.knowledge_documents.c.id == document["id"])
                .values(current_version_id=version["id"])
            )
            c.execute(
                update(s.resources)
                .where(s.resources.c.id == document["id"])
                .values(revision=s.resources.c.revision + 1)
            )
            c.execute(
                update(s.knowledge_bases)
                .where(s.knowledge_bases.c.id == kb["id"])
                .values(index_revision=s.knowledge_bases.c.index_revision + 1)
            )
            c.execute(
                update(s.knowledge_jobs)
                .where(s.knowledge_jobs.c.id == job["id"])
                .values(state="ready", phase="publish", finished_at=now, lease_expires_at=now)
            )
            audit.record(
                c,
                self.principal(job),
                'knowledge.version.publish',
                document['id'],
                'ready',
                m.KnowledgePublished(version_id=str(version['id']), chunks=len(chunks)),
            )
            return {"id": job["id"], "state": "ready", "version_id": version["id"]}

    @staticmethod
    def _failed(c, job, now, code, *, cleaned=False):
        state = "failed" if cleaned else "cleanup_pending"
        c.execute(
            update(s.knowledge_jobs)
            .where(s.knowledge_jobs.c.org_id == job["org_id"], s.knowledge_jobs.c.id == job["id"])
            .values(
                state=state,
                error_code=code,
                cleanup_state="confirmed" if cleaned else "pending",
                finished_at=now if cleaned else None,
            )
        )
        c.execute(
            update(s.knowledge_versions)
            .where(
                s.knowledge_versions.c.org_id == job["org_id"],
                s.knowledge_versions.c.id == job["version_id"],
                s.knowledge_versions.c.state != "deleted",
            )
            .values(state="failed")
        )

    def fail(self, handle, code):
        with self.owned(handle, active=False) as (c, job, now):
            if job["state"] == "ready":
                return job
            cleaned = job["cleanup_state"] == "confirmed" or job["spec"] is None
            self._failed(c, job, now, code, cleaned=cleaned)
            uncertain = c.execute(
                select(s.embedding_calls.c.id).where(
                    s.embedding_calls.c.org_id == job["org_id"],
                    s.embedding_calls.c.job_id == job["id"],
                    s.embedding_calls.c.state.in_(["started", "unknown"]),
                )
            ).first()
            if uncertain and cleaned:
                c.execute(
                    update(s.knowledge_jobs).where(s.knowledge_jobs.c.id == job["id"]).values(state="recovery_required")
                )
            return job

    def stopped(self, handle, response):
        with self.owned(handle, active=False) as (c, job, now):
            if response.get("state") != "destroyed" or response.get("binding_id") != str(job["binding_id"]):
                raise PlatformError("PARSER_CLEANUP_UNCONFIRMED", "Parser cell has not been confirmed stopped", 503)
            self._failed(c, job, now, job["error_code"] or "INGESTION_INTERRUPTED", cleaned=True)

    def recover(self, org, worker):
        with self.db.scoped(org, UUID(int=0)) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == org).with_for_update()).one()
            now = db_now(c)
            row = (
                c.execute(
                    select(s.knowledge_jobs)
                    .where(
                        s.knowledge_jobs.c.org_id == org,
                        s.knowledge_jobs.c.lease_expires_at <= now,
                        or_(
                            s.knowledge_jobs.c.state == "leased",
                            (s.knowledge_jobs.c.state.in_(["cleanup_pending", "failed"]))
                            & (s.knowledge_jobs.c.spec.is_not(None))
                            & s.knowledge_jobs.c.export_acknowledged.is_(False),
                        ),
                    )
                    .order_by(s.knowledge_jobs.c.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            job = dict(row)
            values = {
                "generation": job["generation"] + 1,
                "lease_owner": worker,
                "lease_expires_at": now + timedelta(seconds=self.settings.lease_seconds),
            }
            if (
                job["state"] == "leased"
                and job["phase"] == "embed"
                and job["cleanup_state"] == "confirmed"
                and job["export_acknowledged"]
            ):
                unknown = c.execute(
                    select(s.embedding_calls.c.id).where(
                        s.embedding_calls.c.org_id == org,
                        s.embedding_calls.c.job_id == job["id"],
                        s.embedding_calls.c.state.in_(["started", "unknown"]),
                    )
                ).first()
                values["state"] = "recovery_required" if unknown else "queued"
            else:
                values.update(state="cleanup_pending", error_code=job["error_code"] or "INGESTION_INTERRUPTED")
            c.execute(update(s.knowledge_jobs).where(s.knowledge_jobs.c.id == job["id"]).values(**values))
            return {**job, **values}
