from mini_agent.model_clients.ollama import OllamaModelClient
from urllib.error import HTTPError
from io import BytesIO


def test_ollama_client_uses_builtin_fallback_config():
    client = OllamaModelClient()

    assert client.model == "deepseek-v4-flash:cloud"
    assert client.base_url == "http://127.0.0.1:11434"
    assert client.timeout_seconds == 120


def test_ollama_client_explicit_args_override_fallback_config():
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
