# PLAN.md — Milestones and Current Gate

This file is the **single source of current milestone status**. Other documents link here rather than copying status tables. A phase is complete only when its exit criteria and formal gate are satisfied; implementation presence alone is not completion.

## Current recorded state

- **K0, K1, R0, R1, R2, R3:** recorded complete.
- **R4:** redesigned multi-perspective Strategy implementation is recorded as present, with focused verification recorded; formal closure is pending the documented phase-boundary gate.
- **R5:** paused pending formal R4 closure and an explicit R5 entry gate.
- **R6+:** future work; not authorized by the existence of code or proposed documents.

The supplied project ZIP has no Git metadata. Before taking repository action, verify branch, HEAD, merge status, and worktree on the actual checkout using `AGENTS.md`.

## Next actionable step

Complete the R4 formal-closure gate against the live repository state. Do not begin further R5 implementation or R6 work until the gate is satisfied and R5 is explicitly authorized.

1. Verify the actual branch, HEAD, worktree, and commit history.
2. Reconcile the existing R4 implementation and recorded checks with the phase-boundary merge/closure requirements in `AGENTS.md` and the applicable ADRs.
3. Record only evidence that was actually verified; distinguish source-recorded evidence from freshly rerun commands.
4. Close R4 only through the prescribed phase-boundary process.
5. Run the R5 entry gate and record a clear `READY` or `NOT READY` result before starting R5.

## Milestone overview

| Phase | Recorded status | Purpose |
|---|---|---|
| K0 | Complete | Python/uv, PostgreSQL + pgvector, Alembic, tests, Ruff, mypy. |
| K1 | Complete | Smallest proposal → validation → atomic Kernel commit → Event path (`ingest_source`). |
| R0 | Complete | Freeze Revision 2 architecture semantics and boundaries. |
| R1 | Complete | Verify compatibility with the existing Kernel and Task/write-scope model. |
| R2 | Complete | Durable Objective model and lifecycle. |
| R3 | Complete | Deterministic, read-only StateAssessment with provenance. |
| R4 | Implementation present; formal closure pending | StrategyProposal boundary, multi-Vision/Workstream/Action semantics, deterministic validation and reconstruction. |
| R5 | **Paused** | Materialize one accepted Strategy as one durable Plan and ordinary Tasks. Requires R4 closure plus explicit R5 authorization. |
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

## R4 — StrategyProposal boundary (implementation present; formal closure pending)

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

The source PLAN records the redesigned implementation at commit `50e288a` on the R5 worktree, `44` Strategy tests passing, targeted Ruff, `mypy core`, and `git diff --check` passing, and disposable PostgreSQL migrations reaching `0006_immutable_plan_actions`. It also records that the full suite and R5-specific tests were not run. These are **source-recorded results**, not fresh verification from this ZIP; verify actual Git state and rerun checks as required by the formal gate.

### R4 closure gate

Focused verification does not itself close R4. Follow the phase-boundary merge/closure procedure in `AGENTS.md`. If the actual repository differs from the recorded state, reconcile that difference before marking the phase complete.

## R5 — Plan materialization (**paused**)

Do not start until R4 is formally closed and the R5 entry gate explicitly authorizes work.

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

This ZIP already contains `core/plans.py`, Task runtime prerequisite checks, and migrations `0004_plans.py` through `0006_immutable_plan_actions.py`. Their presence does not release the R5 pause. Do not assume an old proposal for a `0007_plans.py` migration is still applicable; derive any schema change from the actual model and current migration head.

### Open quota-authority issue

`docs/tasks.md` describes `TeamPolicy.rules["budgets"]["max_tasks_per_day"]` as a Task-start quota, while ADR-0027 is marked `Proposed` and the R5 gate remains paused. Before implementation or enforcement is treated as authorized, obtain the explicit decision and gate result. Do not infer acceptance from the quota paragraph or its tests. The intended semantics, if accepted, distinguish daily Team-wide Task starts from `StrategyProposal.constraints.max_tasks`, which is an Action bound for one Strategy. A daily task-count quota is not a daily cost quota.

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
