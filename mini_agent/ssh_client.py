from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SshClient:
    def __init__(self, config_path: Path | None = None, timeout_seconds: int = 20) -> None:
        self.config_path = config_path or ROOT / "data" / "ssh_config.json"
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
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _base_command(self) -> list[str]:
        config = self.config
        command = [
            "ssh",
            "-p",
            str(config["port"]),
            "-i",
            str(Path(config["identityFile"]).expanduser()),
            "-o",
            f"StrictHostKeyChecking={'yes' if config['strictHostKeyChecking'] else 'no'}",
            "-o",
            f"UpdateHostKeys={'yes' if config['updateHostKeys'] else 'no'}",
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

