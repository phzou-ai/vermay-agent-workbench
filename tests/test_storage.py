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
    assert "contexts" in names
    assert "messages" in names
    assert "route_decisions" in names
    assert "main_agent_tasks" in names
    assert "main_agent_task_events" in names
    assert "artifacts" in names
    assert "registered_agents" in names
    assert "delegated_tasks" in names
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
    message_columns = {row["name"] for row in store.query("PRAGMA table_info(messages)")}
    assert "message_id" in message_columns
    assert "context_id" in message_columns
    main_agent_task_columns = {row["name"] for row in store.query("PRAGMA table_info(main_agent_tasks)")}
    assert "input_message_id" in main_agent_task_columns
    assert "output_message_id" in main_agent_task_columns
    assert "schema_migrations" in names
    assert store.schema_version() == 8
    store.close()


def test_agent_store_schema_version_persists_across_reopening(tmp_path):
    path = tmp_path / "agent.sqlite"
    store = AgentStore(path)
    assert store.schema_version() == 8
    store.close()

    reopened = AgentStore(path)
    assert reopened.schema_version() == 8
    reopened.close()


def test_agent_store_rejects_legacy_schema_without_reset_guard(tmp_path, monkeypatch):
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
    monkeypatch.delenv(storage.DEV_SCHEMA_RESET_ENV, raising=False)

    with pytest.raises(RuntimeError, match=storage.DEV_SCHEMA_RESET_ENV):
        AgentStore(path)


def test_agent_store_resets_legacy_schema_with_development_guard(tmp_path, monkeypatch):
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
        INSERT INTO sessions(
            thread_id, input, status, created_at, updated_at
        ) VALUES ('legacy-thread', 'old input', 'completed', '2026-06-02T00:00:00+00:00', '2026-06-02T00:00:00+00:00');
        """
    )
    conn.close()
    monkeypatch.setenv(storage.DEV_SCHEMA_RESET_ENV, "1")

    store = AgentStore(path)

    assert store.schema_version() == 8
    rows = store.query("SELECT version FROM schema_migrations ORDER BY version")
    assert [int(row["version"]) for row in rows] == [1, 2, 3, 4, 5, 6, 7, 8]
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
    assert "contexts" in names
    assert "main_agent_tasks" in names
    assert "registered_agents" in names
    assert "delegated_tasks" in names
    assert store.query("SELECT * FROM legacy_sessions") == []
    store.close()


def test_agent_store_migrations_are_idempotent(tmp_path):
    path = tmp_path / "agent.sqlite"
    first = AgentStore(path)
    first.close()

    second = AgentStore(path)
    rows = second.query("SELECT version, COUNT(*) AS count FROM schema_migrations GROUP BY version")

    assert {int(row["version"]): int(row["count"]) for row in rows} == {
        1: 1,
        2: 1,
        3: 1,
        4: 1,
        5: 1,
        6: 1,
        7: 1,
        8: 1,
    }
    second.close()


def test_agent_store_transaction_rolls_back_execute_calls(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")

    with pytest.raises(RuntimeError, match="rollback probe"):
        with store.transaction():
            store.execute(
                """
                INSERT INTO skill_index(name, path, triggers, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                ("probe", "/tmp/probe", "[]", "2026-06-11T00:00:00+00:00"),
            )
            raise RuntimeError("rollback probe")

    assert store.query("SELECT name FROM skill_index WHERE name=?", ("probe",)) == []


def test_agent_store_failed_migration_is_not_marked_applied(tmp_path, monkeypatch):
    def broken_migration(conn):
        conn.execute("CREATE TABLE broken_migration_probe (id INTEGER PRIMARY KEY)")
        raise RuntimeError("migration failed")

    monkeypatch.setattr(
        storage,
        "MIGRATIONS",
        storage.MIGRATIONS + (SchemaMigration(9, "broken", broken_migration),),
    )
    path = tmp_path / "agent.sqlite"

    with pytest.raises(RuntimeError, match="migration failed"):
        AgentStore(path)

    conn = sqlite3.connect(path)
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    conn.close()

    assert [int(row[0]) for row in rows] == [1, 2, 3, 4, 5, 6, 7, 8]
