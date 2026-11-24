# RW4-2 — Trusted Task boundary and canonical identity

**Status:** Draft for Operator decision and specification review. D1/D2 are not accepted by this document. No implementation is authorized.

**Preparation baseline:** `main` after PR #183 squash merge `710ce27830efa465b6af1727c0fa11fb07b38bda` (2026-11-24).

**Authority:** `PLAN.md` remains the sole milestone/authorization status authority. This document is a bounded RW4-2 preparation artifact. PR #183 is housekeeping/documentation reconciliation and is not implementation authorization.

## 1. Purpose and boundary

RW4-2 establishes the trusted host-to-application Task-creation boundary and the canonical identity/replay contract for one `triage_signal` operation over one Signal and one Team.

The intended boundary is:

```text
trusted host authentication/authorization
    -> typed principal + exact Team/action grant
    -> narrow Watch application adapter
    -> immutable canonical triage_signal Task + one request Event
    -> existing TaskRuntime owns all later lifecycle transitions
```

The model is not involved in Task creation, identity selection, authorization, or request replay. This slice does not implement the triage decision/matcher or SignalDisposition persistence.

### In scope for this specification

- D1 trusted principal and exact Team/action grant.
- D2 business, Task, request-provenance, and disposition identities.
- One narrow Task creator and its immutable request Event.
- Database-enforced canonical Task uniqueness, atomic creation, concurrency arbitration, replay, and conflict semantics.
- Exact Task envelope and immutable request pins, subject to the open pin-source question in §7.
- A requirement-to-test matrix for the creator/replay boundary.

### Explicitly out of scope

- SignalDisposition ORM/table, migration, uniqueness constraint, or lifecycle (RW4-1).
- Matching, duplicate classification, Thread selection/creation, or disposition commit (RW4-3).
- Dormant Thread reactivation and RW-5 locking/decay implementation.
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

### Proposed decision

Accept one narrow host-invoked operation that requests triage for one Signal under one exact Team grant.

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

The adapter must:

1. Reject a missing, wrong-type, malformed, or unsupported principal before durable writes.
2. Validate stable issuer/subject identity using the existing canonical principal-identity rules; do not invent a second actor-identity encoding.
3. Require exactly one applicable Team grant for action `triage_signal`. If the principal carries zero or ambiguous applicable grants, fail closed. The host selects the intended Team by issuing the exact grant.
4. Load the canonical Signal and Team and verify the Signal's domain equals the Team's canonical domain. A request cannot override either value.
5. Require the Team state that the accepted Team contract defines as eligible (expected: active); fail closed for missing/inactive Team or missing Signal.
6. Independently authorize every caller before either creating a Task or resolving/replaying an existing canonical Task.
7. Create or resolve only the canonical `triage_signal` Task described in D2.
8. Return a typed result identifying the Task and whether it was newly created or replayed. It does not admit, execute, or finalize the Task.

### Trust limitation

The principal is an in-process trust contract, not a credential. Only a trusted host composition boundary may construct and pass it. No production host composition root currently exists, so the implementation can prove Watch-side grant validation only. End-to-end host authentication remains an external integration proof.

### D1 non-goals

No login, token verifier, user store, RBAC framework, deployed Watch API/CLI, automatic ingestion trigger, scheduler, queue expansion, or TaskDispatcher change.

## 4. D2 — Canonical identity and replay

### 4.1 Keep identities distinct

| Identity | Proposed definition | Purpose |
|---|---|---|
| Business identity | `(signal_id, team_id)` | One Team-specific triage result |
| Task identity | Deterministic UUIDv5 over canonical Team, Signal, and `triage_signal` operation under a dedicated versioned RW4 namespace | One canonical Task for the pair |
| Request provenance | One immutable Task-attributed request Event | Records who requested the first canonical Task and the immutable request basis |
| Disposition identity | Unique `(signal_id, team_id)` | One persisted disposition; implemented separately in RW4-1 |
| Execution identity | Existing Task ID plus TaskRuntime attempt/recovery state | TaskRuntime owns retries and lifecycle; attempts do not create new Tasks |

### 4.2 Canonical Task ID

**Recommendation:** use the deterministic UUIDv5 as `Task.id` itself. The Task primary-key constraint then provides database-enforced uniqueness without adding a redundant identity column or secondary unique index.

The UUIDv5 namespace must be dedicated to RW4 triage and versioned in source/documentation. The canonical name must unambiguously encode:

- canonical Team UUID;
- operation/task type `triage_signal`;
- canonical Signal UUID.

Use a fixed, documented encoding and canonical UUID representation. Do not use string concatenation without a versioned delimiter/encoding contract. Do not reuse the RW-3 `update_thread` namespace.

The Task ID is independent of requester identity, policy version, matcher version, and retry attempt. Those are request provenance/pins or execution state, not business identity. Reusing the same Signal/Team pair must resolve the same Task even if the caller differs.

Because the deterministic ID is the Task primary key, concurrent inserts are arbitrated by PostgreSQL primary-key uniqueness. Application pre-checks alone are insufficient.

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
- `policy_version`
- `matcher_id`
- `matcher_version`
- `embedding_space_key`
- `chunking_version`
- `requested_by_principal` (canonical issuer/subject attribution)
- `request_fingerprint`

The Event envelope supplies Event ID, Task ID attribution, type, and creation timestamp. Avoid duplicating envelope fields in payload unless the existing Event convention requires them; if duplicated, validate exact equality.

The request fingerprint is SHA-256 over canonical compact UTF-8 JSON with a fixed domain tag and schema version. It binds all immutable request pins and canonical Team/Signal/Task identity. It excludes the fingerprint field itself and excludes requester identity: requester identity is provenance, not semantic equivalence. The raw principal credential/token must never be stored.

The Event is immutable after creation. A later authorized caller with the same canonical pair and identical immutable pins resolves the same Task; it does not replace the first requester's provenance or append another request Event.

### 4.4 Atomic creation and concurrency

Proposed transaction behavior:

1. Validate the typed request and principal.
2. Resolve the exact Team grant and canonical Signal/Team relationship.
3. Resolve the canonical TeamPolicy version and immutable matcher-related pins.
4. Derive the canonical Task UUID.
5. Attempt to insert the pending Task with exact Task envelope and no Objective/Plan/PlanAction links.
6. Only the transaction that wins Task insertion writes `triage_signal_requested`.
7. Commit Task and Event atomically.
8. On deterministic Task-PK conflict, load the winning Task and exactly one request Event; validate Task type, Team, policy pin, Event schema, Signal/Snapshot/hash, all immutable pins, and fingerprint.
9. Return replay only if the immutable request is identical. Missing, duplicate, malformed, cross-Team, or mismatched evidence fails closed. The losing transaction never writes another request Event.

The implementation must use a PostgreSQL-safe conflict/race strategy that leaves the outer transaction usable for loading and validating the winner. The exact SQLAlchemy transaction/savepoint pattern must be selected from the existing repository precedent and covered by real PostgreSQL concurrency tests; do not rely on SQLite behavior.

### 4.5 Replay and conflict matrix

| Condition | Required result |
|---|---|
| First authorized request for pair | Create one Task and one request Event |
| Same pair, same immutable pins, same requester | Replay canonical Task; no new Event |
| Same pair, same immutable pins, different independently authorized requester | Replay canonical Task; preserve original requester provenance |
| Same pair, changed policy pin | Conflict; no second Task/Event |
| Same pair, changed matcher/embedding/chunking pin | Conflict; no second Task/Event |
| Same pair, malformed/missing/duplicate request Event | Fail closed; no repair-by-overwrite |
| Same pair, unauthorized caller | Authorization failure before replay result is disclosed |
| Concurrent same-pair requests | One Task and one request Event; loser validates winner |
| Different Team, same Signal | Separate canonical Task, if Signal/Team domain eligibility passes |
| Different Signal, same Team | Separate canonical Task |

### 4.6 Disposition uniqueness is separate

RW4-2 does not create SignalDisposition. RW4-1 must separately enforce one disposition per `(signal_id, team_id)`. A disposition uniqueness constraint does not replace canonical Task uniqueness, and Task uniqueness does not replace disposition uniqueness.

## 5. Proposed Task envelope

The following is a draft contract, not a frozen implementation instruction:

- `task_type = "triage_signal"`
- `team_id`: Team derived from the trusted grant and canonical Signal/Team validation
- `policy_version`: one validated TeamPolicy version for that Team, pinned immutably
- `status = "pending"`
- `objective_id = plan_id = plan_action_id = NULL`
- `max_attempts`: use the existing ordinary Task default unless a specific RW4 proof justifies a different value
- `allowed_writes`: no model/worker business writes; the exact value must be reconciled with the Task matrix's distinction between worker grants and Kernel-managed effects
- `budget`: zero model/tool cost for this deterministic application operation; no provider call is part of RW4-2
- Task creation and request Event are application-managed; subsequent lifecycle remains exclusively TaskRuntime-owned

The creator does not transition the Task to running, create an Outcome, execute matching, write SignalDisposition, or mutate a Thread.

## 6. TeamPolicy and lock-order boundary

A new Task must pin one exact TeamPolicy version. The creator must not silently substitute a newer policy during replay and must fail closed if the pinned policy/request evidence is invalid.

The repository has no production TeamPolicy publisher. Existing RW-3 creator code provides a precedent for locking Team, selecting/validating the newest TeamPolicy for a new Task, and retaining the historical pin on replay. However, the RW-5 shared locking contract is now frozen separately and defines Team revision/lock mechanics for later writer retrofit.

Before implementation, review the exact RW-5 lock contract against the new creator transaction. Do not introduce a second lock helper or independently retrofit RW-5 writers in RW4-2. Record the exact lock mode/order and the reason the creator is compatible with the frozen contract. If compatibility cannot be established without implementing the RW-5 helper, stop and resolve the dependency rather than inventing a temporary lock protocol.

## 7. Open decision: immutable matching pins

D2 requires the request to bind:

- matcher identifier and version;
- embedding-space key;
- chunking version.

The current source audit does not establish an accepted RW4 matcher contract or an authoritative configuration source for all these values. D4 owns the matching representation and remains a later decision gate.

This is a real dependency, not a field-name exercise. Before D2 is accepted for implementation, choose one of these explicit resolutions:

1. Identify existing canonical, versioned values and prove their source, immutability, and availability at Task creation; or
2. Freeze a minimal code-owned version identity for the initial matcher and its embedding/chunking inputs as part of the D4 design, without adding a speculative configuration subsystem; or
3. Narrow the first RW4 implementation contract so the Task does not claim to pin inputs it will not consume, but only after reconciling the D2 proposal and all authority documents.

Do not invent placeholder values, copy current defaults without source evidence, or let the worker resolve “latest” matcher/configuration at execution time. The Task must carry the exact immutable inputs that its eventual deterministic decision consumes.

## 8. TaskRuntime boundary

The adapter creates or resolves a pending Task only. It does not call TaskRuntime admission or write Task lifecycle Events beyond the one request Event.

When execution is separately implemented, TaskRuntime remains the sole authority for admission, attempts, retry, interruption, recovery, and finalization. The RW4-2 implementation must not add a second scheduler/dispatcher or direct lifecycle mutation. A Task type string or Event allow-list entry alone does not constitute a worker implementation.

## 9. Requirement-to-test matrix

Exact test node IDs are to be added after the implementation plan is reviewed. The minimum proof obligations are:

| ID | Requirement | Required proof |
|---|---|---|
| RW42-AUTH-01 | Typed trusted principal required | Missing, wrong-type, malformed issuer/subject rejected with no Task/Event |
| RW42-AUTH-02 | Exact Team/action grant required | Missing, wrong-Team, wrong-action, ambiguous grant rejected |
| RW42-AUTH-03 | Caller cannot establish Team authority from request body | Request has no authoritative Team field; grant and canonical DB state determine Team |
| RW42-AUTH-04 | Every replay caller independently authorized | Unauthorized caller cannot learn/resolve existing Task |
| RW42-SCOPE-01 | Canonical Signal/Team scope | Missing Signal/Team, inactive Team, domain mismatch fail closed |
| RW42-ID-01 | Canonical Task identity | Stable UUIDv5 across process restart; Team/Signal/task type separation |
| RW42-ID-02 | Database uniqueness | PostgreSQL primary-key conflict arbitrates concurrent same-pair creation |
| RW42-REQ-01 | Atomic Task/request Event | Commit both or neither; exactly one request Event |
| RW42-REQ-02 | Replay integrity | Exact one valid Event; verify all immutable fields and fingerprint |
| RW42-REQ-03 | Requester provenance | Different authorized requester replays without rewriting first requester |
| RW42-REQ-04 | Immutable pin conflict | Changed policy/matcher/embedding/chunking pin conflicts |
| RW42-RACE-01 | Concurrent same-pair requests | Real PostgreSQL race yields one Task, one request Event, valid replay for loser |
| RW42-RACE-02 | Different pairs | Different Team/Signal pairs produce distinct Task IDs |
| RW42-RUNTIME-01 | Lifecycle ownership | Creator leaves Task pending; no direct start/finalization/Outcome |
| RW42-SCOPE-02 | No adjacent feature expansion | No dispatcher, scheduler, worker, provider, disposition, Thread, or migration changes in RW4-2 |

Tests must include tampered/missing/duplicate Event evidence and rollback/crash-safe transaction outcomes. SQLite-only tests are insufficient for uniqueness-race and PostgreSQL lock claims.

## 10. Implementation sequence after decision acceptance

1. Accept D1/D2 and resolve §7 pin sources.
2. Freeze the exact adapter/request/principal types and Task/Event schema.
3. Freeze the RW4-2 requirement-to-test subset and verify lock-order compatibility with the accepted RW-5 contract.
4. Obtain explicit Operator authorization for RW4-2 implementation.
5. Implement the narrow creator/replay path test-first, reusing existing principal validation and TaskRuntime contracts; no new framework.
6. Run focused tests, Ruff, Mypy, full suite, and disposable PostgreSQL migration/concurrency/rollback tests.
7. Obtain one named independent review from someone other than the implementation author.
8. Reconcile `PLAN.md` and the authoritative Task/architecture documents only after the implementation and evidence are accepted.

## 11. Decision record — awaiting Operator disposition

| Decision | Recommendation | Status |
|---|---|---|
| D1 trusted invocation | Accept narrow host-invoked adapter with typed principal and exact Team/`triage_signal` grant; production host authentication remains external | Proposed; not accepted |
| D2 canonical Task identity | UUIDv5 Task primary key over Team + Signal + operation, dedicated namespace; Task/Event atomicity and exact replay validation | Proposed; not accepted |
| D2 requester semantics | Requester is immutable first-request provenance, excluded from semantic request fingerprint; every replay caller independently authorized | Proposed; not accepted |
| D2 disposition uniqueness | Separate unique `(signal_id, team_id)` constraint in RW4-1 | Deferred to RW4-1 |
| D2 matching pins | Must identify authoritative versioned source before implementation; D4 dependency unresolved | Open |
| RW4-2 implementation | Requires accepted D1/D2, reviewed proof subset, lock-order compatibility, and explicit authorization | Not authorized |

**No implementation authorization is requested or implied by PR #183 or this draft.**
