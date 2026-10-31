"""Real PostgreSQL evidence for egress scrubbing (GOV-02.04 / ECASE-33).

A synthetic marker is planted in a marked tool argument, a registered service credential and a
driver exception; the Run goes through a real Worker and every stored/streamed copy is inspected.
"""

from __future__ import annotations

import asyncio
import base64
from decimal import Decimal
import json
import logging
import secrets
from urllib.parse import quote
from uuid import UUID

import pytest
from sqlalchemy import select, text, update

from app.db import schema as s
from app.db.provisioning import provision_agent, provision_model, provision_tool
from app.observability import scrub
from app.runtime.contracts import ModelTurn, PlannedCall
from app.runtime.execution import ExecutionStore
from app.runtime.worker import DurableWorker, ToolDrivers

MARKER = "synthetic-egress-marker-" + secrets.token_hex(6) + "/+?="  # changes under every encoding
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["query", "api_key"],
    "properties": {"query": {"type": "string"}, "api_key": {"type": "string", "x-aio-sensitive": True}},
}


class Model:
    max_charge = Decimal("0.020000")

    def __init__(self, factory):
        self.factory = factory

    def charge(self, turn):
        return Decimal("0.001000")

    async def stream(self, messages, tools):
        self.factory.calls.append(messages)
        if any(m["role"] == "tool" for m in messages):
            yield ModelTurn(content="done", finish_reason="stop", input_tokens=1, output_tokens=1)
        else:
            yield ModelTurn(
                tool_calls=(PlannedCall(id="c1", name="lookup", arguments={"query": "weather", "api_key": MARKER}),),
                finish_reason="tool_calls", input_tokens=1, output_tokens=1,
            )

    async def close(self):
        pass


class Factory:
    def __init__(self):
        self.calls = []

    def create(self, definition):
        return Model(self)


class Echo:
    """A misbehaving tool: echoes what it was given, in several encodings, plus extra material."""

    def __init__(self, extra="", fail=False):
        self.extra, self.fail = extra, fail

    async def execute(self, permit):
        key = permit.arguments["api_key"]
        if self.fail:
            raise RuntimeError(f"upstream 401 for key={key} {self.extra}")
        return {
            "raw": f"Authorization: Bearer {key}",
            "url": f"https://api.example.test/?k={quote(key, safe='')}",
            "b64": base64.b64encode(key.encode()).decode(),
            "service": self.extra,
            "answer": "sunny",
        }


@pytest.fixture
def echo_run(tenant):
    t = dict(tenant)
    with t["admin"].begin() as c:
        model = provision_model(c, org_id=t["org"], owner_id=t["alice"].user_id, provider="test-only",
                                model="m", config={"test_fixture": True, "max_call_charge": "0.020000"})
        tool = provision_tool(c, org_id=t["org"], owner_id=t["alice"].user_id, name="lookup", driver="synthetic",
                              risk="R0", input_schema=SCHEMA,
                              config={"timeout_seconds": 30, "resource_scope": {"system": "synthetic"}})
        agent = provision_agent(c, org_id=t["org"], owner_id=t["alice"].user_id, name="Echo", version="v1",
                                engine="local-harness-v2", instruction="Synthetic",
                                manifest={"run_budget": "0.100000", "max_rounds": 4, "tools": [tool], "model": model})
    session = t["service"].create_session(t["alice"], t["project"], agent, "Echo")["id"]
    run = t["service"].create_run(t["alice"], session, {
        "message": "look it up", "agent_version_id": str(agent), "expected_session_revision": 0,
        "input_artifact_ids": [], "mode": "single",
    }, secrets.token_hex(16))
    t.update(store=ExecutionStore(t["db"], t["settings"]), run_id=run["run_id"], tool=tool, session=session)
    return t


def run_with(t, driver, factory=None):
    worker = DurableWorker(t["store"], t["org"], "scrub-worker", factory or Factory(), ToolDrivers({"synthetic": driver}))
    return asyncio.run(worker.run_once())


def stored_copies(t) -> str:
    """Everything persisted for the Run that a user, model, SSE client, auditor or archive can read."""
    org, run = t["org"], t["run_id"]
    with t["admin"].connect() as c:
        rows = {
            "dispatch": c.execute(select(s.dispatches.c.result).join(
                s.invocations, s.invocations.c.id == s.dispatches.c.invocation_id).where(
                s.invocations.c.run_id == run)).scalars().all(),
            "invocation_result": c.execute(select(s.invocations.c.result).where(s.invocations.c.run_id == run)).scalars().all(),
            # Tool-result messages only: the assistant's own tool_call history and pending_calls are internal
            # replay state holding what the model itself produced (dispatch needs it), not an egress.
            "checkpoint_tool_messages": [
                m for p in c.execute(select(s.checkpoints.c.payload).where(s.checkpoints.c.run_id == run)).scalars()
                for m in p.get("messages", []) if m.get("role") == "tool"
            ],
            "events": c.execute(select(s.events.c.payload).where(s.events.c.run_id == run)).scalars().all(),
            "messages": c.execute(select(s.messages.c.content).where(s.messages.c.run_id == run)).scalars().all(),
            "run": c.execute(select(s.runs.c.result, s.runs.c.error_code).where(s.runs.c.id == run)).all(),
            "audit": c.execute(select(s.audit.c.metadata, s.audit.c.service_actor_id).where(
                s.audit.c.org_id == org)).all(),
        }
    return json.dumps(rows, default=str)


def forms(value):
    return [value, quote(value, safe=""), base64.b64encode(value.encode()).decode(),
            base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")]


def test_a_marked_argument_echoed_by_a_tool_never_reaches_rows_checkpoint_sse_or_model(echo_run):
    t, factory = echo_run, Factory()
    assert run_with(t, Echo(), factory)["state"] == "succeeded"
    copies = stored_copies(t)
    assert not [f for f in forms(MARKER) if f in copies]
    assert "sunny" in copies and scrub.MATERIAL_MASK in copies  # data survives, only the secret is replaced
    tool_messages = json.dumps([m for m in factory.calls[-1] if m.get("role") == "tool"])
    assert not [f for f in forms(MARKER) if f in tool_messages] and "sunny" in tool_messages
    with t["admin"].connect() as c:  # the authoritative call record keeps what was actually sent
        assert c.execute(select(s.invocations.c.arguments).where(
            s.invocations.c.run_id == t["run_id"])).scalar_one()["api_key"] == MARKER


def test_a_registered_service_credential_echoed_by_a_tool_is_scrubbed_everywhere(echo_run):
    t, credential = echo_run, "service-credential-" + secrets.token_hex(12)
    scrub.register_material(credential)
    try:
        assert run_with(t, Echo(extra=credential))["state"] == "succeeded"
        copies = stored_copies(t)
        assert not [f for f in forms(credential) if f in copies]
    finally:
        scrub.forget_material(credential)


def test_a_driver_exception_carrying_secrets_leaves_only_a_code(echo_run, caplog):
    t, credential = echo_run, "service-credential-" + secrets.token_hex(12)
    scrub.register_material(credential)
    scrub.install_log_filter()
    try:
        with caplog.at_level(logging.DEBUG):
            outcome = run_with(t, Echo(extra=credential, fail=True))
        copies = stored_copies(t)
        assert outcome["state"] in {"failed", "recovery_required"}
        for value in (MARKER, credential):
            assert not [f for f in forms(value) if f in copies]
            assert value not in caplog.text
        with t["admin"].connect() as c:
            assert c.execute(select(s.runs.c.error_code).where(s.runs.c.id == t["run_id"])).scalar_one() == "EXECUTION_FAILED"
    finally:
        scrub.forget_material(credential)


def test_unmarked_values_are_not_masked_by_shape(echo_run):
    t = echo_run
    lookalike = "sk-" + "a" * 40

    class Lookalike(Echo):
        async def execute(self, permit):
            return {"note": lookalike, "query": permit.arguments["query"]}

    assert run_with(t, Lookalike())["state"] == "succeeded"
    assert lookalike in stored_copies(t)  # no prefix regex: an unmarked, unknown value is data


def test_removing_the_mark_after_publication_breaks_the_manifest_instead_of_unmasking(echo_run):
    t = echo_run
    unmarked = json.loads(json.dumps(SCHEMA).replace('"x-aio-sensitive": true', '"description": "plain"'))
    with t["admin"].begin() as c:
        c.execute(update(s.tool_versions).where(s.tool_versions.c.id == UUID(t["tool"]["id"])).values(input_schema=unmarked))
    run_with(t, Echo())
    copies = stored_copies(t)
    assert not [f for f in forms(MARKER) if f in copies]
    with t["admin"].connect() as c:
        run = c.execute(select(s.runs.c.state, s.runs.c.error_code).where(s.runs.c.id == t["run_id"])).one()
        sent = c.execute(text("SELECT count(*) FROM aio_dispatches d JOIN aio_invocations i ON i.id = d.invocation_id "
                              "WHERE i.run_id = :r AND d.state <> 'not_sent'"), {"r": t["run_id"]}).scalar_one()
    assert run.state == "failed" and run.error_code == "TOOL_VERSION_CHANGED" and sent == 0
