from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from vermay_agent.langgraph_runtime.results import RunResult
from vermay_agent.storage import AgentStore, utc_now

from .session_models import TaskStatus, normalize_task_status, status_from_run_result


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    context_id: str | None
    title: str | None
    status: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "context_id": self.context_id,
            "title": self.title,
            "status": self.status,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    session_id: str
    thread_id: str
    root_task_id: str | None
    retry_of_task_id: str | None
    input: str
    status: TaskStatus
    attempt: int
    final_answer: str | None
    interrupt: Any | None
    interrupt_message: str | None
    stop_message: str | None
    error_code: str | None
    error_message: str | None
    model: dict[str, Any] | None
    max_loops: int | None
    mcp: dict[str, Any] | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "thread_id": self.thread_id,
            "root_task_id": self.root_task_id,
            "retry_of_task_id": self.retry_of_task_id,
            "status": self.status.value,
            "input": self.input,
            "attempt": self.attempt,
            "final_answer": self.final_answer,
            "interrupt": self.interrupt,
            "interrupt_message": self.interrupt_message,
            "stop_message": self.stop_message,
            "error": _error_payload(self.error_code, self.error_message),
            "model": self.model,
            "max_loops": self.max_loops,
            "mcp": self.mcp,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class TaskEventRecord:
    event_id: int
    task_id: str
    session_id: str
    context_id: str | None
    thread_id: str | None
    event_type: str
    status: str | None
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "context_id": self.context_id,
            "thread_id": self.thread_id,
            "event_type": self.event_type,
            "status": self.status,
            "payload": self.payload,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class TaskArtifactRecord:
    artifact_id: str
    task_id: str
    session_id: str
    context_id: str | None
    a2a_artifact_id: str
    name: str | None
    description: str | None
    parts: list[dict[str, Any]]
    metadata: dict[str, Any]
    extensions: list[str]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "context_id": self.context_id,
            "a2a_artifact_id": self.a2a_artifact_id,
            "name": self.name,
            "description": self.description,
            "parts": self.parts,
            "metadata": self.metadata,
            "extensions": self.extensions,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SessionStore:
    def __init__(self, store: AgentStore) -> None:
        self.store = store

    def create_session(
        self,
        *,
        session_id: str,
        context_id: str | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionRecord:
        now = utc_now()
        self.store.execute(
            """
            INSERT INTO sessions(session_id, context_id, title, status, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                context_id,
                title,
                "active",
                _dumps(metadata or {}) or "{}",
                now,
                now,
            ),
        )
        record = self.get_session(session_id)
        if record is None:
            raise RuntimeError(f"failed to create session: {session_id}")
        return record

    def get_session(self, session_id: str) -> SessionRecord | None:
        rows = self.store.query(
            """
            SELECT session_id, context_id, title, status, metadata, created_at, updated_at
            FROM sessions
            WHERE session_id=?
            """,
            (session_id,),
        )
        if not rows:
            return None
        row = rows[0]
        return SessionRecord(
            session_id=str(row["session_id"]),
            context_id=row["context_id"],
            title=row["title"],
            status=str(row["status"]),
            metadata=_loads(row["metadata"]) or {},
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def get_session_by_context_id(self, context_id: str) -> SessionRecord | None:
        rows = self.store.query(
            """
            SELECT session_id, context_id, title, status, metadata, created_at, updated_at
            FROM sessions
            WHERE context_id=?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (context_id,),
        )
        if not rows:
            return None
        row = rows[0]
        return SessionRecord(
            session_id=str(row["session_id"]),
            context_id=row["context_id"],
            title=row["title"],
            status=str(row["status"]),
            metadata=_loads(row["metadata"]) or {},
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def list_sessions(self) -> list[SessionRecord]:
        rows = self.store.query(
            """
            SELECT session_id, context_id, title, status, metadata, created_at, updated_at
            FROM sessions
            ORDER BY created_at DESC
            """
        )
        return [
            SessionRecord(
                session_id=str(row["session_id"]),
                context_id=row["context_id"],
                title=row["title"],
                status=str(row["status"]),
                metadata=_loads(row["metadata"]) or {},
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]

    def create_task(
        self,
        *,
        task_id: str,
        session_id: str,
        thread_id: str,
        user_input: str,
        model: dict[str, Any] | None,
        max_loops: int | None,
        mcp: dict[str, Any] | None = None,
        attempt: int = 1,
        root_task_id: str | None = None,
        retry_of_task_id: str | None = None,
        status: TaskStatus = TaskStatus.RUNNING,
    ) -> TaskRecord:
        if self.get_session(session_id) is None:
            raise ValueError(f"unknown session: {session_id}")
        active_root_task_id = root_task_id or task_id
        now = utc_now()
        self.store.execute(
            """
            INSERT INTO tasks(
                task_id, session_id, thread_id, root_task_id, retry_of_task_id, input, status, attempt, final_answer, interrupt,
                interrupt_message, stop_message, error_code, error_message, model, max_loops, mcp,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                session_id,
                thread_id,
                active_root_task_id,
                retry_of_task_id,
                user_input,
                status.value,
                attempt,
                None,
                None,
                None,
                None,
                None,
                None,
                _dumps(model),
                max_loops,
                _dumps(mcp),
                now,
                now,
            ),
        )
        record = self.get_task(task_id)
        if record is None:
            raise RuntimeError(f"failed to create task: {task_id}")
        return record

    def mark_task_queued(self, task_id: str) -> TaskRecord:
        return self._update_task_lifecycle(task_id=task_id, status=TaskStatus.QUEUED)

    def mark_task_running(self, task_id: str) -> TaskRecord:
        return self._update_task_lifecycle(task_id=task_id, status=TaskStatus.RUNNING)

    def mark_task_cancel_requested(self, task_id: str, *, stop_message: str | None = None) -> TaskRecord:
        return self._update_task_lifecycle(
            task_id=task_id,
            status=TaskStatus.CANCEL_REQUESTED,
            stop_message=stop_message,
        )

    def mark_task_canceled(self, task_id: str, *, stop_message: str | None = None) -> TaskRecord:
        return self._update_task_lifecycle(
            task_id=task_id,
            status=TaskStatus.CANCELED,
            stop_message=stop_message,
        )

    def save_task_result(
        self,
        *,
        task_id: str,
        result: RunResult,
        model: dict[str, Any] | None,
        max_loops: int | None,
        mcp: dict[str, Any] | None = None,
    ) -> TaskRecord:
        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError(f"unknown task: {task_id}")
        payload = result.to_dict()
        now = utc_now()
        self.store.execute(
            """
            UPDATE tasks SET
                thread_id=?,
                status=?,
                final_answer=?,
                interrupt=?,
                interrupt_message=?,
                stop_message=?,
                error_code=?,
                error_message=?,
                model=?,
                max_loops=?,
                mcp=?,
                updated_at=?
            WHERE task_id=?
            """,
            (
                result.thread_id,
                status_from_run_result(result).value,
                result.final_answer,
                _dumps(payload.get("interrupt")),
                result.interrupt_message,
                result.stop_message,
                None,
                None,
                _dumps(model),
                max_loops,
                _dumps(mcp),
                now,
                task_id,
            ),
        )
        record = self.get_task(task_id)
        if record is None:
            raise RuntimeError(f"failed to save task: {task_id}")
        return record

    def mark_task_failed(
        self,
        *,
        task_id: str,
        error_code: str,
        error_message: str,
    ) -> TaskRecord:
        return self._update_task_lifecycle(
            task_id=task_id,
            status=TaskStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
        )

    def _update_task_lifecycle(
        self,
        *,
        task_id: str,
        status: TaskStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        stop_message: str | None = None,
    ) -> TaskRecord:
        now = utc_now()
        self.store.execute(
            """
            UPDATE tasks SET
                status=?,
                final_answer=?,
                interrupt=?,
                interrupt_message=?,
                stop_message=?,
                error_code=?,
                error_message=?,
                updated_at=?
            WHERE task_id=?
            """,
            (
                status.value,
                None,
                None,
                None,
                stop_message,
                error_code,
                error_message,
                now,
                task_id,
            ),
        )
        record = self.get_task(task_id)
        if record is None:
            raise RuntimeError(f"failed to update task: {task_id}")
        return record

    def get_task(self, task_id: str) -> TaskRecord | None:
        rows = self.store.query(
            """
            SELECT task_id, session_id, thread_id, root_task_id, retry_of_task_id, input, status, attempt, final_answer, interrupt,
                   interrupt_message, stop_message, error_code, error_message, model, max_loops, mcp,
                   created_at, updated_at
            FROM tasks
            WHERE task_id=?
            """,
            (task_id,),
        )
        if not rows:
            return None
        return _task_record_from_row(rows[0])

    def get_task_by_thread_id(self, thread_id: str) -> TaskRecord | None:
        rows = self.store.query(
            """
            SELECT task_id, session_id, thread_id, root_task_id, retry_of_task_id, input, status, attempt, final_answer, interrupt,
                   interrupt_message, stop_message, error_code, error_message, model, max_loops, mcp,
                   created_at, updated_at
            FROM tasks
            WHERE thread_id=?
            """,
            (thread_id,),
        )
        if not rows:
            return None
        return _task_record_from_row(rows[0])

    def list_task_retries(self, root_task_id: str) -> list[TaskRecord]:
        rows = self.store.query(
            """
            SELECT task_id, session_id, thread_id, root_task_id, retry_of_task_id, input, status, attempt, final_answer, interrupt,
                   interrupt_message, stop_message, error_code, error_message, model, max_loops, mcp,
                   created_at, updated_at
            FROM tasks
            WHERE root_task_id=?
            ORDER BY attempt ASC, created_at ASC
            """,
            (root_task_id,),
        )
        return [_task_record_from_row(row) for row in rows]

    def append_task_event(
        self,
        *,
        task_id: str,
        event_type: str,
        status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> TaskEventRecord:
        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError(f"unknown task: {task_id}")
        session = self.get_session(task.session_id)
        now = utc_now()
        cursor = self.store.execute(
            """
            INSERT INTO task_events(task_id, session_id, context_id, thread_id, event_type, status, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.task_id,
                task.session_id,
                session.context_id if session is not None else None,
                task.thread_id,
                event_type,
                status,
                _dumps(payload or {}) or "{}",
                now,
            ),
        )
        event = self.get_task_event(int(cursor.lastrowid))
        if event is None:
            raise RuntimeError(f"failed to append task event: {task_id}")
        return event

    def get_task_event(self, event_id: int) -> TaskEventRecord | None:
        rows = self.store.query(
            """
            SELECT id, task_id, session_id, context_id, thread_id, event_type, status, payload, created_at
            FROM task_events
            WHERE id=?
            """,
            (event_id,),
        )
        if not rows:
            return None
        return _task_event_from_row(rows[0])

    def list_task_events(self, task_id: str) -> list[TaskEventRecord]:
        rows = self.store.query(
            """
            SELECT id, task_id, session_id, context_id, thread_id, event_type, status, payload, created_at
            FROM task_events
            WHERE task_id=?
            ORDER BY id ASC
            """,
            (task_id,),
        )
        return [_task_event_from_row(row) for row in rows]

    def get_task_artifact_by_a2a_id(
        self,
        *,
        task_id: str,
        a2a_artifact_id: str,
    ) -> TaskArtifactRecord | None:
        rows = self.store.query(
            """
            SELECT artifact_id, task_id, session_id, context_id, a2a_artifact_id, name, description,
                   parts, metadata, extensions, created_at, updated_at
            FROM task_artifacts
            WHERE task_id=? AND a2a_artifact_id=?
            """,
            (task_id, a2a_artifact_id),
        )
        if not rows:
            return None
        return _task_artifact_from_row(rows[0])

    def list_task_artifacts(self, task_id: str) -> list[TaskArtifactRecord]:
        rows = self.store.query(
            """
            SELECT artifact_id, task_id, session_id, context_id, a2a_artifact_id, name, description,
                   parts, metadata, extensions, created_at, updated_at
            FROM task_artifacts
            WHERE task_id=?
            ORDER BY created_at ASC, artifact_id ASC
            """,
            (task_id,),
        )
        return [_task_artifact_from_row(row) for row in rows]

    def upsert_task_artifact(
        self,
        *,
        artifact_id: str,
        task_id: str,
        a2a_artifact_id: str,
        name: str | None,
        description: str | None,
        parts: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
        extensions: list[str] | None = None,
    ) -> TaskArtifactRecord:
        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError(f"unknown task: {task_id}")
        session = self.get_session(task.session_id)
        now = utc_now()
        self.store.execute(
            """
            INSERT INTO task_artifacts(
                artifact_id, task_id, session_id, context_id, a2a_artifact_id, name, description,
                parts, metadata, extensions, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id, a2a_artifact_id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                parts=excluded.parts,
                metadata=excluded.metadata,
                extensions=excluded.extensions,
                updated_at=excluded.updated_at
            """,
            (
                artifact_id,
                task.task_id,
                task.session_id,
                session.context_id if session is not None else None,
                a2a_artifact_id,
                name,
                description,
                _dumps(parts) or "[]",
                _dumps(metadata or {}) or "{}",
                _dumps(extensions or []) or "[]",
                now,
                now,
            ),
        )
        record = self.get_task_artifact_by_a2a_id(task_id=task_id, a2a_artifact_id=a2a_artifact_id)
        if record is None:
            raise RuntimeError(f"failed to upsert task artifact: {task_id}/{a2a_artifact_id}")
        return record


def _task_record_from_row(row: Any) -> TaskRecord:
    return TaskRecord(
        task_id=str(row["task_id"]),
        session_id=str(row["session_id"]),
        thread_id=str(row["thread_id"]),
        root_task_id=row["root_task_id"],
        retry_of_task_id=row["retry_of_task_id"],
        input=str(row["input"]),
        status=normalize_task_status(row["status"]),
        attempt=int(row["attempt"]),
        final_answer=row["final_answer"],
        interrupt=_loads(row["interrupt"]),
        interrupt_message=row["interrupt_message"],
        stop_message=row["stop_message"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        model=_loads(row["model"]),
        max_loops=row["max_loops"],
        mcp=_loads(row["mcp"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _task_event_from_row(row: Any) -> TaskEventRecord:
    return TaskEventRecord(
        event_id=int(row["id"]),
        task_id=str(row["task_id"]),
        session_id=str(row["session_id"]),
        context_id=row["context_id"],
        thread_id=row["thread_id"],
        event_type=str(row["event_type"]),
        status=row["status"],
        payload=_loads(row["payload"]) or {},
        created_at=str(row["created_at"]),
    )


def _task_artifact_from_row(row: Any) -> TaskArtifactRecord:
    return TaskArtifactRecord(
        artifact_id=str(row["artifact_id"]),
        task_id=str(row["task_id"]),
        session_id=str(row["session_id"]),
        context_id=row["context_id"],
        a2a_artifact_id=str(row["a2a_artifact_id"]),
        name=row["name"],
        description=row["description"],
        parts=_loads(row["parts"]) or [],
        metadata=_loads(row["metadata"]) or {},
        extensions=_loads(row["extensions"]) or [],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _error_payload(error_code: str | None, error_message: str | None) -> dict[str, str] | None:
    if error_code is None and error_message is None:
        return None
    return {
        "code": error_code or "runtime_error",
        "message": error_message or "runtime error",
    }
