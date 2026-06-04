from pathlib import Path

import pytest

from vermay_agent.model_selection import resolve_model_selection


def write_models_config(path: Path) -> None:
    path.write_text(
        """
{
  "primary_model": "local_ollama",
  "models": {
    "local_ollama": {
      "provider": "ollama",
      "options": {}
    },
    "qwen_vllm": {
      "provider": "openai_compatible",
      "options": {
        "model": "qwen",
        "base_url": "http://localhost:8000/v1"
      }
    }
  }
}
""",
        encoding="utf-8",
    )


def test_model_selection_resolves_default_fixed_model(tmp_path: Path):
    config_path = tmp_path / "models.json"
    write_models_config(config_path)

    config = resolve_model_selection(config_path=config_path)

    assert config.provider == "ollama"
    assert config.options == {}


def test_model_selection_resolves_named_fixed_model(tmp_path: Path):
    config_path = tmp_path / "models.json"
    write_models_config(config_path)

    config = resolve_model_selection(
        config_path=config_path,
        model_name="qwen_vllm",
    )

    assert config.provider == "openai_compatible"
    assert config.options["model"] == "qwen"


def test_model_selection_rejects_unknown_model(tmp_path: Path):
    config_path = tmp_path / "models.json"
    write_models_config(config_path)

    with pytest.raises(ValueError, match="model is not defined: missing"):
        resolve_model_selection(config_path=config_path, model_name="missing")


def test_model_selection_rejects_missing_primary_model(tmp_path: Path):
    config_path = tmp_path / "models.json"
    config_path.write_text(
        """
{
  "models": {
    "local_ollama": {
      "provider": "ollama",
      "options": {}
    }
  }
}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must define primary_model"):
        resolve_model_selection(config_path=config_path)
