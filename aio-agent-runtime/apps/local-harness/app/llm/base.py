from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistantTurn:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class TextDelta:
    """流式过程中的一段文本增量（仅新增部分，非累计）。"""

    text: str = ""


class ModelClient(Protocol):
    async def respond(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantTurn:
        ...

    def respond_stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AsyncIterator["TextDelta | AssistantTurn"]:
        """带 tools 的流式调用：先 yield 若干 TextDelta（最终答案的文本增量），
        最后 yield 一个完整的 AssistantTurn（含 tool_calls）。上层据此边显示文本边判断是否要调工具。"""
        ...

    async def complete(self, system: str, user: str) -> str:
        ...

