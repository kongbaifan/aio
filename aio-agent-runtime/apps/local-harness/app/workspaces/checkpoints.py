"""Private filesystem checkpoints at quiescent approval boundaries.

No container is adopted, no user process is serialized, and no old tool is replayed.
The manager exports and destroys a writer; PostgreSQL binds bytes/authority before
blob writes, then a later generation restores a new cell from verified files.
"""

from __future__ import annotations

import asyncio
import base64
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update, func, null, or_

from ..db import schema as s
from ..platform_errors import PlatformError
from ..policy.repository import db_now, lock_run_resources
from ..runtime.actions import canonical_digest
from .exports import prepare_export
from .references import blob_referenced
from .service import ArtifactService
from .storage import BlobStore, MAX_BLOB_BYTES

SOURCES = (
    "provenance_source_ids",
    "capability_source_ids",
    "capability_read_source_ids",
    "mcp_source_refs",
    "knowledge_source_refs",
)
BOUND_FIELDS = (
    "org_id",
    "id",
    "run_id",
    "project_id",
    "generation",
    "checkpoint_seq",
    "checkpoint_digest",
    "sandbox_lease_id",
    "invocation_id",
    "base_version",
    "profile_id",
    "image_digest",
    "spec_digest",
    *SOURCES,
)
TERMINAL = {"succeeded", "failed", "cancelled", "timed_out"}


def binding_digest(row):
    return canonical_digest(
        "aio-workspace-checkpoint-v1",
        {key: str(row[key]) if isinstance(row[key], UUID) else row[key] for key in BOUND_FIELDS},
    )


def intact(row):
    if binding_digest(row) != row["binding_digest"]:
        return False
    if row["manifest"] is None:
        return row["manifest_digest"] is None and row["ready_at"] is None
    return canonical_digest("aio-workspace-files-v1", row["manifest"]) == row["manifest_digest"]


def allocated(c, org, project=None):
    query = select(func.coalesce(func.sum(s.workspace_checkpoints.c.reserved_bytes), 0)).where(
        s.workspace_checkpoints.c.org_id == org, s.workspace_checkpoints.c.reserved_bytes > 0
    )
    if project is not None:
        query = query.where(s.workspace_checkpoints.c.project_id == project)
    return c.execute(query).scalar_one()


def unfinished(c, run):
    return (
        c.execute(
            select(s.workspace_checkpoints.c.id)
            .where(
                s.workspace_checkpoints.c.org_id == run["org_id"],
                s.workspace_checkpoints.c.run_id == run["id"],
                s.workspace_checkpoints.c.state.in_(["preparing", "bound"]),
            )
            .limit(1)
        ).first()
        is not None
    )


def retire(c, run):
    c.execute(
        update(s.workspace_checkpoints)
        .where(
            s.workspace_checkpoints.c.org_id == run["org_id"],
            s.workspace_checkpoints.c.run_id == run["id"],
            s.workspace_checkpoints.c.state.not_in(["retiring", "purged"]),
        )
        .values(state="retiring")
    )


def checkpoint_view(c, run):
    """Metadata only, called after current Run/project/session/source authorization."""
    row = (
        c.execute(
            select(s.workspace_checkpoints)
            .where(s.workspace_checkpoints.c.org_id == run["org_id"], s.workspace_checkpoints.c.run_id == run["id"])
            .order_by(s.workspace_checkpoints.c.generation.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return {
        "id": str(row["id"]),
        "state": row["state"],
        "generation": row["generation"],
        "engine_checkpoint_seq": row["checkpoint_seq"],
        "file_count": len(row["manifest"]) if row["manifest"] is not None else None,
        "bytes": sum(item["bytes"] for item in row["manifest"]) if row["manifest"] is not None else None,
        "preserved_state": "filesystem_only",
        "manager_acknowledged": row["manager_acknowledged"],
    }


class WorkspaceCheckpointStore:
    def __init__(self, store):
        self.store, self.db = store, store.db
        self.artifacts = (
            ArtifactService(self.db, BlobStore(store.settings.artifact_root)) if store.settings.artifact_root else None
        )

    def _storage(self):
        if self.artifacts is None:
            raise PlatformError("WORKSPACE_STORAGE_UNAVAILABLE", "Private checkpoint storage must be configured", 503)
        return self.artifacts.blobs

    @staticmethod
    def _lease(c, run):
        return (
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

    @staticmethod
    def _row(c, run, id):
        return (
            c.execute(
                select(s.workspace_checkpoints)
                .where(
                    s.workspace_checkpoints.c.org_id == run["org_id"],
                    s.workspace_checkpoints.c.run_id == run["id"],
                    s.workspace_checkpoints.c.id == id,
                )
                .with_for_update()
            )
            .mappings()
            .first()
        )

    def _verify(self, c, run, row, *, ready=True):
        if (
            row is None
            or row["org_id"] != run["org_id"]
            or row["run_id"] != run["id"]
            or row["project_id"] != run["project_id"]
            or binding_digest(row) != row["binding_digest"]
            or row["checkpoint_seq"] > run["checkpoint_seq"]
            or (ready and row["state"] != "ready")
        ):
            raise PlatformError("WORKSPACE_CHECKPOINT_INVALID", "Checkpoint identity or state failed verification", 409)
        cp = self.store._checkpoint(c, {**run, "checkpoint_seq": row["checkpoint_seq"]})
        if cp is None or cp.digest != row["checkpoint_digest"] or cp.restartability == "process_state_dependent":
            raise PlatformError(
                "WORKSPACE_CHECKPOINT_INVALID", "Checkpoint does not bind reconstructible engine state", 409
            )
        if (
            row["manifest"] is not None
            and canonical_digest("aio-workspace-files-v1", row["manifest"]) != row["manifest_digest"]
        ):
            raise PlatformError("WORKSPACE_CHECKPOINT_INVALID", "Checkpoint files failed integrity verification", 409)
        from ..skills.catalog import require_sources
        from ..connections.catalog import require_sources as require_mcp
        from ..knowledge.catalog import require_sources as require_knowledge
        from ..auth.principal import Principal

        member = c.execute(
            select(s.memberships.c.revision).where(
                s.memberships.c.org_id == run["org_id"], s.memberships.c.user_id == run["actor_id"]
            )
        ).scalar_one()
        p = Principal(run["org_id"], run["actor_id"], member)
        require_sources(c, p, row)
        require_mcp(c, p, row["mcp_source_refs"])
        require_knowledge(c, p, row["knowledge_source_refs"])
        for source in row["provenance_source_ids"]:
            ArtifactService.require_artifact(c, p, UUID(source))
        return row

    @staticmethod
    def _barrier(c, run, cp):
        if cp is None or cp.phase != "tools" or cp.restartability == "process_state_dependent":
            raise PlatformError(
                "WORKSPACE_NOT_QUIESCENT", "Only a reconstructible approval boundary can checkpoint files", 409
            )
        inv = (
            c.execute(
                select(s.invocations).where(
                    s.invocations.c.org_id == run["org_id"],
                    s.invocations.c.run_id == run["id"],
                    s.invocations.c.logical_call_id == cp.logical_tool_id,
                )
            )
            .mappings()
            .first()
        )
        if inv is None or inv["risk_class"] != "R2" or inv["state"] not in {"waiting_approval", "authorized", "denied"}:
            raise PlatformError(
                "WORKSPACE_NOT_QUIESCENT", "The exact committed approval action must not have been sent", 409
            )
        approval = c.execute(
            select(s.approvals.c.id).where(
                s.approvals.c.org_id == run["org_id"], s.approvals.c.invocation_id == inv["id"]
            )
        ).first()
        if not approval:
            raise PlatformError("WORKSPACE_NOT_QUIESCENT", "No durable approval boundary exists", 409)
        return inv

    def begin(self, handle):
        self._storage()
        with self.store.locked(handle, project=True, storage_quota=True) as (c, run, job, now, facts):
            cp = self.store._checkpoint(c, run)
            inv = self._barrier(c, run, cp)
            if any(self.store._uncertain(c, run)):
                raise PlatformError("RECONCILIATION_REQUIRED", "Cannot checkpoint with an uncertain effect", 409)
            cell = (
                c.execute(
                    select(s.sandbox_leases).where(
                        s.sandbox_leases.c.org_id == run["org_id"],
                        s.sandbox_leases.c.run_id == run["id"],
                        s.sandbox_leases.c.generation == handle.generation,
                        s.sandbox_leases.c.target_slot == "compute/main",
                    )
                )
                .mappings()
                .first()
            )
            if cell is None:
                return None
            prior = (
                c.execute(
                    select(s.workspace_checkpoints).where(
                        s.workspace_checkpoints.c.org_id == run["org_id"],
                        s.workspace_checkpoints.c.run_id == run["id"],
                        s.workspace_checkpoints.c.generation == handle.generation,
                    )
                )
                .mappings()
                .first()
            )
            if prior:
                self._verify(c, run, prior, ready=False)
                if (
                    prior["checkpoint_seq"] != run["checkpoint_seq"]
                    or prior["invocation_id"] != inv["id"]
                    or prior["state"] not in {"preparing", "bound", "ready"}
                ):
                    raise PlatformError(
                        "WORKSPACE_CHECKPOINT_CONFLICT", "This generation already bound another handoff", 409
                    )
                return {**dict(prior), "spec": cell["spec"]}
            if cell["state"] != "ready" or not cell["spec"]:
                raise PlatformError("WORKSPACE_NOT_QUIESCENT", "Compute cell is not available for safe export", 409)
            lease = self._lease(c, run)
            if (
                lease is None
                or lease["run_id"] != run["id"]
                or lease["generation"] != handle.generation
                or lease["state"] != "active"
                or lease["storage_reserved_bytes"] < MAX_BLOB_BYTES
            ):
                raise PlatformError("WORKSPACE_CHECKPOINT_CONFLICT", "Workspace writer or reservation changed", 409)
            row = dict(
                org_id=run["org_id"],
                id=uuid4(),
                run_id=run["id"],
                project_id=run["project_id"],
                generation=handle.generation,
                checkpoint_seq=run["checkpoint_seq"],
                checkpoint_digest=cp.digest,
                sandbox_lease_id=cell["id"],
                invocation_id=inv["id"],
                base_version=lease["base_version"],
                profile_id=cell["profile_id"],
                image_digest=cell["image_digest"],
                spec_digest=cell["spec_digest"],
                reserved_bytes=MAX_BLOB_BYTES,
                **{name: run[name] for name in SOURCES},
            )
            row["provenance_source_ids"] = sorted(
                set(row["provenance_source_ids"]) | set(run["input"].get("input_artifact_ids", []))
            )
            row["binding_digest"] = binding_digest(row)
            c.execute(insert(s.workspace_checkpoints).values(**row))
            c.execute(update(s.runs).where(s.runs.c.id == run["id"]).values(revision=s.runs.c.revision + 1))
            # Transfer, not duplicate, the existing output hold before the manager destroys anything.
            c.execute(
                update(s.workspace_leases)
                .where(
                    s.workspace_leases.c.org_id == run["org_id"], s.workspace_leases.c.project_id == run["project_id"]
                )
                .values(state="checkpointing", storage_reserved_bytes=0)
            )
            self.store.platform._event(
                c, run["org_id"], run["id"], "workspace.checkpointing", {"checkpoint_id": str(row["id"])}
            )
            return {**row, "state": "preparing", "spec": cell["spec"]}

    def authorize(self, c, run, spec):
        row = (
            c.execute(
                select(s.workspace_checkpoints).where(
                    s.workspace_checkpoints.c.org_id == run["org_id"],
                    s.workspace_checkpoints.c.run_id == run["id"],
                    s.workspace_checkpoints.c.sandbox_lease_id == UUID(spec["binding_id"]),
                )
            )
            .mappings()
            .first()
        )
        self._verify(c, run, row, ready=False)
        cp = self.store._checkpoint(c, run)
        inv = self._barrier(c, run, cp)
        if (
            row["generation"] != run["generation"]
            or row["checkpoint_seq"] != run["checkpoint_seq"]
            or row["invocation_id"] != inv["id"]
            or row["state"] not in {"preparing", "bound", "ready"}
            or row["spec_digest"] != canonical_digest("aio-cell-spec-v1", spec)
            or any(self.store._uncertain(c, run))
        ):
            raise PlatformError("MANAGER_ACTION_DENIED", "Checkpoint is outside its exact committed boundary", 403)

    def accept(self, handle, id, result):
        blobs = self._storage()
        prepared, manifest = prepare_export(result.get("files"))
        digest = canonical_digest("aio-workspace-files-v1", manifest)
        total = sum(item["bytes"] for item in manifest)
        with self.store.locked(handle, project=True, storage_quota=True) as (c, run, job, now, facts):
            row = self._verify(c, run, self._row(c, run, id), ready=False)
            if (
                result.get("state") != "destroyed"
                or result.get("binding_id") != str(row["sandbox_lease_id"])
                or result.get("spec_digest") != row["spec_digest"]
                or row["generation"] != handle.generation
                or row["state"] not in {"preparing", "bound", "ready"}
            ):
                raise PlatformError(
                    "MANAGER_RESPONSE_INVALID", "Checkpoint response did not confirm the expected retired writer", 502
                )
            if row["manifest"] is not None and (row["manifest"] != manifest or row["manifest_digest"] != digest):
                raise PlatformError("WORKSPACE_CHECKPOINT_CONFLICT", "Immutable checkpoint bytes changed", 409)
            if row["state"] == "ready":
                return dict(row)
            if total > row["reserved_bytes"]:
                raise PlatformError("STORAGE_QUOTA_EXCEEDED", "Checkpoint exceeds its existing hold", 429)
            c.execute(
                update(s.workspace_checkpoints)
                .where(s.workspace_checkpoints.c.id == id)
                .values(state="bound", manifest=manifest, manifest_digest=digest, reserved_bytes=total)
            )
            c.execute(
                update(s.sandbox_leases)
                .where(s.sandbox_leases.c.id == row["sandbox_lease_id"])
                .values(state="destroyed")
            )
            c.execute(update(s.runs).where(s.runs.c.id == run["id"]).values(revision=s.runs.c.revision + 1))
        with self.store.locked(handle, project=True, storage_quota=True) as (c, run, job, now, facts):
            row = self._verify(c, run, self._row(c, run, id), ready=False)
            lease = self._lease(c, run)
            if (
                row["state"] != "bound"
                or row["manifest_digest"] != digest
                or run["checkpoint_seq"] != row["checkpoint_seq"]
                or lease["run_id"] != run["id"]
                or lease["generation"] != handle.generation
                or lease["state"] != "checkpointing"
            ):
                raise PlatformError(
                    "WORKSPACE_CHECKPOINT_CONFLICT", "Checkpoint boundary changed before durable completion", 409
                )
            active = c.execute(
                select(s.sandbox_leases.c.id).where(
                    s.sandbox_leases.c.org_id == run["org_id"],
                    s.sandbox_leases.c.run_id == run["id"],
                    s.sandbox_leases.c.state != "destroyed",
                )
            ).first()
            if active:
                raise PlatformError("CLEANUP_UNCONFIRMED", "All old writers must be confirmed stopped", 409)
            # Bounded local blob writes share the storage lock with GC. A cancelled
            # to_thread writer cannot recreate unreferenced bytes after a purge.
            # No network, model, archive extraction or user execution occurs here.
            for item in prepared:
                blobs.put(handle.principal.org_id, item["data"])
            c.execute(
                update(s.workspace_checkpoints)
                .where(s.workspace_checkpoints.c.id == id)
                .values(state="ready", ready_at=now)
            )
            if lease["resume_checkpoint_id"]:
                c.execute(
                    update(s.workspace_checkpoints)
                    .where(
                        s.workspace_checkpoints.c.id == lease["resume_checkpoint_id"],
                        s.workspace_checkpoints.c.state == "ready",
                    )
                    .values(state="retiring")
                )
            c.execute(
                update(s.workspace_leases)
                .where(
                    s.workspace_leases.c.org_id == run["org_id"], s.workspace_leases.c.project_id == run["project_id"]
                )
                .values(state="checkpointed", resume_checkpoint_id=id)
            )
            c.execute(
                update(s.runs)
                .where(s.runs.c.id == run["id"])
                .values(cleanup_state="clean", revision=s.runs.c.revision + 1)
            )
            self.store.platform._event(
                c,
                run["org_id"],
                run["id"],
                "workspace.checkpointed",
                {
                    "checkpoint_id": str(id),
                    "files": len(manifest),
                    "bytes": total,
                    "generation": handle.generation,
                    "preserved_state": "filesystem_only",
                },
            )
            return {**dict(row), "state": "ready"}

    def resume(self, handle):
        # This read is only a hint. Authority, lease and quota are rechecked in the ordered transaction below.
        with self.db.scoped(handle.principal.org_id, handle.principal.user_id) as c:
            info = (
                c.execute(
                    select(s.workspace_leases).where(
                        s.workspace_leases.c.org_id == handle.principal.org_id,
                        s.workspace_leases.c.run_id == handle.run_id,
                    )
                )
                .mappings()
                .first()
            )
        if info is None or info["generation"] == handle.generation:
            return
        self._storage()
        with self.store.locked(handle, project=True, storage_quota=True) as (c, run, job, now, facts):
            lease = self._lease(c, run)
            if lease is None or lease["run_id"] != run["id"]:
                raise PlatformError("WORKSPACE_CHECKPOINT_CONFLICT", "Workspace changed during handoff", 409)
            if lease["generation"] == handle.generation:
                return
            if lease["state"] != "checkpointed" or not lease["resume_checkpoint_id"]:
                raise PlatformError("PROCESS_STATE_LOST", "The old workspace has no confirmed immutable handoff", 409)
            row = self._verify(c, run, self._row(c, run, lease["resume_checkpoint_id"]))
            if row["generation"] >= handle.generation or row["base_version"] != lease["base_version"]:
                raise PlatformError(
                    "WORKSPACE_CHECKPOINT_CONFLICT", "Checkpoint generation or project base changed", 409
                )
            active = c.execute(
                select(s.sandbox_leases.c.id).where(
                    s.sandbox_leases.c.org_id == run["org_id"],
                    s.sandbox_leases.c.run_id == run["id"],
                    s.sandbox_leases.c.state != "destroyed",
                )
            ).first()
            head = c.execute(select(s.projects.c.head_version).where(s.projects.c.id == run["project_id"])).scalar_one()
            if active:
                raise PlatformError("PROCESS_STATE_LOST", "A previous writer is not externally confirmed stopped", 409)
            if head != row["base_version"]:
                raise PlatformError("WORKSPACE_CONFLICT", "Project head changed during a private handoff", 409)
            if len(row["manifest"]) > 64 or sum(item["bytes"] for item in row["manifest"]) > MAX_BLOB_BYTES:
                raise PlatformError("WORKSPACE_CHECKPOINT_INVALID", "Checkpoint files exceed the restore bound", 409)
            # Reject already missing/corrupt files before any later model or remote tool call,
            # not only when a Python command eventually needs to allocate its new cell.
            for item in row["manifest"]:
                self._storage().get(run["org_id"], item["sha256"], item["bytes"])
            additional = max(0, MAX_BLOB_BYTES - lease["storage_reserved_bytes"])
            ArtifactService.check_storage_quota(c, run["org_id"], run["project_id"], additional)
            c.execute(
                update(s.workspace_leases)
                .where(
                    s.workspace_leases.c.org_id == run["org_id"], s.workspace_leases.c.project_id == run["project_id"]
                )
                .values(generation=handle.generation, storage_reserved_bytes=MAX_BLOB_BYTES)
            )
            from ..connections.catalog import merge_sources
            from ..knowledge.catalog import merge_sources as merge_knowledge

            sources = {name: sorted(set(run[name]) | set(row[name])) for name in SOURCES[:3]}
            if any(len(values) > 64 for values in sources.values()):
                raise PlatformError("SOURCE_POLICY_LIMIT", "Restored provenance exceeds the source bound", 409)
            sources["mcp_source_refs"] = merge_sources(run["mcp_source_refs"], row["mcp_source_refs"])
            sources["knowledge_source_refs"] = merge_knowledge(
                run["knowledge_source_refs"], row["knowledge_source_refs"]
            )
            c.execute(update(s.runs).where(s.runs.c.id == run["id"]).values(**sources, revision=s.runs.c.revision + 1))
            self.store.platform._event(
                c,
                run["org_id"],
                run["id"],
                "workspace.resume_ready",
                {
                    "checkpoint_id": str(row["id"]),
                    "generation": handle.generation,
                    "preserved_state": "filesystem_only",
                },
            )

    def inputs(self, handle, *, profile=None, image=None):
        with self.store.locked(handle) as (c, run, job, now, facts):
            lease = self._lease(c, run)
            if lease is None or lease["run_id"] != run["id"] or lease["state"] != "checkpointed":
                return None
            if lease["generation"] != handle.generation:
                raise PlatformError("STALE_GENERATION", "Workspace has not been handed to this generation", 409)
            row = self._verify(c, run, self._row(c, run, lease["resume_checkpoint_id"]))
            if row["generation"] >= handle.generation:
                raise PlatformError("WORKSPACE_HANDOFF_REQUIRED", "A checkpoint must resume in a new generation", 409)
            if (profile and profile != row["profile_id"]) or (image and image != row["image_digest"]):
                raise PlatformError(
                    "WORKSPACE_PROFILE_CHANGED", "A restored workspace cannot change execution profile", 409
                )
            if len(row["manifest"]) > 64 or sum(item["bytes"] for item in row["manifest"]) > MAX_BLOB_BYTES:
                raise PlatformError("WORKSPACE_CHECKPOINT_INVALID", "Checkpoint files exceed the execution bound", 409)
            files = [
                {**item, "source_refs": row["provenance_source_ids"], **{name: row[name] for name in SOURCES[1:]}}
                for item in row["manifest"]
            ]
        blobs = self._storage()
        return [{**item, "data": blobs.get(handle.principal.org_id, item["sha256"], item["bytes"])} for item in files]

    @staticmethod
    def assert_operable(c, run):
        lease = c.execute(
            select(s.workspace_leases.c.generation).where(
                s.workspace_leases.c.org_id == run["org_id"], s.workspace_leases.c.run_id == run["id"]
            )
        ).scalar_one_or_none()
        if lease is not None and lease != run["generation"]:
            raise PlatformError(
                "WORKSPACE_HANDOFF_REQUIRED", "The current generation has not verified its workspace handoff", 409
            )
        if unfinished(c, run):
            raise PlatformError(
                "WORKSPACE_CHECKPOINT_PENDING", "A filesystem checkpoint must finish before new actions", 409
            )
        row = c.execute(
            select(s.workspace_checkpoints.c.id)
            .join(s.workspace_leases, s.workspace_leases.c.resume_checkpoint_id == s.workspace_checkpoints.c.id)
            .where(
                s.workspace_leases.c.org_id == run["org_id"],
                s.workspace_leases.c.run_id == run["id"],
                s.workspace_leases.c.state == "checkpointed",
                s.workspace_checkpoints.c.generation == run["generation"],
            )
        ).first()
        if row:
            raise PlatformError(
                "WORKSPACE_HANDOFF_REQUIRED", "The retired writer must release this generation first", 409
            )

    @staticmethod
    def acknowledge_allowed(c, run, lease):
        snapshot = (
            c.execute(
                select(s.workspace_checkpoints).where(
                    s.workspace_checkpoints.c.org_id == run["org_id"],
                    s.workspace_checkpoints.c.run_id == run["id"],
                    s.workspace_checkpoints.c.sandbox_lease_id == lease["id"],
                    s.workspace_checkpoints.c.state.in_(["ready", "retiring", "purged"]),
                )
            )
            .mappings()
            .first()
        )
        if lease["state"] != "destroyed" or not (snapshot or run["state"] in TERMINAL):
            raise PlatformError("MANAGER_ACTION_DENIED", "Uncommitted checkpoint payload cannot be purged", 403)
        if snapshot and not intact(snapshot):
            raise PlatformError(
                "WORKSPACE_CHECKPOINT_INVALID", "Corrupt checkpoint metadata must not erase its recovery copy", 409
            )

    def mark_acknowledged(self, org, id):
        with self.db.scoped(org, UUID(int=0)) as c:
            info = (
                c.execute(
                    select(s.workspace_checkpoints).where(
                        s.workspace_checkpoints.c.org_id == org, s.workspace_checkpoints.c.id == id
                    )
                )
                .mappings()
                .one()
            )
            lock_run_resources(c, org, info["run_id"])
            c.execute(
                select(s.runs.c.id).where(s.runs.c.org_id == org, s.runs.c.id == info["run_id"]).with_for_update()
            ).one()
            info = self._row(c, {"org_id": org, "id": info["run_id"]}, id)
            if info["manager_acknowledged"]:
                return
            cell = c.execute(
                select(s.sandbox_leases.c.state).where(s.sandbox_leases.c.id == info["sandbox_lease_id"])
            ).scalar_one()
            if info["state"] not in {"ready", "retiring"} or not intact(info) or cell != "destroyed":
                raise PlatformError(
                    "WORKSPACE_CHECKPOINT_INVALID", "Only verified retired payloads can be acknowledged", 409
                )
            c.execute(
                update(s.workspace_checkpoints)
                .where(s.workspace_checkpoints.c.id == id)
                .values(manager_acknowledged=True)
            )
            # Retired inputs need not retain a second copy in the old cell specification.
            c.execute(
                update(s.sandbox_leases)
                .where(s.sandbox_leases.c.id == info["sandbox_lease_id"], s.sandbox_leases.c.state == "destroyed")
                .values(spec=null())
            )
            c.execute(update(s.runs).where(s.runs.c.id == info["run_id"]).values(revision=s.runs.c.revision + 1))
            self.store.platform._event(
                c, org, info["run_id"], "workspace.checkpoint_acknowledged", {"checkpoint_id": str(id)}
            )

    def pending_acknowledgements(self, org, limit=20):
        with self.db.scoped(org, UUID(int=0)) as c:
            return [
                dict(row)
                for row in c.execute(
                    select(s.workspace_checkpoints.c.id, s.sandbox_leases.c.spec)
                    .join(s.sandbox_leases, s.sandbox_leases.c.id == s.workspace_checkpoints.c.sandbox_lease_id)
                    .where(
                        s.workspace_checkpoints.c.org_id == org,
                        s.workspace_checkpoints.c.manager_acknowledged.is_(False),
                        s.workspace_checkpoints.c.state.in_(["ready", "retiring"]),
                        s.sandbox_leases.c.state == "destroyed",
                    )
                    .order_by(s.workspace_checkpoints.c.created_at)
                    .limit(limit)
                ).mappings()
            ]

    def cleanup_candidates(self, org, limit=20):
        with self.db.scoped(org, UUID(int=0)) as c:
            return [
                dict(row)
                for row in c.execute(
                    select(s.sandbox_leases)
                    .join(
                        s.runs,
                        (s.runs.c.org_id == s.sandbox_leases.c.org_id) & (s.runs.c.id == s.sandbox_leases.c.run_id),
                    )
                    .where(
                        s.sandbox_leases.c.org_id == org,
                        s.sandbox_leases.c.state != "destroyed",
                        or_(
                            s.runs.c.state.in_(TERMINAL | {"cancel_requested", "recovery_required"}),
                            s.sandbox_leases.c.generation != s.runs.c.generation,
                        ),
                    )
                    .order_by(s.sandbox_leases.c.created_at)
                    .limit(limit)
                ).mappings()
            ]

    def confirm_stopped(self, spec):
        from ..execution.coordinator import SandboxCoordinator

        SandboxCoordinator(self.store, self.artifacts).observed(spec, "destroyed")

    def gc(self, org, limit=20):
        blobs = self._storage()
        with self.db.scoped(org, UUID(int=0)) as c:
            ids = list(
                c.execute(
                    select(s.workspace_checkpoints.c.id)
                    .where(
                        s.workspace_checkpoints.c.org_id == org,
                        s.workspace_checkpoints.c.state == "retiring",
                        s.workspace_checkpoints.c.manager_acknowledged.is_(True),
                    )
                    .order_by(s.workspace_checkpoints.c.created_at)
                    .limit(limit)
                ).scalars()
            )
        purged = []
        for id in ids:
            with self.db.scoped(org, UUID(int=0)) as c:
                c.execute(select(s.organizations.c.id).where(s.organizations.c.id == org).with_for_update()).one()
                info = (
                    c.execute(select(s.workspace_checkpoints).where(s.workspace_checkpoints.c.id == id))
                    .mappings()
                    .one()
                )
                lock_run_resources(c, org, info["run_id"])
                run = (
                    c.execute(
                        select(s.runs).where(s.runs.c.org_id == org, s.runs.c.id == info["run_id"]).with_for_update()
                    )
                    .mappings()
                    .one()
                )
                row = self._row(c, run, id)
                if row["state"] != "retiring" or not row["manager_acknowledged"] or not intact(row):
                    continue
                cell = c.execute(
                    select(s.sandbox_leases.c.state).where(s.sandbox_leases.c.id == row["sandbox_lease_id"])
                ).scalar_one()
                current = (
                    c.execute(
                        select(s.workspace_leases).where(
                            s.workspace_leases.c.org_id == org, s.workspace_leases.c.run_id == run["id"]
                        )
                    )
                    .mappings()
                    .first()
                )
                if cell != "destroyed" or (
                    run["state"] not in TERMINAL and current and current["resume_checkpoint_id"] == id
                ):
                    continue
                for item in row["manifest"] or []:
                    if not blob_referenced(c, org, item["sha256"], excluding_checkpoint=id):
                        blobs.remove(org, item["sha256"])
                c.execute(
                    update(s.workspace_checkpoints)
                    .where(s.workspace_checkpoints.c.id == id)
                    .values(state="purged", reserved_bytes=0, purged_at=db_now(c))
                )
                c.execute(update(s.runs).where(s.runs.c.id == run["id"]).values(revision=s.runs.c.revision + 1))
                self.store.platform._event(c, org, run["id"], "workspace.checkpoint_purged", {"checkpoint_id": str(id)})
                purged.append(id)
        return purged


async def maintain_once(checkpoints, client, org):
    for lease in await asyncio.to_thread(checkpoints.cleanup_candidates, org):
        if not lease["spec"]:
            continue
        result = await client.call("stop", {"spec": lease["spec"]})
        if result.get("state") != "destroyed" or result.get("binding_id") != str(lease["id"]):
            raise PlatformError("CLEANUP_UNCONFIRMED", "Manager did not confirm this retired writer", 503)
        await asyncio.to_thread(checkpoints.confirm_stopped, lease["spec"])
    for row in await asyncio.to_thread(checkpoints.pending_acknowledgements, org):
        if not row["spec"]:
            continue
        result = await client.call("acknowledge", {"spec": row["spec"]})
        if result.get("state") == "acknowledged" and result.get("binding_id") == row["spec"]["binding_id"]:
            await asyncio.to_thread(checkpoints.mark_acknowledged, org, row["id"])
    return await asyncio.to_thread(checkpoints.gc, org)


async def maintain_checkpoints(checkpoints, client, org, stopping):
    while not stopping.is_set():
        try:
            await maintain_once(checkpoints, client, org)
        except Exception:
            # Retain durable refs/holds; never log raw file/provider payloads or pretend cleanup succeeded.
            pass
        try:
            await asyncio.wait_for(stopping.wait(), timeout=5)
        except TimeoutError:
            pass


def as_export(files):
    return [
        {key: item[key] for key in ("path", "sha256", "bytes")}
        | {"content_b64": base64.b64encode(item["data"]).decode("ascii")}
        for item in files
    ]
