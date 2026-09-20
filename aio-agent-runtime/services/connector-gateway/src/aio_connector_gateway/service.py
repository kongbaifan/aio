"""Authenticated control authority, per-identity credentials, operator-only endpoints and durable dispatch."""

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

import httpx

from .contracts import (
    Binding,
    CallRequest,
    CredentialPut,
    CredentialRevoke,
    DiscoverRequest,
    Endpoint,
    GatewayError,
    bounded,
    strict_json,
)
from .protocol import MCPClient
from .vault import Vault


class RemoteAuthority:
    def __init__(self, origin: str, token: str, *, test_mode=False, client=None, ssl_context=None):
        endpoint = Endpoint(
            "control",
            origin.rstrip("/") + "/internal/v1/connectors/authorize",
            frozenset(),
            authentication="none",
            test_mode=test_mode,
        )
        if len(token) < 32 or not token.isascii() or any(ord(c) <= 32 for c in token):
            raise ValueError("A dedicated control authority credential is required")
        self.url, self._token = endpoint.url, token
        self.client = client or httpx.AsyncClient(
            timeout=3, follow_redirects=False, trust_env=False, verify=ssl_context or True
        )
        self._owns_client = client is None

    async def validate(self, operation, payload):
        try:
            async with self.client.stream(
                "POST",
                self.url,
                json={"operation": operation, **payload},
                headers={"X-Connector-Token": self._token, "Accept-Encoding": "identity"},
            ) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 8192:
                        raise ValueError
                result = strict_json(bytes(data), 8192)
                if response.status_code != 200 or not isinstance(result, dict) or result.get("allowed") is not True:
                    raise ValueError
        except (httpx.HTTPError, ValueError, GatewayError):
            raise GatewayError("CONTROL_AUTHORIZATION_DENIED", 403, not_sent=True) from None

    async def close(self):
        if self._owns_client:
            await self.client.aclose()

    async def stdio(self, operation, payload):
        if operation not in {"prepare", "cleanup", "inputs"}:
            raise ValueError("Unknown stdio authority operation")
        limit = 6 * 1024 * 1024 if operation == "inputs" else 65536
        safe_input_errors = {"STDIO_INPUT_QUOTA_EXCEEDED", "STDIO_INPUT_STORAGE_UNAVAILABLE"}
        try:
            async with self.client.stream(
                "POST",
                self.url.rsplit("/", 1)[0] + "/stdio",
                json={"operation": operation, "payload": payload},
                headers={"X-Connector-Token": self._token, "Accept-Encoding": "identity"},
            ) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ValueError
                result = strict_json(bytes(data), limit)
                if response.status_code != 200 and isinstance(result, dict):
                    error = result.get("error", {})
                    if isinstance(error, dict) and error.get("code") in safe_input_errors:
                        raise GatewayError(error["code"], response.status_code, not_sent=True)
                if response.status_code != 200 or not isinstance(result, dict) or result.get("allowed") is not True:
                    raise ValueError
                return result
        except GatewayError as exc:
            if exc.code in safe_input_errors:
                raise
            raise GatewayError("STDIO_AUTHORITY_DENIED", 403, not_sent=True) from None
        except (httpx.HTTPError, ValueError):
            raise GatewayError("STDIO_AUTHORITY_DENIED", 403, not_sent=True) from None


class ConnectorGateway:
    def __init__(
        self,
        vault: Vault,
        endpoints: dict[str, Endpoint],
        authority,
        *,
        client_factory=MCPClient,
        max_active=8,
        oauth_http_factory=None,
        stdio_manager=None,
    ):
        self.vault, self.endpoints, self.authority, self.client_factory = (
            vault,
            dict(endpoints),
            authority,
            client_factory,
        )
        if not 1 <= max_active <= 32:
            raise ValueError("Connector concurrency must be bounded")
        self.max_active, self._active, self._lock = max_active, set(), asyncio.Lock()
        self.stdio_manager = stdio_manager
        from .oauth import OAuthManager
        from .oauth_http import OAuthHTTP

        self.oauth = OAuthManager(vault, self.endpoints, authority, http_factory=oauth_http_factory or OAuthHTTP)

    def endpoint(self, binding: Binding):
        endpoint = self.endpoints.get(binding.endpoint_id)
        if endpoint is None or endpoint.digest != binding.endpoint_digest:
            raise GatewayError("CONNECTOR_ENDPOINT_CHANGED", 403, not_sent=True)
        return endpoint

    @asynccontextmanager
    async def slot(self, binding):
        key = (binding.org_id, binding.connection_id)
        async with self._lock:
            if len(self._active) >= self.max_active or key in self._active:
                raise GatewayError("CONNECTOR_BUSY", 429, not_sent=True)
            self._active.add(key)
        try:
            yield
        finally:
            async with self._lock:
                self._active.discard(key)

    async def put(self, request: CredentialPut):
        endpoint = self.endpoint(request.binding)
        secret = request.secret.get_secret_value()
        if endpoint.authentication == "oauth2" or (endpoint.authentication == "bearer") != bool(secret):
            raise GatewayError("CREDENTIAL_MODE_MISMATCH", 422, not_sent=True)
        await self.authority.validate("credential.put", request.authority())
        response = await asyncio.to_thread(self.vault.put, request.binding, secret)
        try:
            await self.authority.validate("credential.put", request.authority())
        except Exception:
            await asyncio.to_thread(self.vault.revoke, request.binding)
            raise
        return response

    async def revoke(self, request: CredentialRevoke):
        # Cleanup remains possible after removal of an endpoint or user access.
        await self.authority.validate("credential.revoke", request.model_dump(mode="json"))
        if await asyncio.to_thread(self.oauth.store.is_oauth, request.binding):
            result = await self.oauth.revoke(request)
        else:
            result = await asyncio.to_thread(self.vault.revoke, request.binding)
        if self.stdio_manager:
            await self.stdio_cleanup({"binding": request.binding.model_dump(mode="json")})
        return result

    async def stdio_cleanup(self, payload):
        if not self.stdio_manager:
            return {"state": "not_configured"}
        result = await self.authority.stdio("cleanup", payload)
        for spec in result["specs"]:
            response = await self.stdio_manager.call("stop", {"spec": spec})
            if response.get("binding_id") != spec["binding_id"] or response.get("state") != "destroyed":
                raise GatewayError("STDIO_CLEANUP_UNCONFIRMED")
        return {"state": "destroyed"}

    async def oauth_begin(self, request):
        return await self.oauth.begin(request)

    async def oauth_exchange(self, request):
        return await self.oauth.exchange(request)

    async def _client_ready(self, request, endpoint, operation):
        """Refresh only before a business RPC. A later 401 never replays tools/call."""
        generation = None
        if endpoint.authentication == "oauth2":
            token, generation = await self.oauth.access(request)
        else:
            token = await asyncio.to_thread(self.vault.secret, request.binding)
        if endpoint.transport == "stdio":
            if not self.stdio_manager:
                raise GatewayError("STDIO_EXECUTOR_UNAVAILABLE", 503, not_sent=True)
            from .stdio_client import StdioMCPClient

            prepared = await self.authority.stdio(
                "prepare", {"context": {"operation": operation, "payload": request.model_dump(mode="json")}}
            )
            client = StdioMCPClient(
                endpoint,
                token,
                request,
                operation,
                self.stdio_manager,
                self.authority,
                prepared["spec"],
                needs_inputs=prepared.get("needs_inputs", False),
            )
        else:
            client = self.client_factory(endpoint, token)
        for attempt in range(2):
            try:
                await self.authority.validate(operation, request.model_dump(mode="json"))
                info = await client.initialize()
                tools = await client.list_tools()
                return client, token, info, tools
            except BaseException as exc:
                await client.close()
                if (
                    isinstance(exc, GatewayError)
                    and exc.code == "MCP_AUTH_REQUIRED"
                    and endpoint.authentication == "oauth2"
                ):
                    if attempt == 0:
                        token, generation = await self.oauth.access(request, force=True, observed_generation=generation)
                        client = self.client_factory(endpoint, token)
                        continue
                    await self.oauth.rejected(request.binding)
                raise

    @staticmethod
    def remaining(request, endpoint):
        remaining = (request.not_after - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise GatewayError("CONNECTOR_DEADLINE_EXCEEDED", 409, not_sent=True)
        return min(endpoint.timeout_seconds, remaining)

    async def _watch(self, operation, payload):
        while True:
            await asyncio.sleep(1)
            await self.authority.validate(operation, payload)

    async def _guarded(self, operation, request, endpoint, work):
        task = asyncio.create_task(work())
        guard = asyncio.create_task(self._watch(operation, request.model_dump(mode="json")))
        try:
            async with asyncio.timeout(self.remaining(request, endpoint)):
                done, _ = await asyncio.wait({task, guard}, return_when=asyncio.FIRST_COMPLETED)
                if guard in done:
                    await guard
                return await task
        finally:
            guard.cancel()
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await guard
            with suppress(asyncio.CancelledError, Exception):
                await task

    async def discover(self, request: DiscoverRequest):
        endpoint = self.endpoint(request.binding)
        self.remaining(request, endpoint)
        await self.authority.validate("discover", request.model_dump(mode="json"))
        async with self.slot(request.binding):
            client = None

            async def work():
                nonlocal client
                client, token, info, tools = await self._client_ready(request, endpoint, "discover")
                await self.authority.validate("discover", request.model_dump(mode="json"))
                # Descriptions/instructions never become system policy; only explicit operator tool names are eligible.
                selected = [tool for tool in tools if tool["name"] in endpoint.read_tools]
                result = {
                    **info,
                    "tools": selected,
                    "unapproved_tool_count": len(tools) - len(selected),
                    "endpoint_digest": endpoint.digest,
                }
                # Never return a known credential even if an approved server echoed it in a description.
                import json

                raw = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
                if token and token in raw:
                    raise GatewayError("MCP_CREDENTIAL_ECHO_DENIED")
                return bounded(result, 1048576)

            try:
                result = await self._guarded("discover", request, endpoint, work)
            except GatewayError as exc:
                raise GatewayError(exc.code, exc.status, not_sent=True) from None
            except (TimeoutError, httpx.HTTPError):
                raise GatewayError("MCP_DISCOVERY_FAILED", 502, not_sent=True) from None
            finally:
                if client:
                    await client.close()
            return {**result, "remote_session_closed": client.cleanup_confirmed}

    async def call(self, request: CallRequest):
        try:
            return await self._call(request)
        except GatewayError as exc:
            not_sent = exc.not_sent and not await asyncio.to_thread(self.vault.may_have_effect, request)
            raise GatewayError(exc.code, exc.status, not_sent=not_sent) from None

    async def _call(self, request: CallRequest):
        endpoint = self.endpoint(request.binding)
        self.remaining(request, endpoint)
        if request.tool_name not in endpoint.read_tools:
            raise GatewayError("MCP_TOOL_NOT_APPROVED", 403, not_sent=True)
        await self.authority.validate("call", request.model_dump(mode="json"))
        async with self.slot(request.binding):
            cached = await asyncio.to_thread(self.vault.begin, request)
            if cached is not None:
                return {"operation_key": request.operation_key, "result": cached, "replayed": True}
            client = None
            try:

                async def work():
                    nonlocal client
                    client, token, info, tools = await self._client_ready(request, endpoint, "call")
                    current = next((tool for tool in tools if tool["name"] == request.tool_name), None)
                    if current is None or current["digest"] != request.tool_digest:
                        raise GatewayError("MCP_TOOL_DEFINITION_CHANGED", 409, not_sent=True)
                    await self.authority.validate("call", request.model_dump(mode="json"))
                    # Durable intention before any business RPC. A crash/timeout after this never becomes a retry.
                    await asyncio.to_thread(self.vault.calling, request)
                    result = await client.call_tool(request.tool_name, request.arguments, request.operation_key)
                    await self.authority.validate("call", request.model_dump(mode="json"))
                    await asyncio.to_thread(self.vault.finish, request, result)
                    return result

                result = await self._guarded("call", request, endpoint, work)
            except BaseException as exc:
                code = exc.code if isinstance(exc, GatewayError) else "CONNECTOR_EFFECT_UNKNOWN"
                if code == "MCP_AUTH_REQUIRED" and endpoint.authentication == "oauth2":
                    await self.oauth.rejected(request.binding)
                not_sent = await asyncio.shield(asyncio.to_thread(self.vault.fail, request, code))
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise GatewayError(code, 502, not_sent=not_sent) from None
            finally:
                if client:
                    await client.close()
            return {
                "operation_key": request.operation_key,
                "result": result,
                "replayed": False,
                "remote_session_closed": client.cleanup_confirmed,
            }

    async def status(self, request: CallRequest):
        await self.authority.validate("status", request.model_dump(mode="json"))
        return await asyncio.to_thread(self.vault.status, request)
