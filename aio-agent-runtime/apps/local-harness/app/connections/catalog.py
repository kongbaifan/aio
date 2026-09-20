"""Current MCP authority. A shared definition never implies shared personal credentials."""

from uuid import UUID

from sqlalchemy import select

from ..auth.principal import Principal
from ..db import schema as s
from ..platform_errors import PlatformError

from ..policy.repository import current_facts, require_resource
from ..runtime.actions import canonical_digest

MCP_DRIVERS = frozenset({"mcp.http", "mcp.stdio"})


def server_digest(row, definition):
    return canonical_digest(
        "aio-mcp-server-v1",
        {
            "name": row["name"],
            "version": row["version"],
            "endpoint_id": row["endpoint_id"],
            "endpoint_digest": row["endpoint_digest"],
            "definition": definition,
        },
    )


def current_server(c, p: Principal, id: UUID, expected_digest=None, *, allow_draft=False):
    resource = require_resource(c, p, id, "mcp_server.use")
    row = (
        c.execute(select(s.mcp_servers).where(s.mcp_servers.c.org_id == p.org_id, s.mcp_servers.c.id == id))
        .mappings()
        .first()
    )
    if row is None:
        raise PlatformError("RESOURCE_NOT_FOUND", "MCP definition is not accessible", 404)
    if row["state"] != "published":
        if allow_draft and resource.owner_id == p.user_id:
            return dict(row)
        raise PlatformError("MCP_SERVER_UNAVAILABLE", "MCP definition is not published", 403)
    actual = server_digest(row, row["definition"])
    if actual != row["digest"] or (expected_digest is not None and expected_digest != actual):
        raise PlatformError("MCP_DEFINITION_CHANGED", "MCP definition does not match the fixed version", 409)
    return dict(row)


def connection_query():
    return select(
        s.mcp_connections,
        s.resources.c.owner_id,
        s.resources.c.status.label("resource_status"),
        s.resources.c.revision.label("resource_revision"),
    ).join(
        s.resources, (s.resources.c.org_id == s.mcp_connections.c.org_id) & (s.resources.c.id == s.mcp_connections.c.id)
    )


def current_connection(c, p, id, *, action="connection.use", active=True, allow_draft=False, manage=False, lock=False):
    facts = current_facts(c, p)
    query = connection_query().where(s.mcp_connections.c.org_id == p.org_id, s.mcp_connections.c.id == id)
    row = c.execute(query.with_for_update() if lock else query).mappings().first()
    if row is None or (row["scope"] == "personal" and row["owner_id"] != p.user_id):
        raise PlatformError(
            "RESOURCE_NOT_FOUND", "Personal MCP connections cannot be borrowed or read by another account", 404
        )
    admin = c.execute(
        select(s.memberships.c.role).where(s.memberships.c.org_id == p.org_id, s.memberships.c.user_id == p.user_id)
    ).scalar_one()
    if not (manage and row["scope"] == "department" and admin == "org_admin"):
        require_resource(c, p, id, action, facts=facts)
    if row["scope"] == "department":
        department = c.execute(
            select(s.departments.c.active).where(
                s.departments.c.org_id == p.org_id, s.departments.c.id == row["department_id"]
            )
        ).scalar_one_or_none()
        if not department:
            raise PlatformError("CONNECTION_UNAVAILABLE", "Connection department is inactive", 403)
    if active and (row["state"] != "active" or row["credential_ref"] is None or row["resource_status"] != "active"):
        raise PlatformError(
            "CONNECTION_UNAVAILABLE", "Connection requires a current authorized credential binding", 403
        )
    if not manage:
        current_server(c, p, row["server_id"], allow_draft=allow_draft)
    return dict(row)


def binding_contract(row):
    return {
        "org_id": str(row["org_id"]),
        "connection_id": str(row["connection_id"]),
        "credential_ref": str(row["id"]),
        "credential_revision": row["revision"],
        "endpoint_id": row["endpoint_id"],
        "endpoint_digest": row["endpoint_digest"],
    }


def active_binding(c, p, connection):
    row = (
        c.execute(
            select(s.mcp_bindings).where(
                s.mcp_bindings.c.org_id == p.org_id,
                s.mcp_bindings.c.id == connection["credential_ref"],
                s.mcp_bindings.c.connection_id == connection["id"],
                s.mcp_bindings.c.revision == connection["credential_revision"],
                s.mcp_bindings.c.state == "active",
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise PlatformError("CONNECTION_UNAVAILABLE", "Connection binding is not active", 403)
    return dict(row)


def require_sources(c, p, refs):
    if not isinstance(refs, list) or len(refs) > 64:
        raise PlatformError("SOURCE_POLICY_INVALID", "MCP provenance exceeds its bound", 409)
    for ref in refs:
        try:
            id, revision = UUID(ref["connection_id"]), ref["credential_revision"]
            if type(revision) is not int:
                raise ValueError
        except (KeyError, ValueError, TypeError):
            raise PlatformError("SOURCE_POLICY_INVALID", "MCP provenance identity is invalid", 409) from None
        row = current_connection(c, p, id)
        if row["credential_revision"] != revision:
            raise PlatformError("CONNECTION_IDENTITY_CHANGED", "Source connection identity has changed", 403)
        active_binding(c, p, row)


def merge_sources(*groups):
    values = {(ref["connection_id"], ref["credential_revision"]) for group in groups for ref in group}
    if len(values) > 64:
        raise PlatformError("SOURCE_POLICY_LIMIT", "Too many independent MCP sources", 409)
    return [{"connection_id": id, "credential_revision": revision} for id, revision in sorted(values)]


def resolve_connections(c, p, manifest, requested):
    from ..runtime.catalog import current_tool

    if not isinstance(requested, dict) or len(requested) > 16:
        raise PlatformError("CONNECTION_SCOPE_INVALID", "Connection selection is invalid", 422)
    servers = {}
    for entry in manifest.get("tools", []):
        if entry.get("driver") in MCP_DRIVERS:
            tool = current_tool(c, p, UUID(entry["id"]), entry)
            servers[tool["config"]["server_id"]] = tool["config"]["server_digest"]
    if set(requested) - set(servers) or len(servers) > 16:
        raise PlatformError(
            "CONNECTION_SCOPE_INVALID", "Bindings must belong to this Agent's fixed MCP definitions", 422
        )
    result = []
    for raw, digest in servers.items():
        server = current_server(c, p, UUID(raw), digest)
        if raw in requested:
            try:
                rows = [current_connection(c, p, UUID(requested[raw]))]
            except (ValueError, TypeError):
                raise PlatformError("CONNECTION_SCOPE_INVALID", "Connection identity is invalid", 422) from None
        else:
            candidates = c.execute(
                select(s.mcp_connections.c.id)
                .where(
                    s.mcp_connections.c.org_id == p.org_id,
                    s.mcp_connections.c.server_id == server["id"],
                    s.mcp_connections.c.state == "active",
                )
                .limit(200)
            ).scalars()
            rows = []
            for id in candidates:
                try:
                    rows.append(current_connection(c, p, id))
                except PlatformError as exc:
                    if exc.status not in {403, 404}:
                        raise
        if len(rows) != 1:
            raise PlatformError(
                "CONNECTION_SELECTION_REQUIRED", "Select one authorized personal or department connection", 409
            )
        connection = rows[0]
        if connection["server_id"] != server["id"]:
            raise PlatformError("CONNECTION_SCOPE_INVALID", "Connection belongs to another MCP definition", 403)
        binding = active_binding(c, p, connection)
        result.append({"server_id": str(server["id"]), **binding_contract(binding)})
    return result


def bind_tool(c, p, manifest, tool):
    if tool["driver"] not in MCP_DRIVERS:
        return tool
    sid = tool["config"]["server_id"]
    matches = [v for v in manifest.get("connections", []) if v.get("server_id") == sid]
    if len(matches) != 1:
        raise PlatformError("CONNECTION_SCOPE_INVALID", "Run has no fixed identity for this MCP definition", 403)
    snapshot = matches[0]
    connection = current_connection(c, p, UUID(snapshot["connection_id"]))
    binding = active_binding(c, p, connection)
    expected = {"server_id": sid, **binding_contract(binding)}
    if snapshot != expected:
        raise PlatformError("CONNECTION_IDENTITY_CHANGED", "Connection changed after this Run was accepted", 403)
    return {
        **tool,
        "config": {
            **tool["config"],
            "connection_id": str(connection["id"]),
            "credential_revision": connection["credential_revision"],
            "binding": binding_contract(binding),
        },
    }
