import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth.oidc import OIDCClient
from app.auth.service import LoginAttempt, token_hash
from app.platform_errors import PlatformError


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def setup_client(settings, signing_key, *, overrides=None, response_status=200, wrong_nonce=False):
    now = datetime.now(timezone.utc)
    nonce = "nonce-test-value"
    claims = dict(
        iss=settings.oidc_issuer,
        aud=settings.oidc_client_id,
        sub="alice",
        nonce=nonce,
        exp=int((now + timedelta(minutes=5)).timestamp()),
        iat=int(now.timestamp()),
    )
    claims.update(overrides or {})
    token = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test-key"})
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    jwk.update(kid="test-key", use="sig", alg="RS256")
    seen = []

    def transport(req):
        seen.append(req)
        if req.url.path == "/token":
            return httpx.Response(response_status, json={"id_token": token})
        return httpx.Response(200, json={"keys": [jwk]})

    client = OIDCClient(
        settings, client=httpx.AsyncClient(transport=httpx.MockTransport(transport), follow_redirects=False)
    )
    attempt = LoginAttempt(uuid4(), "pkce-test-verifier", token_hash("wrong" if wrong_nonce else nonce))
    return client, attempt, seen


@pytest.mark.asyncio
async def test_signed_oidc_token_and_pkce(platform_settings, signing_key):
    client, attempt, seen = setup_client(platform_settings, signing_key)
    async with client.client:
        issuer, sub = await client.verify_code("opaque-code", attempt)
    assert issuer == platform_settings.oidc_issuer
    assert sub == "alice"
    body = parse_qs(seen[0].content.decode())
    assert body["code_verifier"] == [attempt.code_verifier]
    assert body["redirect_uri"] == [platform_settings.callback_url]
    assert len(seen) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://attacker.example.test"},
        {"aud": "another-client"},
        {"sub": ""},
        {"exp": 0},
        {"aud": ["platform-tests", "other"]},
        {"azp": "not-this-client"},
    ],
)
async def test_bad_claims_fail_closed(platform_settings, signing_key, overrides):
    client, attempt, _ = setup_client(platform_settings, signing_key, overrides=overrides)
    async with client.client:
        with pytest.raises(PlatformError) as exc:
            await client.verify_code("code", attempt)
    assert exc.value.code == "LOGIN_INVALID"


@pytest.mark.asyncio
async def test_nonce_replay_and_upstream_body_not_exposed(platform_settings, signing_key):
    client, attempt, _ = setup_client(platform_settings, signing_key, wrong_nonce=True)
    async with client.client:
        with pytest.raises(PlatformError):
            await client.verify_code("code", attempt)
    client, attempt, _ = setup_client(platform_settings, signing_key, response_status=302)
    async with client.client:
        with pytest.raises(PlatformError) as exc:
            await client.verify_code("code", attempt)
    assert platform_settings.oidc_client_secret not in str(exc.value)
