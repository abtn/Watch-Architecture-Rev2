# Task protocol

Use this protocol to turn a request into a bounded, verifiable task. Existing
task packet guidance in [`docs/07-codex-task-templates.md`](../07-codex-task-templates.md)
remains applicable.

## Required task elements

A well-formed implementation task should specify, or allow Codex to determine
from authoritative repository sources:

- **Context:** affected subsystem and relevant repository state.
- **Goal:** observable outcome and intended milestone.
- **Scope:** files or behavior in scope, and explicit exclusions.
- **Prerequisites:** earlier milestones, dependencies, credentials, services,
  or human decisions required.
- **Authority and constraints:** applicable instructions, architecture,
  invariants, ADRs, compatibility requirements, and prohibited changes.
- **Acceptance criteria:** measurable behavior or expected repository state.
- **Verification:** documented commands and tests that demonstrate acceptance.
- **Stop conditions:** conflicts, missing authority, decisions, or failures that
  must pause work.

If a necessary detail is missing, Codex may inspect repository sources and
resolve it only when those sources clearly decide it. Otherwise ask the
Operator or stop and report the unresolved item.

## Scoping procedure

1. Classify the request: inspect-only, simulation, documentation, implementation,
   review, or other. Confirm whether edits are allowed.
2. Determine current milestone and prerequisites using
   [`AGENTS.md`](../../AGENTS.md) and [`PLAN.md`](../../PLAN.md).
3. Apply [`CHANGE_MAP.md`](../../CHANGE_MAP.md) to identify authority for
   affected architecture concepts. Read relevant invariants and ADRs; read
   ADR-0026 for Task, Plan, Objective, Trigger, or scheduler changes.
4. Inspect the repository and worktree. Identify existing implementation,
   local changes, related tests, and the smallest affected file set.
5. Define acceptance criteria, verification, and explicit exclusions before
   editing.

## Scope and stop rules

- Implement only the requested slice; do not bundle future milestones,
  speculative features, or unrelated cleanup.
- Do not add a new durable entity, dependency, service, migration, or
  architectural abstraction without a documented need and appropriate scope.
- Do not treat a plan or simulation as authorization to implement.
- Stop if authority is unclear, documents conflict, a prerequisite is absent,
  or a human decision would materially affect architecture, persisted data,
  security, behavior, or toolchain conventions.
- Stop when the requested change cannot satisfy its acceptance criteria
  without expanding scope; report the smallest decision or clarification needed.

The handoff should list changed files, acceptance results, verification
performed, assumptions, and unresolved questions.
