"""OAuth network operations: exact operator URLs, DNS/peer pinning, no proxy/cookie/redirect reuse."""

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import quote_plus

import httpx
import jwt

from .contracts import Endpoint, GatewayError, strict_json
from .egress import PinnedTransport


class OAuthHTTP:
    def __init__(self, endpoint, *, ssl_context=None, client_factory=None):
        self.endpoint, self.policy = endpoint, endpoint.oauth
        self.ssl_context, self.client_factory = ssl_context, client_factory
        self.resource = self.policy.resource or endpoint.url

    async def request(self, url, method="GET", data=None, *, confidential=False, revoke=False):
        approved = {
            self.policy.metadata_url,
            self.policy.resource_metadata_url,
            self.policy.token_endpoint,
            self.policy.revocation_endpoint,
            self.policy.jwks_uri,
        }
        if url not in approved or url is None:
            raise GatewayError("OAUTH_ENDPOINT_DENIED", 403, not_sent=True)
        target = Endpoint(
            "oauth-network",
            url,
            frozenset(),
            authentication="none",
            private_networks=self.endpoint.private_networks,
            denied_networks=self.endpoint.denied_networks,
            timeout_seconds=self.endpoint.timeout_seconds,
            test_mode=self.endpoint.test_mode,
        )
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        data = dict(data or {})
        if confidential:
            data["client_id"] = self.policy.client_id
            if self.policy.client_auth_method != "none":
                secret = os.environ.get(self.policy.client_secret_env, "")
                if (
                    not 16 <= len(secret) <= 8192
                    or not secret.isascii()
                    or any(ord(ch) < 33 or ord(ch) > 126 for ch in secret)
                ):
                    raise GatewayError("OAUTH_CLIENT_CONFIGURATION_INVALID", 503, not_sent=True)
                if self.policy.client_auth_method == "client_secret_basic":
                    raw = quote_plus(self.policy.client_id) + ":" + quote_plus(secret)
                    headers["Authorization"] = "Basic " + base64.b64encode(raw.encode("ascii")).decode("ascii")
                    del data["client_id"]
                else:
                    data["client_secret"] = secret
        client = (
            self.client_factory(target)
            if self.client_factory
            else httpx.AsyncClient(
                transport=PinnedTransport(target, ssl_context=self.ssl_context, allowed_methods=frozenset({method})),
                timeout=httpx.Timeout(self.endpoint.timeout_seconds, connect=5),
                trust_env=False,
                follow_redirects=False,
            )
        )
        try:
            async with client:
                async with client.stream(
                    method, url, data=data if method == "POST" else None, headers=headers
                ) as response:
                    raw = bytearray()
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise GatewayError("OAUTH_RESPONSE_INVALID", not_sent=True)
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 65536:
                            raise GatewayError("OAUTH_RESPONSE_INVALID", not_sent=True)
                    if 300 <= response.status_code < 400:
                        raise GatewayError("OAUTH_REDIRECT_DENIED", not_sent=True)
                    if revoke and response.status_code == 200:
                        return {}
                    if response.headers.get("content-type", "").split(";")[0].lower() != "application/json":
                        raise GatewayError("OAUTH_RESPONSE_INVALID", not_sent=True)
                    value = strict_json(bytes(raw), 65536)
                    if not isinstance(value, dict):
                        raise GatewayError("OAUTH_RESPONSE_INVALID", not_sent=True)
                    if response.status_code != 200:
                        known = {
                            "invalid_grant": "OAUTH_REAUTH_REQUIRED",
                            "invalid_client": "OAUTH_CLIENT_REJECTED",
                            "invalid_scope": "OAUTH_SCOPE_MISMATCH",
                            "access_denied": "OAUTH_ACCESS_DENIED",
                        }
                        raise GatewayError(known.get(value.get("error"), "OAUTH_REQUEST_FAILED"), not_sent=True)
                    return value
        except (httpx.HTTPError, TimeoutError):
            raise GatewayError("OAUTH_RESPONSE_UNKNOWN", 502, not_sent=True) from None

    async def metadata(self):
        def strings(value):
            return (
                isinstance(value, list)
                and len(value) <= 128
                and all(isinstance(item, str) and len(item) <= 2048 for item in value)
            )

        prm = await self.request(self.policy.resource_metadata_url)
        servers = prm.get("authorization_servers")
        if prm.get("resource") != self.resource or not strings(servers) or self.policy.issuer not in servers:
            raise GatewayError("OAUTH_RESOURCE_METADATA_INVALID", not_sent=True)
        supported = prm.get("scopes_supported")
        requested = set(self.policy.scopes) - {"openid", "offline_access"}
        if supported is not None and (not strings(supported) or not requested <= set(supported)):
            raise GatewayError("OAUTH_SCOPE_MISMATCH", not_sent=True)
        meta = await self.request(self.policy.metadata_url)
        for key, default in [
            ("response_types_supported", []),
            ("code_challenge_methods_supported", []),
            ("token_endpoint_auth_methods_supported", ["client_secret_basic"]),
        ]:
            if not strings(meta.get(key, default)):
                raise GatewayError("OAUTH_AUTHORIZATION_METADATA_INVALID", not_sent=True)
        if (
            meta.get("issuer") != self.policy.issuer
            or meta.get("authorization_endpoint") != self.policy.authorization_endpoint
            or meta.get("token_endpoint") != self.policy.token_endpoint
            or "code" not in meta.get("response_types_supported", [])
            or "S256" not in meta.get("code_challenge_methods_supported", [])
            or self.policy.client_auth_method
            not in meta.get("token_endpoint_auth_methods_supported", ["client_secret_basic"])
        ):
            raise GatewayError("OAUTH_AUTHORIZATION_METADATA_INVALID", not_sent=True)
        for key in ("revocation_endpoint", "jwks_uri"):
            value = getattr(self.policy, key)
            if value is not None and meta.get(key) != value:
                raise GatewayError("OAUTH_AUTHORIZATION_METADATA_INVALID", not_sent=True)
        if (
            self.policy.require_issuer_response
            and meta.get("authorization_response_iss_parameter_supported") is not True
        ):
            raise GatewayError("OAUTH_ISSUER_RESPONSE_REQUIRED", not_sent=True)
        return meta

    async def exchange(self, code, verifier):
        return await self.request(
            self.policy.token_endpoint,
            "POST",
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": self.policy.redirect_uri,
                "resource": self.resource,
            },
            confidential=True,
        )

    async def refresh(self, token):
        return await self.request(
            self.policy.token_endpoint,
            "POST",
            {
                "grant_type": "refresh_token",
                "refresh_token": token,
                "resource": self.resource,
                "scope": " ".join(self.policy.scopes),
            },
            confidential=True,
        )

    async def revoke(self, token, hint):
        if not self.policy.revocation_endpoint:
            return False
        await self.request(
            self.policy.revocation_endpoint,
            "POST",
            {"token": token, "token_type_hint": hint},
            confidential=True,
            revoke=True,
        )
        return True

    async def claims(self, encoded, audience, *, identity=False):
        try:
            if not isinstance(encoded, str) or len(encoded) > 16384:
                raise ValueError
            header = jwt.get_unverified_header(encoded)
            if header.get("alg") not in {"RS256", "ES256"} or any(
                key in header for key in ("jku", "x5u", "jwk", "crit")
            ):
                raise ValueError
            if not identity and header.get("typ") not in {"at+jwt", "application/at+jwt"}:
                raise ValueError
            jwks = await self.request(self.policy.jwks_uri)
            keys = jwks.get("keys", [])
            if not isinstance(keys, list) or not 1 <= len(keys) <= 32:
                raise ValueError
            matches = [
                key
                for key in keys
                if isinstance(key, dict)
                and key.get("kid") == header.get("kid")
                and key.get("use", "sig") == "sig"
                and key.get("alg", header["alg"]) == header["alg"]
            ]
            if len(matches) != 1:
                raise ValueError
            key = jwt.PyJWK.from_dict(matches[0], algorithm=header["alg"])
            claims = jwt.decode(
                encoded,
                key.key,
                algorithms=[header["alg"]],
                audience=audience,
                issuer=self.policy.issuer,
                leeway=30,
                options={"require": ["iss", "sub", "aud", "exp", "iat"]},
            )
            if (
                not isinstance(claims["sub"], str)
                or not 1 <= len(claims["sub"]) <= 255
                or type(claims["exp"]) is not int
                or type(claims["iat"]) is not int
            ):
                raise ValueError
            if identity:
                audiences = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
                if (len(audiences) > 1 and claims.get("azp") != self.policy.client_id) or claims.get(
                    "azp", self.policy.client_id
                ) != self.policy.client_id:
                    raise ValueError
            elif claims.get("client_id", claims.get("azp")) != self.policy.client_id:
                raise ValueError
            return claims
        except (jwt.PyJWTError, ValueError, KeyError, TypeError):
            raise GatewayError("OAUTH_JWT_INVALID", not_sent=True) from None

    async def validate_tokens(self, value, *, nonce=None, prior=None):
        def secret(name, required=False):
            token = value.get(name)
            if token is None and not required:
                return None
            if (
                not isinstance(token, str)
                or not 16 <= len(token) <= 8192
                or not token.isascii()
                or any(ord(ch) <= 32 or ord(ch) >= 127 for ch in token)
            ):
                raise GatewayError("OAUTH_TOKEN_RESPONSE_INVALID", not_sent=True)
            return token

        token = secret("access_token", True)
        refresh = secret("refresh_token") or (prior or {}).get("refresh_token")
        expires = value.get("expires_in")
        token_type = value.get("token_type")
        if (
            not isinstance(token_type, str)
            or token_type.lower() != "bearer"
            or type(expires) is not int
            or not 1 <= expires <= 31536000
        ):
            raise GatewayError("OAUTH_TOKEN_RESPONSE_INVALID", not_sent=True)
        scopes = value.get("scope", " ".join(self.policy.scopes))
        if not isinstance(scopes, str) or set(scopes.split()) != set(self.policy.scopes):
            raise GatewayError("OAUTH_SCOPE_MISMATCH", not_sent=True)
        if value.get("resource", self.resource) != self.resource:
            raise GatewayError("OAUTH_AUDIENCE_MISMATCH", not_sent=True)
        subject = (prior or {}).get("subject")
        if "openid" in self.policy.scopes:
            encoded = value.get("id_token")
            if encoded is None and prior is None:
                raise GatewayError("OAUTH_ID_TOKEN_REQUIRED", not_sent=True)
            if encoded is not None:
                identity = await self.claims(encoded, self.policy.client_id, identity=True)
                expected_nonce = nonce or (prior or {}).get("nonce")
                supplied = identity.get("nonce")
                if (prior is None or supplied is not None) and (
                    not isinstance(supplied, str)
                    or not expected_nonce
                    or not hmac.compare_digest(supplied, expected_nonce)
                ):
                    raise GatewayError("OAUTH_NONCE_MISMATCH", not_sent=True)
                if subject is not None and identity["sub"] != subject:
                    raise GatewayError("OAUTH_SUBJECT_CHANGED", not_sent=True)
                subject = identity["sub"]
                if identity.get("at_hash"):
                    actual = (
                        base64.urlsafe_b64encode(hashlib.sha256(token.encode("ascii")).digest()[:16])
                        .rstrip(b"=")
                        .decode("ascii")
                    )
                    if not isinstance(identity["at_hash"], str) or not hmac.compare_digest(identity["at_hash"], actual):
                        raise GatewayError("OAUTH_TOKEN_RESPONSE_INVALID", not_sent=True)
        elif "id_token" in value:
            raise GatewayError("OAUTH_UNREQUESTED_ID_TOKEN", not_sent=True)
        if self.policy.access_token_format == "jwt":
            access = await self.claims(token, self.resource)
            if subject is not None and access["sub"] != subject:
                raise GatewayError("OAUTH_SUBJECT_CHANGED", not_sent=True)
            subject = access["sub"]
            expires = min(expires, int(access["exp"] - time.time()))
            if expires <= 0:
                raise GatewayError("OAUTH_TOKEN_RESPONSE_INVALID", not_sent=True)
        return {
            "access_token": token,
            "refresh_token": refresh,
            "expires_at": time.time() + expires,
            "scopes": sorted(self.policy.scopes),
            "subject": subject,
            "issuer": self.policy.issuer,
            "resource": self.resource,
            "nonce": nonce or (prior or {}).get("nonce"),
            "retire_tokens": [],
        }
