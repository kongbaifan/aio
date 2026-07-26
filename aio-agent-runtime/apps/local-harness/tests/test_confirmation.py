"""人工确认（human-in-the-loop）链路的回归测试。

覆盖 agent 层的 confirmer 回调，以及 /api/chat/stream 的 confirm 帧 →
/api/chat/confirm 反向通道 → agent 恢复执行这条完整路径。
"""

import asyncio
import json

import httpx
import pytest

from app.agent import AgentRunner, ConfirmRequest
from app.audit import AuditLogger
from app.config import Settings
from app.llm.base import AssistantTurn, TextDelta, ToolCall
from app.main import ConfirmationRegistry, RuntimeContainer, create_app
from app.orchestrator import Orchestrator
from app.sessions import SessionStore
from app.skills.registry import SkillRegistry
from app.tools.registry import ToolRegistry
from fakes import FakeBrowser, FakeNode, FakeSandbox


class ScriptedModel:
    """先请求一次 write_file，再给出最终回答。"""

    def __init__(self):
        self._round = 0

    async def respond_stream(self, messages, tools):
        self._round += 1
        if self._round == 1:
            yield AssistantTurn(
                tool_calls=[ToolCall("t1", "write_file", {"path": "a.txt", "content": "x"})]
            )
            return
        yield TextDelta(text="已处理")
        yield AssistantTurn(content="已处理")


def _runner(tmp_path, sandbox):
    tools = ToolRegistry(sandbox, FakeNode(), FakeBrowser())
    return AgentRunner(
        tools,
        SkillRegistry((tmp_path,)),
        SessionStore(),
        AuditLogger(tmp_path / "audit.jsonl"),
        max_rounds=4,
        require_confirmation=True,
    )


def _collect(runner, confirmer):
    async def _go():
        items = []
        async for item in runner.run_stream(
            "写文件", ScriptedModel(), provider="p", model_id="m", confirmer=confirmer
        ):
            items.append(item)
        return items

    return asyncio.run(_go())


def test_confirmer_approval_executes_tool(tmp_path):
    sandbox = FakeSandbox()
    runner = _runner(tmp_path, sandbox)

    async def approve(req: ConfirmRequest) -> bool:
        assert req.tool == "write_file"
        assert req.arguments == {"path": "a.txt", "content": "x"}
        return True

    items = _collect(runner, approve)

    assert any(isinstance(item, ConfirmRequest) for item in items)
    assert sandbox.written == [("a.txt", "x")]
    statuses = [getattr(item, "status", None) for item in items]
    assert "success" in statuses
    assert "blocked" not in statuses


def test_confirmer_rejection_blocks_tool(tmp_path):
    sandbox = FakeSandbox()
    runner = _runner(tmp_path, sandbox)

    async def reject(req: ConfirmRequest) -> bool:
        return False

    items = _collect(runner, reject)

    assert sandbox.written == []
    blocked = [item for item in items if getattr(item, "status", None) == "blocked"]
    assert blocked and blocked[0].name == "write_file"
    assert "用户拒绝" in blocked[0].detail


def test_confirmer_exception_is_treated_as_rejection(tmp_path):
    sandbox = FakeSandbox()
    runner = _runner(tmp_path, sandbox)

    async def boom(req: ConfirmRequest) -> bool:
        raise RuntimeError("连接断开")

    items = _collect(runner, boom)

    assert sandbox.written == []
    assert any(getattr(item, "status", None) == "blocked" for item in items)


@pytest.mark.asyncio
async def test_registry_resolve_before_wait_is_not_lost():
    """已登记但尚未 wait 时到达的 resolve 不能丢。

    create 与 wait 分成两步就是为了这个：SSE 侧先登记，agent 侧稍后才挂上去，
    中间到达的用户决定会留在 Future 里。
    """
    registry = ConfirmationRegistry(timeout_seconds=1.0)
    future = await registry.create("abc")

    assert await registry.resolve("abc", True) is True
    assert await asyncio.wait_for(future, timeout=1) is True
    # 同一 id 重复 create：未完成时复用，已完成则重新登记，不会把决定串到下一次。
    assert await registry.create("abc") is not future
    registry.discard("abc")
    assert await registry.resolve("abc", True) is False


# --- 端到端：/api/chat/stream 的 confirm 帧与反向通道 ---------------------------


def _make_app(tmp_path, sandbox, monkeypatch):
    models_json = tmp_path / "models.json"
    models_json.write_text(
        json.dumps(
            {
                "default": {"provider": "fake", "model": "fake-1"},
                "providers": {
                    "fake": {
                        "baseUrl": "http://127.0.0.1:9",
                        "api": "openai-completions",
                        "apiKey": "test-key",
                        "models": [{"id": "fake-1", "name": "fake-1", "maxTokens": 128}],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESS_MODELS_JSON", str(models_json))
    monkeypatch.setenv("HARNESS_REQUIRE_TOOL_CONFIRMATION", "1")
    monkeypatch.setenv("HARNESS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("HARNESS_SKILL_ROOTS", str(tmp_path))
    monkeypatch.delenv("HARNESS_ENV_FILE", raising=False)
    monkeypatch.delenv("HARNESS_TOKEN", raising=False)

    settings = Settings.from_env()
    app = create_app(settings)
    # 手动装配 runtime，跳过 lifespan，并把外部依赖换成 fake。
    container = RuntimeContainer(settings)
    container.sandbox = sandbox
    container.node = FakeNode()
    container.tools = ToolRegistry(sandbox, container.node, FakeBrowser())
    container.runner = AgentRunner(
        container.tools,
        container.skills,
        container.sessions,
        container.audit,
        settings.max_agent_rounds,
        True,
    )
    # orchestrator 在构造时就持有了 runner 引用，换了 runner 必须一起重建。
    container.orchestrator = Orchestrator(
        container.runner, container.sessions, settings.max_team_steps
    )
    container.models.get_client = lambda provider, model: ScriptedModel()
    app.state.runtime = container
    return app, container


async def _stream_frames(app, payload, on_frame):
    """手动驱动 ASGI 逐帧读 SSE。

    httpx 的 ASGITransport 会把响应整包缓冲，而这条流要等客户端回传确认才会继续，
    用它会直接死锁；所以这里自己收 http.response.body 消息。on_frame 在每帧到达时
    调用，可以在流尚未结束时通过 /api/chat/confirm 回传决定。
    """
    body = json.dumps(payload).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/chat/stream",
        "raw_path": b"/api/chat/stream",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 45678),
        "server": ("127.0.0.1", 8080),
    }
    consumed = False
    disconnected = asyncio.Event()

    async def receive():
        nonlocal consumed
        if not consumed:
            consumed = True
            return {"type": "http.request", "body": body, "more_body": False}
        # StreamingResponse 会并发监听断连，这里必须挂住而不是立刻返回 disconnect，
        # 否则流会被当成客户端断开而提前中止。流正常结束时该任务会被取消。
        await disconnected.wait()
        return {"type": "http.disconnect"}

    frames: list[dict] = []
    buffer = ""
    status: dict[str, int] = {}

    async def send(message):
        nonlocal buffer
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
        elif message["type"] == "http.response.body":
            buffer += message.get("body", b"").decode("utf-8")
            while "\n\n" in buffer:
                chunk, buffer = buffer.split("\n\n", 1)
                chunk = chunk.strip()
                if chunk.startswith("data: "):
                    frame = json.loads(chunk[6:])
                    frames.append(frame)
                    await on_frame(frame)

    await app(scope, receive, send)
    return status.get("code"), frames


async def _post_decision(app, confirmation_id, approved):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/chat/confirm",
            json={"confirmation_id": confirmation_id, "approved": approved},
        )
    return response


@pytest.mark.asyncio
async def test_stream_emits_confirm_frame_and_resumes_after_approval(tmp_path, monkeypatch):
    sandbox = FakeSandbox()
    app, container = _make_app(tmp_path, sandbox, monkeypatch)

    async def on_frame(frame):
        if frame.get("kind") == "confirm":
            response = await _post_decision(app, frame["confirmation_id"], True)
            assert response.status_code == 200

    status, frames = await asyncio.wait_for(
        _stream_frames(app, {"message": "写文件"}, on_frame), timeout=10
    )

    assert status == 200
    confirm = [f for f in frames if f.get("kind") == "confirm"]
    assert len(confirm) == 1
    assert confirm[0]["tool"] == "write_file"
    assert confirm[0]["arguments"] == {"path": "a.txt", "content": "x"}
    # 批准后工具真正执行，流走到 done。
    assert sandbox.written == [("a.txt", "x")]
    tool_events = [f["event"] for f in frames if f.get("kind") == "event" and f["event"]["type"] == "tool"]
    assert any(e["name"] == "write_file" and e["status"] == "success" for e in tool_events)
    assert frames[-1]["kind"] == "done"
    await container.models.close()


@pytest.mark.asyncio
async def test_stream_blocks_tool_after_rejection(tmp_path, monkeypatch):
    sandbox = FakeSandbox()
    app, container = _make_app(tmp_path, sandbox, monkeypatch)

    async def on_frame(frame):
        if frame.get("kind") == "confirm":
            await _post_decision(app, frame["confirmation_id"], False)

    status, frames = await asyncio.wait_for(
        _stream_frames(app, {"message": "写文件"}, on_frame), timeout=10
    )

    assert status == 200
    assert sandbox.written == []
    tool_events = [f["event"] for f in frames if f.get("kind") == "event" and f["event"]["type"] == "tool"]
    assert any(e["name"] == "write_file" and e["status"] == "blocked" for e in tool_events)
    assert frames[-1]["kind"] == "done"
    await container.models.close()


@pytest.mark.asyncio
async def test_confirm_endpoint_rejects_unknown_id(tmp_path, monkeypatch):
    sandbox = FakeSandbox()
    app, container = _make_app(tmp_path, sandbox, monkeypatch)

    response = await _post_decision(app, "no-such-id", True)

    assert response.status_code == 404
    await container.models.close()
