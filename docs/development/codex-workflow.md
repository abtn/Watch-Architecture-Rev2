# Human–Codex workflow

Use this workflow for bounded changes in the Watch repository. The human
Operator owns product and architecture decisions; Codex inspects and executes
the explicitly requested work within repository constraints.

## 1. Interpret the task

- Identify whether the request is inspect-only, a workflow simulation,
  documentation work, implementation, review, or another task.
- Extract the requested outcome, scope, constraints, acceptance criteria, and
  whether file changes are allowed.
- Determine the current milestone from [`PLAN.md`](../../PLAN.md) and
  [`AGENTS.md`](../../AGENTS.md). Do not infer it from older terminology alone.
- If the request is ambiguous in a way that affects scope, architecture, data,
  safety, or acceptance, ask the Operator or stop and report the ambiguity.

## 2. Inspect before planning

- Check the worktree and repository layout before editing; preserve existing
  user changes.
- Read [`AGENTS.md`](../../AGENTS.md), [`CHANGE_MAP.md`](../../CHANGE_MAP.md),
  the relevant part of [`PLAN.md`](../../PLAN.md), and only the applicable
  detailed architecture, invariant, glossary, migration, and ADR documents.
- Search for existing patterns and tests before proposing a new one.
- Separate existing implementation from planned design. Do not assume a
  documented component already exists in code.

## 3. Plan a bounded change

- List the smallest set of files needed and what each change will accomplish.
- State prerequisites, constraints, acceptance criteria, verification
  commands, and stop conditions.
- Identify assumptions explicitly; distinguish documented requirements,
  implementation choices, and decisions needing Operator input.
- If the task conflicts with an authoritative source, stop before editing.

## 4. Implement only the approved scope

- Make precise changes that satisfy the task and preserve existing behavior.
- Avoid unrelated refactors, speculative abstractions, unrequested artifacts,
  and future-milestone behavior.
- Preserve architectural boundaries and invariants; workers propose while
  application code validates and commits durable state.
- Update directly related documentation when needed. Follow the repository's
  invariant change process if an invariant itself must change.
- Do not commit or publish unless explicitly requested.

## 5. Verify and report

- Run the smallest documented checks that cover the change, then any
  milestone-level checks required by the task.
- Report exact files changed, commands actually run, outcomes, skipped checks,
  assumptions, and unresolved issues.
- Distinguish code inspection from executed verification. Do not claim a test,
  build, migration, or external service check passed unless it was run.

## Autonomous decisions and Operator decisions

Codex may autonomously choose implementation details that are fully within the
approved scope, follow established repository patterns, and do not affect
architecture, public behavior, persisted data, security, or deployment
operations. It should state material assumptions in the handoff.

Operator input is required when a choice changes architecture, milestone
scope, durable schema or data semantics, user-visible behavior, security
policy, dependency or toolchain convention not already established, destructive
operations, or acceptance criteria. If the authority documents do not settle a
choice, Codex must not silently choose one.

For task structure and stop conditions, see
[`task-protocol.md`](./task-protocol.md). For blockers, see
[`failure-handling.md`](./failure-handling.md).
