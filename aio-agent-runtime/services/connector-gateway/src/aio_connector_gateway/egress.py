"""DNS-to-socket pinning with the original TLS SNI; no proxy/redirect/resource-link bypass."""

import asyncio
import ipaddress
import socket
import ssl

import httpcore
import httpx
from httpcore._backends.anyio import AnyIOBackend

from .contracts import Endpoint, GatewayError

TRANSLATION_NETWORKS = tuple(
    ipaddress.ip_network(value) for value in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32")
)


def approved_address(endpoint: Endpoint, value: str) -> str:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        raise GatewayError("EGRESS_DENIED", 403, not_sent=True) from None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if any(ip in ipaddress.ip_network(n) for n in endpoint.denied_networks):
        raise GatewayError("EGRESS_DENIED", 403, not_sent=True)
    if ip.is_loopback:
        if endpoint.test_mode:
            return str(ip)
        raise GatewayError("EGRESS_DENIED", 403, not_sent=True)
    if (
        ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
        or any(ip in n for n in TRANSLATION_NETWORKS)
    ):
        raise GatewayError("EGRESS_DENIED", 403, not_sent=True)
    if ip.is_global or any(ip in ipaddress.ip_network(n) for n in endpoint.private_networks):
        return str(ip)
    raise GatewayError("EGRESS_DENIED", 403, not_sent=True)


async def resolve(host, port):
    async with asyncio.timeout(3):
        values = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(item[4][0] for item in values))


class PinnedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, endpoint: Endpoint, *, resolver=resolve, backend=None):
        self.endpoint, self.resolver, self.backend = endpoint, resolver, backend or AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host.lower().rstrip(".") != self.endpoint.host.lower().rstrip(".") or port != self.endpoint.port:
            raise GatewayError("EGRESS_DENIED", 403, not_sent=True)
        try:
            addresses = await self.resolver(host, port)
        except (OSError, TimeoutError):
            raise GatewayError("DNS_UNAVAILABLE", 503, not_sent=True) from None
        if not addresses or len(addresses) > 32:
            raise GatewayError("EGRESS_DENIED", 403, not_sent=True)
        # Reject mixed public/private rebinding answers instead of selecting a convenient safe record.
        allowed = [approved_address(self.endpoint, address) for address in addresses]
        stream = await self.backend.connect_tcp(
            allowed[0], port, timeout=timeout, local_address=None, socket_options=socket_options
        )
        peer = stream.get_extra_info("server_addr")
        if not peer or approved_address(self.endpoint, peer[0]) != allowed[0] or peer[1] != port:
            await stream.aclose()
            raise GatewayError("EGRESS_PEER_MISMATCH", 403, not_sent=True)
        # httpcore performs start_tls(server_hostname=original_host) after this returns.
        return stream

    async def connect_unix_socket(self, *args, **kwargs):
        raise GatewayError("EGRESS_DENIED", 403, not_sent=True)


class PinnedTransport(httpx.AsyncHTTPTransport):
    def __init__(
        self, endpoint: Endpoint, *, resolver=resolve, ssl_context=None, allowed_methods=frozenset({"POST", "DELETE"})
    ):
        # Use an explicitly verified TLS context; HTTPX/httpcore proxies remain disabled.
        context = ssl_context or ssl.create_default_context()
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise ValueError("Connector TLS verification cannot be disabled")
        super().__init__(verify=context, trust_env=False, retries=0)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=context,
            max_connections=4,
            max_keepalive_connections=0,
            retries=0,
            http1=True,
            http2=False,
            network_backend=PinnedBackend(endpoint, resolver=resolver),
        )
        self.endpoint = endpoint
        if not allowed_methods or set(allowed_methods) - {"GET", "POST", "DELETE"}:
            raise ValueError("Only explicit bounded HTTP methods are supported")
        self.allowed_methods = frozenset(allowed_methods)

    async def handle_async_request(self, request):
        expected = httpx.URL(self.endpoint.url)
        if request.url != expected or request.method not in self.allowed_methods:
            raise GatewayError("EGRESS_DENIED", 403, not_sent=True)
        return await super().handle_async_request(request)
