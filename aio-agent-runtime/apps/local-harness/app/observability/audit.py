"""The sole platform audit writer. Facts commit with their caller's transaction."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import json
from dataclasses import dataclass
from typing import get_args
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import insert, select, text
from sqlalchemy.exc import SQLAlchemyError

from ..auth.principal import Principal
from ..db import schema as s
from ..platform_errors import PlatformError
from ..runtime.contracts import bounded_json
from . import redaction as m
from . import scrub

_trace_id: ContextVar[str | None] = ContextVar("platform_audit_trace", default=None)
ARCHIVE_KIND = s.ARCHIVE_KIND


@contextmanager
def trace_scope(trace_id: str):
    # Ignore incoming HTTP trace/header values: the boundary supplies a server-generated ID.
    m.AuditContext(org_id=UUID(int=0), actor_id=UUID(int=0), resource_id=UUID(int=0), trace_id=trace_id)
    token = _trace_id.set(trace_id)
    try:
        yield
    finally:
        _trace_id.reset(token)


@dataclass(frozen=True)
class ActionContract:
    metadata: type[m.ClosedMetadata]
    outcomes: frozenset[str]
    resource_kind: m.ResourceKind | None


def _contract(metadata, outcomes, kind=None):
    return ActionContract(metadata, frozenset(outcomes.split()), kind)


# Every action selects an exact closed model AND an outcome vocabulary. No catch-all action.
CONTRACTS = {
    "member.create": _contract(m.MemberCreated, "created", "member"),
    "member.update": _contract(m.MemberUpdated, "updated", "member"),
    "department.create": _contract(m.EmptyMetadata, "created", "department"),
    "department.membership": _contract(m.DepartmentMembership, "removed granted", "department"),
    "department.status": _contract(m.EmptyMetadata, "active disabled", "department"),
    "resource.grant": _contract(m.ResourceGrant, "granted"),
    "resource.grant.revoke": _contract(m.GrantRevoked, "revoked"),
    "resource.status": _contract(m.EmptyMetadata, "active disabled"),
    "model.version.create": _contract(m.EmptyMetadata, "published", "model"),
    "tool.version.create": _contract(m.EmptyMetadata, "published", "tool"),
    "agent.version.create": _contract(m.EmptyMetadata, "published", "agent"),
    "budget.shared_limit": _contract(m.SharedBudgetLimit, "updated", "budget"),
    "budget.limit": _contract(m.BudgetLimit, "updated", "budget"),
    "operation.stop": _contract(m.EmptyMetadata, "cancel_requested", "run"),
    "organization.policy": _contract(m.EmptyMetadata, "updated", "organization"),
    "mcp.definition.create": _contract(m.EmptyMetadata, "draft", "mcp_server"),
    "mcp.definition.publish": _contract(m.EmptyMetadata, "published", "mcp_server"),
    "mcp.connection.create": _contract(m.EmptyMetadata, "personal department", "connection"),
    "mcp.connection.revoke": _contract(m.EmptyMetadata, "revoked", "connection"),
    "mcp.credential.prepare": _contract(m.CredentialPrepared, "pending", "connection"),
    "mcp.credential.activate": _contract(m.CredentialActivated, "active", "connection"),
    "mcp.discovery": _contract(m.EmptyMetadata, "ready", "connection"),
    "mcp.oauth.authorize": _contract(m.OAuthAuthorized, "authorizing", "connection"),
    "mcp.oauth.complete": _contract(m.CredentialActivated, "authorized", "connection"),
    "knowledge.create": _contract(m.EmptyMetadata, "created", "knowledge"),
    "knowledge.upload.prepare": _contract(m.KnowledgeUpload, "pending", "document"),
    "knowledge.version.publish": _contract(m.KnowledgePublished, "ready", "document"),
    "document.visibility": _contract(m.EmptyMetadata, "restricted inherited", "document"),
    "document.delete": _contract(m.EmptyMetadata, "access_revoked", "document"),
    "embedding.model.create": _contract(m.EmptyMetadata, "published", "embedding_model"),
    "embedding.usage.reconcile": _contract(m.EmptyMetadata, "recorded", "embedding_call"),
    "project.create": _contract(m.EmptyMetadata, "created", "project"),
    "session.create": _contract(m.EmptyMetadata, "created", "session"),
    "session.rename": _contract(m.EmptyMetadata, "renamed", "session"),
    "session.archive": _contract(m.EmptyMetadata, "archived", "session"),
    "run.create": _contract(m.EmptyMetadata, "queued", "run"),
    "run.cancel": _contract(m.EmptyMetadata, "cancelled cancel_requested", "run"),
    "run.finalized": _contract(m.EmptyMetadata, "succeeded failed cancelled timed_out recovery_required", "run"),
    "run.reconcile": _contract(m.RunReconciled, "reconciled", "run"),
    "model.prepared": _contract(m.EmptyMetadata, "prepared", "model_call"),
    "model.usage_reconciled": _contract(m.EmptyMetadata, "accounted", "model_call"),
    "tool.planned": _contract(m.ToolPlanned, "authorized waiting_approval", "invocation"),
    "tool.dispatch_prepared": _contract(m.ToolDispatch, "prepared", "invocation"),
    "tool.dispatch_consumed": _contract(m.ToolDispatch, "dispatching", "invocation"),
    "tool.result": _contract(m.ToolResult, "succeeded failed", "invocation"),
    "approval.decide": _contract(m.ApprovalDecided, "approved rejected expired", "approval"),
    "skill.draft.create": _contract(m.EmptyMetadata, "quarantined", "skill"),
    "skill.validation.request": _contract(m.SkillValidation, "queued", "skill"),
    "skill.review": _contract(m.SkillReviewed, "published rejected", "skill"),
    "skill.archive.prepare": _contract(m.EmptyMetadata, "quarantined", "skill_import"),
    "skill.archive.upload": _contract(m.EmptyMetadata, "queued", "skill_import"),
    "skill.archive.delete": _contract(m.EmptyMetadata, "requested", "skill_import"),
    "skill.archive.finish": _contract(m.ArchiveFinished, "imported cancelled rejected", "skill_import"),
    "artifact.upload": _contract(m.ArtifactUploaded, "stored", "artifact"),
    "audit.read": _contract(m.AuditRead, "read", "organization"),
}


def _unavailable():
    return PlatformError("AUDIT_SINK_UNAVAILABLE", "The required audit fact could not be recorded", 503)


def record(
    c,
    principal: Principal,
    action: str,
    resource_id: UUID,
    outcome: str,
    metadata: m.AuditMetadata = m.EmptyMetadata(),
    *,
    run_id: UUID | None = None,
    resource_kind: m.ResourceKind | None = None,
    decision: str | None = None,
    reason_code: m.ReasonCode | None = None,
    policy_revision: int | None = None,
    subject_revision: int | None = None,
    risk_class: str | None = None,
    event_id: UUID | None = None,
) -> UUID:
    contract = CONTRACTS.get(action)
    if contract is None or outcome not in contract.outcomes or type(metadata) is not contract.metadata:
        raise PlatformError("AUDIT_METADATA_INVALID", "Audit action requires its exact closed metadata contract", 500)
    try:
        # Revalidate instances as well: model_construct/model_copy must not bypass the sink boundary.
        payload = contract.metadata.model_validate(metadata).model_dump(mode="json")
        context = m.AuditContext(
            org_id=principal.org_id, actor_id=principal.user_id, service_actor_id=principal.service_actor_id,
            resource_id=resource_id, resource_kind=resource_kind or contract.resource_kind, run_id=run_id,
            trace_id=_trace_id.get(), decision=decision, reason_code=reason_code, policy_revision=policy_revision,
            subject_revision=subject_revision, risk_class=risk_class,
        )
        if contract.resource_kind is not None and context.resource_kind != contract.resource_kind:
            raise ValueError("Audit subject kind must match its action")
        if event_id is not None and not isinstance(event_id, UUID):
            raise ValueError("Audit identity must be a UUID")
    except (ValidationError, ValueError, TypeError):
        raise PlatformError("AUDIT_METADATA_INVALID", "Audit metadata violates its closed contract", 500) from None
    payload = bounded_json(payload, 4096, "AUDIT_METADATA_TOO_LARGE")
    try:
        # Closed models already exclude content; a hit here means a contract has a gap. Refuse, don't repair.
        scrub.assert_clean(json.dumps([payload, context.model_dump(mode="json")], ensure_ascii=False))
    except scrub.SensitiveLeak:
        raise PlatformError("AUDIT_METADATA_INVALID", "Audit metadata violates its closed contract", 500) from None
    id = event_id or uuid4()
    try:
        # No business row locks or FK lookups. The caller has already authorized the subject;
        # the scoped transaction must nevertheless match the recorded tenant even with a privileged connection.
        org = c.execute(text("SELECT current_setting('aio.org_id', true)")).scalar_one()
        if org != str(principal.org_id):
            raise _unavailable()
        c.execute(
            insert(s.audit).values(
                id=id, **context.model_dump(), action=action, outcome=outcome,
                metadata=payload, metadata_schema=action + ":v1", created_at=text("clock_timestamp()"),
            )
        )
        # Same transaction: a committed fact always has a delivery entry, a rolled-back one never does.
        # The entry is only a pointer; the relay re-reads the fact itself, never a copied payload.
        c.execute(
            insert(s.outbox).values(org_id=principal.org_id, id=uuid4(), aggregate_id=id, kind=ARCHIVE_KIND, payload={})
        )
    except SQLAlchemyError:
        # Never echo DB messages/parameters or an upstream exception chain into an API/SSE error.
        raise _unavailable() from None
    return id


def require_recorded(
    c, principal: Principal, action: str, subject_id: UUID, *, event_id: UUID,
    run_id: UUID | None = None,
) -> None:
    """An exact, fresh receipt is required, not an older fact for the same invocation."""
    if not isinstance(event_id, UUID) or action not in CONTRACTS:
        raise _unavailable()
    try:
        found = c.execute(
            select(s.audit.c.id).where(
                s.audit.c.org_id == principal.org_id, s.audit.c.actor_id == principal.user_id,
                s.audit.c.id == event_id, s.audit.c.action == action, s.audit.c.resource_id == subject_id,
                s.audit.c.run_id == run_id, s.audit.c.metadata_schema == action + ":v1",
            )
        ).first()
    except SQLAlchemyError:
        raise _unavailable() from None
    if found is None:
        raise _unavailable()


# A registry typo cannot silently introduce a permissive model at import time.
assert all(c.metadata in get_args(m.AuditMetadata) for c in CONTRACTS.values())
