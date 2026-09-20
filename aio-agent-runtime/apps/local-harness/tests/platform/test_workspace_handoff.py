"""Actual PG/Manager/Docker filesystem handoff; the model and R2 effect sink are synthetic."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import select, update

from app.db import schema as s
from app.platform_errors import PlatformError
from app.workspaces.storage import MAX_BLOB_BYTES
from team_fixtures import ScriptedModels, EffectSink, plan, answer, tool_call, rows
from test_sandbox_pipeline import pipeline as pipeline, run_pipeline, team_python


def scenario(t, *, compute_after=True):
    turns = [
        plan(["python_compute"], ["capture", "python_compute"] if compute_after else ["capture"]),
        team_python(
            "from pathlib import Path; Path('carry.txt').write_text(str(int(Path('input.txt').read_text())*2)); Path('discard.txt').write_text('checkpoint-only-synthetic-data')"
        ),
        answer("First step produced carry.txt"),
        tool_call(),
    ]
    if compute_after:
        turns.append(
            team_python(
                "from pathlib import Path; Path('result.txt').write_text(Path('carry.txt').read_text()); Path('discard.txt').unlink()"
            )
        )
    turns += [answer("Second step result recorded"), answer("Final summary of confirmed step results")]
    return ScriptedModels(turns), EffectSink()


def approval(t):
    with t["db"].transaction(t["alice"]) as c:
        return (
            c.execute(
                select(s.approvals)
                .join(s.invocations, s.invocations.c.id == s.approvals.c.invocation_id)
                .where(s.invocations.c.run_id == t["run_id"])
            )
            .mappings()
            .one()
        )


def decide(t, value="approve"):
    item = approval(t)
    return t["service"].decide_approval(t["bob"], item["id"], item["revision"], item["action_digest"], value)


def get(t):
    return t["service"].get_run(t["alice"], t["run_id"])


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
@pytest.mark.parametrize("compute_after", [True, False])
def test_real_handoff_restores_new_generation_without_replaying_completed_code(pipeline, compute_after):
    t = pipeline
    models, sink = scenario(t, compute_after=compute_after)
    assert run_pipeline(t, models=models, sink=sink)["state"] == "waiting_approval"
    saved = rows(t, s.workspace_checkpoints)[0]
    old = rows(t, s.sandbox_leases)[0]
    lease = rows(t, s.workspace_leases)[0]
    assert saved["state"] == "ready" and saved["manager_acknowledged"]
    assert saved["reserved_bytes"] == sum(item["bytes"] for item in saved["manifest"]) < MAX_BLOB_BYTES
    assert old["state"] == "destroyed" and old["spec"] is None
    assert lease["state"] == "checkpointed" and lease["storage_reserved_bytes"] == 0
    assert rows(t, s.jobs)[0]["lease_owner"] is None
    assert len(models.calls) == 4 and not sink.requests
    with t["db"].transaction(t["alice"]) as c:
        assert c.execute(select(s.projects.c.head_version).where(s.projects.c.id == t["project"])).scalar_one() == 0
        assert not c.execute(select(s.artifacts.c.id).where(s.artifacts.c.run_id == t["run_id"])).first()
    assert not t["manager"].backend.client.containers.list(
        all=True, filters={"label": "aio.manager=" + t["manager"].journal.installation_id}
    )
    with t["manager"].journal.connect() as c:
        cached = c.execute("SELECT * FROM cells WHERE binding_id=?", (str(old["id"]),)).fetchone()
        assert cached["export_json"] is None and cached["spec_json"] == ""
    decide(t)
    assert run_pipeline(t, models=models, sink=sink, worker_id="restore-worker")["state"] == "succeeded"
    assert len(sink.requests) == 1 and len(sink.operations) == 1
    assert len(models.calls) == (7 if compute_after else 6)
    cells = rows(t, s.sandbox_leases)
    assert len(cells) == (2 if compute_after else 1)
    if compute_after:
        new = next(cell for cell in cells if cell["id"] != old["id"])
        assert new["generation"] > old["generation"] and new["backend_id"] != old["backend_id"]
    run = get(t)
    result = next(
        item for item in run["result"]["artifacts"] if item["path"] == ("result.txt" if compute_after else "carry.txt")
    )
    assert t["artifacts"].download(t["alice"], UUID(result["artifact_id"]))[1] == b"42"
    assert rows(t, s.workspace_checkpoints)[0]["state"] == "retiring"
    previous_revision = get(t)["revision"]
    assert t["store"].workspace.gc(t["org"]) == [saved["id"]]
    assert get(t)["revision"] > previous_revision
    after_gc = get(t)["revision"]
    t["store"].workspace.mark_acknowledged(t["org"], saved["id"])
    assert get(t)["revision"] == after_gc
    assert rows(t, s.workspace_checkpoints)[0]["reserved_bytes"] == 0
    assert t["artifacts"].download(t["alice"], UUID(result["artifact_id"]))[1] == b"42"
    discarded = next(item for item in saved["manifest"] if item["path"] == "discard.txt")
    if compute_after:
        with pytest.raises(PlatformError):
            t["store"].workspace.artifacts.blobs.get(t["org"], discarded["sha256"], discarded["bytes"])
    else:
        # The final artifact still references this hash; snapshot GC cannot delete it.
        assert t["store"].workspace.artifacts.blobs.get(t["org"], discarded["sha256"], discarded["bytes"])


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
@pytest.mark.parametrize("decision", ["reject", "expired"])
def test_denial_or_expiry_keeps_confirmed_files_but_never_sends_the_r2_action(pipeline, decision):
    t = pipeline
    models, sink = scenario(t, compute_after=False)
    assert run_pipeline(t, models=models, sink=sink)["state"] == "waiting_approval"
    if decision == "expired":
        item = approval(t)
        with t["admin"].begin() as c:
            c.execute(
                update(s.approvals)
                .where(s.approvals.c.id == item["id"])
                .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )
    else:
        decide(t, decision)
    assert run_pipeline(t, models=models, sink=sink, worker_id="denial-worker")["state"] == "failed"
    run = get(t)
    assert run["error_code"] == "TEAM_STEPS_INCOMPLETE" and run["team"]["steps"][1]["state"] == "denied"
    assert not sink.requests and len(models.calls) == 6
    carry = next(item for item in run["result"]["artifacts"] if item["path"] == "carry.txt")
    assert t["artifacts"].download(t["alice"], UUID(carry["artifact_id"]))[1] == b"42"


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
def test_concurrent_approval_decision_still_rotates_the_retired_generation(pipeline, monkeypatch):
    t = pipeline
    models, sink = scenario(t)
    original = t["store"].workspace.accept

    def accept_and_approve(*args):
        result = original(*args)
        decide(t)
        return result

    monkeypatch.setattr(t["store"].workspace, "accept", accept_and_approve)
    assert run_pipeline(t, models=models, sink=sink)["state"] == "queued"
    assert get(t)["state"] == "queued" and not sink.requests and len(models.calls) == 4
    assert run_pipeline(t, models=models, sink=sink, worker_id="decided-during-export")["state"] == "succeeded"
    assert len(sink.requests) == 1 and get(t)["generation"] == 2


class SimulatedProcessLoss(BaseException):
    pass


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
def test_crash_after_ready_checkpoint_before_releasing_worker_recovers_without_replaying(pipeline, monkeypatch):
    t = pipeline
    models, sink = scenario(t)
    original = t["store"].suspend_approval

    def crash(handle):
        raise SimulatedProcessLoss()

    monkeypatch.setattr(t["store"], "suspend_approval", crash)
    with pytest.raises(SimulatedProcessLoss):
        run_pipeline(t, models=models, sink=sink)
    assert rows(t, s.workspace_checkpoints)[0]["state"] == "ready"
    assert rows(t, s.jobs)[0]["state"] == "leased"
    monkeypatch.setattr(t["store"], "suspend_approval", original)
    with t["admin"].begin() as c:
        c.execute(
            update(s.jobs)
            .where(s.jobs.c.run_id == t["run_id"])
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    assert run_pipeline(t, models=models, sink=sink, worker_id="crash-recovery")["state"] == "waiting_approval"
    assert len(models.calls) == 4 and not sink.requests
    decide(t)
    assert run_pipeline(t, models=models, sink=sink, worker_id="crash-approved")["state"] == "succeeded"
    assert len(models.calls) == 7 and len(sink.requests) == 1


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
@pytest.mark.parametrize("problem", ["source_revoked", "bytes_corrupt", "manifest_changed", "quota", "head_changed"])
def test_restore_failure_is_checked_before_any_new_model_or_remote_effect(pipeline, problem):
    t = pipeline
    models, sink = scenario(t)
    assert run_pipeline(t, models=models, sink=sink)["state"] == "waiting_approval"
    saved = rows(t, s.workspace_checkpoints)[0]
    if problem == "bytes_corrupt":
        item = next(item for item in saved["manifest"] if item["path"] == "carry.txt")
        path = t["store"].workspace.artifacts.blobs._path(t["org"], item["sha256"])
        assert path.resolve().is_relative_to(t["settings"].artifact_root)
        path.write_bytes(b"xx")
    else:
        with t["admin"].begin() as c:
            if problem == "source_revoked":
                c.execute(update(s.resources).where(s.resources.c.id == t["uploaded"]["id"]).values(status="disabled"))
            elif problem == "manifest_changed":
                c.execute(
                    update(s.workspace_checkpoints)
                    .where(s.workspace_checkpoints.c.id == saved["id"])
                    .values(manifest=[])
                )
            elif problem == "quota":
                c.execute(
                    update(s.projects).where(s.projects.c.id == t["project"]).values(storage_limit_bytes=MAX_BLOB_BYTES)
                )
            else:
                c.execute(update(s.projects).where(s.projects.c.id == t["project"]).values(head_version=9))
    decide(t)
    result = run_pipeline(t, models=models, sink=sink, worker_id="invalid-restore")
    assert result["state"] == "failed", result
    assert len(models.calls) == 4 and not sink.requests


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
def test_checkpoint_is_private_and_incomplete_blob_write_never_becomes_resumable(pipeline, monkeypatch):
    t = pipeline
    models, sink = scenario(t)
    blobs = t["store"].workspace.artifacts.blobs
    original = blobs.put
    seen = []

    def fail_second(org, data):
        seen.append(data)
        if len(seen) == 2:
            raise OSError("synthetic bounded store interruption")
        return original(org, data)

    monkeypatch.setattr(blobs, "put", fail_second)
    assert run_pipeline(t, models=models, sink=sink)["state"] == "recovery_required"
    saved = rows(t, s.workspace_checkpoints)[0]
    assert saved["state"] == "bound" and saved["reserved_bytes"] > 0
    assert len(models.calls) == 4 and not sink.requests
    assert run_pipeline(t, models=models, sink=sink, worker_id="no-blind-restart") is None
    with t["db"].transaction(t["outsider"]) as c:
        assert not c.execute(select(s.workspace_checkpoints).where(s.workspace_checkpoints.c.id == saved["id"])).first()
    with pytest.raises(PlatformError):
        t["service"].get_run(t["bob"], t["run_id"])
    assert t["store"].workspace.gc(t["org"]) == []


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
def test_queued_handoff_cancel_releases_writer_and_retires_snapshot(pipeline, monkeypatch):
    t = pipeline
    models, sink = scenario(t)
    original = t["store"].workspace.accept

    def approved(*args):
        result = original(*args)
        decide(t)
        return result

    monkeypatch.setattr(t["store"].workspace, "accept", approved)
    assert run_pipeline(t, models=models, sink=sink)["state"] == "queued"
    from sqlalchemy.dialects.postgresql import JSONB

    with t["admin"].begin() as c:
        # v3-v8 rows may contain JSON null. That is still an unbound export, not a pending write.
        c.execute(
            update(s.workspace_leases)
            .where(s.workspace_leases.c.run_id == t["run_id"])
            .values(export_manifest=JSONB.NULL)
        )
    assert t["service"].cancel_run(t["alice"], t["run_id"])["state"] == "cancelled"
    assert rows(t, s.workspace_leases)[0]["state"] == "released"
    assert t["store"].workspace.gc(t["org"])
    assert rows(t, s.workspace_checkpoints)[0]["reserved_bytes"] == 0
    assert run_pipeline(t, models=models, sink=sink) is None
    assert len(models.calls) == 4 and not sink.requests


@pytest.mark.parametrize("pipeline", [{"mode": "team", "max_rounds": 12, "max_step_rounds": 6}], indirect=True)
def test_two_handoffs_keep_latest_files_and_gc_cannot_rollback_to_old_snapshot(pipeline):
    t = pipeline
    models = ScriptedModels(
        [
            plan(["python_compute"], ["capture", "python_compute"]),
            team_python("from pathlib import Path; Path('carry.txt').write_text('42')"),
            answer("first"),
            tool_call(7),
            team_python(
                "from pathlib import Path; Path('carry.txt').write_text(str(int(Path('carry.txt').read_text())+1))"
            ),
            tool_call(8),
            team_python("from pathlib import Path; Path('result.txt').write_text(Path('carry.txt').read_text())"),
            answer("second"),
            answer("summary"),
        ]
    )
    sink = EffectSink()
    assert run_pipeline(t, models=models, sink=sink)["state"] == "waiting_approval"
    decide(t)
    assert run_pipeline(t, models=models, sink=sink, worker_id="second-generation")["state"] == "waiting_approval"
    saved = sorted(rows(t, s.workspace_checkpoints), key=lambda row: row["generation"])
    assert [row["state"] for row in saved] == ["retiring", "ready"]
    assert t["store"].workspace.gc(t["org"]) == [saved[0]["id"]]
    with t["db"].transaction(t["alice"]) as c:
        latest = (
            c.execute(
                select(s.approvals)
                .join(s.invocations, s.invocations.c.id == s.approvals.c.invocation_id)
                .where(s.invocations.c.run_id == t["run_id"], s.approvals.c.state == "pending")
            )
            .mappings()
            .one()
        )
    t["service"].decide_approval(t["bob"], latest["id"], latest["revision"], latest["action_digest"], "approve")
    assert run_pipeline(t, models=models, sink=sink, worker_id="third-generation")["state"] == "succeeded"
    assert [permit.arguments["value"] for permit in sink.requests] == [7, 8]
    assert len(rows(t, s.sandbox_leases)) == 3 and len(models.calls) == 9
    result = next(item for item in get(t)["result"]["artifacts"] if item["path"] == "result.txt")
    assert t["artifacts"].download(t["alice"], UUID(result["artifact_id"]))[1] == b"43"


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
def test_lost_checkpoint_response_cleanup_confirms_stop_but_never_replays_or_unblocks(pipeline, monkeypatch):
    import asyncio
    import httpx
    from app.execution.sandbox_client import ManagerClient
    from app.workspaces.checkpoints import maintain_once

    t = pipeline
    models, sink = scenario(t)

    def crash(*args):
        raise SimulatedProcessLoss()

    monkeypatch.setattr(t["store"].workspace, "accept", crash)
    with pytest.raises(SimulatedProcessLoss):
        run_pipeline(t, models=models, sink=sink)
    assert rows(t, s.workspace_checkpoints)[0]["state"] == "preparing"
    assert rows(t, s.sandbox_leases)[0]["state"] == "ready"
    with t["admin"].begin() as c:
        c.execute(
            update(s.jobs)
            .where(s.jobs.c.run_id == t["run_id"])
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    t["store"].recover_due(t["org"])
    assert get(t)["state"] == "recovery_required"

    async def cleanup():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=t["manager_app"]), base_url="http://manager.test"
        ) as http:
            client = ManagerClient("http://127.0.0.1:9999", t["manager_token"], client=http)
            return await maintain_once(t["store"].workspace, client, t["org"])

    assert asyncio.run(cleanup()) == []
    assert get(t)["cleanup_state"] == "clean" and get(t)["state"] == "recovery_required"
    assert rows(t, s.sandbox_leases)[0]["state"] == "destroyed"
    assert rows(t, s.blockers)[0]["resolved_at"] is None
    assert rows(t, s.workspace_checkpoints)[0]["reserved_bytes"] == MAX_BLOB_BYTES
    assert len(models.calls) == 4 and not sink.requests


@pytest.mark.parametrize("pipeline", ["team"], indirect=True)
def test_dispatch_boundary_rejects_a_worker_that_skipped_workspace_resume(pipeline):
    t = pipeline
    models, sink = scenario(t)
    assert run_pipeline(t, models=models, sink=sink)["state"] == "waiting_approval"
    decide(t)
    claimed = t["service"].claim_next(t["org"], "skipped-restore")
    handle = t["store"].handle_for_claim(claimed, "skipped-restore")
    inv = next(item for item in rows(t, s.invocations) if item["risk_class"] == "R2")
    with t["admin"].begin() as c:
        # Simulate an older/incorrect worker advancing its engine state without the v9 handoff preflight.
        c.execute(update(s.runs).where(s.runs.c.id == t["run_id"]).values(state="running"))
    with pytest.raises(PlatformError) as rejected:
        t["store"].prepare_dispatch(handle, claimed["checkpoint_seq"], inv["id"])
    assert rejected.value.code == "WORKSPACE_HANDOFF_REQUIRED"
    assert not sink.requests
    loaded = t["store"].load(handle)
    assert t["store"].prepare_dispatch(handle, loaded["run"]["checkpoint_seq"], inv["id"])["state"] == "prepared"
