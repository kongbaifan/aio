"""平台资源与持久 Run 服务。所有事务短小，绝不在数据库事务里调用模型/执行器。"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..auth.principal import Principal
from ..billing import budgets as shared_budgets
from ..db import schema as s
from ..observability import audit
from ..observability import redaction as m
from ..db.engine import Database
from ..platform_errors import PlatformError
from ..platform_settings import PlatformSettings, WorkerSettings
from ..policy import kill_switches
from ..policy.repository import (
    current_facts,
    db_now,
    require_resource,
    visible_resources,
    lock_resource_rows,
    lock_run_resources,
    try_lock_run_resources,
)
from .actions import ActionSpec, canonical_digest
from .states import TERMINAL_STATES, require_generation, require_transition


class PlatformService:
    def __init__(self, database: Database, settings: PlatformSettings | WorkerSettings):
        self.database, self.settings = database, settings

    @staticmethod
    def _lock_resources(c, principal: Principal, ids: list[UUID]) -> None:
        lock_resource_rows(c, principal.org_id, ids)

    @staticmethod
    def _resource(c, principal: Principal, id: UUID, kind: str, classification: str = "internal") -> None:
        c.execute(
            insert(s.resources).values(
                id=id, org_id=principal.org_id, owner_id=principal.user_id, kind=kind, classification=classification
            )
        )

    @staticmethod
    def _event(c, org_id: UUID, run_id: UUID, kind: str, payload: dict) -> int:
        seq = c.execute(
            update(s.runs)
            .where(s.runs.c.org_id == org_id, s.runs.c.id == run_id)
            .values(next_event_seq=s.runs.c.next_event_seq + 1)
            .returning(s.runs.c.next_event_seq)
        ).scalar_one()
        c.execute(insert(s.events).values(org_id=org_id, run_id=run_id, seq=seq, kind=kind, payload=payload))
        c.execute(
            insert(s.outbox).values(
                id=uuid4(), org_id=org_id, aggregate_id=run_id, kind="run.event.available", payload={"seq": seq}
            )
        )
        return seq

    @staticmethod
    def _run(c, principal: Principal, run_id: UUID, *, lock: bool = False, validate_sources: bool = True):
        require_resource(c, principal, run_id, "run.read")
        if lock:
            lock_run_resources(c, principal.org_id, run_id)
            require_resource(c, principal, run_id, "run.read")
        query = select(s.runs).where(s.runs.c.org_id == principal.org_id, s.runs.c.id == run_id)
        row = c.execute(query.with_for_update() if lock else query).mappings().first()
        if row is None:
            raise PlatformError("RESOURCE_NOT_FOUND", "Run is not accessible", 404)
        if validate_sources:
            from ..connections.catalog import require_sources as require_mcp_sources

            require_mcp_sources(c, principal, row["mcp_source_refs"])
            from ..knowledge.catalog import require_sources as require_knowledge_sources

            require_knowledge_sources(c, principal, row["knowledge_source_refs"])
            from ..skills.catalog import require_sources

            require_sources(c, principal, row)
            from ..workspaces.service import ArtifactService

            for source_id in set(row["input"].get("input_artifact_ids", [])) | set(row["provenance_source_ids"]):
                ArtifactService.require_artifact(c, principal, UUID(source_id))
        return row

    def create_project(self, principal: Principal, name: str) -> dict:
        with self.database.transaction(principal) as c:
            facts = current_facts(c, principal, lock=True)
            if "internal" not in facts.allowed_classifications or "project.create" in facts.denied_actions:
                raise PlatformError("POLICY_DENIED", "Project creation is not permitted", 403)
            id = uuid4()
            self._resource(c, principal, id, "project")
            c.execute(insert(s.projects).values(org_id=principal.org_id, id=id, name=name))
            audit.record(
                c,
                principal,
                'project.create',
                id,
                'created',
            )
            return {"id": id, "name": name, "revision": 0}

    def list_projects(self, principal: Principal, *, after: UUID | None = None, limit: int = 50) -> list[dict]:
        with self.database.transaction(principal) as c:
            predicate = visible_resources(c, principal, "project", "project.read")
            query = (
                select(s.projects, s.resources.c.revision)
                .join(
                    s.resources, (s.resources.c.id == s.projects.c.id) & (s.resources.c.org_id == s.projects.c.org_id)
                )
                .where(predicate)
            )
            if after:
                query = query.where(s.projects.c.id > after)
            return [dict(r) for r in c.execute(query.order_by(s.projects.c.id).limit(min(limit, 100))).mappings()]

    def list_agents(self, principal: Principal) -> list[dict]:
        with self.database.transaction(principal) as c:
            predicate = visible_resources(c, principal, "agent", "agent.use")
            query = select(
                s.agent_versions.c.id,
                s.agent_versions.c.name,
                s.agent_versions.c.version,
                s.agent_versions.c.engine,
                s.agent_versions.c.digest,
            ).join(
                s.resources,
                (s.resources.c.id == s.agent_versions.c.id) & (s.resources.c.org_id == s.agent_versions.c.org_id),
            )
            return [
                dict(r)
                for r in c.execute(
                    query.where(predicate, s.agent_versions.c.published.is_(True))
                    .order_by(s.agent_versions.c.id)
                    .limit(100)
                ).mappings()
            ]

    def create_session(self, principal: Principal, project_id: UUID, agent_version_id: UUID, title: str) -> dict:
        with self.database.transaction(principal) as c:
            facts = current_facts(c, principal, lock=True)
            self._lock_resources(c, principal, [project_id, agent_version_id])
            project = require_resource(c, principal, project_id, "project.read", facts=facts)
            require_resource(c, principal, agent_version_id, "agent.use", facts=facts)
            agent = (
                c.execute(
                    select(s.agent_versions).where(
                        s.agent_versions.c.id == agent_version_id,
                        s.agent_versions.c.org_id == principal.org_id,
                        s.agent_versions.c.published.is_(True),
                    )
                )
                .mappings()
                .first()
            )
            if agent is None:
                raise PlatformError("AGENT_UNAVAILABLE", "This agent version is not available", 409)
            id = uuid4()
            self._resource(c, principal, id, "session", project.classification)
            c.execute(
                insert(s.sessions).values(
                    org_id=principal.org_id,
                    id=id,
                    project_id=project_id,
                    agent_version_id=agent_version_id,
                    title=title,
                )
            )
            audit.record(
                c,
                principal,
                'session.create',
                id,
                'created',
            )
            return {
                "id": id,
                "project_id": project_id,
                "agent_version_id": agent_version_id,
                "title": title,
                "revision": 0,
            }

    def list_sessions(self, principal: Principal, *, after: UUID | None = None, limit: int = 50) -> list[dict]:
        with self.database.transaction(principal) as c:
            predicate = visible_resources(c, principal, "session", "session.read")
            allowed_projects = (
                select(s.resources.c.id)
                .where(visible_resources(c, principal, "project", "project.read"))
                .correlate(None)
            )
            query = (
                select(s.sessions, s.resources.c.revision)
                .join(
                    s.resources, (s.resources.c.id == s.sessions.c.id) & (s.resources.c.org_id == s.sessions.c.org_id)
                )
                .where(predicate)
            )
            query = query.where(s.sessions.c.project_id.in_(allowed_projects))
            if after:
                query = query.where(s.sessions.c.id > after)
            return [dict(r) for r in c.execute(query.order_by(s.sessions.c.id).limit(min(limit, 100))).mappings()]

    def session_detail(self, principal: Principal, id: UUID) -> dict:
        with self.database.transaction(principal) as c:
            resource = require_resource(c, principal, id, "session.read")
            row = (
                c.execute(select(s.sessions).where(s.sessions.c.id == id, s.sessions.c.org_id == principal.org_id))
                .mappings()
                .first()
            )
            if row is None:
                raise PlatformError("RESOURCE_NOT_FOUND", "Session is not accessible", 404)
            require_resource(c, principal, row["project_id"], "project.read")
            messages = (
                c.execute(
                    select(s.messages.c.seq, s.messages.c.role, s.messages.c.content, s.messages.c.run_id)
                    .where(s.messages.c.session_id == id, s.messages.c.org_id == principal.org_id)
                    .order_by(s.messages.c.seq)
                    .limit(200)
                )
                .mappings()
                .all()
            )
            visible = []
            run_visibility = {}
            for message in messages:
                item = dict(message)
                if item["role"] == "assistant":
                    rid = item["run_id"]
                    if rid not in run_visibility:
                        try:
                            self._run(c, principal, rid)
                        except PlatformError as exc:
                            if exc.status not in {401, 403, 404}:
                                raise
                            run_visibility[rid] = False
                        else:
                            run_visibility[rid] = True
                    if not run_visibility[rid]:
                        item["content"] = {
                            "text": "[Content unavailable: source authorization changed]",
                            "redacted": True,
                        }
                visible.append(item)
            runs = (
                c.execute(
                    select(s.runs.c.id, s.runs.c.state, s.runs.c.created_at, s.runs.c.error_code)
                    .where(s.runs.c.org_id == principal.org_id, s.runs.c.session_id == id)
                    .order_by(s.runs.c.created_at.desc(), s.runs.c.id)
                    .limit(30)
                )
                .mappings()
                .all()
            )
            agent_manifest = c.execute(
                select(s.agent_versions.c.manifest).where(
                    s.agent_versions.c.org_id == principal.org_id, s.agent_versions.c.id == row["agent_version_id"]
                )
            ).scalar_one()
            return {
                **dict(row),
                "revision": resource.revision,
                "messages": visible,
                "runs": [dict(r) for r in runs],
                "mcp_server_ids": [item["id"] for item in agent_manifest.get("mcp_servers", [])],
                "supported_modes": ["single", "team"] if agent_manifest.get("team") else ["single"],
            }

    def create_run(self, principal: Principal, session_id: UUID, request: dict, key: str) -> dict:
        if (
            not isinstance(key, str)
            or not 16 <= len(key) <= 128
            or not key.isascii()
            or any(ord(ch) <= 32 for ch in key)
        ):
            raise PlatformError("INVALID_IDEMPOTENCY_KEY", "An explicit bounded Idempotency-Key is required", 422)
        operation = "session.run:" + str(session_id)
        request_hash = canonical_digest("aio-run-request-v1", request)
        key_hash = canonical_digest("aio-idempotency-v1", key)
        with self.database.transaction(principal) as c:
            now = db_now(c)
            c.execute(
                pg_insert(s.idempotency_keys)
                .values(
                    org_id=principal.org_id,
                    actor_id=principal.user_id,
                    operation=operation,
                    key_hash=key_hash,
                    request_hash=request_hash,
                    expires_at=now + timedelta(seconds=self.settings.idempotency_ttl_seconds),
                )
                .on_conflict_do_nothing()
            )
            idem = (
                c.execute(
                    select(s.idempotency_keys)
                    .where(
                        s.idempotency_keys.c.org_id == principal.org_id,
                        s.idempotency_keys.c.actor_id == principal.user_id,
                        s.idempotency_keys.c.operation == operation,
                        s.idempotency_keys.c.key_hash == key_hash,
                    )
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            facts = current_facts(c, principal, lock=True)
            initial_session = (
                c.execute(
                    select(s.sessions).where(s.sessions.c.id == session_id, s.sessions.c.org_id == principal.org_id)
                )
                .mappings()
                .first()
            )
            if initial_session is None:
                raise PlatformError("RESOURCE_NOT_FOUND", "Session is not accessible", 404)
            project_id, agent_id = initial_session["project_id"], initial_session["agent_version_id"]
            self._lock_resources(c, principal, [session_id, project_id, agent_id])
            resource = require_resource(c, principal, session_id, "session.run", facts=facts)
            require_resource(c, principal, project_id, "project.write", facts=facts)
            require_resource(c, principal, agent_id, "agent.use", facts=facts)
            from ..workspaces.service import ArtifactService

            inputs = request.get("input_artifact_ids", [])
            if type(request.get("allow_stdio_attachments", False)) is not bool:
                raise PlatformError("INVALID_INPUTS", "Stdio attachment permission must be an explicit boolean", 422)
            if not isinstance(inputs, list) or len(inputs) > 32:
                raise PlatformError("INVALID_INPUTS", "Input artifact list is invalid", 422)
            input_paths = set()
            capability_sources, capability_reads = set(), set()
            from ..connections.catalog import merge_sources, resolve_connections

            mcp_sources = []
            from ..knowledge.catalog import merge_sources as merge_knowledge_sources, snapshot as snapshot_knowledge

            knowledge_sources = []
            for raw_id in inputs:
                try:
                    artifact_id = UUID(raw_id)
                except (ValueError, TypeError):
                    raise PlatformError("INVALID_INPUTS", "Input artifact ID is invalid", 422) from None
                artifact = ArtifactService.require_artifact(c, principal, artifact_id)
                if artifact["project_id"] != project_id or artifact["path"] in input_paths:
                    raise PlatformError(
                        "INPUT_SCOPE_CONFLICT", "Inputs must belong to this project and have unique paths", 409
                    )
                input_paths.add(artifact["path"])
                capability_sources.update(artifact["capability_source_ids"])
                capability_reads.update(artifact["capability_read_source_ids"])
                mcp_sources = merge_sources(mcp_sources, artifact["mcp_source_refs"])
                knowledge_sources = merge_knowledge_sources(knowledge_sources, artifact["knowledge_source_refs"])

            if idem["request_hash"] != request_hash:
                raise PlatformError("IDEMPOTENCY_CONFLICT", "This key already identifies a different request", 409)
            if idem["run_id"]:
                old = self._run(c, principal, idem["run_id"])
                return {"run_id": old["id"], "state": old["state"], "session_revision": resource.revision}
            session = (
                c.execute(
                    select(s.sessions)
                    .where(s.sessions.c.id == session_id, s.sessions.c.org_id == principal.org_id)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if str(agent_id) != request["agent_version_id"]:
                raise PlatformError("SESSION_AGENT_MISMATCH", "This session uses a fixed agent version", 409)
            if resource.revision != request["expected_session_revision"]:
                raise PlatformError("REVISION_CONFLICT", "Session changed; reload before submitting", 409)
            busy = c.execute(
                select(s.runs.c.id).where(
                    s.runs.c.session_id == session_id,
                    s.runs.c.org_id == principal.org_id,
                    s.runs.c.state.not_in([state.value for state in TERMINAL_STATES]),
                )
            ).first()
            blocked = c.execute(
                select(s.blockers.c.id).where(
                    s.blockers.c.org_id == principal.org_id,
                    s.blockers.c.project_id == project_id,
                    s.blockers.c.resolved_at.is_(None),
                )
            ).first()
            if busy or blocked:
                raise PlatformError(
                    "SESSION_BUSY" if busy else "PROJECT_BLOCKED", "Unresolved work blocks a new run", 409
                )
            agent = (
                c.execute(
                    select(s.agent_versions).where(
                        s.agent_versions.c.id == agent_id, s.agent_versions.c.org_id == principal.org_id
                    )
                )
                .mappings()
                .one()
            )
            if not agent["published"]:
                raise PlatformError("AGENT_UNAVAILABLE", "Agent version is not published", 409)
            # A Run that would need a disabled tool/model/class is refused before any model turn is paid for.
            kill_switches.require_manifest(facts.kill_switches, agent["manifest"], principal.user_id, agent_id)
            mode = request.get("mode", "single")
            if mode not in {"single", "team"}:
                raise PlatformError("ENGINE_MODE_UNAVAILABLE", "Unknown engine mode", 422)
            if mode == "team":
                from .team_contracts import policy_for

                if agent["engine"] != "local-harness-v2":
                    raise PlatformError(
                        "ENGINE_MODE_UNAVAILABLE", "This engine does not support durable team mode", 409
                    )
                policy_for(agent["manifest"], required=True)
            connections = resolve_connections(c, principal, agent["manifest"], request.get("connection_bindings", {}))
            snapshot_manifest = {
                **agent["manifest"],
                "connections": connections,
                "knowledge_snapshot": snapshot_knowledge(c, principal, agent["manifest"]),
            }
            mcp_sources = merge_sources(
                mcp_sources,
                [
                    {"connection_id": item["connection_id"], "credential_revision": item["credential_revision"]}
                    for item in connections
                ],
            )
            from ..skills.catalog import manifest_sources

            own_sources, own_reads = manifest_sources(c, principal, agent["manifest"])
            capability_sources.update(own_sources)
            capability_reads.update(own_reads)
            if len(capability_sources) > 64 or len(capability_reads) > 64:
                raise PlatformError("SOURCE_POLICY_LIMIT", "Inputs have too many capability sources", 409)
            pools = shared_budgets.for_actor(c, principal)
            budget = (
                c.execute(
                    select(s.budgets)
                    .where(
                        s.budgets.c.org_id == principal.org_id,
                        s.budgets.c.owner_id == principal.user_id,
                        s.budgets.c.currency == "USD",
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            # Price/reservation comes from the published server-side manifest, never a client estimate.
            try:
                reserve = Decimal(str(agent["manifest"]["run_budget"]))
            except (KeyError, TypeError, ArithmeticError):
                raise PlatformError("AGENT_UNAVAILABLE", "Agent budget policy is invalid", 409) from None
            if not reserve.is_finite() or reserve <= 0 or reserve.as_tuple().exponent < -6:
                raise PlatformError("AGENT_UNAVAILABLE", "Agent budget policy is invalid", 409)
            if budget is None or budget["consumed"] + budget["reserved"] + reserve > budget["hard_limit"]:
                raise PlatformError("QUOTA_EXCEEDED", "Insufficient budget for another run", 429)
            shared_budgets.check(pools, reserve)
            run_id, snapshot_id = uuid4(), uuid4()
            self._resource(c, principal, run_id, "run", resource.classification)
            c.execute(
                insert(s.manifest_snapshots).values(
                    org_id=principal.org_id,
                    id=snapshot_id,
                    run_id=run_id,
                    content=snapshot_manifest,
                    digest=canonical_digest("aio-manifest-v1", snapshot_manifest),
                )
            )
            c.execute(
                insert(s.runs).values(
                    org_id=principal.org_id,
                    id=run_id,
                    session_id=session_id,
                    project_id=project_id,
                    actor_id=principal.user_id,
                    agent_version_id=agent_id,
                    manifest_snapshot_id=snapshot_id,
                    budget_id=budget["id"],
                    input=request,
                    capability_source_ids=sorted(capability_sources),
                    capability_read_source_ids=sorted(capability_reads),
                    mcp_source_refs=mcp_sources,
                    knowledge_source_refs=knowledge_sources,
                    queue_expires_at=now + timedelta(seconds=self.settings.queue_ttl_seconds),
                )
            )
            c.execute(
                insert(s.messages).values(
                    org_id=principal.org_id,
                    id=uuid4(),
                    session_id=session_id,
                    run_id=run_id,
                    seq=session["message_seq"] + 1,
                    role="user",
                    content={"text": request["message"]},
                )
            )
            c.execute(
                update(s.sessions)
                .where(s.sessions.c.id == session_id)
                .values(message_seq=session["message_seq"] + 1, updated_at=now)
            )
            c.execute(
                update(s.resources)
                .where(s.resources.c.id == session_id, s.resources.c.org_id == principal.org_id)
                .values(revision=resource.revision + 1)
            )
            c.execute(
                update(s.budgets).where(s.budgets.c.id == budget["id"]).values(reserved=budget["reserved"] + reserve)
            )
            c.execute(
                insert(s.reservations).values(
                    org_id=principal.org_id, id=uuid4(), budget_id=budget["id"], run_id=run_id, amount=reserve
                )
            )
            shared_budgets.reserve(c, principal.org_id, pools, reserve, run_id=run_id)
            c.execute(insert(s.jobs).values(org_id=principal.org_id, id=uuid4(), run_id=run_id, not_before=now))
            self._event(c, principal.org_id, run_id, "run.queued", {"state": "queued"})
            audit.record(
                c,
                principal,
                'run.create',
                run_id,
                'queued',
                run_id=run_id,
            )
            c.execute(
                update(s.idempotency_keys)
                .where(
                    s.idempotency_keys.c.org_id == principal.org_id,
                    s.idempotency_keys.c.actor_id == principal.user_id,
                    s.idempotency_keys.c.operation == operation,
                    s.idempotency_keys.c.key_hash == key_hash,
                )
                .values(run_id=run_id)
            )
            return {"run_id": run_id, "state": "queued", "session_revision": resource.revision + 1}

    def get_run(self, principal: Principal, run_id: UUID) -> dict:
        with self.database.transaction(principal) as c:
            row = self._run(c, principal, run_id)
            require_resource(c, principal, row["session_id"], "session.read")
            require_resource(c, principal, row["project_id"], "project.read")
            result = {
                key: row[key]
                for key in (
                    "id",
                    "state",
                    "revision",
                    "generation",
                    "result",
                    "error_code",
                    "cleanup_state",
                    "created_at",
                    "started_at",
                    "deadline_at",
                    "finished_at",
                    "next_event_seq",
                )
            }
            from .team import team_view
            from ..workspaces.checkpoints import checkpoint_view

            return {
                **result,
                "mode": row["input"].get("mode", "single"),
                "team": team_view(c, row),
                "workspace_checkpoint": checkpoint_view(c, row),
            }

    def read_events(self, principal: Principal, run_id: UUID, after: int, limit: int = 100) -> tuple[list[dict], str]:
        with self.database.transaction(principal) as c:
            run = self._run(c, principal, run_id)
            require_resource(c, principal, run["session_id"], "session.read")
            require_resource(c, principal, run["project_id"], "project.read")
            if after < 0 or after > run["next_event_seq"]:
                raise PlatformError("INVALID_EVENT_CURSOR", "Event cursor is outside this run", 409)
            rows = c.execute(
                select(s.events)
                .where(s.events.c.org_id == principal.org_id, s.events.c.run_id == run_id, s.events.c.seq > after)
                .order_by(s.events.c.seq)
                .limit(min(limit, 100))
            ).mappings()
            return [dict(row) for row in rows], run["state"]

    @staticmethod
    def _queued_runs(org_id, now):
        return (
            select(s.runs)
            .join(s.jobs, (s.jobs.c.org_id == s.runs.c.org_id) & (s.jobs.c.run_id == s.runs.c.id))
            .where(
                s.runs.c.org_id == org_id,
                s.runs.c.state.in_(["queued", "waiting_approval", "running"]),
                (
                    (s.runs.c.started_at.is_(None) & (s.runs.c.queue_expires_at > now))
                    | (s.runs.c.started_at.is_not(None) & (s.runs.c.deadline_at > now))
                ),
                s.jobs.c.state == "queued",
                s.jobs.c.not_before <= now,
            )
            .order_by(s.runs.c.created_at, s.runs.c.id)
        )

    def claim_next(self, org_id: UUID, worker_id: str) -> dict | None:
        if not worker_id or len(worker_id) > 128:
            raise ValueError("A bounded worker identity is required")
        # This method is internal, never exposed to browser requests. Runtime role is scoped to the configured org.
        with self.database.scoped(org_id, UUID(int=0)) as c:
            now = db_now(c)
            candidates = (
                c.execute(self._queued_runs(org_id, now).with_only_columns(s.runs.c.id).limit(50)).scalars().all()
            )
            for run_id in candidates:
                # Do not first own Run and then wait on an earlier resource/FK.
                # Savepoint rollback releases every partial lock before skipping
                # a busy candidate; no invocation or external effect is retried.
                with c.begin_nested() as candidate:
                    if not try_lock_run_resources(c, org_id, run_id):
                        candidate.rollback()
                        continue
                    claimed = self._claim_locked(c, org_id, run_id, worker_id)
                    if claimed is None:
                        candidate.rollback()
                        continue
                    return claimed
            return None

    def _claim_locked(self, c, org_id: UUID, run_id: UUID, worker_id: str) -> dict | None:
        """Only claim_next may call this, after locking the canonical resource prefix."""
        now = db_now(c)
        current = (
            c.execute(
                self._queued_runs(org_id, now).where(s.runs.c.id == run_id).with_for_update(of=s.runs, skip_locked=True)
            )
            .mappings()
            .first()
        )
        if current is None:
            return None
        run = dict(current)
        job = (
            c.execute(
                select(s.jobs)
                .where(
                    s.jobs.c.run_id == run_id,
                    s.jobs.c.org_id == org_id,
                    s.jobs.c.state == "queued",
                    s.jobs.c.not_before <= now,
                )
                .with_for_update(skip_locked=True)
            )
            .mappings()
            .first()
        )
        if job is None:
            return None
        generation = run["generation"] + 1
        deadline = run["deadline_at"] or now + timedelta(seconds=self.settings.run_timeout_seconds)
        attempt_id = uuid4()
        c.execute(
            update(s.runs)
            .where(s.runs.c.id == run_id)
            .values(
                state="preparing",
                generation=generation,
                attempt_id=attempt_id,
                started_at=run["started_at"] or now,
                deadline_at=deadline,
                revision=s.runs.c.revision + 1,
            )
        )
        c.execute(
            update(s.jobs)
            .where(s.jobs.c.id == job["id"])
            .values(
                state="leased",
                lease_owner=worker_id,
                lease_version=generation,
                attempt_count=s.jobs.c.attempt_count + 1,
                lease_expires_at=min(deadline, now + timedelta(seconds=self.settings.lease_seconds)),
            )
        )
        self._event(c, org_id, run_id, "run.preparing", {"state": "preparing", "generation": generation})
        return {
            **run,
            "state": "preparing",
            "generation": generation,
            "attempt_id": attempt_id,
            "deadline_at": deadline,
        }

    def heartbeat(self, org_id: UUID, run_id: UUID, generation: int, worker_id: str) -> None:
        with self.database.scoped(org_id, UUID(int=0)) as c:
            exists = c.execute(select(s.runs.c.id).where(s.runs.c.org_id == org_id, s.runs.c.id == run_id)).first()
            if exists is None:
                raise PlatformError("STALE_GENERATION", "Run lease is not current", 409)
            lock_run_resources(c, org_id, run_id)
            run = (
                c.execute(select(s.runs).where(s.runs.c.org_id == org_id, s.runs.c.id == run_id).with_for_update())
                .mappings()
                .one_or_none()
            )
            if run is None:
                raise PlatformError("STALE_GENERATION", "Run lease is not current", 409)
            require_generation(run["generation"], generation)
            job = (
                c.execute(select(s.jobs).where(s.jobs.c.org_id == org_id, s.jobs.c.run_id == run_id).with_for_update())
                .mappings()
                .one()
            )
            now = db_now(c)
            if (
                job["state"] != "leased"
                or job["lease_owner"] != worker_id
                or job["lease_version"] != generation
                or job["lease_expires_at"] <= now
                or run["deadline_at"] <= now
                or run["state"] in {state.value for state in TERMINAL_STATES} | {"recovery_required"}
            ):
                raise PlatformError("STALE_GENERATION", "Run lease is no longer active", 409)
            c.execute(
                update(s.jobs)
                .where(s.jobs.c.id == job["id"])
                .values(lease_expires_at=min(run["deadline_at"], now + timedelta(seconds=self.settings.lease_seconds)))
            )

    def cancel_run(self, principal: Principal, run_id: UUID) -> dict:
        with self.database.transaction(principal) as c:
            facts = current_facts(c, principal, lock=True)
            require_resource(c, principal, run_id, "run.cancel", facts=facts)
            info = self._run(c, principal, run_id, validate_sources=False)
            lock_run_resources(c, principal.org_id, run_id)
            require_resource(c, principal, run_id, "run.cancel", facts=facts)
            # Budget comes before Run in the shared lock order.
            shared_budgets.lock_subject(c, principal.org_id, run_id=run_id)
            budget = (
                c.execute(select(s.budgets).where(s.budgets.c.id == info["budget_id"]).with_for_update())
                .mappings()
                .one()
            )
            run = self._run(c, principal, run_id, lock=True, validate_sources=False)
            if run["state"] in {s.value for s in TERMINAL_STATES} | {"recovery_required", "cancel_requested"}:
                return {"run_id": run_id, "state": run["state"]}
            target = "cancelled" if run["state"] == "queued" else "cancel_requested"
            require_transition(run["state"], target)
            c.execute(
                update(s.runs)
                .where(s.runs.c.id == run_id)
                .values(
                    state=target,
                    revision=s.runs.c.revision + 1,
                    finished_at=db_now(c) if target == "cancelled" else None,
                )
            )
            c.execute(
                update(s.jobs)
                .where(s.jobs.c.org_id == principal.org_id, s.jobs.c.run_id == run_id)
                .values(state="cancelled" if target == "cancelled" else "stopping")
            )
            if target == "cancelled":
                from .team import stop_team

                stop_team(c, run, "cancelled", "RUN_CANCELLED", self._event)
                from ..workspaces.checkpoints import retire

                retire(c, run)
                active_cell = c.execute(
                    select(s.sandbox_leases.c.id).where(
                        s.sandbox_leases.c.org_id == principal.org_id,
                        s.sandbox_leases.c.run_id == run_id,
                        s.sandbox_leases.c.state != "destroyed",
                    )
                ).first()
                if not active_cell:
                    from ..workspaces.exports import unbound_manifest

                    c.execute(
                        update(s.workspace_leases)
                        .where(
                            s.workspace_leases.c.org_id == principal.org_id,
                            s.workspace_leases.c.run_id == run_id,
                            unbound_manifest(s.workspace_leases.c.export_manifest),
                        )
                        .values(state="released", storage_reserved_bytes=0)
                    )
                reservation = (
                    c.execute(select(s.reservations).where(s.reservations.c.run_id == run_id)).mappings().one()
                )
                if reservation["state"] == "reserved":
                    shared_budgets.change(c, principal.org_id, run_id=run_id, release=reservation["amount"])
                    c.execute(
                        update(s.budgets)
                        .where(s.budgets.c.id == budget["id"])
                        .values(reserved=budget["reserved"] - reservation["amount"])
                    )
                    c.execute(
                        update(s.reservations).where(s.reservations.c.id == reservation["id"]).values(state="released")
                    )
            else:
                c.execute(
                    insert(s.outbox).values(
                        org_id=principal.org_id,
                        id=uuid4(),
                        aggregate_id=run_id,
                        kind="run.stop_requested",
                        payload={"generation": run["generation"]},
                    )
                )
            self._event(c, principal.org_id, run_id, "run." + target, {"state": target})
            audit.record(
                c,
                principal,
                'run.cancel',
                run_id,
                target,
                run_id=run_id,
            )
            return {"run_id": run_id, "state": target}

    def transition_run(self, principal: Principal, run_id: UUID, generation: int, target: str) -> dict:
        """Internal worker transition. Success must use a result-publishing operation, not this helper."""
        if target in {"succeeded", "recovery_required", "cancelled"}:
            raise PlatformError(
                "INVALID_TRANSITION", "This transition requires a dedicated result/reconciliation operation", 409
            )
        with self.database.transaction(principal) as c:
            current_facts(c, principal, lock=True)
            run = self._run(c, principal, run_id, lock=True)
            require_generation(run["generation"], generation)
            require_transition(run["state"], target)
            now = db_now(c)
            job = (
                c.execute(
                    select(s.jobs)
                    .where(s.jobs.c.run_id == run_id, s.jobs.c.org_id == principal.org_id)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if job["state"] != "leased" or job["lease_version"] != generation or job["lease_expires_at"] <= now:
                raise PlatformError("STALE_GENERATION", "Execution lease is not active", 409)
            if run["deadline_at"] <= now:
                raise PlatformError("RUN_DEADLINE_EXCEEDED", "Run deadline has expired", 409)
            c.execute(update(s.runs).where(s.runs.c.id == run_id).values(state=target, revision=s.runs.c.revision + 1))
            self._event(c, principal.org_id, run_id, "run." + target, {"state": target})
            return {"run_id": run_id, "state": target}

    def plan_invocation(self, principal: Principal, run_id: UUID, generation: int, action: ActionSpec) -> dict:
        if (action.org_id, action.actor_user_id, action.run_id) != (principal.org_id, principal.user_id, run_id):
            raise PlatformError("ACTION_SCOPE_DENIED", "Action does not match the current run identity", 403)
        with self.database.transaction(principal) as c:
            facts = current_facts(c, principal, lock=True)
            run = self._run(c, principal, run_id, lock=True)
            require_generation(run["generation"], generation)
            require_resource(c, principal, run["project_id"], "project.write")
            require_resource(c, principal, run["session_id"], "session.run")
            require_resource(c, principal, run["agent_version_id"], "agent.use")
            now = db_now(c)
            if (
                run["state"] not in {"running", "waiting_approval"}
                or action.not_after <= now
                or action.not_after > run["deadline_at"]
            ):
                raise PlatformError("ACTION_NOT_EXECUTABLE", "Run/action is not executable", 409)
            job = (
                c.execute(
                    select(s.jobs)
                    .where(s.jobs.c.run_id == run_id, s.jobs.c.org_id == principal.org_id)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if job["state"] != "leased" or job["lease_version"] != generation or job["lease_expires_at"] <= now:
                raise PlatformError("STALE_GENERATION", "Execution lease is not active", 409)
            snapshot = c.execute(
                select(s.manifest_snapshots).where(s.manifest_snapshots.c.id == run["manifest_snapshot_id"])
            )
            manifest = snapshot.mappings().one()["content"]
            tool = next((t for t in manifest.get("tools", []) if t.get("id") == str(action.tool_version_id)), None)
            if tool is None or tool.get("risk") not in {"R0", "R1", "R2"}:
                raise PlatformError("TOOL_NOT_ALLOWED", "Tool is not in the permitted run manifest", 403)
            existing = (
                c.execute(
                    select(s.invocations).where(
                        s.invocations.c.run_id == run_id,
                        s.invocations.c.org_id == principal.org_id,
                        s.invocations.c.logical_call_id == action.logical_call_id,
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                if existing["action_digest"] != action.digest:
                    raise PlatformError("ACTION_CONFLICT", "Logical call already has different immutable contents", 409)
                return {"invocation_id": existing["id"], "state": existing["state"]}
            if run["state"] != "running":
                raise PlatformError("RUN_WAITING_APPROVAL", "Resolve the pending action before planning another", 409)
            invocation_id = uuid4()
            needs_approval = tool["risk"] == "R2"
            state = "waiting_approval" if needs_approval else "authorized"
            c.execute(
                insert(s.invocations).values(
                    org_id=principal.org_id,
                    id=invocation_id,
                    run_id=run_id,
                    logical_call_id=action.logical_call_id,
                    action=action.model_dump(mode="json"),
                    action_digest=action.digest,
                    state=state,
                    risk_class=tool["risk"],
                    external_operation_key=canonical_digest("aio-operation-v1", [str(run_id), action.logical_call_id]),
                )
            )
            approval_id = None
            if needs_approval:
                approval_id = uuid4()
                self._resource(c, principal, approval_id, "approval")
                c.execute(
                    insert(s.approvals).values(
                        org_id=principal.org_id,
                        id=approval_id,
                        invocation_id=invocation_id,
                        action_digest=action.digest,
                        requested_by=principal.user_id,
                        expires_at=min(action.not_after, now + timedelta(seconds=self.settings.approval_ttl_seconds)),
                    )
                )
                c.execute(
                    update(s.runs)
                    .where(s.runs.c.id == run_id)
                    .values(state="waiting_approval", revision=s.runs.c.revision + 1)
                )
                self._event(
                    c,
                    principal.org_id,
                    run_id,
                    "approval.required",
                    {
                        "approval_id": str(approval_id),
                        "invocation_id": str(invocation_id),
                        "action_digest": action.digest,
                    },
                )
            audit.record(
                c,
                principal,
                'tool.planned',
                invocation_id,
                state,
                m.ToolPlanned(tool_version_id=action.tool_version_id, action_digest=action.digest),
                run_id=run_id,
                decision="approval_required" if tool["risk"] == "R2" else "allow",
                reason_code="APPROVAL_REQUIRED" if tool["risk"] == "R2" else "ALLOWED",
                policy_revision=facts.policy_revision,
                subject_revision=0,
                risk_class=tool["risk"],
            )
            return {
                "invocation_id": invocation_id,
                "state": state,
                "approval_id": approval_id,
                "action_digest": action.digest,
            }

    def decide_approval(
        self, principal: Principal, approval_id: UUID, revision: int, digest: str, decision: str
    ) -> dict:
        if decision not in {"approve", "reject"}:
            raise PlatformError("INVALID_REQUEST", "Unknown approval decision", 422)
        pending_error: PlatformError | None = None
        with self.database.transaction(principal) as c:
            facts = current_facts(c, principal, lock=True)
            require_resource(c, principal, approval_id, "approval.decide", facts=facts)
            info = (
                c.execute(
                    select(s.approvals, s.invocations.c.run_id)
                    .join(
                        s.invocations,
                        (s.invocations.c.id == s.approvals.c.invocation_id)
                        & (s.invocations.c.org_id == s.approvals.c.org_id),
                    )
                    .where(s.approvals.c.org_id == principal.org_id, s.approvals.c.id == approval_id)
                )
                .mappings()
                .first()
            )
            if info is None:
                raise PlatformError("RESOURCE_NOT_FOUND", "Approval is not accessible", 404)
            lock_run_resources(c, principal.org_id, info["run_id"])
            require_resource(c, principal, approval_id, "approval.decide", facts=facts, lock=True)
            run = c.execute(select(s.runs).where(s.runs.c.id == info["run_id"]).with_for_update()).mappings().one()
            job = (
                c.execute(
                    select(s.jobs)
                    .where(s.jobs.c.org_id == principal.org_id, s.jobs.c.run_id == run["id"])
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            invocation = c.execute(
                select(s.invocations).where(s.invocations.c.id == info["invocation_id"]).with_for_update()
            ).mappings().one()
            approval = (
                c.execute(select(s.approvals).where(s.approvals.c.id == approval_id).with_for_update()).mappings().one()
            )
            target = "approved" if decision == "approve" else "rejected"
            if approval["action_digest"] != digest:
                raise PlatformError("ACTION_CHANGED", "Approval refers to different action contents", 409)
            if approval["state"] != "pending":
                if approval["state"] == target and approval["decided_by"] == principal.user_id:
                    return {"approval_id": approval_id, "state": target, "revision": approval["revision"]}
                raise PlatformError("APPROVAL_CONFLICT", "Approval has already been resolved", 409)
            if approval["revision"] != revision:
                raise PlatformError("REVISION_CONFLICT", "Approval changed; reload before deciding", 409)
            if approval["requires_different_actor"] and approval["requested_by"] == principal.user_id:
                raise PlatformError("SEPARATION_OF_DUTIES", "This action requires a different authorized approver", 403)
            now = db_now(c)
            if run["state"] != "waiting_approval":
                raise PlatformError("APPROVAL_INVALIDATED", "The run is no longer waiting for this action", 409)
            if approval["expires_at"] <= now or run["deadline_at"] <= now:
                target = "expired"
                pending_error = PlatformError("APPROVAL_EXPIRED", "Approval has expired", 410)
            c.execute(
                update(s.approvals)
                .where(s.approvals.c.id == approval_id)
                .values(state=target, revision=approval["revision"] + 1, decided_by=principal.user_id, decided_at=now)
            )
            c.execute(
                update(s.invocations)
                .where(s.invocations.c.id == approval["invocation_id"])
                .values(state="authorized" if target == "approved" else "denied", revision=s.invocations.c.revision + 1)
            )
            c.execute(
                update(s.runs).where(s.runs.c.id == run["id"]).values(state="running", revision=s.runs.c.revision + 1)
            )
            if job["state"] == "waiting_approval":
                c.execute(
                    update(s.jobs)
                    .where(s.jobs.c.id == job["id"])
                    .values(state="queued", not_before=now, lease_owner=None, lease_expires_at=None)
                )
            self._event(
                c, principal.org_id, run["id"], "approval.resolved", {"approval_id": str(approval_id), "state": target}
            )
            audit_id = uuid4()
            audit.record(
                c,
                principal,
                'approval.decide',
                approval_id,
                target,
                m.ApprovalDecided(invocation_id=approval["invocation_id"], requested_by=approval["requested_by"], requires_different_actor=approval["requires_different_actor"], action_digest=digest),
                run_id=run['id'],
                decision="allow",
                reason_code="ALLOWED",
                policy_revision=facts.policy_revision,
                subject_revision=approval["revision"] + 1,
                risk_class=invocation["risk_class"],
                event_id=audit_id,
            )
            audit.require_recorded(
                c, principal, "approval.decide", approval_id, event_id=audit_id, run_id=run["id"]
            )
        # Persist expiry before returning the error; raising inside the transaction would roll it back.
        if pending_error:
            raise pending_error
        return {"approval_id": approval_id, "state": target, "revision": revision + 1}

    def list_approvals(self, principal: Principal, *, limit: int = 50) -> list[dict]:
        with self.database.transaction(principal) as c:
            facts = current_facts(c, principal)
            predicates = []
            for action in ("approval.read", "approval.decide"):
                if action not in facts.denied_actions:
                    predicates.append(visible_resources(c, principal, "approval", action))
            if not predicates:
                return []
            from sqlalchemy import or_

            query = (
                select(
                    s.approvals.c.id,
                    s.approvals.c.state,
                    s.approvals.c.revision,
                    s.approvals.c.action_digest,
                    s.approvals.c.expires_at,
                    s.approvals.c.requested_by,
                    s.invocations.c.run_id,
                    s.invocations.c.logical_call_id,
                )
                .join(
                    s.resources, (s.resources.c.id == s.approvals.c.id) & (s.resources.c.org_id == s.approvals.c.org_id)
                )
                .join(
                    s.invocations,
                    (s.invocations.c.id == s.approvals.c.invocation_id)
                    & (s.invocations.c.org_id == s.approvals.c.org_id),
                )
            )
            rows = (
                c.execute(
                    query.where(or_(*predicates))
                    .order_by(s.approvals.c.created_at.desc(), s.approvals.c.id)
                    .limit(min(limit, 100))
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    def approval_detail(self, principal: Principal, approval_id: UUID) -> dict:
        with self.database.transaction(principal) as c:
            current_facts(c, principal)
            try:
                require_resource(c, principal, approval_id, "approval.read")
            except PlatformError as exc:
                if exc.status != 404:
                    raise
                require_resource(c, principal, approval_id, "approval.decide")
            row = (
                c.execute(
                    select(s.approvals).where(s.approvals.c.org_id == principal.org_id, s.approvals.c.id == approval_id)
                )
                .mappings()
                .first()
            )
            if row is None:
                raise PlatformError("RESOURCE_NOT_FOUND", "Approval is not accessible", 404)
            inv = (
                c.execute(
                    select(s.invocations).where(
                        s.invocations.c.org_id == principal.org_id, s.invocations.c.id == row["invocation_id"]
                    )
                )
                .mappings()
                .one()
            )
            # Approval visibility is not permission to read the entire private Session or raw credentials.
            tool_id = UUID(inv["action"]["tool_version_id"])
            tool = (
                c.execute(
                    select(s.tool_versions.c.name, s.tool_versions.c.risk).where(
                        s.tool_versions.c.org_id == principal.org_id, s.tool_versions.c.id == tool_id
                    )
                )
                .mappings()
                .first()
            )
            return {
                "approval_id": row["id"],
                "run_id": inv["run_id"],
                "invocation_id": inv["id"],
                "state": row["state"],
                "revision": row["revision"],
                "action_digest": row["action_digest"],
                "expires_at": row["expires_at"],
                "summary": {
                    "tool": tool["name"] if tool else "restricted-tool",
                    "risk": tool["risk"] if tool else inv["risk_class"],
                },
            }

    def project_detail(self, principal: Principal, id: UUID) -> dict:
        with self.database.transaction(principal) as c:
            resource = require_resource(c, principal, id, "project.read")
            row = (
                c.execute(select(s.projects).where(s.projects.c.org_id == principal.org_id, s.projects.c.id == id))
                .mappings()
                .one()
            )
            try:
                require_resource(c, principal, id, "project.members.manage")
            except PlatformError:
                manage = False
            else:
                manage = True
            return {**dict(row), "revision": resource.revision, "can_manage": manage}

    def rename_session(self, principal: Principal, id: UUID, name: str, expected_revision: int) -> dict:
        with self.database.transaction(principal) as c:
            facts = current_facts(c, principal, lock=True)
            resource = require_resource(c, principal, id, "session.update", facts=facts, lock=True)
            if resource.revision != expected_revision:
                raise PlatformError("REVISION_CONFLICT", "Session changed; refresh first", 409)
            c.execute(
                update(s.sessions)
                .where(s.sessions.c.org_id == principal.org_id, s.sessions.c.id == id)
                .values(title=name, updated_at=db_now(c))
            )
            c.execute(
                update(s.resources)
                .where(s.resources.c.org_id == principal.org_id, s.resources.c.id == id)
                .values(revision=resource.revision + 1)
            )
            audit.record(
                c,
                principal,
                'session.rename',
                id,
                'renamed',
            )
            return {"id": id, "title": name, "revision": resource.revision + 1}

    def archive_session(self, principal: Principal, id: UUID, expected_revision: int) -> dict:
        with self.database.transaction(principal) as c:
            facts = current_facts(c, principal, lock=True)
            resource = require_resource(c, principal, id, "session.delete", facts=facts, lock=True)
            if resource.revision != expected_revision:
                raise PlatformError("REVISION_CONFLICT", "Session changed; refresh first", 409)
            busy = c.execute(
                select(s.runs.c.id).where(
                    s.runs.c.org_id == principal.org_id,
                    s.runs.c.session_id == id,
                    s.runs.c.state.not_in([state.value for state in TERMINAL_STATES]),
                )
            ).first()
            if busy:
                raise PlatformError(
                    "SESSION_BUSY", "Resolve or stop active runs before archiving this conversation", 409
                )
            c.execute(
                update(s.resources)
                .where(s.resources.c.org_id == principal.org_id, s.resources.c.id == id)
                .values(status="archived", revision=resource.revision + 1)
            )
            audit.record(
                c,
                principal,
                'session.archive',
                id,
                'archived',
            )
            return {"id": id, "archived": True}
