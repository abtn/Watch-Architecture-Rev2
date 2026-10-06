# Watch — Architecture Revision 2

Watch is an evidence-oriented system for maintaining an auditable model of a
team's world and supporting bounded, explainable work. Its Kernel owns durable
state: workers propose changes, application code validates them, and committed
state is recorded with Task provenance and Events.

## Development status

**R0 is complete. R1 is complete. R2 is implemented, audited, and merged into
`main`. R3 is the current phase: Deterministic StateAssessment.**

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

R2 was then subjected to an adversarial implementation audit. One genuine
contract gap was found and corrected: Operator identity is now carried in
Objective Events when supplied. Final verification reported 49 Objective tests,
17 K1 ingestion tests, 67 total tests, passing Ruff and mypy, and a successful
migration downgrade/upgrade round-trip.

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

### StateAssessment

StateAssessment is derived and non-authoritative. R3 must distinguish the
current assessment from the historical decision basis that future Strategy/Plan
selection may need to preserve. Assessment provenance is expected to use
reconstructable references, a basis hash, and a creation timestamp; an
immutable Snapshot is used only when references and hash are insufficient to
reproduce the exact historical assessment payload.

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
core/                       K1 ingestion + R2 Objective implementation
migrations/                 Alembic environment and schema revisions
tests/                      K1 and R2 PostgreSQL integration tests
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

R2 is complete and merged into `main`. R3 is the current implementation phase.
Each Control-layer milestone remains gated by its preflight/design work and
must preserve the previous milestone's contracts.

| Phase | Status | Purpose |
|---|---|---|
| K0 | Complete | Repository tooling and deterministic test harness |
| K1 | Complete | Smallest executable Kernel ingestion path |
| R0 | Complete | Revision 2 architecture freeze |
| R1 | Complete | Control-layer compatibility contract |
| R2 | Complete | Durable Objective model and lifecycle |
| R3 | Current | Deterministic, read-only StateAssessment |
| R4 | Later | StrategyProposal boundary |
| R5 | Later | Bounded Plan generation/materialization |
| R6 | Later | First intelligent Control loop |
| R7 | Later | Evaluation and learning integration |
| R8 | Later | Multi-domain pressure test |
| R9 | Later | Real model integration / production workflow |
| R10 | Later | Domain pressure testing |

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

