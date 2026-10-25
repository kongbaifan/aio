"""Platform control plane for MCP: definitions are shared, credential identities are explicit resources."""

import asyncio
from contextlib import contextmanager, nullcontext
from datetime import timedelta, timezone
from uuid import UUID, uuid4

import rfc8785
from sqlalchemy import insert, select, update, func

from ..admin.service import AdminService
from ..db import schema as s
from ..observability import audit
from ..observability import redaction as m
from ..db.provisioning import provision_tool
from ..platform_errors import PlatformError
from ..policy.repository import current_facts, db_now, require_resource, visible_resources
from ..runtime.actions import canonical_digest
from ..runtime.catalog import validate_schema
from ..runtime.contracts import bounded_json
from .catalog import (
    active_binding,
    binding_contract,
    connection_query,
    current_connection,
    current_server,
    server_digest,
)
from .client import ConnectorError


class ConnectionService:
    def __init__(self, database, settings, client=None):
        self.db, self.settings, self.client = database, settings, client
        self.admin = AdminService(database, settings)

    def profile(self, id, digest=None):
        row = next((p for p in self.settings.connector_profiles if p["id"] == id), None)
        if row is None or (digest and row["digest"] != digest):
            raise PlatformError(
                "CONNECTOR_ENDPOINT_CHANGED", "MCP endpoint must be approved by the deployment operator", 403
            )
        return row

    def enabled(self):
        if self.client is None:
            raise PlatformError("CONNECTOR_UNAVAILABLE", "An isolated credential gateway is required", 503)

    @contextmanager
    def write(self, p):
        with self.db.transaction(p) as c:
            c.execute(select(s.organizations.c.id).where(s.organizations.c.id == p.org_id).with_for_update()).one()
            current_facts(c, p, lock=True)
            yield c

    @staticmethod
    def metadata(row):
        return {
            key: row[key]
            for key in (
                "id",
                "server_id",
                "name",
                "scope",
                "department_id",
                "state",
                "credential_revision",
                "owner_id",
                "resource_status",
                "resource_revision",
                "created_at",
                "authorization",
                "credential_cleanup",
            )
        }

    def server_metadata(self, row):
        profile = next(
            (
                p
                for p in self.settings.connector_profiles
                if p["id"] == row["endpoint_id"] and p["digest"] == row["endpoint_digest"]
            ),
            None,
        )
        return {
            "endpoint_url": profile["url"] if profile else None,
            "authentication": profile["authentication"] if profile else None,
            "transport": profile.get("transport", "http") if profile else None,
            "stdio": profile.get("stdio") if profile else None,
            "oauth": profile.get("oauth") if profile else None,
            "endpoint_available": profile is not None,
            **{
                key: row[key]
                for key in (
                    "id",
                    "name",
                    "version",
                    "endpoint_id",
                    "endpoint_digest",
                    "state",
                    "revision",
                    "digest",
                    "published_tools",
                    "created_at",
                )
            },
        }

    def list_servers(self, p, *, management=False):
        with self.db.transaction(p) as c:
            current_facts(c, p)
            query = select(s.mcp_servers).join(
                s.resources, (s.resources.c.org_id == s.mcp_servers.c.org_id) & (s.resources.c.id == s.mcp_servers.c.id)
            )
            if management:
                if self.admin.role(c, p) != "org_admin":
                    raise PlatformError("ADMIN_FORBIDDEN", "Organization administration is required", 403)
                query = query.where(s.mcp_servers.c.org_id == p.org_id)
            else:
                query = query.where(
                    visible_resources(c, p, "mcp_server", "mcp_server.use"), s.mcp_servers.c.state == "published"
                )
            return [
                self.server_metadata(row)
                for row in c.execute(query.order_by(s.mcp_servers.c.created_at.desc()).limit(200)).mappings()
            ]

    def create_server(self, p, body):
        profile = self.profile(body.endpoint_id)
        with self.admin.transaction(p, write=True) as c:
            if (
                c.execute(
                    select(func.count()).select_from(s.mcp_servers).where(s.mcp_servers.c.org_id == p.org_id)
                ).scalar_one()
                >= 200
            ):
                raise PlatformError("CATALOG_QUOTA", "Organization MCP catalog quota is exhausted", 429)
            if c.execute(
                select(s.mcp_servers.c.id).where(
                    s.mcp_servers.c.org_id == p.org_id,
                    s.mcp_servers.c.name == body.name,
                    s.mcp_servers.c.version == body.version,
                )
            ).first():
                raise PlatformError("MCP_VERSION_EXISTS", "MCP name/version is already reserved", 409)
            id = uuid4()
            c.execute(
                insert(s.resources).values(
                    org_id=p.org_id, id=id, kind="mcp_server", owner_id=p.user_id, classification="internal"
                )
            )
            require_resource(c, p, id, "mcp_server.update")
            c.execute(
                insert(s.mcp_servers).values(
                    org_id=p.org_id,
                    id=id,
                    name=body.name,
                    version=body.version,
                    endpoint_id=profile["id"],
                    endpoint_digest=profile["digest"],
                )
            )
            audit.record(
                c,
                p,
                'mcp.definition.create',
                id,
                'draft',
            )
            return self.server_metadata(
                c.execute(select(s.mcp_servers).where(s.mcp_servers.c.id == id)).mappings().one()
            )

    def list_connections(self, p):
        with self.db.transaction(p) as c:
            current_facts(c, p)
            candidates = c.execute(
                connection_query()
                .where(s.mcp_connections.c.org_id == p.org_id)
                .order_by(s.mcp_connections.c.created_at.desc())
                .limit(300)
            ).mappings()
            result = []
            for row in candidates:
                if row["scope"] == "personal" and row["owner_id"] != p.user_id:
                    continue
                if row["owner_id"] == p.user_id or (
                    row["scope"] == "department" and self.admin.role(c, p) == "org_admin"
                ):
                    result.append(self.metadata(row))
                    continue
                try:
                    require_resource(c, p, row["id"], "connection.read")
                except PlatformError as exc:
                    if exc.status not in {403, 404}:
                        raise
                else:
                    result.append(self.metadata(row))
            return result

    def create_connection(self, p, body):
        self.enabled()
        if (body.scope == "department") != (body.department_id is not None):
            raise PlatformError("CONNECTION_SCOPE_INVALID", "Connection scope and department must agree", 422)
        with self.write(p) as c:
            server = current_server(c, p, body.server_id, allow_draft=True)
            self.profile(server["endpoint_id"], server["endpoint_digest"])
            if body.scope == "department":
                if self.admin.role(c, p) != "org_admin":
                    raise PlatformError(
                        "ADMIN_FORBIDDEN",
                        "Only an organization administrator can configure a department service identity",
                        403,
                    )
                if not c.execute(
                    select(s.departments.c.id).where(
                        s.departments.c.org_id == p.org_id,
                        s.departments.c.id == body.department_id,
                        s.departments.c.active.is_(True),
                    )
                ).first():
                    raise PlatformError("RESOURCE_NOT_FOUND", "Department is not active in this organization", 404)
            count = c.execute(
                select(func.count()).select_from(s.mcp_connections).where(s.mcp_connections.c.org_id == p.org_id)
            ).scalar_one()
            if count >= 500:
                raise PlatformError("CONNECTION_QUOTA", "Organization connection quota is exhausted", 429)
            id = uuid4()
            c.execute(
                insert(s.resources).values(
                    org_id=p.org_id, id=id, kind="connection", owner_id=p.user_id, classification="internal"
                )
            )
            c.execute(
                insert(s.mcp_connections).values(
                    org_id=p.org_id,
                    id=id,
                    server_id=body.server_id,
                    name=body.name,
                    scope=body.scope,
                    department_id=body.department_id,
                )
            )
            if body.scope == "department":
                for action in ("connection.read", "connection.use"):
                    c.execute(
                        insert(s.department_grants).values(
                            org_id=p.org_id, id=uuid4(), resource_id=id, department_id=body.department_id, action=action
                        )
                    )
            audit.record(
                c,
                p,
                'mcp.connection.create',
                id,
                body.scope,
            )
            return self.metadata(current_connection(c, p, id, action="connection.read", active=False, allow_draft=True))

    def prepare_credential(self, p, id, body, *, oauth=False):
        self.enabled()
        with self.write(p) as c:
            conn = current_connection(c, p, id, action="connection.update", active=False, manage=True, lock=True)
            if conn["state"] == "revoked" or conn["resource_status"] != "active":
                raise PlatformError("CONNECTION_REVOKED", "Create a new connection after revocation", 409)
            existing = (
                c.execute(
                    select(s.mcp_bindings).where(
                        s.mcp_bindings.c.org_id == p.org_id, s.mcp_bindings.c.ticket_id == body.request_id
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                if existing["auth_kind"] != ("oauth2" if oauth else "opaque"):
                    raise PlatformError("OAUTH_REQUIRED", "Credential method does not match the saved intention", 409)
                if existing["connection_id"] != id or existing["requested_by"] != p.user_id:
                    raise PlatformError(
                        "IDEMPOTENCY_CONFLICT", "Credential preparation request belongs to another intention", 409
                    )
                return {"binding_id": existing["id"], "state": existing["state"], "expires_at": existing["expires_at"]}
            if conn["resource_revision"] != body.expected_revision:
                raise PlatformError(
                    "REVISION_CONFLICT", "Connection changed; reload before replacing its identity", 409
                )
            server = (
                c.execute(
                    select(s.mcp_servers).where(
                        s.mcp_servers.c.org_id == p.org_id, s.mcp_servers.c.id == conn["server_id"]
                    )
                )
                .mappings()
                .one()
            )
            profile = self.profile(server["endpoint_id"], server["endpoint_digest"])
            if (profile["authentication"] == "oauth2") != oauth:
                raise PlatformError("OAUTH_REQUIRED", "Use the approved authentication method for this endpoint", 409)
            now = db_now(c)
            c.execute(
                update(s.mcp_bindings)
                .where(
                    s.mcp_bindings.c.org_id == p.org_id,
                    s.mcp_bindings.c.connection_id == id,
                    s.mcp_bindings.c.state == "pending",
                    s.mcp_bindings.c.expires_at <= now,
                )
                .values(state="retiring")
            )
            pending = (
                c.execute(
                    select(s.mcp_bindings).where(
                        s.mcp_bindings.c.org_id == p.org_id,
                        s.mcp_bindings.c.connection_id == id,
                        s.mcp_bindings.c.state == "pending",
                    )
                )
                .mappings()
                .first()
            )
            if pending:
                if pending["requested_by"] == p.user_id and pending["membership_revision"] == p.membership_revision:
                    return {"binding_id": pending["id"], "state": pending["state"], "expires_at": pending["expires_at"]}
                raise PlatformError(
                    "CREDENTIAL_PENDING", "A credential upload is already pending for this connection", 409
                )
            count, rev = c.execute(
                select(func.count(), func.coalesce(func.max(s.mcp_bindings.c.revision), 0)).where(
                    s.mcp_bindings.c.org_id == p.org_id, s.mcp_bindings.c.connection_id == id
                )
            ).one()
            if count >= 100:
                raise PlatformError("CONNECTION_QUOTA", "Credential history quota is exhausted", 429)
            bid, expires = uuid4(), now + timedelta(minutes=10 if oauth else 5)
            c.execute(
                insert(s.mcp_bindings).values(
                    org_id=p.org_id,
                    id=bid,
                    connection_id=id,
                    revision=rev + 1,
                    endpoint_id=server["endpoint_id"],
                    endpoint_digest=server["endpoint_digest"],
                    ticket_id=body.request_id,
                    requested_by=p.user_id,
                    membership_revision=p.membership_revision,
                    expires_at=expires,
                    auth_kind="oauth2" if oauth else "opaque",
                )
            )
            c.execute(
                update(s.resources)
                .where(s.resources.c.org_id == p.org_id, s.resources.c.id == id)
                .values(revision=s.resources.c.revision + 1)
            )
            audit.record(
                c,
                p,
                'mcp.credential.prepare',
                id,
                'pending',
                m.CredentialPrepared(binding_id=str(bid)),
            )
            return {"binding_id": bid, "state": "pending", "expires_at": expires}

    @staticmethod
    def _binding(c, org, id):
        row = (
            c.execute(select(s.mcp_bindings).where(s.mcp_bindings.c.org_id == org, s.mcp_bindings.c.id == id))
            .mappings()
            .first()
        )
        if row is None:
            raise PlatformError("RESOURCE_NOT_FOUND", "Credential binding does not exist in this organization", 404)
        return dict(row)

    def _upload_request(self, p, connection_id, binding_id):
        with self.db.transaction(p) as c:
            row = self._binding(c, p.org_id, binding_id)
            if row["auth_kind"] != "opaque":
                raise PlatformError("OAUTH_REQUIRED", "OAuth credentials cannot be uploaded as bearer tokens", 409)
            if (
                row["connection_id"] != connection_id
                or row["requested_by"] != p.user_id
                or row["membership_revision"] != p.membership_revision
            ):
                raise PlatformError("RESOURCE_NOT_FOUND", "Credential upload is not bound to this identity", 404)
            current_connection(c, p, connection_id, action="connection.update", active=False, manage=True)
            self.profile(row["endpoint_id"], row["endpoint_digest"])
            if row["state"] not in {"pending", "active"} or (
                row["state"] == "pending" and row["expires_at"] <= db_now(c)
            ):
                raise PlatformError("CREDENTIAL_TICKET_EXPIRED", "Credential upload ticket is no longer current", 409)
            return {"binding": binding_contract(row), "ticket_id": str(row["ticket_id"])}

    async def upload_credential(self, p, connection_id, binding_id, body):
        self.enabled()
        request = await asyncio.to_thread(self._upload_request, p, connection_id, binding_id)
        # The raw value is forwarded over the private service channel, never stored in PG or an audit payload.
        result = await self.client.call("credentials/put", {**request, "secret": body.secret.get_secret_value()})
        if result.get("credential_ref") != str(binding_id) or result.get("state") != "stored":
            raise PlatformError("CONNECTOR_INVALID_RESPONSE", "Gateway credential receipt is unrelated", 502)
        return await asyncio.to_thread(self._activate, p, connection_id, binding_id)

    def _activate(self, p, id, binding_id, *, connection=None):
        with self.write(p) if connection is None else nullcontext(connection) as c:
            conn = current_connection(c, p, id, action="connection.update", active=False, manage=True, lock=True)
            row = self._binding(c, p.org_id, binding_id)
            if (
                row["connection_id"] != id
                or row["requested_by"] != p.user_id
                or row["membership_revision"] != p.membership_revision
            ):
                raise PlatformError(
                    "CREDENTIAL_TICKET_EXPIRED", "Credential intention no longer belongs to the caller", 409
                )
            if conn["credential_ref"] == binding_id and row["state"] == "active":
                return self.metadata(conn)
            if row["state"] != "pending" or row["expires_at"] <= db_now(c) or conn["state"] == "revoked":
                raise PlatformError("CREDENTIAL_TICKET_EXPIRED", "Credential activation is obsolete", 409)
            c.execute(
                update(s.mcp_bindings)
                .where(
                    s.mcp_bindings.c.org_id == p.org_id,
                    s.mcp_bindings.c.connection_id == id,
                    s.mcp_bindings.c.state == "active",
                )
                .values(state="retiring")
            )
            c.execute(
                update(s.mcp_bindings)
                .where(s.mcp_bindings.c.org_id == p.org_id, s.mcp_bindings.c.id == binding_id)
                .values(state="active")
            )
            c.execute(
                update(s.mcp_connections)
                .where(s.mcp_connections.c.org_id == p.org_id, s.mcp_connections.c.id == id)
                .values(state="pending", credential_ref=binding_id, credential_revision=row["revision"])
            )
            c.execute(
                update(s.resources)
                .where(s.resources.c.org_id == p.org_id, s.resources.c.id == id)
                .values(revision=s.resources.c.revision + 1)
            )
            audit.record(
                c,
                p,
                'mcp.credential.activate',
                id,
                'active',
                m.CredentialActivated(credential_revision=row['revision']),
            )
            return self.metadata(current_connection(c, p, id, action="connection.read", active=False, manage=True))

    def _start_discovery(self, p, id, request_id):
        with self.write(p) as c:
            conn = current_connection(c, p, id, active=False, allow_draft=True)
            binding = active_binding(c, p, conn)
            profile = self.profile(binding["endpoint_id"], binding["endpoint_digest"])
            old = (
                c.execute(
                    select(s.mcp_discoveries).where(
                        s.mcp_discoveries.c.org_id == p.org_id, s.mcp_discoveries.c.id == request_id
                    )
                )
                .mappings()
                .first()
            )
            if old:
                if old["requested_by"] != p.user_id or old["connection_id"] != id:
                    raise PlatformError("IDEMPOTENCY_CONFLICT", "Discovery request belongs to another identity", 409)
                return {**dict(old), "_new": False}
            count = c.execute(
                select(func.count())
                .select_from(s.mcp_discoveries)
                .where(s.mcp_discoveries.c.org_id == p.org_id, s.mcp_discoveries.c.connection_id == id)
            ).scalar_one()
            if count >= 30:
                raise PlatformError("DISCOVERY_QUOTA", "Connection discovery history is full", 429)
            expires = db_now(c) + timedelta(seconds=profile["timeout_seconds"] + 10)
            spec = {
                "binding": binding_contract(binding),
                "discovery_id": str(request_id),
                "not_after": expires.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            c.execute(
                insert(s.mcp_discoveries).values(
                    org_id=p.org_id,
                    id=request_id,
                    connection_id=id,
                    binding_id=binding["id"],
                    requested_by=p.user_id,
                    membership_revision=p.membership_revision,
                    spec=spec,
                    expires_at=expires,
                )
            )
            return {
                **dict(
                    c.execute(
                        select(s.mcp_discoveries).where(
                            s.mcp_discoveries.c.id == request_id, s.mcp_discoveries.c.org_id == p.org_id
                        )
                    )
                    .mappings()
                    .one()
                ),
                "_new": True,
            }

    async def discover(self, p, id, body):
        self.enabled()
        job = await asyncio.to_thread(self._start_discovery, p, id, body.request_id)
        if job["state"] != "running" or not job["_new"]:
            return {"id": job["id"], "state": job["state"], "result": job["result"], "error_code": job["error_code"]}
        try:
            result = await self.client.call("mcp/discover", job["spec"])
            return await asyncio.to_thread(self._finish_discovery, p, job, result)
        except Exception as exc:
            code = exc.code if isinstance(exc, PlatformError) else "MCP_DISCOVERY_FAILED"
            await asyncio.to_thread(self._fail_discovery, p.org_id, job["id"], code)
            if isinstance(exc, PlatformError):
                raise
            raise PlatformError("MCP_DISCOVERY_FAILED", "MCP discovery could not be confirmed", 502) from None

    def _finish_discovery(self, p, job, result):
        result = bounded_json(result, 1048576)
        if (
            result.get("endpoint_digest") != job["spec"]["binding"]["endpoint_digest"]
            or result.get("protocol_version") != "2025-06-18"
            or not isinstance(result.get("tools"), list)
            or len(result["tools"]) > 64
        ):
            raise PlatformError(
                "CONNECTOR_INVALID_RESPONSE", "MCP discovery does not match its fixed endpoint/protocol", 502
            )
        size = len(rfc8785.dumps(result))
        with self.write(p) as c:
            conn = current_connection(c, p, job["connection_id"], active=False, allow_draft=True)
            current = (
                c.execute(
                    select(s.mcp_discoveries)
                    .where(s.mcp_discoveries.c.org_id == p.org_id, s.mcp_discoveries.c.id == job["id"])
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if (
                current["state"] != "running"
                or current["expires_at"] <= db_now(c)
                or conn["credential_ref"] != current["binding_id"]
            ):
                raise PlatformError("DISCOVERY_OBSOLETE", "MCP identity changed during discovery", 409)
            total = c.execute(
                select(func.coalesce(func.sum(s.mcp_discoveries.c.result_bytes), 0)).where(
                    s.mcp_discoveries.c.org_id == p.org_id
                )
            ).scalar_one()
            if total + size > 16 * 1024 * 1024:
                raise PlatformError("DISCOVERY_QUOTA", "Organization discovery quota is exhausted", 429)
            c.execute(
                update(s.mcp_discoveries)
                .where(s.mcp_discoveries.c.org_id == p.org_id, s.mcp_discoveries.c.id == job["id"])
                .values(state="ready", result=result, result_bytes=size)
            )
            c.execute(
                update(s.mcp_connections)
                .where(s.mcp_connections.c.org_id == p.org_id, s.mcp_connections.c.id == conn["id"])
                .values(state="active")
            )
            audit.record(
                c,
                p,
                'mcp.discovery',
                conn['id'],
                'ready',
            )
            return {"id": job["id"], "state": "ready", "result": result, "error_code": None}

    def _fail_discovery(self, org, id, code):
        with self.db.scoped(org, UUID(int=0)) as c:
            job = (
                c.execute(
                    select(s.mcp_discoveries).where(s.mcp_discoveries.c.org_id == org, s.mcp_discoveries.c.id == id)
                )
                .mappings()
                .first()
            )
            c.execute(
                update(s.mcp_discoveries)
                .where(
                    s.mcp_discoveries.c.org_id == org,
                    s.mcp_discoveries.c.id == id,
                    s.mcp_discoveries.c.state == "running",
                )
                .values(state="failed", error_code=code)
            )
            if job and code == "MCP_AUTH_REQUIRED":
                c.execute(
                    update(s.mcp_connections)
                    .where(
                        s.mcp_connections.c.org_id == org,
                        s.mcp_connections.c.id == job["connection_id"],
                        s.mcp_connections.c.credential_ref == job["binding_id"],
                        s.mcp_connections.c.state.in_(["active", "pending"]),
                    )
                    .values(state="reauth_required")
                )

    def publish(self, p, id, body):
        if not body.acknowledge_readonly_credentials:
            raise PlatformError(
                "MCP_READONLY_REQUIRED",
                "Operator-approved tool names still require genuinely read-only upstream credentials",
                422,
            )
        with self.admin.transaction(p, write=True) as c:
            require_resource(c, p, id, "mcp_server.update")
            server = (
                c.execute(
                    select(s.mcp_servers)
                    .where(s.mcp_servers.c.org_id == p.org_id, s.mcp_servers.c.id == id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if server is None or server["state"] != "draft" or server["revision"] != body.expected_revision:
                raise PlatformError("REVISION_CONFLICT", "MCP definition is no longer an editable draft", 409)
            profile = self.profile(server["endpoint_id"], server["endpoint_digest"])
            discovery = (
                c.execute(
                    select(s.mcp_discoveries).where(
                        s.mcp_discoveries.c.org_id == p.org_id, s.mcp_discoveries.c.id == body.discovery_id
                    )
                )
                .mappings()
                .first()
            )
            if discovery is None or discovery["requested_by"] != p.user_id or discovery["state"] != "ready":
                raise PlatformError(
                    "DISCOVERY_REQUIRED", "Publishing requires this maintainer's authorized discovery", 403
                )
            conn = current_connection(c, p, discovery["connection_id"], allow_draft=True)
            if conn["server_id"] != id or conn["credential_ref"] != discovery["binding_id"]:
                raise PlatformError(
                    "DISCOVERY_OBSOLETE", "MCP discovery belongs to a different definition or credential identity", 409
                )
            available = {t["name"]: t for t in discovery["result"]["tools"]}
            if len({t.remote_name for t in body.tools}) != len(body.tools) or len({t.alias for t in body.tools}) != len(
                body.tools
            ):
                raise PlatformError("TOOL_ALIAS_CONFLICT", "MCP aliases and selected remote names must be unique", 422)
            selected = []
            for item in body.tools:
                remote = available.get(item.remote_name)
                if remote is None or item.remote_name not in profile["read_tools"]:
                    raise PlatformError(
                        "MCP_TOOL_NOT_APPROVED", "MCP tool is outside the operator's allowed read operations", 403
                    )
                raw = {
                    key: remote[key] for key in ("name", "description", "input_schema", "output_schema", "annotations")
                }
                if canonical_digest("aio-mcp-tool-v1", raw) != remote["digest"]:
                    raise PlatformError(
                        "CONNECTOR_INVALID_RESPONSE", "MCP tool definition failed integrity validation", 409
                    )
                schema = bounded_json(remote["input_schema"], 32768)
                # Close only the declared argument envelope; do not rewrite remote metadata or auto-approve new fields.
                schema["additionalProperties"] = False
                validate_schema(schema)
                selected.append({"alias": item.alias, "remote": remote, "input_schema": schema})
            digest = server_digest(server, selected)
            tools = [
                provision_tool(
                    c,
                    org_id=p.org_id,
                    owner_id=p.user_id,
                    name=item["alias"],
                    driver="mcp.stdio" if profile.get("transport") == "stdio" else "mcp.http",
                    risk="R1" if profile.get("transport") == "stdio" else "R0",
                    input_schema=item["input_schema"],
                    config={
                        "server_id": str(id),
                        "server_digest": digest,
                        "remote_tool_name": item["remote"]["name"],
                        "remote_tool_digest": item["remote"]["digest"],
                        "description": item["remote"]["description"][:1024],
                        "timeout_seconds": profile["timeout_seconds"],
                        "target_slot": "connector/mcp",
                        "resource_scope": {"server_id": str(id), "remote_tool": item["remote"]["name"]},
                    },
                )
                for item in selected
            ]
            c.execute(
                update(s.mcp_servers)
                .where(s.mcp_servers.c.org_id == p.org_id, s.mcp_servers.c.id == id)
                .values(
                    state="published",
                    revision=server["revision"] + 1,
                    definition=selected,
                    digest=digest,
                    published_tools=tools,
                    discovery_id=body.discovery_id,
                )
            )
            audit.record(
                c,
                p,
                'mcp.definition.publish',
                id,
                'published',
            )
            return self.server_metadata(
                c.execute(select(s.mcp_servers).where(s.mcp_servers.c.id == id, s.mcp_servers.c.org_id == p.org_id))
                .mappings()
                .one()
            )

    def mark_revoked(self, p, id):
        with self.write(p) as c:
            row = (
                c.execute(
                    connection_query()
                    .where(s.mcp_connections.c.org_id == p.org_id, s.mcp_connections.c.id == id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None or (row["scope"] == "personal" and row["owner_id"] != p.user_id):
                raise PlatformError("RESOURCE_NOT_FOUND", "Connection is private to its owner", 404)
            if row["owner_id"] != p.user_id and not (
                row["scope"] == "department" and self.admin.role(c, p) == "org_admin"
            ):
                raise PlatformError("ADMIN_FORBIDDEN", "Connection revocation is not permitted", 403)
            c.execute(
                update(s.mcp_connections)
                .where(s.mcp_connections.c.org_id == p.org_id, s.mcp_connections.c.id == id)
                .values(state="revoked", credential_cleanup="pending")
            )
            c.execute(
                update(s.resources)
                .where(s.resources.c.org_id == p.org_id, s.resources.c.id == id)
                .values(status="disabled", revision=s.resources.c.revision + 1)
            )
            c.execute(
                update(s.mcp_bindings)
                .where(
                    s.mcp_bindings.c.org_id == p.org_id,
                    s.mcp_bindings.c.connection_id == id,
                    s.mcp_bindings.c.state.in_(["active", "pending"]),
                )
                .values(state="retiring")
            )
            audit.record(
                c,
                p,
                'mcp.connection.revoke',
                id,
                'revoked',
            )
            c.execute(
                update(s.mcp_oauth_attempts)
                .where(
                    s.mcp_oauth_attempts.c.org_id == p.org_id,
                    s.mcp_oauth_attempts.c.connection_id == id,
                    s.mcp_oauth_attempts.c.state.not_in(["completed", "failed", "cancelled"]),
                )
                .values(state="cancelled", error_code="CONNECTION_REVOKED")
            )
            return {"id": id, "state": "revoked", "credential_cleanup": "pending"}

    def retirements(self, org, limit=10):
        with self.db.scoped(org, UUID(int=0)) as c:
            now = db_now(c)
            c.execute(
                update(s.mcp_oauth_attempts)
                .where(
                    s.mcp_oauth_attempts.c.org_id == org,
                    s.mcp_oauth_attempts.c.expires_at <= now,
                    s.mcp_oauth_attempts.c.state.in_(["preparing", "authorizing", "exchanging"]),
                )
                .values(state="failed", error_code="OAUTH_FLOW_EXPIRED")
            )
            c.execute(
                update(s.mcp_bindings)
                .where(
                    s.mcp_bindings.c.org_id == org,
                    s.mcp_bindings.c.state == "pending",
                    s.mcp_bindings.c.expires_at <= now,
                )
                .values(state="retiring")
            )
            rows = c.execute(
                select(s.mcp_bindings)
                .where(s.mcp_bindings.c.org_id == org, s.mcp_bindings.c.state == "retiring")
                .limit(limit)
            ).mappings()
            return [{"binding": binding_contract(row), "ticket_id": str(row["ticket_id"])} for row in rows]

    def retired(self, org, id, remote="local"):
        with self.db.scoped(org, UUID(int=0)) as c:
            if remote not in {"local", "confirmed", "unsupported", "unknown"}:
                raise PlatformError("CONNECTOR_INVALID_RESPONSE", "Unknown credential cleanup receipt", 502)
            row = self._binding(c, org, id)
            c.execute(
                update(s.mcp_bindings)
                .where(s.mcp_bindings.c.org_id == org, s.mcp_bindings.c.id == id, s.mcp_bindings.c.state == "retiring")
                .values(state="revoked", remote_revocation=remote)
            )
            c.execute(
                update(s.mcp_connections)
                .where(
                    s.mcp_connections.c.org_id == org,
                    s.mcp_connections.c.id == row["connection_id"],
                    s.mcp_connections.c.credential_ref == id,
                    s.mcp_connections.c.state == "revoked",
                )
                .values(credential_cleanup=remote)
            )

    async def cleanup(self, org):
        self.enabled()
        count = 0
        for request in await asyncio.to_thread(self.retirements, org):
            response = await self.client.call("credentials/revoke", request)
            if (
                response.get("state") != "revoked"
                or response.get("credential_ref") != request["binding"]["credential_ref"]
            ):
                raise ConnectorError("CONNECTOR_INVALID_RESPONSE")
            await asyncio.to_thread(
                self.retired,
                org,
                UUID(request["binding"]["credential_ref"]),
                response.get("remote_revocation", "local"),
            )
            count += 1
        return count
