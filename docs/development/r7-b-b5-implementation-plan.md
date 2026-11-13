# R7-B B5 — Candidate Creation, Supersession, and Retirement Plan

**Status:** B5.1 implementation complete; B5.2 implementation in draft PR #118; technical review and Operator acceptance in progress
**Planning authorization:** Granted 2026-11-13 for the B5 sequence and its checkpoint plans
**Implementation authorization:** B5.1 only; completed and merged. B5.2–B5.4 require separate checkpoint authorization
**Baseline:** `main` after PR #116 squash merge `d946342907dc1c384c73de18216a5c018dd48e2f`; migration head `0018_r7b_lifecycle_review_date`

**B5.1 implementation closeout (2026-11-13):** PR [#116](https://github.com/abtn/Watch-Architecture-Rev2/pull/116) merged to `main` at `d946342907dc1c384c73de18216a5c018dd48e2f`. Exact PR head `b9fe3ff56347ca456f0db466d07e109a311501ca` passed hosted CI run [#43408281624](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43408281624): fresh PostgreSQL migration/head verification, Ruff, Mypy, patch whitespace, and full suite (**961 passed, 113 warnings in 148.07s**). Operator-local exact-head verification also passed: disposable PostgreSQL migration to `0018_r7b_lifecycle_review_date`, Ruff, Mypy (38 source files), and full suite (**961 passed, 113 warnings in 315.33s**); the disposable container was removed, both database environment variables were restored, and the worktree remained clean. B5.1 is complete; this does not authorize B5.2 implementation.

**B5.2 documentation checkpoint (2026-11-13):** The current documentation change records B5.1 closeout and prepares the Retire checkpoint against the already accepted B5 contract. It does not modify application code, tests, schema, migrations, or implementation authorization. B5.2 implementation remains separately gated.

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

1. Verify repository identity, exact main baseline, migration head, and local programmer-side clean-tree/remote preflight before local sync or tests.
2. Read the accepted B0.1 candidate guards, B4.0 decision, ADR-0032, approval/assessment contracts, lifecycle validator, history reconstruction, projection/indexing, retrieval, and Context assembly.
3. Map each B5 invariant to current code and separate existing mechanisms from missing commit behavior.
4. Confirm that the lifecycle assessment variants are evidence-only and that the active approval allowlist still excludes lifecycle commits.
5. Freeze the B5.1 create proposal binding, predecessor snapshot, policy-derived candidate review date, Task/approval binding, canonical Event/Outcome, idempotency, and replay contract.
6. Establish focused tests and explicit stop conditions before source changes.

**B5.0 findings (verified against main after PR #114):**

| Concern | Existing implementation | B5.1 consequence |
|---|---|---|
| Schema | `KnowledgeItem.supersedes_item_id` and `superseded_by_id` already exist with same-Team foreign keys. The partial unique index `uq_knowledge_items_pending_candidate` permits at most one non-retired candidate per predecessor. Migration head is `0018_r7b_lifecycle_review_date`. | No schema change is currently justified. Recheck exact main migration head in programmer preflight. |
| Assessment | `KnowledgeLifecycleAssessment` already records retire/supersede evidence and successor bindings through its existing Task path. | Reuse it; assessment is not approval authority and B5.1 does not enable retire/supersede writes. |
| Approval | `core/knowledge_approval.py` builds the typed approval binding. `core/operator_application.py` and `core/learning_commit.py` currently admit create/revise/revalidate only. | Candidate remains a create LearningChange. Do not expand approval operation allowlist to retire/supersede in B5.1. |
| Create commit | `core/learning_commit.py` currently commits ordinary creates with both supersession fields NULL and computes `review_after` from the approval Task's pinned TeamPolicy; the interval may be absent. | Extend the existing create path with an optional relation, and require a non-NULL future review date only when creating a successor candidate. |
| Canonical history/hash | `core/learning_history.py` includes both relation fields in full-state snapshots; the semantic content hash is over the content fields, not supersession links. | Bind `supersedes_item_id` in proposal/full-state hash and committed snapshot, but not semantic content hash. Preserve current history format unless tests prove a gap. |
| Retrieval and Context | `core/knowledge_index.py` has a reciprocal supersession publication gate; `core/context_assembly.py` rechecks it against canonical state. A candidate with no reciprocal predecessor link remains hidden. | Preserve this gate and add tests for actual accepted candidates; do not redesign retrieval. |
| Serialization | The approval transaction already locks the Team row. Candidate creation does not yet lock and validate the predecessor row under a frozen Team→item order. | B5.1 must acquire the Team lock first, then lock the predecessor row, and validate the complete canonical state before candidate commit. |

**B5.0 exit:** The accepted contract is implementable within the existing schema, assessment, approval, TaskRuntime, history, and retrieval architecture. The concrete B5.1 gap is create-with-successor validation and commit binding. The existing create-only allowlist remains unchanged for this slice. No migration or earlier-contract change is indicated by the current evidence.

**Exit:** A reviewed implementation map with no unresolved contract ambiguity. If the accepted design cannot be implemented without changing a frozen earlier contract, stop and request a separate decision.

### B5.1 — Create-with-successor candidate

**Purpose:** Create a separately accepted candidate without prematurely publishing it.

1. Extend the existing `create` LearningChange proposal schema and validation to accept optional `supersedes_item_id`; ordinary create remains unchanged when it is absent.
2. Preserve the existing create-only approval allowlist, trusted Operator identity, assessment binding, TaskRuntime admission/finalization, and canonical commit transaction. Do not add a lifecycle operation or a second write path.
3. In the approval transaction, lock the Team row first and then lock the predecessor KnowledgeItem row. Validate its same-Team ownership, full canonical snapshot/current pointer, content hash, `status=active`, timezone-aware UTC `review_after` strictly later than the creation-time check, NULL `superseded_by_id`, and absence of another non-retired candidate. Reject self-reference and any detectable cycle/corrupt lineage. A `needs_review`, due, unscheduled, retired, or already-superseded predecessor is not eligible for candidate creation; it must first be revalidated through the existing authorized path where applicable.
4. Enforce the candidate's own `review_after`: it must be non-NULL and future, computed as canonical commit time plus the interval from the approval Task's pinned TeamPolicy. A missing interval rejects only candidate creation; ordinary create retains existing policy behavior.
5. Bind the predecessor ID and exact predecessor pointer/version/full-state snapshot into the proposed state and its canonical proposal hash. The relation belongs in the full-state history snapshot, not the semantic content hash.
6. Commit the new KnowledgeItem with `status=active`, version 1, its immutable `supersedes_item_id`, NULL `superseded_by_id`, and the policy-derived future review date. The predecessor is not mutated by candidate creation.
7. Preserve the existing reciprocal publication gate: candidate remains accepted but hidden from retrieval and Context until a later accepted supersede commit updates the predecessor. Recheck stale bindings before any canonical writes; failures must leave no partial candidate or LearningChange acceptance.

**Required tests:** ordinary create remains unchanged; eligible candidate; candidate with NULL TeamPolicy review interval; predecessor NULL/due review date; `needs_review`/retired predecessor; wrong Team; existing pending candidate; committed successor; self-link/corrupt cycle; concurrent candidate creation; stale predecessor pointer/version/hash/full state; approval-time drift; replay; no partial writes; candidate absent from both retrieval and Context before reciprocity.

**Exit:** Candidate creation is atomic and idempotent; all candidate guards pass; candidate remains unpublished until reciprocity is established.

### B5.2 — Retire

**Purpose:** Implement the terminal no-successor transition for an ordinary KnowledgeItem and the safe cancellation path for a pending successor candidate. Both operations use the existing lifecycle assessment, trusted Operator approval, canonical commit, and TaskRuntime infrastructure. Retirement is not supersession.

**Implementation boundary:** B5.2 may extend the existing proposal/validation/approval/commit path only as needed to admit retirement. It must not create a second lifecycle write path, new Task type, runtime, scheduler, dispatcher, authentication boundary, or retrieval redesign. The existing schema already represents `retired` and candidate relations; a migration is not presumed. If preflight demonstrates a concrete schema gap, stop and return for a separate decision.

#### B5.2.0 — Baseline and code-path preflight

No source edits in this checkpoint.

1. Start only after the B5.2 implementation checkpoint receives separate, explicit Operator authorization and the B5.2 documentation PR is merged.
2. Record the exact post-documentation `main` merge commit. Create the implementation branch from that commit; do not use a floating branch name as the baseline.
3. Verify repository root, current branch, HEAD, origin, clean worktree, remote SHA, and Alembic head. Confirm the expected migration head before local tests.
4. Inspect the existing implementations and tests for:
   - `KnowledgeLifecycleAssessment` retire evidence and TaskRuntime recording.
   - LearningChange proposal construction, deterministic validation, and proposal/proposed-state hashing.
   - Approval binding, trusted Operator identity, operation allowlist, and canonical commit transaction.
   - Team-first lifecycle locking, deterministic KnowledgeItem row-lock order, and current-pointer compare-and-set.
   - Lifecycle Events/Outcomes, immutable snapshots, history reconstruction, idempotency, and replay.
   - The B5.1 pending-candidate partial unique index and reciprocal retrieval/Context publication gate.
5. Map each frozen requirement below to the actual function, model, transaction, and existing test. Distinguish existing behavior from the minimum missing behavior.
6. Confirm whether the current retire assessment variant is already usable. Reuse it if so; do not add a duplicate variant or Task.
7. Confirm the schema can represent both ordinary retirement and candidate cancellation. Do not add a migration merely for convenience.

**Exit:** A reviewed code-path map, exact implementation baseline, focused test plan, and no unresolved contract ambiguity. If any frozen B0/B4 invariant or schema contract must change, stop and return to the Operator before source edits.

#### B5.2.1 — Retirement proposal and exact state binding

Extend the existing LearningChange proposal and deterministic validation path for retirement with the smallest operation-specific change.

Bind the proposal to:

- Exact Team and target KnowledgeItem IDs.
- Current LearningChange pointer and expected current status.
- Content version, semantic content hash, and full-state snapshot/hash.
- Exact proposed transition to `retired`.
- Operation kind distinguishing ordinary retirement from pending-candidate cancellation where the existing model requires it.
- Immutable candidate predecessor relation (`supersedes_item_id`) when the target is a candidate.
- Lifecycle assessment identity and payload hash.
- A bounded reason/evidence reference consistent with the existing assessment contract.

Validation must establish:

1. The target exists and belongs to the stated Team.
2. The target is currently `active` or `needs_review`; already-retired items are rejected and never reopened or rewritten.
3. The current pointer, content version, semantic content hash, and full-state binding match canonical state.
4. For candidate cancellation, the target is a real pending candidate with an immutable, same-Team `supersedes_item_id`; its relation is preserved exactly.
5. The proposal cannot be retargeted to another item, Team, pointer, version, or candidate relation after assessment.

**Required tests:** active item; `needs_review` item; already-retired rejection; wrong Team; missing target; malformed/non-candidate cancellation target; stale pointer; stale version; stale content hash; stale full-state hash; altered predecessor relation; proposal-hash mismatch.

**Exit:** A retirement proposal is deterministic and bound to the exact canonical item state. No canonical write occurs at proposal or validation time.

#### B5.2.2 — Lifecycle assessment integration

1. Reuse the existing retire variant of `KnowledgeLifecycleAssessment` if it already satisfies the binding contract. Extend only a demonstrated missing field or validation rule.
2. Bind the assessment to the exact Team, item, current pointer, version, content hash, full-state hash, proposed retired state, and operation kind.
3. Record assessment evidence and its attributable Event through the existing TaskRuntime path.
4. Keep assessment evidence separate from approval authority. An accepted assessment alone must never retire a KnowledgeItem.
5. Reject missing, mismatched, stale, conflicting, or replay-incompatible assessment bindings.
6. Preserve immutable assessment records; represent staleness as an application disposition rather than rewriting historical evidence.

**Required tests:** valid ordinary-retire assessment; valid candidate-cancellation assessment; assessment target mismatch; stale pointer/version/hash; changed proposed state; missing assessment; duplicate assessment/task replay; assessment cannot commit without trusted approval.

**Exit:** A valid retirement assessment is durable, attributable evidence, but is not commit authority.

#### B5.2.3 — Trusted approval and canonical retirement commit

Extend the existing trusted Operator approval and canonical commit path only enough to admit the retire operation.

1. Preserve host-authenticated Operator identity and the existing application validation boundary. Do not accept model- or worker-supplied identity as authority.
2. Bind approval to the exact retirement proposal, assessment, and proposed-state hash. A create/revise/revalidate approval must not be reusable as a retirement approval.
3. In the canonical transaction, acquire the Team lifecycle lock first, then lock affected KnowledgeItem rows in deterministic ascending UUID order. For a single-target retirement, lock that target after the Team.
4. Re-read and revalidate Team ownership, current pointer, content version, semantic content hash, full-state hash, expected status, candidate relation, and assessment binding under the lock.
5. Reject stale or changed state before any canonical writes. The compare-and-set loser must leave no partial Event, Outcome, LearningChange, pointer, or KnowledgeItem mutation.
6. Commit the terminal `active → retired` or `needs_review → retired` transition and its attributable lifecycle records atomically, advancing the current LearningChange pointer according to the existing history contract.
7. For an ordinary item, both `supersedes_item_id` and `superseded_by_id` remain NULL.
8. For candidate cancellation, preserve `supersedes_item_id` exactly and leave `superseded_by_id` NULL. Do not mutate the predecessor.
9. Preserve semantic content, content version, semantic content hash, and confidence. Retirement changes lifecycle state, not the knowledge claim.
10. Keep the transition terminal. No operation in B5.2 may reactivate or reopen the retired item.

**Required tests:** successful ordinary retirement from each allowed status; successful candidate cancellation; trusted identity required; wrong operation/approval binding; stale state rejected under lock; concurrent compare-and-set loser; no partial writes; current pointer/history advancement; immutable content/version/hash/confidence; correct NULL/preserved relation fields.

**Exit:** One trusted, atomic canonical commit performs retirement. There is no direct worker write or second commit path.

#### B5.2.4 — Pending-candidate slot release and concurrency

Prove the interaction with B5.1 candidate creation using the existing Team-first lock order and partial unique index.

1. Confirm the pending-candidate uniqueness predicate excludes a candidate only after its canonical status becomes `retired`; proposal, assessment, or rejected approval alone must not release the slot.
2. Confirm that retiring a pending candidate preserves its immutable `supersedes_item_id` and leaves its predecessor unchanged.
3. After candidate retirement commits, verify a replacement candidate can be created only if the predecessor still passes every B5.1 guard at the replacement proposal and commit boundaries.
4. Recheck same-Team ownership, predecessor status `active`, future non-NULL UTC `review_after`, NULL `superseded_by_id`, exact current pointer/version/full state, no other non-retired candidate, and cycle/lineage integrity.
5. Serialize retire-versus-create and competing candidate operations with the Team row lock first, then item locks in ascending UUID order.
6. Verify that retiring a predecessor without supersession does not mutate or publish its pending candidate. The candidate remains pending and hidden until separately retired or superseded through B5.3.
7. Do not create a cascade or implicit candidate cancellation when a predecessor is retired.

**Required tests:** slot remains occupied before retirement commit; slot releases after successful candidate retirement; failed/stale retirement does not release it; replacement candidate succeeds after cancellation when predecessor remains eligible; replacement fails when predecessor is due, unscheduled, `needs_review`, retired, or superseded; concurrent retire versus candidate creation; concurrent replacement attempts; predecessor retirement leaves pending candidate unchanged and hidden.

**Exit:** Candidate cancellation releases exactly one pending slot only after canonical retirement. Replacement creation still enforces all B5.1 guards, and graph races cannot produce duplicate or invalid candidates.

#### B5.2.5 — Idempotency, replay, and history reconstruction

1. Replay the same accepted retirement approval and verify it returns the original committed result without another canonical transition.
2. Reject conflicting reuse of an idempotency key or approval identity with a different proposal, target, or state binding.
3. Replay a stale/rejected retirement and verify the original disposition remains stable and does not become accepted after canonical state changes.
4. Replay the original accepted retirement after later lifecycle activity and verify it does not create duplicate Events, Outcomes, LearningChanges, pointer advances, or graph mutations.
5. Reconstruct history and verify the exact transition, immutable semantic content, confidence, content version/hash, candidate relation, and current pointer.
6. Verify a retired candidate remains linked to its predecessor historically but no longer occupies the pending-candidate slot.
7. Verify a pending candidate remains hidden if its predecessor is retired without supersession; retirement must not manufacture reciprocity.

**Required tests:** same-approval replay; conflicting replay; stale rejection replay; replay after a later transition; no duplicate side effects; snapshot/hash reconstruction; pointer reconstruction; candidate-link preservation; predecessor-retirement/no-implicit-mutation case.

**Exit:** Retirement is replay-safe and canonical history reconstructs the exact lifecycle state without duplicate side effects.

#### B5.2.6 — Integrated regression, verification, and closeout

Run the B5.2 cases together with B5.1 and existing lifecycle behavior.

**Required integrated sequences:**

```text
create → retire
```

```text
create-with-successor → retire candidate → create replacement candidate
```

```text
create-with-successor → retire predecessor
                  → verify candidate remains pending and hidden
                  → retire candidate separately
```

Also verify that existing create, revise, revalidate, review, and B5.1 candidate-creation behavior remains unchanged.

**Acceptance matrix:**

| Area | Required proof |
|---|---|
| Ordinary retirement | `active` and `needs_review` can retire; already-retired cannot be rewritten |
| Candidate cancellation | Candidate retires; immutable predecessor relation is preserved |
| Semantic immutability | Content, content version, content hash, and confidence are unchanged |
| Candidate slot | Slot releases only after canonical candidate retirement |
| Replacement candidate | All B5.1 predecessor and candidate guards are rechecked |
| Predecessor retirement | Pending candidate remains unchanged and hidden; no implicit cascade |
| Isolation | Wrong Team/target/relation and malformed lineage are rejected |
| Stale state | Pointer, version, content hash, full-state hash, and assessment drift are rejected |
| Concurrency | Retire/retire, retire/create, and competing candidate races serialize safely |
| Replay | Original result is returned; no duplicate canonical side effects |
| History | Current pointer and immutable snapshots reconstruct the retirement chain |
| Authority | Assessment is evidence; only trusted Operator approval can commit |
| Regression | Existing B5.1 and create/revise/revalidate/review behavior remains intact |

**Agent coding-side handoff (only after explicit B5.2 implementation authorization):**

1. Create one B5.2 implementation branch from the verified post-documentation `main` merge commit.
2. Implement the checkpoints above in order, with focused tests accompanying each behavior.
3. Keep the implementation in one reviewable PR unless a concrete dependency requires a separately reviewed change.
4. Do not add a migration unless preflight proves the existing schema cannot represent the accepted contract. Stop and report the evidence before changing schema or frozen architecture.
5. Open a draft PR with exact base/head SHAs, changed-file scope, test evidence, and unresolved risks.

**Programmer/local verification-side handoff:**

1. Verify repository root, branch, exact base/head, origin, and clean worktree before synchronization.
2. Review the actual diff and test configuration before executing commands.
3. Run focused B5.2 tests, then the B5.1/lifecycle regression set.
4. Run migrations and the full suite only against a uniquely named disposable PostgreSQL container bound to a dynamic localhost port.
5. Set and restore both `DATABASE_URL` and `TEST_DATABASE_URL`; clean up only the container created by the test.
6. Run Ruff and Mypy using the repository's configured scope.
7. Verify one Alembic head, exact-head hosted CI, clean worktree, restored environment, and disposable-container removal.
8. Report exact commit SHA, test count, warnings, migration revision, and cleanup evidence. Do not claim success from a partial or misconfigured run.

**Stop conditions:** Stop and return to the Operator if any B0/B4 invariant must change; the existing schema cannot represent retirement; a second write path/runtime/dispatcher/authentication boundary is required; retirement changes semantic content or candidate links; predecessor retirement implicitly mutates a candidate; candidate-slot release is premature or incorrect; stale assessment can commit; graph locks cannot serialize races; replay duplicates side effects; or history cannot be reconstructed. Do not weaken acceptance criteria to preserve schedule.

**Definition of done:** B5.2 is complete only when ordinary retirement and candidate cancellation use the existing trusted commit path; retirement is terminal; semantic state is preserved; candidate relation is preserved; pending-slot release and replacement eligibility are proven; predecessor retirement never mutates a pending candidate; stale rejection, concurrency, replay, and history tests pass; B5.1 and wider regression tests remain green; no unapproved migration or architecture expansion exists; exact-head hosted CI and Operator-local full verification pass; documentation is reconciled; and the Operator explicitly accepts the checkpoint.

**Exit:** All B5.2 regression proofs pass, the complete relevant and full suites pass against disposable PostgreSQL, Ruff/Mypy and fresh migration/head checks pass, exact-head hosted CI passes, the diff contains no unauthorized scope expansion, and explicit Operator acceptance is recorded. B5.2 implementation remains separately gated until that authorization is granted.

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

This plan was explicitly accepted by the Operator on 2026-11-13. B5.1 implementation was separately authorized, verified, and merged. The B5.2 documentation checkpoint may refine the existing Retire scope and its verification sequence, but does not authorize production implementation, schema changes, or migrations. B5.2 implementation requires a separate explicit checkpoint authorization. B5.3 and B5.4 remain separately gated. B6 and R7-C remain unauthorized.

## 8. Source authority

This plan is subordinate to and must remain consistent with:

- The accepted R7-B B0.1 design decisions and lifecycle invariants.
- The accepted R7-B B4.0 architecture decision.
- ADR-0032 and the normative lifecycle contracts it records.
- The R7-B implementation plan, Phase B5 and its legal-transition reference.

If this plan conflicts with those accepted sources, stop and resolve the discrepancy before implementation.


## B5.2 implementation review record — 2026-11-13

**Implementation review surface:** PR [#118](https://github.com/abtn/Watch-Architecture-Rev2/pull/118), branch `r7b-b5-2-retire-implementation-20261113`, exact reviewed code head `3d102d8e4a9204580bf187018c51da358aa6c121`. The PR changes seven production modules and three test modules. It adds no migration, model/schema change, Task type, runtime, scheduler, dispatcher, authentication boundary, or retrieval redesign.

**Verified on the exact code head:**
- Operator-local disposable-PostgreSQL migration to `0018_r7b_lifecycle_review_date`; one migration head.
- Ruff passed; Mypy passed for 38 source files.
- Integrated retirement/candidate lifecycle regression passed.
- Full local suite: **962 passed, 113 warnings in 319.76s**. Warnings are Alembic `path_separator` deprecations.
- Disposable PostgreSQL container removed; the verification script reported its final branch/head/worktree checks as passed.
- Hosted GitHub Actions CI run [#43456366139](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/43456366139) completed successfully on the exact code head.

**Diff review:** The implementation routes retirement through the existing proposal, lifecycle assessment, trusted Operator approval, canonical LearningCommit, and TaskRuntime finalization. The retirement commit checks the recorded target snapshot, Team ownership, eligible status, predecessor/successor relation, current pointer, version, content hash, and lifecycle assessment before a status-only CAS to `retired`. The committed snapshot preserves semantic fields and candidate links. Team locking is acquired before the target KnowledgeItem lock. The test-only clock adjustment for the `needs_review` sequence is scoped to the commit call and does not change production clock behavior.

**Acceptance evidence still incomplete:** The integrated test demonstrates ordinary retirement, `needs_review` retirement, already-retired rejection, candidate cancellation and replacement, predecessor retirement without implicit candidate mutation, history reconstruction, semantic immutability, and replay without duplicate Events or Outcomes. The added PR tests do not provide dedicated concurrency proofs for retire-versus-retire, retire-versus-candidate-creation, or competing replacement-candidate attempts. Nor do the added tests independently demonstrate every negative case in the B5.2.1/B5.2.3 matrix (including wrong-Team/malformed-relation and each stale-binding dimension). Existing generic lifecycle tests may cover shared primitives, but they are not treated here as proof of the new retirement paths.

**Disposition:** B5.2.6 execution and exact-head CI are verified. B5.2 is not formally closed. The remaining acceptance proofs and explicit Operator acceptance are required before merge. B5.3, B5.4, B6, R7-C, and R8 remain outside this PR and are not authorized by this record.
