# R6-F — Evidence-linked Experience Distillation: Implementation Plan

## Status, scope, and authority

**Current implementation status:** Checkpoint 1 is merged and verified (PR #29, merge commit `9a0ba491`); Checkpoint 2 is implemented on branch `r6f-checkpoint-2-experience-distiller` and awaits PR review/hosted CI and operator-local verification. This is the detailed R6-F implementation plan. `PLAN.md` remains the sole authority for current milestone status and implementation authorization.

**Step 0 historical boundary:** the original Step 0 created the planning branch, reconciled R6-E closeout status, and established this implementation/verification plan without application code or schema changes. Step 1 was subsequently authorized, implemented, merged, and locally verified. Step 2 is separately authorized by the current operator request.

**Predecessor:** R6-E is closed following PR #28's merge on 2026-11-01 (merge commit `3130e70fd25a35a73034ea412ef8a5af11eba17a`). R6-F Checkpoint 1 then merged as PR #29 at `9a0ba491dd13121178ac1e109d9e95a796bf1502`; hosted CI and operator-local disposable-PostgreSQL checks passed, including 526 full-suite tests. Cloudflare Workers AI remains authorized for R6-E only and is not an approved R6-F provider.

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

#### Detailed work

1. Re-read current models, migration chain, Task write-scope matrix, ADR-0028/0029, and relevant tests at the actual Step 1 starting commit. Confirm the database is still at the expected single Alembic head before adding a migration.
2. Resolve the data-shape questions in §4 before writing the migration, especially the multi-record evidence basis. Add one forward migration after the verified current head for the minimum required entities and constraints.
3. Add ORM mappings and typed schemas for:
   - **Evaluation:** Team ownership, referenced Outcome, subject/conclusion, findings, evaluator kind, evaluator identity/revision, status, Task attribution, and creation/recording metadata.
   - **Evaluation evidence:** the smallest EvidenceLink representation needed to bind an Evaluation to canonical Outcomes, Signals, and immutable Snapshots. Enforce Team ownership and exact Snapshot/hash/quote rules wherever quoted source spans are represented.
   - **KnowledgeItem:** canonical kind, title, statement/body, applicability, preconditions, assumptions, limitations, counterexamples, uncertainty, confidence, status, version, review metadata, and originating LearningChange. Do not store embeddings here.
   - **LearningChange:** operation and target, proposed/previous/committed state, status, proposing/committing Task attribution, operator identity, decision reason, and a complete multi-record evidence basis with deterministic hash.
4. Implement the narrow Evaluation application service. Distinguish proposed, recorded, and rejected Evaluations; revalidate Outcome/Signal/Snapshot ownership and hashes; preserve the evaluator's method/revision; and never mutate the Outcome being evaluated. Do not treat `ExecutionAssessmentBuilder` output as an Evaluation without an explicit, separately justified transformation.
5. Define exact Task types and allowed writes required for recording Evaluations and proposing/approving LearningChanges. Update `docs/tasks.md` in this checkpoint. Keep KnowledgeItem/LearningChange writes behind the learning commit boundary; application-managed Task/Event effects use existing `K` scope semantics.
6. Extend `TaskRuntime` only enough to finalize new learning Task result types safely. Define typed terminal result references and required Event/Outcome semantics; do not overload `success_no_change` to mean an Evaluation or LearningChange was committed. Preserve attempt fencing, replay, terminal Outcome uniqueness, and atomic Task finalization.
7. Do not add a general dispatcher. If a learning Task must execute in this slice, document its exact caller/service boundary and how it is admitted/finalized by the existing TaskRuntime before implementing it.
8. Add database constraints, indexes, unique/idempotency keys, and same-Team safeguards required by the selected design. Invalid statuses, missing provenance, duplicate per-operation records, and illegal target/version combinations fail closed.

#### Checkpoint 1 acceptance

- Fresh disposable PostgreSQL upgrade reaches one Alembic head; upgrade from the preceding head works.
- Evaluation proposal/record/rejection is attributable, replay-safe, and validates same-Team Outcome/evidence ownership and immutable Snapshot hashes.
- An Evaluation cannot be created as a side effect of an Outcome mutation; read-only execution assessment remains unchanged.
- Schema represents evidence from multiple independent Task Outcomes without lossy singular-basis semantics.
- KnowledgeItem and LearningChange canonical records exist, but no distiller can directly create or accept a KnowledgeItem.
- Task scopes and terminal result types are explicit; no second runtime, broad dispatcher, or TeamPolicy write permission is introduced.
- Database constraints, rollback, concurrent attempts, and Task/Event/Outcome attribution have focused tests.

### Checkpoint 2 — ExperienceDistiller and proposed LearningChange

**Purpose:** produce a traceable, bounded candidate abstraction from durable evidence. Stop at a proposed LearningChange.

#### Detailed work

1. Build a deterministic evidence-pack assembler from canonical records only: terminal Task Events and Outcomes, recorded Evaluations, applicable canonical Signal/Snapshot references, and narrowly relevant Plan/Action/Context provenance when present. Do not use unbounded transcripts or retrieval chunks as authority.
2. Bound the evidence pack deterministically by count and bytes/characters. Preserve each record's Team, Task ID, timestamp, source hash, evaluator identity/revision, and role in the basis.
3. Enforce ADR-0029's threshold before provider invocation:
   - one eligible Task/Outcome/Evaluation may produce only a narrow, low-confidence Practice candidate;
   - Pattern, Method, and Playbook require at least two distinct Task IDs, each with a recorded Evaluation and associated Outcome;
   - contrary/conflicting cases must be included or their omission due to bounded selection must be visible in the proposal basis.
4. Define a strict typed proposal schema requiring kind, title, statement, body, applicability, preconditions/task class, assumptions, limitations, non-applicability, failure modes, missing information, uncertainty, known counterexamples, supporting/contrary references, and deterministic evidence-basis hash.
5. Implement `ExperienceDistiller` (suggested module: `core/experience_distiller.py`) as a provider-facing proposal producer. Follow `StrategyProposer` patterns where useful, but do not couple distillation to Strategy acceptance or Plan creation. Treat all model output as untrusted.
6. Persist only a proposed LearningChange through the authorized proposal path. This checkpoint accepts only a KnowledgeItem create proposal with a null target ID. Malformed, unsupported, stale, cross-Team, incomplete, cost-rejected, or overgeneralized output must not create a usable proposal. This service must not create, revise, activate, or index a KnowledgeItem.
7. Reuse `TaskGenerationCostService` with the distinct `experience_distillation` operation. Reserve the maximum possible charge before the injected provider call, pin provider/model/pricing revision, reconcile usage, and fail closed for unknown usage, model mismatch, or overrun. In this checkpoint only a synthetic CI/test card is accepted; it is not a production rate card.
8. Use deterministic fake providers in CI and unit tests. No real provider/model call is permitted until the separate R6-F provider decision in §4 is resolved and explicitly approved. ADR-0031 does not extend the R6-E Cloudflare selection to distillation.

#### Checkpoint 2 acceptance

- Evidence pack and hash are identical for identical canonical inputs and change when any selected basis record changes.
- One-case generalization is rejected; single-case Practice stays narrow and explicitly low confidence; cross-case kinds require distinct Task IDs and recorded Evaluations.
- Every explicitly selected Evaluation and its Outcome is represented; supporting/challenging/mention links retain their declared stance. Uncertainty, applicability, non-applicability, and the absence of observed counterexamples within the available basis are explicit.
- Missing, stale, altered, cross-Team, unsupported, or contradictory references fail validation.
- Fake-provider success, malformed/schema-invalid output, provider error, replay after Task finalization, and concurrent duplicate proposal cases are covered.
- The synthetic test-provider maximum is reserved before provider invocation; unknown/overrun responses cannot yield a valid proposal. No production R6-F provider is enabled.
- No KnowledgeItem or TeamPolicy is written in this checkpoint.



#### Checkpoint 2 implementation boundary and mapping

The current implementation follows the explicit Evaluation-ID selection model: it does not perform a hidden top-k search for additional Evaluations. Every selected Evaluation and its primary execution Outcome is included in the basis; source and evaluator Task completion Events, Evaluation disposition Events, Snapshot references/hashes, and all EvidenceLinks are revalidated and included with their declared stance (supports, challenges, or mentions). The exact Task class must match all selected source Task types; the current checkpoint does not invent a cross-type equivalence taxonomy. "No counterexample was observed" is qualified as referring only to the available selected evidence basis. A broader candidate-selection/retrieval policy is not silently implied.

- core/experience_distiller.py: bounded canonical evidence pack, deterministic complete-basis hash, strict provider output schema, reference/stance validation, stale-basis recheck, and proposed-LearningChange writer.
- core/generation_cost.py: separate experience_distillation operation and synthetic CI/test rate card; existing Strategy accounting remains pinned to its existing Cloudflare card.
- core/task_runtime.py: typed success_learning_change_proposed result, proposal Event and current-attempt reconciled-charge checks; no second Task runtime.
- tests/test_experience_distiller.py: evidence provenance, one-/multi-case threshold, deterministic hash, stance preservation, reservation-before-call, unknown/overrun, malformed output, replay, concurrency, and TaskRuntime finalization tests.

No migration is introduced in Checkpoint 2. The existing 0012_learning_foundation schema is reused. The provider is injected through a narrow protocol; this branch does not ship or configure a live provider adapter.

### Checkpoint 3 — Operator review and canonical learning commit

**Purpose:** provide the only R6-F path that creates, revises, or retires canonical Team Experience.

#### Detailed work

1. Implement a narrow learning commit service (suggested module: `core/learning.py` or `core/learning_changes.py`). Keep proposal generation and commit logic separate.
2. Accept an authenticated operator identity from a trusted application boundary. Do not treat an arbitrary caller-provided string or model field as proof of operator authority. The repository has no full operator dashboard/API; expose a narrow service boundary rather than inventing an authentication subsystem as incidental scope.
3. For approval and rejection, lock the LearningChange and relevant target, then revalidate proposal status/idempotency, Team ownership of all referenced records, exact IDs/hashes/quotes, evidence-basis hash and distinct-Task threshold, current target status/version/operation, Task scope, operator authority, and concurrency preconditions.
4. On acceptance, atomically create or revise/retire the KnowledgeItem, preserve prior state in LearningChange history, store committed state and operator identity, advance canonical version, and emit required Task-attributed Events. Rejection records the decision and reason without creating or mutating a KnowledgeItem.
5. Same-operation replay returns the original disposition without another version. Competing approvals, stale target versions, changed evidence, or conflicting operations reject rather than last-write-win.
6. Narrow `approve_learning_change` to KnowledgeItem/LearningChange plus exact application-managed Events. **No R6-F approval path writes TeamPolicy.** Manual seeding is excluded unless separately approved and shown indispensable.
7. Decide and document `review_after` policy before making expiry-based retrieval eligibility operational. Do not invent an interval or silently treat a nullable timestamp as permanent validity.

#### Checkpoint 3 acceptance

- Explicit operator approval and rejection are durable, attributable, and auditable.
- Create/revise/retire transitions obey version/status rules; prior and committed states remain inspectable.
- Stale, missing, cross-Team, changed-hash, unauthorized, or concurrent proposals cannot commit.
- Injected failures roll back canonical mutations and required Events atomically.
- Replay cannot create a duplicate KnowledgeItem or version.
- No path changes TeamPolicy; no unreviewed proposal becomes canonical knowledge.

### Checkpoint 4 — Team Experience projection and later-task retrieval

**Purpose:** make only current accepted canonical Team Experience discoverable through the existing RAG/Context path.

#### Detailed work

1. Add a Team Experience indexer and projection representation. Preferred initial design: a separate `team_experience_chunks` table with canonical KnowledgeItem ID, Team, version, content hash, chunk identity/text, embedding model/revision, and index timestamps. Preserve the existing non-null `knowledge_chunks.signal_id` relationship and Signal-only meaning.
2. Reuse PostgreSQL + pgvector and full-text infrastructure, the BGE-M3 embedding interface, chunking approach, and provider readiness/failure handling. Do not add a separate vector database or put vectors on canonical KnowledgeItem records.
3. Index only the current canonical KnowledgeItem version when status is eligible (`active`) and its review date has not elapsed under the agreed review policy. Proposed, rejected, superseded, stale, retired, and `needs_review` versions must not be returned.
4. At indexing and retrieval, revalidate canonical Team ownership, version, status, content hash, and review eligibility. Similarity score is not authority.
5. Extend `HybridKnowledgeRetriever` and `TaskContextAssembler` so Domain Knowledge and Team Experience remain separate logical cores in results/manifests. Preserve source/KnowledgeItem IDs, version, canonical hash, index revision, retrieval configuration, and exact provenance.
6. Apply ADR-0028's global limits across both cores together: at most eight final passages and 8,000 Unicode characters. Do not give each core a separate full budget.
7. Keep canonical commit independent from projection publication. If indexing fails, retain the accepted KnowledgeItem/LearningChange, record projection staleness, exclude the unverified new version from retrieval, and permit idempotent retry/rebuild.
8. Prove later-Task reuse from canonical state and the index alone. Do not pass information through an earlier transcript or hidden fixture shortcut.

#### Checkpoint 4 acceptance

- Only the current accepted active KnowledgeItem version is eligible for retrieval.
- Cross-Team access, stale/superseded versions, review-expired content, rejected proposals, and unaccepted KnowledgeItems are excluded.
- Indexing/rebuild is idempotent; failed publication does not roll back canonical acceptance or falsely mark the version current.
- Context manifests distinguish Domain Knowledge and Team Experience and preserve exact source/version/hash provenance.
- Combined retrieval respects eight passages and 8,000 Unicode characters.
- A later Task retrieves accepted Team Experience after the original Task/session is gone.

## 4. Decisions and design questions to close before implementation

These are architecture decisions, not minor coding details. Resolve them against the cited authorities before Checkpoint 1 migration or Checkpoint 2 provider calls.

| ID | Decision required | Current issue | Recommended resolution / guard |
|---|---|---|---|
| D1 | Multi-record LearningChange evidence basis | The legacy architecture sketch has singular `basis_id`; ADR-0029 requires multiple Outcome/Evaluation references plus Signal/Snapshot and contrary evidence. | **Resolved for the first schema:** `LearningChange.evidence_basis` is a JSONB array of typed references with a required SHA-256 complete-basis hash. Checkpoint 3 must revalidate every reference against canonical records. Evaluation EvidenceLinks use normalized rows and same-Team composite foreign keys. |
| D2 | Evaluation model and evaluator identity | `ExecutionAssessmentBuilder` is read-only, not an Evaluation; Evaluation may be rule-, human-, or model-generated. | **Resolved in Checkpoint 1:** Evaluation targets one immutable Outcome, stores conclusion and structured findings, and follows the proposed-to-recorded-or-rejected lifecycle. Evaluator kind, stable identity, and revision are persisted. Findings separate observed/intended result, method, context, alternative explanations, attribution, and uncertainty. The read-only assessment builder remains separate. |
| D3 | Learning Task result and scope | `TaskRuntime` currently accepts ingestion-oriented terminal observations; dispatcher supports only `ingest_source`. The Task matrix describes learning types, but the complete production call path is not implemented. | **Resolved for Evaluation Tasks:** `evaluate_outcome` may write only Evaluation and Evaluation-scoped EvidenceLink records. TaskRuntime accepts `success_evaluation_recorded` / `success_evaluation_rejected` only when the referenced Evaluation belongs to the current Task and Team, has the matching final status, and the Task has both write scopes. No dispatcher or second runtime was added. Distiller/approval Task paths remain for later checkpoints. |
| D4 | Minimum EvidenceLink shape | The conceptual architecture describes a broad evidence-link system; R6-F needs only the subset supporting Evaluation provenance and exact source validation. | **Resolved in Checkpoint 1:** EvidenceLink is restricted to Evaluation subjects and Outcome or Signal sources. Composite foreign keys enforce same-Team Outcome and Evaluation ownership; Signal domain matching is revalidated against the Team's Domain by the service. Snapshot hashes and exact quote spans are checked against immutable Snapshot bytes. No generic polymorphic evidence graph is introduced. |
| D5 | Team Experience projection shape | `knowledge_chunks.signal_id` is mandatory and represents Signal-derived Domain Knowledge. | Prefer a distinct `team_experience_chunks` projection table while sharing embedding, chunking, FTS, and pgvector infrastructure. Do not weaken the Signal projection FK to fit two logical cores into an unsuitable schema. |
| D6 | R6-F generation provider/model | ADR-0031 authorizes Cloudflare Llama 3.1 8B FP8 for R6-E only and explicitly defers R6-F use. | Use deterministic fakes in tests. Before real requests, obtain explicit provider/model, data-handling, token/cost, and rate-card approval; update/extend the applicable ADR. Do not infer authorization from R6-E credentials/configuration. |
| D7 | Review/expiry semantics | ADR-0029 makes `review_after` part of retrieval eligibility, but interval/default and who advances a due item to `needs_review` are not pinned. | Agree interval source, timezone, due boundary, null semantics, and transition owner before enabling expiry filtering. No invented default; absent a rule, keep expiry behavior gated/fail closed. |
| D8 | Operator authorization boundary | There is no full API/dashboard authentication system in the repository. | Require identity from a trusted caller and persist it. Do not claim arbitrary input authenticates an operator or build unrelated authentication infrastructure in R6-F. |
| D9 | Evaluation generation approach | Evaluations are fallible and evaluators may be biased. | Choose the first-slice evaluator source (rule, trusted human input, or separately approved model proposal). Evaluator cannot self-record or self-approve. Do not add self-modifying evaluation procedures. |

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
| 3 — operator commit | Create/revise/retire; approval/rejection identity; stale target; concurrent commit; rollback; exact replay; no TeamPolicy mutation. |
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
