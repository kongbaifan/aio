"""One shared org/department reservation per Team Run: planner, steps, embedding and synthesis.

The documented rule is that a Team Run holds exactly ONE shared-budget allocation per bound
pool for its whole lifetime. Per-stage reservation would silently multiply a department cap by
the step count, and a standalone embedding intent folded into a Run hold would be a free
bypass, so both directions are asserted against real `aio_budget_allocations` rows.
"""

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

from app.admin.contracts import AgentCreate
from app.db import schema as s
from app.db.provisioning import provision_model
from app.knowledge.retrieval import KnowledgeDriver
from app.runtime.contracts import ModelTurn, PlannedCall
from app.runtime.team_contracts import TeamPolicy
from app.runtime.worker import DurableWorker, ToolDrivers
from knowledge_fixtures import base, ingest, upload
from team_fixtures import EffectSink, ScriptedModels, answer, claim, commit_turn, detail, plan, tool_call, worker
from test_shared_budgets import SyntheticModelFactory, assert_projection, department, reconciler, rows
from test_shared_budgets import scenario as scenario
from test_shared_budgets import worker as single_worker

# team_fixtures.ScriptedModels charges this per completed turn and bounds each call at 0.020000.
# The Agent manifest's run_budget (0.200000 in team_scenario) is the whole-Run hold, not a call bound.
TURN = Decimal("0.001000")
RUN_BUDGET = Decimal("0.200000")


def team_allocations(t):
    return [row for row in rows(t, s.budget_allocations) if row["run_id"] == t["run_id"]]


def charged(t):
    return sum(
        (row["actual_charge"] or Decimal(0) for row in rows(t, s.model_calls) if row["run_id"] == t["run_id"]),
        Decimal(0),
    )


def scopes(pools, expected):
    assert sorted(pools, key=str) == sorted(expected, key=str)
    return pools


def test_planner_steps_and_synthesis_share_exactly_one_allocation_per_bound_pool(tenant, team_scenario):
    """Requirement 1: one row per bound pool for the whole Run, never one per stage."""
    departments = [department(tenant, tenant["alice"]), department(tenant, tenant["alice"])]
    t = team_scenario(max_steps=3)
    # Admission binds every active scope up front and holds the published Run budget once.
    admitted = team_allocations(t)
    assert len(admitted) == 3
    assert all(row["reserved"] == RUN_BUDGET and row["consumed"] == 0 for row in admitted)
    models = ScriptedModels([plan([], [], []), answer("one"), answer("two"), answer("three"), answer("summary")])
    assert asyncio.run(worker(t, models).run_once())["state"] == "succeeded"
    calls = rows(t, s.model_calls)
    # Planner + every step + synthesis are five distinct paid calls inside ONE Run.
    assert sorted(call["team_stage"] for call in calls) == ["planning", "step", "step", "step", "synthesis"]
    assert {call["run_id"] for call in calls} == {t["run_id"]}
    assert [step["state"] for step in detail(t)["team"]["steps"]] == ["succeeded"] * 3
    allocations = team_allocations(t)
    pools = scopes(assert_projection(t), [None, *departments])
    # Five paid stages, still three allocations: organization plus each department, exactly once.
    assert len(allocations) == len(pools) == 3
    assert {row["run_id"] for row in allocations} == {t["run_id"]}
    assert all(row["embedding_call_id"] is None and row["origin"] == "admission" for row in allocations)
    assert {row["pool_id"] for row in allocations} == {pool["id"] for pool in pools.values()}
    assert len(rows(t, s.budget_allocations)) == 3
    assert len(rows(t, s.reservations)) == 1


def test_every_step_draws_down_the_single_shared_hold_to_the_real_run_total(tenant, team_scenario):
    """Requirement 2: shared consumption equals the Run's real charge and the hold returns to 0."""
    departments = [department(tenant, tenant["alice"]), department(tenant, tenant["alice"])]
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
    assert asyncio.run(worker(t, models, sink).run_once())["state"] == "succeeded"
    assert [step["state"] for step in detail(t)["team"]["steps"]] == ["succeeded", "succeeded"]
    total = charged(t)
    # Six paid calls across planning, both steps' tool rounds and synthesis.
    assert len(rows(t, s.model_calls)) == 6 and total == 6 * TURN
    assert len(sink.operations) == 2
    pools = scopes(assert_projection(t), [None, *departments])
    for pool in pools.values():
        assert pool["consumed"] == total and pool["reserved"] == 0
    allocations = team_allocations(t)
    assert len(allocations) == 3
    for row in allocations:
        assert row["consumed"] == total and row["reserved"] == 0
    reservation = rows(t, s.reservations)[0]
    assert reservation["state"] == "settled" and reservation["amount"] == 0


def test_department_cap_exhausted_mid_run_refuses_the_next_paid_step_truthfully(tenant, scenario, team_scenario):
    """Requirement 3: a mid-run department overage refuses the next step instead of exceeding the cap."""
    dept = department(tenant, tenant["alice"])
    other = scenario()
    admin = reconciler(other)
    admin.set_shared_budget(other["bob"], dept, Decimal("0.25"), 0)
    # A separate finished Run retains an unknown-usage hold of one model call bound.
    assert (
        asyncio.run(single_worker(other, SyntheticModelFactory(no_tool=True, unknown_usage=True)).run_once())["state"]
        == "succeeded"
    )
    assert assert_projection(other)[dept]["reserved"] == Decimal("0.02")
    # 0.02 held + 0.2 admitted = 0.22, inside the 0.25 department cap, so the Team Run IS admitted.
    t = team_scenario()
    assert assert_projection(t)[dept]["reserved"] == Decimal("0.22")
    handle = claim(t)
    seq = commit_turn(t, handle, plan([], []))
    assert t["store"].advance_team(handle, seq)
    seq = commit_turn(t, handle, answer("first step really finished"))
    assert t["store"].advance_team(handle, seq)
    assert [step["state"] for step in detail(t)["team"]["steps"]] == ["succeeded", "running"]
    # The other Run's real invoice arrives late and pushes the department past its cap mid-run.
    late = next(row for row in rows(other, s.model_calls) if row["run_id"] == other["run_id"])
    other["store"].record_late_model_usage(other["bob"], late["id"], Decimal("0.24"), "mid-run-department-overage")
    exhausted = assert_projection(t)[dept]
    assert exhausted["reserved"] + exhausted["consumed"] > exhausted["hard_limit"]
    models = ScriptedModels([answer("this paid step must never be sent")])
    result = asyncio.run(worker(t, models, worker_id=handle.worker_id).run_handle(handle))
    # Refused, not silently over cap: no third paid request and no fabricated success.
    assert result["state"] == "failed"
    assert not models.calls
    run = detail(t)
    assert run["error_code"] == "SHARED_BUDGET_EXCEEDED"
    assert run["team"]["stage"] == "stopped"
    steps = run["team"]["steps"]
    assert [step["state"] for step in steps] == ["succeeded", "failed"]
    assert steps[1]["result"]["reason_codes"] == ["SHARED_BUDGET_EXCEEDED"]
    assert steps[1]["result"]["answer"] == ""
    team_calls = [row for row in rows(t, s.model_calls) if row["run_id"] == t["run_id"]]
    assert len(team_calls) == 2 and all(row["state"] == "succeeded" for row in team_calls)
    # The refused Run still holds exactly one allocation per scope, now settled at its real charge.
    assert len(team_allocations(t)) == 2
    pools = assert_projection(t)
    assert pools[dept]["consumed"] == Decimal("0.242") and pools[dept]["reserved"] == 0
    assert pools[None]["consumed"] == Decimal("0.242")


def test_cancelling_a_team_run_releases_every_bound_scope_exactly_once(tenant, team_scenario):
    """Requirement 4: one cancellation for the whole team; a repeated cancel cannot release twice."""
    departments = [department(tenant, tenant["alice"]), department(tenant, tenant["alice"])]
    t = team_scenario(max_steps=3)
    handle = claim(t)
    seq = commit_turn(t, handle, plan([], [], []))
    assert t["store"].advance_team(handle, seq)
    seq = commit_turn(t, handle, answer("completed before cancel"))
    assert t["store"].advance_team(handle, seq)
    assert all(pool["reserved"] == RUN_BUDGET for pool in assert_projection(t).values())
    # Cancelling twice mid-flight must request one stop, never release the hold twice.
    assert [t["service"].cancel_run(t["alice"], t["run_id"])["state"] for _ in range(2)] == ["cancel_requested"] * 2
    assert all(pool["reserved"] == RUN_BUDGET for pool in assert_projection(t).values())
    models = ScriptedModels([])
    assert asyncio.run(worker(t, models, worker_id=handle.worker_id).run_handle(handle))["state"] == "cancelled"
    assert not models.calls
    assert [step["state"] for step in detail(t)["team"]["steps"]] == ["succeeded", "cancelled", "skipped"]
    total = charged(t)
    assert total == 2 * TURN
    pools = scopes(assert_projection(t), [None, *departments])
    assert all(pool["reserved"] == 0 and pool["consumed"] == total for pool in pools.values())
    # Repeat the cancel after the terminal state: the hold is already released exactly once.
    for _ in range(2):
        assert t["service"].cancel_run(t["alice"], t["run_id"])["state"] == "cancelled"
    assert all(pool["reserved"] == 0 and pool["consumed"] == total for pool in assert_projection(t).values())
    allocations = team_allocations(t)
    assert len(allocations) == 3
    assert all(row["reserved"] == 0 and row["consumed"] == total for row in allocations)
    reservation = rows(t, s.reservations)[0]
    assert reservation["state"] == "settled" and reservation["amount"] == 0


def test_in_run_query_embedding_folds_in_while_standalone_ingest_reserves_separately(knowledge_platform):
    """Requirement 5: an in-Run embedding joins the Run hold; a standalone ingest hold stays its own."""
    t = knowledge_platform
    dept = department(t, t["alice"])
    kb = base(t, hybrid=True)
    upload(t, kb, "年假与休假申请规则：至少提前三天提交。", title="休假规则")
    # Ingestion is a standalone embedding intent and must reserve against every scope by itself.
    assert asyncio.run(ingest(t))["state"] == "ready"
    standalone = rows(t, s.budget_allocations)
    assert len(standalone) == 2
    assert all(row["run_id"] is None and row["embedding_call_id"] is not None for row in standalone)
    with t["admin"].begin() as c:
        model = provision_model(
            c,
            org_id=t["org"],
            owner_id=t["alice"].user_id,
            provider="test-only",
            model="team-knowledge-fixture",
            config={"max_call_charge": "0.020000"},
        )
    agent = t["knowledge"].admin.create_agent(
        t["alice"],
        AgentCreate(
            name="Team knowledge agent",
            version="1",
            instruction="Summarize only authorized retrieved evidence",
            model_id=UUID(model["id"]),
            knowledge_ids=(kb["id"],),
            run_budget=Decimal("0.1"),
            max_rounds=6,
            team=TeamPolicy(max_steps=1, max_step_rounds=3),
        ),
    )
    alias = next(tool["name"] for tool in agent["manifest"]["tools"] if tool["driver"] == "knowledge.search")
    session = t["service"].create_session(t["alice"], t["project"], agent["id"], "Team knowledge")["id"]
    t["run_id"] = t["service"].create_run(
        t["alice"],
        session,
        {
            "message": "总结年假申请规则",
            "agent_version_id": str(agent["id"]),
            "expected_session_revision": 0,
            "input_artifact_ids": [],
            "mode": "team",
        },
        "team-kb-" + uuid4().hex,
    )["run_id"]
    models = ScriptedModels(
        [
            plan([alias]),
            ModelTurn(
                tool_calls=(PlannedCall(id="kb-1", name=alias, arguments={"query": "年假"}),),
                finish_reason="tool_calls",
                input_tokens=10,
                output_tokens=2,
            ),
            answer("步骤结论：至少提前三天提交。"),
            answer("最终总结：至少提前三天提交。"),
        ]
    )
    result = asyncio.run(
        DurableWorker(
            t["store"],
            t["org"],
            "team-kb-worker",
            models,
            ToolDrivers({"knowledge.search": KnowledgeDriver(t["retrieval"])}),
        ).run_once()
    )
    assert result["state"] == "succeeded", result
    assert t["embedding_factory"].requests[-1] == ["年假"]
    calls = rows(t, s.embedding_calls)
    query_call = next(row for row in calls if row["query_id"] is not None)
    job_call = next(row for row in calls if row["job_id"] is not None)
    # The in-Run query embedding is bound to the Run subject, so it takes no hold of its own.
    assert query_call["run_id"] == t["run_id"] and not query_call["standalone_reserved"]
    assert job_call["run_id"] is None and job_call["standalone_reserved"]
    allocations = rows(t, s.budget_allocations)
    pools = scopes(assert_projection(t), [None, dept])
    run_bound = [row for row in allocations if row["run_id"] == t["run_id"]]
    embedding_bound = [row for row in allocations if row["embedding_call_id"] is not None]
    assert len(run_bound) == 2 and len(embedding_bound) == 2 and len(allocations) == 4
    # The folded-in query embedding is NOT its own charge subject; only the ingest call is.
    assert not [row for row in allocations if row["embedding_call_id"] == query_call["id"]]
    assert {row["embedding_call_id"] for row in embedding_bound} == {job_call["id"]}
    # Four paid model stages plus the folded-in query embedding, settled once per scope.
    model_total = charged(t)
    assert model_total == 4 * TURN and query_call["actual_charge"] == TURN
    for pool in pools.values():
        assert pool["reserved"] == 0
        assert pool["consumed"] == model_total + query_call["actual_charge"] + job_call["actual_charge"]
    for row in run_bound:
        assert row["reserved"] == 0 and row["consumed"] == model_total + query_call["actual_charge"]
