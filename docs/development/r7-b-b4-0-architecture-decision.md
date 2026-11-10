# R7-B B4.0 — Revise and Revalidate Architecture Decision

**Decision date:** 2026-11-10  
**Authority:** explicit Operator authorization, “authorized please continue,” following formal B3 closure.  
**Status:** accepted for B4 implementation; B4.1 is the current bounded slice.

## Decision

Implement revise and revalidate by extending the existing `propose_learning_change` Task path with operation-specific proposal contracts. Reuse the existing assessment and approval infrastructure. Do not create a parallel lifecycle workflow.

This is the smallest architecture consistent with the delivered B3 foundations: B3 already supplies immutable revalidation assessments, assessment Task lifecycle/recovery, operation-specific approval binding, and the single trusted Operator decision path. The missing capability is proposal/assessment integration and canonical commit behavior—not another runtime.

## 1. Proposal authority

- The existing `propose_learning_change` Task remains the only proposal-producing Task for B4.
- It may propose `revise` or `revalidate` only through explicit, operation-specific input and output contracts. Create remains supported with its historical contract.
- Its write scope remains exactly `["LearningChange"]`. TaskRuntime remains the sole owner of admission, attempt fencing, terminal finalization, recovery, and Outcomes.
- The proposal Task may not write a KnowledgeItem, TeamPolicy, approval decision, or Team Experience projection. It cannot commit or authorize its own proposal.
- No new Task type, Task registry, dispatcher activation, scheduler, public API, Watch-owned authentication, or second commit path is introduced.

## 2. Assessment routing

| Operation | Assessment | Required binding |
|---|---|---|
| `revise` | Existing `KnowledgeQualityAssessment` | Exact LearningChange proposal/proposed-state hash, canonical evidence basis, evaluator/rubric identity and revision, and exact current target snapshot. |
| `revalidate` | Existing `KnowledgeRevalidationAssessment` | Exact current target pointer/version/content hash/state, canonical rebuilt evidence basis, proposal hashes, policy pin, and existing assessor identity/revision contract. |

No new assessment type is introduced. A revise proposal must be evaluated as a proposed content state, not as an abstract request to edit. A revalidate proposal is not a content rewrite and must not be routed through the quality assessment path.

## 3. Exact target binding and stale-state behavior

Both operations target one existing same-Team KnowledgeItem and bind the exact current LearningChange pointer, content version, v2 semantic content hash, and reconstructable full-state snapshot/hash.

- Any pointer, version, content hash, full-state hash, Team ownership, or relevant lifecycle-state drift invalidates the proposal/assessment. Do not silently rebase a stale proposal onto a newer item state.
- The application independently rebuilds and verifies target state at proposal validation, assessment request/admission, approval binding, and canonical commit. An identifier or Task status alone is never sufficient.
- The compare-and-set at commit uses the exact expected pointer and version. A concurrent winner causes the losing operation to fail atomically; it must not create a partial state, terminal success Event, or projection publication.
- The exact wire/payload fields, canonicalization, stable error vocabulary, and replay fingerprint are to be frozen in B4.1 after tracing the existing source and tests. This decision does not invent a new schema or migration.

## 4. Operation invariants

### Revise

- Preserve KnowledgeItem identity and origin; increment content version exactly once; advance the current LearningChange pointer atomically.
- Preserve `active` as `active` and `needs_review` as `needs_review`; revise never reactivates.
- Only revise may change confidence. A content-changing revise clears `last_validated_at`.
- Recompute `review_after` from the approval Task's pinned TeamPolicy and canonical commit time; absent interval means NULL.
- Existing B0.1 pending-candidate/successor rules still apply: a revise that changes the predecessor state invalidates pending supersede proposal/assessment state. B4 must not implement the supersede operation itself.

### Revalidate

- Permit only `needs_review → active`, through an accepted LearningChange with a current `KnowledgeRevalidationAssessment`.
- Preserve all semantic content, v2 content hash, content version, and confidence exactly.
- Set `last_validated_at`; recompute `review_after` from the approval Task's pinned TeamPolicy and canonical commit time. A missing interval yields NULL and the item remains retrieval-ineligible.
- Advance the current LearningChange pointer. Republish the Team Experience projection against the new pointer/state before retrieval can expose the item. Do not treat an old projection as current merely because the semantic content hash is unchanged.
- No scheduler-only reactivation.

## 5. Approval and commit boundary

- B4.1 adds proposal/assessment contract support only. The approval allowlist remains exactly `{"create"}`; neither revise nor revalidate can yet be accepted.
- B4.2 and B4.3 separately implement and test revise and revalidate canonical commit behavior. Each commit rechecks the full target/assessment binding, pinned TeamPolicy, trusted host Operator identity, and exact compare-and-set preconditions inside the canonical transaction.
- The existing `approve_learning_change` Task and `LearningCommitService` remain the only trusted decision/commit path. No assessment Task, worker, model, or indexer gains canonical write authority.
- Only after an operation's implementation, replay/recovery, and regression gates pass may its operation be added to the existing approval allowlist. B4 cannot add create-with-successor, supersede, or retire.

## 6. B4 sequence and authorization boundary

1. **B4.1 — Proposal and assessment contracts:** extend the existing proposal path; define strict operation-specific payloads, target bindings, assessment routing, idempotency, Events, Outcome, replay, and focused tests. No canonical lifecycle writes or approval expansion.
2. **B4.2 — Revise commit:** implement same-item version advancement and atomic compare-and-set, using the existing quality assessment.
3. **B4.3 — Revalidate commit:** implement the state-preserving reactivation transition and projection republish gate, using the existing revalidation assessment.
4. **B4.4 — Integrated regression and closeout:** verify all B4 invariants, concurrency, stale assessments, retries/recovery, projection visibility, and hosted CI on the exact PR head, then complete the Operator's source/diff review. Operator-local exact-head verification is not part of the current B4 evidence route.

### Current B4 verification route

For the current B4 execution, local synchronization and local test execution are unavailable and are intentionally skipped. This does not reduce the technical acceptance bar. GitHub-hosted Actions must run against the exact PR head and prove fresh disposable PostgreSQL migration/single-head checks, Ruff, Mypy, the full pytest suite, and cleanup. The exact tested SHA and workflow run must be recorded. The Operator must still review the complete source/test diff and the B4.1 contract matrices. Do not describe hosted CI as an Operator-local run, and do not close B4 if hosted automation misses any required check.
B4 authorization does not authorize B5, B6, or R7-C. Any need to change frozen B0/B1/B2 semantics, introduce a schema migration, or widen the authority model beyond this decision is a stop-and-return decision.

## 7. Evidence at decision time

Read-only source inspection at main `0908a4227f58c4ba126b6dd8744f4f43e0c17db9` established:

- `core/learning_history.py` already validates revise/revalidate history transition invariants.
- `core/knowledge_revalidation.py` already validates a revalidation proposal against its source Task, target snapshot, evidence basis, and current target state, and builds the existing revalidation assessment request.
- `core/knowledge_quality.py` and `core/experience_distiller.py` currently constrain proposal/quality validation to create.
- `core/task_runtime.py` finalization for `propose_learning_change` currently requires create with a NULL target.
- `core/operator_approval.py` retains a create-only supported-operation predicate; `core/learning_commit.py` implements create-only canonical commit.
- `core/knowledge_index.py` provides the existing Team Experience projection path; B4.3 must use its canonical current-pointer/state checks rather than adding a publication shortcut.

This record is an implementation decision and scope contract, not evidence that B4.1 or later code has been implemented or tested.

