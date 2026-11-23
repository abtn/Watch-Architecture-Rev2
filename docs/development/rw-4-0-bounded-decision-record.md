# RW4-0 — Bounded triage decision record

**Status:** Operator review requested; proposals below are not accepted decisions.
**Scope:** First, narrow `triage_signal` slice only. No implementation is authorized by this record.
**Baseline:** main after PR #173, merge commit `126063199c919a9576e20f4909781f0776d1ca87` (2026-11-23).
**Authority:** `PLAN.md` remains authoritative for milestone status and implementation authorization. Existing accepted ADRs, Task contracts, and write-scope matrix remain binding unless explicitly amended.

## 1. Purpose and non-goal

Define the smallest safe first slice that can record one Team's disposition of one canonical Signal. This record narrows the decision surface; it does not attempt to freeze world-memory retrieval, claim-level knowledge attribution, or a general matching platform.

The intended first-slice boundary is:

`trusted host request → immutable triage_signal Task → deterministic application decision → atomic SignalDisposition / permitted Thread change / Event`

The model is not involved in triage. Triage does not create or enqueue `update_thread` Tasks.

## 2. Proposed decisions for Operator review

Each item is a proposal, not an accepted project decision.

### D1 — Explicit, host-authorized invocation

**Proposal:** A trusted host explicitly requests triage for one Signal and one Team through a narrow in-repository application adapter.

- The host authenticates the principal and authorizes that principal for the selected Team before invoking the adapter.
- The adapter receives authenticated host identity/authorization context; it must not trust a Team identifier supplied only by an untrusted caller.
- The adapter validates that the Signal and Team exist and that the Signal is eligible for that Team/domain.
- No automatic `ingest_source → triage_signal` creation, periodic scheduler, queue expansion, or general-purpose Task creator is included.
- The existing TaskRuntime remains the sole Task lifecycle authority. The current TaskDispatcher remains unchanged.

**Reason:** ingestion and Team-specific triage are separate responsibilities. One Signal can have different dispositions for different Teams. An explicit request avoids silently expanding ingestion authority or introducing a second scheduler.

### D2 — One immutable request per Signal/Team pair

**Proposal:** The first release has one canonical triage identity per `(signal_id, team_id)`.

- The immutable Task request binds exactly those canonical identifiers and the approved matching-policy version/identity once that policy is defined.
- A database uniqueness constraint enforces one canonical SignalDisposition per Signal/Team pair.
- Repeating the same request resolves to the existing canonical result; it must not create another disposition, Thread, or business Event.
- A conflicting request for an already-disposed pair fails without mutation. There is no implicit re-triage or overwrite.
- All Task lifecycle writes remain TaskRuntime-owned; business writes go through the existing Kernel commit boundary.

**Reason:** the pair is already the documented disposition scope. Making it the identity avoids inventing a separate idempotency registry for this narrow operation.

### D3 — Deferred is terminal in the first release

**Proposal:** `deferred` is a durable terminal disposition for the first RW-4 release.

- No `update_thread` or `operator_update` write permission is added or retained for SignalDisposition refinement in this first slice.
- Reconsideration, if later justified, requires a separately reviewed operation with explicit actor, authorization, attribution, transition, and replay semantics.
- Do not implement mutable disposition history or a generic disposition state machine now.

**Reason:** the existing architecture text describes deferred refinement, but the accepted RW-2/RW-3 commit path does not implement SignalDisposition writes and RW-3 explicitly excludes them. A terminal first-release state preserves the accepted RW-3 boundary and avoids quietly widening existing Task authority.

**Required reconciliation if accepted:** update the SignalDisposition lifecycle description and Task/write-scope matrix consistently before schema implementation. Do not treat this proposal as already changing those contracts.

### D4 — Keep triage deterministic and avoid speculative projections

**Proposal:** The first release uses deterministic application rules only. It does not call a model and does not introduce Thread embeddings, a new Domain ORM/configuration subsystem, or a general-purpose domain-pack framework.

- Reuse existing canonical Signal, Thread, Team, and immutable Snapshot records.
- Signal KnowledgeChunk embeddings are candidate evidence only; they are not automatically authoritative Thread-matching inputs. Their source identity, chunk-to-Signal mapping, model identity, and rebuild behavior must be verified before any use.
- Do not create Thread embeddings solely to satisfy the older target description.
- Do not overload TeamPolicy with matching/dedup configuration.
- Missing, incompatible, or ambiguous matching inputs fail closed to the approved non-match/deferred path; they never authorize a new Thread.

**Open gate:** the actual deterministic candidate/matching rule is not frozen here. Before RW4-0 closes, a concrete newsroom fixture and source audit must demonstrate a minimal rule for (a) duplicate Signal detection, (b) matching an existing Thread, and (c) the separate strong-match condition for creating a new Thread. The rule must specify scope, version/identity, thresholds if any, tie-breaking, and stable ordering. If the existing canonical data cannot support that rule without a new projection/configuration contract, stop and bring that smallest required addition back for review.

**Reason:** current source inspection found no Thread embedding and no implemented Domain `match_heuristics`/`dedup_policy` configuration. Choosing a vector architecture before proving it necessary would turn missing implementation into speculative infrastructure.

### D5 — Limit first-release dispositions and side effects

**Proposal:** Preserve the documented disposition vocabulary, with these first-release effects:

| Disposition | Required effect |
|---|---|
| `matched` | Reference one deterministically selected existing same-Team/domain Thread. |
| `new_thread` | Create one Thread only when the separately frozen strong-match condition passes. |
| `noise` | Record the Team-specific disposition; no Thread mutation. |
| `duplicate` | Record the Team-specific disposition and a validated same-scope canonical duplicate Signal reference; no Thread mutation. |
| `deferred` | Record an explicit reason; no Thread mutation and no later refinement in this release. |

- A disposition is attributed to the creating Task and has a durable reason.
- References are validated at commit for Team/domain scope and canonical existence.
- The disposition, any permitted Thread creation/reactivation, and the required business Event commit atomically.
- No other entity writes, follow-up Tasks, Hypothesis/EvidenceLink changes, or Team Experience changes are included.

**Reason:** this is the smallest explicit write boundary around the already documented triage purpose.

### D6 — Reactivation is a matched-only atomic transition

**Proposal:** Only a committed `matched` disposition to the deterministically selected dormant Thread may reactivate it, by the transition `dormant → active`.

- Revalidate the Thread's Team/domain and current lifecycle state inside the business commit.
- `new_thread`, `noise`, `duplicate`, and `deferred` do not reactivate a Thread.
- Record the transition in the Task-attributed Event committed with the disposition.
- Define concurrency and replay so two matching requests cannot produce contradictory or duplicate lifecycle effects.

**Open gate:** timestamp semantics (including which field, if any, resets the decay clock) must be agreed with RW-5 before implementation. This record does not authorize changing `last_updated_at`, `last_touched_at`, or any decay basis by assumption.

**Reason:** reactivation must not accidentally bypass or conflict with the independently implementable RW-5 decay contract.

## 3. Explicitly outside this bounded record

The following are not part of this first triage slice and are not authorized here:

- Automatic triage after ingestion, scheduler/dispatcher expansion, or a general-purpose Task creator.
- Deferred disposition refinement or re-triage.
- Model-based triage, live provider calls, or model-generated Thread titles.
- Thread embedding/summary projections, a new Domain subsystem, or generic domain-pack machinery without a demonstrated requirement.
- Hypothesis/EvidenceLink updates, `update_thread` Task creation, or Operator world-memory updates.
- World-memory Context retrieval and model-facing evidence representation (RW4-4).
- RW4-KU claim-level attribution; it remains separately gated.
- RW-5 implementation, though the reactivation/decay contract must be reconciled.
- Persistent database access, scored newsroom execution, R7-C, or R8.

## 4. Required reconciliation before RW4-0 can close

If the Operator accepts the proposals, the following documentation work must be completed before implementation authorization:

1. Reconcile the `triage_signal` Task definition and Task/write-scope matrix with terminal deferred semantics and the exact writes in D5/D6.
2. Define the trusted host-to-adapter identity and Team-authorization boundary without claiming a production host-auth system already exists.
3. Freeze the deterministic matching rule from a concrete fixture and source audit, or explicitly narrow the first implementation to a smaller supported matching scenario.
4. Specify the disposition fields/constraints, valid reference combinations, uniqueness, Task attribution, Event identity, and commit/replay behavior.
5. Agree with RW-5 on reactivation timestamps and concurrency semantics.
6. Produce a requirement-to-test matrix for every disposition, cross-Team/domain rejection, idempotency/conflict, atomic rollback, concurrent requests, Task recovery, and reactivation/decay interaction.
7. Record unresolved items as explicit blockers; do not silently convert proposals into accepted decisions.

## 5. Existing gates remain in force

- RW3.4 formal acceptance remains deferred. Before RW-4 implementation begins, the Operator must either complete its bounded acceptance work and formally accept it, or explicitly authorize a sequencing exception while retaining the deferred disposition.
- Experiment A informs RW4-4 representation only. It does not block RW4-0 through RW4-3 or independent RW-5 work.
- RW-5 design, implementation, and unit-level decay proofs remain independently implementable; integrated RW-4/RW-5 proof must verify reactivation and retrieval against post-decay state.
- R8 remains unscheduled.
- This record is a documentation proposal only. It authorizes no code, schema, migration, test-only follow-up, dispatcher change, provider execution, persistent-database operation, or scored experiment.

## 6. Operator response required

Review D1–D6 individually. Acceptance of this record should mean acceptance of the proposed first-slice boundaries, not automatic closure of every open gate in §4. In particular, D4's concrete matching rule and D6's decay timestamp semantics remain unresolved until supported by evidence and explicitly frozen.

No implementation stage begins until the reconciled RW4-0 decision record, requirement-to-test matrix, and sequencing gate have been independently reviewed and explicitly authorized.
