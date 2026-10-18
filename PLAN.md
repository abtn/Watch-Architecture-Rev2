# PLAN.md — Watch Architecture Revision

## Objective

Establish the revised architecture first, then implement the smallest executable slice that proves the new Control layer without destabilizing the existing Kernel principles.

The Control layer is introduced only after the Kernel tooling and basic Task/Proposal/Commit semantics are working.

Milestone status:
R1 — Complete
R2 — Complete
R3 — Complete
R4 — Redesigned implementation present; focused exit verification passed on the current R5 worktree; formal closure pending
R5 — Paused pending formal R4 closure and R5 entry gate

Implementation status:
K0, K1, and redesigned R4 implementation present; focused R4 verification recorded against the current R5 worktree; R4 not formally closed; R5 not released

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

## Phase R4 — Strategy proposal boundary (redesigned implementation; formal closure pending)

R4 reopened for the redesigned multi-perspective Strategy contract. The implementation is present on this R5 branch; the technical verification result is recorded below. Formal closure remains subject to the milestone sequence in `AGENTS.md`.

One accepted StrategyProposal is one coordinated strategic decision for one Objective and a particular historical StateAssessment basis. It may contain multiple concurrent Visions, Workstreams, Actions, and explicit Action-to-Action prerequisites. Strategy acceptance means deterministic legality and authorization for later Plan materialization; it does not establish wisdom or effectiveness.

- A Vision is a bounded strategic perspective with meaningful scope and boundaries.
- A Workstream groups coherent related Actions for human comprehension; it is not an execution or dependency boundary.
- An Action is purposeful intended work, not conceptually a Task.
- Dependencies may cross Workstreams and Visions when required; validate explicit same-Strategy targets, reject self-dependencies and cycles.
- One Objective initially has one active accepted Strategy; its Visions can proceed concurrently.
- Initially, one accepted Strategy for one Objective produces one Plan. R5 must not invent, omit, repartition, or reinterpret accepted strategic structure without explicit authority.
- Preserve stable identities and provenance through Vision, Workstream, Action, Plan, Task, Outcome, and Evaluation. Strategy/Vision/Workstream/Action do not thereby require standalone durable entities.
- A Strategy may identify capability gaps, but Team/capability changes are a separate proposal path requiring human review before durable structural change.

The model may propose the coordinated strategic structure, subject to deterministic validation. It may not:

- mutate TeamPolicy or Team structure directly
- directly create arbitrary database rows
- bypass Task scope
- invent unsupported capabilities or entity writes
- self-authorize tools
- raise its own budget
- commit durable state

The model may not:

- mutate TeamPolicy
- directly create arbitrary database rows
- bypass Task scope
- invent unsupported entity types
- self-authorize tools
- raise its own budget

Exit:

- approved structured proposal contract covers multiple Visions, Workstreams, Actions, and Action prerequisites
- deterministic validation and rejection tests cover structure, identity, ownership, capability, budget, and acyclic dependencies
- accepted means a validated strategic decision authorized for later Plan materialization, not proof of wisdom/effectiveness
- exact accepted structure is recoverable from canonical Task-attributed Event provenance without transcript, process memory, or regeneration
- preserve proposal hash, assessment basis references/hash/timestamp/payload, replay/idempotency, stale/conflict protection, and proposal-only worker authority
- initial implementation is bounded to a valid one-Vision/one-Workstream/one-Action subset; its configured `ingest_source` limitation is implementation scope, not the architecture definition

The redesigned R4 implementation is present at commit `50e288a`; its focused exit verification was run on the current R5 working tree. `uv run pytest tests/test_strategy.py` passed (44 tests), and targeted Ruff, `uv run mypy core`, and `git diff --check` passed. The full suite and R5-specific tests were not run. To provide an initialized isolated PostgreSQL test database, Alembic setup migrations reached `0006_immutable_plan_actions`; this is environment setup evidence, not an independent R4 exit criterion. Verification does not itself formally close R4 or authorize R5. No R5 implementation may invent, omit, or reinterpret the accepted Strategy structure.

## Phase R5 — Bounded Plan generation (paused pending formal R4 closure and R5 authorization)

Once R4 formal closure and implementation are complete, derive one durable Plan for the Objective from its one active accepted Strategy. Preserve the accepted multi-Vision/Workstream/Action structure and dependencies as immutable execution intent; R5 must not invent, omit, partition, or reinterpret it without explicit authority. A Plan is not execution history, Strategy memory, StateAssessment, a workflow engine, or a second runtime.

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
