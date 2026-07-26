"""可选 MCP 入口：安装 requirements-mcp 后运行本文件即可暴露 Sandbox 工具。

注意这条通路和工作台（/api/chat/stream）是两套策略：工作台对 write_file /
execute_python 会弹人工确认并写审计日志，MCP 这边没有交互式确认的回传通道，
也不接 AuditLogger。为避免"同一份破坏性能力，一条管得严一条完全敞开"，这里：

- 默认（HARNESS_MCP_ALLOW_WRITE 未开）只暴露只读工具：list_files / read_file；
- 显式设 HARNESS_MCP_ALLOW_WRITE=true 才注册 write_file / execute_python，
  且每次调用都记一行审计，和工作台口径一致。

MCP 客户端（如 Claude Desktop）本身通常有自己的工具批准 UI，把"是否放开写"
交给部署者显式决定，而不是代码默默敞开。
"""

import os

from app.audit import AuditLogger
from app.clients.sandbox import SandboxClient
from app.config import Settings

try:
    from fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - 仅在未装 requirements-mcp 时触发
    raise SystemExit(
        "缺少 fastmcp，请先安装：pip install -r requirements-mcp.txt"
    ) from exc


def _bool_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


mcp = FastMCP("AIO Local Harness")
settings = Settings.from_env()
_allow_write = _bool_env("HARNESS_MCP_ALLOW_WRITE")
_audit = AuditLogger(
    settings.audit_log_path,
    max_bytes=settings.audit_max_bytes,
    backup_count=settings.audit_backup_count,
)


async def _call(method: str, *args):
    client = SandboxClient(settings.sandbox_url, settings.sandbox_token)
    try:
        return await getattr(client, method)(*args)
    finally:
        await client.close()


async def _call_audited(method: str, *args):
    """破坏性工具专用：调用前后各记一行审计，和工作台口径对齐。"""
    await _audit.write("mcp.tool.call", {"source": "mcp", "tool": method})
    try:
        result = await _call(method, *args)
    except Exception as exc:
        await _audit.write(
            "mcp.tool.error", {"source": "mcp", "tool": method, "error": str(exc)}
        )
        raise
    await _audit.write("mcp.tool.done", {"source": "mcp", "tool": method})
    return result


@mcp.tool
async def list_files(path: str = ".") -> dict:
    """列出 Sandbox workspace 内的文件。"""
    return await _call("list_files", path)


@mcp.tool
async def read_file(path: str) -> dict:
    """读取 Sandbox workspace 内的文本文件。"""
    return await _call("read_file", path)


if _allow_write:

    @mcp.tool
    async def write_file(path: str, content: str) -> dict:
        """写入 Sandbox workspace 内的文本文件（破坏性，已记审计）。"""
        return await _call_audited("write_file", path, content)

    @mcp.tool
    async def execute_python(code: str) -> dict:
        """执行 Python 代码并返回结果（破坏性，已记审计）。"""
        return await _call_audited("execute_python", code)


if __name__ == "__main__":
    mcp.run()
