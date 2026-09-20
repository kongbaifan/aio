"""Actual PG/Gateway/Manager/Docker attachment handoff with synthetic documents and model output."""

import asyncio
import copy
import json
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.connections.driver import MCPDriver
from app.db import schema as s
from app.platform_errors import PlatformError
from app.runtime.contracts import ModelTurn, PlannedCall
from app.runtime.worker import DurableWorker, ToolDrivers
from test_stdio_integration import published


def upload(t, p, project, path, data):
    slot = t["artifacts"].create_upload(p, project, path, len(data))
    return t["artifacts"].upload(p, slot["upload_id"], data)


def prepare_run(t, agent, *, consent=True, data=b"private-selected-input,value\nalpha,73\n"):
    p = t["alice"]
    project = t["service"].create_project(p, "Explicit input copy")
    selected = upload(t, p, project["id"], "selected.csv", data)
    other = upload(t, p, project["id"], "not-selected.csv", b"must-not-be-sent")
    session = t["service"].create_session(p, project["id"], agent["id"], "Selected attachments only")
    body = {
        "message": "Read only my selected file",
        "agent_version_id": str(agent["id"]),
        "expected_session_revision": 0,
        "mode": "single",
        "input_artifact_ids": [str(selected["id"])],
        "allow_stdio_attachments": consent,
    }
    key = "stdio-input-" + uuid4().hex
    run = t["service"].create_run(p, session["id"], body, key)
    return {**run, "idempotency_key": key}, selected, other, body, session


def worker(t, artifact):
    class Model:
        max_charge = Decimal(".020000")

        def charge(self, turn):
            return Decimal(".001000")

        async def stream(self, messages, tools):
            prior = [item for item in messages if item["role"] == "tool"]
            if len(prior) < 2:
                yield ModelTurn(
                    tool_calls=(
                        PlannedCall(
                            id="synthetic-call", name="company_lookup", arguments={"artifact_id": str(artifact["id"])}
                        ),
                    ),
                    finish_reason="tool_calls",
                    input_tokens=10,
                    output_tokens=2,
                )
            else:
                yield ModelTurn(content=prior[-1]["content"], finish_reason="stop", input_tokens=10, output_tokens=3)

        async def close(self):
            pass

    class Models:
        def create(self, definition):
            return Model()

    driver = MCPDriver(t["connector_client"])
    return DurableWorker(t["store"], t["org"], "stdio-input-worker", Models(), ToolDrivers({"mcp.stdio": driver}))


def decoded(answer):
    value = json.loads(answer)
    return value.get("structuredContent") or json.loads(
        "".join(item["text"] for item in value["content"] if item["type"] == "text")
    )


@pytest.mark.parametrize(
    ("stdio_platform", "consent", "allowed"),
    [("run_attachments", True, True), ("run_attachments", False, False), ("none", True, False)],
    indirect=["stdio_platform"],
)
def test_real_stdio_attachments_require_template_and_frozen_run_consent(stdio_platform, consent, allowed):
    t = stdio_platform

    async def check():
        _, _, agent = await published(t, "read_attachment")
        run, selected, other, body, session = prepare_run(t, agent, consent=consent)
        # This opt-in is part of the same immutable idempotency request, never a mutable connection preference.
        with t["db"].transaction(t["alice"]) as c:
            stored = c.execute(select(s.runs.c.input).where(s.runs.c.id == run["run_id"])).scalar_one()
            assert stored["allow_stdio_attachments"] is consent
        loads = []
        original = t["stdio_authority"].inputs.load

        def inspect(payload):
            forged = copy.deepcopy(payload)
            item = forged["spec"]["input_manifest"][0]
            item.update(
                artifact_id=str(other["id"]),
                path="attachments/" + str(other["id"]),
                sha256=other["sha256"],
                bytes=other["bytes"],
            )
            with pytest.raises(PlatformError):
                original(forged)
            loads.append(copy.deepcopy(payload))
            return original(payload)

        t["stdio_authority"].inputs.load = inspect
        result = await worker(t, selected).run_once()
        if result["state"] != "succeeded":
            with t["admin"].begin() as c:
                failure = c.execute(select(s.runs.c.state, s.runs.c.error_code, s.runs.c.cleanup_state).where(s.runs.c.id == run["run_id"])).mappings().one()
                phases = c.execute(select(s.invocations.c.state).where(s.invocations.c.run_id == run["run_id"])).scalars().all()
            raise AssertionError({**dict(failure), "invocations": phases, "manager_denials": t["manager_denials"]})
        answer = decoded(t["service"].get_run(t["alice"], run["run_id"])["result"]["answer"])
        assert answer["available"] is allowed
        assert len(loads) == (1 if allowed else 0), "Only first initialization can request raw bytes"
        if allowed:
            assert answer["sha256"] == selected["sha256"] and "alpha,73" in answer["preview"]
            assert str(other["id"]) not in json.dumps(loads)
            with pytest.raises(PlatformError):
                original(loads[0])  # A completed Run is not an input download capability.
        with t["db"].transaction(t["alice"]) as c:
            lease = (
                c.execute(select(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.run_id == run["run_id"]))
                .mappings()
                .one()
            )
            assert lease["state"] == "destroyed" and lease["close_reason"] == "requested"
            assert "content_b64" not in str(lease["spec"])
            assert len(lease["spec"].get("input_manifest", [])) == (1 if allowed else 0)
        assert t["artifacts"].download(t["alice"], selected["id"])[1] == b"private-selected-input,value\nalpha,73\n"
        assert not t["manager"].backend.client.containers.list(
            all=True, filters={"label": "aio.manager=" + t["manager"].journal.installation_id}
        )
        with pytest.raises(PlatformError) as conflict:
            t["service"].create_run(
                t["alice"], session["id"], {**body, "allow_stdio_attachments": not consent}, run["idempotency_key"]
            )
        assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
        with pytest.raises(PlatformError):
            t["artifacts"].download(t["bob"], selected["id"])

    asyncio.run(check())


@pytest.mark.parametrize("stdio_platform", ["run_attachments"], indirect=True)
@pytest.mark.parametrize("fault", ["corrupt", "revoke_after_read"])
def test_stdio_input_faults_never_start_a_business_process(stdio_platform, fault, monkeypatch):
    t = stdio_platform

    async def check():
        _, _, agent = await published(t, "read_attachment")
        run, selected, _, _, _ = prepare_run(t, agent)
        blobs = t["artifacts"].blobs
        if fault == "corrupt":
            blobs._path(t["org"], selected["sha256"]).write_bytes(b"corrupt synthetic blob")
        else:
            original = blobs.get

            def revoke(*args):
                data = original(*args)
                with t["admin"].begin() as c:
                    c.execute(
                        update(s.resources)
                        .where(s.resources.c.id == selected["id"])
                        .values(status="disabled", revision=s.resources.c.revision + 1)
                    )
                return data

            monkeypatch.setattr(blobs, "get", revoke)
        await worker(t, selected).run_once()
        with t["admin"].begin() as c:
            leases = (
                c.execute(select(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.run_id == run["run_id"]))
                .mappings()
                .all()
            )
            assert leases and all(row["backend_id"] is None for row in leases)
            assert all(row["state"] == "destroyed" for row in leases)
            assert c.execute(select(s.runs.c.cleanup_state).where(s.runs.c.id == run["run_id"])).scalar_one() == "clean"
            calls = c.execute(select(s.invocations).where(s.invocations.c.run_id == run["run_id"])).mappings().all()
            assert not any(item["state"] == "succeeded" for item in calls)
        assert all(t["manager"].journal.cell(row["id"]) is None for row in leases)
        assert not t["manager"].backend.client.containers.list(
            all=True, filters={"label": "aio.manager=" + t["manager"].journal.installation_id}
        )

    asyncio.run(check())


@pytest.mark.parametrize("stdio_platform", ["run_attachments"], indirect=True)
@pytest.mark.parametrize("extra_bytes", [0, 1])
def test_stdio_attachment_quota_accepts_boundary_but_never_silently_truncates(stdio_platform, monkeypatch, extra_bytes):
    t = stdio_platform

    async def check():
        _, _, agent = await published(t, "read_attachment")
        run, selected, _, _, _ = prepare_run(t, agent, data=b"q" * (4 * 1024 * 1024 + extra_bytes))
        original = t["stdio_authority"].prepare
        errors = []

        def prepare(*args):
            try:
                return original(*args)
            except PlatformError as error:
                errors.append(error.code)
                raise

        monkeypatch.setattr(t["stdio_authority"], "prepare", prepare)
        await worker(t, selected).run_once()
        if extra_bytes:
            assert "STDIO_INPUT_QUOTA_EXCEEDED" in errors
        else:
            assert not errors
            result = t["service"].get_run(t["alice"], run["run_id"])
            assert result["state"] == "succeeded" and result["cleanup_state"] == "clean"
            content = decoded(result["result"]["answer"])
            assert content["bytes"] == 4 * 1024 * 1024 and content["sha256"] == selected["sha256"]
            assert content["truncated"] is True
        with t["db"].transaction(t["alice"]) as c:
            row = (
                c.execute(select(s.mcp_stdio_leases).where(s.mcp_stdio_leases.c.run_id == run["run_id"]))
                .mappings()
                .first()
            )
            assert row is None if extra_bytes else row is not None and row["state"] == "destroyed"
        assert not t["manager"].backend.client.containers.list(
            all=True, filters={"label": "aio.manager=" + t["manager"].journal.installation_id}
        )

    asyncio.run(check())
