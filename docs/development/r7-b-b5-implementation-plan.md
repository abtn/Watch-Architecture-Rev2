# R7-B B5 — Candidate Creation, Supersession, and Retirement Plan

**Status:** Proposed for Operator review — documentation-only planning phase  
**Planning authorization:** Granted 2026-11-13  
**Implementation authorization:** Not granted  
**Baseline:** R7-B B4.4 closeout, after PR #113; documentation baseline is stacked on PR #114  
**Scope authority:** Accepted R7-B B0 design and B4.0 architecture decision; this plan sequences the already accepted B5 design and does not replace it.

## 1. Objective

Implement the three deferred R7-B lifecycle capabilities defined by the accepted design:

1. Create a KnowledgeItem candidate linked to an existing predecessor through `supersedes_item_id`.
2. Retire a KnowledgeItem, including cancellation of a pending candidate.
3. Supersede a predecessor with an already accepted candidate.

All three must use the existing proposal, application-validation, assessment, trusted Operator approval, canonical commit, and TaskRuntime path. B5 must not introduce a second lifecycle write path.

This plan is deliberately limited to B5. It does not authorize B6, R7-C, or R8 implementation.

## 2. Frozen architecture and invariants

The following accepted contracts are prerequisites, not design questions to reopen during B5:

- Canonical writes remain: proposed `LearningChange` → deterministic application validation → operation-specific assessment → trusted Operator approval → atomic canonical commit.
- The existing host-invoked Operator adapter remains the authentication boundary. Assessment records are evidence, not commit authority.
- Ordinary Tasks and the existing TaskRuntime remain in use. No new runtime, scheduler, dispatcher, authentication stack, autonomous approval, or direct model write.
- KnowledgeItem statuses remain `active`, `needs_review`, and `retired`. Supersession is represented by a retired predecessor with a validated `superseded_by_id`, not a new status.
- The candidate's `supersedes_item_id` is immutable. The predecessor's `superseded_by_id` is set only by its accepted supersede transition.
- A candidate is accepted and active but withheld from retrieval and Context assembly until reciprocal predecessor/successor validation succeeds.
- The predecessor and candidate must never both be retrievable. Before supersession, the predecessor is exposed only while its own D7 eligibility holds. If it becomes due or enters `needs_review` while a candidate is pending, neither is exposed. After supersession, the successor is exposed and the predecessor is not.
- Stale is a derived application disposition. Proposals and assessments remain immutable; stale bindings cannot be accepted.
- Graph-changing operations use one Team-scoped lifecycle lock: lock the Team row first, then affected KnowledgeItem rows in ascending UUID order. Retain exact current-pointer/version compare-and-set checks.
- Confidence, semantic content, content version, and content hash are not changed by supersede or retire. Lifecycle snapshots and pointer history remain authoritative.

## 3. Scope

### Included

- Create-with-successor candidate creation using the existing create proposal/approval path.
- Operation-specific `KnowledgeLifecycleAssessment` variants for retire and supersede.
- Canonical retire writes for ordinary items and pending candidates.
- Canonical supersede writes that target and modify the predecessor only.
- Team-level graph serialization, exact state binding, reciprocal-link validation, retrieval/Context eligibility, idempotency, replay, and regression coverage.
- Integrated lifecycle verification and B5 closeout evidence.

### Excluded

- B6 legacy compatibility and additional lifecycle hardening.
- R7-C knowledge-use references, assessments, retrieval benchmarks, or use evaluation.
- New lifecycle statuses, a second write path, new runtime/scheduler/dispatcher/authentication components, autonomous approval, or model-controlled writes.
- Retrieval redesign, reranking, external vector infrastructure, or synchronous indexing shortcuts.
- Schema migrations unless preflight demonstrates a concrete unmet requirement. A migration or change to a frozen B0/B4 contract is a stop-and-return decision, not an implicit B5 addition.
- Any R8 work or dependency claim. B5 is a separately authorized R7-B phase, not an automatic R8 prerequisite.

## 4. Implementation sequence

### B5.0 — Preflight and contract freeze

**Purpose:** Verify that the implementation baseline still matches the accepted design before writing code.

1. Verify repository root, branch, exact HEAD, origin, clean worktree, and migration head.
2. Read the accepted B0.1 candidate guards, B4.0 decision, current approval/assessment contracts, lifecycle validator, current-pointer history, projection/indexing, retrieval, and Context assembly paths.
3. Map every B5 invariant to the current implementation and identify the exact missing behavior.
4. Confirm the existing `KnowledgeLifecycleAssessment` retire/supersede variants and approval path are sufficient; do not infer support from an enum or schema constraint alone.
5. Freeze proposal payloads, expected pointer/version/hash bindings, assessment bindings, Events/Outcomes, idempotency, and replay behavior for each operation.
6. Establish focused test locations and a complete acceptance matrix before implementation.

**Exit:** A reviewed implementation map with no unresolved contract ambiguity. If the accepted design cannot be implemented without changing a frozen earlier contract, stop and request a separate decision.

### B5.1 — Create-with-successor candidate

**Purpose:** Create a separately accepted candidate without prematurely publishing it.

1. Extend the existing create proposal path to accept the optional `supersedes_item_id` relation.
2. Under the Team-scoped lifecycle lock, validate the predecessor:
   - Same Team and canonical current state.
   - `active` and D7-eligible at the creation-time check.
   - Timezone-aware UTC `review_after` strictly later than the check.
   - Valid current pointer and content hash.
   - No committed successor and no other non-retired pending candidate.
   - No self-link or cycle.
3. Validate the candidate's own `review_after`: it must be non-NULL and future, computed from the canonical commit time and the approval Task's pinned TeamPolicy. A missing review interval rejects candidate creation.
4. Bind the predecessor relation into the proposal and proposed-state hash. Do not include it in the semantic content hash.
5. Commit the candidate through the trusted create approval path. It remains active but withheld from retrieval and Context assembly until the reciprocal predecessor link is committed.
6. Ensure a stale predecessor or candidate binding fails closed without partial writes.

**Required tests:** eligible candidate; absent/NULL/due review date; due or `needs_review` predecessor; wrong Team; existing pending candidate; committed successor; self-link/cycle; concurrent candidate creation; stale pointer/version/hash; replay.

**Exit:** Candidate creation is atomic and idempotent; all candidate guards pass; candidate remains unpublished until reciprocity is established.

### B5.2 — Retire

**Purpose:** Provide the terminal no-successor transition and the safe cancellation path for abandoned candidates.

1. Add the retire variant to the existing `KnowledgeLifecycleAssessment` proposal/recording path if not already active.
2. Bind the exact Team, target item, current LearningChange pointer, content version/hash, full-state hash, proposed state, evidence/reason, and assessment payload hash.
3. Require the trusted Operator approval path and exact pointer/version validation at commit.
4. For ordinary retirement, set status to `retired`, leave both successor links NULL, advance the current pointer, and preserve content/version/hash/confidence. The transition is terminal.
5. For candidate cancellation, retire the candidate while preserving its immutable `supersedes_item_id`. It no longer occupies the pending-candidate slot.
6. Permit a replacement candidate only after the earlier candidate is retired and the predecessor again passes every candidate-creation guard.
7. If the predecessor is retired without supersession, any pending candidate remains withheld and must be retired separately; it is never mutated automatically.

**Required tests:** ordinary active retirement; `needs_review` retirement; rejection of already-retired items; candidate cancellation; immutable predecessor relation; candidate-slot release; replacement candidate; wrong Team; stale assessment; concurrent retire/candidate operations; duplicate/replayed approval; no content/hash/version/confidence mutation.

**Exit:** Retire is terminal, replay-safe, and cannot create a successor link or mutate semantic content.

### B5.3 — Supersede

**Purpose:** Atomically retire the predecessor and activate the already accepted candidate through reciprocal-link validation.

1. Create a supersede proposal targeting the predecessor only.
2. Under the Team-scoped lifecycle lock, validate the predecessor's exact current pointer, content version, status, and full state. The predecessor may be `active` or `needs_review`; supersede does not revalidate it.
3. Validate the successor:
   - Same Team, accepted, canonical, and active.
   - `supersedes_item_id` equals the predecessor ID.
   - Non-NULL future UTC `review_after` at commit.
   - Exact current pointer, content version, content hash, and full-state binding match the proposal and lifecycle assessment.
   - No self-link, cycle, or conflicting committed successor.
4. Require the supersede-variant `KnowledgeLifecycleAssessment` and trusted Operator approval.
5. In one transaction, set the predecessor to `retired`, set its `superseded_by_id`, and advance its current LearningChange pointer. Do not modify the successor row.
6. Recheck the reciprocal relationship and D7 eligibility in ordinary retrieval and Context assembly. The successor becomes eligible through reciprocity validation; the predecessor is no longer eligible.
7. A successor in `needs_review`, with NULL/due review date, or with stale binding blocks the operation and leaves the predecessor unchanged.

**Required tests:** successful supersede; active and `needs_review` predecessor; successor review-state/date ineligibility; wrong Team; stale successor pointer/version/hash/full state; stale predecessor binding; self-link/cycle; already superseded predecessor; concurrency and CAS loser; replay after later transitions; projection and Context visibility.

**Exit:** The predecessor transition is atomic; the successor is untouched; reciprocity and D7 gates prevent simultaneous or invalid publication.

### B5.4 — Integrated regression and closeout

Run the complete lifecycle sequence:

`create → review → revise → revalidate → create-with-successor → supersede`

Also cover the alternate branch:

`create-with-successor → retire candidate → create replacement candidate`

And the terminal no-successor branch:

`create → retire`

Verify original create/revise/revalidate/retire/supersede approvals replay after later transitions and return their original results without duplicate Events, Outcomes, or canonical writes.

**Exit evidence:**

- Focused B5 tests and the complete existing regression suite pass.
- Ruff and Mypy pass.
- Fresh disposable PostgreSQL migrations reach one Alembic head; no persistent database is used.
- Exact-head hosted CI passes.
- Diff review confirms no scope expansion or second commit path.
- Current-pointer history, retrieval, and Context assembly remain correct.
- Documentation and verification evidence are reconciled.
- Explicit Operator acceptance is recorded.

## 5. Acceptance matrix

| Invariant | Acceptance evidence |
|---|---|
| Candidate eligibility | All B0.1 predecessor and candidate D7 guards enforced at proposal and commit |
| Single pending candidate | Concurrent attempts serialize; at most one non-retired candidate per predecessor |
| Reciprocal relationship | Candidate link immutable; predecessor link written only by accepted supersede |
| No dual publication | Predecessor and candidate are never both retrievable |
| Safe blocked supersede | Ineligible/stale successor leaves predecessor unchanged |
| Retirement | Terminal no-successor state; candidate cancellation frees slot |
| Atomicity | Team lock plus ordered item locks and exact CAS; no partial graph writes |
| Assessment authority | Immutable typed assessment; only trusted Operator path commits |
| Idempotency and replay | Original decision is returned; no duplicate side effects after later transitions |
| History | Current pointer and immutable snapshots reconstruct the exact lifecycle chain |
| Consumer correctness | Indexing, retrieval, and Context assembly enforce current canonical reciprocity and D7 eligibility |
| Regression | Existing create/revise/revalidate/review behavior remains unchanged |

## 6. Stop conditions

Stop implementation and return to the Operator if:

- Any B0/B4 invariant must change.
- The current schema cannot represent the accepted operation without a migration.
- A second write path, runtime, scheduler, dispatcher, or authentication boundary appears necessary.
- A lifecycle operation requires modifying the successor during supersede.
- Candidate and predecessor can become simultaneously retrievable.
- The Team lock or deterministic row-lock order cannot be applied consistently.
- A stale proposal or assessment can still commit.
- Replay cannot return the original decision without duplicate side effects.

Do not weaken an acceptance criterion to preserve schedule.

## 7. Authorization boundary

This document authorizes planning and review of B5 only. It does not authorize production implementation, schema changes, migrations, or any B6/R7-C/R8 work.

After this plan is reviewed and explicitly accepted, request a separate Operator authorization for B5.1. Each later implementation slice remains subject to its own checkpoint review and verification.

## 8. Source authority

This plan is subordinate to and must remain consistent with:

- The accepted R7-B B0.1 design decisions and lifecycle invariants.
- The accepted R7-B B4.0 architecture decision.
- ADR-0032 and the normative lifecycle contracts it records.
- The R7-B implementation plan, Phase B5 and its legal-transition reference.

If this plan conflicts with those accepted sources, stop and resolve the discrepancy before implementation.
