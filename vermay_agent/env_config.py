from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILES = (".env", ".env.local", ".env.dev.local")


def load_prefixed_env(prefix: str, root: Path | None = None) -> dict[str, str]:
    root = root or ROOT
    values: dict[str, str] = {}
    for name in ENV_FILES:
        path = root / name
        if path.exists():
            values.update(parse_env_file(path, prefix=prefix))

    for key, value in os.environ.items():
        if key.startswith(prefix):
            values[key] = value
    return values


def load_prefixed_env_with_legacy_aliases(
    preferred_prefix: str,
    legacy_prefixes: tuple[str, ...],
    root: Path | None = None,
) -> dict[str, str]:
    root = root or ROOT
    values: dict[str, tuple[str, bool, int]] = {}

    for rank, name in enumerate(ENV_FILES):
        path = root / name
        if not path.exists():
            continue
        for legacy_prefix in legacy_prefixes:
            _merge_prefixed_values(
                values,
                parse_env_file(path, prefix=legacy_prefix),
                source_prefix=legacy_prefix,
                target_prefix=preferred_prefix,
                preferred=False,
                rank=rank,
            )
        _merge_prefixed_values(
            values,
            parse_env_file(path, prefix=preferred_prefix),
            source_prefix=preferred_prefix,
            target_prefix=preferred_prefix,
            preferred=True,
            rank=rank,
        )

    env_rank = len(ENV_FILES)
    for legacy_prefix in legacy_prefixes:
        legacy_values = {key: value for key, value in os.environ.items() if key.startswith(legacy_prefix)}
        _merge_prefixed_values(
            values,
            legacy_values,
            source_prefix=legacy_prefix,
            target_prefix=preferred_prefix,
            preferred=False,
            rank=env_rank,
        )
    preferred_values = {key: value for key, value in os.environ.items() if key.startswith(preferred_prefix)}
    _merge_prefixed_values(
        values,
        preferred_values,
        source_prefix=preferred_prefix,
        target_prefix=preferred_prefix,
        preferred=True,
        rank=env_rank,
    )
    return {key: value for key, (value, _, _) in values.items()}


def _normalize_prefixed_env(values: dict[str, str], source_prefix: str, target_prefix: str) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in values.items():
        if key.startswith(source_prefix):
            normalized[target_prefix + key[len(source_prefix) :]] = value
    return normalized


def _merge_prefixed_values(
    merged: dict[str, tuple[str, bool, int]],
    incoming: dict[str, str],
    *,
    source_prefix: str,
    target_prefix: str,
    preferred: bool,
    rank: int,
) -> None:
    for key, value in _normalize_prefixed_env(incoming, source_prefix, target_prefix).items():
        current = merged.get(key)
        if current is None:
            merged[key] = (value, preferred, rank)
            continue
        _, current_preferred, current_rank = current
        if _should_replace_legacy_alias(
            incoming_preferred=preferred,
            incoming_rank=rank,
            current_preferred=current_preferred,
            current_rank=current_rank,
        ):
            merged[key] = (value, preferred, rank)


def _should_replace_legacy_alias(
    *,
    incoming_preferred: bool,
    incoming_rank: int,
    current_preferred: bool,
    current_rank: int,
) -> bool:
    if incoming_preferred:
        if not current_preferred:
            return True
        return incoming_rank >= current_rank
    if not current_preferred:
        return incoming_rank >= current_rank
    return current_rank == 0 and incoming_rank > current_rank


def parse_env_file(path: Path, prefix: str | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if prefix is not None and not key.startswith(prefix):
            continue
        values[key] = strip_env_value(value.strip())
    return values


def strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
