# Watch — Architecture Revision

## 1. Central architectural statement

### Source-of-truth precedence

Original Watch documents remain authoritative for concepts Revision 2 has not explicitly revised. Revision 2 documents are authoritative only for concepts explicitly revised and mapped in `CHANGE_MAP.md`. Codex must never silently choose between conflicting specifications. If the map does not establish authority, stop and report the ambiguity before changing design or implementation.

Watch is a persistent software system that maintains state and adapts its behavior over time.

LLM Workers are components inside the system.

They are not the system itself.

The architecture therefore separates:

1. authoritative state,
2. operating policy,
3. control/strategy,
4. intelligence/workers,
5. integrity/commit,
6. learning.

## 2. Dual-entry execution model

Watch has two complementary execution entry points. They are not competing models; they converge on the same Task system.

### 2.1 Reactive execution path

For deterministic or routine work where the response is already known:

```text
Signal / Trigger / Scheduler / Operator
→ Task
→ Worker
→ Proposal
→ Kernel validation
→ Commit
```

Examples:

- `ingest_source`
- `apply_decay`
- routine triage
- `record_outcome`
- deterministic maintenance
- direct operator actions via API/CLI

This path remains valid and unchanged in its authority model. Existing Triggers, the scheduler, the API, and task chaining are not removed.

### 2.2 Deliberative control path

For work where the Team must decide what to attempt next given current state, uncertainty, and constraints:

```text
Objective
→ StateAssessment
→ one accepted Strategy (multiple concurrent Visions)
→ Workstreams / Actions / explicit Action prerequisites
→ one Plan
→ ordinary Task materialization
→ existing Task execution path
```

The Control layer is an additive, higher-level decision layer above the existing Task system. It produces ordinary Tasks. Once materialized, those Tasks follow the same state machine, write scopes, budgets, validation, atomic commit, Events, and idempotency as any reactive Task. Plan-linked Tasks additionally obey the Plan dependency admission invariant in `docs/invariants.md`; this does not add a Task state or runtime. The Control path starts from a durable Objective with an explicit lifecycle; no task-scoped ephemeral Objective exists.

A Task may be:

- reactive/unplanned,
- associated with an Objective,
- associated with both an Objective and a Plan.

The existing Task state machine is not redesigned to introduce Control.

## 3. Layers

### 3.1 Integrity Kernel

Owns:

- schemas
- repositories
- invariants
- state transitions
- commit validation
- idempotency
- optimistic concurrency
- Events
- provenance checks
- write scopes

The Kernel is the authority for durable state. Both execution paths converge here.

### 3.2 State layer

Contains:

- World memory
- Team memory
- immutable Snapshots
- Outcomes
- Evaluations
- Events
- current Task/Plan execution records

State is authoritative only when it exists as a validated durable record.

### 3.3 Intelligence layer

Contains Workers:

- deterministic services
- model-driven graphs
- human Operators

Workers consume bounded context and produce proposals or observations.

They do not define system truth.

### 3.4 Control layer

The Control layer answers:

> What should this Team attempt next, given the current state, Objective, TeamPolicy, constraints, and open questions?

It produces:

- Objective
- StateAssessment
- one accepted StrategyProposal for an Objective and historical assessment basis, containing multiple Visions, Workstreams, Actions, and explicit prerequisites
- one Plan derived from the accepted Strategy

One Strategy may contain multiple concurrent Visions. Each Vision is a bounded strategic perspective with meaningful scope and boundaries. A Vision may contain Workstreams: coherent groupings of related Actions that improve human comprehension and may summarize derived progress. Workstreams are not schedulers, workflow engines, dependency boundaries, or lifecycle authorities. An Action is purposeful intended work, not a Task. Explicit Action prerequisites may cross Workstreams and Visions; R5 validates and materializes this accepted structure, and the existing Task admission path enforces prerequisite readiness.

Initially an Objective has one active accepted Strategy, and one accepted Strategy produces one Plan for that Objective. Acceptance means deterministic legality and authority for later materialization, not strategic wisdom or effectiveness. The canonical accepted proposal and its provenance remain reconstructable without a transcript. Vision, Workstream, and Action identities belong in that structure; none requires a standalone durable entity by definition.

A Strategy may expose a capability gap, but organizational changes use a separate proposal path and require human review before durable Team change. They are not direct Strategy writes.

Vision, Workstream, and Action identity is local to one Strategy decision. Similar names or purposes in a later Strategy do not imply persistent identity across decisions.

Task materialization feeds into the existing Task system.

### 3.5 Learning layer

The existing learning model remains:

```text
Outcome
  ↓
Evaluation
  ↓
LearningChange
  ↓
Team memory / TeamPolicy version
```

The change introduced by this revision is that Evaluations can explicitly classify failures of:

- world understanding,
- strategy,
- execution,
- evidence/provenance,
- operating policy.

## 4. Authority model

```text
                 MODEL / HUMAN
                      │
                      ▼
                  Proposal
                      │
                      ▼
                Application code
                      │
               deterministic
                  validation
                      │
                      ▼
                Atomic commit
                      │
                      ▼
               Authoritative state
```

This applies to both ordinary world-memory updates and Control-layer changes. A StrategyProposal and a Plan materialization request are proposals; the Kernel validates and commits.

## 5. State, Policy, Strategy, Plan, Task

These must never collapse into one free-form “agent context”.

### State

Facts and durable records describing current reality as represented by Watch.

### TeamPolicy

Versioned operating rules: review requirements, budgets, tool restrictions, routing, knowledge selection, domain-specific configuration.

### Objective

One durable entity representing a bounded operational goal that the Team is currently trying to accomplish. It is not a Thread and not TeamPolicy. Its statuses are `draft`, `active`, `paused`, `blocked`, `completed`, and `cancelled`; legal transitions are `draft → active/cancelled`, `active → paused/blocked/completed/cancelled`, `paused → active/cancelled`, and `blocked → active/cancelled`. `completed` and `cancelled` are terminal. Tasks may reference an Objective, but there is no second task-scoped ephemeral Objective abstraction.

### Strategy

One coordinated strategic decision for an Objective and a particular historical StateAssessment basis, constrained by TeamPolicy. It identifies the perspectives and purposeful work authorized for pursuit. One Objective initially has one active accepted Strategy; that Strategy may contain multiple concurrent Visions. Acceptance is deterministic legality and authority for later Plan materialization, not proof that the Strategy is wise or effective. Strategic quality is evaluated later through Outcomes, Evaluation, and Learning.

Strategy is contextual, not TeamPolicy or Team memory. The accepted canonical StrategyProposal and its hash are preserved in a Task-attributed audit Event; no standalone Strategy entity is required by this semantic contract.

### Vision

A bounded strategic perspective through which part of an Objective is understood and pursued. A Vision has meaningful scope and boundaries; it is not a category label, scheduler, execution history, or TeamPolicy. Multiple Visions in one accepted Strategy may proceed concurrently. A Vision identity is local to its Strategy decision; do not infer that matching scope/name makes Visions in different Strategies the same entity. Preserve identity and definition in the accepted Strategy and derived Plan provenance; a standalone durable entity or cross-Strategy Vision lifecycle is not implied.

A Vision may accumulate evidence about its usefulness under particular conditions through later Work, Outcomes, and Evaluation. This is cautious evidence, not an automatic score or causal claim: success does not prove the Vision caused success, and failure does not by itself invalidate the Vision.

### Workstream

A coherent grouping of related Actions inside a Vision, primarily to make intended work and derived progress comprehensible to people. A Workstream is not a scheduler, workflow engine, Task lifecycle, dependency-enforcement authority, or execution boundary. It does not prohibit prerequisites between Actions in different Workstreams or Visions. A Workstream identity is local to its Vision within a Strategy decision; matching names across decisions do not imply one durable entity. Preserve its identity and meaning as part of accepted intent; no standalone Workstream entity or runtime is implied.

### Action

A purposeful unit of intended work required by a Workstream. An Action expresses strategic intent; a Task is the executable runtime unit. Action identity is local to one Strategy decision; equal work descriptions in another Strategy are not thereby the same Action. Stable Action identity and its parent Vision/Workstream provenance must survive acceptance and later materialization. The initial materializer may map one Action to one Task, but that implementation contract does not define Action as merely a future Task.

### StateAssessment provenance

StateAssessment remains a derived, deterministic, non-authoritative reconstruction; it is not a second source of truth. When a Strategy is accepted and a Plan is later materialized, preserve enough immutable decision provenance to reconstruct the exact assessment basis: source references, basis hash, creation timestamp, and, where needed, an immutable Snapshot of the assessment payload using the existing Snapshot mechanism. Current world state and historical decision context are distinct: rebuilding an assessment from current state must not overwrite or be mistaken for the historical basis used for the accepted Strategy. This basis provenance is linked to the accepted strategic decision and its derived Plan, not a separate authoritative StateAssessment entity.

### StrategyProposal

A transient structured proposal for one coordinated strategic decision. It may
contain multiple Visions, Workstreams, Actions, and explicit Action-to-Action
prerequisites, including valid cross-Workstream or cross-Vision prerequisites.
R4 deterministically validates the complete structure and records acceptance
or rejection through a Task-attributed Event. An accepted proposal is the
authorized strategic structure for later Plan materialization; R5 must not
invent, omit, partition, or reinterpret its contents without explicit
authority. Acceptance does not prove strategic wisdom or effectiveness.

Current nested R4 Events preserve canonical proposal content and SHA-256,
Objective/Team, and historical assessment context/provenance for exact
transcript-free reconstruction. Earlier flat R4 Events remain immutable
historical records: readers may verify their original stored payload/hash, but
may not infer omitted Vision/Workstream structure or missing assessment detail.
Any normalized nested view is explicitly derived compatibility data, not the
original Strategy. Legacy records lacking complete assessment provenance
cannot authorize new Plan materialization. Proposal data remains transient
apart from these audit records; Vision, Workstream, Action, or Strategy entities
are not implied.

### Plan

A Plan is durable bounded execution intent for exactly one Objective and its Team. It preserves accepted StrategyProposal provenance, reconstructable historical assessment basis, immutable intended actions with stable identities, dependencies, a fixed budget envelope, and completion/stop conditions. It is not execution history, Strategy memory, StateAssessment, a workflow engine, or a second execution runtime. Partial progress is derived from Tasks, not represented as a Plan status.

Plan creation, all initial ordinary Tasks, and the attributable creation Event commit atomically. Each intended action maps to at most one Task; after materialization it maps to exactly one. Nullable `Task.plan_id` and `Task.plan_action_id` identify that mapping and do not change ordinary Task behavior except for dependency admission: the existing Task admission path must not start a dependent Task before its prerequisites' Tasks are `done`.

The Plan's intent is immutable after creation. Lifecycle is `active → completed | stopped` with terminal states; stop reasons are abandoned, invalidated, or superseded. Progress is derived from Tasks. Completion requires every intended action to have a `done` Task and the declared completion condition to be satisfied by durable records. Substantial replanning creates a new Plan; supersession references and stops the prior Plan without rewriting it. Tasks, Events, and Outcomes remain the authority for what actually happened.

### Task

A bounded executable unit. Plan membership is optional. The existing Task state machine and write scopes are unchanged by the Control layer.

## 6. Control-layer validation

The Control layer performs deterministic validation. It cannot establish that a Strategy is semantically wise; strategic quality is subject to Outcome → Evaluation → Learning.

It CAN validate:

- schema
- ownership
- Objective state
- allowed Strategy structure
- valid Task types
- valid dependencies
- cycle absence
- write scopes
- tool allowlists
- budgets
- TeamPolicy constraints
- references to existing entities

It CANNOT validate:

- whether the proposed Strategy is semantically wise
- whether the chosen approach will succeed in the world

Invalid proposals are rejected with Events carrying reasons.

## 7. Trigger role

Triggers are retained.

A Trigger may:

1. directly create a Task when the response is deterministic and already known;
2. create or activate an Objective when the situation requires deliberation.

A future policy may determine which mode is appropriate for a given condition. Not every Trigger must pass through the Control layer.

## 8. Control loop

```text
1. Load authoritative state.
2. Identify the active Objective.
3. Build StateAssessment deterministically.
4. Identify open questions and constraints.
5. Generate candidate StrategyProposals.
6. Validate Strategy against TeamPolicy and Kernel capabilities.
7. Select/create a bounded Plan.
8. Materialize Tasks.
9. Execute Tasks through the existing Task runtime.
10. Commit valid proposals.
11. Record Outcomes where applicable.
12. Re-assess state.
13. Continue, stop, or revise strategy (creating a new Plan rather than silently rewriting the old one).
```

## 9. What the system itself should own

The software should own:

- current state
- identity of Teams
- policy versions
- task lifecycle
- plan lifecycle
- budgets
- write permissions/scopes
- evidence validity
- provenance
- concurrency
- audit trail
- learning transitions

A model may propose what should happen.

The software decides what is legal to happen.

## 10. Budget hierarchy

Budget ceilings are nested:

```text
TeamPolicy budget > Plan budget > Task budget
```

A Plan may never exceed the applicable TeamPolicy ceiling. The sum of Task budget allocations materialized under a Plan, including remaining unallocated budget, may not exceed the Plan envelope. Each materialized Task's own budget remains authoritative for its individual execution. Reactive Tasks without a Plan remain subject to their Task budget and applicable TeamPolicy ceilings.

## 11. What should remain replaceable

These should be replaceable without changing the Kernel:

- model vendor
- model
- prompt template
- Worker implementation
- deterministic source connectors
- retrieval implementation
- queue implementation
- domain pack heuristics
- Control-layer strategy generator

## 11. What should not be represented as “agent personality”

Avoid:

```text
SeniorResearchAgent
CriticalAgent
ManagerAgent
HistorianAgent
WriterAgent
```

unless there is a concrete runtime capability that requires identity.

Prefer:

```text
Task type
Required capability
Tool allowlist
Context builder
Worker implementation
```

## 12. Projection rule

Summaries, embeddings, dashboards, indexes, StateAssessments, and cached assessments are projections.

A decision path should be able to reconstruct its answer from authoritative state.

## 13. Non-goals of this revision

This revision does not introduce:

- self-modifying code
- autonomous Kernel schema changes
- unrestricted tool access
- a hierarchy of persistent Agent personalities
- arbitrary generated Domain code
- unrestricted recursive planning
- automatic policy mutation
- model-as-authority semantics
- a second workflow engine that bypasses the existing Task system
- a requirement that every Task belong to a Plan
- persistent OpenQuestion, Strategy, or PlannerAgent entities
