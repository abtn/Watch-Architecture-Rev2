# ADR-0026 — Dual-Entry Execution Model

## Status

Proposed

## Context

The original Watch design has multiple valid Task entry points:

- Triggers create Tasks based on thresholds, schedules, or manual fire.
- The scheduler creates Tasks for ingestion, decay, review, and overdue scans.
- The API/CLI creates manual Operator Tasks.
- A finishing Task may enqueue a follow-up Task.

The architecture revision introduces a Control layer:

```text
Objective → StateAssessment → StrategyProposal → Plan → Tasks
```

These two models must not become competing execution systems. The Control layer must not replace the existing reactive Task system, and the existing Task system must not silently prevent deliberate, state-aware planning.

## Decision

Watch adopts a dual-entry execution model.

### Entry 1 — Reactive execution path

Used for deterministic or routine work where the response is already known:

```text
Signal / Trigger / Scheduler / Operator
→ Task
→ Worker
→ Proposal
→ Kernel validation
→ Commit
```

Examples: `ingest_source`, `apply_decay`, routine triage, `record_outcome`, deterministic maintenance, direct operator actions.

This path remains valid, unchanged in its authority model, and must not be removed.

### Entry 2 — Deliberative control path

Used when the Team must decide what work should happen next:

```text
Objective
→ deterministic StateAssessment
→ StrategyProposal
→ Plan
→ Task materialization
→ existing Task execution path
```

The Control layer converges into the existing Task system. Plan materialization simply creates ordinary Tasks. Once created, those Tasks follow the same state machine, write scopes, budgets, validation, atomic commit, Events, and idempotency rules as any other Task. Objective is one durable entity with an explicit lifecycle; Tasks may reference it, but there is no task-scoped ephemeral Objective abstraction.

## Consequences

- The Control layer is an additive, higher-level decision layer above the existing Task system.
- A Task may be reactive/unplanned, associated with an Objective, or associated with both an Objective and a Plan.
- Existing Triggers are retained. A Trigger may directly create a Task when the response is deterministic, or create/activate an Objective when deliberation is required. A future policy may determine which mode is appropriate.
- The Task state machine, write-scope matrix, budget mechanism, and commit path are not redesigned to introduce Control.
- Plan membership is optional provenance metadata from the perspective of Task execution.
- Budget hierarchy is `TeamPolicy ceiling > Plan envelope > Task budget`: a Plan cannot exceed the applicable TeamPolicy ceiling, Task allocations cannot exceed the Plan envelope, and each Task's budget governs its individual execution.
- The Plan records intended execution state, not authoritative reality. Actual execution is represented by Tasks, Events, and Outcomes.

## Rejected alternatives

### Replace all Task creation with Control-layer planning

Rejected because deterministic maintenance, operator actions, and simple trigger responses should not pay the latency and model-cost overhead of deliberation.

### Allow the Control layer to own a separate execution runtime

Rejected because that would create two execution models, two failure modes, and two recovery paths. The Control layer must produce Tasks, not bypass them.

### Require every Task to belong to a Plan

Rejected because it would break the existing reactive paths and force over-modeling of simple deterministic work.
