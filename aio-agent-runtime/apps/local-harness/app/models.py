from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: str | None = Field(default=None, max_length=128)
    mode: Literal["single", "team"] = "single"
    # 工作台下拉选中的模型；省略时使用会话已绑定或全局默认
    provider: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128)


class AgentEvent(BaseModel):
    type: Literal["plan", "tool", "result", "error"]
    name: str
    status: Literal["running", "success", "error", "blocked"]
    detail: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=utc_now_iso)
    # 工具调用的 id（来自模型的 tool_call.id）。同一次调用会先发 running、
    # 再发终态（success / error / blocked）两条事件，前端靠这个 id 把后者
    # 替换掉前者，而不是把同一次调用渲染成两行。
    # 非工具事件（plan / result / 整体 error）为空。
    call_id: str = ""


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    mode: Literal["single", "team"]
    events: list[AgentEvent] = Field(default_factory=list)
    files: list[dict[str, Any]] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    provider: str = ""
    model: str = ""


class SessionSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    provider: str = ""
    model: str = ""
    # {prompt_tokens, completion_tokens, total_tokens, calls}
    usage: dict[str, int] = Field(default_factory=dict)


class SessionDetail(SessionSummary):
    """会话摘要 + 完整对话历史，用于点开旧会话时恢复现场。

    messages 里只有 user / assistant 两种角色：工具调用轨迹留在单次运行的临时
    上下文里，不写进会话历史（见 AgentRunner.run_stream）。
    """

    messages: list[dict[str, Any]] = Field(default_factory=list)


class SkillMatchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20000)
    limit: int = Field(default=3, ge=1, le=10)


class ConfirmDecisionRequest(BaseModel):
    confirmation_id: str = Field(min_length=1, max_length=64)
    approved: bool = False
