from __future__ import annotations

from vermay_agent.api.session_models import (
    TaskStatus,
    is_active,
    is_cancelable,
    is_resumable,
    is_terminal,
    normalize_task_status,
    status_from_run_result,
)
from vermay_agent.api.task_contract import (
    ARTIFACT_TASK_EVENT_TYPES,
    INTERNAL_A2A_TASK_EVENT_TYPES,
    TERMINAL_TASK_EVENT_TYPES,
    TaskEventType,
)
from vermay_agent.langgraph_runtime.results import RunResult


def test_task_status_normalization_accepts_known_values():
    assert normalize_task_status("created") == TaskStatus.CREATED
    assert normalize_task_status(TaskStatus.RUNNING) == TaskStatus.RUNNING


def test_task_status_normalization_maps_unknown_values():
    assert normalize_task_status("not-a-status") == TaskStatus.UNKNOWN
    assert normalize_task_status(None) == TaskStatus.UNKNOWN


def test_task_status_predicates():
    assert is_terminal("completed") is True
    assert is_terminal("stopped") is True
    assert is_terminal("failed") is True
    assert is_terminal("canceled") is True
    assert is_terminal("interrupted") is False

    assert is_resumable("interrupted") is True
    assert is_resumable("canceled") is False
    assert is_resumable("running") is False

    assert is_active("created") is True
    assert is_active("running") is True
    assert is_active("interrupted") is True
    assert is_active("cancel_requested") is True
    assert is_active("completed") is False

    assert is_cancelable("queued") is True
    assert is_cancelable("running") is True
    assert is_cancelable("interrupted") is True
    assert is_cancelable("canceled") is False


def test_task_status_from_run_result():
    assert status_from_run_result(RunResult(thread_id="done", final_answer="ok")) == TaskStatus.COMPLETED
    assert status_from_run_result(RunResult(thread_id="paused", interrupt_message="Approval required.")) == (
        TaskStatus.INTERRUPTED
    )
    assert status_from_run_result(RunResult(thread_id="paused", interrupt={"kind": "approval_required"})) == (
        TaskStatus.INTERRUPTED
    )
    assert status_from_run_result(RunResult(thread_id="stopped", stop_message="Stopped.")) == TaskStatus.STOPPED
    assert status_from_run_result(RunResult(thread_id="unknown")) == TaskStatus.UNKNOWN


def test_task_event_type_contract_sets():
    assert TaskEventType.CREATED.value == "task_created"
    assert TaskEventType.CANCELLED.value == "task_cancelled"
    assert ARTIFACT_TASK_EVENT_TYPES == {"task_artifact_created", "task_artifact_updated"}
    assert "task_resumed" in INTERNAL_A2A_TASK_EVENT_TYPES
    assert "task_artifact_created" in INTERNAL_A2A_TASK_EVENT_TYPES
    assert TERMINAL_TASK_EVENT_TYPES == {
        "task_interrupted",
        "task_cancelled",
        "task_completed",
        "task_stopped",
        "task_failed",
    }
