import json
import asyncio

from app.agent import AgentRunner, StreamStart
from app.audit import AuditLogger
from app.llm.base import AssistantTurn, TextDelta, ToolCall
from app.models import AgentEvent
from app.sessions import SessionStore
from app.skills.registry import SkillRegistry
from app.tools.registry import RegisteredTool, ToolRegistry
from fakes import FakeBrowser, FakeNode, FakeSandbox


class ScriptedModel:
    """测试用：按轮次返回预设 tool_calls / 最终回答。"""

    def __init__(self, turns: list[AssistantTurn]):
        self._turns = list(turns)
        self._index = 0

    async def respond(self, messages, tools) -> AssistantTurn:
        if self._index >= len(self._turns):
            return AssistantTurn(content="完成")
        turn = self._turns[self._index]
        self._index += 1
        return turn

    async def respond_stream(self, messages, tools):
        if self._index >= len(self._turns):
            yield AssistantTurn(content="完成")
            return
        turn = self._turns[self._index]
        self._index += 1
        # 先把最终答案文本按字符切成增量（模拟打字机），再给出完整 turn。
        if turn.content:
            for char in turn.content:
                yield TextDelta(text=char)
        yield turn

    async def complete(self, system: str, user: str) -> str:
        return "{}"


def test_agent_calls_tools(tmp_path):
    sandbox = FakeSandbox()
    tools = ToolRegistry(sandbox, FakeNode(), FakeBrowser())
    skills = SkillRegistry((tmp_path,))
    runner = AgentRunner(
        tools,
        skills,
        SessionStore(),
        AuditLogger(tmp_path / "audit.jsonl"),
        max_rounds=4,
    )
    model = ScriptedModel(
        [
            AssistantTurn(tool_calls=[ToolCall("t1", "list_files", {"path": "."})]),
            AssistantTurn(content="已列出文件"),
        ]
    )

    answer, session_id, events, matched = asyncio.run(
        runner.run("列出文件", model, provider="deepseek", model_id="deepseek-chat")
    )

    assert session_id
    assert "已列出文件" in answer
    assert any(event.name == "list_files" and event.status == "success" for event in events)
    assert matched == []


def test_require_confirmation_blocks_destructive_tools(tmp_path):
    sandbox = FakeSandbox()
    tools = ToolRegistry(sandbox, FakeNode(), FakeBrowser())
    skills = SkillRegistry((tmp_path,))
    runner = AgentRunner(
        tools,
        skills,
        SessionStore(),
        AuditLogger(tmp_path / "audit.jsonl"),
        max_rounds=4,
        require_confirmation=True,
    )
    model = ScriptedModel(
        [
            AssistantTurn(
                tool_calls=[ToolCall("t1", "write_file", {"path": "a.txt", "content": "x"})]
            ),
            AssistantTurn(content="已按策略停止破坏性操作"),
        ]
    )

    answer, session_id, events, matched = asyncio.run(
        runner.run("写文件", model, provider="deepseek", model_id="deepseek-chat")
    )

    assert session_id
    assert any(event.status == "blocked" and event.name == "write_file" for event in events)
    assert not any(event.name == "write_file" and event.status == "success" for event in events)


def test_tool_output_is_truncated_before_entering_model_context(tmp_path):
    """超长工具结果不能全量进 messages，且必须告诉模型「这里被截断了」。

    sandbox 侧 read_file 允许 10MB，之前这些字符会原样进上下文并留在里面
    参与之后的每一轮，长会话必然撑爆 context。
    """
    huge = "内容" * 20000  # 40000 字符
    sandbox = FakeSandbox()

    async def _read_file(path):
        return {"path": path, "content": huge}

    sandbox.read_file = _read_file
    tools = ToolRegistry(sandbox, FakeNode(), FakeBrowser())
    captured: list[dict] = []

    class CapturingModel(ScriptedModel):
        async def respond_stream(self, messages, tools):
            captured.append([dict(item) for item in messages])
            async for chunk in super().respond_stream(messages, tools):
                yield chunk

    runner = AgentRunner(
        tools,
        SkillRegistry((tmp_path,)),
        SessionStore(),
        AuditLogger(tmp_path / "audit.jsonl"),
        max_rounds=4,
        tool_context_limit=8000,
    )
    model = CapturingModel(
        [
            AssistantTurn(tool_calls=[ToolCall("t1", "read_file", {"path": "big.txt"})]),
            AssistantTurn(content="读完了"),
        ]
    )

    asyncio.run(runner.run("读大文件", model))

    # 第二轮请求里那条 tool 消息就是进了上下文的那份。
    tool_messages = [item for item in captured[-1] if item.get("role") == "tool"]
    assert len(tool_messages) == 1
    content = tool_messages[0]["content"]
    assert len(content) < len(huge)
    assert len(content) < 8500  # 8000 上限 + 截断说明
    assert "输出已截断" in content


def test_model_failure_reports_usage_so_far(tmp_path):
    """模型中途失败时，前几轮已经花掉的 token 不能跟着丢。

    error 事件的 payload 之前是空的，上层取不到 run_usage，
    整次请求的消耗在界面上显示为 0。
    """
    from app.llm.base import Usage

    class FailingModel(ScriptedModel):
        async def respond_stream(self, messages, tools):
            if self._index == 0:
                self._index += 1
                yield AssistantTurn(
                    tool_calls=[ToolCall("t1", "list_files", {"path": "."})],
                    usage=Usage(500, 20, calls=1),
                )
                return
            raise RuntimeError("上游 500")

    runner = AgentRunner(
        ToolRegistry(FakeSandbox(), FakeNode(), FakeBrowser()),
        SkillRegistry((tmp_path,)),
        SessionStore(),
        AuditLogger(tmp_path / "audit.jsonl"),
        max_rounds=4,
    )

    events = []

    async def go():
        async for item in runner.run_stream("列出文件", FailingModel([])):
            events.append(item)

    asyncio.run(go())

    error = events[-1]
    assert error.type == "error"
    usage = error.payload.get("usage") or {}
    # 第一轮的 500+20 必须还在，另加中断那一次的 calls。
    assert usage.get("prompt_tokens") == 500
    assert usage.get("completion_tokens") == 20
    assert usage.get("calls") == 2


def test_run_stream_emits_start_then_events_then_result(tmp_path):
    sandbox = FakeSandbox()
    tools = ToolRegistry(sandbox, FakeNode(), FakeBrowser())
    skills = SkillRegistry((tmp_path,))
    runner = AgentRunner(
        tools,
        skills,
        SessionStore(),
        AuditLogger(tmp_path / "audit.jsonl"),
        max_rounds=4,
    )
    model = ScriptedModel(
        [
            AssistantTurn(tool_calls=[ToolCall("t1", "list_files", {"path": "."})]),
            AssistantTurn(content="已列出文件"),
        ]
    )

    async def _collect():
        items = []
        async for item in runner.run_stream(
            "列出文件", model, provider="deepseek", model_id="deepseek-chat"
        ):
            items.append(item)
        return items

    items = asyncio.run(_collect())

    # 首个信号必须是 StreamStart，且带会话 id。
    assert isinstance(items[0], StreamStart)
    assert items[0].session_id
    # 其余都是 AgentEvent，且工具与最终答案都被推送。
    events = [item for item in items[1:] if isinstance(item, AgentEvent)]
    assert any(e.name == "list_files" and e.status == "running" for e in events)
    assert any(e.name == "list_files" and e.status == "success" for e in events)
    # 最后一个事件是最终答案。
    assert events[-1].type == "result"
    assert "已列出文件" in events[-1].detail


def test_registered_tool_schema_is_openai_compatible():
    tool = RegisteredTool("sample", "说明", {"type": "object"}, lambda args: None)
    schema = tool.schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "sample"
    assert json.loads(json.dumps(schema, ensure_ascii=False))["function"]["description"] == "说明"
