"""Pure kill-switch matching: which actions/resources/Runs a switch blocks (GOV-04.01/.02)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.admin.contracts import KillSwitchCreate
from app.auth.principal import Principal
from app.platform_errors import PlatformError
from app.policy import kill_switches as k
from app.policy.service import KNOWN_ACTIONS, authorize
from app.policy.types import AuthorizationFacts, Resource

ORG, ALICE, BOB, TOOL, MODEL, AGENT = (uuid4() for _ in range(6))
NOW = datetime.now(timezone.utc)


def switch(scope, target=None, cls=None):
    return k.KillSwitch(uuid4(), scope, target, cls)


def test_only_work_starting_actions_are_blockable_reads_and_cleanup_are_not():
    assert k.BLOCKED_ACTIONS <= KNOWN_ACTIONS
    org = switch("organization")
    for action in ("run.read", "run.cancel", "run.reconcile", "session.read", "artifact.download", "approval.read"):
        assert not org.blocks(action, "run", uuid4(), ALICE)
    for action in k.BLOCKED_ACTIONS:
        assert org.blocks(action, "tool", uuid4(), ALICE)


@pytest.mark.parametrize("sw,blocked,allowed", [
    (switch("user", ALICE), ("agent.use", "agent", AGENT, ALICE), ("agent.use", "agent", AGENT, BOB)),
    (switch("tool", TOOL), ("tool.use", "tool", TOOL, ALICE), ("tool.use", "tool", uuid4(), ALICE)),
    (switch("model", MODEL), ("model.use", "model", MODEL, BOB), ("tool.use", "tool", MODEL, BOB)),
    (switch("agent", AGENT), ("agent.use", "agent", AGENT, BOB), ("agent.use", "agent", uuid4(), BOB)),
    (switch("execution_class", cls="python"), None, ("tool.use", "tool", TOOL, ALICE)),
], ids=["user", "tool", "model", "agent", "class-needs-driver"])
def test_each_scope_blocks_exactly_its_target(sw, blocked, allowed):
    if blocked:
        assert sw.blocks(*blocked)
    assert not sw.blocks(*allowed)


def test_authorize_reports_the_switch_only_after_access_is_established():
    p = Principal(ORG, ALICE, 0)
    facts = AuthorizationFacts(ORG, ALICE, 0, 0, kill_switches=(switch("tool", TOOL),))
    own = Resource(ORG, TOOL, "tool", ALICE)
    other = Resource(ORG, TOOL, "tool", BOB)  # not owned, no grant
    assert authorize(p, "tool.use", own, facts, now=NOW).reason_code == "KILL_SWITCH_ACTIVE"
    assert authorize(p, "tool.use", other, facts, now=NOW).reason_code == "RESOURCE_NOT_FOUND"
    assert authorize(p, "tool.read", own, facts, now=NOW).reason_code == "ALLOWED"


def test_execution_class_and_manifest_admission():
    manifest = {"model": {"id": str(MODEL)}, "tools": [{"id": str(TOOL), "driver": "sandbox.python"}]}
    k.require_manifest((), manifest, ALICE, AGENT)
    for sw in (switch("execution_class", cls="python"), switch("tool", TOOL), switch("model", MODEL),
               switch("agent", AGENT), switch("user", ALICE), switch("organization")):
        with pytest.raises(PlatformError) as error:
            k.require_manifest((sw,), manifest, ALICE, AGENT)
        assert error.value.code == "KILL_SWITCH_ACTIVE" and error.value.status == 403
    for sw in (switch("execution_class", cls="mcp"), switch("user", BOB), switch("tool", uuid4())):
        k.require_manifest((sw,), manifest, ALICE, AGENT)


def test_affected_runs_follow_the_fixed_manifest():
    run = {"actor_id": ALICE, "agent_version_id": AGENT}
    manifest = {"model": {"id": str(MODEL)}, "tools": [{"id": str(TOOL), "driver": "mcp.http"}]}
    for sw, hit in [(switch("organization"), True), (switch("user", ALICE), True), (switch("user", BOB), False),
                    (switch("tool", TOOL), True), (switch("model", MODEL), True), (switch("model", uuid4()), False),
                    (switch("execution_class", cls="mcp"), True), (switch("execution_class", cls="python"), False)]:
        assert k.affects_run(sw, run, manifest) is hit


@pytest.mark.parametrize("values", [
    {"scope": "tool"}, {"scope": "organization", "target_id": TOOL}, {"scope": "execution_class"},
    {"scope": "user", "target_id": ALICE, "execution_class": "python"},
    {"scope": "organization", "expires_at": datetime(2030, 1, 1)}, {"scope": "global"},
    {"scope": "organization", "reason_code": "BECAUSE"},
])
def test_activation_request_names_exactly_one_target_and_closed_reason(values):
    with pytest.raises(ValidationError):
        KillSwitchCreate(**{"reason_code": "SECURITY_INCIDENT", "note": "synthetic", **values})
