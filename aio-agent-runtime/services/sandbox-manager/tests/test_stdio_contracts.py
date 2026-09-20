import base64
import hashlib
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aio_sandbox_manager.contracts import InputFile, ManagerError, digest
from aio_sandbox_manager.stdio_contracts import StdioProfile, StdioSpec, StdioInputSpec, StdioOpen, decode_spec
from aio_sandbox_manager.stdio_inputs import initial_files


def profile(**changes):
    return StdioProfile(
        **{
            "id": "fixed",
            "image_digest": "sha256:" + "a" * 64,
            "executable": "/usr/local/bin/python",
            "arguments": ["-I", "/opt/fixed.py"],
            "dependency_digest": "b" * 64,
            **changes,
        }
    )


@pytest.mark.parametrize(
    "change",
    [
        {"executable": "../bin/sh"},
        {"credential_env": "PATH"},
        {"credential_env": "CONNECTOR_VAULT_KEY"},
        {"credential_env": "PYTHONPATH"},
        {"network_profile": "host"},
        {"image_digest": "python:latest"},
        {"arguments": ["x\0y"]},
    ],
)
def test_stdio_templates_cannot_select_unsafe_host_or_secret_configuration(change):
    with pytest.raises((ValueError, ValidationError)):
        profile(**change)


def test_template_digest_covers_command_environment_dependency_and_limits():
    first = profile()
    for change in [
        {"arguments": ["-I", "/opt/other.py"]},
        {"credential_env": "UPSTREAM_TOKEN"},
        {"dependency_digest": "c" * 64},
        {"pids": 32},
    ]:
        assert profile(**change).template_digest != first.template_digest


def test_cell_scope_and_secret_are_separate_from_persisted_spec():
    template = profile(credential_env="UPSTREAM_TOKEN")
    connection = uuid4()
    values = dict(
        binding_id=uuid4(),
        org_id=uuid4(),
        target_kind="run",
        target_id=uuid4(),
        generation=1,
        connection_id=connection,
        credential_ref=uuid4(),
        credential_revision=1,
        endpoint_id="fixed",
        endpoint_digest="d" * 64,
        profile_id="fixed",
        image_digest=template.image_digest,
        template_digest=template.template_digest,
        deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
        target_slot="connector/stdio/" + str(connection),
    )
    secret = "secret-must-not-be-in-audit-or-spec"
    request = StdioOpen(spec=StdioSpec(**values), context={}, credential=secret)
    assert secret not in repr(request) and secret not in str(request.authority())
    with pytest.raises(ValidationError):
        StdioSpec(**{**values, "target_slot": "compute/main"})
    with pytest.raises(ValidationError):
        StdioSpec(**{**values, "privileged": True})


def input_spec(**changes):
    template = profile(input_policy="run_attachments")
    connection, artifact = uuid4(), uuid4()
    data = b"private file body not for control journals"
    record = {
        "artifact_id": str(artifact),
        "source_path": "files/source.txt",
        "path": "attachments/" + str(artifact),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
    spec = StdioInputSpec(
        **{
            "binding_id": uuid4(),
            "org_id": uuid4(),
            "target_kind": "run",
            "target_id": uuid4(),
            "generation": 1,
            "connection_id": connection,
            "credential_ref": uuid4(),
            "credential_revision": 1,
            "endpoint_id": "fixed",
            "endpoint_digest": "d" * 64,
            "profile_id": template.id,
            "image_digest": template.image_digest,
            "template_digest": template.template_digest,
            "deadline": datetime.now(timezone.utc) + timedelta(minutes=1),
            "target_slot": "connector/stdio/" + str(connection),
            "input_manifest": [record],
            **changes,
        }
    )
    return spec, InputFile(path=record["path"], sha256=record["sha256"], content_b64=base64.b64encode(data).decode())


def test_old_no_input_template_digest_is_preserved_and_input_opt_in_is_explicit():
    old = profile()
    assert old.template_digest == digest("aio-stdio-template-v1", old.model_dump(mode="json", exclude={"input_policy"}))
    assert profile(input_policy="run_attachments").template_digest != old.template_digest
    with pytest.raises(ValidationError):
        profile(input_policy="run_attachments", workspace_bytes=4 * 1024 * 1024)
    with pytest.raises(ValidationError):
        profile(input_policy="host_workspace")


def test_attachment_bytes_are_transient_but_manifest_and_v2_digest_are_persistable():
    spec, file = input_spec()
    request = StdioOpen(spec=spec, context={}, credential="synthetic", input_files=(file,))
    assert "input_files" not in request.authority()
    assert file.content_b64 not in repr(request) and file.content_b64 not in str(request.authority())
    assert decode_spec(spec.model_dump_json()) == spec
    assert spec.spec_digest == digest("aio-stdio-spec-v2", spec.model_dump(mode="json"))
    files = initial_files(spec, (file,))
    assert files[0] == file and files[1].path == "attachments/manifest.json"
    assert file.content_b64 not in files[1].bytes().decode()


@pytest.mark.parametrize(
    "change", [{"path": "../etc/shadow"}, {"source_path": "../secret"}, {"bytes": True}, {"bytes": 4194305}]
)
def test_attachment_metadata_cannot_select_paths_or_unbounded_bytes(change):
    spec, _ = input_spec()
    record = {**spec.input_manifest[0].model_dump(mode="json"), **change}
    with pytest.raises(ValidationError):
        input_spec(input_manifest=[record])


def test_attachment_manifest_rejects_discovery_duplicates_and_aggregate_overflow():
    spec, _ = input_spec()
    record = spec.input_manifest[0].model_dump(mode="json")
    for changes in [{"target_kind": "discovery"}, {"input_manifest": [record, record]}]:
        with pytest.raises(ValidationError):
            input_spec(**changes)
    other_id = uuid4()
    other = {**record, "artifact_id": str(other_id), "path": "attachments/" + str(other_id), "bytes": 3 * 1024 * 1024}
    with pytest.raises(ValidationError):
        input_spec(input_manifest=[{**record, "bytes": 3 * 1024 * 1024}, other])


@pytest.mark.parametrize("bad", ["missing", "duplicate", "changed"])
def test_complete_input_transfer_is_checked_before_allocation(bad):
    spec, file = input_spec()
    values = (
        ()
        if bad == "missing"
        else (file, file)
        if bad == "duplicate"
        else (file.model_copy(update={"content_b64": "eA=="}),)
    )
    with pytest.raises(ManagerError):
        initial_files(spec, values)
