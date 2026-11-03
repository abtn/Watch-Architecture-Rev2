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

- Database-backed tests use the configured disposable/test PostgreSQL database.
- Use a disposable database/volume for migration and concurrency verification.
- Never target a persistent `watch` database to make a test pass.
- Do not run destructive cleanup such as `docker compose down -v` as generic test cleanup.
- If the database cannot be started or a dependency is missing, report the environmental blocker separately from a code defect.

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
git diff --check origin/main...HEAD
```

Use a fresh disposable PostgreSQL database even though this checkpoint has no new migration. Confirm the single head remains `0012_learning_foundation`. The Checkpoint 2 tests cover deterministic and bounded canonical evidence packs; terminal source Task/Outcome and Evaluation provenance; one-case Practice versus distinct-Task multi-case abstraction; supporting/challenging/mention stance retention; stale/mutated evidence both before and during a provider call; supporting/challenging/mention stance classification; cross-Team/missing references; reservation-before-provider, provider failure/model mismatch, invalid output, unknown/overrun costs, replay after finalization, concurrent duplicate calls, and typed TaskRuntime completion. Verify that a proposed LearningChange is the only Team Experience-domain write: no KnowledgeItem, TeamPolicy, or retrieval projection is created.

The disposable PostgreSQL test procedure must bind both `DATABASE_URL` and `TEST_DATABASE_URL` to the disposable instance, restore both variables afterward, and stop only the container it created. Never run these checks against the persistent `watch` database. Report actual command output; hosted CI does not replace the operator-local check.

## R6-F Checkpoint 3 — Host-invoked Operator adapter and canonical learning commit

Checkpoint 3 includes a thin in-repository adapter invoked in-process by a host application. The host authenticates and authorizes the Operator; Watch adds no deployed API/CLI or authentication subsystem. Fake principals/authorizers test the contract, not production authentication.

**First implementation increment (draft PR #31, code head `2619eda`):** `core/operator_application.py` and `tests/test_operator_application.py` implement the typed host-principal boundary and atomic pending Task/request-Event creation with deterministic same-request replay. Operator-local disposable-PostgreSQL verification passed: fresh migration to the single head `0012_learning_foundation`, 14 focused tests, Ruff, mypy (26 source files), 557 full-suite tests, and `git diff --check`. The disposable container was removed and environment variables restored. No migration was introduced.

**Second implementation increment (current draft PR #31 head `fb177c0`):** `TaskRuntime.admit` now permits a no-deadline budget only for an intact `approve_learning_change` Task. Before a start, it validates the exact two-item LearningChange/KnowledgeItem write scope, no Objective/Plan/Action links, pinned attempt limit, zero tools/cost, exactly one request Event with canonical operator identity and matching request fingerprint, and an existing same-Team create-only LearningChange target. This path still consumes the ordinary Team daily-start quota and emits the normal `task_started` Event. Generic Task types still require positive `deadline_seconds`; the 60-second interrupted recovery is unchanged. Hosted CI run [41402113541](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41402113541) passed fresh migration/head checks, Ruff, mypy, and **565 tests**. Local disposable-PostgreSQL verification of this second increment is pending. No migration was introduced.

**Third implementation increment (current draft PR #31 code head `2327e88`):** `core/learning_commit.py` implements create-only Operator acceptance/rejection. Before deciding, it rechecks the approval Task and durable request Event, exact host identity/grant, current Team policy, proposer Task terminal Outcome/Event/Snapshot, and rebuilds the bounded proposal evidence from canonical Evaluations, Outcomes, EvidenceLinks, and Snapshots through a provider-free read-only ExperienceDistiller path. Acceptance atomically creates one active KnowledgeItem v1, stores the exact committed state and Operator/Task attribution on the LearningChange, and writes one `learning_change_accepted` Event. Rejection records the reason and attribution and writes one `learning_change_rejected` Event without creating a KnowledgeItem. A replay must match the exact decision Event payload/timestamp, prove the original and current attempt starts, and (for acceptance) compare every KnowledgeItem field with the durable committed-state snapshot. Tests cover real create-proposal accept/reject, same-Task replay, stale/tampered evidence, wrong actor, stale policy, injected decision-Event failure rollback, and altered KnowledgeItem/Event replay records. Hosted CI run [41407266283](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41407266283) passed fresh migration/head checks, Ruff, mypy (27 source files), and **572 full-suite tests**. Operator-local disposable-PostgreSQL verification of this third increment is pending. No schema migration was introduced.

**Fourth implementation increment (draft PR #31 final head `581ad1853a81d77b2a4fc41abe349ccc53dbe6d2`):** `TaskRuntime.finalize` accepts distinct typed accepted/rejected decision results only for the approval Task. It verifies the durable request, same-Team create-only LearningChange, committing Task, host actor, exact decision Event, original decision attempt, and current attempt. Acceptance additionally checks that the single canonical KnowledgeItem exactly matches `LearningChange.committed_state`; rejection verifies that no KnowledgeItem exists. The existing atomic TaskRuntime terminal path writes the `task_execution` Outcome, observation Snapshot, `task_completed` Event, and `done` Task state. `OperatorApplicationAdapter.decide_learning_change` composes request replay/creation → admission → canonical decision → finalization and returns only after the Task is done. It supports replay after a completed decision. Interrupted recovery distinguishes the two crash windows: before decision commit, ordinary 60-second retry returns the same Task to pending; after decision commit, recovery derives the exact durable accepted/rejected result and finalizes it before considering retry/exhaustion. It reports such Tasks in `RecoveryResult.completed`. There is no schema migration.

**Hosted and operator-local verification passed on final head `581ad1853a81d77b2a4fc41abe349ccc53dbe6d2`:** [hosted CI run 41458560005](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41458560005) passed fresh PostgreSQL migration/head checks, Ruff, mypy (27 source files), and 577 tests. The operator's local run passed fresh disposable PostgreSQL migration and one Alembic head at `0012_learning_foundation`, 83 focused tests across `test_experience_distiller.py`, `test_operator_application.py`, and `test_task_runtime.py`, Ruff, mypy (27 source files), **577 full-suite tests**, and `git diff --check`. The worktree remained clean, only the created disposable container was removed, and both database environment variables were restored.

**Checkpoint 3/4 closure boundary:** C3's create-only approval lifecycle is implemented and verified; D10 explicitly defers revise/retire beyond C3. PR #31 remains open/draft/unmerged. D7 is resolved and implemented in C4. C4 implementation and hosted CI passed on `3682f7e` in run [41589798190](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41589798190): fresh migration to the single head `0013_team_experience_projection`, Ruff, mypy (27 source files), and 588 tests. C4's latest local verification is pending. PR #32 remains open/draft/unmerged and stacked on the C3 branch; integrate PR #31 first, then retarget and reverify PR #32. Do not formally close C4 before local disposable-PostgreSQL verification and sequential integration.

The tests prove:
- typed stable issuer/subject principal; no bare caller/model `operator_id`, display name, or email as authority;
- host authorization for exact Team and `approve_learning_change` action; wrong Team/action or missing/invalid context fails closed;
- atomic pending ordinary approval Task and request Event creation; no Plan links; exact `["LearningChange", "KnowledgeItem"]` scope; zero tools/cost; no direct lifecycle writes;
- host idempotency UUID maps to one deterministic Task ID; same key/same payload replays; same key/changed payload conflicts;
- TaskRuntime remains the only lifecycle authority; TaskDispatcher remains ingestion-only and is not extended for Operator work. The adapter composes the existing runtime synchronously.

Implemented focused coverage in `tests/test_operator_application.py`:
- host principal shape and rejection of a raw string; stable issuer/subject validation;
- Team/action grants, active Team, and proposed create-only LearningChange eligibility;
- exact pending Task shape, latest policy pin, no Task lifecycle mutation, and one request Event;
- same-key replay after policy advances; same-key changed actor/decision conflicts;
- missing/modified/duplicate request Event corruption rejection;
- concurrent identical requests create exactly one Task and one request Event.
- valid no-deadline approval Task admission through TaskRuntime, with exactly one start Event and attempt increment;
- malformed scope/budget/attempt limit, missing request Event, and identity/fingerprint tampering are rejected before any start side effect;
- ordinary Task types still fail admission when `deadline_seconds` is missing.

Run the focused test with `uv run pytest tests/test_operator_application.py -q`.
- `tests/test_learning_commit.py`: accept real Checkpoint 2 create proposals; reject without KnowledgeItem mutation; revalidate evidence hash/references; cross-Team/stale target; version/history; actor/Task attribution; TeamPolicy exclusion.
- `tests/test_learning_commit_concurrency.py`: Task/LearningChange/target locking, duplicate replay, competing accept/reject, transaction failure with no partial LearningChange/KnowledgeItem/Event.
- `tests/test_learning_commit_task_runtime.py`: typed accepted/rejected results, rejection-as-`done`, exact scope/Team/current-attempt, TaskRuntime-only lifecycle, crash after decision commit, recovery to pending, same-Task replay/finalization, stale old-attempt rejection.

Use PostgreSQL for duplicate creation races, locks, rollback, and interrupted recovery. Assert TeamPolicy, unrelated Tasks, Snapshots, and retrieval projections remain unchanged.

The no-deadline admission path for `approve_learning_change` is implemented and locally verified. Its tests cover malformed Task shape, missing/corrupt request Event, identity/fingerprint tampering, no partial start, normal Team quota consumption, and ordinary Task types still requiring a positive deadline. Preserve generic 60-second stale-running recovery; it is crash recovery, not time for a human decision.

For full Checkpoint 4 verification on the named C4 branch, use a fresh disposable pgvector PostgreSQL database and run `uv sync --locked`, `uv run alembic upgrade head`, `uv run alembic heads`, `uv run alembic current`, focused C4 tests (`tests/test_team_experience.py`, `tests/test_context_assembly.py`, `tests/test_knowledge_index.py`, `tests/test_learning_commit.py`, and `tests/test_task_runtime.py`), `uv run ruff check core tests migrations`, `uv run mypy core`, `uv run pytest -q`, and `git diff --check origin/r6f-checkpoint-3-operator-learning-commit...HEAD`. Require exactly one head at `0013_team_experience_projection`. Never use persistent `watch`; no live generation provider.

D10 is resolved (2026-11-02): Checkpoint 3 is create-only. Revise/retire proposal production and commitment are deferred beyond C3 until a separately authorized knowledge-lifecycle scope defines a genuine proposal source and version/history/concurrency/recovery/projection semantics. No `seed_knowledge`, direct fixtures, database writes, or bypass. D7 is resolved and implemented in C4: schema-v2 optional interval pinned to the approval Task, UTC date stamp, NULL/due exclusion, and deterministic ordinary `review_knowledge` Task transition. C4 also has separate chunk and publication-state tables, dual-core retrieval, Context v2 provenance/v1 replay, and later-Task reuse. Hosted CI on `3682f7e` passed 588 tests; operator-local disposable-PostgreSQL verification and sequential PR integration remain.

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
