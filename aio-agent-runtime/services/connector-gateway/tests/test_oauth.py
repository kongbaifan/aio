import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import sys
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import jwt
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts/platform"))
from oauth_fixture import OAuthFixture
from aio_connector_gateway.contracts import Binding, DiscoverRequest, Endpoint, GatewayError
from aio_connector_gateway.oauth_contracts import OAuthBegin, OAuthExchange
from aio_connector_gateway.oauth_http import OAuthHTTP
from aio_connector_gateway.oauth import OAuthManager
from aio_connector_gateway.vault import Vault


class Authority:
    def __init__(self):
        self.calls = []
        self.denied = set()

    async def validate(self, operation, payload):
        self.calls.append((operation, payload))
        if operation in self.denied:
            raise GatewayError("CONTROL_AUTHORIZATION_DENIED", 403, not_sent=True)


async def wait_disabled(manager, binding):
    async with asyncio.timeout(5):
        while True:
            row, _ = await asyncio.to_thread(manager.store.current, binding, inactive=True)
            if not row["active"]:
                return
            await asyncio.sleep(0.005)


@pytest.fixture
def oauth(tmp_path):
    server = OAuthFixture()
    endpoint = Endpoint(
        server.endpoint_id,
        server.origin + "/mcp",
        frozenset({"lookup_identity"}),
        authentication="oauth2",
        oauth=server.policy(),
        test_mode=True,
    )
    vault = Vault(tmp_path.resolve() / "oauth-vault", secrets.token_bytes(32))
    authority = Authority()

    def factory(e):
        return OAuthHTTP(
            e,
            client_factory=lambda target: httpx.AsyncClient(
                transport=httpx.MockTransport(server.handle), follow_redirects=False
            ),
        )

    manager = OAuthManager(vault, {endpoint.id: endpoint}, authority, http_factory=factory)
    binding = Binding(
        org_id=uuid4(),
        connection_id=uuid4(),
        credential_ref=uuid4(),
        credential_revision=1,
        endpoint_id=endpoint.id,
        endpoint_digest=endpoint.digest,
    )
    begin = OAuthBegin(
        binding=binding, flow_id=uuid4(), ticket_id=uuid4(), not_after=datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    try:
        yield manager, server, begin, authority, factory
    finally:
        vault.close()


async def authorize(values, subject="alice"):
    manager, server, begin, _, _ = values
    started = await manager.begin(begin)
    query = parse_qs(urlsplit(started["authorization_url"]).query)
    callback = parse_qs(urlsplit(server.authorize(query, subject)).query)
    exchange = OAuthExchange(
        **begin.model_dump(), code=callback["code"][0], state=callback["state"][0], response_issuer=callback["iss"][0]
    )
    return await manager.exchange(exchange), exchange


@pytest.mark.asyncio
async def test_code_pkce_nonce_resource_identity_and_encrypted_store(oauth):
    manager, server, begin, _, _ = oauth
    result, request = await authorize(oauth)
    assert result["external_identity"]["subject"] == "alice"
    assert "access_token" not in result and "refresh_token" not in result
    row, data = manager.store.current(begin.binding)
    raw = manager.store.vault.path.read_bytes()
    assert data["access_token"].encode() not in raw and data["refresh_token"].encode() not in raw
    with pytest.raises(GatewayError):
        manager.store.vault.secret(begin.binding)
    assert await manager.exchange(request) == result
    assert len([r for r in server.requests if r.url.path == "/oauth/token"]) == 1
    token_request = next(r for r in server.requests if r.url.path == "/oauth/token")
    form = parse_qs(token_request.content.decode())
    assert form["resource"] == [server.origin + "/mcp"] and form["code_verifier"][0]
    assert row["generation"] == 1


@pytest.mark.asyncio
async def test_refresh_is_single_flight_without_changing_authorization_binding(oauth):
    manager, server, begin, _, _ = oauth
    await authorize(oauth)
    with manager.store.vault.connect() as c:
        c.execute("UPDATE oauth_grants SET expires_at=0 WHERE credential_ref=?", (str(begin.binding.credential_ref),))
    request = DiscoverRequest(binding=begin.binding, discovery_id=uuid4(), not_after=begin.not_after)
    values = await asyncio.gather(manager.access(request), manager.access(request))
    assert values[0] == values[1] and values[0][1] == 2 and server.refreshes == 1
    assert begin.binding.credential_revision == 1


@pytest.mark.asyncio
async def test_revocation_wins_over_rotating_refresh_and_retires_late_tokens(oauth):
    from aio_connector_gateway.contracts import CredentialRevoke

    manager, server, begin, _, _ = oauth
    await authorize(oauth)
    with manager.store.vault.connect() as c:
        c.execute("UPDATE oauth_grants SET expires_at=0 WHERE credential_ref=?", (str(begin.binding.credential_ref),))
    server.refresh_started, server.refresh_release = asyncio.Event(), asyncio.Event()
    refresh = asyncio.create_task(
        manager.access(DiscoverRequest(binding=begin.binding, discovery_id=uuid4(), not_after=begin.not_after))
    )
    await server.refresh_started.wait()
    revoke = asyncio.create_task(manager.revoke(CredentialRevoke(binding=begin.binding, ticket_id=begin.ticket_id)))
    await wait_disabled(manager, begin.binding)
    server.refresh_release.set()
    with pytest.raises(GatewayError):
        await refresh
    assert (await revoke)["state"] == "revoked"
    assert not server.refresh_tokens and not server.access_tokens
    with pytest.raises(GatewayError):
        manager.store.current(begin.binding)


@pytest.mark.asyncio
async def test_lost_refresh_is_not_repeated_and_reports_reauth(oauth):
    manager, server, begin, authority, _ = oauth
    await authorize(oauth)
    with manager.store.vault.connect() as c:
        c.execute("UPDATE oauth_grants SET expires_at=0 WHERE credential_ref=?", (str(begin.binding.credential_ref),))
    server.fail_refresh = True
    request = DiscoverRequest(binding=begin.binding, discovery_id=uuid4(), not_after=begin.not_after)
    for _ in range(2):
        with pytest.raises(GatewayError):
            await manager.access(request)
    assert server.refreshes == 1
    assert any(operation == "oauth.reauth_required" for operation, _ in authority.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["nonce", "issuer", "audience", "scope"])
async def test_untrusted_token_claims_or_extra_scope_never_activate(oauth, bad):
    manager, server, begin, _, _ = oauth

    def change(value, claims):
        if bad == "scope":
            return {**value, "scope": "openid mcp.read admin.write"}
        claims[{"nonce": "nonce", "issuer": "iss", "audience": "aud"}[bad]] = "not-approved"
        return {
            **value,
            "id_token": jwt.encode(claims, server.key, algorithm="RS256", headers={"kid": "oauth-fixture-key"}),
        }

    server.mutate_token = change
    with pytest.raises(GatewayError):
        await authorize(oauth)
    with pytest.raises(GatewayError):
        manager.store.current(begin.binding)


@pytest.mark.asyncio
async def test_metadata_redirect_never_sends_credentials_to_redirect_target(oauth):
    manager, server, begin, _, _ = oauth
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://attacker.example/steal"})

    manager.http_factory = lambda e: OAuthHTTP(
        e,
        client_factory=lambda target: httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False),
    )
    with pytest.raises(GatewayError) as error:
        await manager.begin(begin)
    assert error.value.code == "OAUTH_REDIRECT_DENIED" and len(requests) == 1
    assert "authorization" not in requests[0].headers


@pytest.mark.asyncio
async def test_oauth_access_token_is_forwarded_only_to_approved_mcp_resource(oauth):
    from aio_connector_gateway.protocol import MCPClient

    manager, server, begin, _, _ = oauth
    await authorize(oauth)
    row, data = manager.store.current(begin.binding)
    client = MCPClient(
        manager.endpoint(begin.binding),
        data["access_token"],
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(server.handle)),
    )
    try:
        await client.initialize()
        assert (await client.list_tools())[0]["name"] == "lookup_identity"
        result = await client.call_tool("lookup_identity", {"query": "identity"}, "0" * 64)
        assert result["structured_content"]["subject"] == "alice"
    finally:
        await client.close()
    mcp = [request for request in server.requests if request.url.path == "/mcp"]
    assert mcp and all(request.headers["authorization"] == "Bearer " + data["access_token"] for request in mcp)
    assert all(data["refresh_token"] not in str(request.headers) for request in mcp)


@pytest.mark.asyncio
async def test_cancelled_store_thread_is_drained_before_revocation_can_finish(oauth, monkeypatch):
    from threading import Event
    from aio_connector_gateway.contracts import CredentialRevoke

    manager, server, begin, _, _ = oauth
    await authorize(oauth)
    with manager.store.vault.connect() as c:
        c.execute("UPDATE oauth_grants SET expires_at=0")
    entered, release = Event(), Event()
    original = manager.store.refreshed

    def delayed(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(manager.store, "refreshed", delayed)
    task = asyncio.create_task(
        manager.access(DiscoverRequest(binding=begin.binding, discovery_id=uuid4(), not_after=begin.not_after))
    )
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    revoke = asyncio.create_task(manager.revoke(CredentialRevoke(binding=begin.binding, ticket_id=begin.ticket_id)))
    await wait_disabled(manager, begin.binding)
    assert not revoke.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await revoke)["state"] == "revoked"
    row, data = manager.store.current(begin.binding, inactive=True)
    assert not row["active"] and not row["ciphertext"] and data == {}
    assert not server.access_tokens and not server.refresh_tokens


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key", ["response_types_supported", "code_challenge_methods_supported", "token_endpoint_auth_methods_supported"]
)
async def test_metadata_arrays_cannot_be_replaced_with_substring_matches(oauth, key):
    manager, server, begin, _, _ = oauth
    original = server.metadata
    server.metadata = lambda: {**original(), key: "code S256 none"}
    with pytest.raises(GatewayError) as failed:
        await manager.begin(begin)
    assert failed.value.code == "OAUTH_AUTHORIZATION_METADATA_INVALID"


@pytest.mark.asyncio
async def test_refresh_subject_change_and_pkce_code_swap_are_rejected(oauth):
    manager, server, begin, _, _ = oauth
    await authorize(oauth)

    def swapped(value, claims):
        claims["sub"] = "other-account"
        return {
            **value,
            "id_token": jwt.encode(claims, server.key, algorithm="RS256", headers={"kid": "oauth-fixture-key"}),
        }

    server.mutate_token = swapped
    with manager.store.vault.connect() as c:
        c.execute("UPDATE oauth_grants SET expires_at=0")
    with pytest.raises(GatewayError):
        await manager.access(DiscoverRequest(binding=begin.binding, discovery_id=uuid4(), not_after=begin.not_after))
    row, data = manager.store.current(begin.binding, inactive=True)
    assert not row["active"] and data["subject"] == "alice"


@pytest.mark.asyncio
async def test_authorization_code_is_bound_to_the_original_pkce_verifier(oauth):
    manager, server, begin, _, _ = oauth
    started = await manager.begin(begin)
    query = parse_qs(urlsplit(started["authorization_url"]).query)
    query["code_challenge"] = ["Z" * 43]
    callback = parse_qs(urlsplit(server.authorize(query, "attacker")).query)
    request = OAuthExchange(
        **begin.model_dump(), code=callback["code"][0], state=callback["state"][0], response_issuer=callback["iss"][0]
    )
    with pytest.raises(GatewayError):
        await manager.exchange(request)
    assert not server.access_tokens and not server.refresh_tokens


@pytest.mark.asyncio
async def test_revocation_includes_still_live_access_tokens_from_multiple_refreshes(oauth):
    from aio_connector_gateway.contracts import CredentialRevoke

    manager, server, begin, _, _ = oauth
    await authorize(oauth)
    request = DiscoverRequest(binding=begin.binding, discovery_id=uuid4(), not_after=begin.not_after)
    for _ in range(2):
        with manager.store.vault.connect() as c:
            c.execute("UPDATE oauth_grants SET expires_at=0")
        await manager.access(request)
    assert len(server.access_tokens) == 3
    result = await manager.revoke(CredentialRevoke(binding=begin.binding, ticket_id=begin.ticket_id))
    assert result["remote_revocation"] == "confirmed"
    assert not server.access_tokens and not server.refresh_tokens


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_audience", [False, True])
async def test_opt_in_jwt_access_token_validates_resource_and_client(oauth, wrong_audience):
    import time

    manager, server, begin, _, _ = oauth
    policy = {**server.policy(), "scopes": ["mcp.read"], "access_token_format": "jwt"}
    endpoint = Endpoint(
        server.endpoint_id,
        server.resource_uri,
        frozenset({"lookup_identity"}),
        authentication="oauth2",
        oauth=policy,
        test_mode=True,
    )
    http = OAuthHTTP(
        endpoint, client_factory=lambda target: httpx.AsyncClient(transport=httpx.MockTransport(server.handle))
    )
    token = jwt.encode(
        {
            "iss": server.origin + "/oauth",
            "sub": "alice",
            "aud": "https://wrong.example" if wrong_audience else server.resource_uri,
            "client_id": server.client_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        server.key,
        algorithm="RS256",
        headers={"kid": "oauth-fixture-key", "typ": "at+jwt"},
    )
    value = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "mcp.read",
        "resource": server.resource_uri,
    }
    if wrong_audience:
        with pytest.raises(GatewayError):
            await http.validate_tokens(value)
    else:
        assert (await http.validate_tokens(value))["subject"] == "alice"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["client_secret_basic", "client_secret_post"])
async def test_confidential_client_secret_is_sent_only_to_token_endpoint(oauth, monkeypatch, method):
    import base64

    manager, server, begin, _, _ = oauth
    secret = "synthetic-confidential-client-secret"
    monkeypatch.setenv("CONNECTOR_OAUTH_CLIENT_SECRET_TEST", secret)
    policy = {
        **server.policy(),
        "client_auth_method": method,
        "client_secret_env": "CONNECTOR_OAUTH_CLIENT_SECRET_TEST",
    }
    endpoint = Endpoint(
        server.endpoint_id, server.resource_uri, frozenset(), authentication="oauth2", oauth=policy, test_mode=True
    )
    seen = []

    async def handler(request):
        seen.append(request)
        return httpx.Response(200, json={})

    http = OAuthHTTP(endpoint, client_factory=lambda target: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await http.request(policy["metadata_url"])
    await http.request(
        policy["token_endpoint"],
        "POST",
        {"grant_type": "refresh_token", "refresh_token": "synthetic-refresh-token"},
        confidential=True,
    )
    assert "authorization" not in seen[0].headers and secret not in str(seen[0].url)
    form = parse_qs(seen[1].content.decode())
    if method == "client_secret_basic":
        assert base64.b64decode(seen[1].headers["authorization"][6:]).decode() == server.client_id + ":" + secret
        assert "client_secret" not in form
    else:
        assert form["client_secret"] == [secret] and "authorization" not in seen[1].headers
    assert secret not in str(seen[1].url)
