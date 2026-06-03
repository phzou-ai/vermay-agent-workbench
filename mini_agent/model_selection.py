from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from mini_agent.langgraph_runtime import ModelProviderConfig


def resolve_model_selection(
    *,
    config_path: Path,
    model_name: str | None = None,
) -> ModelProviderConfig:
    body = _load_models_config(config_path)
    return _model_provider_config(body, model_name or _primary_model(body))


def _load_models_config(config_path: Path) -> Mapping[str, object]:
    if not config_path.exists():
        raise ValueError(f"model config does not exist: {config_path}")
    body = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise ValueError("model config must be an object")
    return body


def _primary_model(body: Mapping[str, object]) -> str:
    primary_model = body.get("primary_model")
    if not isinstance(primary_model, str):
        raise ValueError("model config must define primary_model")
    return primary_model


def _model_provider_config(body: Mapping[str, object], model_name: str) -> ModelProviderConfig:
    models = body.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("model config must define non-empty models")
    raw_model = models.get(model_name)
    if not isinstance(raw_model, dict):
        raise ValueError(f"model is not defined: {model_name}")
    provider = raw_model.get("provider")
    options = raw_model.get("options") or {}
    if not isinstance(provider, str):
        raise ValueError(f"model '{model_name}' must define provider")
    if not isinstance(options, dict):
        raise ValueError(f"model '{model_name}' options must be an object")
    return ModelProviderConfig(provider=provider, options=options)
