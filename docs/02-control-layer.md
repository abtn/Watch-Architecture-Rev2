# Control Layer

## 1. Purpose

The Control layer is the missing abstraction between:

> what the Team knows

and:

> what the Team executes.

It is not a general “planner agent”.

It is a constrained software subsystem that sits above the existing Task system and converges into it.

## 2. The two entry paths

### 2.1 Reactive path

Used when the response is already known:

```text
Signal / Trigger / Scheduler / Operator
→ Task
→ Worker
→ Proposal
→ Kernel validation
→ Commit
```

This is the existing Watch path. It remains valid.

Examples:

- `ingest_source`
- `apply_decay`
- `record_outcome`
- routine triage
- direct operator action

### 2.2 Deliberative Control path

Used when the Team must decide what work should happen next:

```text
Objective
→ StateAssessment
→ StrategyProposal
→ Plan
→ Task materialization
→ existing Task execution path
```

The Control layer does not create a second execution runtime. It creates ordinary Tasks that then follow the existing Task state machine, write scopes, budgets, validation, atomic commit, Events, and idempotency rules.

## 3. Concepts

### 3.1 Team

Persistent identity.

### 3.2 Team mission

Long-lived purpose.

### 3.3 Objective

A bounded operational goal that the Team is currently trying to accomplish.

Examples:

- maintain an evidence-backed position on a market situation
- investigate whether a technology is suitable for a workload
- resolve a contradiction in a Thread
- prepare a briefing when defined evidence conditions are met

Objectives may be:

- operator-created,
- triggered by a Team condition,
- derived from an existing Thread,
- created by a previous Plan under explicit rules.

An Objective is one durable entity with one explicit lifecycle; there is no task-scoped ephemeral Objective abstraction. Tasks may optionally reference it.

Its explicit state machine is:

```text
draft → active | cancelled
active → paused | blocked | completed | cancelled
paused → active | cancelled
blocked → active | cancelled
completed, cancelled → (terminal)
```

Every transition is validated and audited. No other transitions are legal.

For R2, Objective creation and status transitions are Task-attributed
operations through the existing Task scope, budget, validation, Kernel
commit, and Event path. A Trigger initiates a Task for such a mutation rather
than bypassing Task attribution. Literal Task and Event names are not fixed
by this compatibility contract. Retry, rejection, and concurrency semantics
are defined in `docs/04-data-model-changes.md`.

An Objective should have:

- durable identity
- Team
- statement
- status
- created_by Task
- optional deadline
- success/stop criteria
- scope/constraints

An Objective is not a Thread and not TeamPolicy.

### 3.4 Thread

An ongoing situation in the world. Objectives may reference Threads but are not Threads.

### 3.5 StateAssessment

StateAssessment is not a second source of truth.

It is a derived, deterministic reconstruction of authoritative state relevant to an Objective.

Suggested fields:

```text
assessment_id
objective_id
generated_at
state_refs[]
open_questions[]
contradictions[]
blocked_conditions[]
stale_areas[]
candidate_opportunities[]
constraint_summary
basis_hash
```

The important field is the set of source references. The assessment should answer:

> Which records caused the system to believe this is the current state?

StateAssessment is never authoritative and never directly commits state. When a Strategy/Plan is selected, preserve its exact assessment basis in reconstructable form: basis references, basis hash, and creation timestamp; preserve an immutable Snapshot of the assessment payload when references alone cannot reconstruct the exact historical context. This is immutable decision provenance, not a second authoritative state store. Rebuilding an assessment from current world state must not overwrite the historical basis used for a prior decision.

### 3.6 StrategyProposal

A temporary proposal describing how an Objective should be pursued.

The LLM may produce:

```json
{
  "objective_id": "...",
  "approach": "independent_verification",
  "reason": "...",
  "candidate_actions": [
    {
      "task_type": "search_source",
      "purpose": "find independent primary evidence"
    }
  ],
  "constraints": {
    "max_tasks": 3,
    "max_cost_usd": 0.30
  },
  "stop_conditions": [
    "verified_evidence_found"
  ]
}
```

The LLM may not:

- invent Task types
- raise its own budget
- grant itself tools
- change TeamPolicy
- create arbitrary entity types
- skip required review
- directly commit state

StrategyProposal is not Team memory and is not TeamPolicy.

### 3.7 Strategy validation

Deterministic validation checks:

1. Objective exists and belongs to the Team.
2. Candidate Task types exist.
3. Task scopes are compatible.
4. Tool requirements are allowed.
5. Budget is within TeamPolicy.
6. Required review gates are respected.
7. Referenced state exists.
8. Stop conditions are representable.
9. No Kernel invariant is weakened.
10. Plan size is bounded.

Validation CANNOT establish that the Strategy is semantically wise. Strategic quality is tested by Outcomes and corrected through Evaluation → Learning.

### 3.8 Plan

A Plan is a durable record of intended orchestration for an Objective/Strategy.

Minimal shape:

```text
Plan
 ├── Objective
 ├── Strategy proposal/provenance
 ├── status
 ├── tasks
 ├── dependencies
 ├── budget
 ├── stop conditions
 ├── created_by Task
 └── provenance
```

Budget hierarchy is:

```text
TeamPolicy budget > Plan budget > Task budget
```

A Plan may never exceed the applicable TeamPolicy ceiling. The sum/remaining allocation of materialized Task budgets may not exceed the Plan envelope. Existing Task budgets remain authoritative for individual execution.

A Plan is not:

- TeamPolicy
- Team memory
- a transcript
- a permanent strategy manual
- authoritative execution truth

Actual execution is represented by Tasks, Events, and Outcomes. A Plan may become partially completed, abandoned, invalidated, or superseded without corrupting the execution record.

The R1 compatibility boundary requires one parent Objective and Team, Task
attribution, valid dependencies that do not create cycles, selected
Strategy/Assessment provenance, stop conditions, and a budget envelope.
Substantial replanning must not silently rewrite historical intent; the
architecture describes creating a new Plan, while the exact replacement or
supersession mechanism remains open. Task references to Objective and Plan
remain independently optional; when both are present they must be
parent-consistent and same-Team. The Plan status vocabulary and transition
graph, dependency storage shape, and exact Task scope operation remain for R5
design; R1 adds no Plan schema or runtime.

### 3.9 Task convergence

Plan materialization creates ordinary Tasks. Those Tasks:

- use the existing state machine,
- carry their own budgets and write scopes,
- are validated by the Kernel,
- emit Events,
- are idempotent under retry,
- may optionally reference their Objective and Plan.

A Task does not need a Plan to be valid.

## 4. Trigger roles

Triggers are retained.

A Trigger may:

1. directly create a Task when the response is deterministic and already known;
2. create or activate an Objective when the situation requires deliberation.

A future TeamPolicy rule may determine which mode is appropriate. Not every Trigger must pass through the Control layer.

## 5. Replanning

Replanning is expected.

A running Plan should not silently mutate itself.

Instead:

```text
Plan v1
  ↓
Outcome / failure / state change
  ↓
StateAssessment v2
  ↓
StrategyProposal v2
  ↓
Plan v2
```

The old Plan remains audit history. This gives the system a durable account of adaptation.

Replan only when:

- required preconditions fail,
- an Outcome materially changes relevant state,
- a stop condition is reached,
- a Task fails beyond retry policy,
- new evidence invalidates the Strategy basis,
- budget limits are reached,
- human consultation changes the available path.

## 6. Why not let LangGraph be the planner?

LangGraph can execute a Plan and manage temporary execution state.

It should not own the authoritative representation of:

- why the Plan exists,
- what the Team believes,
- what policy applies,
- what was learned.

That information belongs to durable Watch records.

The Control layer materializes Tasks; LangGraph may execute those Tasks if a particular graph needs resumability. The database remains the source of truth.

## 7. First implementation

Do not implement autonomous recursive planning first.

Start with:

```text
one Objective
one StateAssessment
one StrategyProposal
one Plan
two or three Tasks
```

Prove that the system can:

- explain why each Task exists,
- resume after restart,
- observe a changed state,
- terminate cleanly,
- replan without rewriting history.

## 8. Scenario C — Trigger → Objective → Plan

Scenario C demonstrates that the reactive and deliberative paths converge rather than compete.

### Part A — Reactive Trigger (direct Task)

A scheduled decay window passes.

```text
Trigger: decay_window_elapsed
→ Task: apply_decay
→ Worker: deterministic decay service
→ Proposal: ConfidenceChange for stale Hypotheses
→ Kernel validation
→ Commit
→ Event
```

No Objective, StateAssessment, or Plan is involved. The Trigger directly creates a Task because the response is deterministic.

### Part B — Deliberative Trigger (Objective → Plan)

A Thread has two active Hypotheses with directly contradictory EvidenceLinks. A Trigger detects the conflict.

```text
Trigger: contradiction_detected
→ Objective: resolve contradiction H-101 vs H-102
→ StateAssessment:
   - state_refs: Thread T-1, Hypotheses H-101/H-102, EvidenceLinks E-1/E-2
   - contradictions: H-101 supported by source A, H-102 supported by source B
   - open_questions: can A or B be independently verified?
→ StrategyProposal:
   - approach: independent_verification
   - reason: current confidence relies on two single-origin claims
   - candidate_actions:
      1. search_source for independent primary evidence
      2. triage_signal
      3. update_thread
   - stop_conditions: one verified supporting or challenging EvidenceLink
→ Plan P-1 Tasks:
   1. search_source
   2. triage_signal (on any found Signal)
   3. update_thread
→ Task execution through existing path
→ Outcome: update recorded
→ Evaluation: assess evidence quality and strategy effectiveness
→ new StateAssessment / Plan P-2 or Objective completed
```

The Trigger created the Objective, but all subsequent execution converged on ordinary Tasks validated by the Kernel.

## 9. Do not over-model

Do NOT introduce:

- OpenQuestion entity
- persistent Strategy entity
- persistent PlannerAgent entity
- StrategyAgent entity
- a second workflow engine
- a second memory system
- automatic policy learning
- a requirement that every Task belong to a Plan

Keep Strategy as proposal/plan-selection state until real implementation experience proves a durable entity is necessary.
