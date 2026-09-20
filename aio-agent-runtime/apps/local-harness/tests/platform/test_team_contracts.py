import json

import pytest
from pydantic import ValidationError

from app.platform_errors import PlatformError
from app.runtime.contracts import Checkpoint
from app.runtime.actions import canonical_digest
from app.runtime.team_contracts import TeamPolicy, parse_plan, policy_for


MANIFEST = {"max_rounds": 8, "team": {"max_steps": 2, "max_step_rounds": 3}, "tools": [{"name": "python_compute"}]}


def test_plan_preserves_explicit_subset_and_text_only_step():
    value = {
        "steps": [
            {"title": "计算", "task": "计算并保存结果", "tools": ["python_compute"]},
            {"title": "汇报", "task": "描述结果", "tools": []},
        ]
    }
    parsed = parse_plan(json.dumps(value), MANIFEST)
    assert parsed.steps[0].tools == ("python_compute",)
    assert parsed.steps[1].tools == ()


@pytest.mark.parametrize(
    "change",
    [
        {"tools": ["shell"]},
        {"tools": ["python_compute", "python_compute"]},
        {"model_id": "other-model"},
        {"connection_id": "borrowed-identity"},
        {"task": " "},
        {"title": ""},
        {"tools": ["python.compute"]},
        {"tools": "python_compute"},
        {"task": "x" * 4001},
    ],
)
def test_plan_never_widens_or_accepts_invalid_definition(change):
    value = {"steps": [{"title": "test", "task": "test", "tools": [], **change}]}
    with pytest.raises(PlatformError) as error:
        parse_plan(json.dumps(value), MANIFEST)
    assert error.value.code == "TEAM_PLAN_INVALID"


@pytest.mark.parametrize(
    "raw",
    [
        '{"steps":[],"steps":[{"title":"x","task":"x","tools":[]}]}',
        '{"steps":[]}',
        '```json\n{"steps":[]}\n```',
        '{"steps":["legacy freeform"]}',
        json.dumps({"steps": [{"title": "x", "task": "x", "tools": []}] * 3}),
        '{"steps":[],"value":NaN}',
    ],
)
def test_bad_planner_json_has_no_silent_single_fallback(raw):
    with pytest.raises(PlatformError):
        parse_plan(raw, MANIFEST)


@pytest.mark.parametrize("value", [{"max_steps": True}, {"max_steps": 7}, {"max_step_rounds": "4"}, {"models": []}])
def test_strict_published_team_policy(value):
    with pytest.raises(ValidationError):
        TeamPolicy.model_validate(value)


def test_global_rounds_include_planner_all_steps_and_synthesis():
    with pytest.raises(PlatformError, match="rounds"):
        policy_for({**MANIFEST, "max_rounds": 3}, required=True)
    assert policy_for({"max_rounds": 4}) is None
    with pytest.raises(PlatformError) as error:
        policy_for({"max_rounds": 4}, required=True)
    assert error.value.code == "TEAM_NOT_ENABLED"


def test_ambiguous_parent_aliases_fail_closed():
    with pytest.raises(PlatformError) as error:
        parse_plan(
            '{"steps":[{"title":"x","task":"x","tools":[]}]}',
            {**MANIFEST, "tools": [{"name": "duplicate"}, {"name": "duplicate"}]},
        )
    assert error.value.code == "INVALID_MANIFEST"


def test_v1_checkpoint_digest_not_changed_by_new_team_defaults():
    legacy = {
        "schema_version": 1,
        "phase": "model",
        "round": 3,
        "messages": [{"role": "user", "content": "unchanged"}],
        "pending_calls": [],
        "next_tool": 0,
        "answer": "",
        "finish_reason": "",
        "restartability": "stateless",
    }
    cp = Checkpoint.model_validate(legacy)
    assert cp.model_dump(mode="json") == legacy
    assert cp.digest == canonical_digest("aio-checkpoint-v1", legacy)


def test_plan_boolean_version_is_not_version_one():
    with pytest.raises(PlatformError):
        parse_plan('{"schema_version":true,"steps":[{"title":"x","task":"x","tools":[]}]}', MANIFEST)


def test_plan_aggregate_utf8_byte_limit_is_not_a_character_limit():
    raw = json.dumps({"steps": [{"title": "large", "task": "界" * 4000, "tools": []}] * 6}, ensure_ascii=False)
    with pytest.raises(PlatformError) as error:
        parse_plan(raw, {**MANIFEST, "team": {"max_steps": 6, "max_step_rounds": 1}})
    assert error.value.code == "TEAM_PLAN_INVALID"
