from pathlib import Path

import pytest

from mini_agent.infra import ssh as ssh_module
from mini_agent.infra.ssh import SshClient


def test_ssh_client_loads_env_local_config(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ssh_module, "ROOT", tmp_path)
    monkeypatch.delenv("MINI_AGENT_SSH_TARGET", raising=False)
    monkeypatch.delenv("MINI_AGENT_SSH_PORT", raising=False)
    monkeypatch.delenv("MINI_AGENT_SSH_IDENTITY_FILE", raising=False)
    monkeypatch.delenv("MINI_AGENT_SSH_KNOWN_HOSTS_FILE", raising=False)
    (tmp_path / ".env.local").write_text(
        "\n".join(
            [
                "MINI_AGENT_SSH_TARGET=user@example-host",
                "MINI_AGENT_SSH_PORT=2222",
                "MINI_AGENT_SSH_IDENTITY_FILE=~/.ssh/example",
                "MINI_AGENT_SSH_KNOWN_HOSTS_FILE=~/.ssh/known_hosts",
            ]
        ),
        encoding="utf-8",
    )

    client = SshClient()

    assert client.config == {
        "target": "user@example-host",
        "port": 2222,
        "identityFile": "~/.ssh/example",
        "knownHostsFile": "~/.ssh/known_hosts",
    }


def test_ssh_client_uses_fixed_safe_host_key_options(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ssh_module, "ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MINI_AGENT_SSH_TARGET=user@example-host",
                "MINI_AGENT_SSH_PORT=2222",
                "MINI_AGENT_SSH_IDENTITY_FILE=~/.ssh/example",
                "MINI_AGENT_SSH_KNOWN_HOSTS_FILE=~/.ssh/known_hosts",
            ]
        ),
        encoding="utf-8",
    )

    command = SshClient()._base_command()

    assert "StrictHostKeyChecking=yes" in command
    assert "UpdateHostKeys=yes" in command


def test_ssh_client_env_vars_override_env_files(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ssh_module, "ROOT", tmp_path)
    (tmp_path / ".env.local").write_text(
        "\n".join(
            [
                "MINI_AGENT_SSH_TARGET=file-host",
                "MINI_AGENT_SSH_PORT=22",
                "MINI_AGENT_SSH_IDENTITY_FILE=~/.ssh/file",
                "MINI_AGENT_SSH_KNOWN_HOSTS_FILE=~/.ssh/known_hosts",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_SSH_TARGET", "env-host")
    monkeypatch.setenv("MINI_AGENT_SSH_PORT", "2200")
    monkeypatch.setenv("MINI_AGENT_SSH_IDENTITY_FILE", "~/.ssh/env")
    monkeypatch.setenv("MINI_AGENT_SSH_KNOWN_HOSTS_FILE", "~/.ssh/env_known_hosts")

    client = SshClient()

    assert client.config["target"] == "env-host"
    assert client.config["port"] == 2200
    assert client.config["identityFile"] == "~/.ssh/env"
    assert client.config["knownHostsFile"] == "~/.ssh/env_known_hosts"


def test_ssh_client_reports_missing_env_config(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ssh_module, "ROOT", tmp_path)
    monkeypatch.delenv("MINI_AGENT_SSH_TARGET", raising=False)
    monkeypatch.delenv("MINI_AGENT_SSH_PORT", raising=False)
    monkeypatch.delenv("MINI_AGENT_SSH_IDENTITY_FILE", raising=False)
    monkeypatch.delenv("MINI_AGENT_SSH_KNOWN_HOSTS_FILE", raising=False)

    with pytest.raises(ValueError, match="Missing SSH environment config"):
        SshClient()
