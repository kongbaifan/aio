from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    """一次模型调用的 token 消耗。

    上游没返回 usage 时全为 0——分不清「真的是 0」和「没上报」意义不大，
    调用方看总量即可，calls 能反映实际发生了多少次调用。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            calls=self.calls + other.calls,
        )

    def __sub__(self, other: "Usage") -> "Usage":
        """求两次快照之间的增量，用于「会话累计」里切出「本次消耗」。

        各分量夹到 0：累计值只增不减，出现负数说明快照取错了，
        与其把负数显示给用户，不如归零。
        """
        return Usage(
            prompt_tokens=max(0, self.prompt_tokens - other.prompt_tokens),
            completion_tokens=max(0, self.completion_tokens - other.completion_tokens),
            calls=max(0, self.calls - other.calls),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> "Usage":
        """从 OpenAI 兼容响应的 usage 字段解析；缺字段按 0 处理。"""
        if not isinstance(raw, dict):
            return cls()
        def _int(key: str) -> int:
            value = raw.get(key)
            return value if isinstance(value, int) and value >= 0 else 0
        return cls(
            prompt_tokens=_int("prompt_tokens"),
            completion_tokens=_int("completion_tokens"),
            calls=1,
        )


@dataclass
class AssistantTurn:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    # 上游给的结束原因（stop / length / tool_calls / …）。"length" 表示答案被
    # max_tokens 截断——不记录的话，截断结果和正常完成在上层完全无法区分。
    finish_reason: str = ""


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

    async def complete_with_usage(self, system: str, user: str) -> tuple[str, Usage]:
        """与 complete 相同，但一并返回 token 消耗。

        可选实现；调用方用 getattr 探测，缺失时退回 complete 并记 0。
        """
        ...

