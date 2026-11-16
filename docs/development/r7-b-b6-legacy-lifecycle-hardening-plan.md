# R7-B B6 — Legacy Lifecycle Hardening Delivery Plan

**Status:** COMPLETE — Operator accepted 2026-11-16; PR #124 merged.
**Code baseline:** `29c954fe8685e0a5ddb9b205277a28b1a158c57e` (B5.4 merge).
**Implementation branch base:** `2f5bba245f4440d009e5123f1689098e64350e2e` (B6 documentation-plan merge).
**Implementation branch:** `r7b-b6-legacy-lifecycle-hardening-20261115`.

## Completion record — 2026-11-16

B6 is complete. The read-only audit led to a bounded, test-only scope: prove unique pointerless legacy review reconstruction, repeated review/revalidation reconstruction, and trusted-path retirement of a post-0015 legacy-root/backfilled-pointer representation. No production defect requiring a code change, schema change, or migration was established; the accepted gap was regression-proof coverage.

- **Implementation/test head:** `485db7f91fab0a0d17e32fdbb470ee10f63fe07a`.
- **Files changed:** `tests/test_learning_history.py`, `tests/test_experience_distiller.py` only; 230 additions, no deletions.
- **Local verification:** locked dependency sync; disposable PostgreSQL migration to the single `0018_r7b_lifecycle_review_date` head; Ruff; Mypy (38 source files); full suite **1,002 passed, 113 Alembic `path_separator` deprecation warnings in 356.84s**; container cleanup, environment restoration, exact-HEAD and clean-worktree checks all passed.
- **Hosted CI:** [run #1218](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43733711342) passed on the exact implementation/test head.
- **Operator acceptance:** granted 2026-11-16.
- **Merge:** PR [#124](https://github.com/abtn/Watch-Architecture-Rev2/pull/124) merged at `419312bc678901e2d22179313e6285086bee42da` using a merge commit. Local `main` was fast-forwarded to this exact SHA and verified clean.

The 0014 → 0015 migration remains covered by the existing populated migration tests. The trusted-path retirement integration test simulates the post-migration row representation; it does not itself execute that migration. R7-C and R8 were not part of B6. The next planned track is RW-0, subject to its existing decision/authorization boundaries.


## Goal

Finish B6 as a short, tightly controlled legacy-lifecycle hardening track: minimal production changes, the smallest useful regression set, and one final verification cycle.

B6 has no established sub-milestones or detailed acceptance criteria yet. Do not invent requirements. Define scope from a read-only audit of the actual implementation, history, and tests.

## Phase 0 — Establish baseline

1. Verify repository root, current branch, HEAD, origin, and clean worktree.
2. Verify the B5.4 code baseline `29c954fe8685e0a5ddb9b205277a28b1a158c57e` and reconcile the B6 planning-document merge `2f5bba245f4440d009e5123f1689098e64350e2e`; the implementation branch was created from the latter, which contains the former. If either relationship differs, stop and reconcile the expected baseline; do not silently substitute another SHA.
3. Fast-forward local `main` only after preflight passes. No reset, discard, force update, or automatic stash.
4. Confirm Python environment, Alembic current/head, and migration consistency.
5. Record the exact baseline SHA and environment.

**Exit:** local `main` is at the verified B6 planning baseline `2f5bba245f4440d009e5123f1689098e64350e2e` (with the B5.4 code baseline as its ancestor); worktree is clean; environment and migration baseline are recorded.

## Phase 1 — Read-only B6 audit

Audit without changing production code, tests, migrations, or project status:

- Lifecycle implementation and legacy compatibility paths.
- Old state transitions and their current validity.
- Replay and idempotency behavior.
- Interrupted execution and recovery.
- Current-pointer, history reconstruction, review, and retrieval-eligibility interactions.
- Existing tests and their actual coverage.
- Missing regressions and demonstrated defects.
- F8: determine whether any KnowledgeItems remain rooted in legacy snapshots after the B1 backfill, and whether such items can be retired through the current path.

Produce a concise findings table:

| Behavior / invariant | Evidence in code, data contract, or test | Demonstrated defect or coverage gap | Smallest correction, if needed | Regression proof | Scope risk |
|---|---|---|---|---|---|

Distinguish confirmed defects from hypotheses. F8 is an open question until migration/data evidence establishes whether affected items exist.

**Exit:** explicit proposed B6 scope and acceptance checklist, each item tied to a demonstrated defect or missing regression proof. No production changes during the audit.

## Phase 2 — Freeze scope

After the audit is reviewed:

1. Create one branch from the verified baseline: `r7b-b6-legacy-lifecycle-hardening-20261115`.
2. Record permitted files and behavior changes.
3. Name required regression tests and unchanged behavior.
4. Decide whether a migration is necessary; default to no migration unless the audit demonstrates an integrity requirement.
5. Record explicit exclusions and scope risks.

**Exit:** one approved B6 implementation contract. The audit itself does not authorize implementation.

## Phase 3 — Implement in small checkpoints

For each confirmed defect or accepted proof gap:

1. Add or complete the focused regression test.
2. Verify that the test exposes the defect or missing guarantee.
3. Apply the smallest correction.
4. Run the focused test.
5. Review the complete diff and confirm no unrelated changes.

Prefer targeted fixes and tests over new abstractions.

**Exit:** every approved B6 requirement has a passing regression proof.

## Phase 4 — Integrated lifecycle verification

Run combined lifecycle coverage against:

- B4 / G1–G6 guarantees.
- B5 candidate lifecycle, including supersession and retirement.
- B5.4 integrated lifecycle sequences.
- Approval replay after later transitions.
- TaskRuntime admission and completion.
- History reconstruction and retrieval eligibility.
- Additional B6 cases accepted from the Phase 1 audit.

Do not weaken accepted behavior to make legacy cases pass.

**Exit:** existing guarantees remain intact and every newly accepted B6 proof passes.

## Phase 5 — Final local verification

Run against the exact implementation HEAD:

- Focused B6 tests.
- Relevant integrated lifecycle tests.
- Full test suite.
- Ruff.
- Mypy.
- Alembic heads and migration consistency.
- Disposable PostgreSQL verification if required by the changed paths.

Use disposable PostgreSQL only, with a unique container and dynamic host port. Preserve and restore `DATABASE_URL` and `TEST_DATABASE_URL`; clean up only the container created by the run. Record the exact tested SHA and all results.

**Exit:** all required local checks pass, cleanup and environment restoration are verified, and the exact tested SHA is recorded.

## Phase 6 — Hosted verification and review

1. Open or update the single B6 pull request.
2. Run hosted CI on the exact final implementation head.
3. Review the complete diff against the frozen B6 contract.
4. Reconcile `PLAN.md`, `README.md`, `CHANGE_MAP.md`, and relevant implementation/testing records.
5. Report remaining defects explicitly.
6. Record both the verified code/test SHA and the current documentation-inclusive PR head. If they differ, CI must cover the final head or the unverified state must be stated.

**Exit:** hosted CI is green on the exact final head; scope review passes; no unresolved critical findings are hidden.

## Phase 7 — Acceptance and squash merge

1. Present the accepted checklist and evidence.
2. Obtain explicit Operator acceptance.
3. Squash-merge only after acceptance.
4. Verify the merge SHA and that `main` points to it.
5. Sync the local repository without destructive Git operations.
6. Record B6 completion and remaining limitations in `PLAN.md` and `docs/testing.md`.

**Exit:** B6 is accepted, merged, verified, and documented. Green CI alone is not completion.

## Two coordinated tracks

**Agent coding track:** read-only audit → proposed scope/acceptance → authorized implementation and regression tests → PR/CI/diff/docs.

**Programmer track:** sync and verify `main` → confirm environment and migrations → run focused/full local tests at the final SHA → verify cleanup and report results.

The tracks may overlap after the audit and branch setup. Local verification must use the final implementation SHA.

## Deliberately avoid

- Combining B6 with R7-C.
- Reopening B5.4 without a demonstrated defect.
- Adding migrations before the audit proves they are necessary.
- Broad lifecycle refactoring.
- Repeating already-passing tests at every checkpoint.
- Separate PRs for closely related tiny fixes.
- Weakening acceptance criteria to protect a date.

## Historical first action

Phase 0 baseline synchronization and verification, followed by the Phase 1 read-only audit. This was the entry sequence for the completed B6 track; it is retained as historical delivery guidance.
