# Using Codex in VS Code for Watch

## 1. The central rule

Do not use Codex as:

> “Build Watch for me.”

Use Codex as:

> “Implement this small, already-defined vertical slice and prove it with tests.”

Codex is the implementation worker.

You remain responsible for architecture and product decisions.

## 2. Implementation ordering rule

Do not ask Codex to implement Control-layer behavior before the Kernel baseline exists.

The required order is:

```text
Slice K0: tooling → migration → tests
Slice K1: smallest Kernel commit path
R1: compatibility design (one durable Objective; assessment provenance; budget hierarchy)
R2: Objective lifecycle
R3: StateAssessment
R4: StrategyProposal
R5+: Plan and intelligent loop
```

For authority, follow `AGENTS.md` and `CHANGE_MAP.md`: original documents govern unchanged concepts; mapped Revision 2 documents govern explicitly revised concepts. Stop and report if the authority boundary is ambiguous.

If a Codex task would add Plan/Objective/Strategy code while the Kernel commit path is not green, stop and redirect to the Kernel slice first.

## 3. Recommended VS Code structure

Open the repository root as the workspace.

Keep these files easy to access:

```text
AGENTS.md
PLAN.md
docs/
tests/
src or core/
```

Pin:

- `AGENTS.md`
- current task section in `PLAN.md`
- the relevant architecture document
- `docs/decisions/ADR-0026-dual-entry-execution-model.md` when changing Task, Plan, Objective, Trigger, or scheduler behavior
- the relevant test file

## 4. Every Codex task should contain five parts

### Context

What subsystem is being changed?

### Goal

Exactly what should exist when the task ends?

### Constraints

What must not change?

### Acceptance tests

How do we know the work is correct?

### Verification

Exact commands Codex must run.

Example:

```text
Task: Implement Objective state transitions.

Read:
- AGENTS.md
- CHANGE_MAP.md
- docs/01-architecture-revision.md
- docs/04-data-model-changes.md
- PLAN.md Phase R2

Do:
- add Objective model
- add repository
- add transition service
- add Events
- add invariant tests
- add Alembic migration

Do not:
- add Plan behavior
- add LLM code
- modify TeamPolicy
- refactor unrelated modules

Acceptance:
- one durable Objective follows the lifecycle defined in `docs/04-data-model-changes.md`
- completed and cancelled are terminal
- invalid transitions fail
- every transition emits Event
- tests cover every legal and illegal transition

Verify:
pytest tests/objective
ruff check .
mypy core
```

## 5. Do not let Codex decide architecture accidentally

A dangerous prompt is:

```text
Build the Control layer.
```

A better prompt is:

```text
Implement Slice 3 from PLAN.md.

Do not add new entities unless required by an invariant.
Do not change the schema outside Objective.
Do not introduce an LLM.
Stop and explain if existing architecture contradicts the task.
```

## 6. Use short sessions

One session should ideally end with one meaningful change.

Good:

```text
Implement Objective transitions.
```

Too large:

```text
Implement the entire planning system.
```

## 7. Ask Codex to inspect before editing

For unfamiliar areas:

```text
Inspect the existing repository and explain:
1. where this behavior currently lives,
2. which files are authoritative,
3. which tests already cover it,
4. where the new change should fit.

Do not edit anything yet.
```

This is valuable because the architectural documents may be ahead of the actual code.

## 8. Then switch to implementation

Second prompt:

```text
Implement the design we just identified.

Keep the change scoped to:
...

Before finishing:
- run the specified tests
- show changed files
- report any deviation from the task
```

## 9. Use Codex as a reviewer too

After implementation:

```text
Review this change against:
- AGENTS.md
- relevant architecture section
- invariants

Do not modify files.

Look specifically for:
- bypassed commit paths
- duplicated state
- hidden assumptions
- incorrect authority boundaries
- missing tests
```

Then make a separate implementation session for any fixes.

## 10. Good development loop

```text
You define slice
       ↓
Codex inspects
       ↓
Codex implements
       ↓
Tests
       ↓
Codex reviews
       ↓
You inspect architectural impact
       ↓
Commit
       ↓
Next slice
```

## 11. Use Git aggressively

Keep commits small and architectural:

```text
add Objective state machine
add Objective transition invariants
add deterministic state assessment
add StrategyProposal schema
add Plan materialization
```

Avoid:

```text
implement Watch
fix stuff
big refactor
```

## 12. When to create an ADR

Ask:

> Did we just change what the system fundamentally means?

If yes, write an ADR before or together with the implementation.

Examples:

- Strategy becomes durable memory
- Plan may mutate in place
- TeamPolicy gains autonomous adaptation
- Domain packs may add capabilities
- Workers gain cross-task private memory

These are architecture decisions, not implementation details.

## 13. The Codex mental model

Think:

```text
You = architect / product owner

Codex = implementation workforce

Tests = executable constraints

Kernel = authority

LLM Worker = bounded runtime capability
```

That is much safer than putting the LLM in the role of architect, product owner, implementation worker, and authority simultaneously.
