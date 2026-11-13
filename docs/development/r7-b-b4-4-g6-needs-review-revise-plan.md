# R7-B B4.4 G6 — Accepted revise from needs_review and retrieval ineligibility

**Status: DOCUMENTATION PLAN ONLY — G6 planning authorized 2026-11-13; implementation is not authorized by this plan. A separate explicit Operator decision is required before implementation.**
**Planning base:** `09cb8e6dfae078662e55631ae2f79e31fa8fb8cf` (G5 merge commit).
**Parent gate:** R7-B B4.4. G1–G5 are complete and merged. G6 is the final regression-proof gate. B4.4 remains open until G6, final verification, and explicit Operator acceptance are complete.

## 1. Purpose

Prove that the existing canonical revise operation behaves correctly when its target KnowledgeItem is already in `needs_review`.

The frozen contract permits revise against `active` or `needs_review` and requires status preservation. Existing coverage is split: approval binding can use a `needs_review` target, the history validator proves status-preserving revise semantics, and Team Experience retrieval tests prove a `needs_review` item is hidden even when a projection remains. The integrated G4 regression also revises a `needs_review` item, but its primary purpose is the stale pre-revise revalidation/fresh revalidation sequence. G6 isolates and explicitly asserts the accepted revise commit plus the retrieval-ineligibility boundary.

This is an evidence gap, not a presumed production defect. The first implementation action must be a test-to-acceptance audit. Prefer a focused test-only addition or a small extension to an existing revise regression. Do not change production code unless a concrete failing invariant demonstrates a defect; stop and report before widening scope.

## 2. Frozen contracts to exercise

Use the accepted B4.0 architecture decision, B4.1 proposal/assessment contracts, B4.2 revise commit contract, ADR-0032, D7 review semantics, `docs/tasks.md`, and the existing services/tests as authorities. Do not redefine them.

- Revise may target a current `active` or `needs_review` KnowledgeItem.
- An accepted revise preserves the target's existing status. In G6, the status before and after the revise must remain `needs_review`; revise must not reactivate the item.
- A content-changing revise advances the current LearningChange pointer exactly once and increments the content version exactly once.
- The revised semantic content and content hash change according to the canonical content-hash contract. Do not infer equality/inequality from unrelated metadata.
- Revise clears `last_validated_at`; it does not count as revalidation.
- Review scheduling follows the policy version pinned to the approval Task. Verify `review_after` against the canonical commit timestamp and that pinned policy, rather than ambient or subsequently changed policy.
- `reconstruct_knowledge_item_history` remains the single history authority. The reconstructed final state must match the live canonical KnowledgeItem, including status, pointer, version, content hash, and review/validation dates.
- Team Experience is a separate regenerable projection, not canonical authority. A projection pinned to an earlier pointer/hash is stale immediately after a content-changing revise advances the pointer.
- A `needs_review` item is not eligible for ordinary Team Experience retrieval even if an older projection row remains. Retrieval must recheck canonical status/currentness; a stale or retained projection must not make the item visible.
- The existing trusted Operator approval path, `LearningCommitService`, and single `TaskRuntime` remain the only canonical decision and Task-lifecycle authorities. No second commit path or synchronous indexing shortcut is permitted.

## 3. Required implementation sequence

Use one Team and one canonical KnowledgeItem. Use existing fixtures, proposal/assessment helpers, the trusted Operator adapter, history reconstruction, and Team Experience indexing/retrieval helpers. Confirm exact helper behavior during implementation; do not introduce parallel fixture machinery.

1. **Map existing coverage before editing.** Inspect the revise tests in `tests/test_experience_distiller.py`, status/history tests in `tests/test_learning_history.py`, projection and retrieval tests in `tests/test_team_experience.py`, and the accepted B4 contracts. Build a short table mapping each G6 criterion to an existing assertion or a missing assertion. In particular, identify what the G4 test already proves and do not duplicate its stale-assessment/revalidation sequence.
2. **Establish the canonical item and a real review state.** Create the KnowledgeItem through the existing accepted create path. Use the ordinary D7 review path (or an existing fixture that demonstrably represents its durable result) to place the item in `needs_review`. Capture the complete canonical state, current LearningChange pointer, version, semantic content hash, `last_validated_at`, `review_after`, and relevant TeamPolicy version.
3. **Establish projection visibility before review if needed.** If the chosen fixture supports it, publish the active item through the ordinary Team Experience indexer before D7 review, then verify it is retrievable. After the review transition, verify that the same retained projection does not make the `needs_review` item retrievable. Reuse the existing test `test_needs_review_item_is_not_retrievable_even_if_projection_remains` rather than duplicating it unless the integrated G6 flow needs a distinct assertion.
4. **Create and assess a content-changing revise.** Use the ordinary revise proposal and `KnowledgeQualityAssessment` path against the current `needs_review` item. Ensure the proposal changes semantic content so pointer, version, and content-hash effects are observable. Bind the assessment to the exact current target state.
5. **Accept through the trusted Operator path.** Submit the accepted revise through `OperatorApplicationAdapter.decide_learning_change` with the same Team-authorized principal and existing request contract. Do not call a lower-level commit service directly to simulate an Operator decision.
6. **Assert canonical revise semantics.** Reload the item and assert: status remains `needs_review`; current pointer equals the accepted revise LearningChange; pointer advanced once; version increased by exactly one; semantic content and content hash changed; `last_validated_at` is `None`; and `review_after` equals the contract-derived value from the commit timestamp and approval Task's pinned review interval (including the configured/NULL policy cases only if needed to make the invariant precise). Confirm the accepted decision is attributed to the trusted Operator/approval Task and the Task is finalized through the existing TaskRuntime.
7. **Assert history reconstruction.** Reconstruct the item's history using the existing authoritative function. Verify the accepted revise is in the ordered chain and the reconstructed final state exactly equals the live row. Preserve the D7 review Event as an overlay; do not invent a LearningChange pointer advance for the review Event.
8. **Assert projection and retrieval remain fail-closed.** Verify the pre-revise projection is no longer current after the pointer advance. Run the ordinary retrieval path and assert the item remains absent because canonical status is still `needs_review`, even if the old projection row remains. If an ordinary indexer run is part of the existing test pattern, verify it does not publish a retrievable current projection for a `needs_review` item. Do not add a synchronous indexing shortcut or mutate projection rows manually.
9. **Keep the test bounded.** Do not add a subsequent revalidation acceptance, second revise, supersede, retirement, or cross-Team operation; those are not G6. G4 already proves the integrated revise → stale revalidation rejection → fresh revalidation path.

## 4. Acceptance criteria

G6 is complete only when deterministic regression evidence proves all of the following:

- The target is a canonical KnowledgeItem in `needs_review` before the accepted revise.
- The revise is proposed, assessed, and accepted through the existing trusted Operator/application path.
- The accepted revise preserves `needs_review`; it does not transition the item to `active`.
- A content-changing revise advances the current LearningChange pointer once and increments content version once.
- Semantic content and the canonical content hash reflect the accepted revision.
- `last_validated_at` remains cleared; revise is not treated as revalidation.
- `review_after` is consistent with the commit timestamp and policy pinned to the approval Task.
- Task finalization and decision attribution use the existing TaskRuntime and trusted Operator identity.
- History reconstruction validates the accepted revise and exactly matches the live canonical state; the D7 review Event remains an overlay.
- The old projection cannot be used as current after the pointer advance.
- Ordinary Team Experience retrieval excludes the item while canonical status remains `needs_review`, including when an older projection row remains.
- No synchronous indexing shortcut, direct canonical row mutation, duplicate commit path, schema/migration change, or unrelated lifecycle work is introduced.
- The test is deterministic, uses disposable PostgreSQL through the standard test harness, and leaves fixture-owned cleanup intact.

## 5. Existing test and source surface

Inspect these first; confirm exact helpers and assertions rather than assuming names or introducing parallel abstractions:

- `tests/test_experience_distiller.py`: accepted revise through the Operator path, target/assessment binding, and the existing G4 same-item sequence.
- `tests/test_learning_history.py`: status-preserving revise and D7 review-overlay reconstruction.
- `tests/test_team_experience.py`: `test_needs_review_item_is_not_retrievable_even_if_projection_remains`, `test_changed_canonical_item_invalidates_existing_projection`, and ordinary indexing/retrieval eligibility.
- `core/learning_commit.py`: canonical revise commit and Task-attributed decision.
- `core/knowledge_quality.py` and `core/knowledge_approval.py`: revise assessment and immutable approval binding.
- `core/learning_history.py`: `reconstruct_knowledge_item_history`.
- `core/knowledge_index.py`: ordinary Team Experience projection publication and retrieval eligibility.
- `docs/tasks.md`, the B4.0 decision, and the B4.2 contract: authority and write-scope boundaries.

Preferred implementation location is one focused test in `tests/test_experience_distiller.py`, with only a small adjacent retrieval assertion if the existing test surface cannot prove the combined boundary cleanly. The test-to-acceptance mapping decides the smallest location. Do not duplicate isolated test coverage without a reason.

## 6. Scope and exclusions

**In scope:** one integrated regression proving accepted revise from `needs_review`, status preservation, canonical pointer/version/content/date semantics, history reconstruction, and Team Experience projection/retrieval ineligibility.

**Preferred change:** tests only. No production correction is presumed. If the new regression exposes a production defect, stop and report the exact failed invariant, failing test, relevant source path, and smallest proposed correction. Do not silently widen the PR.

**Out of scope:**

- G1–G5 changes or reimplementation.
- B5 candidate creation/supersession, B6 legacy hardening, R7-C knowledge-use references/assessments/retrieval evaluation.
- Supersede, retire, create-with-successor, or a subsequent revalidation acceptance.
- New migration/schema, Task type, runtime, dispatcher, scheduler, API/authentication subsystem, provider/evaluator, lock changes, or approval-scope expansion.
- Synchronous indexing, direct fixture/manual mutation of canonical or projection rows to simulate production behavior, or a second commit path.
- Changes to frozen B4.0/B4.1/B4.2/B4.3 contracts.

## 7. Verification and review sequence

1. Reconfirm the accepted G6 plan merge commit, repository root, exact branch/HEAD, origin, and clean worktree.
2. Read this plan, the B4.0 architecture decision, B4.1 proposal/assessment contract, B4.2 revise commit contract, ADR-0032, D7 semantics, and relevant current source/tests.
3. Produce the test-to-acceptance mapping before editing. Reuse G4 and existing history/retrieval tests; list only uncovered assertions.
4. Implement the smallest deterministic regression through the trusted Operator path. If a production/schema correction appears necessary, stop and request separate authorization.
5. Run the focused G6 test, then relevant revise/history/Team Experience suites.
6. Run Ruff, Mypy, fresh disposable-PostgreSQL migration/single-head checks, patch whitespace validation, and the full pytest suite using the established local verification protocol. Preserve and restore `DATABASE_URL` and `TEST_DATABASE_URL`; remove only the disposable container created by the run.
7. Review the complete diff for deterministic assertions, exact pointer/version/hash/date behavior, history equality, projection/retrieval exclusion, trusted-path usage, and absence of scope creep.
8. Run hosted CI on the exact PR head. Record the SHA and workflow result; do not rely on branch name alone.
9. Reconcile PLAN.md, CHANGE_MAP.md, the B4.4 audit, the R7-B implementation plan, and docs/testing.md. Stop for explicit Operator review and acceptance. G6 completion does not by itself close B4.4.

## 8. Gate status

This document and its documentation-only PR authorize and record G6 planning only. They do not authorize G6 implementation or claim G6 verification. Implementation begins only after the Operator reviews the plan and separately authorizes the implementation step. B5, B6, and R7-C remain unauthorized. B4.4 remains open until G1–G6 are complete, final verification passes, and explicit Operator acceptance is recorded.
