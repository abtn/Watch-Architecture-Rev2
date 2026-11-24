# RW4-2 — Trusted Task boundary and canonical identity

**Status:** D1 accepted by the Operator on 2026-11-24; D2 remains open for separate Operator decisions. This document remains a design/specification artifact. No creator implementation is authorized.

**Preparation baseline:** `main` after PR #184 squash merge `3fd27167e7e77eeed2110d9a2028a9ecaa005bc3` (2026-11-24).

**Authority:** `PLAN.md` remains the sole milestone/authorization status authority. This document is a bounded RW4-2 preparation artifact. PR #183 is housekeeping/documentation reconciliation and is not implementation authorization.

## 1. Purpose and boundary

RW4-2 establishes the trusted host-to-application Task-creation boundary and the canonical identity/replay contract for one `triage_signal` operation over one Signal and one Team.

The intended boundary is:

```text
trusted host (authentication integration is a post-R8-test prerequisite)
    -> typed principal + exact Team/action grant
    -> Control Room (the single application authority for Task creation)
    -> immutable canonical triage_signal Task + one request Event
    -> existing TaskRuntime owns all later lifecycle transitions
```

The model is not involved in Task creation, identity selection, authorization, or request replay. This slice does not implement the triage decision/matcher or SignalDisposition persistence.

### In scope for this specification

- D1 Control Room as the single Task-creation authority, with a typed trusted principal and exact Team/action grant.
- D2 business, Task, request-provenance, and disposition identities.
- One narrow Task creator and its immutable request Event.
- Database-enforced canonical Task uniqueness, atomic creation, concurrency arbitration, replay, and conflict semantics.
- Exact Task envelope and immutable request pins, subject to the open pin-source question in §7.
- A requirement-to-test matrix for the creator/replay boundary.

### Explicitly out of scope

- SignalDisposition ORM/table, migration, uniqueness constraint, or lifecycle (RW4-1).
- Matching, duplicate classification, Thread selection/creation, or disposition commit (RW4-3).
- Dormant Thread reactivation and RW-5 decay implementation. RW4-2 Task-creator implementation depends on the separately authorized canonical RW-5 lock-helper implementation; this draft does not authorize or implement that helper.
- New scheduler, TaskDispatcher expansion, ingestion-triggered Task creation, routes, CLI, public API, or general-purpose Task factory.
- Production host authentication/composition root; the repository currently has no production host composition root.
- Model/provider invocation, embeddings, new projections, or matching configuration infrastructure.
- Changes to RW-3 `update_thread`, RW-2 Operator commits, or existing TaskRuntime lifecycle ownership.

## 2. Current source facts

The current ORM and application contracts establish the following:

1. `Task.id` is the database primary key. `Task` currently has Team, Task type, status, attempt count, policy version, optional Objective/Plan links, allowed writes, budget, timestamps, and maximum attempts. It has no separate canonical triage identity column.
2. `Task.team_id` and `Task.policy_version` are constrained to a TeamPolicy version for that Team.
3. `Signal` has a UUID ID, domain, source type, origin URL, fetched time, content hash, and immutable Snapshot reference. It has no Team foreign key; ingestion derives Signal.domain from Team.domain.
4. `Event` has Task attribution and a task/type index, but no uniqueness constraint for one request Event per Task. The creator must therefore enforce exact-one request Event through deterministic Task insertion and transactional logic, then validate it on replay.
5. `core/operator_application.py` and the RW-3 `create_update_thread_task` flow provide a proven host-invoked adapter pattern: typed principal, exact Team/action grant, canonical identity, Task/Event atomic creation, deterministic Task ID, and replay validation.
6. The RW-3 identity namespace and key are specific to `update_thread` and its host idempotency UUID. They must not be reused for triage.
7. The production host composition/authentication boundary is absent. Watch-side validation of a supplied in-process principal is not proof of end-to-end authentication.

These are source observations, not acceptance of the proposed RW4 contract.

## 3. D1 — Trusted host invocation

### Accepted Operator decision (2026-11-24)

D1 is accepted with the following decisions:

1. **Single Task-creation authority:** the application Control Room is the only authority allowed to create/persist Tasks. Control Room is the logical application boundary/owner in this decision; this wording does not claim that a dedicated Control Room module or service already exists in the repository. Host-facing adapters and feature-specific entrypoints may request work, but they must delegate to a named Control Room operation. Workers, models, ingestion code, and feature modules must not create Tasks directly or introduce parallel Task factories. Existing supported Task-creation paths must be represented as Control Room operations; this decision does not itself authorize a refactor of existing RW-3 code.
2. **Team eligibility:** only a Team whose persisted state is exactly `active` is eligible for triage Task creation or replay.
3. **Authentication timing:** the host remains responsible for authenticating the requester. Production host authentication integration is accepted as a required prerequisite, scheduled after the R8 test. It must be complete before production use; this decision does not claim authentication is implemented or authorize production use before it exists. The in-process principal remains forgeable by code inside the process.
4. **URL normalization:** broader URL normalization is deferred until after the R8 test. Until then, compare the persisted `origin_url` and `source_type` values exactly. The future minimal foundation should treat DNS hostname case as insignificant (for example, `Google.com` and `google.com` compare as the same host) while preserving scheme, port, path, query, fragment, and trailing-slash distinctions; `source_type` remains exact. This is a proposed narrow rule for the post-R8-test normalization work, not current behavior or implementation authorization.
5. **Policy selection:** use the greatest immutable `TeamPolicy.version` for the Team, resolved under the canonical Team lock. Missing, malformed, or unsupported greatest-version policy/source data fails closed; never fall back to an older version.

### Accepted adapter contract

The host invokes one narrow Control Room operation that requests triage for one Signal under one exact Team grant. The host selects the intended Team and supplies a typed principal with stable issuer/subject identity and an invocation-scoped Team/action grant. The request itself cannot supply authority or select a Team.

The host authenticates the requester and supplies a typed principal with stable issuer and subject identity and an exact Team/action grant. The host is responsible for deciding which Team grant to issue. The adapter must not infer authority from a Team ID, role, email, display name, or claimed identity in an untrusted request payload.

### Proposed adapter contract

Proposed operation name:

```python
create_triage_signal_task(
    principal: TrustedOperatorPrincipal,
    request: TriageSignalTaskRequest,
) -> TriageSignalTaskResult
```

Proposed request shape:

```python
@dataclass(frozen=True)
class TriageSignalTaskRequest:
    signal_id: UUID
```

The request deliberately has no Team ID, requester ID, Task ID, policy version, matcher configuration, or caller-selected identity. The trusted principal carries the exact Team/action grant. The adapter derives the Team from that grant and validates the canonical Signal against it.

Proposed action string: `triage_signal`.

The Control Room operation must:

1. Reject a missing, wrong-type, malformed, or unsupported principal before durable writes.
2. Validate stable issuer/subject identity using the existing canonical principal-identity rules; do not invent a second actor-identity encoding.
3. Require exactly one invocation-scoped Team grant for action `triage_signal`. The principal may hold grants for other actions; those are irrelevant. If more than one Team grant for `triage_signal` is supplied for this invocation, fail closed rather than choosing one. The host selects the intended Team and supplies that exact grant.
4. Load the canonical Signal and Team. Require both (a) `Signal.domain == Team.domain` using stored values and (b) the persisted `(Signal.origin_url, Signal.source_type)` pair to appear in the greatest-version immutable TeamPolicy's `rules["sources"]` allowlist, following ADR-0028. The greatest `TeamPolicy.version` is resolved under the canonical Team lock; there is no active-policy pointer. Domain equality alone is insufficient; an allowlist match alone is also insufficient. Until the separately gated post-R8-test URL-normalization work is accepted and implemented, compare the persisted URL and source type exactly. A request cannot override any of these values. If no policy exists, or the greatest-version policy/schema/source entry is malformed or unsupported, fail closed without falling back to an older version.
5. Require the Team state to be exactly `active`; fail closed for missing or any other Team state, or a missing Signal. Resolve and pin the applicable TeamPolicy version using the accepted creator/lock contract.
6. Independently authorize every caller before either creating a Task or resolving/replaying an existing canonical Task.
7. Create or resolve only the canonical `triage_signal` Task described in D2.
8. Return a typed result identifying the Task and whether it was newly created or replayed. It does not admit, execute, or finalize the Task.

These are creation-time checks, not execution guarantees. Team status, domain/source eligibility, and policy may change while the Task is queued. RW4-3 must revalidate current Team eligibility and the Signal-to-Team source scope under the accepted RW-5 lock chain immediately before matching/commit. A Task that no longer qualifies must not be executed against stale authority.

### Trust limitation

The principal is an in-process trust contract, not a credential or an unforgeable runtime object: any code in the process can construct the Python value. The Control Room is the only application authority that may persist Tasks; its narrow typed operation derives Team and authority exclusively from the supplied trusted principal/grant and canonical database records. Host-facing adapters delegate to the Control Room, and workers/models/feature modules cannot create Tasks directly. Request payload fields cannot supply or override Team, requester, role, or authority. Tests must prove forged/payload-supplied authority is ignored or rejected. No production host composition root currently exists, so Watch-side validation proves only the application-side contract, not end-to-end authentication. The host must authenticate before constructing/calling the adapter; this integration is required before production use and is scheduled after the R8 test.

### D1 non-goals

No login, token verifier, user store, RBAC framework, deployed Watch API/CLI, automatic ingestion trigger, scheduler, queue expansion, or TaskDispatcher change. No URL normalization is implemented in this stage; its narrow hostname-case rule is deferred until after the R8 test. No refactor of existing RW-3 Task-creation code is authorized by this documentation decision.

## 4. D2 — Canonical identity and replay

### 4.1 Keep identities distinct

| Identity | Proposed definition | Purpose |
|---|---|---|
| Business identity | `(signal_id, team_id)` | One Team-specific triage result |
| Task identity | Deterministic UUIDv5 over canonical Team, Signal, `triage_signal`, and fixed identity version `triage_identity_v1`, under a dedicated RW4 namespace | One canonical Task for the pair in the first identity generation |
| Request provenance | One immutable Task-attributed request Event | Records who requested the first canonical Task and the immutable request basis |
| Disposition identity | Unique `(signal_id, team_id)` | One persisted disposition; implemented separately in RW4-1 |
| Execution identity | Existing Task ID plus TaskRuntime attempt/recovery state | TaskRuntime owns retries and lifecycle; attempts do not create new Tasks |

### 4.2 Canonical Task ID

**Recommendation:** use the deterministic UUIDv5 as `Task.id` itself, and separately require persisted identity components and a database unique constraint on `(team_id, signal_id, identity_version)`. The Task primary key arbitrates duplicate UUIDs; the tuple constraint prevents a second writer from assigning a different UUID to the same Team/Signal pair within the same identity generation. The current schema audit found no `signal_id` or `identity_version` fields on Task and no such unique constraint (see §4.9), so this requires a Task-schema migration. The Operator's risk disposition must explicitly account for that migration cost.

The UUIDv5 namespace must be dedicated to RW4 triage and versioned in source/documentation. Proposed frozen namespace UUID: `383bbdde-37be-4895-8fb7-1afa196b5cf7` (UUIDv4 generated for this contract; once accepted, never regenerate or derive it). The canonical name must unambiguously encode, using canonical lowercase UUID text and a fixed documented delimiter/field order:

- fixed identity version `triage_identity_v1`;
- operation/task type `triage_signal`;
- canonical Team UUID;
- canonical Signal UUID.

The canonical name template is exactly `triage_identity_v1|triage_signal|team:<team-uuid>|signal:<signal-uuid>`, with lowercase canonical UUID text and no whitespace. The dedicated RW4 namespace UUID is a separate frozen contract constant; do not reuse the RW-3 `update_thread` namespace. Both constants must be recorded in the accepted spec before implementation. A golden test must pin the resulting UUID for fixed Team/Signal inputs so namespace or encoding drift fails visibly. The proposed golden vector is Team `00000000-0000-4000-8000-000000000001`, Signal `00000000-0000-4000-8000-000000000002`, expected Task ID `5b45ed53-a50f-51e8-ba81-ce52512aa922` under the proposed namespace above. Treat this vector and namespace as proposed draft constants until D2 is accepted.

The Task ID is independent of requester identity, policy version, matcher/embedding/chunking pins, Team revision watermark, and retry attempt. Pins belong in the request fingerprint and conflict on mismatch; they are not part of identity. Reusing the same Signal/Team pair in the first generation derives the same Task ID even if the caller or pins differ; identical pins replay, while changed pins return a conflict against that same canonical identity.

**Re-triage rule for the first release:** there is exactly one Task identity per `(signal_id, team_id, triage_identity_v1)`. A terminally failed or superseded Task continues to occupy that identity; ordinary retry/replay never creates a replacement. A changed policy or matching pin conflicts with the existing Task and does not create a second Task. This means a Signal/Team pair superseded after a legitimate matcher, embedding, or chunking change is not automatically reachable again under v1. The sanctioned future route is an explicitly Operator-approved `triage_identity_v2` generation, introduced only with a documented transition and new canonical identity input; it is not an automatic retry, replay, or re-triage path. The trigger for considering v2 is the first accepted matcher, embedding-space, or chunking change that makes existing v1 Tasks stale, or a separately approved need to recover from terminal failure. Until that approval and transition exist, the pair remains unavailable for another generation. Never mutate v1 semantics or silently create v2.

Because the deterministic ID is the Task primary key, concurrent inserts are arbitrated by PostgreSQL primary-key uniqueness. The PK alone does not prove that a row's stored semantics match its ID: every load/replay must recompute the expected UUID from the row's canonical Team, Signal, operation, and identity version, then compare it to `Task.id`. A mismatch fails closed and is never repaired in place. Application pre-checks alone are insufficient.

### 4.3 Immutable request Event

The winning Task-creation transaction writes exactly one request Event. Task and Event commit or roll back together.

Proposed Event type: `triage_signal_requested`.

Proposed payload fields (exact schema and canonical serialization to be frozen before implementation):

- `schema_version`
- `task_id`
- `team_id`
- `signal_id`
- `signal_snapshot_ref`
- `signal_content_hash`
- `as_of` (the result of PostgreSQL `SELECT clock_timestamp()` captured after acquiring the canonical Team lock; application time, `now()`, and `CURRENT_TIMESTAMP` are prohibited)
- `team_revision_watermark` (captured under that same lock)
- `policy_version`
- `matcher_id`
- `matcher_version`
- `embedding_space_key`
- `chunking_version`
- `requested_by_principal` (canonical issuer/subject attribution)
- `request_fingerprint`
- `matching_pins` (the complete versioned pin object defined in §7)
- `matching_pins_hash` (SHA-256 of the canonical serialized `matching_pins` object)

The Event envelope supplies Event ID, Task ID attribution, type, and creation timestamp. Avoid duplicating envelope fields in payload unless the existing Event convention requires them; if duplicated, validate exact equality.

The request fingerprint is SHA-256 over canonical compact UTF-8 JSON with a fixed domain tag and schema version. It binds canonical Team/Signal/Task identity, the selected policy version, the Signal snapshot/content identity, and all immutable matching pins (including the complete `matching_pins` object and its content hash). It excludes the fingerprint field itself, requester identity, raw database `as_of`, and the Team revision watermark. The latter two are immutable first-writer cutoff metadata captured under the Team lock; they are validated as part of the stored request Event and returned unchanged on replay, but a later replay attempt must not conflict merely because the current database clock or Team revision has advanced. The raw principal credential/token must never be stored. The matcher/embedding/chunking pins are explicitly not inputs to Task identity; they affect replay equivalence only.

The Event is immutable after creation. A later authorized caller with the same canonical pair and identical immutable pins resolves the same Task; it does not replace the first requester's provenance or append another request Event.

### 4.4 Atomic creation and concurrency

Proposed transaction behavior:

1. Validate the typed request and principal, then resolve the exact Team grant and canonical Signal/Team identifiers. Derive the canonical Task UUID. Preliminary reads do not establish the policy/pin snapshot and must be revalidated under lock.
2. Perform a non-locking existence probe for that canonical Task ID only to select the lock path; it is not an authorization, consistency, or replay decision.
3. **If the Task already exists:** begin a replay transaction and use the canonical RW-5 helper to lock Task `FOR UPDATE` first, then Team `FOR NO KEY UPDATE`. Reload the Task after both locks and validate its identity, immutable request Event, original cutoff metadata, policy pin, Signal/Snapshot/hash, and all matching pins. The replay path is read-only.
4. **If the Task does not exist:** begin a creation transaction and use the canonical RW-5 helper's no-Task creator path to lock Team `FOR NO KEY UPDATE` first. No Task row exists at this point. Do not acquire Thread/Hypothesis locks because Task creation does not mutate those rows.
5. Under the Team lock, re-read the Task by canonical ID. If it is still absent, reload and revalidate Team status/domain, Signal source eligibility, the current immutable TeamPolicy, and the code-owned immutable matching-pin declaration. Fail closed if any value is missing, malformed, or no longer eligible.
6. If the Task appeared after the non-locking probe while this transaction waited for Team, do not lock Task after Team. Roll back the read-only creation transaction, release Team, and restart through step 3 so the replay transaction acquires Task → Team in the frozen order. This bounded restart cannot create a second Task or Event.
7. For a genuinely new Task, capture `as_of` by executing PostgreSQL `SELECT clock_timestamp()` after the Team lock is held, and capture the current Team revision watermark under that same lock. Store the returned `timestamptz` as immutable first-writer cutoff metadata. Application clocks, PostgreSQL `now()`/`CURRENT_TIMESTAMP` (transaction-start time), `Task.created_at`, and caller-supplied timestamps are not substitutes. RW4-3 later captures/revalidates a separate current watermark; it never overwrites this creation-time cutoff.
8. Derive the semantic request fingerprint from the validated identity, selected policy, Signal snapshot/content identity, and matching pins. Do not include the newly sampled `as_of` or Team revision watermark in replay-equivalence calculation.
9. Insert the pending Task with the exact Task envelope and no Objective/Plan/PlanAction links. Only the transaction that wins this insertion writes `triage_signal_requested`; commit Task and Event atomically.
10. On deterministic Task-PK conflict not already handled by the Team-lock recheck, use a transaction-safe PostgreSQL conflict strategy. If the transaction remains usable and the winner is visible under READ COMMITTED, validate the winner without violating lock order; otherwise roll back and restart through the existing-Task replay path. Never acquire Task after Team.
11. Return replay only if the semantic request is identical. Preserve and return the winner's original `as_of`, Team revision watermark, and requester provenance. Missing, duplicate, malformed, cross-Team, or mismatched evidence fails closed. A losing transaction never writes another request Event.

The implementation uses `INSERT ... ON CONFLICT (id) DO NOTHING RETURNING id` as a final uniqueness guard. Under the supported protocol, all triage creators serialize on the same Team lock, and the post-lock Task recheck handles the ordinary same-pair race before insertion. If the insert nevertheless returns no row, do not issue a Task `SELECT` while holding Team (that would violate Task → Team lock order for replay). Roll back and restart through the existing-Task replay path, which acquires Task `FOR UPDATE` then Team `FOR NO KEY UPDATE`, and validates the winner. A writer that bypasses the canonical Team lock is a protocol violation; the creator must fail closed rather than treating an unlocked lookup as proof. Only the transaction that inserts the Task may insert the request Event. Cover two-session races on real PostgreSQL; SQLite-only tests are insufficient.

### 4.5 Replay and conflict matrix

| Condition | Required result |
|---|---|
| First authorized request for pair | Create one Task and one request Event |
| Same pair, same immutable pins, same requester | Replay canonical Task; no new Event |
| Same pair, same immutable pins, different independently authorized requester | Replay canonical Task; preserve original requester provenance |
| Same pair, changed policy pin | Conflict; no second Task/Event |
| Same pair, changed matcher/embedding/chunking pin | Conflict; no second Task/Event; if already queued, execution must not proceed on stale pins and the Task must be terminally superseded by a TaskRuntime-owned path (see §7) |
| Same pair, malformed/missing/duplicate request Event | Fail closed; no repair-by-overwrite |
| Same pair, unauthorized caller | Authorization failure before replay result is disclosed |
| Concurrent same-pair requests | One Task and one request Event; loser validates winner |
| Different Team, same Signal | Separate canonical Task, if Signal/Team domain eligibility passes |
| Different Signal, same Team | Separate canonical Task |

### 4.6 Disposition uniqueness is separate

RW4-2 does not create SignalDisposition. RW4-1 must separately enforce one disposition per `(signal_id, team_id)`. A disposition uniqueness constraint does not replace canonical Task uniqueness, and Task uniqueness does not replace disposition uniqueness.

## 4.7 Canonical-identity uniqueness — pending Operator risk disposition

**Status: pending Operator disposition — minimal v1 guarantee recommended.**

**Risk:** the current Task primary key guarantees uniqueness only for the UUID value inserted. It does not enforce one row for a canonical `(team_id, signal_id, identity_version)` tuple if another writer supplies a different UUID. The existing source audit found no persisted `signal_id`/`identity_version` fields on Task and no pair-level unique constraint (see §4.9).

**Minimal v1 guarantee recommended:** retain one narrow supported creator, but do not rely on its check-then-insert behavior for uniqueness. Persist the identity components on Task and enforce a database unique constraint on `(team_id, signal_id, identity_version)`, with a check requiring those components for `task_type = 'triage_signal'`. Keep the deterministic UUIDv5 Task ID, recompute-on-load validation, and one narrow creator; callers cannot supply or override the identity components. Because the audit found no existing equivalent constraint or column, this minimal v1 guarantee **requires a Task-schema migration**. It is not a zero-migration option on current evidence.

**Operator disposition required before Stage B:**
- Approve minimal v1 with the required canonical-identity uniqueness migration, explicitly accepting its migration/preflight/test cost; or
- Do not accept that risk/constraint design and direct a different database-enforced identity representation for review.

A "no-schema-change" approval is not supported by the current audit. It may be reconsidered only if new source/schema evidence demonstrates an existing equivalent database uniqueness constraint. This is a risk acceptance, not a design decision for the spec author or independent reviewer. Status remains pending until the Operator records the disposition. The UUIDv5 namespace, name, golden vector, and v1 identity semantics remain unchanged.

## 4.8 Request-Event exact-one cardinality — pending Operator risk disposition

**Status: pending Operator disposition — minimal v1 guarantee recommended.**

**Risk:** the current Event schema has no unique constraint for one `triage_signal_requested` Event per Task. The transaction protocol can write the Event only in the Task-winning transaction and replay can validate exactly one Event, but those are application/transaction guarantees; the current database schema does not independently enforce the cardinality.

**Minimal v1 guarantee recommended:** accept the bounded transactional invariant only if all Task/Event creation remains in one transaction, the winner-only Event write is covered by the required two-session PostgreSQL race test, replay rejects missing/duplicate/malformed evidence, and the source audit confirms there is one supported writer. This recommendation does not claim database-enforced Event cardinality.

**Operator disposition required before Stage B:**
- Accept the transactional exact-one risk with the stated auditable controls; or
- Require a PostgreSQL partial unique index on `events(task_id)` for `type = 'triage_signal_requested'`, including migration, duplicate-history preflight, and PostgreSQL tests.

If the unique index is selected, its migration cost must be explicitly accepted. This is a risk acceptance, not a design decision for the spec author or independent reviewer. Status remains pending until the Operator records the disposition. This choice does not alter Task identity.

## 4.9 Recorded source/schema audit — evidence for Operator disposition

**Audit scope:** current `main` source/schema at the PR preparation baseline; inspected ORM declarations, matching/index implementation, and existing projection migrations. Findings are evidence for the two risk dispositions and the matching-pin ownership question, not proof of future implementation behavior.

| Area | Inspected source | Recorded finding |
|---|---|---|
| Task canonical identity | `core/models.py`, `Task` model, lines 153–214; `tasks` table | `Task.id` is the primary key; existing unique constraints are `uq_tasks_plan_action` and `uq_tasks_id_team`. Task has no `signal_id`, `identity_version`, or canonical-identity column and no unique constraint over a triage pair/key. **No existing database constraint enforces one Task per canonical Team/Signal identity.** |
| Request Event cardinality | `core/models.py`, `Event` model, lines 240–254; `events` table | `uq_events_id_task` is uniqueness of Event ID/Task attribution, while `ix_events_task_id_type` is a non-unique index. There is no unique or partial unique constraint for `(task_id, type='triage_signal_requested')`. **No existing database constraint enforces exactly one triage request Event per Task.** |
| Signal index configuration | `core/knowledge_index.py`, `CHUNKING_VERSION` and `SignalIndexer.index_signal` | Chunking version is a code constant; the embedding space is obtained from `EmbeddingProvider.current_space()`. The indexer validates the active space during indexing, but this is not a durable single authoritative source-index configuration record used to pin Task creation. |
| Projection metadata | `core/models.py`, `KnowledgeChunk` (line 423 onward); `migrations/versions/0010_knowledge_chunk_projection.py`; `TeamExperienceChunk` (line 491 onward); `migrations/versions/0013_team_experience_projection.py` | Projection rows persist per-row `chunking_version`, `embedding_space_key`, and embedding configuration/provider metadata, with per-projection uniqueness. These are projection facts, not one authoritative immutable source-index configuration record. |
| Team Experience index state | `core/models.py`, `TeamExperienceIndexState` (line 587 onward); migration `0013_team_experience_projection` | The state row tracks publication status and an optional `embedding_space_key`; it does not establish a single authoritative record for both embedding-space and chunking-version ownership. |

**Audit conclusion:** no existing canonical Task identity uniqueness constraint; no existing exact-one triage request Event constraint; and no authoritative source-index configuration record jointly owning the embedding/chunking pins. The expected finding for the latter is therefore "no existing authoritative record", not an inferred future capability. The four matching-pin values remain code-owned for the proposed first release as already stated in §7, pending D4b actual-value acceptance.

**Evidence required to close this audit for Stage B:** preserve these source references in the implementation PR, re-run the schema/source audit against that PR's base and head, record any changed findings, and make the Operator disposition depend on that recorded result. A changed schema or new authoritative index record reopens the corresponding disposition; it must not be silently treated as already accepted.

## 5. Proposed Task envelope

The following is a draft contract, not a frozen implementation instruction. The Task creator captures the applicable Team revision watermark while holding the canonical RW-5 Team lock. The creation-time `as_of` and `team_revision_watermark` are persisted in the immutable `triage_signal_requested` Event payload as the Task's request basis; they are not new columns on the current Task ORM row. This avoids adding Task columns for cutoff metadata. It does not remove the separately required canonical-identity uniqueness migration in the recommended v1 guarantee; the Event-cardinality migration remains a separate Operator choice. RW4-3 must reacquire the same canonical lock chain and revalidate current Team, policy, Signal, and candidate state before matching/commit; it must not treat the creation-time watermark as proof that later state is unchanged.

- `task_type = "triage_signal"`
- `team_id`: Team derived from the trusted grant and canonical Signal/Team validation
- `policy_version`: one validated TeamPolicy version for that Team, selected and pinned while holding the canonical Team lock
- `status = "pending"`
- `objective_id = plan_id = plan_action_id = NULL`
- `max_attempts`: use the existing ordinary Task default unless a specific RW4 proof justifies a different value
- `allowed_writes = []`: the Task has no model/worker business-write grant. Its later SignalDisposition effect, if accepted, is a narrowly specified Kernel-managed effect and is never added to worker `allowed_writes`.
- `budget`: zero model/tool cost for this deterministic application operation; no provider call is part of RW4-2
- `as_of` and `team_revision_watermark`: captured under the canonical Team lock and stored in the immutable request Event payload; do not add Task ORM columns for these cutoff values. This does not waive the canonical-identity uniqueness migration required by the recommended v1 guarantee.
- Task creation and request Event are application-managed; subsequent lifecycle remains exclusively TaskRuntime-owned

The creator does not transition the Task to running, create an Outcome, execute matching, write SignalDisposition, or mutate a Thread.

## 6. TeamPolicy and lock-order boundary

**Implementation sequencing constraint:** RW4-2 is split into two non-overlapping stages to preserve the approved serial stream without violating RW-5. Stage A is this decision/specification work: accept D1/D2 and freeze the creator contract, but do not create production code. Stage B (creator implementation) is deferred until after RW4-1 persistence and the separately authorized RW-5 canonical lock-helper/Team-revision/writer retrofit have landed with their required PostgreSQL proofs. The sequence is therefore RW4-2 design/decision → RW4-1 → RW-5 helper/retrofit → RW4-2 creator implementation → RW4-3. This is a sequencing clarification, not permission to run parallel production streams. No bespoke or temporary helper is permitted.

A new Task must pin the current immutable TeamPolicy selected under the Team lock. The current policy is the row with the greatest `version` for that Team, matching the repository's existing Task-creation selection convention. TeamPolicy versions are immutable and unique per Team/version. If no policy exists, or the greatest-version row is malformed, unsupported, or lacks a valid `rules["sources"]` allowlist, fail closed; do not fall back to an older version. On replay, validate the Task's original pinned version and request Event; do not silently substitute the newest policy or compare the original pin to a newly advanced version.

The repository has no production TeamPolicy publisher. The creator uses the same canonical RW-5 helper as decay and triage; it does not invent a second lock protocol. The helper exposes two paths:

- **First-creation path:** after deriving the canonical Task ID and a non-locking existence probe, if no Task is present, begin the creation transaction and acquire Team `FOR NO KEY UPDATE` first. Under that lock, re-read the Task by canonical ID and revalidate Team, Signal eligibility, current TeamPolicy, and matching pins. If it remains absent, capture `as_of` with PostgreSQL `SELECT clock_timestamp()`, capture the Team revision watermark, then atomically insert the Task and its one request Event. No Thread/Hypothesis locks are taken because creation does not mutate those rows.
- **Existing-Task replay path:** if the preflight probe finds a Task, begin a replay transaction and acquire Task `FOR UPDATE` first, then Team `FOR NO KEY UPDATE`, through the canonical helper. Reload and validate the Task and its request Event while both locks are held. Replay is read-only; it does not rewrite the Task, Event, or first-writer cutoff.

A concurrent creator can pass the initial absent probe while another transaction wins. If, after acquiring Team on the first-creation path, the fresh Task lookup finds that winner, the losing transaction must roll back/release its Team lock and restart through the existing-Task replay path (Task `FOR UPDATE` → Team `FOR NO KEY UPDATE`). It must not acquire Task after Team in the same transaction. This retry is bounded to the single canonical identity and cannot create a replacement Task/Event. The Team lock serializes first creators; the Task lock fences existing-Task replay in the accepted RW-5 order. Every caller is independently authorized before the replay result is disclosed.

The creator is a lock-protected writer for serialization purposes, although it does not mutate world-memory records. It must not use a bespoke Team lock, a temporary lock protocol, or a second helper. The same canonical helper is shared by decay and triage under RW-5 §4.6. The absence of a production TeamPolicy publisher does not remove the lock requirement: any future publisher or same-Team protected writer must serialize against this creator. RW4-3 still reacquires the canonical lock chain and revalidates current eligibility immediately before matching/commit.

## 7. Matching-pin shape, source, and stale-Task fate

Freeze the pin object's **shape** and D4a ownership rule in RW4-2; D4b supplies and accepts the actual values. Version 1 is a strict object with these required fields:

```json
{
  "schema_version": 1,
  "matcher_id": "<D4-defined stable identifier>",
  "matcher_version": "<D4-defined immutable version>",
  "embedding_space_key": "<D4-defined immutable space key>",
  "chunking_version": "<D4-defined immutable version>"
}
```

All four fields are required, non-empty where strings, type-checked, and immutable once the request Event commits. Unknown fields are rejected under schema version 1; adding fields requires an explicit schema-version change. This makes the object extensible without changing Task identity. Serialize it as canonical compact UTF-8 JSON with sorted keys and fixed separators; store the object and its SHA-256 content hash in the immutable request Event. Recompute and compare the hash on every replay/load. The request fingerprint binds this object/hash.

**D4a — pin ownership rule (proposed):** TeamPolicy is not the matching-pin source in the first release and remains unchanged. `matcher_id` and `matcher_version` are code-owned by the single first-release matcher implementation/registry. `embedding_space_key` and `chunking_version` are also code-owned for the first release; the repository has per-projection metadata, but this audit did not establish a single authoritative source-index configuration record that the Task creator can safely pin. Do not infer that per-row metadata is a canonical configuration owner. The creator reads one code-owned, immutable matching-pin declaration while holding the canonical Team lock; execution verifies that the live Signal and candidate projections match those pins and fails closed on mismatch. No generic provider interface, plugin registry, TeamPolicy schema change, or new configuration subsystem is needed for this single implementation. Tests use fixed pin values and pin the canonical object/hash. A later change may move embedding/chunking ownership to the index only after the repository proves a durable, authoritative index configuration record and its consistency/rebuild contract.

**D4b — actual values:** deferred to the matching implementation/decision work. No placeholder, mutable alias, or `latest` resolution is permitted. Experiment A may require a new matching-pin schema version if it changes the pinned representation or field semantics; that does not change Task identity version by itself. Any reprocessing of stale v1 work still requires the separately approved `triage_identity_v2` transition above.

**Queued Task after pin change:** a Task whose recorded pins no longer match the currently accepted execution configuration must not run and must not remain pending/retried forever. RW4-3 must terminally supersede it through TaskRuntime-owned finalization, with a distinct durable superseded reason/outcome. If TaskRuntime does not yet support that terminal category, RW4-3 must define and test it before enabling triage execution; RW4-2 does not add a parallel lifecycle writer. This is a residual implementation dependency, not permission to mutate Task status directly.

The Team revision watermark is separate from this creation-time matching pin object. The Task creator captures it under the canonical Team lock and stores it in the immutable request basis. RW4-3 reacquires the same lock chain and captures/revalidates the current watermark for its execution manifest; it does not overwrite the Task's original cutoff. It is not part of Task identity or semantic replay equivalence.

## 8. TaskRuntime boundary

The adapter creates or resolves a pending Task only. It does not call TaskRuntime admission or write Task lifecycle Events beyond the one request Event.

When execution is separately implemented, TaskRuntime remains the sole authority for admission, attempts, retry, interruption, recovery, and finalization. The RW4-2 implementation must not add a second scheduler/dispatcher or direct lifecycle mutation. A Task type string or Event allow-list entry alone does not constitute a worker implementation.

## 9. Requirement-to-test matrix

Exact test node IDs are to be added after the implementation plan is reviewed. The minimum proof obligations are:

**Frozen first-release test subset:** forged/payload-supplied authority rejection; every-caller authorization including replay; concurrent creation yielding one Task and one request Event using the canonical UUID primary-key race; a separate fabricated-different-UUID/same-logical-tuple insertion proving the composite `(team_id, signal_id, identity_version)` constraint itself rejects the row; different-requester replay preserving original provenance; pin-mismatch conflict; golden UUID; recompute-on-load; dispatcher ignores unsupported `triage_signal` without admission/failure/retry/crash; and migration tests for the Operator-approved canonical-identity uniqueness constraint. The Event partial unique-index migration is included only if separately selected by the Operator. The tested Alembic head must equal the reviewed migration set; do not assert an unchanged head. The existing dispatcher already filters `find_eligible_task()` to `ingest_source` and rejects unsupported types before `TaskRuntime.admit()`; RW4-2 must add a focused regression test proving the complete queued-Task behavior rather than relying on source inspection alone.

| ID | Requirement | Required proof |
|---|---|---|
| RW42-AUTH-01 | Typed trusted principal required | Missing, wrong-type, malformed issuer/subject rejected with no Task/Event |
| RW42-AUTH-02 | Exact Team/action grant required | Missing, wrong-Team, wrong-action, ambiguous grant rejected |
| RW42-AUTH-03 | Caller cannot establish Team authority from request body | Request has no authoritative Team field; grant and canonical DB state determine Team |
| RW42-AUTH-04 | Every replay caller independently authorized | Unauthorized caller cannot learn/resolve existing Task |
| RW42-SCOPE-01 | Canonical Signal/Team/source scope | Missing Signal/Team, inactive Team, domain mismatch, missing source allowlist entry, or any non-exact persisted `origin_url`/`source_type` pair fail closed; exact match passes, while scheme, host-case, path-case, and trailing-slash variants do not match |
| RW42-ID-01 | Canonical Task identity | Stable UUIDv5 across process restart; Team/Signal/task type/identity-version separation; golden UUID for fixed inputs; recompute-and-compare on every Task load/replay |
| RW42-ID-02 | Canonical UUID primary-key uniqueness | Two conforming writers derive the same canonical UUIDv5 for the same Team/Signal/operation/generation; PostgreSQL primary-key conflict rejects the duplicate canonical UUID |
| RW42-REQ-01 | Atomic Task/request Event | Commit both or neither; exactly one request Event |
| RW42-REQ-02 | Replay integrity | Exact one valid Event; verify all immutable fields and fingerprint |
| RW42-REQ-03 | Requester provenance | Different authorized requester replays without rewriting first requester |
| RW42-REQ-04 | Immutable pin conflict | Changed policy/matcher/embedding/chunking pin conflicts |
| RW42-RACE-01 | Concurrent same-pair requests | Two independent PostgreSQL sessions/connections race the same canonical pair using the canonical UUID; assert one Task and exactly one request Event, with the loser validating the winner. Separately attempt a second Task row with a fabricated, different UUID but the same persisted `(team_id, signal_id, identity_version)` tuple; assert that the composite unique constraint itself rejects it. Do not count the primary-key conflict as proof of the composite constraint. |
| RW42-RACE-02 | Different pairs | Different Team/Signal pairs produce distinct Task IDs |
| RW42-RUNTIME-01 | Lifecycle ownership | Creator leaves Task pending; no direct start/finalization/Outcome |
| RW42-DISPATCH-01 | Unsupported Task kind remains queued and ignored | With only a pending `triage_signal` Task, `find_eligible_task()` returns `None`; direct dispatch raises `TaskNotDispatchable` before admission; Task remains pending with zero attempts and no lifecycle Events; dispatcher does not crash or loop |
| RW42-DB-01 | Logical-pair composite uniqueness | The Task-schema migration adds persisted `signal_id` and `identity_version` columns plus the unique constraint on `(team_id, signal_id, identity_version)`. In a separate PostgreSQL proof, insert a row with a fabricated, different Task UUID but the same logical tuple and verify this composite constraint rejects it; demonstrate the composite constraint is responsible, independently of the Task primary key. Migration is required on the current audited schema. |
| RW42-DB-02 | Request Event cardinality disposition | Either prove the accepted transactional exact-one guarantee with the required two-session PostgreSQL test and replay validation, or add/test the Operator-approved partial unique index and migration |
| RW42-SCOPE-02 | No adjacent feature expansion | No dispatcher, scheduler, model worker/provider, disposition persistence, or Thread mutation in RW4-2. Include only the explicitly authorized canonical-identity uniqueness migration required by the recommended v1 guarantee; include the Event partial unique-index migration only if the Operator selects database-enforced Event cardinality. No unrelated schema or runtime expansion |

Tests must include tampered/missing/duplicate Event evidence and rollback/crash-safe transaction outcomes. SQLite-only tests are insufficient for uniqueness-race and PostgreSQL lock claims. The two-session race test is a required, non-optional CI check in the implementation PR, not an optional/manual job or a path-filtered/skipped job. It must use two real PostgreSQL sessions/connections against the supported PostgreSQL version. The implementation PR must record the exact tested head SHA, workflow run ID, required check name, and successful result. A green docs-only CI run, a local-only test, or a test present but not gating CI does not satisfy this requirement. Repository branch protection must require that check before merge. The current draft CI is documentation-only and does not claim to have executed this future concurrency proof.

## 10. Implementation sequence after decision acceptance

1. Complete D1/D2 decision review and accept the creator contract; resolve the two explicit database-enforcement choices in §§4.7–4.8 before implementation authorization.
2. Keep this PR documentation-only. Do not implement or enable the Task creator in this stage.
3. Proceed to RW4-1 persistence only after its independent D3/D5 gate, reviewed proof subset, and explicit authorization.
4. Proceed to the separately authorized RW-5 canonical lock-helper/Team-revision/writer retrofit and prove the helper on real PostgreSQL.
5. Return to RW4-2 creator implementation only after RW4-1 and the RW-5 helper/retrofit have landed; freeze the exact adapter/request/principal types and Task/Event schema, then obtain separate implementation authorization.
6. Implement the narrow creator/replay path test-first, using the canonical helper paths in §6; no new framework or bespoke lock implementation.
7. Run focused tests, Ruff, Mypy, full suite, and disposable PostgreSQL migration/concurrency/rollback tests on the exact tested head.
8. Obtain one named independent review from someone other than the implementation author.
9. Reconcile `PLAN.md` and the authoritative Task/architecture documents only after implementation and evidence are accepted.

## 11. Decision record — D1 accepted; D2 pending Operator disposition

| Decision | Recommendation | Status |
|---|---|---|
| D1 Task-creation authority and trusted invocation | Control Room is the sole application Task-creation authority; typed principal and exact Team/`triage_signal` grant; only `active` Teams; host authentication required before production use and scheduled after R8 test; URL normalization deferred until after R8 test (exact matching meanwhile); greatest-version TeamPolicy under Team lock, fail closed | Accepted 2026-11-24 |
| D2 canonical Task identity | UUIDv5 Task primary key over Team + Signal + operation + `triage_identity_v1`, dedicated namespace; persisted `signal_id` and `identity_version` with database unique constraint on `(team_id, signal_id, identity_version)`; recompute-on-load and golden test | Proposed; not accepted |
| D2 requester semantics | Requester is immutable first-request provenance, excluded from semantic request fingerprint; every replay caller independently authorized | Proposed; not accepted |
| D2 disposition uniqueness | Separate unique `(signal_id, team_id)` constraint in RW4-1 | Deferred to RW4-1 |
| D2 matching-pin shape / D4a | Freeze strict schema-v1 object and canonical content hash; all four values are code-owned in the first release; TeamPolicy remains unchanged | Shape and ownership proposed; actual values deferred to D4b |
| D2 re-triage | One identity generation only; terminal failure and pin change do not create a replacement; later generations require a separately approved identity version | Proposed; not accepted |
| D2 execution watermark | Capture the immutable Task-creation Team revision watermark under the canonical Team lock; RW4-3 separately captures/revalidates the current watermark under the execution lock chain without overwriting the creation cutoff | Proposed; RW4-3 dependency |
| Risk acceptance — canonical Task identity uniqueness | Minimal v1 recommendation: narrow creator plus persisted `signal_id`/`identity_version` and database unique constraint on `(team_id, signal_id, identity_version)`; audited schema requires Task migration | **Pending Operator disposition; migration cost explicit** |
| Risk acceptance — request Event exact-one cardinality | Minimal v1 recommendation: transactional winner-only write, replay validation, source audit, and required PostgreSQL two-session CI test; alternative is partial unique index plus migration | **Pending Operator disposition** |
| RW4-2 implementation | Requires accepted D1/D2, reviewed proof subset, lock-order compatibility, and explicit authorization | Not authorized |

**No implementation authorization is requested or implied by PR #183 or this draft.**
