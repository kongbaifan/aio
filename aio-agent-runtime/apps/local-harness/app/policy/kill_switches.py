"""Emergency kill switches (GOV-04). Authoritative PG state, re-read in every authorization transaction.

There is no cache or notification path to lose: ``current_facts`` loads unreleased, unexpired switches
alongside the identity facts, so every new Run, model call, tool plan/prepare/consume and approval
decision checks the switch in its own transaction. Reads, cancellation, reconciliation and
administration are never blocked, so operators can always observe and clean up.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select, text

from ..db import schema as s
from ..platform_errors import PlatformError

# Only actions that START or ADVANCE work. Reads, cancel, reconcile and administration stay open.
BLOCKED_ACTIONS = frozenset({
    "session.run", "agent.use", "tool.use", "model.use", "embedding_model.use", "knowledge.search",
    "connection.use", "mcp_server.use", "skill.use", "approval.decide",
})
DRIVER_CLASSES = {
    "sandbox.python": "python", "skill.python": "skill", "skill.read": "skill",
    "mcp.http": "mcp", "mcp.stdio": "mcp", "knowledge.search": "knowledge",
}
RESOURCE_SCOPES = {"tool": "tool", "model": "model", "agent": "agent"}


@dataclass(frozen=True, slots=True)
class KillSwitch:
    id: UUID
    scope: str
    target_id: UUID | None
    execution_class: str | None

    def blocks(self, action: str, resource_kind: str, resource_id: UUID, user_id: UUID) -> bool:
        if action not in BLOCKED_ACTIONS:
            return False
        if self.scope == "organization":
            return True
        if self.scope == "user":
            return self.target_id == user_id
        if self.scope in RESOURCE_SCOPES:
            return resource_kind == RESOURCE_SCOPES[self.scope] and resource_id == self.target_id
        return False  # execution_class needs the driver; enforced in require_driver


def active(connection, org_id: UUID) -> tuple[KillSwitch, ...]:
    """Unreleased switches whose expiry (database clock) has not passed."""
    k = s.kill_switches
    rows = connection.execute(
        select(k.c.id, k.c.scope, k.c.target_id, k.c.execution_class).where(
            k.c.org_id == org_id, k.c.released_at.is_(None),
            or_(k.c.expires_at.is_(None), k.c.expires_at > text("clock_timestamp()")),
        )
    ).all()
    return tuple(KillSwitch(r.id, r.scope, r.target_id, r.execution_class) for r in rows)


def denied() -> PlatformError:
    return PlatformError("KILL_SWITCH_ACTIVE", "This capability is disabled by an emergency switch", 403)


def require_driver(switches, driver: str) -> None:
    cls = DRIVER_CLASSES.get(driver)
    if cls and any(sw.scope == "execution_class" and sw.execution_class == cls for sw in switches):
        raise denied()


def require_manifest(switches, manifest: dict, user_id: UUID, agent_id: UUID) -> None:
    """Admission: refuse a Run whose fixed manifest already needs a disabled capability (no wasted model turn)."""
    if not switches:
        return
    model = manifest.get("model") or {}
    targets = [("agent.use", "agent", agent_id)]
    if model.get("id"):
        targets.append(("model.use", "model", UUID(str(model["id"]))))
    for entry in manifest.get("tools") or []:
        if isinstance(entry, dict) and entry.get("id"):
            targets.append(("tool.use", "tool", UUID(str(entry["id"]))))
            require_driver(switches, entry.get("driver", ""))
    # organization/user scopes block every target above through agent.use already.
    if any(sw.blocks(action, kind, rid, user_id) for sw in switches for action, kind, rid in targets):
        raise denied()


def affects_run(sw: KillSwitch, run, manifest: dict) -> bool:
    if sw.scope == "organization":
        return True
    if sw.scope == "user":
        return run["actor_id"] == sw.target_id
    if sw.scope == "agent":
        return run["agent_version_id"] == sw.target_id
    tools = [e for e in manifest.get("tools") or [] if isinstance(e, dict)]
    if sw.scope == "tool":
        return any(str(e.get("id")) == str(sw.target_id) for e in tools)
    if sw.scope == "model":
        return str((manifest.get("model") or {}).get("id")) == str(sw.target_id)
    return any(DRIVER_CLASSES.get(e.get("driver", "")) == sw.execution_class for e in tools)
