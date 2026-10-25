"""Resource-authorized uploads, immutable files and atomic Run workspace publication."""

from __future__ import annotations

import hashlib
import mimetypes
from datetime import timedelta
from contextlib import contextmanager
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update, func, or_

from ..auth.principal import Principal
from ..db import schema as s
from ..observability import audit
from ..observability import redaction as m
from ..db.engine import Database
from ..platform_errors import PlatformError
from ..policy.repository import current_facts, db_now, require_resource, visible_resources
from ..runtime.actions import canonical_digest
from .storage import BlobStore, MAX_BLOB_BYTES, safe_path


class ArtifactService:
    def __init__(self, database: Database, blobs: BlobStore):
        self.db, self.blobs = database, blobs

    @staticmethod
    def check_storage_quota(c, org_id: UUID, project_id: UUID | None, additional: int):
        now = db_now(c)
        scopes = [
            (
                None,
                c.execute(
                    select(s.organizations.c.storage_limit_bytes).where(s.organizations.c.id == org_id)
                ).scalar_one(),
            )
        ]
        if project_id is not None:
            scopes.append(
                (
                    project_id,
                    c.execute(
                        select(s.projects.c.storage_limit_bytes).where(
                            s.projects.c.org_id == org_id, s.projects.c.id == project_id
                        )
                    ).scalar_one(),
                )
            )
        for scope, limit in scopes:
            usage = select(func.coalesce(func.sum(s.artifacts.c.bytes), 0)).where(s.artifacts.c.org_id == org_id)
            pending = select(func.coalesce(func.sum(s.upload_slots.c.max_bytes), 0)).where(
                s.upload_slots.c.org_id == org_id,
                s.upload_slots.c.state.in_(["pending", "uploading"]),
                or_(s.upload_slots.c.expires_at > now, s.upload_slots.c.content_sha256.is_not(None)),
            )
            workspace = select(func.coalesce(func.sum(s.workspace_leases.c.storage_reserved_bytes), 0)).where(
                s.workspace_leases.c.org_id == org_id
            )
            if scope is not None:
                usage = usage.where(s.artifacts.c.project_id == scope)
                pending = pending.where(s.upload_slots.c.project_id == scope)
                workspace = workspace.where(s.workspace_leases.c.project_id == scope)
            total = c.execute(usage).scalar_one() + c.execute(pending).scalar_one() + c.execute(workspace).scalar_one()
            from .checkpoints import allocated

            total += allocated(c, org_id, scope)
            if scope is None:
                from ..knowledge.service import KnowledgeService

                total += KnowledgeService.allocated(c, org_id)
                from ..skills.archive_service import allocated as import_storage

                total += import_storage(c, org_id)
            if total + additional > limit:
                raise PlatformError("STORAGE_QUOTA_EXCEEDED", "Organization or project storage quota is exhausted", 429)

    @staticmethod
    def require_artifact(c, p: Principal, id: UUID, action: str = "artifact.read"):
        require_resource(c, p, id, action)
        row = (
            c.execute(select(s.artifacts).where(s.artifacts.c.org_id == p.org_id, s.artifacts.c.id == id))
            .mappings()
            .first()
        )
        if row is None or row["state"] != "ready":
            raise PlatformError("ARTIFACT_NOT_READY", "File is not available", 404)
        require_resource(c, p, row["project_id"], "project.read")
        from ..skills.catalog import require_sources

        require_sources(c, p, row)
        from ..connections.catalog import require_sources as require_mcp_sources

        require_mcp_sources(c, p, row["mcp_source_refs"])
        from ..knowledge.catalog import require_sources as require_knowledge_sources

        require_knowledge_sources(c, p, row["knowledge_source_refs"])
        # Provenance points to original roots, not recursive chains of intermediate artifacts.
        sources = row["source_refs"]
        if not isinstance(sources, list) or len(sources) > 64:
            raise PlatformError("SOURCE_POLICY_INVALID", "File provenance cannot be safely resolved", 409)
        for source_id in sources:
            source = UUID(source_id)
            require_resource(c, p, source, "artifact.read")
            src = c.execute(
                select(s.artifacts.c.state).where(s.artifacts.c.org_id == p.org_id, s.artifacts.c.id == source)
            ).scalar_one_or_none()
            if src != "ready":
                raise PlatformError("SOURCE_REVOKED", "A source file is no longer accessible", 404)
        return dict(row)

    def create_upload(self, p: Principal, project_id: UUID, path: str, max_bytes: int) -> dict:
        path = safe_path(path)
        if type(max_bytes) is not int or not 0 <= max_bytes <= MAX_BLOB_BYTES:
            raise PlatformError("PAYLOAD_TOO_LARGE", "Upload limit is invalid", 413)
        with self.db.transaction(p) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update()).one()
            facts = current_facts(c, p, lock=True)
            require_resource(c, p, project_id, "project.write", facts=facts, lock=True)
            self.check_storage_quota(c, p.org_id, project_id, max_bytes)
            count = c.execute(
                select(s.upload_slots.c.id).where(
                    s.upload_slots.c.org_id == p.org_id,
                    s.upload_slots.c.user_id == p.user_id,
                    s.upload_slots.c.state == "pending",
                    s.upload_slots.c.expires_at > db_now(c),
                )
            ).all()
            if len(count) >= 16:
                raise PlatformError("UPLOAD_QUOTA_EXCEEDED", "Too many pending uploads", 429)
            id = uuid4()
            expiry = db_now(c) + timedelta(minutes=10)
            c.execute(
                insert(s.upload_slots).values(
                    org_id=p.org_id,
                    id=id,
                    user_id=p.user_id,
                    project_id=project_id,
                    path=path,
                    max_bytes=max_bytes,
                    state="pending",
                    expires_at=expiry,
                )
            )
            return {
                "upload_id": id,
                "expires_at": expiry,
                "max_bytes": max_bytes,
                "content_url": f"/api/v2/uploads/{id}/content",
            }

    def upload(self, p: Principal, slot_id: UUID, data: bytes) -> dict:
        if not isinstance(data, bytes) or len(data) > MAX_BLOB_BYTES:
            raise PlatformError("PAYLOAD_TOO_LARGE", "File exceeds the object limit", 413)
        sha = hashlib.sha256(data).hexdigest()
        with self.db.transaction(p) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update()).one()
            facts = current_facts(c, p, lock=True)
            initial = (
                c.execute(
                    select(s.upload_slots).where(
                        s.upload_slots.c.org_id == p.org_id,
                        s.upload_slots.c.id == slot_id,
                        s.upload_slots.c.user_id == p.user_id,
                    )
                )
                .mappings()
                .first()
            )
            if initial is None:
                raise PlatformError("RESOURCE_NOT_FOUND", "Upload is not accessible", 404)
            require_resource(c, p, initial["project_id"], "project.write", facts=facts, lock=True)
            slot = (
                c.execute(select(s.upload_slots).where(s.upload_slots.c.id == slot_id).with_for_update())
                .mappings()
                .one()
            )
            if slot["state"] == "completed":
                row = self.require_artifact(c, p, slot["artifact_id"])
                if row["sha256"] != sha:
                    raise PlatformError("UPLOAD_CONFLICT", "Slot already contains different bytes", 409)
                return self.metadata(row)
            if slot["expires_at"] <= db_now(c) or len(data) > slot["max_bytes"]:
                raise PlatformError(
                    "UPLOAD_EXPIRED_OR_TOO_LARGE", "Upload is expired or exceeds its reserved size", 413
                )
            if slot["content_sha256"] is not None and slot["content_sha256"] != sha:
                raise PlatformError("UPLOAD_CONFLICT", "This slot is already bound to different immutable content", 409)
            if slot["state"] not in {"pending", "uploading"}:
                raise PlatformError("UPLOAD_EXPIRED", "Upload is not active", 409)
            c.execute(
                update(s.upload_slots)
                .where(s.upload_slots.c.id == slot_id)
                .values(state="uploading", content_sha256=sha, content_bytes=len(data))
            )
        # Capacity is reserved and this hash is bound before touching storage. Conflicting retries write nothing.
        self.blobs.put(p.org_id, data)
        with self.db.transaction(p) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update()).one()
            facts = current_facts(c, p, lock=True)
            project = require_resource(c, p, initial["project_id"], "project.write", facts=facts, lock=True)
            slot = (
                c.execute(
                    select(s.upload_slots)
                    .where(
                        s.upload_slots.c.org_id == p.org_id,
                        s.upload_slots.c.id == slot_id,
                        s.upload_slots.c.user_id == p.user_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if slot["state"] == "completed":
                return self.metadata(self.require_artifact(c, p, slot["artifact_id"]))
            if slot["state"] != "uploading" or slot["content_sha256"] != sha:
                raise PlatformError("UPLOAD_CONFLICT", "Upload state changed before publication", 409)
            if slot["expires_at"] <= db_now(c):
                raise PlatformError("UPLOAD_EXPIRED", "Upload completed after its allowed window", 409)
            id = uuid4()
            c.execute(
                insert(s.resources).values(
                    org_id=p.org_id, id=id, kind="artifact", owner_id=p.user_id, classification=project.classification
                )
            )
            c.execute(
                insert(s.artifacts).values(
                    org_id=p.org_id,
                    id=id,
                    project_id=slot["project_id"],
                    path=slot["path"],
                    sha256=sha,
                    bytes=len(data),
                    media_type=mimetypes.guess_type(slot["path"])[0] or "application/octet-stream",
                    state="ready",
                    kind="upload",
                    source_refs=[],
                    scan_state="opaque_attachment",
                )
            )
            c.execute(
                update(s.upload_slots).where(s.upload_slots.c.id == slot_id).values(state="completed", artifact_id=id)
            )
            audit.record(c, p, "artifact.upload", id, "stored", m.ArtifactUploaded(bytes=len(data)))
            return self.metadata(c.execute(select(s.artifacts).where(s.artifacts.c.id == id)).mappings().one())

    @staticmethod
    def metadata(row):
        return {
            key: row[key]
            for key in ("id", "project_id", "run_id", "path", "bytes", "sha256", "media_type", "state", "scan_state")
        }

    def info(self, p: Principal, id: UUID) -> dict:
        with self.db.transaction(p) as c:
            return self.metadata(self.require_artifact(c, p, id))

    def download(self, p: Principal, id: UUID) -> tuple[dict, bytes]:
        with self.db.transaction(p) as c:
            row = self.require_artifact(c, p, id, "artifact.download")
        data = self.blobs.get(p.org_id, row["sha256"], row["bytes"])
        with self.db.transaction(p) as c:
            self.require_artifact(c, p, id, "artifact.download")
        return self.metadata(row), data

    def list_project(self, p: Principal, project_id: UUID) -> list[dict]:
        with self.db.transaction(p) as c:
            require_resource(c, p, project_id, "project.read")
            pred = visible_resources(c, p, "artifact", "artifact.read")
            rows = (
                c.execute(
                    select(s.artifacts)
                    .join(
                        s.resources,
                        (s.resources.c.org_id == s.artifacts.c.org_id) & (s.resources.c.id == s.artifacts.c.id),
                    )
                    .where(pred, s.artifacts.c.project_id == project_id, s.artifacts.c.state == "ready")
                    .order_by(s.artifacts.c.created_at.desc(), s.artifacts.c.id)
                    .limit(100)
                )
                .mappings()
                .all()
            )
            result = []
            for row in rows:
                try:
                    self.require_artifact(c, p, row["id"])
                except PlatformError as exc:
                    if exc.status == 404:
                        continue
                    raise
                result.append(self.metadata(row))
            return result

    def inputs(self, p: Principal, run: dict) -> list[dict]:
        with self.db.transaction(p) as c:
            require_resource(c, p, run["project_id"], "project.read")
            project = (
                c.execute(
                    select(s.projects).where(s.projects.c.org_id == p.org_id, s.projects.c.id == run["project_id"])
                )
                .mappings()
                .one()
            )
            files = {}
            if project["head_version"]:
                version = (
                    c.execute(
                        select(s.workspace_versions).where(
                            s.workspace_versions.c.org_id == p.org_id,
                            s.workspace_versions.c.project_id == project["id"],
                            s.workspace_versions.c.version == project["head_version"],
                        )
                    )
                    .mappings()
                    .one()
                )
                if canonical_digest("aio-workspace-version-v1", version["manifest"]) != version["digest"]:
                    raise PlatformError(
                        "WORKSPACE_INTEGRITY_ERROR", "Workspace version failed integrity validation", 409
                    )
                for item in version["manifest"]:
                    row = self.require_artifact(c, p, UUID(item["artifact_id"]))
                    files[row["path"]] = row
            for raw in run["input"].get("input_artifact_ids", []):
                row = self.require_artifact(c, p, UUID(raw))
                if row["project_id"] != run["project_id"]:
                    raise PlatformError("INPUT_SCOPE_DENIED", "Input belongs to another project", 403)
                files[row["path"]] = row
            if len(files) > 64 or sum(row["bytes"] for row in files.values()) > MAX_BLOB_BYTES:
                raise PlatformError("INPUT_QUOTA_EXCEEDED", "Run inputs exceed the execution input quota", 413)
        return [{**row, "data": self.blobs.get(p.org_id, row["sha256"], row["bytes"])} for row in files.values()]

    @contextmanager
    def _export_transaction(self, p: Principal, run_id: UUID, generation: int):
        with self.db.transaction(p) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update()).one()
            current_facts(c, p, lock=True)
            info = c.execute(select(s.runs).where(s.runs.c.org_id == p.org_id, s.runs.c.id == run_id)).mappings().one()
            require_resource(c, p, run_id, "run.read")
            project = require_resource(c, p, info["project_id"], "project.write", lock=True)
            c.execute(select(s.projects.c.id).where(s.projects.c.id == info["project_id"]).with_for_update()).one()
            run = c.execute(select(s.runs).where(s.runs.c.id == run_id).with_for_update()).mappings().one()
            lease = (
                c.execute(
                    select(s.workspace_leases)
                    .where(
                        s.workspace_leases.c.org_id == p.org_id, s.workspace_leases.c.project_id == run["project_id"]
                    )
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if (
                run["actor_id"] != p.user_id
                or run["generation"] != generation
                or run["state"] != "running"
                or lease["run_id"] != run_id
                or lease["generation"] != generation
            ):
                raise PlatformError("STALE_GENERATION", "Cannot publish another or obsolete run's workspace", 409)
            yield c, run, lease, project

    def stage_export(self, p: Principal, run_id: UUID, generation: int, files: list[dict]) -> list[dict]:
        from .exports import prepare_export

        prepared, manifest = prepare_export(files)
        total = sum(item["bytes"] for item in prepared)
        with self._export_transaction(p, run_id, generation) as (c, run, lease, project):
            if lease["export_manifest"] is not None and lease["export_manifest"] != manifest:
                raise PlatformError(
                    "ARTIFACT_CONFLICT", "Export was already bound to a different immutable manifest", 409
                )
            if lease["state"] == "staged":
                rows = (
                    c.execute(
                        select(s.artifacts).where(s.artifacts.c.org_id == p.org_id, s.artifacts.c.run_id == run_id)
                    )
                    .mappings()
                    .all()
                )
                return [self.metadata(row) for row in rows]
            if lease["storage_reserved_bytes"] < total:
                raise PlatformError("STORAGE_QUOTA_EXCEEDED", "Generated files exceed the reserved storage budget", 429)
            c.execute(
                update(s.workspace_leases)
                .where(s.workspace_leases.c.org_id == p.org_id, s.workspace_leases.c.project_id == run["project_id"])
                .values(export_manifest=manifest)
            )
        # Immutable expected hashes and storage reservation are durable before any files are written.
        for item in prepared:
            self.blobs.put(p.org_id, item["data"])
        with self._export_transaction(p, run_id, generation) as (c, run, lease, project):
            if lease["export_manifest"] != manifest:
                raise PlatformError("ARTIFACT_CONFLICT", "Export state changed before staging", 409)
            source_ids = set(run["input"].get("input_artifact_ids", [])) | set(run["provenance_source_ids"])
            if lease["base_version"]:
                previous = c.execute(
                    select(s.workspace_versions.c.manifest).where(
                        s.workspace_versions.c.org_id == p.org_id,
                        s.workspace_versions.c.project_id == run["project_id"],
                        s.workspace_versions.c.version == lease["base_version"],
                    )
                ).scalar_one()
                source_ids.update(item["artifact_id"] for item in previous)
            roots = set()
            capability_sources = set(run["capability_source_ids"])
            capability_reads = set(run["capability_read_source_ids"])
            from ..connections.catalog import merge_sources

            mcp_sources = list(run["mcp_source_refs"])
            from ..knowledge.catalog import merge_sources as merge_knowledge_sources

            knowledge_sources = list(run["knowledge_source_refs"])
            for sid in source_ids:
                source = self.require_artifact(c, p, UUID(sid))
                roots.update(source["source_refs"] or [sid])
                capability_sources.update(source["capability_source_ids"])
                capability_reads.update(source["capability_read_source_ids"])
                mcp_sources = merge_sources(mcp_sources, source["mcp_source_refs"])
                knowledge_sources = merge_knowledge_sources(knowledge_sources, source["knowledge_source_refs"])
            if len(roots) > 64:
                raise PlatformError("SOURCE_POLICY_LIMIT", "Too many provenance roots to publish safely", 409)
            result = []
            for file in manifest:
                existing = (
                    c.execute(
                        select(s.artifacts).where(
                            s.artifacts.c.org_id == p.org_id,
                            s.artifacts.c.run_id == run_id,
                            s.artifacts.c.path == file["path"],
                        )
                    )
                    .mappings()
                    .first()
                )
                if existing:
                    if existing["sha256"] != file["sha256"]:
                        raise PlatformError("ARTIFACT_CONFLICT", "Staged output changed", 409)
                    result.append(self.metadata(existing))
                    continue
                id = uuid4()
                c.execute(
                    insert(s.resources).values(
                        org_id=p.org_id,
                        id=id,
                        kind="artifact",
                        owner_id=p.user_id,
                        classification=project.classification,
                    )
                )
                c.execute(
                    insert(s.artifacts).values(
                        org_id=p.org_id,
                        id=id,
                        project_id=run["project_id"],
                        run_id=run_id,
                        **file,
                        media_type=mimetypes.guess_type(file["path"])[0] or "application/octet-stream",
                        state="staged",
                        kind="generated",
                        source_refs=sorted(roots),
                        capability_source_ids=sorted(capability_sources),
                        capability_read_source_ids=sorted(capability_reads),
                        mcp_source_refs=mcp_sources,
                        knowledge_source_refs=knowledge_sources,
                        scan_state="structural_attachment",
                    )
                )
                result.append({"id": id, **file})
            c.execute(
                update(s.workspace_leases)
                .where(s.workspace_leases.c.org_id == p.org_id, s.workspace_leases.c.project_id == run["project_id"])
                .values(state="staged", storage_reserved_bytes=0)
            )
            return result

    @staticmethod
    def publish(c, run, generation: int, principal: Principal) -> list[dict]:
        lease = (
            c.execute(
                select(s.workspace_leases)
                .where(
                    s.workspace_leases.c.org_id == run["org_id"], s.workspace_leases.c.project_id == run["project_id"]
                )
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if lease is None or lease["run_id"] != run["id"]:
            return []
        if lease["generation"] != generation or lease["state"] != "staged":
            raise PlatformError(
                "ARTIFACT_NOT_STAGED", "Execution files must be safely collected before publication", 409
            )
        active = c.execute(
            select(s.sandbox_leases.c.id).where(
                s.sandbox_leases.c.org_id == run["org_id"],
                s.sandbox_leases.c.run_id == run["id"],
                s.sandbox_leases.c.state != "destroyed",
            )
        ).first()
        if active:
            raise PlatformError("CLEANUP_UNCONFIRMED", "Writer must be externally stopped before publication", 409)
        rows = (
            c.execute(
                select(s.artifacts)
                .where(
                    s.artifacts.c.org_id == run["org_id"],
                    s.artifacts.c.run_id == run["id"],
                    s.artifacts.c.state == "staged",
                )
                .order_by(s.artifacts.c.path)
            )
            .mappings()
            .all()
        )
        for row in rows:
            for source_id in row["source_refs"]:
                ArtifactService.require_artifact(c, principal, UUID(source_id))
        manifest = [
            {"path": row["path"], "artifact_id": str(row["id"]), "sha256": row["sha256"], "bytes": row["bytes"]}
            for row in rows
        ]
        changed = c.execute(
            update(s.projects)
            .where(
                s.projects.c.org_id == run["org_id"],
                s.projects.c.id == run["project_id"],
                s.projects.c.head_version == lease["base_version"],
            )
            .values(head_version=lease["base_version"] + 1)
        ).rowcount
        if changed != 1:
            raise PlatformError("WORKSPACE_CONFLICT", "Project head changed; refusing to overwrite it", 409)
        c.execute(
            insert(s.workspace_versions).values(
                org_id=run["org_id"],
                id=uuid4(),
                project_id=run["project_id"],
                run_id=run["id"],
                version=lease["base_version"] + 1,
                parent_version=lease["base_version"],
                manifest=manifest,
                digest=canonical_digest("aio-workspace-version-v1", manifest),
            )
        )
        c.execute(
            update(s.artifacts)
            .where(
                s.artifacts.c.org_id == run["org_id"],
                s.artifacts.c.run_id == run["id"],
                s.artifacts.c.state == "staged",
            )
            .values(state="ready")
        )
        c.execute(
            update(s.workspace_leases)
            .where(s.workspace_leases.c.org_id == run["org_id"], s.workspace_leases.c.project_id == run["project_id"])
            .values(state="released")
        )
        return manifest
