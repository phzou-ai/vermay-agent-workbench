from mini_agent import env_config
from mini_agent.model_clients.ollama import OllamaModelClient
from urllib.error import HTTPError
from io import BytesIO


def test_ollama_client_loads_env_file_config(tmp_path, monkeypatch):
    monkeypatch.setattr(env_config, "ROOT", tmp_path)
    monkeypatch.delenv("MINI_AGENT_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("MINI_AGENT_OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("MINI_AGENT_OLLAMA_TIMEOUT_SECONDS", raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MINI_AGENT_OLLAMA_MODEL=test-model",
                "MINI_AGENT_OLLAMA_BASE_URL=http://ollama.example",
                "MINI_AGENT_OLLAMA_TIMEOUT_SECONDS=7",
            ]
        ),
        encoding="utf-8",
    )

    client = OllamaModelClient()

    assert client.model == "test-model"
    assert client.base_url == "http://ollama.example"
    assert client.timeout_seconds == 7


def test_ollama_client_explicit_args_override_env_config(tmp_path, monkeypatch):
    monkeypatch.setattr(env_config, "ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MINI_AGENT_OLLAMA_MODEL=test-model",
                "MINI_AGENT_OLLAMA_BASE_URL=http://ollama.example",
                "MINI_AGENT_OLLAMA_TIMEOUT_SECONDS=7",
            ]
        ),
        encoding="utf-8",
    )

    client = OllamaModelClient(
        model="override-model",
        base_url="http://override.example/",
        timeout_seconds=9,
    )

    assert client.model == "override-model"
    assert client.base_url == "http://override.example"
    assert client.timeout_seconds == 9


def test_ollama_client_formats_http_error_body():
    error = HTTPError(
        url="http://127.0.0.1:11434/api/chat",
        code=503,
        msg="Service Unavailable",
        hdrs={},
        fp=BytesIO(b'{"error":"model overloaded"}'),
    )

    message = OllamaModelClient()._format_http_error(error)

    assert message == "Ollama request failed: HTTP 503 Service Unavailable: model overloaded"
