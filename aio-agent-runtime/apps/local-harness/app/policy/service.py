"""纯授权求值器。facts 必须每次由受信仓储读取，不能来自用户 JSON。"""

from datetime import datetime

from ..auth.principal import Principal
from .types import AuthorizationFacts, Decision, DecisionKind, Grant, Resource

# Owning a conversation/file never grants declassification, secrets or arbitrary administration.
OWNER_ACTIONS = {
    "approval": frozenset({"approval.read"}),
    "tool": frozenset({"tool.read", "tool.use"}),
    "model": frozenset({"model.read", "model.use"}),
    "project": frozenset({"project.read", "project.update", "project.members.manage", "project.write"}),
    "session": frozenset({"session.read", "session.update", "session.delete", "session.run"}),
    "run": frozenset({"run.read", "run.cancel"}),
    "artifact": frozenset({"artifact.read", "artifact.download"}),
    "agent": frozenset({"agent.read", "agent.use", "agent.update"}),
    "connection": frozenset({"connection.read", "connection.use", "connection.update", "connection.revoke"}),
    "mcp_server": frozenset({"mcp_server.read", "mcp_server.use", "mcp_server.update"}),
    "knowledge": frozenset({"knowledge.read", "knowledge.search", "knowledge.update"}),
    "document": frozenset({"document.read", "document.update"}),
    "embedding_model": frozenset({"embedding_model.read", "embedding_model.use"}),
    "skill": frozenset({"skill.read", "skill.use", "skill.update"}),
    "skill_import": frozenset({"skill_import.read", "skill_import.update"}),
}
SPECIAL_ACTIONS = frozenset({"approval.decide", "support.read", "artifact.share", "run.reconcile"})
KNOWN_ACTIONS = frozenset().union(*OWNER_ACTIONS.values(), SPECIAL_ACTIONS)


def actions_for_kind(kind: str) -> frozenset[str]:
    extra = {"run": {"run.reconcile"}, "approval": {"approval.decide"}, "artifact": {"artifact.share"}}
    return OWNER_ACTIONS.get(kind, frozenset()) | frozenset(extra.get(kind, set()))


def authorize(
    principal: Principal,
    action: str,
    resource: Resource,
    facts: AuthorizationFacts,
    grants: tuple[Grant, ...] = (),
    *,
    now: datetime,
    delegated_actions: frozenset[str] | None = None,
    requires_approval: bool = False,
) -> Decision:
    if now.tzinfo is None:
        raise ValueError("Authorization requires timezone-aware time")

    def deny(reason: str) -> Decision:
        return Decision(DecisionKind.DENY, reason, facts.policy_revision, resource.revision)

    if principal.org_id != resource.org_id or principal.org_id != facts.org_id or principal.user_id != facts.user_id:
        return deny("RESOURCE_NOT_FOUND")
    if not (facts.user_active and facts.membership_active and facts.org_active):
        return deny("IDENTITY_REVOKED")
    if principal.membership_revision != facts.membership_revision:
        return deny("IDENTITY_REVISION_CHANGED")
    if resource.status != "active":
        return deny("RESOURCE_DISABLED")
    if action not in actions_for_kind(resource.kind):
        return deny("UNKNOWN_RESOURCE_ACTION")
    if action not in KNOWN_ACTIONS:
        return deny("UNKNOWN_ACTION")
    if action in facts.denied_actions:
        return deny("ORGANIZATION_POLICY_DENIED")
    if resource.classification not in facts.allowed_classifications:
        return deny("DATA_POLICY_DENIED")
    if delegated_actions is not None and action not in delegated_actions:
        return deny("DELEGATION_SCOPE_DENIED")
    allowed = principal.user_id == resource.owner_id and action in OWNER_ACTIONS.get(resource.kind, frozenset())
    for grant in grants:
        if grant.org_id != principal.org_id or grant.resource_id != resource.id or grant.action != action:
            continue
        if grant.expires_at is not None and grant.expires_at <= now:
            continue
        if grant.subject_type == "user" and grant.subject_id == principal.user_id:
            allowed = True
        elif grant.subject_type == "department" and grant.subject_id in facts.department_ids:
            allowed = True
    if not allowed:
        return deny("RESOURCE_NOT_FOUND")
    kind = DecisionKind.APPROVAL_REQUIRED if requires_approval else DecisionKind.ALLOW
    return Decision(
        kind, "APPROVAL_REQUIRED" if requires_approval else "ALLOWED", facts.policy_revision, resource.revision
    )
