from pathlib import Path

from mini_agent.env_config import load_prefixed_env, parse_env_file


def test_parse_env_file_filters_prefix_and_strips_quotes(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text(
        "\n".join(
            [
                "# comment",
                "MINI_AGENT_OLLAMA_MODEL='demo-model'",
                'MINI_AGENT_OLLAMA_BASE_URL="http://localhost:11434"',
                "OTHER_VALUE=ignored",
            ]
        ),
        encoding="utf-8",
    )

    assert parse_env_file(path, prefix="MINI_AGENT_OLLAMA_") == {
        "MINI_AGENT_OLLAMA_MODEL": "demo-model",
        "MINI_AGENT_OLLAMA_BASE_URL": "http://localhost:11434",
    }


def test_load_prefixed_env_uses_local_file_over_default(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MINI_AGENT_OLLAMA_MODEL", raising=False)
    (tmp_path / ".env").write_text("MINI_AGENT_OLLAMA_MODEL=default-model\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("MINI_AGENT_OLLAMA_MODEL=local-model\n", encoding="utf-8")

    assert load_prefixed_env("MINI_AGENT_OLLAMA_", root=tmp_path)["MINI_AGENT_OLLAMA_MODEL"] == "local-model"


def test_load_prefixed_env_uses_shell_env_over_files(tmp_path: Path, monkeypatch):
    (tmp_path / ".env.local").write_text("MINI_AGENT_OLLAMA_MODEL=local-model\n", encoding="utf-8")
    monkeypatch.setenv("MINI_AGENT_OLLAMA_MODEL", "shell-model")

    assert load_prefixed_env("MINI_AGENT_OLLAMA_", root=tmp_path)["MINI_AGENT_OLLAMA_MODEL"] == "shell-model"
