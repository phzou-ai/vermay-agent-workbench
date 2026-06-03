# Operations

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

The CLI uses `mini_agent/langgraph_runtime/`. No alternate runtime is exposed through the active CLI.

## API Server

Start the local FastAPI server:

```bash
mini-agent serve
```

Default bind address:

```text
127.0.0.1:8000
```

Use a different port:

```bash
mini-agent serve --host 127.0.0.1 --port 9000
```

Available endpoints:

```text
GET  /health
POST /api/sessions
GET  /api/sessions
GET  /api/sessions/{session_id}
POST /api/sessions/{session_id}/tasks
GET  /api/tasks/{task_id}
GET  /api/tasks/{task_id}/events
GET  /api/tasks/{task_id}/stream
POST /api/tasks/{task_id}/resume
POST /api/tasks/{task_id}/cancel
POST /api/tasks/{task_id}/retry
```

`POST /api/sessions` creates a long-lived session/context. `POST /api/sessions/{session_id}/tasks` starts one agent execution in that session and accepts optional structured MCP selection:

```json
{
  "input": "debug service health",
  "wait": true,
  "mcp": {
    "servers": ["k8s"],
    "prompts": [{"server": "k8s", "name": "service-health-check"}],
    "resources": [{"server": "k8s", "uri": "k8s://cluster/services"}]
  }
}
```

`wait` defaults to `true`. When `wait` is `false`, the API returns quickly with a queued task; use `GET /api/tasks/{task_id}` and `GET /api/tasks/{task_id}/events` to inspect progress and final state.

For live task lifecycle updates, use the SSE endpoint:

```bash
curl -N http://127.0.0.1:8000/api/tasks/<task-id>/stream
```

Cancel a task:

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/<task-id>/cancel \
  -H 'Content-Type: application/json' \
  -d '{"reason":"operator requested"}'
```

Retry a terminal task as a new task:

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/<task-id>/retry \
  -H 'Content-Type: application/json' \
  -d '{"reason":"operator requested retry","wait":false}'
```

Retry creates a new `task_id`, copies the source task input/model/MCP/max-loop settings, and records lineage through `root_task_id`, `retry_of_task_id`, and `attempt`. Completed retry tasks create their own final-answer artifact.

API MCP prompt and resource selections must name a server listed in `mcp.servers`. The selected MCP configuration is stored as task metadata and reused on approval resume.

The server is local-only by default and has no authentication. Keep the default bind address unless an access-control layer is added.

## Local Storage

Runtime metadata and generated artifacts are local by default:

```text
data/agent.sqlite
data/checkpoints/langgraph.sqlite
data/eval_runs/*.json
data/skill_proposals/*.md
traces/*.jsonl
```

The tracked configuration and scenario locations are:

```text
config/models.json
config/mcp_servers.json
evals/scenarios/*.json
skills/*.md
```

## Model Configuration

The runtime selects a configured model from `config/models.json` by default. The config defines a `primary_model` and a map of named model provider configurations.

Ollama model settings live in `config/models.json` under the selected model's `options`.

Use the primary model:

```bash
mini-agent "weather forecast for Beijing"
```

Use another configured model:

```bash
mini-agent "weather forecast for Beijing" --model local_ollama
```

Provider-specific CLI override example:

```bash
mini-agent "weather forecast for Beijing" \
  --model-provider ollama \
  --ollama-model qwen3.6:27b \
  --ollama-base-url http://127.0.0.1:11434 \
  --ollama-timeout-seconds 120
```

Advanced model provider options can be passed as repeated flat `key=value` pairs:

```bash
mini-agent "weather forecast for Beijing" \
  --model-provider ollama \
  --model-option model=deepseek-v4-flash:cloud \
  --model-option timeout_seconds=120
```

`--model-option` has higher priority than provider-specific flags. It is intended as a generic escape hatch for provider options; nested JSON values are not supported.

`--ollama-*` flags are valid only with `--model-provider ollama`. Other providers should use `--model-option` until provider-specific flags are added for them.

`timeout_seconds` must be a positive integer.

The CLI maps configured model selections or provider override flags into `ModelProviderConfig(provider, options)`. Runtime assembly lives in `mini_agent/app_factory.py`; provider-specific model construction lives in `mini_agent/langgraph_runtime/model_factory.py`.

OpenAI-compatible endpoint example:

```bash
mini-agent "weather forecast for Beijing" \
  --model-provider openai_compatible \
  --model-option model=qwen \
  --model-option base_url=http://localhost:8000/v1
```

The OpenAI-compatible adapter uses Chat Completions request semantics: `{base_url}/chat/completions`, Bearer authentication when an API key is configured, standard `tools` with `tool_choice: auto` when tools are present, and standard assistant `tool_calls` plus `role: tool` messages with `tool_call_id` for tool results. When no tools are present, `tools` and `tool_choice` are omitted.

Ollama remains separate and uses the project's JSON action protocol rather than OpenAI tool message formatting.

## Memory

Memory writes are explicit:

```bash
mini-agent memory add "Prefer read-only Kubernetes inspection first." --tag k8s --tag preference
mini-agent memory list
mini-agent memory disable 1
```

Enabled memory is selected by deterministic keyword, tag, and latest-item matching and injected as system context before the user message.

## Skills

Authored skills are markdown files under `skills/` with front matter fields `name`, `description`, `triggers`, and `version`.

```bash
mini-agent skills list
mini-agent skills show kubernetes-readonly-debug
mini-agent skills propose-from-trace --trace traces/latest.jsonl
mini-agent skills approve <proposal-id>
```

Generated skills remain proposals under `data/skill_proposals/` until approved.

## Offline Evaluation Replay

Replay uses recorded trace or scenario data only. It does not execute a live model, live SSH, MCP, or dangerous tools.

```bash
mini-agent eval replay --trace traces/latest.jsonl
mini-agent eval replay --scenario evals/scenarios/weather.json
mini-agent eval list-runs
```

Eval metadata is stored in `data/agent.sqlite`; full reports are written under `data/eval_runs/`.

## MCP Client

MCP client configuration lives in `config/mcp_servers.json`.

```bash
mini-agent mcp list-servers
mini-agent mcp list-tools
mini-agent mcp list-tools --server k8s
mini-agent mcp list-resources --server k8s
mini-agent mcp list-prompts --server k8s
```

Configured MCP servers are inactive during normal agent runs until selected with `--mcp-server`. MCP tools are approval-required by default. A server or individual tool must be explicitly marked read-only in config to bypass approval.

Selected MCP prompts and resources can be injected as bounded context:

```bash
mini-agent "debug service health" --mcp-server k8s --mcp-prompt k8s-service-health-check
mini-agent "debug phzou-core service" --mcp-server k8s --mcp-prompt 'k8s-service-health-check?service=phzou-core&namespace=default'
mini-agent "check service status" --mcp-server k8s --mcp-resource k8s://cluster/services
```

Prompts and resources are read once at run start. Prompts are injected as external workflow guidance before local skills, memory, and resources. Resources are injected as external data after local memory. Prompt arguments use query-string syntax after the prompt name. When multiple MCP servers are selected, use qualified forms such as `--mcp-prompt 'k8s:k8s-service-health-check?service=phzou-core'` and `--mcp-resource k8s:k8s://cluster/services`.

The tracked `k8s` MCP server lives under `examples/mcp_servers/k8s/` and exposes read-only Kubernetes tools, resources, and prompts. It uses the existing SSH/microk8s backend, so live tool/resource reads require the existing `MINI_AGENT_SSH_*` environment configuration. The tracked config starts it with `.venv/bin/python` and applies `timeout_seconds` to MCP discovery, tool calls, resources, and prompts. Update `config/mcp_servers.json` if the project is run from another Python environment.

## Trace Path

`--trace` accepts a filename or relative subpath under `traces/`:

```bash
mini-agent "weather forecast for Beijing" --trace runs/latest.jsonl
```

Absolute paths are allowed for debugging and tests. Relative paths cannot escape `traces/`.

## Approval Resume

Dangerous tools require approval and pause the graph through LangGraph interrupt/resume.

In an interactive terminal, the default command prompts for approval and resumes automatically:

```bash
mini-agent "run a dangerous operation"
```

The CLI runtime stores LangGraph checkpoints in:

```text
data/checkpoints/langgraph.sqlite
```

This makes manual resume durable across CLI processes:

```bash
mini-agent "run a dangerous operation" --thread-id approval-session
mini-agent --thread-id approval-session --resume-approval true --approval-reason "approved by operator"
```

Interactive approval asks at most once per run by default. If the model requests another dangerous tool after approval, the run stops instead of repeatedly prompting.

Detailed interrupt, checkpoint, and resume mechanics are documented in [langgraph-interrupt-resume.md](langgraph-interrupt-resume.md).

## Terminal Progress

`ProgressReporter` is enabled by default and writes a compact harness transcript to stderr. It should stay concise and describe harness-level behavior:

```text
loop 1
  context ...
  model_call ...
  model_decision ...
```

The terminal transcript is for scanability. It is not the durable audit log and should not try to expose full tool payloads.

Disable progress output:

```bash
mini-agent "weather forecast for Beijing" --no-progress
```

## JSONL Traces

Machine-readable traces are written to:

```text
traces/*.jsonl
```

`TraceLogger` is the durable audit log. It can store fuller payloads than terminal output, including tool messages, observations, permission decisions, and raw model responses.

## Tests

```bash
.venv/bin/python -m pytest
```
