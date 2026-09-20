import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.platform_errors import PlatformError
from app.runtime.actions import ActionSpec, canonical_digest, strict_json
from app.runtime.states import RunState, TERMINAL_STATES, TRANSITIONS, require_generation, require_transition


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"a":{"k":1,"k":2}}',
        b'{"n":NaN}',
        b'{"n":Infinity}',
        b'{"n":1e999}',
        b'{"n":9007199254740992}',
        b'"\\ud800"',
        b"\xff",
        b"[" * 40 + b"0" + b"]" * 40,
    ],
)
def test_ambiguous_or_unbounded_json_rejected(raw):
    with pytest.raises(PlatformError) as exc:
        strict_json(raw)
    assert exc.value.code == "INVALID_JSON"


def test_raw_size_limit():
    with pytest.raises(PlatformError) as exc:
        strict_json(b'"abcdefgh"', max_bytes=4)
    assert exc.value.status == 413


def test_canonical_hash_is_order_independent_but_domain_separated():
    assert canonical_digest("action-v1", {"a": 1, "b": 2}) == canonical_digest("action-v1", {"b": 2, "a": 1})
    assert canonical_digest("action-v1", {"a": 1}) != canonical_digest("request-v1", {"a": 1})
    assert canonical_digest("action-v1", {"id": "A"}) != canonical_digest("action-v1", {"id": "a"})


def action_payload():
    return dict(
        org_id=uuid4(),
        actor_user_id=uuid4(),
        run_id=uuid4(),
        logical_call_id="call-1",
        tool_version_id=uuid4(),
        arguments_sha256="1" * 64,
        resource_scope_digest="2" * 64,
        network_profile_id="none",
        data_policy_revision=0,
        approval_policy_id="business-write",
        not_after=datetime.now(timezone.utc),
    )


def test_action_is_frozen_and_hashes_exact_versions():
    payload = action_payload()
    action = ActionSpec(**payload)
    with pytest.raises(ValidationError):
        action.network_profile_id = "admin-network"
    other = ActionSpec(**{**payload, "entrypoint_digest": "3" * 64})
    assert other.digest != action.digest
    assert isinstance(action.input_refs, tuple)


def test_equal_deadline_instants_have_identical_canonical_hash():
    payload = action_payload()
    one = ActionSpec(**payload)
    two = ActionSpec(**{**payload, "not_after": payload["not_after"].astimezone(timezone(timedelta(hours=8)))})
    assert one.digest == two.digest


def test_action_rejects_naive_time_extra_fields_and_unbound_secret():
    payload = action_payload()
    with pytest.raises(ValidationError):
        ActionSpec(**{**payload, "not_after": datetime.now()})
    with pytest.raises(ValidationError):
        ActionSpec(**payload, host_path="C:/")
    with pytest.raises(ValidationError):
        ActionSpec(**payload, credential_binding_revision=1)


def test_all_state_transitions_are_enumerated():
    for old in RunState:
        for new in RunState:
            if new in TRANSITIONS[old]:
                require_transition(old, new, reconciliation=(old == RunState.RECOVERY_REQUIRED))
            else:
                with pytest.raises(PlatformError):
                    require_transition(old, new, reconciliation=True)
    assert set(TRANSITIONS) == set(RunState)
    assert all(not TRANSITIONS[state] for state in TERMINAL_STATES)


def test_unknown_effects_cannot_be_resolved_by_normal_worker():
    with pytest.raises(PlatformError) as exc:
        require_transition("recovery_required", "failed")
    assert exc.value.code == "RECONCILIATION_REQUIRED"
    require_transition("waiting_approval", "recovery_required")


@pytest.mark.parametrize("generation", [0, -1, 1, True, "2"])
def test_generation_fence_rejects_stale_or_wrong_types(generation):
    with pytest.raises(PlatformError):
        require_generation(2, generation)
    require_generation(2, 2)


def test_request_contract_rejects_forged_identity():
    from app.api.v2.contracts import RunCreate

    payload = {"message": "hello", "agent_version_id": str(uuid4()), "expected_session_revision": 0}
    RunCreate.model_validate(strict_json(json.dumps(payload).encode()))
    with pytest.raises(ValidationError):
        RunCreate.model_validate({**payload, "user_id": str(uuid4())})
    with pytest.raises(ValidationError):
        RunCreate.model_validate({**payload, "expected_session_revision": True})


def test_generated_schema_constraint_names_are_unique():
    from app.db.schema import metadata

    names = [
        constraint.name for table in metadata.tables.values() for constraint in table.constraints if constraint.name
    ]
    assert len(names) == len(set(names)), "Composite constraints must include all columns in their names"
