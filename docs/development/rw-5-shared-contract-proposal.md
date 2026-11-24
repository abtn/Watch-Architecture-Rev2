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
| `RW-REPLAY-01` — duplicate write outcomes across replay states not exhaustive | Conditional: relevant only if RW-5 introduces a separate business-commit/receipt/recovery boundary. | Directly relevant to RW4-3's receipt and business-commit replay protocol. | Prefer one atomic TaskRuntime/Kernel commit. If a separate marker is unavoidable, prove its exact replay states; do not import an unrelated exhaustive Cartesian matrix. |
| `RW-RT-02` — 45-second update_thread deadline versus strictly-greater-than-60-second recovery threshold | Unrelated to deterministic decay unless the global recovery timing contract is changed. | Unrelated to triage unless it changes that same recovery timing path. | Preserve the existing boundary. Do not change global recovery timing to make an unrelated test reachable. |
| `RW-REC-01` — full locked Session/Task/attempt matrix incomplete | Directly relevant to Task/Team/Thread/Hypothesis lock order and concurrent decay attempts. | Relevant to triage concurrency and any separately authorized reactivation path. | Add targeted lock-order, stale-attempt, and race proofs only. Do not claim the full matrix is closed. |
| `RW-RP-01` — repeated recovery across all duplicate Event/write outcomes incomplete | Conditional: relevant only if RW-5 introduces a separate durable marker/recovery path. | Directly relevant if RW4-3 uses its proposed separate receipt/commit protocol. | Prefer atomic commit. If a separate recovery boundary remains, test its specific repeated-recovery outcomes; retain unrelated residuals. |

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

### 4.2 Authoritative time: one database-captured immutable instant

**Decision proposed:** after acquiring the Team's exclusive `FOR UPDATE` serialization lock, capture one UTC `as_of` instant exactly once from PostgreSQL using `clock_timestamp()` during the typed Task-creation transaction; persist that value in the immutable canonical Task request envelope/Event before releasing the Team lock. The Task request fingerprint includes it. Every writer that can add accepted EvidenceLinks or change Hypothesis confidence/touch state must participate in the same Team lock protocol, so the lock establishes a total order between the captured instant and accepted world-memory commits. Do not use `Task.created_at` as the decay clock: PostgreSQL `now()` is the transaction-start timestamp, not necessarily the Task insertion instant, and the Task may wait in a queue before execution.

- The production creator obtains the timestamp from the database only after it owns the Team serialization lock; callers and models cannot supply or override it. The lock is held through Task/request Event commit.
- Persist the exact value at database precision with timezone-aware UTC representation. The request record is append-only/immutable, with a database-enforced guard against update or replacement. If the current Event schema does not guarantee that property, add the smallest database constraint/trigger required; do not rely on application convention.
- Every Hypothesis, Thread decision, retry, and interrupted recovery for this Task uses the exact same persisted `as_of`. Execution never calls a clock to recompute it.
- The deterministic Task identity excludes `as_of`; a replay loads and validates the winning Task request and reuses its original value.
- Provide a test-only deterministic database-clock seam at Task creation. Production callers must not gain a caller-controlled timestamp parameter.
- If relevant accepted evidence or a state transition is later than `as_of`, the worker skips that record with an explicit deterministic reason. It must not clamp negative elapsed time or pretend the later state existed at the pinned instant.

This makes a Task replay a reconstruction of the original decision, not a new decision made at retry time. The immutable request value—not a mutable Task column or process clock—is the authoritative time source.

### 4.3 Historical evidence is authoritative; current-state fields are only accelerators

**Decision proposed:** reconstruct evidence age from immutable accepted evidence history. `Hypothesis.last_touched_at` is a mutable current-state cache/prefilter, not the authority for a past decay decision.

- Accepted supporting or challenging EvidenceLinks are the authoritative evidence-touch records. An accepted touch resets the evidence-age baseline even if confidence does not change.

**Important timestamp qualification:** the current EvidenceLink and ConfidenceChange `created_at` defaults use PostgreSQL `now()`, which is the transaction-start time. A transaction can begin, wait for the Team lock, and only then commit its evidence/confidence change; its `created_at` can therefore predate the actual serialized acceptance. Do not assume the current `created_at` values establish the correct order relative to the Task's `as_of`. For every new accepted evidence touch and confidence transition, persist an immutable database-captured acceptance/transition instant obtained with `clock_timestamp()` after acquiring the Team lock. Determine whether the existing timestamp columns can be safely populated explicitly after the lock, or whether a minimal dedicated immutable timestamp is required. The Event/audit record must carry the same canonical instant. Legacy rows whose true post-lock acceptance instant cannot be reconstructed need an explicit conservative migration/cutover rule; do not silently treat transaction-start timestamps as exact acceptance times.
- Mentions-only links, rejected proposals, retrieval, and decay do not reset the baseline.
- A duplicate/replayed EvidenceLink is not a new touch. Canonical EvidenceLink identity—not timestamp equality alone—distinguishes new accepted evidence from replay.
- `last_touched_at` may narrow candidate queries, but before mutation the worker reconstructs the latest eligible touch from history and verifies the cache agrees with that history. A mismatch is an integrity failure/defer, not permission to trust the cache.
- For a Hypothesis with no accepted supporting/challenging evidence, use its immutable creation baseline only if the domain contract explicitly says creation starts the inactivity clock; otherwise it is ineligible until a first accepted touch. Freeze this detail before implementation.
- Confidence history is also authoritative for confidence transitions. The low-confidence interval (if later needed) begins at the later of the latest accepted evidence touch and the latest historical ConfidenceChange that transitioned the current Hypothesis into `low`. Do not infer a low streak from the current confidence value alone.

**No-new-column is a hypothesis, not a frozen assumption.** Retain the existing representation only if focused property/replay tests prove exact reconstruction across: evidence touches that do and do not change confidence; same-timestamp distinct accepted touches; duplicate EvidenceLink replay; transitions into and out of `low`; decay catch-up; and evidence arriving after a Task's `as_of`. A dedicated touch-version/reference or low-confidence-start field is justified if those proofs fail.

A new temporal EvidenceLink index is not assumed. Measure the bounded history query and query plan on a representative disposable PostgreSQL fixture. Add the smallest index only if measured cardinality/latency or bounded-work requirements demand it. Do not add an age column or index speculatively.

**Window semantics:** use half-open elapsed windows with an inclusive due boundary:

`due(k) iff as_of >= anchor + k * W`

Use integer/microsecond arithmetic over timezone-aware UTC instants. The anchor is the latest accepted evidence-touch instant, not a value mutated by decay. A newly accepted touch starts a new window sequence. Catch up one actual confidence-band transition per elapsed window, in ordinal order; write one ConfidenceChange per actual transition, with no no-op rows after the lowest band. The same Task/replay must not apply a window twice. A deterministic, versioned key identifies `(team_id, hypothesis_id, canonical evidence-touch identity, window ordinal)`, and a database uniqueness constraint must arbitrate duplicate application across different Tasks.

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

**Proposed common order:**

1. Lock the current Task row and validate running status/current attempt.
2. Lock the Team row with `FOR UPDATE` as the per-Team writer serialization point.
3. Lock affected Thread rows in ascending canonical ID order.
4. Lock affected Hypothesis rows in ascending canonical ID order.
5. Revalidate Team ownership, lifecycle, historical evidence baseline, policy pin, and current-attempt preconditions under those locks.
6. Write ConfidenceChanges and Task-attributed Events through the accepted TaskRuntime/Kernel transaction boundary.

The Team lock is exclusive because the contract requires writer serialization; a shared lock would not provide it. This is intentionally conservative and may serialize all writes for a Team. Measure contention before considering a narrower lock scheme. Any Task creator must follow the compatible Team-first suffix because its Task row does not exist yet; it must not lock a Thread/Hypothesis and then acquire Team.

Before freeze, identify every relevant RW-4/RW-5 writer and prove its acquisition order. Prefer one small shared lock-order helper (or one mechanically equivalent implementation) over duplicated undocumented ordering. An instrumented test must fail on out-of-order acquisition across decay, triage, and ingestion paths. After acquiring the Thread lock, reload the eligible Hypothesis set and revalidate it under lock; do not act on a stale pre-lock candidate list.

Define a bounded lock timeout and classify timeout/deadlock as retryable Task failure under existing TaskRuntime policy. Do not swallow it as a per-Hypothesis skip. PostgreSQL unique constraints, immutable-record guards, and row locks are the concurrency authority; application prechecks only improve diagnostics and are never the guarantee.

### 4.7 Decay/triage race outcomes

The exclusive Team lock serializes decay and triage writers for the same Team. Each operation reloads and revalidates canonical rows and accepted history after acquiring it.

- **Triage commits first:** the later decay operation observes the accepted EvidenceLink and recomputes the baseline from history. A step no longer due at the Task's pinned `as_of` is not applied.
- **Decay commits first:** triage observes the committed confidence state. Before D6 and a durable reactivation/recovery path exist, dormant-Thread behavior is not reachable because RW-5 does not create dormant Threads.
- **After D6:** a separately authorized reactivation path must validate current Team, Thread, Hypothesis, and evidence state under the same lock order and emit at most one reactivation Event. It must also define how decay-first state is reconsidered; merely changing `dormant → active` is not enough.
- A losing concurrent/replayed request loads or validates the canonical committed result; it cannot append a duplicate ConfidenceChange or lifecycle Event.

Prove both race orders with disposable PostgreSQL. Unit tests that mock away row locks do not prove serialization.

### 4.8 Task transaction, recovery, and per-Hypothesis failures

**Atomicity is a required design proof, not an assumption about the current APIs.** The existing `WorldMemoryCommitService.commit_model()` opens its own transaction, while `TaskRuntime.finalize()` opens a separate transaction. `commit_model_in_session()` provides a possible shared-session seam, but the current finalization API does not itself prove that business writes, summary Event, Outcome, and terminal Task state can commit atomically.

Before implementation, demonstrate a TaskRuntime-owned orchestration/finalize-in-session path that commits the following in one database transaction:

- all eligible decay ConfidenceChanges;
- the single deterministic summary Event;
- the Task Outcome; and
- the terminal Task state.

Bound the batch size, transaction duration, and lock duration. Deterministic ineligibility may be skipped only with an explicit stable reason recorded in the summary. Integrity violations, ownership conflicts, stale attempts, malformed policy, lock timeout/deadlock, and infrastructure/transaction errors abort the transaction; do not swallow them as per-Hypothesis skips.

Inject failures before writes, after business writes, before summary Event, and before terminal Task state. Each failure must roll back all business and terminal writes, leaving TaskRuntime's normal retry/recovery policy authoritative. Do not add savepoints unless an accepted requirement demonstrates that individual Hypothesis failures must be isolated.

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
| Clock | Task creation pins one database UTC instant; retry/recovery reuses it; caller-supplied timestamps are rejected/ignored. |
| Boundaries | Before, exactly at, and after each decay-window boundary; timezone/DST-independent UTC behavior. |
| Evidence reset | Supporting/challenging evidence resets age even without confidence change; mentions/rejection/decay do not; post-Team-lock database acceptance instants are ordered correctly against Task `as_of`; legacy rows have an explicit conservative rule; old decay keys cannot suppress a new baseline. |
| Catch-up | Multiple elapsed windows produce the defined sequence once; low-band floor creates no no-op writes. |
| Attribution | Every decay ConfidenceChange has exactly one valid decay Task cause; no EvidenceLink cause; cross-Team/wrong-Task attribution rejected. |
| Dormancy | Excluded from RW-5 first release. D6 plus a durable RW-4 reactivation/recovery path and separate authorization must precede any `active → dormant` transition; prove recovery/reconsideration and at-most-one lifecycle Event in that later slice. |
| Locking | Task → Team → sorted Thread → sorted Hypothesis; PostgreSQL concurrent tests and lock-order review. |
| Race | Triage-first and decay-first outcomes; under-lock revalidation; no stale evidence overwrite. |
| Replay/recovery | Repeated Task execution/recovery produces no duplicate changes or Events; terminal marker ambiguity remains fail-closed if a marker path is ever accepted. |
| Failure | Classified ineligibility versus integrity/transaction failure; no partial writes on failed atomic batch. |
| Bounds | Deterministic scan/write cap and explicit overflow behavior; no silent truncation. |
| Lifecycle | Existing TaskRuntime admits, finalizes, and recovers the Task; exact Task/Event/Outcome behavior is tested. |

Each implementation PR must map its exact tests and source changes to these obligations, identify the exact tested SHA, run hosted CI, and complete required Programmer-local disposable-PostgreSQL verification before merge.

## 7. Separate scheduler/host integration gate (RW5-P)

RW5-P is not part of the deterministic decay core. It is a separately gated integration for periodic invocation by a trusted host scheduler.

It must define schedule cadence/time zone, missed-run behavior, per-Team fan-out, idempotent schedule-slot identity, retry/backoff, disabled/inactive Team behavior, observability, and operator controls. The host scheduler may create an `apply_decay` Task through the typed creator; it may not execute the Task or write world memory. No Watch-owned periodic loop, TaskDispatcher expansion, or second runtime is implied.

## 8. Decision and authorization boundary

This proposal is ready for independent review and Operator disposition. Until accepted:

- the clock, lock order, history-reconstruction algorithm, confidence-window semantics, atomicity, and failure/bounds rules remain proposed; dormancy is explicitly excluded from RW-5 first release;
- no RW-5 production implementation is authorized;
- no RW4-1 or RW4-2 implementation is authorized by this document;
- RW4-1 and RW4-2 remain sequential, not parallel;
- dormant-Thread reactivation remains D6-gated;
- RW3.4 remains implementation-complete with formal acceptance deferred and all seven PARTIAL rows unchanged;
- live provider authorization remains closed;
- R7-C, persistent-database operations, and R8 remain separately gated.

After review, record accepted/rejected decisions here, reconcile the Task and architecture specifications, then request explicit authorization for the single next implementation stream.
