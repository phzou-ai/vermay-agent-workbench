from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from mini_agent.langgraph_runtime.results import RunResult
from mini_agent.storage import AgentStore, utc_now


@dataclass(frozen=True)
class SessionRecord:
    thread_id: str
    input: str
    status: str
    final_answer: str | None
    interrupt: Any | None
    interrupt_message: str | None
    stop_message: str | None
    model: dict[str, Any] | None
    max_loops: int | None
    mcp: dict[str, Any] | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "status": self.status,
            "input": self.input,
            "final_answer": self.final_answer,
            "interrupt": self.interrupt,
            "interrupt_message": self.interrupt_message,
            "stop_message": self.stop_message,
            "mcp": self.mcp,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SessionStore:
    def __init__(self, store: AgentStore) -> None:
        self.store = store

    def save_result(
        self,
        *,
        user_input: str,
        result: RunResult,
        model: dict[str, Any] | None,
        max_loops: int | None,
        mcp: dict[str, Any] | None = None,
    ) -> SessionRecord:
        payload = result.to_dict()
        existing = self.get(result.thread_id)
        now = utc_now()
        created_at = existing.created_at if existing is not None else now
        self.store.execute(
            """
            INSERT INTO sessions(
                thread_id, input, status, final_answer, interrupt, interrupt_message, stop_message,
                model, max_loops, mcp, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                input=excluded.input,
                status=excluded.status,
                final_answer=excluded.final_answer,
                interrupt=excluded.interrupt,
                interrupt_message=excluded.interrupt_message,
                stop_message=excluded.stop_message,
                model=excluded.model,
                max_loops=excluded.max_loops,
                mcp=excluded.mcp,
                updated_at=excluded.updated_at
            """,
            (
                result.thread_id,
                user_input,
                result.status,
                result.final_answer,
                _dumps(payload.get("interrupt")),
                result.interrupt_message,
                result.stop_message,
                _dumps(model),
                max_loops,
                _dumps(mcp),
                created_at,
                now,
            ),
        )
        record = self.get(result.thread_id)
        if record is None:
            raise RuntimeError(f"failed to save session: {result.thread_id}")
        return record

    def get(self, thread_id: str) -> SessionRecord | None:
        rows = self.store.query(
            """
            SELECT thread_id, input, status, final_answer, interrupt, interrupt_message, stop_message,
                   model, max_loops, mcp, created_at, updated_at
            FROM sessions
            WHERE thread_id=?
            """,
            (thread_id,),
        )
        if not rows:
            return None
        row = rows[0]
        return SessionRecord(
            thread_id=str(row["thread_id"]),
            input=str(row["input"]),
            status=str(row["status"]),
            final_answer=row["final_answer"],
            interrupt=_loads(row["interrupt"]),
            interrupt_message=row["interrupt_message"],
            stop_message=row["stop_message"],
            model=_loads(row["model"]),
            max_loops=row["max_loops"],
            mcp=_loads(row["mcp"]),
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
