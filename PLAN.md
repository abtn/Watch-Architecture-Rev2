# PLAN.md — Milestones and Current Gate

This file is the **single source of current milestone status**. Other documents link here rather than copying status tables. A phase is complete only when its exit criteria and formal gate are satisfied; implementation presence alone is not completion.

## Current recorded state

- **K0, K1, R0, R1, R2, R3:** recorded complete.
- **R4:** **closed 2026-10-20.** The redesigned multi-perspective Strategy implementation was verified freshly on the live repository (44 focused Strategy tests + full 185-test suite passing, Ruff, `mypy core`, disposable-DB migrations to `0006_immutable_plan_actions`); ADR-0023/ADR-0024 were accepted by explicit operator decision; the phase-boundary merge to `main` was performed. See the R4 closure record below.
- **R5:** in progress — explicitly authorized by the operator on 2026-10-20; entry gate recorded `READY` after R4 closure (see R5 section). ADR-0027 remains `Proposed` and is not accepted by this status.
- **R6+:** future work; not authorized by the existence of code or proposed documents.

The supplied project ZIP has no Git metadata. Before taking repository action, verify branch, HEAD, merge status, and worktree on the actual checkout using `AGENTS.md`.

## Next actionable step

Execute R5 (Plan materialization) against its exit criteria below. R4 is closed (2026-10-20) and the R5 entry gate is recorded `READY`.

1. Verify branch, HEAD, worktree, and commit history before repository action (`AGENTS.md` preflight).
2. Implement the R5 exit criteria with tests; record every check actually run and its result.
3. Obtain an explicit decision on ADR-0027 before implementing or enforcing the daily Task-start quota; it remains `Proposed`.
4. Record the R5 exit gate honestly; do not start R6.

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
| R5 | **In progress** (operator-authorized 2026-10-20; entry gate READY) | Materialize one accepted Strategy as one durable Plan and ordinary Tasks. |
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

## R5 — Plan materialization (**in progress**)

The operator explicitly authorized R5 work on 2026-10-20. R4 was closed 2026-10-20 (see the R4 closure record above).

### Entry gate — recorded 2026-10-20: READY

- R4 formally closed with fresh, agent-run verification evidence. ✓
- Explicit operator R5 authorization recorded 2026-10-20. ✓
- ADR-0027 remains `Proposed`: the daily Task-start quota feature is excluded from R5 work until an explicit decision is recorded; the READY result does not accept it.

### Intended contract

- One accepted Strategy for one Objective produces one Plan.
- Preserve the accepted Vision/Workstream/Action structure, stable identities, prerequisites, proposal/assessment provenance, budget envelope, and completion/stop conditions as immutable intent.
- Plan creation, its initial ordinary Tasks, and the creation Event commit atomically; partial materialization is not a valid durable state.
- Every intended Action maps to exactly one ordinary Task after materialization. Task may otherwise remain reactive and need no Plan.
- Plan-linked Task prerequisites are enforced in the existing Task admission path; no second runtime or separate scheduler is introduced.
- Plan lifecycle is `active → completed | stopped`; terminal states do not reopen. Stop reasons are `abandoned`, `invalidated`, and `superseded`.
- Progress is derived from durable Task state. Replanning creates a new Plan rather than mutating historical intent.
- Budget hierarchy: TeamPolicy ceiling → Plan envelope → individual Task budget.
- The creating `create_plan` Task's `policy_version` records the version used to validate creation; do not add a separate Plan policy pin without explicit authority.

### Existing implementation artifacts are not phase authorization

This ZIP already contains `core/plans.py`, Task runtime prerequisite checks, and migrations `0004_plans.py` through `0006_immutable_plan_actions.py`. Their presence did not authorize R5; the operator's explicit 2026-10-20 authorization did. Do not assume an old proposal for a `0007_plans.py` migration is still applicable; derive any schema change from the actual model and current migration head.

### Open quota-authority issue

`docs/tasks.md` describes `TeamPolicy.rules["budgets"]["max_tasks_per_day"]` as a Task-start quota, while ADR-0027 is marked `Proposed`. R5's in-progress status (2026-10-20) does not accept ADR-0027. Before implementation or enforcement is treated as authorized, obtain the explicit decision. Do not infer acceptance from the quota paragraph or its tests. The intended semantics, if accepted, distinguish daily Team-wide Task starts from `StrategyProposal.constraints.max_tasks`, which is an Action bound for one Strategy. A daily task-count quota is not a daily cost quota.

### R5 exit criteria

- One bounded Plan and its initial ordinary Tasks commit atomically.
- Accepted Strategy and historical assessment provenance are reconstructable.
- Action identity, uniqueness, retry, concurrent creation, and prerequisite admission are tested.
- Task dependencies do not create a new scheduler or mutate Task states behind the runtime.
- Completion/stopping/supersession preserve immutable intent and are reconstructed from durable Plan/Task/Event state after restart.
- All checks and the phase exit gate are recorded honestly.

## R6 — First intelligent Control loop (future)

Objective → StateAssessment → StrategyProposal → accepted Plan → ordinary Tasks → existing Task execution/Kernel commit → Outcome → new StateAssessment. The system must explain why Tasks exist and resume from durable records after worker/runtime failure.

## R7 — Evaluation and learning integration (future)

Classify world, strategy, execution, evidence, and policy failures. Failure classification must not silently rewrite world memory or TeamPolicy.

## R8 — Multi-domain pressure test (future)

Exercise the same Control layer across newsroom, development-team, and generalist settings while domain-specific knowledge remains outside the Kernel.

## R9 — Agent-assisted production workflow (future)

Codify bounded task packets, test-first changes, architecture reviews, verification evidence, and human approval boundaries.

## Change rule

Update this file whenever milestone status or its gate changes. Other documents should link here instead of duplicating a separate current-status table. Changes to the architecture contract require the applicable spec/ADR and `CHANGE_MAP.md` updates as well.
