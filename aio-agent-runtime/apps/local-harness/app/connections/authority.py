"""Gateway callbacks are checked against durable DB intentions, not incoming user/role claims."""

from datetime import timezone
from uuid import UUID

from sqlalchemy import select

from ..auth.principal import Principal
from ..db import schema as s
from ..platform_errors import PlatformError
from ..policy.repository import current_facts, db_now, require_resource
from ..runtime.actions import ActionSpec, canonical_digest
from ..runtime.contracts import WorkHandle
from .catalog import active_binding, binding_contract, current_connection, MCP_DRIVERS


def call_payload(handle, permit_id, operation_key, tool, action, arguments):
    return {
        "binding": tool["config"]["binding"],
        "run_id": str(handle.run_id),
        "dispatch_id": str(permit_id),
        "generation": handle.generation,
        "operation_key": operation_key,
        "tool_name": tool["config"]["remote_tool_name"],
        "tool_digest": tool["config"]["remote_tool_digest"],
        "arguments": arguments,
        "not_after": action.not_after.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


class ConnectorAuthority:
    def __init__(self, store, service):
        self.store, self.service, self.db = store, service, store.db

    @staticmethod
    def deny():
        raise PlatformError("CONNECTOR_AUTHORITY_DENIED", "Connector action has no current matching authority", 403)

    def authorize(self, operation, payload):
        body = {k: v for k, v in payload.items() if k != "operation"}
        try:
            binding = body["binding"]
            org, ref = UUID(binding["org_id"]), UUID(binding["credential_ref"])
        except (KeyError, ValueError, TypeError, AttributeError):
            self.deny()
        with self.db.scoped(org, UUID(int=0)) as c:
            row = self.service._binding(c, org, ref)
            if binding_contract(row) != binding:
                self.deny()
            if operation in {"oauth.start", "oauth.exchange", "oauth.refresh", "oauth.reauth_required"}:
                from .oauth_service import OAuthService

                oauth = OAuthService(self.service)
                if operation in {"oauth.start", "oauth.exchange"}:
                    oauth.authorize(c, row, operation, body)
                else:
                    oauth.lifecycle(c, row, operation, body)
                return
            if operation in {"credential.put", "credential.revoke"}:
                if body != {"binding": binding_contract(row), "ticket_id": str(row["ticket_id"])}:
                    self.deny()
                if operation == "credential.revoke":
                    if row["state"] not in {"retiring", "revoked"}:
                        self.deny()
                    return
                if row["auth_kind"] != "opaque":
                    self.deny()
                p = Principal(
                    org, row["requested_by"], row["membership_revision"], service_actor_id="connector-gateway"
                )
                current_facts(c, p)
                conn = current_connection(
                    c, p, row["connection_id"], action="connection.update", active=False, manage=True
                )
                self.service.profile(row["endpoint_id"], row["endpoint_digest"])
                if (
                    conn["state"] == "revoked"
                    or conn["resource_status"] != "active"
                    or row["state"] not in {"pending", "active"}
                ):
                    self.deny()
                if row["state"] == "pending" and row["expires_at"] <= db_now(c):
                    self.deny()
                if row["state"] == "active" and conn["credential_ref"] != row["id"]:
                    self.deny()
                return
            if operation == "discover":
                try:
                    id = UUID(body["discovery_id"])
                except (KeyError, TypeError, ValueError):
                    self.deny()
                job = (
                    c.execute(
                        select(s.mcp_discoveries).where(s.mcp_discoveries.c.org_id == org, s.mcp_discoveries.c.id == id)
                    )
                    .mappings()
                    .first()
                )
                if (
                    not job
                    or job["state"] != "running"
                    or job["expires_at"] <= db_now(c)
                    or job["binding_id"] != row["id"]
                    or canonical_digest("aio-connector-discovery-v1", body)
                    != canonical_digest("aio-connector-discovery-v1", job["spec"])
                ):
                    self.deny()
                p = Principal(
                    org, job["requested_by"], job["membership_revision"], service_actor_id="connector-gateway"
                )
                conn = current_connection(c, p, job["connection_id"], active=False, allow_draft=True)
                if conn["credential_ref"] != row["id"] or row["state"] != "active":
                    self.deny()
                active_binding(c, p, conn)
                self.service.profile(row["endpoint_id"], row["endpoint_digest"])
                return {"principal": p, "discovery": dict(job), "connection": conn, "binding": row}
            if operation not in {"call", "status"}:
                self.deny()
            try:
                rid, did, generation = UUID(body["run_id"]), UUID(body["dispatch_id"]), body["generation"]
                if type(generation) is not int:
                    raise ValueError
            except (KeyError, ValueError, TypeError):
                self.deny()
            run = c.execute(select(s.runs).where(s.runs.c.org_id == org, s.runs.c.id == rid)).mappings().first()
            dispatch = (
                c.execute(select(s.dispatches).where(s.dispatches.c.org_id == org, s.dispatches.c.id == did))
                .mappings()
                .first()
            )
            if not run or not dispatch or dispatch["generation"] != generation:
                self.deny()
            inv = (
                c.execute(
                    select(s.invocations).where(
                        s.invocations.c.org_id == org,
                        s.invocations.c.id == dispatch["invocation_id"],
                        s.invocations.c.run_id == rid,
                    )
                )
                .mappings()
                .first()
            )
            if not inv:
                self.deny()
            member = (
                c.execute(
                    select(s.memberships).where(
                        s.memberships.c.org_id == org, s.memberships.c.user_id == run["actor_id"]
                    )
                )
                .mappings()
                .first()
            )
            job = c.execute(select(s.jobs).where(s.jobs.c.org_id == org, s.jobs.c.run_id == rid)).mappings().first()
            if not member or not job:
                self.deny()
            p = Principal(
                org,
                run["actor_id"],
                member["revision"],
                service_actor_id=job["lease_owner"] or "connector-reconciliation",
            )
            handle = WorkHandle(
                p, rid, generation, job["lease_owner"] or "connector-reconciliation", run["deadline_at"]
            )
            if operation == "status":
                # Metadata-only reconciliation is permitted after execution expires; no cached result is exposed here.
                require_resource(c, p, rid, "run.read")
                action = ActionSpec.model_validate(inv["action"])
                tool = (
                    c.execute(
                        select(s.tool_versions).where(
                            s.tool_versions.c.org_id == org, s.tool_versions.c.id == action.tool_version_id
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    not tool
                    or tool["driver"] not in MCP_DRIVERS
                    or action.connection_id != row["connection_id"]
                    or action.credential_binding_revision != row["revision"]
                ):
                    self.deny()
                tool = {**dict(tool), "config": {**tool["config"], "binding": binding_contract(row)}}
                expected = call_payload(handle, did, dispatch["operation_key"], tool, action, inv["arguments"])
                if expected != body:
                    self.deny()
                return
            if dispatch["state"] != "dispatching" or inv["state"] != "executing":
                self.deny()
        with self.store.locked(handle) as (c, run, job, now, facts):
            current = (
                c.execute(select(s.invocations).where(s.invocations.c.org_id == org, s.invocations.c.id == inv["id"]))
                .mappings()
                .one()
            )
            tool, action = self.store._validate_invocation(c, handle, run, current, now, facts)
            if tool["driver"] not in MCP_DRIVERS:
                self.deny()
            profile = self.service.profile(row["endpoint_id"], row["endpoint_digest"])
            if tool["config"]["remote_tool_name"] not in profile["read_tools"]:
                self.deny()
            expected = call_payload(handle, did, dispatch["operation_key"], tool, action, current["arguments"])
            if expected != body:
                self.deny()
            return {"handle": handle, "run": run, "binding": row, "tool": tool, "invocation": dict(current)}
