"""Approved remote stdio executor reference, not a user-supplied executable or Docker request."""

from typing import Literal
from uuid import UUID
from pydantic import Field, field_validator, model_validator
from .contracts import Contract


class StdioEndpoint(Contract):
    profile_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    template_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    credential_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    network_profile: Literal["none"] = "none"
    input_policy: Literal["none", "run_attachments"] = "none"

    @field_validator("credential_env")
    @classmethod
    def no_control_environment(cls, value):
        if value and (
            value in {"PATH", "HOME", "TMPDIR", "USER", "SHELL", "LANG"}
            or value.startswith(("PYTHON", "LD_", "DYLD_", "NODE_", "PLATFORM_", "SANDBOX_", "CONNECTOR_"))
        ):
            raise ValueError("Stdio credentials cannot select interpreter or control-service settings")
        return value


class StdioAttachment(Contract):
    artifact_id: UUID
    source_path: str = Field(min_length=1, max_length=256)
    path: str = Field(min_length=1, max_length=64)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0, le=4 * 1024 * 1024, strict=True)

    @model_validator(mode="after")
    def fixed_path(self):
        if self.path != "attachments/" + str(self.artifact_id):
            raise ValueError("Attachment destinations must be server-derived")
        return self


def attachment_manifest(value):
    if not isinstance(value, list) or len(value) > 32:
        raise ValueError("Attachment manifest must be bounded")
    entries = [StdioAttachment.model_validate(item).model_dump(mode="json") for item in value]
    if (
        entries != value
        or len({item["artifact_id"] for item in entries}) != len(entries)
        or sum(item["bytes"] for item in entries) > 4 * 1024 * 1024
    ):
        raise ValueError("Attachment metadata must be canonical, unique and bounded")
    return entries
