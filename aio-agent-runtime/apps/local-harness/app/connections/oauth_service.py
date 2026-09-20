"""BFF OAuth intentions. Auth codes are transient; tokens/verifiers live only in the gateway."""

import asyncio
import re
from datetime import timezone
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

from sqlalchemy import select, insert, update

from ..auth.principal import Principal
from ..db import schema as s
from ..platform_errors import PlatformError
from ..policy.repository import current_facts, db_now
from ..runtime.actions import canonical_digest
from .catalog import binding_contract, current_connection


class OAuthService:
    def __init__(self, connections):
        self.connections, self.db, self.settings = connections, connections.db, connections.settings

    @staticmethod
    def browser(c, p):
        if p.auth_session_id is None:
            raise PlatformError("AUTH_REQUIRED", "OAuth requires the initiating authenticated browser session", 401)
        session = c.execute(
            select(s.auth_sessions.c.id).where(
                s.auth_sessions.c.org_id == p.org_id,
                s.auth_sessions.c.user_id == p.user_id,
                s.auth_sessions.c.id == p.auth_session_id,
                s.auth_sessions.c.revoked_at.is_(None),
                s.auth_sessions.c.expires_at > db_now(c),
            )
        ).first()
        if not session:
            raise PlatformError("AUTH_REQUIRED", "The initiating browser session is no longer active", 401)
        current_facts(c, p)

    def _check(self, c, p, row):
        self.browser(c, p)
        if (
            row is None
            or row["requested_by"] != p.user_id
            or row["auth_session_id"] != p.auth_session_id
            or row["membership_revision"] != p.membership_revision
        ):
            raise PlatformError("OAUTH_SESSION_MISMATCH", "OAuth intention belongs to another browser or identity", 403)
        conn = current_connection(
            c, p, row["connection_id"], action="connection.update", active=False, manage=True, lock=True
        )
        binding = self.connections._binding(c, p.org_id, row["binding_id"])
        profile = self.connections.profile(binding["endpoint_id"], binding["endpoint_digest"])
        if (
            conn["state"] == "revoked"
            or conn["resource_status"] != "active"
            or binding["auth_kind"] != "oauth2"
            or binding["state"] not in {"pending", "active"}
            or profile["authentication"] != "oauth2"
        ):
            raise PlatformError("OAUTH_FLOW_UNAVAILABLE", "OAuth connection or binding is no longer current", 409)
        if profile["oauth"]["redirect_uri"] != self.settings.public_origin + "/auth/mcp/callback/" + profile["id"]:
            raise PlatformError(
                "OAUTH_CALLBACK_CONFIGURATION_INVALID", "Registered OAuth callback is not this platform", 409
            )
        return conn, binding, profile

    @staticmethod
    def request(row, binding):
        return {
            "binding": binding_contract(binding),
            "flow_id": str(row["id"]),
            "ticket_id": str(binding["ticket_id"]),
            "not_after": row["expires_at"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    def _prepare(self, p, connection_id, binding_id, request_id):
        with self.connections.write(p) as c:
            self.browser(c, p)
            binding = self.connections._binding(c, p.org_id, binding_id)
            old = (
                c.execute(
                    select(s.mcp_oauth_attempts)
                    .where(s.mcp_oauth_attempts.c.org_id == p.org_id, s.mcp_oauth_attempts.c.binding_id == binding_id)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if old:
                self._check(c, p, old)
                if old["state"] not in {"preparing", "authorizing"} or old["expires_at"] <= db_now(c):
                    raise PlatformError("OAUTH_FLOW_USED", "Start a new authorization intention after this flow", 409)
                return dict(old), self.request(old, binding)
            row = dict(
                org_id=p.org_id,
                id=uuid4(),
                connection_id=connection_id,
                binding_id=binding_id,
                requested_by=p.user_id,
                auth_session_id=p.auth_session_id,
                membership_revision=p.membership_revision,
                request_id=request_id,
                state="preparing",
                expires_at=binding["expires_at"],
            )
            self._check(c, p, row)
            if binding["state"] != "pending" or binding["expires_at"] <= db_now(c):
                raise PlatformError("OAUTH_FLOW_EXPIRED", "OAuth credential intention is not pending", 409)
            c.execute(insert(s.mcp_oauth_attempts).values(**row))
            return row, self.request(row, binding)

    async def start(self, p, connection_id, body):
        with self.db.transaction(p) as c:
            self.browser(c, p)
        prepared = await asyncio.to_thread(self.connections.prepare_credential, p, connection_id, body, oauth=True)
        row, request = await asyncio.to_thread(self._prepare, p, connection_id, prepared["binding_id"], body.request_id)
        try:
            result = await self.connections.client.call("oauth/start", request)
            return await asyncio.to_thread(self._started, p, row["id"], result)
        except PlatformError as exc:
            if exc.code != "CONNECTOR_BUSY":
                await asyncio.to_thread(self.fail, p, row["id"], exc.code)
            raise

    def _started(self, p, id, result):
        with self.connections.write(p) as c:
            row = (
                c.execute(
                    select(s.mcp_oauth_attempts)
                    .where(s.mcp_oauth_attempts.c.org_id == p.org_id, s.mcp_oauth_attempts.c.id == id)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            conn, binding, profile = self._check(c, p, row)
            try:
                url = result["authorization_url"]
                actual, expected = urlsplit(url), urlsplit(profile["oauth"]["authorization_endpoint"])
                query = parse_qs(actual.query, keep_blank_values=True, strict_parsing=True)
                if (
                    not isinstance(url, str)
                    or len(url) > 16384
                    or (actual.scheme, actual.netloc, actual.path) != (expected.scheme, expected.netloc, expected.path)
                    or actual.fragment
                    or actual.username is not None
                    or any(len(values) != 1 for values in query.values())
                ):
                    raise ValueError
                fields = {key: values[0] for key, values in query.items()}
                oauth = profile["oauth"]
                if set(fields) - {
                    "response_type",
                    "response_mode",
                    "client_id",
                    "redirect_uri",
                    "resource",
                    "scope",
                    "state",
                    "code_challenge",
                    "code_challenge_method",
                    "nonce",
                    "prompt",
                    "access_type",
                }:
                    raise ValueError
                if (
                    fields.get("redirect_uri") != oauth["redirect_uri"]
                    or fields.get("client_id") != oauth["client_id"]
                    or fields.get("resource") != oauth["resource"]
                    or fields.get("response_type") != "code"
                    or fields.get("response_mode") != "query"
                    or (
                        "openid" in oauth["scopes"]
                        and not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", fields.get("nonce", ""))
                    )
                    or fields.get("code_challenge_method") != "S256"
                    or not re.fullmatch(r"[A-Za-z0-9_-]{43}", fields.get("code_challenge", ""))
                    or set(fields.get("scope", "").split()) != set(oauth["scopes"])
                    or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", fields.get("state", ""))
                    or result["state_hash"] != canonical_digest("aio-oauth-state-v1", fields["state"])
                    or result.get("flow_id") != str(id)
                    or result.get("state") != "authorizing"
                ):
                    raise ValueError
            except (ValueError, TypeError, KeyError):
                raise PlatformError(
                    "OAUTH_GATEWAY_RESPONSE_INVALID", "OAuth redirect does not match the approved intention", 502
                ) from None
            if (
                row["state"] not in {"preparing", "authorizing"}
                or row["expires_at"] <= db_now(c)
                or (row["state_hash"] and row["state_hash"] != result["state_hash"])
            ):
                raise PlatformError("OAUTH_FLOW_CONFLICT", "OAuth state changed before redirect", 409)
            c.execute(
                update(s.mcp_oauth_attempts)
                .where(s.mcp_oauth_attempts.c.id == id)
                .values(state="authorizing", state_hash=result["state_hash"])
            )
            self.connections.admin.audit(c, p, "mcp.oauth.authorize", conn["id"], "authorizing", {"flow_id": str(id)})
            return {
                "flow_id": id,
                "connection_id": conn["id"],
                "authorization_url": url,
                "expires_at": row["expires_at"],
            }

    def consume(self, p, endpoint_id, state, code, error, issuer):
        if (
            not isinstance(state, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", state)
            or bool(code) == bool(error)
            or (code and (len(code) > 4096 or any(not 33 <= ord(ch) <= 126 for ch in code)))
        ):
            raise PlatformError("OAUTH_CALLBACK_INVALID", "OAuth callback is incomplete or ambiguous", 422)
        with self.connections.write(p) as c:
            row = (
                c.execute(
                    select(s.mcp_oauth_attempts)
                    .where(
                        s.mcp_oauth_attempts.c.org_id == p.org_id,
                        s.mcp_oauth_attempts.c.state_hash == canonical_digest("aio-oauth-state-v1", state),
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            conn, binding, profile = self._check(c, p, row)
            oauth = profile["oauth"]
            if (
                binding["endpoint_id"] != endpoint_id
                or (oauth["require_issuer_response"] and issuer is None)
                or (issuer is not None and issuer != oauth["issuer"])
            ):
                raise PlatformError("OAUTH_ISSUER_MISMATCH", "OAuth callback issuer is not the approved server", 403)
            if row["expires_at"] <= db_now(c):
                raise PlatformError("OAUTH_FLOW_EXPIRED", "OAuth authorization window has expired", 409)
            if error:
                if row["state"] not in {"preparing", "authorizing"}:
                    raise PlatformError("OAUTH_FLOW_USED", "OAuth flow was already consumed", 409)
                failure = "OAUTH_ACCESS_DENIED" if error == "access_denied" else "OAUTH_PROVIDER_ERROR"
                self._fail(c, p, row, failure)
                return {"failure": failure, "connection_id": conn["id"]}
            code_hash = canonical_digest("aio-oauth-code-v1", code)
            if row["state"] in {"exchanging", "completed"}:
                if row["code_hash"] != code_hash or row["response_issuer"] != issuer:
                    raise PlatformError(
                        "OAUTH_CALLBACK_REPLAY", "OAuth callback differs from the consumed intention", 409
                    )
                if row["state"] == "completed":
                    return {"completed": True, "connection_id": conn["id"]}
            elif row["state"] == "authorizing":
                c.execute(
                    update(s.mcp_oauth_attempts)
                    .where(s.mcp_oauth_attempts.c.id == row["id"])
                    .values(state="exchanging", code_hash=code_hash, response_issuer=issuer, consumed_at=db_now(c))
                )
            else:
                raise PlatformError("OAUTH_FLOW_USED", "OAuth flow cannot be consumed again", 409)
            return {
                "id": row["id"],
                "connection_id": conn["id"],
                "request": {**self.request(row, binding), "code": code, "state": state, "response_issuer": issuer},
            }

    async def callback(self, p, endpoint_id, state, code=None, error=None, issuer=None):
        consumed = await asyncio.to_thread(self.consume, p, endpoint_id, state, code, error, issuer)
        if consumed.get("failure"):
            raise PlatformError(consumed["failure"], "External authorization was not granted", 409)
        if consumed.get("completed"):
            return consumed
        try:
            response = await self.connections.client.call("oauth/exchange", consumed["request"])
            return await asyncio.to_thread(self.complete, p, consumed["id"], response)
        except PlatformError as exc:
            if exc.code != "CONNECTOR_BUSY":
                await asyncio.to_thread(self.fail, p, consumed["id"], exc.code)
            raise

    def complete(self, p, id, response):
        with self.connections.write(p) as c:
            row = (
                c.execute(
                    select(s.mcp_oauth_attempts)
                    .where(s.mcp_oauth_attempts.c.org_id == p.org_id, s.mcp_oauth_attempts.c.id == id)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            conn, binding, profile = self._check(c, p, row)
            identity = response.get("external_identity", {})
            if (
                response.get("credential_ref") != str(binding["id"])
                or response.get("state") != "stored"
                or response.get("authentication") != "oauth2"
                or set(response.get("scopes", [])) != set(profile["oauth"]["scopes"])
                or not isinstance(identity, dict)
                or identity.get("issuer") != profile["oauth"]["issuer"]
                or (
                    identity.get("subject") is not None
                    and (not isinstance(identity["subject"], str) or not 1 <= len(identity["subject"]) <= 255)
                )
            ):
                raise PlatformError(
                    "OAUTH_GATEWAY_RESPONSE_INVALID", "OAuth receipt does not match the approved grant", 502
                )
            if row["state"] == "completed":
                return {"connection_id": conn["id"], "flow_id": id, "completed": True}
            if row["state"] != "exchanging" or row["expires_at"] <= db_now(c):
                raise PlatformError("OAUTH_FLOW_EXPIRED", "OAuth completion is obsolete", 409)
            self.connections._activate(p, conn["id"], binding["id"], connection=c)
            c.execute(
                update(s.mcp_connections)
                .where(s.mcp_connections.c.id == conn["id"])
                .values(
                    authorization={
                        "kind": "oauth2",
                        "issuer": identity["issuer"],
                        "subject": identity.get("subject"),
                        "scopes": list(profile["oauth"]["scopes"]),
                    },
                    credential_cleanup=None,
                )
            )
            c.execute(
                update(s.mcp_oauth_attempts)
                .where(s.mcp_oauth_attempts.c.id == id)
                .values(state="completed", completed_at=db_now(c))
            )
            self.connections.admin.audit(
                c, p, "mcp.oauth.complete", conn["id"], "authorized", {"credential_revision": binding["revision"]}
            )
            return {"connection_id": conn["id"], "flow_id": id, "completed": True}

    @staticmethod
    def _fail(c, p, row, code):
        c.execute(
            update(s.mcp_oauth_attempts)
            .where(
                s.mcp_oauth_attempts.c.org_id == p.org_id,
                s.mcp_oauth_attempts.c.id == row["id"],
                s.mcp_oauth_attempts.c.state != "completed",
            )
            .values(state="failed", error_code=code)
        )
        c.execute(
            update(s.mcp_bindings)
            .where(
                s.mcp_bindings.c.org_id == p.org_id,
                s.mcp_bindings.c.id == row["binding_id"],
                s.mcp_bindings.c.state == "pending",
            )
            .values(state="retiring")
        )

    def fail(self, p, id, code):
        safe = code if isinstance(code, str) and re.fullmatch(r"[A-Z0-9_]{1,64}", code) else "OAUTH_FAILED"
        with self.db.transaction(p) as c:
            row = (
                c.execute(
                    select(s.mcp_oauth_attempts)
                    .where(
                        s.mcp_oauth_attempts.c.org_id == p.org_id,
                        s.mcp_oauth_attempts.c.id == id,
                        s.mcp_oauth_attempts.c.requested_by == p.user_id,
                        s.mcp_oauth_attempts.c.auth_session_id == p.auth_session_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if row and row["state"] != "completed":
                self._fail(c, p, row, safe)

    def authorize(self, c, binding, operation, body):
        try:
            flow_id = UUID(body["flow_id"])
        except (ValueError, TypeError, KeyError):
            raise PlatformError("CONNECTOR_AUTHORITY_DENIED", "OAuth has no saved intention", 403) from None
        row = (
            c.execute(
                select(s.mcp_oauth_attempts).where(
                    s.mcp_oauth_attempts.c.org_id == binding["org_id"], s.mcp_oauth_attempts.c.id == flow_id
                )
            )
            .mappings()
            .first()
        )
        if row is None or row["binding_id"] != binding["id"]:
            raise PlatformError("CONNECTOR_AUTHORITY_DENIED", "OAuth binding is not the saved intention", 403)
        p = Principal(
            binding["org_id"],
            row["requested_by"],
            row["membership_revision"],
            row["auth_session_id"],
            service_actor_id="connector-gateway",
        )
        self._check(c, p, row)
        expected = self.request(row, binding)
        if operation == "oauth.exchange":
            expected.update(
                code_hash=row["code_hash"], state_hash=row["state_hash"], response_issuer=row["response_issuer"]
            )
            states = {"exchanging", "completed"}
        else:
            states = {"preparing", "authorizing"}
        if body != expected or row["state"] not in states or row["expires_at"] <= db_now(c):
            raise PlatformError("CONNECTOR_AUTHORITY_DENIED", "OAuth action is outside the current intent", 403)

    def lifecycle(self, c, binding, operation, body):
        expected = {"binding": binding_contract(binding)}
        if operation == "oauth.reauth_required":
            expected["error_code"] = "OAUTH_REAUTH_REQUIRED"
        if body != expected or binding["auth_kind"] != "oauth2":
            raise PlatformError("CONNECTOR_AUTHORITY_DENIED", "Unknown OAuth lifecycle action", 403)
        conn = (
            c.execute(
                select(s.mcp_connections, s.resources.c.status)
                .join(
                    s.resources,
                    (s.resources.c.org_id == s.mcp_connections.c.org_id) & (s.resources.c.id == s.mcp_connections.c.id),
                )
                .where(
                    s.mcp_connections.c.org_id == binding["org_id"], s.mcp_connections.c.id == binding["connection_id"]
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        if binding["state"] != "active" or conn["credential_ref"] != binding["id"] or conn["state"] == "revoked":
            raise PlatformError("CONNECTOR_AUTHORITY_DENIED", "OAuth binding has been revoked or superseded", 403)
        if operation == "oauth.reauth_required":
            if conn["state"] != "reauth_required":
                c.execute(
                    update(s.mcp_connections)
                    .where(s.mcp_connections.c.id == conn["id"])
                    .values(state="reauth_required")
                )
                c.execute(
                    update(s.resources)
                    .where(s.resources.c.id == conn["id"])
                    .values(revision=s.resources.c.revision + 1)
                )
            return
        self.connections.profile(binding["endpoint_id"], binding["endpoint_digest"])
        owner = c.execute(select(s.resources.c.owner_id).where(s.resources.c.id == conn["id"])).scalar_one()
        server_status = c.execute(
            select(s.resources.c.status).where(
                s.resources.c.org_id == binding["org_id"], s.resources.c.id == conn["server_id"]
            )
        ).scalar_one()
        active = c.execute(
            select(s.memberships.c.active).where(
                s.memberships.c.org_id == binding["org_id"], s.memberships.c.user_id == owner
            )
        ).scalar_one()
        if (
            conn["status"] != "active"
            or server_status != "active"
            or conn["state"] not in {"pending", "active"}
            or (conn["scope"] == "personal" and not active)
        ):
            raise PlatformError("CONNECTOR_AUTHORITY_DENIED", "OAuth authorization is no longer live", 403)
        if (
            conn["scope"] == "department"
            and not c.execute(
                select(s.departments.c.active).where(
                    s.departments.c.org_id == binding["org_id"], s.departments.c.id == conn["department_id"]
                )
            ).scalar_one()
        ):
            raise PlatformError("CONNECTOR_AUTHORITY_DENIED", "OAuth department is no longer active", 403)
