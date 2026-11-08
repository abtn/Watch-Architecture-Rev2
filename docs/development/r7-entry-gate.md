# R7-0 — Knowledge Quality and Lifecycle: Architecture and Entry Gate

## Status and authority

**R7-0: COMPLETE — 2026-11-04. R7-A: COMPLETE — merged 2026-11-04. R7-B: B0 complete; B1 merged; B2 Steps 1–8 accepted and merged; Step 9 verification partially evidenced; B2 is not formally closed. B3–B6 and R7-C remain unauthorized.

- This document records the accepted R7 architecture and separate phase gates. R7-A is complete. R7-B B0 is complete; B1 was accepted and merged through PR #43. B2 Steps 1–8 are accepted and merged through PRs #45–#57. Step 8 PR #56 merged at `58d88bafdf33e8ce1af2f5a7ba9af11bfd84cb32`; PR #57 merged at `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31`. PR #57 head `114a6311534cd116190e3c2f4143fdfb1a2c979b` passed hosted CI run [42478536427](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42478536427). The merged implementation commit `027b9f1cb0bbd5faaaf8d6d7cc44c8359af49b31` passed hosted run [42479112563](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/42479112563) and Operator-local exact-SHA verification (fresh migration/single-head, Ruff, Mypy, 806 tests and 77 warnings). The local disposable container was confirmed absent. Focused-only execution, `git diff --check`, complete final diff review, and formal B2 exit acceptance remain outstanding; see `docs/testing.md`. The local run preceded merge of the Step 9 planning PR, a sequence deviation recorded there. The active approval allowlist remains exactly `create`. B2 is not formally closed; B3–B6 and R7-C remain unauthorized.
- ADR-0032 remains **Accepted — 2026-11-04 for the original R7 architecture and R7-A scope**. Its R7-B D1/D5 design extension and B0.3 integrity contracts are separately accepted for design on 2026-11-05; this does not authorize implementation.
- PLAN.md remains the sole authority for milestone status and next action.
- R6 is formally complete through R6-G. R6-G approval and merge do not authorize R7.
- The completed R7-0 change was documentation-only. R7-A was separately authorized, implemented and merged within its bounded evidence-lineage and KnowledgeQualityAssessment scope. That authorization is complete and does not carry forward to R7-B lifecycle commits or R7-C retrieval/use work.

## 1. Objective

Extend Watch from a verified first learning loop into a knowledge system that can assess the quality of its abstractions, recognize related and contradictory evidence, measure later retrieval/use, and maintain canonical knowledge through controlled revision, revalidation, supersession, and retirement.

The R7 objective is not to maximize the volume of stored knowledge. It is to improve the reliability of retained knowledge and prevent stale, overgeneralized, duplicated, misleading, or no-longer-applicable abstractions from continuing to influence later Tasks.

## 2. R6 baseline and implementation facts

R7 starts from the current main tree after R7-A was merged:

- Main baseline: 75122a7b34c15e2445b81a2a719020667b55bf06 (PR #39 merge).
- Tested PR head: 47ffa532dacbc10b146ac7b0768302761a2a0b1b; its Git tree is identical to merge tree.
- Current `main` migration head after B2 Step 2: `0016_team_exp_history_pins`; verify exactly one Alembic head during final Step 9 verification.
- Hosted exact-head CI 41844600681 passed. Operator-local disposable-PostgreSQL verification on the same tree passed 631 tests, fresh migration/single head, Ruff, Mypy (31 files), and container cleanup. Full evidence is in docs/testing.md.
- D9 remains ingestion execution-contract conformance only. R7-A adds distinct KnowledgeQualityAssessment for create proposals; no production evaluator provider was selected.
- LearningChange schema vocabulary includes create/revise/retire, but commit service and approval guards remain create-only. Schema strings do not authorize implementation.
- KnowledgeItem has origin_learning_change_id only; current_learning_change_id and superseded_by_id are not implemented. Status remains active/needs_review/retired. review_knowledge owns only active → needs_review.
- Team Experience projection is rebuildable. B2 Steps 2–6 provide current LearningChange/hash-scheme pins, final provider-space publication revalidation, stale legacy republish, reciprocal supersession retrieval gates, and Context manifest v3; historical Context v1/v2 replay remains byte-exact. Step 8's integrated fixtures are merged; Step 9 will verify the exact final code head locally and in hosted CI.

The baseline commit does not prove the Operator's local branch, HEAD, worktree or database. R7-B preflight must run against the actual checkout.

## 3. Scope and authorized delivery sequence

R7-0 documentation is complete and merged. ADR-0032's original architecture acceptance is scoped to R7-A; its R7-B design extension was separately accepted on 2026-11-05. R7-A is complete and merged through PR #39. R7-B B0 is complete and B1 is accepted and merged. B2 implementation was separately authorized on 2026-11-06; Steps 1–8 are accepted and merged through PR #57. Step 9 is the final exact-head verification and formal B2 exit gate; this checkpoint only plans that work and does not execute it. B3–B6 and R7-C remain unauthorized.

### R7-A — Evidence relationships and knowledge-quality assessment

**Status:** COMPLETE — merged through PR #39 on 2026-11-04. Contract and closeout evidence are in [r7-a-implementation-plan.md](r7-a-implementation-plan.md) and docs/testing.md.

**Purpose:** determine whether a proposed abstraction is traceable to canonical evidence and whether its claimed generality is defensible.

Authorized scope:

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

**Status (2026-11-08):** B0 is complete. B1 was accepted and merged through PR #43. B2 Steps 1–8 are accepted and merged through PR #57. Step 8 exact-head hosted CI passed (806 tests, 77 warnings); Operator-local verification on the same code head remains outstanding. Step 9 planning is documentation-only; final exact-head verification and formal B2 exit remain open. The active approval allowlist must remain exactly `create`. B3–B6 and R7-C remain unauthorized.

R7-B extends the existing LearningChange, trusted Operator and TaskRuntime path to revise, revalidate, supersede and retire KnowledgeItems. It preserves stable item identity, immutable origin provenance, current-pointer history, Team isolation, D7 review rules, and fail-closed retrieval. It adds no runtime, dispatcher, scheduler, public API/auth stack or production evaluator provider.

**Accepted B0 design:** confidence participates in the semantic content hash; confidence-only revise is content-changing and clears validation. Revalidation may use verified existing canonical evidence only while temporally relevant and source-valid; time-sensitive/current-condition claims or expired/changed/contradicted bases require new observations. Trusted Operator issuer/subject remains bound in the immutable request fingerprint and decision record. Snapshot/content separators are frozen as `watch.r7b.knowledge-item-state.v1` and `watch.r7b.knowledge-content.v2`. The D5 amendment accepts reciprocal successor links, candidate guards, abandonment/replacement rules, D7-aware publication gating, the full edge table, and fresh supersession from a `needs_review` predecessor under operation-specific guards. Snapshot-first reconstruction is accepted conditionally on B1 proof; failure requires a separate decision on the smallest append-only history record.

**Phase sequence:**

1. **B0 — Design freeze (documentation only):** five Operator decisions and D1/D5 design extensions accepted 2026-11-05. Complete cross-document integration and documentation validation; no code or active Task scopes.
2. **B1 — Schema and history proof:** current pointer and reciprocal supersession fields, safe backfill, create-pointer rollout, both LearningChange constraints, legacy snapshot decoder, chain reconstruction and D7 overlay validation. Stop and seek a history-table decision if reconstruction cannot be proven.
3. **B2 — Hash/projection/Context and chain-aware consumers:** stable content-hash v2; `legacy-opaque` stale/republish transition for pre-existing projections; current-pointer projection pins; Context manifest v3; immutable v1/v2 replay, while enabling only create.
4. **B3 — Assessments:** immutable KnowledgeRevalidationAssessment and KnowledgeLifecycleAssessment through narrow Task paths; no production provider or model scoring for lifecycle assessments.
5. **B4 — Revise/revalidate:** exact pointer/version compare-and-set, status-preserving revise, evidence-bound revalidation and fresh projection publication.
6. **B5 — Supersede/retire/candidate creation:** create-with-successor, reciprocal publication gate, D7-aware commit, abandoned-candidate rules, consistent-snapshot Context validation, and Team-scoped graph lock.
7. **B6 — Legacy compatibility and hardening:** legacy Events/snapshots, repeated review/revalidation, replay after later transitions, mutation rejection and full regression verification.

**Implementation gate:** B1 and B2 were separately authorized; B2 Steps 1–8 are accepted and merged. Step 9 planning is documentation-only; its execution is limited to final exact-head verification and the explicit B2 exit gate. The active approval allowlist remains exactly `create`. B3–B6 require their own later phase authorizations. No R7-C work is authorized.

### R7-C — Retrieval quality and downstream-use evaluation

**Status:** proposed; not authorized.

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

## 4. Accepted architecture decisions and phase gates

The normative architecture is [ADR-0032](../decisions/ADR-0032-knowledge-quality-evaluation-and-lifecycle.md). R7-A's completed implementation contract is [r7-a-implementation-plan.md](r7-a-implementation-plan.md). The R7-B plan sequences the authorized B2 steps and the separately gated B3–B6 work; `PLAN.md` remains the sole source of current milestone status.

| Decision | Accepted resolution / phase-specific gate |
|---|---|
| Execution vs. knowledge assessment | Keep D9/Evaluation Outcome-scoped. Create a distinct KnowledgeQualityAssessment; use a distinct KnowledgeUseAssessment for item-specific downstream judgments. No reuse of worked/mixed/failed as a knowledge verdict. Freeze each typed schema and evaluator identity/revision before implementation. |
| Case identity and independence | Two separately recorded Outcomes from distinct Task IDs remain the minimum. Related/unknown cases still count but are annotated and constrain claims. Freeze the exact canonical lineage fields, normalization, and deterministic rules. |
| Quality rubric | Structured per-dimension dispositions and references; no scalar-only approval. Freeze JSON schema, dispositions, evidence-reference shape, and deterministic validation. |
| Confidence | Create sets initial confidence; only accepted revise may change it. Revalidation, review scheduling, supersession, retirement, and assessments preserve it. |
| Current canonicality chain | Retain origin_learning_change_id and add current_learning_change_id. Freeze snapshot completeness, current-pointer checks, content-version semantics, and exact consumer/test coverage. |
| Canonicality consumers | Update Team Experience indexing/retrieval, Context assembly, LearningCommitService, OperatorApplicationAdapter, and TaskRuntime approval admission/finalization; no create-only assumption may remain on a widened path. |
| Supersession | No new status: predecessor becomes retired with superseded_by_id to an already accepted same-Team successor. Freeze unique predecessor/successor rules, cycle prevention, and concurrency/replay behavior. |
| Revalidation and review | Revalidation is an explicit LearningChange; preserve content/version/hash/confidence, update validation/review timestamps from pinned policy, and republish projection before retrieval. Preserve review_knowledge as active → needs_review only. |
| INV-12 and write scopes | Accepted INV-12 amendment is now recorded in docs/invariants.md. The R7 Task matrix remains non-active until the relevant Task/service code and tests are implemented; no runtime grant is implied by this documentation row. |
| Knowledge-use provenance | Context manifest v2 already records inclusion. Add only the missing application-owned per-claim citation reference and typed downstream-use assessment; bind exact Context/item version/Outcome. |
| Retrieval benchmark | Record label provenance/rationale and synthetic-vs-real status; freeze held-out split, small-n reporting, and hard-zero safety checks. |
| Provider and cost | No provider selected. Any production provider/model, data handling, rate card, maximum reservation and failure semantics require a separate decision; no R6-E inheritance. |

**Task matrix status:** docs/tasks.md records merged R7-A `assess_knowledge_quality` in the active Task specification and write-scope matrix. R7-B lifecycle extensions and R7-C `assess_knowledge_use` remain proposed/non-active. Preparation grants no Task registration or write scope.

**Invariant status:** the Operator accepted ADR-0032 on 2026-11-04 and corresponding INV-12 amendment is active in docs/invariants.md. R7-A enforces KnowledgeQualityAssessment for accepted creates. R7-B must extend enforcement to operation-specific target/current-pointer/version validation and evidence/assessment. No lifecycle operation beyond create is implemented.

## 5. Non-negotiable constraints

- Model/worker/evaluator output is a proposal, never authority to change canonical knowledge.
- All KnowledgeItem content changes and explicit lifecycle decisions require a committed LearningChange and trusted Operator decision. The sole narrow maintenance exception remains the scheduled review_knowledge status-only active → needs_review transition; it cannot change content/confidence or reactivate an item.
- INV-11/INV-13/INV-14 remain in force. INV-12 has been amended as accepted by the Operator on 2026-11-04; R7-A must implement and test its KnowledgeQualityAssessment gate before phase closure. Canonical records govern, commits revalidate atomically, and Tasks stay within exact scope/budget.
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

## 7. R7-0 and R7-A closeout; R7-B preparation status

R7-0 documentation closeout:

- [x] R6 predecessor is formally closed and current main baseline recorded.
- [x] R7 scope, proposed phases, constraints, and non-goals are documented.
- [x] Proposed ADR-0032 and this entry gate identify the decisions and code-level constraints before R7-A.
- [x] The R7 Task/write-scope matrix is recorded as non-active until the corresponding Task implementation and tests merge.
- [x] Accepted INV-12 amendment is recorded in ADR-0032 and applied to docs/invariants.md.
- [x] PLAN.md, README.md, CONTEXT.md, CHANGE_MAP.md, and docs/decisions.md point to the same authority chain.
- [x] Operator explicitly accepted revised ADR-0032 on 2026-11-04.
- [x] Operator explicitly authorized R7-A implementation on 2026-11-04. R7-B and R7-C remain unauthorized.

R7-A implementation gate:

- [x] Operator acceptance of ADR-0032 and R7-A implementation authorization recorded.
- [x] Freeze remaining R7-A schema, evidence-reference, Task completion, retry/idempotency, and failure-injection contracts in [r7-a-implementation-plan.md](r7-a-implementation-plan.md) before source changes.
- [x] Separate explicit Operator instruction authorizes R7-A only; see §3 R7-A scope.
- [x] Local preflight and disposable-PostgreSQL verification completed on tested PR head 47ffa532dacbc10b146ac7b0768302761a2a0b1b, whose Git tree is identical to the merge commit.
- [x] DATABASE_URL and TEST_DATABASE_URL targeted the same fresh disposable PostgreSQL database; runner restored both variables and removed its container.
- [x] Source/migration/Task/invariant review and frozen R7-A implementation contract are recorded.
- [x] Deterministic lineage/rubric fixtures and failure/recovery tests are merged.
- [x] Exact-head hosted CI run 41844600681 passed.
- [x] Operator-local disposable-PostgreSQL verification passed: 631 tests, migration/head checks, Ruff, Mypy and cleanup.
- [x] No production evaluator provider was selected or invoked.

## 8. R7-0 documentation change record

R7-0 was delivered as a separate documentation-only PR. It changed no source, test, or migration files; that PR is merged. R7-A source changes are delivered separately.

- docs/decisions/ADR-0032-knowledge-quality-evaluation-and-lifecycle.md
- docs/development/r7-entry-gate.md
- docs/tasks.md — proposed R7 task/write-scope rows only; current scope matrix remains unchanged
- PLAN.md — current R7-0 status and next action only
- CHANGE_MAP.md — authority mapping
- docs/decisions.md — ADR index
- README.md and CONTEXT.md — concise roadmap/orientation

No source code, tests, migrations, schema, runtime configuration, provider configuration, active Task grants, or active invariant changes belong in R7-0. docs/tasks.md may contain a clearly marked proposed/non-active R7 matrix until corresponding R7 Task/service code is implemented; docs/invariants.md now contains the accepted INV-12 amendment. If an architecture decision requires runtime changes, record it as a proposal and resolve it before implementation.

## 9. R7-0 closeout record

**R7-0: COMPLETE — 2026-11-04.** The Operator accepted ADR-0032 and separately authorized R7-A. The documentation-only PR #38 passed exact-head hosted CI and merged to `main` at `c09578302927471d20e2236bb6fbfb018fab76c4`. This closeout does not authorize R7-B or R7-C.

**R7-A closeout:** PR #39 merged to main at 75122a7b34c15e2445b81a2a719020667b55bf06. Tested head 47ffa532dacbc10b146ac7b0768302761a2a0b1b has identical Git tree. Hosted CI [41844600681](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41844600681) passed; Operator-local disposable-PostgreSQL verification passed 631 tests in 79.22s, fresh single-head 0014_knowledge_quality migration, Ruff, Mypy and cleanup.

**Current gate:** R7-0, R7-A, R7-B B0 and B1 are complete. B2 Steps 1–8 are accepted and merged. Step 9 verification planning is in progress; exact-head hosted and Operator-local verification plus explicit B2 exit acceptance remain outstanding. The active approval allowlist remains exactly `create`. B3–B6 and R7-C remain unauthorized.
