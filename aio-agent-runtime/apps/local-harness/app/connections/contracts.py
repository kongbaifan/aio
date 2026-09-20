from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator

from ..api.v2.contracts import RequestContract


class ServerCreate(RequestContract):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=64)
    endpoint_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class ConnectionCreate(RequestContract):
    server_id: UUID
    name: str = Field(min_length=1, max_length=100)
    scope: Literal["personal", "department"] = "personal"
    department_id: UUID | None = None


class CredentialPrepare(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    request_id: UUID


class CredentialUpload(RequestContract):
    secret: SecretStr = Field(repr=False, max_length=8192)

    @field_validator("secret")
    @classmethod
    def header_safe(cls, value):
        raw = value.get_secret_value()
        if raw and (len(raw) < 16 or not raw.isascii() or any(ord(ch) <= 32 or ord(ch) >= 127 for ch in raw)):
            raise ValueError("Credential must be an opaque HTTP token")
        return value


class DiscoveryCreate(RequestContract):
    request_id: UUID


class ToolSelection(RequestContract):
    remote_name: str = Field(min_length=1, max_length=128)
    alias: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


class ServerPublish(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    discovery_id: UUID
    tools: tuple[ToolSelection, ...] = Field(min_length=1, max_length=32)
    acknowledge_readonly_credentials: bool = Field(strict=True)
