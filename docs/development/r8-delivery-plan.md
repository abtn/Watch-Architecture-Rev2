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

## 2. Baseline and dependencies — November 12

- R7-B B0–B3 are complete.
- B4.1–B4.3 are implemented and merged.
- B4.4 G1–G4 are complete and merged. G4 PR #109 is on main at 15d565956cde44a7bd3d124e0bb62d188063846f.
- G5 rejected-revalidation replay: documentation plan authorized; implementation not authorized.
- G6 accepted revise from needs_review: outstanding; implementation not authorized.

B5, B6, and R7-C are not automatic R8 prerequisites. They remain unauthorized unless a concrete R8 acceptance blocker is identified and the Operator separately authorizes the work.

**Authority note:** This schedule records target dates, not implementation permission. G5 and G6 implementation each require separate explicit authorization. If either is not authorized and completed in time, record the schedule risk; do not claim B4.4 closure or weaken the R8 entry gate.

## 3. Delivery schedule

### November 12 — G4 closure and baseline

Completed: PR #109 verified and squash-merged; hosted CI and local focused/full verification passed; disposable database cleanup and environment restoration were verified.

Result: G4 closed; main baseline 15d565956cde44a7bd3d124e0bb62d188063846f.

### November 13 — Local synchronization and G5

1. Synchronize local main to the verified G4 merge commit.
2. Verify repository root, branch, exact HEAD, origin, clean worktree, migration head, and local environment.
3. Inspect the existing rejected-revalidation and replay paths.
4. Review and accept the G5 documentation plan.
5. Only after separate explicit Operator authorization, implement the focused G5 regression.
6. Replay the exact original rejected revalidation request and verify no duplicate Events, Outcomes, approval Tasks, or canonical writes.
7. Run focused verification and review the exact diff and hosted CI evidence.

Expected result: G5 regression evidence, with no unrelated production changes. Until separately authorized, only documentation and read-only inspection are permitted.

### November 14 — G6 and remaining B4.4 proof

Subject to separate explicit authorization:

1. Inspect the accepted revise path from needs_review.
2. Verify accepted revise preserves needs_review and does not restore retrieval eligibility.
3. Verify pointer, version, history, and date consistency.
4. Verify ordinary retrieval continues to exclude the item while review is required.
5. Run the focused G6 regression and review interactions with G4 and earlier tests.

Expected result: G6 evidence. If authorization is absent, record the blocker and schedule risk; do not proceed as if implementation were authorized.

### November 15 — B4.4 closure and R8 entry gate

**B4.4 final verification**

1. Run the complete relevant regression suite and full test suite.
2. Run Ruff and Mypy.
3. Verify Alembic migration consistency and the single expected head.
4. Run hosted CI on the exact final commit.
5. Review the complete source diff against the frozen B4 contracts.
6. Confirm no unauthorized scope expansion.
7. Reconcile PLAN.md, CHANGE_MAP.md, implementation documentation, and testing evidence.
8. Obtain explicit Operator acceptance.

B4.4 is not closed merely because G1–G6 tests pass; final verification and acceptance are mandatory.

**R8 entry gate**

Freeze the three domain scenarios, common Control/Task path, domain-knowledge boundaries, experience retention/reuse requirements, cross-domain transfer restrictions, failure/abstention behavior, required evidence, exclusions, and dependencies.

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
