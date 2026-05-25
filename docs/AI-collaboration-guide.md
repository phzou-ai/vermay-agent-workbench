# AI Collaboration Guide

## Purpose

This document defines how to work efficiently with AI coding tools in this repository.

It is written for:

- Codex
- ChatGPT-style coding sessions
- Cursor / Claude Code / similar modern AI coding tools

The goal is not to document AI features. The goal is to define a **repeatable collaboration workflow** so that:

- project context does not drift
- long sessions do not become noisy
- decisions survive across sessions
- AI can continue work from docs instead of relying on fragile chat memory

## Core Idea

Treat AI as:

1. a short-term execution partner
2. a long-term reader of repository documentation

This means:

- chat/session context is useful for the current task
- repository docs are the durable memory

Do **not** rely on a long conversation alone as the source of truth.

## Why This Matters

AI tools usually have the same weaknesses:

- they can lose track in long sessions
- they can overfit to recent messages
- they can repeat already completed work
- they can confuse historical plans with current state

The fix is not “explain more in chat”.

The fix is:

- keep repository docs current
- record decisions explicitly
- start new sessions from docs

## Working Model

Use a two-layer model.

### 1. Session Layer

This is the current conversation.

Use it for:

- implementation
- debugging
- local design tradeoffs
- short-lived iteration

Characteristics:

- fast
- temporary
- easy to get noisy

### 2. Documentation Layer

This lives in the repository.

Use it for:

- current state
- decisions
- constraints
- deferred work
- next-step guidance

Characteristics:

- stable
- reusable
- suitable as AI memory

## Principle: Docs Are External Memory

In this repository, docs should function as:

1. project memory
2. decision log
3. task handoff point
4. navigation map for future sessions

This is especially important when:

- a task spans multiple days
- architecture decisions evolve
- there are many deferred items
- multiple modules are being migrated gradually

## Recommended Documentation Structure

Keep docs organized by domain.

Examples already used in this repository:

- `docs/auth`
- `docs/permission`
- `docs/image-implementation`

This is preferred over one large mixed document.

## Repository-Level Documentation Stack

For this repository, documentation now has two repository-facing layers.

### 1. Stable Reference Layer

Use this for:

- project architecture
- project/module responsibilities
- repository structure
- system entry points
- settled cross-project explanations

Recommended locations:

- `docs/README.md`
- `docs/overview/*`
- `docs/projects/*`

Characteristics:

- low-frequency updates
- should be readable by humans and AI as a project entry point
- should avoid detailed migration history
- should avoid patch-by-patch implementation notes

### 2. Active Development Layer

Use this for:

- current implementation plans
- current state
- deferred items
- next-step guidance
- AI handoff memory

Recommended locations:

- `docs/dev/*` as the physical and logical home
- `docs/dev/auth/*`
- `docs/dev/permission/*`
- `docs/dev/admin-ui/*`
- `docs/dev/app-structure/*`
- other domain folders of the same kind

### Organization rule for Active Development docs

The repository now keeps Active Development domains physically under `docs/dev/*`.

Prefer:

1. making status and next-step guidance accurate first
2. clarifying logical ownership second
3. only introducing deeper subfolders when they reduce confusion instead of creating churn

Do **not** pre-design extra subfolders under `docs/dev/*` too early.

Only add deeper grouping when:

1. multiple active domains have truly stabilized into repeatable categories
2. the current flat development layer becomes hard to scan
3. the added structure clearly reduces confusion instead of adding ceremony

### Rule for syncing the two layers

Do **not** update the Stable Reference layer on every small patch.

Instead:

1. write iterative progress into the Active Development layer first
2. when a milestone or phase is truly settled, sync the resulting stable conclusions upward
3. keep the Stable Reference layer free of implementation noise, patch history, and temporary state drift

### Rule

Each major domain should have:

1. a `README.md`
2. topic-specific documents

The `README.md` should act as:

- entry point
- reading order
- current status summary

## Recommended Document Organization Convention

For this repository, the preferred documentation pattern is:

1. one directory per major domain
2. one `README.md` per domain directory
3. one document per stable topic
4. extra child documents only when a subtask becomes large enough

### What belongs in `README.md`

`README.md` should stay short and act as a navigation layer.

It should contain:

- what this domain covers
- what files should be read first
- current overall position
- current recommended next step

It should **not** become the place where every implementation detail is repeated.

### What belongs in a topic document

A topic document should usually keep its major sections **inside the same file**.

Recommended internal structure:

- Objective
- Current State
- Decisions
- Deferred / TODO
- Next Step

This is preferred over splitting those sections into separate files like:

- `objective.md`
- `current-state.md`
- `decisions.md`
- `todo.md`

### Why we do not split sections into separate files by default

Although splitting looks neat at first, it tends to create these problems:

1. higher reading overhead for both humans and AI
2. more document drift between files
3. weaker connection between state, decision, and next action
4. more maintenance burden without enough payoff

For AI tools, it is usually better to read **one coherent topic document** than to reconstruct meaning from many tiny files.

### When to create a separate subtask document

Create a dedicated document only when the subtask is large enough that it would otherwise make the main document noisy.

Typical signals:

1. the subtask has multiple implementation rounds
2. it has its own design decisions
3. it has its own deferred items
4. it is likely to become a future session entry point
5. it is making the parent plan document harder to scan

Example:

- `05-menu-list-ui-improvements.md`

This is a good separate document because it is a self-contained stream of UI work with its own iterations.

### When to create a nested subfolder

Do this only when a domain grows into multiple substantial subdomains.

Good reasons:

- too many topic files in one directory
- each sub-area already has several documents
- each sub-area benefits from its own `README.md`

Do **not** create nested subfolders only for theoretical neatness.

The default should stay simple:

- domain directory
- domain README
- topic documents

### Final rule

Use this hierarchy by default:

1. `docs/<domain>/README.md`
2. `docs/<domain>/<topic>.md`
3. `docs/<domain>/<subtask>.md` only when necessary

Do **not** make separate files for Objective, Current State, Decisions, Deferred, and Next Step unless there is a very strong reason.

## What Good AI-Facing Docs Should Contain

Avoid writing docs as a chronological diary.

Prefer documents with stable sections such as:

### Objective

- what this domain is trying to achieve

### Current State

- what is already working
- what is already implemented
- what is already decided

### Decisions

- what was chosen
- what was rejected
- why

### Deferred / TODO

- what is known but intentionally postponed
- why it is postponed

### Next Step

- what should be done next
- what should *not* be done next

This structure is much more useful to both humans and AI than a timeline of edits.

## Documentation Rules

### 1. Distinguish status clearly

Every plan document should make it obvious which items are:

- completed
- current
- deferred
- deprecated

If this is unclear, AI will tend to repeat work.

### 2. Record decisions, not only facts

High-value docs include statements like:

- which architecture is the target
- which legacy path should no longer be expanded
- which field semantics are deprecated
- which module should be used as implementation template

These decisions are more important than low-level patch history.

### 3. Always record “what to do next”

A document should help future work continue immediately.

Good:

- “Next priority is subtree delete, then drag-and-drop reorder.”

Bad:

- “Need more work later.”

### 4. Keep docs updated when milestones change

If a deferred item becomes complete, update the doc.

If the real state changes but docs still describe the old state, the docs become harmful.

### 5. Keep state at the right level of detail

Docs should record:

- module-level status
- architecture decisions
- constraints that affect future work
- known deferred items
- next-step guidance

Docs should usually **not** record:

- every small patch
- every temporary experiment
- every debug attempt
- low-value chronological notes

Rule of thumb:

If a detail will materially affect future implementation, keep it.

If it only describes transient execution history, leave it out.

## Document Lifecycle

Not every document should live forever in the same role.

Use these lifecycle states intentionally.

### Active

Use for:

- current implementation plans
- ongoing refactors
- current design documents

Characteristics:

- actively updated
- referenced by new sessions
- should contain accurate `Current State` and `Next Step`

### Stable Reference

Use for:

- settled design rules
- implementation conventions
- project-level patterns

Characteristics:

- updated rarely
- used as reference rather than iteration log

Examples:

- invocation rules
- AI collaboration conventions
- target design documents

### Historical / Archived

Use for:

- old rollout stages
- superseded implementation plans
- temporary migration notes that are no longer current

Characteristics:

- kept for traceability
- should not be the default entry point for new work
- should be clearly marked as historical if still retained

## Old Document Management Convention

When a document is no longer the active source of truth, do **not** immediately delete it by default.

Use the following rule set.

### Default rule: keep, but downgrade

If an old document still has reference value:

- keep the file
- mark it clearly as historical or superseded
- remove it from the default reading path in the domain `README.md`

Suggested status note at the top of the document:

```text
Status: Historical
Superseded by:
- <new-doc>.md

This document is kept only for implementation history reference.
Do not use it as the default entry point for new work.
```

This should be the default handling for old but still meaningful documents.

### When to move documents into an `archive/` folder

Create a domain archive folder only when the number of old documents starts to harm readability.

Recommended pattern:

- `docs/<domain>/archive/`

Move documents there when:

1. there are many old documents in the same domain
2. they are no longer part of normal reading order
3. they still have historical or troubleshooting value

Do **not** create archive folders too early.

Archive folders are useful only when they reduce clutter.

### When deletion is acceptable

Delete an old document only when all of the following are true:

1. it has no meaningful historical value
2. it has no debugging or troubleshooting value
3. it is not referenced elsewhere
4. it is mostly redundant with another document

Typical examples:

- temporary debugging notes
- throwaway scratch drafts
- duplicate intermediary files

### Practical rule for this repository

For this repository, prefer this order:

1. keep the old file and mark it as historical
2. if historical files accumulate, move them into `docs/<domain>/archive/`
3. only delete files that are clearly low-value and replaceable

This keeps the repository understandable without over-designing the archive structure too early.

### When to merge or retire a subtask document

A subtask document should be merged back into a broader plan or retired when:

1. the subtask is fully complete
2. its remaining value is only historical reference
3. keeping it active would duplicate current-state information elsewhere

A subtask document should remain active when:

1. it still has deferred items
2. it is likely to be resumed later
3. it is still the clearest entry point for its topic

## End-of-Iteration Minimum Update Checklist

At the end of a meaningful task iteration, perform at least this minimum documentation check:

1. update `Current State`
2. move completed items out of `Deferred / TODO`
3. update `Next Step`
4. check whether the domain `README.md` summary is still accurate

If the iteration changed architecture or conventions, also update:

5. `Decisions`
6. any cross-domain reference docs affected by the change

This checklist exists to prevent the most common failure mode:

- code was updated
- docs still describe the previous state

## Session Restart Templates

Different kinds of new sessions should start differently.

## A. Continue-Implementation Session

Use this when:

- the design is already decided
- the next coding step is clear

Recommended opening format:

```text
Continue work on permission/menu-list.

Please read:
- docs/dev/permission/README.md
- docs/dev/permission/04-menu-definition-management-plan.md
- docs/dev/permission/05-menu-list-ui-improvements.md

Current state:
- menu-list is usable
- search/filter is done
- expand/collapse is done
- icon preview is done
- dynamic menu registration is already completed

Next task:
1. implement delete whole menu branch
2. drag-and-drop reorder later
```

## B. Analysis / Design Session

Use this when:

- code should not be written immediately
- the next step is to evaluate architecture, product behavior, or tradeoffs

Recommended opening format:

```text
Continue work on the permission system design.

Please read:
- docs/dev/permission/README.md
- docs/dev/permission/01-current-state.md
- docs/dev/permission/02-target-design.md
- docs/dev/permission/03-implementation-plan.md

Current state:
- menu permission pages are usable
- operation permission pages are usable
- API permission remains deferred

This session is for design only.
Do not implement code yet.

Please:
1. analyze the current model
2. identify design gaps
3. propose the next implementation path
```

These two templates should cover most future AI sessions in this repository.

## How To Start a New AI Session

When starting a new session, do not assume the model remembers prior threads.

Instead, provide:

1. the topic
2. the relevant docs to read
3. the current confirmed state
4. the next task

### Recommended session-opening format

Use one of the session restart templates above depending on whether the session is:

- implementation-oriented
- analysis/design-oriented

This is much more efficient than asking AI to “remember where we left off”.

## When To Start a New Session

Start a new session when:

- the current conversation becomes long and repetitive
- multiple design branches were explored and abandoned
- state tracking becomes ambiguous
- the next task is clearly scoped and docs already exist

Do **not** force a single session to carry the whole project.

New sessions are often more efficient than continuing a bloated one.

## Suggested Collaboration Workflow

Use this loop for major tasks.

### Step 1: Define the task boundary

Be explicit about:

- what this iteration will do
- what this iteration will not do

Example:

- do subtree delete
- do not do drag-and-drop reorder yet

### Step 2: Let AI inspect and implement

Use the current session for:

- code reading
- implementation
- validation

### Step 3: Write back to docs

At the end of the iteration, update docs with:

- current state
- decision changes
- deferred items
- next step

### Step 4: Start a fresh session when useful

Use docs as the restart point.

## Preferred Invocation Pattern In This Repo

This repository already uses an important rule documented in:

- `docs/dev/auth/05-nextjs-bff-invocation-rules.md`

Summary:

- `service` layer is the real backend invocation layer
- server pages read from services directly
- server actions handle mutation
- route handlers are for client-side async JSON only

This is a good example of the kind of project-specific rule that should always live in docs, not only in chat.

## What To Avoid

### 1. Do not keep all project memory only in chat

If it matters later, write it into docs.

### 2. Do not let docs become stale

Outdated docs are worse than missing docs.

### 3. Do not mix unrelated domains in one giant file

Keep auth, permission, image pipeline, infra, etc. separate.

### 4. Do not treat TODO as commitment unless priority is stated

A good TODO should say whether it is:

- next priority
- deferred
- optional

### 5. Do not let AI infer hidden decisions repeatedly

If a decision is real, write it down.

Example:

- “Code no longer defines menu hierarchy; ParentId does.”

That kind of sentence saves repeated re-analysis later.

## What Makes AI Collaboration Efficient

The highest-leverage practices are:

1. use docs as long-term memory
2. keep domain docs separated
3. maintain a strong `README.md` in each domain folder
4. write explicit current state and next step
5. start fresh sessions from docs when a topic becomes heavy

## Recommended Team Habit

For every meaningful milestone, ensure the repo contains:

1. the code change
2. the design decision
3. the current state
4. the next step

If all four are present, future AI sessions become much more reliable.

## Repository-Specific Advice

For this repository in particular:

1. keep `docs/auth` focused on auth and BFF
2. keep `docs/permission` focused on permission model and admin pages
3. keep `docs/image-implementation` focused on image routing and rollout
4. when a new domain grows large enough, create a new docs subfolder
5. prefer using the domain `README.md` as the first read in any new session

## Current Recommendation

Continue using docs as the canonical handoff layer between sessions.

The current documentation structure is already moving in the right direction.

The next improvement should be:

- keep document status updated as tasks are completed
- keep each domain README usable as a restart point

That is what will produce the biggest efficiency gain in future AI-assisted work.

## Improvement Backlog For This Guide

The following items are intentionally recorded as **future refinements**, not current mandatory rules.

They should be evaluated during trial usage and only promoted to formal conventions if they prove useful in practice.

### 1. Document Header Status Template

Potential future enhancement:

Define a lightweight standard header block at the top of important docs, for example:

- `Status: Active / Stable Reference / Historical`
- `Domain: auth / permission / image-implementation / ...`
- `Last Reviewed: <date>`
- `Superseded by: <doc>` when applicable

Why this may help:

- AI can classify a document faster
- humans can judge whether a document is still current
- historical documents become easier to distinguish from active ones

Why this is not mandatory yet:

- it adds maintenance overhead
- the current docs are still manageable without a fixed header template
- this should first be validated in real usage

### 2. Cross-Link Convention Between Domains

Potential future enhancement:

Define a clearer rule for when and how one domain doc should reference another.

Typical examples:

- permission docs referencing auth/BFF invocation rules
- image docs referencing auth or infrastructure assumptions
- implementation plans referencing target-design documents

Why this may help:

- reduces duplicated explanations
- makes dependency relationships between domains explicit
- helps AI find the right supporting context faster

Possible future rule shape:

1. reference the other domain doc explicitly when the dependency is real
2. keep the source-of-truth concept in only one place
3. update cross-links when the source-of-truth document changes materially

Why this is not mandatory yet:

- current doc graph is still small enough to navigate manually
- a rigid cross-link policy may be premature before more trial usage

## Trial-Run Policy

The current recommendation is:

1. use this guide as-is for real work
2. observe where collaboration still feels inefficient
3. only then decide whether to formalize:
   - document header templates
   - cross-link rules

This keeps the documentation system practical and avoids over-designing rules before they are proven necessary.
