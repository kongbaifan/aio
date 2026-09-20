"""Actual Docker Skill scan/test/execute with real PostgreSQL authority; only the model is synthetic."""

import asyncio
from dataclasses import replace
from decimal import Decimal
import os
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.admin.contracts import AgentCreate, GrantCreate
from app.db import schema as s
from app.db.provisioning import provision_model, provision_tool
from app.execution.coordinator import SandboxCoordinator
from app.execution.sandbox_client import ManagerClient, SandboxPythonDriver
from app.platform_errors import PlatformError
from app.runtime.contracts import ModelTurn, PlannedCall
from app.runtime.actions import strict_json
from app.runtime.execution import ExecutionStore
from app.runtime.worker import DurableWorker, ToolDrivers
from app.skills.contracts import SkillPackage, SkillCreate, SkillValidate
from app.skills.reader import SkillReferenceDriver
from app.skills.worker import SkillValidationWorker
from app.workspaces.service import ArtifactService
from app.workspaces.storage import BlobStore
from skill_fixtures import sample_package, publish_sample


@pytest.fixture
def real_skill_manager(skill_registry, tmp_path):
    if not os.environ.get("AIO_TEST_COMPUTE_IMAGE"):
        pytest.skip("Real Skill execution requires explicit AIO_TEST_COMPUTE_IMAGE")
    from aio_sandbox_manager.api import create_app
    from aio_sandbox_manager.contracts import Profile
    from aio_sandbox_manager.docker_backend import DockerBackend
    from aio_sandbox_manager.journal import Journal
    from aio_sandbox_manager.service import SandboxManager

    t = dict(skill_registry)
    settings = replace(t["settings"], artifact_root=(tmp_path / "skill-blobs").resolve())
    artifacts = ArtifactService(t["db"], BlobStore(settings.artifact_root))
    store = ExecutionStore(t["db"], settings)
    coordinator = SandboxCoordinator(store, artifacts)
    journal = Journal((tmp_path / "skill-manager").resolve())
    backend = DockerBackend(journal.installation_id)
    profile = Profile("test", os.environ["AIO_TEST_COMPUTE_IMAGE"], output_bytes=8192)

    class Guard:
        def validate(self, operation, payload):
            if payload["spec"]["target_slot"] == "skill/validation":
                t["validation"].authorize(operation, payload)
            else:
                coordinator.authorize(operation, payload)

    manager = SandboxManager(journal, backend, {"test": profile}, Guard())
    app = create_app(manager, settings.manager_token, manage_lifecycle=False)
    t.update(
        settings=settings, artifacts=artifacts, store=store, coordinator=coordinator, manager=manager, manager_app=app
    )
    try:
        yield t
    finally:
        manager.close()


class SkillModel:
    max_charge = Decimal("0.020000")

    def __init__(self, factory):
        self.factory = factory

    def charge(self, turn):
        return Decimal("0.001000")

    async def stream(self, messages, tools):
        self.factory.messages = messages
        step = sum(message["role"] == "tool" for message in messages)
        if step == 0:
            call = PlannedCall(
                id="tamper",
                name="workspace_compute",
                arguments={
                    "code": "from pathlib import Path; Path('scripts').mkdir(exist_ok=True); Path('scripts/calculate.py').write_text('def run(payload): return {\"value\":999}')"
                },
            )
        elif step == 1:
            call = PlannedCall(
                id="read", name="read_department_calculation_reference", arguments={"path": "references/rules.md"}
            )
        elif step == 2:
            call = PlannedCall(id="calculate", name="department_calculate", arguments={"value": 7})
        else:
            yield ModelTurn(
                content="The fixed Skill returned 14.", finish_reason="stop", input_tokens=10, output_tokens=5
            )
            return
        yield ModelTurn(tool_calls=(call,), finish_reason="tool_calls", input_tokens=10, output_tokens=5)

    async def close(self):
        pass


class SkillFactory:
    def __init__(self):
        self.messages = []

    def create(self, definition):
        return SkillModel(self)


def test_real_skill_publication_fixed_script_reference_and_transitive_privacy(real_skill_manager, tmp_path):
    t = real_skill_manager

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=t["manager_app"])) as http:
            client = ManagerClient(t["settings"].manager_url, t["settings"].manager_token, client=http)
            package = sample_package().model_dump(mode="json")
            package["files"][-1]["content"] = (
                "import os, socket\nfrom pathlib import Path\ndef run(payload):\n    assert os.getuid() == 10001\n    assert 'PLATFORM_MANAGER_TOKEN' not in os.environ\n    assert 'PLATFORM_DATABASE_URL' not in os.environ\n    try:\n        Path('/usr/aio-unsafe').write_text('no')\n    except OSError:\n        pass\n    else:\n        raise ValueError('root filesystem was writable')\n    sock=socket.socket()\n    sock.settimeout(0.2)\n    try:\n        sock.connect(('1.1.1.1',443))\n    except OSError:\n        pass\n    else:\n        raise ValueError('network escape')\n    finally:\n        sock.close()\n    value = payload['value'] * 2\n    Path('skill-output.txt').write_text(str(value))\n    return {'value':value}\n"
            )
            skill = await publish_sample(t, package=SkillPackage.model_validate(package), manager=client)
            with t["admin"].begin() as c:
                model = provision_model(
                    c,
                    org_id=t["org"],
                    owner_id=t["alice"].user_id,
                    provider="synthetic",
                    model="synthetic",
                    config={"max_call_charge": "0.020000"},
                )
                raw = provision_tool(
                    c,
                    org_id=t["org"],
                    owner_id=t["alice"].user_id,
                    name="workspace_compute",
                    driver="sandbox.python",
                    risk="R1",
                    input_schema={
                        "type": "object",
                        "properties": {"code": {"type": "string"}},
                        "required": ["code"],
                        "additionalProperties": False,
                    },
                    config={
                        "sandbox_profile": "test",
                        "image_digest": os.environ["AIO_TEST_COMPUTE_IMAGE"],
                        "network_profile_id": "none",
                        "timeout_seconds": 10,
                    },
                )
            agent = t["administration"].create_agent(
                t["alice"],
                AgentCreate(
                    name="Shared Skill execution",
                    version="1",
                    instruction="Use fixed capabilities only.",
                    model_id=UUID(model["id"]),
                    tool_ids=(UUID(raw["id"]),),
                    skill_ids=(skill["id"],),
                    run_budget=Decimal("0.1"),
                    max_rounds=5,
                ),
            )
            t["administration"].set_grants(
                t["alice"],
                agent["id"],
                GrantCreate(
                    subject_type="user",
                    subject_id=t["bob"].user_id,
                    actions=("agent.use", "agent.read"),
                    include_dependencies=True,
                ),
            )
            project = t["service"].create_project(t["bob"], "Bob Skill work")
            session = t["service"].create_session(t["bob"], project["id"], agent["id"], "Private execution")
            run = t["service"].create_run(
                t["bob"],
                session["id"],
                {
                    "agent_version_id": str(agent["id"]),
                    "expected_session_revision": 0,
                    "message": "Compute using the fixed package",
                    "input_artifact_ids": [],
                    "mode": "single",
                },
                "real-skill-pipeline-run-idempotency",
            )
            driver = SandboxPythonDriver(t["coordinator"], client)
            factory = SkillFactory()
            result = await DurableWorker(
                t["store"],
                t["org"],
                "real-skill-worker",
                factory,
                ToolDrivers(
                    {"sandbox.python": driver, "skill.python": driver, "skill.read": SkillReferenceDriver(t["store"])}
                ),
            ).run_once()
            assert result["state"] == "succeeded", result
            final = t["service"].get_run(t["bob"], run["run_id"])
            artifact = next(file for file in final["result"]["artifacts"] if file["path"] == "skill-output.txt")
            metadata, data = t["artifacts"].download(t["bob"], UUID(artifact["artifact_id"]))
            assert data == b"14"  # The attacker-controlled workspace script returned 999 instead.
            assert metadata["path"] == "skill-output.txt"
            with t["db"].transaction(t["bob"]) as c:
                stored_file = t["artifacts"].require_artifact(c, t["bob"], UUID(artifact["artifact_id"]))
                assert stored_file["capability_source_ids"] == [str(skill["id"])]
                assert stored_file["capability_read_source_ids"] == [str(skill["id"])]
            assert any(m["role"] == "user" and "Skill reference guidance" in m["content"] for m in factory.messages)
            assert '"value":14' in str(factory.messages).replace(" ", "")
            assert not (tmp_path / "skill-output.txt").exists()
            with pytest.raises(PlatformError):
                t["service"].get_run(t["alice"], run["run_id"])
            grants = t["administration"].grants(t["alice"], skill["id"])["items"]
            read = next(g for g in grants if g["subject_id"] == t["bob"].user_id and g["action"] == "skill.read")
            t["administration"].remove_grant(t["alice"], skill["id"], read["id"], "user")
            assert len(t["skills"].list_authorized(t["bob"])) == 1  # use was not implicitly revoked.
            for action in (
                lambda: t["service"].get_run(t["bob"], run["run_id"]),
                lambda: t["artifacts"].download(t["bob"], UUID(artifact["artifact_id"])),
                lambda: t["service"].read_events(t["bob"], run["run_id"], 0),
            ):
                with pytest.raises(PlatformError):
                    action()
            history = t["service"].session_detail(t["bob"], session["id"])
            assert history["messages"][-1]["content"]["redacted"]
            with t["db"].transaction(t["bob"]) as c:
                assert all(
                    state == "destroyed"
                    for state in c.execute(
                        select(s.sandbox_leases.c.state).where(s.sandbox_leases.c.run_id == run["run_id"])
                    ).scalars()
                )
            return skill

    asyncio.run(run())


@pytest.mark.parametrize(
    "source",
    [
        "def run(payload):\n    return {'value':999}\n",
        "def broken syntax!!!",
        "def run(payload):\n    print('x' * 100000)\n    return {'value':14}\n",
        "import time\ndef run(payload):\n    time.sleep(3)\n    return {'value':14}\n",
    ],
)
def test_real_failed_or_hostile_skill_validation_cannot_publish(real_skill_manager, source):
    t = real_skill_manager
    package = sample_package().model_dump(mode="json")
    package["files"][-1]["content"] = source
    package["entrypoints"][0]["timeout_seconds"] = 1
    row = t["skills"].create(
        t["alice"], SkillCreate(package=SkillPackage.model_validate(package), sandbox_profile="test")
    )
    t["skills"].submit(t["alice"], row["id"], SkillValidate(expected_revision=0, reviewer_id=t["bob"].user_id))

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=t["manager_app"])) as http:
            client = ManagerClient(t["settings"].manager_url, t["settings"].manager_token, client=http)
            return await SkillValidationWorker(t["validation"], client, t["org"], "hostile-test-worker").run_once()

    result = asyncio.run(run())
    assert result["state"] == "failed", result
    detail = t["skills"].detail(t["alice"], row["id"])
    assert detail["state"] == "rejected"
    assert detail["validations"][0]["cleanup_state"] == "confirmed"
    assert t["skills"].list_authorized(t["alice"]) == []


def test_documented_text_package_example_passes_actual_isolated_validation(real_skill_manager):
    t = real_skill_manager
    path = Path(__file__).resolve().parents[4] / "config/skill-packages/example-calculation.json"
    package = SkillPackage.model_validate(strict_json(path.read_bytes(), max_bytes=262144))

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=t["manager_app"])) as http:
            client = ManagerClient(t["settings"].manager_url, t["settings"].manager_token, client=http)
            return await publish_sample(t, package=package, manager=client)

    published = asyncio.run(run())
    detail = t["skills"].detail(t["alice"], published["id"])
    assert detail["state"] == "published"
    assert len(detail["validations"][0]["results"]) == 3  # scanner and two documented examples
    assert detail["validations"][0]["cleanup_state"] == "confirmed"
