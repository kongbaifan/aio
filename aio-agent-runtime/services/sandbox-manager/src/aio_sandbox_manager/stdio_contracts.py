"""Credential-bearing MCP process contracts, distinct from arbitrary-code compute."""

from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator

from .contracts import Contract, CellSpec, InputFile, Profile, digest
from .stdio_inputs import MAX_STDIO_INPUT_BYTES, MAX_STDIO_INPUT_FILES, StdioAttachment


class StdioProfile(Contract):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    executable: str = Field(min_length=1, max_length=512)
    arguments: tuple[str, ...] = Field(default=(), max_length=32)
    dependency_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    credential_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    network_profile: Literal["none"] = "none"
    input_policy: Literal["none", "run_attachments"] = "none"
    memory_bytes: int = Field(default=256 * 1024 * 1024, strict=True)
    workspace_bytes: int = Field(default=8 * 1024 * 1024, strict=True)
    workspace_inodes: int = Field(default=1024, strict=True)
    temp_bytes: int = Field(default=8 * 1024 * 1024, strict=True)
    home_bytes: int = Field(default=8 * 1024 * 1024, strict=True)
    pids: int = Field(default=64, strict=True)
    nano_cpus: int = Field(default=500000000, strict=True)
    frame_bytes: int = Field(default=1048576, ge=1024, le=1048576, strict=True)
    session_output_bytes: int = Field(default=8 * 1024 * 1024, ge=1048576, le=16 * 1024 * 1024, strict=True)
    stderr_bytes: int = Field(default=65536, ge=1024, le=1048576, strict=True)
    max_timeout_seconds: int = Field(default=60, ge=1, le=120, strict=True)

    @field_validator("executable")
    @classmethod
    def absolute_program(cls, value):
        if not PurePosixPath(value).is_absolute() or ".." in value.split("/") or any(ord(ch) < 33 for ch in value):
            raise ValueError("MCP executable must be a fixed absolute image path")
        return value

    @field_validator("arguments")
    @classmethod
    def bounded_arguments(cls, value):
        if sum(len(arg.encode("utf-8")) for arg in value) > 8192 or any(
            len(arg) > 2048 or "\0" in arg for arg in value
        ):
            raise ValueError("Startup arguments exceed the approved bound")
        return value

    @field_validator("credential_env")
    @classmethod
    def credential_namespace(cls, value):
        if value and (
            value in {"PATH", "HOME", "TMPDIR", "USER", "SHELL", "LANG"}
            or value.startswith(("PYTHON", "LD_", "DYLD_", "NODE_", "PLATFORM_", "SANDBOX_", "CONNECTOR_"))
        ):
            raise ValueError("Credential cannot override runtime or control-service environment")
        return value

    def resources(self):
        return Profile(
            self.id,
            self.image_digest,
            memory_bytes=self.memory_bytes,
            workspace_bytes=self.workspace_bytes,
            workspace_inodes=self.workspace_inodes,
            temp_bytes=self.temp_bytes,
            home_bytes=self.home_bytes,
            pids=self.pids,
            nano_cpus=self.nano_cpus,
            output_bytes=self.frame_bytes,
            max_timeout_seconds=self.max_timeout_seconds,
        )

    @model_validator(mode="after")
    def valid_resources(self):
        self.resources()
        if self.input_policy == "run_attachments" and self.workspace_bytes < MAX_STDIO_INPUT_BYTES * 2:
            raise ValueError("Attachment-enabled stdio requires input capacity and separate workspace headroom")
        return self

    @property
    def template_digest(self):
        # Existing no-input templates keep their v1 identity; opting in changes the immutable digest.
        excluded = {"input_policy"} if self.input_policy == "none" else set()
        return digest("aio-stdio-template-v1", self.model_dump(mode="json", exclude=excluded))


class StdioSpec(Contract):
    schema_version: Literal[1] = 1
    kind: Literal["mcp_stdio"] = "mcp_stdio"
    binding_id: UUID
    org_id: UUID
    target_kind: Literal["run", "discovery"]
    target_id: UUID
    generation: int = Field(ge=1, strict=True)
    connection_id: UUID
    credential_ref: UUID
    credential_revision: int = Field(ge=1, strict=True)
    endpoint_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    endpoint_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    template_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    deadline: datetime
    target_slot: str = Field(min_length=1, max_length=128)

    @field_validator("deadline")
    @classmethod
    def aware(cls, value):
        return CellSpec.aware(value)

    @model_validator(mode="after")
    def scope_slot(self):
        if self.target_slot != "connector/stdio/" + str(self.connection_id):
            raise ValueError("Stdio slot must identify its exact connection")
        return self

    @property
    def run_id(self):
        # Docker's common target label is not an invented business Run for discovery jobs.
        return self.target_id

    @property
    def inputs(self):
        return ()

    @property
    def spec_digest(self):
        return digest("aio-stdio-spec-v1", self.model_dump(mode="json"))


class StdioInputSpec(StdioSpec):
    schema_version: Literal[2] = 2
    input_manifest: tuple[StdioAttachment, ...] = Field(default=(), max_length=MAX_STDIO_INPUT_FILES)

    @model_validator(mode="after")
    def bounded_manifest(self):
        if self.target_kind == "discovery" and self.input_manifest:
            raise ValueError("Discovery has no business Run attachments")
        ids = [item.artifact_id for item in self.input_manifest]
        if len(ids) != len(set(ids)) or sum(item.bytes for item in self.input_manifest) > MAX_STDIO_INPUT_BYTES:
            raise ValueError("Run attachment manifest exceeds its unique file/byte bounds")
        return self

    @property
    def spec_digest(self):
        return digest("aio-stdio-spec-v2", self.model_dump(mode="json"))


class StdioOpen(Contract):
    spec: StdioSpec | StdioInputSpec = Field(discriminator="schema_version")
    context: dict
    credential: SecretStr = Field(default_factory=lambda: SecretStr(""), max_length=8192, repr=False)
    input_files: tuple[InputFile, ...] = Field(default=(), max_length=MAX_STDIO_INPUT_FILES, repr=False)

    @field_validator("input_files")
    @classmethod
    def bounded_input_transfer(cls, value):
        if sum(len(item.content_b64) for item in value) > 6 * 1024 * 1024:
            raise ValueError("Stdio attachment transfer exceeds its aggregate bound")
        return value

    def authority(self):
        return self.model_dump(mode="json", exclude={"credential", "input_files"})


class StdioRPC(Contract):
    spec: StdioSpec | StdioInputSpec = Field(discriminator="schema_version")
    context: dict
    request_id: UUID
    method: Literal["initialize", "notifications/initialized", "tools/list", "tools/call"]
    params: dict = Field(default_factory=dict)
    timeout_seconds: int = Field(ge=1, le=120, strict=True)

    @field_validator("context", "params")
    @classmethod
    def bounded(cls, value):
        import rfc8785

        if len(rfc8785.dumps(value)) > 131072:
            raise ValueError("Stdio request exceeds its control bound")
        return value


class StdioControl(Contract):
    spec: StdioSpec | StdioInputSpec = Field(discriminator="schema_version")


def decode_spec(raw):
    import json

    value = json.loads(raw)
    if value.get("kind") == "mcp_stdio":
        cls = StdioInputSpec if value.get("schema_version") == 2 else StdioSpec
        return cls.model_validate(value)
    return CellSpec.model_validate(value)
