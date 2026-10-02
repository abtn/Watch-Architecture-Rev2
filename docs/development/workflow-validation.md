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

### 4. R0 architecture-authority and freeze preflight

- **Task/scenario:** Determine the current architectural authority of Watch,
  establish the starting point for R0, and decide whether the architecture can
  be treated as a coherent, testable hypothesis without a fundamental redesign
  before R0. The task explicitly forbade implementation or architecture edits.
- **Repository state:** The checkout is on `main` and the worktree is clean. The
  current HEAD is `5701423` (`Revise "Simple Explain.md"...`). Recent history
  includes `213c44d` (`README` revision), `23a029e` (`K1 ingestion commit
  path`), and the merge commit `8d4dd59` (`Merge K0 baseline`). The repo already
  contains K0 tooling plus an implemented K1 ingestion path. `README.md` states
  that “K0 is complete. K1 is implemented on `main`.” `PLAN.md` still names K0
  as the current phase and R0 as a later milestone. The codebase contains
  `core/ingestion.py`, `core/models.py`, `core/snapshot_store.py`, migrations,
  tests, and Docker/Postgres configuration, but no Control-layer runtime
  (`Objective`, `StateAssessment`, `StrategyProposal`, `Plan`) implementation.
- **Expected behavior:** The repository instructions require reading
  `AGENTS.md`, `CHANGE_MAP.md`, `PLAN.md`, and the architecture documents in
  authority order, then distinguishing historical state from current repository
  state. The docs also require stopping when authority is ambiguous instead of
  silently selecting a conflict resolution. K0 guidance says Control-layer
  implementation is out of scope; the repo's current K1 implementation is a
  valid Kernel slice without model calls.
- **Observed behavior:** The inspection followed the authority chain and found a
  clear current source-of-truth pattern: `CHANGE_MAP.md` explicitly says
  original documents govern unmapped concepts, while Revision 2 documents
  govern only the concepts they explicitly revise. The repo currently contains
  the K1 implementation reported in `README.md`, which is consistent with the
  code and passing verification. The current state is therefore not a
  documentation-only K0 repo or a pure pre-K1 state; it is a K1-era repo with
  future Control work still deferred.
- **Discrepancies:** The main discrepancy is milestone drift, not code
  instability: `PLAN.md` describes the intended sequence (`K0 → K1 → R0 → ...`),
  while the repository state already contains K1 implementation and says K1 is
  complete on `main`. That means the plan document is a roadmap, not a literal
  current-status mirror. The architecture documents are internally coherent
  about the Kernel and Task boundary, but they are explicitly future-facing for
  Control. There is no contradiction in the current code, but there is a
  documented mismatch between the historical milestone narrative and the current
  repository state. This is significant for R0 freeze planning because the repo
  is not a clean “before R0” baseline; it is “K1 complete, Control deferred.”
- **Lessons:** Treat the repository’s current code and README as the operative
  status for implementation work; treat `PLAN.md` as the intended roadmap and
  historical milestone narrative. For an R0 preflight, the architecture is
  coherent enough as a bounded Kernel-plus-Task hypothesis, but it is not yet a
  complete architectural freeze for the future Control layer. The current code
  supports a valid, testable Kernel slice, and the remaining Control concepts are
  intentionally deferred rather than redesigned in place.
- **Resulting documentation changes:** This workflow-validation entry was
  appended. No implementation files were modified.

### 5. R0 freeze-boundary simulation

- **Task/scenario:** Define the architecture that should be frozen at R0,
  distinguish it from implementation detail and research hypothesis, and keep
  the future control/learning work explicitly deferred rather than silently
  expanded. The task required no implementation, no architecture rewrites, and
  no new design work beyond classification and boundary setting.
- **Repository state:** The repository is on the `R0` branch. The current HEAD is
  `5701423` (`Revise "Simple Explain.md"...`). The worktree is clean before
  this validation record is appended; after this record the workflow file is the
  only modified document. The repo contains the K0 tooling baseline and the K1
  ingestion commit path implemented on `main` before branching. The codebase has
  `core/models.py`, `core/ingestion.py`, `core/snapshot_store.py`, migrations,
  tests, and Docker/Postgres setup, but no implemented Control-layer entities
  (`Objective`, `StateAssessment`, `StrategyProposal`, `Plan`) or LLM runtime.
- **Expected behavior:** The simulation required reading the authority chain and
  the implementation to distinguish: architecture commitment, implementation
  detail, and hypothesis. It specifically forbade turning conceptual framing in
  `Simple Explain.md` into authoritative architecture, and it required a precise
  bound on what R0 should freeze without creating new abstractions merely to
  satisfy future possibilities.
- **Observed behavior:** The repository documents are internally coherent on the
  stable kernel boundary: durable state is authoritative, Workers propose
  changes, the Kernel validates and commits, Tasks remain the execution unit,
  and the Control layer is additive rather than a second runtime. The current
  implementation supports the deterministic ingestion path and the standard
  validation/commit discipline. The architecture documents state that Objective,
  Plan, StrategyProposal, and StateAssessment are specified but not yet
  implemented, and that the learning- and experience-retrieval layer remains a
  future design or research question.
- **Discrepancies:** The main discrepancy is not a contradiction but a category
  mistake: `Simple Explain.md` uses a strong conceptual narrative about a system
  that develops persistent expertise, but the repo does not yet contain evidence
  that the proposed learning loop is empirically validated. That narrative is a
  framing document, not a source of stable architecture. The repo also shows a
  material difference between the roadmap (`K0 → K1 → R0 → ...`) and the actual
  code state (`K1 present`), which is not a contradiction in the architecture
  itself but a reminder that the repo's current reality must be treated as the
  authority over historical milestone wording.
- **Lessons:** R0 should freeze the architectural relationship between Kernel,
  Task execution, proposal/validation/commit, objective/plan semantics, and the
  world-vs-team memory distinction. It should not freeze exact model-provider
  choices, retrieval algorithms, evaluation heuristics, or learning methods.
  The open questions are real, but they are hypotheses or future implementation
  problems, not evidence that the architecture is wrong. The right R0 boundary
  is to freeze the durable contract, not to encode a final theory of expertise.
- **Resulting documentation changes:** This workflow-validation entry was
  appended. No implementation files, architecture documents, migrations, or
  tests were modified.

### 6. R0 Simulation 03 — Architecture Freeze Contract

- **Task/scenario:** Convert the R0-01 and R0-02 observations into a formal
  R0 Freeze Contract. The request authorized only the new contract and this
  chronological validation record; it prohibited architecture-source,
  implementation, migration, and test changes.
- **Repository state:** The `R0` checkout was clean before this simulation.
  K0 tooling and the K1 deterministic ingestion slice were present; Control
  entities and runtime behavior remained unimplemented. `PLAN.md` presents R0
  as the architecture-freeze phase, while `README.md` documents the existing
  K1 implementation. The prior R0 records in this file were observations, not
  replacement architecture authority.
- **Expected behavior:** Read the listed authority chain and repository state;
  preserve the Kernel/Task, dual-entry, Plan, StateAssessment, Strategy,
  provenance, evidence, and learning boundaries; distinguish frozen
  relationships from implementation choices and empirical hypotheses; record
  the result without claiming causal attribution, truth, or prompt-injection
  resistance as solved.
- **Observed behavior:** Codex read the requested authority, architecture,
  control, runtime, schema, plan, task, invariant, glossary, ADR, README,
  explanation, and workflow-validation documents and checked the worktree.
  It found no fundamental architectural contradiction. It created
  `docs/development/r0-freeze-contract.md`, classifying the existing
  architecture as a testable hypothesis; it preserves the explicitly required
  limits on causal attribution, evidence, and runtime security. No
  implementation or architecture-source document was changed.
- **Discrepancies:** The roadmap's K0-current wording and the README/K1 code
  state remain a status-documentation mismatch, not a conflict in the frozen
  architecture. The request supplied only the beginning of its sixth R0
  acceptance criterion; the contract records the supplied acceptance criteria
  and completes the acceptance list with non-conflicting boundary checks.
- **Lessons:** A freeze contract should bind relationships and authority, not
  turn persistent-expertise framing into proof. Provenance must be described as
  a record of actions and observations, not proof of causal attribution; source
  integrity and quote checks must remain distinct from reliability and truth;
  treating external content as data establishes a boundary but does not prove
  runtime prompt-injection resistance.
- **Resulting documentation changes:** Added
  `docs/development/r0-freeze-contract.md` and appended this record. No
  AGENTS.md, architecture-source, implementation, migration, or test file was
  changed.
