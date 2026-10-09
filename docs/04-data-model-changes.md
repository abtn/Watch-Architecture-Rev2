# Proposed Data Model Changes

## 1. Principle

Do not add entities simply because the architecture diagram contains a box.

First ask:

> Is this state durable, independently addressable, queryable, and necessary for an invariant?

If not, keep it derived.

The Control layer must be additive. The existing Task state machine and write-scope matrix must not change merely to introduce Control.

The R1 compatibility rule was that existing K1 Task write-scope semantics remain unchanged and authoritative. Durable Objective and Plan mutations must be Task-attributed and pass through the same Task write-scope authorization and Kernel validation path; Trigger-driven deliberation must materialize a Task before such a mutation. Future Control-layer authorization may be added within this model, but must not rewrite K1 semantics or create a parallel mechanism. Plan remains durable execution intent, not execution truth; Tasks, Events, and Outcomes remain execution truth. Plan schema and lifecycle were deferred at R1 and are closed for R5 in Section 6.

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

### Strategy, Vision, Workstream, and Action — subsequent R4 closure

One Objective initially has one active accepted Strategy: one coordinated
strategic decision based on a particular historical StateAssessment basis.
Acceptance means the complete proposal is deterministically legal and
authorized for later Plan materialization; it does not establish strategic
wisdom or effectiveness. Multiple Visions within that Strategy may proceed
concurrently.

A Vision is a bounded perspective with meaningful scope and boundaries. A
Workstream is a coherent grouping of related Actions for human comprehension
and derived progress; it is not a scheduler, workflow engine, lifecycle, or
dependency boundary. An Action is purposeful intended work, not a Task.
Stable identities and definitions for these concepts belong in the accepted
Strategy structure and later Plan provenance. They do not require separate
entity tables by definition.

Dependencies are explicit Action-to-Action prerequisites validated as part of
the accepted Strategy structure. They may cross Workstreams or Visions; reject
missing targets, self-dependencies, and cycles. Workstream grouping does not
restrict their scope. Runtime admission enforcement remains the existing Task
path under INV-16.

Keep Strategy temporary, not Team memory or TeamPolicy. Current nested R4
Task-attributed Events preserve the canonical accepted/rejected proposal, hash,
and historical assessment context so exact proposals can be reconstructed
without transcript. Earlier flat R4 Events remain immutable, hash-verifiable
historical records. Readers may expose the stored legacy record and optionally
a clearly marked derived nested compatibility view, but missing Vision/
Workstream semantics and missing assessment payload are not reconstructed or
inferred. Such legacy records cannot authorize new Plan materialization. R5 derives one Plan for the Objective from its one active accepted
Strategy and may not invent, omit, partition, or reinterpret strategic
structure without explicit authority. No Strategy, Vision, Workstream,
Action, or StateAssessment entity is introduced by this contract.

A Strategy may reveal a capability gap. Any Team/capability structural change
is a separate proposal path requiring human review; R4 does not mutate Team
structure.

Vision, Workstream, and Action identity is proposal/Strategy-local. Reusing a label or purpose in a later Strategy does not assert shared persistent identity. The deterministic early producer scopes generated identities to its proposal Task and assessment basis so same-request retries reconstruct consistently while later decisions remain distinct.

### Plan

A durable execution-intent entity derived from the one active accepted
Strategy for its Objective. It preserves the accepted Strategy's Vision,
Workstream, Action, and prerequisite structure as immutable intent and
provenance, plus the exact historical StateAssessment basis. Initially one
accepted Strategy produces one Plan. R5 must not invent, omit, partition, or
reinterpret that structure without explicit authority. A Plan is not execution
truth; Tasks, Events, and Outcomes describe what actually happened.

Suggested relationships:

```text
Plan → Objective
Plan → accepted Strategy proposal/provenance (including exact StateAssessment basis)
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
- `plan_id` (nullable Plan provenance)
- `plan_action_id` (nullable stable intended-action identity)

Plan membership is optional provenance. When both Plan/action references are present, the action must belong to that Plan; a `(plan_id, plan_action_id)` pair maps to at most one Task. Once materialized, each intended action maps to exactly one Task. Objective and Team ownership must remain consistent; if both Objective and Plan are present, the Objective must equal the Plan's parent Objective. These references do not otherwise change the Task state machine or ordinary Task semantics.

### OpenQuestion

Do not create this immediately unless the system needs queryable uncertainty independent of Hypotheses.

Start by representing open questions as structured fields on Objectives/Threads or as Task reasons.

Promote to an entity only when independent lifecycle is proven necessary.

## 3. Proposed minimal schema

Across the Control implementation, the intended additive schema is:

```text
Objective
Plan (durable bounded intent and preserved accepted Strategy structure)
Task (nullable Objective, Plan, and Plan-action provenance)
```

Plan identity, stable Action identity, accepted Strategy and assessment provenance, budget, completion conditions, and lifecycle must be durably represented. Preserve Vision/Workstream identity where required for provenance. The representation is an implementation choice; this closure does not require Strategy, Vision, Workstream, or PlanAction entities.

This is not one migration. R2 adds Objective and nullable `Task.objective_id`
after the existing K1 migration. R5 adds Plan and nullable `Task.plan_id` and
`Task.plan_action_id`. Keep the K1 migration immutable and preserve K1 behavior.

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
migration after K1. Plan schema and Task Plan-provenance fields were deferred
to R5 and are closed by the subsequent semantic contract below. No table is
required for a concept merely because it appears in the architecture.

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

### Plan compatibility boundary — R1 record and subsequent R5 closure

A Plan is durable bounded execution intent for exactly one Objective and its Team. It is not execution history, Team/Strategy memory, StateAssessment, a workflow engine, or a second runtime. Its immutable intent includes the accepted proposal Event identity/hash, reconstructable assessment basis, stable intended action definitions, dependencies, budget envelope, and completion/stop conditions. Current assessments never overwrite the historical basis. No Strategy, StateAssessment, or PlanAction entity is required.

The Plan and all initial ordinary Tasks plus the attributable creation Event commit atomically. There is no partial-materialization lifecycle. Each action has a stable identity and maps to zero or one Task before materialization, exactly one afterward. Nullable `Task.plan_id` and `Task.plan_action_id` identify this mapping; an action must belong to the referenced Plan, Team/Objective ownership must match, and each Plan/action pair is unique.

The creating `create_plan` Task's existing `policy_version` records the policy considered at creation; there is no separate Plan policy pin. Policy changes do not rewrite Plan intent or existing Task semantics. Later operations use their applicable policy version. The Plan envelope is bounded by applicable TeamPolicy; Task allocations fit within the envelope, and Task budgets remain authoritative for individual execution.

Dependencies are same-Plan prerequisite references between distinct actions. Missing targets, cross-Plan references, self-dependencies, and cycles are invalid. The existing Task admission/claim path enforces that a dependent Task cannot start until its prerequisite Task is `done`; a failed prerequisite keeps it ineligible until stop or replan. No Task state, separate scheduler, or workflow engine is introduced.

Lifecycle is `active → completed | stopped`; completed and stopped are terminal. `stopped_reason` distinguishes `abandoned`, `invalidated`, and `superseded`. Progress is derived from Tasks. Completion requires every intended action to have exactly one linked Task in `done` and the declared completion condition to be satisfied by durable records. Completion and stopping are explicit application-controlled transitions with attributable Events. Supersession atomically creates a new Plan referring to the old one and stops the old Plan as superseded. Intent fields never change; substantial replanning creates a new Plan.

The narrow `create_plan` operation validates an accepted R4 proposal Event and hash, Objective/Team ownership, supported actions, dependency validity, applicable policy constraints, budgets, and idempotency. It may create only the Plan, initial ordinary Tasks, and explicitly scoped audit Events; it cannot change TeamPolicy or memory or create Strategy/StateAssessment entities.

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
budget governs its execution. The creating Task's existing `policy_version`
records the policy considered at creation; there is no Plan policy pin. Later
operations use their applicable policy version, and policy changes do not
rewrite Plan intent or existing Task semantics. R2 has no Plan envelope and
adds no budget runtime. Enforcement of the Plan and aggregate Task limits
belongs to R5.

### Invariant compatibility

R5 adds cross-cutting INV-16 for Plan dependency admission; see `docs/invariants.md`. The existing Task admission/claim path, not the Plan, enforces prerequisite readiness.

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
