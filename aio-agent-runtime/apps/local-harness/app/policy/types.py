from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class DecisionKind(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


@dataclass(frozen=True, slots=True)
class Resource:
    org_id: UUID
    id: UUID
    kind: str
    owner_id: UUID
    status: str = "active"
    revision: int = 0
    classification: str = "internal"


@dataclass(frozen=True, slots=True)
class Grant:
    org_id: UUID
    resource_id: UUID
    subject_type: str
    subject_id: UUID
    action: str
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AuthorizationFacts:
    org_id: UUID
    user_id: UUID
    membership_revision: int
    policy_revision: int
    user_active: bool = True
    membership_active: bool = True
    org_active: bool = True
    department_ids: frozenset[UUID] = frozenset()
    denied_actions: frozenset[str] = frozenset()
    allowed_classifications: frozenset[str] = frozenset({"public", "internal"})


@dataclass(frozen=True, slots=True)
class Decision:
    outcome: DecisionKind
    reason_code: str
    policy_revision: int
    resource_revision: int
