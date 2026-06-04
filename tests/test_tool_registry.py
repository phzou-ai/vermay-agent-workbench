import pytest
from pydantic import Field

from vermay_agent.tool_registry import ToolRegistry
from vermay_agent.tooling import ToolArgs, structured_tool
from vermay_agent.tools.devops import register_devops_tools
from vermay_agent.tools.devops.constants import (
    KUBECTL_DESCRIBE_RESOURCES,
    KUBECTL_GET_RESOURCES,
    MOCK_KUBECTL_GET_RESOURCES,
)


class SampleArgs(ToolArgs):
    value: str = Field(description="Sample value.")


def make_sample_tool(dangerous: bool = False):
    return structured_tool(
        func=lambda value: value,
        name="sample",
        description="Sample tool.",
        args_schema=SampleArgs,
        dangerous=dangerous,
    )


def test_registry_exposes_schema_from_structured_tool_args_schema():
    registry = ToolRegistry()
    registry.register(make_sample_tool())

    schema = registry.schemas()[0]

    assert registry.names() == ["sample"]
    assert schema["name"] == "sample"
    assert schema["description"] == "Sample tool."
    assert schema["dangerous"] is False
    assert schema["parameters"]["properties"]["value"]["type"] == "string"
    assert schema["parameters"]["properties"]["value"]["description"] == "Sample value."
    assert schema["parameters"]["required"] == ["value"]


def test_registry_exposes_dangerous_metadata():
    registry = ToolRegistry()
    registry.register(make_sample_tool(dangerous=True))

    assert registry.is_dangerous("sample") is True
    assert registry.schemas()[0]["dangerous"] is True


def test_registry_rejects_duplicate_tool_names():
    registry = ToolRegistry()
    tool = make_sample_tool()

    registry.register(tool)

    with pytest.raises(ValueError, match="tool already registered: sample"):
        registry.register(tool)


def test_registry_unknown_tool_has_clear_error():
    registry = ToolRegistry()

    with pytest.raises(KeyError, match="unknown tool: missing"):
        registry.get("missing")


def test_devops_tool_schemas_use_single_source_resource_enums():
    registry = ToolRegistry()
    register_devops_tools(registry)
    schemas = {schema["name"]: schema for schema in registry.schemas()}

    mock_resource_schema = schemas["kubectl_get"]["parameters"]["$defs"]["MockKubectlGetResource"]
    get_resource_schema = schemas["ssh_kubectl_get"]["parameters"]["$defs"]["KubectlGetResource"]
    describe_resource_schema = schemas["ssh_kubectl_describe"]["parameters"]["$defs"]["KubectlDescribeResource"]

    assert mock_resource_schema["enum"] == MOCK_KUBECTL_GET_RESOURCES
    assert get_resource_schema["enum"] == KUBECTL_GET_RESOURCES
    assert describe_resource_schema["enum"] == KUBECTL_DESCRIBE_RESOURCES
