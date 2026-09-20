"""Private gateway wire contracts, separate from user compute and browser authentication."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
import rfc8785

PROTOCOL_VERSION = "2025-06-18"
MAX_RPC_BYTES = 1048576
MAX_RESULT_BYTES = 49152


class GatewayError(Exception):
    def __init__(self, code: str, status: int = 502, *, not_sent: bool = False):
        self.code, self.status, self.not_sent = code, status, not_sent
        super().__init__(code)


def strict_json(data: bytes, limit=MAX_RPC_BYTES):
    if len(data) > limit:
        raise GatewayError("RESPONSE_TOO_LARGE")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def check(value, depth=0):
        if depth > 32 or (type(value) is int and abs(value) > 9007199254740991):
            raise ValueError
        if isinstance(value, dict):
            for item in value.values():
                check(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                check(item, depth + 1)

    try:
        value = json.loads(
            data.decode("utf-8"), object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
        )
        check(value)
        rfc8785.dumps(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError, rfc8785.CanonicalizationError):
        raise GatewayError("MCP_INVALID_JSON") from None


def digest(domain, value):
    return hashlib.sha256(domain.encode("ascii") + b"\0" + rfc8785.dumps(value)).hexdigest()


def bounded(value, limit):
    try:
        return strict_json(rfc8785.dumps(value), limit)
    except (ValueError, TypeError, UnicodeError, RecursionError, rfc8785.CanonicalizationError):
        raise GatewayError("INVALID_REQUEST", 422, not_sent=True) from None


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Binding(Contract):
    org_id: UUID
    connection_id: UUID
    credential_ref: UUID
    credential_revision: int = Field(ge=1, strict=True)
    endpoint_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    endpoint_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def aad(self):
        return rfc8785.dumps(self.model_dump(mode="json"))


class CredentialPut(Contract):
    binding: Binding
    ticket_id: UUID
    secret: SecretStr = Field(repr=False, max_length=8192)

    @field_validator("secret")
    @classmethod
    def header_safe(cls, value):
        secret = value.get_secret_value()
        if secret and (
            len(secret) < 16 or not secret.isascii() or any(ord(ch) <= 32 or ord(ch) >= 127 for ch in secret)
        ):
            raise ValueError("Credential is not a safe opaque HTTP token")
        return value

    def authority(self):
        return self.model_dump(mode="json", exclude={"secret"})


class CredentialRevoke(Contract):
    binding: Binding
    ticket_id: UUID


class TimedBinding(Contract):
    binding: Binding
    not_after: datetime

    @field_validator("not_after")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Deadline must be timezone aware")
        return value.astimezone(timezone.utc)


class DiscoverRequest(TimedBinding):
    discovery_id: UUID


class CallRequest(TimedBinding):
    run_id: UUID
    dispatch_id: UUID
    generation: int = Field(ge=1, strict=True)
    operation_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_name: str = Field(min_length=1, max_length=128)
    tool_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    arguments: dict

    @field_validator("arguments")
    @classmethod
    def bounded_arguments(cls, value):
        return bounded(value, 65536)

    def effect_digest(self):
        # Generation/dispatch may change after controlled recovery, not the intended business operation.
        return digest(
            "aio-connector-effect-v1", self.model_dump(mode="json", exclude={"not_after", "generation", "dispatch_id"})
        )


@dataclass(frozen=True)
class Endpoint:
    id: str
    url: str
    read_tools: frozenset[str]
    authentication: Literal["bearer", "none", "oauth2"] = "bearer"
    private_networks: tuple[str, ...] = ()
    denied_networks: tuple[str, ...] = ()
    timeout_seconds: int = 30
    test_mode: bool = False
    oauth: object | None = None
    _oauth_digest: str | None = field(default=None, init=False, repr=False)
    transport: Literal["http", "stdio"] = "http"
    stdio: object | None = None
    _stdio_digest: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        try:
            p = urlsplit(self.url)
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.id) or len(self.url) > 2048:
                raise ValueError
            if self.transport not in {"http", "stdio"}:
                raise ValueError
            if self.transport == "stdio":
                from .stdio_contracts import StdioEndpoint

                if (
                    not isinstance(self.stdio, dict)
                    or self.authentication not in {"bearer", "none"}
                    or self.oauth is not None
                ):
                    raise ValueError
                raw = bounded(self.stdio, 16384)
                policy = StdioEndpoint.model_validate(raw)
                if self.url != "stdio://" + policy.profile_id or bool(policy.credential_env) != (
                    self.authentication == "bearer"
                ):
                    raise ValueError
                object.__setattr__(self, "stdio", policy)
                object.__setattr__(self, "_stdio_digest", digest("aio-stdio-endpoint-v1", raw))
            elif self.stdio is not None:
                raise ValueError
            if self.transport == "http" and (
                p.scheme not in {"https", "http"}
                or not p.hostname
                or p.username
                or p.password
                or p.query
                or p.fragment
                or "\\" in self.url
                or any(ord(ch) <= 32 for ch in self.url)
            ):
                raise ValueError
            if self.transport == "http" and (
                not p.hostname.isascii() or (p.port is not None and not 1 <= p.port <= 65535)
            ):
                raise ValueError
            if p.scheme == "http" and not (self.test_mode and p.hostname in {"127.0.0.1", "localhost", "::1"}):
                raise ValueError
            if self.authentication not in {"bearer", "none", "oauth2"} or not 1 <= self.timeout_seconds <= 120:
                raise ValueError
            if len(self.read_tools) > 64 or any(
                not isinstance(name, str) or not 1 <= len(name) <= 128 for name in self.read_tools
            ):
                raise ValueError
            for network in (*self.private_networks, *self.denied_networks):
                ipaddress.ip_network(network, strict=True)
            if self.authentication == "oauth2":
                from .oauth_contracts import OAuthConfig

                if not isinstance(self.oauth, dict):
                    raise ValueError
                raw = bounded(self.oauth, 16384)
                policy = OAuthConfig.model_validate(raw, context={"test_mode": self.test_mode})
                if urlsplit(policy.redirect_uri).path != "/auth/mcp/callback/" + self.id:
                    raise ValueError("Each approved issuer endpoint requires its own callback path")
                object.__setattr__(self, "oauth", policy)
                object.__setattr__(self, "_oauth_digest", digest("aio-oauth-config-v1", raw))
            elif self.oauth is not None:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("Endpoint must be an explicit operator-approved bounded HTTPS MCP endpoint") from None

    @property
    def host(self):
        return urlsplit(self.url).hostname

    @property
    def port(self):
        parsed = urlsplit(self.url)
        return parsed.port or (443 if parsed.scheme == "https" else 80)

    @property
    def digest(self):
        payload = {"id": self.id, "url": self.url, "authentication": self.authentication}
        if self._oauth_digest:
            payload["oauth_digest"] = self._oauth_digest
        if self._stdio_digest:
            payload.update(transport="stdio", stdio_digest=self._stdio_digest)
        return digest("aio-connector-endpoint-v1", payload)
