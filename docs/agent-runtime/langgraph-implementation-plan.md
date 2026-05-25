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
- Completed: added a new CLI path without changing the default handwritten runtime path.

Recommended CLI shape:

```bash
mini-agent "grep nginx errors" --runtime langgraph
```

Acceptance criteria:

- Completed: one safe mock tool call can execute in tests.
- Completed: the graph loops back after observation in tests.
- Completed: the graph returns a final answer in tests.
- Completed: `max_steps` is enforced in tests.
- Completed: existing handwritten runtime remains the default.

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

### Batch 2: Reuse Full Current Tool Set

Goal: make the LangGraph runtime support the same safe tools as the handwritten runtime.

Scope:

- Register existing DevOps tools.
- Register existing SSH Kubernetes tools.
- Register existing weather tool.
- Keep dangerous tools registered but blocked by permission policy.
- Reuse `ToolRegistry`, `ToolExecutor`, `PermissionGate`, and `ObservationHandler`.

Acceptance criteria:

- `mini-agent "check real cluster pods" --runtime langgraph` works.
- `mini-agent "check k8s status and the age of phzou.core service" --runtime langgraph` works.
- `mini-agent "weather forecast for Shanghai" --runtime langgraph` works.
- Tool results and observations remain visible in trace output.

### Batch 3: Approval Interrupt and Resume

Goal: replace the handwritten runtime's approval stop with LangGraph interrupt/resume.

Scope:

- Add a checkpointer.
- Require or auto-generate `thread_id` for approval-capable runs.
- Implement `approval_interrupt` node.
- Resume with `Command(resume=...)`.
- Add CLI options for approval and rejection resume.

Possible CLI shape:

```bash
mini-agent "apply deployment fix" --runtime langgraph --thread-id demo-1
mini-agent --runtime langgraph --thread-id demo-1 --resume-approval true
mini-agent --runtime langgraph --thread-id demo-1 --resume-approval false
```

Acceptance criteria:

- Dangerous tool call pauses with a structured approval payload.
- State is checkpointed.
- Resume with approval continues execution.
- Resume with rejection ends cleanly.
- Tool execution does not happen before approval.

### Batch 4: Streaming and Trace Comparison

Goal: compare LangGraph runtime events with current `ProgressReporter` and `TraceLogger`.

Scope:

- Use graph streaming for `updates`, `values`, and `custom` events.
- Keep JSONL trace as domain-specific audit log.
- Add custom stream events for harness-level milestones if needed.
- Document which progress events are provided by LangGraph and which remain custom.

Acceptance criteria:

- Terminal output can show graph node progress.
- JSONL trace still records model response, tool call, permission decision, tool result, observation, and final answer.
- A short comparison is added to this document or a follow-up trace document.

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
- Do not change default CLI runtime until the LangGraph version reaches feature parity for current demos.
- Do not add MCP, A2A, self-evolving behavior, complex memory, or model routing during Phase 2 baseline work.
- Do not use arbitrary SSH execution as a shortcut.
- Do not hide permission checks inside tools without an explicit graph-level decision.
- Do not make `ToolNode` the first implementation target.
- Keep JSONL trace until a better audit log exists.

## Next Step

Start with Batch 2.

Batch 0 and Batch 1 are complete. Batch 2 should verify the LangGraph runtime with the full current tool set, including SSH Kubernetes and weather tools, while keeping the default runtime unchanged.

## References

- LangGraph interrupts: <https://docs.langchain.com/oss/python/langgraph/interrupts>
- LangGraph streaming: <https://docs.langchain.com/oss/python/langgraph/streaming>
- LangGraph persistence: <https://docs.langchain.com/oss/python/langgraph/persistence>
- LangGraph ToolNode reference: <https://reference.langchain.com/python/langgraph/agents/#langgraph.prebuilt.tool_node.ToolNode>
