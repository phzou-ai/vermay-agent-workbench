# Mini Agent Workbench

Mini Agent Workbench is a Python CLI application for running a LangGraph-based agent with visible harness behavior: context construction, model calls, tool execution, permission checks, approval interrupts, memory, skills, evaluation replay, and MCP tool integration.

The default runtime uses LangGraph with LangChain standard message and tool types, including `AIMessage.tool_calls`, `ToolMessage`, `ToolNode`, and `add_messages`.

## Features

- LangGraph runtime with ToolNode-backed tool execution.
- Built-in tools for weather, sample DevOps data, and read-only Kubernetes inspection.
- Permission gate for dangerous tools.
- Interactive approval and durable resume with SQLite checkpoints.
- Explicit memory management.
- Markdown-based skills.
- Trace and scenario replay for evaluation.
- Ollama, OpenAI-compatible, and rule-based model routing adapters.
- MCP client tool discovery from local configuration.
- Local FastAPI server for agent session lifecycle.

## Install

```bash
cd <repo-root>
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Quick Start

```bash
mini-agent "weather forecast for Shanghai"
```

The CLI prints a compact progress transcript to stderr and the final answer to stdout.

Disable progress output:

```bash
mini-agent "weather forecast for Shanghai" --no-progress
```

## API Server

Start the local API server:

```bash
mini-agent serve
```

Defaults:

```text
host: 127.0.0.1
port: 8000
```

Override host or port:

```bash
mini-agent serve --host 127.0.0.1 --port 9000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Start a session:

```bash
curl -X POST http://127.0.0.1:8000/sessions \
  -H 'Content-Type: application/json' \
  -d '{"input":"weather forecast for Shanghai"}'
```

Inspect a session:

```bash
curl http://127.0.0.1:8000/sessions/<thread-id>
```

Resume an approval interrupt:

```bash
curl -X POST http://127.0.0.1:8000/sessions/<thread-id>/resume \
  -H 'Content-Type: application/json' \
  -d '{"approved":true,"reason":"approved by operator"}'
```

The API is local-only by default and does not add authentication. Bind it carefully if exposing it outside the local machine.

## Model Configuration

The runtime uses a model provider adapter. Supported providers are:

- `ollama`
- `openai_compatible`
- `router`

### Ollama

Ollama is the default provider.

```bash
mini-agent "weather forecast for Shanghai" \
  --model-provider ollama \
  --ollama-model deepseek-v4-flash:cloud \
  --ollama-base-url http://127.0.0.1:11434 \
  --ollama-timeout-seconds 120
```

Environment variables are also supported:

```bash
MINI_AGENT_OLLAMA_MODEL=deepseek-v4-flash:cloud
MINI_AGENT_OLLAMA_BASE_URL=http://127.0.0.1:11434
MINI_AGENT_OLLAMA_TIMEOUT_SECONDS=120
```

The project loads `.env`, `.env.local`, `.env.dev.local`, shell environment variables, and then CLI overrides.

### OpenAI-Compatible

Use this provider for OpenAI-style `/chat/completions` endpoints, including vLLM-compatible services.

```bash
mini-agent "weather forecast for Shanghai" \
  --model-provider openai_compatible \
  --model-option model=qwen \
  --model-option base_url=http://localhost:8000/v1
```

Optional authentication can be passed through an environment variable name:

```bash
mini-agent "weather forecast for Shanghai" \
  --model-provider openai_compatible \
  --model-option model=qwen \
  --model-option base_url=https://api.example.com/v1 \
  --model-option api_key_env=OPENAI_API_KEY
```

### Router

The router provider selects a model profile from `config/model_profiles.json`.

```bash
mini-agent "check k8s status" \
  --model-provider router \
  --model-option route_config=config/model_profiles.json
```

`--model-option` accepts repeatable flat `key=value` pairs.

## Approval

Dangerous tools pause the graph and require approval.

In an interactive terminal, approval is prompted automatically:

```bash
mini-agent "apply this kubernetes manifest: ..."
```

Manual resume is available for durable workflows:

```bash
mini-agent --thread-id <thread-id> --resume-approval true --approval-reason "approved by operator"
```

LangGraph checkpoints are stored under `data/checkpoints/`.

## Memory

Memory is written explicitly by command. Enabled memory can be injected into later runs when it matches the request.

```bash
mini-agent memory add "Prefer read-only Kubernetes inspection first." --tag k8s --tag preference
mini-agent memory list
mini-agent memory disable 1
```

Memory metadata is stored in `data/agent.sqlite`.

## Skills

Skills are markdown files under `skills/` with front matter:

```markdown
---
name: kubernetes-readonly-debug
description: Read-only Kubernetes status inspection.
triggers: k8s, kubernetes, pods, services
version: 0.1.0
---

Prefer read-only inspection before proposing a fix.
```

Common commands:

```bash
mini-agent skills list
mini-agent skills show kubernetes-readonly-debug
mini-agent skills propose-from-trace --trace traces/latest.jsonl
mini-agent skills approve <proposal-id>
```

Approved skills live in `skills/`. Generated proposals live in `data/skill_proposals/`.

## Offline Evaluation Replay

Replay evaluates a recorded trace or scenario without executing a live model or live tools.

```bash
mini-agent eval replay --trace traces/latest.jsonl
mini-agent eval replay --scenario evals/scenarios/weather.json
mini-agent eval list-runs
```

Run metadata is stored in `data/agent.sqlite`. Full reports are written to `data/eval_runs/`.

## MCP Tools, Resources, and Prompts

MCP client configuration lives in `config/mcp_servers.json`.

List configured MCP servers and capabilities:

```bash
mini-agent mcp list-servers
mini-agent mcp list-tools
mini-agent mcp list-tools --server k8s
mini-agent mcp list-resources --server k8s
mini-agent mcp list-prompts --server k8s
```

Configured MCP servers are inactive by default during agent runs. Select a server explicitly:

```bash
mini-agent "check k8s status" --mcp-server k8s
mini-agent "check service status" --mcp-server k8s --mcp-resource k8s://cluster/services
mini-agent "debug service health" --mcp-server k8s --mcp-prompt service-health-check
```

Selected MCP tools are wrapped as LangChain `StructuredTool` instances with namespaced model-facing names such as `mcp__k8s__kubectl_get`. MCP tools require approval by default unless the server or tool is marked read-only in config.

Selected MCP prompts and resources are read once at run start. Prompts are injected as bounded external workflow guidance; resources are injected as bounded external data. When multiple MCP servers are selected, use qualified forms such as `--mcp-prompt k8s:service-health-check` and `--mcp-resource k8s:k8s://cluster/services`.

## Local Files

Tracked examples:

```text
config/model_profiles.json
config/mcp_servers.json
evals/scenarios/weather.json
skills/kubernetes-readonly-debug.md
```

Generated local state:

```text
data/agent.sqlite
data/checkpoints/*.sqlite
data/eval_runs/*.json
data/skill_proposals/*.md
traces/*.jsonl
```

Generated local state is ignored by Git.

## Documentation

Project documentation is under [docs/README.md](docs/README.md).

## Tests

```bash
.venv/bin/python -m pytest
```
