from __future__ import annotations

import json
from typing import Any


def parse_json_decision(content: str) -> dict[str, Any] | None:
    normalized = strip_markdown_json_fence(content.strip())
    try:
        decision = json.loads(normalized)
    except json.JSONDecodeError:
        return extract_embedded_action(normalized)
    return decision if isinstance(decision, dict) else None


def strip_markdown_json_fence(content: str) -> str:
    if not content.startswith("```"):
        return content
    lines = content.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return content


def extract_embedded_action(content: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "action" in candidate:
            return candidate
    return None
