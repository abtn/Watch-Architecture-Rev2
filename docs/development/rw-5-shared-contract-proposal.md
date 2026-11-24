# RW-5 Shared Contract — Freeze Proposal

**Decision status:** Proposed for Operator review; not yet frozen.
**Document purpose:** settle the shared time, decay, locking, replay, and Task-production contracts before RW-5 implementation and before RW-4 dormant-Thread reactivation.
**Baseline:** `main` at `5aecf096b077ab34bc7c8fb09cb750a59a19c335` (PR #181 merge).
**Scope of this proposal:** documentation and source-backed design only. It does not authorize production code, schema changes, migrations, scheduler deployment, provider calls, persistent-database operations, or RW3.4 acceptance.

## 1. Decision requested

Approve or correct the proposed contracts in §4. The intent is to freeze the shared RW-5/RW-4 concurrency boundary once, then implement one stream at a time:

1. RW-5 shared contract freeze.
2. RW-5 implementation and proof.
3. RW4-1 SignalDisposition persistence.
4. RW4-2 triage Task identity and TaskRuntime boundary.
5. RW4-3 deterministic matching/commit, initially without dormant-Thread reactivation.
6. RW4-4 bounded Context retrieval after its own gates.
7. D6-gated dormant-Thread reactivation and RW4-5 integrated proof.

RW4-1 and RW4-2 are not to run in parallel. Each implementation stream requires its own explicit authorization and reviewed proof subset. RW4-0 remains an umbrella design-closure milestone, not a blanket implementation authorization.

## 2. Source baseline and constraints

The proposal is grounded in the post-PR-181 source tree:

- `core/models.py:856–900`: Thread lifecycle and `last_updated_at`.
- `core/models.py:900–957`: Hypothesis status, confidence, and `last_touched_at`.
- `core/models.py:153–210`: Task has a UUID primary key, a Team/policy pin, and a database-generated `created_at` (`server_default=func.now()`); it has no generic Task idempotency-key column.
- `core/models.py:957–1020`: ConfidenceChange cause, optional EvidenceLink, generic `created_by_task_id`, idempotency key, and creation time.
- `migrations/versions/0019_rw1_world_memory.py:379–446`: ConfidenceChange persistence, cause checks, and indexes. Its existing uniqueness is scoped to `(created_by_task_id, idempotency_key)`; it does not enforce the same logical decay step across distinct Tasks. The schema has no dedicated `decay_task_id`.
- `core/world_memory.py:1812–1835`: Task-row locking in the existing world-memory commit.
- `core/world_memory.py:1926–2005`: Team, Thread, and Hypothesis locking in the existing commit.
- `core/world_memory.py:2260–2271`: accepted support/challenge evidence updates `last_touched_at`, including evidence that does not necessarily change confidence.
- `core/world_memory.py:2331–2355`: evidence-caused ConfidenceChange persistence.
- `core/task_runtime.py:393–535`: Task then Team locking during admission.
- `core/task_runtime.py:817–835`: Task locking during finalization.
- `core/task_runtime.py:1423–1540`: Task locking and interrupted recovery.
- `core/policy.py:1–60`: narrow policy parsers exist; there is no decay-policy parser.
- `core/dispatcher.py:1–22,55–65`: TaskDispatcher supports configured-source `ingest_source` only; it is not a general scheduled-task runner.
- `docs/tasks.md` (`apply_decay`): current specification calls for a scheduled batch Task, per-Hypothesis handling, and a summary Event. That is a requirement, not evidence of an implemented scheduler or worker.
- `docs/domains.md:20–31`: decay policy concepts are described, but the policy parser and runtime path are absent.

The source audit did not run tests, migrations, provider calls, or database operations. Any claim that an existing schema or service is sufficient must be proven by focused tests before implementation is considered complete.

## 3. RW3.4 residual mapping

The ledger remains **28 PASS / 7 PARTIAL / 0 OPEN**. This mapping classifies whether a residual is touched by the proposed RW-5/RW-4 work; it does not change its status or broaden the sequencing exception.

| Residual | RW-5 relationship | RW-4 relationship | Carry-forward limit |
|---|---|---|---|
| `RW-REQ-01` — production host authentication/composition absent | Conditional: the external host that requests a decay Task must be trusted, but RW-5 must not invent the missing production composition root. | Directly touched by RW4-2's host-authorized triage Task boundary. | Test Watch-side authorization only. Keep production authentication/composition an external integration boundary. |
| `RW-POL-01` — production TeamPolicy publisher and publisher/creator lock orders unproven | Directly touched by decay Task policy pinning and the shared Team serialization rule. | Directly touched by RW4-2 Task creation and policy pinning. | Prove the implemented Task-creator lock order. Do not claim a production publisher exists or implement one as incidental RW work. |
| `RW-CTX-06` — broader Context identity/recovery-state cross-product incomplete | Unrelated unless RW-5 changes the shared TaskRuntime Context/recovery identity path. | RW4-4 has its own Context provenance contract, but that does not automatically close this update_thread-specific ledger row. | Keep PARTIAL. Add only directly relevant proof if the exact shared path changes. |
| `RW-REPLAY-01` — duplicate write outcomes across replay states not exhaustive | Directly touched by required history-writer revision stamping/replay behavior and by any TaskRuntime-owned atomic business/terminal transaction. | Directly relevant to RW4-3's receipt and business-commit replay protocol. | Prefer one atomic TaskRuntime/Kernel commit. If a separate marker is unavoidable, prove its exact replay states; do not import an unrelated exhaustive Cartesian matrix. |
| `RW-RT-02` — 45-second update_thread deadline versus strictly-greater-than-60-second recovery threshold | Unrelated to deterministic decay unless the global recovery timing contract is changed. | Unrelated to triage unless it changes that same recovery timing path. | Preserve the existing boundary. Do not change global recovery timing to make an unrelated test reachable. |
| `RW-REC-01` — full locked Session/Task/attempt matrix incomplete | Directly touched by the existing writer's revision/clock stamping under Task/Team/Thread/Hypothesis locks and by TaskRuntime attempt fencing/finalize-in-session work. | Relevant to triage concurrency and any separately authorized reactivation path. | Add targeted lock-order, stale-attempt, and race proofs only. Do not claim the full matrix is closed. |
| `RW-RP-01` — repeated recovery across all duplicate Event/write outcomes incomplete | Directly touched by proving history revision/clock is not advanced twice on repeated commit/recovery, and by unknown-commit/TaskRuntime terminalization behavior. | Directly relevant if RW4-3 uses its proposed separate receipt/commit protocol. | Prefer atomic commit. If a separate recovery boundary remains, test its specific repeated-recovery outcomes; retain unrelated residuals. |

All seven rows remain PARTIAL. `RW-REQ-01` and `RW-POL-01` remain external integration boundaries. The duplicate/future terminal-marker behavior remains fail-closed: do not weaken integrity checks to force terminalization.

## 4. Proposed RW-5 shared contract

### 4.1 Task production, identity, and authority

**Proposed contract:**

- RW-5 core provides a typed, idempotent application boundary that creates one `apply_decay` Task for one Team, pins the immutable request and TeamPolicy version, and persists the request Event atomically.
- The creator derives Team authority from a trusted host boundary, never from model output or an untrusted worker payload. Production host authentication/composition remains an external integration boundary; this proposal does not invent it.
- A periodic scheduler/host trigger is a separate integration slice, **RW5-P**. It may invoke the typed creator but may not mutate world memory, execute Tasks, or become a second runtime. The existing TaskDispatcher remains `ingest_source`-only.
- RW-5 core acceptance covers deterministic creation/execution from a valid typed invocation. It does not claim autonomous periodic operation. **RW5-P is required before foundation exit/R8 can claim scheduled decay is operational.**

The Task table has no generic idempotency-key column. The proposed database identity is a deterministic UUIDv5 Task primary key from a dedicated, versioned namespace and canonical `(team_id, operation, trusted_schedule_slot)`. The schedule slot is trusted host metadata, not model-selected data. For a manual invocation, use an equivalent caller-generated idempotency token in a distinct, explicitly typed identity form. The captured `as_of` timestamp is deliberately **not** part of the Task identity: it is generated only during creation and must be reused by replay.

The database primary-key constraint arbitrates concurrent creators. A creator that finds the deterministic Task ID validates its immutable request and returns the original Task, original `as_of`, and original policy pin—even if the current TeamPolicy has since advanced. A changed semantic request under the same identity is a conflict. The request Event and Task row are one transaction. Do not take an existing Task row lock after acquiring the Team lock; validate immutable request data without reversing TaskRuntime's Task → Team lock order. Golden vectors, unique-conflict races, and concurrent PostgreSQL tests are required.

The Kernel/application boundary must enforce that only the typed creator can create `apply_decay` Tasks. A convention or worker-side check is insufficient. No generic Task-creation permission is added.

### 4.2 Authoritative time: immutable instant plus serialized history watermark

**Decision proposed:** after acquiring the Team serialization lock, capture one UTC as_of from PostgreSQL with clock_timestamp() during typed Task creation and persist it in the immutable canonical Task request/Event before releasing the lock. The Task fingerprint includes it. Do not use Task.created_at: PostgreSQL now() is transaction-start time and the Task may wait in a queue.

**A wall clock is not an ordering key.** clock_timestamp() can move backwards after a host clock adjustment. Separate elapsed-time measurement from history ordering:

- Add a database-enforced, monotonically increasing per-Team world_memory_revision (or prove an equivalent). Every accepted write that changes Hypothesis confidence or adds an eligible supporting/challenging EvidenceLink acquires the Team lock, increments the revision once for that transaction, and persists that revision on affected immutable history records and corresponding Events.
- Task creation captures both as_of and the current Team revision watermark while holding the same Team lock. The watermark defines which committed history existed at the Task's serialized cutoff; as_of is used for elapsed-window arithmetic.
- Persist a per-Team non-decreasing database clock value under the Team lock, computed as GREATEST(clock_timestamp(), last_team_clock_at). The captured as_of and accepted history timestamps use that value. This prevents a backward clock step from moving logical Team time backwards. It does not protect against an incorrect forward jump; clock health remains a deployment assumption/monitoring concern, and a detected discontinuity must fail closed rather than trigger retroactive catch-up.
- Team revision, not timestamp sorting or UUID ordering, is the primary order for accepted history. A stable record ID breaks ties among multiple records written in the same Team transaction/revision.

This is an explicit schema/design cost, not an assertion that the current schema already provides it. If a smaller database-enforced mechanism proves the same non-decreasing clock and serialized history watermark, substitute it with evidence before freeze. Do not fall back to wall-clock-only ordering.

- The creator obtains both values from PostgreSQL only after it owns the Team lock; callers and models cannot supply or override them. Hold the lock through Task/request Event commit.
- Persist exact UTC precision and immutable request fields. The request record needs a database-enforced update/delete guard; if Event does not provide that property, add the smallest guard required.
- Every Hypothesis decision, retry, and interrupted recovery uses the exact persisted as_of, Team revision watermark, epoch, and history manifest. Execution never recomputes them.
- The deterministic Task identity excludes as_of; replay loads and validates the winning Task request and reuses all original pins.
- Provide a test-only deterministic database-clock seam. Production callers must not gain a caller-controlled timestamp parameter.
- A record with a Team revision above the Task watermark is outside that Task's historical view, even if its wall-clock timestamp is earlier. Never clamp or silently include it.

Replay is reconstruction of the original decision. The database-captured instant measures elapsed time; the Team revision establishes serialized history membership.

### 4.3 Historical evidence is authoritative; current-state fields are only accelerators

**Decision proposed:** reconstruct evidence age from immutable accepted evidence history. Hypothesis.last_touched_at is a mutable current-state cache/prefilter, not the authority for a past decay decision. Accepted supporting or challenging EvidenceLinks are the authoritative evidence-touch records. An accepted touch resets evidence age even if confidence does not change.

**Source-backed history gap:** the existing world-memory commit path uses application datetime.now(timezone.utc) for committed_at and stamps Hypothesis, EvidenceLink/ConfidenceChange, and Events with it. ORM server defaults on other insert paths use PostgreSQL now() (transaction-start time). Neither is a database-captured post-lock acceptance instant. The current Hypothesis creation path sets mutable confidence='low' and records confidence='low' in the immutable hypothesis_created Event, but creates no initial ConfidenceChange row. The Event is the only existing immutable record of the initial band; its timestamp is not a reliable database ordering key.

For new accepted evidence touches and confidence transitions, persist the Team revision plus one database-captured, non-decreasing acceptance/transition instant after acquiring the Team lock. The same values must appear on the history row and its Task-attributed Event. Do not treat existing created_at values as exact serialized acceptance times.

**Required compatibility prerequisite:** the current supported Hypothesis evidence/confidence writer is WorldMemoryCommitService. It currently uses application-captured committed_at and does not populate a Team history revision. Before RW-5 decay can execute, this existing writer must be narrowly adapted to increment the Team revision once per accepted commit, obtain the non-decreasing database clock after its existing Task → Team → Thread → Hypothesis locks, and persist the same revision/instant on Hypothesis, EvidenceLink, ConfidenceChange, and their Task-attributed Events. A replay that reuses an existing committed result must not increment the revision or rewrite history. This is a required history-writer compatibility slice, not the separate global before_flush guard retrofit. It touches a shared RW3.4 path and needs its own explicit scope/review against RW-REC-01, RW-REPLAY-01, and RW-RP-01. Until it is implemented and proven, RW-5 may not treat new Hypothesis history as revision-authoritative or run decay Tasks.

**Initial state and legacy cutover are mandatory:**

- For a Hypothesis created after the new epoch begins, persist its initial confidence band (currently low) in the immutable creation Event together with its Team revision and canonical acceptance instant. A new initial ConfidenceChange row is not required if the immutable creation Event is sufficient and its contract is enforced.
- At first RW-5 activation, create an immutable per-Hypothesis epoch baseline for every existing Hypothesis: current confidence band, epoch ID/version, baseline Team revision, non-decreasing database baseline instant, and the last eligible EvidenceLink ID and ConfidenceChange ID included. This baseline starts that Hypothesis's decay history; do not retroactively decay legacy time or infer a low-confidence interval from mutable current state.
- If current confidence cannot be reconciled with available history, or the baseline cannot be created under the Team lock, defer that Hypothesis with a stable reason. Do not guess the initial band.
- Every Task request pins the epoch ID/version and a bounded, canonical per-Hypothesis history-watermark manifest: Hypothesis ID, baseline reference/hash, last eligible EvidenceLink ID, last ConfidenceChange ID, Team revision, and confidence band considered. Persist the manifest or its immutable reference/hash with the Task request so retry/recovery validates the same inputs rather than recomputing a new decision.
- At execution, after acquiring the canonical locks, compare each Hypothesis's current eligible history against its pinned manifest. A newer supporting/challenging EvidenceLink after the Task watermark resets the baseline and makes that Hypothesis ineligible at the older as_of; record a stable skip reason. A newer ConfidenceChange, changed current confidence, changed lifecycle status, or an advanced Team decay epoch makes the pinned decision stale; defer that Hypothesis/Task rather than overwrite newer state. Unrelated Team revisions do not invalidate a Hypothesis when its own relevant history is unchanged. A Task from a superseded epoch must never commit under the old policy.
- A new TeamPolicy version or decay-algorithm version starts a new epoch at an explicit Team revision and baseline instant. There is no retroactive catch-up across policy/algorithm epochs. Include epoch ID/version, policy version, algorithm version, canonical evidence-touch identity, and window ordinal in the cross-Task decay idempotency key. This prevents a changed window definition from reusing or suppressing an old epoch's step.

Legacy EvidenceLink/ConfidenceChange rows without trustworthy Team revision and post-lock timestamps are covered only by the one-time conservative baseline. No historical catch-up is inferred from their transaction-start or application timestamps.

**No-new-column is not a freeze assumption.** The epoch baseline, Team revision, and non-decreasing clock need a database-enforced representation. Existing EvidenceLink/ConfidenceChange history may be retained only if property/replay tests prove exact reconstruction across touches with and without confidence change, same-time distinct touches, duplicate replay, transitions into/out of low, catch-up, and evidence arriving after a Task cutoff. Add the smallest immutable field/table needed if those proofs fail; do not preserve a no-migration assumption at the expense of correctness.

A new temporal EvidenceLink index is not assumed. Measure bounded history queries and query plans on a representative disposable PostgreSQL fixture. Add the smallest index only if measured cardinality/latency or bounded-work requirements demand it.

**Window semantics:** use half-open elapsed windows with an inclusive due boundary:

due(k) iff as_of >= anchor + k * W

Use integer/microsecond arithmetic over timezone-aware UTC instants. The anchor is the latest accepted evidence-touch instant, not a value mutated by decay. A newly accepted touch starts a new window sequence within its current epoch. Catch up one actual confidence-band transition per elapsed window, in ordinal order; write one ConfidenceChange per actual transition, with no no-op rows after the lowest band. The same Task/replay must not apply a window twice. A deterministic, versioned key identifies (team_id, hypothesis_id, epoch_id, policy_version, algorithm_version, canonical evidence-touch identity, window ordinal), and a database uniqueness constraint must arbitrate duplicate application across different Tasks.

### 4.4 Confidence transition semantics

- Every actual confidence-band transition creates one ConfidenceChange with `cause_kind="decay"`, the current decay Task attribution, and the deterministic per-window idempotency key.
- Decay never rejects, supersedes, deletes, or otherwise changes Hypothesis lifecycle status. It never updates `last_touched_at`.
- Do not create no-op ConfidenceChange rows once the lowest band is reached.
- Missing, malformed, unsupported, or internally inconsistent pinned policy fails closed; do not silently select a newer policy or guess a default.
- The supported policy vocabulary, defaulting rules, and exact confidence-band transition table must be frozen against the existing domain specification before implementation. The absence of a decay parser in `core/policy.py` is a source gap, not permission to add a generic policy framework.

The exact interaction between catch-up windows and policy changes is pinned by the Task's original TeamPolicy version. A replay cannot adopt a newer policy midway through catch-up.

### 4.5 Dormancy is out of scope until D6 recovery exists

**RW-5 first release performs confidence decay only. It does not transition Threads to `dormant`.**

Dormancy is an irreversible lifecycle transition for the current delivery sequence: it can make a Thread unavailable to the first RW-4 matching path, while the authorized reactivation/recovery path is not yet implemented. The non-vacuous rule (“at least one active Hypothesis, and every active Hypothesis is low and beyond the accepted inactivity threshold”) is not sufficient by itself. A lifecycle transition must not ship before its recovery path exists.

- RW-5 must not change Thread status or Thread lifecycle/activity timestamps and must not emit a dormancy Event.
- Do not add dormancy as an optional policy flag in the first RW-5 release.
- Dormancy requires D6 acceptance, a durable RW-4 reactivation path, and an explicit recovery/reconsideration behavior for decay-first and triage-first outcomes.
- If dormancy is later authorized, reconstruct low-confidence age from accepted evidence and ConfidenceChange history as described above; never infer it solely from mutable current-state fields.

This is a hard scope boundary, not a deferred implementation detail within RW-5.

### 4.6 Shared lock order and database-enforced concurrency

**Proposed canonical lock order and modes:**

1. Lock the current Task row with FOR UPDATE; validate running status, exact attempt number/start, immutable request, policy pin, and absence of a newer attempt. Hold this lock through commit/rollback.
2. Lock the Team row with FOR NO KEY UPDATE as the per-Team writer serialization point.
3. Lock affected Thread rows one at a time in ascending canonical ID order with FOR NO KEY UPDATE.
4. Lock affected Hypothesis rows one at a time in ascending canonical ID order with FOR NO KEY UPDATE.
5. Re-read and revalidate Team ownership, Thread/Hypothesis membership and lifecycle, current history watermark, policy/epoch pin, and current-attempt preconditions under those locks.
6. Only then flush child EvidenceLink/ConfidenceChange rows and Task-attributed Events through the accepted TaskRuntime/Kernel transaction boundary.

The lock-mode choice is deliberate. PostgreSQL foreign-key checks take FOR KEY SHARE protection on referenced parent rows. FOR UPDATE conflicts with that protection and can deadlock with a child-first writer; FOR NO KEY UPDATE conflicts with another writer's FOR NO KEY UPDATE (so it still serializes same-Team writers) while remaining compatible with FK FOR KEY SHARE. The disposable spike in tests/test_rw5_postgres_lock_spike.py tests this behavior on real concurrent PostgreSQL sessions. Task rows remain FOR UPDATE because Task attempt/lifecycle fencing is an update boundary. Do not use a set-based ORDER BY ... FOR UPDATE as proof of lock acquisition order: the canonical helper must acquire each Thread/Hypothesis row individually in sorted ID order.

The Task creator has no Task row to lock yet. It acquires Team FOR NO KEY UPDATE, captures as_of and the Team revision watermark, then inserts Task + request Event in that same transaction. It must not discover/lock a Thread or Hypothesis before acquiring Team.

**One canonical helper is mandatory for new RW-5/RW-4 writers.** No per-writer equivalent lock implementations. The helper owns Task fencing (when a Task exists), Team lock, sorted Thread/Hypothesis locks, the session lock registry, and under-lock revalidation. Candidate discovery may be read-only before locking; after Team/Thread locks, reload the candidate and eligible Hypothesis set. If a candidate moved or membership changed, restart discovery or defer; never act on stale discovery.

The session lock registry records exact Task/Team/Thread/Hypothesis locks held by the current SQLAlchemy Session. A before_flush guard checks protected ORM inserts/updates/deletes against that registry for new RW-5/RW-4 paths only. Acquire locks inside session.no_autoflush and do not stage child rows before the helper completes, so autoflush cannot take FK locks before the intended order. The guard must reject a Hypothesis thread_id move through ordinary updates; a future move needs a separately specified operation.

**Protected-write matrix (Task lock is required for both child rows because both have Task foreign keys):**

| Operation | Required locks before ORM flush |
|---|---|
| Create apply_decay Task/request | Team |
| Update Thread | Task → Team → Thread |
| Insert Hypothesis | Task → Team → Thread |
| Update Hypothesis | Task → Team → Thread → Hypothesis |
| Insert Hypothesis-subject EvidenceLink (originating_task_id) | Task → Team → Thread → Hypothesis |
| Insert ConfidenceChange (created_by_task_id) | Task → Team → Thread → Hypothesis |

EvidenceLink rows with subject_kind='evaluation' are not Hypothesis evidence-touch writers and are outside this RW-5 protected-write matrix. Thread creation is not part of RW-5; any later Thread creator must serialize on Team and use a database uniqueness constraint for canonical creation identity because no Thread row exists to lock.

**Scope of enforcement and writer inventory:**

- The helper and lock registry/guard are mandatory for every new RW-5/RW-4 writer introduced under this contract. The guard is activated only for those new-path Sessions; do not retrofit a global enforcing before_flush listener onto all existing production sessions as part of RW-5 freeze.
- The generic existing-writer guard retrofit is a separately gated follow-up: instrument the current production session factory in log-only mode, run the full suite and supported integration paths, classify every protected-table write that lacks registry evidence, then remediate and switch to enforcement in a later reviewed step. The maintained full writer inventory must be generated/updated from this run, not asserted from memory or this bounded source audit. This follow-up is distinct from the required narrow WorldMemoryCommitService revision/clock adaptation above.
- before_flush does not intercept raw SQL, SQLAlchemy Core bulk DML, or other database clients. Database-role/privilege enforcement for scripts and external writers is a named deployment residual, not part of this RW-5 code contract. Do not claim the ORM guard is a complete database security boundary.
- The bounded source audit found the current WorldMemoryCommitService locks Task → Team → Thread → Hypothesis using FOR UPDATE, then writes Hypothesis EvidenceLinks and ConfidenceChanges; it is the current relevant writer path. Its timestamp/revision adaptation is a required precondition before decay execution, separately scoped and reviewed as shared RW3.4-adjacent work. The generic log-only guard retrofit remains a separate follow-up. The new FOR NO KEY UPDATE helper serializes against the existing Team FOR UPDATE lock; FK compatibility improvement applies to the new helper and any writer later migrated to it.

The Team lock intentionally serializes writes for one Team. Measure contention before considering a narrower scheme. A bounded lock timeout is required. PostgreSQL deadlock 40P01 and lock-not-available/lock-timeout 55P03 are retryable Task failures after rolling back the entire transaction. Do not swallow them as per-Hypothesis skips. Application prechecks improve diagnostics; database uniqueness/constraints and row locks remain the concurrency authority.

### 4.7 Decay/triage race outcomes

The exclusive Team lock serializes decay and triage writers for the same Team. Each operation reloads and revalidates canonical rows and accepted history after acquiring it.

- **Triage commits first:** the later decay operation observes the newer EvidenceLink/revision under the Team and Hypothesis locks. Because the touch is after the Task's pinned history watermark, that Hypothesis is skipped as not due at the older `as_of`; the Task never writes a stale confidence decrement over the newer evidence.
- **A newer confidence transition or epoch commits first:** a decay Task with an older per-Hypothesis manifest or superseded epoch defers rather than overwriting the new confidence state or applying an old policy window.
- **Decay commits first:** triage observes the committed confidence state. Before D6 and a durable reactivation/recovery path exist, dormant-Thread behavior is not reachable because RW-5 does not create dormant Threads.
- **After D6:** a separately authorized reactivation path must validate current Team, Thread, Hypothesis, and evidence state under the same lock order and emit at most one reactivation Event. It must also define how decay-first state is reconsidered; merely changing `dormant → active` is not enough.
- A losing concurrent/replayed request loads or validates the canonical committed result; it cannot append a duplicate ConfidenceChange or lifecycle Event.

Prove both race orders with disposable PostgreSQL. Unit tests that mock away row locks do not prove serialization.

### 4.8 Task transaction, recovery, and per-Hypothesis failures

**Atomicity is a required design proof, not an assumption about the current APIs.** The existing WorldMemoryCommitService.commit_model() opens its own transaction, while TaskRuntime.finalize() opens a separate transaction. commit_model_in_session() provides a possible shared-session seam, but the current finalization API does not itself prove that business writes, summary Event, Outcome, and terminal Task state can commit atomically. A TaskRuntime-owned finalize-in-session extension may touch shared RW3.4 code; it is not an incidental RW-5 refactor and is not authorized by this proposal.

Before implementation, separately review the exact shared-runtime change against the seven RW3.4 residuals. The current impact map is: RW-REC-01 (Task/attempt lock and fencing cases), RW-REPLAY-01 (atomic write/replay behavior), and RW-RP-01 (unknown-commit/repeated recovery) are directly touched and require targeted RW-5 proof while remaining PARTIAL outside that proof. RW-CTX-06 is not touched unless Context identity/recovery code changes; RW-RT-02 is not touched unless the 45s/60s timing contract changes; RW-REQ-01 and RW-POL-01 remain external host-authentication and policy-publisher boundaries. No RW3.4 row is closed by this mapping. If the required TaskRuntime change exceeds this narrow boundary, stop for a separate RW3.4 impact review and explicit authorization.

The accepted target is one transaction that commits:

- all eligible decay ConfidenceChanges;
- the single deterministic summary Event;
- the Task Outcome; and
- the terminal Task state.

Task fencing is mandatory: lock Task FOR UPDATE, validate status='running', exact current attempt and its start record, immutable request/fingerprint and policy/epoch pins, and absence of a newer attempt; hold the lock through the entire transaction. Use PostgreSQL READ COMMITTED only after the Team-lock coverage contract is satisfied: every supported writer that changes relevant history must acquire the same Team serialization lock before mutation, and every new RW-5/RW-4 writer must use the canonical helper. After waiting for Team, perform fresh statements to reload history and membership under the lock. Do not use REPEATABLE READ with a snapshot established before waiting for Team; if a future design chooses SERIALIZABLE, classify 40001 as a whole-transaction retry.

Bound batch size, transaction duration, and lock duration. Deterministic ineligibility may be skipped only with an explicit stable reason in the summary. Integrity violations, ownership conflicts, stale attempts, malformed policy, lock timeout/deadlock, and infrastructure/transaction errors abort and roll back the entire transaction; do not swallow them as per-Hypothesis skips.

**Unknown commit resolution:** if the connection is lost during commit, reconnect and inspect only the atomic terminal marker: Task terminal status plus its matching terminal Outcome. If both agree with the pinned Task/attempt/result, treat the transaction as committed. If neither exists, let TaskRuntime's existing retry/recovery policy proceed. If one exists without the other or the pair conflicts, fail closed as inconsistent. Do not re-query/reconstruct the expected business-write set in recovery; the same transaction makes those writes atomic, and tests verify their presence/absence. Database uniqueness on the decay-step identity remains the second line of defense against duplicate writes.

Inject failures before writes, after business writes, before summary Event, and before terminal Task state. Each failure must prove rollback of business rows, Event, Outcome, and Task state. Do not add savepoints unless an accepted requirement demonstrates that individual Hypothesis failures must be isolated.

Classify PostgreSQL errors after rolling back the entire transaction: 40P01 deadlock and 55P03 lock timeout/not-available are retryable; 40001 is retryable only if SERIALIZABLE is deliberately selected; 57014 statement cancellation/timeout is separately classified and is not automatically a lock retry. Never continue in a failed transaction or commit a partial batch.

If a clean single-transaction TaskRuntime path cannot be implemented, stop. A separate durable marker/receipt plus recovery protocol requires a new design and explicit review; do not claim atomicity while using two transactions. TaskRuntime remains the only lifecycle and interrupted-recovery authority.

### 4.9 Bounded work

The Team batch must have explicit maximum Hypothesis count, maximum EvidenceLink-history rows examined, and a bounded transaction/lock duration. Query only the canonical Team scope; detect overflow before mutation and fail/defer the Task rather than silently truncating a candidate or history set. Measure query plans and cardinality on a representative disposable PostgreSQL fixture. Any required pagination must preserve one immutable `as_of`, one pinned policy, and deterministic ordering across the entire Task. The summary Event reports deterministic counts and explicit overflow/failure outcome without leaking unbounded payloads.

### 4.10 RW-5 first-release acceptance boundary

RW-5 first release means: typed idempotent Task creation; database-captured immutable request `as_of`; pinned policy; history-authoritative confidence decay; database-enforced uniqueness and immutable records; shared lock-order proof; atomic TaskRuntime/Kernel business commit and terminalization; bounded work; deterministic retry/replay. It does **not** include periodic scheduling (RW5-P), Thread dormancy, reactivation, or autonomous lifecycle management. RW5-P remains required before foundation exit/R8 can claim periodic decay is operational.

## 5. Schema and migration posture

Prefer the existing Thread, Hypothesis, ConfidenceChange, Task, and Event records. In particular:

- Do not add a dedicated `decay_task_id` column merely to duplicate the generic Task attribution already present on ConfidenceChange.
- Do not use `last_touched_at` as historical authority. Avoid a new age/streak column only if accepted EvidenceLink and ConfidenceChange history—with database-captured post-Team-lock acceptance/transition instants—reconstructs the exact baseline and streak under property/replay tests, while `last_touched_at` is verified as a cache. Add the smallest immutable timestamp/touch identity field if existing records cannot safely carry that information.
- Expect a minimal partial unique index for cross-Task decay-step idempotency unless an equally strong database-enforced alternative is demonstrated; the current Task-scoped unique constraint is not sufficient by itself.
- Use the existing Task UUID primary key for deterministic Task-creation identity if golden-vector and concurrent-creation tests validate the proposed UUIDv5 scheme; add no generic idempotency column by default.
- Do not add Thread embeddings, new Domain policy subsystems, or a scheduler/runtime as part of RW-5.
- A no-migration conclusion is valid only after database-backed tests prove the existing constraints enforce the contract. If a required uniqueness or integrity invariant is not enforceable, propose the smallest migration explicitly rather than relying on application prechecks.

## 6. Required proof before RW-5 implementation exit

| Proof area | Required evidence |
|---|---|
| Clock/history cutoff | Task pins database-captured non-decreasing as_of, Team revision watermark, decay epoch, policy/algorithm versions, and immutable per-Hypothesis history-watermark manifest; replay reuses the exact pins. Legacy data starts from a conservative immutable cutover baseline with no retroactive catch-up. |
| Boundaries | Before, exactly at, and after each decay-window boundary; timezone/DST-independent UTC behavior. |
| Evidence reset | Supporting/challenging evidence resets age even without confidence change; mentions/rejection/decay do not; post-Team-lock database acceptance instants are ordered correctly against Task `as_of`; legacy rows have an explicit conservative rule; old decay keys cannot suppress a new baseline. |
| Catch-up | Multiple elapsed windows produce the defined sequence once; low-band floor creates no no-op writes. |
| Attribution | Every decay ConfidenceChange has exactly one valid decay Task cause; no EvidenceLink cause; cross-Team/wrong-Task attribution rejected. |
| Dormancy | Excluded from RW-5 first release. D6 plus a durable RW-4 reactivation/recovery path and separate authorization must precede any `active → dormant` transition; prove recovery/reconsideration and at-most-one lifecycle Event in that later slice. |
| Locking | Task FOR UPDATE → Team/Thread/Hypothesis FOR NO KEY UPDATE; one-at-a-time sorted row acquisition; session registry/guard on new paths. Spike nodes: `test_fk_child_insert_lock_compatibility` (4 parameter cases), `test_fk_lock_inversion_reproduces_deadlock`, `test_read_committed_reads_after_team_lock_wait`, and `test_opposite_input_orders_use_one_sorted_lock_order`. Existing-writer guard retrofit and DB-role restrictions remain separately gated. |
| Race | Triage-first and decay-first outcomes; under-lock revalidation; no stale evidence overwrite. |
| Replay/recovery | Repeated Task execution/recovery produces no duplicate changes or Events; terminal marker ambiguity remains fail-closed if a marker path is ever accepted. |
| Failure | Classified ineligibility versus integrity/transaction failure; no partial writes on failed atomic batch. |
| Bounds | Deterministic scan/write cap and explicit overflow behavior; no silent truncation. |
| Lifecycle | TaskRuntime owns admission, attempt fencing, one-transaction business/Event/Outcome/terminal commit, and recovery. Unknown commit is resolved from terminal Task + Outcome only; business-write presence/absence is asserted in fault-injection tests. Shared-runtime changes map to RW-REC-01, RW-REPLAY-01, and RW-RP-01; no RW3.4 residual is closed. |

Each implementation PR must map its exact tests and source changes to these obligations, identify the exact tested SHA, run hosted CI, and complete required Programmer-local disposable-PostgreSQL verification before merge.

## 7. Separate scheduler/host integration gate (RW5-P)

RW5-P is not part of the deterministic decay core. It is a separately gated integration for periodic invocation by a trusted host scheduler.

It must define schedule cadence/time zone, missed-run behavior, per-Team fan-out, idempotent schedule-slot identity, retry/backoff, disabled/inactive Team behavior, observability, and operator controls. The host scheduler may create an `apply_decay` Task through the typed creator; it may not execute the Task or write world memory. No Watch-owned periodic loop, TaskDispatcher expansion, or second runtime is implied.

## 8. Decision and authorization boundary

This proposal is ready for independent review and Operator disposition. Until accepted:

- the clock/revision/epoch cutoff, history-reconstruction algorithm, confidence-window semantics, lock helper/guard scope, atomicity, and failure/bounds rules remain proposed; the PostgreSQL spike is lock-mechanics evidence only, not proof of production writer coverage; dormancy is explicitly excluded from RW-5 first release;
- no RW-5 production implementation is authorized;
- no RW4-1 or RW4-2 implementation is authorized by this document;
- RW4-1 and RW4-2 remain sequential, not parallel;
- dormant-Thread reactivation remains D6-gated;
- RW3.4 remains implementation-complete with formal acceptance deferred and all seven PARTIAL rows unchanged;
- live provider authorization remains closed;
- R7-C, persistent-database operations, and R8 remain separately gated.

After review, record accepted/rejected decisions here, reconcile the Task and architecture specifications, then request explicit authorization for the single next implementation stream.
