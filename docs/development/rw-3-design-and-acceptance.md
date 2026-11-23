# RW-3 — Bounded model `update_thread` design and acceptance plan

**Status:** RW-3 implementation was explicitly authorized on 2026-11-19. RW3.1, RW3.2, and RW3.3 were accepted and merged by PRs #136–#138. RW3.4 implementation and deadline/cost stack were merged by PR #152; recovery-finalization correction and supplemental proof integration were merged by PR #163 at `6cbef27cd4fb39b1d1c860de8bf419046f35d5ae`. Documentation reconciliation PR #164 merged at `1165897898cad9ab4f208c5e430ccbb88f1c558a`; test-only PR #165 merged at `864ff905f4fd70f36eea9d0505dfa1d9b61e35fc`. PR #165's rebased head `0837989d97fb66c7118d2269dfcb0f0428aacce8` passed hosted CI with 1,286 tests, and Programmer-local Windows verification passed on its identical source tree. The candidate evidence ledger is 27 PASS / 8 PARTIAL / 0 OPEN. Formal RW3.4 Operator acceptance remains pending. Live Cloudflare invocation remains unauthorized; deterministic fake providers only. `PLAN.md` remains the sole current-status authority.

**Current status (2026-11-23):** RW3.1–RW3.3 are accepted and merged. RW3.4 implementation and recovery corrections are merged through PRs #152, #163, #165, and #167; documentation reconciliation PR #168 is merged at `b00c6df93f224bca03168b7894ec3e154b2293ec`. The bounded follow-up adds six empty-result Context-integrity regressions, resolves the current-tree lifecycle-authority audit (`RW-WK-01`), and clarifies the 45-second/60-second receipt-only recovery boundary. The 35-row candidate ledger is 28 PASS / 7 PARTIAL / 0 OPEN. Formal RW3.4 Operator acceptance remains pending. Live provider authorization remains closed; deterministic fakes only. `PLAN.md` remains the sole current-status authority.

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

- SignalDisposition creation or refinement; triage remains RW-4. `triage_signal` does not create or enqueue an `update_thread` Task. RW-3 Tasks have only the host-authorized Operator creator defined in §10.4; any future application-authored creator (including triage-triggered work) requires a separately specified authorization, attribution, request-Event, idempotency, and replay contract, plus its own explicit approval.
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

RW3-0 decisions are recorded in §8. Thread-local world-memory records use stable canonical ordering; if the complete bounded set does not fit, Context assembly fails closed rather than silently dropping or truncating records. Team Experience is excluded from RW-3: the current `TaskContextAssembler` is scoped to `propose_strategy`, so no existing end-to-end authorized Context path is available to `update_thread` without adding a new integration. RW-3 does not invoke Team Experience retrieval. The following provider compatibility limits are fixed for RW-3 and are not open for expansion. They do not, by themselves, authorize production provider calls:

- Retrieval-derived passages: at most 8 passages and 8,000 Unicode characters.
- Model compatibility baseline: the Cloudflare Workers AI Llama 3.1 8B Instruct FP8 model documented in ADR-0031 only; ADR-0031 authorizes it for R6-E, and RW-3 live use remains separately gated as stated below.
- Total quoted input plus configured output: at most the model's 32,000-token context window, using the existing conservative UTF-8-byte-length-plus-128 framing-token quote.
- Output: at most the existing configured output-token ceiling of 1,024; a lower configured value is valid, a higher value is not.
- If separately authorized, one synchronous, non-streaming provider request per invocation; no tools and no adapter-level retry. TaskRuntime owns retry behavior and preserves the existing three-start Task limit.

RW3-0 fixes the model-worker proposal count at 8 per invocation; the existing 1,024-token output ceiling remains the stricter effective bound for many payloads. The Operator request contract remains unchanged at its existing maximum of 64 proposals. Do not add a separate serialized-output byte limit without a measured need.

## 4. Generation, parsing, and commit sequence

### Existing provider limits carried into RW-3

RW-3 retains the provider compatibility envelope and request limits documented in ADR-0031 and implemented in `core/generation.py`; this is not an extension of ADR-0031's authorization:

- Provider/model remain `cloudflare_workers_ai` and `@cf/meta/llama-3.1-8b-instruct-fp8`. A different provider or model requires a separate decision; the 32,000-token advertised context window does not authorize expanding Watch's own Context budget.
- Any retrieval-derived passage set remains limited to **8 passages and 8,000 Unicode characters**. Apply these limits unchanged; do not enlarge them because the model advertises a 32,000-token context window.
- The provider's conservative input quote remains UTF-8 byte lengths of the exact system and user prompts plus 128 framing tokens. Quoted input plus output must fit within 32,000 tokens.
- The configured output-token limit may be lower, but cannot exceed the existing **1,024-token** ceiling (`DEFAULT_MAX_OUTPUT_TOKENS`). Do not raise this ceiling for RW-3. The approved Task-wide generation-cost ceiling is **$0.02 across all three attempts**; every attempt must reserve its conservative maximum before the provider call, and unresolved/unknown charges continue to count in full.
- The adapter remains synchronous, non-streaming, one HTTP request per invocation, with no tools and no internal retries. It requires valid prompt/completion usage and an exact response-model match; retry eligibility remains TaskRuntime-owned.
- The output is one final JSON object validated locally. Do not rely on provider JSON Mode or expose/persist reasoning traces.

**Provider authorization gate:** ADR-0031 explicitly authorizes Cloudflare Workers AI Llama 3.1 8B FP8 for R6-E only. Checkpoint 3 approval fixes this existing model and rate card as RW-3's compatibility and budget-calculation baseline; it does not extend ADR-0031 or authorize live RW-3 provider calls. A separate explicit provider-authorization decision is required before any production `update_thread` provider invocation. Until that decision is accepted, implementation tests must use a deterministic fake provider and must not call Cloudflare. Any different provider, model, or rate card also requires a separate decision. The deterministic Context and proposal-count decisions are recorded in §8. Do not invent a second character limit for serialized output: the configured token cap is the existing hard output bound unless a separate measured need justifies a tighter application-level bound.

**Generation-cost integration:** the current `TaskGenerationCostService` does not authorize `update_thread`. RW-3 therefore requires a narrow extension to that existing service, not a new accounting subsystem: add one distinct operation identifier for `update_thread`, bind it to Task type `update_thread` and the exact ordered `allowed_writes` scope `[EvidenceLink, Hypothesis, ConfidenceChange]`, and add operation-specific quote/provider/model/rate-card/output-bound validation and tests. Preserve Task/attempt attribution, one reservation per operation per attempt, cumulative Task budget enforcement, and known/unknown/overrun reconciliation. The rate card and model identifier may be used to calculate the approved conservative budget, but ADR-0031 authorizes them for R6-E only. A separate explicit provider-authorization decision is required before any live RW-3 provider call; until then use only a deterministic fake provider. Do not silently broaden provider authorization. Reconciliation and current-attempt charge validation occur before the shared RW-2 commit core is called.

1. Validate the immutable Task request and its trusted Team/Thread target using read-only checks. Do not assemble attempt-specific Context before admission.
2. Admit/claim the Task attempt through TaskRuntime. This establishes the attempt that owns all subsequent Context, generation, and cost records.
3. Assemble and validate the bounded Context for that admitted attempt. If this fails, record failure through TaskRuntime; do not reserve cost or call the provider.
4. Reserve the maximum permitted generation cost for the exact Task attempt through the existing cost-accounting service.
5. Call a live provider only if the separate RW-3 provider-authorization decision has been accepted, and only after reservation succeeds. Until then, use a deterministic fake provider in tests; do not call Cloudflare.
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

- [ ] Existing generation and cost-accounting code is reused without creating a second provider abstraction. Live provider invocation is blocked until a separate explicit RW-3 provider-authorization decision is accepted; deterministic tests use a fake provider until then.
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
3. **Task creation and worker invocation:** use two distinct narrow application operations. A host-invoked Task-creation operation validates the request and creates the immutable `update_thread` Task and its request Event atomically; it does not invoke the model or execute the worker. A separate model-worker adapter accepts an already-created Task, validates its immutable request/target, admits through the existing TaskRuntime, then assembles Context and executes the generation/cost/commit sequence. Do not extend `TaskDispatcher`, add a scheduler, or create a second runtime.
4. **Proposal count:** allow at most 8 model proposals per invocation. The existing 1,024-token output ceiling remains independently enforced and may permit fewer. This 8-proposal cap is conservative, not performance-derived; raise it only if a real Task requires it and output, cost, and atomicity proofs are expanded. Keep the existing Operator `OperatorUpdateRequest` maximum of 64 unchanged; the 8-proposal cap belongs only to the model response parser. Preserve RW-D18/RW-2 mixed-batch and atomic accepted-set semantics.
5. **Empty/no-op:** an explicit empty `proposals` list is a valid no-op. Reconcile the incurred generation charge, skip the commit service and all business writes, then finalize through TaskRuntime with `success_no_change`. Do not retry a valid no-op. The model response envelope permits zero proposals; the shared Operator request model remains non-empty.
6. **Failure/rejection recording:** malformed JSON/schema, unknown fields, unsupported shapes, forged authority fields, excessive proposal count, and output-bound violations are non-retryable TaskRuntime failures with no proposal rejection Events. Structurally valid proposals that fail domain validation receive the existing per-proposal rejection Events. Mixed batches commit valid proposals atomically; all-invalid batches fail the Task through the existing TaskRuntime terminal path.

**Required narrow integration correction discovered during source audit:** the current `WorldMemoryCommitService` is Operator-specific: it requires an Operator principal and writes `operator_id` attribution. RW-3 cannot call it unchanged. RW-3 must extract/reuse the same proposal validation and atomic transaction core behind a narrow trusted actor seam (`operator` for RW-2, `model_worker` for RW-3), preserving RW-2's existing Operator identity and Event behavior. Model actor identity is application-defined and Task-attributed; model output cannot supply it. TaskRuntime also needs only task-type-specific admission, result validation, finalization, and recovery support for `update_thread`; it remains the sole lifecycle authority. This is not permission to add a second commit service, runtime, or generic actor framework.

RW3-0 remains source/design reconciliation only. Any schema migration, provider/model expansion, or change to accepted RW-D18/RW-2 batch semantics requires a separate decision. The design must receive independent review before a separate implementation-authorization decision. No implementation or schema migration is implied.

## 9. Implementation sequence

| Slice | Work | Exit gate |
|---|---|---|
| RW3-0 — design lock | Audit current Task, Context, provider, cost, TaskRuntime, and RW-2 commit contracts; resolve the remaining design locks above; reconcile docs. | Design is internally consistent, all design locks are resolved, and the design is reviewed and ready to present for a separate implementation-authorization decision. RW3-0 completion does not authorize implementation. |
| RW3-1 — Task creation and bounded Context | Implement the host-authorized immutable Task creator and deterministic Thread-scoped Context assembly, source/Snapshot validation, bounds, and provenance manifest. Creation is separate from admission/worker execution. | Positive/negative tests prove grant enforcement, Team derivation, Task/Event atomicity, UUIDv5 replay/conflicts, policy pinning, Context scope, source integrity, deterministic ordering, immutable replay, and fail-closed bounds. |
| RW3-2 — model worker | Implement strict output parsing and narrow worker orchestration using the existing provider and cost boundary. | Fake-provider tests prove provider ordering, schema rejection, bounds, and no authority escalation. |
| RW3-3 — shared commit/lifecycle | Connect proposals to the RW-2 commit service and TaskRuntime; prove mixed/all-invalid batches, atomicity, replay, concurrency, failure, and recovery. | Complete RW-3 proof matrix passes; no alternate runtime or write path. |
| RW3-4 — verification/closeout | Run exact-head local and hosted verification, review diff/docs, record results and explicit acceptance. | Exact tested SHA, all required checks, cleanup evidence, and Operator acceptance recorded. |

Each slice requires its own review/authorization as appropriate. Passing a prior slice does not automatically authorize the next. RW-3 completion does not authorize RW-4, RW-5, R7-C, persistent-database operations, or scored newsroom runs.


## 10. Independent design review corrections

This section resolves the implementation ambiguities identified by the independent reviews. It is normative for RW-3 and supersedes any less-specific wording in §§3–8.

1. **EvidenceLink membership:** include every accepted EvidenceLink belonging to an active Hypothesis on the target Thread. Do not apply relevance ranking, score-based selection, or discretionary filtering. Validate same-Team/same-Thread ownership and source integrity. Include the exact immutable source Snapshot for every included link. If the complete set exceeds any existing count or character bound, fail Context assembly through TaskRuntime; do not select a smaller subset.
2. **Policy pinning:** use only the policy version pinned by the immutable Task request (Task.policy_version). Verify that the pinned policy exists and is valid for the Task's Team. Never substitute the latest policy during execution. A missing, cross-Team, or inconsistent pin fails closed before provider invocation.
3. **Provider usage boundary:** the provider boundary must expose validated response-model identity, raw completion text, and validated usage metadata before JSON parsing. Reconcile usage and validate the exact current-attempt charge before parsing completion text. Then parse the text into typed proposals. If completion JSON is malformed but usage is valid, persist the reconciled charge and record a non-retryable parser failure through TaskRuntime, with no business writes. If usage is absent or invalid, use the existing unknown-cost accounting; do not assume zero. This requires a narrow change to the existing provider result contract because the current adapter parses JSON before returning usage. Do not create a second provider abstraction.
4. **Trusted actor attribution:** the shared commit core accepts a narrow typed actor distinction: the existing canonical Operator principal for operator_update, or a fixed application-defined model_worker actor for RW-3. The model-worker actor is derived only from application code and the admitted Task; model output cannot provide or override actor, principal, or attribution fields. Model-worker Events must identify the Task and actor type, and must not fabricate an Operator identity. Preserve existing RW-2 Operator principal validation and Event payloads unchanged in behavior. Do not introduce a generic actor framework.
5. **TaskRuntime success contract:** the only successful categories accepted for `update_thread` are `success_no_change` and `success_update_thread_committed`. The former means an explicit empty proposals list, a reconciled current-attempt charge, and no commit call or business writes. The latter means the durable commit marker proves that the shared commit core accepted at least one proposal (a mixed batch may also contain rejected proposals). Both require ordinary TaskRuntime terminal Event and Outcome creation, status transition, replay, and recovery. An all-invalid batch is `terminal_failure` with its durable rejection marker and rejection Events. `success_update_thread_committed` is invalid for every other Task type. Preserve the existing `success_no_change` behavior for all other Task types.

### 10.1 Durable generation receipt and proposal-set identity

RW-3 must not treat an in-memory provider response or an adapter return value as replay authority. The exact generated proposal set must be durably bound to one Task attempt before the commit core can write business state. Use the existing immutable Task-attributed `Event` stream and `TaskGenerationCharge`; do not add a proposal table, generic job ledger, or second persistence subsystem.

For each admitted `update_thread` attempt, use this ordered protocol:

1. **Generation receipt and charge reconciliation are one database transaction.** Before invocation, the worker must have assembled or replay-validated exactly one immutable Context Event for the current Task attempt. After the provider returns, the adapter first validates the response model identity and usage metadata and retains the raw completion text. In one transaction, reconcile the exact `TaskGenerationCharge` for `(task_id, attempt_count, operation='update_thread')` and append one `update_thread_generation_received` Event. The Event records schema version, Task/Team/Thread IDs, attempt, Task-pinned policy version, the exact `context_event_id`, `context_snapshot_ref`, and `context_content_hash` consumed by the provider, fixed actor type `model_worker`, operation, charge ID, provider/model, provider request ID when available, prompt/completion token counts, and the raw completion text. These three Context identity fields must match the unique attempt-bound `update_thread_context_assembled` Event and its content-addressed Snapshot; Task/attempt linkage alone is insufficient. A narrow in-session reconciliation entry point may be added to the existing `TaskGenerationCostService` so the receipt Event and charge settlement commit or roll back together; this is not a new cost subsystem. A valid usage receipt must remain durable even if the completion text later fails JSON parsing. Invalid/missing usage or model mismatch follows existing unknown-cost/fail-closed accounting and cannot authorize writes.
2. **Validated proposal set.** Parse only the raw completion text from that durable receipt. On strict-schema success, append one `update_thread_proposals_validated` Event containing schema version, Task/Team/Thread IDs, attempt, pinned policy version, the generation-receipt Event ID, the same `context_event_id`/`context_snapshot_ref`/`context_content_hash` tuple from the receipt, charge ID, and the complete canonical typed proposal list (including an explicit empty list). Include no model-controlled Task, Team, Thread, policy, actor, principal, charge, or attribution values; those fields are copied from trusted application state. Enforce at most 8 proposals before writing this Event.
3. **Canonical proposal fingerprint.** Compute SHA-256 over canonical UTF-8 JSON (`sort_keys=True`, `ensure_ascii=False`, compact separators) for an object containing a fixed protocol/domain tag `watch.rw3.update-thread-proposals.v1`, schema version, Task/Team/Thread IDs, attempt, pinned policy version, generation-receipt Event ID, the exact `context_event_id`/`context_snapshot_ref`/`context_content_hash` tuple, charge ID, and the complete typed proposal list. This binds content and provenance together; the fingerprint is not computed from model text alone. Store the `sha256:<hex>` fingerprint in the validated-proposal Event and every terminal commit/rejection marker.
4. **Commit marker.** For a non-empty proposal set, the shared RW-2 validation/transaction core writes the accepted business rows, per-proposal rejection Events, and exactly one terminal proposal marker in the same database transaction. `update_thread_committed` records Task/Team/Thread, attempt, actor type, generation-receipt Event ID, proposal Event ID, the exact Context identity tuple, charge ID, proposal fingerprint, committed proposal keys, and rejected proposal keys. If every proposal is invalid, write the existing attributable rejection Events plus one `update_thread_rejected` marker in the same transaction and no business rows. A mixed batch has one `update_thread_committed` marker with both committed and rejected keys. Conflicting, duplicate, cross-attempt, or fingerprint-mismatched markers fail closed.
5. **Empty proposal set.** The validated-proposal Event is the durable proof of an explicit empty list. Do not call the commit core and do not write a commit/rejection marker or business row. TaskRuntime may accept `success_no_change` only after it verifies that Event, the matching reconciled charge, and the absence of any RW-3 commit/rejection marker or Task-attributed world-memory write.

The generation receipt, validated-proposal Event, and commit/rejection marker are immutable append-only evidence. The charge ID, attempt, and Context identity tuple must match exactly across all applicable records. Recovery verifies their Task/Team/Thread/policy identity, Context Event/Snapshot identity and hash, Event linkage, canonical fingerprint, proposal keys, and charge state; it never repairs or substitutes contradictory evidence.


### 10.1.1 Explicit Context identity handoff — RW3.2 prerequisite

The Context identity handoff is an explicit protocol requirement, not an inference from Task/attempt linkage. The worker must pass the exact Context object it validated to the provider adapter and then persist this tuple in the generation receipt:

- `context_event_id`: UUID of the unique `update_thread_context_assembled` Event for the current Task attempt.
- `context_snapshot_ref`: exact immutable Snapshot reference from that Event.
- `context_content_hash`: exact SHA-256 content hash from that Event, verified against the Snapshot bytes.

The receipt transaction must revalidate that the tuple identifies exactly one Context Event for the same Task, Team, Thread, attempt, and pinned policy, and that the referenced Snapshot bytes match the recorded hash. The validated-proposal Event and canonical proposal fingerprint carry the same tuple. For non-empty proposals, the commit/rejection marker and typed commit envelope carry it too. Empty proposals still require the validated-proposal Event and receipt to agree on the tuple before `success_no_change`.

RW3.3 recovery must revalidate the same tuple against the Context Event and Snapshot before parsing a receipt-only response, resuming a proposal-only commit, accepting an existing marker, or reconstructing a terminal result. A missing, duplicate, cross-Task/Team/Thread/attempt/policy, changed-reference, or hash-mismatched Context identity is permanent integrity failure: no provider reinvocation, no business writes, and no guessed substitution. The proposal fingerprint inherits Context provenance through its explicit tuple and receipt binding; it does not replace the independent verification of the referenced Context Snapshot.

This decision does not change the RW3.1 Context Event/Snapshot schema or add a migration. It was a prerequisite for RW3.2 implementation; RW3.2 was subsequently authorized, accepted, and merged by PR #137. RW3.3 has since been accepted and merged by PR #138. Neither milestone authorizes live provider use.

### 10.2 Crash windows and TaskRuntime recovery

TaskRuntime remains the only lifecycle authority. Its `update_thread` recovery branch must use the existing application worker and shared commit core only to resume from durable records; it must never invoke the provider again for the same attempt.

- **Provider returned, but the receipt/charge transaction did not commit:** there is no durable response. The still-reserved charge is conservatively changed to `unknown`; the raw response cannot be reconstructed. TaskRuntime applies the existing retry/attempt limit and cumulative budget rules. A later attempt is a new provider invocation and a new charge. Exactly-once external provider invocation is not promised because a process can fail after the remote response and before local durable capture.
- **Receipt and reconciled charge exist, proposal Event absent:** recovery parses the stored raw completion text and writes the validated-proposal Event, or records the deterministic non-retryable parser failure. It does not call the provider.
- **Validated proposal Event exists, marker absent:** recovery resumes the same proposal set through the shared commit core using the stored fingerprint and charge reference. It does not regenerate proposals or call the provider.
- **Commit/rejection marker exists:** recovery validates the receipt, proposal Event, fingerprint, charge, attempt, marker keys, and committed business state, then reconstructs the terminal observation. It does not reapply writes.
- **Empty validated proposal Event exists:** recovery verifies the reconciled charge and absence of commit/business-write evidence, then reconstructs `success_no_change`.

The recovery implementation must recheck Task status and current attempt under the Task-row lock. Any session-scoped commit/resume seam must use that same locked transaction (or an equivalently explicit compare-and-set boundary); it must not open a competing transaction that can race TaskRuntime finalization. A receipt with unknown, unreconciled, model-mismatched, or overrun charge is never eligible for parsing-to-commit or business writes. Missing, duplicate, cross-Task, cross-Team, cross-Thread, cross-policy, cross-attempt, or internally inconsistent records are surfaced as corruption, not guessed around.

### 10.3 TaskRuntime result and recovery contract

For `update_thread`, TaskRuntime accepts exactly these result categories:

- `success_update_thread_committed`: only when one valid `update_thread_committed` marker binds the exact validated proposal Event and reconciled current-attempt charge, contains at least one committed proposal key, and the committed business rows/Event set agree with the marker.
- `success_no_change`: only when one valid validated-proposal Event contains an empty proposal list, its generation receipt and current-attempt charge are valid and reconciled, and no commit/rejection marker or Task-attributed business write exists.
- `terminal_failure`: for parser/provider/Context/cost/authority failures before a validated non-empty proposal set exists, or for an all-invalid proposal set. If a non-empty validated-proposal Event exists, terminal failure is valid only with exactly one matching terminal evidence marker: `update_thread_rejected` proving every proposal key was rejected for an all-invalid domain result, or `update_thread_recovery_inconsistent` proving a permanent integrity/provenance failure with no business writes. A transient persistence failure has no terminal marker and remains resumable through the same proposal set; it cannot be terminalized or sent through a new provider attempt. Without either permitted terminal marker, recovery must run the commit core. An empty validated-proposal Event is `success_no_change`, not failure. No success marker may coexist with failure.

Reject `success_update_thread_committed` on every non-`update_thread` Task. Do not change the existing `success_no_change` contract for other Task types. Other result categories are not valid for `update_thread`. The TaskRuntime recovery path must distinguish a durable commit, durable all-invalid rejection, durable empty proposal set, resumable receipt/proposal set, and an attempt with no durable receipt; only the last case may fall through to ordinary interrupted-attempt retry after settling any reservation as unknown.

The provider adapter, in-session cost reconciliation, proposal receipt, commit marker, and TaskRuntime changes above are design requirements only. This document does not authorize implementation. The corresponding acceptance proofs are listed in the RW implementation plan.


### 10.4 Immutable model-worker request and Thread binding

A model-worker Task has one durable request Event binding it to one target Thread. Use the proven R6-F host-creation and replay pattern; do not add a new Task factory framework, request-key column, or database constraint without a demonstrated gap.

- **Creator and authorization boundary:** add one narrow host-invoked application operation, `create_update_thread_task(principal, request)`, modeled on `OperatorApplicationAdapter`. Its frozen request contains only `thread_id` and a UUID `idempotency_key`; it does not accept a caller-supplied Team as authority. The trusted host authenticates the Operator and issues a `TrustedOperatorPrincipal` containing the exact Team grant `OperatorGrant(team_id=<authorized Team>, action="request_update_thread")` only after checking that Operator's permission to request this operation for that Team. Watch must still resolve the target Thread under the creation transaction, derive its Team from that locked Thread, and call the existing exact `_require_team_grant(principal, team_id, action="request_update_thread")` check before creating anything. The creator validates that the derived Team is active and that the Thread is available for update (same-Team, existing, and not resolved/otherwise unavailable); it then pins the selected valid TeamPolicy version as specified by the Task contract. The action string is a distinct proposed grant and must be used consistently by the trusted host grant issuer and Watch check; do not reuse `operator_update` or `approve_learning_change`. Missing/wrong-type principals, malformed issuer/subject identity, missing/wrong-Team/wrong-action grants, inactive Teams, and unavailable or cross-Team Threads reject without creating a Task or Event. The host-supplied principal is an in-process trust contract, not a credential: the operation must remain reachable only from the trusted host composition boundary, not an untrusted public caller. The repository currently has no production host composition root or constructor call site for `TrustedOperatorPrincipal`; therefore this design proves Watch-side grant enforcement but cannot claim end-to-end host authentication until that integration exists. This does not require a deployed Watch API/CLI or a new Watch authentication system. The operation is the only creator of `update_thread` Tasks and their `update_thread_requested` Events. The worker accepts an existing Task ID and cannot create, amend, retarget, or impersonate the requesting Operator.
- **Stable Task identity:** derive the Task ID deterministically with UUIDv5 from a fixed, versioned namespace and the tuple (team_id, task_type='update_thread', idempotency_key), following R6-F's _approval_task_id pattern. The raw idempotency key is not model input; store only its SHA-256 hash in the request Event. The namespace and tuple encoding are fixed implementation constants, not per-process state. The same host key therefore resolves to the same Task after restart; a different key represents a distinct request.
- **Atomic creation and concurrency:** in one database transaction, insert the pending Task using its deterministic primary key and, only for the transaction that inserted that Task, append its update_thread_requested Event. Task and Event commit or roll back together. Resolve concurrent same-key creation through the Task primary-key conflict: the losing caller loads the winning Task and verifies/replays its request; it must not append a second Event. Do not create the Event before or after the Task transaction.
- **Request identity:** the versioned Event payload contains exactly schema_version, task_id, team_id, thread_id, policy_version, requested_by_operator_id, idempotency_key_hash, and request_fingerprint. `requested_by_operator_id` is the canonical issuer/subject identity from the validated `TrustedOperatorPrincipal`; it is durable authorization attribution, not a model-worker identity. The Event envelope supplies its Event ID, Task attribution, and creation timestamp. The request fingerprint is SHA-256 over canonical UTF-8 JSON containing the fixed domain tag `watch.rw3.update-thread-request.v1` and the immutable request fields (including `requested_by_operator_id` and the idempotency-key hash) except the fingerprint itself. Canonical issuer/subject encoding must be fixed and version-independent (reuse the canonical representation from existing principal validation; do not improvise it at the call site). The Task row remains authoritative for Task ID, Team ID, Task type, and pinned policy version; the Event supplies the immutable Thread binding, requesting Operator attribution, and request identity.
- **Replay and fail-closed validation:** on same-key replay or a Task load before provider invocation, require the expected deterministic Task ID and exact Task shape/type/write scope; load exactly one `update_thread_requested` Event; validate its complete versioned payload and recomputed fingerprint; require duplicated Task fields to match; and revalidate that the Thread and pinned policy exist, are valid, and belong to the Task's Team. Same Team/key plus the same fingerprint and same canonical requesting Operator returns/reconstructs the original Task. Within that Team/key scope, reuse with a different Thread or requesting Operator rejects as an idempotency conflict. The same UUID under another Team is a separate Team-scoped identity, not a cross-Team conflict. Policy advancement alone does not conflict: replay validates and retains the original Task.policy_version and its historical TeamPolicy row. A mismatch between the Task's stored policy pin and its request Event, or invalid/missing historical policy evidence, fails closed. A replay by a different Operator must not inherit the original Operator's authorization. Missing, duplicate, malformed, mutated, or inconsistent records fail closed before provider invocation. Never substitute an Operator request Event or fabricate an Operator identity.
- **Database constraint decision:** no partial unique index or migration is required by this design. The existing Task primary key arbitrates concurrent same-key creation, and the single authorized creator writes the request Event in the same transaction only after winning that insert. Exact-one Event cardinality is an application invariant: creation, replay, and pre-provider validation check it, and duplicates fail closed. The current (task_id, type) Event index remains non-unique. This follows R6-F's precedent: its historical audit recorded the same non-unique Event index, host idempotency UUID, deterministic Task identity, request fingerprint, and “add schema only if tests prove a gap.” A database uniqueness constraint may be reconsidered only if implementation tests demonstrate a concrete race/integrity gap that the Task-PK transaction pattern cannot close; any such migration requires separate authorization. Event append-only behavior remains an application contract here, not a new database immutability guarantee.

This request Event is the durable authorization and attribution binding for the target Thread: it records which authenticated host principal requested the Task, while the host's authentication decision remains outside Watch. The phrase “immutable Task request” in §§3–10 means this Task-plus-Event contract. The model-worker adapter receives only the existing Task and verified request Event; it does not receive a `TrustedOperatorPrincipal`, an `operator_id`, or the requesting Operator's grants. Model-worker proposal/terminal Events are Task-attributed and must not copy `requested_by_operator_id` into an `operator_id` field. RW-2's Operator principal and Event contract remain unchanged. RW-3 does not extend Strategy, PlanService, Plan materialization, or TaskDispatcher to produce these Tasks.

**Checkpoint 1 authorization proof obligations:**

- Reject a missing principal, raw string, wrong principal type, malformed/empty issuer or subject, absent grants, wrong-Team grant, and wrong-action grants (including `operator_update` and `approve_learning_change`) without creating a Task or Event.
- Reject cross-Team, inactive-Team, missing, unavailable, or resolved Thread targets without creating a Task or Event; prove Team identity is derived from the locked Thread rather than caller input.
- Prove the trusted host issues `request_update_thread` only after authenticating the Operator and authorizing the target Team. Until a real host composition root exists, report this host-side proof as an integration limitation, not as a Watch-side test result.
- Prove the request Event records the canonical requesting Operator, its fingerprint binds that identity, and same-key replay by a different Operator or for a different Thread conflicts without creating a second Task/Event.
- Prove model-worker execution and commit attribution contain no Operator principal or `operator_id`, while existing RW-2 Operator identity checks and Event payloads remain unchanged.

These are design/test obligations only. The exact Task shape and budget are resolved by the approved Checkpoint 3 decision in §10.4.2; that decision is still a design/test contract and does not authorize implementation.

### 10.4.1 TeamPolicy selection and concurrency

**Checkpoint 2 decision — approved:** a new `update_thread` Task pins the highest TeamPolicy version for its Team, selected while holding the Team serialization lock. The Task and its request Event persist that version atomically. A policy version is immutable; policy changes append a new version and never edit an existing row. Immutability is an application-level append-only contract, not a database guarantee: the current TeamPolicy mapping has the `(team_id, version)` uniqueness constraint and supported-schema check, but no database rule preventing updates to an existing row. Do not claim DB-enforced immutability or add a trigger/constraint in RW-3 without a separate demonstrated need and authorization. The current `core/policy.py` contains narrow parsers for daily Task quota and the D7 review interval, not a universal TeamPolicy JSON-Schema validator. Implementation must validate `schema_version` against the supported values, require a rules object, and apply existing validators to every rule it actually consumes; it must not claim broader validation than exists. Any new `update_thread` policy vocabulary or schema requires a separate design decision.

**New Task creation order:**

1. Read the target Thread only to discover its candidate `team_id`; the caller still cannot supply an authoritative Team.
2. Lock that Team row with `SELECT ... FOR UPDATE`.
3. Re-read and lock the target Thread with `FOR UPDATE`, constrained to the candidate Team. Revalidate that the Thread still belongs to that Team and remains available for update.
4. Resolve the deterministic Task ID. If the Task already exists, validate/replay it using its stored `Task.policy_version`; do not select the current policy again.
5. Only for a genuinely new Task, select the TeamPolicy with the greatest `version` for that Team, ordered descending and limited to one row, using `FOR SHARE`. Validate that selected row's Team ownership, supported `schema_version`, and the existing versioned rules contract relevant to `update_thread`.
6. If the selected newest policy is missing or invalid, fail closed. Do not fall back to an older policy. Persist the selected version in the Task and request Event in the same transaction as Task/Event creation.

The TeamPolicy model has a unique `(team_id, version)` key and Tasks reference `(team_id, policy_version)`. There is no active-version pointer: the highest version is current. Do not add one for RW-3. Immutability is an application-level append-only contract, not a database guarantee: the current TeamPolicy mapping has the `(team_id, version)` uniqueness constraint and supported-schema check, but no database rule preventing updates to an existing row. Do not claim DB-enforced immutability or add a trigger/constraint in RW-3 without a separate demonstrated need and authorization. The current `core/policy.py` contains narrow parsers for daily Task quota and the D7 review interval, not a universal TeamPolicy JSON-Schema validator. Implementation must validate `schema_version` against the supported values, require a rules object, and apply existing validators to every rule it actually consumes; it must not claim broader validation than exists. Any new `update_thread` policy vocabulary or schema requires a separate design decision.

**Policy publication and serialization:** any future policy-publishing operation must acquire the same Team `FOR UPDATE` lock before determining the next version and inserting a new immutable TeamPolicy row. PostgreSQL's TeamPolicy-to-Team foreign-key check takes a key-share lock on the Team; that conflicts with the creator/publisher's Team `FOR UPDATE` lock. Therefore, when both operations follow this Team-first protocol, the transactions serialize: a creator that wins first pins the prior version, while a publisher that commits first makes the new version visible to the next creator. Keep lock order Team → Thread → TeamPolicy/Task/Event to avoid introducing an inverse-order deadlock.

No production TeamPolicy publishing service was found in the audited repository. This is a required contract for any future publisher, not a claim that a publisher or its integration currently exists. Do not create a publisher, mutate TeamPolicy, add a lock table, active pointer, index, or migration as part of this planning checkpoint.

**Replay and execution:** same-key replay uses the original Task's stored policy version and the matching historical TeamPolicy row, even after a newer version is published. It never re-pins to the latest version. Missing, cross-Team, mutated, unsupported, or invalid historical policy evidence fails closed; a newer valid version does not invalidate an otherwise valid historical pin. Context assembly and worker execution always use the Task-pinned version, never a fresh latest-policy lookup.

**Checkpoint 2 proof obligations:**

- Prove a new Task selects the greatest TeamPolicy version for its Team and rejects when no policy exists.
- Prove the newest selected policy is validated against the supported schema and relevant existing rules; an invalid newest version fails closed rather than falling back to an older valid version.
- Prove Task and request Event persist the same policy version atomically.
- Prove replay after policy advancement returns the original Task and original policy version; same-Team/key request conflicts remain governed by the Checkpoint 1 fingerprint. A different Team is a separate identity scope.
- Prove missing, cross-Team, mutated, unsupported-schema, and invalid historical policy pins fail closed before provider invocation.
- Use disposable PostgreSQL transactions to race Task creation against policy publication in both lock orders. Assert the creator pins exactly the version committed before it acquired the Team lock, with no mixed or ambiguous binding.
- Prove all policy-publishing code follows Team `FOR UPDATE` before version allocation/insertion. Until a real publisher exists, record this as an integration contract and test the creator-side serialization boundary with a controlled competing transaction; do not claim publisher integration coverage.

These are design and test obligations only. They do not authorize a TeamPolicy publisher or RW-3 implementation.

### 10.4.2 Task shape, generation budget, and deadline

**Checkpoint 3 decision — approved:** the immutable `update_thread` Task uses the exact envelope below. It is a planning contract; no ORM/schema migration or runtime implementation is authorized by this approval.

- `task_type="update_thread"`, `status="pending"`, `attempt_count=0`, and `max_attempts=3` at creation.
- `team_id` is derived from the locked target Thread; `thread_id` is the same target bound by the single verified `update_thread_requested` Event. `policy_version` is the valid highest version pinned under §10.4.1.
- `objective_id`, `plan_id`, and `plan_action_id` are all `NULL`.
- `allowed_writes` is exactly the ordered list `["EvidenceLink", "Hypothesis", "ConfidenceChange"]`.
- `budget` is exactly `{ "max_tool_calls": 0, "max_cost_usd": 0.02, "deadline_seconds": 45 }`. No tool capability is granted. The three-start limit is the Task's separate `max_attempts` field, not another budget key.
- Do not add `input_refs` or `allowed_tools` Task columns for this slice. The immutable request Event binds the Thread; application code builds Context from canonical records and the Task-pinned policy. Event and Outcome remain Kernel/TaskRuntime side effects, outside `allowed_writes`.

**Cumulative generation-cost ceiling:** `$0.02` applies to all attempts of one Task, not separately to each attempt. The existing Cloudflare rate card in `core/generation.py` is revision `cloudflare-llama-3.1-8b-fp8-2026-10-30`, with input `$0.152` and output `$0.287` per million tokens. At the maximum 32,000-token context and 1,024-token output, the conservative input quote is at most 30,976 tokens (including the existing 128 framing-token allowance), producing a maximum one-attempt quote of `$0.00500224`; three such reservations total `$0.01500672`, below the `$0.02` Task ceiling. The exact prompt is quoted for each attempt; if its quote plus output does not fit the 32,000-token context or the cumulative Task ceiling, do not call the provider. Keep the existing provider/model/rate card; any pricing or model change requires a separate decision.

The existing `TaskGenerationCostService` must receive one narrow `update_thread` operation mapped only to Task type `update_thread` and the exact ordered write scope above. Preserve the existing reservation ledger, Task/attempt attribution, one reservation per attempt, cumulative accounting across reconciled and unresolved charges, and known/unknown/overrun behavior. Unknown usage retains the full reservation; it is never treated as zero or released to fund a later attempt. A valid reconciled current-attempt charge remains mandatory before business commit.

**Deadline:** the absolute Task deadline is 45 seconds from successful TaskRuntime admission. The worker enforces it across Context assembly, quoting, provider execution, parsing, and pre-commit processing; the provider request timeout is capped at 30 seconds and must not exceed the remaining Task time. No provider call starts after the deadline. The current `TaskRuntime.admit()` validates that `deadline_seconds` is a positive integer but does not enforce elapsed time; the implementation must add only the narrow `update_thread` deadline enforcement required here, not a global runtime redesign. Preserve the existing 60-second interrupted-task recovery threshold; it is not the execution deadline.

**Provider compatibility and proposal bounds:** if live provider use is separately authorized, use only the ADR-0031 Cloudflare Workers AI Llama 3.1 8B FP8 model, one synchronous non-streaming HTTP request per admitted attempt, no tools, no provider-adapter retries, at most 1,024 output tokens, and the existing 32,000-token total quoted-context ceiling. TaskRuntime alone owns the maximum three starts. The model response remains limited to 8 proposals per invocation; the Operator request limit of 64 and RW-2 batch semantics are unchanged.

**Checkpoint 3 proof obligations:**

- Prove exact Task creation/replay/admission shape, including null Objective/Plan/PlanAction links, exact write-scope order, pending/zero-attempt initial state, three maximum starts, and the exact three-key budget. Missing, extra, mistyped, or widened fields fail closed before provider invocation.
- Prove `max_tool_calls=0` and no tool capability; reject any nonzero tool allowance.
- Prove the $0.02 cumulative Task ceiling across all attempts, one reservation per admitted attempt, exact operation/Task/write-scope mapping, and three maximum conservative reservations fitting within the ceiling. Reservation denial must make zero provider calls; unknown reservations remain fully accounted; overrun/unknown/unreconciled charges cannot authorize business writes.
- Prove the live-provider authorization gate: without a separately accepted RW-3 provider decision, the worker/test composition cannot make a Cloudflare call and uses only a deterministic fake provider. If that decision is later accepted, prove exact provider/model/rate-card binding, per-prompt quote, 32,000-token context enforcement, 1,024-token output ceiling, one HTTP request per attempt, and no provider-adapter retry.
- Prove the 45-second absolute deadline is enforced from admission, including Context and post-provider work; provider timeout never exceeds 30 seconds or remaining Task time; no call starts after expiry. Keep the 60-second interrupted recovery threshold unchanged.

These are approved design decisions and proof obligations only. They do not authorize RW-3 implementation.

### 10.5 Executable TaskRuntime recovery handoff

TaskRuntime owns the Task row lock, attempt identity, retry decision, and terminal lifecycle. The worker/commit layer does not open a competing transaction or independently transition Task state.

- Add one narrow in-session recovery entry point, named here resume_update_thread_in_session(session, task, attempt). TaskRuntime calls it only after locking and rechecking the Task row, confirming Task type update_thread, the expected current attempt, and the durable request Event.
- The function receives the already-locked SQLAlchemy Session and the exact Task/attempt. It reads and validates the receipt, reconciled charge, proposal Event, fingerprint, and any marker. It never calls the provider, creates a new attempt, changes Task lifecycle state, commits/rolls back the Session, or opens another Session/transaction.
- With receipt but no proposal Event, it parses the stored raw completion and writes the validated-proposal Event in the caller's transaction, or returns a deterministic parser-failure disposition. With a validated non-empty proposal Event and no marker, it resumes that exact proposal set through the shared commit core in the same Session. With a valid marker, it returns the verified terminal observation without reapplying writes. With a validated empty set, it returns the verified no-op observation.
- TaskRuntime alone translates the returned disposition into the existing terminal Event/Outcome/status transition or a retryable interrupted-attempt disposition. It performs terminalization in the same transaction as the verified marker/observation where required.
- A transient database, deadlock, or serialization failure rolls back the current transaction and leaves the same durable proposal Event resumable. It must not consume a new provider attempt or invoke the provider again. The next recovery pass resumes the same proposal fingerprint.
- A permanent integrity/provenance conflict (wrong Task/Team/Thread/policy/attempt/charge, duplicate or contradictory Event, fingerprint mismatch, or committed rows inconsistent with the marker) fails closed and writes no new business state. TaskRuntime records an update_thread_recovery_inconsistent terminal evidence Event and uses terminal_failure; this is distinct from an all-invalid domain rejection and cannot be represented as update_thread_rejected.
- If no durable receipt exists after an interrupted provider call, TaskRuntime marks the still-reserved charge unknown and applies the existing attempt/budget policy. This is the only recovery case that may return to ordinary new-attempt retry. The remote provider may already have been called; exactly-once invocation is not claimed.

The handoff is a narrow Task-type-specific branch in the existing TaskRuntime, not a generic recovery framework. The worker may expose a normal first-attempt execution method, but all interrupted/replayed execution must converge on this same in-session resume function.

**RW3.4 deadline/recovery correction:** the 45-second Task deadline is one absolute monotonic deadline captured at real TaskRuntime admission. The provider transport deadline is the earliest of that Task deadline, the provider's configured timeout, and the worker-supplied timeout cap. Proposal persistence rechecks the deadline after acquiring the Task lock, before Event insertion, and after flush; if expiry is observed before transaction commit, the proposal transaction rolls back. Recovery may commit only an existing proposal Event whose timestamp is strictly before expiry. A receipt without a pre-deadline proposal Event is insufficient: receipt-only recovery after expiry terminalizes with `update_thread_deadline_exceeded` and does not create a proposal Event or reinvoke the provider. Late or exact-deadline proposal Events fail closed before the shared commit core. Pre-deadline durable proposals remain recoverable without provider reinvocation. The normal interrupted-recovery threshold remains strictly greater than 60 seconds, while this Task's deadline is 45 seconds. Consequently, a receipt-only attempt cannot be discovered by normal `TaskRuntime.recover_interrupted()` before its deadline; the reachable normal recovery case is receipt-only after expiry, which fails terminally as above. Do not add a test that invokes the in-session resume seam before the stale threshold and describe it as normal runtime recovery. Supporting earlier recovery would require a separate safe lease/ownership synchronization mechanism to prove the worker is no longer active.

### 10.6 Typed actor, proposal Events, and terminal validators

The shared commit core accepts a validated proposal envelope and a closed actor union; it does not accept an untyped actor dictionary or infer authority from Event payloads.

- OperatorActor contains the existing canonical authenticated Operator principal and is used only by the existing RW-2 path. Its validation, request Event, proposal rejection Event payloads, commit Event payloads, and replay behavior remain unchanged.
- ModelWorkerActor contains only fixed actor type model_worker, the admitted task_id, and the verified update_thread_requested Event ID. Application code constructs it after TaskRuntime admission and request validation. It has no operator_id, Operator principal, or model-supplied identity.
- The shared core input is a typed envelope containing the trusted actor, Task/Team/Thread IDs, attempt, pinned policy version, generation receipt Event ID, proposal Event ID, charge ID, canonical proposal fingerprint, and parsed proposal objects. Every field is checked against durable records before writes.
- For the model path, accepted proposals produce Task-attributed update_thread_proposal_accepted Events and invalid proposals produce Task-attributed update_thread_proposal_rejected Events. Both include schema version, Task/Team/Thread/attempt, actor type model_worker, proposal key, proposal fingerprint, and stable disposition/reason. They contain no operator_id. Existing RW-2 Operator proposal Event types and payloads are not renamed or weakened.
- The model terminal marker is either update_thread_committed (one or more accepted proposal keys; mixed accepted/rejected keys permitted) or update_thread_rejected (all proposal keys rejected), with the exact receipt/proposal Event IDs, charge, attempt, fingerprint, and exhaustive accepted/rejected key sets. A separate update_thread_recovery_inconsistent Event is used only for permanent integrity failure; it is not a domain rejection marker.
- The model terminal validator checks the model-specific Event types, fixed actor type, Task attribution, request Event linkage, exact proposal/receipt/charge identity, fingerprint, exhaustive key partition, and committed database rows. The Operator terminal validator remains Operator-specific and unchanged. Do not make either validator accept the other's Event family.
- No generic actor framework, second commit service, second Task runtime, or alternate write path is introduced. The actor union exists only at the shared RW-2 proposal-validation/atomic-transaction boundary.

### 10.7 Canonical typed proposal serialization

The proposal Event and fingerprint use one exact serialization contract:

1. Parse into the existing strict RW-2 proposal Pydantic models (or narrowly versioned RW-3 model-worker envelope models). Reject unknown fields, coercion, non-finite numbers, duplicate proposal keys, malformed UUIDs, unsupported enum values, and invalid schema versions before persisting the proposal Event.
2. Serialize each validated proposal with model_dump(mode="json"). UUIDs are canonical lowercase hyphenated strings; enums serialize to their declared string values; datetimes, where present, use the model's canonical JSON representation. No Python repr, database row serialization, or original model JSON text enters the fingerprint.
3. Preserve proposal array order exactly as returned by the model. Do not sort proposals: order is part of the durable response identity. Object keys are canonicalized by the fingerprint encoder. Duplicate proposal keys reject rather than being silently deduplicated.
4. Encode the complete provenance envelope and proposal list as UTF-8 JSON using sort_keys=True, ensure_ascii=False, and separators (",", ":"); reject NaN/Infinity and any value not representable by the strict schema. Hash those exact bytes with SHA-256 and prefix the lowercase hexadecimal digest with sha256:.
5. Persist the same canonical typed proposal list and fingerprint in the validated-proposal Event and verify them byte-for-byte/canonically during recovery. The schema version and domain tag prevent future schema changes from being mistaken for the same proposal set.

### 10.8 Commit failure disposition

A validated non-empty proposal set is never discarded or regenerated merely because commit failed.

- Transient persistence failure: transaction rollback leaves the proposal Event and its fingerprint intact and no partial business writes/marker. The same proposal set remains resumable through §10.5; do not call the provider or consume a new generation attempt.
- All proposals domain-invalid: commit the complete rejection Event set and one update_thread_rejected marker atomically; TaskRuntime records terminal_failure.
- Permanent integrity/provenance failure: write no business rows. Record update_thread_recovery_inconsistent with the exact Task/attempt/proposal fingerprint and stable failure category, then TaskRuntime records terminal_failure. This marker is the only permitted terminal-failure evidence for a non-empty validated proposal set when the failure is not an all-invalid domain result. It must not claim that proposals were rejected by domain validation.
- Successful or mixed commit: write accepted rows, accepted/rejected per-proposal Events, and one update_thread_committed marker in the same transaction. Recovery verifies the exact marker and rows before terminalization.
- No generic retry queue or new retry subsystem is introduced. Existing TaskRuntime policy decides when to retry transient infrastructure failures; it always resumes the same durable proposal set before considering a new provider attempt.

## Checkpoint 4 — deterministic request and proposal identity decisions approved

The following Checkpoint 4 decisions are approved. They resolve earlier provisional wording in this document; the Checkpoint 5 cross-document reconciliation is recorded in §11.

### Task identity and request idempotency

Use a dedicated fixed UUIDv5 namespace for update_thread. The deterministic name is the canonical lowercase, hyphenated Team UUID, the literal operation update_thread, and the canonical lowercase, hyphenated idempotency UUID, separated by colons:

{team_id}:update_thread:{idempotency_key}

The namespace is a fixed implementation constant, never generated at runtime. This is Team-scoped idempotency, matching the R6-F deterministic Task identity precedent.

- Same Team and same key resolve the same Task.
- Within that Team/key scope, a different Thread or canonical requesting Operator conflicts; it must not create a second Task or request Event.
- The same UUID used by a different Team is a separate Team-scoped identity, not a cross-Team conflict. Global cross-Team key uniqueness is not part of RW-3 and would require a different durable uniqueness design.

Use the proven R6-F creation pattern: attempt deterministic Task insertion with conflict-safe insertion; only the transaction that wins Task creation appends the request Event; resolve a competing insert through the Task primary key and validate the existing request. Do not use the weaker RW-2 operator_update insertion path for this concurrency boundary.

### Request Event and fingerprint

The request Event stores no raw idempotency UUID. Store only idempotency_key_hash, computed as SHA-256 over the canonical lowercase, hyphenated UUID string encoded as ASCII, formatted sha256:{64 lowercase hex characters}.

The request fingerprint is SHA-256 over UTF-8 bytes of compact canonical JSON with sorted keys, ensure_ascii=False, and separators (",", ":"). Its exact versioned object contains only:

- domain: watch.rw3.update-thread-request.v1
- schema_version: integer 1
- canonical task_id, team_id, and thread_id
- the Task's pinned integer policy_version
- requested_by_operator_id, produced by the existing canonical_operator_identity() helper
- idempotency_key_hash

Store the digest as sha256:{lowercase hex}. Do not include the fingerprint itself, Event ID, Event timestamp, or database-generated metadata in its preimage. The domain and schema version are fixed protocol constants.

Requester identity must reuse canonical_operator_identity(): stable issuer/subject identity, compact sorted-key JSON, and the helper's existing validation. It is request attribution only; it is not model-worker identity and must never be copied into operator_id for worker Events.

### Replay and pinned policy

Resolve deterministic Task identity before selecting a current policy. For an existing Task, validate its exact Task shape, load exactly one valid request Event, validate its schema and canonical identity, recompute the request fingerprint, and revalidate Thread and historical TeamPolicy ownership/integrity. Return the original Task only if the request matches.

Policy advancement alone does not conflict with replay. Replay retains the Task's original policy_version; it does not select the latest version again. A mismatch between Task policy pin and request Event, missing/cross-Team/invalid historical policy, duplicate or malformed request Event, or fingerprint mismatch fails closed.

### Proposal-set identity is distinct

The request fingerprint identifies the authorized host request and its immutable Task/Thread binding. The proposal-set fingerprint identifies one exact generated proposal set for one Task attempt and charge. Do not combine these identities.

Retain the proposal-set domain watch.rw3.update-thread-proposals.v1. Bind the complete strict typed proposal list to Task, Team, Thread, attempt, pinned policy, durable generation-receipt Event ID, and charge ID. Serialize typed proposals using Pydantic model_dump(mode="json"), canonical compact sorted-key JSON, UTF-8, and SHA-256. Preserve proposal-array order and reject duplicate proposal keys. The response schema permits an explicit empty list and caps non-empty lists at eight; this does not alter the Operator request's existing 64-proposal limit.

### Checkpoint 4 proof obligations

- Deterministic UUIDv5 golden vectors prove namespace and canonical name stability across process restarts.
- Concurrent same-Team/same-key creation produces exactly one Task and one request Event.
- Same-Team/key reuse with a different Thread or requester conflicts without extra Task/Event creation; same key in another Team is independently scoped.
- Request Event cardinality, schema, requester identity, key hash, Task binding, pinned policy, and fingerprint are validated on replay and before provider execution.
- Golden request-fingerprint vectors prove exact canonical bytes and digest; raw idempotency UUID is absent from persisted Event data.
- Policy advancement preserves valid historical replay; Task/Event pin mismatch and invalid historical policy fail closed.
- Golden proposal-set vectors prove canonical typed serialization, UUID/enum representation, preserved array order, duplicate-key rejection, empty-list support, domain separation, and exact digest.
- Proposal-set identity cannot be replayed across Task, Team, Thread, attempt, policy, receipt, or charge.

No application code, tests, migrations, schema, or runtime behavior were changed by this design decision. RW-3 implementation was separately authorized on 2026-11-19, beginning with RW3.1 only.

## 11. Checkpoint 5 — cross-document reconciliation

This design plan is normative for RW-3 protocol, identity, replay, generation, commit, and recovery semantics. `docs/tasks.md` is normative for the Task envelope/write scope/budget; the implementation plan carries the proof matrix and slice order; `docs/architecture.md` summarizes the architectural boundary; `PLAN.md` alone owns current status and authorization; `CHANGE_MAP.md` maps these authorities. The six documents must not create competing definitions. The reconciled Checkpoint 4 identity contract is Team-scoped UUIDv5: same-Team/key reuse with a different Thread or requester conflicts; the same UUID in another Team is a separate identity. Policy advancement alone does not invalidate replay of the original Task policy pin. The request fingerprint and proposal-set fingerprint are separate, versioned identities. Checkpoint 3's provider/model/rate-card values are a compatibility and budget baseline only: ADR-0031 remains scoped to R6-E, and live RW-3 provider calls require a separate explicit provider-authorization decision. Checkpoint 5 reconciliation was documentation-only and did not itself authorize implementation. A separate implementation authorization was granted on 2026-11-19 for RW3.1 only.
