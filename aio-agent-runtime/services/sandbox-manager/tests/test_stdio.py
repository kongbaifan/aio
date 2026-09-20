import base64
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from aio_sandbox_manager.contracts import CellSpec, InputFile, ManagerError
from aio_sandbox_manager.api import create_app
from aio_sandbox_manager.docker_backend import DockerBackend
from aio_sandbox_manager.journal import Journal
from aio_sandbox_manager.service import SandboxManager
from aio_sandbox_manager.stdio_contracts import StdioProfile, StdioSpec, StdioInputSpec, StdioOpen, StdioRPC
from aio_sandbox_manager.stdio_service import StdioManager


@pytest.fixture
def stdio(tmp_path):
    image = os.environ.get("AIO_TEST_STDIO_IMAGE")
    if not image:
        pytest.skip("A real stdio image is required; run scripts/platform/test_stdio.py")
    lock = Path(__file__).resolve().parents[3] / "services/mcp-stdio-runtime/requirements.lock"
    profile = StdioProfile(
        id="stdio-test",
        image_digest=image,
        executable="/usr/local/bin/python",
        arguments=("-I", "-u", "/opt/mcp/example_server.py"),
        dependency_digest=hashlib.sha256(lock.read_bytes()).hexdigest(),
        credential_env="MCP_ACCESS_TOKEN",
    )
    journal = Journal(tmp_path.resolve() / "manager")

    class Guard:
        def __init__(self):
            self.calls = []
            self.denied = set()

        def validate(self, operation, payload):
            self.calls.append((operation, payload))
            if operation in self.denied:
                raise ManagerError("AUTHORITY_REVOKED", "Synthetic revoked authority", 403)

    guard = Guard()
    core = SandboxManager(journal, DockerBackend(journal.installation_id), {}, guard, max_cells=4)
    service = StdioManager(core, {profile.id: profile})
    try:
        yield service, core, profile, guard
    finally:
        core.close()


def spec(profile, *, target=None, connection=None, seconds=90):
    connection = connection or uuid4()
    return StdioSpec(
        binding_id=uuid4(),
        org_id=uuid4(),
        target_kind="run",
        target_id=target or uuid4(),
        generation=1,
        connection_id=connection,
        credential_ref=uuid4(),
        credential_revision=1,
        endpoint_id="stdio-test",
        endpoint_digest="1" * 64,
        profile_id=profile.id,
        image_digest=profile.image_digest,
        template_digest=profile.template_digest,
        deadline=datetime.now(timezone.utc) + timedelta(seconds=seconds),
        target_slot="connector/stdio/" + str(connection),
    )


def rpc(service, spec, method, params=None, timeout=20):
    return service.rpc(
        StdioRPC(
            spec=spec,
            context={"fixture": True},
            request_id=uuid4(),
            method=method,
            params=params or {},
            timeout_seconds=timeout,
        )
    )["response"]


def initialize(service, spec, secret="synthetic-stdio-token-one", inputs=()):
    service.open(StdioOpen(spec=spec, context={"fixture": True}, credential=secret, input_files=inputs))
    value = rpc(
        service,
        spec,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "verified-fixture", "version": "1"},
        },
    )
    assert value["result"]["protocolVersion"] == "2025-06-18"
    rpc(service, spec, "notifications/initialized")


def tool(service, spec, name, args=None):
    value = rpc(service, spec, "tools/call", {"name": name, "arguments": args or {}})
    assert "error" not in value, value
    result = value["result"]
    assert not result.get("isError"), result
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    # MCP permits JSON values encoded as text as well as structuredContent.
    return json.loads("".join(item["text"] for item in result["content"] if item.get("type") == "text"))


def test_real_stdio_protocol_identity_and_same_run_session_reuse(stdio):
    service, core, profile, guard = stdio
    current = spec(profile)
    token = "synthetic-stdio-private-identity-token"
    initialize(service, current, token)
    names = [item["name"] for item in rpc(service, current, "tools/list")["result"]["tools"]]
    assert {"identity", "isolation_facts"} <= set(names)
    first = tool(service, current, "identity", {"query": "first"})
    service.open(StdioOpen(spec=current, context={"fixture": True}, credential=token))
    again = rpc(
        service,
        current,
        "initialize",
        {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "reuse", "version": "1"}},
    )
    assert again["result"]["protocolVersion"] == "2025-06-18"
    second = tool(service, current, "identity", {"query": "second"})
    assert first["subject_digest"] == hashlib.sha256(token.encode()).hexdigest()
    assert first["instance"] == second["instance"] and second["calls"] == first["calls"] + 1
    facts = tool(service, current, "isolation_facts")
    assert facts["uid"] == 10001 and facts["interfaces"] == ["lo"] and not facts["root_writable"]
    assert not facts["control_secrets"] and not facts["docker_socket"]
    container = core.backend.checked(current, None)
    assert token not in str(container.attrs["Config"])
    assert container.attrs["HostConfig"]["LogConfig"]["Type"] == "none"
    assert all(token not in str(payload) for _, payload in guard.calls)
    assert service.stop(current)["state"] == "destroyed"
    with core.journal.connect() as c:
        columns = {row["name"] for row in c.execute("PRAGMA table_info(stdio_rpcs)")}
        assert "result_json" not in columns and "credential" not in columns
    for file in core.journal.root.glob("manager.sqlite3*"):
        assert token.encode() not in file.read_bytes()


def test_two_credential_processes_cannot_share_workspace_home_or_environment(stdio):
    service, core, profile, _ = stdio
    a, b = spec(profile), spec(profile)
    initialize(service, a, "synthetic-secret-for-first-user")
    initialize(service, b, "synthetic-secret-for-second-user")
    tool(service, a, "write_private", {"value": "first-user-only"})
    assert tool(service, b, "read_private") == {"workspace": None, "home": None}
    assert tool(service, a, "read_private") == {"workspace": "first-user-only", "home": "first-user-only"}
    fa, fb = tool(service, a, "identity", {"query": "a"}), tool(service, b, "identity", {"query": "b"})
    assert fa["subject_digest"] != fb["subject_digest"] and fa["instance"] != fb["instance"]
    assert core.backend.checked(a, None).id != core.backend.checked(b, None).id


def test_stdio_uses_different_service_token_and_rejects_generic_compute_access(stdio):
    service, core, profile, _ = stdio
    current = spec(profile)
    compute_token = "compute-manager-" + ("c" * 40)
    gateway_token = "stdio-gateway-" + ("s" * 40)
    app = create_app(core, compute_token, manage_lifecycle=False, stdio_token=gateway_token)
    payload = StdioOpen(spec=current, context={"fixture": True}, credential="synthetic-auth-private-token").model_dump(
        mode="json"
    )
    payload["credential"] = "synthetic-auth-private-token"
    with TestClient(app) as client:
        assert (
            client.post(
                "/v1/stdio/open", json=payload, headers={"Authorization": "Bearer " + compute_token}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/v1/stdio/open", json=payload, headers={"Authorization": "Bearer " + gateway_token}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/v1/cells/execute",
                json={"spec": current.model_dump(mode="json"), "code": "print(1)"},
                headers={"Authorization": "Bearer " + gateway_token},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/v1/cells/ensure",
                json={"spec": current.model_dump(mode="json")},
                headers={"Authorization": "Bearer " + compute_token},
            ).status_code
            == 422
        )
    forged = CellSpec(
        binding_id=current.binding_id,
        org_id=current.org_id,
        run_id=current.target_id,
        generation=current.generation,
        profile_id=profile.id,
        image_digest=profile.image_digest,
        deadline=current.deadline,
    )
    with pytest.raises(ManagerError):
        core.ensure(forged)


@pytest.mark.parametrize(
    "mode,code",
    [
        ("stdout-flood", "STDIO_OUTPUT_LIMIT"),
        ("stderr-flood", "STDIO_STDERR_LIMIT"),
        ("invalid-protocol", "STDIO_PROTOCOL_INVALID"),
        ("hang", "STDIO_RPC_TIMEOUT"),
    ],
)
def test_malformed_flooding_or_hung_stdio_is_bounded_and_cleaned(stdio, mode, code):
    service, core, profile, _ = stdio
    variant = profile.model_copy(update={"id": "bad-stdio", "arguments": (*profile.arguments, mode)})
    service.profiles[variant.id] = variant
    core.profiles[variant.id] = variant.resources()
    current = spec(variant)
    service.open(StdioOpen(spec=current, context={"fixture": True}, credential="synthetic-sensitive-stderr-token"))
    with pytest.raises(ManagerError) as error:
        rpc(
            service,
            current,
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "limits", "version": "1"}},
            timeout=2 if mode == "hang" else 5,
        )
    assert error.value.code in {code, "STDIO_SESSION_LOST"}
    if core.backend.checked(current, None) is not None:
        service.stop(current)
    assert core.backend.checked(current, None) is None


def test_repeated_rpc_never_reexecutes_a_sent_operation(stdio):
    service, core, profile, _ = stdio
    current = spec(profile)
    initialize(service, current)
    request = StdioRPC(
        spec=current,
        context={"fixture": True},
        request_id=uuid4(),
        method="tools/call",
        params={"name": "identity", "arguments": {"query": "once"}},
        timeout_seconds=10,
    )
    service.rpc(request)
    with pytest.raises(ManagerError) as error:
        service.rpc(request)
    assert error.value.code == "STDIO_RPC_ALREADY_SENT"
    assert tool(service, current, "identity", {"query": "next"})["calls"] == 2


def test_revocation_and_manager_loss_do_not_adopt_old_processes(stdio):
    service, core, profile, guard = stdio
    current = spec(profile)
    initialize(service, current)
    guard.denied.add("alive")
    core.reap()
    assert core.backend.checked(current, None) is None
    with pytest.raises(ManagerError):
        service.open(StdioOpen(spec=current, context={"fixture": True}, credential="synthetic-token-never-revive"))


def attachment_spec(profile, data):
    id = uuid4()
    record = {
        "artifact_id": str(id),
        "source_path": "department-private.csv",
        "path": "attachments/" + str(id),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
    current = StdioInputSpec.model_validate(
        {**spec(profile).model_dump(), "schema_version": 2, "input_manifest": [record]}
    )
    file = InputFile(path=record["path"], sha256=record["sha256"], content_b64=base64.b64encode(data).decode())
    return current, file, str(id)


def test_real_stdio_attachment_copy_is_private_not_reinjected_or_journaled(stdio):
    service, core, old_profile, guard = stdio
    profile = old_profile.model_copy(update={"input_policy": "run_attachments"})
    service.profiles[profile.id] = profile
    original = b"selected-private-document-contents\nvalue,73\n"
    a, file, id = attachment_spec(profile, original)
    initialize(service, a, inputs=(file,))
    content = tool(service, a, "read_attachment", {"artifact_id": id})
    assert content["preview"] == original.decode() and content["sha256"] == file.sha256
    assert len(tool(service, a, "list_attachments")["files"]) == 1
    first = tool(service, a, "identity", {"query": "before"})
    assert tool(service, a, "replace_attachment_for_test", {"artifact_id": id, "value": "private-copy-changed"})[
        "saved"
    ]
    initialize(service, a)
    second = tool(service, a, "identity", {"query": "after"})
    assert first["instance"] == second["instance"] and second["calls"] == 2
    assert tool(service, a, "read_attachment", {"artifact_id": id})["preview"] == "private-copy-changed"
    with pytest.raises(ManagerError, match="reimport"):
        service.open(StdioOpen(spec=a, context={}, credential="synthetic", input_files=(file,)))
    b = StdioInputSpec.model_validate({**spec(profile).model_dump(), "schema_version": 2, "input_manifest": []})
    initialize(service, b)
    assert tool(service, b, "list_attachments") == {"files": []}
    assert not tool(service, b, "read_attachment", {"artifact_id": id})["available"]
    assert original.decode() not in str(guard.calls) and file.content_b64 not in str(guard.calls)
    for current in (a, b):
        assert original.decode() not in str(core.backend.checked(current, None).attrs["Config"])
        assert service.stop(current)["state"] == "destroyed"
        assert core.backend.checked(current, None) is None
    for path in core.journal.root.glob("manager.sqlite3*"):
        assert original not in path.read_bytes() and file.content_b64.encode() not in path.read_bytes()


@pytest.mark.parametrize("bad", ["missing", "checksum", "unapproved"])
def test_stdio_invalid_attachment_transfer_allocates_no_container(stdio, bad):
    service, core, old_profile, _ = stdio
    profile = old_profile.model_copy(update={"input_policy": "run_attachments"})
    service.profiles[profile.id] = profile
    current, file, _ = attachment_spec(profile, b"input bytes")
    supplied = (file,)
    if bad == "missing":
        supplied = ()
    elif bad == "checksum":
        supplied = (file.model_copy(update={"content_b64": base64.b64encode(b"wrong bytes").decode()}),)
    else:
        current = spec(old_profile)
        service.profiles[profile.id] = old_profile
    with pytest.raises(ManagerError):
        service.open(StdioOpen(spec=current, context={}, credential="synthetic", input_files=supplied))
    assert core.journal.cell(current.binding_id) is None
    assert core.backend.checked(current, None) is None
