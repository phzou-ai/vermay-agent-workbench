from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from mini_agent.model_clients import OllamaModelClient

from .model_adapters import OllamaModelAdapter
from .nodes import ModelClient


@dataclass(frozen=True)
class ModelProviderConfig:
    provider: str = "ollama"
    options: Mapping[str, object] = field(default_factory=dict)


def build_model_client(config: ModelProviderConfig) -> ModelClient:
    if config.provider == "ollama":
        _validate_ollama_options(config.options)
        return OllamaModelAdapter(
            client=OllamaModelClient(
                model=_optional_str(config.options, "model"),
                base_url=_optional_str(config.options, "base_url"),
                timeout_seconds=_optional_int(config.options, "timeout_seconds"),
            )
        )

    raise ValueError(f"unsupported model provider: {config.provider}")


def _optional_str(options: Mapping[str, object], key: str) -> str | None:
    value = options.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"ollama option '{key}' must be a string")
    return value


def _optional_int(options: Mapping[str, object], key: str) -> int | None:
    value = options.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"ollama option '{key}' must be a positive integer")
    if isinstance(value, int):
        normalized = value
    elif isinstance(value, str) and value.strip().isdecimal():
        normalized = int(value)
    else:
        raise ValueError(f"ollama option '{key}' must be a positive integer")
    if normalized <= 0:
        raise ValueError(f"ollama option '{key}' must be a positive integer")
    return normalized


def _validate_ollama_options(options: Mapping[str, object]) -> None:
    allowed = {"model", "base_url", "timeout_seconds"}
    unknown = sorted(set(options) - allowed)
    if unknown:
        joined = ", ".join(unknown)
        raise ValueError(f"unsupported ollama model option(s): {joined}")
