import json
import asyncio

from app.agent import AgentRunner, StreamStart
from app.audit import AuditLogger
from app.llm.base import AssistantTurn, TextDelta, ToolCall
from app.models import AgentEvent
from app.sessions import SessionStore
from app.skills.registry import SkillRegistry
from app.tools.registry import RegisteredTool, ToolRegistry


class FakeSandbox:
    base_url = ""

    async def list_files(self, path="."):
        return {"items": [{"name": "sample.txt", "type": "file"}], "cwd": path}

    async def read_file(self, path):
        return {"path": path, "content": "hello"}

    async def write_file(self, path, content):
        return {"path": path, "size": len(content)}

    async def execute_python(self, code, session_id=None):
        return {"output": "ok", "error": "", "exit_code": 0}

    async def lint_python(self, code):
        return {"errors": [], "warnings": []}

    async def metrics(self):
        return {"cpu_percent": 0}

    async def browser_info(self):
        return {"data": {}}


class FakeNode:
    base_url = ""


class FakeBrowser:
    enabled = False


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
