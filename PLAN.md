# PLAN.md — Milestones and Current Gate

This file is the **single source of current milestone status**. Other documents link here rather than copying status tables. A phase is complete only when its exit criteria and formal gate are satisfied; implementation presence alone is not completion.

## Current recorded state

- **K0, K1, R0, R1, R2, R3:** recorded complete.
- **R4:** **closed 2026-10-20.** The redesigned multi-perspective Strategy implementation was verified freshly on the live repository (44 focused Strategy tests + full 185-test suite passing, Ruff, `mypy core`, disposable-DB migrations to `0006_immutable_plan_actions`); ADR-0023/ADR-0024 were accepted by explicit operator decision; the phase-boundary merge to `main` was performed. See the R4 closure record below.
- **R5:** in progress; R5-A implementation and test scope reported `READY` by the agent on 2026-10-21, pending integration of its uncommitted code changes and formal gate recording. R5-B lifecycle behavior remains required. ADR-0027 remains `Proposed`; the R5-A report is not formal ADR acceptance or overall R5 closure.
- **R6+:** future work; not authorized by the existence of code or proposed documents.

The supplied project ZIP has no Git metadata. Before taking repository action, verify branch, HEAD, merge status, and worktree on the actual checkout using `AGENTS.md`.

## Next actionable step

**Next: consolidate and close the R5-A implementation record, then execute R5-B.** The R5-A agent report dated 2026-10-21 says implementation and verification passed, but its code changes remain uncommitted in the local worktree. Treat the report as evidence to preserve and review, not proof that the implementation is already consolidated with the updated documentation.

1. Preserve and review the reported R5-A code diff; ensure the new `core/policy.py` and the four modified files are present on `R5-rebased` with no unrelated changes.
2. Integrate the R5-A/R5-B documentation updates already recorded on the remote `R5-rebased` branch without overwriting local code changes.
3. Confirm the reported focused/full verification against the final consolidated tree, then record the R5-A gate based on that branch state.
4. Execute R5-B Plan lifecycle behavior against the acceptance criteria below.
5. Close R5 only when both slices and all overall R5 exit criteria pass. Do not start R6 before formal R5 closure.
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

## R5 — Plan materialization and lifecycle (**in progress**)

R5 is deliberately divided into two implementation slices. This split changes the delivery sequence, not the overall R5 contract or exit criteria. **R5 is not complete until both R5-A and R5-B are implemented and verified.**

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

### R5-A implementation verification report — 2026-10-21 (agent-reported)

The agent reported the following results after reproducing five defects and correcting the implementation. This is a record of that report; this documentation update did not independently rerun the commands.

- Shared quota parsing was added in `core/policy.py` and adopted by PlanService and TaskRuntime, resolving disagreement for zero and non-integer values and handling malformed policy structure.
- Plan materialization now serializes use of an accepted Strategy Event, rejects already-materialized proposals with a stable category, and handles corrupt prior creation Events through a categorized failure path.
- Regression coverage was added for incomplete/corrupt Plan state, accepted-provenance tampering, conflicting and concurrent materialization, policy rejection reasons, pending Tasks not counting as starts, zero/invalid quota values, UTC-day boundaries, and Team scoping.
- Agent-reported checks: focused Strategy/Plan/TaskRuntime tests **147 passed**; full test suite **222 passed** on two disposable database runs; Ruff passed; mypy passed across 11 source files; migrations reached `0006_immutable_plan_actions` on a fresh disposable PostgreSQL database; `git diff --check` was clean.
- The agent reported that code changes remain uncommitted locally (four modified files and new `core/policy.py`) and that its local HEAD remained `7af449d`. Therefore, this is **R5-A implementation-ready evidence**, not proof that implementation and documentation are already consolidated into one branch commit.

**R5-A can be formally recorded READY after its code changes and the R5-A/R5-B documentation are present together on the working branch and the final diff/verification evidence is confirmed. R5-A passing does not close R5.**

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
