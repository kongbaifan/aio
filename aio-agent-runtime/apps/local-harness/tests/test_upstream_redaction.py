"""上游响应体的脱敏与截断。

网关的错误体会走两条路：SSE error 帧发到浏览器、audit.write 落进 var/audit.jsonl。
one-api 系网关常在错误体里回显请求头 / token 前缀，等于把密钥写进日志文件。
这里确认无论 HTTP 4xx、非 JSON、还是缺 choices，异常消息里都不会带出完整密钥。
"""

import httpx
import pytest

from app.llm.openai_compatible import (
    LlmError,
    OpenAICompatibleClient,
    _sanitize_upstream,
)
from app.llm.providers import ModelRef


# 假密钥：形态要像真的（脱敏正则按 sk- + 长串匹配），但绝不能用真实值的任何片段。
SECRET = "sk-test-0000000000000000000000000000fake"


def _client(handler) -> OpenAICompatibleClient:
    ref = ModelRef(
        provider="p",
        id="m",
        name="m",
        base_url="https://gw.example.com/v1",
        api="openai-completions",
        api_key="sk-test-client-key",
    )
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return OpenAICompatibleClient(ref, timeout=5, http_client=http)


@pytest.mark.parametrize(
    "text",
    [
        f'{{"error":"invalid key","authorization":"Bearer {SECRET}"}}',
        f"upstream echoed your key: {SECRET} please retry",
        f"Authorization: Bearer {SECRET}",
    ],
)
def test_sanitize_strips_secrets(text):
    out = _sanitize_upstream(text)
    assert SECRET not in out
    assert "[REDACTED]" in out


def test_sanitize_truncates():
    assert len(_sanitize_upstream("x" * 5000)) == 200


def test_sanitize_keeps_harmless_text():
    msg = "rate limit exceeded, try again later"
    assert _sanitize_upstream(msg) == msg


@pytest.mark.asyncio
async def test_http_error_body_is_redacted():
    def handler(request: httpx.Request) -> httpx.Response:
        # 网关把请求头里的 Authorization 原样回显在错误体里。
        return httpx.Response(401, text=f'{{"detail":"bad token: Bearer {SECRET}"}}')

    client = _client(handler)
    with pytest.raises(LlmError) as err:
        await client.respond([{"role": "user", "content": "hi"}], [])
    message = str(err.value)
    assert SECRET not in message
    assert message == _sanitize_upstream(message)  # 幂等：里面确实没有残留密钥
    assert err.value.body and SECRET not in err.value.body
    await client._client.aclose()


@pytest.mark.asyncio
async def test_non_json_body_is_redacted():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=f"<html>gateway error, token={SECRET}</html>")

    client = _client(handler)
    with pytest.raises(LlmError) as err:
        await client.respond([{"role": "user", "content": "hi"}], [])
    assert SECRET not in str(err.value)
    await client._client.aclose()


@pytest.mark.asyncio
async def test_missing_choices_body_is_redacted():
    def handler(request: httpx.Request) -> httpx.Response:
        # 合法 JSON 但没有 choices，且里面藏了个密钥。
        return httpx.Response(200, json={"echo": {"authorization": f"Bearer {SECRET}"}})

    client = _client(handler)
    with pytest.raises(LlmError) as err:
        await client.respond([{"role": "user", "content": "hi"}], [])
    assert SECRET not in str(err.value)
    await client._client.aclose()
