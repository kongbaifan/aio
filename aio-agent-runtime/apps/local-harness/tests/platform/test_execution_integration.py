"""Deterministic execution/failure tests using real PostgreSQL and explicitly injected test drivers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import secrets
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, select, update

from app.db import schema as s
from app.db.provisioning import provision_agent, provision_model, provision_tool
from app.platform_errors import PlatformError
from app.runtime.actions import canonical_digest
from app.runtime.contracts import ModelTurn, PlannedCall
from app.runtime.execution import ExecutionStore
from app.runtime.worker import DurableWorker, ToolDrivers


class SyntheticModel:
    max_charge = Decimal("0.020000")

    def __init__(self, factory):
        self.factory = factory

    def charge(self, turn):
        return None if turn.input_tokens is None else Decimal("0.001000")

    async def stream(self, messages, tools):
        self.factory.calls.append(messages)
        if self.factory.fail:
            yield "partial output"
            raise RuntimeError("private-provider-response-must-not-be-persisted")
        if self.factory.no_tool or any(m["role"] == "tool" for m in messages):
            yield "Verified answer"
            yield ModelTurn(
                content="Verified answer",
                finish_reason="stop",
                input_tokens=None if self.factory.unknown_usage else 10,
                output_tokens=None if self.factory.unknown_usage else 5,
            )
        else:
            yield ModelTurn(
                tool_calls=(PlannedCall(id="provider-call-1", name="capture", arguments={"value": 7}),),
                finish_reason="tool_calls",
                input_tokens=10,
                output_tokens=2,
            )

    async def close(self):
        pass


class SyntheticModelFactory:
    def __init__(self, *, fail=False, no_tool=False, unknown_usage=False):
        self.calls = []
        self.fail, self.no_tool, self.unknown_usage = fail, no_tool, unknown_usage

    def create(self, definition):
        return SyntheticModel(self)


class EffectSink:
    def __init__(self, *, lose_response=False):
        self.operations = {}
        self.requests = []
        self.lose_response = lose_response

    async def execute(self, permit):
        self.requests.append(permit)
        self.operations.setdefault(permit.operation_key, {"captured": permit.arguments["value"]})
        if self.lose_response:
            raise RuntimeError("response lost after synthetic business effect")
        return self.operations[permit.operation_key]


@pytest.fixture
def scenario(tenant):
    def make(risk="R0"):
        t = dict(tenant)
        with t["admin"].begin() as c:
            model = provision_model(
                c,
                org_id=t["org"],
                owner_id=t["alice"].user_id,
                provider="test-only",
                model="deterministic-model",
                config={"test_fixture": True, "max_call_charge": "0.020000"},
            )
            tool = provision_tool(
                c,
                org_id=t["org"],
                owner_id=t["alice"].user_id,
                name="capture",
                driver="synthetic",
                risk=risk,
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                config={
                    "timeout_seconds": 60,
                    "approver_user_ids": [str(t["bob"].user_id)],
                    "resource_scope": {"system": "synthetic-sink"},
                },
            )
            agent = provision_agent(
                c,
                org_id=t["org"],
                owner_id=t["alice"].user_id,
                name="Durable test",
                version="v2",
                engine="local-harness-v2",
                instruction="Synthetic fixture only",
                manifest={"run_budget": "0.100000", "max_rounds": 4, "tools": [tool], "model": model},
            )
        session = t["service"].create_session(t["alice"], t["project"], agent, "Durable execution")["id"]
        request = {
            "message": "capture and answer",
            "agent_version_id": str(agent),
            "expected_session_revision": 0,
            "input_artifact_ids": [],
            "mode": "single",
        }
        run = t["service"].create_run(t["alice"], session, request, secrets.token_hex(16))
        t.update(
            store=ExecutionStore(t["db"], t["settings"]),
            execution_agent=agent,
            tool_definition=tool,
            model_definition=model,
            execution_session=session,
            run_id=run["run_id"],
            request=request,
        )
        return t

    return make


def worker(t, factory=None, sink=None, worker_id="durable-test"):
    return DurableWorker(
        t["store"],
        t["org"],
        worker_id,
        factory or SyntheticModelFactory(),
        ToolDrivers({"synthetic": sink or EffectSink()}),
    )


def claim(t, worker_id="manual-worker"):
    claimed = t["service"].claim_next(t["org"], worker_id)
    assert claimed and claimed["id"] == t["run_id"]
    return t["store"].handle_for_claim(claimed, worker_id)


def commit_tool_turn(t, handle):
    loaded = t["store"].load(handle)
    seq = loaded["run"]["checkpoint_seq"]
    call = t["store"].prepare_model_call(handle, seq, canonical_digest("test-request", {"turn": 1}), Decimal("0.02"))
    t["store"].start_model_call(handle, call["id"])
    turn = ModelTurn(
        tool_calls=(PlannedCall(id="call-1", name="capture", arguments={"value": 7}),),
        finish_reason="tool_calls",
        input_tokens=10,
        output_tokens=2,
    )
    seq = t["store"].complete_model_call(handle, seq, call["id"], turn, Decimal("0.001"))
    inv = t["store"].plan_tool(handle, seq)
    return seq, inv


def current(t, table, *conditions):
    with t["db"].transaction(t["alice"]) as c:
        return [dict(row) for row in c.execute(select(table).where(table.c.org_id == t["org"], *conditions)).mappings()]


def test_durable_worker_completes_model_tool_model_and_settles_once(scenario):
    t = scenario()
    factory, sink = SyntheticModelFactory(), EffectSink()
    outcome = asyncio.run(worker(t, factory, sink).run_once())
    assert outcome["state"] == "succeeded"
    assert len(factory.calls) == 2
    assert len(sink.operations) == 1
    assert current(t, s.runs)[0]["result"] == {"answer": "Verified answer"}
    budget = current(t, s.budgets, s.budgets.c.owner_id == t["alice"].user_id)[0]
    assert budget["reserved"] == 0
    assert budget["consumed"] == Decimal("0.002")
    assert len(current(t, s.ledger)) == 2
    assert len(current(t, s.checkpoints)) == 4
    assert len(current(t, s.messages, s.messages.c.session_id == t["execution_session"])) == 2
    assert current(t, s.dispatches)[0]["state"] == "succeeded"
    assert asyncio.run(worker(t, factory, sink).run_once()) is None
    assert len(sink.operations) == 1


@pytest.mark.parametrize("revoke_when", ["before_load", "after_load", "after_finish"])
def test_model_history_rechecks_and_inherits_source_authority(scenario, tmp_path, revoke_when):
    from app.workspaces.service import ArtifactService
    from app.workspaces.storage import BlobStore

    t = scenario()
    artifacts = ArtifactService(t["db"], BlobStore((tmp_path / "history-blobs").resolve()))
    slot = artifacts.create_upload(t["alice"], t["project"], "history-source.txt", 128)
    source = artifacts.upload(t["alice"], slot["upload_id"], b"synthetic protected source")
    with t["admin"].begin() as c:
        # Attach the fixture input before its worker claims it; never execute source bytes here.
        c.execute(
            update(s.runs)
            .where(s.runs.c.id == t["run_id"])
            .values(input={**t["request"], "input_artifact_ids": [str(source["id"])]})
        )
    assert asyncio.run(worker(t, SyntheticModelFactory(no_tool=True)).run_once())["state"] == "succeeded"
    sentinel = "history-private-content-must-not-be-laundered"
    with t["admin"].begin() as c:
        c.execute(
            update(s.messages)
            .where(s.messages.c.run_id == t["run_id"], s.messages.c.role == "assistant")
            .values(content={"text": sentinel})
        )

    def revoke():
        with t["admin"].begin() as c:
            c.execute(
                update(s.resources)
                .where(s.resources.c.id == source["id"])
                .values(status="disabled", revision=s.resources.c.revision + 1)
            )

    if revoke_when == "before_load":
        revoke()
    detail = t["service"].session_detail(t["alice"], t["execution_session"])
    request = {**t["request"], "message": "Continue from history", "expected_session_revision": detail["revision"]}
    next_run = t["service"].create_run(t["alice"], t["execution_session"], request, "history-next-" + revoke_when)
    next_t = {**t, "run_id": next_run["run_id"]}
    if revoke_when == "after_load":
        handle = claim(next_t)
        loaded = t["store"].load(handle)
        assert str(source["id"]) in loaded["run"]["provenance_source_ids"]
        assert sentinel in str(loaded["checkpoint"].messages)
        revoke()
        with pytest.raises(PlatformError):
            t["store"].model_definition(handle)
        with pytest.raises(PlatformError):
            t["store"].pulse(handle)
    else:
        factory = SyntheticModelFactory(no_tool=True)
        assert asyncio.run(worker(next_t, factory).run_once())["state"] == "succeeded"
        if revoke_when == "before_load":
            assert sentinel not in str(factory.calls)
            assert "source authorization changed" in str(factory.calls)
            return
        assert sentinel in str(factory.calls)
        revoke()
    with pytest.raises(PlatformError):
        t["service"].get_run(t["alice"], next_run["run_id"])
    with pytest.raises(PlatformError):
        t["service"].read_events(t["alice"], next_run["run_id"], 0)


def test_approval_suspends_worker_and_new_worker_resumes_saved_call(scenario):
    t = scenario("R2")
    factory, sink = SyntheticModelFactory(), EffectSink()
    outcome = asyncio.run(worker(t, factory, sink).run_once())
    assert outcome["state"] == "waiting_approval"
    assert len(factory.calls) == 1 and not sink.operations
    job = current(t, s.jobs)[0]
    assert job["state"] == "waiting_approval" and job["lease_owner"] is None
    a = current(t, s.approvals)[0]
    t["service"].decide_approval(t["bob"], a["id"], a["revision"], a["action_digest"], "approve")
    outcome = asyncio.run(worker(t, factory, sink, "replacement-worker").run_once())
    assert outcome["state"] == "succeeded"
    assert len(factory.calls) == 2 and len(sink.operations) == 1
    assert current(t, s.runs)[0]["generation"] == 2


def test_rejected_approval_is_a_tool_result_not_an_external_effect(scenario):
    t = scenario("R2")
    factory, sink = SyntheticModelFactory(), EffectSink()
    asyncio.run(worker(t, factory, sink).run_once())
    a = current(t, s.approvals)[0]
    t["service"].decide_approval(t["bob"], a["id"], a["revision"], a["action_digest"], "reject")
    outcome = asyncio.run(worker(t, factory, sink, "next-worker").run_once())
    assert outcome["state"] == "succeeded"
    assert not sink.operations and not current(t, s.dispatches)
    assert any("TOOL_DENIED" in m.get("content", "") for m in factory.calls[-1])


def test_after_send_failure_is_unknown_blocks_project_and_never_auto_retries(scenario):
    t = scenario()
    sink = EffectSink(lose_response=True)
    factory = SyntheticModelFactory()
    outcome = asyncio.run(worker(t, factory, sink).run_once())
    assert outcome["state"] == "recovery_required"
    assert len(sink.operations) == 1
    assert current(t, s.dispatches)[0]["state"] == "unknown"
    assert current(t, s.invocations)[0]["state"] == "outcome_unknown"
    assert len(current(t, s.blockers)) == 1
    assert asyncio.run(worker(t, factory, sink).run_once()) is None
    assert len(sink.requests) == 1
    with pytest.raises(PlatformError):
        t["service"].create_run(
            t["alice"], t["execution_session"], {**t["request"], "expected_session_revision": 1}, secrets.token_hex(16)
        )


def test_reconciliation_requires_distinct_authorized_actor_and_preserves_history(scenario):
    t = scenario()
    sink = EffectSink(lose_response=True)
    asyncio.run(worker(t, sink=sink).run_once())
    r = current(t, s.runs)[0]
    with pytest.raises(PlatformError):
        t["store"].reconcile(t["bob"], t["run_id"], r["revision"], "confirmed_success", "ticket/reconcile-1")
    with t["admin"].begin() as c:
        c.execute(
            insert(s.grants).values(
                id=uuid4(),
                org_id=t["org"],
                resource_id=t["run_id"],
                subject_id=t["bob"].user_id,
                action="run.reconcile",
            )
        )
    result = t["store"].reconcile(t["bob"], t["run_id"], r["revision"], "confirmed_success", "ticket/reconcile-1")
    assert result["state"] == "failed"  # External success does not mean entire Agent job succeeded.
    assert current(t, s.blockers)[0]["resolved_by"] == t["bob"].user_id
    assert current(t, s.invocations)[0]["state"] == "succeeded"
    assert len(sink.operations) == 1
    assert current(t, s.runs)[0]["result"]["reconciliation"] == "confirmed_success"


def test_prepared_dispatch_can_be_recovered_without_repeating_model_turn(scenario):
    t = scenario()
    old = claim(t)
    seq, inv = commit_tool_turn(t, old)
    prepared = t["store"].prepare_dispatch(old, seq, inv["id"])
    assert prepared["state"] == "prepared"
    with t["admin"].begin() as c:
        c.execute(
            update(s.jobs)
            .where(s.jobs.c.run_id == t["run_id"])
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    assert t["store"].recover_due(t["org"])[0]["state"] == "queued"
    with pytest.raises(PlatformError):
        t["store"].consume_dispatch(old, prepared["id"])
    factory, sink = SyntheticModelFactory(), EffectSink()
    result = asyncio.run(worker(t, factory, sink, "new-worker").run_once())
    assert result["state"] == "succeeded"
    assert len(factory.calls) == 1  # Only summary; the committed first turn was not regenerated.
    ds = current(t, s.dispatches)
    assert sorted(d["state"] for d in ds) == ["not_sent", "succeeded"]
    assert len({d["operation_key"] for d in ds}) == 1


def test_consumed_dispatch_is_one_shot_and_result_checkpoint_atomic(scenario):
    t = scenario()
    h = claim(t)
    seq, inv = commit_tool_turn(t, h)
    dispatch = t["store"].prepare_dispatch(h, seq, inv["id"])
    permit = t["store"].consume_dispatch(h, dispatch["id"])
    with pytest.raises(PlatformError):
        t["store"].consume_dispatch(h, dispatch["id"])
    result = {"captured": permit.arguments["value"]}
    new_seq = t["store"].complete_dispatch(h, seq, dispatch["id"], result)
    assert new_seq == seq + 1
    assert t["store"].complete_dispatch(h, seq, dispatch["id"], result) == new_seq
    loaded = t["store"].load(h)
    assert loaded["checkpoint"].phase == "model"
    assert loaded["checkpoint"].messages[-1]["role"] == "tool"
    assert len(current(t, s.checkpoints)) == new_seq


def test_expired_sent_dispatch_is_not_requeued(scenario):
    t = scenario()
    h = claim(t)
    seq, inv = commit_tool_turn(t, h)
    dispatch = t["store"].prepare_dispatch(h, seq, inv["id"])
    t["store"].consume_dispatch(h, dispatch["id"])
    with t["admin"].begin() as c:
        c.execute(
            update(s.jobs)
            .where(s.jobs.c.run_id == t["run_id"])
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    result = t["store"].recover_due(t["org"])
    assert result[0]["state"] == "recovery_required"
    assert t["service"].claim_next(t["org"], "new-worker") is None


def test_unknown_model_usage_holds_budget_instead_of_becoming_free(scenario):
    t = scenario()
    factory = SyntheticModelFactory(no_tool=True, unknown_usage=True)
    outcome = asyncio.run(worker(t, factory).run_once())
    assert outcome["state"] == "succeeded"
    reservation = current(t, s.reservations)[0]
    assert reservation["state"] == "held_unknown" and reservation["amount"] == Decimal("0.02")
    assert current(t, s.ledger)[0]["status"] == "unknown"
    budget = current(t, s.budgets, s.budgets.c.owner_id == t["alice"].user_id)[0]
    assert budget["reserved"] == Decimal("0.02") and budget["consumed"] == 0


def test_model_partial_failure_is_not_retried_or_reported_success(scenario):
    t = scenario()
    factory = SyntheticModelFactory(fail=True)
    result = asyncio.run(worker(t, factory).run_once())
    assert result["state"] == "recovery_required"
    assert current(t, s.model_calls)[0]["state"] == "unknown"
    assert len(factory.calls) == 1
    assert asyncio.run(worker(t, factory).run_once()) is None
    assert len(factory.calls) == 1
    assert "private-provider-response" not in str(current(t, s.events))


def test_unknown_or_missing_driver_never_dispatches_or_falls_back_to_host(scenario):
    t = scenario()
    w = DurableWorker(t["store"], t["org"], "no-driver", SyntheticModelFactory(), ToolDrivers())
    result = asyncio.run(w.run_once())
    assert result["state"] == "failed"
    assert current(t, s.runs)[0]["error_code"] == "TOOL_EXECUTOR_UNAVAILABLE"
    assert not current(t, s.dispatches)


def test_tool_definition_change_or_acl_revoke_between_plan_and_send_denies(scenario):
    t = scenario()
    h = claim(t)
    seq, inv = commit_tool_turn(t, h)
    dispatch = t["store"].prepare_dispatch(h, seq, inv["id"])
    with t["admin"].begin() as c:
        c.execute(
            update(s.resources).where(s.resources.c.id == UUID(t["tool_definition"]["id"])).values(status="disabled")
        )
    with pytest.raises(PlatformError):
        t["store"].consume_dispatch(h, dispatch["id"])
    assert current(t, s.dispatches)[0]["state"] == "prepared"


def test_queue_expiration_returns_preallocated_budget_and_no_model_call(scenario):
    t = scenario()
    with t["admin"].begin() as c:
        c.execute(
            update(s.runs)
            .where(s.runs.c.id == t["run_id"])
            .values(queue_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    result = t["store"].recover_due(t["org"])
    assert result[0]["state"] == "timed_out"
    assert current(t, s.reservations)[0]["state"] == "settled"
    assert current(t, s.budgets, s.budgets.c.owner_id == t["alice"].user_id)[0]["reserved"] == 0
    assert not current(t, s.model_calls)


def test_unknown_checkpoint_version_stops_instead_of_starting_from_prompt(scenario):
    t = scenario()
    h = claim(t)
    t["store"].load(h)
    with t["admin"].begin() as c:
        c.execute(update(s.checkpoints).where(s.checkpoints.c.run_id == t["run_id"]).values(schema_version=99))
        c.execute(
            update(s.jobs)
            .where(s.jobs.c.run_id == t["run_id"])
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    result = t["store"].recover_due(t["org"])
    assert result[0]["state"] == "failed"
    assert current(t, s.runs)[0]["error_code"] == "CHECKPOINT_UNSUPPORTED"
    assert t["service"].claim_next(t["org"], "new-worker") is None


def test_late_usage_receipt_releases_hold_and_appends_actual_charge_exactly_once(scenario):
    t = scenario()
    result = asyncio.run(worker(t, SyntheticModelFactory(no_tool=True, unknown_usage=True)).run_once())
    assert result["state"] == "succeeded"
    call = current(t, s.model_calls)[0]
    with t["admin"].begin() as c:
        c.execute(
            insert(s.grants).values(
                id=uuid4(),
                org_id=t["org"],
                resource_id=t["run_id"],
                subject_id=t["bob"].user_id,
                action="run.reconcile",
            )
        )
    one = t["store"].record_late_model_usage(t["bob"], call["id"], Decimal("0.03"), "billing/receipt-1")
    two = t["store"].record_late_model_usage(t["bob"], call["id"], Decimal("0.030000"), "billing/receipt-1")
    assert one == two
    ledger = current(t, s.ledger)
    assert len(ledger) == 2 and {r["producer"] for r in ledger} == {"model", "model_adjustment"}
    assert next(r for r in ledger if r["producer"] == "model")["status"] == "unknown"
    budget = current(t, s.budgets, s.budgets.c.owner_id == t["alice"].user_id)[0]
    assert budget["reserved"] == 0 and budget["consumed"] == Decimal("0.03")
    with pytest.raises(PlatformError):
        t["store"].record_late_model_usage(t["bob"], call["id"], Decimal("0.04"), "billing/receipt-2")


def test_live_cell_blocks_reconciliation_until_external_cleanup_is_confirmed(scenario):
    t = scenario()
    h = claim(t)
    t["store"].load(h)
    with t["admin"].begin() as c:
        c.execute(
            insert(s.sandbox_leases).values(
                id=uuid4(),
                org_id=t["org"],
                run_id=t["run_id"],
                generation=h.generation,
                target_slot="compute/main",
                role="compute",
                profile_id="synthetic",
                image_digest="sha256:" + "1" * 64,
                spec_digest="2" * 64,
                state="leased",
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            )
        )
        c.execute(
            insert(s.grants).values(
                id=uuid4(),
                org_id=t["org"],
                resource_id=t["run_id"],
                subject_id=t["bob"].user_id,
                action="run.reconcile",
            )
        )
    result = t["store"].abort(h, "PROCESS_STATE_LOST")
    assert result["state"] == "recovery_required" and result["cleanup_state"] == "pending"
    run = current(t, s.runs)[0]
    with pytest.raises(PlatformError) as exc:
        t["store"].reconcile(t["bob"], t["run_id"], run["revision"], "confirmed_no_effect", "incident/1")
    assert exc.value.code == "CLEANUP_UNCONFIRMED"
    assert current(t, s.blockers)[0]["resolved_at"] is None
    with t["admin"].begin() as c:
        c.execute(update(s.sandbox_leases).where(s.sandbox_leases.c.run_id == t["run_id"]).values(state="destroyed"))
    assert (
        t["store"].reconcile(t["bob"], t["run_id"], run["revision"], "confirmed_no_effect", "incident/1")["state"]
        == "failed"
    )
    assert current(t, s.blockers)[0]["resolved_at"] is not None


def test_result_and_checkpoint_failure_roll_back_as_one_transaction(scenario, monkeypatch):
    t = scenario()
    h = claim(t)
    seq, inv = commit_tool_turn(t, h)
    dispatch = t["store"].prepare_dispatch(h, seq, inv["id"])
    t["store"].consume_dispatch(h, dispatch["id"])
    original = t["store"]._save_checkpoint

    def fail_checkpoint(*args):
        raise RuntimeError("injected persistence failure after result update")

    monkeypatch.setattr(t["store"], "_save_checkpoint", fail_checkpoint)
    with pytest.raises(RuntimeError):
        t["store"].complete_dispatch(h, seq, dispatch["id"], {"captured": 7})
    assert current(t, s.dispatches)[0]["state"] == "dispatching"
    assert current(t, s.invocations)[0]["state"] == "executing"
    assert current(t, s.runs)[0]["checkpoint_seq"] == seq
    monkeypatch.setattr(t["store"], "_save_checkpoint", original)
    result = t["store"].abort(h, "RESULT_PERSISTENCE_FAILED")
    assert result["state"] == "recovery_required"


def test_concurrent_dispatch_consumption_returns_only_one_permit(scenario):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    t = scenario()
    h = claim(t)
    seq, inv = commit_tool_turn(t, h)
    dispatch = t["store"].prepare_dispatch(h, seq, inv["id"])
    barrier = Barrier(2)

    def consume():
        barrier.wait(timeout=5)
        try:
            return t["store"].consume_dispatch(h, dispatch["id"])
        except PlatformError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(consume), pool.submit(consume)]
        result = [f.result(timeout=15) for f in futures]
    assert sum(not isinstance(r, str) for r in result) == 1
    assert "DISPATCH_ALREADY_CONSUMED" in result


def test_current_approver_revocation_after_approval_denies_dispatch(scenario):
    t = scenario("R2")
    h = claim(t)
    seq, inv = commit_tool_turn(t, h)
    a = current(t, s.approvals)[0]
    t["service"].decide_approval(t["bob"], a["id"], a["revision"], a["action_digest"], "approve")
    d = t["store"].prepare_dispatch(h, seq, inv["id"])
    with t["admin"].begin() as c:
        c.execute(
            update(s.memberships)
            .where(s.memberships.c.org_id == t["org"], s.memberships.c.user_id == t["bob"].user_id)
            .values(active=False, revision=1)
        )
    with pytest.raises(PlatformError):
        t["store"].consume_dispatch(h, d["id"])
    assert current(t, s.dispatches)[0]["state"] == "prepared"


def test_model_call_cannot_underreserve_a_published_budget_bound(scenario):
    t = scenario()
    h = claim(t)
    loaded = t["store"].load(h)
    with pytest.raises(PlatformError) as exc:
        t["store"].prepare_model_call(h, loaded["run"]["checkpoint_seq"], "1" * 64, Decimal("0.000001"))
    assert exc.value.code == "MODEL_COST_POLICY_CHANGED"
    assert not current(t, s.model_calls)


def test_approval_query_does_not_grant_private_session_access(scenario):
    t = scenario("R2")
    asyncio.run(worker(t).run_once())
    approvals = t["service"].list_approvals(t["bob"])
    assert len(approvals) == 1
    detail = t["service"].approval_detail(t["bob"], approvals[0]["id"])
    assert detail["summary"] == {"tool": "capture", "risk": "R2"}
    assert "arguments" not in detail and "messages" not in detail
    with pytest.raises(PlatformError):
        t["service"].session_detail(t["bob"], t["execution_session"])
    assert t["service"].list_approvals(t["outsider"]) == []


def test_cancel_during_model_call_stops_worker_without_reporting_success(scenario):
    t = scenario()
    started = asyncio.Event()
    closed = []

    class SlowModel(SyntheticModel):
        async def stream(self, messages, tools):
            started.set()
            yield "partial"
            await asyncio.Event().wait()

        async def close(self):
            closed.append(True)

    class SlowFactory:
        def create(self, definition):
            return SlowModel(None)

    async def run():
        # Tests shorten the trusted lease configuration to exercise the real heartbeat path.
        from dataclasses import replace

        settings = replace(t["settings"], lease_seconds=2)
        store = ExecutionStore(t["db"], settings)
        task = asyncio.create_task(DurableWorker(store, t["org"], "slow-worker", SlowFactory()).run_once())
        await asyncio.wait_for(started.wait(), timeout=5)
        await asyncio.to_thread(t["service"].cancel_run, t["alice"], t["run_id"])
        return await asyncio.wait_for(task, timeout=5)

    result = asyncio.run(run())
    assert result["state"] == "recovery_required"  # Provider call may have been billed before cancellation.
    assert closed
    assert current(t, s.model_calls)[0]["state"] == "unknown"
    assert current(t, s.runs)[0]["result"] is None


def test_v1_to_v2_migration_preserves_existing_rows(postgres):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from psycopg import sql
    from sqlalchemy import create_engine, text
    from app.db import schema_v1

    _, admin, _ = postgres
    name = "aio_upgrade_" + secrets.token_hex(6)
    org = uuid4()
    engine = None
    try:
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            cursor = c.connection.driver_connection.cursor()
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            cursor.close()
        url = admin.url.set(database=name).render_as_string(hide_password=False)
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        config.attributes["database_url"] = url
        command.upgrade(config, "0001_platform")
        engine = create_engine(url, hide_parameters=True)
        with engine.begin() as c:
            c.execute(
                insert(schema_v1.organizations).values(
                    id=org, name="pre-upgrade-preserved", allowed_classifications=["internal"]
                )
            )
        command.upgrade(config, "head")
        with engine.connect() as c:
            assert (
                c.execute(select(s.organizations.c.name).where(s.organizations.c.id == org)).scalar_one()
                == "pre-upgrade-preserved"
            )
            from app.db.engine import SCHEMA_REVISION

            assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == SCHEMA_REVISION
            assert (
                c.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns WHERE table_name='aio_jobs' AND column_name='recovery_count'"
                    )
                ).scalar_one()
                == 1
            )
            assert c.execute(
                text("SELECT relforcerowsecurity FROM pg_class WHERE relname='aio_model_calls'")
            ).scalar_one()
    finally:
        if engine:
            engine.dispose()
        # This database is created only on the disposable integration server with a generated exact name.
        if not name.startswith("aio_upgrade_"):
            raise RuntimeError("Refusing cleanup of an unrelated database")
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            cursor = c.connection.driver_connection.cursor()
            cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
            cursor.close()


def test_authenticated_approval_and_reconciliation_api_are_scoped(scenario):
    from fastapi.testclient import TestClient
    from app.api.v2.application import create_platform_app
    from app.auth.service import AuthService, csrf_token

    t = scenario("R2")
    factory = SyntheticModelFactory()
    sink = EffectSink(lose_response=True)
    asyncio.run(worker(t, factory, sink).run_once())
    auth = AuthService(t["db"], t["settings"])
    token, _ = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["bob"].user_id))
    app = create_platform_app(t["settings"], database=t["db"])
    with TestClient(app, base_url=t["settings"].public_origin) as client:
        client.cookies.set(t["settings"].session_cookie, token)
        headers = {"Origin": t["settings"].public_origin, "X-CSRF-Token": csrf_token(token)}
        response = client.get("/api/v2/approvals")
        assert response.status_code == 200
        a = response.json()["items"][0]
        detail = client.get("/api/v2/approvals/" + a["id"]).json()
        assert "arguments" not in detail and "messages" not in detail
        decided = client.post(
            "/api/v2/approvals/" + a["id"] + "/decision",
            headers=headers,
            json={"expected_revision": a["revision"], "action_digest": a["action_digest"], "decision": "approve"},
        )
        assert decided.status_code == 200
        assert client.get("/api/v2/sessions/" + str(t["execution_session"])).status_code == 404
    asyncio.run(worker(t, factory, sink, "next-worker").run_once())
    r = current(t, s.runs)[0]
    token2, _ = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["bob"].user_id))
    app2 = create_platform_app(t["settings"], database=t["db"])
    with TestClient(app2, base_url=t["settings"].public_origin) as client:
        client.cookies.set(t["settings"].session_cookie, token2)
        headers = {"Origin": t["settings"].public_origin, "X-CSRF-Token": csrf_token(token2)}
        payload = {
            "expected_revision": r["revision"],
            "conclusion": "confirmed_success",
            "evidence_ref": "case/checked",
        }
        path = "/api/v2/runs/" + str(t["run_id"]) + "/reconcile"
        assert client.post(path, json=payload, headers=headers).status_code == 404
        with t["admin"].begin() as c:
            c.execute(
                insert(s.grants).values(
                    id=uuid4(),
                    org_id=t["org"],
                    resource_id=t["run_id"],
                    subject_id=t["bob"].user_id,
                    action="run.reconcile",
                )
            )
        assert (
            client.post(path, json={**payload, "actor_id": str(t["alice"].user_id)}, headers=headers).status_code == 422
        )
        response = client.post(path, json=payload, headers=headers)
        assert response.status_code == 200 and response.json()["state"] == "failed"
    assert len(sink.operations) == 1


def test_stopping_handle_cannot_forge_another_actor(scenario):
    from dataclasses import replace

    t = scenario()
    h = claim(t)
    forged = replace(h, principal=replace(t["bob"], service_actor_id=h.worker_id))
    with pytest.raises(PlatformError) as exc:
        t["store"].abort(forged, "WORKER_STOPPED")
    assert exc.value.code == "WORKER_IDENTITY_INVALID"
    assert current(t, s.runs)[0]["state"] == "preparing"
