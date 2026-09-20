import asyncio
from dataclasses import replace

import pytest

from aio_connector_gateway.contracts import Endpoint, GatewayError
from aio_connector_gateway.egress import PinnedBackend, approved_address


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "10.1.2.3",
        "100.64.0.1",
        "224.1.1.1",
        "240.1.1.1",
        "::",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "64:ff9b::a9fe:a9fe",
        "2002:7f00:1::",
    ],
)
def test_management_metadata_and_transition_addresses_are_default_denied(ip):
    ep = Endpoint("approved", "https://business.example.test/mcp", frozenset({"read"}))
    with pytest.raises(GatewayError):
        approved_address(ep, ip)


def test_private_business_network_requires_explicit_policy_and_cannot_override_hard_denies():
    ep = Endpoint(
        "approved",
        "https://business.example.test/mcp",
        frozenset({"read"}),
        private_networks=("10.20.0.0/16",),
        denied_networks=("10.20.1.0/24",),
    )
    assert approved_address(ep, "10.20.2.9") == "10.20.2.9"
    assert approved_address(ep, "8.8.8.8") == "8.8.8.8"
    for ip in ("10.20.1.9", "169.254.169.254", "127.0.0.1"):
        with pytest.raises(GatewayError):
            approved_address(replace(ep, private_networks=("0.0.0.0/0",)), ip)


def test_dns_rebinding_is_rejected_and_backend_receives_only_validated_ip():
    ep = Endpoint("approved", "https://business.example.test/mcp", frozenset({"read"}))
    calls = []

    class Stream:
        closed = False

        def get_extra_info(self, name):
            return ("8.8.8.8", 443)

        async def aclose(self):
            self.closed = True

    class Backend:
        async def connect_tcp(self, host, port, **kwargs):
            calls.append((host, port))
            return Stream()

    async def safe(host, port):
        return ["8.8.8.8"]

    async def rebound(host, port):
        return ["8.8.8.8", "127.0.0.1"]

    async def run():
        backend = PinnedBackend(ep, resolver=safe, backend=Backend())
        await backend.connect_tcp(ep.host, 443)
        assert calls == [("8.8.8.8", 443)]
        backend.resolver = rebound
        with pytest.raises(GatewayError):
            await backend.connect_tcp(ep.host, 443)
        with pytest.raises(GatewayError):
            await backend.connect_tcp("unapproved.example.test", 443)
        with pytest.raises(GatewayError):
            await backend.connect_unix_socket("/var/run/docker.sock")
        assert calls == [("8.8.8.8", 443)]

    asyncio.run(run())
