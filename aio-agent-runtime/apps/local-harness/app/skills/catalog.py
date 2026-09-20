"""Current Skill authority; immutable package bytes are not permission grants."""

from uuid import UUID

from sqlalchemy import select

from ..db import schema as s
from ..platform_errors import PlatformError
from ..policy.repository import require_resource


def current_skill(c, principal, skill_id: UUID, digest: str | None = None, *, action="skill.use") -> dict:
    require_resource(c, principal, skill_id, action)
    row = (
        c.execute(
            select(s.skill_versions).where(
                s.skill_versions.c.org_id == principal.org_id, s.skill_versions.c.id == skill_id
            )
        )
        .mappings()
        .first()
    )
    if row is None or row["state"] != "published":
        raise PlatformError("SKILL_UNAVAILABLE", "Skill version is not published", 403)
    from .contracts import package_digest

    actual = package_digest(row["package"])
    if actual != row["digest"] or (digest is not None and digest != actual):
        raise PlatformError("SKILL_VERSION_CHANGED", "Skill package failed immutable version validation", 409)
    return dict(row)


def require_capability_sources(c, principal, values, *, action="skill.use") -> None:
    if not isinstance(values, list) or len(values) > 64 or len(set(values)) != len(values):
        raise PlatformError("SOURCE_POLICY_INVALID", "Capability provenance is invalid", 409)
    for raw in values:
        try:
            id = UUID(raw)
        except (ValueError, TypeError, AttributeError):
            raise PlatformError("SOURCE_POLICY_INVALID", "Capability provenance identity is invalid", 409) from None
        current_skill(c, principal, id, action=action)


def require_sources(c, principal, row) -> None:
    require_capability_sources(c, principal, row["capability_source_ids"])
    require_capability_sources(c, principal, row["capability_read_source_ids"], action="skill.read")


def manifest_sources(c, principal, manifest):
    from ..runtime.catalog import current_tool

    sources = {str(row["id"]) for row in manifest_skills(c, principal, manifest)}
    reads = set()
    for entry in manifest.get("tools", []):
        if entry.get("driver") not in {"skill.read", "skill.python"}:
            continue
        tool = current_tool(c, principal, UUID(entry["id"]), entry)
        id = tool["config"]["skill_id"]
        sources.add(id)
        if tool["driver"] == "skill.read":
            reads.add(id)
    if len(sources) > 16:
        raise PlatformError("SOURCE_POLICY_LIMIT", "Agent has too many Skill capabilities", 409)
    return sources, reads


def manifest_skills(c, principal, manifest: dict) -> list[dict]:
    entries = manifest.get("skills", [])
    if not isinstance(entries, list) or len(entries) > 16:
        raise PlatformError("INVALID_MANIFEST", "Skill manifest is invalid", 409)
    rows, seen = [], set()
    for entry in entries:
        try:
            id, digest = UUID(entry["id"]), entry["digest"]
            if id in seen or not isinstance(digest, str):
                raise ValueError
        except (KeyError, ValueError, TypeError, AttributeError):
            raise PlatformError("INVALID_MANIFEST", "Skill snapshot identity is invalid", 409) from None
        seen.add(id)
        rows.append(current_skill(c, principal, id, digest))
    return rows


def file_text(skill: dict, path: str) -> str:
    for file in skill["package"]["files"]:
        if file["path"] == path:
            return file["content"]
    raise PlatformError("SKILL_FILE_NOT_FOUND", "File is not part of this Skill version", 404)


def skill_for_tool(c, principal, tool: dict) -> dict:
    try:
        config = tool["config"]
        id = UUID(config["skill_id"])
        row = current_skill(c, principal, id, config["skill_digest"])
    except (KeyError, ValueError, TypeError):
        raise PlatformError("SKILL_TOOL_INVALID", "Tool is not bound to an immutable Skill", 409) from None
    if str(tool["id"]) not in {t["id"] for t in row["published_tools"]}:
        raise PlatformError("SKILL_TOOL_INVALID", "Tool was not published with this Skill", 409)
    if row["package"].get("schema_version") == 2 and tool["driver"] == "skill.python":
        if config.get("runtime_manifest_digest") != row["package"]["runtime_manifest_digest"]:
            raise PlatformError(
                "SKILL_RUNTIME_MISMATCH", "Tool is not bound to the Skill's dependency environment", 409
            )
    if tool["driver"] == "skill.read":
        require_resource(c, principal, id, "skill.read")
    return row
