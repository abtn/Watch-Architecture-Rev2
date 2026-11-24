# RW-5 Shared Contract — Freeze Proposal

**Decision status:** Proposed for Operator review; not yet frozen.
**Document purpose:** settle the shared time, decay, locking, replay, and Task-production contracts before RW-5 implementation and before RW-4 dormant-Thread reactivation.
**Baseline:** `main` at `5aecf096b077ab34bc7c8fb09cb750a59a19c335` (PR #181 merge).
**Scope of this proposal:** documentation and source-backed design only. It does not authorize production code, schema changes, migrations, scheduler deployment, provider calls, persistent-database operations, or RW3.4 acceptance. The accepted logical representation requires a migration; that migration and the RW3.4-adjacent writer retrofit are explicit, separately reviewed implementation gates.

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
| `RW-REC-01` — full locked Session/Task/attempt matrix incomplete | Directly touched by the existing writer's revision stamping under the required Task/Team/Thread/Hypothesis lock order and by TaskRuntime attempt fencing/finalize-in-session work. | Relevant to triage concurrency and any separately authorized reactivation path. | Add targeted lock-order, stale-attempt, and race proofs only. Do not claim the full matrix is closed. |
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

**First-release decision:** PostgreSQL is the authoritative clock. After acquiring the canonical Team lock, capture one raw UTC observation with PostgreSQL `clock_timestamp()`. Store that immutable `as_of` in the Task request and request Event. Do not clamp it to the prior high-water mark and do not use Task.created_at: PostgreSQL `now()` is transaction-start time and the Task may wait in a queue. Production callers and models cannot supply or override the instant.

**The Team revision orders history; timestamps measure elapsed time.**

- Add a monotonically increasing per-Team `world_memory_revision`. The canonical world-memory write-lock helper owns the Team `FOR NO KEY UPDATE` lock and allocates/increments the revision exactly once for each accepted transaction that changes relevant Hypothesis/history state. It stamps that revision on affected immutable history rows and corresponding Task-attributed Events. Writers do not implement their own bump logic.
- Task creation captures the current Team revision watermark while holding the same Team lock. It pins the complete active-Hypothesis population and per-Hypothesis history watermarks at that serialized cutoff. The revision, not timestamp sorting or UUID ordering, determines which accepted history existed at the cutoff.
- The Team row is one hot serialization row per Team under world-memory write load. This is an intentional first-release trade-off: it gives one authoritative history watermark and lock order. Measure contention in implementation proof; do not introduce sharded counters or a general sequencing service without evidence.
- Persist a per-Team, per-epoch `last_clock_at` high-water mark. It advances only in the same transaction as a successfully committed decay run, to that run's pinned `as_of`; Task creation and ordinary history writes do not advance it. A rollback advances neither the mark nor decay writes.
- Each Task manifest records raw `as_of`, the `last_clock_at` value observed at creation, and the epoch's `clock_rebase_generation`. At execution, under the canonical Team lock, require the Task's epoch and rebase generation to remain current and require its raw `as_of` not to be earlier than the current `last_clock_at`. A Task made stale by a newer committed decay run or clock rebase defers without business writes. On successful commit, set `last_clock_at = as_of`, including a successful no-transition/low-floor run; never advance it on failure. The Task-attributed summary Event records the previous and resulting high-water values so the advancement is auditable.
- Do not silently clamp a backward raw database clock to the high-water mark. If the database clock moves backwards, later decay Tasks fail closed until an explicit rebase. A large forward jump may therefore advance the mark and temporarily stop subsequent decay when the clock returns to normal. This is a deliberate safety trade-off, not an undetected recovery path.
- **Named recovery operation:** `rebase_decay_epoch_clock` is a trusted Kernel/application operation requiring explicit Operator authorization. As a documented manual procedure for the first release, it acquires the Team lock, captures the corrected current database UTC instant, resets the active epoch's `last_clock_at` to that instant, increments `clock_rebase_generation`, and appends one immutable Event recording Team, epoch, previous mark, new mark, generation, reason, actor, and time. It does not rewrite old Task requests, history, or confidence decisions. Tasks pinned to an earlier rebase generation defer, so a queued pre-rebase Task cannot restore the old high-water mark. Do not run it merely to bypass an unexplained regression; first establish and correct the clock source. No automatic monitor or scheduler is part of this operation.
- The forward-jump residual is explicit: a forward discontinuity can accelerate the first committed decay run; the three-band state machine bounds actual confidence reductions to at most two transitions (`high → moderate → low`), after which `low` is a no-op. This does not make downstream decisions reversible. A compensating ConfidenceChange can correct the durable record but cannot undo downstream decisions already made using the earlier value.
- Revisit clock safeguards if RW5-P introduces unattended periodic execution, deployment becomes multi-node/replicated or uses a different database clock source, a clock incident is observed, or unattended R8 operation is proposed. Until then, the high-water check plus named Operator rebase is the accepted first-release policy; no independent monitor, health singleton, incident latch, or catch-up cap is required.
- A new decay epoch remains the boundary for TeamPolicy/algorithm version changes and conservative cutover. Epoch IDs scope baselines and elapsed-time comparisons; never compare timestamps across epochs. Team revision remains globally monotonic and is the cross-epoch history-ordering authority.

**Team revision is a migration and compatibility change, not a convention.** The single canonical world-memory write-lock helper owns the bump and metadata stamping. The migration adds the Team revision and required revision/epoch/acceptance metadata to relevant history records and Events. Every supported existing writer must be routed through that helper before decay is enabled; its inventory is an implementation artifact, and focused tests must exercise every listed writer entrypoint and prove exactly one revision allocation per accepted transaction and no bump on replay/rollback. The existing `WorldMemoryCommitService` path is in scope for that compatibility retrofit. This changes an accepted RW3.4 path and therefore requires its own explicit authorization and review; it is not silently included in the RW-5 implementation authorization. A missed writer is a correctness failure, not an accepted silent degradation.

The database-clock seam is injectable only in tests. A test source may supply deterministic UTC instants to simulate elapsed weeks, but every simulated run must obey the same monotonic rule against the stored high-water mark and rebase generation. Production construction always uses PostgreSQL `clock_timestamp()`; no caller-controlled production timestamp parameter exists.

Replay reconstructs the original decision. The immutable database-captured instant measures elapsed time; the Team revision establishes serialized history membership.

### 4.3 Historical evidence is authoritative; current-state fields are only accelerators

**Decision proposed:** reconstruct evidence age from immutable accepted evidence history. Hypothesis.last_touched_at is a mutable current-state cache/prefilter, not the authority for a past decay decision. Accepted supporting or challenging EvidenceLinks are the authoritative evidence-touch records. An accepted touch resets evidence age even if confidence does not change.

**Source-backed history gap:** the existing world-memory commit path uses application datetime.now(timezone.utc) for committed_at and stamps Hypothesis, EvidenceLink/ConfidenceChange, and Events with it. ORM server defaults on other insert paths use PostgreSQL now() (transaction-start time). Neither is a database-captured post-lock acceptance instant. The current Hypothesis creation path sets mutable confidence='low' and records confidence='low' in the immutable hypothesis_created Event, but creates no initial ConfidenceChange row. The Event is the only existing immutable record of the initial band; its timestamp is not a reliable database ordering key.

For new accepted evidence touches and confidence transitions, persist the Team revision, active epoch ID, and one raw database-captured UTC acceptance/transition instant after acquiring the canonical Team lock helper. Team revision, not timestamp order, serializes history. The same values must appear on the history row and its Task-attributed Event. Do not compare instants across epochs or treat existing created_at values as exact serialized acceptance times.

**Required compatibility prerequisite:** the current supported Hypothesis evidence/confidence writer is WorldMemoryCommitService. It currently uses application-captured committed_at and does not populate a Team history revision. Before RW-5 decay can execute, this writer must use the canonical world-memory write-lock helper, which allocates the Team revision once and stamps revision, epoch, and raw database-captured acceptance instant on Hypothesis, EvidenceLink, ConfidenceChange, and their Task-attributed Events. A replay that reuses an existing committed result must not increment the revision or rewrite history. This required history-writer compatibility slice is distinct from the global before_flush guard retrofit. It changes an accepted RW3.4 path and requires its own explicit authorization and review against RW-REC-01, RW-REPLAY-01, and RW-RP-01. Until implemented and proven, RW-5 may not treat new Hypothesis history as revision-authoritative or run decay Tasks.

**Epoch bootstrap ownership is explicit:** the initial RW-5 epoch is created only by a dedicated, trusted Kernel/application epoch-transition operation under explicit Operator authorization. This is the same narrow transition boundary that will later handle policy/algorithm epoch changes and explicit clock rebase; it is not the typed `apply_decay` Task creator, TaskRuntime, a worker, or a scheduler. In one transaction it acquires the Team `FOR NO KEY UPDATE` lock and captures the Team revision and database epoch-origin instant, creates exactly one immutable genesis epoch, creates the complete baseline set for every Hypothesis whose canonical lifecycle status is `active` at the epoch's serialized Team-revision cutoff (excluding `superseded` and `rejected` Hypotheses), and activates the epoch. Task creation uses the same Team lock and may admit decay only after it observes that complete active epoch. A database-enforced unique genesis identity (one genesis epoch per Team) and unique `(epoch_id, hypothesis_id)` baseline identity arbitrate duplicates; concurrent bootstrap attempts load and validate the winning complete epoch and never create a second baseline set. If the trusted transition operation, complete baseline set, or explicit authorization is absent, initial activation is unsupported and decay remains disabled/deferred for that Team. No Task creator may synthesize or repair epoch baselines.

**Decay population is active-Hypothesis-only:** at each epoch/bootstrap or successor-epoch transition, the in-scope population is exactly the same-Team Hypotheses whose canonical lifecycle status is `active` at the serialized Team-revision cutoff. Create epoch baselines only for that population. `superseded` and `rejected` Hypotheses are excluded from the epoch baseline set, Task manifest, evidence-age evaluation, and all decay writes; their existing history remains immutable and available for provenance/reconstruction. A Hypothesis created later in the epoch enters the population through its immutable creation Event and current-epoch baseline/anchor rules, and is included in a Task manifest only if it is `active` at that Task's Team-revision cutoff.

At execution, revalidate lifecycle status under the canonical locks. If a manifest member is no longer `active`, do not decay it: record the stable per-Hypothesis skip reason `hypothesis_not_active` and continue only with other still-eligible active members. Unknown or malformed lifecycle states are integrity failures and abort the atomic Task transaction. The operation never changes lifecycle status. The complete Task manifest is the canonical, deterministically ordered set of active Hypotheses at its pinned cutoff; it must not include superseded/rejected rows or silently omit an active row. Manifest bounds apply to this complete active population, and overflow fails Task creation rather than truncating it.

**Initial state and legacy cutover are mandatory:**

- For a Hypothesis created after the new epoch begins, persist its initial confidence band (currently low) in the immutable creation Event together with its current epoch ID/version, Team revision, and canonical acceptance instant. A new initial ConfidenceChange row is not required if the immutable creation Event is sufficient and its contract is enforced.
- At first RW-5 activation, and at every later decay-epoch boundary (including TeamPolicy/decay-algorithm version changes), create an immutable per-Hypothesis epoch baseline for every active Hypothesis in the serialized transition population: current confidence band, epoch ID/version, baseline Team revision, database-captured UTC baseline instant, and the last eligible EvidenceLink ID and ConfidenceChange ID included as history watermarks. Superseded and rejected Hypotheses receive no decay baseline. **The new epoch baseline instant is the decay-age anchor for all evidence accepted before that epoch**, regardless of any legacy or prior-epoch EvidenceLink timestamps. Preserve those prior EvidenceLink IDs and ConfidenceChange IDs for provenance/reconstruction only; never compare their timestamps with the new epoch clock or use them to calculate elapsed decay windows. Only a newly accepted eligible EvidenceLink in the current epoch may replace the epoch-baseline anchor. Do not retroactively decay legacy time or infer a low-confidence interval from mutable current state.
- **All-or-nothing active-population completeness:** if any active Hypothesis cannot be reconciled with immutable confidence history or cannot receive a valid baseline under the Team lock, epoch bootstrap/successor transition fails atomically with stable reason `decay_epoch_baseline_incomplete`; no partial baseline set or active epoch is committed. For an already active epoch, if any active Hypothesis cannot be represented completely in a Task manifest, reject Task creation with stable reason `decay_manifest_incomplete`; do not create a partial Task/request Event, omit the Hypothesis, or insert a fabricated/deferred placeholder. Do not guess an initial band. This preserves the invariant that every admitted Task manifest is the complete active population at its pinned Team-revision cutoff.
- Every Task request pins the epoch ID/version and a bounded, canonical per-Hypothesis history-watermark manifest containing exactly the active Hypotheses at the Task's serialized Team-revision cutoff: Hypothesis ID, baseline reference/hash, last eligible EvidenceLink ID, last ConfidenceChange ID, Team revision, reconstructed confidence band, and the evidence-age anchor identity/instant. The manifest envelope also records raw `as_of`, observed `last_clock_at`, and `clock_rebase_generation`. The complete canonical manifest bytes must be retained either directly in the immutable Task request or in a durable immutable content-addressed manifest record referenced by that request. In the latter case, persist both the immutable reference and its content hash, and prove that the referenced bytes remain retrievable and hash-valid for the full Task/recovery retention period. A bare hash without retrievable manifest content is invalid. If the manifest exceeds the configured bound, reject Task creation with a stable overflow reason and admit no partial Task/request Event; do not truncate it. The canonical Task request fingerprint binds raw `as_of`, Team revision watermark, epoch ID/version, policy/algorithm versions, observed `last_clock_at`, `clock_rebase_generation`, schema/manifest version, and the full manifest content hash.
- At execution, after acquiring the canonical locks, compare each manifest member's current eligible history and lifecycle status against its pinned manifest. A newer supporting/challenging EvidenceLink after the Task watermark resets the baseline and makes that Hypothesis ineligible at the older `as_of`; record a stable per-Hypothesis skip reason and allow other still-valid members to proceed. If a manifest member is now `superseded` or `rejected`, skip only that member with `hypothesis_not_active`; an unknown lifecycle value is an integrity failure. In contrast, any newer ConfidenceChange, mismatch between reconstructed history and the mutable confidence projection, or advanced Team decay epoch invalidates the Task's pinned confidence decision: abort the entire Task transaction, including all otherwise-valid members, and let TaskRuntime own retry/recovery. Never partially commit a batch whose confidence history is stale or inconsistent. Unrelated Team revisions do not invalidate a Hypothesis when its own relevant history is unchanged. A Task from a superseded epoch must never commit under the old policy.
- A new TeamPolicy version or decay-algorithm version starts a new epoch at an explicit Team revision and baseline instant, with a new immutable per-Hypothesis baseline for every Hypothesis whose canonical lifecycle status is `active` at the transition's serialized Team-revision cutoff; `superseded` and `rejected` Hypotheses are excluded. That baseline instant supersedes every pre-epoch EvidenceLink timestamp as the decay-age anchor; prior EvidenceLink IDs remain only in the baseline's history-watermark/provenance fields. There is no retroactive catch-up across policy/algorithm epochs. Only a newly accepted eligible EvidenceLink in the new epoch replaces the baseline anchor. Include epoch ID/version, policy version, algorithm version, canonical evidence-touch identity, and window ordinal in the cross-Task decay idempotency key. This prevents a changed window definition from reusing or suppressing an old epoch's step.

Legacy EvidenceLink/ConfidenceChange rows without trustworthy Team revision and post-lock timestamps are covered only by the one-time conservative baseline. No historical catch-up is inferred from their transaction-start or application timestamps.

ConfidenceChange history is authoritative for the confidence band as well as attribution. Reconstruct the band's value by replaying ConfidenceChanges after the immutable creation/epoch baseline in Team revision order; the mutable Hypothesis.confidence column is only a current-state cache and must equal the replayed result under lock. A mismatch is an integrity failure that aborts the entire Task transaction; it is never a per-Hypothesis skip or permission to trust the mutable value. The Task's pinned manifest records the last ConfidenceChange ID and the reconstructed band. Before commit, any newer ConfidenceChange after that watermark makes the old decision stale and prevents it from overwriting the newer band.

**Confidence history and current-state projection are one Kernel-owned atomic write.** For every actual decay transition, the same TaskRuntime/Kernel transaction must (1) append exactly one immutable, Task-attributed ConfidenceChange with the next valid `(team_revision, transition_ordinal)`, and (2) update the corresponding `Hypothesis.confidence` projection to that row's `to_confidence`. The update is performed by trusted application/Kernel code under the canonical Hypothesis lock; it is not a worker-authored proposal and does not grant model code direct Hypothesis write authority. The bounded `apply_decay` operation therefore has an explicit Kernel-managed Hypothesis confidence-projection side effect in addition to its ConfidenceChange write. Both records must be validated against the replayed prior band and committed or rolled back together with the Task summary Event, Outcome, and terminal Task state. A failed flush, constraint, Event write, or terminalization leaves neither the new ConfidenceChange nor the changed Hypothesis projection committed. After commit, replayed history and the mutable projection must agree exactly. No-op lowest-band windows create neither row nor projection update.

**No-new-column is not a freeze assumption.** The epoch baseline, Team revision, epoch high-water mark, and clock-rebase generation need a database-enforced representation. Existing EvidenceLink/ConfidenceChange history may be retained only if property/replay tests prove exact reconstruction across touches with and without confidence change, same-time distinct touches, duplicate replay, transitions into/out of low, catch-up, and evidence arriving after a Task cutoff. Add the smallest immutable field/table needed if those proofs fail; do not preserve a no-migration assumption at the expense of correctness.

A new temporal EvidenceLink index is not assumed. Measure bounded history queries and query plans on a representative disposable PostgreSQL fixture. Add the smallest index only if measured cardinality/latency or bounded-work requirements demand it.

**Window semantics:** use half-open elapsed windows with an inclusive due boundary:

due(k) iff as_of >= anchor + k * W

Use integer/microsecond arithmetic over timezone-aware UTC instants. The anchor is the latest accepted supporting/challenging EvidenceLink touch included in the Task's pinned Team revision and Hypothesis manifest. Decay itself never changes the anchor. When at least one eligible EvidenceLink accepted in the current decay epoch exists, the anchor identity is that canonical current-epoch EvidenceLink ID and its database-captured, post-Team-lock acceptance instant (the latest eligible current-epoch touch under the pinned Team-revision cutoff). A pre-epoch EvidenceLink is never an elapsed-time anchor in the current epoch, even when it is the latest historical EvidenceLink; its ID may remain in the baseline manifest as a history watermark/provenance reference only. When no eligible current-epoch EvidenceLink exists, the anchor is the immutable current-epoch baseline: for a Hypothesis created in the current epoch, use the immutable `hypothesis_created` Event ID and its database-captured acceptance instant; for a Hypothesis carried into this epoch, use its immutable per-Hypothesis epoch-baseline record ID and baseline instant. Never use a mutable `last_touched_at`, a transaction-start timestamp, or a guessed historical timestamp as this fallback.

The first eligible EvidenceLink accepted in the current epoch replaces that epoch's creation/baseline anchor and starts a fresh window sequence at that touch's acceptance instant. Evidence accepted in a prior epoch never replaces a later epoch's baseline anchor. The canonical evidence-age identity is a typed pair `(anchor_kind, anchor_id)` (`evidence_link`, `hypothesis_created_event`, or `epoch_baseline`) plus the pinned anchor instant; include that identity in the cross-Task decay idempotency key. Thus a no-evidence baseline and a first-evidence touch cannot collide or suppress one another. Anchor availability is part of complete-manifest validity, not a per-Hypothesis execution skip: if an active Hypothesis has neither a trustworthy immutable creation Event nor a valid epoch-baseline record at Task creation, reject the entire Task creation with stable reason `decay_anchor_unavailable` before inserting the Task row, request Event, or any partial manifest. This anchor-specific reason takes precedence over the broader `decay_manifest_incomplete` reason; other missing or unreconstructable manifest/history components use `decay_manifest_incomplete`. After Task creation, if the exact pinned anchor ID/instant is missing, corrupt, or cannot be verified at execution, treat it as a batch integrity failure and abort the entire Task transaction. Do not defer/skip only that Hypothesis or commit other members. TaskRuntime owns the resulting retry/recovery/terminalization; no success Event or Outcome may be committed for the aborted business transaction.

Catch up one actual confidence-band transition per elapsed window, in ordinal order; write one ConfidenceChange per actual transition, with no no-op rows after the lowest band. The same Task/replay must not apply a window twice. A deterministic, versioned key identifies (team_id, hypothesis_id, epoch_id, policy_version, algorithm_version, anchor_kind, anchor_id, window ordinal), and a database uniqueness constraint must arbitrate duplicate application across different Tasks.

### 4.4 Confidence transition and policy semantics

**Frozen first-release vocabulary and precedence:**

- `decay_window` is a required, strictly positive finite duration in the effective TeamPolicy. The selected immutable TeamPolicy is the sole runtime source; any pack-provided value must already have been resolved into that published policy. RW-5 does not merge pack and Team overrides at execution, infer a missing value, or introduce another precedence layer. Missing, malformed, zero, negative, non-finite, or unsupported duration values fail closed.
- `decay_action` has one accepted first-release semantic: lower confidence by exactly one band per elapsed `decay_window`. The Kernel default is this action. A supplied action is accepted only if it expresses that exact behavior; unknown actions and pack overrides that change the transition behavior are rejected. The legacy domain description of dormancy is explicitly excluded from this first-release action and cannot be enabled through policy.
- The ordered confidence bands are `high → moderate → low`. One elapsed window causes at most one actual downward transition in that order; multiple elapsed windows apply one transition per window in sequence, stopping at `low`. Therefore a single forward jump can cause at most two actual reductions; a separate per-run catch-up cap is not part of the first release. `low → low` is a no-op: no ConfidenceChange and no Hypothesis projection update. No upward transition is permitted by decay.
- The action never rejects, supersedes, deletes, or otherwise changes Hypothesis lifecycle status. It never updates `last_touched_at` or Thread lifecycle/activity timestamps.
- The effective `decay_window`, accepted `decay_action` semantic, and algorithm version are pinned in the immutable Task request. A replay uses those exact pins and cannot adopt a newer policy midway through catch-up.
- The absence of a decay parser in `core/policy.py` is a source gap, not permission to add a generic policy framework. Implement only a narrow parser/validator for these two consumed values; fail closed on unsupported vocabulary. No implicit duration default is defined by this contract.

Every actual transition creates exactly one ConfidenceChange with `cause_kind="decay"`, the current decay Task attribution, the deterministic per-window idempotency key, and the next per-Hypothesis transition ordinal. In the same transaction, trusted Kernel code updates `Hypothesis.confidence` to the recorded `to_confidence` as specified above.

### 4.5 Dormancy is out of scope until D6 recovery exists

**RW-5 first release performs confidence decay only. It does not transition Threads to `dormant`.**

Dormancy is an irreversible lifecycle transition for the current delivery sequence: it can make a Thread unavailable to the first RW-4 matching path, while the authorized reactivation/recovery path is not yet implemented. The non-vacuous rule (“at least one active Hypothesis, and every active Hypothesis is low and beyond the accepted inactivity threshold”) is not sufficient by itself. A lifecycle transition must not ship before its recovery path exists.

- RW-5 must not change Thread status or Thread lifecycle/activity timestamps and must not emit a dormancy Event.
- Do not add dormancy as an optional policy flag in the first RW-5 release.
- Dormancy requires D6 acceptance, a durable RW-4 reactivation path, and an explicit recovery/reconsideration behavior for decay-first and triage-first outcomes.
- If dormancy is later authorized, reconstruct low-confidence age from accepted evidence and ConfidenceChange history as described above; never infer it solely from mutable current-state fields.

This is a hard scope boundary, not a deferred implementation detail within RW-5.

### 4.6 Shared lock order and database-enforced concurrency

Use one canonical lock helper for both decay and triage. It acquires and records locks in this order:

1. Task `FOR UPDATE` when a Task exists (attempt/lifecycle fencing).
2. Team `FOR NO KEY UPDATE`.
3. Individual Thread rows in sorted ID order, `FOR NO KEY UPDATE`.
4. Individual Hypothesis rows in sorted ID order, `FOR NO KEY UPDATE`.

A Task creator has no Task row yet: it acquires Team first, captures raw database `as_of` and the Team revision watermark, then inserts Task + request Event atomically. A history writer or epoch transition without a Task acquires Team then sorted affected Thread/Hypothesis rows. Do not lock child rows before Team. Do not use set-based `ORDER BY ... FOR UPDATE` as proof of lock acquisition order; the helper acquires rows individually in sorted order.

The Team `FOR NO KEY UPDATE` mode is deliberate. PostgreSQL foreign-key checks take `FOR KEY SHARE` on referenced parent rows. `FOR UPDATE` conflicts with that protection and can deadlock with a child-first writer; `FOR NO KEY UPDATE` still serializes same-Team writers while remaining compatible with FK `FOR KEY SHARE`. Task rows remain `FOR UPDATE`.

The helper owns the session lock registry and under-lock revalidation. Candidate discovery may be read-only before locking; after Team/Thread/Hypothesis locks, reload candidate ownership, membership, lifecycle, relevant history, epoch, policy pins, and current-attempt preconditions. If discovery changed, restart or defer; never act on stale discovery. Acquire locks inside `session.no_autoflush` and do not stage child rows before the helper completes.

A `before_flush` guard protects new RW-5/RW-4 ORM write paths by requiring the exact locks in the session registry. It must reject protected Hypothesis ownership moves through ordinary updates. This guard is not a complete database security boundary: it does not intercept raw SQL, SQLAlchemy Core bulk DML, or other clients. The global guard retrofit for existing writers and database-role/privilege enforcement for scripts/external writers are deferred follow-ups and named residual risks, not part of this freeze. New protected paths must not bypass the helper with Core bulk DML/raw SQL absent a separately reviewed database function.

| Operation | Canonical acquisition order |
|---|---|
| Create apply_decay Task/request | Team |
| Decay execution | Task → Team → sorted Thread → sorted Hypothesis |
| Triage | Task → Team → sorted Thread → sorted Hypothesis |
| Existing history writer | Task → Team → sorted Thread → sorted Hypothesis |
| Epoch bootstrap/transition/rebase | Team → sorted affected Hypotheses |

The shared helper is the single lock-order implementation for decay and triage. The disposable PostgreSQL spike proves FK lock compatibility, the child-first deadlock cycle, READ COMMITTED visibility after a Team-lock wait, and sorted opposite-order acquisition only. It does not prove production writer coverage or the future canonical helper.

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

A migration is required. The current schema does not provide the Team revision, decay epoch/baselines, epoch-scoped high-water mark/rebase generation, or revision/epoch/acceptance metadata needed to reconstruct relevant history. The migration and the supported existing-writer compatibility adaptation must be separately authorized and reviewed before decay can be enabled. Do not describe RW-5 as migration-free.

Prefer existing Thread, Hypothesis, ConfidenceChange, Task, and Event records where they preserve immutability and ownership. Do not add a dedicated `decay_task_id` merely to duplicate generic Task attribution. Do not use `last_touched_at` as historical authority. Do not add Thread embeddings, a new Domain subsystem, a generic temporal framework, or a second scheduler.

### 5.1 Minimum logical representation and database constraints

The following logical representation is the minimum contract baseline. It requires a migration; this proposal does not authorize that migration or the RW3.4-adjacent writer retrofit.

| Record | Required durable state |
|---|---|
| Team | `world_memory_revision BIGINT NOT NULL`, allocated once per accepted relevant history transaction by the canonical world-memory write-lock helper. The Team row is an intentional per-Team hot serialization row. |
| DecayEpoch | Immutable identity, `team_id`, per-Team ordinal, predecessor, transition kind/key, policy and algorithm versions, epoch origin instant, mutable `last_clock_at` high-water mark, and `clock_rebase_generation`. The high-water mark advances only with a committed decay run; the generation increments only through the named Operator-authorized rebase. |
| DecayEpochBaseline | One immutable row per `(epoch_id, hypothesis_id)`, carrying Team identity, baseline confidence, baseline Team revision, baseline instant, typed anchor kind/ID/instant, and last included EvidenceLink and ConfidenceChange IDs. It exists only for Hypotheses active at the serialized epoch cutoff. |
| Hypothesis creation Event | Immutable initial confidence band, Team revision, epoch ID, and database-captured acceptance instant. |
| Relevant EvidenceLink | Team revision, epoch ID, and database-captured post-lock acceptance instant for eligible Hypothesis-subject support/challenge evidence. |
| ConfidenceChange | Team ID, Team revision, epoch ID, database-captured transition instant, positive per-Hypothesis `transition_ordinal`, and existing Task attribution/idempotency data. Decay rows also persist policy/algorithm versions, typed anchor kind/ID, and window ordinal. |
| Task request/manifest | Immutable epoch ID, raw database-captured `as_of`, Team revision watermark, policy/algorithm versions, observed `last_clock_at`, `clock_rebase_generation`, manifest schema version, and complete canonical manifest content (or immutable content-addressed reference plus hash). |

Required database arbitration/enforcement:

- Unique per-Team epoch ordinal, one active epoch and one genesis epoch per Team.
- Unique per-Team transition identity binding predecessor epoch, transition kind, and target policy/algorithm version.
- `UNIQUE(epoch_id, hypothesis_id)` on DecayEpochBaseline with same-Team ownership enforcement.
- `UNIQUE(hypothesis_id, team_revision, transition_ordinal)` on ConfidenceChange; reject non-positive ordinals and enforce contiguous chains in the trusted writer/replay validator.
- A partial unique key for decay rows on `(team_id, hypothesis_id, epoch_id, policy_version, algorithm_version, anchor_kind, anchor_id, window_ordinal)`; validate typed anchor identity.
- The canonical write-lock helper is the only supported allocator of Team revision. Every supported writer is inventoried and tested through its real entrypoint. The migration must not silently initialize or advance revisions in a way that changes legacy history ordering.
- `last_clock_at` can advance only with a committed decay Task or be reset by `rebase_decay_epoch_clock`; a rebase increments `clock_rebase_generation` and writes the corresponding Event. Ordinary writers cannot update either field.
- Epoch identities, baselines, accepted history metadata, Task request pins, and manifest content are immutable after insertion. Use database constraints/privileges or narrowly scoped triggers for immutability and update restrictions; do not rely on application convention alone.
- If the complete manifest is stored in the Task request, retain its canonical bytes and versioned canonicalization rule. If stored separately, retain both immutable reference and hash; a bare hash is invalid.

The model deliberately avoids a generic temporal framework, generic event store, independent clock monitor, and second scheduler. Reuse existing tables only where they preserve the stated immutability, ownership, and replay guarantees.

## 6. Required proof before RW-5 implementation exit

| Proof area | Required evidence |
|---|---|
| Clock high-water and epoch recovery | Prove raw database `as_of`, commit-only `last_clock_at` advancement, backward-clock fail-closed behavior, and the named Operator-authorized rebase. A rebase must increment `clock_rebase_generation`, append its audit Event, and make older queued Task manifests defer. Prove a forward jump advances the mark only when the decay transaction commits and that the low-band floor limits actual confidence reductions to two. Test-only injected time must simulate elapsed weeks under the same monotonic rule. |
| Clock/history cutoff and cutover | Task pins raw database `as_of`, Team revision watermark, decay epoch, policy/algorithm versions, observed high-water/rebase generation, and the complete retrievable immutable per-Hypothesis history-watermark manifest for exactly the active population at its serialized cutoff; replay reuses exact pins. Superseded/rejected Hypotheses are excluded. Legacy cutover baselines must prevent retroactive mass decay; no active Hypothesis is silently omitted and no manifest is truncated. |
| Team revision writer coverage | The canonical world-memory write-lock helper allocates exactly one revision per accepted relevant transaction and stamps all affected history rows/Events. Inventory every supported existing writer and test each real entrypoint, including WorldMemoryCommitService routes. Replay and rollback must not bump. Prove a missed writer cannot silently leave the Task watermark stale. Record per-Team hot-row contention measurement. |
| Stale confidence batch | Pin a Task for multiple active Hypotheses, then add a newer ConfidenceChange or corrupt one current confidence projection for one member. Prove the entire Task transaction aborts and no otherwise-valid member receives a partial decay write; TaskRuntime alone handles retry/recovery. Separately prove newer evidence and lifecycle changes retain documented per-Hypothesis skip behavior. |
| Confidence replay order | In one transaction, create multiple ConfidenceChanges for one Hypothesis under one Team revision; prove contiguous transition ordinals, database uniqueness, exact replayed band/order, and rejection of duplicate/gapped ordinals or a broken from/to chain. Confirm record UUID order cannot alter reconstructed result. |
| Eligibility and manifest completeness | Build epoch and Task manifest with active, superseded, and rejected Hypotheses; prove only active rows receive baselines/manifest entries and decay writes. Transition a pinned active Hypothesis to superseded/rejected before execution and prove it is skipped with `hypothesis_not_active`, while other active members proceed. Unknown lifecycle values fail closed. Incomplete baseline/history state rejects epoch transition or Task creation atomically. |
| Boundaries and evidence reset | Test before, exactly at, and after each UTC decay-window boundary; timezone/DST-independent arithmetic; no-evidence baseline and first-evidence-anchor transition. Supporting/challenging evidence resets age even without confidence change; mentions/rejection/decay do not. |
| Catch-up and attribution | Multiple elapsed windows apply the defined sequence once, with at most two actual reductions and no no-op rows after `low`. Every decay ConfidenceChange has exactly one valid decay Task cause; no EvidenceLink cause; cross-Team/wrong-Task attribution rejected. |
| Locking | Task `FOR UPDATE` (when present) → Team `FOR NO KEY UPDATE` → sorted Thread/Hypothesis `FOR NO KEY UPDATE`; one-at-a-time sorted acquisition; session registry guards protected new paths. Prove canonical helper reuse by decay and triage and absence of lock cycles. Spike nodes: `test_fk_child_insert_lock_compatibility` (4 parameter cases), `test_fk_lock_inversion_reproduces_deadlock`, `test_read_committed_reads_after_team_lock_wait`, and `test_opposite_input_orders_use_one_sorted_lock_order`. These prove PostgreSQL lock mechanics only, not production writer participation or the future canonical helper. The global before_flush retrofit for existing writers and database-role restrictions are deferred follow-ups and residual risks. |
| RW3.4 Blocker 3 dispositions | Retain Task attempt fencing, READ COMMITTED post-Team-lock revalidation, SQLSTATE retry classification (`40P01`, `55P03`; `40001` only under SERIALIZABLE; `57014` separately classified), simplified unknown-commit resolution from terminal Task + matching Outcome, and the single shared lock helper for decay/triage. Defer the global before_flush retrofit on existing writers and database-role/privilege strategy as follow-up/residual risk. |
| Race and replay/recovery | Prove decay-first and triage-first outcomes, under-lock revalidation, no stale evidence overwrite, no duplicate writes/Events on retry/recovery, and fail-closed terminal-marker ambiguity. |
| Failure, bounds, lifecycle | Distinguish ineligibility from integrity/transaction failure; no partial writes on failed atomic batch; deterministic scan/write cap and explicit overflow. TaskRuntime owns admission, attempt fencing, one-transaction business/Event/Outcome/terminal commit, and recovery. Unknown commit is resolved from terminal Task + matching Outcome only. No RW3.4 residual is closed. |

Each implementation PR must map exact tests and source changes to these obligations, identify the exact tested SHA, run hosted CI, and complete required Programmer-local disposable-PostgreSQL verification before merge.

## 7. Separate scheduler/host integration gate (RW5-P)

RW5-P is not part of the deterministic decay core. It is a separately gated integration for periodic invocation by a trusted host scheduler.

It must define schedule cadence/time zone, missed-run behavior, per-Team fan-out, idempotent schedule-slot identity, retry/backoff, disabled/inactive Team behavior, observability, and operator controls. The host scheduler may create an `apply_decay` Task through the typed creator; it may not execute the Task or write world memory. No Watch-owned periodic loop, TaskDispatcher expansion, or second runtime is implied.

## 8. Bounded regression review and residual-risk register

The regression review is limited to regressions, factual contradictions, or demonstrated blockers under the accepted first-release threat model. It asks:

1. Does the epoch/baseline cutover still prevent retroactive mass decay?
2. Does raw database `as_of`, commit-only high-water advancement, and Operator-authorized rebase preserve monotonicity and make a forward-jump recovery auditable without allowing stale pre-rebase Tasks to commit?
3. Does the single canonical Team write-lock helper allocate the revision exactly once for every supported writer, including existing WorldMemoryCommitService routes, with no replay/rollback bump?
4. Do Task fencing, READ COMMITTED post-lock revalidation, SQLSTATE retry classification, and terminal Task + Outcome unknown-commit resolution remain intact?
5. Does the shared lock helper remain the single lock-order implementation for decay and triage, without reintroducing a monitor or health protocol?

A finding is a blocker only if a supported path can corrupt a durable invariant, double-apply decay, make a committed decision unreconstructable/unreplayable, or commit stale/unauthorized state that the contract promises to reject. Additional hardening belongs in the residual-risk register and does not reopen the freeze absent such evidence.

Residual risks retained explicitly:
- A forward database-clock jump can accelerate at most two confidence-band transitions before the low floor; later decay pauses until the named Operator-authorized `rebase_decay_epoch_clock` procedure resets the high-water mark. A compensating ConfidenceChange repairs the durable record but cannot reverse downstream decisions already made using the earlier value.
- The Team row is a per-Team hot serialization point under world-memory write load; measure contention before considering alternatives.
- The global `before_flush` retrofit for existing writers and database-role/privilege enforcement for scripts or external writers are deferred follow-ups and residual risks. The new-path guard remains in scope; raw SQL/Core/external writers remain a deployment residual.
- Production host authentication/composition and TeamPolicy publisher integration remain the existing external RW3.4 boundaries.

## 9. Decision and authorization boundary

This proposal is ready for independent review and Operator disposition. Until accepted:

- the database-clock/revision/epoch cutoff, history-reconstruction algorithm, confidence-window semantics, lock helper/guard scope, atomicity, and failure/bounds rules remain proposed; the PostgreSQL spike is lock-mechanics evidence only, not proof of production writer coverage; dormancy is explicitly excluded from RW-5 first release;
- no RW-5 production implementation is authorized;
- no RW4-1 or RW4-2 implementation is authorized by this document;
- RW4-1 and RW4-2 remain sequential, not parallel;
- dormant-Thread reactivation remains D6-gated;
- RW3.4 remains implementation-complete with formal acceptance deferred and all seven PARTIAL rows unchanged;
- live provider authorization remains closed;
- R7-C, persistent-database operations, and R8 remain separately gated.

After the one bounded regression review, record only regressions, contradictions, or demonstrated blockers here, reconcile the Task and architecture specifications, then request explicit authorization for the single next implementation stream. A further review round requires explicit Operator authorization and a named blocker.
