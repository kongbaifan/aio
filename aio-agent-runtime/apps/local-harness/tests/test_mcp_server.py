"""MCP 入口的写工具策略。

MCP 这条通路没有交互式确认的回传通道，不能像工作台那样弹确认框。
为避免"同一份破坏性能力，一条管得严一条完全敞开"，写工具默认不暴露，
显式开 HARNESS_MCP_ALLOW_WRITE 才注册，且每次调用记审计。
"""

import importlib
import sys

import pytest

pytest.importorskip("fastmcp")


def _load_mcp(monkeypatch, tmp_path, *, allow_write: bool):
    monkeypatch.setenv("HARNESS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("HARNESS_SESSION_DB", str(tmp_path / "s.db"))
    if allow_write:
        monkeypatch.setenv("HARNESS_MCP_ALLOW_WRITE", "true")
    else:
        monkeypatch.delenv("HARNESS_MCP_ALLOW_WRITE", raising=False)
    sys.modules.pop("mcp_server", None)
    return importlib.import_module("mcp_server")


async def _tool_names(module) -> set[str]:
    tools = await module.mcp.list_tools()
    return {tool.name for tool in tools}


@pytest.mark.asyncio
async def test_write_tools_hidden_by_default(monkeypatch, tmp_path):
    module = _load_mcp(monkeypatch, tmp_path, allow_write=False)
    names = await _tool_names(module)

    assert "list_files" in names
    assert "read_file" in names
    # 默认不暴露破坏性工具。
    assert "write_file" not in names
    assert "execute_python" not in names


@pytest.mark.asyncio
async def test_write_tools_appear_when_opted_in(monkeypatch, tmp_path):
    module = _load_mcp(monkeypatch, tmp_path, allow_write=True)
    names = await _tool_names(module)

    assert "write_file" in names
    assert "execute_python" in names


@pytest.mark.asyncio
async def test_write_tool_writes_audit(monkeypatch, tmp_path):
    module = _load_mcp(monkeypatch, tmp_path, allow_write=True)
    audit_path = tmp_path / "audit.jsonl"

    calls = []

    class FakeSandbox:
        def __init__(self, *a, **k):
            pass

        async def write_file(self, path, content):
            calls.append((path, content))
            return {"path": path, "size": len(content)}

        async def close(self):
            pass

    monkeypatch.setattr(module, "SandboxClient", FakeSandbox)

    result = await module._call_audited("write_file", "a.txt", "hi")
    assert result["path"] == "a.txt"
    assert calls == [("a.txt", "hi")]

    # 审计里应能看到这次 MCP 调用。
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    events = [line for line in lines if "mcp.tool" in line]
    assert any("mcp.tool.call" in line for line in events)
    assert any("mcp.tool.done" in line for line in events)


@pytest.fixture(autouse=True)
def _cleanup_module():
    yield
    sys.modules.pop("mcp_server", None)
