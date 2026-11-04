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

**Purpose:** determine whether a proposed/current abstraction is justified by the canonical evidence and whether its claimed generality is defensible.

Proposed scope:

1. Define canonical case identity/lineage and deterministic relationship classification. Preserve the distinction between distinct Task IDs and genuinely independent evidence.
2. Define the knowledge-quality rubric and typed assessment contract: evidence fidelity, case coverage/relationship, contradiction handling, applicability boundaries, uncertainty calibration, specificity/actionability, and novelty/overlap.
3. Keep execution evaluation (including D9) distinct from abstraction-quality assessment and later knowledge-use evaluation.
4. Define explicit, bounded evidence selection and omission disclosure. Preserve failed/contrary cases and exact canonical provenance.
5. Define the exact binding between KnowledgeItem ID/version/hash, Context Snapshot/manifest, later Task, terminal Outcome, and any knowledge-use assessment. Do not claim use or causation from retrieval alone.
6. Choose whether the existing Evaluation model can safely represent the new assessment contract or whether a minimal distinct record is required. Resolve schema and Task/write scopes before code.
7. Build deterministic fixtures and a held-out quality test set with positive, negative, contradictory, related, and insufficient-evidence cases.

Exit requirements:

- A case relationship cannot be called independent solely because Task IDs differ.
- Every claim and assessment is reconstructable from canonical records, exact hashes, evaluator identity/revision, and rubric revision.
- D9 worked cannot satisfy a knowledge-quality criterion by itself.
- Counterexamples, failed cases, missing evidence, and selection omissions remain visible.
- The same canonical input deterministically produces the same basis hash and rule-based validation result.
- Provider-produced assessment remains untrusted; no model or score can accept knowledge.
- No canonical KnowledgeItem lifecycle operation is widened in this phase unless separately included in its accepted scope.

### R7-B — Canonical KnowledgeItem lifecycle

**Purpose:** implement the missing, controlled state transitions after R7-A defines the evidence and assessment contract.

Proposed scope:

1. Enable revise against an exact KnowledgeItem ID and expected current version, retaining complete previous and committed state history.
2. Define whether the current KnowledgeItem row is a stable identity/version head or whether an append-only version record is necessary. Reconstruction of every accepted historical version is mandatory.
3. Implement explicit needs_review → active revalidation only through a genuine, evidence-backed, Operator-reviewed LearningChange.
4. Implement supersession as an explicit predecessor/successor relationship with same-Team checks, expected-version fencing, cycle prevention, deterministic replay, and one atomic canonical transition.
5. Implement terminal retire with a non-empty reason and evidence basis. Retired items must never re-enter retrieval through stale projection rows.
6. Preserve D7 policy-pinned UTC review scheduling. Any new review date must be derived from the committing Task's pinned policy; no global/default interval, retroactive NULL-date backfill, or TeamPolicy mutation is implied.
7. Route all decisions through the existing host-invoked Operator adapter, application validation, LearningChange commit boundary, and TaskRuntime. No direct database or model write path.

Exit requirements:

- Only accepted, same-Team, current-version LearningChanges commit.
- Competing revisions/revalidation/supersession/retirement cannot both succeed against one stale version.
- Prior accepted state is immutable and reconstructable; replay cannot create duplicate versions or transitions.
- Canonical item state, LearningChange history, and Task-attributed Events commit atomically.
- Due, needs_review, superseded, retired, NULL-dated, stale, and unauthorized items are immediately ineligible at retrieval, independent of projection refresh timing.
- Projection invalidation/update/rebuild is idempotent and separate from canonical acceptance.
- Scheduled review remains active → needs_review only; it never reactivates, revises, or retires an item.

### R7-C — Retrieval quality and downstream-use evaluation

**Purpose:** verify that eligible knowledge is retrieved appropriately, remains correctly scoped, and can be evaluated against later work without inventing causal claims.

Proposed scope:

1. Establish a versioned benchmark corpus of reviewed queries and expected relevant/irrelevant/forbidden/stale candidates.
2. Measure the current hybrid retriever with metrics suitable to the labels, while reporting hard safety failures separately.
3. Preserve exact retrieval-to-Context provenance for each included KnowledgeItem version.
4. Add typed knowledge-use assessment only after distinguishing retrieved, included, cited, and materially evaluated knowledge.
5. Evaluate later Task outcomes against the exact exposure/use evidence and preserve alternative explanations and uncertainty.
6. Run the integrated lifecycle: distill → quality-assess → Operator decide → revise/revalidate/supersede/retire → project/rebuild → retrieve → evaluate later use.
7. Confirm that existing Task passage/character budgets and same-Team/domain isolation remain unchanged unless a separate accepted decision changes them.

Exit requirements:

- Benchmark results are reproducible and report relevance metrics plus zero-tolerance scope/status/provenance violations.
- Retrieval similarity is never used as a truth or commit score.
- Every included item resolves to its current canonical ID/version/hash at Context assembly.
- The system does not infer that a worker used an item merely because it was retrieved or included.
- Later outcomes are assessed as evidence, not proof that the knowledge caused success or failure.
- Rebuild and stale-projection failure cannot re-expose obsolete content.

## 4. Architecture decisions to resolve before R7-A

The normative proposal is ADR-0032. These items are hard design gates, not implementation details:

| Decision | Required resolution |
|---|---|
| Execution vs. knowledge evaluation | Distinct typed meanings, evaluator identities/revisions, and no reuse of D9 worked as knowledge-quality evidence. |
| Case identity and independence | Canonical lineage fields, duplicate/related-case rules, and conservative independent / related / unknown dispositions. |
| Quality rubric | Exact dimension schema, dispositions, validation rules, and evidence links; no scalar-only approval. |
| Knowledge-use provenance | Retrieved vs. included vs. cited vs. evaluated use; exact Context/KnowledgeItem version/Task/Outcome binding. |
| Evaluation persistence | Safe Evaluation extension versus the smallest separate typed assessment record. |
| Revision history | Stable KnowledgeItem identity/version head versus append-only per-version records; complete reconstruction proof. |
| Supersession | Predecessor/successor representation, status transition, uniqueness, cycle prevention, and rollback/replay. |
| Revalidation | Required evidence, Operator decision, last_validated_at, policy-pinned review_after, and legal transition. |
| Retirement | Required reason/evidence, terminality, Task scope, and projection invalidation. |
| Retrieval benchmark | Corpus ownership, label provenance, relevance grades, metrics, and hard safety checks. |
| Provider and cost | Production provider/model, data handling, rate card, maximum reservation and failure semantics; no R6-E inheritance. |

Do not begin R7-A while any decision that changes canonical schema, authority, security, Task scopes, or lifecycle meaning remains unresolved.

## 5. Non-negotiable constraints

- Model/worker/evaluator output is a proposal, never authority to change canonical knowledge.
- All canonical changes require a committed LearningChange and explicit trusted Operator decision.
- INV-11/INV-12/INV-13/INV-14 remain in force: canonical records govern, the learning path owns Team-memory writes, commits revalidate atomically, and Tasks stay within exact scope/budget.
- The existing host remains the authentication root. No Watch-owned authentication stack or public Operator API is part of this gate.
- TaskRuntime remains the sole lifecycle authority. No second runtime, generalized dispatcher, scheduler, queue, or workflow engine.
- TeamPolicy remains separate from learned Team Experience. No automatic TeamPolicy mutation or policy learning.
- Team Experience indexes remain regenerable projections. Canonical status/version/hash and review eligibility must be rechecked at index, retrieval, and Context assembly boundaries.
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
- [x] Proposed ADR-0032 and this entry gate identify the unresolved decisions before R7-A.
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
- PLAN.md — current R7-0 status and next action only
- CHANGE_MAP.md — authority mapping
- docs/decisions.md — ADR index
- README.md and CONTEXT.md — concise roadmap/orientation

No source code, tests, migrations, schema, runtime configuration, provider configuration, task matrix, or invariant changes belong in R7-0. If an architecture decision would require one of those changes, record it as a proposal and resolve it before implementation.

## 9. R7-0 exit criteria

R7-0 is ready to close only when:

1. The documentation-only PR passes required hosted checks and its exact file scope is reviewed.
2. The Operator explicitly accepts or requests changes to ADR-0032 and the R7 entry gate.
3. The unresolved architecture decisions required for R7-A are resolved in the applicable authority documents.
4. A separate explicit Operator authorization names R7-A as the next implementation phase.

Closing R7-0 or accepting ADR-0032 does not, by itself, authorize R7-A unless the Operator explicitly authorizes it.

**Current gate:** R7-0 documentation is prepared for review. ADR-0032 remains Proposed. R7-A/B/C are not authorized.
