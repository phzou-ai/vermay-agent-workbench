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
mini-agent "weather forecast for Shanghai"
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
POST /sessions
GET  /sessions/{thread_id}
POST /sessions/{thread_id}/resume
```

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
config/model_profiles.json
config/mcp_servers.json
evals/scenarios/*.json
skills/*.md
```

## Model Configuration

The runtime builds model adapters through a provider factory. Supported providers are `ollama`, `openai_compatible`, and `router`.

Default Ollama configuration is read from `.env` and can be overridden by `.env.local`, `.env.dev.local`, shell environment variables, or CLI flags.

```bash
MINI_AGENT_OLLAMA_MODEL=deepseek-v4-flash:cloud
MINI_AGENT_OLLAMA_BASE_URL=http://127.0.0.1:11434
MINI_AGENT_OLLAMA_TIMEOUT_SECONDS=120
```

Provider-specific CLI override example:

```bash
mini-agent "weather forecast for Shanghai" \
  --model-provider ollama \
  --ollama-model qwen3.6:27b \
  --ollama-base-url http://127.0.0.1:11434 \
  --ollama-timeout-seconds 120
```

Advanced model provider options can be passed as repeated flat `key=value` pairs:

```bash
mini-agent "weather forecast for Shanghai" \
  --model-provider ollama \
  --model-option model=deepseek-v4-flash:cloud \
  --model-option timeout_seconds=120
```

`--model-option` has higher priority than provider-specific flags. It is intended as a generic escape hatch for provider options; nested JSON values are not supported.

`--ollama-*` flags are valid only with `--model-provider ollama`. Other providers should use `--model-option` until provider-specific flags are added for them.

`timeout_seconds` must be a positive integer.

The CLI maps provider flags and generic model options into `ModelProviderConfig(provider, options)`. Runtime assembly lives in `mini_agent/app_factory.py`; provider-specific model construction lives in `mini_agent/langgraph_runtime/model_factory.py`.

OpenAI-compatible endpoint example:

```bash
mini-agent "weather forecast for Shanghai" \
  --model-provider openai_compatible \
  --model-option model=qwen \
  --model-option base_url=http://localhost:8000/v1
```

Rule-router example:

```bash
mini-agent "weather forecast for Shanghai" \
  --model-provider router \
  --model-option route_config=config/model_profiles.json
```

Routing v1 is deterministic and based on prompt keywords, message length, and tool-error presence.

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

Configured MCP servers are inactive during normal agent runs until selected with `--mcp-server`. MCP tools are approval-required by default. A server or individual tool must be explicitly marked read-only in config to bypass approval. Resource and prompt listing is inspection-only until the resource/prompt injection batches are implemented.

## Trace Path

`--trace` accepts a filename or relative subpath under `traces/`:

```bash
mini-agent "weather forecast for Shanghai" --trace runs/latest.jsonl
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
mini-agent "weather forecast for Shanghai" --no-progress
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
