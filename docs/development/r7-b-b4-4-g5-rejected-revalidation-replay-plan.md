# R7-B B4.4 G5 — Rejected revalidation approval replay and decision idempotency plan

**Status: DOCUMENTATION PLAN ONLY — G5 scope authorized for documentation planning on 2026-11-12; implementation is not authorized.**
**Base:** 15d565956cde44a7bd3d124e0bb62d188063846f.
**Parent gate:** B4.4. G1–G4 are complete and merged. G5 is the next bounded regression proof. G6 remains outstanding and is not authorized.

## 1. Purpose

Add the missing regression proof that an identical replay of an already-rejected revalidation approval returns the original durable rejection without creating duplicate decision records, terminal records, or canonical mutations.

The existing test_rejected_revalidation_does_not_mutate_the_knowledge_item proves that a rejected revalidation leaves the KnowledgeItem unchanged and that the approval Task is finalized. It does not visibly exercise replay of that rejected decision through the trusted OperatorApplicationAdapter, nor assert that request/decision Events and the terminal Outcome remain single records after replay.

This is a test-evidence gap, not a confirmed production defect. G5 must first prove the existing behavior using the ordinary trusted Operator path. It must not redesign rejection semantics or introduce another idempotency mechanism.

## 2. Frozen contracts to exercise

Use the accepted B4.0 architecture decision, ADR-0032, the B4 implementation plan, docs/tasks.md, and existing services/tests as authorities. Do not redefine their behavior.

- Rejection is a successful Operator decision: the LearningChange becomes rejected, records a non-empty rejection reason, trusted Operator identity, approval Task identity, canonical decision timestamp, and one rejection Event.
- Rejection does not create or mutate a KnowledgeItem. For a revalidation rejection, the existing target KnowledgeItem remains equivalent under the repository's canonical state representation, including status, current pointer, version, semantic content hash, and validation/review metadata.
- The rejected LearningChange has no committed KnowledgeItem state (committed_state remains NULL); it is not an accepted lifecycle transition.
- The approval Task is finalized through the existing TaskRuntime and ends done with the rejected-decision success result. TaskRuntime remains the only Task lifecycle authority.
- An identical request using the same trusted principal, target LearningChange, decision, rejection reason, and idempotency key returns the original Task and decision. It does not create another approval Task or another durable request/decision/terminal record.
- Reusing the idempotency key with a materially changed request remains a conflict under the existing approval fingerprint contract. Generic changed-request/principal conflict coverage already exists; G5 should not duplicate that matrix without a demonstrated gap.
- Rejection does not require an acceptance assessment. Do not fabricate or add an assessment solely to make the rejection test pass; follow the existing request-binding rules.
- The trusted OperatorApplicationAdapter, LearningCommitService, and existing TaskRuntime remain the only request, decision, and finalization path.

## 3. Required sequence

Use one Team and one canonical KnowledgeItem. Use the existing fixture, proposal, principal, request, and approval helpers; confirm exact helper behavior during implementation rather than introducing parallel fixtures.

1. **Establish the canonical target.** Create the KnowledgeItem through the existing accepted create path. Put it into needs_review through the ordinary D7 review path so the revalidation proposal targets a valid current item.
2. **Create the revalidation proposal.** Use the existing revalidation proposal path. Do not manually insert canonical KnowledgeItem or LearningChange rows. Capture the target's complete canonical state and semantic content hash before the rejection.
3. **Build one immutable rejection request.** Create a LearningChangeDecisionRequest with decision=reject, a non-empty reason, and one fresh idempotency UUID. Use the existing trusted Team-authorized Operator principal.
4. **Execute the original decision.** Call OperatorApplicationAdapter.decide_learning_change with that principal and request. This must exercise ordinary request creation, TaskRuntime admission, canonical rejection commit, and TaskRuntime terminal finalization. Verify the first result is not marked replayed.
5. **Verify the original rejection.** Verify the returned result identifies the expected LearningChange and approval Task, reports learning_change_status=rejected and task_status=done, preserves the trusted Operator identity and rejection timestamp, and contains the original Outcome identity. Verify the LearningChange has the rejected disposition/reason and no committed KnowledgeItem state. Verify the target KnowledgeItem is unchanged.
6. **Replay the exact request.** Call the same adapter again with the same principal and the exact same request object/idempotency key. Do not create a new key, Task, or request. Verify the result is marked replayed and returns the original Task, LearningChange, decision, rejection timestamp, and Outcome identity.
7. **Verify durable record counts after replay.** In PostgreSQL, assert exactly one original operator_task_requested Event, one learning_change_rejected decision Event, and one terminal Event for the approval Task. The terminal Event must be task_completed, not task_failed. Assert exactly one task_execution Outcome for that Task and that its identity matches both the original and replay results. Confirm replay did not add any Event or Outcome records.
8. **Verify canonical state remains unchanged.** Reload the KnowledgeItem and rejected LearningChange. Confirm the KnowledgeItem's complete canonical state and semantic content hash equal the pre-decision values; the rejected LearningChange remains rejected with the same reason, Operator/Task attribution, timestamp, and no committed state. Confirm no accepted decision Event, second approval Task, pointer advance, version change, or other canonical lifecycle write was introduced.

## 4. Acceptance criteria

G5 is complete only when one deterministic regression (or a small, clearly justified set of tests) proves all of the following:

- The original rejected revalidation approval and its replay use the real trusted OperatorApplicationAdapter path.
- The replay uses the exact original principal, immutable request, and idempotency key.
- The first decision is a successful rejection, not a Task failure.
- The replay returns the original rejection and the same approval Task, LearningChange, commit timestamp, and Outcome identity.
- Exactly one request Event, one rejection decision Event, one terminal task_completed Event, and one task-execution Outcome exist for the approval Task after replay.
- No task_failed terminal Event or duplicate terminal Outcome is created.
- The rejected LearningChange retains its original decision fields and has no committed KnowledgeItem state.
- The target KnowledgeItem remains unchanged across the initial rejection and replay, including current pointer, version, status, content hash, and review/validation dates.
- Replay creates no additional approval Task, Event, Outcome, accepted decision, or canonical lifecycle mutation.
- The regression is deterministic, uses the standard disposable-PostgreSQL test harness, and preserves fixture-owned cleanup.

## 5. Existing test surface and likely implementation location

Start with these authorities; inspect exact helper behavior and current assertions before editing:

- tests/test_experience_distiller.py: existing rejection regression, revalidation proposal helpers, and accepted Operator approval replay tests.
- tests/test_operator_application.py: request idempotency, changed-request/principal conflicts, Task creation, and trusted Operator path.
- tests/test_operator_approval.py: immutable request/fingerprint contract.
- core/operator_application.py: OperatorApplicationAdapter.decide_learning_change and request replay.
- core/learning_commit.py: canonical rejection decision and same-Task decision replay.
- core/task_runtime.py: admission, successful rejection finalization, and terminal Outcome/Event identity.
- docs/tasks.md: rejection, replay, and competing-request contract.
- docs/testing.md: existing G1–G4 verification evidence and the G5 closeout record to be added after implementation.

Preferred implementation: extend the existing rejection regression in tests/test_experience_distiller.py or add one focused adjacent test using the same fixture and established helpers. Choose only after mapping current assertions to the acceptance criteria. Do not duplicate generic idempotency-conflict coverage.

## 6. Scope and exclusions

**In scope:** a bounded regression proving exact replay/idempotency of one rejected revalidation approval, including unchanged decision/Event/Outcome counts and no canonical KnowledgeItem mutation.

**Preferred change:** tests only. No production correction is presumed. If the regression exposes a production defect, stop and report the smallest demonstrated defect and proposed correction before widening the implementation diff.

**Out of scope:**

- G6 accepted revise commit from a needs_review item as a separate proof gap.
- G1–G4 changes or reimplementation.
- B5, B6, R7-C, supersede, retire, or create-with-successor.
- New migration/schema, Task type, runtime, dispatcher, scheduler, API/authentication, provider/evaluator, lock changes, or approval-scope expansion.
- Changes to rejection semantics, approval fingerprints, TaskRuntime ownership, or the frozen B4.0/B4.1/B4.2/B4.3 contracts.
- A broad rewrite of existing approval/replay helpers.

## 7. Execution and review sequence

1. Reconfirm the exact merged main base and clean feature branch.
2. Read this plan, the B4.0 decision, the B4 implementation contract, docs/tasks.md, and the relevant current tests/services.
3. Produce a test-to-acceptance mapping before editing.
4. Implement the smallest regression through the existing trusted Operator path.
5. Run the focused G5 test and relevant focused suites; then run static checks, disposable-PostgreSQL migration/single-head checks, and the full suite through the repository's established workflow.
6. Review the complete diff for deterministic replay, exact record counts/identities, unchanged canonical state, fixture-owned cleanup, and absence of production/schema scope creep.
7. Verify exact-head hosted CI and reconcile PLAN.md, CHANGE_MAP.md, this audit, the R7-B implementation plan, and docs/testing.md.
8. Stop for explicit Operator review and acceptance. A green test or merged documentation plan alone does not close G5.

## 8. Gate status

This document and its documentation-only PR record the G5 plan. They do not claim G5 implementation, test completion, or verification. G5 implementation begins only after the Operator reviews this plan and separately authorizes the implementation step. G6, B5, B6, and R7-C remain unauthorized. B4.4 remains open until G1–G6, final verification, and explicit Operator acceptance are complete.
