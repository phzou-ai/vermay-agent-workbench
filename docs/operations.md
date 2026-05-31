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

## Model Configuration

The runtime builds model adapters through a provider factory. The current provider is `ollama`.

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
