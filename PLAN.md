# PLAN.md — Watch Architecture Revision

## Objective

Establish the revised architecture first, then implement the smallest executable slice that proves the new Control layer without destabilizing the existing Kernel principles.

The Control layer is introduced only after the Kernel tooling and basic Task/Proposal/Commit semantics are working.

R0 status:
Complete

Current phase:
R1 — Control-layer compatibility design

First Control-layer implementation phase:
R2 — Objective model

Implementation status:
K0 complete; K1 implemented

Historical terminology:
M0

## Phase K0 — Kernel baseline (tooling)

Before any Control-layer code, establish the project skeleton and deterministic test harness.

Deliver:

- Python 3.12+ virtual environment
- dependency lock file
- Postgres + pgvector via Docker Compose
- Alembic migration runner
- pytest baseline
- ruff and mypy baseline
- project layout (`core/`, `migrations/`, `tests/`)

Exit verification:

```text
docker compose up -d
alembic upgrade head
pytest
ruff check .
mypy core
```

No Control-layer entities in this phase.

## Phase K1 — Smallest Kernel commit path

Implement the smallest entity/commit path that proves:

```text
Proposal → Validation → Atomic commit → Event
```

No model calls.

Choose one existing Kernel concept (for example, a single Team lifecycle transition or a Signal ingestion with Snapshot storage). Implement:

- model/entities
- repository
- deterministic validation
- commit service
- Event emission
- invariant tests

Exit:

- one green end-to-end commit path
- tests for idempotency and invalid proposals
- existing invariants preserved

## Phase R0 — Architecture freeze for the revision

Deliver:

- `docs/01-architecture-revision.md`
- `docs/02-control-layer.md`
- `docs/03-runtime-model.md`
- `docs/04-data-model-changes.md`
- ADR-0023..0026
- migration notes
- test strategy

Exit:

- no unresolved contradiction between State, TeamPolicy, Strategy, Plan, Task, and Worker
- new vocabulary is stable
- explicit non-goals exist
- dual-entry execution model documented

## Phase R1 — Control-layer compatibility pass

Before adding new Control-layer runtime behavior, inspect the original entity/state model and design the additive Objective/Plan integration.

Deliver:

- written migration decision
- one durable Objective schema and explicit lifecycle (no ephemeral task-scoped Objective)
- Plan schema design
- Task integration design (optional Objective/Plan references, no state-machine change)
- StateAssessment provenance design (references, hash, timestamp, immutable Snapshot only when needed)
- budget validation design: TeamPolicy ceiling > Plan envelope > Task budget
- Trigger integration design (Trigger may create Task directly or create/activate Objective)
- tests for any new invariants

Exit:

- written compatibility decision
- tests for new invariants
- no Control-layer code yet beyond design

## Phase R2 — Objective model

Implement the first Control-layer durable entity.

Deliver:

- one durable Objective model
- repository
- explicit state machine (`draft → active/cancelled`; `active → paused/blocked/completed/cancelled`; `paused → active/cancelled`; `blocked → active/cancelled`; completed/cancelled terminal)
- validation
- Events
- migration
- invariant tests

Exit:

```text
Objective is one durable entity
all specified lifecycle transitions work
unspecified transitions fail
completed and cancelled are terminal
every transition emits Event
```

## Phase R3 — Deterministic StateAssessment

Build a read-only StateAssessment service.

Input:

- Team
- Objective
- authoritative world memory
- Team memory
- TeamPolicy
- outstanding Tasks/Plans
- relevant Events

Output:

- current state summary
- unresolved questions
- contradictions
- stale areas
- blocked work
- candidate opportunities
- basis refs and basis hash

Important:

The first version should be deterministic and code-assembled wherever practical. LLM assistance can be added later.

Exit:

- identical authoritative state produces reproducible assessment data
- when a Strategy/Plan is selected, exact assessment basis references, hash, and timestamp are preserved; immutable Snapshot is used only if required to reconstruct the exact payload
- historical decision basis remains distinct from any later assessment of current state
- no projection is treated as authoritative
- no writes to world/team memory

## Phase R4 — Strategy proposal boundary

Introduce a model-facing strategy proposal interface.

The model may propose:

- objective decomposition
- investigation strategy
- information-gathering needs
- suggested Task types
- ordering constraints
- stop conditions

The model may not:

- mutate TeamPolicy
- directly create arbitrary database rows
- bypass Task scope
- invent unsupported entity types
- self-authorize tools
- raise its own budget

Exit:

- StrategyProposal schema
- deterministic validation
- rejection tests
- persisted audit trail for accepted/rejected proposals
- accepted means a legal candidate, not Strategy selection or Plan creation
- exact accepted candidate is recoverable from canonical Event provenance
  without a transcript, process memory, or regeneration
- ordinary Task attribution; application/Kernel-only disposition Events
- preserve derived R3 basis references, hash, timestamp, and exact audit context

The first R4 slice is bounded to one configured `ingest_source` candidate,
no tools and zero cost. Other capabilities remain rejected rather than
implicitly implemented. R5 selects a candidate and creates a Plan later.

## Phase R5 — Bounded Plan generation

Convert an accepted R4 StrategyProposal into a durable Plan: bounded execution intent for exactly one Objective, not execution history, Strategy memory, StateAssessment, a workflow engine, or a second runtime.

Each immutable intended action has a stable identity and maps to zero or one Task before materialization, then exactly one ordinary Task. `Task.plan_id` and `Task.plan_action_id` are nullable provenance; when set they identify an action in that Plan, obey Team/Objective ownership, and are unique per Plan/action pair. Plan creation, all initial Tasks, and the creation Event commit atomically. No partial-materialization state is defined.

Preserve accepted proposal and assessment provenance; immutable action definitions and identities; dependencies; budget envelope; and completion/stop conditions. The creating `create_plan` Task's existing `policy_version` records the policy used for validation; no separate Plan policy pin is added. Later operations use their applicable policy version; policy changes do not rewrite Plan intent or alter existing Task semantics.

Dependencies are same-Plan prerequisites between actions. Validate targets, reject self-dependencies and cycles, and enforce admission in the existing Task claim path: a Plan-linked Task cannot start until each prerequisite Task is `done`. Failed prerequisites keep dependents ineligible until stop or replan; no Task state or separate scheduler is added.

Plan lifecycle is `active → completed | stopped`; terminal states cannot reopen. `stopped_reason` is `abandoned`, `invalidated`, or `superseded`. Progress is derived from Tasks. Completion requires every intended action to have exactly one linked Task in `done` and the declared completion condition to be satisfied by durable records. Completion/stopping is an explicit application-controlled transition. Supersession atomically creates a new Plan referring to the old and stops the old Plan as superseded. Substantial replanning never edits prior intent.

Plan creation uses a narrowly scoped `create_plan` operation: worker proposal → application validation → Kernel/application commit. It validates accepted proposal Event/hash, Objective/Team ownership, supported actions, acyclic dependencies, policy constraints, budget limits, and retry/idempotency; it may create only the Plan, initial ordinary Tasks, and scoped audit Event(s). No TeamPolicy, memory, Strategy, or StateAssessment writes.

Exit:

- one bounded Plan and its initial ordinary Tasks commit atomically and run through the existing Task runtime
- accepted proposal and historical assessment basis are reconstructable
- action identity, uniqueness, retry, and concurrent creation behavior are tested
- prerequisite admission is enforced without changing Task states
- completion, stopping, and supersession preserve immutable intent
- restart reconstruction requires only durable Plan/Task/Event state

## Phase R6 — First intelligent control loop

End-to-end:

```text
Objective
  ↓
StateAssessment
  ↓
StrategyProposal
  ↓
validated Plan
  ↓
Task materialization
  ↓
Task execution
  ↓
Kernel commit
  ↓
Outcome
  ↓
new StateAssessment / replan or stop
```

Use one domain and one real but bounded scenario.

Exit:

- system can explain why a Task exists
- system can resume after worker death
- no shared transcript is required
- both reactive and deliberative paths are demonstrated

## Phase R7 — Evaluation and learning integration

Extend the existing Outcome → Evaluation → LearningChange path so that evaluation can distinguish:

- world-model failure
- strategy failure
- execution failure
- evidence failure
- policy/constraint failure

A learning change should be able to target the correct layer.

Exit:

- a real failure can revise a method without silently modifying world memory
- Strategy remains distinguishable from TeamPolicy
- learning changes do not mutate policy automatically

## Phase R8 — Multi-domain pressure test

Use:

- newsroom
- devteam

and a lightweight generalist configuration.

The question is not “does it run?”

The question is:

> Does the same Control model work while domain-specific data and heuristics stay outside the Kernel?

## Phase R9 — Codex-assisted production workflow

Once R3-R6 are stable:

- codify implementation task packets
- add architecture-aware repository instructions
- use Codex for bounded vertical slices
- require test-first changes
- keep design decisions in ADRs
