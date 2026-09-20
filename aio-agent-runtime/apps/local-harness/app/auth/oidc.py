"""固定 IdP 端点的 OIDC Code+PKCE 验证，不自动跟随任意发现 URL/redirect。"""

from __future__ import annotations

import hmac
from urllib.parse import urlencode

import httpx
import jwt

from ..platform_errors import PlatformError
from ..platform_settings import PlatformSettings
from ..runtime.actions import strict_json
from .service import LoginAttempt, LoginStart, token_hash


class OIDCClient:
    def __init__(self, settings: PlatformSettings, *, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False)

    def authorization_url(self, login: LoginStart) -> str:
        return (
            self.settings.oidc_authorization_endpoint
            + "?"
            + urlencode(
                {
                    "client_id": self.settings.oidc_client_id,
                    "redirect_uri": self.settings.callback_url,
                    "response_type": "code",
                    "scope": "openid profile",
                    "state": login.state,
                    "nonce": login.nonce,
                    "code_challenge": login.challenge,
                    "code_challenge_method": "S256",
                }
            )
        )

    async def _request_json(self, method: str, url: str, **kwargs) -> dict:
        try:
            async with self.client.stream(method, url, **kwargs) as response:
                if response.status_code != 200:
                    raise PlatformError(
                        "IDENTITY_PROVIDER_UNAVAILABLE", "Identity provider did not authorize the login", 502
                    )
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise PlatformError("IDENTITY_PROVIDER_INVALID", "Identity provider response is invalid", 502)
                result = strict_json(bytes(data), max_bytes=65536)
                if not isinstance(result, dict):
                    raise PlatformError("IDENTITY_PROVIDER_INVALID", "Identity provider response is invalid", 502)
                return result
        except httpx.HTTPError:
            raise PlatformError(
                "IDENTITY_PROVIDER_UNAVAILABLE", "Identity provider is unavailable", 502, retryable=True
            ) from None
        except PlatformError as exc:
            if exc.status != 502:
                raise PlatformError("IDENTITY_PROVIDER_INVALID", "Identity provider response is invalid", 502) from None
            raise

    async def verify_code(self, code: str, attempt: LoginAttempt) -> tuple[str, str]:
        if not code or len(code) > 8192:
            raise PlatformError("LOGIN_INVALID", "Login response is invalid", 401)
        payload = await self._request_json(
            "POST",
            self.settings.oidc_token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.settings.callback_url,
                "client_id": self.settings.oidc_client_id,
                "client_secret": self.settings.oidc_client_secret,
                "code_verifier": attempt.code_verifier,
            },
        )
        encoded = payload.get("id_token")
        if not isinstance(encoded, str) or len(encoded) > 32768:
            raise PlatformError("LOGIN_INVALID", "Identity token is invalid", 401)
        jwks = await self._request_json("GET", self.settings.oidc_jwks_uri)
        try:
            header = jwt.get_unverified_header(encoded)
            if header.get("alg") not in {"RS256", "ES256"} or not isinstance(header.get("kid"), str):
                raise ValueError
            keys = jwks.get("keys")
            if not isinstance(keys, list) or len(keys) > 32:
                raise ValueError
            matches = [
                key
                for key in keys
                if isinstance(key, dict)
                and key.get("kid") == header["kid"]
                and key.get("use", "sig") == "sig"
                and key.get("alg", header["alg"]) == header["alg"]
            ]
            if len(matches) != 1:
                raise ValueError
            public_key = jwt.PyJWK.from_dict(matches[0], algorithm=header["alg"]).key
            claims = jwt.decode(
                encoded,
                public_key,
                algorithms=[header["alg"]],
                issuer=self.settings.oidc_issuer,
                audience=self.settings.oidc_client_id,
                leeway=30,
                options={"require": ["iss", "aud", "sub", "exp", "iat", "nonce"]},
            )
            subject, nonce = claims.get("sub"), claims.get("nonce")
            if not isinstance(subject, str) or not 1 <= len(subject) <= 255 or not isinstance(nonce, str):
                raise ValueError
            if not hmac.compare_digest(token_hash(nonce), attempt.nonce_hash):
                raise ValueError
            audiences = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
            if len(audiences) > 1 and claims.get("azp") != self.settings.oidc_client_id:
                raise ValueError
            if "azp" in claims and claims["azp"] != self.settings.oidc_client_id:
                raise ValueError
        except (ValueError, TypeError, KeyError, jwt.PyJWTError):
            raise PlatformError("LOGIN_INVALID", "Identity token could not be verified", 401) from None
        return self.settings.oidc_issuer, subject

    async def close(self) -> None:
        await self.client.aclose()
