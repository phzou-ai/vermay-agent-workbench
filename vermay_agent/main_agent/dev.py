from __future__ import annotations

from vermay_agent.app_factory import RuntimeFactoryConfig
from vermay_agent.langgraph_runtime.results import RunResult

from .models import MessageRecord, TaskStatus
from .task_runner import LocalTaskRunResult


class DevMockLocalMessageResponder:
    def respond(self, messages: list[MessageRecord]) -> list[dict]:
        text = _latest_user_text(messages) or "No user input provided."
        return [{"kind": "text", "text": f"Dev mock response: {text}"}]


class DevMockLocalTaskRunner:
    def run(self, messages: list[MessageRecord], *, thread_id: str) -> LocalTaskRunResult:
        text = _latest_user_text(messages) or "No task input provided."
        if "__dev_mock_hold_task__" in text:
            return LocalTaskRunResult(status=TaskStatus.RUNNING)
        return LocalTaskRunResult(
            status=TaskStatus.COMPLETED,
            parts=[{"kind": "text", "text": f"Dev mock task completed: {text}"}],
        )

    def close(self) -> None:
        return None


class DevMockRuntime:
    def start(self, user_input: str, thread_id: str | None = None) -> RunResult:
        return RunResult(
            thread_id=thread_id or "dev-mock-thread",
            final_answer=f"Dev mock task completed: {user_input}",
        )

    def resume(self, thread_id: str, approved: bool, reason: str | None = None) -> RunResult:
        status = "approved" if approved else "rejected"
        detail = f": {reason}" if reason else ""
        return RunResult(thread_id=thread_id, final_answer=f"Dev mock resume {status}{detail}")

    def close(self) -> None:
        return None


def build_dev_mock_runtime(_: RuntimeFactoryConfig) -> DevMockRuntime:
    return DevMockRuntime()


def _latest_user_text(messages: list[MessageRecord]) -> str:
    for message in reversed(messages):
        if message.role.value != "user":
            continue
        text = "\n".join(str(part.get("text", "")).strip() for part in message.parts if isinstance(part, dict))
        if text.strip():
            return text.strip()
    return ""
