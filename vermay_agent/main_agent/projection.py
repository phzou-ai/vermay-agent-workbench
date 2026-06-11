from __future__ import annotations

from enum import Enum
from typing import Any

from vermay_agent.a2a_metadata import thread_metadata

from .models import ArtifactRecord, TaskEventRecord, TaskRecord, TaskStatus, normalize_task_status


class A2ATaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    AUTH_REQUIRED = "auth-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"


_STATUS_TO_A2A = {
    TaskStatus.CREATED: A2ATaskState.SUBMITTED,
    TaskStatus.QUEUED: A2ATaskState.SUBMITTED,
    TaskStatus.RUNNING: A2ATaskState.WORKING,
    TaskStatus.CANCEL_REQUESTED: A2ATaskState.WORKING,
    TaskStatus.INPUT_REQUIRED: A2ATaskState.INPUT_REQUIRED,
    TaskStatus.AUTH_REQUIRED: A2ATaskState.AUTH_REQUIRED,
    TaskStatus.COMPLETED: A2ATaskState.COMPLETED,
    TaskStatus.CANCELED: A2ATaskState.CANCELED,
    TaskStatus.FAILED: A2ATaskState.FAILED,
}


def task_status_to_a2a_state(status: object) -> A2ATaskState:
    return _STATUS_TO_A2A[normalize_task_status(status)]


def task_to_a2a_payload(task: TaskRecord) -> dict[str, Any]:
    return {
        "kind": "task",
        "id": task.task_id,
        "contextId": task.context_id,
        "status": {
            "state": task_status_to_a2a_state(task.status).value,
            "timestamp": task.updated_at,
        },
        "metadata": {
            "localContextId": task.context_id,
            "localTaskId": task.task_id,
            **thread_metadata(task.runtime_thread_id, include_runtime_alias=True),
            "inputMessageId": task.input_message_id,
            "outputMessageId": task.output_message_id,
            "localStatus": task.status.value,
            "localAttempt": task.attempt,
        },
    }


def task_event_to_a2a_status_update(event: TaskEventRecord, *, task: TaskRecord) -> dict[str, Any] | None:
    if event.status is None:
        return None
    return {
        "kind": "status-update",
        "taskId": event.task_id,
        "contextId": task.context_id,
        "status": {
            "state": task_status_to_a2a_state(event.status).value,
            "timestamp": event.created_at,
        },
        "final": task_status_to_a2a_state(event.status) in {
            A2ATaskState.COMPLETED,
            A2ATaskState.CANCELED,
            A2ATaskState.FAILED,
        },
        "metadata": {
            "localEventId": event.event_id,
            "localEventType": event.type,
            "localEventCreatedAt": event.created_at,
            **thread_metadata(task.runtime_thread_id, include_runtime_alias=True),
            "localStatus": event.status.value,
        },
    }


def task_event_to_a2a_artifact_update(
    event: TaskEventRecord,
    *,
    task: TaskRecord,
    artifact: ArtifactRecord | None,
) -> dict[str, Any] | None:
    if event.type not in {"task_artifact_created", "task_artifact_updated"}:
        return None
    if artifact is None:
        return None
    return {
        "kind": "artifact-update",
        "taskId": event.task_id,
        "contextId": task.context_id,
        "artifact": {
            "artifactId": str(artifact.metadata.get("kind") or artifact.artifact_id),
            "parts": artifact.parts,
            "metadata": artifact.metadata,
        },
        "append": False,
        "lastChunk": True,
        "metadata": {
            "localEventId": event.event_id,
            "localEventType": event.type,
            "localEventCreatedAt": event.created_at,
            "localArtifactId": artifact.artifact_id,
            **thread_metadata(task.runtime_thread_id, include_runtime_alias=True),
        },
    }
