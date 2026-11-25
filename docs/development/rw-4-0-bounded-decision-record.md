# RW4-0 — Bounded triage decision record

**Status:** D1/all six D2, D3-A/B/C, D4.1/D4.1a/D4.2/D4.3, D5.1–D5.4, and D6.1–D6.6 are accepted. D4 evidence/design closure and implementation gates remain open. No implementation is authorized by this record.

> **Current reconciliation (2026-11-25):** D4.1/D4.1a/D4.2/D4.3, D5.1–D5.4, and D6.1–D6.6 are accepted. Exact raw-hash duplicate scope is same-Team regardless of origin, with the first committed Team/hash Signal canonical; matcher shape is accepted but numeric parameters/query-cost evidence remain open; automatic Thread creation and noise classification are excluded. D5 freezes the three disposition values, reference matrix, deferred reason codes, and TaskRuntime-owned atomic terminal evidence. D6 accepts matched-only dormant reactivation, unchanged Thread timestamps, Team revision increment, the frozen RW-5 lock order, atomic TaskRuntime commit, and DB-enforced replay/recovery. Implementation remains a separate RW4-5 gate. Follow the [RW-4 Readiness and Delivery Plan](rw-4-readiness-and-delivery-plan.md) for consolidated gates.
## RW4-2 D2 Operator decision — canonical Task identity (2026-11-24)

**ACCEPTED:** use UUIDv5 directly as `Task.id` for `triage_signal`, with identity version `triage_identity_v1`. Frozen namespace: `383bbdde-37be-4895-8fb7-1afa196b5cf7`. Exact canonical name: `triage_identity_v1|triage_signal|team:<team-uuid>|signal:<signal-uuid>`, using lowercase canonical UUID text and no whitespace. Accepted golden vector: Team `00000000-0000-4000-8000-000000000001`, Signal `00000000-0000-4000-8000-000000000002`, expected Task ID `5b45ed53-a50f-51e8-ba81-ce52512aa922`.

This is separate from the already accepted Task-schema requirement to persist `signal_id` and `identity_version` and enforce unique `(team_id, signal_id, identity_version)`. All six D2 decisions are design decisions only; no migration or creator implementation is authorized. Decisions 3–6 were accepted on 2026-11-24 and are summarized below.

**Scope:** First, narrow `triage_signal` slice only. D1/all D2, D3-A/B/C, D4.1/D4.1a/D4.2/D4.3, D5.1–D5.4, and D6.1–D6.6 are accepted; D4 evidence closure and separately authorized implementation gates remain. No implementation is authorized by this record.
**Current reconciliation baseline:** main after PR #190 squash merge `4d9c3f3b51cc8f3176aca4ab30b367cb4271686d` (2026-11-25). PR #184 is the earlier D1/D2 proposal baseline; historical proposal origins remain PRs #174 and #176. D3 decisions are recorded in [issue #189](https://github.com/abtn/Watch-Architecture-Rev2/issues/189); D4 decisions are recorded in [issue #191](https://github.com/abtn/Watch-Architecture-Rev2/issues/191).
**Authority:** `PLAN.md` remains authoritative for milestone status and implementation authorization. Existing accepted ADRs, Task contracts, and write-scope matrix remain binding unless explicitly amended.

## 1. Purpose and non-goal

Define the smallest safe first slice that can record one Team's disposition of one canonical Signal. This record narrows the decision surface; it does not attempt to freeze world-memory retrieval, claim-level knowledge attribution, or a general matching platform.

The intended first-slice boundary is:

`trusted host request → immutable triage_signal Task → deterministic application decision → atomic SignalDisposition / permitted Thread change / Event`

The model is not involved in triage. Triage does not create or enqueue `update_thread` Tasks.

## 2. Accepted D1/D2/D3/D4/D5/D6 decisions and remaining engineering gates

D1 and all six D2 decisions are accepted as recorded below. D3-A/B/C, D4.1/D4.1a/D4.2/D4.3, D5.1–D5.4, and D6.1–D6.6 are accepted on 2026-11-25 and reconciled in §7. D4's policy shape is closed, but its canonical Team/hash persistence design and measured matcher evidence remain engineering gates. D6 implementation remains a separate RW4-5 engineering and authorization gate.

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

**Accepted D2 identity/replay contract; adjacent disposition scope remains separate:** the first release has one canonical triage operation per `(signal_id, team_id)`, represented by one immutable `triage_signal` Task. D3 and D5 business semantics are accepted; SignalDisposition persistence/uniqueness remain assigned to RW4-1 and require a reviewed physical design.

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

A valid `deferred` business disposition is immutable/terminal in v1 and its Task completes successfully as `done`. The disposition row, Task attribution/reason, TaskRuntime `task_execution` Outcome, terminal Task status, and `task_completed` Event must commit or roll back together in one TaskRuntime-owned database transaction. The Kernel persistence operation uses the active Session and cannot open/commit a separate transaction. Technical failures remain distinct and follow TaskRuntime retry/recovery; no `update_thread`, `operator_update`, or background refinement may change the disposition. D5.1–D5.4 freeze the disposition contract; D6.1–D6.6 are accepted, with implementation separately gated as RW4-5. D3 acceptance authorizes no code/schema/migration.

### D4 — Duplicate identity, existing-Thread matching, and no automatic Thread creation

**Decision status: D4.1, D4.1a, D4.2, and D4.3 ACCEPTED by the Operator on 2026-11-25.** The decision rules below are accepted; evidence-backed implementation parameters and persistence design remain open.

1. **D4.1 — Duplicate Signal detection (Option A):** exact raw content-hash equality within the same Team's intake history, regardless of origin. Cross-Team equality is not a duplicate. Near-duplicate, syndicated-copy, and semantic duplicate detection are excluded. Duplicate detection identifies a canonical Signal and does not select or mutate a Thread.
2. **D4.1a — Canonical duplicate winner:** the first Signal successfully committed into the Team's intake history for that exact content hash wins. PostgreSQL must arbitrate concurrent first arrivals and the Team/hash association must remain stable. Do not select by fetched_at, application timestamps, UUID order, or origin. This is a decision, not an implemented persistence mechanism: Signal is not Team-owned and Team association is represented by ingestion Events; current origin_url + content_hash ingestion uniqueness does not provide cross-origin Team/hash canonicalization. RW4-3 requires a separately reviewed persistence design and real two-session PostgreSQL proof.
3. **D4.2 — Existing-Thread matching (Option A shape):** derive evidence profiles at read time through Team-scoped EvidenceLink → Hypothesis → Thread; consider same-Team/same-Domain active or dormant Threads and exclude resolved; only supports/challenges EvidenceLinks count (mentions alone is insufficient); validate same-Team ingestion provenance and exact Signal/Snapshot/hash and EvidenceLink Snapshot/hash associations; use only compatible existing KnowledgeChunk projections under the immutable embedding/chunking pins. No Thread embeddings, model calls, re-embedding, summary/alias subsystem, or recency bonus. Maximum pairwise chunk cosine similarity remains an experimental baseline subject to outlier/profile-size bias. Minimum threshold and runner-up margin, score serialization, candidate/evidence bounds, actual pins, fixture performance and PostgreSQL query cost remain open and must be measured. Ambiguity, ties, insufficient valid evidence, incompatibility, or overflow defers; missing, partial, mismatched, or corrupt provenance is a technical/integrity failure, not deferred. No incidental UUID/order tie-break. An active Thread may be matched directly. Under accepted D6, a dormant Thread may be referenced by `matched` only when the same TaskRuntime-owned transaction reactivates it and records the immutable Task-attributed `thread_reactivated` Event. Until RW4-5 implementation is separately authorized and proven, dormant would-be winners with no active winner resolve to terminal deferred with `dormant_thread_requires_reactivation`.
4. **D4.3 — New Thread eligibility (Option A):** automatic Thread creation is disabled in v1. No qualifying existing match, ambiguous/insufficient evidence, or a dormant candidate blocked by the not-yet-implemented RW4-5 path resolves to terminal deferred. Do not derive titles from URLs or use model-generated titles. Future automatic Thread creation requires a separate source-backed design and Operator decision.

D4/D5/D6 decision acceptance does not authorize RW4-1 persistence, RW4-3 implementation, RW4-2 Stage B, or RW4-5 reactivation implementation. It excludes new-Thread creation, near-duplicate detection, and automatic noise classification from the first-release scope.

### D5 — Disposition vocabulary, references, reasons, and terminal evidence (ACCEPTED 2026-11-25)

**Decision status: D5.1–D5.4 ACCEPTED by the Operator on 2026-11-25.** The accepted v1 vocabulary, reference matrix, deferred reason codes, and Task-attributed terminal semantics are recorded in [issue #193](https://github.com/abtn/Watch-Architecture-Rev2/issues/193). This freezes the business contract; it does not approve a physical schema, migration, or implementation.

#### D5.1 — Exactly three v1 disposition values

- `matched`: the Signal is associated with one existing eligible active Thread.
- `duplicate`: the Signal is an exact raw-content-hash duplicate of the canonical Signal for the same Team.
- `deferred`: no safe, sufficiently supported business decision can be made.

`new_thread` and `noise` are excluded. Execution states such as `pending`, `processing`, and `failed` belong to TaskRuntime and are not disposition values. Deferred is a successful terminal business result, not a Task failure.

#### D5.2 — Required reference matrix

| Field | `matched` | `duplicate` | `deferred` |
|---|---|---|---|
| `thread_id` | Required | NULL | NULL |
| `duplicate_of_signal_id` | NULL | Required | NULL |
| `reason_code` | NULL | NULL | Required |
| `decided_by_task_id` | Required | Required | Required |

- A matched Thread must be same-Team and same-Domain. Under accepted D6, a dormant winner may be referenced only when the same TaskRuntime-owned transaction changes it to active, records one immutable Task-attributed `thread_reactivated` Event, writes the matched disposition, and terminalizes the Task. Until RW4-5 implementation is separately authorized and proven, dormant would-be winners still defer with `dormant_thread_requires_reactivation`. Reactivation does not mutate `last_updated_at`.
- A duplicate reference must identify the canonical Signal for the same Team and exact raw content hash; it cannot reference itself. Team association is established through ingestion history, not a Signal.team_id column.
- Deferred carries neither a Thread nor a duplicate reference.
- Every disposition references exactly one canonical `triage_signal` Task for the same Team and Signal. References are validated against persisted records, never caller/model assertions.
- One immutable disposition per `(signal_id, team_id)`; `created_at` is immutable and database-assigned; there is no `updated_at`.
- Database constraints must enforce row-local nullability, uniqueness, and available foreign keys. Same-Team/domain, canonical Team/hash association, and Task/Signal/Team cross-record consistency require a reviewed enforceable relational design and transaction validation; a simple FK must not be claimed to prove them.

#### D5.3 — Stable deferred reason codes

Allowed values:
- `no_eligible_thread`
- `ambiguous_thread_match`
- `insufficient_evidence`
- `no_compatible_evidence`
- `evidence_limit_exceeded`
- `dormant_thread_requires_reactivation`

Human-readable explanation is separate from the stable code and is retained in Task-attributed evidence. Corrupt or inconsistent provenance is a technical/integrity failure, not deferred. Superseded Task pins use TaskRuntime's existing terminal non-success path with status `failed`, result category `terminal_failure`, and reason `matching_pins_superseded`; they do not create a disposition. Database/provider/runtime failures follow TaskRuntime retry/recovery and may ultimately fail.

#### D5.4 — Task attribution and terminal Event semantics

Every disposition references exactly one canonical `triage_signal` Task with the same Team and Signal. The immutable request Event retains the original request and requester provenance. A successful decision produces one TaskRuntime `task_execution` Outcome and one terminal `task_completed` Event. The Outcome records the disposition, the deferred reason code when applicable, and the relevant reference.

The disposition, Task-attributed evidence, Outcome, terminal Task status, and completion Event commit or roll back together in one TaskRuntime-owned transaction. Kernel persistence participates in the active Session and cannot commit independently. Deferred completes successfully with Task status `done`, never `failed`. Replay validates the existing canonical Task, request Event, and disposition; it never creates replacement history.

No disposition may mutate Hypothesis, EvidenceLink, ConfidenceChange, TeamPolicy, or enqueue follow-up Tasks. D5 acceptance does not authorize RW4-1 persistence or any production code/schema/migration. RW4-1 still requires a reviewed physical design, proof subset, and explicit implementation authorization. D4 evidence closure remains required for RW4-3; D6 decisions are accepted; RW4-5 dormant-Thread reactivation implementation remains separate.

### D6 — Accepted dormant Thread reactivation contract (2026-11-25)

**Accepted decisions:** D6.1–D6.6 (issue #195). This is a frozen decision contract, not implementation authorization.

- **D6.1 — matched-only trigger (Option A):** only a valid `triage_signal` may reactivate a dormant Thread, when the deterministic matcher selects it as the unambiguous winner and no active candidate wins. Reactivation is part of that Task's Kernel commit. No standalone Operator, background, `update_thread`, `operator_update`, decay, or model-directed reactivation.
- **D6.2 — timestamp (Option A):** do not mutate `Thread.last_updated_at` or add a reactivation timestamp projection. Preserve existing timestamp semantics; the immutable DB-timestamped `thread_reactivated` Event is authoritative history.
- **D6.3 — atomicity:** Thread `dormant → active`, one Task-attributed reactivation Event, matched SignalDisposition, TaskRuntime `task_execution` Outcome, terminal Task status/completion time, and `task_completed` Event commit or roll back together in one TaskRuntime-owned transaction. Kernel persistence participates in the active Session and never commits independently.
- **D6.4 — revision/stale fencing:** use the frozen RW-5 PostgreSQL clock and Team revision protocol; increment `world_memory_revision` because the transition changes the candidate set. Revalidate Team eligibility, Thread Team/domain/status, matcher winner, and relevant Hypothesis/evidence watermarks under the canonical locks. A stale assessment receipt cannot authorize the transition.
- **D6.5 — locking/races:** use only the canonical RW-5 helper and order: Task `FOR UPDATE` → Team `FOR NO KEY UPDATE` → sorted Thread `FOR NO KEY UPDATE` → sorted Hypothesis `FOR NO KEY UPDATE`. No bespoke lock path. Prove decay-first and triage-first interleavings on disposable PostgreSQL, including revision and Hypothesis-watermark observations. RW-5 first-release decay remains confidence-only and does not own Thread lifecycle.
- **D6.6 — replay/recovery:** committed replay returns the canonical disposition and Task result without another transition/Event; DB boundary enforces at-most-one reactivation Event. Lost responses resolve to the committed result; pre-commit failure leaves no partial bundle; inconsistent status/Event/Task history fails closed without repair or synthesized history. TaskRuntime alone owns retry, interruption recovery, and terminalization.

Exact Event schema/identity and uniqueness, cross-record Team/domain/Task/Signal integrity, stale-receipt fencing, complete lock-row set, both PostgreSQL race proofs, commit/rollback/lost-response/replay/interruption/inconsistency proofs, review of RW3.4 residuals touched, independent requirement-to-test review, exact-head CI, disposable-PostgreSQL local verification, and separate explicit RW4-5 implementation authorization remain required. Any future transition that makes a Thread unavailable to triage needs its own durable recovery/reconsideration path before shipping. D6 does not authorize a dormancy writer.

**Reason:** this preserves one TaskRuntime lifecycle authority, avoids overloading Thread activity timestamps, and serializes the candidate-set change against the frozen RW-5 clock/revision/lock protocol.

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

D1–D6 decisions are accepted and must not be reopened by this reconciliation section. D4 evidence closure and cross-cutting design/documentation work remain before RW4-0 can close; decision acceptance does not itself authorize implementation:

1. D3 lifecycle reconciliation is complete: Signal eligibility is derived without a Signal status column; TaskRuntime owns Task lifecycle and terminal identity occupancy; terminal deferred is immutable and its Task completes `done`; technical failures remain TaskRuntime failures. D5.1–D5.4 and D6.1–D6.6 are accepted; RW4-5 reactivation implementation remains separate.
2. Preserve the accepted D1 trusted-host/Control Room boundary as historical decision text: the application Control Room is the sole logical Task-creation authority; supported producers delegate to named Control Room operations; the host supplies the typed principal and exact Team/action grant; production authentication remains a post-R8 prerequisite. Reconcile implementation evidence and the nine-writer conformance plan without reopening or relabeling D1 as pending. The boundary is trusted application code, not a database-enforced authorization claim.
3. Complete D4 evidence closure without reopening the accepted policy shape: define the Team/hash persistence design and prove first-committed canonical association with two PostgreSQL sessions; calibrate matcher thresholds, margin, score serialization, candidate/evidence bounds, actual v1 pins, false-positive tolerance, and query cost against independently labeled fixtures. Specify all no-candidate, unique-candidate, multiple/tied-candidate, weak, ambiguous, and insufficient-input outcomes.
4. Treat the accepted D2 identity and request-Event decisions as fixed historical inputs, not open proposals: UUIDv5 directly as `Task.id` with the frozen v1 namespace/name/golden vector; persisted `signal_id` and `identity_version` with composite unique `(team_id, signal_id, identity_version)`; partial unique request-Event index (at-most-one) plus atomic Task/Event creation and replay validation (exactly-one); accepted requester provenance/replay/re-triage rules; immutable first-writer watermarks excluded from semantic replay equivalence; and code-owned v1 matching pins with actual values deferred to D4b. Reconcile their implementation/proof requirements and cross-document wording without asking the Operator to accept these decisions again. The accepted schema/creator requirements remain unimplemented and do not authorize a migration or Stage B.
5. Produce and independently review the requirement-to-test matrix for every disposition, cross-Team/domain rejection, canonical Task creation races, same-request replay, conflicting-request rejection, disposition uniqueness, reference combinations, atomic rollback, concurrent triage/decay orderings, Task recovery, and the single reactivation Event behavior required by the later RW4-5 slice.
6. Record unresolved engineering/evidence items as explicit blockers; do not silently convert proposals into implementation authorization.

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
| Existing Thread match | Candidate evaluation may inspect active/dormant same-Team/domain Threads with verified provenance and compatible pins. A dormant Thread may receive a v1 `matched` disposition only through accepted D6 same-transaction reactivation; until RW4-5 implementation is separately authorized and proven, a dormant would-be match defers with `dormant_thread_requires_reactivation`. Ties, ambiguity, insufficient valid evidence, incompatibility, or overflow defer; missing/partial/mismatched/corrupt provenance is a technical/integrity failure. Incidental row/vector ordering cannot decide. |
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

## 7. Accepted Operator decisions and remaining engineering closure gates

D1 and all six D2 decisions were explicitly accepted on 2026-11-24; D3-A/B/C were explicitly accepted on 2026-11-25. They are closed as Operator decisions and must not be presented as awaiting acceptance. Their implementation requirements, migration design, Control Room writer conformance, and PostgreSQL proof remain separate engineering/review gates; acceptance did not authorize code or schema changes.

D1–D6 are accepted decisions. D4.1/D4.1a/D4.2/D4.3 were accepted on 2026-11-25; their numeric/persistence evidence gates remain engineering prerequisites, not pending policy decisions. D3-A/B/C are reconciled: no Signal lifecycle state; an existing disposition excludes a new v1 decision; TaskRuntime owns lifecycle and terminal identity occupancy; deferred is immutable and completes as `done`; disposition plus Task attribution/reason and the TaskRuntime Outcome/status/terminal Event commit atomically; missing or inconsistent canonical Task/request-Event history fails closed without repair or replacement; stale-pin supersession uses the existing TaskRuntime terminal non-success path and is a required RW4-3 proof. Technical failures remain distinct and are never relabeled deferred. D3 reconciliation does not authorize RW4-1 persistence. D4's accepted decision shape still requires canonical Team/hash persistence design and concurrency proof, independent labeled fixtures, measured thresholds/margin/score serialization/bounds, actual v1 pins, and query-plan/cost evidence. D5.1–D5.4 are accepted and reconciled; the RW4-1 physical persistence design remains an engineering gate. D6.1–D6.6 are accepted and reconciled: matched-only dormant reactivation, unchanged Thread timestamps, atomic TaskRuntime commit, Team revision increment, canonical RW-5 lock order, and DB-enforced replay/recovery. RW4-5 implementation/proof remain separately gated. D4.3 has already excluded automatic Thread creation; a deterministic title source is not a v1 gate. Cross-cutting assessment receipt/recovery and later Context-consumer contracts also remain separate closure items. The current D4.2 proposal requires a separate durable TaskRuntime assessment-receipt transaction before business commit; exact Event schema/unique identity, recovery between commits, Team-revision/reference fence, stale-receipt failure mapping, and PostgreSQL proof remain engineering gates. The Team-revision fence is conservative because confidence-only `apply_decay` also increments Team revision; D4.2 must accept that possible false-stale failure or define a narrower matcher-input revision/fingerprint.

An implementation stage may begin only when that slice's own prerequisites and the cross-cutting contracts it depends on are independently reviewed, explicitly accepted where required, its proof subset is frozen, and explicit authorization is recorded. D4–D6 are not a universal blocker for every slice: the accepted D5 contract plus RW4-1's reviewed physical design, proof subset, and explicit authorization gate RW4-1 persistence; D4/C1/accepted D5 plus stale-pin proof gate RW4-3 matching/commit; Accepted D6 plus separate RW4-5 authorization and proof gate dormant-Thread reactivation. This does not reopen D1/D2 or make their accepted design requirements implementation-ready by implication.
