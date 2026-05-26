from __future__ import annotations

import sys
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Sequence

from rich.console import Console


SUPPORTED_STREAM_MODES = {"updates", "values", "debug", "custom"}
DEFAULT_STREAM_MODES = ("updates", "custom")


def parse_stream_modes(values: Sequence[str] | None) -> tuple[str, ...]:
    if not values:
        return DEFAULT_STREAM_MODES

    modes: list[str] = []
    for value in values:
        for part in value.split(","):
            mode = part.strip()
            if mode:
                modes.append(mode)

    invalid = sorted(set(modes) - SUPPORTED_STREAM_MODES)
    if invalid:
        supported = ", ".join(sorted(SUPPORTED_STREAM_MODES))
        raise ValueError(f"Unsupported stream mode(s): {', '.join(invalid)}. Supported modes: {supported}")

    return tuple(dict.fromkeys(modes))


class GraphStreamReporter:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.console = Console(file=sys.stderr, force_terminal=True, color_system="auto")

    def event(self, mode: str, chunk: Any) -> None:
        if not self.enabled:
            return

        summary = summarize_stream_chunk(mode, chunk)
        if summary:
            self.console.print(f"[dim][graph:{mode}][/dim] {summary}")


def summarize_stream_chunk(mode: str, chunk: Any) -> str:
    if mode == "updates":
        return _summarize_updates(chunk)
    if mode == "values":
        return _summarize_values(chunk)
    if mode == "debug":
        return _summarize_debug(chunk)
    if mode == "custom":
        return _summarize_custom(chunk)
    return _short_repr(chunk)


def _summarize_updates(chunk: Any) -> str:
    if not isinstance(chunk, dict):
        return _short_repr(chunk)

    parts = []
    for node, update in chunk.items():
        if node == "__interrupt__":
            parts.append("__interrupt__")
            continue
        if isinstance(update, dict):
            parts.append(f"{node} -> {', '.join(update.keys())}")
        else:
            parts.append(f"{node} -> {_short_repr(update)}")
    return "; ".join(parts)


def _summarize_values(chunk: Any) -> str:
    if not isinstance(chunk, dict):
        return _short_repr(chunk)

    final_answer = chunk.get("final_answer")
    tool_call = _to_plain(chunk.get("tool_call"))
    observations = chunk.get("observations") or []
    pieces = [
        f"step={chunk.get('step')}",
        f"messages={len(chunk.get('messages') or [])}",
        f"observations={len(observations)}",
    ]
    if isinstance(tool_call, dict) and tool_call.get("name"):
        pieces.append(f"tool_call={tool_call['name']}")
    if final_answer is not None:
        pieces.append("final_answer=set")
    if chunk.get("__interrupt__"):
        pieces.append("interrupt=set")
    return " ".join(pieces)


def _summarize_debug(chunk: Any) -> str:
    if not isinstance(chunk, dict):
        return _short_repr(chunk)

    event_type = chunk.get("type")
    payload = chunk.get("payload")
    if isinstance(payload, dict):
        name = payload.get("name")
        if name:
            return f"{event_type} {name}"
    return str(event_type or _short_repr(chunk))


def _summarize_custom(chunk: Any) -> str:
    if not isinstance(chunk, dict):
        return _short_repr(chunk)

    event = chunk.get("event")
    data = {key: value for key, value in chunk.items() if key != "event"}
    fields = " ".join(f"{key}={_short_repr(value)}" for key, value in data.items())
    return f"{event or 'event'} {fields}".strip()


def normalize_stream_chunk(chunk: Any, modes: Iterable[str]) -> tuple[str, Any]:
    if isinstance(chunk, tuple) and len(chunk) == 2 and chunk[0] in SUPPORTED_STREAM_MODES:
        return chunk[0], chunk[1]

    mode_list = tuple(modes)
    if len(mode_list) == 1:
        return mode_list[0], chunk
    return "updates", chunk


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


def _short_repr(value: Any, limit: int = 120) -> str:
    plain = _to_plain(value)
    text = repr(plain)
    if len(text) > limit:
        return text[:limit] + "..."
    return text
