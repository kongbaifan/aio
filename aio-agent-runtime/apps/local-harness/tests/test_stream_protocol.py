"""流式协议解析的边界情况。

respond_stream 里最容易出错的部分此前一行没测：tool_call 分片按 index 归组、
id 只在首片出现、arguments 字符串分片拼接、finish_reason、reasoning_content、
以及连接阶段的重试。这里补上。
"""

import httpx
import pytest

from app.llm.base import TextDelta
from app.llm.openai_compatible import LlmError, OpenAICompatibleClient
from app.llm.providers import ModelRef


def _sse(*chunks: str) -> bytes:
    body = "".join(f"data: {chunk}\n\n" for chunk in chunks)
    return (body + "data: [DONE]\n\n").encode("utf-8")


def _client(handler, *, max_retries: int = 2) -> OpenAICompatibleClient:
    ref = ModelRef(
        provider="p",
        id="m",
        name="m",
        base_url="https://gw.example.com/v1",
        api="openai-completions",
        api_key="sk-test-key",
    )
    return OpenAICompatibleClient(
        ref,
        timeout=5,
        max_retries=max_retries,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def _collect(client, messages=None, tools=None):
    deltas, turn = [], None
    async for item in client.respond_stream(messages or [{"role": "user", "content": "hi"}], tools or []):
        if isinstance(item, TextDelta):
            deltas.append(item.text)
        else:
            turn = item
    await client._client.aclose()
    return deltas, turn


@pytest.mark.asyncio
async def test_tool_call_fragments_are_joined_by_index():
    """arguments 分片拼接 + id 只在首片出现，是最典型的流式 tool_call 形态。"""
    def handler(request):
        return httpx.Response(200, content=_sse(
            '{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","function":{"name":"write_file","arguments":"{\\"path\\""}}]}}]}',
            '{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":": \\"a.txt\\"}"}}]}}]}',
        ))

    _, turn = await _collect(_client(handler))
    assert len(turn.tool_calls) == 1
    call = turn.tool_calls[0]
    assert call.id == "call_1"
    assert call.name == "write_file"
    assert call.arguments == {"path": "a.txt"}


@pytest.mark.asyncio
async def test_parallel_tool_calls_without_index_do_not_merge():
    """上游省略 index 时，两个并行调用不能被拼成一个。

    原实现 raw_call.get("index", 0) 会把所有分片塞进 index 0，
    不同工具的 arguments 首尾相连（{"a":1}{"b":2}）→ JSON 解析失败 →
    静默降级成 {}，而且只剩最后一个工具名，第一个调用彻底消失。
    """
    def handler(request):
        return httpx.Response(200, content=_sse(
            '{"choices":[{"delta":{"tool_calls":[{"id":"c1","function":{"name":"list_files","arguments":"{\\"path\\": \\".\\"}"}}]}}]}',
            '{"choices":[{"delta":{"tool_calls":[{"id":"c2","function":{"name":"read_file","arguments":"{\\"path\\": \\"a.txt\\"}"}}]}}]}',
        ))

    _, turn = await _collect(_client(handler))
    assert [c.name for c in turn.tool_calls] == ["list_files", "read_file"]
    assert turn.tool_calls[0].arguments == {"path": "."}
    assert turn.tool_calls[1].arguments == {"path": "a.txt"}


@pytest.mark.asyncio
async def test_finish_reason_length_is_reported():
    def handler(request):
        return httpx.Response(200, content=_sse(
            '{"choices":[{"delta":{"content":"半截"},"finish_reason":"length"}]}',
        ))

    deltas, turn = await _collect(_client(handler))
    assert deltas == ["半截"]
    # 不记录的话，被 max_tokens 砍断的答案和正常完成完全无法区分。
    assert turn.finish_reason == "length"


@pytest.mark.asyncio
async def test_reasoning_content_is_used_when_body_empty():
    """reasoner 模型只给思考过程时，不能返回空回答。"""
    def handler(request):
        return httpx.Response(200, content=_sse(
            '{"choices":[{"delta":{"reasoning_content":"让我想想…"}}]}',
        ))

    deltas, turn = await _collect(_client(handler))
    assert deltas == []  # 思考过程不混进正文打字机
    assert turn.content == "让我想想…"


@pytest.mark.asyncio
async def test_reasoning_content_does_not_override_real_content():
    def handler(request):
        return httpx.Response(200, content=_sse(
            '{"choices":[{"delta":{"reasoning_content":"思考"}}]}',
            '{"choices":[{"delta":{"content":"答案"}}]}',
        ))

    _, turn = await _collect(_client(handler))
    assert turn.content == "答案"


@pytest.mark.asyncio
async def test_stream_retries_on_5xx_before_emitting():
    """流式路径此前零重试，而工作台默认走流式——LLM_MAX_RETRIES 形同虚设。"""
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(503, text="upstream busy")
        return httpx.Response(200, content=_sse('{"choices":[{"delta":{"content":"好"}}]}'))

    client = _client(handler, max_retries=2)
    client._sleep_before_retry = lambda *a, **k: _noop()  # 别真睡
    deltas, turn = await _collect(client)
    assert len(attempts) == 2
    assert turn.content == "好"


async def _noop():
    return None


@pytest.mark.asyncio
async def test_stream_gives_up_after_retries():
    def handler(request):
        return httpx.Response(503, text="always down")

    client = _client(handler, max_retries=1)
    client._sleep_before_retry = lambda *a, **k: _noop()
    with pytest.raises(LlmError):
        await _collect(client)


@pytest.mark.asyncio
async def test_multiple_data_lines_in_one_chunk():
    """一个 TCP chunk 里塞多条 data:，httpx 的 aiter_lines 要能正确拆开。"""
    def handler(request):
        return httpx.Response(200, content=_sse(
            '{"choices":[{"delta":{"content":"A"}}]}',
            '{"choices":[{"delta":{"content":"B"}}]}',
            '{"choices":[{"delta":{"content":"C"}}]}',
        ))

    deltas, turn = await _collect(_client(handler))
    assert deltas == ["A", "B", "C"]
    assert turn.content == "ABC"


@pytest.mark.asyncio
async def test_malformed_tool_arguments_degrade_to_empty_dict():
    def handler(request):
        return httpx.Response(200, content=_sse(
            '{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"f","arguments":"{not json"}}]}}]}',
        ))

    _, turn = await _collect(_client(handler))
    # 不中断整轮：坏参数降级成空 dict，由工具层报错给模型看。
    assert turn.tool_calls[0].arguments == {}
    assert turn.tool_calls[0].name == "f"
