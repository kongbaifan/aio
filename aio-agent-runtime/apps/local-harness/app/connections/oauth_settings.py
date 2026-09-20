"""Public projection of an operator OAuth profile; no client-secret value enters the BFF."""

import re
from urllib.parse import urlsplit

from ..runtime.actions import canonical_digest


def public_oauth(raw, endpoint_id, endpoint_url, production):
    from ..platform_settings import validate_endpoint

    required = {
        "issuer",
        "metadata_url",
        "resource_metadata_url",
        "authorization_endpoint",
        "token_endpoint",
        "redirect_uri",
        "client_id",
        "scopes",
    }
    optional = {
        "resource",
        "client_auth_method",
        "client_secret_env",
        "revocation_endpoint",
        "jwks_uri",
        "access_token_format",
        "require_issuer_response",
        "authorization_parameters",
    }
    if not isinstance(raw, dict) or not required <= set(raw) or set(raw) - required - optional:
        raise ValueError("Invalid operator OAuth profile")
    for key in (required - {"client_id", "scopes"}) | {"resource", "revocation_endpoint", "jwks_uri"}:
        if raw.get(key) is not None:
            validate_endpoint(raw[key], "OAuth " + key, production=production)
            if not raw[key].isascii() or urlsplit(raw[key]).query or urlsplit(raw[key]).fragment:
                raise ValueError("OAuth endpoints must be fixed URLs")
    if urlsplit(raw["redirect_uri"]).path != "/auth/mcp/callback/" + endpoint_id:
        raise ValueError("OAuth issuer callbacks must use the endpoint-specific platform path")
    scopes = raw["scopes"]
    if (
        not isinstance(scopes, list)
        or not 1 <= len(scopes) <= 32
        or any(
            not isinstance(v, str)
            or not 1 <= len(v) <= 256
            or any(ord(ch) < 33 or ord(ch) > 126 or ch in {'"', "\\"} for ch in v)
            for v in scopes
        )
        or len(set(scopes)) != len(scopes)
    ):
        raise ValueError("Invalid approved OAuth scopes")
    if (
        not isinstance(raw["client_id"], str)
        or not 1 <= len(raw["client_id"]) <= 256
        or any(not 33 <= ord(ch) <= 126 for ch in raw["client_id"])
    ):
        raise ValueError("Invalid OAuth client id")
    method = raw.get("client_auth_method", "none")
    secret = raw.get("client_secret_env")
    if method not in {"none", "client_secret_basic", "client_secret_post"} or (method != "none") != bool(secret):
        raise ValueError("Invalid OAuth client authentication")
    if secret and not re.fullmatch(r"CONNECTOR_OAUTH_CLIENT_SECRET_[A-Z0-9_]{1,64}", secret):
        raise ValueError("OAuth client secrets require a dedicated gateway environment namespace")
    if (
        raw.get("access_token_format", "opaque") not in {"opaque", "jwt"}
        or type(raw.get("require_issuer_response", True)) is not bool
    ):
        raise ValueError("Invalid OAuth validation policy")
    if ("openid" in scopes or raw.get("access_token_format") == "jwt") and not raw.get("jwks_uri"):
        raise ValueError("JWT validation requires a fixed JWKS endpoint")
    extras = raw.get("authorization_parameters", {})
    allowed = {"prompt": {"login", "consent", "select_account"}, "access_type": {"offline", "online"}}
    if not isinstance(extras, dict) or any(k not in allowed or v not in allowed[k] for k, v in extras.items()):
        raise ValueError("OAuth parameter overrides are not allowed")
    return {
        "issuer": raw["issuer"],
        "authorization_endpoint": raw["authorization_endpoint"],
        "redirect_uri": raw["redirect_uri"],
        "client_id": raw["client_id"],
        "scopes": list(scopes),
        "resource": raw.get("resource") or endpoint_url,
        "require_issuer_response": raw.get("require_issuer_response", True),
        "config_digest": canonical_digest("aio-oauth-config-v1", raw),
    }
