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

The exact selection algorithm, bounds, and whether Team Experience is eligible are RW3-0 decisions. Do not invent numeric limits before inspecting existing Task budgets, Context limits, and provider constraints.

## 4. Generation, parsing, and commit sequence

1. Validate the Task type, status, immutable request, target Team/Thread, and policy.
2. Assemble and validate the bounded Context. If this fails, do not call the provider.
3. Admit/claim the attempt through the existing TaskRuntime path.
4. Reserve the maximum permitted generation cost through the existing cost-accounting service.
5. Call the configured existing generation provider only after reservation succeeds.
6. Parse the response against a strict typed schema. Reject malformed JSON, unknown fields, unsupported proposal types, excessive output, and invalid references; do not coerce or repair them.
7. Submit typed proposals to the same commit service used by `operator_update`.
8. Reconcile provider usage/cost, including unknown usage according to existing accounting rules.
9. Finalize or recover through TaskRuntime.

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
- [ ] Reservation succeeds before provider invocation.
- [ ] Output uses a strict typed schema; unknown fields/types and invalid references are rejected.
- [ ] Proposal count and serialized output are bounded by explicit RW3-0 decisions.
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

- [ ] Deterministic fake-provider tests prove the complete positive and negative paths.
- [ ] PostgreSQL tests prove atomicity, ownership, replay, and concurrency where required.
- [ ] A live provider smoke test, if requested later, is separate and does not replace deterministic proofs or become a CI dependency.
- [ ] Ruff, Mypy, focused tests, full suite, disposable PostgreSQL migration/single-head checks, and patch-whitespace checks pass on the exact tested commit.
- [ ] No persistent database is used for verification.
- [ ] Documentation, Task contract, implementation, and proof matrix agree.

## 8. RW3-0 design locks — must resolve before implementation authorization

1. **Context selection and limits:** inspect current Task budget, Context assembly limits, provider request/response constraints, and source volume; then specify deterministic selection and hard bounds.
2. **Team Experience:** verify whether the existing retrieval path can be reused with the required canonical and authorization checks. Otherwise exclude it from RW-3.
3. **Worker invocation:** identify the narrowest existing application composition point. Do not broaden TaskDispatcher into a general framework.
4. **Proposal/output bounds:** set maximum proposal count and serialized response size from existing contracts and provider constraints.
5. **Empty/no-op result:** define terminal semantics and corresponding Task/Outcome/Event proof.
6. **Failure/rejection recording:** align parser-level failures and proposal-level rejection Events with existing TaskRuntime/Event conventions.

RW3-0 is source/design reconciliation only. If it discovers a required schema change, migration, new provider behavior, or changed accepted Task semantics, stop and present the smallest separate decision. No implementation or schema migration is implied.

## 9. Implementation sequence

| Slice | Work | Exit gate |
|---|---|---|
| RW3-0 — design lock | Audit current Task, Context, provider, cost, TaskRuntime, and RW-2 commit contracts; resolve the six design locks above; reconcile docs. | Explicitly approved design and implementation authorization. |
| RW3-1 — bounded Context | Implement deterministic Thread-scoped Context assembly, source/Snapshot validation, bounds, and provenance manifest. | Positive/negative Context tests prove scope, freshness, integrity, determinism, and bounds. |
| RW3-2 — model worker | Implement strict output parsing and narrow worker orchestration using the existing provider and cost boundary. | Fake-provider tests prove provider ordering, schema rejection, bounds, and no authority escalation. |
| RW3-3 — shared commit/lifecycle | Connect proposals to the RW-2 commit service and TaskRuntime; prove mixed/all-invalid batches, atomicity, replay, concurrency, failure, and recovery. | Complete RW-3 proof matrix passes; no alternate runtime or write path. |
| RW3-4 — verification/closeout | Run exact-head local and hosted verification, review diff/docs, record results and explicit acceptance. | Exact tested SHA, all required checks, cleanup evidence, and Operator acceptance recorded. |

Each slice requires its own review/authorization as appropriate. Passing a prior slice does not automatically authorize the next. RW-3 completion does not authorize RW-4, RW-5, R7-C, persistent-database operations, or scored newsroom runs.
