"""Schema-driven egress masking (GOV-02.04): structural marks plus known-material removal, no prefix regex."""

import base64
import json
from urllib.parse import quote

import pytest

from app.observability import scrub as x
from app.runtime.catalog import definition_digest, validate_schema

MARKER = "synthetic-secret-marker-7f3a9c"
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "$defs": {"token": {"type": "string", "x-aio-sensitive": True}},
    "properties": {
        "query": {"type": "string"},
        "api_key": {"$ref": "#/$defs/token"},
        "auth": {"type": "object", "x-aio-sensitive": True, "properties": {"user": {"type": "string"}}},
        "headers": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "value": {"type": "string", "x-aio-sensitive": True}}}},
        "either": {"anyOf": [{"type": "integer"}, {"type": "string", "x-aio-sensitive": True}]},
    },
}


def test_marks_are_found_through_refs_arrays_objects_and_composition():
    assert x.sensitive_paths(SCHEMA) == {("api_key",), ("auth",), ("headers", "*", "value"), ("either",)}


def test_marked_values_are_masked_regardless_of_their_shape():
    arguments = {
        "query": "weather", "api_key": "short", "auth": {"user": "u", "password": MARKER},
        "headers": [{"name": "X-A", "value": "not-a-secret-looking-value"}], "either": 3,
    }
    out = x.scrub(arguments, sensitive=x.sensitive_paths(SCHEMA))
    assert out == {"query": "weather", "api_key": x.MASK, "auth": x.MASK,
                   "headers": [{"name": "X-A", "value": x.MASK}], "either": x.MASK}
    assert arguments["auth"]["password"] == MARKER  # input is not mutated


@pytest.mark.parametrize("encode", [
    lambda v: v, lambda v: quote(v, safe=""), lambda v: base64.b64encode(v.encode()).decode(),
    lambda v: base64.urlsafe_b64encode(v.encode()).decode().rstrip("="),
], ids=["raw", "percent", "base64", "base64url"])
def test_known_material_is_removed_from_header_query_body_env_and_nested_errors(encode):
    secret = MARKER + "/+?&="
    leaked = encode(secret)
    payload = {
        "headers": {"Authorization": f"Bearer {leaked}"},
        "url": f"https://api.example.test/v1?token={leaked}&q=1",
        "body": [{"text": f"upstream echoed {leaked} back"}],
        "env": {"API_TOKEN": leaked},
        "error": {"cause": {"cause": f"KeyError: {leaked}"}},
        leaked: "secret used as a key",
    }
    out = json.dumps(x.scrub(payload, secrets=[secret]))
    assert leaked not in out and secret not in out and x.MATERIAL_MASK in out
    x.assert_clean(out, [secret])


def test_no_prefix_heuristics_and_short_values_are_not_treated_as_material():
    text = {"note": "sk-abcdefghijklmnop Bearer abcdefghij AIzaSyabcdefgh", "pin": "1234"}
    assert x.scrub(text, secrets=["1234"]) == text  # unmarked, unknown shapes pass; 4-char "secret" ignored
    assert x.material_forms(["short"]) == ()


def test_assert_clean_refuses_instead_of_repairing():
    with pytest.raises(x.SensitiveLeak) as error:
        x.assert_clean(json.dumps({"m": quote(MARKER + "!", safe="")}), [MARKER + "!"])
    assert MARKER not in str(error.value)


def test_mark_must_be_boolean_true_and_is_frozen_into_the_tool_digest():
    validate_schema(SCHEMA)
    x.validate_mark(SCHEMA)
    for bad in ("yes", 1, False, None):
        with pytest.raises(ValueError):
            x.validate_mark({"type": "object", "properties": {"a": {"type": "string", "x-aio-sensitive": bad}}})
    unmarked = json.loads(json.dumps(SCHEMA).replace('"x-aio-sensitive": true', '"description": "plain"'))
    assert definition_digest("t", "synthetic", "R0", SCHEMA, {}) != definition_digest("t", "synthetic", "R0", unmarked, {})


def test_a_marked_root_masks_everything():
    assert x.scrub({"a": 1}, sensitive=x.sensitive_paths({"type": "object", "x-aio-sensitive": True})) == x.MASK
