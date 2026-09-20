"""Durable control authority for isolated, credential-bearing stdio processes."""

from contextlib import contextmanager
from datetime import timezone
import re
from uuid import UUID, uuid4

from sqlalchemy import select, insert, update, func

from ..auth.principal import Principal
from ..db import schema as s
from ..platform_errors import PlatformError
from ..policy.repository import current_facts, db_now, require_resource
from ..runtime.actions import canonical_digest
from .catalog import active_binding, binding_contract, current_connection


def active_stdio(c, org, run_id):
    return (
        c.execute(
            select(s.mcp_stdio_leases.c.id)
            .where(
                s.mcp_stdio_leases.c.org_id == org,
                s.mcp_stdio_leases.c.run_id == run_id,
                s.mcp_stdio_leases.c.state != "destroyed",
            )
            .limit(1)
        ).first()
        is not None
    )


def lost_stdio(c, org, run_id):
    return (
        c.execute(
            select(s.mcp_stdio_leases.c.id)
            .where(
                s.mcp_stdio_leases.c.org_id == org,
                s.mcp_stdio_leases.c.run_id == run_id,
                s.mcp_stdio_leases.c.close_reason == "lost",
            )
            .limit(1)
        ).first()
        is not None
    )


def stdio_spec_digest(spec):
    version = spec.get("schema_version")
    if type(version) is not int or version not in {1, 2}:
        raise PlatformError("STDIO_SPEC_INVALID", "Unsupported immutable stdio spec version", 403)
    return canonical_digest(f"aio-stdio-spec-v{version}", spec)


class StdioAuthority:
    def __init__(self, connector):
        self.connector, self.store, self.service, self.db = connector, connector.store, connector.service, connector.db
        from .stdio_inputs import StdioInputStore

        self.inputs = StdioInputStore(self)

    @staticmethod
    def deny(code="STDIO_AUTHORITY_DENIED"):
        raise PlatformError(code, "Stdio operation is not bound to a current authorized execution", 403)

    @contextmanager
    def scope(self, operation, body):
        context = self.connector.authorize(operation, body)
        if operation == "call":
            handle = context["handle"]
            with self.store.locked(handle) as (c, run, job, now, facts):
                current = (
                    c.execute(
                        select(s.invocations).where(
                            s.invocations.c.org_id == run["org_id"], s.invocations.c.id == context["invocation"]["id"]
                        )
                    )
                    .mappings()
                    .one()
                )
                self.store._validate_invocation(c, handle, run, current, now, facts)
                yield c, handle.principal, context["binding"], "run", run["id"], run["generation"], run["deadline_at"]
        elif operation == "discover":
            p = context["principal"]
            with self.service.write(p) as c:
                job = (
                    c.execute(
                        select(s.mcp_discoveries)
                        .where(
                            s.mcp_discoveries.c.org_id == p.org_id, s.mcp_discoveries.c.id == context["discovery"]["id"]
                        )
                        .with_for_update()
                    )
                    .mappings()
                    .one()
                )
                conn = current_connection(c, p, job["connection_id"], active=False, allow_draft=True)
                if (
                    job["state"] != "running"
                    or job["expires_at"] <= db_now(c)
                    or conn["credential_ref"] != job["binding_id"]
                ):
                    self.deny()
                binding = active_binding(c, p, conn)
                yield c, p, binding, "discovery", job["id"], 1, job["expires_at"]
        else:
            self.deny()

    def prepare(self, operation, body):
        with self.scope(operation, body) as (c, p, binding, kind, target, generation, deadline):
            profile = self.service.profile(binding["endpoint_id"], binding["endpoint_digest"])
            if profile.get("transport") != "stdio":
                self.deny()
            template = profile["stdio"]
            input_manifest = self.inputs.manifest(c, p, kind, target, template)
            query = select(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.org_id == p.org_id)
            if kind == "run":
                query = query.where(
                    s.mcp_stdio_leases.c.run_id == target,
                    s.mcp_stdio_leases.c.generation == generation,
                    s.mcp_stdio_leases.c.connection_id == binding["connection_id"],
                )
            else:
                query = query.where(s.mcp_stdio_leases.c.discovery_id == target)
            existing = c.execute(query.with_for_update()).mappings().first()
            if existing:
                if (
                    existing["credential_ref"] != binding["id"]
                    or existing["state"] not in {"preparing", "ready"}
                    or stdio_spec_digest(existing["spec"]) != existing["spec_digest"]
                    or existing["spec"].get("input_manifest") != input_manifest
                ):
                    raise PlatformError(
                        "STDIO_SESSION_LOST", "The original stdio process cannot be silently replaced", 409
                    )
                return {
                    "spec": existing["spec"],
                    "needs_inputs": bool(input_manifest) and existing["state"] == "preparing",
                }
            if (
                c.execute(
                    select(func.count()).select_from(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.org_id == p.org_id)
                ).scalar_one()
                >= 10000
            ):
                raise PlatformError("STDIO_LEASE_QUOTA", "Stdio lifecycle retention has reached its bound", 429)
            id = uuid4()
            spec = {
                "schema_version": 1,
                "kind": "mcp_stdio",
                "binding_id": str(id),
                "org_id": str(p.org_id),
                "target_kind": kind,
                "target_id": str(target),
                "generation": generation,
                "connection_id": str(binding["connection_id"]),
                "credential_ref": str(binding["id"]),
                "credential_revision": binding["revision"],
                "endpoint_id": binding["endpoint_id"],
                "endpoint_digest": binding["endpoint_digest"],
                "profile_id": template["profile_id"],
                "image_digest": template["image_digest"],
                "template_digest": template["template_digest"],
                "deadline": deadline.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "target_slot": "connector/stdio/" + str(binding["connection_id"]),
            }
            if input_manifest is not None:
                spec.update(schema_version=2, input_manifest=input_manifest)
            c.execute(
                insert(s.mcp_stdio_leases).values(
                    org_id=p.org_id,
                    id=id,
                    run_id=target if kind == "run" else None,
                    discovery_id=target if kind == "discovery" else None,
                    generation=generation,
                    connection_id=binding["connection_id"],
                    credential_ref=binding["id"],
                    credential_revision=binding["revision"],
                    requested_by=p.user_id,
                    membership_revision=p.membership_revision,
                    spec=spec,
                    spec_digest=stdio_spec_digest(spec),
                    expires_at=deadline,
                )
            )
            if kind == "run":
                c.execute(
                    update(s.runs)
                    .where(s.runs.c.id == target)
                    .values(cleanup_state="pending", revision=s.runs.c.revision + 1)
                )
                self.store.platform._event(
                    c,
                    p.org_id,
                    target,
                    "stdio.preparing",
                    {"binding_id": str(id), "connection_id": str(binding["connection_id"])},
                )
            return {"spec": spec, "needs_inputs": bool(input_manifest)}

    def row(self, c, spec, *, lock=False):
        try:
            org, id = UUID(spec["org_id"]), UUID(spec["binding_id"])
        except (TypeError, ValueError, KeyError):
            self.deny()
        query = select(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.org_id == org, s.mcp_stdio_leases.c.id == id)
        row = c.execute(query.with_for_update() if lock else query).mappings().first()
        if row is None or row["spec"] != spec or row["spec_digest"] != stdio_spec_digest(spec):
            self.deny()
        return row

    def live(self, c, row):
        if row["state"] not in {"preparing", "ready"} or row["expires_at"] <= db_now(c):
            self.deny()
        if row["run_id"]:
            run = (
                c.execute(select(s.runs).where(s.runs.c.org_id == row["org_id"], s.runs.c.id == row["run_id"]))
                .mappings()
                .one()
            )
            member = (
                c.execute(
                    select(s.memberships).where(
                        s.memberships.c.org_id == row["org_id"], s.memberships.c.user_id == run["actor_id"]
                    )
                )
                .mappings()
                .one()
            )
            p = Principal(row["org_id"], run["actor_id"], member["revision"])
            self.store.platform._run(c, p, run["id"])
            for id, action in [
                (run["project_id"], "project.write"),
                (run["session_id"], "session.run"),
                (run["agent_version_id"], "agent.use"),
            ]:
                require_resource(c, p, id, action)
            job = (
                c.execute(select(s.jobs).where(s.jobs.c.org_id == row["org_id"], s.jobs.c.run_id == run["id"]))
                .mappings()
                .one()
            )
            if (
                run["generation"] != row["generation"]
                or run["state"] not in {"preparing", "running", "waiting_approval"}
                or job["state"] not in {"leased", "waiting_approval"}
            ):
                self.deny()
            if job["state"] == "leased" and (
                job["lease_version"] != row["generation"]
                or not job["lease_expires_at"]
                or job["lease_expires_at"] <= db_now(c)
            ):
                self.deny()
        else:
            p = Principal(row["org_id"], row["requested_by"], row["membership_revision"])
            job = (
                c.execute(
                    select(s.mcp_discoveries).where(
                        s.mcp_discoveries.c.org_id == row["org_id"], s.mcp_discoveries.c.id == row["discovery_id"]
                    )
                )
                .mappings()
                .one()
            )
            if job["state"] != "running" or job["expires_at"] <= db_now(c):
                self.deny()
        current_facts(c, p)
        conn = current_connection(c, p, row["connection_id"], active=bool(row["run_id"]), allow_draft=not row["run_id"])
        binding = active_binding(c, p, conn)
        profile = self.service.profile(binding["endpoint_id"], binding["endpoint_digest"])
        if (
            binding["id"] != row["credential_ref"]
            or binding["revision"] != row["credential_revision"]
            or profile.get("transport") != "stdio"
        ):
            self.deny()
        if (
            profile["stdio"]["template_digest"] != row["spec"]["template_digest"]
            or profile["stdio"]["image_digest"] != row["spec"]["image_digest"]
        ):
            self.deny()
        return p, binding

    def authorize(self, operation, payload):
        spec = payload.get("spec")
        if not isinstance(spec, dict):
            self.deny()
        try:
            org = UUID(spec["org_id"])
        except (KeyError, TypeError, ValueError):
            self.deny()
        context = payload.get("context")
        if operation in {"stdio.claim", "stdio.rpc"}:
            if not isinstance(context, dict) or set(context) != {"operation", "payload"}:
                self.deny()
            kind = context["operation"]
            if kind not in {"call", "discover"}:
                self.deny()
            result = self.connector.authorize(kind, context["payload"])
            if binding_contract(result["binding"]) != context["payload"]["binding"]:
                self.deny()
            target = context["payload"].get("run_id") if kind == "call" else context["payload"].get("discovery_id")
            if (
                target != spec["target_id"]
                or spec["target_kind"] != ("run" if kind == "call" else "discovery")
                or context["payload"]["binding"]["credential_ref"] != spec["credential_ref"]
            ):
                self.deny()
            if operation == "stdio.rpc":
                method, params = payload.get("method"), payload.get("params")
                if method == "tools/call":
                    expected = {
                        "name": context["payload"].get("tool_name"),
                        "arguments": context["payload"].get("arguments"),
                        "_meta": {"aio_operation_key": context["payload"].get("operation_key")},
                    }
                    if kind != "call" or params != expected:
                        self.deny()
                elif method == "initialize":
                    if (
                        not isinstance(params, dict)
                        or params.get("protocolVersion") != "2025-06-18"
                        or params.get("capabilities") != {}
                    ):
                        self.deny()
                elif method == "notifications/initialized":
                    if params != {}:
                        self.deny()
                elif method == "tools/list":
                    if (
                        not isinstance(params, dict)
                        or set(params) - {"cursor"}
                        or (
                            "cursor" in params
                            and (not isinstance(params["cursor"], str) or len(params["cursor"]) > 256)
                        )
                    ):
                        self.deny()
                else:
                    self.deny()
        with self.db.scoped(org, UUID(int=0)) as c:
            # A receipt can run after revocation, so these are structural locks, not new business grants.
            # Match Worker/storage ordering before updating Run state or inserting its event/FK rows.
            info = self.row(c, spec)
            if info["run_id"]:
                from ..policy.repository import lock_run_resources

                lock_run_resources(c, org, info["run_id"])
                c.execute(
                    select(s.runs.c.id).where(s.runs.c.org_id == org, s.runs.c.id == info["run_id"]).with_for_update()
                ).one()
            else:
                c.execute(
                    select(s.organizations.c.id).where(s.organizations.c.id == org).with_for_update(read=True)
                ).one()
                c.execute(
                    select(s.mcp_discoveries.c.id)
                    .where(s.mcp_discoveries.c.org_id == org, s.mcp_discoveries.c.id == info["discovery_id"])
                    .with_for_update()
                ).one()
            row = self.row(c, spec, lock=True)
            node = payload.get("manager_id")
            if operation.startswith("stdio."):
                if not isinstance(node, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", node):
                    self.deny()
                if row["manager_id"] is not None and row["manager_id"] != node:
                    self.deny("STDIO_NODE_MISMATCH")
            if operation == "stdio.stopped":
                if row["manager_id"] != node:
                    self.deny()
                if row["state"] != "destroyed":
                    c.execute(
                        update(s.mcp_stdio_leases)
                        .where(s.mcp_stdio_leases.c.id == row["id"])
                        .values(state="destroyed", close_reason="requested" if row["state"] == "stopping" else "lost")
                    )
                    if row["run_id"]:
                        compute = c.execute(
                            select(s.sandbox_leases.c.id).where(
                                s.sandbox_leases.c.org_id == org,
                                s.sandbox_leases.c.run_id == row["run_id"],
                                s.sandbox_leases.c.state != "destroyed",
                            )
                        ).first()
                        if not compute and not active_stdio(c, org, row["run_id"]):
                            c.execute(
                                update(s.runs)
                                .where(s.runs.c.id == row["run_id"])
                                .values(cleanup_state="clean", revision=s.runs.c.revision + 1)
                            )
                        self.store.platform._event(
                            c, org, row["run_id"], "stdio.stopped", {"binding_id": str(row["id"])}
                        )
                return
            if operation in {"stop", "status", "stdio.stop"}:
                return
            self.live(c, row)
            if operation == "stdio.claim":
                if row["manager_id"] is None:
                    c.execute(
                        update(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.id == row["id"]).values(manager_id=node)
                    )
                return
            if operation == "stdio.ready":
                if row["manager_id"] != node or not re.fullmatch(r"[a-f0-9]{64}", payload.get("backend_id", "")):
                    self.deny()
                if row["backend_id"] and row["backend_id"] != payload["backend_id"]:
                    self.deny("STDIO_PROCESS_REPLACED")
                c.execute(
                    update(s.mcp_stdio_leases)
                    .where(s.mcp_stdio_leases.c.id == row["id"])
                    .values(state="ready", backend_id=payload["backend_id"])
                )
                return
            if operation in {"ensure", "alive"}:
                if row["manager_id"] is None:
                    self.deny()
                return
            if operation == "stdio.rpc":
                if row["state"] != "ready" or row["manager_id"] != node:
                    self.deny()
                return
            self.deny()

    def cleanup(self, body):
        try:
            org = UUID(body["org_id"]) if "org_id" in body else UUID(body["binding"]["org_id"])
        except (KeyError, ValueError, TypeError):
            self.deny()
        with self.db.scoped(org, UUID(int=0)) as c:
            query = select(s.mcp_stdio_leases).where(
                s.mcp_stdio_leases.c.org_id == org, s.mcp_stdio_leases.c.state != "destroyed"
            )
            if set(body) == {"org_id", "run_id", "generation"}:
                if type(body["generation"]) is not int:
                    self.deny()
                query = query.where(
                    s.mcp_stdio_leases.c.run_id == UUID(body["run_id"]),
                    s.mcp_stdio_leases.c.generation == body["generation"],
                )
            elif set(body) == {"org_id", "discovery_id"}:
                query = query.where(s.mcp_stdio_leases.c.discovery_id == UUID(body["discovery_id"]))
            elif set(body) == {"binding"}:
                binding = self.service._binding(c, org, UUID(body["binding"]["credential_ref"]))
                if binding_contract(binding) != body["binding"] or binding["state"] not in {"retiring", "revoked"}:
                    self.deny()
                query = query.where(s.mcp_stdio_leases.c.credential_ref == binding["id"])
            else:
                self.deny()
            rows = c.execute(query.with_for_update()).mappings().all()
            specs = []
            for row in rows:
                if row["manager_id"] is None:
                    # No manager claimed the allocation. Stopping this intent prevents future claim.
                    c.execute(
                        update(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.id == row["id"]).values(state="destroyed")
                    )
                else:
                    c.execute(
                        update(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.id == row["id"]).values(state="stopping")
                    )
                    specs.append(row["spec"])
            return {"specs": specs}
