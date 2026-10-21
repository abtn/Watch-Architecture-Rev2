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
