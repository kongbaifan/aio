"""OAuth grant coordinator; token material never leaves the credential gateway."""

import asyncio
import time
from urllib.parse import urlencode

from .contracts import GatewayError, digest
from .oauth_http import OAuthHTTP
from .oauth_store import OAuthStore


async def db_call(method, *args, **kwargs):
    """Do not release a grant lock while a cancelled to_thread mutation can still commit."""
    task = asyncio.create_task(asyncio.to_thread(method, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        if task.done() and not task.cancelled():
            task.exception()
        raise


class OAuthManager:
    def __init__(self, vault, endpoints, authority, *, http_factory=OAuthHTTP):
        self.store = OAuthStore(vault)
        self.endpoints, self.authority, self.http_factory = endpoints, authority, http_factory
        self._locks = {}
        self._capacity = asyncio.Semaphore(8)

    def lock(self, binding):
        return self._locks.setdefault(binding.credential_ref, asyncio.Lock())

    def endpoint(self, binding):
        endpoint = self.endpoints.get(binding.endpoint_id)
        if not endpoint or endpoint.digest != binding.endpoint_digest or endpoint.authentication != "oauth2":
            raise GatewayError("CONNECTOR_ENDPOINT_CHANGED", 403, not_sent=True)
        return endpoint

    async def begin(self, request):
        endpoint = self.endpoint(request.binding)
        async with self.lock(request.binding), self._capacity:
            await self.authority.validate("oauth.start", request.model_dump(mode="json"))
            data = await db_call(self.store.prepare, request)
            try:
                async with asyncio.timeout(
                    min(endpoint.timeout_seconds, max(0, request.not_after.timestamp() - time.time()))
                ):
                    await self.http_factory(endpoint).metadata()
                await self.authority.validate("oauth.start", request.model_dump(mode="json"))
                await db_call(self.store.authorizing, request)
            except BaseException as exc:
                code = exc.code if isinstance(exc, GatewayError) else "OAUTH_METADATA_UNAVAILABLE"
                await db_call(self.store.fail, request.binding, code, flow_id=request.flow_id)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise GatewayError(code, 502, not_sent=True) from None
            policy = endpoint.oauth
            params = {
                "response_type": "code",
                "response_mode": "query",
                "client_id": policy.client_id,
                "redirect_uri": policy.redirect_uri,
                "resource": policy.resource or endpoint.url,
                "scope": " ".join(policy.scopes),
                "state": data["state"],
                "code_challenge": data["challenge"],
                "code_challenge_method": "S256",
                **policy.authorization_parameters,
            }
            if "openid" in policy.scopes:
                params["nonce"] = data["nonce"]
            return {
                "flow_id": str(request.flow_id),
                "authorization_url": policy.authorization_endpoint + "?" + urlencode(params),
                "state_hash": digest("aio-oauth-state-v1", data["state"]),
                "state": "authorizing",
            }

    async def exchange(self, request):
        endpoint = self.endpoint(request.binding)
        if (endpoint.oauth.require_issuer_response and request.response_issuer is None) or (
            request.response_issuer is not None and request.response_issuer != endpoint.oauth.issuer
        ):
            raise GatewayError("OAUTH_ISSUER_MISMATCH", 403, not_sent=True)
        async with self.lock(request.binding), self._capacity:
            await self.authority.validate("oauth.exchange", request.authority())
            data = await db_call(self.store.exchange, request)
            if data is None:
                return await db_call(self.store.metadata, request.binding)
            raw = None
            try:
                http = self.http_factory(endpoint)
                async with asyncio.timeout(
                    min(endpoint.timeout_seconds, max(0, request.not_after.timestamp() - time.time()))
                ):
                    raw = await http.exchange(request.code.get_secret_value(), data["verifier"])
                    tokens = await http.validate_tokens(raw, nonce=data["nonce"])
                await self.authority.validate("oauth.exchange", request.authority())
                accepted = await db_call(self.store.complete, request, tokens)
                if not accepted:
                    raise GatewayError("OAUTH_REVOKED", 403, not_sent=True)
                await self.authority.validate("oauth.exchange", request.authority())
                return await db_call(self.store.metadata, request.binding)
            except BaseException as exc:
                code = exc.code if isinstance(exc, GatewayError) else "OAUTH_EXCHANGE_UNKNOWN"
                known = code in {
                    "OAUTH_REAUTH_REQUIRED",
                    "OAUTH_CLIENT_REJECTED",
                    "OAUTH_ACCESS_DENIED",
                    "OAUTH_SCOPE_MISMATCH",
                }
                await db_call(
                    self.store.fail,
                    request.binding,
                    code,
                    tokens=raw,
                    unknown=raw is None and not known,
                    flow_id=request.flow_id,
                )
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise GatewayError(code, 502, not_sent=True) from None

    async def report_reauth(self, binding):
        try:
            await self.authority.validate(
                "oauth.reauth_required",
                {"binding": binding.model_dump(mode="json"), "error_code": "OAUTH_REAUTH_REQUIRED"},
            )
        except GatewayError:
            pass  # A revoked/superseded binding must not change the new connection. Local refusal is durable.

    async def access(self, request, *, force=False, observed_generation=None):
        endpoint = self.endpoint(request.binding)
        async with self.lock(request.binding), self._capacity:
            try:
                row, current = await db_call(self.store.current, request.binding)
            except GatewayError:
                await self.report_reauth(request.binding)
                raise
            if (not force or (observed_generation is not None and row["generation"] != observed_generation)) and row[
                "expires_at"
            ] > time.time() + max(30, endpoint.timeout_seconds):
                return current["access_token"], row["generation"]
            retained = [item for item in current.get("retire_tokens", []) if item.get("until", 0) > time.time()]
            if not current.get("refresh_token") or len(retained) >= 6:
                await db_call(self.store.fail, request.binding, "OAUTH_REAUTH_REQUIRED")
                await self.report_reauth(request.binding)
                raise GatewayError("OAUTH_REAUTH_REQUIRED", 401, not_sent=True)
            await self.authority.validate("oauth.refresh", {"binding": request.binding.model_dump(mode="json")})
            await db_call(self.store.refreshing, request.binding, row["generation"])
            raw = None
            try:
                http = self.http_factory(endpoint)
                async with asyncio.timeout(
                    min(endpoint.timeout_seconds, max(0, request.not_after.timestamp() - time.time()))
                ):
                    raw = await http.refresh(current["refresh_token"])
                    tokens = await http.validate_tokens(raw, prior=current)
                await self.authority.validate("oauth.refresh", {"binding": request.binding.model_dump(mode="json")})
                if not await db_call(self.store.refreshed, request.binding, row["generation"], tokens):
                    raise GatewayError("OAUTH_REVOKED", 403, not_sent=True)
                return tokens["access_token"], row["generation"] + 1
            except BaseException as exc:
                code = exc.code if isinstance(exc, GatewayError) else "OAUTH_REFRESH_UNKNOWN"
                known = code in {
                    "OAUTH_REAUTH_REQUIRED",
                    "OAUTH_CLIENT_REJECTED",
                    "OAUTH_SCOPE_MISMATCH",
                    "OAUTH_ACCESS_DENIED",
                }
                await db_call(self.store.fail, request.binding, code, tokens=raw, unknown=raw is None and not known)
                await self.report_reauth(request.binding)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise GatewayError("OAUTH_REAUTH_REQUIRED", 401, not_sent=True) from None

    async def rejected(self, binding):
        await db_call(self.store.fail, binding, "OAUTH_REAUTH_REQUIRED")
        await self.report_reauth(binding)

    async def revoke(self, request):
        await self.authority.validate("credential.revoke", request.model_dump(mode="json"))
        if not await db_call(self.store.is_oauth, request.binding):
            return await db_call(self.store.vault.revoke, request.binding)
        # Disable before waiting for an in-flight refresh; its completion cannot reactivate this reference.
        await db_call(self.store.disable, request.binding)
        async with self.lock(request.binding):
            row, data = await db_call(self.store.current, request.binding, inactive=True)
            if row["state"] == "revoked":
                return {
                    "credential_ref": str(request.binding.credential_ref),
                    "state": "revoked",
                    "remote_revocation": row["remote_revocation"],
                }
            endpoint = self.endpoints.get(request.binding.endpoint_id)
            usable = (
                endpoint and endpoint.digest == request.binding.endpoint_digest and endpoint.authentication == "oauth2"
            )
            remote = "unsupported"
            if usable and endpoint.oauth.revocation_endpoint:
                tokens = {(item["token"], item["hint"]) for item in data.get("retire_tokens", [])}
                for name in ("refresh_token", "access_token"):
                    if data.get(name):
                        tokens.add((data[name], name))
                http = self.http_factory(endpoint)
                async with asyncio.timeout(endpoint.timeout_seconds):
                    for token, hint in sorted(tokens):
                        await http.revoke(token, hint)
                remote = "confirmed"
            if (
                data.get("unknown_issuance")
                or row["remote_revocation"] == "unknown"
                or row["error_code"] in {"OAUTH_REFRESH_UNKNOWN", "OAUTH_EXCHANGE_UNKNOWN", "OAUTH_CLEANUP_UNCERTAIN"}
            ):
                remote = "unknown"
            return await db_call(self.store.revoked, request.binding, remote)
