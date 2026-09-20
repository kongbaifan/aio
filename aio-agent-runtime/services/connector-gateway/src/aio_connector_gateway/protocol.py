"""Bounded MCP 2025-06-18 Streamable HTTP. No hidden transports, retries or automatic resource fetch."""

import asyncio
import base64
import hashlib
import re
from uuid import uuid4

import httpx

from .contracts import (
    Endpoint,
    GatewayError,
    MAX_RPC_BYTES,
    MAX_RESULT_BYTES,
    PROTOCOL_VERSION,
    bounded,
    digest,
    strict_json,
)
from .egress import PinnedTransport


def tool_definition(raw: dict) -> dict:
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("name"), str)
        or not 1 <= len(raw["name"]) <= 128
        or any(ord(c) < 32 for c in raw["name"])
    ):
        raise GatewayError("MCP_INVALID_TOOL")
    schema = raw.get("inputSchema")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise GatewayError("MCP_INVALID_TOOL")
    description = raw.get("description", "")
    if not isinstance(description, str) or len(description.encode("utf-8")) > 8192:
        raise GatewayError("MCP_INVALID_TOOL")
    output_schema = raw.get("outputSchema")
    if output_schema is not None and not isinstance(output_schema, dict):
        raise GatewayError("MCP_INVALID_TOOL")
    value = bounded(
        {
            "name": raw["name"],
            "description": description,
            "input_schema": schema,
            "output_schema": output_schema,
            "annotations": raw.get("annotations", {}),
        },
        65536,
    )
    return {**value, "digest": digest("aio-mcp-tool-v1", value)}


def normalize_result(raw: dict, secret: str) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("content", []), list) or len(raw.get("content", [])) > 32:
        raise GatewayError("MCP_INVALID_RESULT")
    content, omitted = [], []
    for item in raw.get("content", []):
        if not isinstance(item, dict):
            raise GatewayError("MCP_INVALID_RESULT")
        kind = item.get("type")
        if kind == "text":
            if not isinstance(item.get("text"), str):
                raise GatewayError("MCP_INVALID_RESULT")
            content.append({"type": "text", "text": item["text"]})
        elif kind == "resource_link":
            if not isinstance(item.get("uri"), str) or len(item["uri"]) > 2048:
                raise GatewayError("MCP_INVALID_RESULT")
            content.append(
                {
                    "type": "resource_link",
                    "uri": item["uri"],
                    "name": str(item.get("name", ""))[:256],
                    "automatically_fetched": False,
                }
            )
        elif (
            kind == "resource"
            and isinstance(item.get("resource"), dict)
            and isinstance(item["resource"].get("text"), str)
        ):
            content.append(
                {
                    "type": "text",
                    "text": item["resource"]["text"],
                    "source_uri": str(item["resource"].get("uri", ""))[:2048],
                }
            )
        elif kind in {"image", "audio", "resource"}:
            value = item.get("resource", item)
            encoded = value.get("data", value.get("blob")) if isinstance(value, dict) else None
            try:
                if not isinstance(encoded, str) or len(encoded) > MAX_RPC_BYTES:
                    raise ValueError
                data = base64.b64decode(encoded, validate=True)
            except ValueError:
                raise GatewayError("MCP_INVALID_RESULT") from None
            # Binary artifact import is an explicit future path; do not pretend this is a downloadable file.
            omitted.append(
                {
                    "type": kind,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "reason": "BINARY_ARTIFACT_IMPORT_UNAVAILABLE",
                }
            )
        else:
            raise GatewayError("MCP_RESULT_TYPE_UNSUPPORTED")
    if type(raw.get("isError", False)) is not bool:
        raise GatewayError("MCP_INVALID_RESULT")
    structured = raw.get("structuredContent")
    if structured is not None and not isinstance(structured, dict):
        raise GatewayError("MCP_INVALID_RESULT")

    def scrub(value):
        if isinstance(value, str):
            return value.replace(secret, "[credential-redacted]") if secret else value
        if isinstance(value, dict):
            return {scrub(k): scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value

    return bounded(
        scrub(
            {
                "content": content,
                "structured_content": structured,
                "is_error": raw.get("isError", False),
                "omitted_binary": omitted,
                "untrusted_tool_data": True,
            }
        ),
        MAX_RESULT_BYTES,
    )


class MCPClient:
    def __init__(self, endpoint: Endpoint, token: str, *, http_client=None, ssl_context=None):
        self.endpoint, self._token = endpoint, token
        self.client = http_client or httpx.AsyncClient(
            transport=PinnedTransport(endpoint, ssl_context=ssl_context),
            timeout=endpoint.timeout_seconds,
            trust_env=False,
            follow_redirects=False,
        )
        self._owned = http_client is None
        self.session_id = None
        self.initialized = False
        self.business_request_id = None
        self.cleanup_confirmed = True

    def _headers(self):
        headers = {
            "Accept": "application/json, text/event-stream",
            "Accept-Encoding": "identity",
            "Content-Type": "application/json",
        }
        if self.endpoint.authentication in {"bearer", "oauth2"}:
            headers["Authorization"] = "Bearer " + self._token
        if self.initialized:
            headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _session(self, response):
        value = response.headers.get("mcp-session-id")
        if value:
            if len(value) > 256 or not value.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in value):
                raise GatewayError("MCP_INVALID_SESSION")
            if self.session_id is not None and value != self.session_id:
                raise GatewayError("MCP_SESSION_CHANGED")
            self.session_id = value

    async def _bytes(self, response):
        total = 0
        async for chunk in response.aiter_raw():
            total += len(chunk)
            if total > MAX_RPC_BYTES:
                raise GatewayError("RESPONSE_TOO_LARGE")
            yield chunk

    async def _messages(self, response):
        if response.headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
            raise GatewayError("MCP_COMPRESSED_RESPONSE_DENIED")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type == "application/json":
            data = bytearray()
            async for chunk in self._bytes(response):
                data.extend(chunk)
            yield strict_json(bytes(data))
            return
        if content_type != "text/event-stream":
            raise GatewayError("MCP_CONTENT_TYPE_UNSUPPORTED")
        buffer, data = bytearray(), []
        count, frame_bytes = 0, 0
        event = "message"
        async for chunk in self._bytes(response):
            buffer.extend(chunk)
            if len(buffer) + frame_bytes > 262144:
                raise GatewayError("MCP_FRAME_TOO_LARGE")
            while True:
                match = re.search(rb"\r\n|\r|\n", buffer)
                if match is None or (match.group() == b"\r" and match.end() == len(buffer)):
                    break
                line = bytes(buffer[: match.start()])
                del buffer[: match.end()]
                frame_bytes += len(line)
                if frame_bytes > 262144:
                    raise GatewayError("MCP_FRAME_TOO_LARGE")
                if not line:
                    count += 1
                    if count > 256:
                        raise GatewayError("MCP_EVENT_LIMIT")
                    if data:
                        if event != "message":
                            raise GatewayError("MCP_EVENT_UNSUPPORTED")
                        yield strict_json(b"\n".join(data), 262144)
                    data, event, frame_bytes = [], "message", 0
                elif line.startswith(b"data:"):
                    data.append(line[5:].removeprefix(b" "))
                elif line.startswith(b"event:"):
                    try:
                        event = line[6:].strip().decode("ascii")
                    except UnicodeError:
                        raise GatewayError("MCP_EVENT_UNSUPPORTED") from None
                elif line.startswith((b":", b"id:", b"retry:")):
                    pass  # No automatically resumed stream, retry, or external endpoint event.
        if buffer or data:
            raise GatewayError("MCP_INCOMPLETE_RESPONSE")

    async def _post(self, payload, *, expected_id=None):
        self.client.cookies.clear()
        try:
            async with asyncio.timeout(self.endpoint.timeout_seconds):
                async with self.client.stream(
                    "POST", self.endpoint.url, json=payload, headers=self._headers(), follow_redirects=False
                ) as response:
                    if response.status_code in {401, 403}:
                        raise GatewayError("MCP_AUTH_REQUIRED", 403)
                    if response.status_code == 429:
                        raise GatewayError("MCP_RATE_LIMITED", 429)
                    if response.status_code in {301, 302, 303, 307, 308}:
                        raise GatewayError("MCP_REDIRECT_DENIED", 403)
                    if expected_id is None:
                        if response.status_code not in {200, 202, 204}:
                            raise GatewayError("MCP_HTTP_ERROR")
                        # Still bound and reject encoded bodies; notification acknowledgements contain no result.
                        if response.headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
                            raise GatewayError("MCP_COMPRESSED_RESPONSE_DENIED")
                        async for _ in self._bytes(response):
                            pass
                        return None
                    if response.status_code != 200:
                        raise GatewayError("MCP_HTTP_ERROR")
                    self._session(response)
                    events, reverse_requests = 0, 0
                    async for message in self._messages(response):
                        events += 1
                        if events > 256 or not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                            raise GatewayError("MCP_INVALID_RESPONSE")
                        if "method" in message:
                            if "result" in message or "error" in message:
                                raise GatewayError("MCP_INVALID_RESPONSE")
                            if "id" not in message:
                                continue  # Bounded notifications are untrusted data; no logging/sampling side effects.
                            reverse_requests += 1
                            if (
                                reverse_requests > 4
                                or type(message["id"]) not in {str, int}
                                or len(str(message["id"])) > 128
                            ):
                                raise GatewayError("MCP_SERVER_REQUEST_LIMIT")
                            reply = {"jsonrpc": "2.0", "id": message["id"]}
                            if message["method"] == "ping":
                                reply["result"] = {}
                            else:
                                reply["error"] = {"code": -32601, "message": "Client capability is not enabled"}
                            await self._post(reply)
                            continue
                        if (
                            type(message.get("id")) is not str
                            or message["id"] != expected_id
                            or ("result" in message) == ("error" in message)
                        ):
                            raise GatewayError("MCP_RESPONSE_ID_MISMATCH")
                        if "error" in message:
                            raise GatewayError("MCP_REMOTE_ERROR")
                        if not isinstance(message["result"], dict):
                            raise GatewayError("MCP_INVALID_RESPONSE")
                        return bounded(message["result"], MAX_RPC_BYTES)
                    raise GatewayError("MCP_INCOMPLETE_RESPONSE")
        except (httpx.HTTPError, TimeoutError):
            raise GatewayError("MCP_TRANSPORT_UNCONFIRMED") from None
        finally:
            self.client.cookies.clear()

    async def _rpc(self, method, params=None, *, business=False):
        id = "aio-" + uuid4().hex
        if business:
            self.business_request_id = id
        return await self._post({"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}, expected_id=id)

    async def initialize(self):
        response = await self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "aio-connector-gateway", "version": "0.1.0"},
            },
        )
        if response.get("protocolVersion") != PROTOCOL_VERSION:
            raise GatewayError("MCP_PROTOCOL_VERSION_UNSUPPORTED")
        capabilities = response.get("capabilities")
        if not isinstance(capabilities, dict) or "tools" not in capabilities:
            raise GatewayError("MCP_TOOLS_UNAVAILABLE")
        self.initialized = True
        await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return {"protocol_version": PROTOCOL_VERSION, "server_info": bounded(response.get("serverInfo", {}), 4096)}

    async def list_tools(self):
        if not self.initialized:
            raise GatewayError("MCP_NOT_INITIALIZED")
        tools, seen, cursors = [], set(), set()
        cursor = None
        for _ in range(8):
            response = await self._rpc("tools/list", {"cursor": cursor} if cursor is not None else {})
            if not isinstance(response.get("tools"), list):
                raise GatewayError("MCP_INVALID_TOOLS")
            for raw in response["tools"]:
                tool = tool_definition(raw)
                if tool["name"] in seen or len(tools) >= 64:
                    raise GatewayError("MCP_TOOL_LIMIT")
                seen.add(tool["name"])
                tools.append(tool)
            cursor = response.get("nextCursor")
            if cursor is None:
                return tools
            if not isinstance(cursor, str) or not cursor or len(cursor) > 512 or cursor in cursors:
                raise GatewayError("MCP_INVALID_CURSOR")
            cursors.add(cursor)
        raise GatewayError("MCP_TOOL_LIMIT")

    async def call_tool(self, name, arguments, operation_key):
        if not self.initialized or name not in self.endpoint.read_tools:
            raise GatewayError("MCP_TOOL_NOT_APPROVED", 403, not_sent=True)
        raw = await self._rpc(
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
                "_meta": {"progressToken": operation_key, "io.aio/operationKey": operation_key},
            },
            business=True,
        )
        return normalize_result(raw, self._token)

    async def close(self):
        try:
            if self.session_id:
                async with asyncio.timeout(2):
                    self.client.cookies.clear()
                    async with self.client.stream(
                        "DELETE", self.endpoint.url, headers=self._headers(), follow_redirects=False
                    ) as response:
                        self.cleanup_confirmed = response.status_code in {200, 202, 204, 404, 410}
                        async for _ in self._bytes(response):
                            pass
        except (Exception, asyncio.CancelledError):
            self.cleanup_confirmed = False
        finally:
            if self._owned:
                await self.client.aclose()
            self._token = ""
