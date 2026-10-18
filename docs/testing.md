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
| Plan | Accepted structure/provenance is preserved; creation is atomic/idempotent; Action identity and uniqueness hold; dependency admission uses the existing Task runtime; immutable intent survives restart. |
| Daily quota, if formally authorized | Below-limit success; exhausted rejection without partial changes; successful retry consumes another start; concurrent claims for the final unit serialize; absent quota preserves no-limit behavior. Follow the ADR/gate authority before implementing this case. |

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
