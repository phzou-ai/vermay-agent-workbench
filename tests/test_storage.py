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
    assert "schema_migrations" in names
    assert store.schema_version() == 1
    store.close()


def test_agent_store_schema_version_persists_across_reopening(tmp_path):
    path = tmp_path / "agent.sqlite"
    store = AgentStore(path)
    assert store.schema_version() == 1
    store.close()

    reopened = AgentStore(path)
    assert reopened.schema_version() == 1
    reopened.close()
