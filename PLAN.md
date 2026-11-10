# PLAN.md — Milestones and Current Gate

This file is the **single source of current milestone status**. Other documents link here rather than copying status tables. A phase is complete only when its exit criteria and formal gate are satisfied; implementation presence alone is not completion.

## Current recorded state

- **Completed foundations:** K0–K1 and R0–R5 are complete.
- **R6: COMPLETE** through R6-G; formally closed on 2026-11-04.
- **R7-0, R7-A, and R7-B B0: COMPLETE.**
- **R7-B B1: ACCEPTED and MERGED (2026-11-06).** PR [#43](https://github.com/abtn/Watch-Architecture-Rev2/pull/43) merged to `main` at `d1a8b88fd930207142304fc9b0b7274de5de4992`. The exact PR head `a7c6d4a7de5529ea9fb4faff5c9ab17bbbc51fd8` passed hosted CI run [42246346103](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42246346103): fresh PostgreSQL migration/single-head checks, Ruff, Mypy (32 source files), 690 tests, and container cleanup. Operator-local exact-code-head verification and the B1 integrity corrections are recorded in `docs/testing.md`.
- **R7-B B2: COMPLETE — formally closed 2026-11-08 with accepted residual verification gaps.** Steps 1–8 are accepted and merged at `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`; the three accepted residuals remain: no separate focused regression run, no recorded `git diff --check`, and no complete line-by-line final diff review. The active approval allowlist remains exactly `create`.
- **R7-B B3.2: COMPLETE — Checkpoint 4 formally accepted (2026-11-08); B3.3 implementation explicitly authorized.** PR [#60](https://github.com/abtn/Watch-Architecture-Rev2/pull/60) merged on 2026-11-08 at `31be3a25cf7f52ca81eab65cc10280a855738c3d`; final PR head `0eecefedbc4ef6e4b60cbd8c3eacf31e1256f362` passed hosted CI run [42496681657](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42496681657): fresh PostgreSQL migration/single-head, Ruff, Mypy, and 823 tests (95 warnings). Operator-local exact-merge verification passed on the same merge SHA: migration/single-head at `0017_r7b_assessments`, 9 model tests, 8 migration tests, Ruff, Mypy (33 files), 823 full-suite tests (95 warnings, 123.45s), and both diff checks. The disposable container was removed and database environment values restored; full evidence is in `docs/testing.md`. The Operator accepted Checkpoint 4 and authorized B3.3 on 2026-11-08.
- **R7-B B3.3: COMPLETE — merged 2026-11-09.** PR [#62](https://github.com/abtn/Watch-Architecture-Rev2/pull/62) merged at `f7683b3c7812c3250e0fed5e8e689ade6ecaeca5`; final PR head `8ffd6ac5a2b178d6d7045a8d765f3e7c33b59b4e` passed hosted CI run [42580930086](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42580930086). The implementation head `24de1ffa33b30060d8de6816cf7b5351f72c7eaf` passed hosted CI run [42579389483](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42579389483) and Operator-local exact-head verification: migration/single-head at `0017_r7b_assessments`, 61 focused tests, Ruff, Mypy, 848 full-suite tests (95 warnings, 128.61s), diff checks, environment restoration, and disposable-container cleanup. The documentation-updated final PR head also passed hosted CI before merge. Full evidence is in `docs/testing.md`.
- **R7-B B3.4: COMPLETE — Operator-accepted and merged 2026-11-09.** PR [#64](https://github.com/abtn/Watch-Architecture-Rev2/pull/64) merged to `main` at `9abd949a8e682b4df75a77f03acca638a62e472e`. Final PR head `e0944645f8756b702367c69f15e2743880364694` passed Operator-local exact-head verification: fresh PostgreSQL migration/single-head at `0018_r7b_lifecycle_review_date`, Ruff, Mypy (37 source files), 89 focused tests, 881 full-suite tests (113 Alembic deprecation warnings), and `git diff --check`; the disposable container was removed and database environment variables restored. Hosted CI run [42590404433](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42590404433) passed on implementation code head `e2fa162b6f9d77506d16458c1b24c81a57a21b66` (881 passed, 113 warnings). B3.4 delivers deterministic retire/supersede assessment and immutable recording only; it does not commit lifecycle changes or widen approval.

**B3.5 — TaskRuntime, recovery, and lifecycle Events: COMPLETE — IMPLEMENTED AND MERGED (2026-11-10).** PR [#66](https://github.com/abtn/Watch-Architecture-Rev2/pull/66) squash-merged to `main` at `a6cc81c2aef47d659252b89421e27b08735d944b` from exact PR head `65edf206eb6cd68859147ee8c2f68a4717c6fa87`. Hosted CI run [42655193654](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42655193654) passed fresh PostgreSQL migration/single-head checks, Ruff, Mypy, and the full suite (**884 passed, 113 warnings**). Operator-local verification on the same exact PR head passed fresh disposable PostgreSQL migration to the sole head `0018_r7b_lifecycle_review_date`, 43 focused lifecycle tests, Ruff, Mypy (37 source files), 884 full-suite tests, and both diff checks; the worktree was clean, environment variables restored, and the disposable container removed. B3.5 adds explicit lifecycle TaskRuntime admission/finalization/recovery/replay and a narrow TaskRunner; it does not add automatic TaskDispatcher registration or canonical `KnowledgeItem`/`LearningChange` writes. The active approval allowlist remains exactly `create`. B3.6–B3.9 remain separately gated.

**B3.6 — approval-time assessment binding: IMPLEMENTED AND MERGED (2026-11-10).** PR [#68](https://github.com/abtn/Watch-Architecture-Rev2/pull/68) squash-merged to `main` at `4735b93c74025ddee3bd099ef6d5e64cbac34719`; exact PR head `86f3bcf91ca024486f3a3b918a2c7490ec0ea9da`. Hosted CI run [42777343863](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42777343863) passed fresh PostgreSQL migration/single-head checks, Ruff, Mypy (38 source files), and the full suite (**908 passed, 113 warnings**). Operator-local exact-head verification passed on the same PR head: fresh disposable PostgreSQL, sole Alembic head `0018_r7b_lifecycle_review_date`, Ruff, Mypy (38 source files), **908 full-suite tests**, `git diff --check`, clean worktree, environment restoration, and disposable-container cleanup. The 113 warnings are existing Alembic `path_separator` deprecations. B3.6 binds operation-specific assessment state, payload hashes, canonical host Operator identity, policy/evaluator/proposal/target/evidence data, and the complete supersede successor snapshot across request fingerprint, TaskRuntime, commit, finalization, and replay. Historical request/decision schemas remain compatible. The approval allowlist remains exactly `{"create"}`; non-create lifecycle requests remain rejected and no lifecycle commit path is enabled.

## Next actionable step

**B3.7 — TEST IMPLEMENTATION COMPLETE (2026-11-10): integrated regression matrix.** B3.2–B3.6 are implemented and merged. The frozen B3.7 matrix is now mapped to concrete tests across RV-01–RV-06, LC-01–LC-05, DB-01–DB-04, TK-01–TK-02, EV-01–EV-02, RP-01–RP-03, AP-01–AP-05, and E2E-01–E2E-05. Cumulative regression checkpoints are merged in PRs #69–#82, #84–#87, and #89–#92; PRs #83 and #88 were superseded and closed after their changes were carried forward by rebased PRs #86 and #89. The later slices add target/proposal drift (#80), successor drift and malformed retire proposals (#81–#82), time-sensitive observation checks (#84), revalidation and lifecycle persistence/finalization/recovery failure atomicity (#85, #89–#90), canonical evidence and cross-Team reference integrity (#86–#87), missing/duplicate recorded-Event rejection (#91), and service-level proposal-delete restriction (#92). PR [#92](https://github.com/abtn/Watch-Architecture-Rev2/pull/92) merged at `0a76c27b8d455509f90a864bc2695d01db04805d` from exact tested head `6b624310d4d3ae53153dba1b9f47e949564de079`; hosted CI run [42831066494](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42831066494) passed fresh PostgreSQL migration/single-head, Ruff, Mypy, and **946 tests (113 existing Alembic deprecation warnings)**. The 113 warnings are the existing Alembic `path_separator` deprecations. Hosted CI is green for the merged B3.7 test checkpoints. Operator-local exact-head verification for PRs #80–#92 has not been run; that is a B3.8 responsibility. B3.7 test implementation is complete, but this is not B3 phase closure: B3.8 exact-head verification and B3.9 documentation closeout/formal B3 exit acceptance remain separately gated. The approval allowlist remains exactly `{"create"}`; no lifecycle commit authority is enabled.

## Milestone overview

| Phase | Recorded status | Purpose |
|---|---|---|
| K0 | Complete | Python/uv, PostgreSQL + pgvector, Alembic, tests, Ruff, mypy. |
| K1 | Complete | Smallest proposal → validation → atomic Kernel commit → Event path (`ingest_source`). |
| R0 | Complete | Freeze Revision 2 architecture semantics and boundaries. |
| R1 | Complete | Verify compatibility with the existing Kernel and Task/write-scope model. |
| R2 | Complete | Durable Objective model and lifecycle. |
| R3 | Complete | Deterministic, read-only StateAssessment with provenance. |
| R4 | **Complete** (closed 2026-10-20) | StrategyProposal boundary, multi-Vision/Workstream/Action semantics, deterministic validation and reconstruction. |
| R5 | **Complete — closed 2026-10-24 by explicit operator decision** | Materialize one accepted Strategy as one durable Plan and ordinary Tasks; retain the Task-execution dependency for R6. |
| R6 | **COMPLETE — G0 through R6-G; formally closed 2026-11-04.** | The integrated three-case source→Evaluation→distillation→Operator→Team Experience path passed the ten-proof technical review and received explicit Operator exit approval. PR #35 merged to `main` at `56745b613b5b77a21a514b4e261d3450f90c0df1`; final PR-head CI passed, and exact implementation-head hosted/local verification is recorded below. D10 remains create-only; R7 implementation remains separately gated. |
| R7 | **R7-0/R7-A/B0 complete; B1 merged; B2 closed with accepted residuals; B3.2–B3.6 implemented and merged; B3.7 test implementation complete; B3.8–B3.9 remain gated.** | B3.2–B3.6 merge evidence remains recorded above. B3.7's full integrated regression matrix is mapped and merged through PRs #69–#82, #84–#87, and #89–#92 (PRs #83/#88 were superseded and closed). Latest checkpoint PR #92 merged at `0a76c27b8d455509f90a864bc2695d01db04805d`; exact PR head `6b624310d4d3ae53153dba1b9f47e949564de079` passed hosted CI run [42831066494](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42831066494): fresh PostgreSQL migration/single-head, Ruff, Mypy, 946 tests, and 113 existing Alembic deprecation warnings. The matrix maps all RV, LC, DB, TK, EV, RP, AP, and E2E IDs. Operator-local exact-head verification has not been run for B3.7 checkpoints and belongs to B3.8. B3.9 formal closeout and Operator B3 exit acceptance remain pending. The approval allowlist remains exactly `{"create"}`; no lifecycle commit, B4–B6, or R7-C work is authorized. |
| R8 | Future | Multi-domain pressure test. |
| R9 | Future | Codified agent-assisted production workflow. |

## K0 — Tooling baseline (complete)

Expected baseline: Python 3.12+, `uv`, PostgreSQL + pgvector, Alembic, pytest, Ruff, and mypy. The executable versions/configuration are in `pyproject.toml`, `uv.lock`, `compose.yaml`, and the migrations.

## K1 — Smallest Kernel commit path (complete)

Proves proposal → deterministic application validation → atomic persistence → Task-attributed Event. The bounded initial path is `ingest_source`; it must preserve immutable content-addressed Snapshots, hash validation, idempotency, and write-scope enforcement. Do not expand the K1 task types while doing later Control work unless an authorized milestone explicitly requires it.

## R0–R3 — Control foundations (recorded complete)

- **R0:** Revision 2 semantics and non-goals established.
- **R1:** preserve existing Task, Kernel, policy, and commit boundaries.
- **R2:** Objective is durable, team-owned, and follows its explicit lifecycle.
- **R3:** StateAssessment is deterministic derived state. Its basis/hash/timestamp and any required immutable payload are preserved when a historical assessment informs a decision. It never mutates world/team memory and is not authoritative.

See the relevant code/tests and the source-control history for the evidence of each completed phase.

## R4 — StrategyProposal boundary (complete — closed 2026-10-20)

### Semantic contract

One accepted StrategyProposal is one coordinated strategic decision for one Objective and one historical StateAssessment basis. It may contain multiple concurrent **Visions → Workstreams → Actions**, with explicit Action-to-Action prerequisites. Prerequisites may cross Vision/Workstream boundaries; reject invalid targets, self-dependencies, and cycles.

- A Vision is a bounded strategic perspective.
- A Workstream groups related Actions for human comprehension; it is not a dependency or execution boundary.
- An Action is intended work, not a Task.
- Acceptance establishes deterministic legality and authorization for later Plan materialization; it does not prove wisdom or effectiveness.
- The exact accepted structure and provenance must be reconstructable from durable Task-attributed Event data without the model transcript.
- Strategy/Vision/Workstream/Action are not thereby required to be separate durable entities.
- Model output cannot mutate TeamPolicy/Team structure, create arbitrary rows, self-authorize tools, bypass Task scope, raise its budget, or commit durable state.

### Recorded implementation and verification evidence

The source PLAN records the redesigned implementation at commit `50e288a` on the R5 worktree, `44` Strategy tests passing, targeted Ruff, `mypy core`, and `git diff --check` passing, and disposable PostgreSQL migrations reaching `0006_immutable_plan_actions`. It also records that the full suite and R5-specific tests were not run. These are **source-recorded results**; the fresh closure verification below supersedes them where it repeats them.

### Closure record — 2026-10-20

- **Live Git state (verified by preflight):** branch `docs/refactor` at `cee2bbf`; the redesigned implementation commit `50e288a` is an ancestor of HEAD; `main` is an ancestor of `docs/refactor` (no divergence).
- **Fresh verification — commands actually run on this state**, against a disposable PostgreSQL database (`watch_r4_gate`; the persistent `watch` database was never used):
  - `uv run pytest tests/test_strategy.py` → `44 passed`.
  - `uv run pytest` (full suite) → `185 passed`. The full suite had not been run for R4 previously; this closes that evidence gap.
  - `uv run ruff check .` → passed.
  - `uv run mypy core` → passed (10 source files).
  - `uv run alembic upgrade head` (disposable DB) → reached `0006_immutable_plan_actions`.
  - `git diff --check` → clean.
- **Operator-reported evidence (recorded distinctly):** on 2026-10-20 the operator stated that all code is correct and the tests passed and that they had checked them personally. This is operator-reported, not agent-rerun.
- **Authority resolution:** ADR-0023 (Control layer) and ADR-0024 (Strategy is not TeamPolicy) moved from `Proposed` to `Accepted` by explicit operator decision dated 2026-10-20, recorded in the ADRs. ADR-0025, ADR-0026, and ADR-0027 remain `Proposed` (R5 scope; not required for R4 closure).
- **Phase boundary:** `docs/refactor` merged into `main` with a merge commit per operator decision, following the repository's `Merge branch '...'` convention. No push was performed.

## R5 — Plan materialization and lifecycle (**complete — closed 2026-10-24**)

R5 was deliberately divided into two required implementation slices. This split changed the delivery sequence, not the overall R5 contract or exit criteria. Both R5-A and R5-B are recorded READY, their correction is integrated into `main`, and the operator's formal R5 closure decision is recorded below.

### Entry gate — recorded 2026-10-20: READY

- R4 formally closed with fresh, agent-run verification evidence. ✓
- Explicit operator R5 authorization recorded 2026-10-20. ✓
- ADR-0027 remains `Proposed`. The operator's R5-A instructions on 2026-10-21 authorize verification and correction of the existing daily Task-start quota behavior against the semantics stated below and in `docs/tasks.md`; this implementation scope does not silently change ADR-0027's formal status.

### Overall R5 contract

- One accepted Strategy for one Objective produces one Plan.
- Preserve the complete accepted Vision/Workstream/Action structure, stable identities, prerequisites, proposal/assessment provenance, budget envelope, and completion/stop conditions as immutable intent.
- Plan creation, its initial ordinary Tasks, and the creation Event commit atomically; partial materialization is not a valid durable state.
- Every intended Action maps to exactly one initial ordinary Task after materialization. A Task may otherwise remain reactive and need no Plan.
- Plan-linked Task prerequisites are enforced in the existing Task admission path; no second runtime or separate scheduler is introduced.
- Plan lifecycle is `active → completed | stopped`; terminal states do not reopen. Stop reasons are `abandoned`, `invalidated`, and `superseded`.
- Progress is derived from durable Task state. Completion requires every intended Action to have exactly one linked Task in `done` status and the declared completion condition to be satisfied by durable records.
- Replanning creates a new Plan rather than silently mutating historical intent. The separate replanning capability remains outside R5-A and R5-B.
- Budget hierarchy: TeamPolicy ceiling → Plan envelope → individual Task budget.
- The creating `create_plan` Task's `policy_version` records the version used to validate creation; do not add a separate Plan policy pin without explicit authority.

### Existing implementation artifacts are not proof of completion

The repository contains `core/plans.py`, Task runtime prerequisite checks, tests, and migrations `0004_plans.py` through `0006_immutable_plan_actions.py`. Their presence alone does not prove every R5 acceptance criterion is satisfied. Derive any schema change from the actual model and current migration head; do not assume an old proposal for a `0007_plans.py` migration still applies.

### R5-A — Reliable Plan Materialization and Recovery (**current slice**)

R5-A validates and makes reliable the accepted-Strategy → Plan → initial ordinary Tasks transition. It does not implement the remaining Plan lifecycle transitions.

Acceptance criteria:

- Materialization preserves the complete accepted Strategy structure, canonical Action definitions and identities, prerequisites, accepted proposal Event/hash, Objective/Team ownership, historical assessment basis/timestamp, budget, and completion condition.
- The Plan, Action mappings, initial Tasks, and required attributable creation Event commit atomically.
- Every accepted Action has exactly one Plan Action mapping and exactly one initial ordinary Task; invalid, missing, duplicate, or contradictory mappings are rejected.
- Same-operation replay is idempotent; conflicting reuse is rejected; concurrent operations cannot produce duplicate or partial materialization.
- Reconstruction after restart reproduces the accepted intent from durable records. Missing, corrupt, incomplete, or inconsistent required records fail clearly; reconstruction must not fabricate, silently repair, or accept invalid authoritative state.
- Plan/Action immutability, provenance, action identity/uniqueness, and rollback behavior are tested.
- Prerequisites are validated against the accepted Strategy and enforced at the existing Task admission boundary without a second scheduler or runtime.
- Daily Team quota accounting, when configured, uses durable `task_started` Events for the Team and UTC calendar-day boundaries. Test retries, the final available unit under concurrency, rejection without partial changes, absent quota, zero quota, invalid configuration, and validation consistency between PlanService and TaskRuntime. A pending Task created during materialization is not a Task start.
- A Task-count quota is not monetary/token-spend accounting; do not claim that daily cost limits are enforced.

Failure-path behavior is a first-class acceptance criterion. In addition to successful cases, tests must check rollback and durable-state integrity when validation, reconstruction, admission, persistence, or a concurrent operation fails.

### R5-A implementation and gate record — 2026-10-21

The agent reported and committed the following fixes on `R5-rebased`. The commit is local and was not pushed as part of the commit task.

- Shared quota parsing was added in `core/policy.py` and adopted by PlanService and TaskRuntime, resolving disagreement for zero and non-integer values and handling malformed policy structure.
- Plan materialization now serializes use of an accepted Strategy Event, rejects already-materialized proposals with a stable category, and handles corrupt prior creation Events through a categorized failure path.
- Regression coverage was added for incomplete/corrupt Plan state, accepted-provenance tampering, conflicting and concurrent materialization, policy rejection reasons, pending Tasks not counting as starts, zero/invalid quota values, UTC-day boundaries, and Team scoping.
- Post-commit focused Strategy/Plan/TaskRuntime tests: **147 passed**. Post-commit full test suite: **222 passed**. Ruff passed, mypy passed across 11 source files, and `git diff --check` was clean.
- Local implementation commit: `71c7b1d7488c7de5e5e40f939283ff35f8abe5d0` (`R5-A: harden Plan materialization and quota policy`). The agent confirmed the intended five code/test paths only, a clean worktree after commit, and no schema migration was required.
- The agent also reported a fresh disposable PostgreSQL migration run reaching `0006_immutable_plan_actions`, with both immutability triggers present. The report does not state that this migration command was rerun after the implementation commit; the full suite and static checks were explicitly rerun after commit.
- The implementation includes failure-oriented regression coverage for incomplete/corrupt state and daily quota edge cases.

**R5-A gate: READY (2026-10-21).** This historical record marks the completed R5-A slice only. At that point, overall R5 remained in progress pending R5-B and the overall exit criteria. ADR-0027 remains `Proposed`; this slice gate does not change its formal status and does not claim any daily monetary/token-cost enforcement.

### R5-B — Plan Lifecycle Behavior (**required after R5-A**)

R5-B implements and verifies the lifecycle contract already required by the overall R5 milestone and the relevant Plan specification/ADR.

Acceptance criteria:

- Legal application-controlled transitions from `active` to `completed` or `stopped` are persisted with the required attributable Events; illegal transitions reject without partial state changes.
- Terminal Plans cannot reopen.
- `stopped_reason` is constrained to `abandoned`, `invalidated`, or `superseded`.
- Completion is allowed only when every intended Action has exactly one linked Task in `done` status and the declared completion condition is satisfied by durable records.
- Plan progress and completion decisions derive from durable Task/Event state rather than model assertions or transient in-memory state.
- Lifecycle state and transition provenance remain consistent and reconstructable after restart; concurrent/conflicting transitions are rejected safely.
- Supersession can stop the old Plan without rewriting its immutable intent. Choosing and materializing a replacement Plan through replanning remains in the later dedicated milestone.

Define tests for each legal transition, illegal transition, terminal-state protection, completion preconditions, stop reasons, stale/concurrent transition, rollback, and restart reconstruction. Do not mark lifecycle behavior complete from model-only or service-only tests that bypass persistence contracts.

### R5-B implementation and gate record — 2026-10-21

The following records the initial R5-B implementation and pre-fix verification report. The original report described the code as uncommitted; that state was superseded by implementation commit `1012aaa`, the lifecycle Event-validation correction, and the 2026-10-24 database-constraint correction recorded below.

- **Implementation.** `PlanService.transition` in `core/plans.py` implements the `transition_plan` Task operation and lifecycle reconstruction validation; `core/models.py` adds the Plan lifecycle columns and constraints; migration `migrations/versions/0007_plan_lifecycle.py` (revision `0007_plan_lifecycle`, revising `0006_immutable_plan_actions`) adds `plans.stopped_reason` and `plans.successor_plan_id`, the check constraints `ck_plans_status`, `ck_plans_stopped_reason`, and `ck_plans_lifecycle_state`, the `fk_plans_successor` self-reference, and replaces the `preserve_plan_intent` trigger with a scoped version that permits only lifecycle-column changes. Action immutability and the R5-A constraints are unchanged, and no historical migration was edited.
- **Operation contract.** A running same-Team `transition_plan` Task with `allowed_writes=["Plan"]`, active Team, matching policy version, and a zero-usage budget; `active → completed` and `active → stopped` only; terminal Plans cannot reopen; stop reasons `abandoned`, `invalidated`, `superseded`; `superseded` requires an already-existing active successor Plan for the same Objective, distinct from itself. Success Events are `plan_completed` and `plan_stopped`; a rejection emits a categorized `plan_transition_rejected` Event. A matching same-Task retry replays the recorded transition; conflicting reuse, stale expected status, and concurrent transitions reject.
- **Completion preconditions.** Every Action has exactly one linked Task, every linked Task is `done`, and each linked Task carries a durable successful ingestion outcome (`signal_ingested` or `fetch_no_change`), so the declared `configured_source_ingested` condition is proven by durable records rather than model assertion.
- **Reconstruction.** `PlanService.reconstruct` validates persisted lifecycle state against its required attributable Event; missing, tampered, or contradictory lifecycle records fail clearly and are never fabricated or silently repaired.
- **Freshly run verification on this checkout.** Focused R5-B tests **32 passed**; focused Strategy/Plan/TaskRuntime tests **147 passed**; full test suite **254 passed** on two disposable PostgreSQL databases (an existing disposable database upgraded `0006 → 0007`, and a freshly installed disposable database); Ruff passed; `mypy core` passed across 11 source files; `git diff --check` was clean.
- **Migration evidence on disposable databases.** Fresh installation reached `0007_plan_lifecycle`; upgrade from the previous head succeeded; a `0007 → 0006 → 0007` round trip restored an identical schema; and a downgrade attempt was refused with a clear error while a non-active Plan existed.

**R5-B gate: READY (2026-10-21).** This records the R5-B slice only.

#### R5-B commit and post-fix verification follow-up — 2026-10-24

- **Commit.** The R5-B implementation, migration, tests, documentation, and `.gitignore` update were committed locally on `R5-rebased` as `1012aaa` (`R5-B: implement and verify Plan lifecycle`). The worktree was clean after the commit; the branch was eight commits ahead of `origin/main` and had not been pushed at the time of verification.
- **Lifecycle Event-validation correction.** The transition path now validates the recorded lifecycle Event before same-Task replay, and reconstruction requires the full expected payload (`operation`, Plan ID, expected/target statuses, stop reason, successor reference, Objective/Team identity, and from/to statuses). Four parameterized tampering cases and one same-Task retry-after-tampering case were added.
- **Post-fix verification.** On the disposable `watch_r5b_fresh` database, `uv run pytest tests/test_plan_lifecycle.py -q` passed (**36 passed**); `uv run pytest tests/test_plans.py tests/test_task_runtime.py tests/test_strategy.py -q` passed (**147 passed**); and `uv run pytest -q` passed (**258 passed**). `uv run ruff check core/plans.py tests/test_plan_lifecycle.py`, `uv run mypy core` (11 source files), and `git diff --check` all passed.
- **Migration qualification.** The post-fix patch changed only `core/plans.py` and `tests/test_plan_lifecycle.py`; migrations were not rerun in this post-fix pass. Fresh-install, previous-head upgrade, downgrade/upgrade round-trip, and downgrade refusal evidence remains the earlier recorded R5-B migration verification above. The persistent `watch` database was not targeted.

#### R5-B database-constraint correction — verified on disposable PostgreSQL (2026-10-24)

A follow-up review found that migration `0007_plan_lifecycle` did not require `successor_plan_id IS NULL` when a stopped Plan's reason was `abandoned` or `invalidated`. Correction commit `95a1e8e` adds migration `0008_plan_lifecycle_state`, mirrors the stricter constraint in `core/models.py`, and adds two parameterized regression cases for those invalid database states.

Programmer-reported verification on the checkout at `c99858f` in `r5b-lifecycle-constraint-fix`:

- `uv run alembic current` before the upgrade reported `0007_plan_lifecycle`.
- `uv run alembic upgrade head` succeeded; `uv run alembic current` then reported `0008_plan_lifecycle_state (head)`.
- `uv run pytest tests/test_plan_lifecycle.py -q` — **38 passed**.
- `uv run pytest tests/test_plans.py tests/test_task_runtime.py tests/test_strategy.py -q` — **147 passed**.
- `uv run pytest -q` — **260 passed**.
- `uv run ruff check .` — passed.
- `uv run mypy core` — passed, 11 source files.
- `git diff --check` — clean.

Both `DATABASE_URL` and `TEST_DATABASE_URL` were set to the disposable `watch_r5b_fresh` database; the persistent `watch` database was not targeted. This pass verifies the existing-database upgrade from `0007` to `0008`. A fresh full-chain migration through `0008` was not rerun for this correction. After synchronizing the documentation commits, the programmer successfully downgraded to `0007_plan_lifecycle` and upgraded back to `0008_plan_lifecycle_state` on the same disposable database; schema equivalence was not separately compared. At the time this verification record was written, review/integration and the operator's formal overall R5 gate were pending. The correction was subsequently integrated into `main` by PR #2, merge commit `435e88f`; the operator later formally closed R5 on 2026-10-24, as recorded below.


#### Task-completion dependency — recorded, not resolved in R5

No component in the current codebase moves a Task to `done`. `docs/architecture.md` §4 assigns the `running → done` transition to the worker/execution path, and the current repository contains no worker runtime, so no Plan-linked Task can reach `done` through the system as it stands. The R5-B completion precondition is therefore verified against durable Task/Event state prepared for the test; that preparation is not itself a delivered capability.

This does not change the R5 exit criteria. `PLAN.md` "Overall R5 exit criteria" require that the R5-B "completion/stopping/supersession rules" pass, and the R5-B acceptance criteria require that completion be **allowed only when** the durable preconditions hold; neither requires R5 to deliver the Task execution path that produces `done`. The end-to-end loop that exercises it is R6 ("ordinary Tasks → existing Task execution/Kernel commit"). The dependency is recorded here and carried forward to the milestone that delivers Task execution. No existing criterion is weakened, and no new requirement is invented in this record.

#### R5 status after R5-B

The R5-A implementation and the R5-B lifecycle implementation, including the `0008_plan_lifecycle_state` database-constraint correction, have passed the recorded focused/full tests and static checks on the corrective branch. The migration upgrade from `0007` to `0008` was verified on disposable PostgreSQL. The correction is integrated into `main` by PR #2, merge commit `435e88f`. The operator formally approved R5 closure on 2026-10-24; the closure record below preserves the verification qualifications and Task-execution dependency. ADR-0027 remains `Proposed`. R6-A was subsequently authorized and is complete (see the R6 section).

#### Formal R5 closure record — 2026-10-24

**Decision:** The operator explicitly approved closing R5, with the Task-execution dependency retained for R6. R5 is CLOSED as of 2026-10-24. This is a milestone-gate decision, not acceptance of ADR-0027 or authorization to start R6.

**Exit-gate basis:**

- R5-A is recorded READY for Plan materialization, reconstruction, integrity, prerequisite admission, quota, atomicity, idempotency, concurrency, immutability, and provenance.
- R5-B is recorded READY for Plan lifecycle transitions, terminal-state protection, durable completion preconditions, stop/supersession rules, Event validation, reconstruction, concurrency, and rollback behavior. The database constraint correction was integrated through PR #2 (merge `435e88f`); the preceding R5 status-alignment documentation was integrated through PR #3 (merge `9ba1072`).
- Programmer-reported verification on disposable PostgreSQL: 38 lifecycle tests, 147 focused R5-A/Strategy regression tests, and 260 full-suite tests passed; `ruff check .`, `mypy core` (11 source files), and `git diff --check` passed. This record preserves those results as reported; they were not independently rerun during closure documentation.
- Migration qualification: upgrading an existing disposable database from `0007_plan_lifecycle` to `0008_plan_lifecycle_state` and the later `0008 → 0007 → 0008` round trip were reported successful. A fresh full-chain installation through `0008` was not rerun, and schema equivalence after the downgrade/upgrade round trip was not separately compared.

**Task-execution dependency retained for R6:** The current repository has no worker/execution path that transitions a Task to `done`; R5-B completion tests therefore use durable Task/Event state prepared for the test. R5 verified that Plan completion is allowed only when its required durable preconditions hold. Delivering the end-to-end Task execution path remains R6 work and is not claimed as completed by R5.

**Decision boundaries:** ADR-0027 remains `Proposed`. R5 closure does not itself authorize R6; a separate operator authorization and R6 entry-gate review are required.


### Daily quota semantics and authority

The quota setting is `TeamPolicy.rules["budgets"]["max_tasks_per_day"]`. It is distinct from `StrategyProposal.constraints.max_tasks`, which bounds Actions within a Strategy. When configured, the daily quota counts successful starts from durable `task_started` Events associated with the Team, including successful retries, over the UTC calendar day. Rejected starts count zero; absence preserves unlimited behavior; zero permits no starts that UTC day; configured values must be non-negative integers, with booleans and non-integer types rejected. Quota check, Task transition, attempt increment, and Event must be transactionally consistent and concurrency-safe.

ADR-0027 remains `Proposed` in the decision index. The R5-A implementation/test task must not change that status implicitly, claim that the ADR has been formally accepted, or broaden task-count accounting into spend accounting.

### Overall R5 exit criteria

- R5-A materialization, reconstruction, integrity, prerequisite admission, quota, atomicity, idempotency, concurrency, immutability, and provenance criteria pass.
- R5-B lifecycle transitions, completion/stopping/supersession rules, and durable reconstruction criteria pass.
- Task dependencies do not create a new scheduler or mutate Task states behind the runtime.
- Required focused and full verification is freshly run; migration/integration evidence uses a disposable PostgreSQL database.
- All checks and the formal phase exit gate are recorded honestly.

## R6 — Knowledge-grounded execution and experience distillation

**Status and authority:** R6-G0 and R6-A through R6-E are complete. R6-F Checkpoints 1–4 are complete and merged. PR #33 merged on 2026-11-03 at `de1af38d67a7e79d71110bdda7155244717fbf73`; local C3+C4 verification passed on the exact merged tree against a disposable PostgreSQL database, with one `0013_team_experience_projection` head, 118 focused tests, Ruff, Mypy (27 source files), 594 full-suite tests and diff check. Hosted CI run [41613573334](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41613573334) passed fresh migrations, Ruff, Mypy and 594 tests. D10 and D7 are resolved; D7 implementation resides in C4. R6-G was completed and formally closed on 2026-11-04 after explicit Operator approval and merge of PR #35.

**R6-A implementation record.** The operator authorized R6-A implementation. Four checkpoints were delivered on branch `r6a-step1-schema-outcome` and merged to `main` by PR #12 (merge commit `ebbc48d`, 2026-10-28): Step 1 schema at `42257ad` (migration `0009_task_lifecycle_outcome` — Task `created_at`, nullable `completed_at`, `max_attempts` with a backfill from the earliest `task_started` Event, `uq_tasks_id_team`, and the `outcomes` table with its eight named constraints — the matching `Outcome` ORM mapping, explicit `max_attempts=3` pinning in `PlanService._create`, and focused schema tests); Checkpoint 2A terminal finalization at `c3e9428` (atomic terminal `task_execution` Outcome persistence with observation Snapshot, terminal Task status, and terminal Events in one transaction, plus replay/idempotency and conflict handling); Checkpoint 2B retry scheduling and attempt exhaustion at `e05a8a4` (retryable failure returns the Task to `pending` with `task_attempt_failed`/`task_retry_scheduled`, exhausted admission is rejected with `task_attempts_exhausted`, and duplicate/corrupt retry reports are rejected); and Checkpoint 2C interrupted-task recovery at `da47694` in `TaskRuntime.recover_interrupted()` (read-only discovery, Task-row-lock recheck, retry through the existing durable disposition, exhausted recovery through the single terminal finalizer with a deterministic observation, and safe handling of races, missing current-attempt evidence, and corruption), with focused tests in `tests/test_task_lifecycle_recovery.py`. Automated CI is committed at `bda8d55` and passed on the merged head `ffe8e76`. R6-A's exit criteria in [the R6 entry gate](docs/development/r6-entry-gate.md) are satisfied: legal transitions only, Task state and Events agree, terminal finalization cannot commit without its required Outcome, and retries and crashes do not double-commit or leave partial lifecycle changes.

**R6-B implementation record.** `core/dispatcher.py` and `core/source_fetch.py` form the bounded configured-source path: startup interrupted-task recovery, durable source resolution from a Plan Action, restricted fetch, `IngestionService` commit, and lifecycle reporting through `TaskRuntime`. Durable source identity is authorized by `TeamPolicy.rules["sources"]`; the path deliberately does not add a second runtime or general-purpose scheduler.

**R6-C implementation record.** `core/execution_assessment.py` rebuilds a deterministic read-only execution assessment from Plan intent, Tasks, attempts, Events, terminal Outcomes, and Snapshot/Signal evidence. It validates outcome-to-event consistency and hashes the canonical derived result. It does not persist an Evaluation or write lifecycle records. RAG Context, persistent Evaluation/KnowledgeItem, and experience-distillation/index-publication paths remain later work.

**Revised target:** deliver the first small end-to-end knowledge cycle: retrieve scoped, source-traceable knowledge through RAG; assemble a bounded task Context; propose and validate Strategy; materialize immutable Plan and ordinary Tasks; execute one bounded configured-source Task; persist durable evidence and Outcome; reassess; distill an evidence-linked abstraction from experience; commit it through the authorized learning path; index the accepted canonical version; then retrieve it for a later task.

The logical knowledge layers are: **Domain Knowledge Core** (what the team knows about the subject), **Team Experience Core** (what it has learned from doing the work), and a derived **Task Context** (what matters for one job). RAG indexes are regenerable projections, not authority. A vector match does not establish truth; current canonical records, source provenance, access control, status, uncertainty, and the existing application/Kernel validation gates remain authoritative. The layers may share physical retrieval infrastructure, but their scope and semantics must remain distinguishable.

**R6-G closeout:** the integrated Objective/assessment → RAG Context → validated Strategy → immutable Plan/Tasks → three bounded source cases → terminal Outcomes → deterministic reassessment → recorded rule Evaluations → mixed-case ExperienceDistiller proposal → explicit Operator decision → canonical KnowledgeItem → Team Experience projection → later-Task retrieval path is implemented and merged by PR #35. Its ten acceptance proofs passed technical review; the Operator approved the R6 exit gate on 2026-11-04. Preserve one TaskRuntime, the narrow configured-source TaskDispatcher, D10 create-only scope, and all existing validation, provenance, write-scope, policy, budget and canonical-authority boundaries.
### R6-G implementation, verification and closure record — 2026-11-04

**D9 RESOLVED by explicit Operator decision:** the first R6-G integrated slice uses the deterministic ruleset `watch.r6g.ingest-source-rules`, revision `1`, for configured-source `ingest_source` terminal Outcomes only. No human or model-generated Evaluation producer is included. The Operator separately authorized the bounded implementation and approved the R6-G exit gate after the ten-proof technical review; PR #35 merged on 2026-11-04 at `56745b613b5b77a21a514b4e261d3450f90c0df1`.

**Step 1 — evaluator source selected and bounded.** The initial ruleset is `watch.r6g.ingest-source-rules`, revision `1`, for `ingest_source` Task Outcomes only. It verifies immutable terminal Outcome/Task Events and their linked canonical Signal/Snapshot records. `success_signal_created` and `success_no_change` classify as `worked` only when every required identity, status, event, and hash predicate agrees; `terminal_failure` classifies as `failed` only when the terminal failure record is internally consistent. Inconsistent, stale, cross-Team, corrupt, or unsupported evidence fails closed and creates no Evaluation. The conclusion describes ingestion execution-contract conformance, not source truth, causal impact, or Objective achievement. The ruleset emits no `mixed` conclusion in revision 1; unsupported cases are not forced into `inconclusive`. The existing `EvaluationService` remains the proposal/provenance/disposition boundary; the rule evaluator cannot record its own status or commit knowledge.

**Step 2 — integrated fixture and service interaction implemented.** The implementation follows `docs/development/r6g-integrated-fixture-design.md`: one Team/Objective, baseline Domain Knowledge, real hybrid Context retrieval, fake StrategyProposer, immutable Plan and three Plan-materialized ingestion cases (new Signal, legitimate no-change, terminal failure), D9 evaluator Tasks, read-only ExecutionAssessment, ExperienceDistiller, Operator rejection/acceptance, Team Experience indexing and later-Task retrieval. Source terminalization creates the evaluator Task and request Event atomically; TaskRuntime recovers committed Evaluations; v2 evidence packs preserve terminal failure as contrary evidence while leaving canonical EvidenceLink stance unchanged. Each persisted case has an explicit schema marker; legacy unmarked R6-F v1 evidence is reconstructed using the original v1 representation. The design's one-runtime and narrow-dispatcher boundaries remain unchanged.

**Step 3 — acceptance tests, exact-head verification and ten-proof review complete; Operator exit approved; PR #35 merged.** The branch contains `tests/test_rule_evaluator.py`, `tests/test_evaluation_tasks.py`, `tests/test_r6g_distillation.py`, `tests/test_r6g_vertical_slice.py`, and extensions to Strategy, Plan and ExperienceDistiller suites. Coverage includes deterministic D9 mappings, atomic evaluator enqueue and committed-Evaluation recovery, failed-case contrary evidence, historical v1 reconstruction, typed Strategy/Plan Task completion and the integrated path to later-Task Team Experience retrieval. `docs/testing.md` retains the ten-criterion acceptance checklist. Hosted CI passed on exact implementation head `2a55acfeadaf37e23b9f2cffd8819b7b460ba6b3` (run [41782439302](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41782439302)): fresh PostgreSQL migration/head validation, Ruff, Mypy, and 614 tests in 44.93s. Programmer-local disposable-PostgreSQL verification on that same exact head also passed; full details are recorded below. The technical ten-proof review supports all ten criteria with no blocking gap; the Operator explicitly approved the exit gate on 2026-11-04 and PR #35 merged.



**Programmer-local verification — 2026-11-04 (operator-reported on the exact implementation head).** On branch `r6g-implementation-20261103`, commit `2a55acfeadaf37e23b9f2cffd8819b7b460ba6b3`, the working tree was clean before and after verification.

- Environment: Python 3.12.12; `uv sync --locked` passed.
- Disposable PostgreSQL: container `watch-r6g-local-20261104-b`, image `pgvector/pgvector:pg16`, database `watch_r6g_check`, host binding `127.0.0.1:55466`. The database was confirmed fresh before migration (`0` user tables; no `alembic_version`). Both `DATABASE_URL` and `TEST_DATABASE_URL` targeted this database during the run and were restored afterwards. The container and its anonymous volume were removed after success; the persistent `watch` database was not targeted.
- `uv run alembic upgrade head` passed. `uv run alembic heads` and `uv run alembic current` both reported the single revision `0013_team_experience_projection (head)`.
- Focused R6-G suite (rule evaluator, evaluator Tasks, R6-G distillation/vertical slice, ExperienceDistiller, StrategyProposer and Plans): **134 passed in 32.23s**.
- `uv run ruff check core tests migrations` passed.
- `uv run mypy core` passed (29 source files).
- `uv run pytest -q` (full suite): **614 passed in 74.48s**.
- `git diff --check` passed; disposable container cleanup succeeded; final `git status --short --branch` was clean and `HEAD` remained `2a55acfeadaf37e23b9f2cffd8819b7b460ba6b3`.

This is operator-reported local evidence, recorded distinctly from hosted CI. It verifies implementation commit `2a55acfeadaf37e23b9f2cffd8819b7b460ba6b3`, which is the source-code tree merged by PR #35; subsequent commits on that PR were documentation-only. The ten-proof technical review and explicit Operator exit approval are recorded in `docs/testing.md`.

**Gate disposition: CLOSED — 2026-11-04.** The ten-proof technical review found no blocking gap; the Operator explicitly approved the R6-G exit gate, and PR #35 merged to `main` at `56745b613b5b77a21a514b4e261d3450f90c0df1`. Final PR-head CI, exact implementation-head CI and operator-local disposable-PostgreSQL results are recorded above. Preserve one TaskRuntime, the narrow configured-source TaskDispatcher, R6-F create-only D10 scope, no production R6-F provider, and all canonical evidence, write-scope and security checks.

**R6-D local verification record (2026-10-29/30):** The first 2026-10-29 local smoke passed functionally but targeted the persistent Compose `watch` database on host port `5432`; it is retained as historical evidence only and is not the disposable-database result. On 2026-10-30, the operator reran the integration against the dedicated container `watch-r6d-embedding-smoke-pg`, bound to `127.0.0.1:55450`, database `watch_embedding_smoke`. Both `DATABASE_URL` and `TEST_DATABASE_URL` pointed to that exact target. `uv run alembic upgrade head` succeeded and `uv run alembic current` reported `0010_knowledge_chunk_projection (head)`. The embedding integration smoke test reported PASS for provider `openai_compatible`, model `text-embedding-bge-m3`, revision `metadata-sha256:e8ffcf172118d67251eccbf45916e407b7e0537deef08f70bbd62e86518e9c69`, 1,024 dimensions, projection indexing, repeat-indexing idempotency, and authorized hybrid retrieval. The same test was repeated with `WATCH_EMBEDDING_REVISION` explicitly set to that exact value and passed again. **Disposable database verification: PASSED. Embedding integration smoke test: PASSED.** The value is the API metadata fingerprint observed during qualification; it is not proof of the model-file or quantized-weight bytes. The operator must change the explicit pin when model weights, quantization, normalization, or preprocessing changes.
### R6-E implementation and verification record — 2026-11-01

R6-E was delivered on `r6e-cloudflare-llama31-provider` in three separately verified checkpoints. The selected generation provider is Cloudflare Workers AI with `@cf/meta/llama-3.1-8b-instruct-fp8` (ADR-0031).

- **Step 1 — Context assembly:** operator-local disposable PostgreSQL verification at `0010_knowledge_chunk_projection`; 12 focused Context assembly tests passed and the full suite passed. The immutable Context Snapshot and Task-attributed manifest/Event are implemented.
- **Step 2 — StrategyProposer:** 30 focused Context/StateAssessment/StrategyProposer tests passed; the full suite passed (**501 passed**). Hosted CI run [41202063715](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41202063715) passed. Provider output remains an untrusted proposal and acceptance stays within `StrategyService`.
- **Step 3 — Task cost accounting:** operator-local disposable PostgreSQL reached `0011_task_generation_cost` with exactly one Alembic head. The focused generation/cost/proposer/assessment suite passed (**43 passed**); Ruff, mypy, the full test suite, and `git diff --check` passed. The disposable PostgreSQL container was stopped and the prior `DATABASE_URL` / `TEST_DATABASE_URL` values were restored.
- **Hosted CI on implementation head `936e4794`:** [run 41279796198](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41279796198) passed fresh migrations, single-head verification, Ruff, mypy, and the full suite (**515 passed in 24.95s**).

**Merge boundary:** PR #28 merged on 2026-11-01, and R6-E is formally closed. R6-F Checkpoints 1–4 are integrated; C3 and C4 merge/verification details are recorded in the current R6 status above. R6-G was separately authorized, verified, approved and merged by PR #35 on 2026-11-04; the C4 merge alone did not confer that authorization.

**Traversal after G0 (design gate completed 2026-10-25):** R6-A Task lifecycle and recovery, including atomic terminal `task_execution` Outcome persistence; R6-B one bounded configured-source worker; R6-C Outcome-backed deterministic read-only reassessment; R6-D minimal RAG-backed Knowledge Cores and safe, traceable retrieval; R6-E bounded Context assembly, StrategyProposer, and Task generation cost accounting (**implementation and verification complete; PR #28 merged and R6-E closed**); R6-F first experience-distillation path through the authorized learning path; R6-G integrated vertical slice, full verification, and explicit exit gate. Each slice has its own narrow scope, tests, and predecessor gate. The terminal Outcome is written atomically with terminal Task finalization in R6-A, and R6-C consumes those already-durable Outcomes; [ADR-0030](docs/decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md) §5 fixes this sequencing boundary without changing the accepted Outcome contract. Exact decisions and acceptance conditions are listed in [the R6 entry gate](docs/development/r6-entry-gate.md).

**G0 design decisions are recorded** in ADR-0025, ADR-0026, ADR-0028, ADR-0029, ADR-0030 and the [R6 entry gate](docs/development/r6-entry-gate.md). ADR-0027 remains Proposed. All G0 exit criteria are satisfied and R6-G0 is COMPLETE. The operator selected local BAAI/BGE-M3 through LM Studio's OpenAI-compatible embeddings API for R6-D on 2026-10-29; ADR-0028 records the API contract, model/revision fingerprint, readiness policy, and rebuild requirement. The generation provider/model was subsequently selected for R6-E and recorded in ADR-0031; R6-E implementation and verification are complete, and PR #28 merged on 2026-11-01.

### R6-G0 local preflight record — 2026-10-25

This is the evidence-based operational prerequisite required before R6-G0 could be declared complete. It records a documentation-only closeout: no application code, tests, migrations, schema, Docker volumes, or persistent database contents were changed, and no commit, push, merge, reset, or branch deletion was performed.

**Verified local Git state:**

- Branch: `R5-rebased`; HEAD: `f9207156533b6944d320a6adfff42963f7e1e17c`.
- HEAD is identical to `origin/main` (`f920715`); no divergence and no local-only commits (`git rev-list --left-right --count origin/main...HEAD` → `0 0`).
- The preflight checks were completed while the working tree was clean. The closeout itself introduces six intentional, unstaged documentation modifications (`PLAN.md`, `docs/development/r6-entry-gate.md`, `docs/development/r6-g0-decision-proposals.md`, `CHANGE_MAP.md`, `CONTEXT.md`, `docs/control-model.md`). The working tree is therefore **not** clean at the end of this closeout; nothing is staged, committed, or pushed.

**Migrations (source-only inspection; no database commands were run during this closeout):**

- Source migration chain is a single lineage ending at `0008_plan_lifecycle_state`, preceded by `0001` → `0007` in order.
- The recorded preflight ran `uv run alembic upgrade head`, `uv run alembic current`, and `uv run alembic heads` against the isolated disposable database `watch_r6_preflight`, reporting `0008_plan_lifecycle_state (head)` and exactly one head.

**Recorded preflight verification results (not rerun during this documentation-only closeout):**

- `DATABASE_URL` and `TEST_DATABASE_URL` were verified to target `watch_r6_preflight` on `127.0.0.1:55448`; the persistent `watch` database was never targeted.
- `uv run pytest` → **260 passed** in 25.88 seconds.
- `uv run ruff check core tests migrations` → passed.
- `uv run mypy core` → passed, 11 source files.
- `git diff --check` → clean.

**G0 exit criteria disposition:** every item in the §6 checklist of the [R6 entry gate](docs/development/r6-entry-gate.md) is satisfied — the design-decision items are recorded in the accepted ADRs, and the previously unchecked operational item (verified local branch, HEAD, merge status, worktree, migrations, and disposable PostgreSQL database) is satisfied by this record. **R6-G0 status: COMPLETE.**

**Boundary retained:** this closeout records the G0 gate only; it did not start R6-A, accept ADR-0027, or weaken any R5 constraint. At the time of this G0 closeout, provider selection was pending. Those provider prerequisites were subsequently satisfied: R6-D's embedding choice is recorded in ADR-0028, and R6-E's generation provider/model choice is recorded in ADR-0031. R6-A was authorized separately afterwards and is implemented end to end; R6-E was separately authorized, implemented, and verified, with formal phase closeout pending PR #28 merge.

## R7 — Knowledge quality evaluation and lifecycle

### R7-0 — Architecture and entry gate

R7-0 is complete. ADR-0032 was accepted on 2026-11-04 and its INV-12 amendment is active in docs/invariants.md.

### R7-A — Evidence lineage and knowledge-quality assessment — COMPLETE

PR [#39](https://github.com/abtn/Watch-Architecture-Rev2/pull/39) merged on 2026-11-04 at 75122a7b34c15e2445b81a2a719020667b55bf06. Tested PR head 47ffa532dacbc10b146ac7b0768302761a2a0b1b has the same tree as the merge commit. It adds deterministic related/independent/unknown lineage classification, immutable KnowledgeQualityAssessment and migration 0014, the narrow assess_knowledge_quality Task, and the assessment guard for accepted KnowledgeItem creates.

**Verification:** hosted exact-head CI [41844600681](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41844600681) passed. Operator-local verification on the same tree passed fresh disposable-PostgreSQL migration to the single 0014_knowledge_quality head, Ruff, Mypy (31 source files), and 631 tests in 79.22s. The committed runner restored both database environment variables and removed its temporary container. Full evidence is in docs/testing.md. No production evaluator provider was selected.

### R7-B — Canonical KnowledgeItem lifecycle — B0 COMPLETE; B1 MERGED; B2 CLOSED WITH ACCEPTED RESIDUALS; B3.2–B3.5 IMPLEMENTED AND MERGED; B3.6+ GATED

**Status:** B0 was merged by PR #41 on 2026-11-05 at `64d5fb19be541d80b3cb8941ce3359d4b69565c1`. B1 was separately authorized on 2026-11-05, accepted on 2026-11-06, and merged by PR [#43](https://github.com/abtn/Watch-Architecture-Rev2/pull/43) on 2026-11-06 at `d1a8b88fd930207142304fc9b0b7274de5de4992`. The migration rejects create roots unless `version = 1`, `status = active`, and JSON `last_validated_at = null`; live history validation rejects reciprocal predecessor links unless the predecessor is `retired`. Operator-local verification passed at code head `ca498ecd43207e72082332c803a74eb30173d41c` with disposable PostgreSQL migration to `0015_r7b_history`, 33 focused migration tests, Ruff, Mypy (32 files), and 690 full-suite tests. Final PR-head hosted CI [run 42246346103](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42246346103) passed on `a7c6d4a7de5529ea9fb4faff5c9ab17bbbc51fd8`: fresh PostgreSQL migration/single-head checks, Ruff, Mypy (32 files), 690 tests, and cleanup. Full evidence is in `docs/testing.md`.

B3.5 implementation was merged by PR #66 at `a6cc81c2aef47d659252b89421e27b08735d944b` after hosted and Operator-local exact-PR-head verification; B3.6–B3.9 remain separately gated.



**Accepted B0 decisions:**
- Confidence participates in semantic content identity. A confidence-only revise changes content hash/version and clears `last_validated_at`; revalidation preserves confidence, version, and hash.
- Verified re-examination of existing canonical evidence may qualify only while temporally relevant and source-valid. Time-sensitive/current-condition claims, expired/changed sources, or material newer/contradictory evidence require new observations.
- The trusted host-supplied Operator issuer/subject remains in the immutable approval-request fingerprint and decision record; the R7 fingerprint binds the complete target/evidence/assessment/policy/successor contract.
- Snapshot separator: `watch.r7b.knowledge-item-state.v1`. Content separator: `watch.r7b.knowledge-content.v2`.
- D5 candidate guards, abandonment/replacement rules, all edge cases, fresh supersession from a `needs_review` predecessor under operation-specific guards, reciprocal publication gating, and Team-scoped graph locking are accepted.

Snapshot-first history reconstruction is conditionally accepted, subject to B1 proof from immutable snapshots, the validated current pointer, and the D7 overlay. If proof fails, stop and seek a separate Operator decision on the smallest append-only history record.

**B0 — Design freeze (documentation only):** complete cross-document integration, cross-reference and authority checks, and the documentation-only PR. No source, schema, migration, test, runtime, provider, active Task-scope or Task-registration changes.

**B1 — Schema and reconstruction proof:** add/backfill the current LearningChange pointer and both supersession links; update both LearningChange operation/target constraints; roll out create-pointer writes atomically; add the legacy snapshot decoder and D7-overlay-aware history validator. Stop if reconstruction cannot be proven; propose the smallest append-only history record rather than adding one unilaterally.

**B2 — Hash and canonicality consumers:** introduce the versioned content-hash scheme and controlled stale/republish transition; update canonicality checks, projections and Context manifest v3 while preserving v1/v2 replay; exercise only the create operation.

**B3 — Assessments:** implement immutable KnowledgeRevalidationAssessment and KnowledgeLifecycleAssessment with narrow assessment Tasks. No production evaluator provider or model scoring for lifecycle assessments.

**B4 — Revise/revalidate:** extend the single LearningChange/trusted Operator/TaskRuntime commit path with exact pointer/version compare-and-set, status-preserving revise, and evidence-bound revalidation.

**B5 — Supersede/retire/candidate creation:** implement create-with-supersedes_item_id, the D7-aware reciprocal publication gate, abandoned-candidate rules and Team-scoped graph lock. The predecessor and candidate must never both be exposed.

**B6 — Legacy compatibility and hardening:** repeated review/revalidation history, legacy Events/snapshots, approval replay after later transitions, unauthorized drift rejection and full regression verification.

B3.5 TaskRuntime/recovery/Event integration is implemented and merged; B3.6–B3.9 remain separately gated pending their own authorization.

### R7-C — Retrieval quality and downstream-use evaluation — NOT AUTHORIZED

R7-C remains separately gated: retrieval benchmark, label provenance/small-n reporting, application-written per-claim TaskKnowledgeReference, typed KnowledgeUseAssessment, and later-Task outcome evaluation without causal overclaiming. No R7-C implementation is authorized by R7-A completion or R7-B planning.

## R8 — Multi-domain pressure test (future)

Exercise the same Control layer across newsroom, development-team, and generalist settings while domain-specific knowledge remains outside the Kernel.

## R9 — Agent-assisted production workflow (future)

Codify bounded task packets, test-first changes, architecture reviews, verification evidence, and human approval boundaries.

## Deferred cross-cutting work (not part of R5-A or R5-B)

### Execution security and complete spend accounting

Before expanding beyond tightly bounded workers, define and enforce each worker's allowed filesystem, network, and tool surface; keep secrets out of worker contexts; and isolate execution. Before claiming monetary or token-cost limits, account for all relevant model and tool spend, including failed calls and retries, and test the completeness of that accounting. The current bounded ingestion capability with zero tools and zero cost does not require a general cost-accounting framework or recursive harness.

### Broader experience library beyond the initial R6 slice

The first bounded Domain Knowledge Core, Team Experience Core, and controlled distillation/retrieval loop are now part of the proposed R6 target. A broad, multi-domain experience library and more advanced transfer learning remain later work. Retain abstractions only with an identified situation, supporting evidence, applicability boundaries, known limitations, counterexamples where available, and a reason they may transfer. Do not store arbitrary reflections as durable knowledge or implement recursive self-improvement inside the Kernel or Plan materialization layer.

## Change rule

Update this file whenever milestone status or its gate changes. Other documents should link here instead of duplicating a separate current-status table. Changes to the architecture contract require the applicable spec/ADR and `CHANGE_MAP.md` updates as well.
