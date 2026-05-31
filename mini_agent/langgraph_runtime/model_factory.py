from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from mini_agent.model_clients import OllamaModelClient, OpenAICompatibleModelClient

from .model_adapters import OllamaModelAdapter, OpenAICompatibleModelAdapter, RuleRouterModelAdapter
from .nodes import ModelClient


@dataclass(frozen=True)
class ModelProviderConfig:
    provider: str = "ollama"
    options: Mapping[str, object] = field(default_factory=dict)


def build_model_client(config: ModelProviderConfig) -> ModelClient:
    return _build_model_client(config, allow_router=True)


def _build_model_client(config: ModelProviderConfig, *, allow_router: bool) -> ModelClient:
    if config.provider == "ollama":
        _validate_ollama_options(config.options)
        return OllamaModelAdapter(
            client=OllamaModelClient(
                model=_optional_str(config.options, "model"),
                base_url=_optional_str(config.options, "base_url"),
                timeout_seconds=_optional_int(config.options, "timeout_seconds"),
            )
        )
    if config.provider == "openai_compatible":
        _validate_openai_compatible_options(config.options)
        timeout = _optional_int(config.options, "timeout_seconds", provider="openai_compatible") or 120
        return OpenAICompatibleModelAdapter(
            client=OpenAICompatibleModelClient(
                model=_required_str(config.options, "model", provider="openai_compatible"),
                base_url=_required_str(config.options, "base_url", provider="openai_compatible"),
                api_key=_optional_str(config.options, "api_key", provider="openai_compatible"),
                api_key_env=_optional_str(config.options, "api_key_env", provider="openai_compatible"),
                timeout_seconds=timeout,
            )
        )
    if config.provider == "router":
        if not allow_router:
            raise ValueError("router provider cannot be nested inside another router")
        return _build_router(config.options)

    raise ValueError(f"unsupported model provider: {config.provider}")


def _build_router(options: Mapping[str, object]) -> ModelClient:
    _validate_router_options(options)
    route_config = Path(_required_str(options, "route_config", provider="router"))
    body = json.loads(route_config.read_text(encoding="utf-8"))
    profiles_config = body.get("profiles")
    if not isinstance(profiles_config, dict) or not profiles_config:
        raise ValueError("router route_config must define non-empty profiles")
    default_profile = body.get("default_profile")
    if not isinstance(default_profile, str):
        raise ValueError("router route_config must define default_profile")
    profiles = {}
    for name, raw_profile in profiles_config.items():
        if not isinstance(raw_profile, dict):
            raise ValueError(f"router profile '{name}' must be an object")
        provider = raw_profile.get("provider")
        profile_options = raw_profile.get("options") or {}
        if not isinstance(provider, str):
            raise ValueError(f"router profile '{name}' must define provider")
        if not isinstance(profile_options, dict):
            raise ValueError(f"router profile '{name}' options must be an object")
        profiles[str(name)] = _build_model_client(
            ModelProviderConfig(provider=provider, options=profile_options),
            allow_router=False,
        )
    rules = body.get("rules") or []
    if not isinstance(rules, list):
        raise ValueError("router route_config rules must be a list")
    return RuleRouterModelAdapter(profiles=profiles, rules=rules, default_profile=default_profile)


def _optional_str(options: Mapping[str, object], key: str, *, provider: str = "ollama") -> str | None:
    value = options.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{provider} option '{key}' must be a string")
    return value


def _required_str(options: Mapping[str, object], key: str, *, provider: str) -> str:
    value = _optional_str(options, key, provider=provider)
    if value is None or not value:
        raise ValueError(f"{provider} option '{key}' is required")
    return value


def _optional_int(options: Mapping[str, object], key: str, *, provider: str = "ollama") -> int | None:
    value = options.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{provider} option '{key}' must be a positive integer")
    if isinstance(value, int):
        normalized = value
    elif isinstance(value, str) and value.strip().isdecimal():
        normalized = int(value)
    else:
        raise ValueError(f"{provider} option '{key}' must be a positive integer")
    if normalized <= 0:
        raise ValueError(f"{provider} option '{key}' must be a positive integer")
    return normalized


def _validate_ollama_options(options: Mapping[str, object]) -> None:
    allowed = {"model", "base_url", "timeout_seconds"}
    unknown = sorted(set(options) - allowed)
    if unknown:
        joined = ", ".join(unknown)
        raise ValueError(f"unsupported ollama model option(s): {joined}")


def _validate_openai_compatible_options(options: Mapping[str, object]) -> None:
    allowed = {"model", "base_url", "api_key", "api_key_env", "timeout_seconds"}
    unknown = sorted(set(options) - allowed)
    if unknown:
        joined = ", ".join(unknown)
        raise ValueError(f"unsupported openai_compatible model option(s): {joined}")


def _validate_router_options(options: Mapping[str, object]) -> None:
    allowed = {"route_config"}
    unknown = sorted(set(options) - allowed)
    if unknown:
        joined = ", ".join(unknown)
        raise ValueError(f"unsupported router model option(s): {joined}")
