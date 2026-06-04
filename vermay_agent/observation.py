from __future__ import annotations

"""Legacy observation formatter for the archived hands-on harness path.

The active LangGraph runtime consumes LangChain `ToolMessage` values instead of
project `Observation` objects. This module remains for compatibility tests and
for documenting the earlier explicit ToolResult -> Observation boundary.
"""

import json

from .types import Observation, ToolResult


class ObservationHandler:
    def process(self, result: ToolResult) -> Observation:
        if result.ok:
            content = self._format_output(result.output)
        else:
            content = f"TOOL_ERROR: {result.error}"

        return Observation(tool_name=result.name, content=content, ok=result.ok)

    def _format_output(self, output: object) -> str:
        if isinstance(output, str):
            text = output
        else:
            text = json.dumps(output, ensure_ascii=False, indent=2)
        if len(text) > 4000:
            return text[:4000] + "\n...<truncated>"
        return text
