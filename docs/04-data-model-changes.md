# Proposed Data Model Changes

## 1. Principle

Do not add entities simply because the architecture diagram contains a box.

First ask:

> Is this state durable, independently addressable, queryable, and necessary for an invariant?

If not, keep it derived.

The Control layer must be additive. The existing Task state machine and write-scope matrix must not change merely to introduce Control.

Compatibility rule for the R1 design pass: existing K1 Task write-scope semantics remain unchanged and authoritative. Durable Objective and Plan mutations must be Task-attributed and pass through the same Task write-scope authorization and Kernel validation path; Trigger-driven deliberation must materialize a Task before such a mutation. Future Control-layer authorization may be added within this model, but must not rewrite K1 semantics or create a parallel mechanism. Plan remains durable execution intent, not execution truth; Tasks, Events, and Outcomes remain execution truth. Plan schema and its complete lifecycle remain deferred to R5; see Section 6.

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

Both references are independently optional: a Task may have neither, either
one, or both. When both are present, `objective_id` must equal the parent
Objective of the referenced Plan. Every referenced Objective or Plan must
belong to the Task's Team. The existing Kernel validation path checks these
relationships; they do not change the Task state machine.

### OpenQuestion

Do not create this immediately unless the system needs queryable uncertainty independent of Hypotheses.

Start by representing open questions as structured fields on Objectives/Threads or as Task reasons.

Promote to an entity only when independent lifecycle is proven necessary.

## 3. Proposed minimal schema

Across the Control implementation, the intended additive schema is:

```text
Objective
Plan
Task (with optional Objective/Plan FKs)
```

This is not one migration. R2 adds Objective and nullable `Task.objective_id`
after the existing K1 migration. Plan and nullable `Task.plan_id` belong to
R5. The K1 migration is immutable; later migrations must preserve K1 behavior.

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

## 6. R1 compatibility closure

This section closes the R1 design decisions needed before R2. It does not add
Control schema or runtime. K1 migration `0002_ingestion_kernel` and its
write-scope behavior remain unchanged. Objective schema belongs in a new
migration after K1; Plan schema and `Task.plan_id` remain deferred to R5. No
table is required for a concept merely because it appears in the architecture.

### Objective mutation and scope

R2 must provide Task-attributed operations to create an Objective in `draft`
and to perform its specified status transitions. These operations do not
establish permanent immutability for Objective descriptive fields; R2 scope
is limited to the operations in its milestone, and any additional mutation
semantics remain subject to later design. A Trigger or Operator may initiate
Objective mutation only through an ordinary Task; the Trigger itself does
not bypass Task attribution.

Both operations use `Objective` in the Task's `allowed_writes`, plus only the
Task-attributed Event and normal Task lifecycle effects allowed by the scope
matrix. The Task must be running, its Team must be active under the common
Task rules, its configured write scope must authorize the operation, and its
existing budget applies. The Objective's Team must match the creating or
transitioning Task's Team. Any referenced Objective or Plan must be owned by
that same Team. Application validation and the existing Kernel commit path
are the only mutation authority. Human-initiated operations use the same
path and retain Operator identity in Event payloads.

### Objective lifecycle, Events, and retries

The only legal Objective transitions are:

```text
draft → active | cancelled
active → paused | blocked | completed | cancelled
paused → active | cancelled
blocked → active | cancelled
completed, cancelled → (terminal)
```

Creation starts in `draft`. A successful Objective mutation commits through
the existing Kernel boundary and produces a durable, Task-attributed Event
sufficient to reconstruct the committed transition. A rejected mutation
leaves Objective state unchanged and produces an auditable rejection Event
with a stable reason/category sufficient for diagnosis. The Event remains
attributable to an existing Task. Literal Event names, reason codes, and
whether rejection recording uses a separate transaction remain open.

INV-13 requires that retrying the same successful mutation from the same Task
does not double-commit it. Revalidating an Objective transition at commit
must reject stale or conflicting state rather than silently overwrite it;
the commit is atomic. The semantic outcome is fixed, while the operation
identity representation, treatment of repeated rejection Events, and
database concurrency mechanism remain implementation choices. No particular
lock strategy, SQL statement, or new version field is required here.

### Task relationship rules

Both `objective_id` and `plan_id` are independently nullable provenance
references. A Task may have neither, either one, or both. When both are
present, the Task's Objective must equal the Plan's parent Objective. Each
referenced record must match the Task's Team. Neither reference changes Task
state, scope, budget, or commit semantics.

### Plan compatibility boundary

Plan ownership is the Objective's Team, and each Plan has one parent
Objective. A Plan is created by a Task, preserves selected Strategy and
StateAssessment decision provenance, and records intended dependencies,
budget envelope, and stop conditions. Dependencies must be explicit and
valid, and must not create cycles. Tasks may reference an Objective and/or a
Plan, subject to the parent-consistency rule above; they remain authoritative
for execution. Events and Outcomes record what happened. A Plan may be
partially completed, abandoned, invalidated, or superseded. Substantial
replanning must not silently rewrite prior intent/history; the architecture
describes creating a new Plan, while the exact replacement/supersession
mechanism remains open.

The following remain deliberately open for R5: Plan status vocabulary and
transition graph; whether/how an existing Plan's status and task membership
may change while preserving its original intent; physical dependency
representation; the Task type and exact write-scope row that creates or
updates a Plan; and Plan materialization retry/idempotency details. R1 does
not create a Plan table or prescribe these implementation details.

### Assessment and budget compatibility

When a StateAssessment is selected for a Strategy/Plan, preserve its source
references, basis hash, and creation timestamp with that decision provenance.
Use an immutable Snapshot of the assessment payload only if references and
hash cannot reconstruct the exact selected basis. This is semantically
required provenance, not a durable StateAssessment entity. Serialization,
storage technology, and the hashing algorithm are implementation choices not
fixed by R1.

The fixed budget ordering is:

```text
TeamPolicy ceiling > Plan envelope > Task budget
```

A Plan cannot exceed the applicable TeamPolicy ceiling; allocated plus
remaining Task budgets cannot exceed the Plan envelope; each Task's own
budget governs its execution. R2 has no Plan envelope and adds no budget
runtime. Enforcement of the Plan and aggregate Task limits belongs to R5.

### Invariant compatibility

| Invariant | Compatibility requirement | Later enforcement/test | R1 status |
|---|---|---|---|
| INV-01 | Control decisions use durable records, not shared transcripts. | R2/R3 restart and replay do not depend on transcript state. | No runtime added. |
| INV-02 | Objective and Plan writes are validated proposals committed by application/Kernel code. | R2 tests Kernel-only Objective writes; R5 does the same for Plan. | No enforcement added. |
| INV-03 | Any Snapshot used to reconstruct selected Assessment provenance is immutable and verified. | R3 tests Snapshot integrity if a Snapshot is required. | No Snapshot or Assessment added. |
| INV-11 | StateAssessment is derived and cannot replace authoritative records. | R3 tests deterministic read-only construction. | No Assessment added. |
| INV-12 | Strategy/Plan provenance cannot change Team memory or TeamPolicy outside LearningChange. | R4/R5 test that proposals cannot bypass the learning path. | No learning behavior added. |
| INV-13 | Revalidate ownership, expected status, scope, and prior Task outcome; reject conflicts and avoid duplicate commits. | R2 tests Objective retry and concurrency; R5 tests Plan materialization retry/conflict. | No runtime or enforcement added. |
| INV-14 | Objective/Plan writes require explicit Task scope and budget. | R2/R5 test unauthorized write and budget rejection. | No scope enforcement added. |
| INV-15 | Operator Objective writes use the same validation path and Task-attributed Events with identity. | R2 tests Operator success and rejection paths. | No Operator path added. |
