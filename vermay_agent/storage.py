from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

SCHEMA_VERSION = 6


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SchemaMigration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


def _apply_schema_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1,
            source TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS skill_index (
            name TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            description TEXT,
            triggers TEXT NOT NULL DEFAULT '[]',
            version TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS eval_runs (
            id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_path TEXT NOT NULL,
            status TEXT NOT NULL,
            input TEXT,
            report_path TEXT NOT NULL,
            summary TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS eval_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            name TEXT NOT NULL,
            passed INTEGER NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(run_id) REFERENCES eval_runs(id)
        );

        CREATE TABLE IF NOT EXISTS model_profiles (
            name TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            options TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            thread_id TEXT PRIMARY KEY,
            input TEXT NOT NULL,
            status TEXT NOT NULL,
            final_answer TEXT,
            interrupt TEXT,
            interrupt_message TEXT,
            stop_message TEXT,
            model TEXT,
            max_loops INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


def _apply_schema_v2(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "sessions", "mcp", "TEXT")
    _ensure_column(conn, "sessions", "error_code", "TEXT")
    _ensure_column(conn, "sessions", "error_message", "TEXT")


def _apply_schema_v3(conn: sqlite3.Connection) -> None:
    """Baseline marker for the ordered migration framework."""


def _apply_schema_v4(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "sessions") and _is_legacy_sessions_table(conn, "sessions"):
        if not _table_exists(conn, "legacy_sessions"):
            conn.execute("ALTER TABLE sessions RENAME TO legacy_sessions")
        else:
            conn.execute("DROP TABLE sessions")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            context_id TEXT,
            title TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            thread_id TEXT NOT NULL UNIQUE,
            input TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 1,
            final_answer TEXT,
            interrupt TEXT,
            interrupt_message TEXT,
            stop_message TEXT,
            error_code TEXT,
            error_message TEXT,
            model TEXT,
            max_loops INTEGER,
            mcp TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            context_id TEXT,
            thread_id TEXT,
            event_type TEXT NOT NULL,
            status TEXT,
            payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES tasks(task_id),
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_session_id ON tasks(session_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_thread_id ON tasks(thread_id);
        CREATE INDEX IF NOT EXISTS idx_task_events_task_id_id ON task_events(task_id, id);
        CREATE INDEX IF NOT EXISTS idx_task_events_session_id_id ON task_events(session_id, id);
        """
    )


def _apply_schema_v5(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "tasks", "root_task_id", "TEXT")
    _ensure_column(conn, "tasks", "retry_of_task_id", "TEXT")
    conn.execute("UPDATE tasks SET root_task_id=task_id WHERE root_task_id IS NULL")
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_tasks_root_task_id ON tasks(root_task_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_retry_of_task_id ON tasks(retry_of_task_id);
        """
    )


def _apply_schema_v6(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS task_artifacts (
            artifact_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            context_id TEXT,
            a2a_artifact_id TEXT NOT NULL,
            name TEXT,
            description TEXT,
            parts TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            extensions TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(task_id, a2a_artifact_id),
            FOREIGN KEY(task_id) REFERENCES tasks(task_id),
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_task_artifacts_task_id ON task_artifacts(task_id);
        CREATE INDEX IF NOT EXISTS idx_task_artifacts_session_id ON task_artifacts(session_id);
        """
    )


MIGRATIONS: tuple[SchemaMigration, ...] = (
    SchemaMigration(1, "initial_metadata_tables", _apply_schema_v1),
    SchemaMigration(2, "session_mcp_and_error_metadata", _apply_schema_v2),
    SchemaMigration(3, "ordered_migration_baseline", _apply_schema_v3),
    SchemaMigration(4, "session_task_event_identity_cleanup", _apply_schema_v4),
    SchemaMigration(5, "task_retry_lineage", _apply_schema_v5),
    SchemaMigration(6, "task_artifacts", _apply_schema_v6),
)


@dataclass
class AgentStore:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.setup()

    def setup(self) -> None:
        with self._lock:
            _ensure_schema_migrations_table(self.conn)
            self._apply_pending_migrations()

    def _ensure_column(self, table: str, column: str, declaration: str) -> None:
        _ensure_column(self.conn, table, column, declaration)

    def _apply_pending_migrations(self) -> None:
        applied_versions = self._applied_schema_versions()
        for migration in MIGRATIONS:
            if migration.version in applied_versions:
                continue
            with self.conn:
                migration.apply(self.conn)
                self.conn.execute(
                    """
                    INSERT INTO schema_migrations(version, applied_at)
                    VALUES (?, ?)
                    """,
                    (migration.version, utc_now()),
                )
            applied_versions.add(migration.version)

    def _applied_schema_versions(self) -> set[int]:
        return {
            int(row["version"])
            for row in self.conn.execute("SELECT version FROM schema_migrations")
        }

    def execute(self, sql: str, values: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self.conn.execute(sql, tuple(values))
            self.conn.commit()
            return cursor

    def query(self, sql: str, values: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self.conn.execute(sql, tuple(values)))

    def schema_version(self) -> int:
        rows = self.query("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations")
        return int(rows[0]["version"])

    def upsert_skill_index(
        self,
        *,
        name: str,
        path: Path,
        description: str,
        triggers: list[str],
        version: str,
    ) -> None:
        self.execute(
            """
            INSERT INTO skill_index(name, path, description, triggers, version, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                path=excluded.path,
                description=excluded.description,
                triggers=excluded.triggers,
                version=excluded.version,
                updated_at=excluded.updated_at
            """,
            (
                name,
                str(path),
                description,
                json.dumps(triggers, ensure_ascii=False),
                version,
                utc_now(),
            ),
        )

    def record_eval_run(
        self,
        *,
        run_id: str,
        source_type: str,
        source_path: Path,
        status: str,
        input_text: str,
        report_path: Path,
        summary: dict[str, Any],
    ) -> None:
        self.execute(
            """
            INSERT INTO eval_runs(id, source_type, source_path, status, input, report_path, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source_type,
                str(source_path),
                status,
                input_text,
                str(report_path),
                json.dumps(summary, ensure_ascii=False, sort_keys=True),
                utc_now(),
            ),
        )

    def list_eval_runs(self) -> list[dict[str, Any]]:
        rows = self.query(
            """
            SELECT id, source_type, source_path, status, input, report_path, summary, created_at
            FROM eval_runs
            ORDER BY created_at DESC
            """
        )
        return [dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self.conn.close()


def _ensure_schema_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _is_legacy_sessions_table(conn: sqlite3.Connection, table: str) -> bool:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    return "thread_id" in columns and "session_id" not in columns
