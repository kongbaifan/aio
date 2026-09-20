"""严格 JSON、域分隔 RFC 8785 摘要与不可变审批动作。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

import rfc8785
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..platform_errors import PlatformError

MAX_SAFE_INTEGER = 9007199254740991
MAX_DEPTH = 32


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError("non-finite number")


def _validate_tree(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ValueError("JSON is too deeply nested")
    if type(value) is int and abs(value) > MAX_SAFE_INTEGER:
        raise ValueError("integer outside interoperable range")
    if isinstance(value, str):
        value.encode("utf-8", errors="strict")
    elif isinstance(value, dict):
        for key, child in value.items():
            key.encode("utf-8", errors="strict")
            _validate_tree(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _validate_tree(child, depth + 1)


def strict_json(raw: bytes, *, max_bytes: int = 1048576) -> Any:
    if len(raw) > max_bytes:
        raise PlatformError("PAYLOAD_TOO_LARGE", "Request exceeds the configured size limit", 413)
    try:
        text = raw.decode("utf-8", errors="strict")
        result = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        _validate_tree(result)
        # This also rejects floats overflowed to infinity and malformed Unicode.
        rfc8785.dumps(result)
        return result
    except (ValueError, UnicodeError, RecursionError, rfc8785.CanonicalizationError):
        raise PlatformError("INVALID_JSON", "Request must be finite, bounded, unambiguous JSON", 422) from None


def canonical_digest(domain: str, value: Any) -> str:
    if not domain or not domain.isascii() or "\0" in domain:
        raise ValueError("Invalid digest domain")
    try:
        payload = rfc8785.dumps(value)
    except (ValueError, UnicodeError, RecursionError, rfc8785.CanonicalizationError):
        raise PlatformError("INVALID_ACTION", "Action is not canonically representable", 422) from None
    return hashlib.sha256(domain.encode("ascii") + b"\0" + payload).hexdigest()


class ImmutableContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class ContentRef(ImmutableContract):
    id: UUID
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ActionSpec(ImmutableContract):
    schema_version: Literal[1] = 1
    canonicalization_version: Literal["action-v1"] = "action-v1"
    org_id: UUID
    actor_user_id: UUID
    run_id: UUID
    logical_call_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    tool_version_id: UUID
    arguments_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resource_scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    connection_id: UUID | None = None
    credential_binding_revision: int | None = Field(default=None, ge=0, strict=True)
    input_refs: tuple[ContentRef, ...] = Field(default=(), max_length=32)
    entrypoint_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    dependency_image_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    network_profile_id: str = Field(min_length=1, max_length=128)
    data_policy_revision: int = Field(ge=0, strict=True)
    approval_policy_id: str = Field(min_length=1, max_length=128)
    not_after: datetime

    @field_validator("not_after")
    @classmethod
    def aware_deadline(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Deadline must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def bound_connection_revision(self):
        if (self.connection_id is None) != (self.credential_binding_revision is None):
            raise ValueError("Connection identity and credential revision must be bound together")
        return self

    @property
    def digest(self) -> str:
        return canonical_digest("aio-action-v1", self.model_dump(mode="json"))
