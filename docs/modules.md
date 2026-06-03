# Key Modules

## Entry Point

`mini_agent/main.py`

- Defines the `mini-agent` console entry point.
- Dispatches prompt execution or named subcommands.
- Re-exports a small set of CLI helpers for compatibility with existing tests.

`mini_agent/cli/prompt.py`

- Parses prompt-run CLI arguments.
- Maps provider-specific flags and `--model-option key=value` into model provider options.
- Resolves trace paths.
- Handles approval resume CLI options.
- Owns terminal-only interactive approval prompting.

`mini_agent/cli/subcommands.py`

- Dispatches subcommands for `serve`, memory, skills, eval replay, and MCP inspection.
- Owns subcommand-specific argument parsing.
- Keeps local SQLite store lifecycle scoped to each command invocation.

## API

`mini_agent/api/`

- `app.py`: FastAPI app factory and HTTP route definitions.
- `a2a_readiness.py`: local projection helpers for A2A task, status, and artifact adapter work.
- `a2a/`: opt-in A2A adapter package and protocol route definitions over `AgentService`.
- `service.py`: service boundary for creating sessions, starting or queueing tasks, resuming approval, retrying terminal tasks, cancelling tasks, and reading task/session metadata.
- `session_models.py`: project-level task status model and lifecycle predicates.
- `session_store.py`: SQLite-backed session, task, task-event, and task-artifact metadata, including selected MCP task configuration and retry lineage.
- `task_contract.py`: shared task event type contract and event classification sets.
- `lifecycle.py`: compact lifecycle observer abstractions for API operation monitoring.

The API layer uses `LangGraphAgentRuntime.start()` and `resume()` through task-level service methods. It accepts structured MCP task selection, stores that selection in task metadata, and reuses it on approval resume. It does not call CLI string-output helpers and does not expose raw graph state by default.

A2A support belongs at this API boundary. A2A adapters call `AgentService` and use `a2a_readiness.py`-style projection helpers; they should not modify the LangGraph graph topology or introduce A2A protocol concepts into `mini_agent/langgraph_runtime/`.

## Runtime Factory

`mini_agent/app_factory.py`

- Defines `RuntimeFactoryConfig`.
- Builds the active LangGraph runtime through `build_runtime()`.
- Wires model adapters, tools, permission checks, trace logging, progress reporting, memory, skills, and approval handling.
- Injects the CLI SQLite checkpointer.
- Registers runtime close callbacks for owned resources such as SQLite connections.
- Owns factory-level paths such as `trace_path`, `checkpoint_path`, `agent_store_path`, `skills_path`, and `mcp_config_path`.

## LangGraph Runtime

`mini_agent/langgraph_runtime/`

- `state.py`: standard LangGraph state using `messages: Annotated[list[BaseMessage], add_messages]`.
- `nodes.py`: model, permission, approval, tool-message recording, and loop-control nodes.
- `routing.py`: message routing helpers based on `AIMessage.tool_calls`.
- `graph.py`: graph topology using `ToolNode` after permission and approval checks.
- `runner.py`: runtime wrapper around the compiled graph.
- `results.py`: structured runtime result type and API-facing result payload helpers.
- `model_adapters.py`: adapters from project model clients to a thin `AIMessage` wrapper, plus deterministic model routing.
- `model_factory.py`: provider factory for constructing runtime model adapters.

This package is the only active runtime path. It is the production-oriented path and uses LangChain / LangGraph standard message and tool execution types.

## Shared Harness Components

`mini_agent/`

- `context_builder.py`: builds the default system prompt and remains the source for context policy text.
- `checkpointing.py`: builds SQLite checkpointers for durable CLI approval resume.
- `tooling.py`: helper for creating `StructuredTool` objects with Pydantic `args_schema` and project metadata.
- `tool_schema.py`: converts active `StructuredTool` objects into model-facing schemas.
- `tool_registry.py`: stores `StructuredTool` objects and exposes schema inspection over the same tool objects.
- `permission.py`: blocks dangerous tools before execution.
- `result_summary.py`: shared summary helpers for terminal progress output.
- `trace.py`: writes JSONL runtime events.
- `progress.py`: renders the default human-readable harness progress transcript.
- `errors.py`: shared project error taxonomy for API response mapping and failed-task persistence.
- `storage.py`: local SQLite metadata store with schema version marker.
- `memory.py`: SQLite-backed explicit-write memory.
- `skills.py`: authored skill parser, retrieval, proposal generation, and approval.
- `runtime_context.py`: injects selected MCP prompts, authored skills, memory, and selected MCP resources as initial system context.
- `evaluation.py`: offline trace/scenario replay reporting without live model or live tool execution.
- `mcp_client.py`: high-level MCP client manager and compatibility re-exports.
- `mcp_config.py`: MCP server config parsing and exposure policy constants.
- `mcp_models.py`: MCP server, tool, resource, prompt, and report dataclasses.
- `mcp_tool_adapter.py`: MCP tool exposure policy, namespacing, reports, and `StructuredTool` conversion.
- `mcp_transport.py`: stdio MCP transport calls, bounded operation timeouts, transport errors, and result serialization.
- `mcp_selection.py`: structured MCP selection model used by the API service and runtime factory wiring.
- `mcp_prompts.py`: selected MCP prompt retrieval, truncation, and context injection.
- `mcp_resources.py`: selected MCP resource retrieval, truncation, and context injection.
- `types.py`: shared dataclasses for project message, tool-call, result, observation, and model-response payloads.

The active tool schema source is each tool's Pydantic `args_schema`. Model adapters and `ToolRegistry.schemas()` both derive schemas from the same `StructuredTool` objects that `ToolNode` executes.

`tool_executor.py` and `observation.py` are retained for compatibility and explicit harness tests. They are not the active ToolNode execution path.

## Model Adapters

`mini_agent/model_clients/ollama.py`

- Calls Ollama `/api/chat`.
- Uses a small JSON action protocol for final answers and tool calls.
- Reads model configuration from `config/models.json` or explicit runtime overrides.

`mini_agent/model_clients/openai_compatible.py`

- Calls OpenAI-style `{base_url}/chat/completions` endpoints.
- Sends Bearer authentication when `api_key` or `api_key_env` is configured.
- Uses standard Chat Completions `tools`, `tool_choice`, assistant `tool_calls`, and `role: tool` messages with `tool_call_id`.
- Omits `tools` and `tool_choice` when no tools are available.

`mini_agent/langgraph_runtime/model_factory.py`

- Builds provider-specific model adapters for the active runtime.
- Accepts `ModelProviderConfig(provider, options)`.
- Validates provider-specific options.
- Supports configured `ollama` and `openai_compatible` model providers.
- `openai_compatible` targets OpenAI-style `/chat/completions` endpoints such as vLLM.
- `config/models.json` defines named model provider configs and the primary model.

## Tool Domains

`mini_agent/tools/devops/`

- Local file and log inspection tools.
- Local sample Kubernetes data tools.
- SSH-backed read-only Kubernetes tools.
- Dangerous tool placeholders that require approval.

`mini_agent/tools/weather/`

- `weather_forecast` read-only external data tool backed by `wttr.in`.

Configured MCP servers are inactive by default. Runtime construction loads MCP tools only from explicitly selected servers, such as `--mcp-server k8s`. Eligible discovered MCP tools are wrapped as `StructuredTool` objects with namespaced model-facing names and registered through the same `ToolRegistry` path as built-in tools.

Explicitly selected MCP prompts and resources are read once at run start. `RuntimeContextProvider` injects them in this order: MCP prompts, local authored skills, explicit memory, MCP resources. Prompts are treated as external workflow guidance; resources are treated as untrusted external data. Prompt selections can carry explicit string arguments, which are passed to the MCP server when retrieving the prompt.

`examples/mcp_servers/k8s/`

- Read-only MCP stdio server for Kubernetes inspection.
- Reuses the existing SSH/microk8s backend.
- Exposes read-only tools, resources, and prompts without adding Kubernetes-specific logic to the runtime core.

## Infrastructure

`mini_agent/infra/ssh.py`

- Builds strict SSH commands from environment configuration.
- Enforces host key checking and known hosts usage.
- Redacts identity file path in returned command traces.

## Archive

`archive/hands_on_langgraph_runtime/`

- Contains the earlier explicit harness implementation.
- Is not exposed through the CLI.
- Is not part of the default pytest suite.
- Should be treated as historical reference material, not a second runtime track.
