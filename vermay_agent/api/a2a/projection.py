from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..session_models import TaskStatus, normalize_task_status
from ..session_store import TaskArtifactRecord, TaskEventRecord, TaskRecord
from ..task_contract import ARTIFACT_TASK_EVENT_TYPES, INTERNAL_A2A_TASK_EVENT_TYPES


class A2ATaskState(str, Enum):
    UNSPECIFIED = "TASK_STATE_UNSPECIFIED"
    SUBMITTED = "TASK_STATE_SUBMITTED"
    WORKING = "TASK_STATE_WORKING"
    COMPLETED = "TASK_STATE_COMPLETED"
    FAILED = "TASK_STATE_FAILED"
    CANCELED = "TASK_STATE_CANCELED"
    REJECTED = "TASK_STATE_REJECTED"
    INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
    AUTH_REQUIRED = "TASK_STATE_AUTH_REQUIRED"


class A2AProjectionKind(str, Enum):
    TASK = "task"
    ARTIFACT = "artifact"
    STATUS_UPDATE = "status_update"
    ARTIFACT_UPDATE = "artifact_update"
    INTERNAL = "internal"


TERMINAL_A2A_TASK_STATES = frozenset(
    {
        A2ATaskState.COMPLETED,
        A2ATaskState.FAILED,
        A2ATaskState.CANCELED,
        A2ATaskState.REJECTED,
    }
)

_STATUS_MAPPING = {
    TaskStatus.CREATED: A2ATaskState.SUBMITTED,
    TaskStatus.QUEUED: A2ATaskState.SUBMITTED,
    TaskStatus.RUNNING: A2ATaskState.WORKING,
    TaskStatus.INTERRUPTED: A2ATaskState.INPUT_REQUIRED,
    TaskStatus.CANCEL_REQUESTED: A2ATaskState.WORKING,
    TaskStatus.CANCELED: A2ATaskState.CANCELED,
    TaskStatus.COMPLETED: A2ATaskState.COMPLETED,
    TaskStatus.STOPPED: A2ATaskState.FAILED,
    TaskStatus.FAILED: A2ATaskState.FAILED,
    TaskStatus.UNKNOWN: A2ATaskState.UNSPECIFIED,
}

_CANCELED_STATUSES = frozenset({"canceled", "cancelled"})
_REJECTED_STATUSES = frozenset({"rejected"})
_AUTH_REQUIRED_STATUSES = frozenset({"auth_required", "auth-required"})


@dataclass(frozen=True)
class A2AProjection:
    kind: A2AProjectionKind
    payload: dict[str, Any] | None


def project_task(
    task: TaskRecord,
    *,
    context_id: str | None = None,
    artifacts: list[TaskArtifactRecord] | None = None,
) -> A2AProjection:
    resolved_context_id = _context_id(context_id=context_id, session_id=task.session_id)
    task_payload: dict[str, Any] = {
        "id": task.task_id,
        "contextId": resolved_context_id,
        "status": {
            "state": map_task_status(task.status).value,
            "timestamp": task.updated_at,
        },
        "metadata": _metadata(
            session_id=task.session_id,
            task_id=task.task_id,
            local_status=task.status.value,
            attempt=task.attempt,
            root_task_id=task.root_task_id,
            retry_of_task_id=task.retry_of_task_id,
        ),
    }
    if artifacts:
        for artifact in artifacts:
            if artifact.task_id != task.task_id:
                raise ValueError(f"artifact task_id mismatch: task={task.task_id}, artifact={artifact.task_id}")
        task_payload["artifacts"] = [_artifact_payload(artifact) for artifact in artifacts]
    payload = {"task": task_payload}
    return A2AProjection(kind=A2AProjectionKind.TASK, payload=payload)


def project_task_event(event: TaskEventRecord) -> A2AProjection:
    if event.event_type in INTERNAL_A2A_TASK_EVENT_TYPES:
        return A2AProjection(kind=A2AProjectionKind.INTERNAL, payload=None)
    if event.status is None:
        return A2AProjection(kind=A2AProjectionKind.INTERNAL, payload=None)

    context_id = _context_id(context_id=event.context_id, session_id=event.session_id)
    state = map_task_status(event.status)
    payload = {
        "statusUpdate": {
            "taskId": event.task_id,
            "contextId": context_id,
            "status": {
                "state": state.value,
                "timestamp": event.created_at,
            },
            "metadata": _metadata(
                session_id=event.session_id,
                task_id=event.task_id,
                event_id=event.event_id,
                event_type=event.event_type,
                local_status=event.status,
            ),
        }
    }
    return A2AProjection(kind=A2AProjectionKind.STATUS_UPDATE, payload=payload)


def project_task_artifact(artifact: TaskArtifactRecord) -> A2AProjection:
    return A2AProjection(kind=A2AProjectionKind.ARTIFACT, payload={"artifact": _artifact_payload(artifact)})


def project_task_artifact_event(event: TaskEventRecord, *, artifact: TaskArtifactRecord | None) -> A2AProjection:
    if event.event_type not in ARTIFACT_TASK_EVENT_TYPES:
        return A2AProjection(kind=A2AProjectionKind.INTERNAL, payload=None)
    if artifact is None:
        return A2AProjection(kind=A2AProjectionKind.INTERNAL, payload=None)
    if artifact.task_id != event.task_id:
        raise ValueError(f"artifact task_id mismatch: event={event.task_id}, artifact={artifact.task_id}")

    context_id = _context_id(context_id=event.context_id or artifact.context_id, session_id=event.session_id)
    payload = {
        "artifactUpdate": {
            "taskId": event.task_id,
            "contextId": context_id,
            "artifact": _artifact_payload(artifact),
            "append": False,
            "lastChunk": True,
            "metadata": _metadata(
                session_id=event.session_id,
                task_id=event.task_id,
                event_id=event.event_id,
                event_type=event.event_type,
                local_status=event.status or "unknown",
            ),
        }
    }
    return A2AProjection(kind=A2AProjectionKind.ARTIFACT_UPDATE, payload=payload)


def map_task_status(status: object) -> A2ATaskState:
    if isinstance(status, str):
        normalized = status.strip().lower()
        if normalized in _CANCELED_STATUSES:
            return A2ATaskState.CANCELED
        if normalized in _REJECTED_STATUSES:
            return A2ATaskState.REJECTED
        if normalized in _AUTH_REQUIRED_STATUSES:
            return A2ATaskState.AUTH_REQUIRED
    return _STATUS_MAPPING[normalize_task_status(status)]


def is_terminal_a2a_state(state: object) -> bool:
    try:
        normalized = state if isinstance(state, A2ATaskState) else A2ATaskState(str(state))
    except ValueError:
        return False
    return normalized in TERMINAL_A2A_TASK_STATES


def _context_id(*, context_id: str | None, session_id: str) -> str:
    return context_id or session_id


def _artifact_payload(artifact: TaskArtifactRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "artifactId": artifact.a2a_artifact_id,
        "parts": artifact.parts,
        "metadata": artifact.metadata,
        "extensions": artifact.extensions,
    }
    if artifact.name is not None:
        payload["name"] = artifact.name
    if artifact.description is not None:
        payload["description"] = artifact.description
    return payload


def _metadata(
    *,
    session_id: str,
    task_id: str,
    local_status: str,
    attempt: int | None = None,
    root_task_id: str | None = None,
    retry_of_task_id: str | None = None,
    event_id: int | None = None,
    event_type: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "localSessionId": session_id,
        "localTaskId": task_id,
        "localStatus": local_status,
    }
    if attempt is not None:
        metadata["localAttempt"] = attempt
    if root_task_id is not None:
        metadata["localRootTaskId"] = root_task_id
    if retry_of_task_id is not None:
        metadata["localRetryOfTaskId"] = retry_of_task_id
    if event_id is not None:
        metadata["localEventId"] = event_id
    if event_type is not None:
        metadata["localEventType"] = event_type
    return metadata
