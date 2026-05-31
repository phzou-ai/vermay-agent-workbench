from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

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
            self.conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, utc_now()),
            )
            self.conn.commit()

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
