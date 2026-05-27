from __future__ import annotations

import json
import sys
from typing import Any


class ProgressReporter:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._last_step: int | None = None

    def event(self, step: int | None, event: str, **fields: Any) -> None:
        if not self.enabled:
            return
        if event.endswith("_start") and event != "model_call_start" and event != "tool_execute_start":
            return

        line = self._format_event(step, event, fields)
        if line:
            print(line, file=sys.stderr, flush=True)

    def _format_event(self, step: int | None, event: str, fields: dict[str, Any]) -> str | None:
        if event == "run_started":
            self._last_step = None
            return f"> {self._input_summary(str(fields['input']))}  max_steps={fields['max_steps']}"
        if event == "context_built":
            self._step_header(step)
            roles = []
            for message in fields["message_preview"]:
                role = message["role"]
                if message.get("name"):
                    role += f":{message['name']}"
                roles.append(role)
            return (
                f"  {'context':<11} messages={fields['messages']} "
                f"observations={fields['observations']} roles={' -> '.join(roles)}"
            )
        if event == "model_call_start":
            self._step_header(step)
            return f"  {'model':<11} call"
        if event == "model_response":
            self._step_header(step)
            if fields.get("tool"):
                return f"  {'model':<11} tool_request name={fields['tool']}"
            return f"  {'model':<11} final {self._content_summary(fields['content'])}"
        if event == "tool_call":
            self._step_header(step)
            payload = fields["payload"]
            name = payload.get("name") if isinstance(payload, dict) else None
            args = payload.get("arguments") if isinstance(payload, dict) else payload
            return f"  {'tool_call':<11} name={name} args={self._args_summary(args)}"
        if event == "permission":
            self._step_header(step)
            status = "allowed" if fields["allowed"] else "blocked"
            return (
                f"  {'permission':<11} {status} "
                f"approval={fields['approval']} reason={fields['reason']}"
            )
        if event == "tool_execute_start":
            self._step_header(step)
            return f"  {'execute':<11} tool={fields['tool']}"
        if event == "tool_result":
            self._step_header(step)
            parts = [f"  {'result':<11} tool={fields['tool']} ok={fields['ok']}"]
            if fields.get("exit_code") is not None:
                parts.append(f"exit_code={fields['exit_code']}")
            if fields.get("command_summary"):
                parts.append(f"cmd={self._preview(str(fields['command_summary']), 140, True)}")
            return " ".join(parts)
        if event == "observation":
            self._step_header(step)
            return (
                f"  {'observation':<11} tool={fields['tool']} ok={fields['ok']} "
                f"{self._summary_preview(fields['summary'])}"
            )
        if event == "final_answer":
            self._step_header(step)
            return f"  {'done':<11} final_answer"
        if event == "approval_required":
            self._step_header(step)
            return f"  {'approval':<11} required tool={fields['tool']}"
        if event == "approval_resumed":
            self._step_header(step)
            return f"  {'approval':<11} resumed tool={fields['tool']}"
        if event == "max_steps_reached":
            return f"stopped max_steps={fields['max_steps']}"
        if not event.endswith("_start"):
            self._step_header(step)
            return f"  {event:<11} {self._preview(str(fields), 180, True)}"
        return None

    def _step_header(self, step: int | None) -> None:
        if step is None or self._last_step == step:
            return
        if self._last_step is not None:
            print("", file=sys.stderr, flush=True)
        print(f"step {step}", file=sys.stderr, flush=True)
        self._last_step = step

    def _preview(self, value: str, limit: int = 500, single_line: bool = False) -> str:
        text = value.replace("\n", "\\n") if single_line else value
        if len(text) > limit:
            return text[:limit] + "...<truncated>"
        return text

    def _input_summary(self, value: str) -> str:
        lines = value.splitlines()
        first_line = lines[0] if lines else value
        if "\n" in value:
            return f"{self._preview(first_line, 90, single_line=True)} <{len(value)} chars, {len(lines)} lines>"
        if len(value) > 120:
            return f"{self._preview(value, 90, single_line=True)} <{len(value)} chars>"
        return value

    def _args_summary(self, value: Any) -> str:
        if isinstance(value, dict):
            parts = []
            for key, item in value.items():
                parts.append(f"{key}={self._value_summary(item)}")
            return "{" + ", ".join(parts) + "}"
        return self._value_summary(value)

    def _value_summary(self, value: Any) -> str:
        if isinstance(value, str):
            line_count = value.count("\n") + 1
            if "\n" in value:
                return f"<{len(value)} chars, {line_count} lines>"
            if len(value) > 80:
                return f"<{len(value)} chars>"
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, (int, float, bool)) or value is None:
            return json.dumps(value, ensure_ascii=False)
        try:
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            rendered = str(value)
        if len(rendered) > 120:
            return f"<{type(value).__name__}, {len(rendered)} chars>"
        return rendered

    def _content_summary(self, value: Any) -> str:
        text = str(value)
        if "\n" in text:
            lines = text.splitlines()
            first_line = lines[0] if lines else ""
            return f"{self._preview(first_line, 120, single_line=True)} <{len(text)} chars, {len(lines)} lines>"
        return self._preview(text, 180, single_line=True)

    def _summary_preview(self, value: Any) -> str:
        text = str(value)
        if "\n" in text:
            lines = text.splitlines()
            first_line = lines[0] if lines else ""
            return f"{self._preview(first_line, 120, single_line=True)} <{len(text)} chars, {len(lines)} lines>"
        return self._preview(text, 180, single_line=True)
