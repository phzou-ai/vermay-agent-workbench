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

## Evaluation Replay

Replay evaluates a recorded trace or scenario without executing live tools.

```bash
mini-agent eval replay --trace traces/latest.jsonl
mini-agent eval replay --scenario evals/scenarios/weather.json
mini-agent eval list-runs
```

Run metadata is stored in `data/agent.sqlite`. Full reports are written to `data/eval_runs/`.

## MCP Tools

MCP client configuration lives in `config/mcp_servers.json`.

List configured MCP tools:

```bash
mini-agent mcp list-tools
```

Discovered MCP tools are wrapped as LangChain `StructuredTool` instances. MCP tools require approval by default unless the server or tool is marked read-only in config.

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
