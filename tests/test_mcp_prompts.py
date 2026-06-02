from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from langchain_core.messages import SystemMessage

from mini_agent.mcp_client import MCPServerConfig, MCPToolLoader
from mini_agent.mcp_prompts import MCPPromptProvider, resolve_mcp_prompt_selections
from mini_agent.runtime_context import RuntimeContextProvider


class FakeMCPClientManager:
    def __init__(self, values: dict[tuple[str, str], str]) -> None:
        self.values = values
        self.calls: list[tuple[str, str]] = []

    def get_prompt(self, server: str, name: str, arguments: dict[str, str] | None = None) -> str:
        self.calls.append((server, name))
        assert arguments is None
        return self.values[(server, name)]


class StaticContextProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    def context_text(self) -> str:
        return self.content


@dataclass
class FakeMemoryItem:
    id: int
    content: str


class FakeMemoryStore:
    def retrieve(self, user_input: str, limit: int) -> list[FakeMemoryItem]:
        assert user_input == "debug k8s"
        assert limit == 5
        return [FakeMemoryItem(id=1, content="Memory item")]


@dataclass
class FakeSkill:
    name: str
    version: str
    description: str
    content: str


class FakeSkillStore:
    def retrieve(self, user_input: str, limit: int) -> list[FakeSkill]:
        assert user_input == "debug k8s"
        assert limit == 3
        return [
            FakeSkill(
                name="k8s-debug",
                version="1",
                description="Debug Kubernetes state",
                content="Skill content",
            )
        ]


def test_resolve_mcp_prompt_selection_requires_selected_server():
    with pytest.raises(ValueError, match="requires at least one --mcp-server"):
        resolve_mcp_prompt_selections((), ("debug",))


def test_resolve_mcp_prompt_selection_requires_qualified_name_with_multiple_servers():
    with pytest.raises(ValueError, match="server:name"):
        resolve_mcp_prompt_selections(("docs", "k8s"), ("debug",))


def test_resolve_mcp_prompt_selection_uses_selected_server_for_unqualified_name():
    selections = resolve_mcp_prompt_selections(("docs",), ("debug", "docs:review"))

    assert [(item.server, item.name) for item in selections] == [
        ("docs", "debug"),
        ("docs", "review"),
    ]


def test_resolve_mcp_prompt_selection_rejects_empty_name():
    with pytest.raises(ValueError, match="name cannot be empty"):
        resolve_mcp_prompt_selections(("docs",), ("",))


def test_resolve_mcp_prompt_selection_rejects_unselected_qualified_server():
    with pytest.raises(ValueError, match="unselected MCP server"):
        resolve_mcp_prompt_selections(("docs", "k8s"), ("other:debug",))


def test_runtime_context_injects_mcp_prompt_context():
    manager = FakeMCPClientManager({("docs", "debug"): "Debug guidance"})
    provider = MCPPromptProvider(
        config_path=Path("unused.json"),
        selected_servers=("docs",),
        selected_prompts=("debug",),
        client_manager=manager,
    )

    messages = RuntimeContextProvider(mcp_prompts=provider).context_messages("debug docs")

    assert len(messages) == 1
    assert isinstance(messages[0], SystemMessage)
    assert "Selected MCP prompt guidance:" in str(messages[0].content)
    assert "server: docs" in str(messages[0].content)
    assert "prompt: debug" in str(messages[0].content)
    assert "Debug guidance" in str(messages[0].content)
    assert manager.calls == [("docs", "debug")]


def test_runtime_context_orders_mcp_prompt_before_skills_memory_and_resources():
    messages = RuntimeContextProvider(
        mcp_prompts=StaticContextProvider("Selected MCP prompt guidance:\nPrompt content"),
        skills=FakeSkillStore(),
        memory=FakeMemoryStore(),
        mcp_resources=StaticContextProvider("External MCP resources:\nResource content"),
    ).context_messages("debug k8s")

    contents = [str(message.content) for message in messages]

    assert contents[0].startswith("Selected MCP prompt guidance:")
    assert contents[1].startswith("Relevant skills:")
    assert contents[2].startswith("Memory:")
    assert contents[3].startswith("External MCP resources:")


def test_mcp_prompt_provider_truncates_and_skips_by_total_budget():
    manager = FakeMCPClientManager(
        {
            ("docs", "one"): "abcdef",
            ("docs", "two"): "uvwxyz",
            ("docs", "three"): "123456",
        }
    )
    provider = MCPPromptProvider(
        config_path=Path("unused.json"),
        selected_servers=("docs",),
        selected_prompts=("one", "two", "three"),
        client_manager=manager,
        max_prompt_chars=6,
        max_total_prompt_chars=8,
    )

    content = provider.context_text()

    assert content is not None
    assert "abcdef" in content
    assert "uv" in content
    assert "123456" not in content
    assert manager.calls == [("docs", "one"), ("docs", "two")]


def test_mcp_client_get_prompt_uses_prompt_getter(tmp_path):
    config = tmp_path / "mcp_servers.json"
    config.write_text('{"servers":{"docs":{"transport":"stdio","command":"server"}}}', encoding="utf-8")

    def get_prompt(server: MCPServerConfig, name: str, arguments: dict[str, str] | None) -> str:
        assert server.name == "docs"
        assert name == "debug"
        assert arguments is None
        return "Debug guidance"

    text = MCPToolLoader(config, prompt_getter=get_prompt).get_prompt("docs", "debug")

    assert text == "Debug guidance"
