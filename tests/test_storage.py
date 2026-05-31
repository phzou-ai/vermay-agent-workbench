from __future__ import annotations

from mini_agent.storage import AgentStore


def test_agent_store_creates_expected_tables(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    rows = store.query("SELECT name FROM sqlite_master WHERE type='table'")
    names = {row["name"] for row in rows}

    assert "memory_items" in names
    assert "skill_index" in names
    assert "eval_runs" in names
    assert "model_profiles" in names
    store.close()
