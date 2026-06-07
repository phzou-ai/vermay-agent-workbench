from __future__ import annotations

import pytest

from vermay_agent.api.a2a.projection import (
    A2AProjectionKind,
    A2ATaskState,
    is_terminal_a2a_state,
    map_task_status,
    project_task,
    project_task_artifact,
    project_task_artifact_event,
    project_task_event,
)
from vermay_agent.api.output_envelope import OutputVisibility, RedactionStatus, final_answer_envelope
from vermay_agent.api.session_models import TaskStatus
from vermay_agent.api.session_store import TaskArtifactRecord, TaskEventRecord, TaskRecord


def test_a2a_status_mapping_covers_current_local_task_statuses():
    assert map_task_status(TaskStatus.CREATED) == A2ATaskState.SUBMITTED
    assert map_task_status(TaskStatus.QUEUED) == A2ATaskState.SUBMITTED
    assert map_task_status(TaskStatus.RUNNING) == A2ATaskState.WORKING
    assert map_task_status(TaskStatus.INTERRUPTED) == A2ATaskState.INPUT_REQUIRED
    assert map_task_status(TaskStatus.CANCEL_REQUESTED) == A2ATaskState.WORKING
    assert map_task_status(TaskStatus.CANCELED) == A2ATaskState.CANCELED
    assert map_task_status(TaskStatus.COMPLETED) == A2ATaskState.COMPLETED
    assert map_task_status(TaskStatus.STOPPED) == A2ATaskState.FAILED
    assert map_task_status(TaskStatus.FAILED) == A2ATaskState.FAILED
    assert map_task_status(TaskStatus.UNKNOWN) == A2ATaskState.UNSPECIFIED


def test_a2a_status_mapping_reserves_future_protocol_states():
    assert map_task_status("canceled") == A2ATaskState.CANCELED
    assert map_task_status("cancelled") == A2ATaskState.CANCELED
    assert map_task_status("rejected") == A2ATaskState.REJECTED
    assert map_task_status("auth-required") == A2ATaskState.AUTH_REQUIRED


def test_a2a_terminal_state_helper():
    assert is_terminal_a2a_state(A2ATaskState.COMPLETED) is True
    assert is_terminal_a2a_state(A2ATaskState.FAILED.value) is True
    assert is_terminal_a2a_state(A2ATaskState.WORKING) is False
    assert is_terminal_a2a_state("unknown") is False


def test_project_task_uses_context_id_and_omits_thread_id_from_payload():
    task = _task(status=TaskStatus.RUNNING)

    projection = project_task(task, context_id="ctx-1")

    assert projection.kind == A2AProjectionKind.TASK
    assert projection.payload == {
        "kind": "task",
        "id": "task-1",
        "contextId": "ctx-1",
        "status": {
            "state": "TASK_STATE_WORKING",
            "timestamp": "2026-06-03T00:00:01+00:00",
        },
        "metadata": {
            "localSessionId": "session-1",
            "localTaskId": "task-1",
            "localStatus": "running",
            "localAttempt": 1,
            "localRootTaskId": "task-1",
        },
    }
    assert "thread_id" not in str(projection.payload)
    assert "thread-1" not in str(projection.payload)


def test_project_task_falls_back_to_session_id_as_context_id():
    task = _task(status=TaskStatus.COMPLETED)

    projection = project_task(task)

    assert projection.payload is not None
    assert projection.payload["kind"] == "task"
    assert projection.payload["contextId"] == "session-1"
    assert projection.payload["status"]["state"] == "TASK_STATE_COMPLETED"


def test_project_retry_task_includes_local_lineage_metadata():
    task = _task(
        status=TaskStatus.RUNNING,
        task_id="task-2",
        root_task_id="task-1",
        retry_of_task_id="task-1",
        attempt=2,
    )

    projection = project_task(task, context_id="ctx-1")

    assert projection.payload is not None
    metadata = projection.payload["metadata"]
    assert metadata["localTaskId"] == "task-2"
    assert metadata["localAttempt"] == 2
    assert metadata["localRootTaskId"] == "task-1"
    assert metadata["localRetryOfTaskId"] == "task-1"


def test_project_task_can_include_artifacts_without_thread_id():
    task = _task(status=TaskStatus.COMPLETED)
    artifact = _artifact()

    projection = project_task(task, context_id="ctx-1", artifacts=[artifact])

    assert projection.kind == A2AProjectionKind.TASK
    assert projection.payload is not None
    assert projection.payload["artifacts"] == [
        {
            "artifactId": "final_answer",
            "name": "Final answer",
            "description": "Final text answer returned by the agent.",
            "parts": [{"text": "done", "mediaType": "text/plain"}],
            "metadata": final_answer_envelope().to_metadata(),
            "extensions": [],
        }
    ]
    assert "task-1:final_answer" not in str(projection.payload)
    assert "thread-1" not in str(projection.payload)


def test_project_task_omits_non_projectable_artifacts():
    task = _task(status=TaskStatus.COMPLETED)
    artifact = _artifact(metadata=_final_answer_metadata(visibility=OutputVisibility.INTERNAL.value))

    projection = project_task(task, context_id="ctx-1", artifacts=[artifact])

    assert projection.kind == A2AProjectionKind.TASK
    assert projection.payload is not None
    assert "artifacts" not in projection.payload


def test_project_task_requires_matching_artifact_task_id():
    task = _task(status=TaskStatus.COMPLETED)

    with pytest.raises(ValueError, match="artifact task_id mismatch"):
        project_task(task, artifacts=[_artifact(task_id="task-2")])


def test_project_task_event_maps_status_update():
    event = _event(event_type="task_queued", status="queued", context_id="ctx-1")

    projection = project_task_event(event)

    assert projection.kind == A2AProjectionKind.STATUS_UPDATE
    assert projection.payload == {
        "kind": "status-update",
        "taskId": "task-1",
        "contextId": "ctx-1",
        "status": {
            "state": "TASK_STATE_SUBMITTED",
            "timestamp": "2026-06-03T00:00:02+00:00",
        },
        "metadata": {
            "localSessionId": "session-1",
            "localTaskId": "task-1",
            "localStatus": "queued",
            "localEventId": 7,
            "localEventType": "task_queued",
        },
    }
    assert "thread-1" not in str(projection.payload)


def test_project_task_event_keeps_internal_events_out_of_status_stream():
    projection = project_task_event(_event(event_type="task_resumed", status="interrupted"))

    assert projection.kind == A2AProjectionKind.INTERNAL
    assert projection.payload is None


def test_project_task_event_keeps_artifact_events_out_of_status_stream():
    projection = project_task_event(_event(event_type="task_artifact_created", status="completed"))

    assert projection.kind == A2AProjectionKind.INTERNAL
    assert projection.payload is None


def test_project_task_event_maps_cancelled_status_update():
    projection = project_task_event(_event(event_type="task_cancelled", status="canceled"))

    assert projection.kind == A2AProjectionKind.STATUS_UPDATE
    assert projection.payload is not None
    assert projection.payload["kind"] == "status-update"
    assert projection.payload["status"]["state"] == "TASK_STATE_CANCELED"


def test_project_task_artifact_projects_a2a_artifact_payload():
    projection = project_task_artifact(_artifact())

    assert projection.kind == A2AProjectionKind.ARTIFACT
    assert projection.payload == {
        "kind": "artifact",
        "artifactId": "final_answer",
        "name": "Final answer",
        "description": "Final text answer returned by the agent.",
        "parts": [{"text": "done", "mediaType": "text/plain"}],
        "metadata": final_answer_envelope().to_metadata(),
        "extensions": [],
    }
    assert "task-1:final_answer" not in str(projection.payload)


def test_project_task_artifact_normalizes_legacy_final_answer_metadata():
    projection = project_task_artifact(_artifact(metadata={"kind": "final_answer"}))

    assert projection.kind == A2AProjectionKind.ARTIFACT
    assert projection.payload is not None
    assert projection.payload["metadata"] == final_answer_envelope().to_metadata()


def test_project_task_artifact_keeps_non_projectable_artifact_internal():
    projection = project_task_artifact(_artifact(metadata=_final_answer_metadata(redaction_status=RedactionStatus.UNSAFE.value)))

    assert projection.kind == A2AProjectionKind.INTERNAL
    assert projection.payload is None


def test_project_task_artifact_event_maps_artifact_update():
    event = _event(event_type="task_artifact_created", status="completed", context_id="ctx-1")

    projection = project_task_artifact_event(event, artifact=_artifact())

    assert projection.kind == A2AProjectionKind.ARTIFACT_UPDATE
    assert projection.payload == {
        "kind": "artifact-update",
        "taskId": "task-1",
        "contextId": "ctx-1",
        "artifact": {
            "artifactId": "final_answer",
            "name": "Final answer",
            "description": "Final text answer returned by the agent.",
            "parts": [{"text": "done", "mediaType": "text/plain"}],
            "metadata": final_answer_envelope().to_metadata(),
            "extensions": [],
        },
        "append": False,
        "lastChunk": True,
        "metadata": {
            "localSessionId": "session-1",
            "localTaskId": "task-1",
            "localStatus": "completed",
            "localEventId": 7,
            "localEventType": "task_artifact_created",
        },
    }
    assert "task-1:final_answer" not in str(projection.payload)
    assert "thread-1" not in str(projection.payload)


def test_project_task_artifact_event_keeps_non_projectable_artifact_internal():
    event = _event(event_type="task_artifact_created", status="completed", context_id="ctx-1")

    projection = project_task_artifact_event(
        event,
        artifact=_artifact(metadata=_final_answer_metadata(redaction_status=RedactionStatus.UNKNOWN.value)),
    )

    assert projection.kind == A2AProjectionKind.INTERNAL
    assert projection.payload is None


def test_project_task_artifact_event_falls_back_to_artifact_context_id():
    event = _event(event_type="task_artifact_updated", status="completed")

    projection = project_task_artifact_event(event, artifact=_artifact(context_id="artifact-ctx"))

    assert projection.payload is not None
    assert projection.payload["kind"] == "artifact-update"
    assert projection.payload["contextId"] == "artifact-ctx"


def test_project_task_artifact_event_ignores_non_artifact_events():
    projection = project_task_artifact_event(_event(event_type="task_completed", status="completed"), artifact=_artifact())

    assert projection.kind == A2AProjectionKind.INTERNAL
    assert projection.payload is None


def test_project_task_artifact_event_requires_matching_task_id():
    event = _event(event_type="task_artifact_created", status="completed")

    with pytest.raises(ValueError, match="artifact task_id mismatch"):
        project_task_artifact_event(event, artifact=_artifact(task_id="task-2"))


def _task(
    *,
    status: TaskStatus,
    task_id: str = "task-1",
    root_task_id: str | None = "task-1",
    retry_of_task_id: str | None = None,
    attempt: int = 1,
) -> TaskRecord:
    return TaskRecord(
        task_id=task_id,
        session_id="session-1",
        thread_id="thread-1",
        root_task_id=root_task_id,
        retry_of_task_id=retry_of_task_id,
        input="hidden input",
        status=status,
        attempt=attempt,
        final_answer=None,
        interrupt=None,
        interrupt_message=None,
        stop_message=None,
        error_code=None,
        error_message=None,
        model=None,
        max_loops=None,
        mcp=None,
        created_at="2026-06-03T00:00:00+00:00",
        updated_at="2026-06-03T00:00:01+00:00",
    )


def _artifact(
    *,
    task_id: str = "task-1",
    context_id: str | None = "ctx-1",
    metadata: dict | None = None,
) -> TaskArtifactRecord:
    return TaskArtifactRecord(
        artifact_id=f"{task_id}:final_answer",
        task_id=task_id,
        session_id="session-1",
        context_id=context_id,
        a2a_artifact_id="final_answer",
        name="Final answer",
        description="Final text answer returned by the agent.",
        parts=[{"text": "done", "mediaType": "text/plain"}],
        metadata=metadata or final_answer_envelope().to_metadata(),
        extensions=[],
        created_at="2026-06-03T00:00:02+00:00",
        updated_at="2026-06-03T00:00:03+00:00",
    )


def _final_answer_metadata(**updates) -> dict:
    metadata = final_answer_envelope().to_metadata()
    metadata.update(updates)
    return metadata


def _event(*, event_type: str, status: str | None, context_id: str | None = None) -> TaskEventRecord:
    return TaskEventRecord(
        event_id=7,
        task_id="task-1",
        session_id="session-1",
        context_id=context_id,
        thread_id="thread-1",
        event_type=event_type,
        status=status,
        payload={},
        created_at="2026-06-03T00:00:02+00:00",
    )
