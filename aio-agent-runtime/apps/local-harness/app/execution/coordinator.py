"""PostgreSQL-backed sandbox binding and manager live authorization authority."""

from __future__ import annotations

import base64
from datetime import timezone
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update, null

from ..auth.principal import Principal
from ..db import schema as s
from ..platform_errors import PlatformError
from ..policy.repository import current_facts, db_now, require_resource, lock_run_resources
from ..runtime.actions import canonical_digest
from ..runtime.contracts import DispatchPermit, WorkHandle
from ..runtime.execution import ExecutionStore
from ..workspaces.service import ArtifactService


class SandboxCoordinator:
    def __init__(self, store: ExecutionStore, artifacts: ArtifactService):
        self.store, self.db, self.artifacts = store, store.db, artifacts

    def reserve(self, permit: DispatchPermit) -> dict:
        h = permit.handle
        profile = permit.config.get("sandbox_profile")
        image = permit.config.get("image_digest")
        if (
            permit.driver not in {"sandbox.python", "skill.python"}
            or not profile
            or not image
            or permit.config.get("network_profile_id", "none") != "none"
        ):
            raise PlatformError(
                "SANDBOX_PROFILE_INVALID", "Tool must select an approved no-network sandbox profile", 409
            )
        with self.store.locked(h, project=True, storage_quota=True) as (c, run, job, now, facts):
            project = (
                c.execute(
                    select(s.projects).where(s.projects.c.org_id == run["org_id"], s.projects.c.id == run["project_id"])
                )
                .mappings()
                .one()
            )
            existing = (
                c.execute(
                    select(s.workspace_leases)
                    .where(
                        s.workspace_leases.c.org_id == run["org_id"],
                        s.workspace_leases.c.project_id == run["project_id"],
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if (
                existing
                and existing["state"] != "released"
                and (existing["run_id"] != run["id"] or existing["generation"] != h.generation)
            ):
                raise PlatformError("PROJECT_BUSY", "A different run still owns this workspace writer", 409)
            if existing is None or existing["state"] == "released":
                if existing and existing["storage_reserved_bytes"]:
                    raise PlatformError(
                        "STORAGE_RECONCILIATION_REQUIRED", "Previous output reservation must be reconciled", 409
                    )
                self.artifacts.check_storage_quota(c, run["org_id"], run["project_id"], 8 * 1024 * 1024)
            if existing is None:
                c.execute(
                    insert(s.workspace_leases).values(
                        org_id=run["org_id"],
                        project_id=run["project_id"],
                        run_id=run["id"],
                        generation=h.generation,
                        base_version=project["head_version"],
                        storage_reserved_bytes=8 * 1024 * 1024,
                        export_manifest=null(),
                        resume_checkpoint_id=None,
                        state="active",
                        expires_at=run["deadline_at"],
                    )
                )
            elif existing["state"] == "released":
                c.execute(
                    update(s.workspace_leases)
                    .where(
                        s.workspace_leases.c.org_id == run["org_id"],
                        s.workspace_leases.c.project_id == run["project_id"],
                    )
                    .values(
                        run_id=run["id"],
                        generation=h.generation,
                        base_version=project["head_version"],
                        storage_reserved_bytes=8 * 1024 * 1024,
                        export_manifest=null(),
                        resume_checkpoint_id=None,
                        state="active",
                        expires_at=run["deadline_at"],
                    )
                )
            lease = (
                c.execute(
                    select(s.sandbox_leases).where(
                        s.sandbox_leases.c.org_id == run["org_id"],
                        s.sandbox_leases.c.run_id == run["id"],
                        s.sandbox_leases.c.generation == h.generation,
                        s.sandbox_leases.c.target_slot == "compute/main",
                    )
                )
                .mappings()
                .first()
            )
            if lease:
                if (
                    lease["profile_id"] != profile
                    or lease["image_digest"] != image
                    or lease["state"] not in {"provisioning", "ready"}
                ):
                    raise PlatformError("CELL_UNAVAILABLE", "Current execution binding cannot be reused", 409)
                return lease["spec"]
        inputs = self.store.workspace.inputs(h, profile=profile, image=image)
        if inputs is None:
            inputs = self.artifacts.inputs(h.principal, dict(run))
        source_ids = set(run["provenance_source_ids"])
        capability_sources = set(run["capability_source_ids"])
        capability_reads = set(run["capability_read_source_ids"])
        from ..connections.catalog import merge_sources

        mcp_sources = list(run["mcp_source_refs"])
        from ..knowledge.catalog import merge_sources as merge_knowledge_sources

        knowledge_sources = list(run["knowledge_source_refs"])
        for item in inputs:
            source_ids.update(item["source_refs"] or ([str(item["id"])] if item.get("id") else []))
            capability_sources.update(item["capability_source_ids"])
            capability_reads.update(item["capability_read_source_ids"])
            mcp_sources = merge_sources(mcp_sources, item["mcp_source_refs"])
            knowledge_sources = merge_knowledge_sources(knowledge_sources, item["knowledge_source_refs"])
        if max(len(source_ids), len(capability_sources), len(capability_reads)) > 64:
            raise PlatformError("SOURCE_POLICY_LIMIT", "Run has too many independent data sources", 409)
        spec = {
            "schema_version": 1,
            "binding_id": str(uuid4()),
            "org_id": str(run["org_id"]),
            "run_id": str(run["id"]),
            "generation": h.generation,
            "target_slot": "compute/main",
            "profile_id": profile,
            "image_digest": image,
            "deadline": run["deadline_at"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "inputs": [
                {
                    "path": row["path"],
                    "sha256": row["sha256"],
                    "content_b64": base64.b64encode(row["data"]).decode("ascii"),
                }
                for row in sorted(inputs, key=lambda v: v["path"])
            ],
        }
        with self.store.locked(h, project=True, storage_quota=True) as (c, run, job, now, facts):
            lease = (
                c.execute(
                    select(s.workspace_leases)
                    .where(
                        s.workspace_leases.c.org_id == run["org_id"],
                        s.workspace_leases.c.project_id == run["project_id"],
                    )
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if lease["run_id"] != run["id"] or lease["generation"] != h.generation:
                raise PlatformError("STALE_GENERATION", "Workspace binding changed during allocation", 409)
            c.execute(
                update(s.workspace_leases)
                .where(
                    s.workspace_leases.c.org_id == run["org_id"], s.workspace_leases.c.project_id == run["project_id"]
                )
                .values(state="active")
            )
            c.execute(
                insert(s.sandbox_leases).values(
                    org_id=run["org_id"],
                    id=UUID(spec["binding_id"]),
                    run_id=run["id"],
                    generation=h.generation,
                    target_slot="compute/main",
                    role="compute",
                    profile_id=profile,
                    image_digest=image,
                    spec_digest=canonical_digest("aio-cell-spec-v1", spec),
                    state="provisioning",
                    expires_at=run["deadline_at"],
                    spec=spec,
                )
            )
            c.execute(
                update(s.runs)
                .where(s.runs.c.id == run["id"])
                .values(
                    cleanup_state="pending",
                    provenance_source_ids=sorted(source_ids),
                    capability_source_ids=sorted(capability_sources),
                    capability_read_source_ids=sorted(capability_reads),
                    mcp_source_refs=mcp_sources,
                    knowledge_source_refs=knowledge_sources,
                )
            )
        return spec

    def authorize(self, operation: str, payload: dict) -> None:
        if not isinstance(operation, str) or operation not in {
            "ensure",
            "execute",
            "finalize",
            "checkpoint",
            "acknowledge",
            "alive",
            "stop",
            "status",
        }:
            raise PlatformError("MANAGER_ACTION_DENIED", "Unknown execution management action", 403)
        try:
            spec = payload["spec"]
            org = UUID(spec["org_id"])
            bid = UUID(spec["binding_id"])
            rid = UUID(spec["run_id"])
            generation = spec["generation"]
            if type(generation) is not int:
                raise ValueError
        except (KeyError, ValueError, TypeError):
            raise PlatformError("MANAGER_ACTION_DENIED", "Invalid execution identity", 403) from None
        with self.db.scoped(org, UUID(int=0)) as c:
            lease = (
                c.execute(
                    select(s.sandbox_leases).where(s.sandbox_leases.c.org_id == org, s.sandbox_leases.c.id == bid)
                )
                .mappings()
                .first()
            )
            if (
                lease is None
                or lease["run_id"] != rid
                or lease["generation"] != generation
                or lease["spec_digest"] != canonical_digest("aio-cell-spec-v1", spec)
            ):
                raise PlatformError(
                    "MANAGER_ACTION_DENIED", "Execution specification is not bound by the platform", 403
                )
            if operation in {"stop", "status"}:
                return
            run = c.execute(select(s.runs).where(s.runs.c.org_id == org, s.runs.c.id == rid)).mappings().one()
            if operation == "acknowledge":
                self.store.workspace.acknowledge_allowed(c, run, lease)
                return
            # This checks current approval even on heartbeats, not only when a Skill is published.
            from .runtime_policy import require_runtime

            manifest = self.store._manifest(c, run)
            ids = [
                UUID(item["id"])
                for item in manifest.get("tools", [])
                if item.get("driver") in {"sandbox.python", "skill.python"}
            ]
            if ids:
                configs = c.execute(
                    select(s.tool_versions.c.config).where(
                        s.tool_versions.c.org_id == org, s.tool_versions.c.id.in_(ids)
                    )
                ).scalars()
                for config in configs:
                    if (
                        config.get("runtime_manifest_digest")
                        and config.get("sandbox_profile") == spec["profile_id"]
                        and config.get("image_digest") == spec["image_digest"]
                    ):
                        require_runtime(
                            self.store.settings,
                            spec["profile_id"],
                            spec["image_digest"],
                            config["runtime_manifest_digest"],
                        )
            member = (
                c.execute(
                    select(s.memberships).where(
                        s.memberships.c.org_id == org, s.memberships.c.user_id == run["actor_id"]
                    )
                )
                .mappings()
                .first()
            )
            job = c.execute(select(s.jobs).where(s.jobs.c.org_id == org, s.jobs.c.run_id == rid)).mappings().one()
            if not member:
                raise PlatformError("MANAGER_ACTION_DENIED", "Run actor is not active", 403)
            principal = Principal(org, run["actor_id"], member["revision"], service_actor_id=job["lease_owner"])
            from ..skills.catalog import require_sources

            require_sources(c, principal, run)
            from ..connections.catalog import require_sources as require_mcp_sources

            require_mcp_sources(c, principal, run["mcp_source_refs"])
            from ..knowledge.catalog import require_sources as require_knowledge_sources

            require_knowledge_sources(c, principal, run["knowledge_source_refs"])
            current_facts(c, principal)
            for obj, action in [
                (rid, "run.read"),
                (run["project_id"], "project.write"),
                (run["session_id"], "session.run"),
                (run["agent_version_id"], "agent.use"),
            ]:
                require_resource(c, principal, obj, action)
            for source_id in set(run["input"].get("input_artifact_ids", [])) | set(run["provenance_source_ids"]):
                self.artifacts.require_artifact(c, principal, UUID(source_id))
            now = db_now(c)
            if (
                run["generation"] != generation
                or run["state"] not in {"running", "preparing", "waiting_approval", "persisting"}
                or not run["deadline_at"]
                or run["deadline_at"] <= now
                or lease["expires_at"] <= now
            ):
                raise PlatformError("MANAGER_ACTION_DENIED", "Execution lease is obsolete or expired", 403)
            if operation in {"ensure", "execute", "alive"} and lease["state"] not in {"provisioning", "ready"}:
                raise PlatformError("MANAGER_ACTION_DENIED", "Execution binding has been retired", 403)
            if operation == "alive" and run["state"] == "waiting_approval" and job["state"] == "waiting_approval":
                return
            if (
                job["state"] != "leased"
                or not job["lease_owner"]
                or job["lease_expires_at"] <= now
                or job["lease_version"] != generation
            ):
                raise PlatformError("MANAGER_ACTION_DENIED", "Worker no longer owns the execution lease", 403)
            if operation == "alive":
                return
            handle = WorkHandle(principal, rid, generation, job["lease_owner"], run["deadline_at"])
        with self.store.locked(handle) as (c, run, job, now, facts):
            if operation == "checkpoint":
                self.store.workspace.authorize(c, run, spec)
                return
            if operation == "finalize":
                cp = self.store._checkpoint(c, run)
                if cp is None or cp.phase != "final":
                    raise PlatformError("MANAGER_ACTION_DENIED", "Only final results can be collected", 403)
                team = self.store.team.cursor(c, run, self.store._manifest(c, run))
                if team is not None and team["stage"] != "synthesis":
                    raise PlatformError(
                        "MANAGER_ACTION_DENIED", "A team step cannot finalize the shared Run workspace", 403
                    )
                return
            if operation == "ensure":
                return
            try:
                dispatch_id = UUID(payload["dispatch_id"])
            except (KeyError, TypeError, ValueError):
                raise PlatformError("MANAGER_ACTION_DENIED", "Dispatch ID is invalid", 403) from None
            d = (
                c.execute(select(s.dispatches).where(s.dispatches.c.org_id == org, s.dispatches.c.id == dispatch_id))
                .mappings()
                .first()
            )
            if not d or d["generation"] != generation or d["state"] != "dispatching":
                raise PlatformError("MANAGER_ACTION_DENIED", "Dispatch is not active", 403)
            inv = (
                c.execute(
                    select(s.invocations).where(
                        s.invocations.c.org_id == org,
                        s.invocations.c.id == d["invocation_id"],
                        s.invocations.c.run_id == rid,
                    )
                )
                .mappings()
                .first()
            )
            if not inv or inv["state"] != "executing":
                raise PlatformError("MANAGER_ACTION_DENIED", "Invocation is not executing", 403)
            tool, action = self.store._validate_invocation(c, handle, run, inv, now, facts)
            code = inv["arguments"].get("code") if tool["driver"] == "sandbox.python" else None
            if tool["driver"] == "skill.python":
                from ..skills.catalog import skill_for_tool
                from ..skills.commands import call_code

                skill = skill_for_tool(c, handle.principal, tool)
                code = call_code(skill, tool["config"]["entrypoint"], inv["arguments"])
            if (
                tool["driver"] not in {"sandbox.python", "skill.python"}
                or code != payload.get("code")
                or payload.get("language") != "python"
                or type(payload.get("timeout_seconds")) is not int
                or not 1 <= payload["timeout_seconds"] <= tool["config"].get("timeout_seconds", 120)
            ):
                raise PlatformError(
                    "MANAGER_ACTION_DENIED", "Command differs from the authorized immutable action", 403
                )

    def command(self, permit: DispatchPermit) -> str:
        if permit.driver == "sandbox.python":
            return permit.arguments["code"]
        from ..skills.catalog import current_skill
        from ..skills.commands import call_code

        with self.store.locked(permit.handle) as (c, run, job, now, facts):
            skill = current_skill(
                c, permit.handle.principal, UUID(permit.config["skill_id"]), permit.config["skill_digest"]
            )
            return call_code(skill, permit.config["entrypoint"], permit.arguments)

    def skill_result(self, permit, result):
        from ..skills.catalog import current_skill
        from ..skills.commands import entrypoint, result_value

        with self.store.locked(permit.handle) as (c, run, job, now, facts):
            skill = current_skill(
                c, permit.handle.principal, UUID(permit.config["skill_id"]), permit.config["skill_digest"]
            )
            e = entrypoint(skill, permit.config["entrypoint"])
            try:
                return {
                    "result": result_value(result, output_schema=e["output_schema"]),
                    "skill_digest": skill["digest"],
                }
            except PlatformError as exc:
                return {"error_code": exc.code, "message": "The isolated Skill did not produce its declared result"}

    def leases(self, handle: WorkHandle) -> list[dict]:
        with self.db.transaction(handle.principal) as c:
            return [
                dict(r)
                for r in c.execute(
                    select(s.sandbox_leases).where(
                        s.sandbox_leases.c.org_id == handle.principal.org_id,
                        s.sandbox_leases.c.run_id == handle.run_id,
                        s.sandbox_leases.c.generation == handle.generation,
                    )
                ).mappings()
            ]

    def observed(self, spec: dict, state: str, backend_id: str | None = None):
        if state not in {"ready", "destroyed"}:
            raise ValueError("Unknown manager observation")
        org = UUID(spec["org_id"])
        bid = UUID(spec["binding_id"])
        rid = UUID(spec["run_id"])
        with self.db.scoped(org, UUID(int=0)) as c:
            lock_run_resources(c, org, rid)
            c.execute(select(s.runs.c.id).where(s.runs.c.org_id == org, s.runs.c.id == rid).with_for_update()).one()
            lease = (
                c.execute(
                    select(s.sandbox_leases)
                    .where(s.sandbox_leases.c.org_id == org, s.sandbox_leases.c.id == bid)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if lease["spec_digest"] != canonical_digest("aio-cell-spec-v1", spec):
                raise PlatformError("MANAGER_RESPONSE_INVALID", "Manager observation does not match the binding", 409)
            if state == "ready" and lease["state"] == "destroyed":
                raise PlatformError("CELL_DESTROYED", "Cannot revive an already destroyed execution binding", 409)
            c.execute(
                update(s.sandbox_leases)
                .where(s.sandbox_leases.c.id == bid)
                .values(state=state, backend_id=backend_id or lease["backend_id"])
            )
            if state == "destroyed":
                remaining = c.execute(
                    select(s.sandbox_leases.c.id).where(
                        s.sandbox_leases.c.org_id == org,
                        s.sandbox_leases.c.run_id == rid,
                        s.sandbox_leases.c.state != "destroyed",
                    )
                ).first()
                if remaining is None:
                    c.execute(
                        update(s.runs)
                        .where(s.runs.c.org_id == org, s.runs.c.id == rid, s.runs.c.cleanup_state != "clean")
                        .values(cleanup_state="clean", revision=s.runs.c.revision + 1)
                    )
