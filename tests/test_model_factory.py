from __future__ import annotations

import pytest

from langchain_core.messages import AIMessage, HumanMessage

from mini_agent.langgraph_runtime import (
    ModelInvocation,
    ModelProviderConfig,
    OllamaModelAdapter,
    OpenAICompatibleModelAdapter,
    RuleRouterModelAdapter,
    build_model_client,
)


class FakeAdapter:
    def __init__(self, name: str) -> None:
        self.name = name

    def invoke(self, messages, tools):
        return ModelInvocation(message=AIMessage(content=self.name))


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


def test_model_factory_builds_openai_compatible_adapter():
    model = build_model_client(
        ModelProviderConfig(
            provider="openai_compatible",
            options={
                "model": "qwen",
                "base_url": "http://localhost:8000/v1",
                "timeout_seconds": "12",
            },
        )
    )

    assert isinstance(model, OpenAICompatibleModelAdapter)
    assert model.client.model == "qwen"
    assert model.client.base_url == "http://localhost:8000/v1"
    assert model.client.timeout_seconds == 12


def test_model_factory_rejects_missing_openai_compatible_options():
    with pytest.raises(ValueError, match="openai_compatible option 'model' is required"):
        build_model_client(
            ModelProviderConfig(
                provider="openai_compatible",
                options={"base_url": "http://localhost:8000/v1"},
            )
        )


def test_rule_router_selects_keyword_profile():
    router = RuleRouterModelAdapter(
        profiles={"default": FakeAdapter("default"), "large": FakeAdapter("large")},
        rules=[{"profile": "large", "contains": ["large model"]}],
        default_profile="default",
    )

    result = router.invoke([HumanMessage(content="use large model")], tools=[])

    assert result.message.content == "large"


def test_rule_router_uses_fallback_when_no_rule_matches():
    router = RuleRouterModelAdapter(
        profiles={"default": FakeAdapter("default"), "large": FakeAdapter("large")},
        rules=[{"profile": "large", "contains": ["large model"]}],
        default_profile="default",
    )

    result = router.invoke([HumanMessage(content="hello")], tools=[])

    assert result.message.content == "default"


def test_model_factory_builds_router_from_route_config(tmp_path):
    route_config = tmp_path / "model_profiles.json"
    route_config.write_text(
        """
{
  "default_profile": "default",
  "profiles": {
    "default": {
      "provider": "ollama",
      "options": {"model": "test-model"}
    }
  },
  "rules": []
}
""",
        encoding="utf-8",
    )

    model = build_model_client(
        ModelProviderConfig(provider="router", options={"route_config": str(route_config)})
    )

    assert isinstance(model, RuleRouterModelAdapter)
