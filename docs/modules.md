# Key Modules

## Entry Point

`mini_agent/main.py`

- Defines the `mini-agent` CLI.
- Builds the LangGraph runtime.
- Wires model, tools, memory, trace, progress reporting, and checkpoint storage.
- Handles approval resume CLI options.
- Owns terminal-only interactive approval prompting.

## LangGraph Runtime

`mini_agent/langgraph_runtime/`

- `runner.py`: runtime wrapper around the compiled graph.
- `results.py`: structured runtime result type and API-facing result payload helpers.
- `graph.py`: LangGraph node and edge topology.
- `nodes.py`: graph node implementations that call the shared harness components.
- `routing.py`: conditional edge routing functions.
- `state.py`: graph state shape.
- `streaming.py`: summarized graph stream reporting.
- `toolnode_adapter.py`: adapters between project tool types and LangChain/LangGraph tool message types; not part of the active runtime path yet.
- `adapters.py`: payload conversion helpers for trace and progress output.

## Shared Harness Components

`mini_agent/`

- `context_builder.py`: builds model messages from user input, memory, skills, and observations.
- `tool_registry.py`: stores tool specs and exposes model-facing schemas.
- `tool_executor.py`: executes tool calls and normalizes failures into `ToolResult`.
- `permission.py`: blocks dangerous tools before execution.
- `observation.py`: converts tool results into model-readable observations.
- `result_summary.py`: shared summary helpers for terminal progress output.
- `trace.py`: writes JSONL runtime events.
- `progress.py`: renders human-readable terminal progress.
- `memory.py`: minimal file-backed memory placeholder.
- `types.py`: shared dataclasses for messages, tools, results, observations, and model responses.

## Model Adapter

`mini_agent/model_clients/ollama.py`

- Calls Ollama `/api/chat`.
- Uses a small JSON action protocol for final answers and tool calls.
- Reads default model configuration from `.env`, `.env.local`, `.env.dev.local`, or shell environment.

## Tool Domains

`mini_agent/tools/devops/`

- Local file and log inspection tools.
- Local sample Kubernetes data tools.
- SSH-backed read-only Kubernetes tools.
- Dangerous tool placeholders that require approval.

`mini_agent/tools/weather/`

- `weather_forecast` read-only external data tool backed by `wttr.in`.

## Infrastructure

`mini_agent/infra/ssh.py`

- Builds strict SSH commands from environment configuration.
- Enforces host key checking and known hosts usage.
- Redacts identity file path in returned command traces.
