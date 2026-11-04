# R7-0 — Knowledge Quality and Lifecycle: Architecture and Entry Gate

## Status and authority

**R7-0: DOCUMENTATION / DESIGN IN PROGRESS — 2026-11-04.**

- This document is the proposed R7 implementation entry gate. It is not an implementation authorization.
- ADR-0032 is **Proposed** and requires explicit Operator review/acceptance.
- PLAN.md remains the sole authority for milestone status and next action.
- R6 is formally complete through R6-G. R6-G approval and merge do not authorize R7.
- This R7-0 scope is documentation only: no application code, tests, migrations, schemas, Task types, write scopes, provider configuration, or runtime behavior may change.

## 1. Objective

Extend Watch from a verified first learning loop into a knowledge system that can assess the quality of its abstractions, recognize related and contradictory evidence, measure later retrieval/use, and maintain canonical knowledge through controlled revision, revalidation, supersession, and retirement.

The R7 objective is not to maximize the volume of stored knowledge. It is to improve the reliability of retained knowledge and prevent stale, overgeneralized, duplicated, misleading, or no-longer-applicable abstractions from continuing to influence later Tasks.

## 2. R6 baseline and implementation facts

R7 starts from the current main tree after the R6-G closeout merge:

- Main baseline commit: b0ac8707009a773955e26b7a7809ff84fe1c2f90 (merge of PR #37, R6-G formal documentation closeout).
- R6-G implementation merge: 56745b613b5b77a21a514b4e261d3450f90c0df1 (PR #35).
- The verified R6 implementation migration head is 0013_team_experience_projection; R7 local preflight must confirm the live source migration chain and exactly one Alembic head before any schema work.
- Recorded R6-G verification: exact implementation-head hosted CI passed 614 tests; operator-local disposable-PostgreSQL verification passed 134 focused and 614 full-suite tests, Ruff, Mypy, migration/head checks and git diff --check. Exact details and the offline fake-provider qualification remain in docs/testing.md.
- The existing D9 evaluator means ingestion execution-contract conformance only. It is not a knowledge-quality evaluator.
- R6-F's create-only LearningChange proposal/commit path is implemented. Database vocabulary for revise and retire does not make those operations reachable or authorized.
- KnowledgeItem currently uses active, needs_review, and retired. review_knowledge owns only the scheduled active → needs_review transition; a separate accepted revalidation path is not implemented.
- Current Team Experience projection is separate and rebuildable. Current canonical status/version/hash/review eligibility is checked before model exposure. Do not treat projection records as canonical state.

The base commit is a repository baseline reference, not proof of the Operator's local branch, HEAD, worktree, or database. The R7-A preflight must be performed against the actual local checkout.

## 3. Scope and proposed delivery sequence

R7 is proposed as three bounded implementation phases after R7-0 is accepted.

### R7-A — Evidence relationships and knowledge-quality evaluation

**Purpose:** determine whether a proposed/current abstraction is justified by canonical evidence and whether its claimed generality is defensible.

Proposed scope:

1. Define canonical case identity/lineage and deterministic relationship classification using source Signal IDs, Snapshot references/hashes, normalized source content, PlanAction identity, repeated underlying events, and common upstream evidence.
2. Preserve the two-distinct-source-Task minimum from ADR-0029. Related and unknown cases with distinct Task IDs still count toward the minimum, but must be labelled, included, and reflected in the quality assessment; they may not be represented as independent.
3. Define the exact KnowledgeQualityAssessment typed record. Do not extend the current Outcome-scoped Evaluation or Evaluation-only EvidenceLink contract for abstraction-quality rubrics.
4. Freeze the rubric schema and evaluator identity/revision: evidence fidelity, case coverage/relationship, contradiction handling, applicability boundaries, uncertainty, specificity/actionability, and novelty/overlap.
5. Define deterministic evidence selection, omissions, typed source references, and exact binding to the LearningChange proposal hash and expected target version.
6. Define the proposed assessment Task and write scope. The assessment Task writes only its own typed assessment and Task-attributed Event; it cannot write LearningChange or KnowledgeItem.
7. Preserve the confidence rule: create establishes initial confidence; only accepted revise may change it; revalidation and all other operations preserve it.
8. Build deterministic fixtures and held-out quality tests with positive, negative, contradictory, related, unknown, duplicate/replay, and insufficient-evidence cases.

Exit requirements:

- Different Task IDs are not described as independent unless canonical lineage supports that classification.
- Related/unknown cases count toward the minimum but limit the supported breadth of the abstraction.
- Every claim and assessment is reconstructable from canonical records, exact hashes, evaluator identity/revision, and rubric revision.
- D9 worked cannot satisfy a knowledge-quality criterion by itself.
- Counterexamples, failed cases, missing evidence, and selection omissions remain visible.
- The same canonical input deterministically produces the same basis hash and rule-based validation result.
- Assessment output remains untrusted; no model or score can accept knowledge.
- R7-A adds no KnowledgeItem lifecycle write path; canonical lifecycle widening belongs to R7-B after this contract is accepted.

### R7-B — Canonical KnowledgeItem lifecycle

**Purpose:** implement controlled transitions through LearningChange after R7-A establishes the evidence and assessment contract.

Proposed scope:

1. Add KnowledgeItem.current_learning_change_id while retaining immutable origin_learning_change_id. Create sets both to the create change; every accepted revise/revalidate/supersede/retire advances the current pointer.
2. Prove complete reconstruction from immutable LearningChange previous_state/committed_state snapshots and the current pointer. If that is insufficient, add the smallest append-only version-history record.
3. Define content-version semantics: create starts at 1; revise increments the content version; lifecycle-only revalidate/supersede/retire preserve content version/hash but advance the current change pointer.
4. Update all canonicality consumers and admission/finalization guards: Team Experience index/retrieval, Context assembly, LearningCommitService, OperatorApplicationAdapter, and TaskRuntime approval Task validation/finalization. Remove create-only assumptions only through operation-specific checks.
5. Implement revise against exact KnowledgeItem ID, current LearningChange pointer, and expected version, retaining complete immutable previous and committed state.
6. Implement revalidation as needs_review → active only through a typed evidence-backed revalidation LearningChange and trusted Operator approval. Preserve content/hash/version/confidence; update last_validated_at and review_after from the approval Task's pinned TeamPolicy.
7. Implement supersession as predecessor status retired plus a superseded_by_id link to an already accepted, active, same-Team successor. Keep no separate superseded status. Enforce one successor per predecessor, at most one predecessor per successor, no self-link/cycle, exact predecessor fencing, and deterministic replay.
8. Implement terminal retire without a successor, with a non-empty reason and evidence basis.
9. Preserve D7 policy-pinned UTC review scheduling. NULL/due items remain ineligible. After revalidation, the previously ineligible projection must be republished and revalidated before Context can expose the item.
10. Route all decisions through the existing host-invoked Operator adapter, application validation, LearningChange commit boundary, and TaskRuntime. No direct database or model write path.

Exit requirements:

- Only accepted, same-Team, current-pointer/version LearningChanges commit.
- Competing revisions/revalidation/supersession/retirement cannot both succeed against stale state.
- Prior accepted state is immutable and reconstructable; replay cannot create duplicate versions or transitions.
- Canonical item state, LearningChange history, and Task-attributed Events commit atomically.
- Due, needs_review, retired, superseded predecessors, NULL-dated, stale, and unauthorized items are immediately ineligible, independent of projection refresh timing.
- Superseded predecessors are represented as retired plus a validated successor pointer, not a nonexistent status.
- Projection invalidation/update/rebuild is idempotent and separate from canonical acceptance.
- Scheduled review remains active → needs_review only; it never reactivates, revises, supersedes, or retires an item.

### R7-C — Retrieval quality and downstream-use evaluation

**Purpose:** verify that eligible knowledge is retrieved appropriately, remains correctly scoped, and can be evaluated against later work without inventing causal claims.

Proposed scope:

1. Establish a versioned benchmark corpus of reviewed queries and expected relevant/irrelevant/forbidden/stale candidates.
2. Keep synthetic cases visibly distinct from canonical-derived and human/operator-reviewed labels. Record label provenance, rationale, corpus revision, and reviewer/source reference. Keep tuning data separate from held-out evaluation data.
3. Given the currently narrow real R6 evidence base, report small-n results descriptively: per-query outcomes, raw counts, and label-appropriate metrics. Do not claim statistical significance or broad real-world generalization from a synthetic or small corpus.
4. Preserve exact retrieval-to-Context provenance for each included KnowledgeItem version. Reuse Context manifest v2 for included items; a new manifest version must also preserve current LearningChange identity while retaining v1/v2 replay.
5. Add an application-owned TaskKnowledgeReference for per-claim citations. The model may nominate a reference, but code validates it against the immutable Context manifest and writes the Task-attributed record. Inclusion is already captured and must not be duplicated.
6. Add typed KnowledgeUseAssessment only after distinguishing retrieved, included, cited, and materially evaluated knowledge. Bind it to the exact item version/hash, citation, Task Context, and terminal Outcome, with its own non-ambiguous disposition vocabulary.
7. Evaluate later Task outcomes as evidence and preserve alternative explanations and uncertainty; never infer causation from retrieval, inclusion, citation, or success alone.
8. Run the integrated lifecycle: distill → quality-assess → Operator decide → revise/revalidate/supersede/retire → project/rebuild → retrieve → application-validated citation → assess later use.
9. Confirm that existing Task passage/character budgets and same-Team/domain isolation remain unchanged unless a separate accepted decision changes them.

Exit requirements:

- Benchmark results are reproducible and report relevance metrics plus zero-tolerance scope/status/provenance violations.
- Synthetic and real/human-reviewed labels are visibly separated; small-n results are not presented as generalization.
- Retrieval similarity is never used as a truth or commit score.
- Every included item resolves to its current canonical ID/version/hash/current-LearningChange identity at Context assembly.
- A cited record is application-written and resolves to the exact included Context version.
- The system does not infer that a worker used an item merely because it was retrieved or included.
- Later outcomes are assessed as evidence, not proof that the knowledge caused success or failure.
- Rebuild and stale-projection failure cannot re-expose obsolete content.

## 4. Architecture decisions and hard gates before R7-A

The normative proposal is [ADR-0032](../decisions/ADR-0032-knowledge-quality-evaluation-and-lifecycle.md). The following decisions are proposed in ADR-0032 but still require explicit Operator acceptance and exact implementation-level freezing before the relevant phase:

| Decision | Proposed resolution / remaining gate |
|---|---|
| Execution vs. knowledge assessment | Keep D9/Evaluation Outcome-scoped. Create a distinct KnowledgeQualityAssessment; use a distinct KnowledgeUseAssessment for item-specific downstream judgments. No reuse of worked/mixed/failed as a knowledge verdict. Freeze each typed schema and evaluator identity/revision before implementation. |
| Case identity and independence | Two separately recorded Outcomes from distinct Task IDs remain the minimum. Related/unknown cases still count but are annotated and constrain claims. Freeze the exact canonical lineage fields, normalization, and deterministic rules. |
| Quality rubric | Structured per-dimension dispositions and references; no scalar-only approval. Freeze JSON schema, dispositions, evidence-reference shape, and deterministic validation. |
| Confidence | Create sets initial confidence; only accepted revise may change it. Revalidation, review scheduling, supersession, retirement, and assessments preserve it. |
| Current canonicality chain | Retain origin_learning_change_id and add current_learning_change_id. Freeze snapshot completeness, current-pointer checks, content-version semantics, and exact consumer/test coverage. |
| Canonicality consumers | Update Team Experience indexing/retrieval, Context assembly, LearningCommitService, OperatorApplicationAdapter, and TaskRuntime approval admission/finalization; no create-only assumption may remain on a widened path. |
| Supersession | No new status: predecessor becomes retired with superseded_by_id to an already accepted same-Team successor. Freeze unique predecessor/successor rules, cycle prevention, and concurrency/replay behavior. |
| Revalidation and review | Revalidation is an explicit LearningChange; preserve content/version/hash/confidence, update validation/review timestamps from pinned policy, and republish projection before retrieval. Preserve review_knowledge as active → needs_review only. |
| INV-12 and write scopes | Accept the proposed INV-12 amendment in ADR-0032 and freeze the proposed R7 Task/write-scope matrix. Do not change the active invariant or active scope grants while ADR-0032 remains Proposed. |
| Knowledge-use provenance | Context manifest v2 already records inclusion. Add only the missing application-owned per-claim citation reference and typed downstream-use assessment; bind exact Context/item version/Outcome. |
| Retrieval benchmark | Record label provenance/rationale and synthetic-vs-real status; freeze held-out split, small-n reporting, and hard-zero safety checks. |
| Provider and cost | No provider selected. Any production provider/model, data handling, rate card, maximum reservation and failure semantics require a separate decision; no R6-E inheritance. |

**Proposed Task matrix:** docs/tasks.md must include a clearly marked non-active R7 matrix for assessment Tasks and the existing Operator lifecycle approval Task. It is design documentation only; it grants no current write scope.

**Proposed invariant amendment:** ADR-0032 contains a complete proposed INV-12 replacement. Do not edit the active invariant until the Operator accepts ADR-0032. Upon acceptance, update docs/invariants.md before any implementation starts.

Do not begin R7-A while any decision that changes canonical schema, authority, security, Task scopes, or lifecycle meaning remains unresolved.

## 5. Non-negotiable constraints

- Model/worker/evaluator output is a proposal, never authority to change canonical knowledge.
- All KnowledgeItem content changes and explicit lifecycle decisions require a committed LearningChange and trusted Operator decision. The sole narrow maintenance exception remains the scheduled review_knowledge status-only active → needs_review transition; it cannot change content/confidence or reactivate an item.
- INV-11/INV-13/INV-14 remain in force. INV-12 remains the active rule until ADR-0032 is accepted; the proposed amendment in ADR-0032 must be applied to docs/invariants.md before implementation. Canonical records govern, commits revalidate atomically, and Tasks stay within exact scope/budget.
- The existing host remains the authentication root. No Watch-owned authentication stack or public Operator API is part of this gate.
- TaskRuntime remains the sole lifecycle authority. No second runtime, generalized dispatcher, scheduler, queue, or workflow engine.
- TeamPolicy remains separate from learned Team Experience. No automatic TeamPolicy mutation or policy learning.
- Team Experience indexes remain regenerable projections. Canonical status/content-version/hash, origin/current LearningChange pointers, and review eligibility must be rechecked at index, retrieval, and Context assembly boundaries. Revalidation requires republishing a current projection before exposure.
- Same-Team isolation and current access authorization remain hard requirements. Multi-Team transfer and cross-domain knowledge publication are not R7 scope.
- Existing Context limits and provider boundaries remain unchanged until separately approved.
- Tests/migrations use disposable PostgreSQL only. Never use the persistent watch database.

## 6. Provider and external-service gate

R6-E's Cloudflare Workers AI selection is authorized for R6-E only. No production R6-F distillation provider was selected. R7-0 selects no provider, model, embedding revision, reranker, vector service, SDK, or credentials path.

If a production provider is needed, its separate decision must cover: model/provider identity and revision; data sent and retention/training handling; exact request bounds; pinned rate card; maximum pre-call reservation; usage reconciliation; unknown/overrun behavior; retry/recovery; secrets isolation; and an operator-approved smoke-test boundary. Until then, use deterministic fakes and synthetic cost cards only.

## 7. R7-0 acceptance and implementation entry checklist

R7-0 documentation acceptance:

- [x] R6 predecessor is formally closed and current main baseline recorded.
- [x] R7 scope, proposed phases, constraints, and non-goals are documented.
- [x] Proposed ADR-0032 and this entry gate identify the decisions and code-level constraints before R7-A.
- [x] A proposed, non-active R7 Task/write-scope matrix is recorded in docs/tasks.md; no current Task grant is changed.
- [x] Proposed INV-12 amendment is included in ADR-0032; active docs/invariants.md remains unchanged pending acceptance.
- [x] PLAN.md, README.md, CONTEXT.md, CHANGE_MAP.md, and docs/decisions.md point to the same authority chain.
- [ ] Operator explicitly accepts, rejects, or revises ADR-0032's proposed architecture decisions.
- [ ] Operator explicitly authorizes the next implementation phase; R7-0 does not authorize it.

Before R7-A implementation:

- [ ] Operator acceptance of the ADR and resolution of every R7-A architecture decision above.
- [ ] Separate explicit Operator instruction authorizing R7-A implementation and its bounded file/scope.
- [ ] Local preflight on the actual checkout: current branch, HEAD, clean/known worktree, sync with intended base, merge status, and exact migration heads.
- [ ] Confirm DATABASE_URL and TEST_DATABASE_URL are pointed only at an identified disposable PostgreSQL database before database-backed checks.
- [ ] Review actual current code, migration chain, Task matrix, invariants, and tests; do not assume the current migration number or infer implementation from this plan.
- [ ] Freeze deterministic fixtures, rubric revision, case-lineage rules, failure-injection/recovery tests, and acceptance evidence.
- [ ] Any live provider decision is accepted before a real provider call; otherwise use deterministic fakes.

## 8. R7-0 file and change boundary

Expected R7-0 changes are documentation only:

- docs/decisions/ADR-0032-knowledge-quality-evaluation-and-lifecycle.md
- docs/development/r7-entry-gate.md
- docs/tasks.md — proposed R7 task/write-scope rows only; current scope matrix remains unchanged
- PLAN.md — current R7-0 status and next action only
- CHANGE_MAP.md — authority mapping
- docs/decisions.md — ADR index
- README.md and CONTEXT.md — concise roadmap/orientation

No source code, tests, migrations, schema, runtime configuration, provider configuration, active Task grants, or active invariant changes belong in R7-0. docs/tasks.md may contain only a clearly marked proposed/non-active R7 matrix; docs/invariants.md remains unchanged until ADR-0032 is accepted. If an architecture decision requires runtime changes, record it as a proposal and resolve it before implementation.

## 9. R7-0 exit criteria

R7-0 is ready to close only when:

1. The documentation-only PR passes required hosted checks and its exact file scope is reviewed.
2. The Operator explicitly accepts or requests changes to ADR-0032 and the R7 entry gate.
3. The unresolved architecture decisions required for R7-A are resolved in the applicable authority documents.
4. A separate explicit Operator authorization names R7-A as the next implementation phase.

Closing R7-0 or accepting ADR-0032 does not, by itself, authorize R7-A unless the Operator explicitly authorizes it.

**Current gate:** R7-0 documentation is prepared for review. ADR-0032 remains Proposed. R7-A/B/C are not authorized.
