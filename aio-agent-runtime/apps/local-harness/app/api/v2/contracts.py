from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RequestContract(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ProjectCreate(RequestContract):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()


class SessionCreate(RequestContract):
    project_id: UUID
    agent_version_id: UUID
    title: str = Field(default="新会话", min_length=1, max_length=200)


class RunCreate(RequestContract):
    message: str = Field(min_length=1, max_length=65536)
    agent_version_id: UUID
    expected_session_revision: int = Field(ge=0, strict=True)
    input_artifact_ids: tuple[UUID, ...] = Field(default=(), max_length=32)
    allow_stdio_attachments: bool = Field(default=False, strict=True)
    connection_bindings: dict[UUID, UUID] = Field(default_factory=dict, max_length=16)
    mode: Literal["single", "team"] = "single"

    @field_validator("message")
    @classmethod
    def bounded_message(cls, value: str) -> str:
        if not value.strip() or len(value.encode("utf-8")) > 65536:
            raise ValueError("Message must be nonblank and within the byte limit")
        return value


class ApprovalDecision(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    action_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approve", "reject"]


class RunReconciliation(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    conclusion: Literal["confirmed_success", "confirmed_failure", "confirmed_no_effect"]
    evidence_ref: str = Field(min_length=1, max_length=256)


class UploadCreate(RequestContract):
    path: str = Field(min_length=1, max_length=512)
    max_bytes: int = Field(ge=0, le=8 * 1024 * 1024, strict=True)
