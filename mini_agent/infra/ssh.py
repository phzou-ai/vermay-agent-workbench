from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

ENV_FILES = (".env", ".env.local", ".env.dev.local")


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

        values = self._load_env_values()
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

    def _load_env_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for name in ENV_FILES:
            path = ROOT / name
            if path.exists():
                values.update(self._parse_env_file(path))

        for key in (
            "MINI_AGENT_SSH_TARGET",
            "MINI_AGENT_SSH_PORT",
            "MINI_AGENT_SSH_IDENTITY_FILE",
            "MINI_AGENT_SSH_KNOWN_HOSTS_FILE",
        ):
            if key in os.environ:
                values[key] = os.environ[key]
        return values

    def _parse_env_file(self, path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = self._strip_env_value(value.strip())
        return values

    def _strip_env_value(self, value: str) -> str:
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value

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
