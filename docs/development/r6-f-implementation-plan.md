# R6-F — Evidence-linked Experience Distillation: Implementation Plan

## Status, scope, and authority

**Current implementation status:** Checkpoints 1–2 are merged (PR #29 at `9a0ba491`; PR #30 at `61be8db75b6bd4e23fcc91ef00f1a8a833dde0`). C3 create-only was merged to `main` by PR #31 at `99f8b6bbd76521eaac47761dcf432ebb3c0d28e3`; final operator-local verification passed 85 focused/579 full-suite tests, Ruff, mypy (27 files), fresh migration to one `0012_learning_foundation` head, and `git diff --check`. D10 remains create-only; revise/retire proposal production and commitment are deferred. D7 is resolved and implemented in C4: optional schema-v2 TeamPolicy interval pinned to approval Task policy version, UTC review date, NULL/due retrieval exclusion, and deterministic review Task. C4 has been reconciled against merged `main`; it adds migration `0013_team_experience_projection`, separate projection/publication ledger, canonical index/rebuild, dual-core retrieval, Context v2 provenance/v1 replay, and TaskRuntime review completion. Earlier C4 hosted CI run `41589798190` passed 588 tests on `3682f7e`; fresh hosted CI and combined local verification are pending on reconciled PR #32. `PLAN.md` remains the sole status/authorization authority.

**Historical boundaries:** Original Step 0 created the planning branch and established this plan without application changes. Step 1/Checkpoint 1 and Step 2/Checkpoint 2 were separately authorized, implemented, merged, and locally verified. Checkpoint 3 was separately authorized on 2026-11-01. Checkpoint 4 was later separately authorized and implemented on stacked PR #32; neither checkpoint authorization extends to R6-G.

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

### Checkpoint 2 completion record — 2026-11-01

PR #30 merged to `main` at `61be8db75b6bd4e23fcc91ef00f1a8f0a833dde0` (implementation head `d6b8d07562c72e8ffa7989f24396ea1e73d45442`). Hosted CI run [41315770806](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41315770806) passed on the corrected head. Operator-local verification used the disposable container `watch-r6f-step2-pg`, database `watch_ci`, and port `55457`; migration reached the single head `0012_learning_foundation`, 36 focused tests passed, Ruff passed, mypy passed on 25 source files, and the full suite passed with 543 tests. The disposable container was removed and the database environment variables were restored. Two surplus EOF newlines were then removed from `CHANGE_MAP.md` and `tests/test_experience_distiller.py`; after syncing those whitespace-only commits, `git diff --check origin/main...HEAD` passed. Checkpoint 2 is CLOSED. No live R6-F provider was used or authorized.

### Checkpoint 3 — Operator review and canonical learning commit

**Status and authorization (updated 2026-11-03): IMPLEMENTED, MERGED, AND LOCALLY VERIFIED FOR CREATE-ONLY SCOPE.** C3 was merged by PR #31 to `main` at `99f8b6bbd76521eaac47761dcf432ebb3c0d28e3`. Final operator-local disposable-PostgreSQL verification passed on head `891bea490099a7478ef3538645f8924615187500`: 85 focused tests, 579 full-suite tests, Ruff, mypy (27 files), fresh migration to the single `0012_learning_foundation` head, and `git diff --check`. This included the D12 competing-approval loser-Task finalization and recovery cases. D10 remains resolved: C3 is create-only; revise/retire production is deferred. No C3 schema migration was introduced.

**Purpose:** provide the R6-F canonical learning-commit boundary. Checkpoint 3 implements that boundary for real create-only LearningChanges; revise/retire proposal production and commitment are deferred beyond this checkpoint until a separately authorized knowledge-lifecycle scope exists.

#### Detailed work

1. Implement a narrow learning commit service (suggested module: `core/learning.py` or `core/learning_changes.py`). Keep proposal generation and commit logic separate.
2. Accept an authenticated operator identity from a trusted application boundary. Do not treat an arbitrary caller-provided string or model field as proof of operator authority. The repository has no full operator dashboard/API; expose a narrow service boundary rather than inventing an authentication subsystem as incidental scope.
3. For approval and rejection, lock the LearningChange and relevant target, then revalidate proposal status/idempotency, Team ownership of all referenced records, exact IDs/hashes/quotes, evidence-basis hash and distinct-Task threshold, current target status/version/operation, Task scope, operator authority, and concurrency preconditions.
4. For this checkpoint's create-only path, acceptance atomically creates exactly one active KnowledgeItem version 1, preserves the committed state and LearningChange history, stores Operator/Task attribution, and emits the required Task-attributed decision Event. Rejection records the decision and reason without creating or mutating a KnowledgeItem. Revision and retirement transitions are not implemented or required here; they remain deferred until a separately authorized proposal source and their target-version/history/concurrency/projection semantics are defined.
5. Same-operation replay returns the original disposition without another version. Competing approvals, stale target versions, changed evidence, or conflicting operations reject rather than last-write-win.
6. Narrow `approve_learning_change` to KnowledgeItem/LearningChange plus exact application-managed Events. **No R6-F approval path writes TeamPolicy.** Manual seeding is excluded unless separately approved and shown indispensable.
7. **D7 resolved 2026-11-02:** `review.knowledge_item_interval_days` is optional TeamPolicy input, positive non-boolean integer only, with no default. The accepting approval Task's pinned `policy_version` supplies the value. Compute UTC `review_after = committed_at + N × 24 hours`; a missing key yields NULL, which is excluded from indexing/retrieval. Due at `now_utc >= review_after`. Only the deterministic `review_knowledge` Task changes `active → needs_review`; retrieval excludes due items before that Task runs. The key requires a forward rules-schema revision. Do not backfill old NULL dates or authorize TeamPolicy writes through this checkpoint.

#### Initial Checkpoint 3 implementation sequence

**Audit decision:** Checkpoint 3 includes a thin in-repository application adapter. The host authenticates and authorizes the Operator, then invokes the adapter in-process with a typed principal context. No separate deployed Watch API/CLI or Watch-owned authentication subsystem is planned. See [the detailed boundary audit](r6-f-checkpoint-3-operator-boundary-audit.md).

1. **Host principal/authorization contract:** stable issuer + subject and exact Team/action grant. Host owns authentication/authorization. No bare `operator_id`, request-body identity, display name, email, or model field as proof. A Python object is an in-process contract, not cryptographic proof; call only from trusted host path.
2. **Thin adapter:** add `core/operator_application.py` for synchronous `approve_learning_change`. Host supplies typed principal and a request with LearningChange ID, decision, rejection reason where needed, and host-generated idempotency UUID; the adapter derives Team from the LearningChange rather than trusting a caller-supplied Team. No routes, CLI, login, token verifier, user store, or second runtime.
3. **Pending Task and durable replay:** create one same-Team pending Task using current policy, no Objective/Plan/Action links, exact `["LearningChange", "KnowledgeItem"]` grant, zero tools/cost. Preferred design: derive Task UUIDv5 from fixed namespace + Team + Task type + host idempotency UUID; atomically insert Task and `operator_task_requested` Event with target, canonical actor, decision, and request fingerprint. Same key/same request replays; changed content conflicts. Add schema only if PostgreSQL restart/concurrency tests prove an integrity gap.
4. **Existing runtime admission (implemented and locally verified):** `TaskRuntime.admit` alone starts the approval Task. Permit the no-deadline budget only when the approval Task has exact scope, zero tools/cost, no Objective/Plan/Action links, the pinned attempt limit, one intact canonical request Event/fingerprint, and a same-Team create proposal target. Keep normal Team quota accounting and generic 60-second recovery; ordinary Task types still require a positive deadline. Do not insert a running Task or mutate lifecycle directly.
5. **Canonical decision service (implemented and locally verified on `bddd1e9`):** `LearningCommitService` reads target and decision from the durable request Event, rechecks the host principal/current Task attempt, rebuilds the bounded evidence pack from canonical Evaluation/Outcome/EvidenceLink/Snapshot records through a provider-free read-only `ExperienceDistiller` path, and accepts/rejects only `knowledge_item/create` proposals. Acceptance atomically creates one active KnowledgeItem v1 and commits LearningChange history/actor/Task attribution plus one decision Event. Rejection commits the reason/actor/Task plus one Event and creates no KnowledgeItem. No TeamPolicy writes.
6. **Replay integrity (implemented):** verify exact decision Event payload/timestamp, the start Events for the original and current attempts, and every canonical KnowledgeItem field against `LearningChange.committed_state`. Tampered evidence, actor, policy pin, canonical item, or decision Event fails closed.
7. **Typed TaskRuntime finalization (implemented on draft PR #31):** accepted and rejected LearningChange decisions use distinct typed success categories. Before terminalization, TaskRuntime validates the durable request Event, same-Team create-only LearningChange, committing approval Task, actor, decision Event and exact payload/timestamp, original decision attempt, current attempt, and (on acceptance) the full canonical KnowledgeItem state. It then uses the existing atomic Task execution Outcome/Snapshot/terminal Event path. Rejection is successful: Task ends `done`, LearningChange remains `rejected`.
8. **Synchronous adapter orchestration (implemented):** when configured with the existing SnapshotStore, `OperatorApplicationAdapter.decide_learning_change` runs request replay/creation → ordinary `TaskRuntime.admit` → `LearningCommitService.decide` → `TaskRuntime.finalize`. It returns only after Task finalization and supports replay of an already completed decision without a second Task or Outcome.
9. **Crash/recovery and attempt fencing (implemented):** a crash before canonical decision commit follows ordinary 60-second retry and reuses the same approval Task on the next attempt. A crash after the decision Event/LearningChange commit is recovered by deriving the canonical accepted/rejected observation and finalizing through TaskRuntime before retry/exhaustion. Stale attempt results and mismatched decision categories fail closed. Generic recovery behavior remains unchanged for all other Task types.
10. **Competing approval Tasks (review follow-up, hosted CI passed):** distinct idempotency keys may create distinct requests for the same proposed LearningChange. Only one Task can win the locked canonical decision. A losing running Task is recorded as terminal failure through TaskRuntime, with a deterministic observation based on its current-attempt start; the same failure is reconstructed after interruption and replayed as a typed request conflict. The winning LearningChange/KnowledgeItem commit is unchanged.

**Reachability / D10 resolution (2026-11-02):** Checkpoint 2 emits only `operation="create"` proposals, and Checkpoint 3's real production path consumes those proposals. By explicit operator decision, Checkpoint 3 is create-only: revise/retire LearningChange production and commitment are deferred beyond this checkpoint until a separately authorized knowledge-lifecycle scope provides a genuine proposal source and defines target-version pinning, history, concurrency, replay/recovery, and projection invalidation. The schema's operation vocabulary does not itself authorize those paths. Do not use `seed_knowledge`, direct database mutation, test-only proposal injection, ad-hoc endpoints, or any bypass. Future revise/retire operations must use the same Operator approval and canonical learning-commit authority.

**Review-date guard (D7 resolved 2026-11-02):** apply the normative rules in ADR-0029 before enabling Team Experience retrieval. D7 is a design resolution, not itself Checkpoint 4 authorization. C4 was separately authorized and is implemented on stacked PR #32; its policy-version pinning, UTC date assignment, deterministic review Task, and null/due-aware retrieval behavior are documented on that branch.

#### Checkpoint 3 acceptance

Checkpoint 3's acceptance contract is limited to real create proposals from Checkpoint 2. D10 is resolved; no revise/retire reachability is required. The follow-up code passed hosted CI; formal closeout requires the final operator-local disposable-PostgreSQL run on PR #31 head `b9f1baf`, then review and merge. C4 is authorized separately and is not part of C3.


- Explicit Operator approval and rejection of create LearningChanges are durable, attributable, and auditable.
- Acceptance creates exactly one active KnowledgeItem version 1 with complete committed state and LearningChange history; rejection creates no KnowledgeItem and preserves its reason.
- The host principal, Team/action grant, Task scope, policy pin, evidence basis/hash, target status/version, and current attempt are revalidated; stale, missing, cross-Team, changed-hash, unauthorized, or concurrent decisions fail closed.
- Canonical decision, LearningChange state/history, KnowledgeItem mutation (on acceptance), and decision Event commit atomically.
- Replay cannot create a duplicate KnowledgeItem, version, decision Event, or terminal Task Outcome.
- Crash before decision commit follows normal same-Task retry; crash after decision commit is recovered through TaskRuntime finalization without replaying the business mutation.
- No path changes TeamPolicy; no unreviewed proposal becomes canonical knowledge.
- Revision/retirement proposal production and commitment are explicitly out of scope; no seed/bypass path is used.

### Checkpoint 4 — Team Experience projection and later-task retrieval

**Purpose:** make only current accepted canonical Team Experience discoverable through the existing RAG/Context path, subject to the resolved D7 review contract.

**D7 implementation prerequisites (design is resolved; none of these are claimed implemented by this documentation change):**

1. Extend the versioned TeamPolicy rules schema with optional `review.knowledge_item_interval_days` through a forward schema revision. The current conceptual architecture describes `schema_version`, but the current `TeamPolicy` ORM does not expose that field; preflight the actual model/migration/validation path and reconcile this discrepancy before implementing schema versioning. Do not silently mutate the fixed v1 vocabulary.
2. Update canonical LearningChange acceptance so it reads the TeamPolicy row pinned by the approval Task's `policy_version`, computes and persists UTC `review_after` from `committed_at`, and includes the value in canonical committed-state/replay validation. Missing key means NULL; invalid present values fail closed. New policy versions do not rewrite old dates. No retroactive backfill of existing NULL items is authorized.
3. Establish the deterministic `review_knowledge` Task execution path. The scheduler/host may enqueue ordinary Tasks only; the deterministic service locks/rechecks current same-Team rows and atomically commits `active → needs_review` plus Task-attributed Event. `TaskRuntime` remains the sole lifecycle authority. Do not expand the ingestion-only `TaskDispatcher`, introduce a general scheduler, or add a second runtime. If the existing host execution boundary cannot invoke this Task safely, pause and request a separately scoped implementation decision rather than building a parallel execution system.
4. Index and retrieve only current canonical `active` items with non-null `review_after` strictly later than the UTC retrieval time. NULL and due records are excluded even if their stored status is still `active`.

#### Detailed work

1. Add a Team Experience indexer and projection representation. Preferred initial design: a separate `team_experience_chunks` table with canonical KnowledgeItem ID, Team, version, content hash, chunk identity/text, embedding model/revision, and index timestamps. Preserve the existing non-null `knowledge_chunks.signal_id` relationship and Signal-only meaning.
2. Reuse PostgreSQL + pgvector and full-text infrastructure, the BGE-M3 embedding interface, chunking approach, and provider readiness/failure handling. Do not add a separate vector database or put vectors on canonical KnowledgeItem records.
3. Index only the current canonical KnowledgeItem version when status is `active`, `review_after` is non-null, and `review_after > now_utc`. Proposed, rejected, superseded, stale, retired, `needs_review`, NULL-dated, and due versions must not be returned. The exact due boundary is `now_utc >= review_after`.
4. At indexing and retrieval, revalidate canonical Team ownership, version, status, content hash, non-null review date, and UTC review eligibility against the current time. Do not rely on a prior index/scan or on `active` status alone. Similarity score is not authority.
5. Extend `HybridKnowledgeRetriever` and `TaskContextAssembler` so Domain Knowledge and Team Experience remain separate logical cores in results/manifests. Preserve source/KnowledgeItem IDs, version, canonical hash, index revision, retrieval configuration, and exact provenance.
6. Apply ADR-0028's global limits across both cores together: at most eight final passages and 8,000 Unicode characters. Do not give each core a separate full budget.
7. Keep canonical commit independent from projection publication. If indexing fails, retain the accepted KnowledgeItem/LearningChange, record projection staleness, exclude the unverified new version from retrieval, and permit idempotent retry/rebuild.
8. Prove later-Task reuse from canonical state and the index alone. Do not pass information through an earlier transcript or hidden fixture shortcut.

#### Checkpoint 4 acceptance

- Only the current accepted `active` KnowledgeItem with a non-null `review_after` strictly later than retrieval time is eligible.
- Cross-Team access, stale/superseded versions, NULL-dated items, review-due/expired content, rejected proposals, and unaccepted KnowledgeItems are excluded, even when a due item's stored status has not yet changed to `needs_review`.
- Tests prove pinned-policy date assignment, policy-schema validation, absence of defaults, UTC calculation and exact-boundary behavior, no retroactive rewrite/backfill, and fail-closed rejection of invalid configured values.
- Tests prove that only `review_knowledge` Task execution changes due items to `needs_review`, with atomic Task-attributed Event, idempotent retry/concurrency, no scheduler-side mutation, and no automatic reactivation.
- Indexing/rebuild is idempotent; failed publication does not roll back canonical acceptance or falsely mark the version current.
- Context manifests distinguish Domain Knowledge and Team Experience and preserve exact source/version/hash provenance.
- Combined retrieval respects eight passages and 8,000 Unicode characters.
- A later Task retrieves accepted Team Experience after the original Task/session is gone.

### Checkpoint 4 — Team Experience projection and later-Task retrieval

**Status (2026-11-03): IMPLEMENTED ON PR #32; RECONCILED WITH MERGED C3 MAIN; FRESH HOSTED CI PASSED; COMBINED LOCAL VERIFICATION PENDING.** Checkpoint 4 was separately authorized on 2026-11-02. The original C4 implementation head `3682f7e` passed hosted CI run `41589798190` with 588 tests. C4 was then reconciled with C3 merge commit `99f8b6b` using merge commit `923268b0efda16d2c87e1b53aba2acb1990680ad` and retargeted to `main`. Fresh hosted CI run [41598895890](https://github.com/abtn/Watch-Architecture-Rev2/actions/runs/41598895890) passed on that exact combined head: fresh PostgreSQL migration to one `0013_team_experience_projection` head, Ruff, mypy (27 files), and **590 tests**. Final operator-local disposable-PostgreSQL verification on this combined C3+C4 tree remains required before formally closing C4.

**Purpose:** make only current, accepted, eligible canonical Team Experience discoverable through the existing knowledge retrieval and Task Context path, without changing the existing Signal-only Domain Knowledge projection.

#### Implemented work

1. **Policy versioning and canonical review dates:** migration `0013_team_experience_projection` adds TeamPolicy `schema_version` support (existing policies remain v1; `review.knowledge_item_interval_days` requires v2). The optional interval must be a positive non-boolean integer and has no default. Acceptance reads the approval Task's pinned policy version and calculates UTC `review_after` from canonical `committed_at`; missing configuration leaves NULL. No retroactive NULL backfill or TeamPolicy write through `approve_learning_change`.
2. **Separate Team Experience projection:** `TeamExperienceChunk` / `team_experience_chunks` uses same-Team composite references to canonical KnowledgeItem and originating LearningChange. The existing `knowledge_chunks.signal_id` and Domain Knowledge projection remain unchanged.
3. **Durable publication state and rebuild:** `TeamExperienceIndexState` / `team_experience_index_state` tracks `stale`, `published`, and `ineligible`, canonical item/version/hash/origin, embedding-space key, chunk/attempt counts, error class, and timestamps. Index attempts mark state stale before provider work; chunks and matching published state commit atomically. Failed indexing cannot roll back canonical acceptance and stale chunks remain undiscoverable. `rebuild_all()` is idempotent and retries stale rows.
4. **Canonical indexing eligibility:** index only a current, accepted create LearningChange whose KnowledgeItem is active, has a non-null future UTC review date, and matches the exact approval Task, decision Event, terminal Outcome, and committed-state record. Lock and recheck canonical state after embedding and before publication.
5. **Dual-core retrieval:** reuse the existing provider-neutral embedding identity/BGE-M3 interface, chunker, PostgreSQL full-text search, pgvector, and reciprocal-rank fusion. Search Domain Knowledge and Team Experience using the same query embedding, fuse candidates, then apply one combined maximum of eight passages and 8,000 Unicode characters.
6. **Context v2 and provenance:** Context and manifest preserve logical core, canonical Signal or KnowledgeItem ID, KnowledgeItem version/content hash, LearningChange provenance, chunk ID/index/hash, and embedding-space identity. Existing same-Task Context v1 snapshots replay immutably; later Tasks perform new retrieval.
7. **Deterministic review Task:** `TaskRuntime.complete_knowledge_review(task_id)` composes existing admission and terminal finalization for an already-created ordinary `review_knowledge` Task. The due KnowledgeItem transition `active → needs_review`, Task-attributed Event, terminal Outcome/Snapshot, and Task completion are atomic and replayable. The host only enqueues; no second runtime, scheduler, or TaskDispatcher expansion is added.
8. **Later-Task proof:** an independent Strategy Task retrieves eligible Team Experience through ordinary retrieval and immutable Context, with canonical item/version/LearningChange provenance.

#### Checkpoint 4 acceptance

- Only the current accepted active KnowledgeItem with a non-null future `review_after` is discoverable; NULL/due items are excluded at indexing, retrieval, and Context assembly.
- Cross-Team, rejected, unaccepted, changed/tampered canonical state, superseded version, and stale/unpublished projection rows fail closed.
- Schema-v1/v2 policy behavior, strict interval validation, pinned-policy date assignment, UTC arithmetic, exact due boundary, and no retroactive backfill are tested.
- Only the ordinary `review_knowledge` Task path changes due items to `needs_review`; the operation is atomic, idempotent, attempt-fenced, and does not reactivate items.
- Failed indexing records stale state and never makes old chunks discoverable; successful publication commits chunks and published state together; rebuild is safe.
- Both cores share the combined eight-passage/8,000-character bound; Context v2 records per-core provenance and v1 replay remains immutable.
- A later Task retrieves canonical Team Experience after the originating Task/session is gone.

**Verification gate:** run `41598895890` is the current hosted verification on the reconciled PR #32 head `923268b`; it passed fresh migration/head validation, Ruff, mypy, and 590 tests. Operator-local disposable-PostgreSQL verification on the same head is required before C4 merge. `docs/testing.md` contains the full command/environment contract. R6-G remains separately gated.

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
| D7 | Review/expiry semantics | ADR-0029 makes `review_after` part of retrieval eligibility. | **Resolved and implemented in C4:** optional positive non-boolean TeamPolicy schema-v2 rule `review.knowledge_item_interval_days`, no default, pinned to approval Task policy version; UTC `review_after`; NULL/due items excluded; deterministic ordinary `review_knowledge` Task owns atomic `active → needs_review`. No retroactive NULL backfill or TeamPolicy write through C3. |
| D8 | Operator authorization boundary | No separate deployed Watch API/CLI or authentication subsystem exists; the host application is the authentication root. | **Resolved direction:** Checkpoint 3 includes a thin in-repository adapter invoked in-process by the host after authentication and Team/action authorization. Pass typed issuer/subject context; reject raw request/model identity. The adapter is not a deployed API/CLI or authentication credential. |
| D9 | Evaluation generation approach | Evaluations are fallible and evaluators may be biased. | Choose the first-slice evaluator source (rule, trusted human input, or separately approved model proposal). Evaluator cannot self-record or self-approve. Do not add self-modifying evaluation procedures. |
| D10 | Reachability of revise/retire LearningChanges | Checkpoint 2 emits only `operation="create"` proposals, while the earlier broad Checkpoint 3 acceptance language also named revise/retire. | **Resolved 2026-11-02 by explicit operator decision:** Checkpoint 3 is complete in scope for genuine Checkpoint 2 create proposals only. Revise/retire proposal production and commitment are deferred beyond Checkpoint 3 until a separately authorized knowledge-lifecycle scope supplies a genuine proposal source and defines target-version pinning, history, concurrency, replay/recovery, and projection invalidation. Schema vocabulary does not authorize those paths; no seed, direct DB write, test-only injection, ad-hoc endpoint, or bypass. This narrows Checkpoint 3 delivery scope and does not amend ADR-0029's broader lifecycle principles.
| D11 | Manual Task deadline and recovery semantics | Human approval happens before Task creation; only synchronous application work runs in `running`. Admission requires positive `deadline_seconds`; generic recovery uses a 60-second stale threshold. | **Implementation contract:** allow the documented no-deadline budget for `approve_learning_change` only; preserve generic 60-second stale recovery. Prove crash/recovery same-request/same-Task replay; no human waits in a Task. |
| D12 | Durable approval target and request idempotency | Task has no `input_refs`, target column, or generic request-key column; Event indexing is not unique. | **Implemented:** host idempotency UUID + fixed UUIDv5 namespace maps Team + `approve_learning_change` + request UUID to one Task primary key. Distinct keys may create separate Tasks; one locked LearningChange decision wins and the losing Task is durably failed through TaskRuntime, including on recovery. No migration was needed. |

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
