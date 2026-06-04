from __future__ import annotations

import sqlite3

import pytest

from vermay_agent import storage
from vermay_agent.storage import AgentStore, SchemaMigration


def test_agent_store_creates_expected_tables(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    rows = store.query("SELECT name FROM sqlite_master WHERE type='table'")
    names = {row["name"] for row in rows}

    assert "memory_items" in names
    assert "skill_index" in names
    assert "eval_runs" in names
    assert "model_profiles" in names
    assert "sessions" in names
    assert "tasks" in names
    assert "task_events" in names
    assert "task_artifacts" in names
    assert "legacy_sessions" in names
    session_columns = {row["name"] for row in store.query("PRAGMA table_info(sessions)")}
    assert "session_id" in session_columns
    assert "context_id" in session_columns
    task_columns = {row["name"] for row in store.query("PRAGMA table_info(tasks)")}
    assert "task_id" in task_columns
    assert "thread_id" in task_columns
    assert "root_task_id" in task_columns
    assert "retry_of_task_id" in task_columns
    event_columns = {row["name"] for row in store.query("PRAGMA table_info(task_events)")}
    assert "event_type" in event_columns
    artifact_columns = {row["name"] for row in store.query("PRAGMA table_info(task_artifacts)")}
    assert "artifact_id" in artifact_columns
    assert "parts" in artifact_columns
    assert "extensions" in artifact_columns
    assert "schema_migrations" in names
    assert store.schema_version() == 6
    store.close()


def test_agent_store_schema_version_persists_across_reopening(tmp_path):
    path = tmp_path / "agent.sqlite"
    store = AgentStore(path)
    assert store.schema_version() == 6
    store.close()

    reopened = AgentStore(path)
    assert reopened.schema_version() == 6
    reopened.close()


def test_agent_store_upgrades_existing_schema_v2_database(tmp_path):
    path = tmp_path / "agent.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        INSERT INTO schema_migrations(version, applied_at) VALUES (2, '2026-06-02T00:00:00+00:00');
        CREATE TABLE sessions (
            thread_id TEXT PRIMARY KEY,
            input TEXT NOT NULL,
            status TEXT NOT NULL,
            final_answer TEXT,
            interrupt TEXT,
            interrupt_message TEXT,
            stop_message TEXT,
            model TEXT,
            max_loops INTEGER,
            mcp TEXT,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.close()

    store = AgentStore(path)

    assert store.schema_version() == 6
    rows = store.query("SELECT version FROM schema_migrations ORDER BY version")
    assert [int(row["version"]) for row in rows] == [1, 2, 3, 4, 5, 6]
    names = {row["name"] for row in store.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "legacy_sessions" in names
    assert "sessions" in names
    session_columns = {row["name"] for row in store.query("PRAGMA table_info(sessions)")}
    assert "session_id" in session_columns
    task_columns = {row["name"] for row in store.query("PRAGMA table_info(tasks)")}
    assert "root_task_id" in task_columns
    assert "retry_of_task_id" in task_columns
    artifact_columns = {row["name"] for row in store.query("PRAGMA table_info(task_artifacts)")}
    assert "artifact_id" in artifact_columns
    store.close()


def test_agent_store_migrations_are_idempotent(tmp_path):
    path = tmp_path / "agent.sqlite"
    first = AgentStore(path)
    first.close()

    second = AgentStore(path)
    rows = second.query("SELECT version, COUNT(*) AS count FROM schema_migrations GROUP BY version")

    assert {int(row["version"]): int(row["count"]) for row in rows} == {1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1}
    second.close()


def test_agent_store_failed_migration_is_not_marked_applied(tmp_path, monkeypatch):
    def broken_migration(conn):
        conn.execute("CREATE TABLE broken_migration_probe (id INTEGER PRIMARY KEY)")
        raise RuntimeError("migration failed")

    monkeypatch.setattr(
        storage,
        "MIGRATIONS",
        storage.MIGRATIONS + (SchemaMigration(7, "broken", broken_migration),),
    )
    path = tmp_path / "agent.sqlite"

    with pytest.raises(RuntimeError, match="migration failed"):
        AgentStore(path)

    conn = sqlite3.connect(path)
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    conn.close()

    assert [int(row[0]) for row in rows] == [1, 2, 3, 4, 5, 6]
