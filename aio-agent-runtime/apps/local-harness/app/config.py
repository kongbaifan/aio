import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .paths import project_root


def _as_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _as_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _as_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _optional_path(name: str, default: Path) -> Path | None:
    """显式设成空字符串表示关闭该功能，未设置则用默认路径。"""
    raw = os.environ.get(name)
    if raw is None:
        return default
    cleaned = raw.strip()
    return Path(cleaned).expanduser().resolve() if cleaned else None


def _as_optional_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        return None


def _load_environment_file(project_root: Path) -> None:
    """按优先级加载外部配置，保留启动脚本已经注入的环境变量。

    优先使用 HARNESS_ENV_FILE 指定的路径，其次是项目根目录的 .env。
    """
    configured = os.environ.get("HARNESS_ENV_FILE", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.append(project_root / ".env")
    for candidate in candidates:
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return


@dataclass(frozen=True)
class Settings:
    """集中管理环境变量，避免配置散落在路由和业务代码中。"""

    host: str
    port: int
    harness_token: str
    sandbox_url: str
    sandbox_token: str
    node_repl_url: str
    agent_browser_command: str
    llm_mode: str
    llm_provider: str
    llm_model: str
    harness_model: str
    llm_timeout_seconds: int
    llm_temperature: float
    llm_max_tokens: int | None
    llm_max_retries: int
    models_json: str
    max_agent_rounds: int
    max_team_steps: int
    require_tool_confirmation: bool
    # 单个工具结果进入模型上下文的字符上限；超出部分截断并附说明。设 0 表示不截断。
    tool_context_limit: int
    audit_log_path: Path
    # 审计日志轮转：单文件上限与保留份数；上限设 0 表示不轮转
    audit_max_bytes: int
    audit_backup_count: int
    # 会话持久化数据库；设为空字符串则退回纯内存（重启即丢）
    session_db_path: Path | None
    skill_roots: tuple[Path, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        root = project_root()
        _load_environment_file(root)
        skill_root_value = os.environ.get("HARNESS_SKILL_ROOTS", str(root / "skills"))
        skill_roots = tuple(
            Path(value.strip()).expanduser().resolve()
            for value in skill_root_value.split(os.pathsep)
            if value.strip()
        )
        # 模型目录默认 <project>/config/models.json；仅允许显式 HARNESS_MODELS_JSON 覆盖路径。
        models_json = os.environ.get("HARNESS_MODELS_JSON", "").strip()
        return cls(
            host=os.environ.get("HARNESS_HOST", "127.0.0.1"),
            port=_as_int("HARNESS_PORT", 8080),
            harness_token=os.environ.get("HARNESS_TOKEN", "").strip(),
            sandbox_url=os.environ.get("SANDBOX_URL", "http://127.0.0.1:8081").rstrip("/"),
            sandbox_token=os.environ.get("SANDBOX_TOKEN", "").strip(),
            node_repl_url=os.environ.get("NODE_REPL_URL", "").rstrip("/"),
            agent_browser_command=os.environ.get("AGENT_BROWSER_COMMAND", "").strip(),
            # 保留字段兼容旧 env；模型选择以 config/models.json 为准。
            llm_mode=os.environ.get("LLM_MODE", "models.json").strip().lower() or "models.json",
            llm_provider=os.environ.get("LLM_PROVIDER", "").strip().lower(),
            llm_model=(os.environ.get("LLM_MODEL") or os.environ.get("MODEL_NAME") or "").strip(),
            # 推荐：HARNESS_MODEL=provider/model
            harness_model=os.environ.get("HARNESS_MODEL", "").strip(),
            llm_timeout_seconds=_as_int("LLM_TIMEOUT_SECONDS", 90),
            llm_temperature=_as_float("LLM_TEMPERATURE", 0.1),
            llm_max_tokens=_as_optional_int("LLM_MAX_TOKENS"),
            llm_max_retries=_as_int("LLM_MAX_RETRIES", 2, minimum=0),
            models_json=models_json,
            max_agent_rounds=_as_int("MAX_AGENT_ROUNDS", 8),
            max_team_steps=_as_int("MAX_TEAM_STEPS", 4),
            tool_context_limit=_as_int("HARNESS_TOOL_CONTEXT_LIMIT", 8000, minimum=0),
            audit_log_path=Path(
                os.environ.get("HARNESS_AUDIT_LOG", str(root / "var" / "audit.jsonl"))
            ).expanduser().resolve(),
            # 默认开启：破坏性工具执行前必须人工确认。关掉等于无人值守改文件和跑代码。
            require_tool_confirmation=_as_bool("HARNESS_REQUIRE_TOOL_CONFIRMATION", True),
            audit_max_bytes=_as_int("HARNESS_AUDIT_MAX_BYTES", 5 * 1024 * 1024, minimum=0),
            audit_backup_count=_as_int("HARNESS_AUDIT_BACKUPS", 3, minimum=0),
            session_db_path=_optional_path("HARNESS_SESSION_DB", root / "var" / "sessions.db"),
            skill_roots=skill_roots,
        )
