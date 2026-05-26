from __future__ import annotations

import json
import subprocess
from pathlib import Path

from mini_agent.env_config import load_prefixed_env

ROOT = Path(__file__).resolve().parents[2]


class SshClient:
    def __init__(self, config_path: Path | None = None, timeout_seconds: int = 20) -> None:
        self.config_path = config_path
        self.timeout_seconds = timeout_seconds
        self.config = self._load_config()

    def run(self, remote_command: str) -> dict:
        command = self._base_command() + [remote_command]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "command": self._redact_command(command),
                "stdout": exc.stdout or "",
                "stderr": f"SSH command timed out after {self.timeout_seconds}s",
                "exit_code": None,
            }

        return {
            "ok": completed.returncode == 0,
            "command": self._redact_command(command),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "exit_code": completed.returncode,
        }

    def _load_config(self) -> dict:
        if self.config_path is not None:
            return json.loads(self.config_path.read_text(encoding="utf-8"))

        values = load_prefixed_env("MINI_AGENT_SSH_", root=ROOT)
        required = {
            "target": values.get("MINI_AGENT_SSH_TARGET"),
            "port": values.get("MINI_AGENT_SSH_PORT"),
            "identityFile": values.get("MINI_AGENT_SSH_IDENTITY_FILE"),
            "knownHostsFile": values.get("MINI_AGENT_SSH_KNOWN_HOSTS_FILE"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(
                "Missing SSH environment config: "
                + ", ".join(missing)
                + ". Define it in .env.local using .env as the template."
            )

        return {
            "target": required["target"],
            "port": int(str(required["port"])),
            "identityFile": required["identityFile"],
            "knownHostsFile": required["knownHostsFile"],
        }

    def _base_command(self) -> list[str]:
        config = self.config
        command = [
            "ssh",
            "-p",
            str(config["port"]),
            "-i",
            str(Path(config["identityFile"]).expanduser()),
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UpdateHostKeys=yes",
            "-o",
            f"UserKnownHostsFile={Path(config['knownHostsFile']).expanduser()}",
            config["target"],
        ]
        return command

    def _redact_command(self, command: list[str]) -> str:
        redacted = []
        skip_next = False
        for part in command:
            if skip_next:
                redacted.append("<identity-file>")
                skip_next = False
                continue
            redacted.append(part)
            if part == "-i":
                skip_next = True
        return " ".join(redacted)
