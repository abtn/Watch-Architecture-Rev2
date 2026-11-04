# R7-B — Canonical KnowledgeItem Lifecycle: Implementation Preparation

## Status and authority

**PREPARATION ONLY — R7-B implementation is not authorized.**

R7-0 is complete, ADR-0032 is Accepted, and R7-A is complete and merged. This is a technical preparation proposal; it does not amend the ADR, activate Task write scopes, authorize code/schema changes, or start R7-B. The Operator must resolve §10 and separately authorize implementation. R7-C remains separately gated.

## 1. Objective and scope

Implement revise, revalidate, supersede and retire through the existing LearningChange, trusted Operator and TaskRuntime boundaries. Preserve stable item identity, immutable provenance, complete history, Team isolation, D7 review rules and fail-closed retrieval.

TaskRuntime remains the sole Task lifecycle authority; the host remains the authentication root; LearningCommitService remains the only canonical KnowledgeItem commit path. No second runtime, dispatcher, scheduler, public API/auth stack or worker direct-write path.

R7-B excludes R7-C citations, TaskKnowledgeReference, KnowledgeUseAssessment, retrieval benchmark, reranking and cross-Team transfer.

## 2. Verified post-R7-A baseline

R7-A merged through PR #39 on 2026-11-04:
- Merge commit: `75122a7b34c15e2445b81a2a719020667b55bf06`.
- Tested PR head: `47ffa532dacbc10b146ac7b0768302761a2a0b1b`; same Git tree as merge: `378aabcc376df5b0a44d2602e2790bcbb879618f`.
- Migration head: `0014_knowledge_quality`.
- Hosted exact-head CI [41844600681](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41844600681): PASS.
- Operator-local disposable PostgreSQL on same tree: 631 passed in 79.22s; fresh migration/single head, Ruff, Mypy (31 files), environment restoration and container cleanup passed.

| Concern | Current code | R7-B consequence |
|---|---|---|
| LearningChange operations | DB vocabulary create/revise/retire; service/guards remain create-only. | Add revalidate/supersede to vocabulary/target constraints; schema strings do not authorize operations. |
| KnowledgeItem identity | Stable ID, version, confidence, active/needs_review/retired, immutable origin_learning_change_id; no current/successor pointer. | Add current_learning_change_id and superseded_by_id with same-Team constraints/backfill. |
| LC history | previous_state/committed_state snapshots exist. | Prove deterministic chain from snapshots/current pointer; never infer via timestamps/latest-row ordering. |
| Commit/approval | LearningCommitService, OperatorApplicationAdapter and TaskRuntime guards are create-only. | Extend same path with operation-specific validation, request binding, admission/finalization/recovery and replay. |
| Assessment | R7-A KnowledgeQualityAssessment is immutable and create-scoped. | Reuse for revise against exact proposed state; keep revalidation semantically distinct. |
| Canonicality | Index/context helper requires accepted create at origin pointer. | Replace create-only assumptions with operation-aware current-chain validator. |
| Projection | TeamExperienceChunk/IndexState pin origin, version/hash, not current LearningChange. | Pin current pointer; old publications become ineligible immediately after pointer changes. |
| Context | Manifest v2 records item ID/version/hash/origin. | Add v3 with origin/current LearningChange IDs; preserve v1/v2 replay. |
| Review | review_knowledge only active → needs_review; D7 review_after uses pinned policy. | Preserve scheduling; only accepted revalidate may reactivate. |

Mandatory preflight: core/models.py, core/learning_commit.py, core/operator_application.py, core/task_runtime.py, core/knowledge_index.py, core/context_assembly.py, core/knowledge_quality.py, core/knowledge_quality_tasks.py, core/experience_distiller.py, migrations, Task specs, invariants and focused tests.

## 3. Canonical lifecycle semantics

ADR-0032 is normative:

| Operation | Canonical effect | Required guard/version semantics |
|---|---|---|
| create | Create item at version 1. | Existing R7-A path. Origin/current identify accepted create; exact recorded KnowledgeQualityAssessment required. |
| revise | Update same item ID; advance current pointer. | Exact Team/target/current pointer/version/hash/status. Increment content version once; preserve origin. Only revise may change confidence. Require KQA bound to exact revised proposal. |
| revalidate | needs_review → active; advance current pointer. | Fresh evidence, typed revalidation assessment, Operator approval, exact target/pointer/version/hash, pinned TeamPolicy. Preserve content/hash/version/confidence/origin; set last_validated_at from committed_at and recompute review_after from pinned policy. |
| supersede | Retire predecessor; set superseded_by_id to already accepted active same-Team successor. Advance predecessor pointer only. | Successor is not modified. Validate exact predecessor, canonical successor, no self/cycle, at most one predecessor per successor. No new status. |
| retire | Retire item without successor; advance current pointer. | Exact target/pointer/version/hash; non-empty reason/evidence. Preserve content/confidence/version/origin; successor pointer remains NULL. Retired is terminal. |

**Recommended revise behavior — pending Operator disposition:** preserve status on revise (active remains active; needs_review remains needs_review), clear last_validated_at after content changes, recompute review_after from canonical commit time and approval Task's pinned TeamPolicy. Revise cannot implicitly reactivate. Only revise may change confidence.

## 4. Current pointer and immutable history

- Keep origin_learning_change_id immutable and bound to accepted create.
- Add current_learning_change_id, same-Team FK to LearningChange(id, team_id), pointing to latest accepted transition—not latest timestamp.
- Add nullable superseded_by_id, same-Team FK to KnowledgeItem(id, team_id), with no-self and one-predecessor-per-successor constraints.
- Keep status active/needs_review/retired. Content version: create=1; revise increments; revalidate/supersede/retire preserve version/hash.

For every accepted non-create transition, under the item row lock and atomically: validate exact pointer/version/status/hash, Team, evidence, assessment, policy, Task scope and Operator; persist full previous_state; apply only permitted fields; advance current pointer; persist full committed_state including pointer; accept LearningChange and attributable Event.

The history must form one reconstructable chain. Missing parents, forks, duplicate transitions from same predecessor, cross-Team links, snapshot mismatch or pointer not resolving to exact committed row fail closed. Never repair/fabricate state.

**Legacy roots:** backfill current pointer to origin only after validating accepted create, committed state and Team. Do not rewrite historic LearningChange snapshots. Explicitly recognize valid legacy roots. If reconstruction cannot be proven, add the smallest append-only history record allowed by ADR-0032; never use timestamps/latest-row selection.

## 5. Schema and migration preparation

Candidate migration: `0015_knowledge_item_lifecycle`; recheck actual graph and revision length at preflight.

Expected: current_learning_change_id composite Team FK; superseded_by_id composite Team self-FK/no-self/unique predecessor; operation/target constraints for create/revise/revalidate/supersede/retire; justified indexes; current pointer on TeamExperienceChunk and TeamExperienceIndexState; validated safe backfill. Fail on inconsistent legacy state.

## 6. Proposal, assessment and trusted Operator path

**Proposal:** extend existing propose_learning_change, not a new runtime. Bind item ID/Team, expected current pointer, version/hash/status, proposed state, evidence hash, idempotency and proposal hash; supersede also binds successor ID/pointer/version/hash. Worker scope remains LearningChange proposal only.

**Revise assessment:** extend assess_knowledge_quality/KQA to support create and revise, preserving seven dimensions. Bind exact proposed state/evidence/target/pointer/version/hash. Independently require correct assessment at Operator admission, TaskRuntime validation/finalization and LearningCommitService. KQA does not satisfy revalidation.

**Revalidation assessment:** recommended distinct immutable KnowledgeRevalidationAssessment and narrow assess_knowledge_revalidation Task, bound to item/current pointer/version/hash/fresh evidence hash/evaluator identity. It records evidence review, not autonomous pass/reactivation. Freeze vocabulary, references, evaluator boundary, Task budget/retry/recovery and deterministic validation before code. Use fakes absent separate provider approval.

**Retire/supersede:** validate target history, Team, reason/evidence and (for supersede) accepted/current/active successor. Resolve whether application checks plus explicit Operator review satisfy INV-12 or typed assessments are necessary.

**Approval:** reuse host-invoked approve_learning_change and typed principal. Bind operation, target, expected pointer/version/hash/status, successor and required assessment IDs/hashes in request Event/fingerprint. TaskRuntime admission/finalization/recovery validates request. LearningCommitService locks/revalidates target/successor and atomically commits LearningChange/item/Event. Rejection leaves item unchanged. Replay is identical; stale competitors lose through TaskRuntime; use deterministic two-row lock order.

## 7. Canonical consumers, projection and Context v3

Update canonicality helper and every consumer: Team Experience index/retrieval, Context assembly, OperatorApplicationAdapter, LearningCommitService and TaskRuntime approval guards. Validate pointer, origin, operation, committed state, version/hash, Team, approval/Task provenance, policy and D7 eligibility.

Add current_learning_change_id to TeamExperienceChunk and TeamExperienceIndexState. A publication is eligible only when current pointer, item ID, version/hash, origin, embedding space and review eligibility match canonical state.

Canonical acceptance and projection publication remain separate. Old revise chunks fail version/hash/pointer checks; revalidated items stay hidden until fresh publication; retired/superseded items excluded immediately despite stale physical rows. Failed indexing never exposes an obsolete publication.

New Context manifest v3 records item ID/version/hash plus origin/current LearningChange IDs. Preserve immutable v1/v2 replay. No R7-C references/KnowledgeUseAssessment.

## 8. Recommended checkpoints

| Checkpoint | Deliverable | Exit proof |
|---|---|---|
| B0 | Source preflight; resolve §10; freeze operation/request schemas. | Operator accepts plan and separately authorizes R7-B; no code before that. |
| B1 | Pointers, operation constraints, safe backfill, history validator/migration tests. | Fresh upgrade; legacy root reconstructs; corrupt/forked/cross-Team history fails; one head. |
| B2 | Targeted proposals, KQA revise, typed revalidation assessment. | Exact pointer/version/hash; stale/replay conflicts reject; no direct item writes. |
| B3 | Trusted approval, TaskRuntime validation, LearningCommitService lifecycle. | Atomic transitions, rejection/concurrency safety, deterministic recovery/replay. |
| B4 | Canonicality consumers, projection current pointer, Context v3. | Stale data never exposed; revalidation needs fresh publication; v1/v2 replay. |
| B5 | Integrated lifecycle fixture across R6-G/R7-A, D7, retries/recovery and retrieval. | Full operation matrix, isolation, history proof and disposable-PostgreSQL full verification. |

Checkpoint split is advisory; phase exit requirements cannot be weakened.

## 9. Required tests

- Safe backfill only for valid accepted create roots; proposed/rejected changes cannot become current.
- Same-Team FKs, pointer/successor constraints, no-self, one predecessor, operation/target checks.
- Reconstruct create→revise→revise and create→revalidate→revise without timestamps; reject missing parents, forks, duplicates, cross-Team refs, mutated snapshots, wrong version/hash and corrupt successor graph.
- Revise preserves status, increments version once, keeps origin, alone may change confidence, requires exact KQA; retired rejected.
- Revalidate only needs_review→active; fresh typed evidence; content/hash/version/confidence/origin unchanged; UTC dates use pinned policy.
- Supersede needs accepted/active/current/same-Team successor; rejects self/cycles/already-linked successor; only predecessor changes.
- Retire needs reason/evidence/no successor; terminal; content/version/hash/confidence unchanged. review_knowledge remains active→needs_review only.
- Missing/stale KQA blocks revise; missing/mismatched revalidation assessment blocks activation.
- Trusted Operator identity/grant rechecked at request and commit.
- Competing operations on one pointer have one winner; loser Task terminalized through TaskRuntime.
- Replay/recovery do not duplicate assessment, LearningChange, Events, Outcome or version.
- Old projections excluded immediately after lifecycle changes; revalidation requires fresh publication.
- Context v3 exact provenance/v1-v2 replay; assembly fails closed on stale history/publication.
- R6-G/R7-A, Team isolation, D7, Context limits/full regressions pass.
- Fresh disposable PostgreSQL only; both DATABASE_URL and TEST_DATABASE_URL target it. Never persistent watch.
- Exact-head hosted CI and Operator-local verification required.

## 10. Decisions required before authorization

Recommendations are not accepted changes:

| Decision | Recommendation | Why resolve it |
|---|---|---|
| Snapshot-chain sufficiency | Prove reconstruction from immutable snapshots/current pointer first; add minimal append-only history only if proof fails. | Avoid duplicate history without weakening reconstruction. |
| Revalidation assessment | Add distinct KnowledgeRevalidationAssessment and narrow assess_knowledge_revalidation Task. | Tests current content against fresh evidence, not abstraction quality. |
| Revise of needs_review | Preserve needs_review; clear last_validated_at on content change. | Prevent implicit D7 reactivation. |
| Retire/supersede assessment | Start with application-validated reason/evidence and Operator decision; add typed assessment only if necessary. | Avoid unnecessary evaluator Tasks while satisfying INV-12. |
| Successor exposure window | Decide whether overlap is acceptable after successor acceptance before predecessor supersession, or ADR-0032 needs a publication gate/coordinated transition. | Single-target supersession does not atomically accept successor and retire predecessor; delayed/abandoned second approval can leave both exposed. |
| History snapshot shape | Freeze serialization, required fields, hashes, predecessor link and legacy root semantics. | Reconstruct exact canonical state. |
| Manifest/projection pins | Add current pointer to chunk/index state and Context v3; preserve v1/v2. | Origin-only metadata cannot prove freshness after pointer change. |
| Approval contract | Bind operation, target, pointer/version/hash/status, successor and assessment IDs/hashes in Event/fingerprint. | Prevent approval/replay against another state. |
| Review dates | Preserve D7 pinned policy, UTC commit time and NULL/due exclusion; decide needs_review revise behavior. | Prevent accidental eligibility changes. |

Any unresolved decision affecting schema, authority, eligibility or concurrency is a stop condition. Operator may accept/revise or request narrow design review.

## 11. Non-goals and phase boundary

No code, tests, migrations, provider wiring, Task grants, runtime/dispatcher/scheduler/API/auth, direct worker writes, TeamPolicy mutation, multi-Team transfer, reranker/vector DB, Context budget change, R7-C citation/KnowledgeUseAssessment/benchmark, or causal use claim.

**Entry gate:** R7-B may be authorized only after Operator resolves/revises §10, source preflight confirms migration/consumer baseline and a separate explicit instruction authorizes implementation. Until then, implementation remains stopped at documentation preparation.