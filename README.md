# Watch — Architecture Revision 2

Watch is an evidence-oriented system for maintaining an auditable model of a
team's world and supporting bounded, explainable work. Its Kernel owns durable
state: workers propose changes, application code validates them, and committed
state is recorded with Task provenance and Events.

## Development status

**K0–R4 are complete. R4 is implemented, audited, committed, pushed, and merged
into `main`. R5 is now the active phase: Bounded Plan generation design.**

Current repository position:

```text
R3
 ↓
Deterministic StateAssessment
 ↓
R4
 ↓
StrategyProposal → deterministic validation → durable audit
 ↓
main
 ↓
R5
 ↓
Plan boundary design gate
```

The next milestone is intentionally still in the design/reality stage. R5 will
turn a selected, validated strategy candidate into durable execution intent,
while keeping Plan state distinct from actual Task/Event/Outcome history.

R2 introduced the first durable Control-layer entity while preserving the
existing Kernel and K1 execution boundaries:

```text
Objective
  ↓
Task-attributed mutation
  ↓
deterministic validation
  ↓
atomic Objective + Event commit
```

R2 delivered:

- one durable Objective with Team ownership and an explicit lifecycle;
- nullable `Task.objective_id` with same-Team database enforcement;
- Task-attributed Objective creation and lifecycle transitions;
- deterministic validation, rejection audit, same-Task replay, and concurrent
  transition protection;
- migration `0003_objectives`;
- focused Objective integration tests.

R2 was subjected to an adversarial implementation audit. The final R2
verification preserved the Kernel and K1 boundaries and established Objective
as the first durable Control-layer entity.

R3 then added a deterministic, read-only StateAssessment over authoritative
records that actually exist in the repository.

R3 delivered:

- Objective-scoped operational state reconstruction;
- deterministic basis references and SHA-256 basis hashing;
- explicit separation between Task scope and Event provenance;
- read-only, repeatable assessment construction;
- focused tests for scope isolation, determinism, provenance, and
  non-authoritative behavior.

R3 introduced no Strategy, Plan, memory, or LLM runtime.

R4 then added the first model-facing Control boundary without turning Strategy
into durable memory:

```text
Objective
   ↓
StateAssessment
   ↓
transient StrategyProposal
   ↓
deterministic validation
   ↓
accepted / rejected disposition
   ↓
durable Task-attributed audit
```

R4 delivered:

- a transient typed `StrategyProposal`;
- a deterministic fake producer;
- deterministic proposal validation;
- a narrowly scoped proposal Task operation;
- Task-attributed accepted/rejected audit Events;
- canonical proposal persistence and SHA-256 integrity verification;
- exact accepted-proposal reconstruction without the original model transcript;
- assessment-basis provenance preservation;
- idempotent replay and conflict/stale-authority protection;
- no Strategy or Plan durable entity;
- no Plan materialization or second execution runtime.

For the first executable R4 slice, the supported candidate capability is
deliberately narrow: `ingest_source`, with no requested tools and zero added
cost. This is a current implementation boundary, not a permanent architectural
limit.

R4 was adversarially audited and verified with 111 tests on a fresh migrated
PostgreSQL database, plus focused R3/R4 verification. Ruff, mypy, and
`git diff --check` passed. R4 was then merged into `main`.

R3 is now the next Control-layer slice:

```text
Objective
   ↓
deterministic StateAssessment
```

R3 is a read-only, derived, reproducible assessment service. Its preflight/design
gate must first establish the smallest coherent executable assessment surface
from authoritative state that actually exists in the repository. It must not
invent missing domain infrastructure.

The first R3 version contains no LLM, StrategyProposal, Plan, autonomous Control
loop, Trigger runtime, scheduler changes, or second execution/commit system.

K1 remains the first executable Kernel slice and proves deterministic source
ingestion without model calls:

```text
fetched bytes
    ↓
transient IngestionProposal
    ↓
deterministic validation
    ↓
immutable local Snapshot
    ↓
atomic PostgreSQL commit: Signal + Event
```

The K1 path validates the running `ingest_source` Task, active Team, TeamPolicy
version and configured source, Signal write scope, content hash, and proposal
preconditions. Duplicate content is a no-change result; a matching retry
reuses its Task-attributed outcome Event. Invalid proposals are rejected with
a reason-bearing Event. The PostgreSQL Signal and success Event commit
together.

K1 deliberately does **not** implement source fetching/connectors, production
Team or Task bootstrap, Task scheduling or queue/runtime, Trigger execution,
triage, embeddings, or model calls. Test fixtures supply the prerequisite
active Team, source policy, and running Task. These are setup records, not
production lifecycle behavior.

## Architectural decisions

### Current Control-layer position

Watch currently stops at the boundary between **validated strategy candidates**
and **durable Plans**.

```text
R4
StrategyProposal
= valid candidate

R5
Plan
= durable execution intent
```

R4 does not select or execute a Strategy. R5 is responsible for representing
the selected candidate as a bounded Plan and later materializing ordinary Tasks
without changing the Task execution runtime.

### Kernel authority and Task execution

- Durable writes go through application validation and commit; workers do not
  write directly.
- Tasks are the execution unit. Reactive work remains valid without an
  Objective or Plan.
- A future deliberative Control path must materialize ordinary Tasks and use
  the same Task execution and Kernel commit path; it must not introduce a
  second runtime or commit kernel.
- Plans record intended execution, not execution truth. Tasks, Events, and
  Outcomes represent actual execution.
- StateAssessment is derived and non-authoritative.

### Objective authority and lifecycle

Objective is a durable Control-layer entity. Its lifecycle is explicit and
deterministically validated. Objective mutations are Task-attributed and pass
through application validation and the existing Kernel authority boundary.
Objective state and its corresponding successful Event commit atomically.

Objective is not TeamPolicy, Thread, Strategy, Plan, or Team memory. Its R2
schema is intentionally minimal; richer Objective semantics remain open unless
later milestones require them.

### Task write scopes: W / C / K

- **W** — a worker-proposable business/domain write, checked against the
  Task's `allowed_writes`.
- **C** — a controlled create/write operation explicitly defined by a Task
  specification.
- **K** — an exact, bounded Kernel-managed side effect, performed by
  application code and attributable to the Task.

For K1 `ingest_source`, Signal is `W`; its associated immutable Snapshot and
Task-attributed Event are `K`. For R2 Objective operations, Objective mutation
is explicitly authorized by the designated Task operation and Objective scope;
Objective state and success Events remain application-managed and
Kernel-validated.

### StateAssessment and decision provenance

StateAssessment is derived and non-authoritative. R3 distinguishes the current
assessment from historical decision provenance.

R4 preserves the assessment context used by a proposal through reconstructable
references, a basis hash, and a creation timestamp, with an immutable Snapshot
only when references and hash are insufficient to reproduce the exact payload.

An accepted R4 proposal means **valid candidate**, not selected Strategy.
Selection and durable Plan provenance belong to R5.

### Snapshot and commit boundary

K1 stores content outside PostgreSQL in a local, immutable, content-addressed
filesystem store, using references of the form
`snap://sha256/<64-lowercase-hex-digest>`. The object is written completely
before publication and is never overwritten. A failed database commit may
leave an unreferenced object; committed database records determine
Watch-domain visibility. K1 does not implement distributed transactions or
object garbage collection.

Duplicate identity is `(origin_url, content_hash)`, protected by a database
unique constraint. Matching Task retries use the Task's existing ingestion
outcome Event as their idempotency evidence; no Proposal or idempotency table
is introduced.

### Source-of-truth rules

Original Watch documents govern concepts that Revision 2 has not explicitly
revised. Revision 2 documents govern only the concepts mapped in
[`CHANGE_MAP.md`](CHANGE_MAP.md). Do not silently reconcile conflicting
specifications; stop and report the ambiguity. The architectural invariants
are listed in [`docs/invariants.md`](docs/invariants.md).

## Technology and repository layout

- Python 3.12+
- `uv` for dependency and command management
- PostgreSQL 16 with pgvector, via Docker Compose
- SQLAlchemy and Alembic
- pytest, Ruff, and mypy

```text
core/                       K1 ingestion + R2 Objective + R3/R4 Control slices
migrations/                 Alembic environment and schema revisions
tests/                      K1, R2, R3, and R4 PostgreSQL integration tests
docs/                       Architecture, invariants, task specs, and plans
PLAN.md                     Milestones and implementation order
CHANGE_MAP.md               Document authority mapping
```

## Local setup and verification

From the repository root:

```powershell
uv sync --python 3.12
docker compose up -d
uv run alembic upgrade head
uv run pytest tests/test_objectives.py
uv run pytest tests/test_ingestion.py
uv run ruff check .
uv run mypy core
uv run pytest
```

The tests use PostgreSQL. They accept `TEST_DATABASE_URL` or `DATABASE_URL`;
otherwise they connect to the Compose default database at
`postgresql+psycopg://watch:watch@localhost:5432/watch`.

To verify the R2 migration round trip, use a **disposable** database:

```powershell
uv run alembic downgrade 0002_ingestion_kernel
uv run alembic upgrade head
```

Do not run the downgrade against a database containing data that must be
preserved. This round-trip removes the R2 Objective schema and recreates it
without altering the earlier K1 migrations.

## Milestones and documentation

R4 is complete and merged into `main`. R5 is the current phase and is beginning
with a design/reality gate. Each Control-layer milestone remains gated by its
preflight/design work and must preserve the previous milestone's contracts.

| Phase | Status | Purpose |
|---|---|---|
| K0 | Complete | Repository tooling and deterministic test harness |
| K1 | Complete | Smallest executable Kernel ingestion path |
| R0 | Complete | Revision 2 architecture freeze |
| R1 | Complete | Control-layer compatibility contract |
| R2 | Complete | Durable Objective model and lifecycle |
| R3 | Complete | Deterministic, read-only StateAssessment |
| R4 | Complete | StrategyProposal boundary, validation, and durable audit |
| R5 | Current | Bounded Plan generation/materialization design |
| R6 | Later | First intelligent Control loop |
| R7 | Later | Evaluation and learning integration |
| R8 | Later | Multi-domain pressure test |
| R9 | Later | Codex-assisted production workflow |

In particular, the architecture specification is not, by itself, authorization
to implement later Control-layer behavior.

| Document | Purpose |
|---|---|
| [`PLAN.md`](PLAN.md) | Milestones and implementation order |
| [`CHANGE_MAP.md`](CHANGE_MAP.md) | Source authority and revision mapping |
| [`docs/architecture.md`](docs/architecture.md) | Original Watch architecture |
| [`docs/01-architecture-revision.md`](docs/01-architecture-revision.md) | Revision 2 architecture |
| [`docs/02-control-layer.md`](docs/02-control-layer.md) | Control-layer specification |
| [`docs/03-runtime-model.md`](docs/03-runtime-model.md) | Runtime and execution semantics |
| [`docs/04-data-model-changes.md`](docs/04-data-model-changes.md) | Data-model proposals and boundaries |
| [`docs/05-implementation-plan.md`](docs/05-implementation-plan.md) | K1 contract and later implementation sequence |
| [`docs/tasks.md`](docs/tasks.md) | Task behaviors, validation, budgets, and scope matrix |
| [`docs/invariants.md`](docs/invariants.md) | Non-negotiable system invariants |
| [`docs/10-test-strategy.md`](docs/10-test-strategy.md) | Architecture-focused test strategy |
| [`docs/decisions/ADR-0023-control-layer.md`](docs/decisions/ADR-0023-control-layer.md) | Control-layer boundary |
| [`docs/decisions/ADR-0026-dual-entry-execution-model.md`](docs/decisions/ADR-0026-dual-entry-execution-model.md) | Reactive and deliberative execution paths |
| [`AGENTS.md`](AGENTS.md) | Repository instructions for implementation work |

