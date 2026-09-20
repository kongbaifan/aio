"""Real sockets, TLS and the pinned official MCP 2.2 server (in its 2025 handshake compatibility mode)."""

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import socket
import ssl
import threading
import time

import httpx
import pytest
import uvicorn
from pydantic import BaseModel
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from aio_connector_gateway.contracts import Endpoint, PROTOCOL_VERSION
from aio_connector_gateway.egress import PinnedTransport
from aio_connector_gateway.protocol import MCPClient
from helpers import TOKEN_A, TOKEN_B


@contextmanager
def server(app, *, cert=None, key=None, sni=None):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        access_log=False,
        timeout_graceful_shutdown=1,
        ssl_certfile=str(cert) if cert else None,
        ssl_keyfile=str(key) if key else None,
    )
    config.load()
    if sni is not None:
        config.ssl.sni_callback = lambda sock, name, ctx: sni.append(name)
    instance = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: instance.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not instance.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Owned verification server did not start")
            time.sleep(0.01)
        yield port
    finally:
        instance.should_exit = True
        thread.join(5)
        sock.close()
        if thread.is_alive():
            instance.force_exit = True
            thread.join(3)
        assert not thread.is_alive(), "Owned verification server must stop"


@pytest.mark.parametrize("json_response", [False, True])
def test_official_sdk_server_with_actual_http_and_per_identity_sessions(json_response):
    from importlib.metadata import version
    from mcp.server.mcpserver import MCPServer

    assert version("mcp") == "2.2.0", "Interop evidence requires the pinned server dependency"
    upstream = MCPServer("aio-synthetic-interop", version="fixture-only")
    observed, effects = [], []

    class Output(BaseModel):
        value: int

    @upstream.tool(name="whoami", structured_output=True)
    async def whoami(value: int = 0) -> Output:
        effects.append(value)
        return Output(value=value * 2)

    app = upstream.streamable_http_app(json_response=json_response, stateless_http=False, session_idle_timeout=10)

    class Authenticate:
        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                headers = dict(scope["headers"])
                auth = headers.get(b"authorization", b"")
                if auth not in {("Bearer " + TOKEN_A).encode(), ("Bearer " + TOKEN_B).encode()}:
                    await JSONResponse({"error": "synthetic_auth_required"}, status_code=401)(scope, receive, send)
                    return
                observed.append((auth, headers.get(b"mcp-session-id"), headers.get(b"mcp-protocol-version")))
            await app(scope, receive, send)

    with server(Authenticate()) as port:
        ep = Endpoint("sdk", f"http://127.0.0.1:{port}/mcp", frozenset({"whoami"}), test_mode=True)

        async def one(token, value):
            client = MCPClient(ep, token)
            try:
                assert (await client.initialize())["protocol_version"] == PROTOCOL_VERSION
                tools = await client.list_tools()
                assert [t["name"] for t in tools] == ["whoami"]
                result = await client.call_tool("whoami", {"value": value}, str(value) * 64)
                assert result["structured_content"] == {"value": value * 2}, result
            finally:
                await client.close()
            assert client.cleanup_confirmed

        async def run():
            await asyncio.gather(one(TOKEN_A, 2), one(TOKEN_B, 3))

        asyncio.run(run())
    assert sorted(effects) == [2, 3]
    sessions = {}
    for token, session, protocol in observed:
        if session:
            sessions.setdefault(token, set()).add(session)
            assert protocol == PROTOCOL_VERSION.encode()
    assert all(len(v) == 1 for v in sessions.values())
    assert len(set.union(*sessions.values())) == 2


def certificates(root):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MCP verification fixture CA")])
    now = datetime.now(timezone.utc)
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mcp.fixture.test")]))
        .issuer_name(name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("mcp.fixture.test")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    ca_path, cert, private = root / "ca.pem", root / "server.pem", root / "server-key.pem"
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    return ca_path, cert, private


def test_real_tls_keeps_original_sni_and_host_while_connecting_to_pinned_ip(tmp_path, monkeypatch):
    ca, cert, key = certificates(tmp_path)
    app = FastAPI()
    seen, sni, dns = [], [], []

    @app.post("/mcp")
    async def echo(request: Request):
        seen.append(dict(request.headers))
        return {"host": request.headers["host"]}

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    with server(app, cert=cert, key=key, sni=sni) as port:
        ep = Endpoint("tls", f"https://mcp.fixture.test:{port}/mcp", frozenset(), test_mode=True)

        async def resolver(host, target_port):
            dns.append((host, target_port))
            return ["127.0.0.1"]

        async def run():
            context = ssl.create_default_context(cafile=str(ca))
            transport = PinnedTransport(ep, resolver=resolver, ssl_context=context)
            async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
                result = await client.post(ep.url, json={}, headers={"Authorization": "Bearer " + TOKEN_A})
                assert result.json()["host"] == f"mcp.fixture.test:{port}"
            wrong = Endpoint("tls", f"https://wrong.fixture.test:{port}/mcp", frozenset(), test_mode=True)
            async with httpx.AsyncClient(
                transport=PinnedTransport(wrong, resolver=resolver, ssl_context=context), trust_env=False
            ) as client:
                with pytest.raises(httpx.ConnectError):
                    await client.post(wrong.url, json={}, headers={"Authorization": "Bearer " + TOKEN_B})

        asyncio.run(run())
    assert dns[0] == ("mcp.fixture.test", port)
    assert "mcp.fixture.test" in sni
    assert len(seen) == 1 and seen[0]["authorization"] == "Bearer " + TOKEN_A
