# PLAN.md — Milestones and Current Gate

This file is the **single source of current milestone status**. Other documents link here rather than copying status tables. A phase is complete only when its exit criteria and formal gate are satisfied; implementation presence alone is not completion.

## Current recorded state

- **K0, K1, R0, R1, R2, R3:** recorded complete.
- **R4:** **closed 2026-10-20.** The redesigned multi-perspective Strategy implementation was verified freshly on the live repository (44 focused Strategy tests + full 185-test suite passing, Ruff, `mypy core`, disposable-DB migrations to `0006_immutable_plan_actions`); ADR-0023/ADR-0024 were accepted by explicit operator decision; the phase-boundary merge to `main` was performed. See the R4 closure record below.
- **R5: CLOSED 2026-10-24 by explicit operator decision.** **R5-A: READY (2026-10-21)** and **R5-B: READY (2026-10-24, programmer-reported verification)** are integrated into `main`. PR #2 merged the lifecycle-constraint correction (`95a1e8e`) and migration `0008_plan_lifecycle_state` at merge commit `435e88f`; PR #3 merged the preceding R5 status-alignment documentation at `9ba1072`. This formal closure record is added by the current documentation change. On the checkout at `c99858f` in `r5b-lifecycle-constraint-fix`, the disposable database upgraded from `0007_plan_lifecycle` to `0008_plan_lifecycle_state`; 38 lifecycle tests, 147 R5-A/Strategy regression tests, and 260 full-suite tests passed; Ruff, `mypy core` (11 source files), and `git diff --check` passed. A fresh full-chain migration through `0008` was not rerun; the subsequent `0008 → 0007 → 0008` downgrade/upgrade round trip succeeded on the same disposable database, but schema equivalence after that round trip was not separately compared. The end-to-end Task-completion path remains assigned to R6; the R5 completion-precondition requirements are unchanged. ADR-0027 remains `Proposed`; R5 closure does not itself authorize R6.
- **R6+:** future work; not authorized by the existence of code or proposed documents.

The supplied project ZIP has no Git metadata. Before taking repository action, verify branch, HEAD, merge status, and worktree on the actual checkout using `AGENTS.md`.

## Next actionable step

**R5 is formally closed as of 2026-10-24. No subsequent milestone is authorized by this closure.** Before beginning R6 implementation, obtain separate explicit operator authorization and scope the R6 entry gate. R6 owns the end-to-end worker/execution path that transitions Tasks to `done`; R5's durable Plan-completion preconditions remain mandatory. Keep ADR-0027 `Proposed` unless it is separately accepted.


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
| R6 | Future | First end-to-end intelligent Control loop. |
| R7 | Future | Evaluation and learning integration. |
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

The R5-A implementation and the R5-B lifecycle implementation, including the `0008_plan_lifecycle_state` database-constraint correction, have passed the recorded focused/full tests and static checks on the corrective branch. The migration upgrade from `0007` to `0008` was verified on disposable PostgreSQL. The correction is integrated into `main` by PR #2, merge commit `435e88f`. The operator formally approved R5 closure on 2026-10-24; the closure record below preserves the verification qualifications and Task-execution dependency. ADR-0027 remains `Proposed`, and R6 is not authorized.

#### Formal R5 closure record — 2026-10-24

**Decision:** The operator explicitly approved closing R5, with the Task-execution dependency retained for R6. R5 is CLOSED as of 2026-10-24. This is a milestone-gate decision, not acceptance of ADR-0027 or authorization to start R6.

**Exit-gate basis:**

- R5-A is recorded READY for Plan materialization, reconstruction, integrity, prerequisite admission, quota, atomicity, idempotency, concurrency, immutability, and provenance.
- R5-B is recorded READY for Plan lifecycle transitions, terminal-state protection, durable completion preconditions, stop/supersession rules, Event validation, reconstruction, concurrency, and rollback behavior. The database constraint correction was integrated through PR #2 (merge `435e88f`), and the documentation/closure record was integrated through PR #3 (merge `9ba1072`).
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

## R6 — First intelligent Control loop (future)

Objective → StateAssessment → StrategyProposal → accepted Plan → ordinary Tasks → existing Task execution/Kernel commit → Outcome → new StateAssessment. The system must explain why Tasks exist and resume from durable records after worker/runtime failure.

## R7 — Evaluation and learning integration (future)

Classify world, strategy, execution, evidence, and policy failures. Failure classification must not silently rewrite world memory or TeamPolicy.

## R8 — Multi-domain pressure test (future)

Exercise the same Control layer across newsroom, development-team, and generalist settings while domain-specific knowledge remains outside the Kernel.

## R9 — Agent-assisted production workflow (future)

Codify bounded task packets, test-first changes, architecture reviews, verification evidence, and human approval boundaries.

## Deferred cross-cutting work (not part of R5-A or R5-B)

### Execution security and complete spend accounting

Before expanding beyond tightly bounded workers, define and enforce each worker's allowed filesystem, network, and tool surface; keep secrets out of worker contexts; and isolate execution. Before claiming monetary or token-cost limits, account for all relevant model and tool spend, including failed calls and retries, and test the completeness of that accounting. The current bounded ingestion capability with zero tools and zero cost does not require a general cost-accounting framework or recursive harness.

### Durable experience library

A later dedicated milestone may add a bounded, domain-aware library of reusable experience. Retain a lesson only with an identified situation, supporting evidence, known limitations, and a reason it may transfer to another situation. Do not store arbitrary reflections as durable knowledge and do not implement recursive self-improvement inside the Kernel or Plan materialization layer.

## Change rule

Update this file whenever milestone status or its gate changes. Other documents should link here instead of duplicating a separate current-status table. Changes to the architecture contract require the applicable spec/ADR and `CHANGE_MAP.md` updates as well.
