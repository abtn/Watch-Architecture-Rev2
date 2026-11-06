# Testing and Verification

Tests are evidence for the behavior they exercise. A green focused test is not proof that the full suite, database migration path, or milestone gate passed.

## Standard checks

Run the focused tests first, then applicable broader checks:

```bash
uv run pytest tests/test_<area>.py
uv run ruff check <changed-paths>
uv run mypy core
git diff --check
```

When required by the task or milestone, also run:

```bash
uv run pytest
uv run ruff check .
uv run alembic upgrade head
```

Use commands supported by `pyproject.toml` and the current repository environment. Report exact commands and outcomes; do not infer success from inspection.

## Database safety

- Every database-backed test run requires an explicit `TEST_DATABASE_URL` pointing to a disposable PostgreSQL database.
- The test fixture does not fall back to `DATABASE_URL` and has no hard-coded connection to the developer's `watch` database.
- The test fixture rejects SQLite and rejects a database named exactly `watch`, even when supplied through `TEST_DATABASE_URL`.
- It is acceptable for `DATABASE_URL` to keep pointing at the persistent application database while `TEST_DATABASE_URL` points at the disposable test database; tests use only `TEST_DATABASE_URL`.
- Use a disposable database/volume for migration and concurrency verification.
- Never target a persistent `watch` database to make a test pass.
- Do not run destructive cleanup such as `docker compose down -v` as generic test cleanup.
- If the database cannot be started or a dependency is missing, report the environmental blocker separately from a code defect.

Before running database-backed tests, configure the test URL explicitly. For example, after starting a disposable PostgreSQL instance:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://watch:watch@127.0.0.1:55463/watch_test"
uv run pytest -q
```

The example URL is illustrative; it does not create the database. Use the actual port and database name of the disposable instance. The fixture fails with a clear configuration error when `TEST_DATABASE_URL` is missing or unsafe.

## What to test by boundary

| Area | Minimum proof appropriate to the change |
|---|---|
| Kernel/commit path | Valid write commits atomically with its Task-attributed Event; invalid proposal leaves no forbidden partial state; hashes/ownership/scope are checked. |
| Idempotency/retry | Replay does not duplicate durable effects or success Events beyond the contract. |
| Concurrency | Competing transitions/claims cannot both win a single-state transition or exceed a shared serialized bound. Run against PostgreSQL where DB locking semantics are part of the behavior. |
| Objective lifecycle | Legal transitions succeed, illegal transitions fail, Event/provenance is preserved, and concurrent/conflicting transitions are rejected. |
| StateAssessment | Identical authoritative inputs yield identical normalized data/basis hash; assessment does not write authoritative state. |
| Strategy | Schema, identity, ownership, supported capability, policy/budget, prerequisite targets, cycles, replay, and historical reconstruction are tested. Tests must not claim to judge strategic wisdom. |
| Plan / R5-A | Accepted Strategy structure and provenance are preserved; Plan, Action mappings, initial Tasks, and required Events commit atomically; mapping cardinality, idempotency, immutability, and prerequisite admission hold. Reconstruct from durable records after restart; missing/corrupt/inconsistent records fail clearly without fabrication or silent repair. Test failure rollback as well as success. |
| TeamPolicy daily Task-start quota (R5-A) | Use durable `task_started` Events as the accounting source. Test below-limit success; final available unit under concurrent admission; exhausted rejection without a start Event, Task transition, or attempt increment; successful retries count again; UTC day-boundary behavior; absent/unlimited and zero quota; invalid type/range values (including booleans, floats, and strings); PlanService/TaskRuntime validation consistency; rollback on failed operations. This is Task-count enforcement, not monetary/token-cost accounting. Keep ADR-0027's status unchanged unless separately accepted. |
| Plan lifecycle / R5-B | Test `active → completed` and `active → stopped`; stale/illegal transitions; terminal-state protection; completion preconditions from durable Task status and successful outcome Events; valid/invalid stop reasons; required same-Objective successor on supersession; same-Task replay and conflicting reuse; concurrent transitions; atomic Event/state rollback; restart reconstruction. Verify PostgreSQL locking and migration behavior on a disposable database. |

## R5-B verification

The R5-B lifecycle operation is `PlanService.transition` (`core/plans.py`), with durable state in the `plans` table as changed by migration `0007_plan_lifecycle` and coverage in `tests/test_plan_lifecycle.py`.

Tested against disposable PostgreSQL:

- **Legal transitions and durability.** `active → completed` and `active → stopped` persist the lifecycle state and one attributable success Event (`plan_completed` / `plan_stopped`) in one transaction; the Plan and its Action/Task mapping remain reconstructable afterwards.
- **Completion preconditions.** Completion is rejected when a linked Task is not `done` (`plan_tasks_not_done`), when an Action lacks exactly one linked Task (`plan_actions_incomplete`), and when a linked Task has no durable successful ingestion outcome Event (`completion_evidence_missing`). A `done` status alone is rejected.
- **Stop reasons and supersession.** Missing and invalid stop reasons are rejected; a successor reference is rejected for non-superseded stops, for an unknown Plan, for a Plan of another Objective, for the Plan itself, and for a successor that is not active; an accepted supersession records the successor reference.
- **Terminal-state protection.** A terminal Plan rejects reopening from another Task, both with a stale expected status and with its own terminal status as the expectation.
- **Idempotency and conflicting reuse.** A matching same-Task retry replays the recorded Event and adds no second Event; a conflicting request on the same Task is rejected with `task_outcome_conflict`.
- **Stale and concurrent transitions.** A wrong expected status is rejected; two concurrent transitions on one Plan produce exactly one winner and one rejection.
- **Rollback.** An injected failure while writing the success Event leaves the Plan status, stop reason, and successor reference unchanged, with no success Event committed and no partial state.
- **Lifecycle reconstruction.** Reconstruction after restart reports the persisted lifecycle state; a missing lifecycle Event, a tampered lifecycle Event, and a contradictory supersession reference fail clearly rather than being repaired or accepted.
- **Database-level protection.** Invalid status, stop reason, and lifecycle combinations, and a supersession without a successor, are rejected by database constraints; updates to immutable Plan intent (budget, completion condition, proposal hash) are rejected by the scoped intent trigger.
- **Migration paths.** Verified on disposable databases: fresh installation to `0007_plan_lifecycle`, upgrade from the previous head, a `0007 → 0006 → 0007` round trip with an identical schema, and a refused downgrade while a non-active Plan exists.

### Post-fix verification — 2026-10-24

After strengthening lifecycle Event-payload validation and validating history before same-Task replay (commit `1012aaa`):

- `uv run pytest tests/test_plan_lifecycle.py -q` — **36 passed**.
- `uv run pytest tests/test_plans.py tests/test_task_runtime.py tests/test_strategy.py -q` — **147 passed**.
- `uv run pytest -q` — **258 passed**, with `TEST_DATABASE_URL` set to the disposable `watch_r5b_fresh` database.
- `uv run ruff check core/plans.py tests/test_plan_lifecycle.py` — passed.
- `uv run mypy core` — passed, 11 source files.
- `git diff --check` — passed.

The four additional parameterized tampering cases cover `stopped_reason`, `operation`, `expected_status`, and `target_status`; another test verifies that a same-Task retry rejects a tampered lifecycle Event instead of replaying it. The follow-up changed no schema or migration, so the migration-path results above are the earlier R5-B verification and were not rerun in this post-fix pass. The persistent `watch` database was not used.

### Database constraint follow-up — verified on disposable PostgreSQL (2026-10-24)

Review of migration `0007_plan_lifecycle` found that `ck_plans_lifecycle_state` did not require `successor_plan_id IS NULL` for stopped Plans with reason `abandoned` or `invalidated`. Correction commit `95a1e8e` adds migration `0008_plan_lifecycle_state` and two parameterized regression cases for the invalid combinations.

Programmer-reported verification on the corrective branch at `c99858f`:

- Database initially at `0007_plan_lifecycle`; `uv run alembic upgrade head` succeeded and `uv run alembic current` reported `0008_plan_lifecycle_state (head)`.
- `uv run pytest tests/test_plan_lifecycle.py -q` — **38 passed**.
- `uv run pytest tests/test_plans.py tests/test_task_runtime.py tests/test_strategy.py -q` — **147 passed**.
- `uv run pytest -q` — **260 passed**.
- `uv run ruff check .` — passed.
- `uv run mypy core` — passed, 11 source files.
- `git diff --check` — clean.

Both `DATABASE_URL` and `TEST_DATABASE_URL` targeted the disposable `watch_r5b_fresh` database, not the persistent `watch` database. This follow-up verified upgrade from `0007` to `0008`. After synchronizing the documentation commits, the programmer also successfully downgraded to `0007_plan_lifecycle` and upgraded back to `0008_plan_lifecycle_state` on the same disposable database. A fresh full-chain installation through `0008` was not rerun, and schema equivalence after the round trip was not separately compared. The results are programmer-reported local verification, not an independent rerun from this documentation update.

**Unresolved dependency, distinct from the tested behavior above.** No component in the current codebase moves a Task to `done`; `docs/architecture.md` §4 assigns the `running → done` transition to the worker/execution path, which this repository does not implement. The completion-precondition tests therefore exercise durable Task/Event state prepared for the test. Preparing that state is not a delivered capability, and these tests do not demonstrate an end-to-end executable Plan completion. `PLAN.md` records this dependency and its effect on the R5 gate.

## R5-A failure-oriented verification

In addition to success-path tests, assert that reconstruction and failed operations do not create or preserve a falsely valid state. Cover missing required Plan Actions, Tasks, mappings, provenance, or Events; inconsistent Action/Task references; and altered identity/hash data where those records are part of the contract. Invalid durable state must fail explicitly rather than be fabricated, silently repaired, or accepted.

For atomic operations, inject or simulate failures at meaningful persistence boundaries and verify that no partial Plan, Action mapping, Task transition, quota consumption, or required Event remains committed. Run concurrency and locking behavior against disposable PostgreSQL, not a substitute database whose locking semantics differ from production.


## R6-E Step 3 — Task-attributed generation cost

Run the following focused tests on the disposable PostgreSQL test database.
Concurrency and injected Event-write rollback are PostgreSQL behavior tests and
must not be substituted with SQLite.

```bash
uv run pytest tests/test_generation.py tests/test_generation_cost.py tests/test_strategy_proposer.py tests/test_state_assessment.py -q
uv run ruff check core tests migrations
uv run mypy core
uv run alembic upgrade head
uv run alembic current
uv run pytest -q
git diff --check
```

The new migration is `0011_task_generation_cost`; verify that
`0011_task_generation_cost (head)` is the single migration head before the
full suite. Set both `DATABASE_URL` and `TEST_DATABASE_URL` explicitly to the
same disposable database before executing database-backed checks. Never allow
the test fixture's local fallback to target the persistent `watch` database.

The focused tests must demonstrate reservation commit before the provider call,
Task-wide cost ceiling enforcement, exactly one reservation under concurrent
same-attempt calls, reconciliation from the pinned price card, unknown usage
retaining the full maximum, usage overrun preventing Strategy acceptance,
retries charging against previous attempts, Strategy disposition provenance,
and rollback/recovery when the reconciliation Event write fails. The real
Cloudflare API smoke is separate from this deterministic test suite and is not
required for CI.

## R6-F planned verification

R6-F is divided into four checkpoints. Each requires focused tests, applicable full-suite/static checks, and disposable-PostgreSQL verification for migrations, transaction atomicity, constraints, locking, and replay. The detailed acceptance matrix is in [the R6-F implementation plan](development/r6-f-implementation-plan.md).

| Checkpoint | Required proof |
|---|---|
| 1 — Evaluation and canonical learning foundation | Fresh migration from the preceding head with one Alembic head; Evaluation lifecycle; Team/Outcome/Signal/Snapshot/hash/quote validation; multi-record evidence representation; Task scope and TaskRuntime result fencing; rollback and database constraints. |
| 2 — ExperienceDistiller and LearningChange proposal | Deterministic evidence pack/hash; fake-provider valid/invalid/malformed/error cases; one-case Practice and distinct-Task cross-case threshold; contrary evidence and uncertainty preservation; stale/cross-Team reference rejection; reservation-before-call and unknown/overrun cost behavior; proposal replay. |
| 3 — Operator approval and canonical commit | Trusted Operator identity; create-only approve/reject; stale-evidence and concurrent-decision rejection; atomic rollback; exact replay and crash recovery; no revise/retire production path; proof TeamPolicy cannot be changed. |
| 4 — Team Experience projection and retrieval | Migration to one head at `0013_team_experience_projection`; TeamPolicy schema v1/v2 and pinned review-date assignment; positive non-boolean interval validation with no default; UTC arithmetic/exact due boundary; NULL/due exclusion; deterministic `review_knowledge` Task completion/replay with atomic status/Event/Outcome; separate Team Experience projection and publication-state constraints; `stale` on provider/index failure, atomic chunks+`published`, `ineligible` for NULL/due; failure leaves canonical rows unchanged; rebuild/retry/idempotency; canonical rechecks at indexing/retrieval/Context; dual-core FTS/vector RRF and combined eight-passage/8,000-character limit; Context v2 provenance and v1 replay; later-Task reuse.

Use deterministic fake providers in CI. ADR-0031 selects a provider for R6-E only; separate R6-F provider/model approval is required before any production distillation request. Never use the persistent `watch` database for these checks.

## Automated CI

`.github/workflows/ci.yml` runs the verification chain on every push to `main` and `r6a-step1-schema-outcome` and on every pull request. It provisions a disposable `pgvector/pgvector:pg16` service container, installs the locked dependency set with `uv sync --locked`, applies `alembic upgrade head` to a fresh database, asserts exactly one migration head and that the database is at that head, then runs `ruff check core tests migrations`, `mypy core`, and `pytest -q`.

CI is a repeatable check, not milestone evidence by itself. A green CI run proves only the named commands in that environment; it does not close a milestone or replace the disposable-database verification required by a phase gate. The workflow targets its own service container and never the persistent `watch` database.

## Invariant and architecture tests

Maintain tests for the invariants relevant to the slice, including the proposal/commit authority boundary, immutable Snapshots/evidence, commit-time revalidation, Task write scope, and idempotency. Use `docs/invariants.md` for the normative invariant list and `docs/tasks.md` for the exact scope of each Task type.

## Reporting evidence

For each check state:

- command/environment used;
- pass/fail and salient failure;
- whether it was focused or full-suite;
- any checks skipped and why;
- whether verification is freshly run or only recorded in an existing document.

Do not describe disposable database setup as an independent milestone exit criterion unless the milestone explicitly says it is one.



## R6-F Checkpoint 2 — ExperienceDistiller and proposed LearningChange

Checkpoint 2 reuses migration head `0012_learning_foundation`; it adds no migration. The new focused tests exercise the evidence-pack and proposal path through a deterministic injected provider. Do not configure Cloudflare or another live provider for these tests: ADR-0031 authorizes Cloudflare for R6-E only, and a separate R6-F provider decision remains required.

Run:

```bash
uv run alembic upgrade head
uv run alembic heads
uv run pytest tests/test_experience_distiller.py tests/test_generation_cost.py tests/test_evaluations.py
uv run ruff check core tests migrations
uv run mypy core
uv run pytest -q
git diff --check c8e7317^1...c8e7317
```

Use a fresh disposable PostgreSQL database even though this checkpoint has no new migration. Confirm the single head remains `0012_learning_foundation`. The Checkpoint 2 tests cover deterministic and bounded canonical evidence packs; terminal source Task/Outcome and Evaluation provenance; one-case Practice versus distinct-Task multi-case abstraction; supporting/challenging/mention stance retention; stale/mutated evidence both before and during a provider call; supporting/challenging/mention stance classification; cross-Team/missing references; reservation-before-provider, provider failure/model mismatch, invalid output, unknown/overrun costs, replay after finalization, concurrent duplicate calls, and typed TaskRuntime completion. Verify that a proposed LearningChange is the only Team Experience-domain write: no KnowledgeItem, TeamPolicy, or retrieval projection is created.

The disposable PostgreSQL test procedure must bind both `DATABASE_URL` and `TEST_DATABASE_URL` to the disposable instance, restore both variables afterward, and stop only the container it created. Never run these checks against the persistent `watch` database. Report actual command output; hosted CI does not replace the operator-local check.

## R6-F Checkpoint 3 — Host-invoked Operator adapter and canonical learning commit

Checkpoint 3 implements a thin in-repository adapter invoked in-process by a host application. The host authenticates and authorizes the Operator; Watch adds no deployed API/CLI or authentication subsystem. Fake principals/authorizers test the in-process contract, not production authentication.

**Scope:** accept/reject only genuine create-operation LearningChanges emitted by the authorized Checkpoint 2 ExperienceDistiller. The adapter accepts a typed issuer/subject principal plus exact Team/action grants, creates/replays one pending approval Task and request Event from a host idempotency UUID, and composes ordinary TaskRuntime admission, LearningCommitService decision, and TaskRuntime finalization. The decision service revalidates the canonical proposal, source Outcomes/Evaluations/EvidenceLinks/Snapshots, same-Team ownership, pinned TeamPolicy version, actor and current attempt. Acceptance atomically creates one active KnowledgeItem v1 and records the complete committed state and Task/operator attribution. Rejection records a non-empty reason and attribution without creating a KnowledgeItem. TaskRuntime writes the terminal Outcome/Snapshot/Event and owns all lifecycle transitions. No schema migration was introduced.

**D12 competing-request behavior:** different idempotency keys may create separate approval Tasks while a LearningChange is proposed, but the LearningChange row lock allows only one canonical decision to win. An admitted losing Task must not remain running: the adapter records one TaskRuntime terminal failure with reason learning_change_already_decided and returns a typed conflict. If the process stops before that failure is finalized, the existing 60-second recovery reconstructs the same attempt-fenced failure before retry/exhaustion. A same-request replay returns the same conflict and does not add another Outcome or KnowledgeItem. This remains inside the one existing TaskRuntime; no dispatcher, scheduler, or schema change is added.

**Hosted verification on the review follow-up head b9f1baf5362cd899ccc96ceecef99484bd52b2d2:** CI run 41593590306 passed fresh PostgreSQL migrations and exactly one Alembic head at 0012_learning_foundation, Ruff, mypy (27 source files), and 579 full-suite tests. Focused additions in tests/test_experience_distiller.py exercise both direct losing-request finalization and interrupted-recovery finalization/replay.

**Final operator-local verification:** the merged C3 head `891bea490099a7478ef3538645f8924615187500` passed fresh disposable PostgreSQL migration/head checks, 85 focused tests across `test_operator_application.py`, `test_experience_distiller.py`, and `test_task_runtime.py`, Ruff, mypy (27 source files), 579 full-suite tests, and `git diff --check`. The worktree was clean, the disposable container was removed, and database environment variables were restored. The earlier C4 run on `8333d69` predates C3 integration and does not verify the combined C3+C4 branch.

The tests are located in the files that actually exist:
- tests/test_operator_application.py: typed principal validation, Team/action authorization, request Task/Event creation, same-key replay/conflict, corrupt request Event rejection, duplicate same-key concurrency, approval-only no-deadline admission, malformed Task shape, and request fingerprint/identity tampering.
- tests/test_experience_distiller.py: real create-proposal acceptance/rejection, exact decision replay, evidence/actor/policy tampering, atomic rollback, synchronous adapter completion, crash before/after decision commit, stale attempt fencing, and distinct-key competing approval Tasks (direct conflict and interrupted recovery).
- tests/test_task_runtime.py: ordinary Task admission and lifecycle regressions, including generic deadline/quota behavior.

Focused test command:
    uv run pytest tests/test_operator_application.py tests/test_experience_distiller.py tests/test_task_runtime.py -q

For full verification use a fresh disposable PostgreSQL instance, bind both DATABASE_URL and TEST_DATABASE_URL to it, then run uv sync --locked, uv run alembic upgrade head, confirm one head/current at 0012_learning_foundation, the focused tests above, uv run ruff check core tests migrations, uv run mypy core, uv run pytest -q, and git diff --check origin/main...HEAD. Restore both database environment variables and remove only the container created by the check. Never use the persistent watch database; no live generation provider is called.

**C3 closure:** PR #31 is merged to `main` at `99f8b6bbd76521eaac47761dcf432ebb3c0d28e3`. Final operator-local disposable-PostgreSQL verification passed 85 focused tests, 579 full-suite tests, Ruff, mypy (27 source files), fresh migration to the single head `0012_learning_foundation`, and `git diff --check`. D10 remains resolved: C3 is create-only; revise/retire proposal production and commitment are deferred to separately authorized lifecycle work. D7's review-date semantics are implemented in C4, not written through the C3 approval scope.

## R6-F Checkpoint 4 — Team Experience projection and later-Task retrieval

Checkpoint 4 was separately authorized on 2026-11-02. It implements the resolved D7 contract and publishes only eligible accepted canonical Team Experience through a separate regenerable projection.

**Implementation boundaries**
- Migration `0013_team_experience_projection` adds TeamPolicy rules-schema version support plus separate `team_experience_chunks` and `team_experience_index_state` tables. The Signal-only `knowledge_chunks.signal_id` projection remains unchanged.
- Canonical acceptance reads optional `review.knowledge_item_interval_days` from the approval Task's pinned TeamPolicy version. The interval must be a positive non-boolean integer; there is no default. `review_after` is calculated from canonical `committed_at` in UTC. Missing configuration yields NULL, which is ineligible for Team Experience retrieval.
- `TeamExperienceIndexer` verifies the accepted create LearningChange, approval Task, canonical decision Event and terminal Outcome, committed KnowledgeItem state, current version, active status, and future review date. It rechecks canonical state after embedding before atomically publishing chunks and `published` state. Failures preserve canonical acceptance, mark publication `stale`, and keep chunks undiscoverable. NULL/due items become `ineligible`; `rebuild_all()` retries stale rows idempotently.
- `HybridKnowledgeRetriever` reuses the existing BGE-M3 embedding interface, PostgreSQL full-text search, pgvector, and reciprocal-rank fusion across Domain Knowledge and Team Experience. It applies one combined limit of eight passages and 8,000 Unicode characters.
- Context v2 records per-core provenance, KnowledgeItem version/hash, LearningChange identity, chunk details, and embedding identity. Existing same-Task Context v1 snapshots replay immutably; a later Task performs fresh retrieval.
- `TaskRuntime.complete_knowledge_review(task_id)` runs an already-enqueued ordinary `review_knowledge` Task through existing admission/finalization. Due item transitions, Task-attributed Event, terminal Outcome/Snapshot, and Task completion are atomic and replayable. No new scheduler, dispatcher, or Task runtime was introduced.

**Prior hosted verification (before C3 reconciliation):** [run 41589798190](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41589798190) passed on code head `3682f7e270ca65820e064d68c6e0bef5c390c5da` with 588 tests. **Fresh hosted verification after reconciliation:** [run 41598895890](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41598895890) passed on exact combined head `923268b0efda16d2c87e1b53aba2acb1990680ad`: fresh PostgreSQL migration to one `0013_team_experience_projection` head, Ruff, mypy (27 source files), and **590 tests**.

**Local verification gate:** rerun on the reconciled PR #32 head, using a fresh disposable pgvector PostgreSQL database with both `DATABASE_URL` and `TEST_DATABASE_URL` bound to it. Run `uv sync --locked`, `uv run alembic upgrade head`, confirm exactly one head/current at `0013_team_experience_projection`, then:

```bash
uv run pytest tests/test_team_experience.py tests/test_context_assembly.py tests/test_knowledge_index.py tests/test_experience_distiller.py tests/test_operator_application.py tests/test_task_runtime.py -q
uv run ruff check core tests migrations
uv run mypy core
uv run pytest -q
git diff --check origin/main...HEAD
```

Restore both database environment variables and remove only the disposable container. Never use persistent `watch`; no live generation provider is called.

**Merge and operator-local verification record (2026-11-03):** PR #32 merged C4 to `main` at `c8e7317da6144a15725231e499b07f1c110c4c22`. The combined C3+C4 local run was executed on PR #33 head `7bd7c5df95e56ee6658f6817d71eededf6f784c5`, before PR #33 merged. It used the isolated pgvector PostgreSQL container `watch-r6f-local-20261103`, database `watch_r6f_check`, host port `55464`; the script removed that temporary container and ran its `finally`-block environment restoration commands. The tested PR head and PR #33 merge commit `de1af38d67a7e79d71110bdda7155244717fbf73` have the identical Git tree SHA `5bca55cddea91d6d76b5c3581bfaa3645e03bb82`. After the merge, local `main` was fast-forwarded to `de1af38`, verified equal to `origin/main`, and confirmed clean. Therefore the local results apply to the exact source tree now on `main`; no separate test execution after switching to `main` is claimed.

- `uv sync --locked`: passed.
- `uv run alembic upgrade head`: passed; `alembic heads` and `alembic current` both identified the single expected revision `0013_team_experience_projection`.
- Focused C3/C4 command (the six files listed in the local verification procedure above): **118 passed** in 17.95 seconds.
- `uv run ruff check core tests migrations`: passed.
- `uv run mypy core`: passed, no issues in 27 source files.
- `uv run pytest -q`: **594 passed** in 67.11 seconds.
- `git diff --check origin/main...HEAD`: passed on the tested feature branch.
- Final local synchronization: `main` and `origin/main` both at `de1af38d67a7e79d71110bdda7155244717fbf73`; working tree clean.

**C4 local verification disposition:** PASS for the exact merged source tree. The operator-local run happened immediately before merge rather than after the merge commit; tree identity was explicitly verified, and the subsequent fast-forward synchronization confirmed the local `main` snapshot. Do not describe this as a post-merge test rerun. R6-G was separately authorized, verified and formally closed after explicit Operator approval and merge of PR #35 on 2026-11-04.

## R6-F Checkpoint 1 — Evaluation and canonical learning schema

Checkpoint 1 adds `0012_learning_foundation`, Evaluation/EvidenceLink persistence and services, and canonical KnowledgeItem/LearningChange schema foundations. It also adds typed Evaluation terminal result categories to the existing TaskRuntime.

Run the focused checks first:

```bash
uv run alembic upgrade head
uv run alembic heads
uv run pytest tests/test_evaluations.py
uv run ruff check core/evaluations.py core/models.py core/task_runtime.py tests/test_evaluations.py migrations/versions/0012_learning_foundation.py
uv run mypy core
uv run pytest -q
git diff --check
```

Use a fresh disposable PostgreSQL database. Confirm one Alembic head and a successful upgrade from `0011_task_generation_cost`; never use the persistent `watch` database. The Evaluation tests cover same-Team Outcome references, domain-scoped Signal references, exact Snapshot/hash/quote validation, evaluator identity/revision, proposal idempotency, recorded/rejected dispositions, Task write scope, and TaskRuntime terminal finalization. This checkpoint deliberately does not implement ExperienceDistiller, LearningChange proposal/approval writes, KnowledgeItem commits, or Team Experience indexing.
## R6-G implementation, verification and formal closeout (2026-11-04; COMPLETE)

**Implementation status: COMPLETE and formally closed 2026-11-04.** The bounded implementation on `r6g-implementation-20261103` was verified, the ten-proof review passed, and the Operator explicitly approved the exit gate. PR #35 merged to `main` at `56745b613b5b77a21a514b4e261d3450f90c0df1`. The implementation code head was `2a55acfeadaf37e23b9f2cffd8819b7b460ba6b3`; subsequent PR commits were documentation-only.

### Three-step resolution

1. **Evaluator source — implemented.** Use deterministic code-defined rules for `ingest_source` terminal Outcomes only. Validate terminal result category, current attempt, Task status, terminal Event payload, ingestion business Event, and canonical same-Team/domain Signal/Snapshot identity/hash. Map valid `success_signal_created` and `success_no_change` to `worked`; map a consistent `terminal_failure` to `failed`. Reject inconsistent, stale, cross-Team, corrupt or unsupported evidence without creating an Evaluation. The conclusion is execution-contract conformance only, not source truth or Objective success. Persist the fixed rule identity/revision. No human/model Evaluation producer is included.
2. **Integrated fixture/service sequence — implemented.** `tests/test_r6g_vertical_slice.py` builds one Team/Objective and three Plan-materialized ingestion cases (new Signal, legitimate no-change, terminal failure), baseline Domain Knowledge indexed by deterministic fake embeddings, real hybrid Context retrieval, fake StrategyProposer, StrategyService, PlanService and TaskDispatcher. TaskRuntime creates each evaluator Task and immutable request Event atomically with source terminalization; the pure D9 evaluator proposes, EvaluationService records, and TaskRuntime finalizes or recovers the Evaluation Task. ExperienceDistiller includes the failed Task in a versioned v2 evidence pack as contrary evidence while preserving canonical EvidenceLink stance and historical v1 reconstruction. The fixture continues through separate one-case rejection and three-case Operator acceptance, canonical Team Experience indexing, and later-Task retrieval. The implementation retains one TaskRuntime, a narrow ingestion-only TaskDispatcher, and no production R6-G provider.
3. **Acceptance mapping — implemented tests; technical review and Operator exit approval complete.** The focused R6-G test modules now exist: `tests/test_rule_evaluator.py`, `tests/test_evaluation_tasks.py`, `tests/test_r6g_distillation.py`, and `tests/test_r6g_vertical_slice.py`; Strategy, Plan and ExperienceDistiller suites also contain R6-G coverage. See the table below for the ten proofs and the component/integrated test boundaries.

### Ten acceptance criteria mapped to tests

| # | Acceptance proof | Existing component coverage | R6-G proof location / acceptance check |
|---:|---|---|---|
| 1 | Configured HTTPS fixture ingestion; no arbitrary URL; source allowlist. | `tests/test_r6b_dispatcher.py` | `test_r6g_vertical_slice.py` dispatches only PlanAction-configured sources; R6-B dispatcher tests retain unsafe/unconfigured source and restricted-fetch rejection coverage. |
| 2 | Authorized Domain Knowledge retrieval, Team/domain/status/hash filtering, hybrid retrieval and global context bound. | `tests/test_knowledge_index.py`, `tests/test_context_assembly.py`, `tests/test_team_experience.py` | The integrated fixture uses the real dual-core retriever; component suites prove Team/domain/status/hash filtering and the eight-passage/8,000-character Context bound. |
| 3 | Immutable content-addressed Context Snapshot and Task-attributed manifest. | `tests/test_context_assembly.py` | Integrated Strategy consumes the actual assembled Context; component tests prove exact Snapshot/Event replay and reject changed/tampered Context provenance. |
| 4 | Fake StrategyProposer → StrategyService validation → immutable Plan and ordinary Tasks; rejected proposal creates no Plan. | `tests/test_strategy_proposer.py`, `tests/test_plans.py`, `tests/test_strategy.py` | The integrated fixture materializes from accepted Strategy provenance; the StrategyProposer suite separately proves rejected Strategy Task finalization and absence of a Plan. |
| 5 | One TaskRuntime, bounded fetch, retries/exhaustion, crash recovery, read-only Plan execution assessment and no duplicate ingestion/Outcome/Event. | `tests/test_r6b_dispatcher.py`, `tests/test_execution_assessment.py`, `tests/test_task_lifecycle_retry.py`, `tests/test_task_lifecycle_recovery.py`, `tests/test_task_runtime.py` | Integrated three-case fixture proves mixed Plan assessment; R6-B/lifecycle suites cover restricted fetch, retry/exhaustion, crash replay and one terminal record. |
| 6 | Deterministic Evaluations from immutable Outcomes, with recorded evaluator identity/revision and exact evidence provenance. | `tests/test_evaluations.py` | `test_rule_evaluator.py` covers all three D9 results, deterministic drafts, terminal-Event mismatch, cross-domain Signal and contradictory business-event rejection; `test_evaluation_tasks.py` covers immutable request binding, rollback, concurrency and recovery. |
| 7 | At least two independently evaluated Task Outcomes plus a contrasting case; deterministic evidence basis/hash; preserve contrary evidence. | `tests/test_experience_distiller.py` | `test_r6g_distillation.py` proves two successful cases plus one terminal failure remain three distinct v2 cases, with failure reason/case-relative contrary stance and unchanged canonical EvidenceLink stance; replay is order-independent. |
| 8 | Rejection creates no usable KnowledgeItem; acceptance commits one canonical create-only version. | `tests/test_experience_distiller.py`, `tests/test_operator_application.py` | Integrated fixture rejects a distinct one-case proposal and accepts the independent three-case create proposal through the Operator adapter; component tests prove atomic attribution and commit/replay behavior. |
| 9 | Current eligible Team Experience is published and retrieved by a later Task without transcript carry-over; stale rows excluded/rebuilt. | `tests/test_team_experience.py`, `tests/test_context_assembly.py` | Integrated fixture indexes the accepted canonical item and retrieves its current version/provenance in a different later Task; Team Experience component tests cover stale, due, NULL-dated, cross-Team and unpublished exclusion/rebuild. |
| 10 | Provider, transaction, projection, recovery and replay failures preserve canonical atomicity. | `tests/test_generation_cost.py`, `tests/test_experience_distiller.py`, `tests/test_operator_application.py`, `tests/test_team_experience.py`, `tests/test_task_runtime.py` | R6-G enqueue tests prove rollback on request creation failure, concurrent duplicate finalization and one request; component suites cover provider/commit failure, projection staleness/rebuild, committed-record recovery and terminal replay. |


### Technical acceptance review — 2026-11-04

**Review disposition: 10/10 PASS — supported by implementation and test evidence.**

This is a code/test review of implementation commit `2a55acfeadaf37e23b9f2cffd8819b7b460ba6b3`, followed by explicit Operator approval of the R6 exit gate on 2026-11-04. Review checked the integrated fixture, mapped component tests and relevant failure/recovery/replay paths.

| # | Review disposition | Evidence reviewed |
|---:|---|---|
| 1 | **PASS** | The integrated fixture dispatches only PlanAction-configured sources. Dispatcher tests reject missing/unconfigured sources before admission and verify the configured URL is passed to the fetcher. RestrictedFetcher tests cover HTTPS/canonical URL validation, DNS/private/loopback/metadata screening, redirects, HTTP status, media type, content encoding and size limits. |
| 2 | **PASS** | Domain Knowledge tests cover current source allowlist, Team/domain scope, Snapshot/hash and tampered chunk rejection, semantic/vector retrieval and eight-passage/8,000-character limits. Context assembly rechecks retrieved material against current policy. Team Experience filters are covered separately in item 9. |
| 3 | **PASS** | Context tests verify content-addressed immutable Snapshot plus Task-attributed manifest Event, exact replay, changed-context conflict, current-policy revocation and bounds. The integrated Strategy consumes the assembled Context. |
| 4 | **PASS** | StrategyProposer routes proposals through StrategyService. Rejected proposals produce a durable rejection and no Plan; accepted proposals materialize immutable Plan Actions and ordinary Tasks. TaskRuntime typed completion, replay and interrupted recovery are tested. |
| 5 | **PASS** | The integrated fixture uses one TaskRuntime and the narrow configured-source TaskDispatcher, then rebuilds a deterministic read-only Plan assessment across two successful cases and one terminal failure. R6-B/lifecycle component tests cover retry/exhaustion, crash recovery, attempt fencing and no duplicate Signal, ingestion Event or Outcome. |
| 6 | **PASS** | The D9 evaluator is deterministic and bound to exact configured-source request, current attempt, terminal Outcome, Events, business Event and canonical Signal/Snapshot hashes. Tests cover all three mappings, tampering, cross-domain evidence, contradictory business Events, atomic enqueue rollback, concurrent duplicate finalization, committed-Evaluation recovery, Evaluation evidence revalidation and terminal replay. |
| 7 | **PASS** | The R6-G distillation test builds two distinct successful source cases plus one terminal-failure case; the evidence-basis hash is order-independent; each v2 basis case is marked; failed evidence becomes case-relative contrary evidence without changing canonical EvidenceLink stance. Omitting contrary evidence is rejected. |
| 8 | **PASS** | The integrated fixture rejects a one-case proposal and proves it creates no KnowledgeItem, then accepts a separate three-case create proposal. Component tests verify trusted Operator identity/grant, create-only preconditions, atomic LearningChange/KnowledgeItem/Event commit, replay and rollback when the decision Event fails. |
| 9 | **PASS** | Team Experience tests verify eligible canonical publication, idempotent indexing, stale publication exclusion and rebuild after provider failure, due/NULL/review-status exclusion, tamper/canonical-change invalidation, and retrieval by a separate later Task through immutable Context. The integrated fixture verifies the same path with the accepted KnowledgeItem and provenance. |
| 10 | **PASS** | Failure evidence spans evaluator-request transaction rollback and concurrent replay, provider/cost failure, LearningChange decision-Event rollback, publication staleness/rebuild, typed TaskRuntime recovery for Evaluation/Strategy/Plan/Operator results, and terminal/request/projection replay. |

**Qualifications and non-blocking observations**

- The integrated fixture deliberately uses deterministic fake fetch, Strategy, distillation and embedding providers; it does not make live outbound network or real model-provider calls. The actual RestrictedFetcher URL/DNS/HTTP safety components and hybrid retrieval behavior are tested in component suites. This is an offline deterministic qualification, not live-provider qualification.
- “Worked” means configured-source execution-contract consistency only. It does not establish source truth, causal impact or Objective achievement. The failed case is preserved as contrary operational evidence, not treated as scientific proof of a causal counterexample.
- One test docstring in `tests/test_r6b_dispatcher.py::test_dispatcher_uses_the_configured_source_not_a_caller_supplied_url` says a `RestrictedFetcher` is bound, while the test currently injects `FakeFetcher`. The assertion still checks that the configured PlanAction URL is the one passed to the fetcher; URL/DNS/HTTP safety is covered by separate tests. This is a test-description inconsistency, not an implementation or acceptance blocker.
- No uncovered blocking gap was found against the ten documented criteria.

**Review disposition: ACCEPTED.** All ten criteria are supported by the code and tests; no blocking gap was found. The Operator explicitly approved the R6 exit gate on 2026-11-04, and PR #35 is merged. R6-G is formally closed.

### New test boundaries and execution rules

- `tests/test_rule_evaluator.py` tests all three D9 mappings, deterministic drafts and fail-closed terminal-event mismatch, cross-domain Signal and contradictory-business-event checks; it makes no model or network call.
- `tests/test_evaluation_tasks.py` tests atomic source-terminal enqueue, rollback on evaluator-request creation failure, concurrent duplicate terminal finalization producing one Outcome/request, exact request Task/Event shape, tamper rejection and committed-Evaluation recovery.
- `tests/test_experience_distiller.py` covers failed-source provenance, claim-relative contrary evidence, per-case v2 version markers, legacy unmarked-v1 reconstruction, and rejection when contrary evidence is omitted.
- `tests/test_r6g_vertical_slice.py` covers the integrated Objective Context → Strategy → Plan → three source Outcomes/Evaluations → distillation → Operator rejection/acceptance → Team Experience projection → later-Task retrieval path.
- Use fake Strategy and distillation generation providers, synthetic R6-E/R6-F test cost cards, deterministic test embeddings, and a deterministic restricted fetcher. No production R6-G evaluator provider or production R6-F distillation provider is approved or needed.
- Hosted CI on exact implementation head `2a55acfeadaf37e23b9f2cffd8819b7b460ba6b3` passed run [41782439302](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41782439302): fresh PostgreSQL migration and single-head validation, Ruff, Mypy, and **614 tests in 44.93s**. The earlier 610-test CI run is superseded by this final-head result.

**Programmer-local verification — 2026-11-04 (operator-reported on the exact implementation head).** On branch `r6g-implementation-20261103`, commit `2a55acfeadaf37e23b9f2cffd8819b7b460ba6b3`, the working tree was clean before and after verification.

- Environment: Python 3.12.12; `uv sync --locked` passed.
- Disposable PostgreSQL: container `watch-r6g-local-20261104-b`, image `pgvector/pgvector:pg16`, database `watch_r6g_check`, host binding `127.0.0.1:55466`. The database was confirmed fresh before migration (`0` user tables; no `alembic_version`). Both `DATABASE_URL` and `TEST_DATABASE_URL` targeted this database during the run and were restored afterwards. The container and its anonymous volume were removed after success; the persistent `watch` database was not targeted.
- `uv run alembic upgrade head` passed. `uv run alembic heads` and `uv run alembic current` both reported the single revision `0013_team_experience_projection (head)`.
- Focused R6-G suite (rule evaluator, evaluator Tasks, R6-G distillation/vertical slice, ExperienceDistiller, StrategyProposer and Plans): **134 passed in 32.23s**.
- `uv run ruff check core tests migrations` passed.
- `uv run mypy core` passed (29 source files).
- `uv run pytest -q` (full suite): **614 passed in 74.48s**.
- `git diff --check` passed; disposable container cleanup succeeded; final `git status --short --branch` was clean and `HEAD` remained `2a55acfeadaf37e23b9f2cffd8819b7b460ba6b3`.

This is operator-reported local evidence, recorded distinctly from hosted CI. It verifies implementation commit `2a55acfeadaf37e23b9f2cffd8819b7b460ba6b3`; the technical review and Operator approval are recorded above. The final PR-head CI run after documentation-only updates is [41788001379](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41788001379). PR #35 merged at `56745b613b5b77a21a514b4e261d3450f90c0df1`.
- Existing component tests do not satisfy integrated R6-G acceptance by themselves. The integrated and mapped component proofs were reviewed together before the Operator approved closure.

**Exit boundary: CLOSED — 2026-11-04.** Exact-head hosted and operator-local verification passed, the ten-proof technical review found no blocker, the Operator approved the exit gate, and PR #35 merged to `main`. The fake-provider/offline qualification and all scope non-goals remain part of the accepted record.

## R7-A — Evidence lineage and knowledge-quality assessment (COMPLETE — PR #39 merged 2026-11-04)

R7-A adds migration 0014_knowledge_quality, deterministic case-lineage classification, immutable KnowledgeQualityAssessment, narrow TaskRuntime-managed assess_knowledge_quality, and the assessment-bound guard on accepted KnowledgeItem creates.

Focused coverage: `tests/test_knowledge_quality.py` validates lineage/rubric; `tests/test_experience_distiller.py` validates enqueue, binding and recovery; `tests/test_operator_application.py` validates trusted adapter binding; `tests/test_r6g_vertical_slice.py` verifies integrated assessment-before-acceptance.

### Hosted exact-head verification

PR #39 tested head `47ffa532dacbc10b146ac7b0768302761a2a0b1b`. Hosted CI [41844600681](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41844600681) passed fresh disposable PostgreSQL migration to the single `0014_knowledge_quality` head, Ruff, Mypy, full suite and container cleanup.

### Operator-local exact-tree verification

The committed `scripts/test-disposable-postgres.ps1` ran on the same PR-head tree, identical to merge commit `75122a7b34c15e2445b81a2a719020667b55bf06`:

- Fresh disposable pgvector/pg16 container; both DATABASE_URL and TEST_DATABASE_URL targeted the same temporary database.
- Fresh migration passed; `alembic heads` reported the single `0014_knowledge_quality` head.
- Ruff passed; Mypy had no issues in 31 source files.
- Full suite: **631 passed in 79.22s**.
- Script restored both database environment variables and removed its disposable container.

No production evaluator provider was wired or selected; tests used deterministic fakes and no live model calls occurred. R7-A is complete and merged. R7-B is in documentation preparation only and is not authorized; R7-C citations/retrieval/downstream use remain unauthorized.


## R7-B B0 — design-freeze and documentation validation record (2026-11-05)

The Operator accepted all five B0 decisions, the R7-B D1 typed-assessment extension, and the D5 reciprocal-successor/publication-gate amendment on 2026-11-05. The accepted contracts are recorded in ADR-0032 and `docs/development/r7-b-implementation-plan.md`; the decision index, PLAN status, R7 entry gate, Task matrix, invariant, CHANGE_MAP, CONTEXT, and README are aligned by the B0 documentation integration.

**Accepted design checks:** confidence is part of semantic content identity; confidence-only revise is content-changing and clears validation; existing canonical evidence may support revalidation only while temporally relevant and source-valid; the trusted host identity remains bound in the approval-request fingerprint and decision record; the exact snapshot/content domain separators are frozen; and the complete D5 candidate, abandonment, edge-case, visibility, and graph-lock contracts are accepted. Snapshot-first history reconstruction remains conditional on B1 proof; any failure requires a separate Operator decision on the smallest append-only history record.

**Scope and verification boundary:** this record concerns documentation and architecture acceptance only. No source files, migrations, tests, Task registrations, provider configuration, active write scopes, or runtime behavior are changed by B0. No code test suite, database migration, or local disposable-PostgreSQL run is claimed by this documentation-only checkpoint. B0 closeout requires the documentation-only PR to pass its checks and merge. B1 remains unauthorized pending separate written Operator implementation authorization.


## R7-B B1 — final integrity corrections and exact-head verification (2026-11-06)

The Operator separately authorized B1 on 2026-11-05 and accepted the B1 phase on 2026-11-06. During final review, two integrity findings were corrected without expanding B1 scope.

**Final review corrections**

- The `0015_r7b_history` migration now requires every legacy create root to have exactly `version = 1`, `status = active`, and JSON `last_validated_at = null`. Regression tests use well-typed but semantically invalid values and prove rejection occurs before backfill. A valid companion KnowledgeItem is present in each malformed fixture; failed migration leaves the Alembic revision, pointer column state, all KnowledgeItem rows, and all stored LearningChange snapshots unchanged.
- Live supersession validation now requires a predecessor with a reciprocal `superseded_by_id` link to be `retired`. Tests reject reciprocal links from `active` and `needs_review` predecessors, accept a `retired` predecessor, and preserve pending-candidate behavior when the predecessor has no reciprocal link.

**Operator-local exact-head verification (reported 2026-11-06).** The committed code tree was tested on branch `r7b-b1-snapshot-history-proof` at `ca498ecd43207e72082332c803a74eb30173d41c`:

- A disposable `pgvector/pgvector:pg16` container was started as `watch-r7b-b1-local-0efc20cd9f`, with database `watch_r7b_b1_disposable` on temporary host port `26114`. Both `DATABASE_URL` and `TEST_DATABASE_URL` targeted this disposable database.
- `uv run alembic upgrade head` passed. `alembic heads` and `alembic current` both reported the single `0015_r7b_history (head)` revision.
- `uv run pytest tests/test_r7b_history_migration.py -q`: **33 passed in 17.36s**.
- `uv run ruff check core tests migrations` passed.
- `uv run mypy core` passed with no issues in 32 source files.
- `uv run pytest -q` (full suite): **690 passed in 105.00s**.
- `git diff --check 64d5fb19be541d80b3cb8941ce3359d4b69565c1...HEAD` passed. The final branch/worktree check was clean; the runner noted only the intentionally excluded local `sync-and-test-r7b-b1.ps1` script. It removed its disposable container. The persistent `watch` database was not targeted.

**Hosted-CI verification of the reviewed implementation tree:** PR head `08abdf17c65864fba832678230d1eddfa884ea04` passed hosted CI [run 42244835481](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42244835481) on 2026-11-06 (run 449). The workflow checked out that exact commit, applied migrations to a fresh PostgreSQL database and verified the single Alembic head; Ruff passed; Mypy found no issues in 32 source files; the full suite passed with **690 tests, 65 warnings in 46.89s**; and disposable PostgreSQL container cleanup passed. The warnings are Alembic's existing `path_separator` configuration deprecations. Git compare confirms that the nine commits between locally verified code head `ca498ecd43207e72082332c803a74eb30173d41c` and tested head `08abdf17c65864fba832678230d1eddfa884ea04` changed documentation only; no application code, migration, or test code changed after local verification. The later B1 status-closeout commits change documentation only; the latest PR-head workflow result is available from [PR #43](https://github.com/abtn/Watch-Architecture-Rev2/pull/43).

**Disposition:** both final-review findings are corrected. The corrected code tree passed operator-local exact-code-head verification, and the final B1 PR head passed hosted CI run [42246346103](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42246346103): 690 tests, fresh PostgreSQL migration/single-head checks, Ruff, Mypy, and cleanup all passed. Final technical review found no blocking B1 issue and zero unresolved inline review threads; the recorded technical review was COMMENTED, not an approval. PR #43 was subsequently merged and closed on 2026-11-06 at merge commit `d1a8b88fd930207142304fc9b0b7274de5de4992`. B1 is complete. B2 implementation was separately authorized by the Operator on 2026-11-06; Step 1 hosted verification is recorded below. B3–B6 and R7-C remain unauthorized.

## R7-B B2 Step 1 — v2 semantic content hash (2026-11-06)

The Operator separately authorized B2 implementation on 2026-11-06. Step 0 preflight/inventory and the accepted `legacy-opaque` compatibility amendment are recorded in ADR-0032 and the R7-B implementation plan. Step 1 implementation is submitted in draft PR [#45](https://github.com/abtn/Watch-Architecture-Rev2/pull/45), based on B1 merge commit `d1a8b88fd930207142304fc9b0b7274de5de4992`.

**Implemented scope (exact PR head `cd2426e64d86f32916be28f639ada19574f8607e`):**
- Adds the explicit `watch.r7b.knowledge-content.v2` content-hash scheme in `core/learning_history.py`.
- Hashes exactly the 14 accepted semantic fields using canonical JSON, fixed-point confidence normalization, UTF-8 domain-separator framing, one NUL byte, and SHA-256.
- Leaves identity, Team, lifecycle state, versions, review dates, pointers, and supersession links outside the semantic content hash.
- Routes the existing Team Experience hash helper through the v2 implementation.
- Adds focused regression tests for the fixed digest vector, all semantic fields, excluded identity/lifecycle fields, array ordering, confidence-only changes and normalization, canonical object-key ordering, invalid confidence, and the Team Experience entry point.
- The PR changes only `core/learning_history.py`, `core/knowledge_index.py`, and `tests/test_knowledge_content_hash.py`. It does not include the legacy projection migration, model changes, projection pins, retrieval changes, Context v3, or approval-path changes.

**Hosted exact-head verification:** CI [run 42286427354](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42286427354) checked out the exact PR head above and passed:
- Fresh PostgreSQL migration and verification of the single Alembic head.
- Ruff.
- Mypy: no issues in 32 source files.
- Full suite: **732 passed, 65 warnings in 48.36s**.
- Disposable PostgreSQL container cleanup.

The warnings are the existing Alembic `path_separator` configuration deprecations. CI did not target the persistent `watch` database. No Operator-local Step 1 verification is claimed in this record. PR #45 remains open and draft; the merge was not authorized. **Step 1 awaits Operator-local exact-head verification and explicit Step 1 acceptance. Do not begin Step 2 until that review/acceptance is recorded.** B3–B6 and R7-C remain unauthorized.

