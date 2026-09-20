"""MCP transport through the isolated Manager, never a subprocess on the Gateway host."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx

from .contracts import Endpoint, GatewayError, PROTOCOL_VERSION, strict_json, bounded, digest
from .protocol import tool_definition, normalize_result
from .stdio_contracts import attachment_manifest


class StdioManagerClient:
    def __init__(self, url, token, *, test_mode=False, http_client=None, ssl_context=None):
        endpoint = Endpoint("stdio-manager", url.rstrip("/"), frozenset(), authentication="none", test_mode=test_mode)
        if not token or not token.isascii() or len(token) < 32:
            raise ValueError("Stdio manager requires its own strong private service credential")
        self.url, self._token = endpoint.url, token
        self.http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(130, connect=5), trust_env=False, follow_redirects=False, verify=ssl_context or True
        )
        self.owned = http_client is None

    async def call(self, operation, payload):
        if operation not in {"open", "rpc", "stop"}:
            raise ValueError("Unknown stdio management operation")
        try:
            async with self.http.stream(
                "POST",
                self.url + "/v1/stdio/" + operation,
                json=payload,
                headers={"Authorization": "Bearer " + self._token, "Accept-Encoding": "identity"},
            ) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 2 * 1024 * 1024:
                        raise GatewayError("STDIO_MANAGER_RESPONSE_TOO_LARGE")
                value = strict_json(bytes(data), 2 * 1024 * 1024)
                if response.status_code != 200 or not isinstance(value, dict):
                    error = value.get("error", {}) if isinstance(value, dict) else {}
                    code = error.get("code", "STDIO_MANAGER_FAILED")
                    if not isinstance(code, str) or len(code) > 64 or not code.replace("_", "").isalnum():
                        code = "STDIO_MANAGER_FAILED"
                    raise GatewayError(code, 502, not_sent=False)
                return value
        except httpx.HTTPError:
            raise GatewayError("STDIO_MANAGER_UNAVAILABLE", 503, not_sent=False) from None

    async def close(self):
        if self.owned:
            await self.http.aclose()


class StdioMCPClient:
    def __init__(self, endpoint, token, request, operation, manager, authority, spec, *, needs_inputs=False):
        self.endpoint, self.token, self.request, self.operation = endpoint, token, request, operation
        self.manager, self.authority, self.spec = manager, authority, spec
        self.context = {"operation": operation, "payload": request.model_dump(mode="json")}
        self.cleanup_confirmed = False
        self.needs_inputs = needs_inputs
        expected = {
            "schema_version": 2 if endpoint.stdio.input_policy == "run_attachments" else 1,
            "kind": "mcp_stdio",
            "org_id": str(request.binding.org_id),
            "connection_id": str(request.binding.connection_id),
            "credential_ref": str(request.binding.credential_ref),
            "credential_revision": request.binding.credential_revision,
            "endpoint_id": endpoint.id,
            "endpoint_digest": endpoint.digest,
            "profile_id": endpoint.stdio.profile_id,
            "image_digest": endpoint.stdio.image_digest,
            "template_digest": endpoint.stdio.template_digest,
            "target_kind": "run" if operation == "call" else "discovery",
            "target_id": str(request.run_id if operation == "call" else request.discovery_id),
            "generation": request.generation if operation == "call" else 1,
            "target_slot": "connector/stdio/" + str(request.binding.connection_id),
        }
        try:
            if expected["schema_version"] == 2:
                expected["input_manifest"] = attachment_manifest(spec.get("input_manifest"))
                if operation == "discover" and expected["input_manifest"]:
                    raise ValueError
            if type(needs_inputs) is not bool or (needs_inputs and not expected.get("input_manifest")):
                raise ValueError
            if type(spec.get("schema_version")) is not int:
                raise ValueError
            UUID(spec["binding_id"])
            deadline = datetime.fromisoformat(spec["deadline"].replace("Z", "+00:00"))
            if set(spec) != set(expected) | {"binding_id", "deadline"} or any(
                spec.get(key) != value for key, value in expected.items()
            ):
                raise ValueError
            if deadline.tzinfo is None or not 0 < (deadline - datetime.now(timezone.utc)).total_seconds() <= 3600:
                raise ValueError
        except (KeyError, ValueError, TypeError):
            raise GatewayError("STDIO_SPEC_INVALID", 403, not_sent=True) from None

    async def rpc(self, method, params=None):
        id = uuid4()
        remaining = (self.request.not_after - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise GatewayError("CONNECTOR_DEADLINE_EXCEEDED", 409, not_sent=True)
        value = await self.manager.call(
            "rpc",
            {
                "spec": self.spec,
                "context": self.context,
                "request_id": str(id),
                "method": method,
                "params": params or {},
                "timeout_seconds": max(1, min(self.endpoint.timeout_seconds, int(remaining))),
            },
        )
        if value.get("binding_id") != self.spec["binding_id"] or value.get("request_id") != str(id):
            raise GatewayError("STDIO_RESPONSE_INVALID")
        message = value.get("response")
        if method.startswith("notifications/"):
            if message is not None:
                raise GatewayError("STDIO_RESPONSE_INVALID")
            return None
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or message.get("id") != str(id):
            raise GatewayError("STDIO_RESPONSE_INVALID")
        if "error" in message:
            raise GatewayError("MCP_REMOTE_ERROR")
        result = message.get("result")
        if not isinstance(result, dict):
            raise GatewayError("STDIO_RESPONSE_INVALID")
        return bounded(result, 1048576)

    async def initialize(self):
        files = []
        if self.needs_inputs:
            supplied = await self.authority.stdio("inputs", {"spec": self.spec, "context": self.context})
            files = supplied.get("input_files")
            if not isinstance(files, list) or len(files) != len(self.spec["input_manifest"]):
                raise GatewayError("STDIO_INPUT_MANIFEST_MISMATCH", 403, not_sent=True)
        try:
            ready = await self.manager.call(
                "open", {"spec": self.spec, "context": self.context, "credential": self.token, "input_files": files}
            )
        finally:
            # Do not retain document bodies in this client or an operation journal.
            files = None
        if (
            ready.get("binding_id") != self.spec["binding_id"]
            or ready.get("state") != "ready"
            or ready.get("spec_digest") != digest(f"aio-stdio-spec-v{self.spec['schema_version']}", self.spec)
        ):
            raise GatewayError("STDIO_RESPONSE_INVALID")
        result = await self.rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "aio-connector-gateway", "version": "1"},
            },
        )
        if result.get("protocolVersion") != PROTOCOL_VERSION or not isinstance(result.get("serverInfo"), dict):
            raise GatewayError("MCP_PROTOCOL_UNSUPPORTED")
        await self.rpc("notifications/initialized")
        return {"protocol_version": PROTOCOL_VERSION, "server_info": result["serverInfo"], "transport": "stdio"}

    async def list_tools(self):
        tools, seen, cursor = [], set(), None
        for _ in range(8):
            result = await self.rpc("tools/list", {"cursor": cursor} if cursor else {})
            values = result.get("tools")
            if not isinstance(values, list) or len(values) + len(tools) > 64:
                raise GatewayError("MCP_TOOL_LIMIT")
            for value in values:
                tool = tool_definition(value)
                if tool["name"] in seen:
                    raise GatewayError("MCP_DUPLICATE_TOOL")
                tools.append(tool)
                seen.add(tool["name"])
            following = result.get("nextCursor")
            if following is None:
                return tools
            if not isinstance(following, str) or not 1 <= len(following) <= 256 or following == cursor:
                raise GatewayError("MCP_CURSOR_INVALID")
            cursor = following
        raise GatewayError("MCP_TOOL_LIMIT")

    async def call_tool(self, name, arguments, operation_key):
        return normalize_result(
            await self.rpc(
                "tools/call", {"name": name, "arguments": arguments, "_meta": {"aio_operation_key": operation_key}}
            ),
            self.token,
        )

    async def close(self):
        if self.operation == "discover":
            value = await self.authority.stdio(
                "cleanup", {"org_id": str(self.request.binding.org_id), "discovery_id": str(self.request.discovery_id)}
            )
            for spec in value["specs"]:
                result = await self.manager.call("stop", {"spec": spec})
                if result.get("binding_id") != spec["binding_id"] or result.get("state") != "destroyed":
                    raise GatewayError("STDIO_CLEANUP_UNCONFIRMED")
            self.cleanup_confirmed = True
