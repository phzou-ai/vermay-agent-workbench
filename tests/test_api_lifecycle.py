from __future__ import annotations

import json

from vermay_agent.api.lifecycle import LifecycleContext, TraceLifecycleObserver, lifecycle_payload
from vermay_agent.trace import TraceLogger


def test_lifecycle_payload_is_compact():
    context = LifecycleContext.create(
        session_id="session-1",
        task_id="task-1",
        thread_id="task:task-1:attempt:1",
        operation="start_task",
        model_provider="ollama",
        max_loops=5,
        mcp_selected=False,
    )

    payload = lifecycle_payload(context, status="completed")

    assert set(payload) == {
        "session_id",
        "task_id",
        "thread_id",
        "operation",
        "status",
        "model_provider",
        "max_loops",
        "mcp_selected",
        "duration_ms",
        "error_code",
    }
    assert payload["session_id"] == "session-1"
    assert payload["task_id"] == "task-1"
    assert payload["thread_id"] == "task:task-1:attempt:1"
    assert payload["operation"] == "start_task"
    assert payload["status"] == "completed"
    assert payload["model_provider"] == "ollama"
    assert payload["max_loops"] == 5
    assert payload["mcp_selected"] is False
    assert payload["error_code"] is None
    assert isinstance(payload["duration_ms"], int)


def test_trace_lifecycle_observer_writes_jsonl_event(tmp_path):
    trace_path = tmp_path / "lifecycle.jsonl"
    observer = TraceLifecycleObserver(TraceLogger(trace_path))

    observer.emit(
        "task_failed",
        {
            "session_id": "session-1",
            "task_id": "task-1",
            "thread_id": "task:task-1:attempt:1",
            "operation": "start_task",
            "status": "failed",
            "model_provider": "ollama",
            "max_loops": 5,
            "mcp_selected": False,
            "duration_ms": 12,
            "error_code": "runtime_error",
        },
    )

    event = json.loads(trace_path.read_text(encoding="utf-8"))
    assert event["type"] == "task_failed"
    assert event["payload"] == {
        "session_id": "session-1",
        "task_id": "task-1",
        "thread_id": "task:task-1:attempt:1",
        "operation": "start_task",
        "status": "failed",
        "model_provider": "ollama",
        "max_loops": 5,
        "mcp_selected": False,
        "duration_ms": 12,
        "error_code": "runtime_error",
    }
