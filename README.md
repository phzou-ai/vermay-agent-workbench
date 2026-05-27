# Mini Agent Workbench

Mini Agent Workbench is a Python project for validating and practicing agent runtime patterns in concrete command-line workflows.

The current default runtime is LangGraph. The project keeps the core harness boundaries explicit so agent behavior can be inspected, tested, and extended without hiding tool execution, permission checks, or observations inside a single opaque node.

Current focus:

- LangGraph orchestration.
- Tool calling through an explicit registry and executor.
- Permission control before dangerous operations.
- Approval interrupt and resume.
- SSH-backed read-only Kubernetes inspection.
- External read-only data tools.
- Human-readable progress output.
- JSONL audit traces.

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
mini-agent "check cluster status"
mini-agent "check real cluster pods"
mini-agent "grep nginx errors"
mini-agent "weather forecast for Shanghai"
```

The LangGraph runtime is the default:

```bash
mini-agent "grep nginx errors"
```

The compact handwritten runtime remains available:

```bash
mini-agent "grep nginx errors" --runtime handwritten
```

## Ollama Configuration

Default model configuration is read from `.env`, then overridden by `.env.local`, `.env.dev.local`, shell environment variables, and finally CLI flags.

```bash
MINI_AGENT_OLLAMA_MODEL=deepseek-v4-flash:cloud
MINI_AGENT_OLLAMA_BASE_URL=http://127.0.0.1:11434
MINI_AGENT_OLLAMA_TIMEOUT_SECONDS=120
```

Example CLI override:

```bash
mini-agent "grep nginx errors" \
  --ollama-model qwen3.6:27b \
  --ollama-base-url http://127.0.0.1:11434 \
  --ollama-timeout-seconds 120
```

The Ollama adapter uses `/api/chat` and expects a JSON action protocol:

```json
{"action":"final","content":"..."}
```

or:

```json
{"action":"tool_call","name":"tool_name","arguments":{}}
```

## SSH Kubernetes Configuration

Real cluster inspection is available through allowlisted read-only SSH Kubernetes tools.

Local configuration should be placed in `.env.local` or exported in the shell:

```bash
MINI_AGENT_SSH_TARGET=user@example-host
MINI_AGENT_SSH_PORT=22
MINI_AGENT_SSH_IDENTITY_FILE=~/.ssh/example_ed25519
MINI_AGENT_SSH_KNOWN_HOSTS_FILE=~/.ssh/known_hosts
```

The SSH client always uses:

```text
StrictHostKeyChecking=yes
UpdateHostKeys=yes
```

Supported read-only tools:

- `ssh_kubectl_get`
- `ssh_kubectl_describe`

Supported operations:

- `kubectl get pods|services|deployments|nodes|namespaces|events`
- `kubectl describe pod|service|deployment|node`

## Approval Resume

Dangerous tools are interrupted before execution and require explicit resume:

```bash
mini-agent "apply deployment fix" --thread-id approval-session
mini-agent --thread-id approval-session --resume-approval false --approval-reason "not allowed"
mini-agent --thread-id approval-session --resume-approval true --approval-reason "approved"
```

For an interactive terminal flow in the same process:

```bash
mini-agent "apply deployment fix" --interactive-approval
```

Interactive approval asks at most once per run by default. If the model requests another dangerous tool after approval, the run stops instead of repeatedly prompting.

The default progress output is an indented agent transcript written to stderr.

Checkpoint data is stored locally in:

```text
traces/langgraph_checkpoints.sqlite
```

## Observability

Progress output is written to stderr by default.

```bash
mini-agent "check real cluster pods" --no-progress
```

LangGraph stream inspection is optional:

```bash
mini-agent "grep nginx errors" --graph-stream
mini-agent "grep nginx errors" --graph-stream-mode updates,custom,debug
mini-agent "grep nginx errors" --graph-stream-mode updates --graph-stream-mode values --no-progress
```

JSONL traces are written to:

```text
traces/*.jsonl
```

## Project Structure

```text
mini_agent/
  main.py
  context_builder.py
  tool_registry.py
  tool_executor.py
  permission.py
  observation.py
  progress.py
  trace.py
  model_clients/
  tools/
  infra/

mini_agent_langgraph/
  state.py
  graph.py
  nodes.py
  routing.py
  runner.py
  streaming.py

docs/
  README.md
  overview.md
  modules.md
  operations.md
```

## Documentation

Stable project documentation is under [docs/README.md](docs/README.md).

Planning notes and historical implementation records are kept outside this repository in the companion `mini-agent-docs` workspace.

## Tests

```bash
.venv/bin/python -m pytest
```
