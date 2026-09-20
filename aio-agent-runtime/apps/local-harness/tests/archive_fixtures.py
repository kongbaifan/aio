"""Synthetic Skill archives with real PG, Manager and Docker import processing."""

import asyncio
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
from uuid import uuid4
import zipfile

import httpx
import pytest
from sqlalchemy import update

from app.db import schema as s
from app.execution.sandbox_client import ManagerClient
from app.skills.archive_contracts import SkillArchivePrepare
from app.skills.archive_jobs import SkillArchiveJobs
from app.skills.archive_service import SkillArchiveService
from app.skills.archive_worker import SkillArchiveWorker
from app.workspaces.storage import BlobStore


def archive(*, name="import-fixture", native=False, source="return {'value': payload['value'] * 2}"):
    package = {
        "name": name,
        "version": "1.0.0",
        "description": "Synthetic archive capability",
        "source": "internal synthetic test",
        "license": "MIT",
        "instruction_path": "SKILL.md",
        "reference_paths": [],
        "entrypoints": []
        if native
        else [
            {
                "name": "double",
                "path": "double.py",
                "description": "Synthetic doubled value",
                "input_schema": {
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                "tests": [{"input": {"value": 21}, "expected": {"value": 42}}],
                "timeout_seconds": 10,
            }
        ],
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if not native:
            z.writestr("skill.json", json.dumps(package))
        z.writestr("SKILL.md", "# Synthetic package\nUse only approved capabilities.")
        z.writestr("double.py", "def run(payload):\n    " + source + "\n")
    return output.getvalue(), (
        {k: package[k] for k in ("name", "version", "description", "source", "license")} if native else None
    )


def request(t, raw, native=None, *, request_id=None):
    return SkillArchivePrepare(
        request_id=request_id or uuid4(),
        archive_format="zip",
        bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        sandbox_profile="import-test",
        native=native,
    )


@pytest.fixture
def archive_platform(tenant, tmp_path):
    image = os.environ.get("AIO_TEST_COMPUTE_IMAGE")
    if not image:
        pytest.skip("Archive import integration requires the approved real Docker image")
    from aio_sandbox_manager.api import create_app
    from aio_sandbox_manager.contracts import Profile
    from aio_sandbox_manager.docker_backend import DockerBackend
    from aio_sandbox_manager.journal import Journal
    from aio_sandbox_manager.service import SandboxManager
    from app.skills.validation import SkillValidationStore

    t = dict(tenant)
    with t["admin"].begin() as c:
        c.execute(update(s.memberships).where(s.memberships.c.org_id == t["org"]).values(role="org_admin"))
    token = "archive-manager-test-" + "m" * 40
    runtime_profiles, runtime_keys = (), None
    runtime = os.environ.get("AIO_TEST_DEPENDENCY_PROFILE")
    if runtime:
        from aio_runtime_policy import load_trust_keys
        from app.platform_settings import _sandbox_profiles

        runtime_profiles = _sandbox_profiles(
            {
                "PLATFORM_SANDBOX_PROFILES": runtime,
                "PLATFORM_RUNTIME_TRUST_KEYS": os.environ["AIO_TEST_RUNTIME_TRUST_KEYS"],
                "HARNESS_MODE": "platform-test",
            }
        )
        runtime_keys = load_trust_keys(os.environ["AIO_TEST_RUNTIME_TRUST_KEYS"])
    settings = replace(
        t["settings"],
        artifact_root=(tmp_path / "blobs").resolve(),
        manager_url="http://127.0.0.1:9999",
        manager_token=token,
        manager_control_token="archive-control-test-" + "c" * 40,
        sandbox_profiles=({"id": "import-test", "image_digest": image, "max_timeout_seconds": 30}, *runtime_profiles),
        skill_import_profile="import-test",
    )
    service = SkillArchiveService(t["db"], settings, BlobStore(settings.artifact_root))
    jobs = SkillArchiveJobs(service)
    validation = SkillValidationStore(t["db"], settings)

    class Guard:
        def __init__(self):
            self.operations = []

        def validate(self, operation, payload):
            self.operations.append(operation)
            if payload["spec"].get("target_slot") == "skill/archive-import":
                jobs.authorize(operation, payload)
            else:
                validation.authorize(operation, payload)

    guard = Guard()
    journal = Journal((tmp_path / "manager").resolve())
    profile = Profile("import-test", image, workspace_bytes=8 * 1024 * 1024, max_timeout_seconds=30)
    manager_profiles = {profile.id: profile}
    if runtime:
        raw_profile = json.loads(Path(runtime).read_text(encoding="utf-8"))["profiles"][0]
        manager_profiles[raw_profile["id"]] = Profile(**raw_profile)
    manager = SandboxManager(
        journal,
        DockerBackend(journal.installation_id),
        manager_profiles,
        guard,
        max_cells=2,
        runtime_keys=runtime_keys,
        allow_test_runtimes=True,
    )
    t.update(
        settings=settings,
        archives=service,
        import_jobs=jobs,
        validation=validation,
        guard=guard,
        manager=manager,
        manager_token=token,
        manager_app=create_app(manager, token, manage_lifecycle=False),
    )
    try:
        yield t
    finally:
        manager.close()


async def import_once(t, *, worker="archive-worker"):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=t["manager_app"]), base_url="http://manager.test"
    ) as http:
        client = ManagerClient("http://127.0.0.1:9999", t["manager_token"], client=http)
        return await SkillArchiveWorker(t["import_jobs"], client, t["org"], worker).run_once()


def execute_import(t, **kwargs):
    return asyncio.run(import_once(t, **kwargs))
