"""Closed audit metadata schemas. Content is excluded by construction, not a regex.

These contracts cover the audit sink only. Schema-driven filtering of connector,
model and diagnostic outputs is a separate delivery slice.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..policy.service import KNOWN_ACTIONS

Revision = Annotated[int, Field(ge=0, le=9007199254740991, strict=True)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", max_length=64)]
Amount = Annotated[str, Field(pattern=r"^(?:0|[1-9][0-9]{0,13})(?:\.[0-9]{1,6})?$", max_length=21)]
Role = Literal["member", "org_admin", "operator", "auditor"]
PermissionAction = Literal[
    "approval.read", "approval.decide", "tool.read", "tool.use", "model.read", "model.use",
    "project.read", "project.update", "project.members.manage", "project.write",
    "session.read", "session.update", "session.delete", "session.run", "run.read", "run.cancel", "run.reconcile",
    "artifact.read", "artifact.download", "artifact.share", "agent.read", "agent.use", "agent.update",
    "connection.read", "connection.use", "connection.update", "connection.revoke",
    "mcp_server.read", "mcp_server.use", "mcp_server.update", "knowledge.read", "knowledge.search", "knowledge.update",
    "document.read", "document.update", "embedding_model.read", "embedding_model.use",
    "skill.read", "skill.use", "skill.update", "skill_import.read", "skill_import.update", "support.read",
]
ResourceKind = Literal[
    "approval", "tool", "model", "project", "session", "run", "artifact", "agent",
    "connection", "mcp_server", "knowledge", "document", "embedding_model", "skill", "skill_import",
    "organization", "member", "department", "budget", "invocation", "model_call", "embedding_call",
]
ReasonCode = Literal[
    "ALLOWED", "APPROVAL_REQUIRED", "RESOURCE_NOT_FOUND", "IDENTITY_REVOKED",
    "IDENTITY_REVISION_CHANGED", "RESOURCE_DISABLED", "UNKNOWN_RESOURCE_ACTION", "UNKNOWN_ACTION",
    "ORGANIZATION_POLICY_DENIED", "DATA_POLICY_DENIED", "DELEGATION_SCOPE_DENIED",
]


class ClosedMetadata(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, hide_input_in_errors=True, revalidate_instances="always"
    )


class EmptyMetadata(ClosedMetadata):
    pass


class MemberCreated(ClosedMetadata):
    role: Role


class MemberUpdated(MemberCreated):
    active: bool = Field(strict=True)


class DepartmentMembership(ClosedMetadata):
    user_id: UUID


class ResourceGrant(ClosedMetadata):
    subject_type: Literal["user", "department"]
    subject_id: UUID
    actions: tuple[PermissionAction, ...] = Field(min_length=1, max_length=64)

    @field_validator("actions")
    @classmethod
    def known_actions(cls, value):
        if any(action not in KNOWN_ACTIONS for action in value) or len(set(value)) != len(value):
            raise ValueError("Audit grant actions must use the authorization vocabulary")
        return value


class GrantRevoked(ClosedMetadata):
    grant_id: UUID


class BudgetLimit(ClosedMetadata):
    owner_id: UUID
    hard_limit: Amount
    currency: Literal["USD"] = "USD"


class SharedBudgetLimit(ClosedMetadata):
    department_id: UUID | None
    hard_limit: Amount | None
    currency: Literal["USD"] = "USD"
    revision: Revision


class CredentialPrepared(ClosedMetadata):
    binding_id: UUID


class CredentialActivated(ClosedMetadata):
    credential_revision: Revision


class OAuthAuthorized(ClosedMetadata):
    flow_id: UUID


class KnowledgeUpload(ClosedMetadata):
    version_id: UUID


class KnowledgePublished(KnowledgeUpload):
    chunks: Annotated[int, Field(ge=0, le=1000000, strict=True)]


class ArchiveFinished(ClosedMetadata):
    skill_id: UUID | None = None


class SkillValidation(ClosedMetadata):
    job_id: UUID
    reviewer_id: UUID
    package_digest: Digest


class SkillReviewed(ClosedMetadata):
    validation_job_id: UUID
    package_digest: Digest


class ArtifactUploaded(ClosedMetadata):
    bytes: Annotated[int, Field(ge=0, le=9007199254740991, strict=True)]


class ToolPlanned(ClosedMetadata):
    tool_version_id: UUID
    action_digest: Digest


class ToolDispatch(ToolPlanned):
    dispatch_id: UUID
    generation: Annotated[int, Field(ge=1, le=2147483647, strict=True)]


class ToolResult(ToolDispatch):
    outcome_digest: Digest
    dispatch_outcome: Literal["succeeded", "failed", "not_sent"]


class ApprovalDecided(ClosedMetadata):
    invocation_id: UUID
    requested_by: UUID
    requires_different_actor: bool = Field(strict=True)
    action_digest: Digest


class RunReconciled(ClosedMetadata):
    # The free-text evidence reference stays in the business row; the audit fact binds only its digest.
    conclusion: Literal["confirmed_success", "confirmed_failure", "confirmed_no_effect"]
    resolved_invocations: Annotated[int, Field(ge=0, le=10000, strict=True)]
    evidence_digest: Digest


class AuditRead(ClosedMetadata):
    scope: Literal["organization"] = "organization"
    row_count: Annotated[int, Field(ge=0, le=200, strict=True)]
    limit: Annotated[int, Field(ge=1, le=200, strict=True)]
    since: datetime | None = None
    until: datetime | None = None
    before_created_at: datetime | None = None
    before_id: UUID | None = None

    @field_validator("since", "until", "before_created_at")
    @classmethod
    def aware(cls, value):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Audit timestamps require an explicit timezone")
            return value.astimezone(timezone.utc)
        return value

    @model_validator(mode="after")
    def ordered(self):
        if (self.before_created_at is None) != (self.before_id is None):
            raise ValueError("Audit cursor requires both timestamp and identity")
        if self.since is not None and self.until is not None and self.since >= self.until:
            raise ValueError("Audit time window must be increasing")
        return self


AuditMetadata = (
    EmptyMetadata | MemberCreated | MemberUpdated | DepartmentMembership | ResourceGrant | GrantRevoked
    | BudgetLimit | SharedBudgetLimit | CredentialPrepared | CredentialActivated | OAuthAuthorized
    | KnowledgeUpload | KnowledgePublished | ArchiveFinished | SkillValidation | SkillReviewed
    | ArtifactUploaded | ToolPlanned | ToolDispatch | ToolResult | ApprovalDecided | RunReconciled | AuditRead
)


class AuditContext(ClosedMetadata):
    """Only trusted identity, decision facts, revisions and correlation identifiers."""

    org_id: UUID
    actor_id: UUID
    service_actor_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")] | None = None
    resource_id: UUID
    resource_kind: ResourceKind | None = None
    run_id: UUID | None = None
    trace_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$", max_length=32)] | None = None
    decision: Literal["allow", "deny", "approval_required"] | None = None
    reason_code: ReasonCode | None = None
    policy_revision: Revision | None = None
    subject_revision: Revision | None = None
    risk_class: Literal["R0", "R1", "R2"] | None = None

    @field_validator("trace_id")
    @classmethod
    def nonzero_trace(cls, value):
        if value == "0" * 32:
            raise ValueError("A trace identifier must be nonzero")
        return value
