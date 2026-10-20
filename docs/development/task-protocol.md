# Task Protocol and Reusable Briefs

Use this protocol to turn a request into a bounded implementation unit. Templates are starting points; fill them with the current repository's real paths, gates, and commands.

## Required task packet

Every implementation packet should state:

1. **Goal:** one observable capability or defect.
2. **Authority:** relevant PLAN section, spec, ADR, and invariants.
3. **Current state:** actual code/test locations, branch/worktree constraints, existing user changes.
4. **Allowed changes:** explicit files/areas; mention when migrations are allowed.
5. **Acceptance:** observable behavior, including rejection and failure cases.
6. **Tests:** regression tests and actual commands.
7. **Non-goals:** later milestones, adjacent refactors, new abstractions, or unrelated cleanup to avoid.
8. **Stop condition:** exact unresolved decision or failed gate that blocks further work.
9. **Handoff:** files changed, commands/results, assumptions, and unresolved items.

## Template A — Inspect only

```text
Task: inspect and report; do not edit files.
Read the relevant repository instructions, PLAN section, CHANGE_MAP row, spec/ADR, implementation, and tests.
Report: (1) what exists, (2) authoritative intended behavior, (3) gaps/risks, (4) minimal next slice, (5) tests required, (6) conflicts or gates that block implementation. Separate code presence from verification evidence.
```

## Template B — Implement one slice

```text
Goal: <one observable behavior>
Authority: <PLAN section, spec, ADR, invariant>
Allowed changes: <specific files/areas>
Required tests: <specific expected behaviors>
Acceptance criteria: <verifiable criteria>
Non-goals: no unrelated refactor, no later milestone, no new entity/runtime/default without authority.
Stop if: source conflict, unapproved architecture/schema/security decision, or unmet milestone gate.
Verification: run <focused commands> and any applicable broader checks.
Final report: changed files; command/result pairs; assumptions; unrun checks; unresolved issues.
```

## Template C — Architecture review (no edits)

```text
Compare implementation against the authoritative spec and ADRs. Check:
- State / TeamPolicy / Strategy / Plan / Task boundaries
- reactive and deliberative paths converge on ordinary Tasks
- model/worker authority versus application validation/commit
- Task scope, budget, ownership, Event attribution, atomicity
- concurrency, idempotency, replay, and restart reconstruction
- immutable Plan intent and historical provenance
Report violations, risks, missing tests, contradictory sources, and the smallest justified follow-up. Do not implement fixes.
```

## Template D — Test-first change

```text
Identify the invariant and write a regression test that fails for the current defect. Implement the smallest change. Run the focused test and relevant invariant suite. Do not weaken or delete a test just to accommodate the implementation. Report any environmental failure separately.
```

## Template E — Refactor guard

```text
Refactor only; externally observable behavior and architecture must remain unchanged. Prove equivalence for state transitions, write scopes, Events, idempotency, errors, and relevant tests. Do not introduce abstractions unless they directly remove established duplication.
```

## Template F — Specification conflict

```text
Stop before implementation. Identify the exact conflicting statements and their source paths. Explain what decision is missing without silently selecting an interpretation. Propose the smallest explicit ADR/status update or operator decision needed to unblock the task.
```
