# Mini Agent Workbench

Mini Agent Workbench is an out-of-the-box Python workbench for building and validating an agent harness.

The active runtime is built on LangGraph and follows LangChain / LangGraph standard message types: `BaseMessage`, `AIMessage.tool_calls`, `ToolMessage`, `ToolNode`, and `add_messages`. The project keeps harness boundaries explicit so model calls, tool registration, permission checks, approval interrupts, progress output, and JSONL traces remain visible project modules.

## Harness Boundary

In this project, harness means the engineering layer around the model that turns model intent into controlled execution.

The harness is responsible for:

```text
build context
  -> call model
  -> inspect model decision
  -> check permission
  -> execute tool
  -> record tool message
  -> continue or finish
```

Core harness modules include `context_builder.py`, `tool_registry.py`, `permission.py`, `trace.py`, `progress.py`, and `types.py`.

The active runtime is `mini_agent/langgraph_runtime/`. The earlier hands-on runtime has been moved to `archive/hands_on_langgraph_runtime/` as historical reference material and is not exposed by the CLI.

## Tool Schema Source

Tool definitions use one source of truth:

```text
Pydantic args_schema
  -> StructuredTool
  -> model-facing schema per model call
  -> ToolNode execution validation
```

`ToolRegistry.schemas()` is an inspection helper over the same `StructuredTool` list, not a second schema source. Dangerous-tool metadata is stored on the `StructuredTool` metadata and read by `PermissionGate`. The active runtime does not maintain a separate `ToolSpec.parameters` schema.

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
mini-agent "weather forecast for Shanghai"
```

By default, the CLI prints a compact harness progress transcript to stderr. The final answer is printed to stdout.

## Model Client

The runtime calls models through a provider adapter boundary. Provider-specific request formats, authentication, timeouts, and response parsing stay outside graph orchestration.

The CLI builds the runtime through `mini_agent/app_factory.py`. Model adapters are built through `mini_agent/langgraph_runtime/model_factory.py`. The current provider is `ollama`; later providers such as vLLM or OpenAI should be added to the model factory instead of being wired directly in `main.py`.

The Ollama-compatible client is implemented in `mini_agent/model_clients/ollama.py`. Its default configuration is read from `.env`, then overridden by `.env.local`, `.env.dev.local`, shell environment variables, and finally CLI flags.

```bash
MINI_AGENT_OLLAMA_MODEL=deepseek-v4-flash:cloud
MINI_AGENT_OLLAMA_BASE_URL=http://127.0.0.1:11434
MINI_AGENT_OLLAMA_TIMEOUT_SECONDS=120
```

CLI override example:

```bash
mini-agent "weather forecast for Shanghai" \
  --model-provider ollama \
  --ollama-model qwen3.6:27b \
  --ollama-base-url http://127.0.0.1:11434 \
  --ollama-timeout-seconds 120
```

Generic provider options are also supported for advanced overrides:

```bash
mini-agent "weather forecast for Shanghai" \
  --model-provider ollama \
  --ollama-model qwen3.6:27b \
  --model-option model=deepseek-v4-flash:cloud
```

`--model-option` accepts flat `key=value` pairs only. It can be repeated and has higher priority than provider-specific CLI flags.

`--ollama-*` flags are valid only with `--model-provider ollama`. Other providers should use `--model-option` until provider-specific flags are added.

`timeout_seconds` must be a positive integer. The `--trace` option accepts a filename or subpath under `traces/`; relative paths cannot escape that directory.

Additional providers should implement the same model adapter boundary and return the project runtime's thin wrapper around `AIMessage`.

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

Planning notes and historical implementation records are kept outside this repository in the companion `mini-agent-docs` workspace. Archived code retained in this repository is under `archive/`.

## Tests

```bash
.venv/bin/python -m pytest
```
