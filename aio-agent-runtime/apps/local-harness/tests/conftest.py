import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
# 测试从任意工作目录启动时，都把 local-harness 根目录加入导入路径。
sys.path.insert(0, str(_TESTS_DIR.parent))
# 让各测试文件能 `from fakes import ...`，不依赖 pytest 的 rootdir 插入行为。
sys.path.insert(0, str(_TESTS_DIR))

from fakes import FakeSandbox  # noqa: E402  上面刚把 tests 目录加进路径


@pytest.fixture(autouse=True)
def isolate_runtime_paths(tmp_path, monkeypatch):
    """把所有会落盘的路径重定向到 tmp，测试绝不碰项目的 var/。

    起因：SessionStore 接上 SQLite 之后，构造 RuntimeContainer 的端到端测试
    开始往真实的 var/sessions.db 里写会话，跑一次 pytest 就往本地数据里塞几条
    "写文件" 的假会话。审计日志同理。
    """
    monkeypatch.setenv("HARNESS_SESSION_DB", str(tmp_path / "sessions.db"))
    monkeypatch.setenv("HARNESS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))


@pytest.fixture()
def sandbox() -> FakeSandbox:
    return FakeSandbox()
