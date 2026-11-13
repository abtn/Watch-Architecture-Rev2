# Watch — R8 Delivery Plan

**Official completion deadline: Monday, November 23, 2026**

## 1. Objective

Complete and verify the R8 three-domain pressure test without compromising Watch's architectural boundaries.

R8 must demonstrate:

- Shared Kernel and Control behavior remains consistent across domains.
- Domain-specific knowledge remains outside the shared Kernel.
- Experience can be retained, reconstructed, and reused.
- Cross-domain experience transfer respects explicit applicability boundaries.
- Poor, conflicting, irrelevant, or insufficient evidence produces safe behavior rather than unsupported decisions or writes.

The objective is to demonstrate the existing architecture under different domain conditions, not to add another architectural layer.

## 2. Baseline and dependencies — November 13

- R7-B B0–B3 are complete.
- B4.1–B4.3 are implemented and merged.
- B4.4 G1–G4 are complete and merged.
- G5 rejected-revalidation approval replay is complete and merged by PR #111 at 09cb8e6dfae078662e55631ae2f79e31fa8fb8cf; hosted CI and Operator-local focused/full verification passed.
- R7-B B0–B3 are complete; B3 is formally closed.
- B4.1–B4.3 are implemented and merged.
- B4.4 G1–G5 are complete and merged through PRs #103, #105, #107, #109, and #111.
- G6's bounded test-only regression is implemented in open PR [#113](https://github.com/abtn/Watch-Architecture-Rev2/pull/113), which is not yet merged. Latest exact PR head `44a31cb59588457cbaedc4863046795cea03ca3a` passed hosted CI run [#43394074207](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43394074207). Fresh PostgreSQL migration/single-head, Ruff, Mypy, patch-whitespace, full-test, and disposable-container cleanup workflow steps completed successfully. The available run metadata does not expose the final-head test count.
- Supplemental Operator-local full-suite verification passed on the earlier implementation head `d5b9ac9806b5af31fa337ee01cf1c9a5a7e6f6fd`: 956 passed, 113 Alembic deprecation warnings, 292.91s. The earlier 36-failure run did not reproduce; its cause remains undetermined. Local Ruff/Mypy and focused-only runs are not claimed.
- All six B4.4 regression proofs are complete. The technical closeout review passed; formal B4.4 closure remains pending documentation reconciliation, review of the reconciled exact head, and explicit Operator acceptance.

**Authority note:** This schedule records target dates, not blanket implementation permission. G6 implementation and verification are complete in open PR #113. The technical B4.4 closeout review has passed, but B4.4 remains formally open until documentation is reconciled, the reconciled exact head is verified, and the Operator explicitly accepts closure. The November 15 R8 entry gate must record a separate explicit decision; it does not automatically authorize implementation. B5, B6, and R7-C remain unauthorized.

## 3. Delivery schedule

### November 12 — G4 closure and baseline

Completed: PR #109 verified and squash-merged; hosted CI and local focused/full verification passed; disposable database cleanup and environment restoration were verified.

Result: G4 closed; main baseline 15d565956cde44a7bd3d124e0bb62d188063846f.

### November 13 — G5 closure and G6 planning

Completed:

1. Verified the exact G5 branch, commit, and clean local worktree.
2. Ran the focused G5 rejection/replay regression through disposable PostgreSQL.
3. Ran Ruff, Mypy, migration/single-head checks, patch whitespace validation, and the full suite (955 passed).
4. Verified disposable database cleanup and restoration of the original process database variables.
5. Reviewed the exact G5 test-only diff and green hosted CI on the exact PR head.
6. Squash-merged PR #111 to main at 09cb8e6dfae078662e55631ae2f79e31fa8fb8cf.
7. Merged the G6 documentation plan in PR #112, then received separate Operator authorization and opened the test-only implementation PR #113.

Expected result: G5 complete; G6 scope and execution sequence documented. Separate G6 implementation authorization was subsequently granted, and its bounded test-only proof is complete in PR #113.

### November 13–14 — G6 implementation and verification (complete; B4.4 closeout pending)

1. Synchronize to the accepted G6 planning merge commit and create a clean implementation branch from exact `main` baseline `7fea4accf2b862271f31b92287666f495b859d04`.
2. Inspect the accepted B4.0/B4.1/B4.2 contracts and map existing revise, history, projection, and retrieval tests to the G6 acceptance criteria.
3. Add the smallest deterministic regression for an accepted content-changing revise against a current needs_review item, using the trusted Operator path.
4. Verify status preservation, one pointer/version advance, changed semantic content/hash, cleared last_validated_at, and review_after derived from the pinned approval Task policy.
5. Verify reconstructed history matches the live canonical state.
6. Verify the old Team Experience projection is stale/ineligible and ordinary retrieval continues to exclude the item while it remains needs_review; do not add synchronous indexing.
7. Run focused tests, related lifecycle/retrieval suites, static checks, disposable-PostgreSQL migration/single-head checks, patch whitespace validation, and the full suite.
8. Review the exact diff and hosted CI on the exact PR head. Stop and report if a production/schema change appears necessary.

**Result:** the bounded test-only regression is implemented and verified in PR #113. Hosted CI run [#43386762345](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43386762345) passed on exact PR head `d5b9ac9806b5af31fa337ee01cf1c9a5a7e6f6fd`: fresh PostgreSQL migration/single-head, Ruff, Mypy (38 source files), patch whitespace, full suite (**956 passed, 113 warnings**), and disposable-container cleanup. Operator-local exact-head verification on `d5b9ac9806b5af31fa337ee01cf1c9a5a7e6f6fd`: fresh disposable PostgreSQL migration reached `0018_r7b_lifecycle_review_date`; the full suite, run first and alone against that fresh database, passed **956 tests with 113 Alembic `path_separator` deprecation warnings in 292.91s**. The script restored the original process `DATABASE_URL` and `TEST_DATABASE_URL`, removed only its disposable container, and confirmed the exact branch/HEAD and clean worktree. The earlier 36-failure run did not reproduce in this isolated full-suite run; its cause remains undetermined. Local Ruff/Mypy and focused-only runs are not claimed; those checks passed in hosted CI. The earlier 36-failure run did not reproduce in the isolated full-suite run; its cause remains undetermined. No production correction or unrelated scope expansion was required. G6 is complete as a regression-proof gate; B4.4 is not yet formally closed.

### November 15 — B4.4 closure and R8 entry gate

**B4.4 final verification**

1. Confirm G1–G6 regression evidence and run any remaining closeout verification required by the Operator; do not assume the historical test run is a fresh run on the reconciled documentation head.
2. Run Ruff and Mypy.
3. Verify Alembic migration consistency and the single expected head.
4. Run hosted CI on the exact final commit.
5. Review the complete source diff against the frozen B4 contracts.
6. Confirm no unauthorized scope expansion.
7. Reconcile PLAN.md, CHANGE_MAP.md, implementation documentation, and testing evidence.
8. Obtain explicit Operator acceptance of B4.4 closure.

B4.4 is not closed merely because G1–G6 tests pass; final verification and acceptance are mandatory.

**R8 entry gate**

After B4.4 is formally closed, freeze the three domain scenarios, common Control/Task path, domain-knowledge boundaries, experience retention/reuse requirements, cross-domain transfer restrictions, failure/abstention behavior, required evidence, exclusions, and dependencies. Record explicit R8 implementation authorization separately.

B5, B6, and R7-C remain excluded unless an actual R8 blocker is identified and separately authorized.

### November 16 — Domain 1: Newsroom

Establish newsroom-specific knowledge and vocabulary; exercise signal/evidence interpretation; run through shared Control and Task infrastructure; retain and reconstruct a useful experience; test insufficient or conflicting evidence.

Expected result: newsroom scenario operational, with domain knowledge outside the Kernel.

### November 17 — Domain 2: Development team

Exercise software-development evidence and task interpretation through the same shared Control/Task infrastructure; retain and reconstruct a useful development experience; test poor or contradictory evidence.

Expected result: development-team scenario operational without domain-specific Kernel changes.

### November 18 — Domain 3: Generalist

Exercise a generalist scenario without newsroom or development assumptions; use shared Control/Task execution; retain and reconstruct a useful experience; test insufficient context and irrelevant prior experience.

Expected result: generalist scenario operational without specialized domain assumptions.

### November 19 — Cross-domain integration

Run all three scenarios against the same shared architecture. Compare Control behavior and execution boundaries. Verify consistent lifecycle/authority rules, domain knowledge separation, and that one domain's experience does not silently become another domain's knowledge.

Expected result: shared Control invariance and knowledge separation demonstrated.

### November 20 — Experience retention and safe transfer

Reconstruct experience in each domain; verify relevant reuse and rejection of irrelevant experience; test cross-domain applicability; require evidence and validation before transfer; verify invalid transfer cannot produce unsupported canonical writes and does not corrupt original experience.

Expected result: retention, reuse, and transfer boundaries verified.

### November 21 — Failure and regression

Test insufficient context, poor evidence, conflicting evidence, irrelevant experience, invalid cross-domain transfer, stale/inconsistent knowledge, repeated/replayed operations, and supported execution/recovery failures.

For each applicable case, verify no invented evidence, no invalid canonical writes, no duplicate side effects, no corruption of valid experience, intact Control/write boundaries, and observable failure.

Expected result: failure behavior and regression suite pass; no unresolved critical architectural defect.

### November 22 — Final review

Run full tests, Ruff, Mypy, migration checks, and exact-head hosted CI. Review all implementation diffs and all three domain scenarios. Reconcile Control invariance, knowledge separation, experience retention, transfer boundaries, failure behavior, documentation, and outstanding defects. Confirm no deferred milestone was silently pulled into scope.

Expected result: complete evidence package and readiness for acceptance.

### November 23 — R8 acceptance and closure

Acceptance requires:

- [ ] Newsroom, development-team, and generalist scenarios pass.
- [ ] Shared Control behavior is invariant across all three domains.
- [ ] Domain knowledge remains outside the shared Kernel.
- [ ] Experience is retained, reconstructed, and relevantly reused.
- [ ] Irrelevant experience is rejected.
- [ ] Cross-domain transfer respects applicability boundaries.
- [ ] Insufficient, poor, and conflicting evidence produces safe behavior.
- [ ] No unauthorized canonical writes or duplicate side effects occur.
- [ ] Full regression suite and exact-commit hosted CI pass.
- [ ] Documentation and implementation status are reconciled.
- [ ] No unresolved critical defects remain.
- [ ] Operator acceptance is recorded.

Result: R8 is formally closed only if all criteria pass; otherwise it remains open with failed criteria and delivery risk recorded.

## 4. Architectural constraints

1. No second commit path; domain capabilities use existing controlled execution and commit infrastructure.
2. Shared Kernel/Control behavior remains domain-invariant.
3. Domain-specific knowledge remains outside the Kernel.
4. Experience survives beyond the model or agent session that produced it.
5. Experience transfer is bounded by evidence and applicability.
6. Insufficient or conflicting evidence cannot become an unsupported canonical decision.
7. Add only what is necessary to satisfy a demonstrated R8 criterion.

## 5. Verification protocol

For each implementation checkpoint, verify repository root, branch, exact HEAD, origin, and clean worktree before mutation. Review the complete diff and exact commit identity. Use hosted CI on the exact commit. Use disposable PostgreSQL only, with dynamic ports; never use the persistent watch database or assume port 5432. Preserve and restore DATABASE_URL and TEST_DATABASE_URL. Remove only the disposable container created by the test. Never force synchronization or discard local work.

For longer PowerShell scripts, follow the project local sync/test guide: create a .ps1 file using a single-quoted here-string, parse it before execution, check native-command exit codes, and include explicit preflight and final verification.

## 6. Deadline protection

November 23 is the fixed target. If a blocker appears, identify the failed acceptance criterion, determine whether it is essential, reduce nonessential scope before adding architecture, keep B5/B6/R7-C outside scope unless separately authorized, and record the schedule risk. Do not declare R8 complete by weakening its acceptance criteria.
