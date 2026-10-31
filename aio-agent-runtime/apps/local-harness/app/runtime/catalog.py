"""Versioned current authorization for tools/models. No user-selected Python imports or shell."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID
from urllib.parse import unquote

from jsonschema import Draft202012Validator
from sqlalchemy import select

from ..auth.principal import Principal
from ..connections.catalog import MCP_DRIVERS
from ..db import schema as s
from ..platform_errors import PlatformError
from ..policy import kill_switches
from ..policy.repository import require_resource
from .actions import canonical_digest
from .contracts import bounded_json


def definition_digest(name: str, driver: str, risk: str, input_schema: dict, config: dict) -> str:
    return canonical_digest(
        "aio-tool-definition-v1", dict(name=name, driver=driver, risk=risk, input_schema=input_schema, config=config)
    )


def validate_schema(schema: dict) -> None:
    bounded_json(schema, 32768)
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise PlatformError("INVALID_TOOL_SCHEMA", "Tool input requires a closed object schema", 422)

    expanded_nodes = 0

    def walk(value, depth=0, refs=(), kind="schema"):
        nonlocal expanded_nodes
        expanded_nodes += 1
        if expanded_nodes > 1024 or depth > 16:
            raise PlatformError("INVALID_TOOL_SCHEMA", "Tool schema exceeds the bounded validation dialect", 422)
        if isinstance(value, dict):
            # Python's backtracking regexp engine and recursive schema graphs must not become
            # attacker-controlled programs on API/Worker threads during argument validation.
            if kind == "schema" and set(value) & {
                "pattern",
                "patternProperties",
                "$id",
                "$anchor",
                "$dynamicAnchor",
                "$dynamicRef",
                "$recursiveRef",
                "unevaluatedItems",
                "unevaluatedProperties",
            }:
                raise PlatformError(
                    "INVALID_TOOL_SCHEMA",
                    "Unbounded regular-expression or recursive schema features are not supported",
                    422,
                )
            if (
                kind == "schema"
                and "$schema" in value
                and value["$schema"] != "https://json-schema.org/draft/2020-12/schema"
            ):
                raise PlatformError("INVALID_TOOL_SCHEMA", "Tool schemas cannot switch validation dialect", 422)
            if (
                kind == "schema"
                and value.get("uniqueItems") is True
                and (type(value.get("maxItems")) is not int or not 0 <= value["maxItems"] <= 128)
            ):
                raise PlatformError("INVALID_TOOL_SCHEMA", "Unique arrays require a small explicit item bound", 422)
            for key, item in value.items():
                if kind == "schema" and key == "$ref":
                    if not isinstance(item, str) or not item.startswith("#/$defs/"):
                        raise PlatformError("INVALID_TOOL_SCHEMA", "Schema references must be local and acyclic", 422)
                    try:
                        reference = unquote(item, encoding="utf-8", errors="strict")
                    except UnicodeError:
                        raise PlatformError(
                            "INVALID_TOOL_SCHEMA", "Schema reference encoding is invalid", 422
                        ) from None
                    if reference in refs:
                        raise PlatformError("INVALID_TOOL_SCHEMA", "Schema references must be local and acyclic", 422)
                    target = schema
                    try:
                        # JSON Schema resolves URI percent-encoding BEFORE JSON Pointer tokens.
                        # Inspect the same target, not an attacker-provided benign alias containing %2F.
                        for part in reference[2:].split("/"):
                            target = target[part.replace("~1", "/").replace("~0", "~")]
                    except (KeyError, TypeError):
                        raise PlatformError(
                            "INVALID_TOOL_SCHEMA", "Local schema reference does not resolve", 422
                        ) from None
                    walk(target, depth + 1, (*refs, reference))
                else:
                    # `properties.pattern` is a property NAME, and enum/default objects are
                    # literal data. They must not be confused with executable schema keywords.
                    child_kind = "literal"
                    if kind == "map":
                        child_kind = "schema"
                    elif kind == "schema":
                        if key in {"properties", "$defs", "definitions", "dependentSchemas"}:
                            child_kind = "map"
                        elif key in {"allOf", "anyOf", "oneOf", "prefixItems"}:
                            child_kind = "list"
                        elif key in {
                            "items",
                            "additionalItems",
                            "additionalProperties",
                            "contains",
                            "propertyNames",
                            "not",
                            "if",
                            "then",
                            "else",
                        }:
                            child_kind = "schema"
                    walk(item, depth + 1, refs, child_kind)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1, refs, "schema" if kind == "list" else "literal")

    walk(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception:
        raise PlatformError("INVALID_TOOL_SCHEMA", "Tool schema is invalid", 422) from None


def current_tool(c, principal: Principal, tool_id: UUID, snapshot_entry: dict) -> dict:
    require_resource(c, principal, tool_id, "tool.use")
    row = (
        c.execute(
            select(s.tool_versions).where(s.tool_versions.c.org_id == principal.org_id, s.tool_versions.c.id == tool_id)
        )
        .mappings()
        .first()
    )
    if row is None or not row["published"]:
        raise PlatformError("TOOL_UNAVAILABLE", "Tool version is not published", 403)
    expected = definition_digest(row["name"], row["driver"], row["risk"], row["input_schema"], row["config"])
    if (
        expected != row["digest"]
        or snapshot_entry.get("digest") != expected
        or snapshot_entry.get("name") != row["name"]
        or snapshot_entry.get("driver") != row["driver"]
        or snapshot_entry.get("risk") != row["risk"]
    ):
        raise PlatformError("TOOL_VERSION_CHANGED", "The tool no longer matches this run manifest", 409)
    validate_schema(row["input_schema"])
    kill_switches.require_driver(kill_switches.active(c, principal.org_id), row["driver"])
    if row["driver"] == "knowledge.search":
        from ..knowledge.catalog import current_knowledge, current_embedding

        kb = current_knowledge(c, principal, UUID(row["config"]["knowledge_id"]))
        if kb["tool_id"] != tool_id:
            raise PlatformError("KNOWLEDGE_SCOPE_DENIED", "Tool was not registered for this knowledge base", 403)
        if kb["embedding_model_id"]:
            current_embedding(c, principal, kb["embedding_model_id"])
    if row["driver"] in MCP_DRIVERS:
        from ..connections.catalog import current_server

        server = current_server(c, principal, UUID(row["config"]["server_id"]), row["config"]["server_digest"])
        if str(tool_id) not in {item["id"] for item in server["published_tools"]}:
            raise PlatformError("MCP_DEFINITION_CHANGED", "Tool was not published by this MCP definition", 409)
    if row["driver"] in {"skill.python", "skill.read"}:
        from ..skills.catalog import skill_for_tool

        skill_for_tool(c, principal, dict(row))
    return dict(row)


def _ordered_schema(value):
    # Apply cheap cardinality failures before any uniqueness/combinator work, including
    # referenced schemas. JSONB key order is not a safe validation execution order.
    priority = {"type": 0, "maxItems": 1, "maxProperties": 1, "maxLength": 1}
    if isinstance(value, dict):
        return {key: _ordered_schema(value[key]) for key in sorted(value, key=lambda key: priority.get(key, 2))}
    if isinstance(value, list):
        return [_ordered_schema(item) for item in value]
    return value


def validate_arguments(tool: dict, arguments: dict) -> dict:
    result = bounded_json(arguments, 65536)
    try:
        if not Draft202012Validator(_ordered_schema(tool["input_schema"])).is_valid(result):
            raise ValueError
    except Exception:
        raise PlatformError("TOOL_ARGUMENTS_INVALID", "Tool arguments do not match the approved schema", 422) from None
    return result


def snapshot_tool(manifest: dict, alias: str) -> dict:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", alias):
        raise PlatformError("TOOL_NOT_ALLOWED", "Tool alias is not permitted", 403)
    items = manifest.get("tools", [])
    if not isinstance(items, list) or len(items) > 64:
        raise PlatformError("INVALID_MANIFEST", "Tool manifest is invalid", 409)
    matches = [item for item in items if isinstance(item, dict) and item.get("name") == alias]
    if len(matches) != 1:
        raise PlatformError("TOOL_NOT_ALLOWED", "Tool alias is not in the fixed manifest", 403)
    return matches[0]


def current_model(c, principal: Principal, model_id: UUID, expected_digest: str) -> dict[str, Any]:
    require_resource(c, principal, model_id, "model.use")
    row = (
        c.execute(
            select(s.model_configs).where(
                s.model_configs.c.org_id == principal.org_id, s.model_configs.c.id == model_id
            )
        )
        .mappings()
        .first()
    )
    if row is None or not row["published"]:
        raise PlatformError("MODEL_UNAVAILABLE", "Model configuration is not published", 403)
    digest = canonical_digest(
        "aio-model-definition-v1", {"provider": row["provider"], "model": row["model"], "config": row["config"]}
    )
    if digest != row["digest"] or digest != expected_digest:
        raise PlatformError("MODEL_VERSION_CHANGED", "The model configuration no longer matches this run", 409)
    return dict(row)
