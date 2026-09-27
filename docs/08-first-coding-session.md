# First Coding Session

## Goal

Start implementation without allowing the new architecture to become another documentation-only exercise.

The Control layer is introduced only after the Kernel tooling and basic Task/Proposal/Commit semantics are proven.

## Ordering rule

```text
K0 tooling
K1 smallest Kernel commit path
R1 Control compatibility design
R2 Objective
R3 StateAssessment
R4 StrategyProposal
R5 Plan materialization
R6 One intelligent vertical slice
R7+ Real model, learning, domain pressure test
```

Do not skip K0/K1 to start with Objective or Plan.

## Session 0 — Repository inspection

Ask Codex to inspect only.

Prompt:

```text
Open the repository and inspect the current Watch design and codebase.

Read:
- AGENTS.md
- PLAN.md
- docs/architecture.md
- docs/invariants.md
- docs/glossary.md
- docs/tasks.md
- docs/decisions/ADR-0026-dual-entry-execution-model.md

Do not edit files.

Tell me:
1. current implementation status,
2. current repository structure,
3. exact M0/K0 starting point,
4. which parts of the architecture revision would conflict,
5. which new Control-layer concepts can be introduced without changing existing Kernel behavior.
```

## Session K0 — Establish baseline

Create:

- clean virtual environment
- dependency lock state
- Postgres + pgvector container
- migration runner
- pytest baseline
- lint/type baseline

Do not add Control-layer entities yet.

Acceptance:

```text
docker compose up -d
alembic upgrade head
pytest
ruff check .
mypy core
```

## Session K1 — Implement the smallest Kernel slice

Use the original plan's M0 principle:

> kernel before intelligence.

Implement the smallest current entity/commit path that proves:

```text
proposal
 ↓
validation
 ↓
atomic commit
 ↓
Event
```

No model calls.

For example: create a Team lifecycle transition, or ingest a Signal with Snapshot storage and hash validation.

Acceptance:

- one green commit path
- invalid proposals rejected with Events
- retry/idempotency covered
- existing invariants preserved

## Session R1 — Control compatibility design

Before writing Objective or Plan code:

- inspect the existing Task table and state machine
- design one durable Objective entity with explicit lifecycle; no task-scoped ephemeral Objective exists
- decide whether Task gets nullable `objective_id` and `plan_id`
- confirm the Task state machine does not change
- define assessment-basis provenance (references, hash, timestamp, Snapshot only if needed)
- define budget hierarchy checks: TeamPolicy ceiling > Plan envelope > Task budget
- decide how Triggers create Objectives vs. direct Tasks
- write a short compatibility note

No `Objective` model yet.

## Session R2 — Objective

Add Objective only after the Kernel baseline is green and the compatibility design is written.

The first Control-layer feature should be purely structural.

Do not build autonomous planning.

Acceptance:

```text
Objective is one durable entity
all specified lifecycle transitions work
every unspecified transition fails
completed and cancelled are terminal
every transition emits Event
StateAssessment not implemented yet
```

## Session R3 — StateAssessment

Implement a read-only deterministic builder.

The first version can simply produce structured JSON.

Example:

```json
{
  "objective_id": "...",
  "state_refs": ["thread:...", "hypothesis:..."],
  "open_questions": [],
  "blocked": [],
  "stale": [],
  "basis_hash": "..."
}
```

Acceptance:

- reads authoritative records
- deterministic for identical input
- preserves reconstructable historical basis when a Strategy/Plan is selected
- no assessment writes to authoritative world/team state

## Session R4 — Fake Strategy Worker

Use a deterministic FakeWorker.

Example:

```text
Objective:
verify conflicting evidence

StrategyProposal:
seek independent source

Plan:
1. search_source
2. triage_signal
3. update_thread
```

This proves the abstraction without model behavior.

Acceptance:

- valid StrategyProposal accepted
- invalid Task type rejected
- budget escalation rejected
- proposal audit Event recorded

## Session R5 — Plan materialization

Convert a validated StrategyProposal into a Plan, then into ordinary Tasks.

Acceptance:

- Plan contains Tasks and dependencies
- Plan budget is within the TeamPolicy ceiling
- aggregate Task allocations do not exceed the Plan envelope
- each Task budget governs individual execution
- created Tasks use the existing Task execution path
- Plan is execution intent, not execution truth
- failed Task does not silently rewrite Plan

## Session R6 — Plan execution

Run the Plan through the normal Task infrastructure.

Use LangGraph only if a specific Task genuinely needs resumable execution.

Acceptance:

- both reactive and deliberative paths run
- Trigger-bypassed Task still works
- system can explain why each Task exists

## Session R7 — Real model

Connect the ModelClient behind the same boundary.

The model should replace the FakeStrategyWorker—not the Control layer.

## Critical success criterion

At the end of the first intelligent loop, the system must be able to answer:

> Why did you perform this Task?

with durable references:

```text
Objective
→ StateAssessment
→ Strategy
→ Plan
→ Task
```

and also:

```text
Trigger
→ Task
```

for deterministic reactive work.

Not:

```text
because the previous agent conversation said so
```
