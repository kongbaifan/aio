import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..clients.browser import BrowserCliClient
from ..clients.node_repl import NodeReplClient
from ..clients.sandbox import SandboxClient
from ..skills.registry import SkillRegistry


ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

# 浏览器只允许打开 http/https，且拒绝以 "-" 开头的值，避免被下游 CLI 当作选项解析。
_ALLOWED_URL_SCHEMES = ("http://", "https://")


logger = logging.getLogger(__name__)


def _viewport_env(primary: str, fallback: str, default: int) -> int:
    """读视口尺寸环境变量；填了非数字就退回默认值。

    原来是在 handler 里直接 int()，填个 "abc" 会抛 ValueError——虽然会被
    agent 的 except 兜住转成工具错误，但模型看到的是
    "invalid literal for int()"，对它毫无指导性。
    """
    raw = (os.environ.get(primary) or os.environ.get(fallback) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("视口环境变量 %s/%s 不是整数：%r，改用默认值 %s", primary, fallback, raw, default)
        return default


def _validate_url(url: Any) -> str:
    if not isinstance(url, str):
        raise ValueError("url must be a string")
    cleaned = url.strip()
    if not cleaned.lower().startswith(_ALLOWED_URL_SCHEMES):
        raise ValueError("url must start with http:// or https://")
    return cleaned


@dataclass
class RegisteredTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    requires_confirmation: bool = False

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """集中定义模型可见 schema 和实际 handler，防止两处契约漂移。"""

    def __init__(
        self,
        sandbox: SandboxClient,
        node: NodeReplClient,
        browser: BrowserCliClient,
        skills: SkillRegistry | None = None,
    ):
        self.sandbox = sandbox
        self.node = node
        self.browser = browser
        self.skills = skills
        self._tools: dict[str, RegisteredTool] = {}
        self._register_defaults()

    def register(self, tool: RegisteredTool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def requires_confirmation(self, name: str) -> bool:
        """该工具是否属于需要确认的破坏性/执行类操作。"""
        tool = self._tools.get(name)
        return bool(tool and tool.requires_confirmation)

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        result = await tool.handler(arguments)
        return json.dumps(result, ensure_ascii=False, default=str)

    def _register_defaults(self) -> None:
        object_schema = {"type": "object", "additionalProperties": False}
        self.register(
            RegisteredTool(
                "list_files",
                "列出 Sandbox workspace 中指定目录的文件。",
                {**object_schema, "properties": {"path": {"type": "string"}}},
                # 用 or 而不是 get 的默认值：模型传 {"path": ""} 时键是存在的，
                # 默认值不生效，空串会一路透传到 safe_path 换来一个 400。
                # 而同一个 registry 里 list_skill_files 的描述明确写着「留空表示
                # 根目录」，两个列目录工具语义相反，模型很容易踩。
                lambda args: self.sandbox.list_files(args.get("path") or "."),
            )
        )
        self.register(
            RegisteredTool(
                "read_file",
                "读取 Sandbox workspace 内的 UTF-8 文本文件。",
                {
                    **object_schema,
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                lambda args: self.sandbox.read_file(args["path"]),
            )
        )
        self.register(
            RegisteredTool(
                "write_file",
                "在 Sandbox workspace 内创建或覆盖 UTF-8 文本文件。",
                {
                    **object_schema,
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
                lambda args: self.sandbox.write_file(args["path"], args["content"]),
                requires_confirmation=True,
            )
        )
        self.register(
            RegisteredTool(
                "execute_python",
                "在隔离 workspace 中执行 Python 代码并返回 stdout、stderr 和退出码。",
                {
                    **object_schema,
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                },
                lambda args: self.sandbox.execute_python(args["code"]),
                requires_confirmation=True,
            )
        )
        self.register(
            RegisteredTool(
                "lint_python",
                "只解析 Python 代码并返回语法错误，不执行代码。",
                {
                    **object_schema,
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                },
                lambda args: self.sandbox.lint_python(args["code"]),
            )
        )
        self.register(
            RegisteredTool(
                "get_metrics",
                "读取 Sandbox 的 CPU、内存、磁盘和会话指标。",
                {**object_schema, "properties": {}},
                lambda args: self.sandbox.metrics(),
            )
        )
        self.register(
            RegisteredTool(
                "get_browser_info",
                "读取浏览器连接和视口信息。",
                {**object_schema, "properties": {}},
                lambda args: self.sandbox.browser_info(),
            )
        )
        if self.skills is not None:
            # skill 正文和 references 在项目的 skills/ 目录里，不在 sandbox workspace，
            # read_file 够不着。SKILL.md 又常常要求先读某个 references 文档，
            # 所以单开一个只读入口，路径边界由 SkillRegistry 约束。
            self.register(
                RegisteredTool(
                    "read_skill",
                    "读取 skill 目录内的文档（SKILL.md 或其 references）。"
                    "路径相对 skill 根，例如 business/lark-minutes/SKILL.md。",
                    {
                        **object_schema,
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                    lambda args: asyncio.to_thread(self.skills.read, args["path"]),
                )
            )
            self.register(
                RegisteredTool(
                    "list_skill_files",
                    "列出 skill 目录内的文件和子目录，用于查找 references。"
                    "路径相对 skill 根，留空表示根目录。",
                    {**object_schema, "properties": {"path": {"type": "string"}}},
                    lambda args: asyncio.to_thread(self.skills.entries, args.get("path", "")),
                )
            )
        if self.node.base_url:
            self.register(
                RegisteredTool(
                    "execute_javascript",
                    "在有状态 Node.js REPL session 中执行 JavaScript。",
                    {
                        **object_schema,
                        "properties": {
                            "code": {"type": "string"},
                            "session_id": {"type": "string"},
                        },
                        "required": ["code"],
                    },
                    lambda args: self.node.execute(args["code"], args.get("session_id")),
                    requires_confirmation=True,
                )
            )
        if self.browser.enabled:
            async def _browser_open(args: dict[str, Any]) -> dict[str, Any]:
                # 打开页面后强制视口为配置尺寸（默认 1368x1080），保证有头窗口内容区一致。
                width = _viewport_env("AGENT_BROWSER_WIDTH", "SANDBOX_BROWSER_WIDTH", 1368)
                height = _viewport_env("AGENT_BROWSER_HEIGHT", "SANDBOX_BROWSER_HEIGHT", 1080)
                open_result = await self.browser.run(["open", _validate_url(args["url"])])
                try:
                    viewport_result = await self.browser.run(["set", "viewport", str(width), str(height)])
                except Exception as exc:
                    return {"open": open_result, "viewport_error": str(exc), "viewport": {"width": width, "height": height}}
                return {"open": open_result, "viewport": viewport_result, "size": {"width": width, "height": height}}

            self.register(
                RegisteredTool(
                    "browser_open",
                    "使用 agent-browser 打开网页（默认视口 1368x1080）。",
                    {
                        **object_schema,
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                    _browser_open,
                    requires_confirmation=True,
                )
            )
            self.register(
                RegisteredTool(
                    "browser_snapshot",
                    "获取当前网页的交互元素快照。",
                    {**object_schema, "properties": {}},
                    lambda args: self.browser.run(["snapshot", "-i", "--json"]),
                )
            )

