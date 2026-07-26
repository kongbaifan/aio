"""team 模式的回归测试。

改造前 team 模式有两个问题：orchestrator 调 runner.run() 时不传 confirmer，
破坏性工具一律被判为拒绝；每个子步骤用独立会话，步骤之间没有上下文。
"""

import json

import pytest

from app.agent import AgentRunner, ConfirmRequest, StreamStart
from app.audit import AuditLogger
from app.llm.base import AssistantTurn, TextDelta, ToolCall
from app.models import AgentEvent
from app.orchestrator import Orchestrator
from app.sessions import SessionStore
from app.skills.registry import SkillRegistry
from app.tools.registry import ToolRegistry
from fakes import FakeBrowser, FakeNode, FakeSandbox


class TeamModel:
    """规划成两步；第一步请求写文件，第二步直接作答。"""

    def __init__(self):
        self.turns = 0
        self.seen: list[list[dict]] = []

    async def complete(self, system: str, user: str) -> str:
        if "拆成" in system:
            return json.dumps({"steps": ["建立数据文件", "核对结果"]}, ensure_ascii=False)
        return "汇总结果"

    async def respond_stream(self, messages, tools):
        self.turns += 1
        self.seen.append(list(messages))
        if self.turns == 1:
            yield AssistantTurn(
                tool_calls=[ToolCall("t1", "write_file", {"path": "a.txt", "content": "x"})]
            )
            return
        text = "第一步完成" if self.turns == 2 else "第二步完成"
        yield TextDelta(text=text)
        yield AssistantTurn(content=text)


def _orchestrator(tmp_path, sandbox, *, require_confirmation=True):
    tools = ToolRegistry(sandbox, FakeNode(), FakeBrowser())
    sessions = SessionStore()
    runner = AgentRunner(
        tools,
        SkillRegistry((tmp_path,)),
        sessions,
        AuditLogger(tmp_path / "audit.jsonl"),
        max_rounds=4,
        require_confirmation=require_confirmation,
    )
    return Orchestrator(runner, sessions, max_steps=4), sessions


async def _collect(orchestrator, model, confirmer=None):
    items = []
    async for item in orchestrator.run_stream(
        "做两件事", model, None, "team", provider="p", model_id="m", confirmer=confirmer
    ):
        items.append(item)
    return items


@pytest.mark.asyncio
async def test_team_mode_asks_for_confirmation_instead_of_refusing(tmp_path):
    sandbox = FakeSandbox()
    orchestrator, _ = _orchestrator(tmp_path, sandbox)
    asked: list[str] = []

    async def approve(req: ConfirmRequest) -> bool:
        asked.append(req.tool)
        return True

    items = await _collect(orchestrator, TeamModel(), approve)

    # 确认请求既外发给了上层（SSE 侧要据此发帧），也真的被询问了
    assert asked == ["write_file"]
    assert any(isinstance(item, ConfirmRequest) for item in items)
    assert sandbox.written == [("a.txt", "x")]


@pytest.mark.asyncio
async def test_team_mode_without_confirmer_still_blocks(tmp_path):
    sandbox = FakeSandbox()
    orchestrator, _ = _orchestrator(tmp_path, sandbox)

    items = await _collect(orchestrator, TeamModel(), None)

    assert sandbox.written == []
    assert any(getattr(item, "status", None) == "blocked" for item in items)


@pytest.mark.asyncio
async def test_team_steps_share_one_session(tmp_path):
    sandbox = FakeSandbox()
    orchestrator, sessions = _orchestrator(tmp_path, sandbox)
    model = TeamModel()

    async def approve(req):
        return True

    items = await _collect(orchestrator, model, approve)

    start = next(item for item in items if isinstance(item, StreamStart))
    # 只有一个会话：父会话，子步骤复用它
    summaries = await sessions.list()
    assert [item.id for item in summaries] == [start.session_id]

    # 第二步能看到第一步的子任务和答案
    last_messages = model.seen[-1]
    rendered = json.dumps(last_messages, ensure_ascii=False)
    assert "建立数据文件" in rendered
    assert "第一步完成" in rendered


@pytest.mark.asyncio
async def test_step_results_are_named_and_final_answer_last(tmp_path):
    sandbox = FakeSandbox()
    orchestrator, _ = _orchestrator(tmp_path, sandbox)

    async def approve(req):
        return True

    items = await _collect(orchestrator, TeamModel(), approve)
    events = [item for item in items if isinstance(item, AgentEvent)]
    names = [event.name for event in events]

    assert "step-1" in names and "step-2" in names
    # 只有最终汇总叫 answer，SSE 侧据此判断哪个才是最终回答
    assert names.count("answer") == 1
    assert names[-1] == "answer"
    assert events[-1].detail == "汇总结果"
    assert events[-1].type == "result"


@pytest.mark.asyncio
async def test_failed_step_reports_error_status_but_result_type(tmp_path):
    """子步骤失败时 status=error，但 type 仍是 result——type=error 留给整体失败。"""

    class FailingModel(TeamModel):
        async def respond_stream(self, messages, tools):
            self.turns += 1
            self.seen.append(list(messages))
            raise RuntimeError("上游 500")
            yield  # 不可达；有 yield 才是异步生成器，否则测的是"返回协程"而非"调用抛错"

    sandbox = FakeSandbox()
    orchestrator, _ = _orchestrator(tmp_path, sandbox)

    items = await _collect(orchestrator, FailingModel(), None)
    events = [item for item in items if isinstance(item, AgentEvent)]
    steps = [event for event in events if event.name.startswith("step-")]

    assert steps and all(event.type == "result" for event in steps)
    assert all(event.status == "error" for event in steps)
    # 整体仍然收敛到一个 answer，不会把流卡死
    assert events[-1].name == "answer"


def test_non_stream_run_still_returns_quadruple(tmp_path):
    """orchestrator.run() 的签名被 /api/chat 依赖，保持向后兼容。"""
    import asyncio

    sandbox = FakeSandbox()
    orchestrator, _ = _orchestrator(tmp_path, sandbox)

    answer, session_id, events, matched = asyncio.run(
        orchestrator.run("做两件事", TeamModel(), None, "team", provider="p", model_id="m")
    )

    assert answer == "汇总结果"
    assert session_id
    assert isinstance(events, list) and events
    assert matched == []
