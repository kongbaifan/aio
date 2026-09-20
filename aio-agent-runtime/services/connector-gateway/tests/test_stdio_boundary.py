import base64
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import httpx

from aio_connector_gateway.contracts import Endpoint, Binding, CallRequest, DiscoverRequest, GatewayError, digest
from aio_connector_gateway.service import ConnectorGateway, RemoteAuthority
from aio_connector_gateway.stdio_client import StdioMCPClient
from aio_connector_gateway.stdio_contracts import attachment_manifest
from aio_connector_gateway.vault import Vault


def endpoint():
    return Endpoint(
        "stdio",
        "stdio://approved",
        frozenset({"read"}),
        transport="stdio",
        stdio={
            "profile_id": "approved",
            "image_digest": "sha256:" + "a" * 64,
            "template_digest": "b" * 64,
            "credential_env": "UPSTREAM_TOKEN",
        },
    )


@pytest.mark.asyncio
async def test_missing_stdio_manager_never_uses_host_or_http_fallback(tmp_path):
    ep = endpoint()
    vault = Vault(tmp_path.resolve() / "vault", b"v" * 32)
    binding = Binding(
        org_id=uuid4(),
        connection_id=uuid4(),
        credential_ref=uuid4(),
        credential_revision=1,
        endpoint_id=ep.id,
        endpoint_digest=ep.digest,
    )
    vault.put(binding, "synthetic-private-stdio-token")

    class Authority:
        async def validate(self, operation, payload):
            pass

    def never_http(endpoint, token):
        raise AssertionError("stdio must not be treated as an HTTP endpoint")

    gateway = ConnectorGateway(vault, {ep.id: ep}, Authority(), client_factory=never_http)
    try:
        with pytest.raises(GatewayError) as error:
            await gateway.discover(
                DiscoverRequest(
                    binding=binding, discovery_id=uuid4(), not_after=datetime.now(timezone.utc) + timedelta(seconds=10)
                )
            )
        assert error.value.code == "STDIO_EXECUTOR_UNAVAILABLE" and error.value.not_sent
    finally:
        vault.close()


@pytest.mark.parametrize(
    "change",
    [
        {"transport": "stdio", "stdio": {"profile_id": "x"}},
        {"url": "stdio://other"},
        {"authentication": "oauth2"},
        {"stdio": {"profile_id": "approved", "image_digest": "latest", "template_digest": "a" * 64}},
    ],
)
def test_stdio_endpoint_requires_pinned_reference_and_matching_identity_policy(change):
    data = {
        "id": "stdio",
        "url": "stdio://approved",
        "read_tools": frozenset(),
        "transport": "stdio",
        "stdio": {
            "profile_id": "approved",
            "image_digest": "sha256:" + "a" * 64,
            "template_digest": "b" * 64,
            "credential_env": "UPSTREAM_TOKEN",
        },
    }
    with pytest.raises(ValueError):
        Endpoint(**{**data, **change})


def input_client_data():
    ep = Endpoint(
        "stdio",
        "stdio://approved",
        frozenset({"read"}),
        transport="stdio",
        stdio={
            "profile_id": "approved",
            "image_digest": "sha256:" + "a" * 64,
            "template_digest": "b" * 64,
            "credential_env": "UPSTREAM_TOKEN",
            "input_policy": "run_attachments",
        },
    )
    binding = Binding(
        org_id=uuid4(),
        connection_id=uuid4(),
        credential_ref=uuid4(),
        credential_revision=1,
        endpoint_id=ep.id,
        endpoint_digest=ep.digest,
    )
    call = CallRequest(
        binding=binding,
        run_id=uuid4(),
        dispatch_id=uuid4(),
        generation=1,
        operation_key="c" * 64,
        tool_name="read",
        tool_digest="d" * 64,
        arguments={},
        not_after=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    id = str(uuid4())
    body = b"private-transient-document"
    item = {
        "artifact_id": id,
        "source_path": "source.csv",
        "path": "attachments/" + id,
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }
    spec = {
        "schema_version": 2,
        "kind": "mcp_stdio",
        "binding_id": str(uuid4()),
        "org_id": str(binding.org_id),
        "target_kind": "run",
        "target_id": str(call.run_id),
        "generation": 1,
        "connection_id": str(binding.connection_id),
        "credential_ref": str(binding.credential_ref),
        "credential_revision": 1,
        "endpoint_id": ep.id,
        "endpoint_digest": ep.digest,
        "profile_id": ep.stdio.profile_id,
        "image_digest": ep.stdio.image_digest,
        "template_digest": ep.stdio.template_digest,
        "deadline": call.not_after.isoformat(),
        "target_slot": "connector/stdio/" + str(binding.connection_id),
        "input_manifest": [item],
    }
    file = {"path": item["path"], "sha256": item["sha256"], "content_b64": base64.b64encode(body).decode()}
    return ep, call, spec, file


@pytest.mark.asyncio
async def test_stdio_gateway_only_transfers_raw_inputs_for_first_initialization():
    ep, call, spec, file = input_client_data()

    class Authority:
        calls = 0

        async def stdio(self, operation, payload):
            assert operation == "inputs" and payload["spec"] == spec
            self.calls += 1
            return {"allowed": True, "input_files": [file]}

    class Manager:
        opened = []

        async def call(self, operation, payload):
            if operation == "open":
                self.opened.append(payload["input_files"])
                return {
                    "binding_id": spec["binding_id"],
                    "state": "ready",
                    "spec_digest": digest("aio-stdio-spec-v2", spec),
                }
            response = None
            if payload["method"] == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": payload["request_id"],
                    "result": {"protocolVersion": "2025-06-18", "serverInfo": {"name": "synthetic"}},
                }
            return {"binding_id": spec["binding_id"], "request_id": payload["request_id"], "response": response}

    authority, manager = Authority(), Manager()
    first = StdioMCPClient(ep, "synthetic-token", call, "call", manager, authority, spec, needs_inputs=True)
    await first.initialize()
    await StdioMCPClient(ep, "synthetic-token", call, "call", manager, authority, spec).initialize()
    assert authority.calls == 1 and manager.opened == [[file], []]
    assert file["content_b64"] not in str(vars(first))


@pytest.mark.parametrize("bad", ["path", "overflow", "duplicate", "body"])
def test_stdio_gateway_rejects_noncanonical_or_expanded_input_manifests(bad):
    _, _, spec, _ = input_client_data()
    item = spec["input_manifest"][0]
    if bad == "path":
        item["path"] = "/etc/passwd"
    elif bad == "overflow":
        item["bytes"] = 4 * 1024 * 1024 + 1
    elif bad == "body":
        item["content_b64"] = "eA=="
    else:
        spec["input_manifest"].append(item)
    with pytest.raises(ValueError):
        attachment_manifest(spec["input_manifest"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "bytes", "allowed"),
    [("inputs", 70000, True), ("cleanup", 70000, False), ("inputs", 6 * 1024 * 1024, False)],
)
async def test_stdio_input_response_has_its_own_hard_bound(operation, bytes, allowed):
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"allowed": True, "input_files": ["x" * bytes]})
        )
    )
    authority = RemoteAuthority("https://control.example.test", "synthetic-" + "a" * 32, client=http)
    try:
        if allowed:
            assert (await authority.stdio(operation, {}))["allowed"] is True
        else:
            with pytest.raises(GatewayError):
                await authority.stdio(operation, {})
    finally:
        await http.aclose()
