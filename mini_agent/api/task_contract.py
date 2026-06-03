from __future__ import annotations

from enum import Enum


class TaskEventType(str, Enum):
    CREATED = "task_created"
    QUEUED = "task_queued"
    STARTED = "task_started"
    INTERRUPTED = "task_interrupted"
    RESUMED = "task_resumed"
    RETRY_REQUESTED = "task_retry_requested"
    RETRIED = "task_retried"
    CANCEL_REQUESTED = "task_cancel_requested"
    CANCELLED = "task_cancelled"
    ARTIFACT_CREATED = "task_artifact_created"
    ARTIFACT_UPDATED = "task_artifact_updated"
    COMPLETED = "task_completed"
    STOPPED = "task_stopped"
    FAILED = "task_failed"


ARTIFACT_TASK_EVENT_TYPES = frozenset(
    {
        TaskEventType.ARTIFACT_CREATED.value,
        TaskEventType.ARTIFACT_UPDATED.value,
    }
)

INTERNAL_A2A_TASK_EVENT_TYPES = frozenset(
    {
        TaskEventType.RESUMED.value,
        TaskEventType.RETRY_REQUESTED.value,
        TaskEventType.RETRIED.value,
        TaskEventType.CANCEL_REQUESTED.value,
        TaskEventType.ARTIFACT_CREATED.value,
        TaskEventType.ARTIFACT_UPDATED.value,
    }
)

TERMINAL_TASK_EVENT_TYPES = frozenset(
    {
        TaskEventType.INTERRUPTED.value,
        TaskEventType.CANCELLED.value,
        TaskEventType.COMPLETED.value,
        TaskEventType.STOPPED.value,
        TaskEventType.FAILED.value,
    }
)
