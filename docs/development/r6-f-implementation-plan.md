# R6-F — Evidence-linked Experience Distillation: Implementation Plan

## Status, scope, and authority

**Current implementation status:** Checkpoints 1–2 are merged and verified (PR #29 at `9a0ba491`; PR #30 at `61be8db75b6bd4e23fcc91ef00f1a8f0a833dde0`). Checkpoint 3's create-only Operator approval path is implemented on draft [PR #31](https://github.com/abtn/Watch-Architecture-Rev2/pull/31) and was locally/hosted verified on code head `581ad185` (83 focused tests, 577 full-suite tests, Ruff, mypy 27 files, one Alembic head at `0012_learning_foundation`). D10 is resolved: revise/retire proposal production and commitment are deferred beyond C3 until a separately authorized knowledge-lifecycle source exists. D7 is resolved and implemented in C4: optional schema-v2 TeamPolicy rule `review.knowledge_item_interval_days` pinned to the approval Task's policy version; UTC `committed_at + N days`; NULL/due items excluded; ordinary `review_knowledge` Task owns `active → needs_review`. Checkpoint 4 was explicitly authorized on 2026-11-02 and is implemented on draft [PR #32](https://github.com/abtn/Watch-Architecture-Rev2/pull/32), branch `r6f-checkpoint-4-team-experience`, stacked on the C3 branch. It adds migration `0013_team_experience_projection`, separate `team_experience_chunks` and `team_experience_index_state`, canonical index/rebuild, dual-core PostgreSQL/pgvector + FTS RRF retrieval, shared eight-passage/8,000-character bounds, Context v2 provenance and immutable v1 same-Task replay, and atomic/replayable review Task completion. Hosted CI run [41589798190](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41589798190) passed on `3682f7e`: migration to one Alembic head at `0013_team_experience_projection`, Ruff, mypy (27 files), and 588 tests. Operator-local disposable-PostgreSQL verification is the next gate. PR #31 and #32 remain open/draft/unmerged; C3 must integrate before C4 is retargeted/integrated. C4 is not formally closed until local verification and sequential integration pass. R6-G remains separately gated. `PLAN.md` is the sole milestone/authorization authority.


**Historical boundaries:** Original Step 0 created the planning branch and established this plan without application changes. Step 1/Checkpoint 1 and Step 2/Checkpoint 2 were separately authorized, implemented, merged, and locally verified. Checkpoint 3 is separately authorized by the operator's explicit instruction on 2026-11-01. Checkpoint 4 was separately authorized on 2026-11-02. Neither checkpoint authorization extends to R6-G.

**Predecessor:** R6-E is closed following PR #28's merge on 2026-11-01 (merge commit `3130e70fd25a35a73034ea412ef8a5af11eba17a`). R6-F Checkpoint 1 merged as PR #29 at `9a0ba491dd13121178ac1e109d9e95a796bf1502`; hosted CI and operator-local disposable-PostgreSQL checks passed, including 526 full-suite tests. Checkpoint 2 merged as PR #30 at `61be8db75b6bd4e23fcc91ef00f1a8f0a833dde0` from implementation head `d6b8d07562c72e8ffa7989f24396ea1e73d45442`; hosted CI run `41315770806` passed. Operator-local verification passed fresh disposable-PostgreSQL migration to the single head `0012_learning_foundation`, 36 focused tests, Ruff, mypy (25 source files), and 543 full-suite tests; the corrected head also passed `git diff --check`. Cloudflare Workers AI remains authorized for R6-E only and is not an approved R6-F provider.

**Governing contracts:**
- [ADR-0028 — RAG-backed Knowledge Cores](../decisions/ADR-0028-rag-backed-knowledge-cores.md): canonical-vs-projection boundary, Team Experience Core, PostgreSQL hybrid retrieval, scope, freshness, provenance, and bounded Context.
- [ADR-0029 — LLM-assisted Experience Distillation](../decisions/ADR-0029-llm-assisted-experience-distillation.md): evidence-linked abstraction, multi-case threshold, operator-reviewed LearningChange, versioning, and publication.
- [ADR-0030 — R6 bounded execution, source safety, and Outcome](../decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md): Task lifecycle and immutable terminal execution evidence.
- [ADR-0031 — Cloudflare Workers AI generation](../decisions/ADR-0031-cloudflare-workers-ai-generation.md): authorizes the selected provider for R6-E only and explicitly defers R6-F distillation use.
- [docs/invariants.md](../invariants.md), especially INV-02, INV-03, INV-04, INV-11, INV-12, INV-13, INV-14, and INV-15.
- [docs/tasks.md](../tasks.md): Task types, write scopes, application-managed effects, and budgets.

If this plan and an accepted ADR differ, stop and reconcile the conflict before implementation. A recommendation below is not an accepted architectural decision unless its governing authority is updated through the repository's decision process.

## 1. Objective and boundaries

R6-F implements the first controlled path that turns durable, evaluated work into reusable Team Experience:

**Task execution → terminal Outcome → recorded Evaluation → bounded distillation proposal → validated LearningChange → explicit Operator approval → canonical KnowledgeItem version → regenerable Team Experience projection → retrieval by a later Task.**

Keep these concepts distinct:

- **Outcome:** a durable observation of what happened during a Task. It is not an explanation, evaluation, or proof that the Task caused the observed result.
- **Evaluation:** a recorded, attributable assessment of an Outcome and its supporting evidence. It is fallible and retains evaluator identity/revision and its evidence basis.
- **LearningChange:** a proposed and reviewed change to Team Experience. A generated proposal is not accepted knowledge.
- **KnowledgeItem:** the canonical, versioned record of an accepted practice, pattern, method, or playbook.
- **Retrieval projection:** a rebuildable index over eligible canonical KnowledgeItems. It is never authoritative and cannot itself accept, revise, or retire knowledge.

R6-F covers the smallest complete path for one Team. It does not implement a general knowledge graph, broad World-memory entity families, multi-Team transfer, model training/fine-tuning, recursive self-improvement, automatic policy adaptation, or an autonomous learning loop. It introduces no second Task runtime, scheduler, or workflow engine.

### Authority and safety boundaries

1. Model output is untrusted proposal data. Application code validates schema, provenance, Team ownership, evidence thresholds, scope, status, version, and concurrency.
2. Only the authorized learning commit path changes canonical KnowledgeItems. Every first-slice LearningChange is explicitly reviewed by an Operator through `approve_learning_change`.
3. R6-F must not modify TeamPolicy. The approval scope is narrowed to LearningChange and KnowledgeItem plus exact application-managed Events; the older generic Task matrix must not be interpreted as permission to write TeamPolicy during R6-F.
4. Outcomes, source Snapshots, and accepted historical versions are immutable evidence. Corrections and revisions create new attributable records or versions.
5. A single apparent success may support only a narrow, low-confidence Practice candidate. A cross-case Pattern, Method, or Playbook requires at least two independently recorded Outcomes from distinct Task IDs, each with a corresponding recorded Evaluation. This permits a proposal; it does not prove causation or transferability.
6. Preserve contrary cases, known failure modes, non-applicability, assumptions, limitations, missing information, and uncertainty. If no counterexample appears in the evidence pack, say it was not observed in the available basis; do not claim none exists.
7. Canonical learning commit and retrieval projection are separate operations. Projection failure must not roll back or falsify the canonical decision, and the new version must not be advertised as retrievable until its projection is current and verified.
8. Persistence is not proof of cumulative intelligence. R6-F proves traceable storage and later retrieval, not that every stored lesson is correct or useful.

## 2. Existing implementation baseline and gaps

The verified repository baseline has a single Alembic lineage ending at `0011_task_generation_cost`.

| Area | Existing capability | R6-F implication |
|---|---|---|
| Task execution | `TaskRuntime` owns admission, attempts, terminal Task state, Events, and terminal `task_execution` Outcomes. | Reuse this one lifecycle authority. Its terminal result shape is ingestion-oriented and must be extended narrowly for learning operations. |
| Dispatch | `TaskDispatcher` currently dispatches the configured-source `ingest_source` path. | Do not turn it into a general dispatcher or add a second runner. Define narrow service entrypoints and the existing TaskRuntime admission/finalization boundary for learning operations. |
| Execution assessment | `ExecutionAssessmentBuilder` is deterministic and read-only. | It is not a persisted Evaluation and must not be relabelled or repurposed as one. |
| Persistence | ORM models include Task, Outcome, TaskGenerationCharge, and KnowledgeChunk, but no Evaluation, EvidenceLink, KnowledgeItem, or LearningChange ORM implementation. | Add the minimum canonical learning schema and constraints. Recheck source and migration head before selecting a migration number. |
| Domain Knowledge index | `knowledge_chunks.signal_id` is mandatory and Signal-scoped. | Preserve its meaning. Preferred Team Experience design: a separate projection table rather than weakening the Signal foreign key. |
| Retrieval and Context | `HybridKnowledgeRetriever` searches authorized Signal passages; `TaskContextAssembler` currently exposes Domain Knowledge. | Extend retrieval and Context manifests to distinguish Domain Knowledge and Team Experience while preserving global passage/character limits. |
| Generation and cost | R6-E provides a replaceable generation boundary and `TaskGenerationCostService`. | Reuse the accounting pattern with a distinct operation key such as `experience_distillation`; reserve before any real provider call. |

The architecture describes conceptual Evaluation, EvidenceLink, KnowledgeItem, and LearningChange fields, but the ORM/migrations do not implement them. Derive the schema from accepted ADRs and current code, not by copying legacy conceptual columns blindly. Embeddings belong in rebuildable projection rows, not canonical KnowledgeItem records.

## 3. Recommended delivery structure: four checkpoints

R6-F should be divided into four checkpoints. They follow distinct authority boundaries and allow meaningful verification before moving on. Each checkpoint is a separate implementation/review unit. Under the established operator workflow, hosted CI must pass first; the operator then syncs and performs local verification against disposable PostgreSQL. Do not start the next checkpoint until that local result is reported and reconciled.

### Checkpoint 1 — Evaluation and canonical learning foundation

**Purpose:** make evidence and canonical learning records real without allowing a model to publish accepted Team Experience.

#### Implemented work

1. **Separate projection:** added `TeamExperienceChunk` / `team_experience_chunks`, with composite same-Team KnowledgeItem and originating LearningChange foreign keys. The existing `knowledge_chunks.signal_id` and Signal-only Domain Knowledge projection remain unchanged.
2. **Shared retrieval infrastructure:** reuses the current provider-neutral embedding adapter and embedding-space identity, deterministic chunker, PostgreSQL full-text search, pgvector vector search, and reciprocal-rank fusion. No new provider, vector database, or embedding service.
3. **Canonical eligibility and integrity:** indexing validates accepted create LearningChange, approval Task, exact decision Event and terminal Outcome, full committed KnowledgeItem state, current item version, active status, and non-null future UTC review date. The item is locked and rechecked after embedding before chunk publication.
4. **Dual-core retrieval:** both logical cores use the same query embedding, FTS/vector candidate search, and RRF. Candidates are fused and then passed through one global eight-passage/8,000-Unicode-character bound.
5. **Context v2:** Context and manifest record logical core, canonical Signal or KnowledgeItem ID, KnowledgeItem version, content hash, LearningChange provenance, chunk ID/index/hash, and embedding-space identity. Existing same-Task Context v1 snapshots replay immutably; a later Task performs fresh retrieval without transcript reuse.
6. **Publication state and rebuild:** `TeamExperienceIndexState` / `team_experience_index_state` records `stale`, `published`, or `ineligible`, plus canonical item/version/hash/origin, embedding-space key, chunk/attempt counts, last error class, attempt time, and publication time. An indexing attempt marks state stale before the provider call. Projection chunks and published state commit atomically. A failure records stale/error metadata without changing canonical KnowledgeItem or LearningChange; retrieval/Context require matching published state. `rebuild_all()` includes stale state rows and retries idempotently.
7. **Deterministic review Task:** the existing TaskRuntime owns due status transitions and their Event/Outcome transaction. The host only enqueues the ordinary Task.
8. **Later-Task proof:** an independent Strategy Task retrieves Team Experience through the normal retriever and receives it in immutable Context with canonical provenance.

#### Checkpoint 4 acceptance#### Checkpoint 4 acceptance

- Only the current accepted `active` KnowledgeItem with a non-null `review_after` strictly later than retrieval time is eligible.
- Cross-Team access, stale/superseded versions, NULL-dated items, review-due/expired content, rejected proposals, and unaccepted KnowledgeItems are excluded, even when a due item's stored status has not yet changed to `needs_review`.
- Tests prove pinned-policy date assignment, policy-schema validation, absence of defaults, UTC calculation and exact-boundary behavior, no retroactive rewrite/backfill, and fail-closed rejection of invalid configured values.
- Tests prove that only `review_knowledge` Task execution changes due items to `needs_review`, with atomic Task-attributed Event, idempotent retry/concurrency, no scheduler-side mutation, and no automatic reactivation.
- Indexing/rebuild is idempotent; failed publication leaves a durable `stale` state and no discoverable chunks while canonical acceptance remains unchanged. Successful chunk rows and `published` state commit atomically; NULL/due items become `ineligible`. Retrieval and Context require a matching published state plus canonical checks.
- Context manifests distinguish Domain Knowledge and Team Experience and preserve exact source/version/hash provenance.
- Combined retrieval respects eight passages and 8,000 Unicode characters.
- A later Task retrieves accepted Team Experience after the original Task/session is gone.

## 4. Decisions and design questions to close before implementation

These are architecture decisions, not minor coding details. Resolve each remaining decision before the implementation step it governs; Checkpoints 1 and 2 are complete.

| ID | Decision required | Current issue | Recommended resolution / guard |
|---|---|---|---|
| D1 | Multi-record LearningChange evidence basis | The legacy architecture sketch has singular `basis_id`; ADR-0029 requires multiple Outcome/Evaluation references plus Signal/Snapshot and contrary evidence. | **Resolved for the first schema:** `LearningChange.evidence_basis` is a JSONB array of typed references with a required SHA-256 complete-basis hash. Checkpoint 3 must revalidate every reference against canonical records. Evaluation EvidenceLinks use normalized rows and same-Team composite foreign keys. |
| D2 | Evaluation model and evaluator identity | `ExecutionAssessmentBuilder` is read-only, not an Evaluation; Evaluation may be rule-, human-, or model-generated. | **Resolved in Checkpoint 1:** Evaluation targets one immutable Outcome, stores conclusion and structured findings, and follows the proposed-to-recorded-or-rejected lifecycle. Evaluator kind, stable identity, and revision are persisted. Findings separate observed/intended result, method, context, alternative explanations, attribution, and uncertainty. The read-only assessment builder remains separate. |
| D3 | Learning Task result and scope | `TaskRuntime` currently accepts ingestion-oriented terminal observations; dispatcher supports only `ingest_source`. The Task matrix describes learning types, but the complete production call path is not implemented. | **Resolved for Evaluation Tasks:** `evaluate_outcome` may write only Evaluation and Evaluation-scoped EvidenceLink records. TaskRuntime accepts `success_evaluation_recorded` / `success_evaluation_rejected` only when the referenced Evaluation belongs to the current Task and Team, has the matching final status, and the Task has both write scopes. No dispatcher or second runtime was added. Distiller/approval Task paths remain for later checkpoints. |
| D4 | Minimum EvidenceLink shape | The conceptual architecture describes a broad evidence-link system; R6-F needs only the subset supporting Evaluation provenance and exact source validation. | **Resolved in Checkpoint 1:** EvidenceLink is restricted to Evaluation subjects and Outcome or Signal sources. Composite foreign keys enforce same-Team Outcome and Evaluation ownership; Signal domain matching is revalidated against the Team's Domain by the service. Snapshot hashes and exact quote spans are checked against immutable Snapshot bytes. No generic polymorphic evidence graph is introduced. |
| D5 | Team Experience projection shape | `knowledge_chunks.signal_id` is mandatory and represents Signal-derived Domain Knowledge. | Prefer a distinct `team_experience_chunks` projection table while sharing embedding, chunking, FTS, and pgvector infrastructure. Do not weaken the Signal projection FK to fit two logical cores into an unsuitable schema. |
| D6 | R6-F generation provider/model | ADR-0031 authorizes Cloudflare Llama 3.1 8B FP8 for R6-E only and explicitly defers R6-F use. | Use deterministic fakes in tests. Before real requests, obtain explicit provider/model, data-handling, token/cost, and rate-card approval; update/extend the applicable ADR. Do not infer authorization from R6-E credentials/configuration. |
| D7 | Review/expiry semantics | ADR-0029 makes `review_after` part of retrieval eligibility; interval/default, due boundary, NULL behavior, and transition owner were not pinned. | **Resolved 2026-11-02 by explicit operator decision:** optional `review.knowledge_item_interval_days` in a forward TeamPolicy rules-schema revision; positive non-boolean integer, no default; use the `approve_learning_change` Task's pinned policy version; `review_after = committed_at + N × 24 hours` in UTC; NULL is unscheduled and excluded from retrieval; due at `now_utc >= review_after`; a deterministic ordinary `review_knowledge` Task alone commits `active → needs_review` plus Event atomically. Retrieval excludes due items immediately before the Task runs. No automatic reactivation, retroactive NULL backfill, TeamPolicy write, scheduler/runtime expansion, or Checkpoint 4 authorization. See ADR-0029 and `docs/tasks.md`.
| D8 | Operator authorization boundary | No separate deployed Watch API/CLI or authentication subsystem exists; the host application is the authentication root. | **Resolved direction:** Checkpoint 3 includes a thin in-repository adapter invoked in-process by the host after authentication and Team/action authorization. Pass typed issuer/subject context; reject raw request/model identity. The adapter is not a deployed API/CLI or authentication credential. |
| D9 | Evaluation generation approach | Evaluations are fallible and evaluators may be biased. | Choose the first-slice evaluator source (rule, trusted human input, or separately approved model proposal). Evaluator cannot self-record or self-approve. Do not add self-modifying evaluation procedures. |
| D10 | Reachability of revise/retire LearningChanges | Checkpoint 2 emits only `operation="create"` proposals, while the earlier broad Checkpoint 3 acceptance language also named revise/retire. | **Resolved 2026-11-02 by explicit operator decision:** Checkpoint 3 is complete in scope for genuine Checkpoint 2 create proposals only. Revise/retire proposal production and commitment are deferred beyond Checkpoint 3 until a separately authorized knowledge-lifecycle scope supplies a genuine proposal source and defines target-version pinning, history, concurrency, replay/recovery, and projection invalidation. Schema vocabulary does not authorize those paths; no seed, direct DB write, test-only injection, ad-hoc endpoint, or bypass. This narrows Checkpoint 3 delivery scope and does not amend ADR-0029's broader lifecycle principles.
| D11 | Manual Task deadline and recovery semantics | Human approval happens before Task creation; only synchronous application work runs in `running`. Admission requires positive `deadline_seconds`; generic recovery uses a 60-second stale threshold. | **Implementation contract:** allow the documented no-deadline budget for `approve_learning_change` only; preserve generic 60-second stale recovery. Prove crash/recovery same-request/same-Task replay; no human waits in a Task. |
| D12 | Durable approval target and request idempotency | Task has no `input_refs`, target column, or generic request-key column; Event indexing is not unique. | **Preferred design:** host idempotency UUID + fixed UUIDv5 namespace maps Team + `approve_learning_change` + request UUID to one Task primary key. Insert Task and fingerprinted request Event atomically; add minimal schema only if PostgreSQL tests expose an integrity gap. |

## 5. Cross-cutting implementation rules

- **No transcript memory:** evidence packs use canonical records and immutable Snapshots, not chat history.
- **No causality inflation:** sequence, correlation, or successful Task status does not prove that the Task caused an outcome.
- **No confidence laundering:** model confidence or fluent prose cannot replace independent Outcomes, recorded Evaluations, or source evidence.
- **No hidden write scopes:** update the Task matrix before adding a Task caller; application-managed `K` writes remain exact and narrow.
- **No policy learning:** R6-F LearningChanges target KnowledgeItems only. TeamPolicy is excluded.
- **No stale retrieval:** revalidate current canonical version/status/hash at retrieval.
- **No index authority:** projections and embeddings are disposable and rebuildable.
- **No provider assumptions:** R6-E provider selection does not authorize R6-F calls.
- **No premature R6-G closure:** an isolated distillation path is not the full R6 exit gate.

## 6. Verification and delivery protocol

For each checkpoint:

1. Add focused tests for successful, rejected, and failure paths.
2. Run focused tests first, then Ruff, mypy, and applicable full-suite/CI checks.
3. Run migrations and database concurrency/rollback tests against an explicitly identified disposable PostgreSQL database. Verify exactly one Alembic head.
4. Exercise replay after restart and injected failures at transaction/projection boundaries.
5. Confirm hosted CI on the checkpoint head before operator sync.
6. Operator syncs the branch, verifies branch/HEAD/worktree, runs named local checks against disposable PostgreSQL, and reports results.
A PR is opened only with explicit operator authorization; the operator explicitly requested a Checkpoint 1 PR for this delivery. Advance only after hosted CI and operator-local verification are reviewed.

| Checkpoint | Focused verification |
|---|---|
| 1 — canonical foundation | Migration from prior head; one head; Evaluation lifecycle; evidence ownership/hash/quote checks; schema constraints; TaskRuntime lifecycle/replay; no direct KnowledgeItem or TeamPolicy writes. |
| 2 — distillation proposal | Fake-provider valid/invalid output; one-case threshold; distinct-Task multi-case evidence; contrary cases; deterministic basis hash; stale/cross-Team refs; cost reserve/unknown/overrun; proposal replay. |
| 3 — operator commit | Create-only proposal approval/rejection; host identity and authorization; stale evidence/target; concurrent decisions; atomic rollback; exact replay and crash recovery; no revise/retire production path or TeamPolicy mutation. |
| 4 — retrieval projection | Team/status/version/review filtering; projection failure/rebuild; canonical recheck; manifest provenance; global passage/character limits; later-Task reuse. |

Use standard commands in [docs/testing.md](../testing.md). Never use the persistent `watch` database for test/migration verification. Do not claim a full suite, migration, provider smoke, or local verification passed unless that exact check ran on the named state.

## 7. R6-F exit criteria and boundary to R6-G

R6-F is complete only when all four checkpoints are implemented and verified and the following path is demonstrated:

1. A terminal Task Outcome and immutable evidence remain canonical and unchanged.
2. A valid Evaluation is recorded with evaluator identity/revision and traceable evidence.
3. The distiller proposes a typed LearningChange whose basis is deterministic, multi-record, Team-scoped, and satisfies one-case/cross-case rules.
4. An Operator explicitly accepts or rejects it through the authorized learning path.
5. Acceptance creates one canonical KnowledgeItem version with prior/current history; rejection creates no usable KnowledgeItem.
6. Only the current accepted eligible version is projected.
7. A later Task retrieves that Team Experience through the existing Context path, with provenance and global limits intact.
8. Transaction failure, duplicate replay, concurrency, stale evidence/target, provider error, missing usage, projection failure, and rebuild behavior are covered.
9. Hosted CI, fresh disposable-PostgreSQL migration/integration checks, focused/full tests, Ruff, mypy, and `git diff --check` are recorded honestly.

R6-F does not close R6. R6-G remains the integrated vertical slice and explicit R6 exit gate described in [the R6 entry gate](r6-entry-gate.md).

## 8. Step 0 completion record

Step 0 is complete when the R6-F branch exists from verified current `main`, R6-E closeout and project status documents agree, this plan and unresolved decisions are linked from the authority map and entry gate, and the documentation change is committed on the R6-F branch without application-code changes.

**Step 1 is not part of Step 0.** The first implementation checkpoint is Checkpoint 1 above. Its migration/schema choices must first resolve the decision items in §4.

## Checkpoint 1 implementation record — R6-F Step 1

**Status:** implementation committed on `r6f-experience-distillation`; hosted CI and operator-local disposable-PostgreSQL verification are pending.

- Migration `0012_learning_foundation` follows `0011_task_generation_cost` as the only Alembic successor.
- Evaluation is Outcome-scoped, attributable to its creating/resolving Task, and records evaluator kind, identity, revision, conclusion, structured findings, idempotency key, and proposal hash.
- EvidenceLink is Evaluation-scoped. Outcome references use same-Team composite foreign keys; Signal ownership is checked against the Team's Domain by the service. Snapshot hashes and quote offsets are verified against immutable Snapshot bytes.
- LearningChange stores a typed JSONB evidence-basis collection and complete-basis hash; the legacy singular `basis_id` is not the sole basis.
- KnowledgeItem requires a same-Team originating LearningChange. Embeddings are absent from canonical KnowledgeItem.
- TaskRuntime recognizes typed Evaluation terminal results through the existing lifecycle authority. No dispatcher, provider, distiller, approval writer, TeamPolicy writer, or retrieval projection was added.

**Checkpoint 1 boundary:** proposal/record/reject for Evaluations only. LearningChange and KnowledgeItem are schema foundations; no application write path for either is introduced in this checkpoint. D5–D9 remain gated for their relevant later work.
