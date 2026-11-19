# RW-3 — Bounded model `update_thread` design and acceptance plan

**Status:** Planning proposal only. RW-2 is accepted; RW-3 implementation is not authorized. This document defines the proposed boundary and the design work required before a separate implementation authorization.

**Depends on:** accepted RW-1 persistence and RW-2 deterministic Operator commit path.

**Authority:** `PLAN.md` is the sole current-status authority. The [RW implementation plan and proof matrix](rw-implementation-plan.md) carries the milestone sequence and cross-slice proofs. The [Task specification](../tasks.md) carries the operative Task contract.

## 1. Purpose

Add a bounded model worker for `update_thread`. The model may propose changes to one existing Thread. It is not an authority, a commit service, a Task runtime, or a source of trusted identity.

The boundary remains:

1. TaskRuntime admits and owns the Task attempt.
2. Application code resolves trusted Task, Team, Thread, policy, and bounded Context.
3. The existing generation boundary returns untrusted model output.
4. A strict parser converts only a valid response into typed proposals.
5. The shared RW-2 proposal-validation and atomic transaction core validates and commits the accepted proposal set through a narrow trusted actor seam; the existing Operator service and identity checks remain intact.
6. TaskRuntime owns terminalization, recovery, and Outcome side effects.

Do not add a second runtime, scheduler, provider abstraction, authentication system, model-to-database path, or generic dispatch framework.

## 2. Authority and write boundary

The immutable Task request and trusted database state determine the Team and target Thread. Model output cannot select or override either identity, the Task, policy, allowed writes, principal, budget, or Event attribution.

The proposed business `allowed_writes` are exactly:

- `EvidenceLink`
- `Hypothesis`
- `ConfidenceChange`

Event and Outcome effects remain Kernel/TaskRuntime side effects, not model-worker business writes.

RW-3 reuses the RW-2 proposal types and commit-time validation. It does not create a parallel validation path. All applicable RW-2 constraints remain binding, including same-Team/same-Thread ownership, immutable Snapshot and quote/hash/offset validation, evidence stance, confidence-cause pairing, low initial Hypothesis confidence, legal transitions, same-Thread supersession, idempotency, replay, concurrency, and atomic accepted-set commit.

**Explicit exclusions:**

- SignalDisposition creation or refinement; triage remains RW-4.
- Thread creation, reactivation, or summary/projection writes.
- TeamPolicy or KnowledgeItem mutation.
- Artifact or Consultation creation.
- Outcome writes by the worker.
- Any mutation to another Thread.
- Automatic semantic repair or model re-proposal loops.

## 3. Task Context

The worker receives one bounded, immutable Task Context assembled by application code. The target Thread is resolved from the trusted Task request, not generated text.

### Proposed inclusion

- The target Thread's canonical state.
- Active Hypotheses belonging to that Thread.
- Relevant accepted EvidenceLinks for those Hypotheses/Thread.
- The exact immutable source Snapshots needed to verify the evidence presented.
- The current applicable Team policy.
- Team Experience is excluded from RW-3; no new retrieval integration is added.

### Exclusions

- SignalDisposition, deferred/unprocessed triage state, or any other RW-4 triage input.
- Other Threads or cross-Team records.
- Rejected, stale, unauthorized, or integrity-invalid sources.
- Unverified source text or mutable content in place of immutable Snapshots.
- Thread summary projections as a write target.

### Required Context guarantees

- Enforce Team and Thread scope before any model exposure.
- Revalidate canonical ownership, status, source identity, and Snapshot/hash integrity.
- Fail closed on stale, unauthorized, missing, or corrupt required references.
- Deterministic selection for the same database state, policy, and configuration.
- Explicit token/character and item-count bounds.
- Preserve the exact Context Snapshot/manifest using the repository's established Context provenance pattern.
- Do not silently truncate evidence or alter its meaning to fit the budget.

RW3-0 decisions are recorded in §8. Thread-local world-memory records use stable canonical ordering; if the complete bounded set does not fit, Context assembly fails closed rather than silently dropping or truncating records. Team Experience is excluded from RW-3: the current `TaskContextAssembler` is scoped to `propose_strategy`, so no existing end-to-end authorized Context path is available to `update_thread` without adding a new integration. RW-3 does not invoke Team Experience retrieval. The following provider limits are fixed for RW-3 and are not open for expansion:

- Retrieval-derived passages: at most 8 passages and 8,000 Unicode characters.
- Model: the ADR-0031-selected Cloudflare Workers AI Llama 3.1 8B Instruct FP8 model only.
- Total quoted input plus configured output: at most the model's 32,000-token context window, using the existing conservative UTF-8-byte-length-plus-128 framing-token quote.
- Output: at most the existing configured output-token ceiling of 1,024; a lower configured value is valid, a higher value is not.
- One synchronous, non-streaming provider request per invocation; no tools and no adapter-level retry. TaskRuntime owns retry behavior and preserves ADR-0031's existing three-start Task limit.

RW3-0 fixes the model-worker proposal count at 8 per invocation; the existing 1,024-token output ceiling remains the stricter effective bound for many payloads. The Operator request contract remains unchanged at its existing maximum of 64 proposals. Do not add a separate serialized-output byte limit without a measured need.

## 4. Generation, parsing, and commit sequence

### Existing provider limits carried into RW-3

RW-3 retains the provider and request limits already accepted by ADR-0031 and implemented in `core/generation.py`:

- Provider/model remain `cloudflare_workers_ai` and `@cf/meta/llama-3.1-8b-instruct-fp8`. A different provider or model requires a separate decision; the 32,000-token advertised context window does not authorize expanding Watch's own Context budget.
- Any retrieval-derived passage set remains limited to **8 passages and 8,000 Unicode characters**. Apply these limits unchanged; do not enlarge them because the model advertises a 32,000-token context window.
- The provider's conservative input quote remains UTF-8 byte lengths of the exact system and user prompts plus 128 framing tokens. Quoted input plus output must fit within 32,000 tokens.
- The configured output-token limit may be lower, but cannot exceed the existing **1,024-token** ceiling (`DEFAULT_MAX_OUTPUT_TOKENS`). Do not raise this ceiling for RW-3. The Task's existing cost budget and cost reservation remain independently binding.
- The adapter remains synchronous, non-streaming, one HTTP request per invocation, with no tools and no internal retries. It requires valid prompt/completion usage and an exact response-model match; retry eligibility remains TaskRuntime-owned.
- The output is one final JSON object validated locally. Do not rely on provider JSON Mode or expose/persist reasoning traces.

These are inherited constraints, not new RW-3 provider authorization. The deterministic Context and proposal-count decisions are recorded in §8. Do not invent a second character limit for serialized output: the configured token cap is the existing hard output bound unless a separate measured need justifies a tighter application-level bound.

**Generation-cost integration:** the current `TaskGenerationCostService` does not authorize `update_thread`. RW-3 therefore requires a narrow extension to that existing service, not a new accounting subsystem: add one distinct operation identifier for `update_thread`, bind it to Task type `update_thread` and the exact ordered `allowed_writes` scope `[EvidenceLink, Hypothesis, ConfidenceChange]`, and add operation-specific quote/provider/model/rate-card/output-bound validation and tests. Preserve Task/attempt attribution, one reservation per operation per attempt, cumulative Task budget enforcement, and known/unknown/overrun reconciliation. The implementation must use only a provider/model/rate card already authorized by ADR-0031 or stop for a separate decision; do not silently broaden provider authorization. Reconciliation and current-attempt charge validation occur before the shared RW-2 commit core is called.

1. Validate the immutable Task request and its trusted Team/Thread target using read-only checks. Do not assemble attempt-specific Context before admission.
2. Admit/claim the Task attempt through TaskRuntime. This establishes the attempt that owns all subsequent Context, generation, and cost records.
3. Assemble and validate the bounded Context for that admitted attempt. If this fails, record failure through TaskRuntime; do not reserve cost or call the provider.
4. Reserve the maximum permitted generation cost for the exact Task attempt through the existing cost-accounting service.
5. Call the configured existing generation provider only after reservation succeeds.
6. Reconcile provider usage/cost from the raw provider response and validate the exact current-attempt charge. Do this even if the response body will later fail parsing. Missing/unknown/unreconciled/overrun usage cannot authorize business writes; preserve the applicable reservation/unknown-cost accounting and fail through TaskRuntime.
7. Parse the response against a strict typed schema. Reject malformed JSON, unknown fields, unsupported proposal types, malformed identifiers, excessive output, and more than 8 proposals; do not coerce or repair them. Canonical reference ownership, freshness, and domain validity remain commit-core checks and produce per-proposal rejection Events where applicable.
8. Submit non-empty typed proposals to the shared RW-2 validation and transaction core through a narrow actor-neutral seam. The current `WorldMemoryCommitService` is Operator-specific: it validates an Operator principal and records `operator_id`; it cannot be called unchanged by a model worker. Preserve the Operator adapter and its event contract, and add only the minimum trusted `model_worker` actor attribution needed by `update_thread`. This remains the sole business-write boundary; do not create a parallel commit service.
9. Finalize or recover through TaskRuntime. A failure after reconciliation but before commit leaves no accepted business writes; the incurred charge remains recorded.

There are no hidden provider retries and no automatic semantic repair/re-proposal loop. Transport retries, if any, are only those already permitted by bounded TaskRuntime policy. A later attempt is a separate Task attempt and remains subject to ordinary admission and budget accounting.

## 5. Proposal-set semantics

Preserve the accepted RW-D18/RW-2 contract:

- Each invalid proposal receives an attributable rejection Event with a stable reason.
- Valid proposals are committed atomically as one accepted set.
- A failure while committing that accepted set leaves none of that set committed.
- Invalid proposals do not partially mutate business state.
- The Task fails only when every proposal is rejected.
- A mixed result may commit the valid set while retaining rejection Events for invalid proposals.

An explicit response with an empty `proposals` list is a valid no-op. After successful cost reconciliation, do not call the commit service or write business state; finalize the Task through TaskRuntime as `success_no_change` with its normal Task-attributed terminal records. Do not retry a valid no-op. The model response envelope therefore permits zero proposals, while each non-empty proposal still uses the existing strict proposal types. TaskRuntime must add only the narrow `update_thread` result validation needed to accept this no-op and the model commit result.

## 6. Failure behavior

| Condition | Required behavior |
|---|---|
| Invalid Task, target, or policy | Reject before provider execution; no business writes. |
| Invalid/stale/cross-scope Context | Fail closed; no provider call and no business writes. |
| Cost reservation denied | No provider call. |
| Provider timeout/transport failure | Existing bounded TaskRuntime failure/retry behavior; no business commit. |
| Malformed or oversized output | Reconcile provider usage first; then record a non-retryable TaskRuntime failure. No per-proposal rejection Events and no business commit. |
| Invalid individual proposal | Rejection Event; exclude it from the accepted set. |
| All proposals invalid | Task fails; no business writes. |
| Mixed valid/invalid proposals | Commit valid set atomically; preserve invalid-proposal rejection Events. |
| Accepted-set transaction failure | Roll back the entire accepted set; TaskRuntime handles failure/recovery. |
| Unknown provider usage/cost | Use existing unknown-cost accounting; never assume zero. |
| Replay or concurrent attempt | Existing TaskRuntime and commit-service idempotency/concurrency rules; no duplicate writes. |

Parser-level failures (invalid JSON, unknown fields, unsupported shapes/types, forged authority fields, or proposal count above 8) are non-retryable Task failures recorded through TaskRuntime; they do not produce per-proposal rejection Events because no trusted typed proposal set exists. Structurally valid proposals that fail domain validation receive the existing attributable `proposal_rejected` Events from the shared commit core. Mixed batches commit the valid subset atomically; all-invalid batches retain the existing Task-failure behavior. Do not create a second rejection protocol.

## 7. Acceptance criteria

### Context and isolation

- [ ] Target Team and Thread are derived only from trusted Task/database state.
- [ ] No cross-Team or cross-Thread record reaches the model.
- [ ] Only active Hypotheses and accepted, relevant EvidenceLinks are included.
- [ ] Every exposed source is tied to the exact immutable, hash-verified Snapshot.
- [ ] Stale, missing, unauthorized, or corrupt required references fail closed before provider invocation.
- [ ] Context selection is deterministic and explicitly bounded.
- [ ] Context Snapshot/manifest records exact provenance and selected references.
- [ ] SignalDisposition and triage data are absent.
- [ ] Team Experience is excluded from RW-3; no Team Experience retrieval or projection changes are introduced.

### Model and provider boundary

- [ ] Existing generation provider and cost-accounting services are reused.
- [ ] TaskRuntime admission establishes the attempt before attempt-specific Context assembly.
- [ ] The existing cost service has a distinct `update_thread` operation mapped to Task type `update_thread` and exactly `[EvidenceLink, Hypothesis, ConfidenceChange]`; provider/model/rate-card and output bounds are validated by that operation.
- [ ] Reservation succeeds before provider invocation.
- [ ] The exact current-attempt charge is reconciled and validated before the shared RW-2 commit core can write business state; unknown, unreconciled, and overrun charges cannot authorize writes.
- [ ] Output uses a strict typed schema; unknown fields/types and invalid references are rejected.
- [ ] Retrieval-derived Context remains within 8 passages and 8,000 Unicode characters; quoted input plus configured output fits the 32,000-token model context; output is capped at the existing configured maximum of 1,024 tokens.
- [ ] The model response contains at most 8 proposals; the existing 1,024-token output cap is also enforced. The Operator request's existing 64-proposal limit is unchanged; no separate serialized-output byte limit is introduced without measured justification.
- [ ] Model output cannot alter Task/Team/Thread identity, policy, budget, allowed writes, or attribution.
- [ ] No automatic semantic repair/re-proposal loop or unapproved provider retry exists.
- [ ] Usage and cost reconcile under existing known/unknown-cost rules.

### Commit and lifecycle

- [ ] The shared RW-2 proposal-validation and atomic transaction core is reused through a narrow trusted actor seam; the Operator adapter, principal checks, and existing Event behavior remain unchanged.
- [ ] Business `allowed_writes` are exactly EvidenceLink, Hypothesis, and ConfidenceChange.
- [ ] Every RW-2 evidence, confidence, transition, ownership, replay, and concurrency proof remains passing for the model entry path.
- [ ] Valid proposals commit as one atomic accepted set; invalid proposals produce attributable rejection Events. An empty response finalizes as `success_no_change` after charge reconciliation and creates no business writes.
- [ ] All-invalid output fails the Task; mixed valid/invalid output commits only the valid set.
- [ ] Provider, parser, Context, reservation, and commit failures cannot leave unauthorized or partial business writes.
- [ ] TaskRuntime remains the sole admission, attempt, finalization, and recovery authority.

### Verification and operations

- [ ] Deterministic fake-provider tests prove the complete positive and negative paths, including admission-before-Context, reservation-before-provider, reconciliation-before-commit, unknown/overrun blocking, and TaskRuntime recovery.
- [ ] PostgreSQL tests prove atomicity, ownership, replay, and concurrency where required.
- [ ] A live provider smoke test, if requested later, is separate and does not replace deterministic proofs or become a CI dependency.
- [ ] Ruff, Mypy, focused tests, full suite, disposable PostgreSQL migration/single-head checks, and patch-whitespace checks pass on the exact tested commit.
- [ ] No persistent database is used for verification.
- [ ] Documentation, Task contract, implementation, and proof matrix agree.

## 8. RW3-0 decisions — resolved proposal; review still required

These decisions close the six planning locks for the proposed RW-3 scope. They do not authorize implementation.

1. **Deterministic Context selection:** include the target Thread, all active same-Thread Hypotheses, and all relevant accepted EvidenceLinks with their exact immutable source Snapshot references. Order Hypotheses by `(created_at ASC, id ASC)` and EvidenceLinks by `(hypothesis_id ASC, created_at ASC, id ASC)`; order unique Snapshot references lexically. Do not rank or silently truncate canonical world-memory records. Bound the Context to at most 8 active Hypotheses, 8 EvidenceLinks, 8 unique source Snapshots, and 8,000 Unicode characters of evidence text. If any item-count or character bound is exceeded, fail Context assembly through TaskRuntime before provider invocation. Preserve the existing 8-passage/8,000-character retrieval ceiling and 32,000-token provider context limit; RW-3 does not expand them.
2. **Team Experience:** exclude it from RW-3. Although `KnowledgeIndex` has Team Experience retrieval and canonical validation, the current Task Context assembler is explicitly scoped to `propose_strategy`; adding a new update_thread retrieval integration is not necessary for this slice. No Team Experience retrieval call or projection change is authorized.
3. **Worker invocation:** use one narrow host-invoked application adapter for an already-created `update_thread` Task. It validates the immutable request/target, admits through the existing TaskRuntime, then assembles Context and executes the generation/cost/commit sequence. Do not extend `TaskDispatcher`, add a scheduler, or create a second runtime.
4. **Proposal count:** allow at most 8 model proposals per invocation. The existing 1,024-token output ceiling remains independently enforced and may permit fewer. This 8-proposal cap is conservative, not performance-derived; raise it only if a real Task requires it and output, cost, and atomicity proofs are expanded. Keep the existing Operator `OperatorUpdateRequest` maximum of 64 unchanged; the 8-proposal cap belongs only to the model response parser. Preserve RW-D18/RW-2 mixed-batch and atomic accepted-set semantics.
5. **Empty/no-op:** an explicit empty `proposals` list is a valid no-op. Reconcile the incurred generation charge, skip the commit service and all business writes, then finalize through TaskRuntime with `success_no_change`. Do not retry a valid no-op. The model response envelope permits zero proposals; the shared Operator request model remains non-empty.
6. **Failure/rejection recording:** malformed JSON/schema, unknown fields, unsupported shapes, forged authority fields, excessive proposal count, and output-bound violations are non-retryable TaskRuntime failures with no proposal rejection Events. Structurally valid proposals that fail domain validation receive the existing per-proposal rejection Events. Mixed batches commit valid proposals atomically; all-invalid batches fail the Task through the existing TaskRuntime terminal path.

**Required narrow integration correction discovered during source audit:** the current `WorldMemoryCommitService` is Operator-specific: it requires an Operator principal and writes `operator_id` attribution. RW-3 cannot call it unchanged. RW-3 must extract/reuse the same proposal validation and atomic transaction core behind a narrow trusted actor seam (`operator` for RW-2, `model_worker` for RW-3), preserving RW-2's existing Operator identity and Event behavior. Model actor identity is application-defined and Task-attributed; model output cannot supply it. TaskRuntime also needs only task-type-specific admission, result validation, finalization, and recovery support for `update_thread`; it remains the sole lifecycle authority. This is not permission to add a second commit service, runtime, or generic actor framework.

RW3-0 remains source/design reconciliation only. Any schema migration, provider/model expansion, or change to accepted RW-D18/RW-2 batch semantics requires a separate decision. The design must receive independent review before a separate implementation-authorization decision. No implementation or schema migration is implied.

## 9. Implementation sequence

| Slice | Work | Exit gate |
|---|---|---|
| RW3-0 — design lock | Audit current Task, Context, provider, cost, TaskRuntime, and RW-2 commit contracts; resolve the remaining design locks above; reconcile docs. | Design is internally consistent, all design locks are resolved, and the design is reviewed and ready to present for a separate implementation-authorization decision. RW3-0 completion does not authorize implementation. |
| RW3-1 — bounded Context | Implement deterministic Thread-scoped Context assembly, source/Snapshot validation, bounds, and provenance manifest. | Positive/negative Context tests prove scope, freshness, integrity, determinism, and bounds. |
| RW3-2 — model worker | Implement strict output parsing and narrow worker orchestration using the existing provider and cost boundary. | Fake-provider tests prove provider ordering, schema rejection, bounds, and no authority escalation. |
| RW3-3 — shared commit/lifecycle | Connect proposals to the RW-2 commit service and TaskRuntime; prove mixed/all-invalid batches, atomicity, replay, concurrency, failure, and recovery. | Complete RW-3 proof matrix passes; no alternate runtime or write path. |
| RW3-4 — verification/closeout | Run exact-head local and hosted verification, review diff/docs, record results and explicit acceptance. | Exact tested SHA, all required checks, cleanup evidence, and Operator acceptance recorded. |

Each slice requires its own review/authorization as appropriate. Passing a prior slice does not automatically authorize the next. RW-3 completion does not authorize RW-4, RW-5, R7-C, persistent-database operations, or scored newsroom runs.


## 10. Independent design review corrections

This section resolves the implementation ambiguities identified by the independent review. It is normative for RW-3 and supersedes any less-specific wording in §§3–8.

1. **EvidenceLink membership:** include every accepted EvidenceLink belonging to an active Hypothesis on the target Thread. Do not apply relevance ranking, score-based selection, or discretionary filtering. Validate same-Team/same-Thread ownership and source integrity. Include the exact immutable source Snapshot for every included link. If the complete set exceeds any existing count or character bound, fail Context assembly through TaskRuntime; do not select a smaller subset.
2. **Policy pinning:** use only the policy version pinned by the immutable Task request (Task.policy_version). Verify that the pinned policy exists and is valid for the Task's Team. Never substitute the latest policy during execution. A missing, cross-Team, or inconsistent pin fails closed before provider invocation.
3. **Provider usage boundary:** the provider boundary must expose validated response-model identity, raw completion text, and validated usage metadata before JSON parsing. Reconcile usage and validate the exact current-attempt charge before parsing completion text. Then parse the text into typed proposals. If completion JSON is malformed but usage is valid, persist the reconciled charge and record a non-retryable parser failure through TaskRuntime, with no business writes. If usage is absent or invalid, use the existing unknown-cost accounting; do not assume zero. This requires a narrow change to the existing provider result contract because the current adapter parses JSON before returning usage. Do not create a second provider abstraction.
4. **Trusted actor attribution:** the shared commit core accepts a narrow typed actor distinction: the existing canonical Operator principal for operator_update, or a fixed application-defined model_worker actor for RW-3. The model-worker actor is derived only from application code and the admitted Task; model output cannot provide or override actor, principal, or attribution fields. Model-worker Events must identify the Task and actor type, and must not fabricate an Operator identity. Preserve existing RW-2 Operator principal validation and Event payloads unchanged in behavior. Do not introduce a generic actor framework.
5. **TaskRuntime success contract:** success_no_change means an explicit empty proposals list after valid usage reconciliation and no commit call. success_world_memory_updated means the shared commit core completed and at least one proposal was accepted (including a mixed batch with rejection Events). Both are RW-3-specific successful terminal categories, with normal Task-attributed terminal Event and Outcome creation, status transition, replay, and recovery. An all-invalid batch remains a Task failure with the existing rejection Events. Do not permit arbitrary success categories or change other Task types' result validation.

The provider adapter and TaskRuntime changes above are design requirements only; this document does not authorize implementation. Their acceptance proofs are listed in the RW implementation plan.
