from __future__ import annotations

from vermay_agent.observation import ObservationHandler
from vermay_agent.types import ToolResult


def test_observation_formats_successful_string_output():
    observation = ObservationHandler().process(ToolResult(name="echo", ok=True, output="ok"))

    assert observation.tool_name == "echo"
    assert observation.ok is True
    assert observation.content == "ok"


def test_observation_marks_failed_tool_result():
    observation = ObservationHandler().process(ToolResult(name="echo", ok=False, error="boom"))

    assert observation.tool_name == "echo"
    assert observation.ok is False
    assert observation.content == "TOOL_ERROR: boom"


def test_observation_truncates_long_string_output_with_marker():
    output = "x" * 4001

    observation = ObservationHandler().process(ToolResult(name="echo", ok=True, output=output))

    assert observation.content == ("x" * 4000) + "\n...<truncated>"


def test_observation_truncates_long_json_output_with_marker():
    output = {"payload": "x" * 5000}

    observation = ObservationHandler().process(ToolResult(name="echo", ok=True, output=output))

    assert observation.content.endswith("\n...<truncated>")
    assert len(observation.content) == len("\n...<truncated>") + 4000
