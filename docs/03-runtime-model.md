# Runtime Model

## 1. Runtime responsibilities

Runtime components have four broad responsibilities:

```text
Reactive runtime
    creates Tasks directly from Signals, Triggers, scheduler, or operator actions

Control runtime
    chooses bounded work from one durable Objective through Assessment → Strategy → Plan

Execution runtime
    runs Tasks (regardless of how they were created)

Kernel
    validates and commits

Scheduler
    wakes eligible work
```

The Control runtime is additive. It starts from one durable Objective (never a task-scoped ephemeral Objective), materializes ordinary Tasks, and uses the same execution runtime as reactive Tasks.

## 2. Lifecycle

### Reactive path

```text
Signal / Trigger / Scheduler / Operator
→ Task creation
→ Worker pick-up
→ Proposal / observation
→ Kernel validation
→ Atomic commit
→ Event
→ (optional) Outcome
```

This is the existing path. It does not require an Objective, StateAssessment, or Plan.

### Deliberative Control path

```text
One durable Objective becomes active
→ StateAssessment build (deterministic, read-only)
→ one StrategyProposal for the Objective and historical assessment basis
→ deterministic validation and Task-attributed acceptance/rejection
→ accepted Strategy with concurrent Visions, grouped Workstreams, intended Actions, and explicit Action prerequisites
→ one Plan derived from the complete accepted Strategy
→ Plan materialization
→ Task creation (ordinary Tasks)
→ existing Task execution path
→ Worker pick-up
→ Proposal / observation
→ Kernel validation
→ Atomic commit
→ Event
→ Outcome
→ re-assessment / replan / stop
```

After Task materialization, both paths use ordinary Task execution. The existing Task admission/claim path enforces Plan-action prerequisites; it does not create a second execution runtime.

## 3. Detailed Control lifecycle

### Step 1 — Objective becomes active

An Objective enters an executable status.

### Step 2 — Assessment

The Control service loads authoritative state and produces a deterministic StateAssessment. StateAssessment is read-only and derived. When selecting a Strategy/Plan, persist reconstructable decision provenance (basis references, hash, creation timestamp, and, where necessary, an immutable Snapshot of the assessment payload). This historical basis does not become authoritative state and must not be overwritten when a new assessment is built from current records. A Plan references the accepted proposal Event and proposal hash; it does not duplicate the proposal payload unless needed for exact reconstruction. R4's Event also preserves the historical assessment basis references, hash, timestamp, and projection payload, so current assessments cannot replace the basis used for this decision.

### Step 3 — StrategyProposal

A model worker (or deterministic generator in early slices) proposes one
coordinated StrategyProposal for this Objective and a particular assessment
basis. The structure may contain multiple concurrent Visions, Workstreams,
Actions, and cross-Workstream/Vision prerequisites. Strategy acceptance
authorizes the complete validated structure for one later Plan; it does not
prove strategic wisdom or effectiveness. Accepted canonical content, hash,
Task attribution, and historical assessment context remain reconstructable
from durable audit without a transcript. Team/capability changes are separate
human-reviewed proposals, not Strategy writes.

### Step 4 — Validation

Application code validates the StrategyProposal deterministically.

### Step 5 — Plan creation and initial Task materialization

One accepted StrategyProposal becomes one bounded Plan for its Objective through a narrowly scoped `create_plan` Task. The Plan preserves the complete accepted Vision/Workstream/Action structure and prerequisite relationships as immutable intent. Application code validates the accepted proposal Event/hash, Objective and Team ownership, action support, dependencies (which may cross Workstreams and Visions), applicable TeamPolicy constraints, and budget envelope. R5 does not invent, omit, partition, or reinterpret accepted strategy structure without explicit authority. The Plan, all initial ordinary Tasks, and attributable creation Event commit atomically. The creating Task's existing `policy_version` records the policy considered; no separate Plan policy pin is introduced. Later operations use their applicable policy version, without rewriting existing Plan intent or Task policy semantics. Replacing a Plan creates the new Plan and stops the old active Plan as `superseded` in the same transaction.

### Step 6 — Task execution admission

Each immutable Plan action has a stable identity and Vision/Workstream provenance; its Task carries nullable `plan_id` and `plan_action_id` provenance. The existing Task admission/claim path must not start a dependent Task until all prerequisite action Tasks are `done`. A failed prerequisite keeps dependent work ineligible until the Plan is stopped or replanned. This adds no Task state or separate scheduler. Once admitted, the ordinary Task execution path is unchanged. Enforce `TeamPolicy ceiling > Plan envelope > Task budget`; Plan allocations, including remaining unallocated budget, stay within the envelope, and each Task's own budget governs execution.

### Step 7 — Worker execution

A Worker executes one Task.

### Step 8 — Proposal

Worker returns proposals and observations.

### Step 9 — Commit

Kernel validates and atomically commits valid proposals.

### Step 10 — Outcome

Where the task has an observable external result, record an Outcome.

### Step 11 — Re-assessment and Plan lifecycle

The Control layer may determine that:

- the Objective is complete,
- more Tasks are required,
- the Strategy failed,
- the Plan should stop,
- a new Plan should be created.

Plan lifecycle is `active → completed | stopped`; terminal Plans cannot reopen. Stopping records `abandoned`, `invalidated`, or `superseded`. Progress is derived from Tasks. Completion is an explicit application-controlled transition and requires every intended action's one linked Task to be `done` and the declared completion condition to be satisfied by durable records. Replanning creates a new Plan; supersession atomically creates the replacement and stops the prior Plan without changing its intent.

### Objective mutation contract for R2

R2 provides Task-attributed operations for Objective creation and legal
status transitions. A Trigger initiates a Task for such a mutation; it does
not bypass Task attribution. The Task and Objective must have the same Team,
and the operation passes the existing scope, budget, deterministic validation,
and Kernel commit boundary.

A successful Objective mutation and its attributable Event commit atomically
and record enough information to reconstruct the committed transition. A
rejected mutation leaves Objective state unchanged and produces an auditable
rejection Event with a stable reason/category. Retrying the same successful
mutation from the same Task cannot double-commit it. Revalidate expected
Objective state at commit; reject stale/conflicting transitions rather than
silently overwriting them. Event names, reason-code strings, rejection
transaction structure, rejection-Event reuse, and the database concurrency
mechanism remain open implementation choices.

## 4. Worker isolation

A Worker receives:

- Task identity
- bounded context
- model/tool configuration
- budget
- required output schema
- optional Objective and Plan references

A Worker does not receive:

- unrestricted database access
- arbitrary Team secrets
- global unrestricted conversation history
- authority to bypass Kernel services

## 5. Context construction

Context is assembled deterministically from:

- Task
- Objective (if any)
- relevant Plan (if any)
- StateAssessment basis provenance (historical basis used for this Plan, when applicable)
- authoritative entities
- selected TeamPolicy
- bounded Team memory

The context builder should output:

```text
context_payload
context_refs[]
context_hash
```

The hash is associated with the Task.

## 6. Execution provenance

For every model-driven Task, record enough information to answer:

> What did the Worker see, what model/configuration produced the proposal, and what did the system commit?

Minimum execution metadata:

- Task id
- Objective id (if any)
- Plan id (if any)
- Worker kind
- model/provider
- model version
- prompt/template version
- context hash
- tool calls and tool outputs
- token usage
- cost
- proposal hash
- commit result
- code version

Full transcripts are optional execution artifacts, not team memory.

## 7. Failure classes

Failures should be distinguished.

### Validation failure

The Worker proposed something structurally invalid.

### Evidence failure

The proposed evidence could not be verified.

### Execution failure

The Task could not complete.

### Strategy failure

The chosen approach produced poor results despite valid execution.

### World-model failure

The team's Hypothesis was wrong or insufficient.

### Policy failure

TeamPolicy prevented a useful action or allowed a repeatedly bad method.

These distinctions matter for learning.

## 8. Replanning rules

Do not replan merely because a model “feels uncertain”.

Replan when:

- required preconditions fail,
- an Outcome materially changes relevant state,
- a stop condition is reached,
- a Task fails beyond retry policy,
- new evidence invalidates the Strategy basis,
- budget limits are reached,
- human consultation changes the available path.

Replanning creates a new Plan. The old Plan remains audit history and is not silently mutated.

## 9. Restart semantics

A crashed runtime should recover by reading:

- Plan state (if any)
- Task state
- Events
- authoritative entities

It should not require a model transcript to understand where it was.

Because the Control layer converges into ordinary Tasks, recovery starts from Task/Plan/Events, not from a planner-specific checkpoint. Plan creation and all initial Tasks commit atomically, so durable state contains either no Plan from that attempt or the complete initial Plan, Tasks, and creation Event. For each action, stable identity and the unique Plan/action Task mapping let recovery distinguish intended work from existing execution without transcripts or regeneration. Policy version on the creating Task records the version considered at Plan creation; later operations use their applicable policy version, and no policy change rewrites Plan intent or existing Task semantics.

## 10. Trigger integration

Triggers are retained.

A Trigger may:

1. directly create a Task when the response is deterministic (e.g., `apply_decay`);
2. create or activate an Objective when the situation requires deliberation.

The scheduler fires both kinds of Triggers. The execution runtime treats all created Tasks the same way.
