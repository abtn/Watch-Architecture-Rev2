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

## R7-B B2 Step 1 — v2 semantic content hash (2026-11-06; merged 2026-11-07)

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

The warnings are the existing Alembic `path_separator` configuration deprecations. CI did not target the persistent `watch` database. Operator-local exact-head verification was subsequently reported on 2026-11-07 for commit `cd2426e64d86f32916be28f639ada19574f8607e`: 42 focused tests passed; Ruff passed; Mypy passed across 32 source files. PR #45 was merged to `main` at `18595356a3da93b47a8701c7e94fe7dbde098d55`. Step 1 is complete; Step 2 may proceed.



## R7-B B2 Step 2 — projection provenance pins (ACCEPTED AND MERGED — PR #46)

The Operator authorized B2 implementation on 2026-11-06. Step 1 was merged through PR #45 at `18595356a3da93b47a8701c7e94fe7dbde098d55` after hosted and Operator-local exact-head verification. Step 2 implementation was in PR [#46](https://github.com/abtn/Watch-Architecture-Rev2/pull/46), branch `r7b-b2-step2-projection-provenance`, verified implementation head `906ec3cf31510375343c2cc8e3cd03ef9fa74af5`; the PR's documentation closeout head was `fbe52fd971641121a20b64995f5b4f19cc6e3f54`.

The Step 2 change adds current-pointer and content-hash-scheme pins to Team Experience chunks and index-state rows; classifies historical projections as `legacy-opaque` with NULL current pointers; marks existing index-state rows stale; preserves existing projection hashes and embedding data; and adds same-Team foreign keys and scheme/pointer constraints. New indexer publications write the v2 scheme and current pointer.

The first hosted run failed before application tests because revision ID `0016_team_experience_history_pins` exceeded Alembic's 32-character `alembic_version.version_num` column. The identifier was shortened to `0016_team_exp_history_pins`. A subsequent run passed migration but found Ruff import/line-length issues; those were corrected before the verified implementation head.

**Hosted verification:** `906ec3cf31510375343c2cc8e3cd03ef9fa74af5` passed [CI run 42347539252](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42347539252): fresh PostgreSQL migration and single-head checks, Ruff, Mypy across 32 source files, 735 tests (74 warnings), and disposable-container cleanup.

**Operator-local verification:** Operator-local exact-head verification passed on `906ec3cf31510375343c2cc8e3cd03ef9fa74af5`: focused tests 18 passed, Ruff passed, and Mypy passed across 32 source files. A separate fresh disposable PostgreSQL run applied migrations to exactly one head (`0016_team_exp_history_pins`) and ran the full suite alone: **735 passed, 0 failed** in 89.17s (74 existing Alembic `path_separator` deprecation warnings). The container used a dynamically assigned localhost port and was removed by the script. A prior local full-suite attempt had 10 failures; none reproduced in the clean full-suite-only run. The cause of that earlier discrepancy was not established, and no source changes were made in response.

**Earlier local discrepancy:** A previous local full-suite attempt reported 725 passed and 10 failed. The ten failures did not reproduce in the separate fresh-database full-suite-only run above. Their cause was not established; no source changes were made in response. The successful clean run is the evidence used for this verification record.

**Acceptance and merge:** The Operator explicitly accepted Step 2 on 2026-11-07. PR #46 merged to `main` at `669d2e8140036ea4db07cbc44b33f6baa2e2608d`. Hosted CI on the final documentation closeout head passed [run 42350516648](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42350516648). Step 2 is accepted and closed. B2 Step 3 may proceed; B3–B6 and R7-C remain unauthorized.

## R7-B B2 Step 3 — current-pointer canonicality (ACCEPTED AND MERGED — PR #48; 738 TESTS PASSED LOCALLY AND HOSTED)

Step 2 was accepted and merged through PR #46 at `669d2e8140036ea4db07cbc44b33f6baa2e2608d`. Step 3 was explicitly accepted and merged through PR [#48](https://github.com/abtn/Watch-Architecture-Rev2/pull/48) at merge commit `1ba9f38ec2fa0b7c4a748181bce4096d8f65b356` (PR head `fcb9f4bd9b56b2353299828a7db39619a4650604`).

The canonicality reader now resolves `KnowledgeItem.current_learning_change_id`, validates create-root versus later-transition target semantics, and delegates full accepted-chain, snapshot, approval-task, pinned-policy, decision-event, committed-timestamp, and D7 overlay verification to B1's `reconstruct_knowledge_item_history`. Indexer, retriever, Context validation, and due-review readers load the current LearningChange pointer. Actual lifecycle commits remain create-only; no migration or schema change is introduced.

Synthetic accepted-revision tests cover:
- The current pointer resolving to a non-origin `revise` transition while the origin create is rejected as the current change.
- Indexing and retrieval of a valid reconstructed non-origin current change.
- Context assembly using a revised item while preserving the origin pointer in the existing manifest format.
- Due-review processing and D7 reconstruction when the current pointer is a non-origin transition.

**Hosted exact-head verification:** PR head `67cac9d7a4ec6b395fcc3a1d8465d8c400abde8a` passed [CI run 42351625886](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42351625886): fresh PostgreSQL migration and single-head checks, Ruff, Mypy (32 source files), **737 tests passed** (74 warnings), and disposable-container cleanup. An earlier CI attempt exposed a synthetic-fixture flush-order error; the fixture now persists the LearningChange before moving the KnowledgeItem pointer, and the final expanded run passed.

**Prior Operator-local exact-head verification (2026-11-07; before the final-review correction):** the Operator verified the then-current PR implementation head `326be859d36d82c042fe5b183e16a9168f7b3e4b`. Branch/HEAD/clean-worktree preflight passed; `uv sync --locked`, Ruff (`uv run ruff check core tests migrations`), and Mypy (`uv run mypy core`, 32 source files) passed. On a fresh disposable PostgreSQL container, Alembic upgraded to `0016_team_exp_history_pins`, exactly one migration head was present and the database revision matched it. Focused `tests/test_team_experience.py`: **17 passed** in 3.56s. The separate fresh-database full suite: **737 passed, 0 failed** in 114.89s. Both disposable containers were removed and the original process `DATABASE_URL` / `TEST_DATABASE_URL` values were restored. The 74 warnings are the existing Alembic `path_separator` deprecation warnings; they did not fail the run. No persistent `watch` database was targeted. This local verification predates the final-review correction below; it does not establish local verification of the corrected PR head.

**Final-review correction and corrected-head hosted verification (2026-11-07):** final review found that retrieval and Context validation did not enforce Step 2's current-pointer and content-hash-scheme pins consistently. The correction now:
- Requires the current LearningChange pointer on the KnowledgeItem, TeamExperienceChunk, and TeamExperienceIndexState to agree in the retrieval candidate SQL and verifier.
- Requires the chunk and index-state content-hash schemes to agree and equal `KNOWLEDGE_CONTENT_HASH_SCHEME`.
- Independently checks both pins in Context passage validation.
- Adds a synthetic accepted-revalidation regression: a due-review event is followed by accepted `revalidate`, with unchanged semantic content and item version but a new current pointer. Retrieval and Context reject the old publication; a rebuilt publication becomes retrievable.

The corrected code/test head `673de5f74e734e3a9fa6059b3f4333e93a055a99` passed hosted CI [run 42382712672](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42382712672): fresh PostgreSQL migration and single-head checks, Ruff, Mypy (32 source files), **738 tests passed** (74 warnings), and disposable-container cleanup. This is hosted evidence for the corrected head; Operator-local exact-head re-verification remains pending.

**Acceptance and verification disposition (2026-11-07):** the Operator accepted Step 3 and authorized merge. PR #48 merged to `main` at `1ba9f38ec2fa0b7c4a748181bce4096d8f65b356`. Corrected-head hosted CI run [42383223932](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42383223932) passed. Operator-local exact-head verification on `fcb9f4bd9b56b2353299828a7db39619a4650604` passed Ruff, Mypy (32 source files), migration/single-head checks at `0016_team_exp_history_pins`, and the full suite (**738 passed, 74 Alembic deprecation warnings**). The environment was restored and the disposable PostgreSQL container was removed. No persistent `watch` database was targeted. Step 3 is accepted and closed; actual lifecycle commits remain create-only.

**Boundaries:** no live revise/revalidate/supersede/retire commit path; Step 4 publication changes, Step 5 retrieval rollout, Step 6 Context manifest v3, and Step 7 approval refactor remain unimplemented. B3–B6 and R7-C remain unauthorized.


## R7-B B2 Step 4 — requirement gap analysis on merged main (Sequences 2–3; 2026-11-07)

**Exact baseline:** merged `main` at `1ba9f38ec2fa0b7c4a748181bce4096d8f65b356` (PR #48 merge). The inspection was read-only and covered `core/knowledge_index.py`, `tests/test_team_experience.py`, `migrations/versions/0016_team_experience_history_pins.py`, and `tests/test_team_experience_projection_migration.py`. No local test execution, source/test edit, migration, provider call, database operation, or persistent-state access occurred in this investigation.

### Requirement-by-requirement disposition

| Step 4 requirement | Code evidence on baseline | Existing test evidence | Gap / disposition |
|---|---|---|---|
| 1. Bind exact current LearningChange ID and v2 content-hash scheme to every chunk and index-state row; check them in `_projection_matches` and final publication. | `index_knowledge_item` constructs chunks with both pins. `_upsert_index_state` writes both pins. `_projection_matches` requires the current pointer and v2 scheme on state and every chunk. Final publication re-locks the KnowledgeItem, validates its current LearningChange chain, and checks version/hash/origin/current pointer before inserting rows constructed from the same source state. | `test_separate_team_experience_projection_is_idempotent_and_retrievable` checks chunk and index-state pins. `test_revalidation_pointer_only_transition_invalidates_old_projection` proves a pointer-only change invalidates old projection rows until republished. | **Satisfied.** No Step 4 implementation change identified. |
| 2. Recheck item ID/Team, current pointer, version/hash, scheme, status, D7 eligibility, canonical history, and embedding-space identity immediately before publication. | The final transaction selects the item by ID with `FOR UPDATE`; `_accepted_learning_change_is_canonical` validates the accepted current pointer and reconstructed history; `_review_date_is_eligible` enforces active status and a future timezone-aware UTC `review_after`; `_upsert_index_state` rechecks Team, version, origin/current pointers and semantic hash and writes the v2 scheme. But provider-space identity is checked only after embedding and before row construction/final transaction. There is no provider-space revalidation at the final publication boundary. | Canonicality/current-pointer and D7 tests cover canonical state and eligibility. No deterministic test changes the provider's current space after the post-embedding check but before publication. | **One confirmed narrow implementation gap:** final provider-space revalidation. The observed window can publish a projection marked `published` for a provider space that changed after the earlier check. Retrieval still requires query/chunk/state space identity to match; no cross-space retrieval was demonstrated. |
| 3. Mark a required refresh stale before the provider call; atomically publish replacement chunks and matching index state after checks. | `_record_index_state(status="stale")` commits before `embed()`. The final transaction deletes old chunks, inserts replacement chunks, and upserts the matching `published` index-state record in one transaction. Retrieval requires `st.status = 'published'`. | `test_failed_publication_records_staleness_and_rebuilds` proves provider failure leaves the old chunks undiscoverable and a later rebuild succeeds. | **Satisfied.** No Step 4 implementation change identified. |
| 4. Make `rebuild_all` discover `legacy-opaque`/stale rows for ordinary republish. | `rebuild_all()` unions item IDs from active eligible KnowledgeItems, existing `TeamExperienceChunk` rows, and `TeamExperienceIndexState` rows. Migrated legacy rows remain discoverable through the projection tables and are routed through `index_knowledge_item`. | `test_0016_preserves_legacy_projection_bytes_and_marks_them_opaque_and_stale` proves legacy rows are preserved, marked opaque, and index state marked stale. `test_failed_publication_records_staleness_and_rebuilds` proves ordinary stale-row rebuild. Neither directly rebuilds a migrated `legacy-opaque` row. | **Implementation present; direct regression coverage missing.** Add a migration-to-`rebuild_all` integration regression; no new discovery algorithm is indicated. |

### Existing test inventory relevant to Step 4

- `test_separate_team_experience_projection_is_idempotent_and_retrievable`: successful publication, idempotency, and current-pointer/hash-scheme pins on chunks and index state.
- `test_failed_publication_records_staleness_and_rebuilds`: stale-before-embedding failure behavior, retrieval exclusion, and successful retry/rebuild.
- `test_revalidation_pointer_only_transition_invalidates_old_projection`: old projection rejection when only the current LearningChange pointer changes, followed by successful republish.
- `test_unconfigured_review_date_is_not_indexed` and `test_review_expired_knowledge_is_not_indexed`: D7 eligibility exclusions.
- `test_0016_preserves_legacy_projection_bytes_and_marks_them_opaque_and_stale`: migration preserves old projection values, marks index state stale, and sets `legacy-opaque`/NULL-pointer pins.
- `test_0016_accepts_v2_pins_and_rejects_invalid_scheme_and_cross_team_pointer`: supported scheme and same-Team pointer constraints.
- `test_0016_failed_migration_rolls_back_schema_and_existing_rows`: failed migration rollback.

### Bounded Step 4 implementation/test delta

1. Add a deterministic provider-space interleaving regression: provider reports space A after embedding validation, changes to B before the final publication boundary, and the indexer must not publish the A batch as current. Preserve stale/fail-closed state and prove a subsequent B retry can publish normally.
2. Add a direct migration-to-rebuild regression: start with a migrated `legacy-opaque`/stale projection, invoke `rebuild_all()`, and prove normal indexing republishes v2 pins and makes the item retrievable.
3. Preserve all already-satisfied Step 4 behavior. Do not add a provider lock, new migration, provider abstraction, state machine, or broad retrieval changes without separate evidence.
4. Keep lifecycle commits create-only. Steps 5–7, B3–B6, and R7-C are outside this work.

**Sequence 3 disposition:** requirement-by-requirement gap analysis is complete. **Sequence 4 has not started**; this record authorizes no source edit by itself. Sequence 1 documentation closeout is being synchronized with this finding. No Step 4 tests were run during this read-only analysis.


## R7-B B2 Step 4 — publication-boundary hardening (ACCEPTED AND MERGED — PR #50)

PR [#50](https://github.com/abtn/Watch-Architecture-Rev2/pull/50) merged to `main` at `96447318484d539ffa240745b9adc95b8b510871`; final PR head was `6b15a55478c2ec6b0e933201aa5f250adb38b449`. The implementation rechecks provider embedding-space identity at the final publication boundary, fails closed on provider-space change/error without publishing replacement chunks or incrementing the attempt count a second time, and adds a direct rebuild regression for the post-0016 legacy-opaque/stale projection state.

- Hosted CI passed on the exact PR head: [run 42389377578](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42389377578).
- Hosted CI passed on the merge commit: [run 42389752995](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42389752995).
- Operator-local exact merged-head verification on `96447318484d539ffa240745b9adc95b8b510871` passed: fresh disposable PostgreSQL migration to the single head `0016_team_exp_history_pins`, Ruff, Mypy (32 source files), **740 tests passed, 74 warnings**, `git diff --check`, environment restoration, and disposable-container cleanup. The persistent `watch` database was not targeted.
- Coverage qualification: the rebuild regression simulates the post-migration legacy-opaque/stale state and then calls `rebuild_all()`; it does not run Alembic migration and rebuild in one integrated fixture. Migration marking/preservation is tested separately.

## R7-B B2 Step 5 — reciprocal supersession retrieval gates (ACCEPTED AND MERGED — PR #52)

PR [#52](https://github.com/abtn/Watch-Architecture-Rev2/pull/52) merged to `main` at `bc0d71e20fbe3ed01ef13493099a80367d8a5a42`; exact PR head `a9f72979c4da8b5c02705ca812760ed4386a40ba`. The retriever excludes predecessors with a committed successor and validates a candidate's reciprocal predecessor relationship against canonical supersession history within the retriever's consistent snapshot. Existing D7 eligibility remains enforced. Regression cases cover pending candidate visibility, predecessor review/due/retired states, and canonical reciprocal supersession. No schema or migration change was introduced.

- Hosted CI passed on the exact PR head: [run 42462369436](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42462369436), including migration/single-head checks, Ruff, Mypy, full pytest suite, and cleanup.
- Operator-local exact-head verification was skipped at the Operator's direction. No local test count is claimed.

## R7-B B2 Step 6 — Context manifest v3 (ACCEPTED AND MERGED — PR #53)

PR [#53](https://github.com/abtn/Watch-Architecture-Rev2/pull/53) merged to `main` at `70ee2217aa7dc20e32b263a597af9b1b37261e29`; exact PR head `f0efbbb79f827fd48b9862262adccba15eabd2e9`. New Context manifests record the current LearningChange ID and content-hash scheme. Final Context validation independently checks canonical history and reciprocal supersession visibility. Historical manifest v1/v2 replay remains immutable and byte-exact; the outer Task Context schema remains v2.

- Hosted CI passed on the exact PR head: [run 42464991372](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42464991372), including migration/single-head checks, Ruff, Mypy, full pytest suite, and cleanup.
- Operator-local exact-head verification was skipped at the Operator's direction. No local test count is claimed.

## R7-B B2 Step 7 — approval-validation refactoring (ACCEPTED AND MERGED — PR #55)

**Implementation and verification passed; PR [#55](https://github.com/abtn/Watch-Architecture-Rev2/pull/55) merged to `main` at `47aad564ac0496f4ff984bc4d937355922d36c77` (2026-11-08).** A dependency-light `core.operator_approval` module owns pure request-envelope, identity, decision/rejection shape, assessment-pin, idempotency-hash shape, and fingerprint validation. `OperatorApplicationAdapter`, TaskRuntime, and `LearningCommitService` reuse these contracts while retaining independent database-owned eligibility, assessment, commit, finalization, and recovery checks. The only eligible LearningChange remains `knowledge_item/create/NULL target`; `revise`, `revalidate`, `supersede`, and `retire` remain rejected.

- **Hosted CI:** passed on exact implementation PR head `534a7fad6b6cb3cfa3fd7381bcdb0d8ecdb1b8e2`: [run 42468214569](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42468214569). Fresh PostgreSQL migration reached the single `0016_team_exp_history_pins` head; Ruff passed; Mypy passed across 33 source files; full suite: **793 passed, 74 warnings**; CI container cleanup passed.
- **Operator-local exact-head verification:** passed on the same implementation head `534a7fad6b6cb3cfa3fd7381bcdb0d8ecdb1b8e2`. The existing `scripts/test-disposable-postgres.ps1` runner created a disposable PostgreSQL container, applied migrations, confirmed the single Alembic head `0016_team_exp_history_pins`, passed Ruff and Mypy (33 source files), and ran the full suite: **793 passed, 74 warnings in 132.82s**. The runner removed its disposable container. Final Git status was clean on `r7b-b2-step7-approval-validation`, tracking `origin/r7b-b2-step7-approval-validation`. The warnings were Alembic `path_separator` deprecation warnings (65 from `test_r7b_history_migration.py`, 9 from `test_team_experience_projection_migration.py`). The persistent `watch` database was not targeted.
- No Task registration, write-scope, schema, migration, runtime, provider, or authentication changes were introduced. Step 8 integrated fixtures are now accepted and merged; Step 9 formal B2 verification remains open. B3–B6 and R7-C remain unauthorized.

## R7-B B2 Step 8 — integrated regression fixtures (ACCEPTED AND MERGED — PRs #56 and #57)

**Closeout (2026-11-08):** PR #56 (inspection/documentation checkpoint) merged at `58d88bafdf33e8ce1af2f5a7ba9af11bfd84cb32`; PR #57 (integrated fixtures) merged at `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`. PR #57 exact head `114a6311534cd116190e3c2f4143fdfb1a2c979b` passed hosted CI run [42478536427](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42478536427): fresh PostgreSQL migration/single-head, Ruff, Mypy, and **806 passed, 77 warnings**. Operator-local verification on the same code head has not yet been recorded; it is required by Step 9.

- Accepted create → canonical LearningChange/current pointer → v2 hash → Team Experience projection → retrieval → Context manifest v3.
- Real Alembic `0016` migration → legacy-opaque/stale projection blocked from retrieval → application `rebuild_all()` → republished v2/current-pointer pins → retrieval restored.
- Failed publication → stale/undiscoverable projection → successful rebuild → repeated rebuild is unchanged without another embedding publication.
- Canonicality/tampering matrix: current pointer, Team, target, status, committed snapshot, hash scheme, stale state, and chunk hash; rejected data remains absent from retrieval and Context. Cross-Team projection mutation is separately rejected by the database composite constraint.
- Offset-aware D7 boundary: eligible immediately before the boundary and ineligible at the exact boundary.
- Context v1/v2 replay remains byte-exact without reassembly or KnowledgeItem hash recalculation.
- Existing D5 visibility cases and Step 7's create-only approval matrix remain intact; no production code or authority expansion was introduced.

**Boundary:** Step 8 is complete and merged. The active approval allowlist remains exactly `create`; B3–B6 and R7-C remain unauthorized.

## R7-B B2 Step 9 — exact-head verification and formal B2 exit (EVIDENCE RECORDED — 2026-11-08)

Step 9 verification was executed against the merged implementation code head. This record distinguishes checks actually performed from prescribed checks not separately evidenced. It does **not** record formal B2 acceptance.

**Exact implementation code head:** `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31` (PR #57 merge commit). PR #57's exact head was `114a6311534cd116190e3c2f4143fdfb1a2c979b`; its hosted CI passed in [run 42478536427](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42478536427). The exact merged code head was then independently verified in hosted CI [run 42479112563](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42479112563) and locally. The hosted run's `postgres, static checks, tests` job completed successfully with fresh migration/single-head, Ruff, Mypy, and 806 tests (77 warnings).

**Operator-local exact-code-head verification (2026-11-08):** passed on `main` at the exact merged implementation commit `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`, matching `origin/main`. Preflight confirmed the repository root, clean worktree, and unchanged HEAD. `uv sync --locked` passed. A fresh disposable PostgreSQL container `watch-b2-step9-clean-d8f56de433` used database `watch_b2_step9_clean` and dynamically assigned loopback port `10891`. The complete Alembic chain passed from an empty database; current revision was `0016_team_exp_history_pins` with exactly one head. Ruff passed; Mypy passed across 33 source files; the full suite ran once, without a preceding focused-test run: **806 passed, 77 warnings in 136.25s**. The warnings were recorded in `tests/test_r7b_history_migration.py` (65) and `tests/test_team_experience_projection_migration.py` (12), including the Alembic `path_separator` deprecation warning. Final HEAD was unchanged and the worktree remained clean. The exact disposable container was subsequently confirmed absent. Environment restoration assignments executed; original values were not printed as part of cleanup evidence. The persistent `watch` database and host port `5432` were not targeted.

**Hosted exact-code-head verification:** workflow run [42479112563](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42479112563) passed on the same merged implementation commit `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`. Its `postgres, static checks, tests` job completed successfully: fresh PostgreSQL migration/single-head proof, Ruff, Mypy, and **806 tests passed, 77 warnings**. This is the hosted result that matches the Operator-local code SHA. The earlier PR-head run [42478536427](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42478536427) on `114a6311534cd116190e3c2f4143fdfb1a2c979b` also passed, but it is not substituted for the merge-commit exact-SHA comparison.

**Checks not separately evidenced:**

- The prescribed focused regression groups (history/hash, migration, Team Experience indexing/publication, retrieval gates, Context assembly/replay, Operator application/approval, LearningCommitService, and TaskRuntime admission/finalization/recovery) were not run as a separate focused command on the local exact-head run. The full suite did pass once and includes the repository's tests; this does not turn a separate focused-run requirement into a recorded pass.
- `git diff --check` was not run or recorded in the clean local verification script.
- The scope review compared the B2 changed-file inventory and inspected key approval guards; a complete line-by-line final diff review remains to be recorded. No scope expansion was identified in the reviewed surfaces, and the active approval allowlist remains exactly `create`.

**Sequence deviation and remaining evidence:** this Operator-local run occurred while this Step 9 planning PR (#58) was still open and unmerged, although the plan originally placed execution after the planning checkpoint was merged. Record this as a procedural sequence deviation, not as a code-head mismatch: both local and hosted verification tested the same unchanged implementation commit `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`, and PR #58 contains documentation only. The full suite exercises the focused regression tests, but the prescribed focused groups were **not run as a separate command**. `git diff --check` was **not recorded** in the clean verification run. The review performed so far compared the B2 changed-file inventory and inspected key approval guards; a complete line-by-line final diff review and the missing explicit checks remain open.

**B2 exit disposition at the time this Step 9 evidence section was written:** technical full-suite, migration, static-check, and exact-code-SHA hosted/local evidence were positive. B2 was then **OPEN** because the separate focused-run and diff-check evidence, complete final diff review, documentation synchronization, and explicit Operator acceptance had not yet been recorded. This is a historical snapshot of the pre-closure state; the subsequent explicit Operator closure decision and accepted residuals are recorded in the next section.

**Boundary:** no source, tests, migration, schema, runtime, provider, authentication, active Task grant, or database configuration was changed by this documentation reconciliation. The disposable verification database/container was not retained.


## R7-B B2 — Operator closure decision (2026-11-08)

**Disposition: B2 formally CLOSED by explicit Operator instruction on 2026-11-08.**

The Operator instructed: “Close B2.” This is the formal phase-exit decision. It accepts the remaining verification gaps as residuals; it does not convert them into passed checks or alter the historical execution record.

### Evidence accepted at closure

- B2 Steps 1–8 are merged; integrated regression PR #57 is merged at `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`.
- Hosted exact-code-head CI run [42479112563](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42479112563) passed on that merged implementation commit.
- Operator-local verification passed on the same code SHA: fresh disposable PostgreSQL migration to the single head `0016_team_exp_history_pins`, Ruff, Mypy, and full suite **806 passed, 77 warnings in 136.25s**.
- The disposable local container was confirmed absent. The persistent `watch` database and host port 5432 were not targeted.
- Hosted and local verification therefore tested the same implementation code SHA.

### Accepted residuals — not passed checks

1. The prescribed focused regression groups were not separately invoked as a distinct local command. The full suite passed, but this is not recorded as a separate focused-run pass.
2. `git diff --check` was not recorded in the local verification.
3. A complete line-by-line final diff review was not completed. The review performed compared the B2 changed-file inventory and inspected key create-only approval guards; no scope expansion was identified in those reviewed surfaces. This is not represented as a complete diff review.

### Procedural sequence deviation

The Operator-local exact-code-head verification occurred while the Step 9 documentation PR #58 was still open and unmerged, contrary to the original planned sequence. This remains recorded as a procedural deviation. It did not create a code-SHA mismatch because hosted and local verification both tested `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`.

### Authority and follow-on boundary

- The active approval allowlist remains exactly `create`.
- B2 closure does not authorize revise, revalidate, supersede, or retire commits.
- B3.0 read-only preflight and B3.1 contract planning/review may proceed.
- At the B2 closeout record's point in time, B3 implementation still required separate written Operator authorization; the subsequent B3.3 authorization is recorded in the Checkpoint 4 disposition below. B4–B6 and R7-C remain unauthorized.
- No production source, test, migration, schema, runtime, Task registration, provider, authentication, or database configuration change is part of this closure record.


## R7-B B3.2 — Immutable assessment schema and Checkpoint 4

**Implementation:** PR [#60](https://github.com/abtn/Watch-Architecture-Rev2/pull/60) merged to `main` at `31be3a25cf7f52ca81eab65cc10280a855738c3d`. The final PR head was `0eecefedbc4ef6e4b60cbd8c3eacf31e1256f362`.

**Hosted exact-PR-head CI:** [run 42496681657](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42496681657) passed:
- Fresh PostgreSQL migration and single Alembic head.
- Ruff.
- Mypy.
- Full test suite: **823 passed, 95 warnings in 58.97s**.

**Schema scope delivered**
- Migration `0017_r7b_assessments` creates `learning_change_operator_provenance`, `knowledge_revalidation_assessments`, and `knowledge_lifecycle_assessments`.
- ORM metadata adds the two separate assessment models and immutable Operator provenance mapping.
- Composite ownership/attribution constraints bind Team, Task, proposal operation, proposal target, KnowledgeItem, request/recorded Events, and successor references.
- Database uniqueness protects assessment identity, Task/idempotency, and request/recorded Event identity. Checks enforce hash formats, operation vocabularies, positive versions/attempts, JSON payload shape, and strict retire/supersede variants.
- PostgreSQL triggers reject row UPDATE/DELETE and statement TRUNCATE for both assessment tables and Operator provenance. No application database role existed to receive a narrower privilege boundary, so no role was invented or altered; privileged superuser/replication bypass remains an operational boundary.
- Downgrade refuses to remove persisted assessment/provenance history; empty-schema downgrade is separately tested.
- Final PR fixes reject whitespace-only provenance, evaluator identity/revision, and idempotency values in both ORM and migration constraints.

**Important historical-pointer distinction:** assessment proposal references remain target-bound to the exact KnowledgeItem. The historical `current_learning_change_id` pointer is intentionally Team-bound only because B1 backfills it to the original create LearningChange, whose `target_id` is NULL. This is not a relaxation of the proposal-to-target FK. The successor's historical current pointer follows the same rule.

**Earlier Operator-local verification — pre-final-fix head only:** local verification on `02913493f1c82bda25aaa8e843097b9f4c2a7c52` passed migration to `0017_r7b_assessments`, single-head checks, Ruff, Mypy, 13 focused tests, 819 full-suite tests (87 warnings), and `git diff --check`. It predates the final PR corrections and is not exact-merge verification.

**Operator-local exact-merge verification — PASSED (2026-11-08)**

- Tested SHA: `31be3a25cf7f52ca81eab65cc10280a855738c3d`; local `main` was fast-forwarded to the exact `origin/main` merge commit after a clean-worktree preflight.
- `uv sync --locked` passed.
- Fresh disposable PostgreSQL container `watch-r7b-b3c4-15bc377052`, database `watch_r7b_b3c4_15bc377052`, dynamically assigned loopback port `29544`.
- `uv run alembic upgrade head` passed; database revision and sole Alembic head: `0017_r7b_assessments`.
- Focused tests: `uv run pytest tests/test_r7b_assessment_models.py -q` → **9 passed**; `uv run pytest tests/test_r7b_assessment_migration.py -q` → **8 passed, 18 warnings**.
- `uv run ruff check core tests migrations` passed.
- `uv run mypy core` passed (33 source files).
- `uv run pytest -q` → **823 passed, 95 warnings in 123.45s**.
- Both `git diff --check 31be3a25cf7f52ca81eab65cc10280a855738c3d^ 31be3a25cf7f52ca81eab65cc10280a855738c3d` and worktree `git diff --check` passed.
- Original `DATABASE_URL` and `TEST_DATABASE_URL` values were restored. The runner removed only its disposable container; removal was confirmed. Persistent `watch` and host port 5432 were not targeted.
- All 95 warnings were Alembic `path_separator` deprecation warnings: 18 from assessment migration tests, 65 from `tests/test_r7b_history_migration.py`, and 12 from `tests/test_team_experience_projection_migration.py`. They did not fail tests or checks.

This is exact-merge local evidence, not a result on the PR head or the earlier pre-final-fix commit.

**Checkpoint 4 disposition (2026-11-08): ACCEPTED BY EXPLICIT OPERATOR INSTRUCTION.** Exact-merge local execution and the schema/contract review are accepted as complete. The Operator also explicitly authorized B3.3 — Revalidation assessment service and Task — by the same written instruction to merge the verified documentation update and start the next checkpoint. Authorization is limited to B3.3; it does not authorize B3.4–B3.9 or any later phase.

**Authority boundary:** B3.2 adds persistence contracts only. It does not register `assess_knowledge_revalidation` or `assess_knowledge_lifecycle`, add worker write grants, implement assessment services, or enable lifecycle commits. The approval allowlist remains exactly `create`. B3.3 implementation is now authorized and starts as the next stage. Its Task remains subject to the stated narrow write scope and existing TaskRuntime; no worker may write `KnowledgeItem` or `LearningChange`. B3.4–B3.9 remain separately gated.


**Operator decision record (2026-11-08):** The Operator instructed: “If all is alright merge and start next checkpoint.” After PR #61 head/CI and scope verification, this was applied as formal acceptance of Checkpoint 4 and explicit authorization to begin B3.3 only.

## R7-B B3.3 — Revalidation assessment service and Task

**Implementation:** PR [#62](https://github.com/abtn/Watch-Architecture-Rev2/pull/62), branch `r7b-b3-3-revalidation-assessment`. Exact implementation head verified locally and by hosted CI: `24de1ffa33b30060d8de6816cf7b5351f72c7eaf`. PR remains open and unmerged pending explicit Operator approval.

**Hosted exact-head CI:** [run 42579389483](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42579389483) passed fresh PostgreSQL migration/single-head verification, Ruff, Mypy, and the full suite (**848 passed, 95 warnings in 63.09s**). CI cleanup completed.

**Operator-local exact-head verification — PASSED (2026-11-09)**

- Preflight: local worktree was clean on the B3.3 branch; local `main` was fast-forwarded from `31be3a2` to `3d6ba4c` (PR #61 documentation closeout), then the verification runner fetched both `main` and the B3.3 branch.
- Exact tested PR head: `24de1ffa33b30060d8de6816cf7b5351f72c7eaf`.
- `uv sync --locked`: passed.
- Fresh disposable PostgreSQL container created by the runner; database `watch_r7b_b3_3_6013e50c48`, dynamic loopback port `8405`.
- Migration upgrade, current revision, and sole Alembic head verification passed at `0017_r7b_assessments`.
- Focused tests: `tests/test_knowledge_revalidation.py` and `tests/test_experience_distiller.py` → **61 passed in 23.73s**.
- `uv run ruff check core tests migrations`: passed.
- `uv run mypy core`: passed (35 source files).
- `uv run pytest -q`: **848 passed, 95 warnings in 128.61s**.
- Both diff checks passed: `git diff --check origin/main...HEAD` and `git diff --check`.
- The runner restored `DATABASE_URL` and `TEST_DATABASE_URL`, removed only its own disposable container `watch-r7b-b3-3-6013e50c48`, and confirmed cleanup. Persistent `watch` and host port 5432 were not targeted.
- All 95 warnings were existing Alembic `path_separator` deprecations: 18 from `tests/test_r7b_assessment_migration.py`, 65 from `tests/test_r7b_history_migration.py`, and 12 from `tests/test_team_experience_projection_migration.py`. They did not fail tests or checks.

**Merge disposition (2026-11-09):** PR #62 merged after all required checks passed. The final documentation-updated PR head `8ffd6ac5a2b178d6d7045a8d765f3e7c33b59b4e` passed hosted CI run [42580930086](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42580930086). Squash merge commit: `f7683b3c7812c3250e0fed5e8e689ade6ecaeca5`.

**Authority and gate boundary:** B3.3 implements only the revalidation assessment service/Task. No KnowledgeItem or LearningChange writes, approval path changes, lifecycle commit, production evaluator, public API/auth stack, dispatcher/registry activation, or later B3/B4–B6/R7-C authorization is included. The active approval allowlist remains exactly `create`. Local and hosted verification passing does not itself merge or formally close the checkpoint.

**Operator authorization record (2026-11-09):** After confirming B3.3's final hosted CI success, the Operator explicitly instructed: “if the checks are ok and 3.3 is done please merge and move on to 3.4 and update the documents.” This authorizes B3.4 — Lifecycle assessment service and Task — only. The next stage must implement deterministic `retire`/`supersede` assessment validation; it does not authorize candidate creation, canonical lifecycle commit, approval, Task registry activation, or B3.5–B3.9. The approval allowlist remains exactly `create`.

## R7-B B3.4 — deterministic lifecycle assessment service and Task (ACCEPTED AND MERGED — PR #64)

**Disposition (2026-11-09):** The Operator approved merge after exact-head local verification. PR [#64](https://github.com/abtn/Watch-Architecture-Rev2/pull/64) merged to `main` at `9abd949a8e682b4df75a77f03acca638a62e472e`. The final PR head was `e0944645f8756b702367c69f15e2743880364694`; the implementation code head tested by hosted CI was `e2fa162b6f9d77506d16458c1b24c81a57a21b66`.

**Hosted exact-code-head CI:** [run 42590404433](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42590404433) passed Ruff, Mypy, fresh PostgreSQL migration/single-head verification, and the full suite (**881 passed, 113 warnings in 67.99s**).

**Operator-local exact-PR-head verification — PASSED (2026-11-09)**

- Repository root, branch, exact HEAD, and remote branch matched the expected PR state; only the local verification script was untracked.
- `uv sync --locked` passed; Python `3.12.12` was confirmed.
- Fresh disposable PostgreSQL container: `watch-r7b-b34-local-59bf4c6a5425`; database `watch_r7b_b34_59bf4c6a5425`; dynamically assigned loopback port `52598`.
- Fresh migration upgrade passed; database revision and sole Alembic head: `0018_r7b_lifecycle_review_date`.
- `uv run ruff check core tests migrations`: passed.
- `uv run mypy core`: passed (37 source files).
- Focused tests — `tests/test_knowledge_lifecycle.py`, `tests/test_experience_distiller.py`, `tests/test_r7b_assessment_models.py`, and `tests/test_r7b_assessment_migration.py`: **89 passed, 36 warnings in 34.68s**.
- Full suite: **881 passed, 113 warnings in 135.71s**.
- `git diff --check`: passed.
- Final repository state: exact tested HEAD retained, no tracked changes, and no unexpected untracked files.
- Original `DATABASE_URL` and `TEST_DATABASE_URL` state was restored. The runner removed its own disposable container; removal was confirmed. Persistent `watch` and host port 5432 were not targeted.

**Warnings:** all 113 local warnings were Alembic `path_separator` deprecation warnings: 36 from `tests/test_r7b_assessment_migration.py`, 65 from `tests/test_r7b_history_migration.py`, and 12 from `tests/test_team_experience_projection_migration.py`. They did not fail tests or checks.

**Implementation scope delivered**
- `core/knowledge_lifecycle.py`: deterministic operation-specific `retire`/`supersede` proposal validation; canonical rationale and proposed-state hash binding; original host-authenticated Operator provenance; read-only canonical evidence reconstruction; exact predecessor and successor snapshot binding; deterministic findings; immutable assessment serialization/hash; idempotent request/recorded Event verification.
- `core/knowledge_lifecycle_tasks.py`: narrow Task creation/validation/recording adapter; exact worker write scope is `["KnowledgeLifecycleAssessment"]`.
- Focused and integration tests cover malformed variants/rationale, cross-Team and stale bindings, explicit NULL successor review date, replay/conflict, Event attribution, no canonical writes, database immutability, and fixture cleanup.

**B3.4 acceptance and authority boundary:** B3.4 is accepted and merged. It adds deterministic lifecycle assessment and immutable recording only. It does not add TaskRuntime lifecycle hooks, a TaskRunner, TaskDispatcher activation, candidate creation, approval, or `KnowledgeItem`/`LearningChange` writes. The active approval allowlist remains exactly `create`.

**Next gate at B3.4 closeout (2026-11-09):** B3.5 plan extraction and documentation-only work were authorized at that time. B3.5 implementation was subsequently authorized, verified, and merged as recorded in the following section. B3.6–B3.9 and B4–B6 remain gated.


## R7-B B3.5 — TaskRuntime, recovery, and lifecycle Events (MERGED — PR #66)

**Disposition (2026-11-10):** PR [#66](https://github.com/abtn/Watch-Architecture-Rev2/pull/66) was squash-merged to `main` at `a6cc81c2aef47d659252b89421e27b08735d944b`. The exact implementation/verification PR head was `65edf206eb6cd68859147ee8c2f68a4717c6fa87`. Hosted and Operator-local checks both ran against the same exact PR-head code SHA; this record does not imply that CI separately ran on the merge commit.

**Hosted exact-head CI:** [run 42655193654](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42655193654) passed on `65edf206eb6cd68859147ee8c2f68a4717c6fa87`: fresh PostgreSQL migration/single Alembic head at `0018_r7b_lifecycle_review_date`, Ruff, Mypy, and the full suite (**884 passed, 113 warnings**).

**Operator-local exact-PR-head verification — PASSED (2026-11-10)**

- Repository root and branch were correct; worktree was clean before synchronization.
- The branch was fetched and fast-forwarded only to exact PR head `65edf206eb6cd68859147ee8c2f68a4717c6fa87`.
- `uv sync --locked` passed; Python 3.12 was used.
- Fresh disposable PostgreSQL database `watch_r7b_b35_disposable`, dynamically assigned loopback port `38860`.
- Fresh `alembic upgrade head` passed; exactly one Alembic head and current database revision: `0018_r7b_lifecycle_review_date`.
- Focused lifecycle integration tests: `tests/test_experience_distiller.py` → **43 passed in 37.67s**.
- `uv run ruff check core tests migrations`: passed.
- `uv run mypy core`: passed (37 source files).
- Full suite: **884 passed, 113 warnings in 141.48s**.
- Base-to-HEAD and worktree `git diff --check` passed; final HEAD remained `65edf206eb6cd68859147ee8c2f68a4717c6fa87`; worktree was clean.
- Original `DATABASE_URL` and `TEST_DATABASE_URL` values were restored. The disposable container was removed successfully. Persistent `watch` and host port 5432 were not targeted.

**Warnings:** all 113 warnings were existing Alembic `path_separator` deprecations: 36 from `tests/test_r7b_assessment_migration.py`, 65 from `tests/test_r7b_history_migration.py`, and 12 from `tests/test_team_experience_projection_migration.py`. They did not fail tests or checks.

**Correction and regression history:** review found that failed-task replay initially treated all `task_attempt_failed` Events as terminal duplicates. The correction indexes attempt Events by `attempt_count`, validates each earlier retry failure against its matching `task_retry_scheduled` Event and chronology, and binds the final attempt failure to the single terminal `task_failed` Event and Outcome. A regression test covers interrupted attempt → retry → terminal failure → repeated replay and verifies no duplicate terminal records. The first CI run exposed missing fixture cleanup for the additional retry Task; cleanup was corrected, and both final hosted and local full-suite runs passed.

**Implementation scope delivered**
- Explicit lifecycle Task recognition in the existing TaskRuntime admission/finalization/recovery path; no generic Task registry.
- Exact lifecycle worker write scope `["KnowledgeLifecycleAssessment"]`, three attempts, zero tool calls/cost, and a 30-second deadline.
- Typed lifecycle success observation and optional assessment ID, conditionally serialized to preserve historical observation payloads when absent.
- Narrow `KnowledgeLifecycleAssessmentTaskRunner` composing the B3.4 adapter with TaskRuntime admission, post-admission validation, assessment recording, terminal finalization, replay, and recovery. TaskRuntime remains the sole owner of Task lifecycle transitions, attempt fencing, terminal Outcomes, and lifecycle Events.
- Recovery from a committed immutable assessment and its exact recorded Event; existing retry disposition for interrupted attempts without a committed assessment; deterministic failure for stale proposals; fail-closed behavior for corrupted/mismatched immutable records or Events.
- Failed replay validates the full attempt history and unique Outcome/terminal Events. Existing revalidation behavior remains covered.

**B3.5 checkpoint authority and scope boundary (historical):** no migration, TaskDispatcher activation, generic registry/scheduler, public API/auth, canonical `KnowledgeItem`/`LearningChange` writes, lifecycle commit, approval expansion, or then-gated B3.6–B3.9/B4–B6/R7-C work was included in that B3.5 slice. The approval allowlist remained exactly `create`. At that checkpoint B3.5 was merged and B3.6 approval-time assessment binding was still separately gated; later B3.6–B3.9 records below supersede that historical status.

## R7-B B3.6 — approval-time assessment binding (2026-11-10; merged)

- PR #68 merged to `main` at `4735b93c74025ddee3bd099ef6d5e64cbac34719`; exact PR head `86f3bcf91ca024486f3a3b918a2c7490ec0ea9da`.
- Hosted CI run [42777343863](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42777343863): fresh PostgreSQL migration/single-head, Ruff, Mypy (38 source files), full suite **908 passed, 113 warnings**.
- Operator-local verification on the exact PR head: fresh disposable PostgreSQL; sole Alembic head `0018_r7b_lifecycle_review_date`; Ruff; Mypy (38 source files); full suite **908 passed, 113 warnings**; `git diff --check`; clean worktree; environment restoration; disposable-container cleanup.
- Warnings are the existing Alembic `path_separator` deprecations (36 in `tests/test_r7b_assessment_migration.py`, 65 in `tests/test_r7b_history_migration.py`, 12 in `tests/test_team_experience_projection_migration.py`).
- B3.6 binds operation-specific recorded-assessment state, payload hashes, canonical host Operator identity, policy/evaluator/proposal/target/evidence bindings, and the full supersede successor snapshot across request fingerprint, TaskRuntime, commit, finalization, and replay. Historical request/decision schemas remain compatible.
- The approval allowlist remains exactly `{"create"}`. Non-create lifecycle requests remain rejected; no lifecycle commit path, automatic dispatcher, migration, public API/auth, or B4–B6/R7-C work was introduced.

## R7-B B3.7 — integrated regression matrix (test implementation complete; B3.8 pending)

The acceptance inventory and complete row-to-test mapping are maintained in [the B3.7 integrated regression matrix](development/r7-b-b3-7-integrated-regression-matrix.md). B3.7 test implementation was separately authorized after B3.6 merged. Every frozen matrix ID is now mapped to concrete tests; no omission was accepted or required.

Merged cumulative checkpoints:

- PRs [#69–#79](https://github.com/abtn/Watch-Architecture-Rev2/pulls?q=is%3Apr+is%3Amerged+69..79) established and reconciled the initial integrated revalidation/supersede paths, TaskRuntime/recovery/Event checks, write scopes, EvidenceLink proposal-hash drift rejection, all five freshness dispositions, and malformed evaluator-output rejection. PR #78 merged at `80ee1ac54ed9459d4c1a9ccb01d2dd1e78ad2cfd`; its exact head passed 929 tests.
- PR [#80](https://github.com/abtn/Watch-Architecture-Rev2/pull/80) covers seven target/proposal drift variants at pre-admission and approval-time boundaries.
- PR [#81](https://github.com/abtn/Watch-Architecture-Rev2/pull/81) covers nine supersede successor/proposal drift variants at approval time.
- PR [#82](https://github.com/abtn/Watch-Architecture-Rev2/pull/82) adds malformed retire-proposal rejection before Task creation.
- PR [#84](https://github.com/abtn/Watch-Architecture-Rev2/pull/84) requires a new observation for stale time-sensitive claims rather than allowing old evidence to support revalidation.
- PR [#85](https://github.com/abtn/Watch-Architecture-Rev2/pull/85) adds revalidation assessment-persistence failure atomicity and same-Task recovery.
- PR [#86](https://github.com/abtn/Watch-Architecture-Rev2/pull/86) adds changed source Outcome hash and omitted canonical EvidenceLink cases.
- PR [#87](https://github.com/abtn/Watch-Architecture-Rev2/pull/87) rejects a real EvidenceLink reference belonging to another Team.
- PR [#89](https://github.com/abtn/Watch-Architecture-Rev2/pull/89) adds lifecycle assessment-persistence failure atomicity and same-Task recovery.
- PR [#90](https://github.com/abtn/Watch-Architecture-Rev2/pull/90) injects failures during TaskRuntime finalization and interrupted recovery; later recovery completes from the original assessment/Event.
- PR [#91](https://github.com/abtn/Watch-Architecture-Rev2/pull/91) rejects missing and duplicate recorded assessment Events for both assessment types. Existing payload-hash tampering and wrong-Task database checks remain.
- PR [#92](https://github.com/abtn/Watch-Architecture-Rev2/pull/92) proves in a service-level transaction that a persisted assessment restricts deletion of its referenced LearningChange proposal.

PRs #83 and #88 were superseded and closed after their changes were carried forward on current `main` by rebased PRs #86 and #89; neither is counted as a merged checkpoint.

**Latest hosted verification:** PR #92 merged at `0a76c27b8d455509f90a864bc2695d01db04805d` from exact tested head `6b624310d4d3ae53153dba1b9f47e949564de079`. CI run [42831066494](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42831066494) passed fresh PostgreSQL migration/single-head, Ruff, Mypy, and **946 passed, 113 warnings**. The 113 warnings are existing Alembic `path_separator` deprecations. Hosted CI is green for the cumulative merged B3.7 test checkpoints.

**Verification qualification:** The Operator-local B3.8 exact-head run is recorded below. Its cumulative diff-check qualification is explicit: three Markdown hard-break trailing-space findings were reported in the B3.7 matrix metadata; the cumulative check scoped to the changed Python source/test files passed, and the clean-checkout diff check passed. The whole cumulative diff-check is not represented as clean.

**Status:** B3.7 test implementation and matrix mapping are complete. B3.8 exact-head verification passed with the documented Markdown-only qualification. B3.9 documentation closeout and formal B3 exit are recorded in [the B3 closeout record](development/r7-b-b3-9-closeout.md). B3 is formally closed on 2026-11-10; the approval allowlist remains exactly `{"create"}`, and no lifecycle commit authority is enabled.

## R7-B B3.8 — Operator-local exact-head verification (2026-11-10)

**Hosted implementation evidence:** PR #92 merged at `0a76c27b8d455509f90a864bc2695d01db04805d` from exact tested head `6b624310d4d3ae53153dba1b9f47e949564de079`. CI run [42831066494](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42831066494) passed fresh PostgreSQL migration/single-head, Ruff, Mypy, and **946 passed, 113 warnings**. The warnings are existing Alembic `path_separator` deprecations. PR #93 documentation reconciliation then advanced `main` to `0a588bc43ee6bfab8c6fccd86dbb28c5c2c803dc`. Because PR #92 was squash-merged, its original head is not a literal ancestor of `main`; B3.8 verified the known merge base `7dadc2e715acbfb21881d61432b63ced377f7e8e` and confirmed the only difference to the synchronized `main` snapshot was the reviewed 11-file PR #93 documentation delta.

**Operator-local exact-head result:** the Operator ran the generated PowerShell verification script and supplied the full terminal transcript. It checked out exact hosted-tested SHA `6b624310d4d3ae53153dba1b9f47e949564de079`, used Python 3.12.12 and a disposable PostgreSQL container on dynamically assigned loopback port 41914, and verified the single Alembic head `0018_r7b_lifecycle_review_date` on separate focused/full-suite databases.

Focused tests, run independently:

| Test file | Result |
|---|---:|
| `tests/test_experience_distiller.py` | 81 passed |
| `tests/test_knowledge_revalidation.py` | 22 passed |
| `tests/test_knowledge_lifecycle.py` | 27 passed |
| `tests/test_knowledge_approval.py` | 10 passed |
| `tests/test_operator_application.py` | 43 passed |
| `tests/test_r7b_assessment_models.py` | 9 passed |
| `tests/test_r7b_assessment_migration.py` | 13 passed |
| `tests/test_task_runtime.py` | 33 passed |
| **Total** | **238 passed** |

- `uv run ruff check core tests migrations` — passed.
- `uv run mypy core` — passed; 38 source files.
- Fresh focused and full-suite PostgreSQL databases each migrated to the sole head `0018_r7b_lifecycle_review_date`.
- `uv run pytest -q` — **946 passed, 113 warnings in 192.71s**.
- Warnings are existing Alembic `path_separator` deprecations: 36 assessment-migration, 65 history-migration, and 12 Team Experience projection-migration warnings.
- The disposable container `watch-b38-exact-ae71b1581782` was removed. `DATABASE_URL` and `TEST_DATABASE_URL` were restored. The checkout returned to clean `main` at `0a588bc43ee6bfab8c6fccd86dbb28c5c2c803dc`.
- The cumulative diff inventory remained the reviewed 12-file B3.7 set. The scoped cumulative `git diff --check` over `core/knowledge_lifecycle.py` and `tests/test_experience_distiller.py` passed; the clean-checkout `git diff --check` passed.

**Diff-check qualification:** the initial whole cumulative diff-check reported trailing spaces on three Markdown metadata lines (lines 3–5) in `docs/development/r7-b-b3-7-integrated-regression-matrix.md`. Those spaces were Markdown hard-break syntax, not Python source/test whitespace. The full cumulative diff-check is therefore recorded as qualified, not passed. B3.9 normalizes the current matrix metadata formatting; this does not retroactively alter the tested SHA.

## R7-B B3.9 — Documentation closeout and formal B3 exit (2026-11-10)

The closeout traceability matrix and formal exit record are in [r7-b-b3-9-closeout.md](development/r7-b-b3-9-closeout.md). The current status is authoritative in `PLAN.md`. The documentation reconciliation updates PLAN, CHANGE_MAP, CONTEXT, README, testing records, Task documentation, the B3.7 matrix, the R7-B implementation plan, the R7 entry gate, ADR-0032, and the ADR index. No implementation, migration, Task registration, approval expansion, or next-phase work is part of B3.9.

**Formal disposition:** B3 is COMPLETE and formally closed on 2026-11-10 following the Operator's explicit instruction to proceed to B3.9 and establish the formal exit status. B4, B5, B6, and R7-C remain NOT AUTHORIZED and require separate written Operator decisions. The approval allowlist remains exactly `{"create"}`.

## R7-B B4.1 — proposal contracts and replay corrections (2026-11-11)

PR [#97](https://github.com/abtn/Watch-Architecture-Rev2/pull/97) implements the B4.1 revise/revalidate proposal and assessment contracts. The implementation reuses the existing `propose_learning_change` Task and TaskRuntime, keeps the proposal write scope at `["LearningChange"]`, routes revise to `KnowledgeQualityAssessment` and revalidate to `KnowledgeRevalidationAssessment`, leaves canonical `KnowledgeItem` state unchanged, retains the create-only approval allowlist, and introduces no migration.

### Operator-local verification of the pre-replay-fix implementation head

Exact tested SHA: `34282c724b17d6e4c3e07816de58dae24b677605`.

- Fresh disposable PostgreSQL 16 database; migration from empty database succeeded.
- Exactly one Alembic head; current revision `0018_r7b_lifecycle_review_date`.
- Ruff and Mypy passed.
- `git diff --check origin/main...HEAD` passed.
- Full suite: **947 passed, 113 warnings, 267.34 seconds**.
- Disposable PostgreSQL container removed; `DATABASE_URL` and `TEST_DATABASE_URL` restored.
- The 113 warnings were Alembic `path_separator` deprecation warnings.

This result is exact evidence for SHA `34282c7...` only. It predates the replay corrections described below and must not be represented as local verification of the later PR head.

### Replay review corrections

The source review identified two completed-Task replay defects:

1. Revalidation checked for an existing proposal only after requiring a running Task. It now validates the original Task identity/write scope with completed Tasks permitted for an existing matching proposal, then returns the persisted proposal read-only. Conflicting operation, target, evidence IDs, or rationale still fail. A completed Task without an existing proposal cannot create one.
2. Revise replay checked provider configuration before checking for an existing proposal. The provider check now occurs only after the existing-proposal replay path and running-Task validation. A matching completed proposal can therefore replay without a configured provider.

Regression coverage now verifies:
- Revalidation proposal replay after TaskRuntime completion returns the same LearningChange ID.
- Reusing the completed revalidation Task with a conflicting rationale is rejected.
- Replay creates no additional LearningChange or proposal Event.
- Revise replay after Task completion succeeds with `provider=None` and creates no additional LearningChange or proposal Event.

### Latest-head verification

The replay corrections and regression tests are committed to the same draft PR branch. Exact-head hosted CI passed on `fb20a3b1a0943926b9cea60a33efdfe329b919dc`: [run #874](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42984911531). Fresh PostgreSQL migration/single-head, Ruff, Mypy, patch whitespace, and the full suite (**948 passed, 113 warnings**) all passed. The 113 warnings are existing Alembic `path_separator` deprecations. The Operator approved the frozen B4.1 contract matrix on 2026-11-11 and authorized B4.2. B4.1's executable verification and Operator review gates are complete; PR #97 remains draft and unmerged.

## R7-B B4.2 — revise canonical commit (MERGED — PR #99)

B4.1 was merged first in PR #97 at `d1c70a312688b8b297027500abcb57d13f53961d`. The stacked B4.2 work was then placed on a clean branch based directly on that merged main tree; the superseded stacked PR #98 was closed rather than merged, avoiding a duplicate B4.1 diff.

PR [#99](https://github.com/abtn/Watch-Architecture-Rev2/pull/99) merged to `main` at `1c69073990b8ccd7a1ee29a806faf04c066d95ad`. Exact PR head `802d0aafacf3ccaee8a8c496416bbf9f09caf2aa` passed hosted CI run [#897](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42993908728):
- Fresh PostgreSQL migration and single Alembic-head verification.
- Ruff, Mypy, and PR patch-whitespace check.
- Full suite: **951 passed, 113 warnings**.
- Disposable PostgreSQL container and network cleanup.

B4.2 enables only revise canonical commit through the existing Operator Task and TaskRuntime path. No migration, new Task type, second runtime, dispatcher, scheduler, public API, or authentication subsystem was introduced. B4.3 remained separate until the Operator explicitly authorized it after B4.2 merged.

## R7-B B4.3 — revalidate canonical commit (PR #100 merge verification record)

Merged branch: `r7b-b4-3-revalidate-commit`; PR [#100](https://github.com/abtn/Watch-Architecture-Rev2/pull/100) squash-merged to `main` at `f9c585c174799cf26fc0d7bf8ed57a8396e2b5aa`. Final PR head: `2f4135a7affe38cf1b564409e5b1b077ba4cb3ae`.

The current implementation work:
- Enables revalidate in the existing trusted Operator approval path, while keeping supersede and retire outside the allowlist.
- Binds the exact same-Team needs_review target, current pointer, content version/hash/scheme, full-state snapshot, and recorded supported KnowledgeRevalidationAssessment.
- Adds a locked target recheck and compare-and-set for the needs_review → active transition.
- Preserves semantic content, confidence, content hash, content version, origin, and supersession links; sets last_validated_at and recomputes review_after from the approval Task's pinned TeamPolicy.
- Adds revalidation-specific decision Event assessment references and TaskRuntime admission/finalization/replay validation.
- Adds accepted and rejected commit regression tests plus a Team Experience projection test proving the old projection stays hidden until republished against the advanced pointer.

The initial implementation and pre-reconciliation PR heads are historical evidence: `77b14203feee844d0ad43bc3d7c6bb3008ed1b72` passed CI run #923 and `19bf0f491728539d548dd3702b2c076e608066b4` passed exact-head CI run #926 (each reported 949 passed, 113 existing Alembic `path_separator` deprecation warnings). The final PR head `2f4135a7affe38cf1b564409e5b1b077ba4cb3ae` passed exact-head hosted CI run [#932](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43023350956). The hosted job completed successfully: fresh PostgreSQL migration and single-head verification, Ruff, Mypy, patch whitespace, the full test step, and disposable PostgreSQL/runner cleanup all passed. The job metadata confirms the test step passed but does not expose its test count, so no count is asserted here. PR #100 was squash-merged to `main` at `f9c585c174799cf26fc0d7bf8ed57a8396e2b5aa`.

No migration, new Task type, second runtime, dispatcher, scheduler, API, authentication subsystem, production evaluator/provider, B5 lifecycle commit, B6, or R7-C work is included. B5, B6, and R7-C remain unauthorized.


## R7-B B4.4 — integrated regression audit (IN PROGRESS — G1/G2/G3 PROOFS VERIFIED; G3 MERGE PENDING)

The initial read-only source/test audit is recorded in [the B4.4 audit](development/r7-b-b4-4-integrated-regression-audit.md), against exact merged main SHA 5f37927ff33d9e740c0ff56512d261dace36ab67. It identified six regression-proof gaps. G1 (concurrent revise/revalidate application and PostgreSQL CAS proofs) and G2 (accepted-revalidation approval recovery after canonical decision commit) are complete and merged. G3 (revalidation replay after a later accepted revision) is verified on open PR #107. G4–G6 remain evidence gaps, not confirmed implementation defects; they remain unauthorized.

### Supplemental B4.3 Operator-local verification on exact merged-main tree

The Operator ran the verification script on branch r7b-b4-3-merged-verification, exact HEAD 5f37927ff33d9e740c0ff56512d261dace36ab67. Fresh disposable PostgreSQL migration and single-head checks passed; 232 focused B4.3 tests passed; Ruff passed; Mypy passed across 38 source files; and the full suite passed **949 tests with 113 warnings in 211.03s**. Pytest exit code was 0. The disposable container was removed. The 113 warnings were Alembic path_separator deprecations. This supplements, but does not replace, the exact-PR-head hosted CI evidence for PR #100 (run #932). The test log was saved at %TEMP%\watch-b43-full-tests-20261111-164732.log.

### B4.4 G1 — Concurrent revise/revalidate proofs (updated 2026-11-12)

**Superseded approaches:** the initial combined test removed production `FOR UPDATE` clauses with a SQL event hook and synchronized full approval transactions at the KnowledgeItem CAS. That was not valid evidence for the real application locking path. A narrower barrier behind the Team lock deadlocked because the first approval waited while the second was blocked on that lock. Both approaches were discarded; no production lock was removed or bypassed.

**Test A — application serialization and loser lifecycle:** `test_concurrent_revise_approvals_advance_one_knowledge_item_once` and `test_concurrent_revalidate_approvals_advance_one_knowledge_item_once` run two independently proposed changes, approval Tasks, requests, and idempotency keys concurrently through `OperatorApplicationAdapter`. Their barrier is only at worker entry, before either workflow begins. There is no SQL event hook, lock suppression, arbitrary sleep, or barrier behind a production lock. The normal LearningChange, Team, KnowledgeItem, Task, and other workflow locks remain intact; the shared Team lock serializes the approvals and one competing proposal becomes stale.

The stale loser is now terminalized through the existing `TaskRuntime` path. The Task becomes `failed`, with one durable `task_execution` Outcome and the `task_attempt_failed` / `task_failed` Events carrying the operation-specific stale reason. TaskRuntime independently reconstructs that same failure from the immutable request, current target state, and original attempt-start Event. A repeated request validates against the stored immutable approval binding and replays the same failure; it does not create another Outcome or terminal Event. The losing LearningChange remains proposed and uncommitted; only the winner advances the canonical item.

**Test B — production CAS statement race:** `test_concurrent_revise_knowledge_item_cas_allows_one_update` and `test_concurrent_revalidate_knowledge_item_cas_allows_one_update` use two independent PostgreSQL connections/transactions. Each worker reads the same initial pointer/version/status, records its backend PID, and synchronizes immediately before executing `UPDATE ... RETURNING`. The tests call `_knowledge_item_cas_statement` from `core.learning_commit`; this is the same statement builder used by `LearningCommitService`, not a separately authored test predicate. The builder includes item ID, Team ID, expected pointer, expected version, and for revalidation the `needs_review` status predicate. Exactly one update returns the item ID; the other returns no row, and the persisted winner state is checked.

**Proof boundary:** Test A proves application-level serialization through the real approval path. Test B exercises the exact production CAS statement construction under two concurrent PostgreSQL transactions. Because the Team lock serializes full approval workflows before the CAS, these tests do not claim that two full production approval workflows simultaneously reach the CAS statement.

**Production changes:** the Operator adapter now terminalizes the recognized stale revise/revalidate approval conflict through TaskRuntime. TaskRuntime validates and reconstructs the stale failure for initial finalization and replay. Existing failed approval requests verify their immutable stored request binding when the current target has moved, rather than misclassifying a legitimate retry as a different idempotency request. The production CAS predicate itself is unchanged; its statement construction is shared with the database tests. No migration, schema change, or lock change was introduced.

**Exact-head hosted verification:** implementation commit `e7ca526ac2720ab44e58b768a5c702f3e669d1c1` passed [CI run #43174903501](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43174903501), with the workflow checking out that exact SHA. Fresh PostgreSQL migration and single-head checks, Ruff, Mypy, patch whitespace, full suite (**953 passed, 113 warnings in 132.06s**), and disposable PostgreSQL/runner cleanup all passed. A local full-suite run of this final revision is not claimed.

PR [#103](https://github.com/abtn/Watch-Architecture-Rev2/pull/103) was squash-merged to `main` on 2026-11-12 at `313f379e75f3ab40d0805de371caa8745b998add` from exact PR head `81b3b8a40fda49e8c398cacdd1b9010e9dad5814`. The final exact-head hosted CI run [#43175397785](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43175397785) passed with 953 tests and 113 warnings. The Operator's local run on the same exact head also passed fresh disposable PostgreSQL migration/single-head checks, Ruff, Mypy, and **953 passed, 113 warnings in 306.89s**. The local script removed the disposable container and restored `DATABASE_URL` and `TEST_DATABASE_URL`. G1 is complete and merged.

### B4.4 G2 — Accepted-revalidation approval crash/recovery (PR #105 merged 2026-11-12)

PR [#105](https://github.com/abtn/Watch-Architecture-Rev2/pull/105) was squash-merged at `ac01836b8548c147690f33cffdd66fd7b7c5af74` from exact PR head `60790c6e4ec19393f0c236238ab290c8df60fb05`. Its sole changed file is `tests/test_experience_distiller.py`; no production source, schema, or migration changed.

The regression `test_operator_commits_and_recovers_revalidation_after_finalize_crash` uses the real trusted Operator approval path and injects a deterministic one-shot interruption after the accepted revalidation decision commits but before TaskRuntime finalization. It verifies recovery of the same approval Task through `TaskRuntime.recover_interrupted`, preservation of the immutable approval request and assessment provenance, exactly one terminal Outcome/Snapshot/Event set, no duplicate KnowledgeItem transition or decision Event, and idempotent repeated recovery/replay. The interruption is simulated at the commit/finalization boundary; it is not an OS process kill. The proof covers accepted revalidation only and does not claim G5 rejected-approval replay.

**Hosted exact-head CI:** run [#43182375964](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43182375964) passed on `60790c6e4ec19393f0c236238ab290c8df60fb05`: fresh PostgreSQL migration/single-head, locked dependency install, Ruff, Mypy, patch whitespace, full suite (**953 passed, 113 warnings**), and disposable-container cleanup.

**Operator-local exact-head verification:** the same SHA passed migration/single-head at `0018_r7b_lifecycle_review_date`, Ruff, Mypy (38 source files), `git diff --check`, and full pytest (**953 passed, 113 warnings in 286.09s**). The worktree was clean; `DATABASE_URL` and `TEST_DATABASE_URL` were restored; the disposable container was removed.


### B4.4 G3 — Revalidation approval replay after a later history transition (verified on open PR #107)

The focused regression `test_original_revalidation_approval_replays_after_later_history_transition` in `tests/test_experience_distiller.py` proves replay of the original accepted revalidation approval after a later accepted revise on the same KnowledgeItem. It uses the existing fixtures/helpers and trusted `OperatorApplicationAdapter` canonical path. The original request and idempotency key are replayed only after the later revision is current. The test verifies the original approval Task, LearningChange, commit time, and persisted Outcome identity; unchanged later KnowledgeItem state/current pointer; exactly one terminal Event across `task_completed`/`task_failed`; and no duplicate request, decision Event, or Outcome. It is test-only: no manual canonical-row fabrication, production correction, schema/migration, runtime, lock, or approval-scope change.

**Historical implementation-head evidence:** hosted CI run [#43188355825](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43188355825) passed on `24591c2e5a3597d36506ca5f5926d540e87f3dee`: fresh PostgreSQL migration/single-head, Ruff, Mypy, patch whitespace, full pytest (**954 passed, 113 warnings in 111.28s**), and disposable PostgreSQL cleanup. Operator-local verification on that implementation head passed migration/single-head at `0018_r7b_lifecycle_review_date`, Ruff, Mypy (38 source files), focused G3 test (**1 passed in 6.27s**), and full pytest (**954 passed, 113 warnings in 303.61s**). The disposable container was confirmed absent. The first script's environment-restoration assertion raised; subsequent inspection showed the three process variables present with empty values, but no independent pre-run snapshot had been emitted. Environment restoration on that historical run therefore remains **not independently verified**. This historical caveat is retained rather than retroactively changed.

**Prior documentation-updated-head verification (before the assertion-strengthening correction):** PR head `ef963eda7f9a0031ec767b5734a34391c782c275` passed hosted CI run [#43242981821](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43242981821): fresh PostgreSQL migrations/single-head, Ruff, Mypy, patch whitespace, full pytest (**954 passed, 113 warnings**), and disposable PostgreSQL cleanup. Operator-local exact-head verification on the same SHA passed dependency sync, fresh disposable PostgreSQL migrations/single-head at `0018_r7b_lifecycle_review_date`, Ruff, Mypy (38 source files), focused G3 test (**1 passed in 5.50s**), full pytest (**954 passed, 113 warnings in 314.39s**), explicit environment restoration, and disposable-container cleanup. The 113 warnings are Alembic `path_separator` deprecations.

The `ef963` run resolves the environment-restoration uncertainty for that source tree, but it predates the terminal-Event/Outcome-identity assertion correction. **Corrected current-head verification:** exact PR head `97fc75afff7d6e349bcfef167d93b4f82a8f7c86` passed hosted CI run [#43246996445](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43246996445). Operator-local verification on that exact SHA passed `uv sync --locked`, disposable PostgreSQL migration/single-head at `0018_r7b_lifecycle_review_date` (dynamic loopback port `20477`), Ruff, Mypy (38 source files), `git diff --check`, the focused G3 test (**1 passed in 6.88s**), and the full suite (**954 passed, 113 warnings in 324.58s**). The script's final success checks confirmed environment restoration, disposable-container removal, exact branch/HEAD, and a clean worktree. The 113 warnings are Alembic `path_separator` deprecations. The historical implementation-head restoration caveat above remains attached only to that earlier run.

PR #107 remains open and unmerged pending explicit Operator approval. G4–G6 remain unauthorized; B5, B6, and R7-C remain unauthorized.
