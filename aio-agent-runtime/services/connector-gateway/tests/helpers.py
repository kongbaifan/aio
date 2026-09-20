from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import httpx

from aio_connector_gateway.contracts import Binding, CallRequest, Endpoint, GatewayError, PROTOCOL_VERSION
from aio_connector_gateway.protocol import MCPClient, tool_definition

TOKEN_A = "synthetic-mcp-alice-credential"
TOKEN_B = "synthetic-mcp-bob-credential"
TOOL = {
    "name": "whoami",
    "description": "Synthetic read-only identity tool",
    "inputSchema": {"type": "object", "properties": {"value": {"type": "integer"}}, "additionalProperties": False},
}


def endpoint(**kwargs):
    return Endpoint("business", "http://127.0.0.1:9999/mcp", frozenset({"whoami"}), test_mode=True, **kwargs)


def binding(ep=None):
    ep = ep or endpoint()
    return Binding(
        org_id=uuid4(),
        connection_id=uuid4(),
        credential_ref=uuid4(),
        credential_revision=1,
        endpoint_id=ep.id,
        endpoint_digest=ep.digest,
    )


def call_request(b=None, **changes):
    data = dict(
        binding=b or binding(),
        not_after=datetime.now(timezone.utc) + timedelta(seconds=30),
        run_id=uuid4(),
        dispatch_id=uuid4(),
        generation=1,
        operation_key=uuid4().hex + uuid4().hex,
        tool_name="whoami",
        tool_digest=tool_definition(TOOL)["digest"],
        arguments={"value": 7},
    )
    return CallRequest(**{**data, **changes})


class Authority:
    def __init__(self):
        self.calls = []
        self.denied = False

    async def validate(self, operation, payload):
        self.calls.append((operation, payload))
        if self.denied:
            raise GatewayError("CONTROL_AUTHORIZATION_DENIED", 403, not_sent=True)

    async def close(self):
        pass


class Chunks(httpx.AsyncByteStream):
    def __init__(self, *parts):
        self.parts = parts

    async def __aiter__(self):
        for part in self.parts:
            yield part


def response(value=None, *, code=200, headers=None, raw=None):
    data = raw if raw is not None else json.dumps(value).encode() if value is not None else b""
    return httpx.Response(code, headers={"Content-Type": "application/json", **(headers or {})}, stream=Chunks(data))


class MCPFixture:
    def __init__(self, *, sse=False):
        self.calls, self.sse, self.business_calls = [], sse, 0
        self.tool = TOOL
        self.fail_after_effect = False

    async def handle(self, request):
        token = request.headers.get("Authorization", "")
        self.calls.append(
            (
                request.method,
                str(request.url),
                token,
                request.headers.get("Mcp-Session-Id"),
                request.headers.get("cookie"),
            )
        )
        if request.method == "DELETE":
            return response(code=204)
        body = json.loads(request.content)
        method = body.get("method")
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "explicit-synthetic-mcp", "version": "1"},
            }
            return response(
                {"jsonrpc": "2.0", "id": body["id"], "result": result},
                headers={
                    "Mcp-Session-Id": "session-" + token.rsplit("-", 2)[1],
                    "Set-Cookie": "private-cookie=must-not-forward",
                },
            )
        if method == "notifications/initialized" or method is None:
            return response(code=202)
        if method == "tools/list":
            result = {"tools": [self.tool]}
        else:
            assert method == "tools/call"
            self.business_calls += 1
            if self.fail_after_effect:
                raise httpx.ReadError("Synthetic response lost AFTER effect", request=request)
            result = {
                "content": [{"type": "text", "text": "alice" if token == "Bearer " + TOKEN_A else "bob"}],
                "structuredContent": {"value": body["params"]["arguments"].get("value", 0)},
            }
        message = {"jsonrpc": "2.0", "id": body["id"], "result": result}
        if self.sse:
            data = b"event: message\r\ndata: " + json.dumps(message).encode() + b"\r\n\r\n"
            return httpx.Response(
                200, headers={"Content-Type": "text/event-stream"}, stream=Chunks(data[:17], data[17:])
            )
        return response(message)

    def client(self, ep, token):
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))
        result = MCPClient(ep, token, http_client=client)
        result._owned = True
        return result
