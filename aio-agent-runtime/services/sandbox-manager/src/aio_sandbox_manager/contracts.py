"""Narrow manager protocol. User code never selects Docker flags, mounts or daemon URL."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import rfc8785


class ManagerError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


def digest(domain: str, value) -> str:
    return hashlib.sha256(domain.encode("ascii") + b"\0" + rfc8785.dumps(value)).hexdigest()


def safe_relative(value: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 512:
        raise ValueError("Invalid workspace path")
    if any(ord(ch) < 32 for ch in value) or "\\" in value or ":" in value:
        raise ValueError("Unsupported workspace path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"..", ".", ""} for part in value.split("/")) or len(path.parts) > 12:
        raise ValueError("Path must be a bounded relative path")
    return value


class InputFile(Contract):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_b64: str = Field(max_length=12000000)

    @field_validator("path")
    @classmethod
    def path_is_safe(cls, value):
        return safe_relative(value)

    def bytes(self) -> bytes:
        try:
            value = base64.b64decode(self.content_b64, validate=True)
        except ValueError:
            raise ManagerError("INPUT_INVALID", "Input encoding is invalid", 422) from None
        if len(value) > 8 * 1024 * 1024 or hashlib.sha256(value).hexdigest() != self.sha256:
            raise ManagerError("INPUT_INVALID", "Input checksum or size is invalid", 422)
        return value


class CellSpec(Contract):
    schema_version: Literal[1] = 1
    binding_id: UUID
    org_id: UUID
    run_id: UUID
    generation: int = Field(ge=1, strict=True)
    target_slot: Literal["compute/main", "skill/validation", "knowledge/ingestion", "skill/archive-import"] = (
        "compute/main"
    )
    profile_id: str = Field(min_length=1, max_length=64)
    image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    deadline: datetime
    inputs: tuple[InputFile, ...] = Field(default=(), max_length=64)

    @field_validator("deadline")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Deadline must be timezone aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def unique_inputs(self):
        paths = [item.path for item in self.inputs]
        if len(paths) != len(set(paths)):
            raise ValueError("Duplicate input path")
        if sum(len(item.content_b64) for item in self.inputs) > 12000000:
            raise ValueError("Inputs exceed the aggregate limit")
        return self

    @property
    def spec_digest(self):
        return digest("aio-cell-spec-v1", self.model_dump(mode="json"))


class ExecuteRequest(Contract):
    spec: CellSpec
    dispatch_id: UUID
    language: Literal["python"] = "python"
    code: str = Field(min_length=1, max_length=65536)
    timeout_seconds: int = Field(ge=1, le=300, strict=True)

    @field_validator("code")
    @classmethod
    def bounded_code(cls, value):
        if len(value.encode("utf-8")) > 65536 or "\0" in value:
            raise ValueError("Code exceeds its UTF-8 bound")
        return value


class ControlRequest(Contract):
    spec: CellSpec


@dataclass(frozen=True)
class Profile:
    id: str
    image_digest: str
    memory_bytes: int = 256 * 1024 * 1024
    workspace_bytes: int = 32 * 1024 * 1024
    workspace_inodes: int = 4096
    temp_bytes: int = 8 * 1024 * 1024
    home_bytes: int = 8 * 1024 * 1024
    pids: int = 64
    nano_cpus: int = 500000000
    output_bytes: int = 8192
    artifact_bytes: int = 8 * 1024 * 1024
    artifact_files: int = 64
    max_timeout_seconds: int = 120
    runtime_approval: dict | None = None

    def __post_init__(self):
        import re

        if self.runtime_approval is not None:
            from aio_runtime_policy import RuntimeApproval

            approval = RuntimeApproval.model_validate(self.runtime_approval)
            if approval.image_digest != self.image_digest:
                raise ValueError("Runtime approval must bind this exact image")

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.id) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", self.image_digest
        ):
            raise ValueError("Profile identity must use a pinned image digest")
        if not (64 * 1024 * 1024 <= self.memory_bytes <= 8 * 1024 * 1024 * 1024):
            raise ValueError("Memory profile is out of bounds")
        if self.workspace_bytes + self.temp_bytes + self.home_bytes >= self.memory_bytes:
            raise ValueError("tmpfs limits must leave memory for processes")
        if not (1024 * 1024 <= self.workspace_bytes <= 1024 * 1024 * 1024 and 128 <= self.workspace_inodes <= 65536):
            raise ValueError("Workspace quota is invalid")
        if not (16 <= self.pids <= 256 and 100000000 <= self.nano_cpus <= 4000000000):
            raise ValueError("CPU/PID quota is invalid")
        if not (
            1024 <= self.output_bytes <= 1048576
            and 1 <= self.artifact_files <= 256
            and 1024 <= self.artifact_bytes <= 16 * 1024 * 1024
            and 1 <= self.max_timeout_seconds <= 300
        ):
            raise ValueError("Output profile is invalid")
