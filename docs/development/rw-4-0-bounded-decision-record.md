# RW4-0 — Bounded triage decision record

**Status:** D1/all six D2, D3-A/B/C, and D4.1/D4.1a/D4.2/D4.3 are accepted. D4 evidence/design closure remains open; D5 and D6 remain separate Operator decisions. No implementation is authorized by this record.

> **Current reconciliation (2026-11-25):** D4.1/D4.1a/D4.2/D4.3 are accepted. Exact raw-hash duplicate scope is same-Team regardless of origin, with the first committed Team/hash Signal canonical; the narrow existing-Thread matcher shape is accepted but maximum-pairwise similarity remains experimental and its numeric parameters/query-cost evidence are open; automatic Thread creation is disabled in v1. D5's disposition/reference matrix and D6 reactivation remain open. Follow the [RW-4 Readiness and Delivery Plan](rw-4-readiness-and-delivery-plan.md) for consolidated gates.
## RW4-2 D2 Operator decision — canonical Task identity (2026-11-24)

**ACCEPTED:** use UUIDv5 directly as `Task.id` for `triage_signal`, with identity version `triage_identity_v1`. Frozen namespace: `383bbdde-37be-4895-8fb7-1afa196b5cf7`. Exact canonical name: `triage_identity_v1|triage_signal|team:<team-uuid>|signal:<signal-uuid>`, using lowercase canonical UUID text and no whitespace. Accepted golden vector: Team `00000000-0000-4000-8000-000000000001`, Signal `00000000-0000-4000-8000-000000000002`, expected Task ID `5b45ed53-a50f-51e8-ba81-ce52512aa922`.

This is separate from the already accepted Task-schema requirement to persist `signal_id` and `identity_version` and enforce unique `(team_id, signal_id, identity_version)`. All six D2 decisions are design decisions only; no migration or creator implementation is authorized. Decisions 3–6 were accepted on 2026-11-24 and are summarized below.

**Scope:** First, narrow `triage_signal` slice only. D1/all D2, D3-A/B/C, and D4.1/D4.1a/D4.2/D4.3 are accepted; D4 evidence closure, D5 disposition/reference decisions, and D6 reactivation remain separate gates. No implementation is authorized by this record.
**Current reconciliation baseline:** main after PR #187 squash merge `94563be9e551ebf73faee626d952e9b839b57946` (2026-11-25). PR #184 is the earlier D1/D2 proposal baseline; historical proposal origins remain PRs #174 and #176. D3 decisions are recorded in [issue #189](https://github.com/abtn/Watch-Architecture-Rev2/issues/189).
**Authority:** `PLAN.md` remains authoritative for milestone status and implementation authorization. Existing accepted ADRs, Task contracts, and write-scope matrix remain binding unless explicitly amended.

## 1. Purpose and non-goal

Define the smallest safe first slice that can record one Team's disposition of one canonical Signal. This record narrows the decision surface; it does not attempt to freeze world-memory retrieval, claim-level knowledge attribution, or a general matching platform.

The intended first-slice boundary is:

`trusted host request → immutable triage_signal Task → deterministic application decision → atomic SignalDisposition / permitted Thread change / Event`

The model is not involved in triage. Triage does not create or enqueue `update_thread` Tasks.

## 2. Accepted D1/D2/D3/D4 decisions and remaining D5/D6 proposals

D1 and all six D2 decisions are accepted as recorded below. D3-A/B/C and D4.1/D4.1a/D4.2/D4.3 are accepted on 2026-11-25 and reconciled in §7. D4's policy shape is closed, but its canonical Team/hash persistence design and measured matcher evidence remain engineering gates. D5 and D6 require separate Operator decisions.

### D1 — Control Room is the single Task-creation authority

**ACCEPTED — 2026-11-24**

**Operator decision:** The application Control Room is the single authority allowed to create and persist Tasks. Control Room is the logical application boundary/owner in this decision; this wording does not claim that a dedicated Control Room module or service already exists in the repository. Every host-facing adapter or feature-specific entrypoint must delegate Task creation to a named Control Room operation. Workers, models, ingestion code, and feature modules must not create Tasks directly or introduce parallel Task factories. Existing supported Task-creation paths are to be represented as Control Room operations; this decision does not itself authorize refactoring existing RW-3 code.

The accepted `triage_signal` operation has these boundaries:

- The host authenticates the requester and supplies a typed principal identity plus an invocation-scoped grant for exactly one Team and the `triage_signal` action. The request payload cannot choose or override Team, requester, role, Task ID, or authority.
- Only a Team whose persisted state is exactly `active` may create or replay a triage Task.
- Production host authentication integration is a required prerequisite scheduled after the R8 test. It must be complete before production use. The current repository still has no production host composition/authentication root; this decision does not claim end-to-end authentication is implemented. The in-process principal remains forgeable by code inside the process.
- URL normalization is deferred until after the R8 test. Until then, persisted `origin_url` and `source_type` values are compared exactly. The future minimal foundation should make DNS hostname case insignificant (for example, `Google.com` and `google.com` compare as the same host), while preserving scheme, port, path, query, fragment, and trailing-slash distinctions. `source_type` remains exact. This future rule is not current behavior and is not implementation-authorized.
- The greatest immutable `TeamPolicy.version` is current, resolved under the canonical Team lock. Missing, malformed, or unsupported greatest-version policy/source data fails closed; there is no fallback to an older version.
- RW4-3 must revalidate Team eligibility, domain/source scope, and policy under the accepted RW-5 lock chain immediately before matching/commit.
- TaskRuntime remains the sole authority for Task admission, attempts, retry, interruption, recovery, and finalization. The Control Room creates/resolves the Task; it does not execute or finalize it.

**Reason:** Task creation is an application control-plane responsibility, not a capability distributed across workers or domain features. A single Control Room authority makes authorization, identity, audit, and idempotency enforceable at one boundary.

**Implementation boundary:** This is a design decision only. It does not authorize a Control Room refactor, a new creator implementation, host-authentication integration, URL normalization, TaskDispatcher changes, or any production code/schema/migration work. RW4-2 Stage B remains separately gated.

### D2 — One canonical Task and disposition per Signal/Team pair

**Accepted D2 identity/replay contract; adjacent disposition scope remains separate:** the first release has one canonical triage operation per `(signal_id, team_id)`, represented by one immutable `triage_signal` Task. D3 lifecycle semantics are accepted; SignalDisposition persistence/uniqueness remain assigned to RW4-1, and the complete allowed disposition vocabulary/reference matrix remains D5.

Keep these identities distinct:

1. **Business identity:** the canonical pair `(signal_id, team_id)`; this scopes the single first-release disposition.
2. **Task identity:** one deterministic canonical UUIDv5 derived from canonical Team, Signal, `triage_signal`, and fixed identity version `triage_identity_v1` under a dedicated RW4 namespace. The accepted contract uses that UUID directly as `Task.id`, so the Task primary key enforces uniqueness for that canonical UUID. Separately, the accepted v1 guarantee persists `signal_id` and `identity_version` on triage Tasks and enforces a database unique constraint on `(team_id, signal_id, identity_version)`. The primary key alone does not enforce logical-pair uniqueness against a writer that supplies a different UUID.
3. **Request provenance:** one immutable, Task-attributed request Event binds the first authorized requester, canonical Team and Signal IDs, canonical Signal Snapshot reference/hash, pinned TeamPolicy version, matcher identifier/version, embedding-space key, chunking version, and a canonical request fingerprint. The requester is provenance, not part of semantic request equivalence. A later authorized caller with the same canonical request resolves the existing Task without replacing the original requester attribution. A different policy pin or other immutable request content conflicts.
4. **Execution replay:** TaskRuntime owns attempts and lifecycle. Kernel business commit uses the canonical Task identity/Event evidence to recognize a prior disposition/Thread/Event commit and never repeats those writes.

Request behavior:

- The first authorized request creates the canonical Task and its request Event atomically.
- **The accepted v1 guarantee requires both canonical-UUID and logical-pair uniqueness.** Use the canonical UUIDv5 as `Task.id`; the primary-key constraint arbitrates concurrent inserts of that exact canonical UUID. In addition, persist `signal_id` and `identity_version` on triage Tasks and enforce a database unique constraint on `(team_id, signal_id, identity_version)`, with validation requiring these identity fields for `task_type = 'triage_signal'` and preventing callers from supplying or overriding them. The current audited Task schema has neither the required identity columns nor the pair-level constraint, so this guarantee requires a Task-schema migration. A narrow single-creator application invariant and source-audit/tests remain required controls, but are not equivalent to the database constraint and are not an alternative to it. The Operator accepted the migration cost on 2026-11-24. The exact migration/preflight/backfill and writer-compatibility design still requires review and separate implementation authorization. Do not claim that the primary key alone enforces arbitrary logical-pair uniqueness.
- Task insertion and its immutable request Event are one transaction. The Event schema currently has no unique request-event-per-Task constraint. The Operator accepted a PostgreSQL partial unique index on `(task_id)` for the `triage_signal_requested` Event type, plus atomic Task/Event creation and replay validation. The index enforces at-most-one; atomic creation establishes existence, and replay validation verifies exactly one well-formed, consistent Event. Duplicate-history preflight and PostgreSQL proof remain required.
- On a Task uniqueness conflict, the losing request must restart through the canonical existing-Task lock path (Task `FOR UPDATE` → Team `FOR NO KEY UPDATE`) and validate the winning Task and request Event. It must not acquire Task after Team or create another request Event.
- **Accepted D2 #4 (2026-11-24):** each caller is independently authorized before creation or replay; unauthorized callers learn nothing about Task existence. A later authorized caller with the same canonical pair and immutable pins resolves the canonical Task; the original request Event retains the first requester's provenance, and requester identity is excluded from semantic equivalence. Changed policy/matcher/embedding/chunking pins conflict. A terminally failed or superseded v1 Task continues to occupy its identity. Any future `triage_identity_v2` requires separate Operator approval and a documented transition.
- A unique constraint separately enforces one canonical SignalDisposition per Signal/Team pair. Task uniqueness and request Event/fingerprint validation are distinct protections; disposition uniqueness alone is not Task idempotency.
- The immutable Task request binds the canonical identifiers, Signal Snapshot reference/hash, TeamPolicy version, matcher identifier/version, embedding-space key, and chunking version. **Accepted D2 #6 (2026-11-24):** all four matching pins are code-owned and immutable for v1; actual values are decided in D4b, and TeamPolicy remains unchanged. The request fingerprint covers semantic pins but excludes requester provenance and first-writer `as_of`/Team revision metadata. Those watermark values are stored immutably in the request Event, validated and returned unchanged on replay. Time or Team revision advancement alone does not create a conflict; RW4-3 still revalidates current state before execution. If any required pin or matching policy is not yet defined, Task creation is not implementation-ready.
- All Task lifecycle writes remain TaskRuntime-owned; business writes go through the existing Kernel commit boundary.

**Reason:** the pair is the documented disposition scope, but a disposition constraint cannot prevent duplicate Task creation. The first release needs a canonical Task identity and immutable request/replay contract as well as business-row uniqueness. The Operator accepted the Task-schema migration and composite `(team_id, signal_id, identity_version)` constraint on 2026-11-24. The Operator separately accepted the canonical UUIDv5 namespace, name template, identity version, and golden vector on 2026-11-24. **Accepted D2 #3–#5 (2026-11-24):** require the partial unique request-Event index plus atomic creation/replay validation; preserve same-pin replay and original requester provenance with v1 identity occupancy after terminal failure/supersession and separately approved v2; preserve first-writer watermarks as immutable Event metadata excluded from semantic replay equivalence.

**Implementation note:** the existing `update_thread` host-invoked creator is a relevant precedent for deterministic Task identity, conflict-safe insertion, immutable request Event, fingerprint validation, and replay. Reuse its proven pattern where applicable, but use a distinct identity namespace and triage-specific fingerprint. Do not copy its Thread-specific key scope or change its contract.

### D3 — Deferred lifecycle, Task terminality, and integrity — ACCEPTED 2026-11-25

D3-A/B/C are accepted. Signal has no lifecycle/status column; eligibility derives from canonical Signal/Snapshot integrity and provenance plus active-Team, caller-authorization, and source/domain/policy checks. An existing Team/Signal disposition excludes another v1 decision. An authorized replay may return the canonical D2 Task's recorded result without re-execution or mutation. If the disposition exists but the canonical Task or exactly-one valid request Event is missing or inconsistent, fail closed; do not synthesize history, create a replacement, or mutate the disposition.

TaskRuntime remains the sole lifecycle authority. `pending` and `running` follow normal admission/attempt/recovery rules; `done` and `failed` are terminal and occupy the v1 identity. A stale-pin queued Task must be terminally superseded through the existing TaskRuntime terminal non-success path as status `failed`, result category `terminal_failure`, and stable reason `matching_pins_superseded`; this is not a technical execution fault and adds no Task status or result category. RW4-3 must prove this behavior before enabling triage execution.

A valid `deferred` business disposition is immutable/terminal in v1 and its Task completes successfully as `done`. The disposition row, Task attribution/reason, TaskRuntime `task_execution` Outcome, terminal Task status, and `task_completed` Event must commit or roll back together in one TaskRuntime-owned database transaction. The Kernel persistence operation uses the active Session and cannot open/commit a separate transaction. Technical failures remain distinct and follow TaskRuntime retry/recovery; no `update_thread`, `operator_update`, or background refinement may change the disposition. D5 still owns the complete disposition vocabulary/reference matrix; D6 alone may authorize dormant-Thread reactivation. D3 acceptance authorizes no code/schema/migration.

### D4 — Duplicate identity, existing-Thread matching, and no automatic Thread creation

**Decision status: D4.1, D4.1a, D4.2, and D4.3 ACCEPTED by the Operator on 2026-11-25.** The decision rules below are accepted; evidence-backed implementation parameters and persistence design remain open.

1. **D4.1 — Duplicate Signal detection (Option A):** exact raw content-hash equality within the same Team's intake history, regardless of origin. Cross-Team equality is not a duplicate. Near-duplicate, syndicated-copy, and semantic duplicate detection are excluded. Duplicate detection identifies a canonical Signal and does not select or mutate a Thread.
2. **D4.1a — Canonical duplicate winner:** the first Signal successfully committed into the Team's intake history for that exact content hash wins. PostgreSQL must arbitrate concurrent first arrivals and the Team/hash association must remain stable. Do not select by fetched_at, application timestamps, UUID order, or origin. This is a decision, not an implemented persistence mechanism: Signal is not Team-owned and Team association is represented by ingestion Events; current origin_url + content_hash ingestion uniqueness does not provide cross-origin Team/hash canonicalization. RW4-3 requires a separately reviewed persistence design and real two-session PostgreSQL proof.
3. **D4.2 — Existing-Thread matching (Option A shape):** derive evidence profiles at read time through Team-scoped EvidenceLink → Hypothesis → Thread; consider same-Team/same-Domain active or dormant Threads and exclude resolved; only supports/challenges EvidenceLinks count (mentions alone is insufficient); validate same-Team ingestion provenance and exact Signal/Snapshot/hash and EvidenceLink Snapshot/hash associations; use only compatible existing KnowledgeChunk projections under the immutable embedding/chunking pins. No Thread embeddings, model calls, re-embedding, summary/alias subsystem, or recency bonus. Maximum pairwise chunk cosine similarity remains an experimental baseline subject to outlier/profile-size bias. Minimum threshold and runner-up margin, score serialization, candidate/evidence bounds, actual pins, fixture performance and PostgreSQL query cost remain open and must be measured. Ambiguity, ties, insufficient evidence, corruption, incompatibility, or overflow defers; no incidental UUID/order tie-break. A dormant candidate is not reactivated; until D6 and separate authorization, a dormant would-be match resolves to terminal deferred rather than a matched result implying reactivation.
4. **D4.3 — New Thread eligibility (Option A):** automatic Thread creation is disabled in v1. No qualifying existing match, ambiguous/insufficient evidence, or a dormant candidate blocked by the no-reactivation gate resolves to terminal deferred. Do not derive titles from URLs or use model-generated titles. Future automatic Thread creation requires a separate source-backed design and Operator decision.

D4 acceptance does not close D5's disposition/reference matrix, authorize RW4-1 persistence, RW4-3 implementation, RW4-2 Stage B, or D6 reactivation. It excludes new-Thread creation, near-duplicate detection, and automatic noise classification from the first-release scope.

### D5 — Disposition vocabulary and reference matrix (OPEN)

D5 remains an Operator decision. D4.3 has already excluded automatic new_thread creation in v1; D5 must not re-open it by implication. Automatic noise classification remains excluded absent a separate deterministic, source-backed rule. The proposed first-release business outcomes are matched, duplicate, and terminal deferred, but the complete allowed/prohibited reference combinations, reason vocabulary, and Task-attributed Event semantics are not yet accepted.

Before RW4-1, freeze every disposition/reference combination and enforce it at persistence/commit:
- matched: one existing same-Team/domain Thread; dormant candidates cannot produce a matched result that implies reactivation before D6.
- duplicate: one canonical same-Team exact-content duplicate Signal reference.
- deferred: a validated durable reason and no Thread or duplicate reference.
- no new_thread in v1; no automatic noise outcome in this slice.

No disposition may mutate Hypothesis, EvidenceLink, ConfidenceChange, TeamPolicy, or enqueue follow-up Tasks. The disposition, permitted references, Task attribution, and required Event semantics must be closed and validated. RW4-1 remains gated on D5 acceptance, its reviewed proof subset, and explicit authorization.

### D6 — Reactivation is a matched-only atomic transition with defined race outcomes

**Proposal:** Only a committed `matched` disposition to the deterministically selected dormant Thread may reactivate it, by the transition `dormant → active`.

- Revalidate the Thread's Team/domain and current lifecycle state inside the business commit; do not rely on candidate-search state read earlier.
- Decay and triage must use a consistent lock order for the Thread and any associated disposition/Task records. The exact lock set must be derived from the existing RW-5 transaction design before implementation, not invented here.
- Both operations re-check the current Thread state under lock. A stale decay decision must not mark a Thread dormant after a later committed reactivation; a stale triage decision must not reactivate a Thread whose state has changed incompatibly.
- If decay commits first, a subsequent valid matched triage may observe the dormant state and reactivate it once.
- If triage commits first, a concurrent decay operation must re-evaluate against the post-reactivation state and current decay basis; it may decay only if the newly committed state is independently eligible under the agreed timestamp/decay rules. It must not apply a pre-reactivation stale decision.
- Concurrent/replayed triage requests resolve to the canonical Task/disposition and produce at most one reactivation Event. A repeated request does not toggle state or emit a second transition Event.
- `new_thread`, `noise`, `duplicate`, and `deferred` do not reactivate a Thread.
- Record the transition in the Task-attributed Event committed with the disposition.

**Open gate:** timestamp semantics (including which field, if any, resets the decay clock) must be agreed with RW-5 before implementation. This record does not authorize changing `last_updated_at`, `last_touched_at`, or any decay basis by assumption. RW-5 must define its eligibility calculation against the same committed lifecycle/timestamp contract.

**Reason:** reactivation must not accidentally bypass or conflict with the independently implementable RW-5 decay contract. Locking alone is insufficient unless both sides re-evaluate state and stale decisions cannot overwrite the winner.

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

D1, all six D2 decisions, D3-A/B/C, and D4.1/D4.1a/D4.2/D4.3 are accepted and must not be reopened by this reconciliation section. The remaining D5/D6 decisions and D4 evidence closure plus cross-cutting documentation work must be completed before RW4-0 can close; acceptance does not itself authorize implementation:

1. D3 lifecycle reconciliation is complete: Signal eligibility is derived without a Signal status column; TaskRuntime owns Task lifecycle and terminal identity occupancy; terminal deferred is immutable and its Task completes `done`; technical failures remain TaskRuntime failures. D5 vocabulary/reference combinations and D6 Thread reactivation remain separate.
2. Preserve the accepted D1 trusted-host/Control Room boundary as historical decision text: the application Control Room is the sole logical Task-creation authority; supported producers delegate to named Control Room operations; the host supplies the typed principal and exact Team/action grant; production authentication remains a post-R8 prerequisite. Reconcile implementation evidence and the nine-writer conformance plan without reopening or relabeling D1 as pending. The boundary is trusted application code, not a database-enforced authorization claim.
3. Freeze the separate duplicate-Signal, existing-Thread match, and new-Thread eligibility rules from a concrete fixture and source audit, or explicitly narrow the first implementation to a smaller supported scenario. Specify all no-candidate, unique-candidate, multiple/tied-candidate, weak, ambiguous, and insufficient-input outcomes.
4. Treat the accepted D2 identity and request-Event decisions as fixed historical inputs, not open proposals: UUIDv5 directly as `Task.id` with the frozen v1 namespace/name/golden vector; persisted `signal_id` and `identity_version` with composite unique `(team_id, signal_id, identity_version)`; partial unique request-Event index (at-most-one) plus atomic Task/Event creation and replay validation (exactly-one); accepted requester provenance/replay/re-triage rules; immutable first-writer watermarks excluded from semantic replay equivalence; and code-owned v1 matching pins with actual values deferred to D4b. Reconcile their implementation/proof requirements and cross-document wording without asking the Operator to accept these decisions again. The accepted schema/creator requirements remain unimplemented and do not authorize a migration or Stage B.
5. Define the minimum Thread creation contract, including deterministic title source/normalization, initial status, canonical Team/domain derivation, timestamp source, and Task/Signal provenance. If any required field cannot be supplied safely, remove `new_thread` from the first release.
6. Agree with RW-5 on reactivation timestamps, lock order, revalidation rules, and the decay-first/triage-first race outcomes.
7. Produce a requirement-to-test matrix for every disposition, cross-Team/domain rejection, canonical Task creation races, same-request replay, conflicting-request rejection, disposition uniqueness, reference combinations, atomic rollback, concurrent triage/decay orderings, Task recovery, and single reactivation Event behavior.
8. Record unresolved items as explicit blockers; do not silently convert proposals into accepted decisions.

## 5. Proposed requirement-to-test matrix

This matrix identifies proof obligations, not existing tests or implementation evidence. Exact test module/node names are frozen only after the source audit and decision contracts above are accepted.

| Requirement | Minimum proof |
|---|---|
| Host authority and Team scope | Missing/untrusted principal, absent/wrong Team grant, wrong operation grant, inactive/missing Team, and Signal-domain mismatch all fail before Task creation; request Event records the trusted requester. |
| Canonical Task UUID identity | Two conforming writers derive the same canonical UUIDv5 for the same Team/Signal/operation/identity version; the Task primary key rejects a duplicate insert using that exact UUID. |
| Logical-pair Task uniqueness | Persisted triage Task identity fields and the composite unique constraint on `(team_id, signal_id, identity_version)` reject a second row for the same logical tuple even when the attempted row uses a fabricated, different Task UUID. This proof must demonstrate that the composite constraint—not the primary key—rejects the row. |
| Concurrent Task/request-Event creation | Two independent PostgreSQL sessions race the same canonical request; exactly one Task and one request Event are committed, and the losing request resolves and validates the winner. This race proof does not replace the separate fabricated-UUID composite-constraint proof. |
| Request replay/conflict | Each caller is independently authorized; the same canonical request resolves to the same Task without replacing first-requester provenance; changed policy pin or other immutable request content conflicts without mutation. |
| Disposition uniqueness | Concurrent commits for one Signal/Team pair produce one disposition; another Team remains an independent scope. |
| Duplicate Signal | Exact raw content-hash equality within the same Team regardless of origin resolves to the first successfully committed Team/hash canonical Signal; cross-Team equality is not duplicate; concurrent first arrivals are database-arbitrated and stable; duplicate never creates/reactivates a Thread. |
| Existing Thread match | Unique valid active/dormant same-Team/domain candidate may be selected only with verified provenance and compatible pins; ties, ambiguity, insufficient/corrupt evidence, or overflow defer. A dormant would-be match defers until D6 reactivation is accepted and separately authorized; incidental row/vector ordering cannot decide. |
| No automatic Thread creation | No qualifying existing match, ambiguous/insufficient evidence, or a dormant candidate blocked by D6 resolves to terminal deferred. No URL-derived/model-generated title or automatic Thread insert is permitted in v1. |
| Disposition reference matrix | Each disposition accepts only its specified Thread/duplicate references; every invalid combination rejects without partial writes. |
| Atomic business commit | Disposition, permitted Thread mutation, and required Event commit together or roll back together. |
| Task recovery/replay | Recovery uses TaskRuntime; a prior committed business result is recognized without duplicate disposition, Thread, or Event writes. |
| Reactivation idempotency | Repeated/concurrent same-pair requests produce at most one dormant-to-active transition and one transition Event. |
| Decay/triage race | Exercise decay-first then triage and triage-first then decay; both revalidate under a consistent lock order, and neither stale decision overwrites the committed winner. Timestamp eligibility follows the agreed RW-5 contract. |

## 6. Existing gates remain in force

- RW3.4 formal acceptance remains deferred. Before RW-4 implementation begins, the Operator must either complete its bounded acceptance work and formally accept it, or explicitly authorize a sequencing exception while retaining the deferred disposition.
- Experiment A informs RW4-4 representation only. It does not block RW4-0 through RW4-3 or independent RW-5 work.
- RW-5 design, implementation, and unit-level decay proofs remain independently implementable; integrated RW-4/RW-5 proof must verify reactivation and retrieval against post-decay state.
- R8 remains unscheduled.
- This record is a documentation proposal only. It authorizes no code, schema, migration, test-only follow-up, dispatcher change, provider execution, persistent-database operation, or scored experiment.

## 7. Remaining Operator decisions and closure gate

D1 and all six D2 decisions were explicitly accepted on 2026-11-24; D3-A/B/C were explicitly accepted on 2026-11-25. They are closed as Operator decisions and must not be presented as awaiting acceptance. Their implementation requirements, migration design, Control Room writer conformance, and PostgreSQL proof remain separate engineering/review gates; acceptance did not authorize code or schema changes.

The remaining Operator decisions are D5 and D6. D4.1/D4.1a/D4.2/D4.3 were accepted on 2026-11-25; their numeric/persistence evidence gates remain engineering prerequisites, not pending policy decisions. D3-A/B/C were accepted on 2026-11-25 and are reconciled: no Signal lifecycle state; an existing disposition excludes a new v1 decision; TaskRuntime owns lifecycle and terminal identity occupancy; deferred is immutable and completes as `done`; disposition plus Task attribution/reason and the TaskRuntime Outcome/status/terminal Event commit atomically; missing or inconsistent canonical Task/request-Event history fails closed without repair or replacement; stale-pin supersession uses the existing TaskRuntime terminal non-success path and is a required RW4-3 proof; and dormant-Thread reactivation remains prohibited until D6. Technical failures remain distinct and are never relabeled deferred. D3 reconciliation does not authorize RW4-1 persistence. D4's accepted decision shape still requires canonical Team/hash persistence design and concurrency proof, independent labeled fixtures, measured thresholds/margin/score serialization/bounds, actual v1 pins, and query-plan/cost evidence. D5's complete disposition/reference matrix and durable reason/Event semantics, and D6's decay/reactivation timestamp, locking, and race semantics remain unresolved. D4.3 has already excluded automatic Thread creation; a deterministic title source is not a v1 gate. Cross-cutting assessment receipt/recovery and later Context-consumer contracts also remain separate closure items.

An implementation stage may begin only when that slice's own prerequisites and the cross-cutting contracts it depends on are independently reviewed, explicitly accepted where required, its proof subset is frozen, and explicit authorization is recorded. D4–D6 are not a universal blocker for every slice: D5 gates RW4-1 disposition persistence; D4/C1/D5 gate RW4-3 matching/commit; D6 gates dormant-Thread reactivation. This does not reopen D1/D2 or make their accepted design requirements implementation-ready by implication.
