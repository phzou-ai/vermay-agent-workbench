# Key Modules

## Entry Point

`mini_agent/main.py`

- Defines the `mini-agent` CLI.
- Builds the selected LangGraph runtime.
- Wires model, tools, memory, trace, progress reporting, and checkpoint storage.
- Supports controlled runtime comparison through `--runtime reference` and `--runtime standard`.
- Handles approval resume CLI options.
- Owns terminal-only interactive approval prompting.

## Reference LangGraph Runtime

`mini_agent/langgraph_runtime/`

- `runner.py`: runtime wrapper around the compiled graph.
- `results.py`: structured runtime result type and API-facing result payload helpers.
- `graph.py`: LangGraph node and edge topology.
- `nodes.py`: graph node implementations that call the shared harness components.
- `routing.py`: conditional edge routing functions.
- `state.py`: graph state shape.
- `streaming.py`: optional LangGraph stream inspection and summarized graph stream reporting.
- `toolnode_adapter.py`: adapters between project tool types and LangChain/LangGraph tool message types; retained for reference-runtime compatibility experiments.
- `adapters.py`: payload conversion helpers for trace and progress output.

This package remains the default CLI runtime and the reference baseline for harness mechanics. It should not keep expanding as the future production-oriented runtime unless a task explicitly targets the reference baseline.

## Standard LangGraph Runtime

`mini_agent/standard_runtime/`

- `state.py`: standard LangGraph state using `messages: Annotated[list[BaseMessage], add_messages]`.
- `nodes.py`: standard model, permission, approval, tool-message recording, and loop-control nodes.
- `routing.py`: standard message routing helpers based on `AIMessage.tool_calls`.
- `graph.py`: standard graph using `ToolNode` after permission and approval checks.
- `runner.py`: runtime wrapper with start/resume methods.
- `model_adapters.py`: adapter from the project Ollama client to `AIMessage` / `tool_calls`.
- `tools.py`: conversion from project `ToolSpec` to LangChain `StructuredTool`.

This package can be selected with `mini-agent "<prompt>" --runtime standard`. It is the future production-oriented runtime direction and is being compared against the reference runtime before any default switch.

## Shared Harness Components

`mini_agent/`

- `context_builder.py`: builds model messages from user input, memory, skills, and observations.
- `tool_registry.py`: stores tool specs and exposes model-facing schemas.
- `tool_executor.py`: executes tool calls and normalizes failures into `ToolResult`.
- `permission.py`: blocks dangerous tools before execution.
- `observation.py`: converts tool results into model-readable observations.
- `result_summary.py`: shared summary helpers for terminal progress output.
- `trace.py`: writes JSONL runtime events.
- `progress.py`: renders the default human-readable harness progress transcript.
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
