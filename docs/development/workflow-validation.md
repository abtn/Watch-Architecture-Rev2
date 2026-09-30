# Workflow validation

Development-workflow simulations are a formal way to check whether a human
Operator and Codex can carry out important work safely and efficiently before
the implementation itself begins.

## When to simulate

Use a simulation before important implementation work, or when the workflow,
repository instructions, or task protocol changes. Simulations can expose
ambiguous terminology, missing instructions, inefficient inspection steps,
unclear ownership, and unsafe assumptions without requiring implementation.

A simulation may be inspect-only or may ask Codex to produce a proposed plan.
Respect the scenario's explicit boundary: a no-edit simulation must not modify
implementation files.

## Standard simulation record

Record each simulation chronologically, distinguishing expectations supported
by repository instructions from observed behavior. Include:

1. **Task/scenario** — the request being simulated and its intended boundary.
2. **Repository state** — relevant files, milestone, and pre-existing changes.
3. **Expected behavior** — cite documented expectations where available; mark
   any expectation not defined by the repository as unresolved rather than
   retroactively inventing it.
4. **Observed behavior** — what Codex actually inspected, changed, verified,
   or reported.
5. **Discrepancies** — ambiguity, missing guidance, mistakes, or explicit
   absence of a discrepancy.
6. **Lessons** — process improvements supported by the evidence.
7. **Resulting documentation changes** — files updated because of the
   simulation, or state that none were made. A simulation does not authorize
   architecture or implementation changes.

Append new records; do not rewrite historical observations. Do not describe a
workflow finding as an architectural fact unless an authoritative architecture
source establishes it.

## Recorded simulations

### 1. M0/K0 inspect-only request

- **Task/scenario:** The Operator requested an implementation-free inspection
  and a concrete account of how to implement “M0,” including files, assumptions,
  commands, required information, and expected final state.
- **Repository state:** The checkout was documentation-only. The then-inspected
  [`AGENTS.md`](../../AGENTS.md) and [`PLAN.md`](../../PLAN.md) identified K0
  as the current implementation milestone; the requested name M0 also appeared
  in historical workflow material.
- **Expected behavior:** The prompt explicitly required no implementation.
  The repository instructions required checking the current milestone and
  reporting ambiguity rather than silently selecting an authority.
- **Observed behavior:** Codex made no file changes, identified K0 as the
  current scope, distinguished that from the M0 wording, and described the
  K0 tooling plan and missing setup decisions.
- **Discrepancies:** The first request used M0 without defining whether it
  meant K0 or an older milestone label. Current
  [`PLAN.md`](../../PLAN.md) now explicitly labels K0 as current and M0 as
  historical terminology; older references such as
  [`docs/invariants.md`](../invariants.md) and
  [`docs/walkthrough.md`](../walkthrough.md) still use M0 in their own
  contexts. This is a terminology/workflow finding, not evidence of a Watch
  architectural conflict. Whether every older M0 item has been reassigned to
  K0 remains unspecified.
- **Lessons:** Name the current milestone explicitly in implementation requests.
  If a task relies on a historical milestone label, ask what scope is intended
  instead of assuming equivalence.
- **Resulting documentation changes:** This record captures the observed
  finding. It does not change milestone definitions or architecture.

### 2. K0 implementation-plan simulation

- **Task/scenario:** The Operator clarified that K0 was intended and requested
  a concrete implementation plan without file changes, including file-by-file
  justification, constraints, verification, failure modes, and human decisions.
- **Repository state:** K0 was the current milestone; the checkout had no
  application implementation, dependency manifest/lockfile, migrations,
  tests, or Compose configuration. Repository guidance did not define a
  package manager, install command, or initial migration scope.
- **Expected behavior:** Respect the no-edit boundary, follow K0 deliverables
  and acceptance commands, avoid Control and K1 work, and distinguish
  requirements from choices and unresolved decisions.
- **Observed behavior:** Codex made no file changes, outlined a proposed K0
  file set and verification sequence, and identified choices requiring
  Operator input rather than presenting them as established conventions.
- **Discrepancies:** The plan included suggested filenames and tooling layout
  as proposals, not documented requirements. Those proposals would require
  approval before implementation. No K0 setup or verification command was
  actually run.
- **Lessons:** For a plan-only task, clearly label proposed file paths and
  choices as provisional; do not turn a plan into approval to implement them.
  Report verification as planned, not passed.
- **Resulting documentation changes:** This record captures the observed
  workflow. No K0 implementation was performed.

### 3. Beginning-of-K1 implementation-planning simulation

- **Task/scenario:** The Operator explicitly authorized moving from K0 to K1
  and asked Codex to inspect the repository, compare the documented Team
  lifecycle and Signal-ingestion examples, and produce an implementation-ready
  plan without implementing K1. Only this validation record could be changed.
- **Repository state:** The checkout was on `main` at `1c8a536`, with a clean
  worktree. The K0 branch tip `6e7ff09` is an ancestor of `main` through merge
  commit `8d4dd59`. K0 setup files were present: `pyproject.toml`, `uv.lock`,
  `compose.yaml`, Alembic configuration, and a pgvector-extension migration.
  Application code consisted of `core/__init__.py`; the only test was a
  PostgreSQL pgvector-extension check. No application entity, Task, Event,
  repository, validation, or commit-service implementation was present.
- **Expected behavior:** The task prompt authorized K1 planning, not
  implementation. Repository workflow guidance requires respecting the
  Task/Proposal/Commit boundary, attributing durable writes to Tasks, emitting
  Events tied to Tasks, and stopping rather than inventing architecture when
  authority or requirements are ambiguous. K1 is documented to prove
  Proposal → Validation → Atomic commit → Event, with idempotency and rejected
  proposals recorded by Event.
- **Observed behavior:** Codex read the requested authority, planning,
  workflow, architecture, invariant, task, and ADR documents; inspected the
  current implementation and Git history; and made no implementation changes.
  Ruff and mypy passed. Alembic history showed only the pgvector extension
  revision. The pytest database check did not complete: it remained at the
  PostgreSQL test and was interrupted, so no pytest result is claimed.
  Inspection found that `Task` requires a Team and every Event requires a
  Task, while `create_team` itself creates the Team; the documents do not
  specify how that initial `create_team` Task is associated with a Team that
  does not yet exist. Signal ingestion also requires an active Team and Task
  provenance, neither of which is implemented in the current codebase.
- **Discrepancies:** The Operator's authorization supersedes the repository's
  default K0-only instruction for this planning task. The documented K1
  examples do not resolve the Task/Team bootstrap and provenance relationship,
  so the smallest self-contained candidate cannot be selected confidently
  without an additional architectural assumption. This is an unresolved
  implementation prerequisite, not a decision to change the Task model.
- **Lessons:** Before implementation, resolve how the initial team-creation
  operation receives Task provenance when Task requires a Team, and whether
  K1 may assume an already-existing active Team for Signal ingestion. Do not
  solve either issue by silently making `Task.team_id` nullable, bypassing
  Task attribution, or seeding durable application state outside the commit
  path. After that boundary is settled, compare the complete Task, Snapshot,
  Event, and idempotency requirements of the chosen vertical slice.
- **Resulting documentation changes:** This chronological record was appended.
  No K1 code, tests, migrations, milestone wording, or architectural decisions
  were changed.

### 4. Second K1 candidate and bootstrap reassessment

- **Task/scenario:** The Operator requested a second inspect-only simulation to
  test the previous conclusion that K1 could not select a candidate because
  Tasks belong to Teams while `create_team` creates the Team. The Operator
  explicitly authorized K1 planning, not implementation; this record is the
  only permitted change.
- **Repository state:** The checkout remained on `main` at `1c8a536`; K0 is
  merged into `main`. The only pre-existing worktree change was the K1
  simulation record above in this file. Application code remained limited to
  `core/__init__.py`, the database-extension test, and the pgvector Alembic
  migration; no Team, Task, Snapshot, Signal, or Event application model or
  runtime was present.
- **Expected behavior:** Re-read the authority, K1, Task, invariant,
  walkthrough, and dual-entry specifications; distinguish test prerequisites
  from production bootstrap and from the commit path being tested; compare
  `create_team`, `activate_team`, and `ingest_source`; do not implement K1 or
  infer an architectural exception.
- **Observed behavior:** `PLAN.md` and `docs/05-implementation-plan.md` call
  for one Kernel commit path and explicitly name Team lifecycle and Signal
  ingestion as examples, without requiring complete production Task-creation
  runtime. `docs/tasks.md` names API/CLI, scheduler, Trigger, enqueue, and retry
  as Task creation sources; it does not say that creating a Task must itself
  be committed by a prior Task. `docs/walkthrough.md` explicitly says it is an
  integration-test fixture specification and shows an already-active Team
  before `ingest_source` Task TSK-201 stores a Snapshot, commits a Signal, and
  emits `fetch_no_change` on identical-content refetch. This supports using
  prerequisite Team, source configuration, and running Task records as test
  setup rather than implementing their production creation flows as part of
  this slice. No K1 code or tests were run.
- **Reassessment and discrepancy:** The prior conclusion that no candidate
  could be selected is **overturned** as applied to the Signal-ingestion
  vertical slice: it conflated the separate production/bootstrap problem with
  preconditions for exercising a single Kernel commit path. However, the
  walkthrough says the active Team is seeded through `seed_knowledge`, while
  the `docs/tasks.md` write-scope matrix gives `seed_knowledge` no Team write
  and `docs/architecture.md` describes Team creation and activation through
  `create_team` and `activate_team`. The walkthrough therefore should not be
  treated as proof of a production Team-bootstrap flow. Its explicit fixture
  role still supports loading precondition records in test setup; that setup
  is not the production commit behavior under test. The `create_team`
  bootstrap question remains separate and does not block Signal ingestion.
- **Candidate result:** `create_team` still has the unresolved first-Task /
  Team attribution question. `activate_team` depends on a TeamDraft, policy
  validation, TeamPolicy, starter Threads, and Team lifecycle transition, so
  it is broader. `ingest_source` has a dedicated Task specification and a
  concrete walkthrough trace for Snapshot-before-Signal, hash, duplicate
  handling, and Event behavior; triage and its follow-on behavior can remain
  outside the selected commit slice.
- **Lessons:** Establish already-existing Team, source configuration, and
  Task records in disposable test fixtures when they are prerequisites to a
  focused commit-path test; do not implement their production bootstrap
  runtime unless the chosen acceptance criteria require it. Task creation
  being an entry point does not, by itself, imply recursive Task creation.
  Keep fixture setup distinct from assertions about production provenance,
  and do not use the walkthrough's `seed_knowledge` Team setup as an
  authoritative production flow without reconciling its scope mismatch.
- **Resulting documentation changes:** This simulation record was appended.
  No implementation, migration, test, project configuration, or architecture
  document was changed; no K1 implementation or test result is claimed.
