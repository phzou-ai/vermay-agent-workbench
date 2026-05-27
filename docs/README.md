# Mini Agent Workbench Documentation

## Scope

This directory contains stable project-facing documentation for Mini Agent Workbench.

The project is positioned as an agent validation and practice workbench. It is intended to provide a concrete runtime for testing agent orchestration, tool execution, approval control, observability, and real-world integration patterns.

## Reading Order

1. [overview.md](overview.md) - project purpose, current capabilities, and operating model.
2. [modules.md](modules.md) - key packages and module responsibilities.
3. [operations.md](operations.md) - CLI usage, runtime options, environment configuration, and traces.
4. [toolnode-evaluation.md](toolnode-evaluation.md) - isolated `ToolNode` compatibility evaluation and current decision.
5. [code-organization-review.md](code-organization-review.md) - current code organization assessment and cleanup order.

## Documentation Boundary

Repository docs should describe the current project and its stable module boundaries.

Historical planning notes, batch implementation records, and broader roadmap material are kept outside this repository in the companion `mini-agent-docs` workspace.
