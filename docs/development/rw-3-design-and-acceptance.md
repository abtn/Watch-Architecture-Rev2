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
5. The existing RW-2 commit service validates and commits the accepted proposal set.
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
- Team Experience only when the existing authorized retrieval path can supply it with canonical identity, Team eligibility, freshness, and provenance checks. RW-3 must not build a new retrieval subsystem to obtain it.

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

The exact selection algorithm and maximum proposal count remain RW3-0 decisions. The following existing provider limits are fixed for RW-3 and are not open for expansion:

- Retrieval-derived passages: at most 8 passages and 8,000 Unicode characters.
- Model: the ADR-0031-selected Cloudflare Workers AI Llama 3.1 8B Instruct FP8 model only.
- Total quoted input plus configured output: at most the model's 32,000-token context window, using the existing conservative UTF-8-byte-length-plus-128 framing-token quote.
- Output: at most the existing configured output-token ceiling of 1,024; a lower configured value is valid, a higher value is not.
- One synchronous, non-streaming provider request per invocation; no tools and no adapter-level retry. TaskRuntime owns retry behavior.

RW3-0 must still specify deterministic selection within these limits, decide whether Team Experience is eligible, and set a maximum proposal count compatible with the response cap. Do not add a separate serialized-output byte limit without a measured need.

## 4. Generation, parsing, and commit sequence

### Existing provider limits carried into RW-3

RW-3 retains the provider and request limits already accepted by ADR-0031 and implemented in `core/generation.py`:

- Provider/model remain `cloudflare_workers_ai` and `@cf/meta/llama-3.1-8b-instruct-fp8`. A different provider or model requires a separate decision; the 32,000-token advertised context window does not authorize expanding Watch's own Context budget.
- Any retrieval-derived passage set remains limited to **8 passages and 8,000 Unicode characters**. Apply these limits unchanged; do not enlarge them because the model advertises a 32,000-token context window.
- The provider's conservative input quote remains UTF-8 byte lengths of the exact system and user prompts plus 128 framing tokens. Quoted input plus output must fit within 32,000 tokens.
- The configured output-token limit may be lower, but cannot exceed the existing **1,024-token** ceiling (`DEFAULT_MAX_OUTPUT_TOKENS`). Do not raise this ceiling for RW-3. The Task's existing cost budget and cost reservation remain independently binding.
- The adapter remains synchronous, non-streaming, one HTTP request per invocation, with no tools and no internal retries. It requires valid prompt/completion usage and an exact response-model match; retry eligibility remains TaskRuntime-owned.
- The output is one final JSON object validated locally. Do not rely on provider JSON Mode or expose/persist reasoning traces.

These are inherited constraints, not new RW-3 provider authorization. RW3-0 still must choose deterministic Context selection and the maximum number of proposals that can fit the bounded response. Do not invent a second character limit for serialized output: the configured token cap is the existing hard output bound unless a separate measured need justifies a tighter application-level bound.

**Generation-cost integration:** the current `TaskGenerationCostService` does not authorize `update_thread`. RW-3 therefore requires a narrow extension to that existing service, not a new accounting subsystem: add one distinct operation identifier for `update_thread`, bind it to Task type `update_thread` and the exact ordered `allowed_writes` scope `[EvidenceLink, Hypothesis, ConfidenceChange]`, and add operation-specific quote/provider/model/rate-card/output-bound validation and tests. Preserve Task/attempt attribution, one reservation per operation per attempt, cumulative Task budget enforcement, and known/unknown/overrun reconciliation. The implementation must use only a provider/model/rate card already authorized by ADR-0031 or stop for a separate decision; do not silently broaden provider authorization. Reconciliation and current-attempt charge validation occur before the RW-2 commit service is called.

1. Validate the immutable Task request and its trusted Team/Thread target using read-only checks. Do not assemble attempt-specific Context before admission.
2. Admit/claim the Task attempt through TaskRuntime. This establishes the attempt that owns all subsequent Context, generation, and cost records.
3. Assemble and validate the bounded Context for that admitted attempt. If this fails, record failure through TaskRuntime; do not reserve cost or call the provider.
4. Reserve the maximum permitted generation cost for the exact Task attempt through the existing cost-accounting service.
5. Call the configured existing generation provider only after reservation succeeds.
6. Parse the response against a strict typed schema. Reject malformed JSON, unknown fields, unsupported proposal types, excessive output, and invalid references; do not coerce or repair them.
7. Reconcile provider usage/cost and validate the exact current-attempt charge before any business commit. A missing, unknown, unreconciled, or overrun charge cannot authorize business writes; retain the applicable reservation/unknown-cost accounting and fail the Task through TaskRuntime.
8. Submit the typed proposals to the same commit service used by `operator_update`. The commit service remains the only business-write boundary.
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

An empty/no-op model response is not yet specified. RW3-0 must decide whether it is a valid no-op terminal result or a rejected/failed attempt, and align the decision with the Task contract and Outcome semantics before implementation.

## 6. Failure behavior

| Condition | Required behavior |
|---|---|
| Invalid Task, target, or policy | Reject before provider execution; no business writes. |
| Invalid/stale/cross-scope Context | Fail closed; no provider call and no business writes. |
| Cost reservation denied | No provider call. |
| Provider timeout/transport failure | Existing bounded TaskRuntime failure/retry behavior; no business commit. |
| Malformed or oversized output | No business commit; record the permitted Task failure/rejection evidence. |
| Invalid individual proposal | Rejection Event; exclude it from the accepted set. |
| All proposals invalid | Task fails; no business writes. |
| Mixed valid/invalid proposals | Commit valid set atomically; preserve invalid-proposal rejection Events. |
| Accepted-set transaction failure | Roll back the entire accepted set; TaskRuntime handles failure/recovery. |
| Unknown provider usage/cost | Use existing unknown-cost accounting; never assume zero. |
| Replay or concurrent attempt | Existing TaskRuntime and commit-service idempotency/concurrency rules; no duplicate writes. |

The precise distinction between parser-level invalid output and proposal-level rejection Events must be finalized in RW3-0 against existing Event conventions. Do not create a second rejection protocol.

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
- [ ] Team Experience is either excluded or supplied only by an existing authorized, provenance-preserving retrieval path.

### Model and provider boundary

- [ ] Existing generation provider and cost-accounting services are reused.
- [ ] TaskRuntime admission establishes the attempt before attempt-specific Context assembly.
- [ ] The existing cost service has a distinct `update_thread` operation mapped to Task type `update_thread` and exactly `[EvidenceLink, Hypothesis, ConfidenceChange]`; provider/model/rate-card and output bounds are validated by that operation.
- [ ] Reservation succeeds before provider invocation.
- [ ] The exact current-attempt charge is reconciled and validated before the shared commit service can write business state; unknown, unreconciled, and overrun charges cannot authorize writes.
- [ ] Output uses a strict typed schema; unknown fields/types and invalid references are rejected.
- [ ] Retrieval-derived Context remains within 8 passages and 8,000 Unicode characters; quoted input plus configured output fits the 32,000-token model context; output is capped at the existing configured maximum of 1,024 tokens.
- [ ] Maximum proposal count is explicitly set in RW3-0 and tested against the output cap; no separate serialized-output byte limit is introduced without measured justification.
- [ ] Model output cannot alter Task/Team/Thread identity, policy, budget, allowed writes, or attribution.
- [ ] No automatic semantic repair/re-proposal loop or unapproved provider retry exists.
- [ ] Usage and cost reconcile under existing known/unknown-cost rules.

### Commit and lifecycle

- [ ] The same RW-2 commit service and validation rules are used.
- [ ] Business `allowed_writes` are exactly EvidenceLink, Hypothesis, and ConfidenceChange.
- [ ] Every RW-2 evidence, confidence, transition, ownership, replay, and concurrency proof remains passing for the model entry path.
- [ ] Valid proposals commit as one atomic accepted set; invalid proposals produce attributable rejection Events.
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

## 8. RW3-0 design locks — must resolve before implementation authorization

1. **Context selection:** define deterministic selection and per-entity bounds within the fixed retrieval ceiling of 8 passages/8,000 Unicode characters and the provider's 32,000-token total context window. The UTF-8-byte-length-plus-128 input quote is already defined by ADR-0031.
2. **Team Experience:** verify whether the existing retrieval path can be reused with the required canonical and authorization checks. Otherwise exclude it from RW-3.
3. **Worker invocation:** identify the narrowest existing application composition point. Do not broaden TaskDispatcher into a general framework.
4. **Proposal count:** set and justify the maximum number of proposals that can be returned within the existing configured output ceiling of 1,024 tokens. The output ceiling itself is fixed; do not raise it or add an arbitrary byte cap.
5. **Empty/no-op result:** define terminal semantics and corresponding Task/Outcome/Event proof.
6. **Failure/rejection recording:** align parser-level failures and proposal-level rejection Events with existing TaskRuntime/Event conventions.

RW3-0 is source/design reconciliation only. If it discovers a required schema change, migration, new provider behavior, or changed accepted Task semantics, stop and present the smallest separate decision. No implementation or schema migration is implied.

## 9. Implementation sequence

| Slice | Work | Exit gate |
|---|---|---|
| RW3-0 — design lock | Audit current Task, Context, provider, cost, TaskRuntime, and RW-2 commit contracts; resolve the remaining design locks above; reconcile docs. | Design is internally consistent, all design locks are resolved, and the design is reviewed and ready to present for a separate implementation-authorization decision. RW3-0 completion does not authorize implementation. |
| RW3-1 — bounded Context | Implement deterministic Thread-scoped Context assembly, source/Snapshot validation, bounds, and provenance manifest. | Positive/negative Context tests prove scope, freshness, integrity, determinism, and bounds. |
| RW3-2 — model worker | Implement strict output parsing and narrow worker orchestration using the existing provider and cost boundary. | Fake-provider tests prove provider ordering, schema rejection, bounds, and no authority escalation. |
| RW3-3 — shared commit/lifecycle | Connect proposals to the RW-2 commit service and TaskRuntime; prove mixed/all-invalid batches, atomicity, replay, concurrency, failure, and recovery. | Complete RW-3 proof matrix passes; no alternate runtime or write path. |
| RW3-4 — verification/closeout | Run exact-head local and hosted verification, review diff/docs, record results and explicit acceptance. | Exact tested SHA, all required checks, cleanup evidence, and Operator acceptance recorded. |

Each slice requires its own review/authorization as appropriate. Passing a prior slice does not automatically authorize the next. RW-3 completion does not authorize RW-4, RW-5, R7-C, persistent-database operations, or scored newsroom runs.
