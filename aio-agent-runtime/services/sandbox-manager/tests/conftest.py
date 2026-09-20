import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pytest

from aio_sandbox_manager.contracts import Profile
from aio_sandbox_manager.journal import Journal
from aio_sandbox_manager.docker_backend import DockerBackend
from aio_sandbox_manager.service import SandboxManager


class Guard:
    def __init__(self):
        self.denied = set()
        self.calls = []

    def validate(self, operation, payload):
        self.calls.append((operation, payload))
        if operation in self.denied:
            raise RuntimeError("synthetic revoked authority")


@pytest.fixture
def managed(tmp_path):
    image = os.environ.get("AIO_TEST_COMPUTE_IMAGE")
    if not image:
        pytest.skip("Real Linux compute image not selected; use test_sandbox.py")
    journal = Journal(tmp_path.resolve() / "manager")
    guard = Guard()
    backend = DockerBackend(journal.installation_id)
    profile = Profile(
        "test",
        image,
        workspace_bytes=2 * 1024 * 1024,
        workspace_inodes=128,
        output_bytes=4096,
        artifact_bytes=1024 * 1024,
        artifact_files=32,
        max_timeout_seconds=10,
    )
    manager = SandboxManager(journal, backend, {"test": profile}, guard, max_cells=2)
    try:
        yield manager, guard, profile
    finally:
        manager.close()
