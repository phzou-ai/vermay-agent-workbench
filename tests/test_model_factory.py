from __future__ import annotations

import pytest

from mini_agent.langgraph_runtime import ModelProviderConfig, OllamaModelAdapter, build_model_client


def test_model_factory_builds_ollama_adapter_with_options():
    model = build_model_client(
        ModelProviderConfig(
            provider="ollama",
            options={
                "model": "test-model",
                "base_url": "http://ollama.example/",
                "timeout_seconds": "7",
            },
        )
    )

    assert isinstance(model, OllamaModelAdapter)
    assert model.client.model == "test-model"
    assert model.client.base_url == "http://ollama.example"
    assert model.client.timeout_seconds == 7


def test_model_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="unsupported model provider: missing"):
        build_model_client(ModelProviderConfig(provider="missing"))


def test_model_factory_rejects_unknown_ollama_option():
    with pytest.raises(ValueError, match="unsupported ollama model option\\(s\\): typo"):
        build_model_client(ModelProviderConfig(provider="ollama", options={"typo": "value"}))


def test_model_factory_rejects_invalid_ollama_timeout():
    with pytest.raises(ValueError, match="ollama option 'timeout_seconds' must be a positive integer"):
        build_model_client(ModelProviderConfig(provider="ollama", options={"timeout_seconds": "slow"}))


@pytest.mark.parametrize("value", [True, 1.5, "12.5", "", "0", 0, -1])
def test_model_factory_rejects_non_positive_integer_ollama_timeout(value):
    with pytest.raises(ValueError, match="ollama option 'timeout_seconds' must be .*integer"):
        build_model_client(ModelProviderConfig(provider="ollama", options={"timeout_seconds": value}))


def test_model_factory_rejects_non_string_ollama_model():
    with pytest.raises(ValueError, match="ollama option 'model' must be a string"):
        build_model_client(ModelProviderConfig(provider="ollama", options={"model": 123}))
