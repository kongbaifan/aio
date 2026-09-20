"""Signed environment -> real Skill validation/review -> two real isolated Runs and immutable artifacts."""

import asyncio
from dataclasses import replace
from decimal import Decimal
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from aio_runtime_policy import load_trust_keys
from app.admin.contracts import AgentCreate, GrantCreate
from app.admin.service import AdminService
from app.db import schema as s
from app.db.provisioning import provision_model
from app.execution.coordinator import SandboxCoordinator
from app.execution.sandbox_client import ManagerClient, SandboxPythonDriver
from app.platform_errors import PlatformError
from app.platform_settings import _sandbox_profiles
from app.runtime.contracts import ModelTurn, PlannedCall
from app.runtime.execution import ExecutionStore
from app.runtime.service import PlatformService
from app.runtime.worker import DurableWorker, ToolDrivers
from app.skills.contracts import DependencySkillPackage, SkillCreate
from app.skills.service import SkillService
from app.skills.validation import SkillValidationStore
from app.workspaces.service import ArtifactService
from app.workspaces.storage import BlobStore
from skill_fixtures import publish_sample

ROOT = Path(__file__).resolve().parents[4]


def example(**changes):
    raw = json.loads((ROOT / "config/skill-packages/example-analytics.json").read_text(encoding="utf-8"))
    return DependencySkillPackage.model_validate({**raw, **changes})


@pytest.fixture
def dependency_platform(skill_registry, tmp_path):
    path = os.environ.get("AIO_TEST_DEPENDENCY_PROFILE")
    if not path:
        pytest.skip("Requires the actual signed dependency runtime")
    from aio_sandbox_manager.api import create_app
    from aio_sandbox_manager.contracts import Profile
    from aio_sandbox_manager.docker_backend import DockerBackend
    from aio_sandbox_manager.journal import Journal
    from aio_sandbox_manager.service import SandboxManager

    raw = json.loads(Path(path).read_text(encoding="utf-8"))["profiles"][0]
    profiles = _sandbox_profiles(
        {
            "PLATFORM_SANDBOX_PROFILES": path,
            "PLATFORM_RUNTIME_TRUST_KEYS": os.environ["AIO_TEST_RUNTIME_TRUST_KEYS"],
            "HARNESS_MODE": "platform-test",
        }
    )
    t = dict(skill_registry)
    settings = replace(t["settings"], sandbox_profiles=profiles, artifact_root=(tmp_path / "objects").resolve())
    store = ExecutionStore(t["db"], settings)
    artifacts = ArtifactService(t["db"], BlobStore(settings.artifact_root))
    coordinator = SandboxCoordinator(store, artifacts)
    validation = SkillValidationStore(t["db"], settings)
    journal = Journal((tmp_path / "manager").resolve())

    class Guard:
        def validate(self, operation, payload):
            if payload["spec"]["target_slot"] == "skill/validation":
                validation.authorize(operation, payload)
            else:
                coordinator.authorize(operation, payload)

    manager = SandboxManager(
        journal,
        DockerBackend(journal.installation_id),
        {raw["id"]: Profile(**raw)},
        Guard(),
        runtime_keys=load_trust_keys(os.environ["AIO_TEST_RUNTIME_TRUST_KEYS"]),
        allow_test_runtimes=True,
    )
    t.update(
        settings=settings,
        store=store,
        service=PlatformService(t["db"], settings),
        administration=AdminService(t["db"], settings),
        skills=SkillService(t["db"], settings),
        validation=validation,
        artifacts=artifacts,
        coordinator=coordinator,
        manager=manager,
        manager_app=create_app(manager, settings.manager_token, manage_lifecycle=False),
    )
    try:
        yield t
    finally:
        manager.close()


class Models:
    def create(self, definition):
        return self

    max_charge = Decimal(".02")

    def charge(self, turn):
        return Decimal(".001")

    async def stream(self, messages, tools):
        results = [item for item in messages if item["role"] == "tool"]
        if not results:
            yield ModelTurn(
                tool_calls=(
                    PlannedCall(id="synthetic-analytics", name="analytics_summary", arguments={"values": [2, 4, 6]}),
                ),
                finish_reason="tool_calls",
                input_tokens=10,
                output_tokens=5,
            )
        else:
            yield ModelTurn(content=results[-1]["content"], finish_reason="stop", input_tokens=10, output_tokens=5)

    async def close(self):
        pass


def create_agent(t, skill):
    with t["admin"].begin() as c:
        model = provision_model(
            c,
            org_id=t["org"],
            owner_id=t["alice"].user_id,
            provider="synthetic",
            model="synthetic",
            config={"max_call_charge": "0.020000"},
        )
    return t["administration"].create_agent(
        t["alice"],
        AgentCreate(
            name="Approved analytics",
            version="1",
            instruction="Use the exact approved dependency Skill",
            model_id=UUID(model["id"]),
            skill_ids=(skill["id"],),
            run_budget=Decimal(".1"),
            max_rounds=4,
        ),
    )


def create_run(t, principal, agent):
    project = t["service"].create_project(principal, "Private analytics")
    session = t["service"].create_session(principal, project["id"], agent["id"], "Locked dependencies")
    return t["service"].create_run(
        principal,
        session["id"],
        {
            "message": "summarize",
            "agent_version_id": str(agent["id"]),
            "expected_session_revision": 0,
            "mode": "single",
            "input_artifact_ids": [],
        },
        "analytics-" + uuid4().hex,
    )


def test_real_dependency_skill_validation_publication_and_two_user_artifacts(dependency_platform):
    t = dependency_platform

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=t["manager_app"])) as http:
            client = ManagerClient(t["settings"].manager_url, t["settings"].manager_token, client=http)
            skill = await publish_sample(t, package=example(), manager=client, profile="analytics")
            detail = t["skills"].detail(t["alice"], skill["id"])
            assert (
                detail["package"]["schema_version"] == 2 and detail["validations"][0]["results"][0]["kind"] == "runtime"
            )
            agent = create_agent(t, skill)
            t["administration"].set_grants(
                t["alice"],
                agent["id"],
                GrantCreate(
                    subject_type="user",
                    subject_id=t["bob"].user_id,
                    actions=("agent.read", "agent.use"),
                    include_dependencies=True,
                ),
            )
            driver = SandboxPythonDriver(t["coordinator"], client)
            for actor in [t["alice"], t["bob"]]:
                created = create_run(t, actor, agent)
                result = await DurableWorker(
                    t["store"], t["org"], "analytics-worker", Models(), ToolDrivers({"skill.python": driver})
                ).run_once()
                assert result["state"] == "succeeded" and result["cleanup_state"] == "clean", result
                value = t["service"].get_run(actor, created["run_id"])
                artifact = next(item for item in value["result"]["artifacts"] if item["path"] == "analytics-result.csv")
                data = t["artifacts"].download(actor, UUID(artifact["artifact_id"]))[1]
                assert data == b"value\n2\n4\n6\n"
                other = t["bob"] if actor == t["alice"] else t["alice"]
                with pytest.raises(PlatformError):
                    t["artifacts"].download(other, UUID(artifact["artifact_id"]))
            with t["db"].transaction(t["alice"]) as c:
                leases = (
                    c.execute(select(s.sandbox_leases).where(s.sandbox_leases.c.org_id == t["org"])).mappings().all()
                )
                assert len(leases) == 2 and all(row["state"] == "destroyed" for row in leases)
            assert not t["manager"].backend.client.containers.list(
                all=True, filters={"label": "aio.manager=" + t["manager"].journal.installation_id}
            )

    asyncio.run(run())


@pytest.mark.parametrize(
    "change", [{"runtime_manifest_digest": "f" * 64}, {"dependencies": [{"name": "numpy", "version": "0.0.1"}]}]
)
def test_dependency_declarations_cannot_request_unapproved_installations(dependency_platform, change):
    t = dependency_platform
    with pytest.raises(PlatformError) as error:
        t["skills"].create(t["alice"], SkillCreate(package=example(**change), sandbox_profile="analytics"))
    assert error.value.code in {"SKILL_RUNTIME_MISMATCH", "SKILL_DEPENDENCY_MISMATCH"}
    with t["db"].transaction(t["alice"]) as c:
        assert c.execute(select(s.skill_versions.c.id).where(s.skill_versions.c.org_id == t["org"])).first() is None


def test_withdrawn_dependency_profile_blocks_new_run_commands_but_allows_cleanup(dependency_platform):
    t = dependency_platform

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=t["manager_app"])) as http:
            client = ManagerClient(t["settings"].manager_url, t["settings"].manager_token, client=http)
            skill = await publish_sample(t, package=example(), manager=client, profile="analytics")
            agent = create_agent(t, skill)
            created = create_run(t, t["alice"], agent)
            t["store"].settings = replace(t["settings"], sandbox_profiles=())
            driver = SandboxPythonDriver(t["coordinator"], client)
            await DurableWorker(
                t["store"], t["org"], "withdrawn-worker", Models(), ToolDrivers({"skill.python": driver})
            ).run_once()
            with t["db"].transaction(t["alice"]) as c:
                invocations = (
                    c.execute(select(s.invocations).where(s.invocations.c.run_id == created["run_id"])).mappings().all()
                )
                assert invocations and not any(row["state"] == "succeeded" for row in invocations)
            assert not t["manager"].backend.client.containers.list(
                all=True, filters={"label": "aio.manager=" + t["manager"].journal.installation_id}
            )

    asyncio.run(run())


def test_agent_rejects_incompatible_compute_profiles_before_any_run(dependency_platform):
    t = dependency_platform

    async def run():
        from app.db.provisioning import provision_tool

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=t["manager_app"])) as http:
            client = ManagerClient(t["settings"].manager_url, t["settings"].manager_token, client=http)
            skill = await publish_sample(t, package=example(), manager=client, profile="analytics")
            with t["admin"].begin() as c:
                model = provision_model(
                    c,
                    org_id=t["org"],
                    owner_id=t["alice"].user_id,
                    provider="synthetic",
                    model="synthetic",
                    config={"max_call_charge": "0.020000"},
                )
                tool = provision_tool(
                    c,
                    org_id=t["org"],
                    owner_id=t["alice"].user_id,
                    name="other_environment",
                    driver="sandbox.python",
                    risk="R1",
                    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                    config={
                        "sandbox_profile": "another-profile",
                        "image_digest": t["settings"].sandbox_profiles[0]["image_digest"],
                        "network_profile_id": "none",
                        "timeout_seconds": 10,
                    },
                )
            with pytest.raises(PlatformError) as error:
                t["administration"].create_agent(
                    t["alice"],
                    AgentCreate(
                        name="Must not mix",
                        version="1",
                        instruction="fixed",
                        model_id=UUID(model["id"]),
                        skill_ids=(skill["id"],),
                    tool_ids=(UUID(tool["id"]),),
                    run_budget=Decimal(".1"),
                    max_rounds=4,
                    ),
                )
            assert error.value.code == "AGENT_RUNTIME_CONFLICT"

    asyncio.run(run())
