# Watch — Architecture Revision 2

Watch is an evidence-oriented system for maintaining an auditable model of a
team's world and supporting bounded, explainable work. Its Kernel owns durable
state: workers propose changes, application code validates them, and committed
state is recorded with Task provenance and Events.

## Development status

**K0 is complete. K1 is implemented on `main`.** K1 is the first executable
Kernel slice; it proves deterministic source ingestion without model calls:

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

The Control layer is specified but not implemented. Objective, StateAssessment,
StrategyProposal runtime, Plan, autonomous planning, and LLM integration are
out of scope for K1 and remain later work.

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

### Task write scopes: W / C / K

The Task scope matrix in [`docs/tasks.md`](docs/tasks.md) distinguishes:

- **W** — a worker-proposable business/domain write, checked against the
  Task's `allowed_writes`.
- **C** — a controlled create/write operation explicitly defined by a Task
  specification.
- **K** — an exact, bounded Kernel-managed side effect, performed by
  application code and attributable to the Task.

For K1 `ingest_source`, Signal is `W`; its associated immutable Snapshot and
Task-attributed Event are `K`. K is part of scope enforcement, not an
exception to INV-14 or permission for a worker to create arbitrary Snapshots,
Events, or other records.

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
core/                       K1 models, ingestion, and Snapshot storage
migrations/                 Alembic environment and schema revisions
tests/                      PostgreSQL and K1 integration tests
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
uv run pytest tests/test_ingestion.py
uv run ruff check .
uv run mypy core
uv run pytest
```

The tests use PostgreSQL. They accept `TEST_DATABASE_URL` or `DATABASE_URL`;
otherwise they connect to the Compose default database at
`postgresql+psycopg://watch:watch@localhost:5432/watch`.

To verify the K1 migration round trip, use a **disposable** database:

```powershell
uv run alembic downgrade 0001_enable_pgvector
uv run alembic upgrade head
```

Do not run the downgrade against a database containing data that must be
preserved. The K1 downgrade removes K1 tables but must leave the pre-existing
pgvector extension in place.

## Milestones and documentation

K1 is complete; subsequent implementation remains gated by the milestone
plan and architecture decisions. In particular, do not treat the architecture
specification as authorization to implement later Control-layer behavior.

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
| [`docs/decisions/ADR-0026-dual-entry-execution-model.md`](docs/decisions/ADR-0026-dual-entry-execution-model.md) | Reactive and deliberative execution paths |
| [`AGENTS.md`](AGENTS.md) | Repository instructions for implementation work |
