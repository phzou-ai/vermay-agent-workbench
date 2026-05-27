from __future__ import annotations

import re


def tool_command_summary(output: object) -> str | None:
    if isinstance(output, dict) and "command" in output:
        command = str(output["command"])
        matches = re.findall(
            r"(?:/snap/bin/microk8s\s+kubectl|microk8s\s+kubectl|kubectl)\s+(?:get|describe)\s+[^;]+",
            command,
        )
        if matches:
            return matches[0].strip()
        return command
    return None


def tool_exit_code(output: object) -> object:
    if isinstance(output, dict) and "exit_code" in output:
        return output["exit_code"]
    return None


def observation_summary(output: object, content: str) -> str:
    if isinstance(output, dict):
        stdout = str(output.get("stdout") or "")
        stderr = str(output.get("stderr") or "")
        if stdout:
            lines = stdout.splitlines()
            preview = "\n".join(lines[:8])
            if len(lines) > 8:
                preview += f"\n... ({len(lines) - 8} more lines in JSONL trace)"
            return f"stdout_lines: {len(lines)}\n{preview}"
        if stderr:
            return f"stderr:\n{stderr}"
    return content
