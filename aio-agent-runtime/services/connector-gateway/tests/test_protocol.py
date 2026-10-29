import asyncio
import base64
import json
from urllib.parse import quote

import httpx
import pytest

from aio_connector_gateway.contracts import GatewayError, strict_json
from aio_connector_gateway.protocol import MCPClient, normalize_result
from helpers import MCPFixture, TOKEN_A, TOKEN_B, endpoint, response


@pytest.mark.parametrize("sse", [False, True])
def test_standard_initialize_list_call_and_close_with_json_and_sse(sse):
    fixture = MCPFixture(sse=sse)

    async def run():
        client = fixture.client(endpoint(), TOKEN_A)
        try:
            assert (await client.initialize())["protocol_version"] == "2025-06-18"
            tools = await client.list_tools()
            assert tools[0]["name"] == "whoami"
            result = await client.call_tool("whoami", {"value": 7}, "a" * 64)
            assert result["content"][0]["text"] == "alice"
            assert result["structured_content"] == {"value": 7}
        finally:
            await client.close()
        assert client.cleanup_confirmed

    asyncio.run(run())
    assert fixture.business_calls == 1
    assert fixture.calls[-1][0] == "DELETE"
    assert all(call[4] is None for call in fixture.calls)


def test_parallel_identities_do_not_share_mcp_sessions_or_cookies():
    fixture = MCPFixture(sse=True)

    async def one(token):
        client = fixture.client(endpoint(), token)
        try:
            await client.initialize()
            return await client.call_tool("whoami", {"value": 5}, "f" * 64)
        finally:
            await client.close()

    async def run():
        return await asyncio.gather(one(TOKEN_A), one(TOKEN_B))

    results = asyncio.run(run())
    assert [r["content"][0]["text"] for r in results] == ["alice", "bob"]
    for _, _, token, session, cookie in fixture.calls:
        assert cookie is None
        if session:
            assert session == ("session-alice" if token.endswith(TOKEN_A) else "session-bob")


@pytest.mark.parametrize("data", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":9007199254740992}', b'"\xff"'])
def test_ambiguous_rpc_json_is_rejected(data):
    with pytest.raises(GatewayError):
        strict_json(data)


@pytest.mark.parametrize(
    "kind", ["redirect", "compression", "wrong-id", "batch", "huge", "incomplete-sse", "legacy-endpoint"]
)
def test_protocol_failures_never_follow_urls_or_retry(kind):
    calls = []

    async def handler(request):
        calls.append(str(request.url))
        body = json.loads(request.content)
        if kind == "redirect":
            return response(code=307, headers={"Location": "http://169.254.169.254/metadata"})
        if kind == "compression":
            return response({}, headers={"Content-Encoding": "gzip"})
        if kind == "wrong-id":
            return response({"jsonrpc": "2.0", "id": "wrong", "result": {}})
        if kind == "batch":
            return response([{"jsonrpc": "2.0", "id": body["id"], "result": {}}])
        if kind == "huge":
            return response(raw=b"x" * 1048577)
        if kind == "incomplete-sse":
            return response(raw=b'data: {"jsonrpc":"2.0"}', headers={"Content-Type": "text/event-stream"})
        return response(raw=b"event: endpoint\ndata: /new-endpoint\n\n", headers={"Content-Type": "text/event-stream"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = MCPClient(endpoint(), TOKEN_A, http_client=http)
            with pytest.raises(GatewayError):
                await client.initialize()

    asyncio.run(run())
    assert calls == [endpoint().url]


def test_unadvertised_sampling_is_refused_instead_of_executed():
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if "method" not in body:
            return response(code=202)
        if body["method"] == "notifications/initialized":
            return response(code=202)
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "synthetic"}}
        first = {"jsonrpc": "2.0", "id": "bad-sampling", "method": "sampling/createMessage", "params": {"messages": []}}
        second = {"jsonrpc": "2.0", "id": body["id"], "result": result}
        raw = b"data: " + json.dumps(first).encode() + b"\n\ndata: " + json.dumps(second).encode() + b"\n\n"
        return response(raw=raw, headers={"Content-Type": "text/event-stream"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = MCPClient(endpoint(), TOKEN_A, http_client=http)
            await client.initialize()

    asyncio.run(run())
    refused = next(r for r in requests if r.get("id") == "bad-sampling")
    assert refused["error"]["code"] == -32601
    assert requests[0]["params"]["capabilities"] == {}


def test_resource_links_are_data_not_http_requests_and_binaries_are_explicitly_unavailable():
    value = normalize_result(
        {
            "content": [
                {"type": "resource_link", "uri": "http://169.254.169.254/latest/meta-data", "name": "untrusted"},
                {"type": "image", "mimeType": "image/png", "data": "aW5lcnQ="},
                {"type": "text", "text": "do not expose " + TOKEN_A},
            ]
        },
        TOKEN_A,
    )
    assert value["content"][0]["automatically_fetched"] is False
    assert value["omitted_binary"][0]["reason"] == "BINARY_ARTIFACT_IMPORT_UNAVAILABLE"
    assert TOKEN_A not in str(value)


@pytest.mark.parametrize("encode", [
    lambda v: v, lambda v: quote(v, safe=""), lambda v: base64.b64encode(v.encode()).decode(),
    lambda v: base64.urlsafe_b64encode(v.encode()).decode().rstrip("="),
], ids=["raw", "percent", "base64", "base64url"])
def test_echoed_credential_is_removed_in_every_encoding_a_server_may_use(encode):
    credential = TOKEN_A + "/+?&="
    echoed = encode(credential)
    value = normalize_result(
        {
            "content": [{"type": "text", "text": f"Authorization: Bearer {echoed}"}],
            "structuredContent": {"url": f"https://api.example.test/?token={echoed}", echoed: "as key"},
        },
        credential,
    )
    rendered = json.dumps(value)
    assert echoed not in rendered and credential not in rendered and "[credential-redacted]" in rendered
