import base64
import hashlib
from uuid import uuid4

import pytest

from app.platform_errors import PlatformError
from app.workspaces.checkpoints import binding_digest, SOURCES
from app.workspaces.exports import prepare_export


def file(path="result.txt", data=b"bounded file"):
    return {
        "path": path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "content_b64": base64.b64encode(data).decode("ascii"),
    }


def test_export_manifest_is_sorted_verified_and_does_not_execute_content():
    prepared, manifest = prepare_export(
        [file("z.py", b'raise RuntimeError("never execute on host")'), file("a.bin", b"\x00\xff")]
    )
    assert [item["path"] for item in manifest] == ["a.bin", "z.py"]
    assert prepared[0]["data"] == b"\x00\xff"
    assert all(set(item) == {"path", "sha256", "bytes"} for item in manifest)


@pytest.mark.parametrize(
    "change",
    [
        {"path": "../host"},
        {"path": "/etc/passwd"},
        {"bytes": True},
        {"bytes": 2},
        {"sha256": "0" * 64},
        {"content_b64": "!invalid!"},
        {"mount": "/var/run/docker.sock"},
    ],
)
def test_export_rejects_ambiguous_or_unbound_files(change):
    with pytest.raises(PlatformError):
        prepare_export([{**file(), **change}])


def test_export_rejects_duplicate_paths_and_excess_files():
    with pytest.raises(PlatformError):
        prepare_export([file(), file()])
    with pytest.raises(PlatformError):
        prepare_export([file(str(i)) for i in range(65)])


def test_checkpoint_binding_covers_scope_cursor_image_and_every_source_family():
    row = dict(
        org_id=uuid4(),
        id=uuid4(),
        run_id=uuid4(),
        project_id=uuid4(),
        generation=1,
        checkpoint_seq=4,
        checkpoint_digest="0" * 64,
        sandbox_lease_id=uuid4(),
        invocation_id=uuid4(),
        base_version=0,
        profile_id="approved",
        image_digest="sha256:" + "a" * 64,
        spec_digest="b" * 64,
        **{name: [] for name in SOURCES},
    )
    digest = binding_digest(row)
    for key, value in [
        ("generation", 2),
        ("run_id", uuid4()),
        ("project_id", uuid4()),
        ("checkpoint_seq", 5),
        ("profile_id", "different"),
        ("image_digest", "sha256:" + "c" * 64),
    ]:
        assert binding_digest({**row, key: value}) != digest
    for name in SOURCES:
        assert binding_digest({**row, name: [str(uuid4())]}) != digest
