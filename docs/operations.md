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

The CLI uses the LangGraph runtime:

```bash
mini-agent "grep nginx errors"
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

In an interactive terminal, the default command prompts for approval in the same process:

```bash
mini-agent "run a dangerous operation" --thread-id approval-session
```

In non-interactive environments, the command returns a manual resume instruction. Manual resume remains available:

```bash
mini-agent --thread-id approval-session --resume-approval false --approval-reason "not allowed"
mini-agent --thread-id approval-session --resume-approval true --approval-reason "approved"
```

Interactive approval asks at most once per run by default. If the model requests another dangerous tool after approval, the run stops instead of repeatedly prompting.

The default progress output is an indented agent transcript written to stderr.

Detailed interrupt, checkpoint, and resume mechanics are documented in [langgraph-interrupt-resume.md](langgraph-interrupt-resume.md).

Checkpoint data is stored locally:

```text
traces/langgraph_checkpoints.sqlite
```

## Observability

The CLI has two terminal-facing reporters.

`ProgressReporter` is enabled by default and writes a compact harness transcript to stderr. It is intended for normal CLI use and shows each agent loop as readable event blocks: context build, model call, tool call, permission check, tool result, observation, and final answer.

`GraphStreamReporter` is disabled by default. It is enabled only with `--graph-stream` or `--graph-stream-mode`, and is intended for inspecting LangGraph runtime stream chunks such as `updates`, `custom`, `values`, and `debug`. Enabling graph stream inspection suppresses the default progress transcript so graph-level events and harness-level events do not interleave.

Disable progress output:

```bash
mini-agent "check real cluster pods" --no-progress
```

Enable LangGraph stream inspection:

```bash
mini-agent "grep nginx errors" --graph-stream
mini-agent "grep nginx errors" --graph-stream-mode updates,custom,debug
```

Machine-readable traces are written to:

```text
traces/*.jsonl
```

## Reporter Policy

The project keeps three observability outputs with separate responsibilities.

`ProgressReporter` is the default human-facing CLI transcript. It should stay concise and describe harness-level behavior. It uses `loop N` in terminal output because the value represents one agent decision loop, not a LangGraph node step.

`GraphStreamReporter` is a debug view over LangGraph stream chunks. It should expose graph-level runtime information only when explicitly requested with `--graph-stream` or `--graph-stream-mode`.

`TraceLogger` is the durable machine-readable audit log. It can store fuller payloads than terminal output, including tool results, observations, permission decisions, and raw model responses.

The current state and trace schema still use the field name `step`. In this codebase, `step` currently means agent loop iteration. Future code should prefer `loop_index` for new internal fields that represent this concept.

Do not merge these outputs into one reporter:

- terminal progress optimizes for scanability
- graph stream optimizes for graph runtime inspection
- JSONL trace optimizes for replay, audit, and later evaluation

## Tests

```bash
.venv/bin/python -m pytest
```
