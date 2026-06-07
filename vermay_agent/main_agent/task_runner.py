from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Protocol

from vermay_agent.app_factory import RuntimeFactoryConfig, build_runtime
from vermay_agent.langgraph_runtime import LangGraphAgentRuntime

from .models import MessageRecord, TaskStatus


@dataclass(frozen=True)
class LocalTaskRunResult:
    status: TaskStatus
    parts: list[dict] = field(default_factory=list)
    artifact_parts: list[dict] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class LocalTaskRunner(Protocol):
    def run(self, messages: list[MessageRecord], *, thread_id: str) -> LocalTaskRunResult:
        """Run a local task with bounded context history."""


class DirectLangGraphLocalTaskRunner:
    def __init__(self, runtime: LangGraphAgentRuntime | None = None) -> None:
        self.runtime = runtime or build_runtime(RuntimeFactoryConfig(show_progress=False))
        self._lock = threading.RLock()

    def run(self, messages: list[MessageRecord], *, thread_id: str) -> LocalTaskRunResult:
        user_input = _task_input_from_messages(messages)
        with self._lock:
            result = self.runtime.start(user_input, thread_id=thread_id)
        if result.status == "completed":
            parts = [{"kind": "text", "text": result.final_answer or ""}]
            return LocalTaskRunResult(status=TaskStatus.COMPLETED, parts=parts)
        if result.status == "interrupted":
            parts = [{"kind": "text", "text": result.interrupt_message or "Approval required."}]
            return LocalTaskRunResult(
                status=TaskStatus.INPUT_REQUIRED,
                parts=parts,
                error_code="input_required",
                error_message=result.interrupt_message,
            )
        return LocalTaskRunResult(
            status=TaskStatus.FAILED,
            error_code=result.status,
            error_message=result.stop_message or "Local task did not complete.",
        )

    def close(self) -> None:
        self.runtime.close()


def _task_input_from_messages(messages: list[MessageRecord]) -> str:
    latest_user = next((message for message in reversed(messages) if message.role.value == "user"), None)
    if latest_user is None:
        return ""
    previous = [message for message in messages if message.message_id != latest_user.message_id]
    current_input = _text_from_parts(latest_user.parts)
    if not previous:
        return current_input
    history = "\n".join(
        f"{message.role.value}: {_text_from_parts(message.parts)}"
        for message in previous
        if _text_from_parts(message.parts)
    )
    if not history:
        return current_input
    return f"Conversation history:\n{history}\n\nCurrent task:\n{current_input}"


def _text_from_parts(parts: list[dict]) -> str:
    return "\n".join(str(part.get("text")) for part in parts if part.get("text") is not None)
