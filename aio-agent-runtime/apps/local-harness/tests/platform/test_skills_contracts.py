"""Text-package structural admission never imports/executes uploader code on the host."""

import copy

import pytest
from pydantic import ValidationError

from app.platform_errors import PlatformError
from app.skills.contracts import SkillPackage
from app.skills.commands import call_code, result_value
from app.runtime.catalog import validate_schema, validate_arguments
from skill_fixtures import sample_package


@pytest.mark.parametrize(
    "path",
    [
        "../SKILL.md",
        "/SKILL.md",
        "C:/SKILL.md",
        "x\\SKILL.md",
        "./SKILL.md",
        "x//SKILL.md",
        ".env.txt",
        "cache/node_modules/x.py",
        "file.exe",
        "x\0.md",
    ],
)
def test_reject_nonportable_or_unsafe_package_paths(path):
    p = sample_package().model_dump(mode="json")
    p["files"].append({"path": path, "content": "inert"})
    with pytest.raises((ValidationError, PlatformError)):
        SkillPackage.model_validate(p)


def test_normalized_content_digest_ignores_file_order_but_not_script_bytes():
    p = sample_package()
    changed = p.model_dump(mode="json")
    changed["files"].reverse()
    assert SkillPackage.model_validate(changed).digest() == p.digest()
    changed["files"][0]["content"] += "\n# meaningful immutable byte difference"
    assert SkillPackage.model_validate(changed).digest() != p.digest()


def test_duplicate_case_paths_remote_schema_refs_and_unbounded_tests_denied():
    p = sample_package().model_dump(mode="json")
    duplicate = copy.deepcopy(p)
    duplicate["files"].append({"path": "skill.md", "content": "shadow"})
    with pytest.raises(ValidationError):
        SkillPackage.model_validate(duplicate)
    remote = copy.deepcopy(p)
    remote["entrypoints"][0]["input_schema"]["properties"]["value"] = {"$ref": "https://metadata.invalid/secret"}
    with pytest.raises(PlatformError):
        SkillPackage.model_validate(remote)
    p["entrypoints"][0]["tests"][0]["input"]["unexpected"] = "not allowed"
    with pytest.raises(PlatformError):
        SkillPackage.model_validate(p)


def test_source_is_inert_during_admission_and_command_building(tmp_path):
    marker = tmp_path / "must-not-exist.txt"
    p = sample_package().model_dump(mode="json")
    source = (
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('unsafe')\ndef run(payload):\n    return payload\n"
    )
    p["files"][-1]["content"] = source
    package = SkillPackage.model_validate(p)
    command = call_code(
        {"package": package.normalized(), "digest": package.digest()}, "department_calculate", {"value": 4}
    )
    assert not marker.exists()
    assert "exec(compile(" in command and "scripts/calculate.py" in command
    assert "read_text" not in command  # Entry source is not reloaded from a writable workspace.


@pytest.mark.parametrize(
    "result",
    [
        {"exit_code": 0, "stdout": 'AIO_SKILL_RESULT:{"value":1,"value":2}'},
        {"exit_code": 0, "stdout": 'AIO_SKILL_RESULT:{"value":NaN}'},
        {"exit_code": 0, "stdout": "AIO_SKILL_RESULT:{}\nAIO_SKILL_RESULT:{}"},
        {"exit_code": 1, "stdout": "AIO_SKILL_RESULT:{}"},
        {"exit_code": 0, "stdout": "AIO_SKILL_RESULT:{}", "truncated": True},
    ],
)
def test_ambiguous_or_failed_result_never_becomes_a_success(result):
    with pytest.raises(PlatformError):
        result_value(result)


@pytest.mark.parametrize(
    "child",
    [
        {"type": "string", "pattern": "(a+)+$"},
        {"type": "object", "patternProperties": {"(a+)+$": {"type": "string"}}},
        {"type": "array", "uniqueItems": True, "items": {"type": "object"}},
        {"$ref": "#/$defs/recursive"},
    ],
)
def test_untrusted_schema_cannot_install_regex_or_recursive_validation_program(child):
    schema = {
        "type": "object",
        "properties": {"value": child},
        "additionalProperties": False,
        "$defs": {"recursive": {"$ref": "#/$defs/recursive"}} if "$ref" in child else {},
    }
    with pytest.raises(PlatformError):
        validate_schema(schema)


def test_bounded_acyclic_local_schema_references_remain_supported():
    schema = {
        "type": "object",
        "properties": {"value": {"$ref": "#/$defs/number"}},
        "required": ["value"],
        "additionalProperties": False,
        "$defs": {"number": {"type": "integer", "minimum": 0, "maximum": 100}},
    }
    validate_schema(schema)
    assert validate_arguments({"input_schema": schema}, {"value": 7}) == {"value": 7}


def test_unique_array_cardinality_is_checked_before_quadratic_work(monkeypatch):
    from jsonschema import Draft202012Validator

    schema = {
        "type": "object",
        "properties": {"value": {"uniqueItems": True, "maxItems": 128, "type": "array"}},
        "additionalProperties": False,
    }
    validate_schema(schema)
    calls = []

    def expensive(*args):
        calls.append(True)
        raise RuntimeError("Uniqueness must not be evaluated for an oversized array")

    monkeypatch.setattr(
        Draft202012Validator, "VALIDATORS", {**Draft202012Validator.VALIDATORS, "uniqueItems": expensive}
    )
    with pytest.raises(PlatformError):
        validate_arguments({"input_schema": schema}, {"value": list(range(129))})
    assert calls == []


def test_schema_keyword_names_are_allowed_as_literal_data_properties():
    schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "config": {"enum": [{"pattern": "literal", "$ref": "opaque-data-not-a-reference"}]},
        },
        "required": ["pattern", "config"],
        "additionalProperties": False,
    }
    validate_schema(schema)
    value = {
        "pattern": "(a+)+$ is data, not a validator",
        "config": {"pattern": "literal", "$ref": "opaque-data-not-a-reference"},
    }
    assert validate_arguments({"input_schema": schema}, value) == value


@pytest.mark.parametrize(
    "extension", [{"$id": "https://unapproved.invalid/schema"}, {"$schema": "http://json-schema.org/draft-07/schema#"}]
)
def test_tool_schema_cannot_change_resolution_base_or_dialect(extension):
    schema = {
        "type": "object",
        "properties": {"value": {"type": "integer", **extension}},
        "additionalProperties": False,
    }
    with pytest.raises(PlatformError):
        validate_schema(schema)


@pytest.mark.parametrize(
    "target", [{"pattern": "(a+)+$", "type": "string"}, {"$ref": "https://unapproved.invalid/schema"}]
)
def test_percent_encoded_reference_cannot_hide_an_executable_schema_in_literal_metadata(target):
    schema = {
        "type": "object",
        "properties": {"value": {"$ref": "#/$defs/alias%2Fhidden"}},
        "additionalProperties": False,
        "$defs": {"alias%2Fhidden": {"type": "integer"}, "alias": {"hidden": target}},
    }
    with pytest.raises(PlatformError):
        validate_schema(schema)


def test_percent_encoded_local_definition_is_resolved_like_the_actual_validator():
    schema = {
        "type": "object",
        "properties": {"value": {"$ref": "#/$defs/with%20space"}},
        "additionalProperties": False,
        "$defs": {"with space": {"type": "integer"}},
    }
    validate_schema(schema)
    assert validate_arguments({"input_schema": schema}, {"value": 3}) == {"value": 3}
