"""显式状态表：未知外部效果不是可安全重试的普通失败。"""

from enum import Enum

from ..platform_errors import PlatformError


class RunState(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    PERSISTING = "persisting"
    CANCEL_REQUESTED = "cancel_requested"
    RECOVERY_REQUIRED = "recovery_required"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


TERMINAL_STATES = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED, RunState.TIMED_OUT})
UNRESOLVED_STATES = frozenset(set(RunState) - TERMINAL_STATES)
TRANSITIONS = {
    RunState.QUEUED: frozenset({RunState.PREPARING, RunState.CANCELLED, RunState.TIMED_OUT, RunState.FAILED}),
    RunState.PREPARING: frozenset(
        {RunState.RUNNING, RunState.CANCEL_REQUESTED, RunState.FAILED, RunState.TIMED_OUT, RunState.RECOVERY_REQUIRED}
    ),
    RunState.RUNNING: frozenset(
        {
            RunState.WAITING_APPROVAL,
            RunState.PERSISTING,
            RunState.CANCEL_REQUESTED,
            RunState.FAILED,
            RunState.TIMED_OUT,
            RunState.RECOVERY_REQUIRED,
        }
    ),
    RunState.WAITING_APPROVAL: frozenset(
        {RunState.RUNNING, RunState.CANCEL_REQUESTED, RunState.FAILED, RunState.TIMED_OUT, RunState.RECOVERY_REQUIRED}
    ),
    RunState.PERSISTING: frozenset(
        {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCEL_REQUESTED, RunState.RECOVERY_REQUIRED}
    ),
    RunState.CANCEL_REQUESTED: frozenset({RunState.CANCELLED, RunState.RECOVERY_REQUIRED, RunState.FAILED}),
    RunState.RECOVERY_REQUIRED: frozenset(
        {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED, RunState.TIMED_OUT}
    ),
    **{state: frozenset() for state in TERMINAL_STATES},
}


def require_transition(current: RunState | str, target: RunState | str, *, reconciliation: bool = False) -> None:
    try:
        old, new = RunState(current), RunState(target)
    except ValueError:
        raise PlatformError("INVALID_RUN_STATE", "Unknown run state", 409) from None
    if old == RunState.RECOVERY_REQUIRED and not reconciliation:
        raise PlatformError("RECONCILIATION_REQUIRED", "Uncertain effects require an authorized reconciliation", 409)
    if new not in TRANSITIONS[old]:
        raise PlatformError("INVALID_TRANSITION", "This run state transition is not permitted", 409)


def require_generation(actual: int, expected: int) -> None:
    if type(expected) is not int or expected < 1 or actual != expected:
        raise PlatformError("STALE_GENERATION", "This execution lease is no longer current", 409)
