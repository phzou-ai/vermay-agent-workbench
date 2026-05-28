from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunResult:
    thread_id: str
    final_answer: str | None = None
    interrupt: Any | None = None
    interrupt_message: str | None = None
    state: dict[str, Any] = field(default_factory=dict)
    stop_message: str | None = None

    def to_output(self) -> str:
        if self.interrupt_message is not None:
            return self.interrupt_message
        if self.final_answer is not None:
            return self.final_answer
        if self.stop_message is not None:
            return self.stop_message
        return f"Run finished for thread {self.thread_id}, but no final answer was produced."
