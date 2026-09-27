# Test Strategy

## 1. Test the architecture, not only the code

Watch needs tests for the boundaries that make the architecture trustworthy.

## 2. Kernel baseline tests (K0/K1)

Before Control-layer tests exist:

- migration up/down roundtrip
- pytest baseline
- ruff and mypy clean
- one end-to-end commit path with Event emission
- idempotency under retry
- invalid proposal rejection with Event

## 3. Existing invariant tests

Preserve the existing invariant suite:

- INV-01 through INV-15

## 4. Control-layer invariant tests

Add tests that prove the dual-entry model:

### Dual-entry convergence

- A Task created by Plan materialization uses the same state machine as a reactive Task.
- A reactive Task can still be created without an Objective or Plan.
- A Plan cannot bypass Kernel commit validation.
- Plan membership is optional at the Task level.

### Objective state transitions

- Objective is one durable entity; no task-scoped ephemeral Objective exists
- legal transitions succeed: `draft → active/cancelled`; `active → paused/blocked/completed/cancelled`; `paused → active/cancelled`; `blocked → active/cancelled`
- `completed` and `cancelled` are terminal
- invalid transitions fail
- every transition emits Event

### StateAssessment determinism

Same authoritative inputs → same assessment basis and basis hash.

### StateAssessment provenance

- StateAssessment remains derived and non-authoritative
- when a Strategy/Plan is selected, basis references, hash, and creation timestamp are preserved
- an immutable Snapshot preserves the exact payload when references and hash alone are insufficient
- a later assessment from current state does not overwrite historical decision context

### Budget hierarchy

- Plan budget does not exceed the applicable TeamPolicy ceiling
- sum/remaining allocation of materialized Task budgets does not exceed the Plan envelope
- each Task's actual execution is bounded by its own authoritative Task budget
- reactive Tasks without a Plan still obey their Task budget and TeamPolicy ceiling

### Strategy validation — can validate

Accept:

- known Task types
- allowed tools
- budgets within policy
- valid dependencies
- references to existing entities
- acyclic dependency graphs

Reject:

- unknown Task types
- unknown tools
- budget escalation
- invalid dependencies
- cycles
- forbidden policy changes
- missing Objective
- references to non-existent entities

### Strategy validation — cannot validate

Tests document that validation does not judge strategic wisdom:

- a valid StrategyProposal may still produce poor outcomes
- a bad Strategy is corrected through Outcome → Evaluation → Learning, not through proposal rejection

### Plan semantics

- dependencies are explicit
- budget is bounded
- stop conditions are explicit
- Plan can be inspected after restart
- Plan may be partially completed, abandoned, or superseded without corrupting Task/Events/Outcomes
- replanning creates a new Plan; old Plan remains history

## 5. Failure tests

Deliberately create:

1. source unavailable
2. invalid Worker proposal
3. concurrent state change
4. expired evidence
5. Task retry
6. partial Plan progress
7. runtime restart
8. changed Objective state
9. Strategy no longer applicable
10. Plan materialization creates invalid Task

The system should react deterministically and preserve history.

## 6. Learning tests

Verify that:

- execution failure does not become a world-model change automatically
- world-model failure does not silently rewrite TeamPolicy
- Strategy failure can be recognized as Strategy failure
- LearningChange remains the only route to Team memory
- policy/constraint failure is classifiable in Evaluation

## 7. Trigger integration tests

- deterministic Trigger directly creates a Task
- deliberative Trigger creates/activates an Objective
- a single Trigger condition cannot do both simultaneously without explicit policy
- Trigger-created Objective eventually produces ordinary Tasks

## 8. Golden trace

Create one small “golden trace” for each path.

### Reactive golden trace

```text
Trigger
Task
Worker
Proposal
Commit
Event
Outcome
```

### Deliberative golden trace

```text
Objective O1
StateAssessment SA1
StrategyProposal SP1
Plan P1
Task T1
Task T2
Outcome O2
StateAssessment SA2
Plan P2
```

Each trace should be reconstructable from the database after killing the runtime.

## 9. Codex acceptance rule

Every Codex implementation task must add or update tests that prove the requested architectural behavior.

A task that only “looks correct” is not complete.

Kernel slices must be green before Control-layer slices are accepted.
