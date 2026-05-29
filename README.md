# Mini Agent Workbench

Mini Agent Workbench is an out-of-the-box Python workbench for building and validating an agent harness.

The runtime is built on LangGraph, while the harness boundaries remain explicit: context construction, model calls, tool registration, permission checks, tool execution, observations, progress output, and JSONL traces are implemented as visible project modules instead of being hidden inside one opaque node.

The project is intended to provide a concrete, runnable baseline for agent harness engineering:

- LangGraph runtime orchestration.
- Tool calling through an explicit registry and executor.
- Permission control before dangerous operations.
- Approval interrupt and resume.
- Model adapter boundary.
- Human-readable progress output.
- JSONL audit traces.

## Harness Boundary

In this project, harness means the engineering layer around the model that turns model intent into controlled execution.

The model may produce an action such as:

```json
{"action":"tool_call","name":"weather_forecast","arguments":{"location":"Beijing"}}
```

The harness is responsible for:

```text
build context
  -> call model
  -> parse model action
  -> check permission
  -> execute tool
  -> convert result to observation
  -> record progress and trace
  -> continue or finish
```

Core harness modules include `context_builder.py`, `tool_registry.py`, `tool_executor.py`, `permission.py`, `observation.py`, `trace.py`, `progress.py`, and `types.py`.

`mini_agent/langgraph_runtime/` is the current orchestration layer that wires those harness components into a LangGraph state machine. It now serves as the reference baseline for harness mechanics.

`mini_agent/standard_runtime/` contains the first skeleton of the future production-oriented runtime. That path aligns with LangChain / LangGraph standard message types such as `BaseMessage`, `AIMessage.tool_calls`, `ToolMessage`, and `add_messages`, but it is not wired into the CLI yet.

## Install

```bash
cd <repo-root>
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Run

```bash
mini-agent "weather forecast for Beijing"
```

The CLI currently uses the reference LangGraph runtime in `mini_agent/langgraph_runtime/`.

By default, the CLI prints a compact harness progress transcript to stderr. This is produced by `ProgressReporter` and shows each agent loop as readable event blocks: context build, model call, tool call, permission check, tool result, observation, and final answer.

LangGraph stream inspection is separate and disabled by default. `GraphStreamReporter` is enabled only with `--graph-stream` or `--graph-stream-mode`; it summarizes LangGraph runtime chunks such as `updates`, `custom`, `values`, and `debug`. When graph stream inspection is enabled, the default progress transcript is suppressed so the two reporter layers do not interleave.

```bash
# default harness progress
mini-agent "weather forecast for Beijing"

# LangGraph stream debug inspection
mini-agent "weather forecast for Beijing" --graph-stream
```

## Model Client

The runtime calls models through a `ModelClient` boundary. This keeps provider-specific request formats, authentication, timeouts, and response parsing outside the harness orchestration.

The current implementation includes an Ollama-compatible client in `mini_agent/model_clients/ollama.py`. Its default configuration is read from `.env`, then overridden by `.env.local`, `.env.dev.local`, shell environment variables, and finally CLI flags.

```bash
MINI_AGENT_OLLAMA_MODEL=deepseek-v4-flash:cloud
MINI_AGENT_OLLAMA_BASE_URL=http://127.0.0.1:11434
MINI_AGENT_OLLAMA_TIMEOUT_SECONDS=120
```

CLI override example:

```bash
# default model configuration
mini-agent "weather forecast for Beijing"

# override model client settings
mini-agent "weather forecast for Beijing" \
  --ollama-model qwen3.6:27b \
  --ollama-base-url http://127.0.0.1:11434 \
  --ollama-timeout-seconds 120
```

Additional providers can be added by implementing the same model client protocol and returning the project `ModelResponse` type.

The active adapter expects a JSON action protocol:

```json
{"action":"final","content":"..."}
```

or:

```json
{"action":"tool_call","name":"tool_name","arguments":{}}
```

## Documentation

Stable project documentation is under [docs/README.md](docs/README.md).

Planning notes and historical implementation records are kept outside this repository in the companion `mini-agent-docs` workspace.

## Tests

```bash
.venv/bin/python -m pytest
```
