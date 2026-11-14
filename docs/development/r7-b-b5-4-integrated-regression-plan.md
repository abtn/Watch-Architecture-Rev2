# R7-B B5.4 — Integrated Lifecycle Regression and Closeout Plan

**Status:** B5.3 is formally closed. B5.4.0 remote read-only baseline/coverage audit is complete and recorded in [the audit report](r7-b-b5-4-baseline-audit.md). Local Operator preflight remains pending. No source/test, migration, schema, model, or runtime change has been authorized; B5.4.1–B5.4.5 remain separately gated.
**Planning baseline:** `main` after B5.4 planning PR #121 squash merge `eef7815db922984c798e95ebd91d6d5c6c87e3b0`.
**Implementation baseline requirement:** The implementation branch `r7b-b5-4-implementation-20261114` was created from exact current `main` SHA `eef7815db922984c798e95ebd91d6d5c6c87e3b0` after PR #121 merged. The exact SHA and remote source/test inventory are recorded in [the B5.4.0 audit](r7-b-b5-4-baseline-audit.md). Do not branch from the earlier planning branch.
**Scope:** Integrated regression evidence for the already implemented B5.1 Create-with-successor, B5.2 Retire, and B5.3 Supersede lifecycle paths. Prefer test-only changes and existing fixtures/entry points.

## 1. Objective

Prove that the three B5 lifecycle capabilities compose correctly as complete histories, not merely as individually passing operations:

- Create-with-successor candidate.
- Retire a candidate or a KnowledgeItem.
- Supersede a predecessor with an already accepted candidate.

The work is an integration/regression and closeout phase. It must not redesign the accepted lifecycle contract or add new production architecture.

## 2. Frozen constraints

- All canonical writes continue through the existing proposal, deterministic application validation, operation-specific assessment, trusted Operator approval, canonical LearningCommit, and TaskRuntime path.
- No second lifecycle write path, new Task type/runtime, scheduler, dispatcher, authentication boundary, or autonomous approval.
- No migration or schema/model change is assumed or authorized by this plan.
- Candidate `supersedes_item_id` remains immutable; the predecessor's `superseded_by_id` is written only by accepted supersede.
- Supersede changes only the predecessor. The accepted candidate row remains unchanged.
- The predecessor and candidate must not both become retrievable; projection, ordinary retrieval, and Context continue to enforce reciprocal publication and D7 eligibility.
- Replay returns the original durable decision and must not duplicate Events, Outcomes, LearningChanges, pointer advances, or other canonical writes.
- If a production defect or missing architectural capability is found, isolate the failing criterion and stop for Operator review. This planning PR does not authorize production corrections, schema changes, or scope expansion.
- B5.4 is not an automatic R8 prerequisite. B6 and R7-C remain outside this plan.

## 3. Implementation sequence

### B5.4.0 — Baseline and coverage audit

1. Start from the exact current verified `main` commit after planning PR #121 is merged. The Operator's 2026-11-14 authorization covers this B5.4.0 audit only.
2. Verify repository, branch, origin, exact HEAD, clean worktree, migration head, and test database configuration.
3. Read the accepted B5 plan, B0/B4 lifecycle invariants, and the B5.1–B5.3 closeout evidence.
4. Inventory existing tests and fixtures for create, review, revise, revalidate, create-with-successor, supersede, retirement, history reconstruction, retrieval, Context, and approval replay.
5. Build a coverage matrix mapping each required scenario below to existing tests and identify only the missing integration assertions.
6. Confirm whether the required proof can be completed in tests without production changes. If not, stop and report the exact blocker.

**Deliverable:** Completed in [the B5.4.0 baseline/coverage audit](r7-b-b5-4-baseline-audit.md). It identifies two bounded test-only gaps and one create-with-successor replay interpretation point. No production or architectural gap was found by the remote inventory.

**Exit:** Remote exact baseline and source/test inventory verified. Local Operator worktree/database preflight remains pending. No source/test change is proposed without separate checkpoint authorization.

### B5.4.1 — Complete lifecycle sequence

Exercise the complete path through the existing trusted application entry points:

`create → review → revise → revalidate → create-with-successor → supersede`

Verify after each transition:
- The expected Task, LearningChange, Outcome, and Event records are attributable to the operation.
- Current pointer, version, semantic content/hash, lifecycle status, and immutable history advance exactly as specified.
- Review and revalidation use the existing assessment and trusted approval boundaries.
- Candidate creation binds the exact predecessor and does not prematurely publish the candidate.
- Supersede atomically retires/links only the predecessor; the accepted candidate's row and immutable predecessor link remain unchanged.
- The predecessor is excluded and the candidate is visible only after reciprocal canonical state and D7 eligibility permit it.
- Ordinary retrieval and Context agree with the canonical relationship.

**Exit:** One integrated test or a minimal cohesive set of tests proves the whole chain and its durable history without hand-fabricating canonical rows.

### B5.4.2 — Candidate cancellation and replacement branch

Exercise:

`create-with-successor → retire candidate → create replacement candidate`

Verify:
- Retiring the pending candidate is a canonical, trusted retirement and does not retire or mutate the predecessor.
- The retired candidate remains terminal and its immutable `supersedes_item_id` is preserved.
- Candidate retirement frees the single-pending-candidate slot.
- A replacement candidate can be proposed for the same predecessor and is bound to the correct Team, predecessor pointer/version/hash, and immutable relationship.
- No stale or retired candidate is published; no predecessor reciprocal successor pointer is written before accepted supersede.
- History reconstruction shows both the retired candidate and replacement candidate accurately.

**Exit:** Candidate cancellation/replacement works without cascade, stale graph state, or dual publication.

### B5.4.3 — Terminal no-successor branch

Exercise:

`create → retire`

Verify:
- The trusted retirement path creates the expected immutable lifecycle records and advances the current pointer exactly once.
- The item becomes terminally retired with no successor link.
- No candidate, successor pointer, or supersede decision is fabricated.
- Retrieval and Context exclude the retired item.
- History reconstruction preserves the create and retire sequence.

**Exit:** Ordinary retirement remains correct as a terminal path independent of candidate/supersede behavior.

### B5.4.4 — Cross-transition approval replay matrix

Replay the original accepted approvals after later lifecycle transitions for:
- Create.
- Revise.
- Revalidate.
- Retire.
- Supersede.

For each replay, verify:
- The original Task, LearningChange, decision, Operator attribution, commit timestamp, and Outcome identity are returned.
- The original disposition is preserved even when the target has since moved through later history.
- No duplicate request/decision/terminal Events, Outcomes, LearningChanges, snapshots, or canonical pointer writes occur.
- Conflicting reuse of an idempotency identity with a different operation, target, or immutable binding is rejected.
- Replay reconstructs current history without overwriting later state or fabricating records.

Reuse existing focused replay proofs where they already establish the exact invariant; add only the missing cross-transition integration assertions.

**Exit:** Every lifecycle approval remains idempotent and historically stable after later operations.

### B5.4.5 — Integrated verification and closeout

1. Run the focused B5.4 tests.
2. Run the B5.1, B5.2, and B5.3 lifecycle regressions, then the relevant R7-B regression set.
3. Run the full suite against a fresh disposable PostgreSQL database; verify migrations and exactly one Alembic head.
4. Run Ruff, Mypy, and `git diff --check`.
5. Verify disposable-container cleanup, restoration of `DATABASE_URL` and `TEST_DATABASE_URL`, exact branch/HEAD, and clean worktree.
6. Review the complete diff for lifecycle invariants, lock order, canonical-only writes, replay semantics, retrieval/Context parity, and scope.
7. Require hosted CI to pass on the exact final PR head.
8. Reconcile `PLAN.md`, README, CHANGE_MAP, this plan, and `docs/testing.md`.
9. Obtain explicit Operator technical acceptance.

**Exit:** Complete lifecycle branches, durable history, consumer eligibility, and replay pass exact-head hosted/local verification; no unauthorized scope expansion remains; documentation agrees with evidence; and the Operator explicitly accepts B5.4.

## 4. Acceptance matrix

| Scenario | Required proof |
|---|---|
| Full lifecycle | Create → review → revise → revalidate → create-with-successor → supersede |
| Candidate replacement | Retire pending candidate, then create a replacement for the same predecessor |
| Terminal retirement | Create → retire, with no successor |
| Approval replay | Original create/revise/revalidate/retire/supersede approvals replay after later transitions |
| Side-effect uniqueness | No duplicate Events, Outcomes, LearningChanges, snapshots, or pointer advances |
| History | Exact current pointers and immutable lifecycle snapshots reconstruct |
| Publication | Projection, ordinary retrieval, and Context agree on reciprocal links and D7 eligibility |
| Architecture | Existing trusted approval and canonical commit path only; no second write path |
| Verification | Fresh disposable PostgreSQL, one Alembic head, Ruff, Mypy, full suite, exact-head CI |
| Scope | No migration/schema/runtime/dispatcher/scheduler/authentication or R7-C/B6 expansion without separate authorization |

## 5. Stop conditions

Stop and return to the Operator if:
- Any accepted B0/B4 invariant must change.
- A migration, schema/model change, or new runtime/dispatcher/scheduler/authentication boundary appears necessary.
- Any lifecycle operation bypasses trusted Operator approval or canonical LearningCommit.
- Candidate cancellation mutates the predecessor or creates a successor pointer.
- Supersede mutates the accepted candidate.
- Predecessor and candidate can both be published.
- A stale proposal/assessment can commit.
- Replay duplicates durable side effects or overwrites later history.
- The complete proof cannot be built from existing paths without production changes.

Do not weaken an acceptance criterion to preserve schedule.

## 6. Authorization boundary

The Operator explicitly authorized B5.4.0 on 2026-11-14. The remote implementation branch and read-only audit are complete; see [the B5.4.0 audit](r7-b-b5-4-baseline-audit.md). Local Operator preflight remains pending. This authorization did not permit source/test, migration, schema, model, or runtime changes. B5.4.1–B5.4.5 remain gated and require separate checkpoint decisions. If later implementation work demonstrates a production defect or architecture change is necessary, stop and return for authorization.

B5.3 is formally closed by the Operator's explicit instruction to close and squash-merge PR #120. The B5.4.0 audit does not make B5.4 an automatic R8 prerequisite. B6 and R7-C remain unauthorized. R8 remains governed by its separate entry gate and delivery plan.
