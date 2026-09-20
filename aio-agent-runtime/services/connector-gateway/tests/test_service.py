import asyncio
from datetime import datetime, timedelta, timezone
import secrets
from uuid import uuid4

import httpx
import pytest

from aio_connector_gateway.api import create_app
from aio_connector_gateway.contracts import CredentialPut, CredentialRevoke, DiscoverRequest, GatewayError
from aio_connector_gateway.service import ConnectorGateway
from aio_connector_gateway.vault import Vault
from helpers import Authority, MCPFixture, TOKEN_A, TOKEN_B, binding, call_request, endpoint


def setup(tmp_path, fixture=None):
    ep = endpoint()
    vault = Vault(tmp_path / "vault", secrets.token_bytes(32))
    authority = Authority()
    fixture = fixture or MCPFixture()
    gateway = ConnectorGateway(vault, {ep.id: ep}, authority, client_factory=fixture.client)
    return ep, vault, authority, fixture, gateway


def test_bound_credentials_discovery_and_replay_do_not_repeat_business_rpc(tmp_path):
    ep, v, a, fixture, gateway = setup(tmp_path)
    b = binding(ep)
    request = call_request(b)

    async def run():
        await gateway.put(CredentialPut(binding=b, ticket_id=uuid4(), secret=TOKEN_A))
        found = await gateway.discover(DiscoverRequest(binding=b, discovery_id=uuid4(), not_after=request.not_after))
        assert len(found["tools"]) == 1
        assert found["tools"][0]["digest"] == request.tool_digest
        first = await gateway.call(request)
        replay = await gateway.call(request)
        assert first["result"] == replay["result"]
        assert replay["replayed"] and fixture.business_calls == 1
        assert TOKEN_A not in str(a.calls)
        a.denied = True
        with pytest.raises(GatewayError) as revoked:
            await gateway.call(request)
        assert not revoked.value.not_sent  # Prior result exists: do not falsely declare no historical effect.

    try:
        asyncio.run(run())
    finally:
        v.close()


def test_upstream_response_loss_is_durable_unknown_and_cannot_be_retried(tmp_path):
    ep, v, a, fixture, gateway = setup(tmp_path)
    b = binding(ep)
    v.put(b, TOKEN_A)
    request = call_request(b)
    fixture.fail_after_effect = True

    async def run():
        with pytest.raises(GatewayError) as first:
            await gateway.call(request)
        assert not first.value.not_sent
        assert v.status(request)["state"] == "unknown"
        with pytest.raises(GatewayError) as second:
            await gateway.call(request)
        assert not second.value.not_sent
        assert fixture.business_calls == 1

    try:
        asyncio.run(run())
    finally:
        v.close()


def test_schema_drift_and_unapproved_tools_stop_before_business_request(tmp_path):
    ep, v, a, fixture, gateway = setup(tmp_path)
    b = binding(ep)
    v.put(b, TOKEN_A)
    request = call_request(b)
    fixture.tool = {**fixture.tool, "description": "Changed untrusted instructions"}

    async def run():
        with pytest.raises(GatewayError) as drift:
            await gateway.call(request)
        assert drift.value.code == "MCP_TOOL_DEFINITION_CHANGED" and drift.value.not_sent
        assert v.status(request)["state"] == "not_sent"
        with pytest.raises(GatewayError) as unknown:
            await gateway.call(request.model_copy(update={"tool_name": "write_everything"}))
        assert unknown.value.not_sent
        assert fixture.business_calls == 0

    try:
        asyncio.run(run())
    finally:
        v.close()


def test_live_authority_revocation_cancels_waiting_rpc_and_preserves_unknown(tmp_path):
    ep, v, authority, fixture, gateway = setup(tmp_path)
    b = binding(ep)
    v.put(b, TOKEN_A)
    request = call_request(b)

    async def run():
        entered, forever = asyncio.Event(), asyncio.Event()

        class SlowClient:
            cleanup_confirmed = True

            async def initialize(self):
                return {}

            async def list_tools(self):
                from aio_connector_gateway.protocol import tool_definition

                return [tool_definition(fixture.tool)]

            async def call_tool(self, *args):
                entered.set()
                await forever.wait()

            async def close(self):
                pass

        gateway.client_factory = lambda ep, token: SlowClient()
        task = asyncio.create_task(gateway.call(request))
        await asyncio.wait_for(entered.wait(), 2)
        authority.denied = True
        with pytest.raises(GatewayError) as cancelled:
            await asyncio.wait_for(task, 3)
        assert not cancelled.value.not_sent
        assert v.status(request)["state"] == "unknown"

    try:
        asyncio.run(run())
    finally:
        v.close()


def test_endpoint_change_and_expired_deadline_do_not_send_credentials(tmp_path):
    ep, v, a, fixture, gateway = setup(tmp_path)
    b = binding(ep)
    v.put(b, TOKEN_A)

    async def run():
        for request in [
            call_request(b.model_copy(update={"endpoint_digest": "e" * 64})),
            call_request(b, not_after=datetime.now(timezone.utc) - timedelta(seconds=1)),
        ]:
            with pytest.raises(GatewayError) as blocked:
                await gateway.call(request)
            assert blocked.value.not_sent
        assert fixture.calls == []

    try:
        asyncio.run(run())
    finally:
        v.close()


def test_private_api_has_no_token_read_or_arbitrary_proxy_bypass(tmp_path):
    ep, v, a, fixture, gateway = setup(tmp_path)
    token = "synthetic-service-token-" + "x" * 40
    app = create_app(gateway, token, manage_lifecycle=False)
    b = binding(ep)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://private-gateway.test"
        ) as client:
            body = {"binding": b.model_dump(mode="json"), "ticket_id": str(uuid4()), "secret": TOKEN_A}
            assert (await client.post("/v1/credentials/put", json=body)).status_code == 401
            client.headers["Authorization"] = "Bearer " + token
            bad = await client.post("/v1/credentials/put", json={**body, "exec": "must-not-run"})
            assert bad.status_code == 422 and TOKEN_A not in bad.text
            created = await client.post("/v1/credentials/put", json=body)
            assert created.status_code == 200 and TOKEN_A not in created.text
            assert (await client.get("/v1/credentials/" + str(b.credential_ref))).status_code == 404
            assert (await client.post("/v1/proxy", json={"url": "http://169.254.169.254/"})).status_code == 404
            assert (await client.post("/v1/credentials/put", json={**body, "secret": TOKEN_B})).status_code == 409
            revoked = await client.post(
                "/v1/credentials/revoke", json=CredentialRevoke(binding=b, ticket_id=uuid4()).model_dump(mode="json")
            )
            assert revoked.status_code == 200
            with pytest.raises(GatewayError):
                v.secret(b)

    try:
        asyncio.run(run())
    finally:
        v.close()
