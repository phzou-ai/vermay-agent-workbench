from __future__ import annotations

from enum import Enum

from mini_agent.langgraph_runtime.results import RunResult


class TaskStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELED = "canceled"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"


TERMINAL_TASK_STATUSES = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.STOPPED,
        TaskStatus.FAILED,
        TaskStatus.CANCELED,
    }
)
ACTIVE_TASK_STATUSES = frozenset(
    {
        TaskStatus.CREATED,
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.INTERRUPTED,
        TaskStatus.CANCEL_REQUESTED,
    }
)


def normalize_task_status(value: object) -> TaskStatus:
    if isinstance(value, TaskStatus):
        return value
    try:
        return TaskStatus(str(value))
    except ValueError:
        return TaskStatus.UNKNOWN


def status_from_run_result(result: RunResult) -> TaskStatus:
    return normalize_task_status(result.status)


def is_terminal(status: object) -> bool:
    return normalize_task_status(status) in TERMINAL_TASK_STATUSES


def is_resumable(status: object) -> bool:
    return normalize_task_status(status) == TaskStatus.INTERRUPTED


def is_active(status: object) -> bool:
    return normalize_task_status(status) in ACTIVE_TASK_STATUSES


def is_cancelable(status: object) -> bool:
    return normalize_task_status(status) in ACTIVE_TASK_STATUSES


TERMINAL_SESSION_STATUSES = TERMINAL_TASK_STATUSES
ACTIVE_SESSION_STATUSES = ACTIVE_TASK_STATUSES
SessionStatus = TaskStatus
normalize_session_status = normalize_task_status
