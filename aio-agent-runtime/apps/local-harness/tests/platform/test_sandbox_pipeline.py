"""Full Worker -> authenticated manager -> real Docker -> artifact PostgreSQL pipeline.

Only the language model is synthetic. User code, quotas, files, API authorization,
manager control checks, and lifecycle cleanup are real in these opt-in tests.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal
import os
from uuid import UUID

import pytest
import httpx
from sqlalchemy import select

from app.api.v2.application import create_platform_app
from app.db import schema as s
from app.db.provisioning import provision_agent, provision_model, provision_tool
from app.execution.coordinator import SandboxCoordinator
from app.execution.sandbox_client import ManagerClient, SandboxPythonDriver
from app.runtime.contracts import ModelTurn, PlannedCall
from app.runtime.execution import ExecutionStore
from app.runtime.worker import DurableWorker, ToolDrivers
from app.workspaces.storage import BlobStore
from app.workspaces.service import ArtifactService


class AnalysisModel:
    max_charge = Decimal("0.020000")

    def charge(self, turn):
        return Decimal("0.001000")

    async def stream(self, messages, tools):
        if any(m["role"] == "tool" for m in messages):
            yield "File analysis completed."
            yield ModelTurn(content="File analysis completed.", finish_reason="stop", input_tokens=10, output_tokens=5)
        else:
            code = "from pathlib import Path; n=int(Path('input.txt').read_text()); Path('result.txt').write_text(str(n*2)); print('processed')"
            yield ModelTurn(
                tool_calls=(PlannedCall(id="python-1", name="python_compute", arguments={"code": code}),),
                finish_reason="tool_calls",
                input_tokens=10,
                output_tokens=5,
            )

    async def close(self):
        pass


class AnalysisFactory:
    def create(self, definition):
        return AnalysisModel()


@pytest.fixture
def pipeline(tenant, tmp_path, request):
    image = os.environ.get("AIO_TEST_COMPUTE_IMAGE")
    if not image:
        pytest.skip("Real Docker pipeline requires explicit AIO_TEST_COMPUTE_IMAGE")
    from aio_sandbox_manager.api import create_app as manager_app
    from aio_sandbox_manager.contracts import Profile
    from aio_sandbox_manager.docker_backend import DockerBackend
    from aio_sandbox_manager.journal import Journal
    from aio_sandbox_manager.service import SandboxManager

    t = dict(tenant)
    param = getattr(request, "param", "single")
    options = param if isinstance(param, dict) else {"mode": param}
    team_mode = options["mode"] == "team"
    settings = replace(
        t["settings"],
        artifact_root=(tmp_path / "blobstore").resolve(),
        manager_control_token="control-authority-test-" + ("c" * 40),
    )
    blobs = BlobStore(settings.artifact_root)
    artifacts = ArtifactService(t["db"], blobs)
    store = ExecutionStore(t["db"], settings)
    coordinator = SandboxCoordinator(store, artifacts)
    journal = Journal((tmp_path / "manager").resolve())
    backend = DockerBackend(journal.installation_id)
    profile = Profile("test", image, workspace_bytes=4 * 1024 * 1024, artifact_bytes=2 * 1024 * 1024, output_bytes=4096)

    class Guard:
        def validate(self, operation, payload):
            coordinator.authorize(operation, payload)

    manager = SandboxManager(journal, backend, {"test": profile}, Guard())
    token = "worker-manager-test-" + ("m" * 40)
    app = manager_app(manager, token, manage_lifecycle=False)
    with t["admin"].begin() as c:
        model = provision_model(
            c,
            org_id=t["org"],
            owner_id=t["alice"].user_id,
            provider="fixture",
            model="fixture",
            config={"max_call_charge": "0.020000"},
        )
        tool = provision_tool(
            c,
            org_id=t["org"],
            owner_id=t["alice"].user_id,
            name="python_compute",
            driver="sandbox.python",
            risk="R1",
            input_schema={
                "type": "object",
                "properties": {"code": {"type": "string", "minLength": 1, "maxLength": 65536}},
                "required": ["code"],
                "additionalProperties": False,
            },
            config={
                "sandbox_profile": "test",
                "image_digest": image,
                "network_profile_id": "none",
                "timeout_seconds": 10,
            },
        )
        tools = [tool]
        if team_mode:
            tools.append(
                provision_tool(
                    c,
                    org_id=t["org"],
                    owner_id=t["alice"].user_id,
                    name="capture",
                    driver="synthetic",
                    risk="R2",
                    input_schema={
                        "type": "object",
                        "properties": {"value": {"type": "integer"}},
                        "required": ["value"],
                        "additionalProperties": False,
                    },
                    config={"timeout_seconds": 10, "approver_user_ids": [str(t["bob"].user_id)]},
                )
            )
        manifest = (
            {"run_budget": "0.200000", "max_rounds": 8, "model": model, "tools": tools}
            if team_mode
            else {
                "run_budget": "0.100000",
                "max_rounds": 4,
                "model": model,
                "tools": tools,
            }
        )
        if team_mode:
            manifest["max_rounds"] = options.get("max_rounds", 8)
            manifest["team"] = {"max_steps": 2, "max_step_rounds": options.get("max_step_rounds", 3)}
        agent = provision_agent(
            c,
            org_id=t["org"],
            owner_id=t["alice"].user_id,
            name="Real isolated analysis",
            version="1",
            engine="local-harness-v2",
            instruction="Fixture model uses the real isolated Python tool.",
            manifest=manifest,
        )
    slot = artifacts.create_upload(t["alice"], t["project"], "input.txt", 1024)
    uploaded = artifacts.upload(t["alice"], slot["upload_id"], b"21")
    session = t["service"].create_session(t["alice"], t["project"], agent, "real-cell-test")["id"]
    run = t["service"].create_run(
        t["alice"],
        session,
        {
            "message": "double the input file",
            "agent_version_id": str(agent),
            "expected_session_revision": 0,
            "mode": "team" if team_mode else "single",
            "input_artifact_ids": [str(uploaded["id"])],
        },
        "real-docker-pipeline-key",
    )
    t.update(
        settings=settings,
        artifacts=artifacts,
        store=store,
        coordinator=coordinator,
        manager=manager,
        manager_app=app,
        manager_token=token,
        run_id=run["run_id"],
        uploaded=uploaded,
        execution_agent=agent,
        execution_session=session,
    )
    try:
        yield t
    finally:
        manager.close()


def run_pipeline(t, *, models=None, sink=None, worker_id="real-pipeline-worker"):
    async def work():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=t["manager_app"]), base_url="http://manager.test"
        ) as http:
            client = ManagerClient("http://127.0.0.1:9999", t["manager_token"], client=http)
            driver = SandboxPythonDriver(t["coordinator"], client)
            drivers = {"sandbox.python": driver}
            if sink is not None:
                drivers["synthetic"] = sink
            result = await DurableWorker(
                t["store"], t["org"], worker_id, models or AnalysisFactory(), ToolDrivers(drivers)
            ).run_once()
            return result

    return asyncio.run(work())


def test_real_worker_executes_in_container_and_publishes_private_artifact(pipeline):
    t = pipeline
    result = run_pipeline(t)
    assert result["state"] == "succeeded", result
    run = t["service"].get_run(t["alice"], t["run_id"])
    assert run["cleanup_state"] == "clean"
    files = run["result"]["artifacts"]
    result_file = next(f for f in files if f["path"] == "result.txt")
    meta, data = t["artifacts"].download(t["alice"], UUID(result_file["artifact_id"]))
    assert data == b"42" and meta["scan_state"] == "structural_attachment"
    from app.platform_errors import PlatformError

    with pytest.raises(PlatformError) as denied:
        t["artifacts"].download(t["bob"], UUID(result_file["artifact_id"]))
    assert denied.value.status == 404
    with t["db"].transaction(t["alice"]) as c:
        assert c.execute(select(s.projects.c.head_version).where(s.projects.c.id == t["project"])).scalar_one() == 1
        lease = c.execute(select(s.sandbox_leases).where(s.sandbox_leases.c.run_id == t["run_id"])).mappings().one()
        assert lease["state"] == "destroyed"
        assert (
            c.execute(
                select(s.workspace_leases.c.state).where(s.workspace_leases.c.project_id == t["project"])
            ).scalar_one()
            == "released"
        )
    assert not t["manager"].backend.client.containers.list(
        all=True, filters={"label": "aio.manager=" + t["manager"].journal.installation_id}
    )
    assert not t["manager"].backend.client.volumes.list(
        filters={"label": "aio.manager=" + t["manager"].journal.installation_id}
    )


def test_manager_authorization_rpc_and_spec_forgery_are_checked_against_postgres(pipeline):
    from fastapi.testclient import TestClient
    from app.platform_errors import PlatformError

    t = pipeline
    # Execute first so the persisted binding/spec and completed result are available for scope checks.
    assert run_pipeline(t)["state"] == "succeeded"
    with t["db"].transaction(t["alice"]) as c:
        spec = c.execute(select(s.sandbox_leases.c.spec).where(s.sandbox_leases.c.run_id == t["run_id"])).scalar_one()
    app = create_platform_app(t["settings"], database=t["db"])
    with TestClient(app, base_url=t["settings"].public_origin) as client:
        path = "/internal/v1/sandbox/authorize"
        assert client.post(path, json={"operation": "status", "spec": spec}).status_code == 401
        headers = {"X-Manager-Token": t["settings"].manager_control_token}
        assert client.post(path, json={"operation": "status", "spec": spec}, headers=headers).json() == {
            "allowed": True
        }
        changed = {**spec, "generation": spec["generation"] + 1}
        assert client.post(path, json={"operation": "status", "spec": changed}, headers=headers).status_code == 403
        assert client.post(path, json={"operation": "execute", "spec": spec}, headers=headers).status_code == 403
    with pytest.raises(PlatformError):
        t["coordinator"].authorize("execute", {"spec": spec, "code": "print(9)"})


def test_source_revocation_prevents_further_model_or_code_actions(pipeline):
    from app.platform_errors import PlatformError
    from sqlalchemy import update

    t = pipeline
    claimed = t["service"].claim_next(t["org"], "source-revocation-worker")
    handle = t["store"].handle_for_claim(claimed, "source-revocation-worker")
    t["store"].load(handle)
    with t["admin"].begin() as c:
        c.execute(update(s.resources).where(s.resources.c.id == t["uploaded"]["id"]).values(status="disabled"))
    with pytest.raises(PlatformError):
        t["store"].load(handle)
    assert not t["manager"].journal.cells()


def test_revoked_input_blocks_run_result_and_replay_without_preventing_safe_cancel(pipeline):
    from app.platform_errors import PlatformError
    from sqlalchemy import update

    t = pipeline
    assert run_pipeline(t)["state"] == "succeeded"
    with t["db"].transaction(t["alice"]) as c:
        session_id = c.execute(select(s.runs.c.session_id).where(s.runs.c.id == t["run_id"])).scalar_one()
    with t["admin"].begin() as c:
        c.execute(update(s.resources).where(s.resources.c.id == t["uploaded"]["id"]).values(status="disabled"))
    with pytest.raises(PlatformError):
        t["service"].get_run(t["alice"], t["run_id"])
    with pytest.raises(PlatformError):
        t["service"].read_events(t["alice"], t["run_id"], 0)
    history = t["service"].session_detail(t["alice"], session_id)
    assert history["messages"][-1]["content"]["redacted"] is True
    assert t["service"].cancel_run(t["alice"], t["run_id"])["state"] == "succeeded"


def team_python(code):
    return ModelTurn(
        tool_calls=(PlannedCall(id="same-id-across-steps", name="python_compute", arguments={"code": code}),),
        finish_reason="tool_calls",
        input_tokens=10,
        output_tokens=5,
    )


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
def test_real_team_steps_share_one_cell_then_other_run_gets_a_new_writer(pipeline, monkeypatch):
    from team_fixtures import ScriptedModels, plan, answer
    from app.platform_errors import PlatformError

    t = pipeline
    premature_finalization = []
    complete = t["store"].complete_model_call

    def completed(handle, checkpoint_seq, call_id, turn, amount):
        seq = complete(handle, checkpoint_seq, call_id, turn, amount)
        with t["db"].transaction(t["alice"]) as c:
            stage = c.execute(
                select(s.run_teams.c.stage).where(s.run_teams.c.run_id == handle.run_id)
            ).scalar_one_or_none()
            spec = c.execute(
                select(s.sandbox_leases.c.spec).where(s.sandbox_leases.c.run_id == handle.run_id)
            ).scalar_one_or_none()
        if turn.finish_reason == "stop" and stage == "step" and spec:
            # Exercise the real Manager -> PG authorization contract, not just the Worker branch.
            with pytest.raises(PlatformError) as denied:
                t["coordinator"].authorize("finalize", {"spec": spec})
            assert denied.value.code == "MANAGER_ACTION_DENIED"
            premature_finalization.append(spec["binding_id"])
        return seq

    monkeypatch.setattr(t["store"], "complete_model_call", completed)
    models = ScriptedModels(
        [
            plan(["python_compute"], ["python_compute"]),
            team_python(
                "from pathlib import Path; Path('intermediate.txt').write_text(str(int(Path('input.txt').read_text())*2))"
            ),
            answer("Created intermediate.txt"),
            team_python(
                "from pathlib import Path; Path('result.txt').write_text(Path('intermediate.txt').read_text())"
            ),
            answer("Read prior output and created result.txt"),
            answer("Both sequential steps completed"),
        ]
    )
    assert run_pipeline(t, models=models)["state"] == "succeeded"
    assert len(premature_finalization) == 2
    run = t["service"].get_run(t["alice"], t["run_id"])
    assert [step["state"] for step in run["team"]["steps"]] == ["succeeded", "succeeded"]
    artifact = next(item for item in run["result"]["artifacts"] if item["path"] == "result.txt")
    assert t["artifacts"].download(t["alice"], UUID(artifact["artifact_id"]))[1] == b"42"
    with t["db"].transaction(t["alice"]) as c:
        cell = c.execute(select(s.sandbox_leases).where(s.sandbox_leases.c.run_id == t["run_id"])).mappings().one()
        assert cell["state"] == "destroyed" and cell["target_slot"] == "compute/main"
        assert len(c.execute(select(s.invocations.c.id).where(s.invocations.c.run_id == t["run_id"])).all()) == 2
    session = t["service"].session_detail(t["alice"], t["execution_session"])
    followup = t["service"].create_run(
        t["alice"],
        t["execution_session"],
        {
            "message": "Use an independent writer",
            "agent_version_id": str(t["execution_agent"]),
            "expected_session_revision": session["revision"],
            "mode": "single",
            "input_artifact_ids": [],
        },
        "separate-run-workspace-check",
    )
    next_t = {**t, "run_id": followup["run_id"]}
    assert (
        run_pipeline(
            next_t,
            models=ScriptedModels(
                [
                    team_python("from pathlib import Path; Path('result.txt').write_text('999')"),
                    answer("New run wrote a separate result"),
                ]
            ),
        )["state"]
        == "succeeded"
    )
    with t["db"].transaction(t["alice"]) as c:
        other = (
            c.execute(select(s.sandbox_leases).where(s.sandbox_leases.c.run_id == followup["run_id"])).mappings().one()
        )
        assert other["id"] != cell["id"] and other["backend_id"] and other["backend_id"] != cell["backend_id"]
    assert t["artifacts"].download(t["alice"], UUID(artifact["artifact_id"]))[1] == b"42"


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
def test_real_team_nonzero_exit_cannot_be_overwritten_by_model_success(pipeline):
    from team_fixtures import ScriptedModels, plan, answer

    t = pipeline
    models = ScriptedModels(
        [
            plan(["python_compute"], []),
            team_python("raise ValueError('synthetic step failed')"),
            answer("Model wrongly says success"),
            answer("Second task done"),
            answer("Model claims all done"),
        ]
    )
    assert run_pipeline(t, models=models)["state"] == "failed"
    run = t["service"].get_run(t["alice"], t["run_id"])
    assert run["error_code"] == "TEAM_STEPS_INCOMPLETE"
    assert run["team"]["steps"][0]["result"]["reason_codes"] == ["TOOL_EXECUTION_FAILED"]
    assert "任务未全部完成" in run["result"]["answer"]
    assert "TOOL_EXECUTION_FAILED" in str(models.calls[-1]["messages"])


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
def test_worker_cannot_release_live_writer_without_checkpoint_hook(pipeline, monkeypatch):
    from team_fixtures import ScriptedModels, EffectSink, plan, answer, tool_call

    t = pipeline

    async def no_checkpoint(self, handle):
        pass

    monkeypatch.setattr(SandboxPythonDriver, "suspend", no_checkpoint)
    models = ScriptedModels(
        [
            plan(["python_compute"], ["capture"]),
            team_python("print('known compute result')"),
            answer("First step completed"),
            tool_call(),
        ]
    )
    sink = EffectSink()
    assert run_pipeline(t, models=models, sink=sink)["state"] == "failed"
    run = t["service"].get_run(t["alice"], t["run_id"])
    assert run["error_code"] == "WORKSPACE_CHECKPOINT_REQUIRED"
    with t["db"].transaction(t["alice"]) as c:
        assert (
            c.execute(
                select(s.workspace_leases.c.storage_reserved_bytes).where(s.workspace_leases.c.run_id == t["run_id"])
            ).scalar_one()
            == 0
        )
    assert len(models.calls) == 4 and not sink.requests
    assert [step["state"] for step in run["team"]["steps"]] == ["succeeded", "failed"]
