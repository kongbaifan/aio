"""Bounded durable engine state and trusted execution handles.

Only model text/tool arguments are model-controlled. Run identity, target,
versions, budget and dispatch authority are supplied by the platform.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from ..auth.principal import Principal
from ..platform_errors import PlatformError
from .actions import ImmutableContract, canonical_digest, strict_json

MAX_CHECKPOINT_BYTES = 2 * 1024 * 1024
MAX_ARGUMENT_BYTES = 65536
MAX_TOOL_RESULT_BYTES = 65536
MAX_ANSWER_BYTES = 262144


def bounded_json(value: Any, limit: int, code: str = "CONTENT_TOO_LARGE") -> Any:
    import json

    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise PlatformError("INVALID_CONTENT", "Content is not finite bounded JSON", 422) from None
    if len(raw) > limit:
        raise PlatformError(code, "Content exceeds its bounded storage contract", 413)
    return strict_json(raw, max_bytes=limit)


class PlannedCall(ImmutableContract):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    arguments: dict[str, Any]

    @field_validator("arguments")
    @classmethod
    def bounded_arguments(cls, value):
        return bounded_json(value, MAX_ARGUMENT_BYTES)


class ModelTurn(ImmutableContract):
    content: str = Field(default="", max_length=MAX_ANSWER_BYTES)
    tool_calls: tuple[PlannedCall, ...] = Field(default=(), max_length=16)
    input_tokens: int | None = Field(default=None, ge=0, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, strict=True)
    finish_reason: Literal["stop", "tool_calls", "length"]

    @model_validator(mode="after")
    def consistent(self):
        if len(self.content.encode("utf-8")) > MAX_ANSWER_BYTES:
            raise ValueError("Answer exceeds its byte limit")
        if len({call.id for call in self.tool_calls}) != len(self.tool_calls):
            raise ValueError("Tool call IDs must be unique in a complete model turn")
        if (self.input_tokens is None) != (self.output_tokens is None):
            raise ValueError("Usage is either complete or explicitly unknown")
        if self.finish_reason == "tool_calls" and not self.tool_calls:
            raise ValueError("Tool-call finish reason without calls")
        return self


class Checkpoint(ImmutableContract):
    schema_version: Literal[1] = 1
    phase: Literal["model", "tools", "final"] = "model"
    round: int = Field(default=0, ge=0, le=64, strict=True)
    messages: tuple[dict[str, Any], ...] = Field(max_length=256)
    pending_calls: tuple[PlannedCall, ...] = Field(default=(), max_length=16)
    next_tool: int = Field(default=0, ge=0, le=16, strict=True)
    answer: str = Field(default="", max_length=MAX_ANSWER_BYTES)
    finish_reason: str = Field(default="", max_length=32)
    restartability: Literal["stateless", "reconstructible", "process_state_dependent"] = "stateless"

    @model_validator(mode="after")
    def valid_cursor(self):
        if self.next_tool > len(self.pending_calls):
            raise ValueError("Checkpoint cursor is outside the committed turn")
        if self.phase == "tools" and not self.pending_calls:
            raise ValueError("Tool phase requires a persisted model turn")
        if self.phase != "tools" and self.pending_calls:
            raise ValueError("Non-tool checkpoint cannot contain pending calls")
        bounded_json(self.model_dump(mode="json"), MAX_CHECKPOINT_BYTES)
        return self

    @property
    def digest(self) -> str:
        return canonical_digest("aio-checkpoint-v1", self.model_dump(mode="json"))

    @property
    def logical_model_id(self) -> str:
        return f"model:{self.round}"

    @property
    def logical_tool_id(self) -> str:
        if self.phase != "tools" or self.next_tool >= len(self.pending_calls):
            raise PlatformError("INVALID_CHECKPOINT", "Checkpoint has no next tool", 409)
        return f"turn:{self.round}:tool:{self.next_tool}"

    def with_turn(self, turn: ModelTurn) -> "Checkpoint":
        import json

        if self.phase != "model":
            raise PlatformError("CHECKPOINT_CONFLICT", "Model result does not match checkpoint phase", 409)
        message: dict[str, Any] = {"role": "assistant", "content": turn.content}
        if turn.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False, separators=(",", ":")),
                    },
                }
                for call in turn.tool_calls
            ]
        messages = (*self.messages, message)
        if turn.finish_reason == "length":
            # Do not execute a possibly truncated tool-call turn.
            return Checkpoint(
                phase="final",
                round=self.round + 1,
                messages=messages,
                answer=turn.content,
                finish_reason="length",
                restartability=self.restartability,
            )
        if turn.tool_calls:
            return Checkpoint(
                phase="tools",
                round=self.round + 1,
                messages=messages,
                pending_calls=turn.tool_calls,
                restartability=self.restartability,
            )
        return Checkpoint(
            phase="final",
            round=self.round + 1,
            messages=messages,
            answer=turn.content,
            finish_reason=turn.finish_reason,
            restartability=self.restartability,
        )

    def with_tool_result(self, logical_call_id: str, result: Any) -> "Checkpoint":
        import json

        if logical_call_id != self.logical_tool_id:
            raise PlatformError("CHECKPOINT_CONFLICT", "Tool result does not match the committed cursor", 409)
        payload = bounded_json(result, MAX_TOOL_RESULT_BYTES, "TOOL_RESULT_TOO_LARGE")
        call = self.pending_calls[self.next_tool]
        message = {
            "role": "tool",
            "tool_call_id": call.id,
            "name": call.name,
            "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        }
        done = self.next_tool + 1 == len(self.pending_calls)
        return Checkpoint(
            phase="model" if done else "tools",
            round=self.round,
            messages=(*self.messages, message),
            pending_calls=() if done else self.pending_calls,
            next_tool=0 if done else self.next_tool + 1,
            restartability=self.restartability,
        )


@dataclass(frozen=True, slots=True)
class WorkHandle:
    principal: Principal
    run_id: UUID
    generation: int
    worker_id: str
    deadline: datetime


@dataclass(frozen=True, slots=True)
class DispatchPermit:
    handle: WorkHandle
    id: UUID
    invocation_id: UUID
    operation_key: str
    tool_version_id: UUID
    driver: str
    config: dict[str, Any]
    arguments: dict[str, Any]
    not_after: datetime


@dataclass(frozen=True, slots=True)
class UsageReceipt:
    status: Literal["actual", "unknown"]
    amount: Decimal | None
    input_tokens: int | None
    output_tokens: int | None


class EffectUnknown(PlatformError):
    def __init__(self):
        super().__init__("EXTERNAL_OUTCOME_UNKNOWN", "The external effect could not be confirmed", 409)


class NotDispatched(PlatformError):
    """May only be raised by a trusted adapter BEFORE any external request/command."""
