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

### 7. R0 Simulation 04 — Freeze Contract consistency audit

- **Task/scenario:** Audit the repository documentation against the R0 Freeze
  Contract, using the established authority chain. The request required an
  evidence-based discrepancy report and prohibited changes to architecture,
  implementation, plans, ADRs, tests, or migrations; this validation record
  was the only permitted edit.
- **Repository state:** The checkout was on `R0` at
  `038aba6a4028a5e18560bc9899f3c653ee1bc72d`. The only pre-existing worktree
  change was `.gitignore` adding `Project2text.txt`; it was not changed. The
  R0-03 contract and validation record were committed at HEAD, and no tracked
  files changed after that commit before this record. K0 tooling and the K1
  ingestion slice were present. The implemented code contained only the K1
  Team, TeamPolicy, Task, Signal, and Event mappings plus ingestion and
  Snapshot storage; no Objective, StateAssessment, StrategyProposal, Plan,
  Control runtime, retrieval, learning runtime, or LLM integration was
  present.
- **Expected behavior:** `AGENTS.md` requires the authority chain to be read,
  source conflicts to be reported rather than inferred away, and workflow
  simulations to append a chronological record without implementation edits.
  The Freeze Contract requires the Worker/Kernel, dual-entry, single-runtime,
  Plan, StateAssessment, Strategy, memory, learning, provenance, evidence,
  and external-content boundaries to remain intact without treating open
  hypotheses as established capability.
- **Observed behavior:** The audit read the required authority, architecture,
  control, runtime, schema, milestone, task, invariant, glossary, ADR, README,
  explanation, and workflow documents; inspected Git history, the worktree,
  package/runtime configuration, migrations, models, and tests; and made no
  source, implementation, migration, or ADR edit. The major architecture
  documents and ADR-0023 through ADR-0026 agree on Worker proposal versus
  Kernel commit, convergence of reactive and deliberative work into ordinary
  Tasks, Plan-as-intent, non-authoritative StateAssessment, Strategy distinct
  from TeamPolicy, and controlled Team-learning changes. No test command was
  run, so this record makes no new verification-pass claim.
- **Discrepancies:** No architectural contradiction was found. Status wording
  in `AGENTS.md`, `PLAN.md`, and `docs/05-implementation-plan.md` still frames
  K0 as current and K1 as unimplemented/planned despite the committed K1
  implementation. `docs/invariants.md` says every invariant is enforced and
  covered by a named test, while the repository currently contains only the K1
  slice and its focused tests. `docs/architecture.md` describes the larger v1
  LangGraph/Anthropic/Redis/FastAPI runtime in present tense although those
  dependencies and runtime components are absent. `Simple Explain.md` states
  desired expertise improvements and cross-model benefits more strongly than
  the contract's explicitly unproven hypotheses. Capitalized `Evidence` is
  used in conceptual diagrams while the glossary defines `EvidenceLink`, which
  leaves its exact meaning unclear. These are stale documentation,
  inconsistency, or terminology-cleanup findings, not a reason to redesign.
- **Lessons:** Treat repository code and committed migrations as the source for
  implementation status, while keeping the authority map for architectural
  meaning. Keep roadmap/specification language visibly distinct from claims
  about what is implemented or empirically demonstrated. The R0 contract can
  leave a technology choice non-frozen without invalidating an older v1
  implementation preference; the choice must not be mistaken for a frozen
  architectural relationship.
- **Resulting documentation changes:** Appended this record only. No
  architecture-source, plan, ADR, implementation, migration, test, or
  `.gitignore` file was changed.

### 7. R0-04 corrected freeze contract consistency audit

- **Task/scenario:** Correct the previous R0-04 documentation audit by using the
  actual checked-out repo, the freeze contract, the current implementation, and
  the authority-chain rules. The task boundary forbade architecture redesign,
  implementation changes, or rewriting source documents; only this validation
  record could be appended.
- **Repository state:** The checkout was on the `R0` branch at
  `096e927975940fb57b511fd618c0e89eab22e99a`. `git status --short --branch`
  showed a clean worktree. No `.gitignore` modification was active. The
  repository contains the K0 tooling baseline and a committed K1 ingestion
  path: `core/models.py`, `core/ingestion.py`, `core/snapshot_store.py`, the
  associated migrations/tests, and passing verification (`uv run pytest -q`:
  18 passed; `uv run ruff check .` and `uv run mypy core`: pass). The repo
  still does not contain implemented Control-layer entities or runtime
  (`Objective`, `StateAssessment`, `StrategyProposal`, `Plan`, LLM integration,
  scheduling, retrieval, etc.).
- **Expected behavior:** The audit must use the captured Freeze Contract as the
  exact source of truth for the R0 boundary, not the previous report or any
  paraphrase. It must distinguish architecture freeze, implementation status,
  experiment status, and documentation status. It must not treat
  unimplemented features or unresolved empirical hypotheses as architectural
  contradictions, and it must not rewrite source documents or invent missing
  architecture.
- **Observed behavior:** The audit read the actual Freeze Contract and the
  authoritative repository documents, then checked the code and tests. The
  repository is consistent with the Freeze Contract on the core boundary: the
  Kernel, Task execution, proposal-validation-commit flow, immutable Snapshot,
  Plan-as-intent semantics, StateAssessment as derived/non-authoritative,
  Strategy as situational intent, and the divide between world memory and team
  learning are all preserved. The architecture is not contradicted by the
  current K1 implementation. The only material drift is documentary: some
  milestone/status wording in `AGENTS.md`, `README.md`, `PLAN.md`, and
  `docs/05-implementation-plan.md` still describes the project as a K0-only or
  pre-K1 repo even though K1 and its tests are present and passing.
- **Discrepancies:** The repository state is not a contradiction; it is a
  documentation-status mismatch. `AGENTS.md` says K0 is complete and K1 should
  not begin, but the repo contains and tests the K1 ingestion slice. `README.md`
  states “K1 is implemented on `main`,” which is stale relative to the active
  `R0` checkout and the actual Git branch state. `PLAN.md` and
  `docs/05-implementation-plan.md` are roadmap documents, not live status
  summaries, and must not be mistaken for the current implementation state.
  `docs/glossary.md` and the wider design language still use capitalized
  conceptual nouns such as `Evidence` and `EvidenceLink` inconsistently,
  creating a terminology-cleanup issue rather than a structural failure.
  `Simple Explain.md` is persuasive narrative framing, not authoritative
  architecture or implementation status, and its stronger claims are limited by
  the Freeze Contract's explicit non-proven hypotheses. No actual
  architectural contradiction was found.
- **Lessons:** The real source of truth for current implementation status is the
  working tree and codebase, not milestone wording. The Freeze Contract is
  coherent and is satisfied by the repository's current boundary: K1
  deterministic ingestion is implemented, while Control-layer entities remain
  future work. The correct verdict is not “R0 broken,” but “R0 coherently
  frozen with documentation cleanup required.” The repository should be
  documented as: K0 merged, K1 implemented, Control layer deferred, and the
  future architecture still explicitly unproven.
- **Resulting documentation changes:** This validation record was appended only.
  No implementation files, architecture-source documents, ADRs, tests,
  migrations, or `.gitignore` files were modified.

### 8. R0-04c final evidence correction pass

- **Task/scenario:** Correct source exactness, invariant evidence, selected
  document classifications, and worktree/test reporting in the preceding
  R0-04b audit. No architecture redesign or source-document cleanup was
  authorized; this section is an append-only correction record.
- **Repository state:** Branch `R0`, HEAD
  `096e927975940fb57b511fd618c0e89eab22e99a`. R0-04b began with a clean
  worktree and appended its record without committing it. At the start of this
  pass, the only modification was that preceding append to this file; no
  `.gitignore` or other user modification was present. The current append also
  remains uncommitted.
- **Freeze Contract exactness corrections:** The architectural-objective quote
  in R0-04b was exact. H1–H7 headline labels were exact, but the section was an
  incomplete faithful summary because it omitted each row's explanatory
  sentence and status. The seven redesign triggers and their order were
  faithfully paraphrased, not exact quotations. The acceptance-criteria list
  was also not an exact extraction. In particular, criterion 8 is: “The listed
  implementation choices and empirical hypotheses remain open; none is
  represented as an R0 proof or mandatory implementation choice.” R0-04b
  omitted the second clause, materially weakening that criterion. Criterion 6
  was compressed; the actual criterion names durable state, execution
  provenance, and the validation/commit boundary as the things that remain
  attributable and reconstructable through the existing model.
- **Invariant evidence correction:** `docs/invariants.md` defines INV-01
  through INV-15 and contains a planned invariant-to-test mapping, but that
  mapping is not proof of implementation. The current test tree contains
  `test_database.py` and `test_ingestion.py`; the implementation contains only
  the K1 ingestion path. Current enforcement/test status is therefore partial
  only for INV-02, INV-03, INV-13, and INV-14, limited to K1; the other
  invariants are not reached by the current implementation. This corrects
  R0-04b's unsupported implications that INV-04, INV-07, or INV-09 are
  currently enforced or tested.
- **Documentation-status corrections:** `AGENTS.md` says K0 tooling is on the
  `k0` branch and that K0 is complete; these statements are accurate. Its
  K0-boundary heading and “Do not begin K1 unless explicitly requested”
  instruction are ambiguous about present K1 status, but do not explicitly say
  K1 is unimplemented. `README.md` says K1 is implemented on `main`; this is
  supported by the `k1` commit being an ancestor of `origin/main`, so the
  active `R0` checkout does not make that statement stale. `PLAN.md` explicitly
  says “Current implementation milestone: K0”; that status is stale against
  the R0 checkout containing K1. `docs/05-implementation-plan.md` is a K0/K1
  implementation plan and does not assert that K1 is the current status.
  `docs/architecture.md` is an architecture specification, not evidence that
  its described runtime is implemented. `docs/glossary.md` defines
  `EvidenceLink` but has no standalone `Evidence` definition despite
  capitalized conceptual use elsewhere; classify this as terminology
  ambiguity, not a proven competing entity. `Simple Explain.md` is
  explanatory framing; its “designed to” wording is not a claim of validated
  capability.
- **Verification and worktree reconciliation:** In R0-04b, direct `pytest -q`
  did not run because `pytest` was unavailable as a PowerShell command; this
  was an environment/command-availability failure, not a test failure.
  `uv run pytest -q` succeeded: 18 passed in 132.61 seconds. `uv run ruff
  check .` and `uv run mypy core` both passed. Before this append, the worktree
  was modified only in `docs/development/workflow-validation.md` by the
  uncommitted R0-04b append. After this append, that remains the only modified
  path; there is no clean-worktree claim and no commit explains the change.
- **Corrected result:** No Freeze Contract redesign trigger is evidenced by
  this review. The verdict remains `R0 CONSISTENT WITH DOCUMENTATION CLEANUP`,
  based on the stale explicit K0 milestone status in `PLAN.md` and the bounded
  terminology ambiguity around Evidence/EvidenceLink—not on test success.
  The K1-limited implementation evidence does not establish enforcement of
  the full invariant suite.
- **Resulting documentation changes:** This correction record was appended to
  this file only. No source documents, implementation, migrations, tests, or
  `.gitignore` were changed.

### 9. R0-05 documentation alignment

- **Task/scenario:** Align current milestone wording and clarify the
  Evidence/EvidenceLink vocabulary following the R0-04c correction findings.
- **Repository state:** R0-04c and the preceding audit were committed. The
  worktree was clean before this task. K0 is complete, K1 ingestion is
  implemented, and R0 is the current architecture-freeze/alignment phase.
- **Expected behavior:** Make only the supported status and terminology
  clarifications; preserve the Freeze Contract's testable-hypothesis boundary
  and leave architecture and implementation unchanged.
- **Observed behavior:** Updated `PLAN.md` to identify R0 as the current phase
  and mark K0/K1 complete; clarified in `AGENTS.md` that K1 is implemented
  while retaining the K0 boundary and Control-layer restriction; defined
  `Evidence` as conceptual terminology distinct from the concrete `EvidenceLink`
  record in `docs/glossary.md`.
- **Discrepancies:** No new architectural discrepancy was identified. This
  cleanup does not claim that the Control layer, full invariant suite, or
  expertise-learning hypotheses are implemented or proven.
- **Lessons:** Keep implementation milestone status distinct from the
  architecture-freeze phase, and distinguish a conceptual category from its
  concrete record vocabulary.
- **Resulting documentation changes:** Only `PLAN.md`, `AGENTS.md`,
  `docs/glossary.md`, and this validation record were changed. The R0 Freeze
  Contract, architecture, K1 implementation, and tests were unchanged.

### 10. R1-03 compatibility decision recording

- **Task/scenario:** R1-02 resolved the write-scope/provenance conflict; R1-03
  recorded that decision in the Revision-2 data-model authority.
- **Observed result:** Existing K1 scope semantics remain unchanged; future
  Control authorization is additive; Objective and Plan mutations remain
  Task-attributed; the original baseline and R0 Freeze Contract were unchanged.
- **Boundaries:** No Control runtime, schema, migration, tests, or other durable
  implementation was added. The complete Plan lifecycle table remains deferred.
- **Resulting documentation changes:** Updated
  [`docs/04-data-model-changes.md`](../04-data-model-changes.md) and appended
  this record only.

### 11. R1-01 implementation contract pass

- **Task/scenario:** Establish the repository-backed R1 scope and first
  implementation boundary without beginning implementation.
- **Repository state:** Branch `R1`, HEAD `63d836e`; worktree clean at start.
  The R0 branch and R0-05 alignment commit are ancestors of HEAD. K0 and K1
  are present; Control-layer models and runtime are absent.
- **Observed result:** `PLAN.md` and `docs/05-implementation-plan.md` define
  R1 as a compatibility design pass, explicitly with no Control-layer code
  beyond design; Objective implementation begins in R2. The committed R1-03
  compatibility note preserves K1 write-scope semantics and Task-attributed
  Objective/Plan changes. No implementation files were changed.
- **Discrepancies:** `PLAN.md` still labels R0 as the current phase although
  this branch contains an R1-03 decision commit. The task label R1-01 also
  follows the R1-03 entry in the existing chronological record. These are
  status/sequence documentation mismatches, not contradictions with the R0
  Freeze Contract. Exact Plan lifecycle and some schema/runtime details remain
  deferred or unspecified; they must not be invented in this pass.
- **Resulting documentation changes:** Appended this record only. No
  implementation, migration, test, architecture, ADR, milestone, or Freeze
  Contract file was changed.

### 12. R1-04 compatibility design closure

- **Task/scenario:** Close the compatibility decisions needed to begin R2
  without implementing Control behavior or changing the R0-frozen model.
- **Repository state:** Branch `R1`, HEAD `bddb7a5`; worktree clean at start.
  R0 is in branch ancestry, and the Freeze Contract matches `origin/R0`.
  K1 migration `0002_ingestion_kernel` and its Objective-free models remain
  the existing implementation baseline.
- **Decisions closed:** `PLAN.md` now identifies R0 complete, R1 current, and
  R2 as the first Control implementation phase. Objective mutations are
  authorized only through Task-attributed `create_objective` and
  `transition_objective` operations, with the existing scope, Team, budget,
  Kernel, Event, retry, and optimistic-conflict boundaries. Task Objective/
  Plan reference rules and the R2/R5 migration split are explicit. Selected
  Assessment basis and budget hierarchy requirements are recorded. Relevant
  INV-01, INV-02, INV-03, INV-11, INV-12, INV-13, INV-14, and INV-15
  obligations are mapped to future R2-R5 tests.
- **Deliberately open:** Plan status vocabulary/transitions, dependency
  storage, Plan mutation scope and event vocabulary, materialization retry
  details, database constraint/index choices, and Assessment serialization,
  storage, and hash implementation remain for the appropriate later design or
  implementation choice. No Plan schema is added in R1.
- **R0 boundary and implementation:** Worker proposal, Kernel validation and
  commit authority, Task convergence, one execution runtime, non-authoritative
  Assessment, Plan-as-intent, memory separation, provenance limits, evidence
  limits, and the external-content boundary remain unchanged. No code,
  migration, or test was added; no Control runtime was implemented.
- **Resulting documentation changes:** Updated `PLAN.md`,
  `docs/04-data-model-changes.md`, `docs/03-runtime-model.md`,
  `docs/tasks.md`, `docs/02-control-layer.md`, and
  `docs/05-implementation-plan.md`; appended this record. Readiness:
  `R1 COMPATIBILITY CONTRACT CLOSED WITH EXPLICIT OPEN ITEMS`.

### 13. R1-05 compatibility closure challenge audit

- **Task/scenario:** Adversarially review the uncommitted R1-04 documentation
  changes against the current authority chain; do not amend those changes.
- **Repository state:** Branch `R1`, base commit `bddb7a5`; the seven R1-04
  documentation paths were already modified. Their changes were preserved.
- **Source-supported findings:** Objective lifecycle and terminal states;
  Task attribution, same-Team ownership, scoped Kernel validation and
  reason-bearing rejection; atomic revalidation and rejection of conflicting
  commits; optional Task references; reconstructable selected Assessment
  provenance; Plan-as-intent, stop conditions, dependencies with cycle
  validation, non-silent replanning, and the TeamPolicy > Plan > Task budget
  hierarchy are supported by the mapped architecture, invariants, and
  milestones.
- **Over-specification:** Exact Objective Task names, success/rejection Event
  names, stable reason strings, rejection transaction separation, replay
  comparison fields and reuse of rejection outcomes, Objective deduplication
  policy, `W` scope classification, and restriction to no model/tool usage
  are not fixed by the authorities. They should remain implementation choices
  or be stated only as semantic requirements. The optimistic expected-state
  revalidation guarantee itself is supported by INV-13; no particular new
  lock/version mechanism is mandated.
- **Contradiction:** R1-04 declares Plan-only Tasks invalid and requires
  `objective_id` whenever `plan_id` is present. `CHANGE_MAP.md` says Tasks may
  optionally reference an Objective “and/or” a Plan; the pre-existing data
  model requires parent consistency only when both references are present.
  The new prohibition therefore narrows the authorized relationship and
  conflicts with the mapped source. Plan ownership by its Objective does not
  require duplicating that Objective reference on every Task.
- **Assessment:** R1-04 is `R1-04 REQUIRES REWORK`. The R1-04 patch was not
  changed or discarded. Minimal correction is to remove the Plan-only
  prohibition, retain same-Team and parent consistency where both references
  exist, and relax literal identifiers, reason names, rejection persistence,
  retry, scope-category, and no-tool/model choices to their source-supported
  semantics. Plan cycles/stop conditions and Assessment basis hash/timestamp
  requirements are source-supported; their storage and serialization details
  remain open.
- **Resulting documentation changes:** Appended this audit record only. No
  R1-04 source document, code, migration, test, ADR, or Freeze Contract was
  modified. No commit was made.

### 14. R1-06 rework of R1-04 compatibility contract

- **Task/scenario:** Surgically rework the uncommitted R1-04 compatibility
  changes following the R1-05 challenge audit; preserve the R0 architecture
  and make no implementation changes.
- **Repository state:** Branch `R1`, base commit `bddb7a5`; the seven
  uncommitted R1-04 documentation paths and the R1-05 audit entry were
  preserved.
- **Corrections:** R1-05 identified the genuine Task-reference contradiction.
  The contract now permits neither reference, Objective only, Plan only, or
  both, with parent consistency when both are present and consistent Team
  ownership. Objective mutation, success Event, and rejection requirements
  are semantic; literal Task/Event names and reason codes are open. Unsupported
  rejection transaction/replay details, Objective text-field immutability,
  cross-Task deduplication, W scope classification, and no-model/tool limits
  were removed. INV-13's atomic revalidation and no-silent-conflict guarantee
  remains without prescribing a database mechanism. Plan dependency validity,
  cycle prevention, stop conditions, historical intent, Assessment
  reconstructability, and the budget hierarchy remain semantic requirements;
  physical representation and implementation details remain open.
- **R0 boundary and implementation:** The R0 Freeze Contract is unchanged.
  R1 remains design-only; R2 is Objective implementation and R5 is Plan
  materialization. No code, migration, test, or Control runtime was added.
- **Resulting documentation changes:** Corrected the existing R1-04 wording
  in `docs/04-data-model-changes.md`, `docs/03-runtime-model.md`,
  `docs/tasks.md`, `docs/02-control-layer.md`, and
  `docs/05-implementation-plan.md`; appended this record. No commit was made.

### 15. R1-07 final closure audit

- **Task/scenario:** Verify the completed R1 compatibility work against the
  final authority chain, check for remaining contradictions, and establish
  the documentation commit boundary without implementing R2.
- **Repository state:** Branch `R1`, HEAD `b3b21d6`. The worktree was clean at
  audit start. HEAD already contains the seven authorized R1 documentation
  files; this audit did not create or amend that commit.
- **Observed result:** The contract permits Tasks with neither Objective nor
  Plan, either reference alone, or both; parent consistency applies when both
  are present, and referenced records must match the Task's Team. Objective
  lifecycle, Task attribution, Kernel authority, INV-13 semantics, Plan intent
  and stop conditions, Assessment provenance, and budget hierarchy agree with
  the mapped sources. Remaining names, storage, locking, replay representation,
  Plan lifecycle/scope, and serialization details remain deferred.
- **Contradiction scan:** No operative contradiction remains. Superseded
  identifiers and the former Plan-only prohibition occur only in preserved
  chronological R1-04/R1-05 audit text; K1 rejection vocabulary remains
  specific to K1.
- **Boundaries:** The R0 Freeze Contract is unchanged. No R0 redesign trigger
  appeared. No implementation, migration, test, or Control runtime was added.
- **Commit boundary:** The R1 documentation change is already committed at
  `b3b21d6` and contains exactly `PLAN.md`, `docs/04-data-model-changes.md`,
  `docs/03-runtime-model.md`, `docs/tasks.md`, `docs/02-control-layer.md`,
  `docs/05-implementation-plan.md`, and
  `docs/development/workflow-validation.md`. No further commit was made.
- **Final status:** `R1 COMPLETE WITH EXPLICIT LATER-MILESTONE OPEN ITEMS`.

### 16. R3-00 StateAssessment preflight and design gate

- **Task/scenario:** Audit the repository exactly as an R3 preflight and
  design gate, with implementation forbidden and only this workflow record
  allowed to change. The task explicitly required no architecture change,
  no migration/test/core edits, and no commit.
- **Repository state:** Branch `R3`; `git status --short --branch` is clean.
  `git rev-parse HEAD` resolves to `eafb01799bf096e50691c41c4e0be0cbd36d30ef`.
  `git log --oneline -15` shows `HEAD -> R3, origin/R3` on the R3 branch,
  `main` contains the R2 merge commit `385ff1f`, and `git merge-base
  --is-ancestor R2 main` succeeds. The worktree has no uncommitted
  modifications at the start of this gate. The repository currently contains
  the K1 ingestion implementation and the R2 Objective model, but no
  durable Control-layer StateAssessment, StrategyProposal, Plan, Team-memory,
  or world-memory implementation.
- **Expected behavior:** Use the authority chain in order, preserve the
  source-of-truth rules from `AGENTS.md` and `CHANGE_MAP.md`, preserve the
  R0/R1/R2 boundaries, and decide whether any honest bounded R3 scope
  exists without inventing future infrastructure. The simulation also
  required checking for any earlier malformed or partial R3-00 record and
  repairing only the chronology, not discarding prior entries.
- **Observed behavior:** The repository check and authority review found a
  clean R3 branch with R2 already merged into `main`. No earlier R3-00
  workflow record was present in the file, so no repair was required to an
  existing record. The current repo is internally consistent with the
  architecture on the boundary that matters here: StateAssessment is derived
  and non-authoritative; Plan and Strategy are future concepts; tasks and
  events remain the durable execution truth; the K1 ingestion path and the
  R2 Objective model are implemented while full Control-layer runtime remains
  absent.
- **Discrepancies:** There is no substantive repository conflict. The real
  discrepancy is scope: the full conceptual R3 described in the architecture
  requires inputs and durable records that do not exist in the current
  repository. The implemented state includes Team, TeamPolicy, Task,
  Objective, Signal, and Event, but it does not yet contain the missing
  StrategyProposal/Plan/assessment infrastructure, Team memory, world memory,
  or the later selection semantics that the architecture describes for the
  full Control loop.
- **Lessons:** The correct R3 gate is not “full conceptual assessment is
  implementable now.” A bounded R3 slice is possible, but only if it starts
  from the durable records that actually exist and remains read-only,
  derived, and reconstructable. The assessment must not become a second
  source of truth, must not invent missing world-memory infrastructure, and
  must not imply that unimplemented Strategy or Plan entities already exist.
- **Resulting documentation changes:** Appended this record only. No
  implementation files, migrations, tests, architecture documents, or prior
  workflow entries were modified or rewritten. The repository remains a
  clean R3 design gate with no code changes.
- **Decision gate:** `R3 READY WITH EXPLICIT BOUNDED SCOPE`.


### 17. R5 workflow-instruction enforcement review

- **Task/scenario:** Review the repository's agent instructions after repeated
  milestone work exposed a workflow failure: Codex can read `AGENTS.md` yet
  omit the required append to `docs/development/workflow-validation.md`.
  The requested correction was to make `AGENTS.md` operationally useful to
  models and make workflow-reporting omissions harder to repeat.
- **Repository state:** The active development branch is `R5`. R4 is already
  merged into `main`; R5 was created from that merged state. The existing
  `AGENTS.md` still contained historical K0/K1 status language and treated
  workflow validation as conditional on the task being explicitly designated
  as such. `PLAN.md` also contains historical milestone-status wording that
  does not reliably identify the actual current branch state.
- **Expected behavior:** Agent instructions should direct Codex to determine
  current state from Git and current milestone documents rather than trusting
  stale status copied into `AGENTS.md`. When a task tests or evaluates the
  development workflow, the agent should read the workflow-validation record,
  append a chronological observation, and verify that the append actually
  exists. A no-implementation simulation should prohibit source changes while
  still allowing the designated workflow record to change.
- **Observed behavior:** The previous `AGENTS.md` already described the
  required contents of a workflow-validation record, but the trigger was too
  narrow: it said “When a task is explicitly designated” and therefore allowed
  an agent to interpret workflow/audit tasks as ordinary implementation work.
  The file also embedded obsolete milestone state. This made it possible for a
  model to read the file, follow the broad development rules, and still omit
  the workflow report.
- **Discrepancies:** The principal discrepancy is between documented intent
  and operational model behavior: the repository wanted chronological
  workflow evidence, but the instruction did not reliably identify when that
  obligation applied. A second discrepancy was that `AGENTS.md` itself could
  become stale as branches advanced, undermining its value as a current-state
  guide.
- **Lessons:** Workflow requirements must be triggered by the semantics of the
  task, not by a magic phrase in the user's prompt. Repository instructions
  should also avoid embedding current milestone claims that become stale after
  branch transitions. Completion checklists should include verification that a
  required documentation artifact was actually changed.
- **Resulting documentation changes:** Replaced `AGENTS.md` with an
  operational repository contract. It now requires Git/milestone preflight,
  explicit authority handling, design/reality gates, semantic workflow-
  validation triggers, chronological append-only reporting, and verification
  that the workflow record was actually updated. This record documents that
  change; no implementation behavior or architecture was changed.
