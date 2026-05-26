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
mini-agent "check cluster status"
mini-agent "check real cluster pods"
mini-agent "grep nginx errors"
mini-agent "weather forecast for Shanghai"
```

The default runtime is LangGraph:

```bash
mini-agent "grep nginx errors"
```

The handwritten runtime remains available:

```bash
mini-agent "grep nginx errors" --runtime handwritten
```

## Model Configuration

Default Ollama configuration is read from `.env` and can be overridden by `.env.local`, `.env.dev.local`, shell environment variables, or CLI flags.

```bash
MINI_AGENT_OLLAMA_MODEL=deepseek-v4-flash:cloud
MINI_AGENT_OLLAMA_BASE_URL=http://127.0.0.1:11434
MINI_AGENT_OLLAMA_TIMEOUT_SECONDS=120
```

CLI override example:

```bash
mini-agent "grep nginx errors" \
  --ollama-model qwen3.6:27b \
  --ollama-base-url http://127.0.0.1:11434 \
  --ollama-timeout-seconds 120
```

## SSH Kubernetes Configuration

Local SSH configuration should be placed in `.env.local` or exported in the shell.

```bash
MINI_AGENT_SSH_TARGET=user@example-host
MINI_AGENT_SSH_PORT=22
MINI_AGENT_SSH_IDENTITY_FILE=~/.ssh/example_ed25519
MINI_AGENT_SSH_KNOWN_HOSTS_FILE=~/.ssh/known_hosts
```

SSH host key checking is always enabled:

```text
StrictHostKeyChecking=yes
UpdateHostKeys=yes
```

Read-only Kubernetes tools:

- `ssh_kubectl_get`
- `ssh_kubectl_describe`

Supported read operations:

- `kubectl get pods|services|deployments|nodes|namespaces|events`
- `kubectl describe pod|service|deployment|node`

## Approval Resume

Dangerous tools require approval and pause the graph through LangGraph interrupt/resume.

```bash
mini-agent "apply deployment fix" --thread-id approval-session
mini-agent --thread-id approval-session --resume-approval false --approval-reason "not allowed"
mini-agent --thread-id approval-session --resume-approval true --approval-reason "approved"
```

Checkpoint data is stored locally:

```text
traces/langgraph_checkpoints.sqlite
```

## Observability

Human-readable progress is enabled by default and written to stderr.

Disable progress output:

```bash
mini-agent "check real cluster pods" --no-progress
```

Enable LangGraph stream inspection:

```bash
mini-agent "grep nginx errors" --graph-stream
mini-agent "grep nginx errors" --graph-stream-mode updates,custom,debug
mini-agent "grep nginx errors" --graph-stream-mode updates --graph-stream-mode values --no-progress
```

Machine-readable traces are written to:

```text
traces/*.jsonl
```

## Tests

```bash
.venv/bin/python -m pytest
```
