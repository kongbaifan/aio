"""Schema-driven masking of sensitive values on every egress (GOV-02.04).

Two independent rules, both applied, and neither depends on recognising a secret by its shape:
1. Structural: a JSON-schema property marked ``"x-aio-sensitive": true`` is masked wherever that
   path appears (the value is never inspected). The mark lives in the tool's ``input_schema``,
   so it is part of ``definition_digest``: removing it later changes the digest and fails the
   run-manifest check instead of silently un-masking.
2. Material: any occurrence of a currently known secret value (credential, token, env value) in
   any string, in any encoding we emit (raw, percent-encoded, base64), is replaced.

Prefix regexes are not used; an unmarked value that is not known secret material passes as is.
``assert_clean`` is the defence-in-depth check for sinks that must refuse rather than repair.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable, Mapping
from urllib.parse import quote

SENSITIVE = "x-aio-sensitive"
MASK = "[sensitive]"
MATERIAL_MASK = "[credential-redacted]"
# Below this length a "secret" would mask ordinary words; such values are rejected at configuration.
MIN_MATERIAL_LENGTH = 8
_MAX_DEPTH = 32


class SensitiveLeak(Exception):
    """A sink received known secret material after scrubbing: refuse, never write it."""


def validate_mark(schema: Mapping) -> None:
    """The mark is a strict boolean on a schema node; anything else is a configuration error."""

    def walk(node, depth=0):
        if depth > _MAX_DEPTH:
            return
        if isinstance(node, Mapping):
            if SENSITIVE in node and node[SENSITIVE] is not True:
                raise ValueError(f"{SENSITIVE} must be the boolean true when present")
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, list):
            for value in node:
                walk(value, depth + 1)

    walk(schema)


def sensitive_paths(schema: Mapping) -> frozenset[tuple[str, ...]]:
    """Property paths ("*" = any array index) whose schema node carries the mark.

    Follows local ``#/$defs/`` refs and allOf/anyOf/oneOf, so a mark cannot be hidden behind
    composition. A marked object/array masks its whole subtree.
    """
    found: set[tuple[str, ...]] = set()

    def resolve(node):
        ref = node.get("$ref") if isinstance(node, Mapping) else None
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            return schema.get("$defs", {}).get(ref[len("#/$defs/"):], {})
        return node

    def walk(node, path, depth):
        node = resolve(node)
        if depth > _MAX_DEPTH or not isinstance(node, Mapping):
            return
        if node.get(SENSITIVE) is True:
            found.add(path)
            return
        for key in ("allOf", "anyOf", "oneOf"):
            for branch in node.get(key, ()) if isinstance(node.get(key), list) else ():
                walk(branch, path, depth + 1)
        for name, child in (node.get("properties") or {}).items():
            walk(child, (*path, name), depth + 1)
        for key in ("items", "additionalProperties"):
            if isinstance(node.get(key), Mapping):
                walk(node[key], (*path, "*"), depth + 1)
        for child in node.get("prefixItems", ()) if isinstance(node.get("prefixItems"), list) else ():
            walk(child, (*path, "*"), depth + 1)

    walk(schema, (), 0)
    return frozenset(found)


def material_forms(secrets: Iterable[str]) -> tuple[str, ...]:
    """Every encoding of each secret that our own transports may emit, longest first."""
    forms = set()
    for secret in secrets:
        if not isinstance(secret, str) or len(secret) < MIN_MATERIAL_LENGTH:
            continue
        raw = secret.encode("utf-8")
        forms.update({secret, quote(secret, safe=""), base64.b64encode(raw).decode("ascii"),
                      base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")})
    return tuple(sorted(forms, key=len, reverse=True))


def _matches(path: tuple[str, ...], patterns: frozenset[tuple[str, ...]]) -> bool:
    return any(
        len(pattern) <= len(path) and all(p == "*" or p == q for p, q in zip(pattern, path))
        for pattern in patterns
    )


def scrub(value, *, sensitive: frozenset[tuple[str, ...]] = frozenset(), secrets: Iterable[str] = ()):
    """Return a copy with marked paths masked and known secret material removed from all strings."""
    forms = material_forms(secrets)

    def text(item: str) -> str:
        for form in forms:
            if form in item:
                item = item.replace(form, MATERIAL_MASK)
        return item

    def walk(item, path, depth):
        if sensitive and _matches(path, sensitive):
            return MASK
        if depth > _MAX_DEPTH:
            return MASK
        if isinstance(item, str):
            return text(item)
        if isinstance(item, Mapping):
            return {text(str(k)): walk(v, (*path, str(k)), depth + 1) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [walk(v, (*path, "*"), depth + 1) for v in item]
        return item

    return walk(value, (), 0)


def assert_clean(serialized: str, secrets: Iterable[str]) -> None:
    """Refuse (never repair) when known material survived scrubbing: it means a layer has a gap."""
    for form in material_forms(secrets):
        if form in serialized:
            raise SensitiveLeak("Known secret material reached a sink")
