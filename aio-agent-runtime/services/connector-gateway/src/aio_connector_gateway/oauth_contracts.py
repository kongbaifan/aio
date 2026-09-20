"""Operator-approved OAuth endpoints and private, session-bound grant intents."""

from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator

from .contracts import Contract, TimedBinding, digest


def approved_oauth_url(value, testing=False):
    p = urlsplit(value)
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 2048
        or not p.hostname
        or not p.hostname.isascii()
        or p.scheme not in {"https", "http"}
        or p.username is not None
        or p.password is not None
        or p.query
        or p.fragment
        or "\\" in value
        or any(ord(ch) <= 32 or ord(ch) >= 127 for ch in value)
        or (p.port is not None and not 1 <= p.port <= 65535)
    ):
        raise ValueError("OAuth URLs must be exact approved HTTPS endpoints without query or credentials")
    if p.scheme == "http" and not (testing and p.hostname in {"127.0.0.1", "localhost", "::1"}):
        raise ValueError("OAuth HTTP is limited to explicit loopback tests")
    return value


class OAuthConfig(Contract):
    issuer: str
    metadata_url: str
    resource_metadata_url: str
    authorization_endpoint: str
    token_endpoint: str
    redirect_uri: str
    client_id: str = Field(min_length=1, max_length=256)
    scopes: tuple[str, ...] = Field(min_length=1, max_length=32)
    resource: str | None = None
    client_auth_method: Literal["none", "client_secret_basic", "client_secret_post"] = "none"
    client_secret_env: str | None = Field(default=None, pattern=r"^CONNECTOR_OAUTH_CLIENT_SECRET_[A-Z0-9_]{1,64}$")
    revocation_endpoint: str | None = None
    jwks_uri: str | None = None
    access_token_format: Literal["opaque", "jwt"] = "opaque"
    require_issuer_response: bool = Field(default=True, strict=True)
    authorization_parameters: dict[str, str] = Field(default_factory=dict, max_length=2)

    @field_validator(
        "issuer",
        "metadata_url",
        "resource_metadata_url",
        "authorization_endpoint",
        "token_endpoint",
        "redirect_uri",
        "resource",
        "revocation_endpoint",
        "jwks_uri",
    )
    @classmethod
    def url(cls, value, info: ValidationInfo):
        return approved_oauth_url(value, (info.context or {}).get("test_mode", False)) if value is not None else None

    @field_validator("scopes")
    @classmethod
    def scopes_valid(cls, values):
        if len(set(values)) != len(values) or any(
            not value or len(value) > 256 or any(ord(ch) < 33 or ord(ch) > 126 or ch in {'"', "\\"} for ch in value)
            for value in values
        ):
            raise ValueError("OAuth scopes must be a unique bounded approved set")
        return values

    @model_validator(mode="after")
    def dependencies(self):
        if (self.client_auth_method != "none") != (self.client_secret_env is not None):
            raise ValueError("Confidential OAuth clients require a dedicated gateway-only secret reference")
        if ("openid" in self.scopes or self.access_token_format == "jwt") and not self.jwks_uri:
            raise ValueError("JWT validation needs an explicitly approved JWKS endpoint")
        allowed = {"prompt": {"consent", "select_account", "login"}, "access_type": {"offline", "online"}}
        if any(key not in allowed or value not in allowed[key] for key, value in self.authorization_parameters.items()):
            raise ValueError("OAuth query overrides are not allowed")
        if not self.client_id.isascii() or any(ord(ch) < 33 or ord(ch) > 126 for ch in self.client_id):
            raise ValueError("OAuth client id must be bounded and printable")
        return self


class OAuthBegin(TimedBinding):
    flow_id: UUID
    ticket_id: UUID


class OAuthExchange(OAuthBegin):
    code: SecretStr = Field(min_length=1, max_length=4096, repr=False)
    state: SecretStr = Field(min_length=32, max_length=128, repr=False)
    response_issuer: str | None = Field(default=None, max_length=2048)

    @field_validator("code", "state")
    @classmethod
    def bounded_secret(cls, value):
        raw = value.get_secret_value()
        if not raw.isascii() or any(ord(ch) <= 32 or ord(ch) > 126 for ch in raw):
            raise ValueError("OAuth responses must be bounded printable values")
        return value

    def authority(self):
        result = self.model_dump(mode="json", exclude={"code", "state"})
        result["code_hash"] = digest("aio-oauth-code-v1", self.code.get_secret_value())
        result["state_hash"] = digest("aio-oauth-state-v1", self.state.get_secret_value())
        return result
