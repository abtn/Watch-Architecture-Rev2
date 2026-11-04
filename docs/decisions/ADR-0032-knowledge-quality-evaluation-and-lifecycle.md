# ADR-0032 — Knowledge Quality Evaluation and Lifecycle

## Status

**Accepted — 2026-11-04.** The Operator accepted the revised architecture and explicitly authorized R7-A implementation. Acceptance establishes the design direction in this ADR; it authorizes only the bounded R7-A phase described in the R7 entry gate. R7-B and R7-C, lifecycle commits, production providers, and unrelated Task/write-scope changes remain unauthorized. Acceptance does not itself establish implementation correctness or a local verification result.

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

The following are proposed resolutions for Operator review. Until accepted, they are design guidance only.

### D1 — Keep execution, abstraction, and knowledge-use assessment distinct

Keep three questions and their evidence contracts separate:

1. **Execution conformance:** did a Task satisfy its execution contract? D9 revision 1 answers only its configured-source ingestion question.
2. **Abstraction quality:** does a proposed/current KnowledgeItem faithfully represent its cited canonical evidence, preserve contradictions, and state defensible applicability boundaries?
3. **Knowledge-use result:** what happened in a later Task that had a particular KnowledgeItem version in its exact Context, what did the worker explicitly cite, and what evidence supports or challenges the claimed usefulness?

**Decision:** do not extend the existing Evaluation record to represent abstraction quality. Evaluation is structurally and semantically Outcome-scoped: it requires an Outcome, has the worked/mixed/failed/inconclusive conclusion vocabulary, and its EvidenceLink rows are Evaluation-scoped and point to Outcomes or Signals. Those constraints do not fit a rubric assessment of a proposed KnowledgeItem/LearningChange. Create a dedicated typed KnowledgeQualityAssessment record. It must bind to the exact LearningChange proposal and proposed-state hash (and, for a revision, the exact target ID and expected version), carry a rubric revision, evaluator kind/identity/revision, per-dimension dispositions/findings, and a hash-verified typed evidence basis. It is an assessment record, not commit authority. It may exist before a new KnowledgeItem has been created.

Do not overload EvidenceLink with a new subject kind implicitly. Its current contract is Evaluation-only. The R7-A design must define the smallest typed evidence-reference representation for KnowledgeQualityAssessment and validate Team ownership, source identity, Snapshot hashes, and reference keys.

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

**Canonical confidence rule:** KnowledgeItem.confidence is a canonical field, not an authorization score. Create may establish its initial value. Only an explicitly proposed and Operator-accepted **revise** operation may change it, with a recorded rationale and evidence basis. Revalidation must preserve confidence exactly; it is a validity check, not a confidence-promotion path. Supersession, retirement, review scheduling, quality assessment, and downstream-use assessment must not change it. A model-suggested confidence value is never committed without the explicit revise path.

### D4 — Preserve exact knowledge-exposure provenance; add citations, not a duplicate inclusion record

Distinguish four states:

- a candidate returned by retrieval;
- a KnowledgeItem version actually included in the immutable Task Context;
- a specific claim/output that explicitly cites or references that exact version;
- a later assessment of whether the cited knowledge was materially helpful, harmful, or unsupported.

The current Context manifest v2 already records included Team Experience passages with KnowledgeItem ID, version, content hash, and origin LearningChange ID. Reuse that record for inclusion; do not add a second inclusion record. The manifest does not record per-claim citations. The current StrategyProposer output has no per-claim KnowledgeItem citation contract.

**Proposed R7-C resolution:** introduce an application-owned, Task-attributed TaskKnowledgeReference record (or an equivalently typed immutable Event only if it satisfies query and integrity needs). A worker may nominate a reference as untrusted input, but application code must verify that the exact item ID/version/content hash is present in that Task's immutable Context manifest and then write the citation/reference. This follows INV-10's principle that code writes citations, not the model. A citation proves only that the claim referenced an included item; it does not prove material use or benefit.

A KnowledgeUseAssessment must bind to the exact Task, terminal Outcome, Context Snapshot/hash, TaskKnowledgeReference, KnowledgeItem ID/version/content hash, and the current accepted LearningChange identity captured for that version. Do not infer a citation from inclusion, use from retrieval, or causation from citation or Task success. Retrieval candidates not selected into Context may be observed in benchmark instrumentation; they are not inclusion or citation evidence.

### D5 — Extend the existing LearningChange path with a reconstructable current-state chain

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

R7-A is authorized. Before its source implementation, freeze the R7-A-specific contracts in the R7-A implementation plan: (1) exact case-lineage field/normalization/rule definitions and `independent`/`related`/`unknown` truth table; (2) KnowledgeQualityAssessment schema, evidence-reference contract, rubric revision/disposition rules, stable evaluator identity/revision and assessment Task lifecycle/idempotency; (3) deterministic application validation and the exact create-approval gate that enforces the accepted INV-12 amendment; and (4) deterministic fixtures, failure/replay tests, and the no-provider boundary. The following later-phase decisions remain intentionally deferred and are not R7-A blockers:

1. **Knowledge-use trace (R7-C):** TaskKnowledgeReference schema, claim identity, exact Context-manifest binding, KnowledgeUseAssessment vocabulary/recording contract. Reuse Context manifest v2 for included passages; do not duplicate inclusion.
2. **Version history and lifecycle (R7-B):** current_learning_change_id implementation, immutable reconstruction proof, content-version semantics, legal transitions, successor relation, concurrency/replay, canonicality consumers, D7 review dates, and projection invalidation/republishing.
3. **Retrieval benchmark (R7-C):** corpus ownership/size, label provenance, synthetic/real separation, held-out split, small-n reporting, and hard-zero scope/status/provenance checks.
4. **Provider/cost (separately gated):** any production provider/model, data handling, rate card, maximum reservation, and failure semantics. No provider is selected by this ADR.

**Accepted INV-12 amendment (effective 2026-11-04):** Team memory changes remain possible only through the authorized learning path. Creating, revising, revalidating, superseding, or retiring a KnowledgeItem requires a proposed LearningChange, operation-specific evidence and assessment, application validation against the exact current target/pointer/version, and a committed trusted-Operator decision through the authorized Task. Create retains its recorded Evaluation or explicit Operator-seed evidence basis and additionally requires the R7 KnowledgeQualityAssessment gate when that gate is in force. Revise requires a KnowledgeQualityAssessment bound to its exact proposed state. Revalidate requires fresh/rechecked evidence and a typed revalidation assessment, and must preserve content, content hash, content version, and confidence. Supersede requires a separately accepted same-Team successor plus an explicit predecessor link; retire requires reason/evidence and no successor. No assessment Task, worker, model, indexer, or retrieval path may write KnowledgeItem directly. TeamPolicy changes remain separate and require explicit Operator approval. The only scheduled-maintenance exception is review_knowledge performing status-only active → needs_review; it cannot change content/confidence, extend review dates, or reactivate an item. No other write path exists.

Do not begin R7-A while any decision that changes canonical schema, authority, security, Task scopes, or lifecycle meaning remains unresolved.

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

**Implementation boundary:** this ADR is Accepted and R7-A alone is authorized. R7-B and R7-C remain separately gated and unauthorized. Acceptance and phase authorization do not substitute for hosted/local verification or establish that the implementation is correct.

**Implementation boundary:** this ADR is proposed. Its acceptance would establish design authority only; R7 implementation still requires a separate explicit Operator authorization and a verified local preflight.
