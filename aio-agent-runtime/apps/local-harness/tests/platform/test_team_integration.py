"""Real PostgreSQL team lifecycle, scoped dispatch, recovery and shared accounting."""

import asyncio
import json
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from app.db import schema as s
from app.platform_errors import PlatformError
from app.runtime.contracts import NotDispatched
from team_fixtures import ScriptedModels, EffectSink, answer, plan, tool_call, worker, claim, commit_turn, detail, rows


def test_one_run_shared_budget_unique_calls_and_only_final_answer_deltas(team_scenario):
    t = team_scenario()
    models = ScriptedModels(
        [
            plan(["capture"], ["capture"]),
            tool_call(),
            answer("first done"),
            tool_call(8),
            answer("second done"),
            answer("final summary"),
        ]
    )
    sink = EffectSink()
    result = asyncio.run(worker(t, models, sink).run_once())
    assert result["state"] == "succeeded"
    run = detail(t)
    assert run["team"]["stage"] == "completed"
    assert [step["state"] for step in run["team"]["steps"]] == ["succeeded", "succeeded"]
    assert [step["result"]["answer"] for step in run["team"]["steps"]] == ["first done", "second done"]
    assert models.calls[0]["tools"] == models.calls[-1]["tools"] == []
    assert "first done" in json.dumps(models.calls[3]["messages"])
    calls = sorted(rows(t, s.model_calls), key=lambda call: int(call["logical_call_id"].split(":")[1]))
    assert [call["logical_call_id"] for call in calls] == [f"model:{i}" for i in range(6)]
    assert [call["team_stage"] for call in calls] == ["planning", "step", "step", "step", "step", "synthesis"]
    assert len({call["model_config_id"] for call in calls}) == 1
    assert len(sink.operations) == 2
    assert all(permit.handle.run_id == t["run_id"] for permit in sink.requests)
    invocations = rows(t, s.invocations)
    assert len({item["team_step_id"] for item in invocations}) == 2
    events = rows(t, s.events)
    assert "".join(e["payload"]["text"] for e in events if e["kind"] == "answer.delta") == "final summary"
    assert any(e["kind"] == "team.output.delta" for e in events)
    assert len(rows(t, s.messages)) == 2
    assert sum(call["actual_charge"] for call in calls) == Decimal("0.006000")
    assert len(rows(t, s.reservations)) == 1
    assert asyncio.run(worker(t, models, sink).run_once()) is None
    assert len(models.calls) == 6


@pytest.mark.parametrize("case", ["invalid_plan", "planner_tool", "step_escalation", "synthesis_tool"])
def test_stage_or_plan_cannot_grant_capabilities(team_scenario, case):
    t = team_scenario()
    turns = {
        "invalid_plan": [answer('{"steps":[{"title":"x","task":"x","tools":["host_shell"]}]}')],
        "planner_tool": [tool_call()],
        "step_escalation": [plan([], []), tool_call()],
        "synthesis_tool": [plan([], []), answer("one"), answer("two"), tool_call()],
    }[case]
    models, sink = ScriptedModels(turns), EffectSink()
    assert asyncio.run(worker(t, models, sink).run_once())["state"] == "failed"
    assert not sink.requests and not rows(t, s.dispatches)
    assert detail(t)["error_code"] in {"TEAM_PLAN_INVALID", "TEAM_STAGE_TOOLS_FORBIDDEN", "TEAM_TOOL_NOT_ALLOWED"}
    assert all(call["actual_charge"] is not None for call in rows(t, s.model_calls))
    assert detail(t)["team"]["stage"] == "stopped"


def test_disabled_team_rejected_before_reservation_or_message(team_scenario):
    t = team_scenario(enabled=False, create=False)
    with pytest.raises(PlatformError) as error:
        t["service"].create_run(t["alice"], t["execution_session"], t["request"], secrets.token_hex(16))
    assert error.value.code == "TEAM_NOT_ENABLED"
    with t["admin"].connect() as c:
        assert not c.execute(select(s.runs).where(s.runs.c.session_id == t["execution_session"])).first()
        assert not c.execute(select(s.messages).where(s.messages.c.session_id == t["execution_session"])).first()
    assert t["service"].session_detail(t["alice"], t["execution_session"])["supported_modes"] == ["single"]


@pytest.mark.parametrize("decision", ["approved", "denied", "expired"])
def test_approval_releases_worker_then_resumes_exact_step_and_honest_summary(team_scenario, decision):
    t = team_scenario(risk="R2")
    models = ScriptedModels(
        [plan(["capture"], []), tool_call(), answer("model claims done"), answer("second done"), answer("summary")]
    )
    sink = EffectSink()
    assert asyncio.run(worker(t, models, sink).run_once())["state"] == "waiting_approval"
    assert len(models.calls) == 2 and not sink.requests
    assert rows(t, s.jobs)[0]["lease_owner"] is None
    approval = rows(t, s.approvals)[0]
    if decision == "expired":
        with t["admin"].begin() as c:
            c.execute(
                update(s.approvals)
                .where(s.approvals.c.id == approval["id"])
                .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )
    else:
        t["service"].decide_approval(
            t["bob"],
            approval["id"],
            approval["revision"],
            approval["action_digest"],
            "approve" if decision == "approved" else "reject",
        )
    result = asyncio.run(worker(t, models, sink, "team-resume").run_once())
    expected = "succeeded" if decision == "approved" else "failed"
    assert result["state"] == expected
    assert len(sink.requests) == (1 if decision == "approved" else 0)
    run = detail(t)
    assert run["team"]["steps"][0]["state"] == ("succeeded" if decision == "approved" else "denied")
    assert len(rows(t, s.invocations)) == 1 and len(models.calls) == 5
    if decision != "approved":
        assert "denied" in json.dumps(models.calls[-1]["messages"])
        assert "TOOL_DENIED" in run["result"]["answer"]
        assert run["error_code"] == "TEAM_STEPS_INCOMPLETE"


def test_restart_after_completed_step_checkpoint_does_not_replan_or_rerun(team_scenario):
    t = team_scenario()
    handle = claim(t)
    seq = commit_turn(t, handle, plan([], []))
    assert t["store"].advance_team(handle, seq)
    commit_turn(t, handle, answer("first output survives restart"))
    with t["admin"].begin() as c:
        c.execute(
            update(s.jobs)
            .where(s.jobs.c.run_id == t["run_id"])
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    models = ScriptedModels([answer("second after restart"), answer("summary after restart")])
    assert asyncio.run(worker(t, models, worker_id="replacement").run_once())["state"] == "succeeded"
    with pytest.raises(PlatformError):
        t["store"].advance_team(handle, seq)
    assert len(models.calls) == 2
    assert "first output survives restart" in json.dumps(models.calls[0]["messages"])
    assert len(rows(t, s.run_steps)) == 2
    assert len([event for event in rows(t, s.events) if event["kind"] == "team.step.completed"]) == 2
    assert len(rows(t, s.model_calls)) == 4
    assert detail(t)["generation"] > handle.generation


def test_cancel_between_steps_keeps_done_skips_future_and_never_summarizes(team_scenario):
    t = team_scenario(max_steps=3)
    handle = claim(t)
    seq = commit_turn(t, handle, plan([], [], []))
    t["store"].advance_team(handle, seq)
    seq = commit_turn(t, handle, answer("completed first"))
    t["store"].advance_team(handle, seq)
    t["service"].cancel_run(t["alice"], t["run_id"])
    models = ScriptedModels([])
    assert asyncio.run(worker(t, models, worker_id=handle.worker_id).run_handle(handle))["state"] == "cancelled"
    assert not models.calls
    assert [item["state"] for item in detail(t)["team"]["steps"]] == ["succeeded", "cancelled", "skipped"]


def test_budget_includes_synthesis_and_no_extra_call_after_exhaustion(team_scenario):
    t = team_scenario(budget="0.060000")
    models = ScriptedModels(
        [plan([], []), answer("one"), answer("two"), answer("must not send")], charge=Decimal("0.020000")
    )
    assert asyncio.run(worker(t, models).run_once())["state"] == "failed"
    assert detail(t)["error_code"] == "RUN_BUDGET_EXCEEDED"
    assert len(models.calls) == 3
    assert all(step["state"] == "succeeded" for step in detail(t)["team"]["steps"])
    assert detail(t)["team"]["stage"] == "stopped"
    assert sum(call["actual_charge"] for call in rows(t, s.model_calls)) == Decimal("0.060000")


def test_unknown_planner_usage_is_not_free(team_scenario):
    t = team_scenario()
    first = plan([], []).model_copy(update={"input_tokens": None, "output_tokens": None})
    models = ScriptedModels([first, answer("one"), answer("two"), answer("summary")])
    assert asyncio.run(worker(t, models).run_once())["state"] == "succeeded"
    reservation = rows(t, s.reservations)[0]
    assert reservation["state"] == "held_unknown"
    assert reservation["amount"] == Decimal("0.020000")
    assert next(call for call in rows(t, s.model_calls) if call["team_stage"] == "planning")["actual_charge"] is None


@pytest.mark.parametrize("limit", ["step", "global"])
def test_round_bound_retains_failed_step_and_reserves_final_synthesis(team_scenario, limit):
    t = team_scenario(max_step_rounds=1 if limit == "step" else 3, max_rounds=8 if limit == "step" else 4)
    models = ScriptedModels([plan(["capture"], []), tool_call(), answer("second done"), answer("truthful summary")])
    assert asyncio.run(worker(t, models).run_once())["state"] == "failed"
    steps = detail(t)["team"]["steps"]
    assert steps[0]["state"] == "failed" and steps[1]["state"] == "succeeded"
    assert steps[0]["result"]["reason_codes"] == ["TEAM_STEP_ROUND_LIMIT"]
    assert len(models.calls) == 4
    assert "TEAM_STEP_ROUND_LIMIT" in json.dumps(models.calls[-1]["messages"])


def test_known_not_sent_error_is_not_reported_as_success(team_scenario):
    class Unavailable:
        async def execute(self, permit):
            raise NotDispatched("TEST_NOT_SENT", "Synthetic executor unavailable", 503)

    t = team_scenario()
    models = ScriptedModels(
        [plan(["capture"], []), tool_call(), answer("claimed success"), answer("two"), answer("summary")]
    )
    assert asyncio.run(worker(t, models, Unavailable()).run_once())["state"] == "failed"
    assert detail(t)["team"]["steps"][0]["result"]["reason_codes"] == ["TOOL_FAILED"]
    assert rows(t, s.dispatches)[0]["state"] == "not_sent"


def test_uncertain_effect_stops_whole_team_without_blind_replay(team_scenario):
    t = team_scenario()
    models, sink = ScriptedModels([plan(["capture"], []), tool_call()]), EffectSink(lose_response=True)
    assert asyncio.run(worker(t, models, sink).run_once())["state"] == "recovery_required"
    assert [step["state"] for step in detail(t)["team"]["steps"]] == ["recovery_required", "skipped"]
    assert rows(t, s.invocations)[0]["state"] == "outcome_unknown"
    assert len(rows(t, s.blockers)) == 1
    assert asyncio.run(worker(t, models, sink).run_once()) is None
    assert len(models.calls) == 2 and len(sink.requests) == 1


def test_team_projection_reuses_run_authorization_and_force_rls(team_scenario):
    t = team_scenario()
    assert (
        asyncio.run(
            worker(t, ScriptedModels([plan([], []), answer("one"), answer("two"), answer("summary")])).run_once()
        )["state"]
        == "succeeded"
    )
    for principal in [t["bob"], t["outsider"]]:
        with pytest.raises(PlatformError):
            t["service"].get_run(principal, t["run_id"])
    with t["db"].transaction(t["outsider"]) as c:
        assert not c.execute(select(s.run_teams).where(s.run_teams.c.run_id == t["run_id"])).first()
        assert not c.execute(select(s.run_steps).where(s.run_steps.c.run_id == t["run_id"])).first()
        with pytest.raises(IntegrityError):
            c.execute(
                insert(s.run_steps).values(
                    org_id=t["outsider"].org_id,
                    id=t["project"],
                    run_id=t["run_id"],
                    ordinal=1,
                    definition={},
                    definition_digest="0" * 64,
                )
            )


def test_deadline_before_synthesis_does_not_start_an_extra_paid_request(team_scenario):
    t = team_scenario()
    handle = claim(t)
    for turn in [plan([], []), answer("one"), answer("two")]:
        seq = commit_turn(t, handle, turn)
        t["store"].advance_team(handle, seq)
    with t["admin"].begin() as c:
        c.execute(
            update(s.runs)
            .where(s.runs.c.id == t["run_id"])
            .values(deadline_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    models = ScriptedModels([])
    assert asyncio.run(worker(t, models, worker_id=handle.worker_id).run_handle(handle))["state"] == "timed_out"
    assert not models.calls and len(rows(t, s.model_calls)) == 3
    assert detail(t)["team"]["stage"] == "stopped"


def test_changed_step_definition_is_not_executed(team_scenario):
    t = team_scenario()
    handle = claim(t)
    seq = commit_turn(t, handle, plan([], []))
    t["store"].advance_team(handle, seq)
    first = min(rows(t, s.run_steps), key=lambda row: row["ordinal"])
    with t["admin"].begin() as c:
        c.execute(
            update(s.run_steps)
            .where(s.run_steps.c.id == first["id"])
            .values(definition={**first["definition"], "tools": ["capture"]})
        )
    models = ScriptedModels([])
    assert asyncio.run(worker(t, models, worker_id=handle.worker_id).run_handle(handle))["state"] == "failed"
    assert detail(t)["error_code"] == "TEAM_STATE_CORRUPT" and not models.calls


def test_prepared_model_cannot_be_rebound_to_another_step(team_scenario):
    from app.runtime.actions import canonical_digest

    t = team_scenario()
    handle = claim(t)
    seq = commit_turn(t, handle, plan([], []))
    t["store"].advance_team(handle, seq)
    loaded = t["store"].load(handle)
    call = t["store"].prepare_model_call(
        handle,
        loaded["run"]["checkpoint_seq"],
        canonical_digest("team-test", loaded["checkpoint"].messages),
        Decimal("0.020000"),
    )
    second = max(rows(t, s.run_steps), key=lambda row: row["ordinal"])
    with t["admin"].begin() as c:
        c.execute(update(s.model_calls).where(s.model_calls.c.id == call["id"]).values(team_step_id=second["id"]))
    with pytest.raises(PlatformError) as error:
        t["store"].start_model_call(handle, call["id"])
    assert error.value.code == "MODEL_CALL_CONFLICT"


def test_history_provenance_survives_planner_step_and_synthesis_context_resets(team_scenario, tmp_path):
    from app.workspaces.service import ArtifactService
    from app.workspaces.storage import BlobStore

    t = team_scenario()
    artifacts = ArtifactService(t["db"], BlobStore((tmp_path / "team-history").resolve()))
    slot = artifacts.create_upload(t["alice"], t["project"], "protected.txt", 128)
    source = artifacts.upload(t["alice"], slot["upload_id"], b"synthetic protected input")
    with t["admin"].begin() as c:
        c.execute(
            update(s.runs)
            .where(s.runs.c.id == t["run_id"])
            .values(input={**t["request"], "input_artifact_ids": [str(source["id"])]})
        )
    marker = "history-answer-derived-from-protected-source"
    assert (
        asyncio.run(worker(t, ScriptedModels([plan([], []), answer("one"), answer("two"), answer(marker)])).run_once())[
            "state"
        ]
        == "succeeded"
    )
    session = t["service"].session_detail(t["alice"], t["execution_session"])
    following = t["service"].create_run(
        t["alice"],
        t["execution_session"],
        {
            **t["request"],
            "message": "Continue with previous authorized answer",
            "expected_session_revision": session["revision"],
        },
        "team-history-continuation",
    )
    next_t = {**t, "run_id": following["run_id"]}
    models = ScriptedModels(
        [plan([], []), answer("continued one"), answer("continued two"), answer("continued summary")]
    )
    assert asyncio.run(worker(next_t, models).run_once())["state"] == "succeeded"
    assert all(marker in str(call["messages"]) for call in models.calls)
    with t["admin"].connect() as c:
        inherited = c.execute(
            select(s.runs.c.provenance_source_ids).where(s.runs.c.id == following["run_id"])
        ).scalar_one()
    assert str(source["id"]) in inherited
    with t["admin"].begin() as c:
        c.execute(update(s.resources).where(s.resources.c.id == source["id"]).values(status="disabled"))
    with pytest.raises(PlatformError):
        detail(next_t)
    with pytest.raises(PlatformError):
        t["service"].read_events(t["alice"], following["run_id"], 0)
