# Mini Agent Runtime Current State

## Objective

Mini Agent Workbench was created to study and verify agent harness mechanics with a small handwritten runtime.

The current implementation is intended to make the runtime loop explicit:

1. build context
2. call model
3. parse model response
4. execute tool call when requested
5. apply permission checks before execution
6. convert tool result into observation
7. rebuild context with observations
8. repeat until final answer or step limit

The project is now at a natural Phase 1 stopping point. The handwritten implementation has enough functionality to serve as a reference baseline. The next architectural question is whether to reproduce the same workflow with LangGraph while preserving flexibility where custom harness logic remains useful.

## Current State

### Environment

The project has a local Python environment and an editable package setup.

- Python virtual environment: `.venv/`
- Package metadata: `pyproject.toml`
- CLI entry point: `mini-agent`
- Main dependency: `rich`, used for readable terminal traces

Typical command:

```bash
cd /Users/phzou/Documents/Code/AI/agent
source .venv/bin/activate
mini-agent "check real cluster pods"
```

### Runtime Flow

The main loop is implemented in `mini_agent/runtime.py`.

For each step, the runtime:

1. builds messages through `ContextBuilder`
2. sends messages and tool schemas to the model client
3. records the model response
4. returns immediately if the model response is final
5. checks permission when a tool call is requested
6. stops for approval if the tool is dangerous
7. executes safe tools through `ToolExecutor`
8. converts tool output into an `Observation`
9. appends the observation to the next context

`max_steps` defaults to `5`. This is the maximum number of model calls in one run, not the maximum number of tool calls. A run may stop earlier when the model returns a final answer.

### Model Layer

The current model layer has one concrete adapter:

- `mini_agent/model_clients/ollama.py`

The default model is:

```text
deepseek-v4-flash:cloud
```

The adapter talks to the local Ollama HTTP API:

```text
http://127.0.0.1:11434/api/chat
```

The runtime asks the model to use a small JSON action protocol:

```json
{"action":"final","content":"..."}
```

or:

```json
{"action":"tool_call","name":"ssh_kubectl_get","arguments":{"resource":"pods","namespace":"all"}}
```

The parser is intentionally tolerant. If the model returns plain markdown or a JSON object with a `content` field but no recognized action, the response is treated as a final answer. This prevents cloud models from breaking the run when they produce useful prose instead of strict protocol JSON.

### Harness Components

The current runtime separates the harness into small modules:

- `ContextBuilder`: builds system, user, memory, skill, and observation messages.
- `ToolRegistry`: stores `ToolSpec` definitions and exposes model-facing schemas.
- `ToolExecutor`: executes registered tool functions and normalizes failures.
- `PermissionGate`: classifies safe and dangerous tool calls.
- `ObservationHandler`: converts `ToolResult` into model-readable observations.
- `TraceLogger`: writes machine-readable JSONL events.
- `ProgressReporter`: renders a human-readable Rich trace in the terminal.
- `MemoryStore`: provides a minimal file-backed memory placeholder.

This separation is useful for learning because each harness responsibility is visible. The same separation should inform the LangGraph version rather than disappearing into one graph node.

### Tools

The project currently has four tool groups.

Mock DevOps tools:

- `read_file`
- `grep_logs`
- `kubectl_get`

These operate on local demo data in `data/`.

SSH-backed Kubernetes tools:

- `ssh_kubectl_get`
- `ssh_kubectl_describe`

These inspect the real MicroK8s cluster through SSH configuration in `data/ssh_config.json`. They are read-only and allowlisted.

Dangerous placeholder tools:

- `exec_shell`
- `kubectl_apply`
- `delete_resource`

These exist to exercise the permission path. They are marked dangerous and are not executed automatically.

Weather tool:

- `weather_forecast`

This reads forecast data from `wttr.in` and is treated as a safe external read-only tool.

### Real Kubernetes Inspection

The SSH client lives under:

```text
mini_agent/infra/ssh.py
```

Kubernetes-specific tool logic lives under:

```text
mini_agent/tools/devops/remote_kubernetes.py
```

The remote Kubernetes command resolver handles MicroK8s shell environment differences by trying:

1. `kubectl`
2. `microk8s kubectl`
3. `/snap/bin/microk8s kubectl`

The read-only allowlist currently supports:

- `kubectl get pods|services|deployments|nodes|namespaces|events`
- `kubectl describe pod|service|deployment|node`

The runtime does not expose arbitrary SSH command execution.

### Observability

There are two tracing layers.

Human-readable terminal trace:

- rendered by `ProgressReporter`
- shows context build, model call, model response, tool call, permission, tool result, observation, and final answer
- optimized for studying harness behavior during a run

Machine-readable JSONL trace:

- written by `TraceLogger`
- stored in `traces/*.jsonl`
- preserves full event payloads, including complete tool results and observations

The terminal trace is intentionally summarized so it remains readable. Full payload inspection belongs in the JSONL trace.

### Verified Scenarios

The following scenarios are currently supported:

```bash
mini-agent "grep nginx errors"
mini-agent "check real cluster pods"
mini-agent "check k8s status and the age of phzou.core service"
mini-agent "weather forecast for Shanghai today"
mini-agent "apply deployment fix"
```

Expected behavior:

- log and file queries use mock tools when sufficient
- real cluster questions can use SSH-backed Kubernetes tools
- weather questions can use `weather_forecast`
- dangerous operations stop at approval instead of executing

## Decisions

### Handwritten Runtime First

The project started with a handwritten mini runtime to expose harness internals directly. This was the right first step because it made the following mechanics concrete:

- context construction
- tool schema exposure
- model action parsing
- permission gating
- observation injection
- trace events
- loop termination

This implementation should now be treated as a learning baseline, not a framework to expand indefinitely.

### Ollama Adapter Only

The earlier rule-mode fallback was removed. The runtime now depends on the model path for behavior.

This keeps the demo focused on real model-driven tool selection instead of hiding agent behavior behind deterministic shortcuts.

### Direct Ollama HTTP Client

The model adapter uses the local Ollama HTTP API directly rather than the official Python package.

The direct HTTP adapter is useful for learning because request shape, response parsing, error handling, and protocol tolerance are visible in one small file. The official package could be adopted later if the project needs less adapter code or better compatibility with Ollama client conventions.

### Rich Terminal Trace Plus JSONL Trace

Terminal logs are used for human inspection of the harness loop.

JSONL traces are used as durable run records. They are the right place for full payloads that would make terminal output too dense.

### SSH Client Placement

Generic SSH execution belongs in `mini_agent/infra/ssh.py`.

Kubernetes command construction belongs in `mini_agent/tools/devops/remote_kubernetes.py`.

This keeps infrastructure transport separate from domain-specific tools.

### Read-Only Real Cluster Tools

Real Kubernetes tools are intentionally read-only and allowlisted.

This keeps the demo useful against a real cluster while preserving the safety boundary required for harness learning.

### Weather as Safe External Tool

The weather tool was added as a second type of safe read-only tool.

It demonstrates that the harness is not limited to DevOps tools. Tool registration, schema exposure, execution, observation, and tracing are shared across domains.

## Code Quality Evaluation

The current code is adequate for a Phase 1 learning baseline.

Good current boundaries:

- model clients are isolated under `mini_agent/model_clients/`
- transport infrastructure is isolated under `mini_agent/infra/`
- DevOps and weather tools are split by domain
- tool registration is explicit
- permission policy is centralized
- terminal trace and JSONL trace are separate

Areas that should not be over-refactored before LangGraph:

- `MiniAgentRuntime` is still intentionally central; this is useful for reading the loop.
- synchronous execution is acceptable for the current CLI demo.
- memory is intentionally minimal.
- approval currently stops the run instead of implementing resume.

Refactors worth considering after the LangGraph comparison:

- introduce a formal observer interface for terminal progress and JSONL tracing
- add tests for model response parsing
- add tests for permission decisions
- add tests for remote Kubernetes command construction
- add tests for weather result normalization
- make observation summarization configurable per tool
- define richer typed metadata for `ToolResult`

Known risks:

- cloud models may still drift from the requested JSON action protocol
- `wttr.in` availability and response shape are outside project control
- terminal trace formatting is optimized for learning, not production logging
- shell-based SSH command construction needs continued allowlist discipline

## LangGraph Consideration

Switching to LangGraph is appropriate for Phase 2, but it should not replace the handwritten runtime immediately.

The recommended approach is:

1. keep the handwritten runtime as the explicit harness reference
2. implement a second LangGraph workflow that reproduces the same behavior
3. compare what LangGraph provides against what the handwritten runtime made explicit
4. move future expansion to the LangGraph path only after the same baseline behavior works

Suggested LangGraph mapping:

| Current Runtime Concept | LangGraph Equivalent |
| --- | --- |
| `while step <= max_steps` loop | graph edges and conditional edges |
| message list | graph state with message reducer |
| context build | node before model call or part of model node |
| model invocation | model node |
| model response parser | route function or model node output parser |
| tool execution | `ToolNode` or custom tool node |
| permission gate | approval node plus conditional edge |
| approval stop | interrupt/resume flow |
| observations | state updates |
| JSONL trace | custom callbacks or event logging |
| terminal trace | streaming/event observer |
| memory placeholder | checkpointer or external memory node |

The comparison should evaluate:

- whether the graph makes control flow clearer or more indirect
- how checkpoint and resume affect human-in-the-loop design
- how much custom code is still needed for permission and observation handling
- whether tool schemas and tool execution become easier to maintain
- whether tracing becomes more complete or more fragmented
- whether memory and skills are easier to add as nodes

Do not begin MCP, A2A, or self-evolving work before the LangGraph baseline exists.

## Deferred / TODO

Current deferred items:

- LangGraph version of the same workflow.
- Parser tests for strict JSON, plain markdown, malformed JSON, and content-only JSON.
- Unit tests for tool registry, permission gate, and tool executor failure handling.
- Tests for SSH Kubernetes allowlist and command generation.
- Tests for weather response normalization.
- Real human approval resume flow.
- Streaming model output.
- Skill loading, retrieval, and injection.
- Real memory write and retrieval policies.
- Model routing.
- MCP integration.
- A2A integration.
- Evaluation datasets and trajectory evaluation.
- Self-evolving skill proposal workflow.

These items are intentionally deferred because the current milestone is to close Phase 1 and prepare a clean Phase 2 comparison.

## Next Step

Recommended next sequence:

1. Completed: freeze this handwritten runtime as the Phase 1 baseline with minimal tests.
2. Completed: create a parallel `mini_agent_langgraph/` implementation that reproduces the same loop with one safe tool call and one final answer in tests.
3. Add the existing SSH Kubernetes and weather tools to the LangGraph path.
4. Add checkpointing and human-in-the-loop resume.
5. Add streaming and improved tracing.
6. Decide which path becomes the main extension point for memory, skills, model routing, MCP, and evaluation.

The immediate next implementation should verify current tool parity in the LangGraph runtime, not add unrelated capabilities to the handwritten runtime.

The detailed Phase 2 implementation plan is maintained in [langgraph-implementation-plan.md](langgraph-implementation-plan.md).
