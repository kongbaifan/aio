"""Typed management requests. The UI cannot submit arbitrary SQL, shell, secrets or Docker flags."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from ..api.v2.contracts import RequestContract
from ..runtime.team_contracts import TeamPolicy


class MemberCreate(RequestContract):
    subject: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=100)
    role: Literal["member", "org_admin", "operator", "auditor"] = "member"


class MemberUpdate(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    display_name: str = Field(min_length=1, max_length=100)
    active: bool = Field(strict=True)
    role: Literal["member", "org_admin", "operator", "auditor"]


class DepartmentCreate(RequestContract):
    name: str = Field(min_length=1, max_length=100)


class DepartmentMember(RequestContract):
    user_id: UUID
    role: Literal["member", "manager"] = "member"


class GrantCreate(RequestContract):
    subject_type: Literal["user", "department"]
    subject_id: UUID
    actions: tuple[str, ...] = Field(min_length=1, max_length=10)
    expires_at: datetime | None = None
    include_dependencies: bool = Field(default=False, strict=True)

    @field_validator("expires_at")
    @classmethod
    def aware(cls, value):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Expiry must be timezone aware")
            return value.astimezone(timezone.utc)
        return value


class ResourceStatus(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    status: Literal["active", "disabled"]


class ModelCreate(RequestContract):
    name: str = Field(min_length=1, max_length=100)
    provider: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    model: str = Field(min_length=1, max_length=128)
    endpoint: str = Field(min_length=1, max_length=1024)
    secret_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    max_output_tokens: int = Field(ge=1, le=32768, strict=True)
    max_call_charge: Decimal = Field(gt=0, le=100, max_digits=12, decimal_places=6)
    input_price_per_million: Decimal = Field(ge=0, le=10000, max_digits=12, decimal_places=6)
    output_price_per_million: Decimal = Field(ge=0, le=10000, max_digits=12, decimal_places=6)
    max_tokens_field: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"


class ToolCreate(RequestContract):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    description: str = Field(min_length=1, max_length=1024)
    sandbox_profile: str = Field(min_length=1, max_length=64)
    timeout_seconds: int = Field(ge=1, le=300, strict=True)


class AgentCreate(RequestContract):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=64)
    instruction: str = Field(min_length=1, max_length=32768)
    model_id: UUID
    tool_ids: tuple[UUID, ...] = Field(default=(), max_length=32)
    skill_ids: tuple[UUID, ...] = Field(default=(), max_length=16)
    mcp_server_ids: tuple[UUID, ...] = Field(default=(), max_length=16)
    knowledge_ids: tuple[UUID, ...] = Field(default=(), max_length=8)
    run_budget: Decimal = Field(gt=0, le=100, max_digits=12, decimal_places=6)
    max_rounds: int = Field(ge=1, le=32, strict=True)
    team: TeamPolicy | None = None

    @model_validator(mode="after")
    def team_round_budget(self):
        if self.team and self.max_rounds < self.team.max_steps + 2:
            raise ValueError("Global round budget must cover planner, all steps and synthesis")
        return self


class BudgetUpdate(RequestContract):
    hard_limit: Decimal = Field(gt=0, le=1000000, max_digits=16, decimal_places=6)


class SharedBudgetUpdate(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    hard_limit: Decimal | None = Field(..., ge=0, le=1000000, max_digits=16, decimal_places=6)


class Rename(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    name: str = Field(min_length=1, max_length=200)


class KillSwitchCreate(RequestContract):
    scope: Literal["organization", "user", "tool", "model", "agent", "execution_class"]
    target_id: UUID | None = None
    execution_class: Literal["python", "mcp", "knowledge", "skill"] | None = None
    reason_code: Literal["SECURITY_INCIDENT", "DATA_EXPOSURE", "COST_RUNAWAY", "PROVIDER_INCIDENT", "OPERATOR_REQUEST"]
    # Free text is accepted for the operator's record but only its digest is stored or audited.
    note: str = Field(min_length=1, max_length=2000)
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def aware(cls, value):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Expiry must be timezone aware")
            return value.astimezone(timezone.utc)
        return value

    @model_validator(mode="after")
    def exact_target(self):
        needs_target = self.scope in {"user", "tool", "model", "agent"}
        if needs_target != (self.target_id is not None):
            raise ValueError("This scope requires exactly one target")
        if (self.scope == "execution_class") != (self.execution_class is not None):
            raise ValueError("Only the execution_class scope names an execution class")
        return self


class KillSwitchRelease(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    evidence: str = Field(min_length=1, max_length=2000)


class OrganizationPolicy(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    allowed_classifications: tuple[Literal["public", "internal", "confidential"], ...] = Field(
        min_length=1, max_length=3
    )
    denied_actions: tuple[str, ...] = Field(default=(), max_length=64)
    storage_limit_bytes: int = Field(ge=1048576, le=1099511627776, strict=True)
