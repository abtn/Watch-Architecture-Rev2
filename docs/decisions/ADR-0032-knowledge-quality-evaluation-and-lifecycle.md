# ADR-0032 — Knowledge Quality Evaluation and Lifecycle

## Status

**Proposed for Operator review — 2026-11-04.** This ADR records the proposed R7 architecture direction and the decisions that must be accepted or resolved before implementation. It does not authorize R7-A, a schema migration, a production model/provider, or a change to any Task write scope.

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

### D1 — Keep execution, abstraction, and knowledge-use evaluation distinct

Use three separate questions and preserve their separate evidence:

1. **Execution conformance:** did the Task satisfy its execution contract? Existing D9 revision 1 answers only its configured-source ingestion question.
2. **Abstraction quality:** does a proposed or current KnowledgeItem faithfully represent its stated evidence, preserve contradictions, and describe defensible applicability boundaries?
3. **Knowledge-use result:** what happened in a later Task that had a particular KnowledgeItem version available in its exact Context, and what evidence supports or challenges the claimed usefulness of that knowledge?

An Evaluation of one category must not silently stand in for another. In particular, D9's worked result is not a positive knowledge-quality score. A successful Task is not proof that a retrieved item caused the result. R7 must give each new evaluator a stable kind, identity, revision, and explicit evidence basis.

**Proposed resolution:** introduce a typed, versioned knowledge-assessment contract through the existing application/Task boundaries. Reuse the existing Evaluation model only if its current Outcome-scoped semantics can be extended without weakening R6-G's exact D9 contract or creating ambiguous evaluator meanings. Otherwise define the smallest separate typed record. Decide this in R7-A before selecting a migration.

### D2 — Treat distinct Task IDs as a minimum threshold, not proof of independence

ADR-0029's threshold remains a minimum eligibility rule: cross-case Pattern, Method, or Playbook proposals need at least two recorded Outcomes from distinct Task IDs, each with a corresponding recorded Evaluation. That threshold permits a proposal; it does not establish statistically independent evidence or general transfer.

The evidence review must also examine lineage that may make apparently separate cases related: shared source Signals or Snapshot hashes, duplicate/near-duplicate content, common PlanAction or Objective, repeated processing of the same underlying event, and common upstream evidence. A shared Team or task class alone does not automatically make cases duplicates.

**Proposed resolution:** classify case relationships conservatively as independent, related, or unknown, with deterministic rules and preserved provenance. Only claim independence when the available lineage supports it. Do not silently drop related or unknown cases; include them with their relationship and limitations, or make bounded selection/omission visible. R7-A must define the exact lineage fields and comparison rules before implementation.

### D3 — Evaluate abstraction quality with a structured rubric, not one confidence score

A knowledge-quality assessment should address at least:

- **Evidence fidelity:** every material claim is supported by the cited canonical basis and does not exceed what the observations establish.
- **Case coverage and relationship:** the proposal reflects the selected cases and does not overstate their independence or diversity.
- **Contradiction handling:** contrary, failed, mixed, and disconfirming cases are preserved and explained rather than averaged away.
- **Applicability boundaries:** situation, preconditions, non-applicability, failure modes, and assumptions are concrete enough to test.
- **Uncertainty calibration:** missing evidence and uncertainty are explicit; confidence is not inferred from model fluency or case count alone.
- **Specificity and utility:** the abstraction is actionable and falsifiable without claiming a universal rule.
- **Novelty and overlap:** the proposal is compared with current Team Experience so duplicates, conflicts, and possible supersession are surfaced.

**Proposed resolution:** use a rubric with per-dimension dispositions such as supported, limited, contradicted, and insufficient_evidence, together with findings and references. A scalar score may be retained as diagnostic data only after its calibration is justified; it must not independently authorize acceptance, revision, publication, or retrieval. Application validation remains deterministic for schema, ownership, hashes, references, and lifecycle preconditions. A model-based evaluator, if later authorized, produces another untrusted assessment proposal, not an oracle.

### D4 — Preserve exact knowledge-exposure provenance; do not infer use or causation

For a later Task, distinguish:

- a KnowledgeItem candidate found by retrieval;
- a KnowledgeItem version actually included in the immutable Task Context;
- a knowledge claim the worker explicitly referenced in its proposal/output;
- evidence that the knowledge was materially useful or harmful to the result.

The existing Context manifest and Snapshot provide a starting point for exact exposure provenance. R7 should bind any use assessment to the exact Task, Context Snapshot/hash, KnowledgeItem ID, version, content hash, and relevant Task Outcome/Evaluation. It must not infer that the model used an item merely because it was retrieved, or infer causal contribution merely because the Task succeeded.

**Proposed resolution:** first determine whether the current Task Context v2 manifest plus Task-attributed Events and Outcome can provide the full required chain. Add the smallest typed use reference/record only if the current records cannot distinguish retrieved, included, cited, and evaluated use reliably. Do not create a general-purpose knowledge graph or a generic event bus to solve this problem.

### D5 — Keep all canonical lifecycle changes behind LearningChange and trusted Operator approval

R7 may propose to extend the learning path beyond create-only, but must not create a second write path. Candidate revision, revalidation, supersession, and retirement operations must be represented as typed LearningChanges, validated against canonical evidence and an exact current target version, then accepted or rejected by a trusted Operator through the host-invoked application adapter.

Proposed lifecycle semantics:

| Operation | Proposed effect | Required guard |
|---|---|---|
| revise | Replace the current content/state of one KnowledgeItem and advance its version while preserving the prior accepted state in immutable LearningChange history. | Exact target ID and expected version; complete previous/proposed/committed state; evidence revalidation; atomic compare-and-set. |
| revalidate | Reconsider an item in needs_review and, only when the evidence supports it, return it to active. | New or rechecked evidence, recorded assessment, explicit Operator decision, updated validation/review timestamps; never a scheduler-only reactivation. |
| supersede | Make a KnowledgeItem ineligible because a distinct accepted successor replaces it. | Explicit predecessor/successor relationship, same-Team ownership, no cycles, exact predecessor version, atomic canonical transition. |
| retire | Permanently remove the current item from retrieval without replacing it. | Explicit reason and evidence basis, exact current version, explicit Operator decision; terminal transition. |

The preferred revision model is a stable KnowledgeItem identity whose current version increments, with immutable accepted LearningChange state snapshots preserving history. A distinct successor relationship is required when one KnowledgeItem supersedes another; it must not be simulated by editing text or silently reusing an ID. R7-A/B must test whether the existing LearningChange history is sufficient for complete version reconstruction or whether an append-only version record is required.

**Proposed resolution:** keep KnowledgeItem as the canonical current-state record; use LearningChange's previous/committed states as immutable transition history if they prove sufficient. Do not add a version table, successor column, or status value until the exact reconstruction, concurrency, and projection-invalidation invariants are specified. The current database vocabulary does not authorize any of these paths.

### D6 — Preserve review scheduling and canonical-versus-projection authority

The accepted ADR-0029 D7 rules remain the baseline:

- the review interval is optional, positive, non-boolean, and read from the TeamPolicy version pinned by the committing Task;
- review_after is timezone-aware UTC and computed from the canonical commit time;
- NULL and due items are ineligible for retrieval;
- the scheduled review_knowledge Task may only perform active → needs_review;
- revalidation and reactivation are separate explicit operations.

R7 must preserve these rules. A later TeamPolicy version must not silently rewrite existing KnowledgeItem review dates. TeamPolicy changes remain a separate explicitly authorized policy operation, never an automatic consequence of knowledge evaluation.

On every accepted canonical transition, stale projection rows must cease to be eligible immediately. Projection update/rebuild is a separate, idempotent operation; projection failure cannot roll back the canonical Operator decision or cause stale content to be advertised as current.

### D7 — Make retrieval quality measurable without treating ranking as truth

Create a fixed, versioned retrieval benchmark with reviewed queries and expected relevant, irrelevant, forbidden, and stale/due candidates. The benchmark should cover lexical and semantic matches, exact concepts, applicability constraints, counterexamples, and negative queries. Keep Team/domain isolation and current canonical eligibility as hard correctness constraints.

**Proposed resolution:** establish a reproducible baseline using the existing PostgreSQL full-text/vector hybrid retriever and its current bounds. Report suitable ranking measures (for example Precision@k and Recall@k; MRR or nDCG only where the labels support them), plus separate hard-failure counts for cross-Team leakage, stale/due/retired inclusion, and provenance mismatch. No metric or similarity score becomes a truth score. Do not add a reranker, external vector service, or relax the existing Context passage/character budget unless a measured benchmark and separate decision justify it.

### D8 — Keep provider, Task, identity, and security choices separately gated

R7 does not inherit provider approval from R6-E. No production R6-F distillation provider was approved, and ADR-0031 authorizes Cloudflare only for R6-E. Any production model used for R7 must receive a separate provider/model/data-handling/rate-card decision before live invocation. Reuse Task-attributed maximum reservation and reconciliation; unknown or overrun usage fails closed.

All R7 operations must use ordinary Tasks, exact Task write scopes, the existing TaskRuntime, attempt fencing, replay, and application validation. The host remains the authentication root for Operators. Do not add a second runtime, general dispatcher, Watch-owned authentication stack, autonomous approval, automatic TeamPolicy mutation, or direct model writes.

## 3. Proposed lifecycle and quality flow

1. Select a bounded, explicit set of canonical cases and record the selection rule/version.
2. Rebuild the complete evidence basis from canonical Outcomes, recorded Evaluations, Events, EvidenceLinks, immutable Snapshots, and exact Context manifests where relevant.
3. Classify case lineage and expose related/unknown cases, contradictions, failed cases, and omissions.
4. Produce a versioned knowledge-quality assessment against the structured rubric. It remains a proposal.
5. Revalidate all references, ownership, hashes, evaluator identity/revision, target version, policy pin, and Task scope in application code.
6. Present the proposal to the trusted Operator through an ordinary Task and the existing host identity boundary.
7. On acceptance, commit one atomic LearningChange and canonical KnowledgeItem transition. On rejection, record the reason without changing canonical knowledge.
8. Invalidate/update the regenerable projection independently. Retrieval returns only the current eligible canonical state.
9. Where a later Task used the exact KnowledgeItem version, evaluate the later result against its own evidence without asserting causation.

No transcript, retrieved chunk, vector rank, model confidence, or free-form self-reflection becomes canonical evidence.

## 4. Required decisions before implementation

R7-A must not begin until the Operator accepts or revises the proposed direction above and the following details are frozen in the R7 entry gate or a superseding ADR:

1. The canonical case-lineage fields and deterministic independent / related / unknown classification rules.
2. The exact quality-rubric schema, evaluator identity/revision, disposition semantics, and whether Evaluation can be extended safely or a distinct record is required.
3. The evidence contract for knowledge exposure and downstream use, including how Context manifest, item version/hash, Task Outcome, and Evaluation are bound.
4. The exact version-history model and reconstruction guarantees for revision.
5. Supersession representation, legal transitions, successor uniqueness, cycle prevention, and competing-operation behavior.
6. Revalidation evidence requirements, Operator action, and review-date calculation under the pinned policy.
7. Retirement reason/evidence requirements and terminality.
8. Retrieval benchmark ownership, labeled-corpus provenance, relevance grades, and required metrics.
9. Any production provider/model, data handling, and complete maximum-cost/rate-card decision. No provider is selected by this ADR.

## 5. Non-goals

R7 does not implement multi-Team knowledge sharing or cross-domain transfer; broad World-memory or general-purpose evidence graphs; autonomous learning acceptance; autonomous TeamPolicy changes; automatic confidence promotion; model training or fine-tuning; self-modifying Kernel/runtime behavior; a new Task runtime, scheduler, dispatcher, or workflow engine; a separate vector database or reranker by default; or an unbounded transcript-memory system.

## 6. Consequences and alternatives

This direction makes quality a question with inspectable evidence, not a confidence number. It also makes lifecycle changes explicit and reviewable while preserving the R6 canonical/projection boundary.

Rejected alternatives:

- Reuse D9 worked as a positive knowledge-quality label: rejected because it means only execution-contract conformance.
- Treat two Task IDs as proof of independent evidence: rejected because tasks may share upstream sources, Plans, or the same underlying event.
- Let the distiller approve or revise its own KnowledgeItem: rejected by INV-12 and the proposal/commit authority boundary.
- Use retrieval similarity or a single quality score as truth/commit authority: rejected because ranking and heuristic scores are derived signals.
- Add a broad knowledge graph, generic scheduler, or new runtime to make R7 convenient: rejected as disproportionate and outside the established architecture.

**Implementation boundary:** this ADR is proposed. Its acceptance would establish design authority only; R7 implementation still requires a separate explicit Operator authorization and a verified local preflight.
