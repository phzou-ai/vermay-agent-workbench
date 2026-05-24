from __future__ import annotations

import json
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


class ProgressReporter:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.console = Console(file=sys.stderr, force_terminal=True, color_system="auto")

    def event(self, step: int | None, event: str, **fields: Any) -> None:
        if not self.enabled:
            return

        if event == "run_started":
            self._run_started(fields)
        elif event == "context_built":
            self._context_built(step, fields)
        elif event == "model_call_start":
            self._simple(step, "Model Call", "Sending current context and tool schemas to the model.", "cyan")
        elif event == "model_response":
            self._model_response(step, fields)
        elif event == "tool_call":
            self._json_panel(step, "Tool Call", fields["payload"], "yellow")
        elif event == "permission":
            self._permission(step, fields)
        elif event == "tool_execute_start":
            self._simple(step, "Tool Execute", f"Executing {fields['tool']}", "yellow")
        elif event == "tool_result":
            self._tool_result(step, fields)
        elif event == "observation":
            self._observation(step, fields)
        elif event == "final_answer":
            self._simple(step, "Final Answer", "Model returned a final answer. Agent loop stops.", "green")
        elif event == "approval_required":
            self._simple(step, "Approval Required", f"Tool requires approval: {fields['tool']}", "red")
        elif event == "max_steps_reached":
            self._simple(None, "Max Steps Reached", f"Stopped after {fields['max_steps']} model calls.", "red")
        elif event.endswith("_start"):
            return
        else:
            self._simple(step, event, self._preview(str(fields)), "white")

    def _run_started(self, fields: dict[str, Any]) -> None:
        content = Text()
        content.append("input: ", style="bold")
        content.append(str(fields["input"]))
        content.append("\nmax_steps: ", style="bold")
        content.append(str(fields["max_steps"]))
        self.console.print(Panel(content, title="Agent Run", border_style="bold blue"))

    def _context_built(self, step: int | None, fields: dict[str, Any]) -> None:
        roles = []
        for message in fields["message_preview"]:
            label = message["role"]
            if message.get("name"):
                label += f":{message['name']}"
            roles.append(label)
        content = (
            f"messages: {fields['messages']}\n"
            f"observations: {fields['observations']}\n"
            f"roles: {' -> '.join(roles)}"
        )
        self.console.print(Panel(content, title=self._title(step, "Context Build"), border_style="magenta"))

    def _model_response(self, step: int | None, fields: dict[str, Any]) -> None:
        title = self._title(step, "Model Response")
        content = self._preview(fields["content"], 700)
        if fields.get("tool"):
            content += f"\n\nnext: tool_call -> {fields['tool']}"
        else:
            content += "\n\nnext: final_answer"
        self.console.print(Panel(content, title=title, border_style="cyan"))

    def _permission(self, step: int | None, fields: dict[str, Any]) -> None:
        status = "allowed" if fields["allowed"] else "blocked"
        style = "green" if fields["allowed"] else "red"
        content = (
            f"status: {status}\n"
            f"requires_approval: {fields['approval']}\n"
            f"reason: {fields['reason']}"
        )
        self.console.print(Panel(content, title=self._title(step, "Permission Gate"), border_style=style))

    def _tool_result(self, step: int | None, fields: dict[str, Any]) -> None:
        lines = [
            f"tool: {fields['tool']}",
            f"ok: {fields['ok']}",
        ]
        if fields.get("exit_code") is not None:
            lines.append(f"exit_code: {fields['exit_code']}")
        if fields.get("command_summary"):
            lines.append(f"command: {fields['command_summary']}")
        self.console.print(Panel("\n".join(lines), title=self._title(step, "Tool Result"), border_style="yellow"))

    def _observation(self, step: int | None, fields: dict[str, Any]) -> None:
        content = (
            f"tool: {fields['tool']}\n"
            f"ok: {fields['ok']}\n\n"
            f"{fields['summary']}"
        )
        self.console.print(Panel(content, title=self._title(step, "Observation"), border_style="blue"))

    def _json_panel(self, step: int | None, title: str, payload: Any, color: str) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        syntax = Syntax(text, "json", theme="ansi_dark", word_wrap=True)
        self.console.print(Panel(syntax, title=self._title(step, title), border_style=color))

    def _simple(self, step: int | None, title: str, message: str, color: str) -> None:
        self.console.print(Panel(message, title=self._title(step, title), border_style=color))

    def _title(self, step: int | None, label: str) -> str:
        if step is None:
            return label
        return f"Step {step} · {label}"

    def _preview(self, value: str, limit: int = 500, single_line: bool = False) -> str:
        text = value.replace("\n", "\\n") if single_line else value
        if len(text) > limit:
            return text[:limit] + "...<truncated>"
        return text
