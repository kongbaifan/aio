"""在读取 legacy .env/ModelRegistry 之前选择模式，生产配置失败时绝不降级。"""

from __future__ import annotations

import ipaddress
import os
import re
from uuid import UUID, uuid4
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qs, urlsplit

from .platform_errors import PlatformConfigurationError


class DeploymentMode(str, Enum):
    LEGACY_LOCAL = "legacy-local"
    TEST = "platform-test"
    PRODUCTION = "platform-production"


def deployment_mode(env: Mapping[str, str] | None = None) -> DeploymentMode:
    source = os.environ if env is None else env
    value = source.get("HARNESS_MODE", DeploymentMode.LEGACY_LOCAL.value)
    try:
        return DeploymentMode(value)
    except ValueError:
        raise PlatformConfigurationError("HARNESS_MODE must name an explicit supported mode") from None


def require_legacy_mode() -> None:
    if deployment_mode() is not DeploymentMode.LEGACY_LOCAL:
        raise PlatformConfigurationError("Legacy configuration and runtime are disabled in platform mode")


def _integer(source: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = source.get(name, str(default))
    if not raw.isascii() or not raw.isdecimal():
        raise PlatformConfigurationError(f"{name} must be a bounded integer")
    value = int(raw)
    if not low <= value <= high:
        raise PlatformConfigurationError(f"{name} is out of range")
    return value


def _required(source: Mapping[str, str], name: str) -> str:
    value = source.get(name, "").strip()
    if not value:
        raise PlatformConfigurationError(f"{name} is required in platform mode")
    return value


def validate_endpoint(value: str, label: str, *, production: bool, origin_only: bool = False) -> str:
    """仅管理员配置的 URL；运行期 SSRF/出站策略仍需独立执行。"""
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(ord(char) <= 32 for char in value)
            or "\\" in value
            or (port is not None and not 1 <= port <= 65535)
            or (origin_only and parsed.path not in {"", "/"})
        ):
            raise ValueError
        if parsed.scheme == "http":
            try:
                local = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                local = parsed.hostname == "localhost"
            if production or not local:
                raise ValueError
    except ValueError:
        raise PlatformConfigurationError(
            f"{label} must be an approved HTTPS endpoint (test HTTP: loopback only)"
        ) from None
    return value.rstrip("/") if origin_only else value


def _database_url(source: Mapping[str, str], *, production: bool) -> str:
    database_url = _required(source, "PLATFORM_DATABASE_URL")
    try:
        parts = urlsplit(database_url)
        options = parse_qs(parts.query)
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise ValueError
        if parts.scheme != "postgresql+psycopg" or not parts.hostname or not parts.path.strip("/"):
            raise ValueError
        if not parts.username or not parts.password or parts.fragment:
            raise ValueError
        if production and options.get("sslmode") != ["verify-full"]:
            raise ValueError
    except ValueError:
        raise PlatformConfigurationError(
            "PLATFORM_DATABASE_URL must use PostgreSQL; production requires verify-full TLS"
        ) from None
    return database_url


def _artifact_root(source: Mapping[str, str]) -> Path | None:
    value = source.get("PLATFORM_ARTIFACT_ROOT", "").strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        raise PlatformConfigurationError("PLATFORM_ARTIFACT_ROOT must be an explicit absolute storage root")
    return path


def _optional_secret(source: Mapping[str, str], name: str) -> str | None:
    value = source.get(name, "").strip()
    if value and (len(value) < 32 or not value.isascii() or any(ord(ch) < 33 for ch in value)):
        raise PlatformConfigurationError(name + " must be a strong service credential")
    return value or None


def _model_origins(source: Mapping[str, str], production: bool) -> frozenset[str]:
    raw = source.get("PLATFORM_MODEL_ALLOWED_ORIGINS", "")
    return frozenset(
        validate_endpoint(v.strip(), "model origin", production=production, origin_only=True)
        for v in raw.split(",")
        if v.strip()
    )


def _model_secret_names(source: Mapping[str, str]) -> frozenset[str]:
    names = frozenset(v.strip() for v in source.get("PLATFORM_MODEL_SECRET_ENV_ALLOWLIST", "").split(",") if v.strip())
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", name) for name in names):
        raise PlatformConfigurationError("Model credential references must be approved environment-variable names")
    return names


def _sandbox_profiles(source: Mapping[str, str]) -> tuple[dict, ...]:
    import json

    raw = source.get("PLATFORM_SANDBOX_PROFILES", "").strip()
    if not raw:
        return ()
    path = Path(raw)
    try:
        if not path.is_absolute() or path.stat().st_size > 1024 * 1024:
            raise ValueError
        values = json.loads(path.read_text(encoding="utf-8"))["profiles"]
        if not isinstance(values, list) or len(values) > 16:
            raise ValueError
        result = []
        names = set()
        for item in values:
            if not isinstance(item, dict) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", item.get("id", "")):
                raise ValueError
            if item["id"] in names or not re.fullmatch(r"sha256:[0-9a-f]{64}", item.get("image_digest", "")):
                raise ValueError
            names.add(item["id"])
            timeout = item.get("max_timeout_seconds", 120)
            if type(timeout) is not int or not 1 <= timeout <= 300:
                raise ValueError
            profile = {"id": item["id"], "image_digest": item["image_digest"], "max_timeout_seconds": timeout}
            if item.get("runtime_approval") is not None:
                from aio_runtime_policy import load_trust_keys, verify_approval

                approval = verify_approval(
                    item["runtime_approval"],
                    item["image_digest"],
                    load_trust_keys(source.get("PLATFORM_RUNTIME_TRUST_KEYS")),
                    allow_test=source.get("HARNESS_MODE") == "platform-test",
                )
                profile["runtime"] = {
                    "manifest_digest": approval.manifest.digest,
                    "manifest": approval.manifest.model_dump(mode="json"),
                    "key_id": approval.key_id,
                    "purpose": approval.purpose,
                }
            result.append(profile)
        return tuple(result)
    except (OSError, ValueError, KeyError, TypeError):
        raise PlatformConfigurationError(
            "Sandbox catalog must contain unique approved profile IDs and pinned image digests"
        ) from None


def _web_dist(source: Mapping[str, str]) -> Path | None:
    raw = source.get("PLATFORM_WEB_DIST", "").strip()
    if raw:
        path = Path(raw)
    else:
        from .paths import find_root

        here = Path(__file__).resolve()
        explicit = source.get("HARNESS_PROJECT_ROOT", "").strip()
        root = Path(explicit) if explicit else find_root(here) or here.parent.parent
        path = root / "web" / "platform" / "dist"
    if not path.is_absolute():
        raise PlatformConfigurationError("Platform Web assets require an absolute build directory")
    return path


def _login_org(source: Mapping[str, str]) -> UUID | None:
    raw = source.get("PLATFORM_LOGIN_ORG_ID", "").strip()
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        raise PlatformConfigurationError("Login organization ID must be a UUID") from None


def _connector_service(source, production, *, control=False):
    url = source.get("PLATFORM_CONNECTOR_URL", "").strip() or None
    token = _optional_secret(source, "PLATFORM_CONNECTOR_TOKEN")
    authority = _optional_secret(source, "PLATFORM_CONNECTOR_CONTROL_TOKEN") if control else None
    if url:
        url = validate_endpoint(url, "PLATFORM_CONNECTOR_URL", production=production)
        if not token or (control and not authority) or (authority and authority == token):
            raise PlatformConfigurationError(
                "Connector service and control authority require distinct explicit credentials"
            )
    elif token or authority:
        raise PlatformConfigurationError("Connector credentials require an explicit isolated gateway URL")
    return url, token, authority


def _connector_profiles(source, production):
    import json
    from .runtime.actions import canonical_digest

    raw = source.get("PLATFORM_CONNECTOR_ENDPOINTS", "").strip()
    if not raw:
        return ()
    path = Path(raw)
    try:
        if not path.is_absolute() or path.stat().st_size > 65536:
            raise ValueError
        items = json.loads(path.read_text(encoding="utf-8"))["endpoints"]
        if not isinstance(items, list) or len(items) > 32:
            raise ValueError
        result, names = [], set()
        for item in items:
            name = item["id"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) or name in names:
                raise ValueError
            names.add(name)
            transport = item.get("transport", "http")
            if transport not in {"http", "stdio"}:
                raise ValueError
            url = (
                validate_endpoint(item["url"], "MCP endpoint", production=production)
                if transport == "http"
                else item["url"]
            )
            auth = item.get("authentication", "bearer")
            tools = item["read_tools"]
            timeout = item.get("timeout_seconds", 30)
            if (
                auth not in {"bearer", "none", "oauth2"}
                or not isinstance(tools, list)
                or len(tools) > 64
                or any(not isinstance(v, str) or not 1 <= len(v) <= 128 for v in tools)
                or type(timeout) is not int
                or not 1 <= timeout <= 120
            ):
                raise ValueError
            payload = {"id": name, "url": url, "authentication": auth}
            oauth = None
            stdio = None
            if transport == "stdio":
                from .connections.stdio_settings import stdio_policy

                stdio = stdio_policy(item.get("stdio"), url, auth)
                payload.update(transport="stdio", stdio_digest=stdio["config_digest"])
            elif item.get("stdio") is not None:
                raise ValueError
            if auth == "oauth2":
                from .connections.oauth_settings import public_oauth

                oauth = public_oauth(item.get("oauth"), name, url, production)
                payload["oauth_digest"] = oauth["config_digest"]
            elif item.get("oauth") is not None:
                raise ValueError
            result.append(
                {
                    "id": name,
                    "url": url,
                    "authentication": auth,
                    "read_tools": list(dict.fromkeys(tools)),
                    "timeout_seconds": timeout,
                    "digest": canonical_digest("aio-connector-endpoint-v1", payload),
                    **({"oauth": oauth} if oauth else {}),
                    **({"transport": "stdio", "stdio": stdio} if stdio else {}),
                }
            )
        return tuple(result)
    except (OSError, ValueError, TypeError, KeyError):
        raise PlatformConfigurationError(
            "MCP catalog must contain bounded, explicit operator-approved endpoint templates"
        ) from None


def _skill_import_profile(source, profiles):
    value = source.get("PLATFORM_SKILL_IMPORT_PROFILE", "").strip() or None
    if value is None:
        return None
    selected = next((p for p in profiles if p["id"] == value), None)
    if (
        selected is None
        or selected.get("max_timeout_seconds", 120) < 10
        or not source.get("PLATFORM_MANAGER_URL", "").strip()
        or not source.get("PLATFORM_ARTIFACT_ROOT", "").strip()
    ):
        raise PlatformConfigurationError(
            "Skill archive imports require an approved scanner profile, manager and private storage"
        )
    return value


@dataclass(frozen=True)
class PlatformSettings:
    mode: DeploymentMode
    database_url: str = field(repr=False)
    public_origin: str
    oidc_issuer: str
    oidc_client_id: str
    oidc_client_secret: str = field(repr=False)
    oidc_authorization_endpoint: str
    oidc_token_endpoint: str
    oidc_jwks_uri: str
    host: str = "127.0.0.1"
    port: int = 8080
    session_ttl_seconds: int = 28800
    login_ttl_seconds: int = 300
    max_request_bytes: int = 1048576
    max_message_bytes: int = 65536
    idempotency_ttl_seconds: int = 86400
    queue_ttl_seconds: int = 900
    run_timeout_seconds: int = 600
    lease_seconds: int = 45
    approval_ttl_seconds: int = 300
    sse_batch_size: int = 100
    sse_poll_seconds: int = 1
    # Executor is never replaced by local subprocess; unavailable execution stays unavailable.
    manager_url: str | None = None
    manager_token: str | None = field(default=None, repr=False)
    artifact_root: Path | None = None
    manager_control_token: str | None = field(default=None, repr=False)
    max_upload_bytes: int = 8 * 1024 * 1024
    model_allowed_origins: frozenset[str] = frozenset()
    model_secret_names: frozenset[str] = frozenset()
    sandbox_profiles: tuple[dict, ...] = ()
    skill_import_profile: str | None = None
    web_dist: Path | None = None
    login_org_id: UUID | None = None
    organization_label: str = "企业 Agent 工作台"
    connector_url: str | None = None
    connector_token: str | None = field(default=None, repr=False)
    connector_control_token: str | None = field(default=None, repr=False)
    connector_profiles: tuple[dict, ...] = ()
    document_profiles: tuple[dict, ...] = ()

    @property
    def secure_cookies(self) -> bool:
        return self.public_origin.startswith("https://")

    @property
    def session_cookie(self) -> str:
        return "__Host-aio_session" if self.secure_cookies else "aio_session"

    @property
    def callback_url(self) -> str:
        return self.public_origin + "/auth/callback"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "PlatformSettings":
        source = os.environ if env is None else env
        mode = deployment_mode(source)
        if mode is DeploymentMode.LEGACY_LOCAL:
            raise PlatformConfigurationError("PlatformSettings requires a platform deployment mode")
        production = mode is DeploymentMode.PRODUCTION
        database_url = _database_url(source, production=production)
        connector_url, connector_token, connector_control = _connector_service(source, production, control=True)

        def endpoint(name: str, *, origin_only: bool = False) -> str:
            return validate_endpoint(_required(source, name), name, production=production, origin_only=origin_only)

        manager = source.get("PLATFORM_MANAGER_URL", "").strip() or None
        manager_token = source.get("PLATFORM_MANAGER_TOKEN", "").strip() or None
        if manager:
            manager = validate_endpoint(manager, "PLATFORM_MANAGER_URL", production=production)
            if not manager_token or len(manager_token) < 32:
                raise PlatformConfigurationError("PLATFORM_MANAGER_TOKEN must be a strong service credential")
        elif manager_token:
            raise PlatformConfigurationError("Manager credentials require an explicit manager endpoint")
        # No legacy dotenv/model parsing is performed here, including when validation fails.
        profiles = _sandbox_profiles(source)
        return cls(
            mode=mode,
            database_url=database_url,
            public_origin=endpoint("PLATFORM_PUBLIC_ORIGIN", origin_only=True),
            oidc_issuer=endpoint("PLATFORM_OIDC_ISSUER"),
            oidc_client_id=_required(source, "PLATFORM_OIDC_CLIENT_ID"),
            oidc_client_secret=_required(source, "PLATFORM_OIDC_CLIENT_SECRET"),
            oidc_authorization_endpoint=endpoint("PLATFORM_OIDC_AUTHORIZATION_ENDPOINT"),
            oidc_token_endpoint=endpoint("PLATFORM_OIDC_TOKEN_ENDPOINT"),
            oidc_jwks_uri=endpoint("PLATFORM_OIDC_JWKS_URI"),
            host=source.get("HARNESS_HOST", "127.0.0.1"),
            port=_integer(source, "HARNESS_PORT", 8080, 1, 65535),
            session_ttl_seconds=_integer(source, "PLATFORM_SESSION_TTL", 28800, 60, 86400),
            login_ttl_seconds=_integer(source, "PLATFORM_LOGIN_TTL", 300, 30, 600),
            max_request_bytes=_integer(source, "PLATFORM_MAX_REQUEST_BYTES", 1048576, 1024, 10485760),
            max_message_bytes=_integer(source, "PLATFORM_MAX_MESSAGE_BYTES", 65536, 128, 262144),
            queue_ttl_seconds=_integer(source, "PLATFORM_QUEUE_TTL", 900, 30, 86400),
            run_timeout_seconds=_integer(source, "PLATFORM_RUN_TIMEOUT", 600, 1, 3600),
            lease_seconds=_integer(source, "PLATFORM_LEASE_SECONDS", 45, 10, 300),
            approval_ttl_seconds=_integer(source, "PLATFORM_APPROVAL_TTL", 300, 10, 600),
            manager_url=manager,
            manager_token=manager_token,
            artifact_root=_artifact_root(source),
            model_allowed_origins=_model_origins(source, production),
            model_secret_names=_model_secret_names(source),
            sandbox_profiles=profiles,
            skill_import_profile=_skill_import_profile(source, profiles),
            web_dist=_web_dist(source),
            login_org_id=_login_org(source),
            organization_label=source.get("PLATFORM_ORGANIZATION_LABEL", "企业 Agent 工作台")[:100],
            connector_url=connector_url,
            connector_token=connector_token,
            connector_control_token=connector_control,
            connector_profiles=_connector_profiles(source, production),
            document_profiles=_sandbox_profiles(
                {"PLATFORM_SANDBOX_PROFILES": source.get("PLATFORM_DOCUMENT_PROFILES", "")}
            ),
            manager_control_token=_optional_secret(source, "PLATFORM_MANAGER_CONTROL_TOKEN"),
            max_upload_bytes=_integer(source, "PLATFORM_MAX_UPLOAD_BYTES", 8 * 1024 * 1024, 1024, 8 * 1024 * 1024),
        )


@dataclass(frozen=True)
class WorkerSettings:
    """Least-privilege worker configuration: no OIDC browser-client secret is required."""

    mode: DeploymentMode
    database_url: str = field(repr=False)
    org_id: UUID
    worker_id: str
    approved_model_origins: frozenset[str]
    approved_secret_names: frozenset[str]
    artifact_root: Path | None = None
    manager_url: str | None = None
    manager_token: str | None = field(default=None, repr=False)
    queue_ttl_seconds: int = 900
    run_timeout_seconds: int = 600
    lease_seconds: int = 45
    approval_ttl_seconds: int = 300
    idempotency_ttl_seconds: int = 86400

    connector_url: str | None = None
    connector_token: str | None = field(default=None, repr=False)
    sandbox_profiles: tuple[dict, ...] = ()
    skill_import_profile: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "WorkerSettings":
        source = os.environ if env is None else env
        mode = deployment_mode(source)
        if mode is DeploymentMode.LEGACY_LOCAL:
            raise PlatformConfigurationError("Worker requires an explicit platform deployment mode")
        production = mode is DeploymentMode.PRODUCTION
        database_url = _database_url(source, production=production)
        connector_url, connector_token, _ = _connector_service(source, production)
        try:
            org_id = UUID(_required(source, "PLATFORM_WORKER_ORG_ID"))
        except ValueError:
            raise PlatformConfigurationError("Worker requires an explicit organization UUID") from None
        worker_id = source.get("PLATFORM_WORKER_ID", "worker-" + uuid4().hex)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", worker_id):
            raise PlatformConfigurationError("Worker identity is invalid")
        origins = frozenset(
            validate_endpoint(value.strip(), "approved model origin", production=production, origin_only=True)
            for value in _required(source, "PLATFORM_MODEL_ALLOWED_ORIGINS").split(",")
            if value.strip()
        )
        names = frozenset(
            value.strip()
            for value in _required(source, "PLATFORM_MODEL_SECRET_ENV_ALLOWLIST").split(",")
            if value.strip()
        )
        if not origins or not names or any(not re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", name) for name in names):
            raise PlatformConfigurationError("Explicit model origin and credential-name allowlists are required")
        manager_url = source.get("PLATFORM_MANAGER_URL", "").strip() or None
        manager_token = _optional_secret(source, "PLATFORM_MANAGER_TOKEN")
        artifact_root = _artifact_root(source)
        if manager_url:
            manager_url = validate_endpoint(manager_url, "PLATFORM_MANAGER_URL", production=production)
            if not manager_token or not artifact_root:
                raise PlatformConfigurationError("Sandbox worker requires a manager credential and artifact store")
        elif manager_token:
            raise PlatformConfigurationError("Manager token requires an explicit manager URL")
        profiles = _sandbox_profiles(source)
        return cls(
            mode=mode,
            database_url=database_url,
            org_id=org_id,
            artifact_root=artifact_root,
            manager_url=manager_url,
            manager_token=manager_token,
            connector_url=connector_url,
            connector_token=connector_token,
            sandbox_profiles=profiles,
            skill_import_profile=_skill_import_profile(source, profiles),
            worker_id=worker_id,
            approved_model_origins=origins,
            approved_secret_names=names,
            queue_ttl_seconds=_integer(source, "PLATFORM_QUEUE_TTL", 900, 30, 86400),
            run_timeout_seconds=_integer(source, "PLATFORM_RUN_TIMEOUT", 600, 1, 3600),
            lease_seconds=_integer(source, "PLATFORM_LEASE_SECONDS", 45, 10, 300),
            approval_ttl_seconds=_integer(source, "PLATFORM_APPROVAL_TTL", 300, 10, 600),
        )
