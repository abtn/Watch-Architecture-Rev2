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
→ StrategyProposal
→ Plan
→ Task materialization
→ existing Task execution path
```

The Control layer is an additive, higher-level decision layer above the existing Task system. It produces ordinary Tasks. Once materialized, those Tasks follow the same state machine, write scopes, budgets, validation, atomic commit, Events, and idempotency as any reactive Task. It starts from a durable Objective with an explicit lifecycle; no task-scoped ephemeral Objective exists.

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
- StrategyProposal
- Plan

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

A temporary approach for making progress toward an Objective under the current StateAssessment and TeamPolicy.

Examples:

- investigate contradiction before rendering
- seek an independent source
- ask a human expert
- compare two competing explanations
- delay publication until evidence threshold is met

Strategy is temporary and context-sensitive. It is represented by a StrategyProposal and, if accepted, recorded as part of a Plan's provenance. It is not a durable memory entity.

### StateAssessment provenance

StateAssessment remains a derived, deterministic, non-authoritative reconstruction; it is not a second source of truth. When a StrategyProposal is selected and a Plan is created, preserve enough immutable decision provenance to reconstruct the exact assessment basis: source references, basis hash, creation timestamp, and, where needed, an immutable Snapshot of the assessment payload using the existing Snapshot mechanism. Current world state and historical decision context are distinct: rebuilding an assessment from current state must not overwrite or be mistaken for the historical basis used to select the Plan. This basis provenance is linked to the durable Plan/Strategy selection, not a separate authoritative StateAssessment entity.

### StrategyProposal

A transient structured candidate describing how an Objective should be pursued.
At R4, deterministic validation accepts it as a legal candidate for later
planning or rejects it. Acceptance does not select a Strategy or create a
Plan; selection and Plan creation belong to R5. Both dispositions are
Task-attributed Events controlled by application/Kernel code. Accepted audit
preserves the canonical proposal and its hash so the exact candidate can be
recovered without a transcript or regeneration. Events are audit/provenance,
not Strategy memory. R4 also retains the derived assessment basis references,
hash, timestamp, and exact projection payload in the audit; this is not an
authoritative StateAssessment entity or R5 selection provenance.

### Plan

A durable record of intended orchestration for an Objective/Strategy. It contains Tasks, dependencies, conditions, and budget envelopes.

A Plan is execution intent, not execution truth. Tasks, Events, and Outcomes remain authoritative for what actually happened. A Plan may be partially completed, abandoned, invalidated, or superseded without corrupting the execution record.

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
