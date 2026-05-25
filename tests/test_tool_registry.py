import pytest

from mini_agent.tool_registry import ToolRegistry
from mini_agent.types import ToolSpec


def test_registry_exposes_schema_without_function():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="sample",
            description="Sample tool.",
            parameters={"type": "object", "properties": {"value": {"type": "string"}}},
            dangerous=False,
            func=lambda value: value,
        )
    )

    assert registry.names() == ["sample"]
    assert registry.schemas() == [
        {
            "name": "sample",
            "description": "Sample tool.",
            "parameters": {"type": "object", "properties": {"value": {"type": "string"}}},
            "dangerous": False,
        }
    ]


def test_registry_rejects_duplicate_tool_names():
    registry = ToolRegistry()
    spec = ToolSpec(
        name="sample",
        description="Sample tool.",
        parameters={"type": "object", "properties": {}},
        dangerous=False,
        func=lambda: None,
    )

    registry.register(spec)

    with pytest.raises(ValueError, match="tool already registered: sample"):
        registry.register(spec)


def test_registry_unknown_tool_has_clear_error():
    registry = ToolRegistry()

    with pytest.raises(KeyError, match="unknown tool: missing"):
        registry.get("missing")
