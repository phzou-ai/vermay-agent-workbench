# LangGraph Implementation Plan

## Objective

This plan defines the Phase 2 implementation path for Mini Agent Workbench.

The goal is to build a LangGraph implementation that reproduces the current handwritten runtime behavior, then use it as the main path for checkpointing, human approval resume, streaming, and later agent engineering topics.

The handwritten runtime remains in the repository as a Phase 1 harness reference. It should not be deleted or aggressively refactored during the LangGraph baseline work.

## Evaluation of the Proposed Direction

The proposed direction is correct at the architectural level:

- The handwritten runtime has already served its learning purpose.
- The current gap is graph orchestration, checkpoint/resume, interrupt, and streaming.
- These gaps map directly to LangGraph strengths.
- A parallel implementation is lower risk than a direct migration.

The plan needs two important adjustments.

First, Phase 2 should not immediately migrate every current capability. It should reproduce behavior in small batches and keep the handwritten runtime stable while the graph version matures.

Second, the first LangGraph version should use a custom tool execution node instead of immediately adopting the prebuilt `ToolNode`. The current runtime uses a custom JSON action protocol:

```json
{"action":"tool_call","name":"ssh_kubectl_get","arguments":{"resource":"pods","namespace":"all"}}
```

LangGraph `ToolNode` can support several input shapes, including direct tool calls, but the first goal is to preserve current harness semantics: `ToolRegistry`, `PermissionGate`, `ToolExecutor`, and `ObservationHandler` should remain visible. `ToolNode` should be evaluated after the custom graph baseline is working.

Reference points from current LangGraph documentation:

- Interrupts pause graph execution, persist state through a checkpointer, and resume with `Command(resume=...)` using the same `thread_id`.
- Streaming supports runtime event views such as `updates`, `values`, `messages`, `custom`, `checkpoints`, `tasks`, and `debug`.
- `ToolNode` supports graph state, message lists, and direct tool call inputs, but standard routing still expects conventional tool-call messages.

## Current Baseline to Preserve

The LangGraph version must reproduce the following handwritten runtime behavior before new capabilities are added:

1. build context from user input, memory, skills, and observations
2. call the Ollama model adapter
3. parse final answer or tool call from the custom JSON action protocol
4. check permission before tool execution
5. execute safe tools through the existing `ToolExecutor`
6. convert `ToolResult` into `Observation`
7. rebuild context with prior observations
8. stop on final answer, approval requirement, or `max_steps`
9. emit readable progress events and durable JSONL trace events

The initial LangGraph work should not change existing CLI behavior for `mini-agent`.

## Target Architecture

Keep the current handwritten runtime:

```text
mini_agent/runtime.py
```

Add a parallel top-level LangGraph package:

```text
mini_agent/
  # Phase 1 handwritten runtime and shared harness modules.
  runtime.py
  context_builder.py
  tool_registry.py
  tool_executor.py
  permission.py
  observation.py
  trace.py
  ...

mini_agent_langgraph/
  # Phase 2 LangGraph orchestration runtime.
  __init__.py
  state.py
  graph.py
  nodes.py
  routing.py
  adapters.py
  runner.py
```

Suggested responsibilities:

- `state.py`: typed graph state definition.
- `graph.py`: graph construction and compilation.
- `nodes.py`: node functions that call existing harness modules.
- `routing.py`: conditional edge functions.
- `adapters.py`: conversions between existing project types and LangGraph-friendly state.
- `runner.py`: CLI-facing wrapper for invoking or streaming the graph.

The existing tools, model client, permission policy, observation handler, and trace logger should be reused from `mini_agent`.

This package split is intentional:

- `mini_agent` keeps a clear meaning as the Phase 1 handwritten harness baseline.
- `mini_agent_langgraph` represents a parallel Phase 2 orchestration implementation.
- Both runtimes can be compared without hiding one inside the other.
- Shared harness modules can still be imported from `mini_agent`; code should not be duplicated.
- A separate common package should not be introduced yet. If LangGraph becomes the main path later, shared modules can be extracted only when there is a concrete maintenance need.

The package name should use lowercase snake case:

```text
mini_agent_langgraph
```

Avoid mixed-case package names such as `mini_agent_langGraph`.

## State Design

Start with a compact state.

```python
class AgentState(TypedDict):
    user_input: str
    messages: list[dict]
    observations: list[dict]
    parsed_response: dict | None
    tool_call: dict | None
    permission_decision: dict | None
    tool_result: dict | None
    observation: dict | None
    final_answer: str | None
    step: int
    max_steps: int
    errors: list[dict]
```

Keep `messages` and `observations` explicit because they are central to the current harness learning goal.

Do not introduce long-term memory, skills retrieval, or model routing into the initial state. Add those only after the baseline graph matches current behavior.

## Graph Shape

The first full graph should expose harness steps as separate nodes:

```text
START
  -> build_context
  -> call_model
  -> route_response
       -> final: END
       -> tool_call: check_permission
  -> route_permission
       -> approval_required: approval_interrupt
       -> denied: reject_tool
       -> allowed: execute_tool
  -> handle_observation
  -> increment_step
  -> route_step_limit
       -> continue: build_context
       -> stop: END
```

This graph is more verbose than a standard ReAct graph, but it is the right shape for this repository because it keeps harness mechanics visible.

## Implementation Batches

### Batch 0: Freeze Handwritten Baseline

Status: Completed.

Goal: protect current behavior before LangGraph work begins.

Scope:

- Completed: minimal tests for model response parsing.
- Completed: minimal tests for permission decisions.
- Completed: minimal tests for tool registry behavior.
- Completed: minimal tests for tool executor failure handling.
- Completed: minimal tests for SSH Kubernetes allowlist and command construction.

Acceptance criteria:

- Completed: existing CLI path remains unchanged.
- Covered by tests: dangerous tool requests still stop at approval.
- Completed: tests run locally without requiring live SSH or live weather network calls.
- Manual smoke test remains optional for live Ollama, SSH, and weather scenarios.

Notes:

- Use mocks or direct function calls for SSH and weather tests.
- Do not refactor the runtime heavily during this batch.
- Test command:

```bash
.venv/bin/python -m pytest
```

Batch 0 added one small parser compatibility improvement: model JSON wrapped in a markdown fenced code block is now parsed as JSON instead of being treated as plain final text.

### Batch 1: Minimal LangGraph Runtime Skeleton

Status: Completed.

Goal: create a graph runtime that can run one safe mock tool loop.

Scope:

- Completed: added `langgraph` dependency.
- Completed: created `mini_agent_langgraph/`.
- Completed: defined `AgentState`.
- Completed: implemented `build_context`, `call_model`, `check_permission`, `execute_tool`, `handle_observation`, and `increment_step` nodes.
- Completed: implemented routing functions for response, permission, and step limit.
- Completed: added a new CLI path. The CLI default was later switched to LangGraph after Batch 1 stabilization.

Recommended CLI shape:

```bash
mini-agent "grep nginx errors" --runtime langgraph
```

Acceptance criteria:

- Completed: one safe mock tool call can execute in tests.
- Completed: the graph loops back after observation in tests.
- Completed: the graph returns a final answer in tests.
- Completed: `max_steps` is enforced in tests.
- Superseded: existing handwritten runtime no longer remains the default. It is still available through `--runtime handwritten`.

Current implementation files:

```text
mini_agent_langgraph/
  __init__.py
  state.py
  graph.py
  nodes.py
  routing.py
  adapters.py
  runner.py
```

Test command:

```bash
.venv/bin/python -m pytest tests/test_langgraph_runtime.py
```

Temporary progress bridge:

- Added after Batch 1 to make LangGraph runs readable before the formal Batch 4 streaming work.
- LangGraph nodes now call the existing `ProgressReporter` for context build, model call, model response, tool call, permission, tool execution, tool result, observation, final answer, and approval required events.
- This is not a replacement for LangGraph streaming. Batch 4 should still compare graph stream modes with the project JSONL trace and progress reporter.

### Batch 2: Reuse Full Current Tool Set

Status: Completed.

Goal: make the LangGraph runtime support the same safe tools as the handwritten runtime.

Scope:

- Completed: register existing DevOps tools.
- Completed: register existing SSH Kubernetes tools.
- Completed: register existing weather tool.
- Completed: keep dangerous tools registered but blocked by permission policy.
- Completed: reuse `ToolRegistry`, `ToolExecutor`, `PermissionGate`, and `ObservationHandler`.

Acceptance criteria:

- Completed: `mini-agent "check real cluster pods"` works with the default LangGraph runtime.
- Completed: `mini-agent "weather forecast for Shanghai"` works with the default LangGraph runtime.
- Completed: mock DevOps tools work with the default LangGraph runtime.
- Completed: dangerous tool requests remain blocked before execution.
- Completed: tool results and observations remain visible in progress output and JSONL trace.

Test coverage:

```bash
.venv/bin/python -m pytest tests/test_langgraph_tool_parity.py
```

Smoke commands run:

```bash
mini-agent "grep nginx errors" --max-steps 3 --no-progress
mini-agent "weather forecast for Shanghai" --max-steps 3 --no-progress
mini-agent "check real cluster pods" --max-steps 3 --no-progress
```

### Batch 3: Approval Interrupt and Resume

Status: Completed.

Goal: replace the handwritten runtime's approval stop with LangGraph interrupt/resume.

Scope:

- Completed: added SQLite checkpointer for CLI persistence.
- Completed: added `thread_id` support; runs auto-generate a thread id when none is provided.
- Completed: implemented approval interrupt in the `approval_required` node.
- Completed: resume with `Command(resume=...)`.
- Completed: added CLI options for approval and rejection resume.

Possible CLI shape:

```bash
mini-agent "apply deployment fix" --runtime langgraph --thread-id demo-1
mini-agent --runtime langgraph --thread-id demo-1 --resume-approval true
mini-agent --runtime langgraph --thread-id demo-1 --resume-approval false
```

Acceptance criteria:

- Completed: dangerous tool call pauses with a structured approval payload.
- Completed: state is checkpointed in `traces/langgraph_checkpoints.sqlite`.
- Completed: resume with approval continues execution.
- Completed: resume with rejection ends cleanly.
- Completed: tool execution does not happen before approval.

Implemented CLI shape:

```bash
mini-agent "apply deployment fix" --thread-id demo-1
mini-agent --thread-id demo-1 --resume-approval true --approval-reason "approved"
mini-agent --thread-id demo-1 --resume-approval false --approval-reason "not allowed"
```

Test coverage:

```bash
.venv/bin/python -m pytest tests/test_langgraph_runtime.py
```

### Batch 4: Streaming and Trace Comparison

Goal: compare LangGraph runtime events with current `ProgressReporter` and `TraceLogger`.

Status: completed.

Scope:

- Use graph streaming for `updates`, `values`, `debug`, and `custom` events.
- Keep JSONL trace as domain-specific audit log.
- Add custom stream events for harness-level milestones.
- Document which progress events are provided by LangGraph and which remain custom.

Implementation:

- Added `mini_agent_langgraph/streaming.py`.
- Added CLI options:
  - `--graph-stream`
  - `--graph-stream-mode`
- `--graph-stream` uses `graph.stream(...)` instead of `graph.invoke(...)` for the initial run.
- Default stream modes are `updates,custom`.
- `updates` reports graph node state deltas.
- `values` reports full state snapshots in summarized form.
- `debug` reports LangGraph checkpoint/task events.
- `custom` reports harness-defined events emitted from graph nodes.
- Existing `ProgressReporter` and `TraceLogger` remain in place.

Current comparison:

| Layer | Source | Purpose |
| --- | --- | --- |
| `ProgressReporter` | project harness | Human-readable harness loop view. |
| LangGraph `updates` | graph runtime | Node-level state transition inspection. |
| LangGraph `values` | graph runtime | Full state snapshot inspection. |
| LangGraph `debug` | graph runtime | Checkpoint/task-level runtime events. |
| LangGraph `custom` | project graph nodes | Harness milestone events carried through LangGraph stream. |
| JSONL trace | project harness | Domain-specific audit trail with full tool and observation payloads. |

Acceptance criteria:

- Completed: terminal output can show graph node progress through `--graph-stream`.
- Completed: JSONL trace still records model response, tool call, permission decision, tool result, observation, and final answer.
- Completed: comparison recorded in this section.

Example commands:

```bash
mini-agent "grep nginx errors" --graph-stream
mini-agent "grep nginx errors" --graph-stream-mode updates --graph-stream-mode values --no-progress
mini-agent "grep nginx errors" --graph-stream-mode updates,custom,debug
```

### Batch 5: ToolNode Evaluation

Goal: decide whether the graph should adopt LangGraph `ToolNode`.

Reason for deferral:

- The current runtime uses a custom JSON action protocol instead of standard LangChain `AIMessage.tool_calls`.
- The Phase 2 learning target is to map existing harness semantics into a graph, not to hide tool execution behind a prebuilt node immediately.
- `PermissionGate` must remain explicit before tool execution, especially for dangerous tools.
- `ObservationHandler` is a project-level semantic layer and should remain visible until the graph baseline is understood.
- A custom execution node makes the first comparison against the handwritten runtime more direct.

Scope:

- Add adapter from current parsed tool call to LangGraph direct tool-call format.
- Test prebuilt `ToolNode` with one safe local tool.
- Compare error handling, output shape, traceability, and permission integration.

Acceptance criteria:

- Decision recorded: keep custom tool node, adopt `ToolNode`, or use both for different cases.
- If `ToolNode` is adopted, permission gate must remain explicit before execution.

### Batch 6: Phase 2 Closeout

Goal: decide which runtime becomes the main extension path.

Scope:

- Compare handwritten runtime and LangGraph runtime across:
  - control flow readability
  - checkpoint/resume
  - approval handling
  - trace quality
  - tool extensibility
  - future memory and skills support
- Update `docs/agent-runtime/current-state.md`.
- Mark Phase 1 runtime as frozen if LangGraph becomes the main path.

Acceptance criteria:

- Future work has one recommended main path.
- Deferred work is reclassified into Phase 3 topics: skills, memory, model routing, MCP, A2A, evaluation, self-evolving.

## Dependency Plan

Add LangGraph only when Batch 1 starts.

Expected dependency:

```toml
dependencies = [
  "rich>=13.7",
  "langgraph>=1.0",
]
```

If LangGraph requires additional LangChain packages for `ToolNode` experiments, add them only in Batch 5.

## Testing Plan

Use tests to protect boundaries, not to exhaustively validate model quality.

Priority test groups:

1. model response parser
2. permission policy
3. registry schema generation
4. executor failure normalization
5. SSH Kubernetes allowlist and command construction
6. LangGraph routing functions
7. approval interrupt/resume flow

Network-dependent behavior should be tested through mocks by default.

Live tests for Ollama, SSH, and weather can be kept as manual smoke tests.

## Implementation Rules

- Do not delete the handwritten runtime.
- Keep the LangGraph runtime in top-level `mini_agent_langgraph/`, not inside `mini_agent/`.
- Completed: default CLI runtime has been switched to LangGraph after current safe tool parity was verified. The handwritten runtime remains available through `--runtime handwritten`.
- Do not add MCP, A2A, self-evolving behavior, complex memory, or model routing during Phase 2 baseline work.
- Do not use arbitrary SSH execution as a shortcut.
- Do not hide permission checks inside tools without an explicit graph-level decision.
- Do not make `ToolNode` the first implementation target.
- Keep JSONL trace until a better audit log exists.

## Next Step

Start with Batch 5.

Batch 0 through Batch 4 are complete. Batch 5 should evaluate whether LangGraph `ToolNode` should be adopted, while keeping `PermissionGate` explicit before execution.

## References

- LangGraph interrupts: <https://docs.langchain.com/oss/python/langgraph/interrupts>
- LangGraph streaming: <https://docs.langchain.com/oss/python/langgraph/streaming>
- LangGraph persistence: <https://docs.langchain.com/oss/python/langgraph/persistence>
- LangGraph ToolNode reference: <https://reference.langchain.com/python/langgraph/agents/#langgraph.prebuilt.tool_node.ToolNode>
