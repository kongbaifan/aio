"""Explicit synthetic models/effects; identity, budgets, fencing and storage use PostgreSQL."""

import json
import secrets
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.provisioning import provision_agent, provision_model, provision_tool
from app.runtime.actions import canonical_digest
from app.runtime.contracts import ModelTurn, PlannedCall
from app.runtime.execution import ExecutionStore
from app.runtime.worker import DurableWorker, ToolDrivers


def answer(text, *, unknown_usage=False):
    return ModelTurn(
        content=text,
        finish_reason="stop",
        input_tokens=None if unknown_usage else 10,
        output_tokens=None if unknown_usage else 5,
    )


def plan(*tools):
    return answer(
        json.dumps(
            {
                "steps": [
                    {"title": f"Step {i}", "task": f"Perform synthetic step {i}", "tools": list(names)}
                    for i, names in enumerate(tools, 1)
                ]
            }
        )
    )


def tool_call(value=7, *, name="capture", call_id="reused-provider-id"):
    return ModelTurn(
        tool_calls=(PlannedCall(id=call_id, name=name, arguments={"value": value}),),
        finish_reason="tool_calls",
        input_tokens=10,
        output_tokens=2,
    )


class ScriptedModels:
    def __init__(self, turns, *, charge=Decimal("0.001000")):
        self.turns, self.calls, self.amount = list(turns), [], charge

    def create(self, definition):
        factory = self

        class Model:
            max_charge = Decimal("0.020000")

            def charge(self, turn):
                return factory.amount if turn.input_tokens is not None else None

            async def stream(self, messages, tools):
                factory.calls.append({"messages": messages, "tools": tools, "model_id": definition["id"]})
                if not factory.turns:
                    raise AssertionError("Unexpected extra paid model request")
                item = factory.turns.pop(0)
                if isinstance(item, Exception):
                    raise item
                if item.content:
                    yield item.content
                yield item

            async def close(self):
                pass

        return Model()


class EffectSink:
    def __init__(self, *, lose_response=False):
        self.requests, self.operations = [], {}
        self.lose_response = lose_response

    async def execute(self, permit):
        self.requests.append(permit)
        result = self.operations.setdefault(permit.operation_key, {"value": permit.arguments["value"]})
        if self.lose_response:
            raise RuntimeError("synthetic downstream effect succeeded; response lost")
        return result


@pytest.fixture
def team_scenario(tenant):
    def make(*, risk="R0", max_steps=2, max_rounds=8, max_step_rounds=3, budget="0.200000", enabled=True, create=True):
        t = dict(tenant)
        with t["admin"].begin() as c:
            model = provision_model(
                c,
                org_id=t["org"],
                owner_id=t["alice"].user_id,
                provider="test-only",
                model="team-fixture",
                config={"max_call_charge": "0.020000"},
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
                config={"timeout_seconds": 60, "approver_user_ids": [str(t["bob"].user_id)]},
            )
            manifest = {"run_budget": budget, "max_rounds": max_rounds, "tools": [tool], "model": model}
            if enabled:
                manifest["team"] = {"max_steps": max_steps, "max_step_rounds": max_step_rounds}
            agent = provision_agent(
                c,
                org_id=t["org"],
                owner_id=t["alice"].user_id,
                name="Team fixture",
                version="1",
                engine="local-harness-v2",
                instruction="Synthetic team task only",
                manifest=manifest,
            )
        session = t["service"].create_session(t["alice"], t["project"], agent, "Team test")["id"]
        request = {
            "message": "Execute a synthetic sequential team task",
            "agent_version_id": str(agent),
            "expected_session_revision": 0,
            "input_artifact_ids": [],
            "mode": "team",
        }
        t.update(
            store=ExecutionStore(t["db"], t["settings"]),
            execution_agent=agent,
            execution_session=session,
            tool_definition=tool,
            model_definition=model,
            manifest=manifest,
            request=request,
        )
        if create:
            t["run_id"] = t["service"].create_run(t["alice"], session, request, secrets.token_hex(16))["run_id"]
        return t

    return make


def worker(t, models, sink=None, worker_id="team-test"):
    return DurableWorker(t["store"], t["org"], worker_id, models, ToolDrivers({"synthetic": sink or EffectSink()}))


def claim(t, worker_id="manual-team"):
    claimed = t["service"].claim_next(t["org"], worker_id)
    assert claimed and claimed["id"] == t["run_id"]
    return t["store"].handle_for_claim(claimed, worker_id)


def commit_turn(t, handle, turn, amount=Decimal("0.001000")):
    loaded = t["store"].load(handle)
    digest = canonical_digest("team-test-request", {"messages": loaded["checkpoint"].messages})
    call = t["store"].prepare_model_call(handle, loaded["run"]["checkpoint_seq"], digest, Decimal("0.020000"))
    t["store"].start_model_call(handle, call["id"])
    return t["store"].complete_model_call(handle, loaded["run"]["checkpoint_seq"], call["id"], turn, amount)


def rows(t, table):
    with t["admin"].connect() as c:
        query = select(table).where(table.c.org_id == t["org"])
        if "run_id" in table.c:
            query = query.where(table.c.run_id == t["run_id"])
        return list(c.execute(query).mappings())


def detail(t):
    return t["service"].get_run(t["alice"], t["run_id"])
