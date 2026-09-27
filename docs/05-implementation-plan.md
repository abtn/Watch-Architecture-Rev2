# Implementation Plan for the Revised Architecture

## Guiding principle

Do not rewrite the entire project.

Do not implement the Control layer before the Kernel is working.

Make the smallest architectural change that proves the new Control model while preserving the existing reactive execution path.

## Slice K0 — Repository and test harness

Goal:

- create the project skeleton
- establish a deterministic test suite
- preserve original invariants

Codex should not implement Control logic here.

Deliver:

- Python 3.12+ virtual environment
- dependency lock file
- Postgres + pgvector via Docker Compose
- Alembic migration runner
- pytest baseline
- ruff and mypy baseline
- project layout (`core/`, `migrations/`, `tests/`)

Acceptance:

```text
docker compose up -d
alembic upgrade head
pytest
ruff check .
mypy core
```

## Slice K1 — Smallest Kernel commit path

Implement the smallest entity/commit path that proves:

```text
Proposal → Validation → Atomic commit → Event
```

No model calls.

Choose one existing Kernel concept (e.g., a Team lifecycle transition or Signal ingestion with Snapshot storage). Implement model, repository, deterministic validation, commit service, Event emission, and invariant tests.

Acceptance:

- one green end-to-end commit path
- tests for idempotency
- invalid proposals rejected with Events
- existing invariants preserved

## Slice R1 — Control-layer compatibility design

Before writing Control-layer code:

- inspect the original entity/state model and apply the `CHANGE_MAP.md` authority rules
- design one durable Objective entity and its explicit lifecycle; do not add an ephemeral task-scoped Objective
- design Plan schema and optional `objective_id` / `plan_id` on Task
- specify reconstructable StateAssessment provenance (references, hash, timestamp, and Snapshot only when needed)
- define budget checks: TeamPolicy ceiling > Plan envelope > Task budget
- decide Trigger integration (direct Task vs. Objective creation)
- identify which existing entities can represent Objective/Strategy/Plan concepts
- avoid schema additions where a derived representation is sufficient
- create only the smallest new durable entities required by actual invariants

Deliver:

- written migration decision
- tests for any new invariants
- no Control-layer runtime code yet

## Slice R2 — Objective model

Implement one durable Objective entity with its explicit lifecycle; Tasks may reference it, but no second ephemeral Objective abstraction exists.

Implement:

- Objective model
- repository
- state machine (`draft → active/cancelled`; `active → paused/blocked/completed/cancelled`; `paused → active/cancelled`; `blocked → active/cancelled`; completed/cancelled terminal)
- validation
- Events
- migration
- invariant tests

Acceptance:

```text
Objective is one durable entity
all specified lifecycle transitions work
unspecified transitions fail
completed and cancelled are terminal
every transition emits Event
```

## Slice R3 — Read-only StateAssessment

Implement:

```text
StateAssessmentBuilder.build(objective_id)
```

No LLM.

Acceptance:

- reads authoritative records
- records basis refs, hash, and creation timestamp
- preserves the exact assessment basis when a Strategy/Plan is selected, using an immutable Snapshot if references and hash alone are insufficient
- produces stable structured output
- does not write world/team memory or become an authoritative state store
- projections are not required for correctness

## Slice R4 — Strategy proposal boundary

Implement:

- `StrategyProposal` Pydantic schema
- validator
- FakeStrategyWorker
- proposal audit Events

Acceptance:

- valid strategy accepted
- invalid Task type rejected
- budget escalation rejected
- forbidden tool rejected
- policy bypass rejected

## Slice R5 — Plan materialization

Implement:

```text
StrategyProposal
    ↓
Plan
    ↓
Task[]
```

Plan materialization simply creates ordinary Tasks. Those Tasks then use the existing Task execution path.

Acceptance:

- dependencies are explicit
- Plan budget is within applicable TeamPolicy ceiling
- aggregate allocated/remaining Task budgets stay within Plan envelope
- each Task budget governs individual execution
- stop conditions are explicit
- Plan can be inspected after restart
- Plan is execution intent; Tasks/Events/Outcomes remain authoritative

## Slice R6 — One intelligent vertical slice

Use one scenario only.

Example:

```text
Objective:
Verify whether a current Thread requires independent evidence.

State:
Two competing Hypotheses.

Strategy:
Search an independent source.

Plan:
1. search_source
2. triage_signal
3. update_thread
```

Acceptance:

- system explains task purpose
- model output is bounded
- Kernel commits valid proposal
- invalid proposals are visible
- runtime can restart between tasks

## Slice R7 — Replanning

Create a deliberate failure:

```text
Plan A
  ↓
source unavailable
  ↓
Task failure
  ↓
new assessment
  ↓
Plan B
```

Acceptance:

- Plan A remains history
- Plan B points to the reason for replanning
- no silent mutation of Plan A

## Slice R8 — Learning integration

Add classification:

```text
world_failure
strategy_failure
execution_failure
evidence_failure
policy_failure
```

Do not automatically modify policy.

First measure.

## Slice R9 — Real model

Only now connect a real model.

Use:

- bounded context
- structured output
- strict proposal schema
- explicit cost limit
- context hash
- execution provenance

## Slice R10 — Domain pressure test

Run the same Control layer against:

- newsroom
- devteam

The goal is to discover where the Kernel is truly domain-independent.
