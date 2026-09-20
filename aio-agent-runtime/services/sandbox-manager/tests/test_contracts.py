from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aio_sandbox_manager.contracts import CellSpec, ExecuteRequest, InputFile, ManagerError, Profile, safe_relative


def spec():
    return dict(
        binding_id=uuid4(),
        org_id=uuid4(),
        run_id=uuid4(),
        generation=1,
        profile_id="test",
        image_digest="sha256:" + "1" * 64,
        deadline=datetime.now(timezone.utc) + timedelta(minutes=1),
    )


@pytest.mark.parametrize(
    "value", ["../x", "/etc/passwd", "a/../../b", "C:/Windows", "a\\b", "a//b", ".", "a/./b", "a\x00b"]
)
def test_paths_are_not_system_paths(value):
    with pytest.raises((ValueError, ValidationError)):
        safe_relative(value)


def test_private_protocol_forbids_privilege_mounts_and_unpinned_images():
    with pytest.raises(ValidationError):
        CellSpec(**spec(), privileged=True)
    with pytest.raises(ValidationError):
        CellSpec(**{**spec(), "image_digest": "python:latest"})
    with pytest.raises(ValidationError):
        CellSpec(**{**spec(), "deadline": datetime.now()})
    with pytest.raises(ValidationError):
        ExecuteRequest(spec=CellSpec(**spec()), dispatch_id=uuid4(), language="shell", code="id", timeout_seconds=1)


def test_input_digest_is_verified_not_trusted():
    item = InputFile(path="input.txt", sha256="1" * 64, content_b64="aGVsbG8=")
    with pytest.raises(ManagerError):
        item.bytes()


def test_profile_requires_memory_reserve_for_tmpfs():
    with pytest.raises(ValueError):
        Profile("test", "sha256:" + "1" * 64, memory_bytes=64 * 1024 * 1024, workspace_bytes=64 * 1024 * 1024)
