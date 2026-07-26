"""token 用量统计。

skill 清单全量注入后 system prompt 涨到约 4k token 且每轮都发，team 模式还会
乘以步数——消耗必须能被看见，否则没法判断这个取舍值不值。
"""

import asyncio
import json

import httpx
import pytest

from app.agent import StreamStart
from app.audit import AuditLogger
from app.llm.base import AssistantTurn, TextDelta, ToolCall, Usage
from app.llm.openai_compatible import OpenAICompatibleClient
from app.llm.providers import ModelRef
from app.orchestrator import Orchestrator
from app.sessions import SessionStore
from app.skills.registry import SkillRegistry
from fakes import FakeBrowser, FakeNode, FakeSandbox


# --- Usage 本身 -------------------------------------------------------------


def test_usage_addition_and_total():
    total = Usage(10, 2, calls=1) + Usage(5, 3, calls=1)

    assert total == Usage(15, 5, calls=2)
    assert total.total_tokens == 20


def test_usage_from_payload_handles_junk():
    assert Usage.from_payload(None) == Usage()
    assert Usage.from_payload({"prompt_tokens": "x", "completion_tokens": -5}) == Usage(calls=1)
    assert Usage.from_payload({"prompt_tokens": 7}) == Usage(7, 0, calls=1)


def test_usage_subtraction_clamps_at_zero():
    assert Usage(15, 5, calls=2) - Usage(10, 2, calls=1) == Usage(5, 3, calls=1)
    # 累计值只增不减；真出现负数说明快照取错了，归零而不是显示负数。
    assert Usage(1, 1, calls=1) - Usage(9, 9, calls=9) == Usage(0, 0, calls=0)


def test_usage_to_dict_exposes_total():
    assert Usage(3, 4, calls=1).to_dict() == {
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
        "calls": 1,
    }


# --- 客户端解析 -------------------------------------------------------------


def _ref(**kwargs) -> ModelRef:
    defaults = dict(
        provider="fake",
        id="fake-1",
        name="fake-1",
        base_url="https://example.invalid/v1",
        api="openai-completions",
        api_key="k",
    )
    defaults.update(kwargs)
    return ModelRef(**defaults)


def _client(handler, **ref_kwargs) -> OpenAICompatibleClient:
    client = OpenAICompatibleClient(_ref(**ref_kwargs))
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def _sse(*chunks: str) -> str:
    return "".join(f"data: {chunk}\n\n" for chunk in chunks) + "data: [DONE]\n\n"


def test_stream_collects_usage_from_final_chunk():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            text=_sse(
                '{"choices":[{"delta":{"content":"你好"}}]}',
                '{"choices":[],"usage":{"prompt_tokens":4001,"completion_tokens":120}}',
            ),
        )

    async def go():
        client = _client(handler)
        items = [chunk async for chunk in client.respond_stream([{"role": "user", "content": "hi"}], [])]
        await client.close()
        return items

    items = asyncio.run(go())

    # 请求里带了 include_usage，否则上游不会回 usage
    assert seen["stream_options"] == {"include_usage": True}
    turn = items[-1]
    assert isinstance(turn, AssistantTurn)
    assert turn.usage == Usage(4001, 120, calls=1)
    assert turn.content == "你好"


def test_stream_usage_can_be_disabled_per_provider():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, text=_sse('{"choices":[{"delta":{"content":"x"}}]}'))

    async def go():
        client = _client(handler, supports_stream_usage=False)
        items = [chunk async for chunk in client.respond_stream([{"role": "user", "content": "hi"}], [])]
        await client.close()
        return items

    items = asyncio.run(go())

    assert "stream_options" not in seen
    # 上游没上报，但确实调用过一次
    assert items[-1].usage == Usage(calls=1)


def test_non_stream_and_complete_collect_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 5},
            },
        )

    async def go():
        client = _client(handler)
        turn = await client.respond([{"role": "user", "content": "hi"}], [])
        text, usage = await client.complete_with_usage("sys", "user")
        plain = await client.complete("sys", "user")
        await client.close()
        return turn, text, usage, plain

    turn, text, usage, plain = asyncio.run(go())

    assert turn.usage == Usage(30, 5, calls=1)
    assert (text, plain) == ("ok", "ok")
    assert usage == Usage(30, 5, calls=1)


# --- 会话累计 ---------------------------------------------------------------


def test_session_accumulates_usage_across_calls():
    async def go():
        store = SessionStore()
        session = await store.get_or_create(None, "标题")
        await store.add_usage(session, Usage(100, 10, calls=1))
        await store.add_usage(session, Usage(200, 20, calls=1))
        await store.add_usage(session, Usage())  # 空的不该改变计数
        return session, await store.list()

    session, summaries = asyncio.run(go())

    assert session.usage == Usage(300, 30, calls=2)
    assert summaries[0].usage == {
        "prompt_tokens": 300,
        "completion_tokens": 30,
        "total_tokens": 330,
        "calls": 2,
    }


# --- 端到端聚合 -------------------------------------------------------------


class UsageModel:
    """每轮上报固定消耗；complete 走 complete_with_usage。"""

    def __init__(self):
        self.turns = 0

    async def complete_with_usage(self, system, user):
        if "拆成" in system:
            return json.dumps({"steps": ["一", "二"]}, ensure_ascii=False), Usage(50, 10, calls=1)
        return "汇总", Usage(70, 15, calls=1)

    async def complete(self, system, user):
        text, _ = await self.complete_with_usage(system, user)
        return text

    async def respond_stream(self, messages, tools):
        self.turns += 1
        if self.turns == 1:
            yield AssistantTurn(
                tool_calls=[ToolCall("t1", "list_files", {"path": "."})],
                usage=Usage(1000, 40, calls=1),
            )
            return
        yield TextDelta(text="好")
        yield AssistantTurn(content="好", usage=Usage(1200, 25, calls=1))


def _runner(tmp_path):
    from app.agent import AgentRunner
    from app.tools.registry import ToolRegistry

    sessions = SessionStore()
    runner = AgentRunner(
        ToolRegistry(FakeSandbox(), FakeNode(), FakeBrowser()),
        SkillRegistry((tmp_path,)),
        sessions,
        AuditLogger(tmp_path / "audit.jsonl"),
        max_rounds=4,
    )
    return runner, sessions


@pytest.mark.asyncio
async def test_single_run_reports_usage_in_result_payload(tmp_path):
    runner, sessions = _runner(tmp_path)
    model = UsageModel()

    events = []
    async for item in runner.run_stream("列出文件", model, None, provider="p", model_id="m"):
        events.append(item)

    result = events[-1]
    # 两轮调用：1000+40 和 1200+25
    assert result.payload["usage"] == {
        "prompt_tokens": 2200,
        "completion_tokens": 65,
        "total_tokens": 2265,
        "calls": 2,
    }
    summaries = await sessions.list()
    assert summaries[0].usage["total_tokens"] == 2265


@pytest.mark.asyncio
async def test_team_run_includes_planner_and_step_usage(tmp_path):
    runner, sessions = _runner(tmp_path)
    orchestrator = Orchestrator(runner, sessions, max_steps=4)
    model = UsageModel()

    events = []
    async for item in orchestrator.run_stream(
        "做两件事", model, None, "team", provider="p", model_id="m"
    ):
        events.append(item)

    final = events[-1]
    # 规划 50+10，汇总 70+15
    assert final.payload["planner_usage"] == {
        "prompt_tokens": 120,
        "completion_tokens": 25,
        "total_tokens": 145,
        "calls": 2,
    }
    # 总量 = 规划 + 汇总 + 各子步骤，且与会话累计一致
    summaries = await sessions.list()
    assert final.payload["usage"] == summaries[0].usage
    assert final.payload["usage"]["total_tokens"] > final.payload["planner_usage"]["total_tokens"]
    assert final.payload["usage"]["calls"] >= 3


@pytest.mark.asyncio
async def test_team_usage_on_existing_session_excludes_earlier_rounds(tmp_path):
    """在【已有会话】上跑 team，本次消耗不能把之前轮次的算进来。

    之前 team 直接上报 parent.usage（会话累计），新会话下恰好等于本次消耗，
    所以上面那个用例（session_id=None）测不出来；换成已有会话就会虚报。
    """
    runner, sessions = _runner(tmp_path)
    orchestrator = Orchestrator(runner, sessions, max_steps=4)

    # 第 1 轮：先在会话里攒下一些消耗。
    session_id = None
    async for item in orchestrator.run_stream(
        "第一轮", UsageModel(), None, "single", provider="p", model_id="m"
    ):
        if isinstance(item, StreamStart):
            session_id = item.session_id
    before = (await sessions.get(session_id)).usage.to_dict()
    assert before["total_tokens"] > 0  # 前置条件：确实攒下了消耗

    # 第 2 轮：同一会话上跑 team。
    final = None
    async for item in orchestrator.run_stream(
        "第二轮", UsageModel(), session_id, "team", provider="p", model_id="m"
    ):
        if getattr(item, "type", None) == "result" and getattr(item, "name", None) == "answer":
            final = item

    after = (await sessions.get(session_id)).usage.to_dict()
    actual = {key: after[key] - before[key] for key in after}

    assert final.payload["usage"] == actual
    assert final.payload["usage"] != after  # 不再是会话累计值
