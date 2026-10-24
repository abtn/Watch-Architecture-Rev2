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

Both `DATABASE_URL` and `TEST_DATABASE_URL` targeted the disposable `watch_r5b_fresh` database, not the persistent `watch` database. This follow-up verified upgrade from `0007` to `0008`; a fresh full-chain installation through `0008` and an `0008 → 0007 → 0008` round trip were not rerun. The results are programmer-reported local verification, not an independent rerun from this documentation update.

**Unresolved dependency, distinct from the tested behavior above.** No component in the current codebase moves a Task to `done`; `docs/architecture.md` §4 assigns the `running → done` transition to the worker/execution path, which this repository does not implement. The completion-precondition tests therefore exercise durable Task/Event state prepared for the test. Preparing that state is not a delivered capability, and these tests do not demonstrate an end-to-end executable Plan completion. `PLAN.md` records this dependency and its effect on the R5 gate.

## R5-A failure-oriented verification

In addition to success-path tests, assert that reconstruction and failed operations do not create or preserve a falsely valid state. Cover missing required Plan Actions, Tasks, mappings, provenance, or Events; inconsistent Action/Task references; and altered identity/hash data where those records are part of the contract. Invalid durable state must fail explicitly rather than be fabricated, silently repaired, or accepted.

For atomic operations, inject or simulate failures at meaningful persistence boundaries and verify that no partial Plan, Action mapping, Task transition, quota consumption, or required Event remains committed. Run concurrency and locking behavior against disposable PostgreSQL, not a substitute database whose locking semantics differ from production.

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
