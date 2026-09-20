"""Team plans are untrusted data, not permission-bearing agent definitions."""

from typing import Literal
from pydantic import Field, ValidationError, field_validator

from ..platform_errors import PlatformError
from .actions import ImmutableContract, strict_json


class TeamPolicy(ImmutableContract):
    max_steps: int = Field(default=4, ge=1, le=6, strict=True)
    max_step_rounds: int = Field(default=4, ge=1, le=16, strict=True)


class TeamStep(ImmutableContract):
    title: str = Field(min_length=1, max_length=120)
    task: str = Field(min_length=1, max_length=4000)
    tools: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("title", "task")
    @classmethod
    def nonempty(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Step text must not be empty or contain NUL")
        return value

    @field_validator("tools")
    @classmethod
    def aliases(cls, value):
        import re

        if len(set(value)) != len(value) or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", t) for t in value):
            raise ValueError("Step tools must be unique registered aliases")
        return value


class TeamPlan(ImmutableContract):
    schema_version: Literal[1] = 1
    steps: tuple[TeamStep, ...] = Field(min_length=1, max_length=6)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Plan version must be an integer")
        return value


def policy_for(manifest: dict, *, required: bool = False) -> TeamPolicy | None:
    value = manifest.get("team")
    if value is None:
        if required:
            raise PlatformError("TEAM_NOT_ENABLED", "This agent version has not enabled team mode", 409)
        return None
    try:
        policy = TeamPolicy.model_validate(value)
        rounds = manifest["max_rounds"]
        if type(rounds) is not int or not policy.max_steps + 2 <= rounds <= 32:
            raise ValueError
    except (KeyError, TypeError, ValueError, ValidationError):
        raise PlatformError(
            "TEAM_POLICY_INVALID", "Team policy must reserve planner, step and synthesis rounds", 409
        ) from None
    return policy


def manifest_aliases(manifest: dict) -> set[str]:
    entries = manifest.get("tools", [])
    try:
        names = [item["name"] for item in entries]
        if len(names) != len(set(names)) or len(names) > 64:
            raise ValueError
        TeamStep(title="aliases", task="validate", tools=tuple(names))
    except (KeyError, TypeError, ValueError, ValidationError):
        raise PlatformError("INVALID_MANIFEST", "Tool aliases must be unique and bounded", 409) from None
    return set(names)


def parse_plan(raw: str, manifest: dict) -> TeamPlan:
    policy = policy_for(manifest, required=True)
    allowed = manifest_aliases(manifest)
    try:
        plan = TeamPlan.model_validate(strict_json(raw.encode("utf-8"), max_bytes=65536))
        if len(plan.steps) > policy.max_steps or any(set(step.tools) - allowed for step in plan.steps):
            raise ValueError
    except (ValueError, TypeError, ValidationError, PlatformError):
        raise PlatformError(
            "TEAM_PLAN_INVALID", "Planner must return a bounded plan using only approved tools", 409
        ) from None
    return plan
