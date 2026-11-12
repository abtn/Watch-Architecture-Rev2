# R7-B B4.4 G4 — Same-item revise → revalidate sequence plan

**Status: DOCUMENTATION PLAN ONLY — G4 scope authorized on 2026-11-12; implementation not started.**  
**Base:** G3 closeout merge commit `647526c44d26e61069c23ddd2bc4ceaf2c15b713`.  
**Parent gate:** B4.4. G1, G2, and G3 are complete; G4 is the next bounded regression proof. G5 and G6 remain unauthorized.

## 1. Purpose

Add one integrated regression proving that the existing B4 revise and revalidate operations work sequentially against the **same canonical KnowledgeItem**, with the second operation assessed against the exact state produced by the first.

The missing evidence is not that revise and revalidate work independently. Existing tests cover those paths separately. G4 must prove the boundary between them: a revalidation proposal/assessment bound before a revise cannot be reused after the revise changes the item's current pointer and content version; a fresh revalidation assessment against the revised state can then be accepted.

This is a regression-proof task, not a request to redesign the lifecycle.

## 2. Frozen contracts to exercise

Use the accepted B4.0 architecture decision, ADR-0032, the B4 implementation plan, and the existing services as authorities. Do not redefine their behavior.

- Revise may target an `active` or `needs_review` item. It preserves the target's status; revise never reactivates an item.
- A content-changing revise advances the current LearningChange pointer and content version, changes the semantic content hash, and clears `last_validated_at`. Review scheduling follows the pinned approval Task policy.
- Revalidation is a separate operation with a separate immutable `KnowledgeRevalidationAssessment`. It is permitted only for a current `needs_review` item and must bind the exact current pointer, content version, content hash, full-state snapshot, and valid evidence basis.
- Revalidation preserves semantic content, confidence, content version, and content hash; it changes only the lifecycle/validation metadata required by the accepted contract, advances the current LearningChange pointer, and transitions `needs_review → active`.
- A pointer advance immediately makes the prior Team Experience projection ineligible. Revalidation does not make the item retrievable until the existing indexer republishes against the new current pointer and state.
- `reconstruct_knowledge_item_history` remains the single history authority. The D7 `active → needs_review` review Event is an overlay and does not itself advance the LearningChange pointer.
- The trusted Operator approval path and existing TaskRuntime remain the only canonical commit and Task-lifecycle authorities.

## 3. Required sequence

Use one Team and one KnowledgeItem throughout. Use the existing proposal, assessment, approval, history, and projection helpers; do not fabricate canonical rows or bypass the trusted Operator adapter.

1. **Establish the item and review state.** Create the KnowledgeItem through the existing canonical create path. Move it to `needs_review` through the existing D7 review path (or use an equivalent existing fixture setup only if the test still proves the real transition contract). Capture the exact canonical state and current LearningChange pointer.
2. **Capture a pre-revise revalidation binding.** Build a valid revalidation proposal and immutable revalidation assessment against the current `needs_review` state. Retain the original proposal/assessment identifiers and the pointer, version, hash, and snapshot they bind. Do not approve it yet.
3. **Revise the same item.** Propose, assess, and accept a content-changing revise through the trusted Operator path. The revise must target the same item while it is `needs_review`. Verify that the item remains `needs_review`, the current pointer and content version advance, the semantic content hash changes, and `last_validated_at` is cleared as required.
4. **Prove the old revalidation binding is stale.** Attempt to use the pre-revise revalidation proposal/assessment through the normal approval path. It must fail closed as stale/invalid; it must not rebase or silently refresh the assessment. Verify no revalidation LearningChange commit, pointer advance, status change, duplicate decision Event, or successful terminal Task is produced by the stale attempt. Preserve the immutable historical assessment.
5. **Create a fresh revalidation after revise.** Rebuild the revalidation proposal and assessment from the revised item's exact current state and valid current evidence. Assert the new assessment pins the post-revise pointer, version, content hash, and full-state snapshot—not the pre-revise values.
6. **Accept revalidation.** Accept through the same trusted Operator path. Verify `needs_review → active`, one pointer advance, unchanged revised semantic content/confidence/version/hash, and validation/review timestamps derived from the canonical commit time and pinned TeamPolicy.
7. **Verify reconstructed history.** Call the existing history reconstruction/validation path and prove the chain contains the create, D7 review overlay, accepted revise, and accepted revalidate in the correct order. The reconstructed final state must exactly match the live KnowledgeItem, including current pointer, version, hash, status, and validation/review dates.
8. **Verify projection eligibility.** Prove the pre-revise projection is ineligible after revise and remains ineligible after revalidation's pointer advance. Retrieval must remain empty until the ordinary Team Experience indexer republishes the revised/revalidated current state. After ordinary republish, verify the current projection pins the final pointer/hash scheme and retrieval can expose the item. Do not add a synchronous indexing shortcut.

## 4. Acceptance criteria

G4 is complete only when one deterministic regression (or a small, clearly justified set of tests) proves all of the following:

- Both accepted transitions target the same KnowledgeItem and use the existing trusted Operator/canonical commit path.
- Revise begins from `needs_review` and preserves `needs_review`; it does not reactivate the item.
- The pre-revise revalidation proposal/assessment is immutably bound to its original target state and cannot be accepted after revise changes that state.
- The stale attempt fails closed without a canonical revalidation commit, partial state, pointer movement, or terminal success.
- A fresh revalidation assessment is created only after revise and is bound to the revised current pointer/version/hash/snapshot.
- Accepted revalidation transitions the same item to `active`, advances the pointer once, and preserves the revised semantic content, confidence, content version, and content hash.
- The existing history reconstruction path validates the complete ordered sequence and matches the live canonical row.
- Old projections become ineligible immediately at each pointer transition; no retrieval occurs before ordinary republish; the republished projection is pinned to the final current state.
- Repeated request/replay where exercised does not duplicate canonical decisions, Events, Outcomes, or pointer advances.
- The regression is deterministic, uses disposable PostgreSQL in the standard test harness, and leaves fixture-owned cleanup intact.

## 5. Likely test surface

Start with these existing authorities and test surfaces; confirm exact helper names and fixture behavior during implementation rather than introducing parallel helpers:

- `tests/test_experience_distiller.py`: real proposal/assessment/Operator approval flows, revise/revalidate commits, stale binding, and lifecycle history.
- `tests/test_knowledge_quality.py` and `tests/test_knowledge_revalidation.py`: operation-specific assessment contracts and target freshness.
- `tests/test_team_experience.py`: projection invalidation, ordinary republish, and retrieval eligibility.
- `core/learning_history.py`: `reconstruct_knowledge_item_history`.
- `core/knowledge_quality.py`, `core/knowledge_revalidation.py`, and `core/learning_commit.py`: existing assessment validation and canonical commit boundaries.
- `core/knowledge_index.py`: existing Team Experience publication/retrieval path.

The implementation should first map existing tests to the acceptance criteria and add only the missing integrated sequence. Do not duplicate already-proven unit or isolated commit coverage without a reason.

## 6. Scope and exclusions

**In scope:** a bounded integrated regression for revise → stale pre-revise revalidation rejection → fresh post-revise revalidation acceptance on one KnowledgeItem, including history and projection eligibility.

**Preferred change:** tests only. A production correction is not presumed. If the regression exposes a production defect, stop and report the smallest demonstrated defect and proposed correction before widening the implementation diff.

**Out of scope:**

- G5 rejected-revalidation approval replay/idempotency proof.
- G6 accepted revise commit starting from a `needs_review` item as a separate proof gap (G4 may use revise-on-`needs_review` as a necessary part of its own integrated sequence, but must not claim G6 complete).
- B5, B6, R7-C, supersede, retire, or create-with-successor.
- New migration/schema, Task type, runtime, dispatcher, scheduler, API/authentication, provider/evaluator, lock changes, synchronous indexing, or approval-scope expansion.
- Any changes to the frozen B4.0/B4.1/B4.2/B4.3 contracts.

## 7. Execution and review sequence

1. Reconfirm the exact merged `main` base and clean feature branch.
2. Read this plan, the B4.0 decision, the B4 implementation contract, and the relevant existing tests.
3. Produce a test-to-acceptance mapping before editing.
4. Implement the smallest integrated regression; stop if it requires an unapproved production or schema change.
5. Run the focused G4 test, relevant focused suites, static checks, disposable-PostgreSQL migration/head checks, and the full suite through the repository's established verification workflow.
6. Review the complete diff for test determinism, use of real application paths, exact state assertions, and absence of scope creep.
7. Reconcile exact-head hosted/local evidence and documentation. G4 is not complete until verification and explicit Operator acceptance are recorded.

## 8. Gate status

This document and its documentation-only PR record the G4 plan. They do **not** claim G4 implementation or verification. Implementation begins only after the Operator reviews this extracted plan and explicitly authorizes the implementation step. G5, G6, B5, B6, and R7-C remain unauthorized.
