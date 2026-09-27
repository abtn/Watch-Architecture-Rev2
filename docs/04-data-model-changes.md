# Proposed Data Model Changes

## 1. Principle

Do not add entities simply because the architecture diagram contains a box.

First ask:

> Is this state durable, independently addressable, queryable, and necessary for an invariant?

If not, keep it derived.

The Control layer must be additive. The existing Task state machine and write-scope matrix must not change merely to introduce Control.

## 2. Candidates

### Objective

Objective is one new durable Kernel entity with:

- explicit lifecycle
- stable identity
- Team ownership
- relationships to Plans/Tasks
- completion criteria
- audit provenance

Tasks may reference it; do not add a second task-scoped ephemeral Objective abstraction.

Statuses and legal lifecycle:

```text
draft → active | cancelled
active → paused | blocked | completed | cancelled
paused → active | cancelled
blocked → active | cancelled
completed, cancelled → (terminal)
```

Every legal transition is validated and audited. No other transitions are permitted.

An Objective is not a Thread and not TeamPolicy.

### StateAssessment

StateAssessment is derived and non-authoritative. It may be rebuilt from current authoritative records, but when a Strategy/Plan is selected its exact historical basis must remain reconstructable.

Preserve basis references, basis hash, and creation timestamp with the selected Strategy/Plan provenance. If these references cannot reproduce the exact assessment payload, retain an immutable Snapshot of that payload using the existing Snapshot mechanism. This is immutable decision provenance, not another authoritative state store. A new assessment built from current world state must not overwrite the historical basis.

### Strategy

Do not make Strategy a permanent “memory” table initially.

Represent the accepted Strategy through the Plan plus its provenance. A StrategyProposal is a validated proposal object; once accepted, it becomes part of the Plan record.

If later experiments prove that Strategy needs independent lifecycle/history, create an explicit entity then.

### Plan

A durable execution-intent entity.

Suggested relationships:

```text
Plan → Objective
Plan → Strategy proposal/provenance (including exact StateAssessment basis)
Plan → Tasks
Plan → Events
```

Budget hierarchy:

```text
TeamPolicy budget > Plan budget > Task budget
```

A Plan may never exceed the applicable TeamPolicy ceiling. The sum of materialized Task budget allocations plus remaining unallocated budget must not exceed the Plan envelope. Each Task's budget remains authoritative for that Task's individual execution.

A Plan is execution intent, not execution truth. It references Tasks but does not own their state machine.

### Task

No change to the Task entity's core state machine or write-scope matrix.

Optional additions:

- `objective_id` (nullable FK)
- `plan_id` (nullable FK)

Plan membership is optional provenance metadata. If both references are present, the Objective must match the Plan's parent Objective. Neither reference changes Task execution semantics.

### OpenQuestion

Do not create this immediately unless the system needs queryable uncertainty independent of Hypotheses.

Start by representing open questions as structured fields on Objectives/Threads or as Task reasons.

Promote to an entity only when independent lifecycle is proven necessary.

## 3. Proposed minimal schema

The first revision should attempt:

```text
Objective
Plan
Task (with optional Objective/Plan FKs)
```

and avoid:

```text
Strategy (as durable entity)
StateAssessment (as durable entity)
OpenQuestion (as durable entity)
```

as separate durable entities until implementation pressure justifies them.

## 4. Why this conservative approach matters

The original design already has significant domain complexity.

The revision should not answer a missing abstraction by creating five new tables.

The new abstraction should be proven through runtime semantics first.

The Control layer must converge into the existing Task path, so the schema additions are limited to the Objective/Plan layer and optional provenance links on Tasks.

## 5. Data authority

Authoritative:

- Objective
- Plan
- Task
- Team
- TeamPolicy
- world/team memory
- Outcomes
- Events

Derived:

- StateAssessment
- summaries
- embeddings
- dashboards
- retrieval indexes

Potentially persisted execution/decision provenance records:

- model response
- prompt render
- tool trace
- context package
- immutable StateAssessment payload Snapshot when basis references and hash cannot reconstruct the exact assessment used to select a Strategy/Plan

These are provenance/execution artifacts, not Team memory or authoritative world state. Preserve the assessment basis references, hash, and creation timestamp alongside the selected Strategy/Plan provenance.
