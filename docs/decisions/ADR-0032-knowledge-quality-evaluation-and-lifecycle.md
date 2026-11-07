# ADR-0032 — Knowledge Quality Evaluation and Lifecycle

## Status

**Accepted — 2026-11-04.** The Operator accepted the revised architecture and explicitly authorized R7-A implementation. Acceptance establishes the design direction in this ADR; it authorizes only the bounded R7-A phase described in the R7 entry gate. R7-B B0 design was separately accepted on 2026-11-05; B1 and B2 implementation later received separate written Operator authorization. B1 is merged; B2 Step 1 and Step 2 are accepted and merged; B2 Step 3 is in progress. B3–B6 and R7-C remain unauthorized, as do unrelated Task/write-scope/runtime changes. Acceptance does not itself establish implementation correctness or a local verification result.

**R7-B B0 design acceptance (2026-11-05):** The Operator explicitly accepted the five R7-B B0 decisions, the D1 typed-assessment extension, and the D5 reciprocal-successor/publication-gate amendment recorded below and in the R7-B implementation plan. This is a separately scoped acceptance of R7-B design; it does not rewrite the original 2026-11-04 R7-A acceptance. It authorizes documentation of the frozen design only—not B1–B6 schema, source, test, migration, Task registration, provider, active write-scope, runtime, or R7-C work. B1 requires separate written Operator implementation authorization after B0 documentation closeout.

**Implementation progression (updated 2026-11-07):** B0 documentation closeout is complete. B1 received separate written implementation authorization, was accepted after verification, and merged through PR [#43](https://github.com/abtn/Watch-Architecture-Rev2/pull/43) at `d1a8b88fd930207142304fc9b0b7274de5de4992`. B2 Step 0 inventory/preflight and the `legacy-opaque` compatibility amendment are complete. The Operator separately authorized B2 implementation on 2026-11-06. Step 1 merged through PR [#45](https://github.com/abtn/Watch-Architecture-Rev2/pull/45) at `18595356a3da93b47a8701c7e94fe7dbde098d55`; hosted and Operator-local exact-head verification passed. Step 2 was accepted on 2026-11-07 and merged through PR [#46](https://github.com/abtn/Watch-Architecture-Rev2/pull/46) at `669d2e8140036ea4db07cbc44b33f6baa2e2608d`. Hosted CI run [42347539252](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42347539252) passed fresh migration/single-head checks, Ruff, Mypy (32 source files), 735 tests (74 warnings), and cleanup. Operator-local exact-head verification passed focused tests, Ruff, Mypy, and a separate fresh-disposable-PostgreSQL full-suite-only run (**735 passed, 0 failed**). Step 2 is accepted and merged. B2 Step 3 is in progress on `r7b-b2-step3-history-aware-canonicality`. Hosted CI run [42351625886](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42351625886) passed migration/single-head checks, Ruff, Mypy (32 source files), 737 tests, and cleanup; Operator-local exact-head verification is pending. B3–B6 and R7-C remain unauthorized.

**Predecessors:** ADR-0028 (Knowledge Cores and retrieval), ADR-0029 (Experience Distillation), ADR-0030 (Task lifecycle and Outcomes), and ADR-0031 (R6-E generation provider). R6 is formally complete through R6-G; its closure does not authorize R7.

## 1. Context and current boundary

R6 established the first controlled learning loop:

**durable Task evidence → recorded Evaluation → bounded ExperienceDistiller proposal → proposed LearningChange → explicit Operator decision → canonical KnowledgeItem → regenerable Team Experience projection → later-Task Context.**

R7 addresses a different question: whether the abstractions Watch preserves are well-supported, appropriately scoped, useful when retrieved, and maintained safely as evidence changes.

The current implementation baseline is deliberately narrower than the longer-term architecture:

- R6-G's D9 evaluator is the deterministic ruleset watch.r6g.ingest-source-rules, revision 1, for configured-source ingest_source terminal Outcomes. Its worked result means only that the ingestion execution contract was satisfied. It does not establish source truth, Objective achievement, causation, abstraction quality, or transferability.
- ExperienceDistiller consumes explicitly selected Evaluation IDs and creates a proposed KnowledgeItem create LearningChange. It does not discover an unbounded case set.
- The create-only Operator learning-commit service accepts or rejects those proposals. The persisted LearningChange operation vocabulary includes create, revise, and retire, but the current commit service accepts only create; vocabulary in a constraint is not an implemented or authorized path.
- KnowledgeItem currently has active, needs_review, and retired statuses. The deterministic review_knowledge path owns active → needs_review; retrieval excludes due and unscheduled items. No separate revalidation/reactivation, KnowledgeItem revision, supersession, or retirement commit path is delivered by R6.
- Team Experience is a canonical KnowledgeItem-backed, regenerable projection. Retrieval and Context assembly recheck current canonical eligibility; index rows and similarity rankings are not authority.
- R6-F did not select or authorize a production distillation provider. The Cloudflare provider decision in ADR-0031 applies to R6-E only.

The R7 design must not conflate the initial execution evaluator with later evaluation of knowledge. Nor should it treat two Task IDs, repeated retrieval, a high model confidence value, or fluent prose as proof that a lesson is correct.

## 2. Proposed architectural decisions

The original R7 architecture decisions were accepted on 2026-11-04 for R7-A only. The R7-B D1/D5 design extensions and B0.3 contracts are separately accepted design as of 2026-11-05; their implementation remains gated.

### D1 — Keep execution, abstraction, and knowledge-use assessment distinct (R7-B assessment extension accepted for design only)

Keep three questions and their evidence contracts separate:

1. **Execution conformance:** did a Task satisfy its execution contract? D9 revision 1 answers only its configured-source ingestion question.
2. **Abstraction quality:** does a proposed/current KnowledgeItem faithfully represent its cited canonical evidence, preserve contradictions, and state defensible applicability boundaries?
3. **Knowledge-use result:** what happened in a later Task that had a particular KnowledgeItem version in its exact Context, what did the worker explicitly cite, and what evidence supports or challenges the claimed usefulness?

**Decision:** do not extend the existing Evaluation record to represent abstraction quality. Evaluation is structurally and semantically Outcome-scoped: it requires an Outcome, has the worked/mixed/failed/inconclusive conclusion vocabulary, and its EvidenceLink rows are Evaluation-scoped and point to Outcomes or Signals. Those constraints do not fit a rubric assessment of a proposed KnowledgeItem/LearningChange. Create a dedicated typed KnowledgeQualityAssessment record. It must bind to the exact LearningChange proposal and proposed-state hash (and, for a revision, the exact target ID and expected version), carry a rubric revision, evaluator kind/identity/revision, per-dimension dispositions/findings, and a hash-verified typed evidence basis. It is an assessment record, not commit authority. It may exist before a new KnowledgeItem has been created.

Do not overload EvidenceLink with a new subject kind implicitly. Its current contract is Evaluation-only. The R7-A design must define the smallest typed evidence-reference representation for KnowledgeQualityAssessment and validate Team ownership, source identity, Snapshot hashes, and reference keys.

**Accepted R7-B design extension (2026-11-05; implementation separately gated):** add immutable `KnowledgeRevalidationAssessment` and `KnowledgeLifecycleAssessment` records, distinct from `KnowledgeQualityAssessment` and `KnowledgeUseAssessment`. Revalidation assessment binds the exact item, Team, current LearningChange pointer, content version/hash, rebuilt and verified evidence-basis hash/references, temporal relevance disposition, and evaluator identity/revision. Existing canonical evidence may qualify only while temporally relevant and source-valid; time-sensitive/current-condition claims, expired or changed sources, or material newer/contradictory evidence require new observations. Lifecycle assessment has strict retire/supersede variants bound to the exact proposal and target state; supersede additionally binds the exact successor state and replacement rationale. Neither assessment is commit authority. Assessment Tasks may record only their own typed assessment and Task-attributed Events; only the existing trusted `approve_learning_change` path may commit. These Task contracts remain non-active until separately authorized implementation.

For downstream item-specific usefulness, use a distinct KnowledgeUseAssessment contract in R7-C rather than reusing Evaluation.conclusion. It must bind the exact Task Outcome to validated TaskKnowledgeReference records and the exact exposed item version/hash. Evaluation may remain separate evidence about the Task Outcome; the item-specific judgment must have its own vocabulary (for example helpful, harmful, mixed, no_observed_effect, or insufficient_evidence) and must not make the word worked mean that the knowledge itself worked.

No evaluator result, including a deterministic rule or a model assessment, is an oracle. Each assessment is validated, attributable, versioned, and inspectable; an evaluator proposes findings, while application validation and the trusted Operator path govern canonical changes.

### D2 — Treat distinct Task IDs as the minimum recorded-case threshold, not proof of evidentiary independence

Preserve ADR-0029's existing minimum: a cross-case Pattern, Method, or Playbook proposal must be based on at least two separately recorded Outcomes from distinct source Task IDs, each with its corresponding recorded Evaluation. The two-Task rule is a minimum proposal-eligibility threshold, not proof that the underlying observations are independent, diverse, or transferable.

**Explicit interpretation proposed by this ADR:** ADR-0029's phrase “independently recorded Outcomes” means separately durable and attributable Outcome records from distinct Task IDs. It does not mean statistical independence or independent upstream evidence. This is an explicit clarification/amendment to the ADR-0029 evidence rule upon acceptance of ADR-0032.

Classify each selected case relationship as **independent**, **related**, or **unknown** using available canonical lineage, including source Signal IDs, Snapshot references/hashes, normalized source content, PlanAction identity, repeated underlying events, and common upstream evidence. Shared Team, Objective, or task class alone is not sufficient to classify cases as related. The exact field set and deterministic comparison rules must be frozen in R7-A.

**Related and unknown cases still count toward the two-distinct-Task threshold** when they have distinct source Task IDs and separately recorded Outcomes/Evaluations. They must be labelled and included in the quality assessment; they must not be silently discarded or described as independent. Their relationship limits the strength and scope of any abstraction claim. A repeated Task ID is one case, not two. An exact duplicate/replay of the same Task-attributed Outcome is not a second case.

The quality rubric decides whether the selected evidence supports the proposed abstraction and its claimed breadth. The two-case threshold only permits the proposal to be considered; it does not force acceptance or permit a broad claim from related/unknown evidence.

### D3 — Evaluate abstraction quality with a structured rubric, not one confidence score

A KnowledgeQualityAssessment must address at least:

- **Evidence fidelity:** every material claim is supported by the cited canonical basis and does not exceed what the observations establish.
- **Case coverage and relationship:** the proposal reflects the selected cases and does not overstate their independence or diversity.
- **Contradiction handling:** contrary, failed, mixed, and disconfirming cases are preserved and explained rather than averaged away.
- **Applicability boundaries:** situation, preconditions, non-applicability, failure modes, and assumptions are concrete enough to test.
- **Uncertainty calibration:** missing evidence and uncertainty are explicit; confidence is not inferred from model fluency or case count alone.
- **Specificity and utility:** the abstraction is actionable and falsifiable without claiming a universal rule.
- **Novelty and overlap:** the proposal is compared with current Team Experience so duplicates, conflicts, and possible supersession are surfaced.

Use per-dimension dispositions such as supported, limited, contradicted, and insufficient_evidence, with findings and references. A scalar may be retained as diagnostic data only after calibration is justified; it must not independently authorize acceptance, revision, publication, or retrieval. Application validation remains deterministic for schema, ownership, hashes, references, and lifecycle preconditions. A model-based evaluator, if separately authorized, produces another untrusted assessment proposal.

**Canonical confidence rule:** KnowledgeItem.confidence is a canonical field, not an authorization score. Create may establish its initial value. Only an explicitly proposed and Operator-accepted **revise** operation may change it, with a recorded rationale and evidence basis. Under the accepted R7-B content-hash contract, confidence participates in semantic content identity: a confidence-only revise increments content version, changes the content hash, and clears `last_validated_at`. Revalidation must preserve confidence, content version, and content hash exactly; it is a validity check, not a confidence-promotion path. Supersession, retirement, review scheduling, quality assessment, and downstream-use assessment must not change it. A model-suggested confidence value is never committed without the explicit revise path.

### D4 — Preserve exact knowledge-exposure provenance; add citations, not a duplicate inclusion record

Distinguish four states:

- a candidate returned by retrieval;
- a KnowledgeItem version actually included in the immutable Task Context;
- a specific claim/output that explicitly cites or references that exact version;
- a later assessment of whether the cited knowledge was materially helpful, harmful, or unsupported.

The current Context manifest v2 already records included Team Experience passages with KnowledgeItem ID, version, content hash, and origin LearningChange ID. Reuse that record for inclusion; do not add a second inclusion record. The manifest does not record per-claim citations. The current StrategyProposer output has no per-claim KnowledgeItem citation contract.

**Proposed R7-C resolution:** introduce an application-owned, Task-attributed TaskKnowledgeReference record (or an equivalently typed immutable Event only if it satisfies query and integrity needs). A worker may nominate a reference as untrusted input, but application code must verify that the exact item ID/version/content hash is present in that Task's immutable Context manifest and then write the citation/reference. This follows INV-10's principle that code writes citations, not the model. A citation proves only that the claim referenced an included item; it does not prove material use or benefit.

A KnowledgeUseAssessment must bind to the exact Task, terminal Outcome, Context Snapshot/hash, TaskKnowledgeReference, KnowledgeItem ID/version/content hash, and the current accepted LearningChange identity captured for that version. Do not infer a citation from inclusion, use from retrieval, or causation from citation or Task success. Retrieval candidates not selected into Context may be observed in benchmark instrumentation; they are not inclusion or citation evidence.

### D5 — Extend the existing LearningChange path with a reconstructable current-state chain (original architecture accepted 2026-11-04; R7-B extension accepted for design 2026-11-05)

Every canonical KnowledgeItem lifecycle change remains behind a proposed LearningChange, application validation, and explicit trusted Operator approval through the host-invoked adapter. Do not create a second write path.

The current schema is not sufficient for the proposed lifecycle as written: KnowledgeItem has an immutable origin_learning_change_id but no pointer to its latest accepted transition; LearningChange has one target_id; its database operation vocabulary is create/revise/retire; and the commit service, operator admission, canonicality helper, Context assembly, and TaskRuntime approval finalization are create-only. An accepted revision would no longer match the create LearningChange that currently establishes canonicality.

**Required current-state chain:** retain origin_learning_change_id as the immutable create provenance and add current_learning_change_id to KnowledgeItem. On create, both point to the accepted create LearningChange. On every accepted LearningChange lifecycle transition (revise, revalidate, supersede, retire), update current_learning_change_id atomically to that accepted transition. The current pointer must resolve to an accepted same-Team LearningChange whose committed state establishes this item: for the original create, target_id is NULL and the committed state identifies this new item; for later transitions, target_id equals this KnowledgeItem ID. Its committed_state must match the current canonical row. Each accepted LearningChange's previous_state and committed_state are immutable full snapshots sufficient to reconstruct the transition history. If R7-A/B cannot prove complete reconstruction from those snapshots plus the current pointer, the design must add the smallest append-only version-history record rather than relying on timestamps or “latest row” ordering.

The KnowledgeItem content version has explicit semantics: create starts at version 1; revise increments the content version; revalidate, supersede, and retire change lifecycle state but do not change the content version/hash. The current LearningChange pointer still advances on each accepted lifecycle operation. A new Context manifest version must capture both origin and current LearningChange identity for included Team Experience passages; preserve immutable Context manifest v1/v2 replay.

Proposed lifecycle operations:

| Operation | Proposed canonical effect | Required guard |
|---|---|---|
| create | Create a new active KnowledgeItem at content version 1; origin and current pointers both reference the accepted create change. | Same-Team evidence, exact proposal hash, quality assessment, trusted Operator decision, pinned review policy. |
| revise | Update the same KnowledgeItem ID, increment content version, preserve origin, and advance current_learning_change_id. | Exact target ID/current pointer/expected content version; immutable previous/proposed/committed snapshots; quality assessment; atomic compare-and-set. Only this operation may change confidence after creation. |
| revalidate | Move needs_review to active without changing content, content hash, content version, or confidence; advance current_learning_change_id and update last_validated_at/review_after. | Fresh/rechecked evidence, typed revalidation assessment, explicit Operator decision, exact current pointer, pinned review policy. No scheduler-only reactivation. |
| supersede | Retire the predecessor and set its superseded_by_id to an already accepted, active, same-Team successor. The successor is not modified by this operation. | LearningChange targets the predecessor; exact predecessor pointer/version; successor's current canonical state verified; no self-link/cycle; a successor may have at most one predecessor; atomic predecessor status/link/history update. |
| retire | Retire the item without a successor. | Explicit reason/evidence, exact target ID/current pointer/version, explicit Operator decision; terminal transition. |

**Supersession is not a fourth KnowledgeItem status.** Keep the existing status vocabulary active/needs_review/retired. A superseded predecessor is status retired with a validated successor link; an ordinarily retired item has no successor link. The accepted LearningChange operation distinguishes supersede from retire. The proposed LearningChange operation vocabulary becomes create/revise/revalidate/supersede/retire, and every non-create operation targets one existing KnowledgeItem ID. Supersession does not require a two-item LearningChange: the successor must already exist as a separately accepted canonical item, and the supersede transaction changes only the predecessor plus its pointer/history. If a future design requires creating and superseding in one transaction, that is a different multi-target operation and must be separately designed; do not pretend the current single target_id can atomically express two item writes.

**Consumer changes are mandatory, not optional follow-up tests.** R7-B must update the canonicality check used by Team Experience indexing/retrieval and Context assembly; the create-only LearningChange checks in OperatorApplicationAdapter and LearningCommitService; and the TaskRuntime approval-Task request/finalization validation that currently insists on operation=create. Each must validate the current pointer, exact target, operation-specific preconditions, current committed-state match, policy pin, and same-Team ownership. A stale projection must immediately become ineligible after any canonical transition.

### D5 amendment — reciprocal successor fields and pending-successor publication gate (accepted R7-B design, 2026-11-05)

**Acceptance boundary:** this amendment is accepted as R7-B design. B1 and B2 implementation have separate Operator authorization; B2 Step 2 is the current bounded implementation slice. This does not authorize B3–B6, unrelated Task registrations, providers, active write scopes, runtime changes, or R7-C.

A lifecycle-aware KnowledgeItem carries two reciprocal, same-Team references:

- `supersedes_item_id` on a successor identifies its predecessor. It is set in the successor's accepted create and is immutable.
- `superseded_by_id` on a predecessor identifies its accepted successor. It is set only by the predecessor's accepted supersede LearningChange.

A successor with non-null `supersedes_item_id` is accepted but withheld from retrieval and Context assembly until its predecessor is retired and its `superseded_by_id` points back to that successor. The supersede LearningChange targets and modifies the predecessor only; it never writes the successor. Retrieval and Context assembly validate both directions against canonical current state and D7 eligibility at read time. Enforce same-Team ownership, no self-links, no cycles, at most one non-retired pending candidate per predecessor, and at most one committed successor. A retired candidate keeps its immutable historical predecessor reference but no longer occupies the pending-candidate slot.

**Candidate creation guards:** candidate creation is permitted only when the predecessor is canonically valid and D7-eligible: `active`, timezone-aware UTC `review_after` later than the creation-time check, valid current pointer/content hash, same Team, no committed successor, and no other non-retired pending candidate. A predecessor already in `needs_review` must be revalidated before a *new* candidate is created. The candidate's own review date, computed from the approval Task's pinned TeamPolicy and canonical commit time, must be non-null and future; if the policy has no review interval, reject candidate creation. The relation is part of the proposed-state hash, not the semantic content hash.

At supersession commit, the successor must be accepted, canonical, same-Team, `active`, and have a non-null future UTC `review_after`; its current pointer, content version, content hash, and full-state binding must still match the proposal and lifecycle assessment. The predecessor's exact current pointer, version, and actual status must match its fresh proposal/assessment. The predecessor may be `active` or `needs_review`; a `needs_review` predecessor is retired by supersession and is not revalidated by that operation. A successor in `needs_review`, with NULL/due review date, or with stale binding blocks supersession without changing the predecessor.

**Visibility invariant:** predecessor and candidate are never both exposed. The predecessor is exposed only while its own D7 eligibility holds. If it becomes due or enters `needs_review` while a candidate remains pending, neither may be retrievable until the reciprocal supersession gate is satisfied. That temporary absence is acceptable.

**Abandoned-candidate rules:**

- Retire an abandoned candidate through an ordinary retire LearningChange with a retire-variant KnowledgeLifecycleAssessment. Keep `supersedes_item_id` immutable.
- A replacement candidate may be created only after the prior candidate is retired and only while the predecessor again passes every candidate-creation guard.
- If the predecessor is revised or revalidated before supersession, the candidate remains withheld and any proposal/assessment whose bound predecessor state changed is stale; create a new proposal/assessment bound to the new pointer/state.
- If scheduled `review_knowledge` moves the predecessor from `active` to `needs_review` while a candidate is pending, the candidate remains withheld and assessments bound to the former status are stale. A fresh supersede proposal/assessment may proceed from the predecessor's actual `needs_review` state only if every supersede-specific guard holds and the successor remains accepted, active, canonical, and D7-eligible. This does not revalidate the predecessor.
- If the predecessor is retired without supersession, the candidate remains permanently withheld and must be retired separately. It is never mutated automatically.
- If the successor is revised or revalidated, its old supersede proposal/assessment is stale and must be refreshed. If it is retired, it can never become the committed replacement.

Stale is a derived application disposition, not a LearningChange status. LearningChange remains `proposed / accepted / rejected`; proposals and assessments remain immutable and cannot pass approval-time pointer/state validation once stale. Cleanup uses the existing trusted rejection path, never an autonomous Task.

Graph mutations (candidate creation, supersede, and retirement of a candidate) require a Team-scoped transaction lock before graph inspection or writes. Lock the Team row with `SELECT ... FOR UPDATE` first, then affected KnowledgeItem rows in ascending UUID order. Every graph-changing path uses this lock order; per-item operations also compare-and-set the exact current pointer and version. Retrieval and Context assembly validate reciprocity against one consistent canonical snapshot. Context's final validation must not rely on a previously returned retrieval result alone.

**Accepted R7-B integrity decisions:**

1. **Semantic content hash:** hash exactly `kind`, `title`, `statement`, `body`, `applicability`, `preconditions`, `assumptions`, `limitations`, `non_applicability`, `failure_modes`, `known_counterexamples`, `missing_information`, `uncertainty`, and `confidence`. Exclude item/Team identity, status, content version, validation/review dates, origin/current pointers, and both supersession links. Preserve the stored order of all arrays; do not sort them as sets. A confidence-only revise changes the hash and clears `last_validated_at`; revalidation preserves confidence, version, and hash.
2. **Hash scheme and projection transition:** new Team Experience projections and Context manifest v3 entries identify `content_hash_scheme`; the new content domain separator is `watch.r7b.knowledge-content.v2`. By the Operator-accepted amendment of 2026-11-06, all pre-existing Team Experience projection rows must receive the `legacy-opaque` storage disposition (not a hash algorithm), retain a NULL `current_learning_change_id`, and have their index state marked `stale` by the B2 migration. They must remain ineligible for retrieval until a normal successful republish writes v2 provenance. Existing hashes, chunks, embeddings and metadata are preserved unchanged. No universal legacy projection-hash verifier is assumed.
3. **Full-state snapshot:** the versioned envelope contains every semantic and lifecycle field, including explicit NULLs, origin/current pointers, both supersession links, and `snapshot_version`. Use `core.state_assessment._canonical_json` after normalization: UUIDs are lowercase hyphenated strings; Decimal values are fixed-point strings without exponents and never JSON floats; timestamps are timezone-aware UTC ISO-8601 with `Z` and exactly six fractional digits; naive timestamps are rejected. Preserve array order. Snapshot domain separator: `watch.r7b.knowledge-item-state.v1`.
4. **Hash framing:** SHA-256 over UTF-8 domain-separator bytes, one NUL byte (`0x00`), and UTF-8 canonical JSON bytes; exclude the hash field itself. Store `sha256:<64 lowercase hex characters>`.
5. **Legacy decoder:** historical create snapshots are immutable and lack `snapshot_version`, `current_learning_change_id`, `supersedes_item_id`, and `superseded_by_id`. Decode only the exact historical create shape. Treat `current_learning_change_id = origin_learning_change_id` as reconstructed from the validated backfill; reconstruct both supersession links as NULL. Preserve recorded `origin_learning_change_id`. Mark every reconstructed value as legacy-derived, never as a field actually recorded in the old snapshot.
6. **Approval fingerprint:** bind Team, target ID, expected current pointer, content version, status, operation, proposal hash, proposed-state hash, pinned TeamPolicy version, evidence references and evidence-basis hash, assessment payload hashes, expected content hash and full-state snapshot hash, and (for supersede) the exact successor ID/pointer/version/content hash/status/review date. The typed host-supplied Operator issuer/subject identity is available before the request Event in the existing adapter and remains bound in the immutable request fingerprint and committed decision record. Reuse of the same host idempotency key with a different principal conflicts. Actor identity is not content identity.
7. **Staleness:** there is no persisted `invalidated` or `stale` LearningChange status. Stale is a derived application disposition. Old proposals and assessments remain immutable; mismatched expected state cannot be accepted; new proposals/assessments bind current state; cleanup uses the trusted rejection path.
8. **Revalidation freshness:** verified re-examination of existing canonical evidence may qualify only while it remains temporally relevant and source-valid for the claim. Rebuild the evidence basis at assessment time; verify canonical references, Team ownership, source hashes, and applicable provenance/quote constraints; bind the assessment to current content version/hash. Time-sensitive/current-condition claims, expired or changed sources, and material newer/contradictory evidence require new observations. A timestamp alone never establishes freshness.
9. **D7 review Events and Context:** new `knowledge_items_reviewed` Events carry the current LearningChange pointer. Legacy Events without it are accepted only on one unique match through durable Task/Event provenance and recorded item state; ambiguity fails closed. New Context manifest v3 records origin/current LearningChange identity and content-hash scheme for each included Team Experience passage. Manifest v1/v2 replay remains immutable under its existing Context snapshot/Event validation; it does not recalculate KnowledgeItem content hashes. Do not infer a content-hash scheme from manifest version or rewrite historical Context payloads. An embedded historical passage hash remains opaque data in that immutable record.
**Operator-accepted B0.3 compatibility amendment (2026-11-06):** Step 0 inspection found that the pre-B1 content hash used a pre-B1 21-field state representation, while the post-B1 helper uses a normalized 24-field state representation including current-pointer/supersession fields. Existing projection rows persist no discriminator for which calculation produced their hash; the persistent `watch` database was not inspected, so the actual distribution is unknown. The Operator accepted the following fail-closed disposition: mark all pre-existing Team Experience projection rows `legacy-opaque`, leave their current-pointer pin NULL, and mark index-state rows stale; preserve hashes, chunks, embeddings and metadata unchanged; prohibit retrieval until ordinary republish produces a v2 projection. `legacy-opaque` denotes a storage disposition, not a digest algorithm. Historical Context manifest v1/v2 replay stays byte-exact under its existing immutable snapshot/Event validation and does not require or imply a legacy KnowledgeItem content-hash verifier. Historical LearningChange snapshot hashes continue to use their separate snapshot decoding/verification rules. This amendment changes the original B0.3 compatibility wording. B2 implementation was separately authorized by the Operator on 2026-11-06; this amendment does not authorize B3–B6 or R7-C.

10. **Typed assessment authority:** `KnowledgeRevalidationAssessment` and `KnowledgeLifecycleAssessment` are immutable. Their recording Tasks may write only their own typed assessment and Task-attributed Events; no assessment Task, worker, model, indexer, or retrieval path writes KnowledgeItem or LearningChange. The trusted `approve_learning_change` Task remains the sole lifecycle commit authority. No model score becomes commit authority.
### D6 — Preserve review scheduling and canonical-versus-projection authority

The accepted ADR-0029 D7 rules remain the baseline:

- The review interval is optional, positive, non-boolean, and read from the TeamPolicy version pinned by the committing Task.
- review_after is timezone-aware UTC and computed from the canonical commit time.
- NULL and due items are ineligible for retrieval.
- The scheduled review_knowledge Task may only perform active → needs_review.
- Revalidation and reactivation are separate explicit LearningChange operations.

For accepted create, revise, and revalidate operations, calculate review_after from that operation's canonical committed_at and the approval Task's pinned TeamPolicy. A missing interval yields NULL and therefore no retrieval eligibility; a revalidation must never make an unscheduled item appear eligible. A later TeamPolicy version must not silently rewrite existing KnowledgeItem review dates. TeamPolicy changes remain a separate explicitly authorized policy operation, never an automatic consequence of knowledge evaluation.

On every accepted canonical transition, stale projection rows must cease to be eligible immediately. Projection update/rebuild is a separate, idempotent operation; projection failure cannot roll back the canonical Operator decision or cause stale content to be advertised as current. In particular, revalidation from needs_review to active does not reactivate old ineligible chunks: the exact current item version/hash/current-LearningChange pointer must be republished and revalidated before retrieval can expose it.

The scheduled review Task is the only exception to the LearningChange lifecycle path: it may make the status-only active → needs_review transition and emit its Task-attributed Event, but it may not edit content/confidence, change review_after, or reactivate/retire/supersede the item.

### D7 — Make retrieval quality measurable without treating ranking as truth

Create a fixed, versioned retrieval benchmark with reviewed queries and expected relevant, irrelevant, forbidden, and stale/due candidates. Cover lexical and semantic matches, exact concepts, applicability constraints, counterexamples, and negative queries. Keep Team/domain isolation and current canonical eligibility as hard correctness constraints.

**Small-n and label provenance:** the current real R6 evidence base is narrow and primarily configured-source ingestion. R7-C may use synthetic items/queries to exercise retrieval behavior, but synthetic results must be labelled as synthetic and must not be presented as evidence of real-world retrieval generalization. Every benchmark label must record its provenance (synthetic fixture, canonical-derived, or human/operator reviewed), rationale, corpus revision, and reviewer/source reference. Keep tuning examples separate from held-out evaluation examples. With a small or synthetic corpus, report per-query outcomes, raw counts, and descriptive Precision@k/Recall@k; do not imply statistical significance, broad coverage, or population-level generalization. Add MRR/nDCG only where graded labels justify them.

Establish a reproducible baseline using the existing PostgreSQL full-text/vector hybrid retriever and current bounds. Report ranking measures separately from hard-failure counts for cross-Team leakage, stale/due/retired/superseded-predecessor inclusion, and provenance mismatch. No metric or similarity score becomes a truth score. Do not add a reranker, external vector service, or relax the existing Context passage/character budget unless a measured benchmark and separate decision justify it.

### D8 — Keep provider, Task, identity, and security choices separately gated

R7 does not inherit provider approval from R6-E. No production R6-F distillation provider was approved, and ADR-0031 authorizes Cloudflare only for R6-E. Any production model used for R7 must receive a separate provider/model/data-handling/rate-card decision before live invocation. Reuse Task-attributed maximum reservation and reconciliation; unknown or overrun usage fails closed.

All R7 work must use ordinary Tasks, exact Task write scopes, the existing TaskRuntime, attempt fencing, replay, and application validation. The host remains the authentication root for Operators. Assessment Tasks may only record their own typed assessment/reference proposals; they cannot write LearningChange or KnowledgeItem. Lifecycle approval remains a trusted Operator decision through the existing host-supplied identity boundary. Do not add a second runtime, general dispatcher, Watch-owned authentication stack, autonomous approval, automatic TeamPolicy mutation, or direct model writes.

## 3. Proposed lifecycle and quality flow

1. Select a bounded, explicit set of canonical cases and record the selection rule/version.
2. Rebuild the complete evidence basis from canonical Outcomes, recorded Evaluations, Events, EvidenceLinks, immutable Snapshots, and exact Context manifests where relevant.
3. Classify case lineage as independent, related, or unknown; include related/unknown cases in the two-distinct-Task minimum and make their limitations visible.
4. Produce a versioned KnowledgeQualityAssessment for the exact LearningChange candidate and proposed-state hash. Preserve rubric dimensions, evidence references, evaluator identity/revision, contradictions, and missing evidence.
5. Revalidate all references, ownership, hashes, evaluator identity/revision, target/current LearningChange pointer, policy pin, and Task scope in application code.
6. Present the LearningChange proposal to the trusted Operator through an ordinary Task and the host identity boundary.
7. On acceptance, commit one atomic LearningChange and canonical KnowledgeItem transition. On rejection, record the reason without changing canonical knowledge.
8. Invalidate/update the regenerable projection independently. Retrieval returns only the current eligible canonical state; revalidation requires a fresh current projection before exposure.
9. When a later Task explicitly cites an included item, application code validates the reference against the immutable Context manifest and writes the TaskKnowledgeReference. Inclusion itself is already captured by the manifest and does not create a duplicate record.
10. Where a later Task has a validated item reference, assess its outcome with a KnowledgeUseAssessment bound to the exact Outcome, Context, item version/hash, and citation. Preserve alternative explanations; do not assert causation.

No transcript, retrieved chunk, vector rank, model confidence, or free-form self-reflection becomes canonical evidence.

## 4. Required decisions before implementation

R7-A is authorized. Its implementation contracts are frozen in [the R7-A implementation plan](../development/r7-a-implementation-plan.md): (1) exact case-lineage field/normalization/rule definitions and `independent`/`related`/`unknown` truth table; (2) KnowledgeQualityAssessment schema, evidence-reference contract, rubric revision/disposition rules, stable evaluator identity/revision and assessment Task lifecycle/idempotency; (3) deterministic application validation and the exact create-approval gate that enforces the accepted INV-12 amendment; and (4) deterministic fixtures, failure/replay tests, and the no-provider boundary. The following later-phase decisions remain intentionally deferred and are not R7-A blockers:

1. **Knowledge-use trace (R7-C):** TaskKnowledgeReference schema, claim identity, exact Context-manifest binding, KnowledgeUseAssessment vocabulary/recording contract. Reuse Context manifest v2 for included passages; do not duplicate inclusion.
2. **KnowledgeItem version history and lifecycle (R7-B):** the Operator accepted the B0 design decisions and D1/D5 extensions on 2026-11-05. The frozen design covers current-pointer history, the exact legacy snapshot decoder, versioned semantic/full-state hashes, confidence participation, the bounded evidence-freshness rule, trusted Operator identity in the approval-request fingerprint, reciprocal pending-successor publication gating, typed lifecycle/revalidation assessments, D7 overlays, Team-scoped graph serialization, and Context v3/projection pins. Snapshot-first reconstruction remains conditional on B1 proof; if that proof fails, stop and seek a separate Operator decision on the smallest append-only history record. The [R7-B implementation plan](../development/r7-b-implementation-plan.md) is the detailed phase authority. B0 design acceptance does not authorize implementation; B1–B6 require separate written Operator implementation authorization.
3. **Retrieval benchmark (R7-C):** corpus ownership/size, label provenance, synthetic/real separation, held-out split, small-n reporting, and hard-zero scope/status/provenance checks.
4. **Provider/cost (separately gated):** any production provider/model, data handling, rate card, maximum reservation, and failure semantics. No provider is selected by this ADR.

**Accepted INV-12 amendment (effective 2026-11-04):** Team memory changes remain possible only through the authorized learning path. Creating, revising, revalidating, superseding, or retiring a KnowledgeItem requires a proposed LearningChange, operation-specific evidence and assessment, application validation against the exact current target/pointer/version, and a committed trusted-Operator decision through the authorized Task. Create retains its recorded Evaluation or explicit Operator-seed evidence basis and additionally requires the R7 KnowledgeQualityAssessment gate when that gate is in force. Revise requires a KnowledgeQualityAssessment bound to its exact proposed state. Revalidate requires fresh/rechecked evidence and a typed revalidation assessment, and must preserve content, content hash, content version, and confidence. Supersede requires a separately accepted same-Team successor plus an explicit predecessor link; retire requires reason/evidence and no successor. No assessment Task, worker, model, indexer, or retrieval path may write KnowledgeItem directly. TeamPolicy changes remain separate and require explicit Operator approval. The only scheduled-maintenance exception is review_knowledge performing status-only active → needs_review; it cannot change content/confidence, extend review dates, or reactivate an item. No other write path exists.

R7-A remains limited to its frozen implementation plan and completed scope. The R7-B D1/D5 design extension and B0.3 integrity contracts above were accepted for design on 2026-11-05. B1 was separately authorized, accepted, and merged on 2026-11-06. B2 implementation was separately authorized on 2026-11-06; Step 1 is complete and merged, and Step 2 implementation and verification are complete in PR #46. Step 2 is accepted and merged; B2 Step 3 is in progress. B3–B6 and R7-C remain unauthorized.

## 5. Non-goals

R7 does not implement multi-Team knowledge sharing or cross-domain transfer; broad World-memory or general-purpose evidence graphs; autonomous learning acceptance; autonomous TeamPolicy changes; automatic confidence promotion; model training or fine-tuning; self-modifying Kernel/runtime behavior; a new Task runtime, scheduler, dispatcher, or workflow engine; a separate vector database or reranker by default; or an unbounded transcript-memory system.

## 6. Consequences and alternatives

This direction makes quality a question with inspectable evidence, not a confidence number. It makes canonical lifecycle history reconstructable, keeps inclusion separate from citation/use, and preserves explicit Operator authority.

Rejected alternatives:

- Reuse D9 worked as a positive knowledge-quality label: rejected because it means only execution-contract conformance.
- Reuse the current Evaluation/EvidenceLink schema for abstraction quality: rejected because it is Outcome-scoped and its conclusion/subject constraints do not represent a KnowledgeItem/LearningChange rubric.
- Treat two Task IDs as proof of independent evidence: rejected because distinct durable records can share upstream sources, Plans, or the same underlying event.
- Drop related/unknown cases silently: rejected because it hides evidence selection and can overstate independence.
- Add a superseded KnowledgeItem status while retaining no two-item relation: rejected; use retired plus an explicit validated successor pointer.
- Let the distiller approve or revise its own KnowledgeItem: rejected by INV-12 and the proposal/commit authority boundary.
- Use retrieval similarity or a single quality score as truth/commit authority: rejected because ranking and heuristic scores are derived signals.
- Add a broad knowledge graph, generic scheduler, or new runtime to make R7 convenient: rejected as disproportionate and outside the established architecture.

**Implementation boundary:** the original ADR-0032 architecture was accepted on 2026-11-04 for R7-A. The R7-B D1/D5 design extensions and B0.3 integrity contracts were separately accepted for design on 2026-11-05. R7-A and B1 are complete and merged. B2 implementation was separately authorized on 2026-11-06; Step 1 and Step 2 are accepted and merged. Step 3 is in progress within the accepted B2 sequence. B3–B6 require separate later authorization. R7-C remains separately gated and unauthorized.

