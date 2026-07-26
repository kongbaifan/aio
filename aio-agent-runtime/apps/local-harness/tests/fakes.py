"""测试用的外部依赖替身。

原先 test_agent / test_confirmation / test_team_mode / test_usage / test_skills
各自抄了一份，五份还互有出入（有的记 written，有的 list_files 返回空），
改一处行为要翻五个文件。统一放这里。
"""

from typing import Any


class FakeSandbox:
    """替代 SandboxClient：记录写入与执行，其余返回最小可用结果。"""

    base_url = ""

    def __init__(self):
        self.written: list[tuple[str, str]] = []
        self.executed: list[str] = []

    async def list_files(self, path: str = ".") -> dict[str, Any]:
        return {"items": [{"name": "sample.txt", "type": "file"}], "cwd": path}

    async def read_file(self, path: str) -> dict[str, Any]:
        return {"path": path, "content": "hello"}

    async def write_file(self, path: str, content: str) -> dict[str, Any]:
        self.written.append((path, content))
        return {"path": path, "size": len(content)}

    async def execute_python(self, code: str, session_id: str | None = None) -> dict[str, Any]:
        self.executed.append(code)
        return {"output": "ok", "error": "", "exit_code": 0}

    async def lint_python(self, code: str) -> dict[str, Any]:
        return {"errors": [], "warnings": []}

    async def metrics(self) -> dict[str, Any]:
        return {"cpu_percent": 0}

    async def browser_info(self) -> dict[str, Any]:
        return {"data": {}}

    async def close(self) -> None:
        return None


class FakeNode:
    """base_url 为空即视为未启用，ToolRegistry 不会注册 execute_javascript。"""

    base_url = ""

    async def close(self) -> None:
        return None


class FakeBrowser:
    enabled = False
