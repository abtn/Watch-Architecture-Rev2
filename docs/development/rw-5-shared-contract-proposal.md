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
- `core/models.py:957–1020`: ConfidenceChange cause, optional EvidenceLink, generic `created_by_task_id`, idempotency key, and creation time.
- `migrations/versions/0019_rw1_world_memory.py:379–446`: ConfidenceChange persistence, cause checks, and indexes. The schema has no dedicated `decay_task_id`.
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

### 4.1 Task production and authority

**Proposed split:**

- RW-5 core includes a typed, idempotent application boundary that creates an `apply_decay` Task for one Team, pins its immutable request and TeamPolicy version, and records the Task request Event atomically.
- The Task is executed and finalized only by the existing TaskRuntime and Kernel commit path.
- A periodic scheduler/host trigger is a separate integration slice, provisionally named **RW5-P**. It may invoke the typed creator but may not mutate world memory, execute Tasks, or become a second runtime.
- The current TaskDispatcher remains `ingest_source`-only. Do not expand it to schedule or execute decay.
- The external production host/authentication composition remains outside the Watch-side implementation until separately provided and authorized.

The creator must derive Team authority from a trusted host boundary, not from model output or an untrusted worker payload. The request identity must be database-arbitrated and replay-safe; an application-only precheck is insufficient. The exact identity columns/constraint must be established by a focused schema audit before implementation. Add a migration only if existing Task identity fields cannot enforce the required uniqueness.

### 4.2 Authoritative time

**Proposed choice:** the database-generated UTC `Task.created_at` is the immutable `as_of` instant for the decay Task.

- Capture it once when the Task is inserted; do not accept caller/model-supplied time.
- The Task's `as_of` is reused for every Hypothesis, every Thread, and every retry/recovery of that Task.
- Do not call the application clock independently per Hypothesis or substitute retry-start time.
- Persisting a second timestamp field is unnecessary if the existing Task creation timestamp is confirmed database-generated, timezone-aware, immutable, and available to the worker. If any of those conditions is false, stop and present the smallest schema change before implementation.

This keeps the operation reproducible: the same Task request always evaluates the same time boundary.

### 4.3 Evidence age and decay-window boundaries

**Proposed choice:** a decay window becomes due inclusively at its exact UTC boundary.

For a Hypothesis with evidence-touch baseline (t_0), Task time (t_a), and configured window (W):

[
n_{due} = leftlfloor rac{t_a-t_0}{W} ightfloor
]

No decay step is due when (t_a < t_0+W). A step becomes due when (t_a ge t_0+W). All arithmetic uses timezone-aware UTC instants and a single pinned policy version.

`last_touched_at` is an evidence-activity clock, not a generic row-update timestamp:

- Accepted supporting or challenging evidence resets the evidence-age baseline, even if the confidence band does not change.
- Mentions-only evidence, rejected proposals, retrieval, and decay itself do not reset it.
- Decay must never write `last_touched_at`.
- Any other operation that is allowed to reset it must do so atomically with its accepted evidence commit.

**Idempotency without a new age column:** first test whether the existing ConfidenceChange idempotency key and database uniqueness constraint can identify each decay window deterministically. The proposed key is a versioned hash of `(hypothesis_id, last_touched_at, window_ordinal)`. A retry for the same evidence baseline and elapsed window therefore addresses the same logical decay step; new accepted evidence changes the baseline and starts a new sequence. This is a test-backed design constraint, not a claim that no migration will be needed. Do not count decay rows using timestamps alone where equal transaction timestamps could make ordering ambiguous.

### 4.4 Confidence transition semantics

**Proposed choice:** apply one confidence-band transition for each elapsed decay window, catching up all due windows in the same Task, subject to the configured decay policy and the lowest band.

- Every actual band transition creates one ConfidenceChange with `cause_kind="decay"`, the current decay Task attribution, and the deterministic window idempotency key.
- Decay never rejects, supersedes, deletes, or otherwise changes Hypothesis lifecycle status.
- Do not create no-op ConfidenceChange rows once the lowest band is reached.
- A Task retry must not apply a window twice.
- A policy that is missing, malformed, unsupported, or internally inconsistent fails closed; do not silently fall back to a different policy version or a default guessed by the worker.

The supported policy vocabulary, defaulting rules, and exact confidence-band transition table must be frozen against the existing domain specification before implementation. The absence of a decay parser in `core/policy.py` is a source gap, not permission to add a generic policy framework.

### 4.5 Thread dormancy

**Proposed conservative rule:** a Thread may transition `active → dormant` only when the pinned policy explicitly enables dormancy, the Thread has at least one active Hypothesis, and every active Hypothesis satisfies the accepted stale/low-confidence dormancy condition at the Task's `as_of`.

- An empty active-Hypothesis set must not satisfy the condition by vacuous truth.
- Rejected and superseded Hypotheses are not active evidence and do not independently trigger dormancy.
- The exact stale threshold and confidence condition must be part of the frozen policy vocabulary, not hard-coded in a worker.
- A decay-caused dormancy transition updates the Thread lifecycle timestamp and writes exactly one Task-attributed lifecycle Event; it does not rewrite any Hypothesis evidence-touch timestamp.
- Repeated execution/recovery must not emit a second transition Event.

A dormant Thread is not reactivated by RW-5. Reactivation remains a separately gated RW-4 operation under D6.

### 4.6 Shared lock order

**Proposed common execution order:**

1. Lock the current Task row and validate its running status/current attempt.
2. Lock the Team row `FOR UPDATE` as the per-Team serialization point.
3. Lock all affected Thread rows in ascending canonical ID order.
4. Lock all affected Hypothesis rows in ascending canonical ID order.
5. Revalidate ownership, lifecycle, evidence-touch baseline, policy pin, and current-attempt preconditions under those locks.
6. Write ConfidenceChanges, lifecycle transitions, and Task-attributed Events through the existing commit boundary.

The TeamPolicy version is immutable and pinned at Task creation. Execution consumes that pinned version; it must not silently switch to the latest policy. The Team row is locked before selecting/pinning the latest policy in the creator. The creator's lock suffix must remain compatible with the common Team → Thread ordering; it must never lock a Thread/Hypothesis and then acquire the Team lock.

This order is a proposed common contract, not an assertion that every current code path already follows it. Before freeze, review every relevant RW-4/RW-5 path and record any exception explicitly. No path may acquire a lower-ranked lock after a higher-ranked one.

### 4.7 Decay/triage race outcomes

The Team lock serializes decay and triage operations for the same Team. Both operations must reload and revalidate canonical rows after acquiring it.

- **Triage commits first:** accepted evidence updates `last_touched_at`; the later decay operation sees the new baseline and does not apply a step that is no longer due.
- **Decay commits first:** triage observes the committed confidence/lifecycle state. Before D6 is accepted, a dormant candidate cannot be reactivated or reported as a successful `matched` disposition implying reactivation; the applicable RW-4 path must use the accepted terminal `deferred` outcome.
- **After D6:** the explicitly authorized reactivation path must revalidate Team, Thread state, and evidence under the same lock order and emit at most one reactivation Event.
- A losing concurrent/replayed request must return or validate the canonical committed result; it must not append a duplicate ConfidenceChange or lifecycle Event.

The integrated proof must exercise both race orders against disposable PostgreSQL. A unit test that mocks away row locks is not sufficient evidence for the serialization contract.

### 4.8 Task transaction, recovery, and per-Hypothesis failures

**Preferred design:** keep the decay business changes, summary Event, Outcome, and Task terminal transition within the existing TaskRuntime/Kernel transaction boundary where the current APIs permit it. This avoids introducing a separate receipt/commit-marker protocol solely for decay.

- TaskRuntime remains the only lifecycle and interrupted-recovery authority.
- Do not create a decay-specific runtime, scheduler-owned worker, or second recovery system.
- If atomic business commit plus terminalization is not possible, stop and design the durable commit marker/recovery contract before implementation. That alternative must be separately reviewed and tested; it is not authorized by this proposal.
- Skip only deterministic, explicitly classified per-Hypothesis ineligibility. Integrity violations, ownership conflicts, stale-attempt failures, malformed policy, and infrastructure/transaction failures must not be swallowed as ordinary per-Hypothesis skips.
- The existing Task specification says per-Hypothesis errors are logged and skipped. Before implementation, reconcile that broad wording with transaction-abort behavior: a failed PostgreSQL transaction cannot safely continue without a deliberate savepoint/rollback contract. Do not add savepoint complexity unless the accepted requirement genuinely needs it.
- The Task emits one bounded summary Event containing deterministic counts/outcomes. Event vocabulary and payload shape must be frozen with the Task contract. Do not emit repeated summary Events on retry.

### 4.9 Bounded work

The current specification describes a Team batch but does not define a proven maximum scan/write bound. Before implementation, define a deterministic per-Task bound and overflow behavior from the existing Task/policy budget model. Never silently truncate a Team's Hypotheses or partially process an arbitrary prefix while claiming the batch is complete. If the bound is exceeded, fail or defer before business writes, or use an explicitly designed continuation identity; do not invent continuation Tasks inside the worker.

## 5. Schema and migration posture

Prefer the existing Thread, Hypothesis, ConfidenceChange, Task, and Event records. In particular:

- Do not add a dedicated `decay_task_id` column merely to duplicate the generic Task attribution already present on ConfidenceChange.
- Do not add a new age/streak column if the existing `last_touched_at` plus deterministic ConfidenceChange idempotency keys can prove correct reset, catch-up, and replay behavior.
- Do not add Thread embeddings, new Domain policy subsystems, or a scheduler/runtime as part of RW-5.
- A no-migration conclusion is valid only after database-backed tests prove the existing constraints enforce the contract. If a required uniqueness or integrity invariant is not enforceable, propose the smallest migration explicitly rather than relying on application prechecks.

## 6. Required proof before RW-5 implementation exit

| Proof area | Required evidence |
|---|---|
| Clock | Task creation pins one database UTC instant; retry/recovery reuses it; caller-supplied timestamps are rejected/ignored. |
| Boundaries | Before, exactly at, and after each decay-window boundary; timezone/DST-independent UTC behavior. |
| Evidence reset | Supporting/challenging evidence resets age even without confidence change; mentions/rejection/decay do not; old decay keys cannot suppress a new baseline. |
| Catch-up | Multiple elapsed windows produce the defined sequence once; low-band floor creates no no-op writes. |
| Attribution | Every decay ConfidenceChange has exactly one valid decay Task cause; no EvidenceLink cause; cross-Team/wrong-Task attribution rejected. |
| Dormancy | Non-empty active set requirement; exact threshold; no vacuous truth; one lifecycle Event; no automatic reactivation. |
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

- the clock, lock order, age algorithm, dormancy condition, and failure/bounds rules remain proposed;
- no RW-5 production implementation is authorized;
- no RW4-1 or RW4-2 implementation is authorized by this document;
- RW4-1 and RW4-2 remain sequential, not parallel;
- dormant-Thread reactivation remains D6-gated;
- RW3.4 remains implementation-complete with formal acceptance deferred and all seven PARTIAL rows unchanged;
- live provider authorization remains closed;
- R7-C, persistent-database operations, and R8 remain separately gated.

After review, record accepted/rejected decisions here, reconcile the Task and architecture specifications, then request explicit authorization for the single next implementation stream.
