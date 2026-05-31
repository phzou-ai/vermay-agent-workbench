from __future__ import annotations

from mini_agent.api.session_store import SessionStore
from mini_agent.langgraph_runtime.results import RunResult
from mini_agent.storage import AgentStore


def test_session_store_persists_run_result_across_reopening(tmp_path):
    path = tmp_path / "agent.sqlite"
    store = AgentStore(path)
    sessions = SessionStore(store)
    sessions.save_result(
        user_input="hello",
        result=RunResult(thread_id="session-1", final_answer="done", state={"raw": "not persisted"}),
        model={"provider": "ollama", "options": {"model": "test"}},
        max_loops=3,
    )
    store.close()

    reopened = AgentStore(path)
    record = SessionStore(reopened).get("session-1")

    assert record is not None
    assert record.thread_id == "session-1"
    assert record.status == "completed"
    assert record.final_answer == "done"
    assert record.model == {"provider": "ollama", "options": {"model": "test"}}
    assert record.max_loops == 3
    assert "state" not in record.to_dict()
    reopened.close()


def test_session_store_maps_interrupted_and_stopped_results(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    sessions = SessionStore(store)

    interrupted = sessions.save_result(
        user_input="dangerous",
        result=RunResult(
            thread_id="session-interrupt",
            interrupt={"kind": "approval_required"},
            interrupt_message="Approval required.",
        ),
        model=None,
        max_loops=5,
    )
    stopped = sessions.save_result(
        user_input="loop",
        result=RunResult(thread_id="session-stopped", stop_message="Stopped."),
        model=None,
        max_loops=5,
    )

    assert interrupted.status == "interrupted"
    assert interrupted.interrupt == {"kind": "approval_required"}
    assert stopped.status == "stopped"
    store.close()
