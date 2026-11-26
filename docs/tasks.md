# Task specifications
Every durable write in Watch is performed by a Task. This document is the spec for each v1 task type: what it reads, what it may write, how it runs, what is validated at commit time, and how it fails.

## Task creation authority — accepted D1 boundary (2026-11-24)

The application Control Room is the single logical authority permitted to create and persist Tasks. Host-facing adapters and feature-specific entrypoints delegate to named Control Room operations; workers, models, ingestion code, and feature modules do not create Tasks directly. Control Room is an architectural boundary/owner, not a claim that a dedicated module/service already exists. This documentation decision does not refactor source code; before the accepted D1 boundary is implemented, all nine inventoried production Task writers must delegate to named Control Room-owned operations, with no direct-persistence fallback. TaskRuntime remains the sole lifecycle/recovery authority after creation. For RW4-2's Team eligibility, authentication timing, URL-normalization deferral, and TeamPolicy selection rules, see the [accepted D1 specification](development/rw-4-2-decision-and-specification-draft.md#3-d1--trusted-host-invocation). All six D2 decisions are accepted: UUIDv5 identity, Task-schema logical-pair uniqueness, partial unique request-Event index, replay/provenance/re-triage semantics, immutable first-writer watermark semantics, and code-owned v1 matching pins (actual values deferred to D4b). No RW4-2 creator or migration implementation is authorized.

## RW implementation status and evidence contract

This is the current implementation-status summary. RW3.1–RW3.3 are accepted and merged. RW3.4 implementation and bounded recovery-marker proof follow-ups are merged through PR #178; PR #180 reconciled the current six-document project baseline. The ledger remains 28 PASS / 7 PARTIAL / 0 OPEN and formal acceptance is deferred. The Operator's 2026-11-24 sequencing exception permits RW-4/RW-5 to advance under individual staged gates; it does not blanket-authorize any slice. The approved serial order is **RW4-2 Stage A (design/decision) → RW4-1 (SignalDisposition persistence) → RW-5 canonical lock helper/Team revision/writer retrofit → RW4-2 Stage B (creator implementation) → RW4-3 (initially without dormant-Thread reactivation) → RW-5 decay implementation → RW4-4 (Context retrieval) → RW4-5 (D6 dormant reactivation and integrated proof; D6 decisions accepted, implementation separately authorized)**. Stage A is documentation/decision work only and creates no production code; Stage B requires RW4-1 and the RW-5 helper/retrofit with real PostgreSQL lock proof. This is the sequence recorded in `PLAN.md` and expanded in [the RW-4 Readiness and Delivery Plan](development/rw-4-readiness-and-delivery-plan.md) and [the sequencing decision](development/rw-4-rw-5-sequencing-decision.md). Only one production implementation stream may be active; every slice still requires its own reviewed proof subset and explicit authorization. The proposed RW-5 clock, decay, locking, Task-production, and residual-mapping contract is [here](development/rw-5-shared-contract-proposal.md). Live provider authorization remains closed. `PLAN.md` is the sole authority for milestone status and authorization; exact verification evidence is recorded in `docs/testing.md`.

| Task / entity | Current implementation state |
|---|---|
| ingest_source | Implemented for the existing deterministic Signal-ingestion path. This does not include triage. |
| triage_signal | Specified; not implemented. RW-4 slices may proceed under the 2026-11-24 sequencing exception only after their own design gates, reviewed proof subset, and explicit authorization. D6 decisions are accepted; dormant-Thread reactivation remains gated on separately authorized and proven RW4-5 implementation. See the [RW-4 readiness plan](development/rw-4-readiness-and-delivery-plan.md). |
| update_thread | RW3.1–RW3.3 are accepted; RW3.4 implementation and bounded recovery-marker proof follow-ups are merged through PR #178. The 35-row ledger remains 28 PASS / 7 PARTIAL / 0 OPEN. Formal RW3.4 acceptance is deferred; seven PARTIAL qualifications remain. See [PLAN.md](../PLAN.md), [RW3.4 closeout plan](development/rw-3-4-verification-closeout-plan.md), and [testing evidence](testing.md). Deterministic fake providers only; live provider authorization remains closed. |
| operator_update | Deterministic host-invoked Operator path implemented and formally accepted in RW-2; PR #134 merged to main. |
| apply_decay | Specified; not implemented. RW-5 may advance under its own reviewed contract, proof subset, and explicit authorization; the shared timestamp/decay/locking contract is the first step. |
| Thread / Hypothesis / ConfidenceChange | ORM persistence implemented in RW-1; deterministic Operator commit path implemented and accepted in RW-2. |
| SignalDisposition | Not implemented. D3 lifecycle and D5.1–D5.4 business semantics are accepted: matched/duplicate/deferred only; immutable Team/Signal row; required references and Task attribution; stable deferred reasons; TaskRuntime-owned atomic terminal evidence. RW4-1 physical design, schema, migration, PostgreSQL proofs, and implementation authorization remain gated. See the [RW-4 readiness plan](development/rw-4-readiness-and-delivery-plan.md). |
| EvidenceLink | RW-1 persistence and RW-2 commit path support the accepted Hypothesis/Evaluation subjects and currently usable Signal/Outcome sources; Artifact/Consultation source rows remain staged and unusable until their canonical entities exist. |

The Event-scope allow-list in `core/ingestion.py` contains future Task type names so bounded Task-attributed Events can be recorded; an allow-list entry alone is not implementation. The current `core/dispatcher.py` remains narrow and supports the configured-source `ingest_source` worker. This status summary does not authorize dispatcher expansion.

### EvidenceLink contract for RW

- ADR-0007 accepts one polymorphic EvidenceLink model with subjects **hypothesis | evaluation** and sources **signal | outcome | artifact**. Quotes must match exact offsets in immutable hashed Snapshots. Only **supports** and **challenges** may anchor a ConfidenceChange.
- ADR-0020 adds **consultation** as a source kind; an answer is an immutable hashed Snapshot and is quote-verifiable.
- RW-1 extended the existing EvidenceLink table/model with typed Evaluation/Hypothesis subject references and Task provenance under the accepted D132 design. RW-2 adds the deterministic Hypothesis commit path; the existing Evaluation service remains Evaluation-scoped. These are one logical EvidenceLink contract, not sibling evidence systems.
- Signal and Outcome are the currently usable source kinds for the RW-2 Operator path. Artifact and Consultation source kinds remain staged and must not be treated as valid references until their canonical source entities and validation paths exist.
- Preserve same-Team ownership, deterministic quote/hash/offset validation, stance rules, uniqueness, and replay behavior. If implementation requires changing an accepted ADR contract, stop for an ADR addendum and Operator decision.

## 1. Task model
- Every Task has: Team, `task_type`, optional Thread, `input_refs`, `allowed_tools`, `allowed_writes`, `policy_version`, `budget` (`max_tool_calls`, `max_cost_usd`, `deadline_seconds`), `created_at`, `attempt_count`, and a per-Task pinned `max_attempts` (initial default: 3 total starts). `completed_at` is nullable and set only for status `done`. These lifecycle fields are part of the R6 target; they are not all present in the current ORM baseline.
- Task statuses and transitions: see `docs/architecture.md` §4.
- **All durable writes go through core repositories/services** that enforce schema, ownership, scope, and transitions (INV-02, INV-14). Graph nodes return proposal objects; they never write.
- `allowed_writes` names the business/domain entity kinds that the Task's worker may propose to create or change, subject to this matrix. It does not grant the worker direct database or object-storage access.
- The matrix also marks `K` operations: explicitly bounded writes performed only by trusted application/Kernel code, never by a worker or model. They may include Task lifecycle/enqueue records, Events, Snapshots, and narrowly specified business-entity side effects (for example, `apply_decay` updating the Hypothesis confidence projection alongside its ConfidenceChange). A `K` cell authorizes only the exact operation and fields defined by that Task type's specification; it is not an exception to INV-14 and never grants general entity-write authority or worker `allowed_writes`. The application controls Task lifecycle/enqueue data and Event type, payload, and attribution; validates Snapshot content/reference and association; and performs any explicitly authorized business projection under the required locks and transaction boundary.
- Every Task transition emits a Task-attributed Event. A commit emits its required success, no-change, or rejection Event as applicable. These Kernel-generated records are constrained by the row's `K` entries; the worker cannot write them directly. Commit-time preconditions are re-checked (INV-13).
- **Per-proposal validation:** valid proposals commit atomically as one set; invalid proposals are rejected with Events carrying reasons; a Task whose proposals all fail is marked failed.
- Retries must re-execute idempotently: prior business commits are detected through canonical idempotency keys and Task Events and skipped. R6's initial policy is three total starts per Task; retry/failure transitions, attempt fencing, and interrupted-task recovery are specified in [ADR-0030](decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md).
- `TaskRuntime.admit` is the application-controlled worker-pickup boundary: it validates a pending Task, active Team (except team setup), matching TeamPolicy version, and prerequisites; then atomically increments `attempt_count`, changes `pending → running`, and records one Task-attributed `task_started` Event. The Task-row lock serializes competing claims; non-pending claims are rejected rather than replayed as a second transition. `attempt_count` counts successful starts, including retries.
- Tool calls and token usage are attributed to the Task and counted against its budget.
- Most task types require an `active` Team; `create_team`, `configure_team`, and `activate_team` operate on shell/configuring teams and are the exceptions.
- **No path bypasses validation for being human** (INV-15): operator task types use the same commit kernel, and operator identity is recorded in Event payloads.

### RW-3 `update_thread` Task envelope — accepted contract and implementation status

A newly created `update_thread` Task has the following exact shape:

- `task_type="update_thread"`; `status="pending"`; `attempt_count=0`; `max_attempts=3`.
- `team_id` is derived from the locked target Thread; `thread_id` is the same target bound by exactly one verified `update_thread_requested` Event; `policy_version` is the valid highest TeamPolicy version pinned under the Checkpoint 2 locking contract.
- `objective_id`, `plan_id`, and `plan_action_id` are `NULL`.
- `allowed_writes` is exactly `["EvidenceLink", "Hypothesis", "ConfidenceChange"]` in that order.
- `budget` is exactly `{ "max_tool_calls": 0, "max_cost_usd": 0.02, "deadline_seconds": 45 }`. The Task has no tool capability. `max_attempts` is a separate Task field, not a budget key.
- Do not add `input_refs` or `allowed_tools` Task columns for RW-3. The immutable request Event binds the target; application code assembles Context from canonical records and the Task-pinned policy. Event and Outcome remain Kernel/TaskRuntime side effects, not worker business writes.

The `$0.02` cost ceiling is cumulative across all three starts. The existing ADR-0031 Cloudflare rate card is used strictly as the approved budget-calculation baseline: it quotes at most `$0.00500224` for one maximum 30,976-input/1,024-output-token attempt and `$0.01500672` for three such reservations. ADR-0031 authorizes Cloudflare for R6-E only; Checkpoint 3 does not authorize live RW-3 provider calls. A separate explicit provider-authorization decision is required before production invocation; until then, use a deterministic fake provider. Every exact prompt is quoted and its maximum charge reserved before any authorized provider invocation; unknown/unresolved reservations continue to count in full. The only authorized cost integration is a narrow `update_thread` operation in the existing `TaskGenerationCostService`, bound to this Task type and exact write scope. The absolute 45-second deadline begins at admission and is enforced by the worker across Context assembly, provider execution, parsing, and pre-commit work; provider timeout is at most 30 seconds and cannot exceed remaining Task time. The current TaskRuntime validates the positive deadline field but does not enforce elapsed time; implementation must add only the narrow `update_thread` enforcement. The existing 60-second interrupted-task recovery threshold remains unchanged. See [RW-3 design §10.4.2](development/rw-3-design-and-acceptance.md#1042-task-shape-generation-budget-and-deadline).

### R6 first-slice lifecycle contract

**Status authority.** Current milestone status and verification evidence live only in [PLAN.md](../PLAN.md). This section records the enduring R6 lifecycle and dispatcher contract; the requirements below remain mandatory.

The sole lifecycle authority is `TaskRuntime` (an internal service may be called by it but may not become a second authority). Workers return typed results and never write Task status, attempt counters, or lifecycle Events directly.

| Transition | Required atomic effects |
|---|---|
| `pending → running` | Increment `attempt_count`; emit `task_started` |
| `running → pending` after retryable failure with starts remaining | Emit `task_attempt_failed` and `task_retry_scheduled` with attempt/reason metadata |
| `running → done` | Set `completed_at`; emit `task_completed`; persist the unique terminal `task_execution` Outcome |
| `running → failed` after non-retryable failure or exhaustion | Emit `task_attempt_failed` and `task_failed`; persist the terminal failure Outcome |

Every finalization supplies the attempt number that was admitted. A stale result from an earlier attempt is rejected if recovery/re-admission advanced the attempt. The first worker has a 30-second execution deadline; a still-running Task whose last start is older than 60 seconds at dispatcher startup is recovered to pending if starts remain, otherwise failed. This is compare-and-set recovery in the existing runtime, not a new scheduler.

`TaskRuntime.recover_interrupted()` implements that recovery. It is a method on the existing runtime, not a second runtime or scheduler. Discovery is read-only; every candidate is rechecked under the Task-row lock before any change, so a Task that completed, was re-admitted, or was already recovered by another caller is skipped rather than overwritten. Staleness is judged from the latest `task_started` Event of the Task's **current** attempt, so an older start from a previous attempt cannot make a newly admitted attempt look stale; the age comparison is strict, so a start exactly 60 seconds old is not yet stale. A `running` Task with no start Event for its current attempt is inconsistent recorded state: it is reported in the result (`inconsistent`), never reset and never assigned a fabricated start time. Retry recovery reuses the durable retry disposition and creates no Outcome or Snapshot; exhausted recovery delegates to the single terminal finalizer and derives `observed_at` from the durable current-attempt start, so repeated or concurrent recovery replays instead of conflicting.

`TaskDispatcher` (`core/dispatcher.py`) is the R6-B execution path for this contract. It runs `recover_interrupted()` at startup, finds one eligible `pending` `ingest_source` Task, resolves that Task's durable source from its `PlanAction`, fetches it with the approved restricted fetcher, commits the bytes through `IngestionService`, and reports the result through `TaskRuntime`. It never writes Task status, attempt counters, lifecycle Events, or terminal Outcomes/Snapshots itself, makes at most one attempt per call, and grants no tool capability. Durable source identity must come from the Task's Plan Action (`origin_url`, `source_type`) and be authorized by `TeamPolicy.rules["sources"]`; a Task with no Plan Action has no durable source identity and is rejected before admission rather than guessed at.

For the initial `ingest_source` worker, transient transport failures/timeouts and HTTP 408, 429, and 5xx may retry. Unsafe/mismatched URLs, redirects, unsupported media types, malformed data, other 4xx responses, and application validation errors are non-retryable. The full URL/DNS/IP, redirect, timeout, and byte-limit contract is in [ADR-0030](decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md). Each dispatcher invocation makes at most one attempt; it must not spin in an unbounded retry loop.

The terminal Task status, terminal Task Event, and terminal Outcome are committed atomically. The ingestion business commit remains independently atomic and idempotent; replay after a crash must reuse that result and never duplicate Signal, terminal Event, or Outcome.

### TeamPolicy daily Task-start quota
> **Authority status:** ADR-0027 remains `Proposed`; this paragraph does not change that formal status. For R5-A, the operator has explicitly directed verification and correction of the existing configured quota path against the behavior below. Keep the implementation auditable and report any conflict that cannot be resolved from these requirements. Do not imply that this Task-count quota enforces monetary or token spend.
When a TeamPolicy configures `rules["budgets"]["max_tasks_per_day"]`, the
application must enforce it as an aggregate limit on successful Task starts
for that Team during each UTC calendar day.
- **Counting window:** Count durable `task_started` Events for Tasks belonging
to the Team whose `created_at` timestamp falls within the current UTC day,
from 00:00 UTC inclusive to the next 00:00 UTC exclusive.
- **What consumes quota:** Every successful `TaskRuntime.admit` transition from
`pending` to `running` consumes one unit. A later successful start after a
retry has returned the Task to `pending` consumes another unit.
- **What does not consume quota:** An admission rejected before the successful
start does not consume a unit and must not create a `task_started` Event.
- **Atomicity:** The quota check must be serialized across concurrent
admissions for the same Team at the database level. The quota check, Task
status transition, `attempt_count` increment, and `task_started` Event must be
committed in one transaction. A rejected admission or transaction failure
must not leave partial Task or Event changes.
- **Configuration:** If `max_tasks_per_day` is absent, preserve the existing
no-limit behavior. If configured, it must be a non-negative integer; `0`
allows no successful starts for that Team on that UTC day. Booleans are not
valid integer quota values.
- **Separate from Strategy limits:** `StrategyProposal.constraints.max_tasks`
is an upper bound on the Actions authorized by one Strategy, not a daily Task
quota. It must not be compared with `max_tasks_per_day`.
- **Scope:** This rule enforces a Task-start count quota only. It does not mean
that daily cost quotas are enforced.
**Creation sources:** Triggers (all three types), separately implemented and authorized host/scheduler integrations (including ingestion, review, and overdue scans; decay requires the distinct RW5-P gate), explicitly authorized Task enqueues (consultation follow-ups), and Task retries. Manual Operator Tasks are created by a thin in-repository application adapter invoked in-process by a host after it authenticates and authorizes the Operator. This is not a separate deployed Watch API/CLI. R6-F Checkpoint 3 implements the adapter for `approve_learning_change`; RW-2 adds `operator_update` through the same host boundary. Other manual Task specifications do not imply implemented callers.
## 2. Common validation rules (every commit path)
1. Task status is `running` and budget is not exhausted (operator task types: no model cost, no enforced deadline).
2. All referenced entities exist and belong to the Task's Team.
3. All worker-proposed business writes are within `allowed_writes` and the Task's scope matrix entry (§4). Kernel-managed side effects are permitted only where the same row explicitly marks `K`, and only in the documented association with that Task operation.
4. Snapshots referenced by quotes exist and hashes match (INV-03, INV-04).
5. All state transitions are legal per the architecture §4 tables.
6. The Task's Team is `active`, except for the team-setup task types.
7. Before a Plan-linked Task transitions from `pending` to `running`, the existing Task admission/claim path verifies that every prerequisite action's linked Task is `done` (INV-16). Otherwise it remains ineligible; a failed prerequisite does not release dependents. No new Task state or separate dependency scheduler is introduced.
## 3. Task types
### `ingest_source` — deterministic
- **Purpose:** poll one configured source; create Signals.
- **Reads:** source configuration, recent Signal hashes for the origin.
- **Writes:** Signal (+Snapshot first), Event.
- **Flow:** F1 steps 1–3.
- **Validation:** identical `(origin_url, content_hash)` → no new Signal (fetch-no-change Event); Snapshot stored before Signal commit; atomic.
- **Failure:** connector error → retry per arq policy. Signal and Event database records commit together or not at all. Snapshot bytes are stored first in immutable content-addressed object storage; a failed database commit may leave an unreferenced object, but no committed Signal may reference a missing object.
- **Budget:** no model calls; see §5.
#### K1 implementation boundary
K1 exercises the deterministic proposal/validation/commit path only. It
receives fetched bytes and source identity in a transient typed application
object; it does not poll a source or implement a connector, scheduler, Trigger,
Task creation/runtime, triage, or embeddings. The fixture supplies an active
Team, the policy version referenced by the Task with matching source
configuration, and a running, in-scope
`ingest_source` Task.
In development, Snapshot bytes use the immutable content-addressed local
filesystem storage specified in `docs/architecture.md` §10. The reference and
hash are persisted on Signal; K1 does not store bytes in PostgreSQL or require
a separate Snapshot table. Snapshot objects are written and verified before
database references are committed. The Signal row and success Event commit in
one database transaction. A failed transaction may leave an unreferenced
immutable file; such a file is not visible as committed domain state, and a
retry reuses it. K1 does not add garbage collection.
`fetch_no_change` is the documented Event for identical
`(origin_url, content_hash)`. The walkthrough uses `proposal_rejected` for a
rejection; the architecture requires rejection Events with reasons but does
not fix a string type. K1 uses `proposal_rejected`. The success Event name is
not fixed in the architecture; K1 may use `signal_ingested` as a local choice.
Every Event is attributed to the Task. Events for a Task's already-recorded
matching outcome are reused on retry; the retry emits no second outcome
Event.
The Signal fields required for K1 are `domain`, `source_type`, `origin_url`,
`fetched_at`, `content_hash`, and `snapshot_ref`. `domain` comes from the
Team. `extracted_summary` is optional/non-authoritative; `embedding` and
`embedding_model` are projections and are not generated or required by K1.
### `manual_signal_ingest` — Operator via host-invoked application adapter
- **Purpose:** admit externally obtained material with provenance.
- **Writes:** same as `ingest_source`. A host application authenticates/authorizes the Operator and invokes the in-repository manual-Task adapter; the adapter creates the ordinary Task. This caller is not implemented by the current R6-F slice, which first supplies the adapter for `approve_learning_change`.
- **Validation:** same as `ingest_source`.
### `triage_signal` — deterministic

**Implementation status:** Specified; not implemented. Planned for RW-4. This Task remains outside the RW3.4 `update_thread` implementation and its acceptance boundary.
- **Purpose:** record a deterministic Team-specific disposition for one canonical Signal.
- **Decision status:** D1 and all six D2 decisions are accepted; D3-A/B/C were accepted on 2026-11-25. D4.1/D4.1a/D4.2/D4.3, D5.1–D5.4, and D6.1–D6.6 are accepted (issues #191, #193, #195). D4 evidence closure remains open for Team/hash persistence, PostgreSQL arbitration, measured thresholds/margin/score serialization/bounds/query cost, and actual pins. D6 implementation remains a separately authorized RW4-5 gate.
- **Reads under the accepted design:** canonical Signal and Snapshot; same-Team ingestion provenance and the Team/hash canonical-duplicate association; Team-scoped EvidenceLink → Hypothesis → Thread evidence; compatible existing KnowledgeChunk projections under immutable embedding-space and chunking pins. Candidate Threads may include same-Team/same-Domain active or dormant Threads for evaluation; resolved is excluded. A matched disposition requires the selected Thread to be `active` at the serialized decision commit point. Under accepted D6, a dormant Thread may receive a v1 `matched` disposition only when it is the unambiguous matcher winner and no active candidate wins, with same-transaction `dormant → active` reactivation before disposition insertion and one immutable Task-attributed `thread_reactivated` Event. Until RW4-5 is separately authorized and proven, such a dormant would-be winner continues to defer with `dormant_thread_requires_reactivation`. Later valid transitions to dormant/resolved do not invalidate the historical disposition or its replay. `Thread.domain` must match the Team domain at decision time and is immutable after a matched disposition references the Thread; a database guard rejects later changes. No status/domain snapshot columns are added to SignalDisposition. Only supports/challenges EvidenceLinks count; mentions alone is insufficient. No Thread embedding, model call, re-embedding, or new matching subsystem.
- **Write boundary:** RW4-1 owns SignalDisposition persistence and Task-attributed provenance; no model/worker business writes. The triage Task envelope remains `allowed_writes=[]`; any disposition write is a narrowly specified Kernel-managed effect, not a worker grant. D3 requires an existing disposition to exclude another v1 decision and makes a deferred disposition immutable/terminal. D4.3 excludes automatic Thread creation; no qualifying existing match or ambiguous/insufficient evidence becomes terminal deferred. D5.1–D5.4 freeze the vocabulary, reference matrix, deferred reason codes, and atomic terminal evidence. D6.1–D6.6 are accepted; dormant reactivation remains unavailable until separately authorized and proven RW4-5 implementation.
- **Outcome distinction:** a valid business decision to defer is persisted as a terminal immutable `deferred` disposition with a durable reason and the Task completes successfully as `done`. The disposition, Task attribution/reason, TaskRuntime `task_execution` Outcome, terminal Task status, and `task_completed` Event commit or roll back in one TaskRuntime-owned transaction; the Kernel persistence operation uses the active Session and never commits independently. Technical execution/integrity failures are not deferred dispositions; they follow TaskRuntime retry/recovery and may end as `failed`. Eligibility failures before Task creation reject without a Task. D4 specifies exact raw content-hash duplicates within the same Team regardless of origin, with the first successfully committed Team/hash association as canonical winner; cross-Team and near-duplicate matches are excluded. A non-duplicate with no qualifying existing Thread match, insufficient/ambiguous evidence, or a dormant candidate blocked by the not-yet-implemented RW4-5 path becomes terminal deferred. No automatic Thread creation or URL/model title fallback is permitted.
- **Integrity/replay failure:** if a disposition exists without its canonical Task and exactly one valid request Event, or the identity/Event is missing, duplicated, malformed, or inconsistent, fail closed. Do not synthesize history, create a replacement Task/Event, or mutate the disposition.
- **Superseded queued Task:** RW4-3 must terminally supersede a Task whose pins are no longer supported through TaskRuntime's existing terminal non-success path: status `failed`, result category `terminal_failure`, stable reason `matching_pins_superseded`. This is not a technical execution fault or retryable attempt failure; no new Task status/category is added. RW4-3 must prove this mapping before triage execution is enabled.

**RW-4 authority note:** the older generic target description (Thread embeddings, Domain matching configuration, automatic new-Thread creation, and deferred refinement) is not implementation evidence. D1/all D2, D3-A/B/C, D4.1/D4.1a/D4.2/D4.3, D5.1–D5.4, and D6.1–D6.6 are accepted. D4's accepted scope is exact same-Team raw-hash duplicates with first-committed canonical association, a bounded existing-Thread evidence matcher, and no automatic Thread creation; near-duplicates and automatic noise are excluded. The matcher parameters, Team/hash persistence mechanism, query-cost evidence, and D4b pin values remain open. Deferred is terminal/immutable in v1 and is a successful Task result (`done`), not a technical Task failure. RW4-1 physical persistence remains gated on its reviewed design, proof subset, and separate authorization; RW4-2 Stage B remains gated on its migration/compatibility/proof requirements and separate authorization; RW4-3 remains gated on D4 evidence closure, C1, accepted D5, stale-pin supersession proof, and the canonical lock helper. D6 is accepted; dormant-Thread reactivation remains confined to RW4-5 after RW4-4 and requires its own implementation design, proof, and explicit authorization. See the [RW-4 readiness and delivery plan](development/rw-4-readiness-and-delivery-plan.md).
### `update_thread` — model worker

**Implementation status:** RW3.1–RW3.3 are formally accepted. RW3.4 implementation and bounded recovery-marker proof follow-ups are merged through PRs #152, #163, #165, #167, #169, and #178; the 35-row ledger remains 28 PASS / 7 PARTIAL / 0 OPEN. Formal RW3.4 acceptance remains deferred; RW3.4 is not formally accepted or closed. PR #178's terminal-marker tests prove fail-closed refusal rather than terminalization when marker identity is ambiguous. Deterministic fake providers only; live provider authorization remains closed. See PLAN.md for current status and docs/testing.md for exact verification evidence.

- **Purpose:** incorporate new evidence into one existing Thread's world model through a bounded model proposal and the shared RW-2 commit boundary.
- **Trusted target:** Team and Thread are resolved from the immutable Task request and canonical database state. Model output cannot select or override them.
- **Reads:** target Thread; all active same-Thread Hypotheses ordered by `(created_at ASC, id ASC)`; every accepted EvidenceLink belonging to those Hypotheses ordered by `(hypothesis_id ASC, created_at ASC, id ASC)` (no relevance ranking or discretionary filtering); exact immutable source Snapshots ordered by reference; only the TeamPolicy version pinned by the immutable Task's `policy_version`. A missing, invalid, inconsistent, or cross-Team policy pin fails closed before provider invocation; never substitute the latest policy. Bound to 8 Hypotheses, 8 EvidenceLinks, 8 Snapshots, and 8,000 Unicode characters of evidence text; overflow fails closed after admission and before provider invocation. Team Experience is excluded from RW-3 because the existing Task Context assembler is scoped to `propose_strategy`; no new retrieval integration is added. SignalDisposition and triage state are excluded (RW-4).
- **Writes:** exactly EvidenceLink, Hypothesis (create/supersede/reject), and ConfidenceChange. Event and Outcome remain Kernel/TaskRuntime side effects. **Not:** SignalDisposition, Thread creation/reactivation/summary projection, KnowledgeItem, TeamPolicy, Artifact, Consultation, worker-written Outcome, or other Threads.
- **Task creation and authorization:** `create_update_thread_task(principal, request)` is a narrow host-invoked operation modeled on R6-F. The frozen request contains only `thread_id` and a UUID `idempotency_key`; Team is derived from the locked target Thread, not accepted from the caller. The trusted host authenticates the Operator and issues `TrustedOperatorPrincipal` with the exact `OperatorGrant(team_id, action="request_update_thread")` only after host-side authorization. Watch independently checks that exact grant against the Team derived from the Thread, validates active Team and available same-Team Thread state, then atomically creates the Task and request Event. Missing/wrong-type/malformed principal, wrong Team/action, cross-Team/inactive-Team/unavailable/resolved Thread reject with no Task/Event. The host-supplied principal is an in-process trust contract, not a credential; the repository has no production host composition root, so end-to-end host authentication remains unproven until integrated. The request Event stores canonical `requested_by_operator_id`, and the request fingerprint binds it; same-Team/key replay by a different Operator or for a different Thread conflicts; the same UUID under another Team is a separate Team-scoped identity. Policy advancement alone does not invalidate replay; the original Task policy pin is retained. The model worker receives only the existing Task/request Event and never receives or fabricates an Operator principal or `operator_id`. This does not add Watch authentication, a deployed API/CLI, or a second Task creator.
- **TeamPolicy pinning and concurrency (Checkpoint 2 approved):** for a new Task, resolve Team from the target Thread, lock Team `FOR UPDATE`, then lock/revalidate the Thread, and select the highest TeamPolicy version for that Team with `FOR SHARE`. Validate the selected newest row's Team, supported `schema_version`, and existing rules relevant to `update_thread`; if it is invalid, fail closed without falling back to an older version. Persist the same `policy_version` in Task and request Event atomically. There is no active-policy pointer. Same-key replay uses the existing Task's pinned historical version even after a newer version is published; Context and execution use that pin. TeamPolicy versions are append-only and immutable by application contract; the current schema does not enforce row immutability. Any future publisher must lock Team `FOR UPDATE` before allocating/inserting the next version, serializing with Task creation through PostgreSQL's Team foreign-key lock. The current `core/policy.py` provides narrow daily-quota and D7 review-interval parsers, not a universal rules-schema validator: validate supported `schema_version`, require a rules object, and apply existing validators only to rules actually consumed. New `update_thread` policy vocabulary requires a separate decision. No publisher, policy mutation, active pointer, schema change, or migration is added here; the repository currently has no production TeamPolicy publisher. See RW-3 design §10.4.1 and proof `RW-POL-01`.
- **Worker flow:** a separate model-worker adapter consumes an already-created `update_thread` Task; read-only validation of its immutable request and trusted target → TaskRuntime admission → attempt-bound Context assembly/validation → maximum cost reservation → existing generation provider → raw usage reconciliation and exact current-attempt charge validation → strict typed parsing (maximum 8 model proposals) → shared RW-2 validation/transaction core through a narrow trusted actor seam → TaskRuntime finalization. Reconcile known usage even if the response body is malformed; unknown, unreconciled, or overrun charges cannot authorize business writes. Context failure after admission is recorded through TaskRuntime and makes no provider call. Do not extend TaskDispatcher or add a scheduler/second runtime. The current `WorldMemoryCommitService` is Operator-specific and cannot be called unchanged: extract/reuse its validation and atomic transaction core while preserving RW-2 Operator principal checks and Event behavior; model actor identity is fixed by application code and Task-attributed, never supplied by model output. Cost must be reconciled and accepted before any business commit.
- **Commit-time validation:** identical to RW-2; no model-specific exception. Preserve exact Snapshot quote/hash/offset checks (INV-04), stance rule (INV-06), confidence cause pairing (INV-05), legal transitions/reasons (INV-07), Team/Thread ownership, low initial confidence, idempotency, replay, concurrency, and atomic accepted-set semantics (INV-14/INV-15).
- **Batch semantics:** preserve the accepted RW-D18/RW-2 contract: invalid proposals receive attributable rejection Events; valid proposals commit atomically as one accepted set; the Task fails only when all proposals are rejected. Mixed valid/invalid batches may commit the valid set only. A transaction failure rolls back the entire accepted set. The model response is capped at 8 proposals; the existing Operator request limit of 64 is unchanged.
- **Generation-cost boundary:** the existing cost service currently has no `update_thread` operation. RW-3 requires a narrow extension mapping a distinct operation to Task type `update_thread` and exactly the declared three-write scope, with provider/model/rate-card/output-bound validation. No new cost subsystem or provider authorization is implied.
- **No-op:** an explicit empty model `proposals` list is valid. After charge reconciliation, persist its validated-proposal Event, skip commit and business writes, and finalize through TaskRuntime as `success_no_change`; do not retry. Recovery treats this durable empty set as success.
- **All-invalid terminal result:** a non-empty validated-proposal Event cannot be terminalized as failure without its matching `update_thread_rejected` marker proving every proposal was rejected. If the marker is absent, the proposal set remains resumable through the shared commit core. An empty proposal Event cannot become `terminal_failure`.
- **Failure:** Context failures after admission, provider failures, parser/schema/authority/count/output-bound failures, and all-invalid batches use TaskRuntime's terminal/retry path as specified by failure class. Parser failures are non-retryable and create no per-proposal rejection Events; structurally valid domain-invalid proposals use the existing attributable rejection Events. Unknown, unreconciled, or overrun cost cannot authorize business commit. No semantic repair/re-proposal loop or hidden provider retries.
- **Provider compatibility limits (not authorization):** retain ADR-0031's constraints unchanged: at most 8 retrieval-derived passages and 8,000 Unicode characters; the exact prompt quote uses UTF-8 byte lengths plus 128 framing tokens; input plus configured output must fit the 32,000-token model context; output is capped at the existing configured maximum of 1,024 tokens. The existing Cloudflare model is the fixed budget/compatibility baseline, but ADR-0031 authorizes it for R6-E only. Live RW-3 provider calls require a separate explicit provider-authorization decision; until then use a deterministic fake provider. If separately authorized, retain one non-streaming request per invocation, no tools, and no adapter-level retries. TaskRuntime owns retries and preserves the existing three-start Task limit.
- **RW3-0 decisions recorded for independent review:** deterministic exhaustive Context membership and canonical ordering with fail-closed bounds (8 Hypotheses, 8 EvidenceLinks, 8 Snapshots, 8,000 evidence characters); immutable Task-pinned policy; Team Experience excluded; separate host-invoked Task creator and model-worker adapter without TaskDispatcher expansion; maximum 8 model proposals while preserving accepted mixed-batch semantics; atomic response-receipt/charge reconciliation; durable proposal-set fingerprint and commit/rejection marker; crash-safe TaskRuntime replay; empty response as successful no-op after charge reconciliation; parser failures separated from proposal-level rejection Events. The actor-neutral commit seam is also documented. These decisions do not authorize implementation. See [RW-3 design and acceptance plan](development/rw-3-design-and-acceptance.md).
- **Verification:** deterministic fake-provider tests are mandatory; live provider smoke tests, if later requested, are separate and cannot replace deterministic proofs or become a CI dependency.

### `operator_update` — Operator via host-invoked application adapter

**Implementation status:** the deterministic Operator path was formally accepted in RW-2 on 2026-11-18 and PR #134 was squash-merged to `main` at `601f7816eaa51495d7d40d4b9d32d846122b4a59`. Exact-head local and hosted verification are recorded in `docs/testing.md`.
- **Purpose:** a human expert contributes directly to world memory — their own hypotheses, evidence, confidence judgments, and explicit transitions (ADR-0021).
- **Shared contract:** Operator and model paths use the same proposal and commit-validation contract. RW-2 implemented and accepted the deterministic human entry. RW3.1 is implementing the host Task creator and bounded Context; the model worker remains unimplemented and separately gated.
- **RW-2 implemented writes:** Hypothesis creation/transitions, EvidenceLink addition from Signal/Outcome, and evidence-caused ConfidenceChange. The Task's `allowed_writes` are exactly `["EvidenceLink", "Hypothesis", "ConfidenceChange"]`; the target Thread is bound by the immutable `operator_update_requested` Event. Event and Outcome writes are Kernel/TaskRuntime side effects, not worker `allowed_writes`.
- **Commit-time validation:** exact Snapshot reference/hash/quote offsets (INV-04), stance rule (INV-06), cause pairing (INV-05), legal transitions with reasons (INV-07), Team/Thread ownership, idempotency, replay, concurrency, and atomic proposal-set commit (INV-14/INV-15). Every new Hypothesis starts at `low`; higher confidence requires a later Task-attributed ConfidenceChange.
- **Explicit deferrals:** creating/refining SignalDisposition remains RW-4-owned; `update_thread` and `operator_update` cannot refine a triage disposition, including terminal deferred. Thread summaries and retrieval projections remain deferred to the retrieval slice; Artifact/Consultation sources remain staged until their canonical entities and validation paths exist.
- **Failure:** invalid proposals are rejected with attributable Events; the Task fails only when every proposal is rejected. Human identity is never a validation exemption (INV-15).
### `apply_decay` — deterministic Task; periodic host trigger separately gated

**Implementation status:** specified; not implemented. Planned for RW-5. The proposed shared contract is documented in [RW-5 Shared Contract](development/rw-5-shared-contract-proposal.md) and remains subject to Operator review; it does not authorize implementation. The deterministic Task creator/executor belongs to RW-5 core; periodic scheduler/host invocation is a separate proposed RW5-P integration.
- **Purpose:** lower confidence of stale Hypotheses using one database-captured immutable `as_of` persisted in the canonical Task request.
- **Task production:** a typed, idempotent creator pins the already-active TeamPolicy, decay epoch, algorithm version, one raw database-captured `as_of`, the Team's monotonic `world_memory_revision` watermark, and a bounded immutable history-watermark manifest containing exactly the same-Team Hypotheses whose canonical lifecycle status is `active` at the Task's serialized Team-revision cutoff. `superseded` and `rejected` Hypotheses are excluded from the manifest and receive no decay baseline or decay writes. It acquires Team `FOR NO KEY UPDATE`, captures raw PostgreSQL `clock_timestamp()` as `as_of` and the current Team revision, then inserts Task + request Event in the same transaction. Decay execution uses Task `FOR UPDATE` → Team `FOR NO KEY UPDATE` → sorted Thread → sorted Hypothesis; history writers/epoch transitions without a Task use Team → sorted affected rows. The Task manifest records the observed epoch high-water mark and `clock_rebase_generation` as audit/execution-fence metadata, not deterministic identity inputs; only a successfully committed decay run advances the mark. If a later committed run advances the mark past this Task's immutable `as_of`, TaskRuntime terminalizes it as `stopped` with reason `decay_task_superseded` and does not retry it; the producer must create a new Task with a fresh `as_of`. A backward raw clock fails closed until the named Operator-authorized `rebase_decay_epoch_clock` procedure resets the mark, increments the generation, and appends an audit Event. Tasks pinned to an older generation are terminally stopped as `decay_task_superseded`. The clock measures elapsed time; the Team revision defines serialized history membership. Initial epoch bootstrap is a separate trusted Kernel/application epoch-transition operation requiring explicit Operator authorization and an atomic complete baseline set; the Task creator cannot create epochs or synthesize baselines. TeamPolicy/algorithm version changes likewise require that trusted atomic transition boundary. Until the production publisher/transition boundary is implemented and proven (`RW-POL-01` remains PARTIAL), version changes are unsupported and decay remains disabled/deferred for the affected Team. Legacy Hypotheses receive immutable cutover baselines with no retroactive catch-up. Migration initializes existing Team revisions to 0 and marks existing Hypothesis/EvidenceLink/ConfidenceChange/history Event rows with `team_revision=0`, `epoch_id=NULL`, and `accepted_at=NULL`; new metadata remains nullable for this reserved legacy shape, while constraints require complete metadata on all new positive-revision rows. No legacy timestamp is promoted to a new acceptance instant or decay anchor. Periodic host/scheduler invocation remains separate RW5-P integration. Retries/recovery reuse every original semantic pin; observed high-water and rebase generation are audit/fencing metadata, not identity inputs. A duplicate creator request with the same deterministic identity and semantic request but changed operational clock metadata returns the original stored Task envelope; only corruption of the stored envelope itself is an integrity failure. Superseded Tasks are terminal and not retried; the producer creates a fresh Task. Callers and models cannot supply timestamps or watermarks.
- **Reads:** pinned TeamPolicy/epoch/algorithm; exactly the active Hypotheses at the Task's Team-revision cutoff; canonical accepted supporting/challenging EvidenceLink history ordered by Team revision with stable record ID only as a deterministic tie-breaker where no domain order exists; ConfidenceChange history ordered strictly by `(team_revision, transition_ordinal)`, never UUID/record ID. The exact last EvidenceLink and ConfidenceChange IDs are recorded in the Task manifest. The manifest is the complete deterministically ordered active-Hypothesis population at that cutoff, plus the versioned first-release limits `max_hypotheses=500`, `max_history_rows=10000`, and `max_transaction_duration_ms=5000`; the complete set must fit those limits in one Task. Count overflow terminally rejects admission with `decay_manifest_overflow`, creates no Task/request Event, and emits one durable operator-visible `decay_task_rejected` Event; duration overflow rolls back all business writes and TaskRuntime terminalizes the Task as `stopped` with Outcome reason `decay_execution_limit_exceeded`, without automatic retry. No truncation, pagination, partitioning, retry loop, or silent skip is allowed; no active row may be omitted and excluded lifecycle states are not represented. The initial confidence band must come from immutable creation/baseline history, and current confidence must be reconstructed by replaying ConfidenceChanges in the required ordinal order and checked against the mutable Hypothesis field. Existing world-memory writes currently use application-captured `committed_at`; other ORM defaults use PostgreSQL `now()`. Neither is a trustworthy database acceptance timestamp. `last_touched_at` is only a query accelerator and must be checked against history before mutation.
- **History-writer prerequisite:** before decay Tasks can execute, the current WorldMemoryCommitService writer must use the canonical world-memory write-lock helper, which allocates the Team revision once and stamps revision, epoch, and raw database-captured acceptance instant on Hypothesis, EvidenceLink, ConfidenceChange, and their Events. Replayed commits must not advance the revision twice. This changes an accepted RW3.4 path and requires separate explicit authorization and review; it is distinct from the deferred global before_flush guard retrofit.
- **Writes:** for each actual transition, trusted Kernel code atomically appends one ConfidenceChange (`cause_kind="decay"` only, exact Task attribution and transition ordinal) and updates the same Hypothesis `confidence` projection to that row’s `to_confidence`; both are committed or rolled back together. These are Kernel-managed application side effects, not worker/model-authored proposals. The Task write-scope matrix grants `apply_decay` bounded `K` authority for Hypothesis confidence projection and ConfidenceChange only; it grants no worker `allowed_writes` and no lifecycle/status mutation. One bounded Task-attributed summary Event is committed in the same TaskRuntime transaction. Team revision allocation/stamping is Kernel-owned coordination metadata performed by the canonical write-lock helper for accepted relevant history writes; epoch `last_clock_at` advances only in the committed decay transaction, and `clock_rebase_generation` changes only through the named Operator-authorized rebase. Worker/model code cannot mutate Team. No Thread status or lifecycle/activity timestamp writes in RW-5 first release.
- **Flow:** F3 confidence decay only, and only for Hypotheses whose canonical lifecycle status is `active` at the Task cutoff. `superseded` and `rejected` Hypotheses are never decayed. If a manifest member becomes non-active before execution, skip that member with stable reason `hypothesis_not_active`; other eligible active members may proceed. Unknown lifecycle values fail closed. Thread dormancy remains excluded until a durable reactivation/recovery path is implemented and separately authorized. D6 decisions are accepted but do not authorize a dormancy writer.
- **Validation:** never rejects a Hypothesis; never changes `last_touched_at`; only this Task type may write decay causes (INV-08). Validate the pinned positive `decay_window` and the single supported one-band-per-window `decay_action`; unsupported/missing values fail closed. Under the canonical locks, revalidate lifecycle status and compare current per-Hypothesis history and epoch with the Task's immutable manifest: a manifest member no longer `active` is skipped with `hypothesis_not_active`; newer evidence resets the baseline and is skipped at the older `as_of`. These two conditions are per-Hypothesis ineligibility and do not prevent other still-valid manifest members from proceeding. Any newer ConfidenceChange, mismatch between reconstructed history and current confidence, or superseded epoch invalidates the Task's pinned confidence decision and aborts the entire Task transaction; no Hypothesis in that batch is committed. Before writing, reconstructed confidence must equal the mutable projection; after every transition, the projection must equal the appended ConfidenceChange `to_confidence`. Unrelated Team revisions do not invalidate unchanged Hypothesis history. Database uniqueness and immutable-request constraints enforce cross-Task idempotency and reproducibility; application prechecks are not the guarantee.
- **Failure:** deterministic per-Hypothesis ineligibility (`hypothesis_not_active` or newer evidence after the pinned cutoff) is summarized with an explicit reason; other eligible members may proceed. A missing, corrupt, or unreconstructable baseline/history entry for any active Hypothesis makes the complete manifest invalid: if the immutable creation Event or epoch-baseline anchor is missing, Task creation is rejected with stable reason `decay_anchor_unavailable`; this check occurs before inserting the Task row, request Event, or partial manifest. Other incomplete or unreconstructable manifest/history state is rejected with stable reason `decay_manifest_incomplete`. No active row is omitted or represented by a fabricated/deferred placeholder, and neither reason admits a partial Task/request Event. The same all-or-nothing rule applies to epoch bootstrap/successor transition: if any active Hypothesis cannot receive a valid baseline, the transaction creates neither a partially populated epoch nor an active epoch. Once a Task exists, a missing, corrupt, or unverifiable pinned anchor is an execution-time integrity failure that aborts the entire Task transaction; it is never a per-Hypothesis skip. At execution, any newer ConfidenceChange, confidence-projection mismatch, superseded epoch, integrity, ownership, stale-attempt, policy, lock, or transaction failure aborts the entire atomic Task commit; do not convert these failures into per-Hypothesis skips. A pinned transaction-duration limit breach rolls back business writes and is terminally recorded as `stopped` / `decay_execution_limit_exceeded`, not retried. No partial ConfidenceChange, summary Event, successful Outcome, or successful terminal Task state may commit. TaskRuntime owns retry/recovery and terminalization.
### `check_triggers` — deterministic, scheduled
- **Purpose:** evaluate threshold Triggers; fire scheduled ones on schedule.
- **Reads:** active Triggers, current entity state for conditions.
- **Writes:** Trigger `last_fired_at`/`next_fire_at`; creation of the Trigger's target Task; Event.
- **Validation:** a Trigger creates Tasks only — it never mutates world memory or publishes output.
### `review_knowledge` — deterministic ordinary Task (Checkpoint 4 implementation)
- **Purpose:** mark due same-Team KnowledgeItems as requiring review; this is a lifecycle/status operation, not a knowledge judgment.
- **Task production:** the host/scheduler may enqueue an ordinary `review_knowledge` Task. The producer only creates the Task; it never changes KnowledgeItem state. There is no Watch-owned schedule loop, second runtime, or TaskDispatcher expansion.
- **Execution:** `TaskRuntime.complete_knowledge_review(task_id)` composes the existing `TaskRuntime.admit()` and typed `finalize()` transitions. It accepts an already-created Task only; unsupported Task types, malformed Task shape, non-pending attempts, and wrong result categories fail closed. A repeated call after successful completion replays the original terminal Outcome rather than starting a second attempt.
- **Reads:** same-Team KnowledgeItems with `status="active"` and non-null `review_after <= observed_at_utc`; the operation uses one timezone-aware UTC observation time. NULL dates are unscheduled and remain ineligible for retrieval.
- **Writes:** for each due item, KnowledgeItem status `active → needs_review` and one Task-attributed `knowledge_items_reviewed` Event. The row lock, canonical LearningChange/approval provenance check, status/date recheck, Event, terminal Outcome/Snapshot, and Task completion share the existing TaskRuntime transaction; rollback leaves no partial transition.
- **Due boundary:** due when `now_utc >= review_after`; retrieval excludes the item at this same boundary even if the scheduled Task has not yet run.
- **Validation:** only the current accepted same-Team canonical KnowledgeItem may transition. This Task never calculates/changes `review_after`, revises/retires an item, or moves `needs_review → active`. Revalidation/reactivation requires a separately specified and authorized operation.
### `render_output` — model worker + deterministic assembly
- **Purpose:** produce an Artifact from the current world model.
- **Reads:** Thread, active Hypotheses, verified evidence packs, relevant active KnowledgeItems, current policy, prior Artifacts.
- **Writes:** Artifact (+Snapshot +hash), Event. **Not:** any world-memory entity (INV-14).
- **Flow:** F4. Delivery gating: if a policy-required Consultation on the subject is open, the Task ends after recording an Event and enqueuing `request_consultation` — it does not wait inside the Task (ADR-0020).
- **Commit-time validation:** evidence pack quotes pre-validated; deterministic post-check rejects bodies containing URL/link patterns; Snapshot stored and hashed.
- **Failure:** post-check failure → Task failed; no Artifact committed.
### `record_outcome` — Operator via host-invoked application adapter (connector later)
- **Purpose:** durably record what happened — or register a prediction before the result is known.
- **Reads:** subject entity (validates existence and Team ownership).
- **Writes:** Outcome (+observation Snapshot +hash where an observation exists), Event.
- **Validation:** predictions are two Outcomes — `prediction_registered` (`expected` validated against the fixed schema: resolution condition, `check_by`, `predicted_band`; observation fields null, permitted for this type only) and `prediction_check` (observation filled; `expected.registered_outcome_id` names the registration). Delivery outcomes on an Artifact with an open policy-required Consultation are rejected. Subject polymorphism validated.
### `evaluate_outcome` — evaluator proposal (R6-G first slice: deterministic rules)

- **Purpose:** assess one immutable Outcome without rewriting the observation.
- **R6-G D9 decision (2026-11-03):** the first integrated caller is the deterministic code-defined ruleset `watch.r6g.ingest-source-rules`, revision `1`, for `ingest_source` terminal Outcomes only. It evaluates execution-contract consistency from typed terminal categories, task/attempt Events, the corresponding ingestion business Event, and canonical Signal/Snapshot identity/hash checks. `success_signal_created` and `success_no_change` can produce `worked`; a consistent `terminal_failure` can produce `failed`. `worked` does not mean source truth, causal impact, or Objective achievement. Unsupported or inconsistent evidence fails closed without creating an Evaluation. Revision 1 does not emit `mixed` or invent an `inconclusive` judgment.
- **Evaluator boundary:** the rule component returns a typed `EvaluationDraft` only. It passes that draft to `EvaluationService.propose(evaluator_kind="rule", evaluator_identity="watch.r6g.ingest-source-rules", evaluator_revision="1")`; the service validates evidence and owns proposal/disposition Events, while `TaskRuntime` owns the Evaluation Task's terminal lifecycle. No human/model Evaluation producer is wired or authorized for R6-G v1. The generic persisted evaluator-kind vocabulary is not additional R6-G authorization.
- **Durable target binding:** in the same transaction that `TaskRuntime` commits the terminal `task_execution` Outcome for a configured-source `ingest_source` Task, application code creates exactly one ordinary same-Team `evaluate_outcome` Task and its immutable `evaluation_task_requested` Event. The Event is owned by the evaluator Task and binds Team, source Task/attempt/result, PlanAction and policy pin, target Outcome ID and observation Snapshot ref/hash, evaluator identity/revision, and a canonical request fingerprint. A fixed UUIDv5 namespace derives the Task ID from Team + Outcome + ruleset identity/revision. The Task copies the source Task policy version, has no Objective/Plan/Action links, exact `allowed_writes=["Evaluation", "EvidenceLink"]`, zero tools/cost, a 30-second deadline, and three maximum attempts. TaskRuntime verifies exact Task/Event shape before admission and verifies the request exists on source-terminal replay. Task/Event creation is a narrow K side effect, not a general queue, dispatcher, or scheduler; a missing/duplicate/mismatched record fails closed.
- **Reads:** exactly one `evaluation_task_requested` Event owned by this Task (including the target Outcome ID/hash and pinned evaluator identity/revision), the target Outcome, its source Task and immutable PlanAction/policy provenance, related same-Team Outcomes, domain-matching Signals, and immutable Snapshots referenced by those records. The Event target and fingerprint are revalidated before producing a draft.
- **Writes:** one Evaluation proposal and its Evaluation-scoped EvidenceLinks, plus the narrowly scoped Events `evaluation_proposed`, `evaluation_recorded`, or `evaluation_rejected`. The lifecycle is `proposed → recorded or rejected`; the worker supplies draft findings and evidence only. Trusted application code supplies evaluator kind, stable identity, and revision, validates the proposal, and alone changes its disposition.
- **Validation:** the target Outcome and Outcome evidence belong to the Task's Team; Signal evidence matches the Team's Domain; Snapshot references and hashes match the canonical source; quoted spans match exact UTF-8-decoded Snapshot text at supplied character offsets. The primary Outcome must appear as an evidence link. Idempotency is scoped to the creating Task.
- **Task completion:** only a recorded or rejected Evaluation may be reported to `TaskRuntime`, using `success_evaluation_recorded` or `success_evaluation_rejected` with its Evaluation ID. TaskRuntime verifies the Evaluation's Team, creating and resolving Task, final status, and write scope before terminal finalization.
- **Not permitted:** mutation of Outcome, KnowledgeItem, LearningChange, or TeamPolicy; changing Task lifecycle directly; committing a LearningChange; or treating a successful Task as proof of causation.
- **Failure:** invalid, stale, cross-Team, mismatched-hash, or invalid-quote evidence leaves no Evaluation or EvidenceLink. A disposition conflict cannot overwrite the first decision.
### `propose_learning_change` — model worker (R6-F Checkpoint 2; R7-B B5.1 extension)
- **Purpose:** distill bounded, durable Team experience into one proposed KnowledgeItem creation; optionally propose that it supersede one existing predecessor. It does not commit learning.
- **Reads:** explicit IDs of one or more recorded Evaluations from the same Team; each Evaluation's terminal `task_execution` Outcome, terminal source Task Event, Evaluation-scoped EvidenceLinks, canonical Outcome/Signal Snapshots and hashes, and available Objective/Plan/Action/Context provenance. For create-with-successor only, it also reads the exact same-Team predecessor and its canonical current history.
- **Writes:** exactly one `LearningChange` with `target_kind="knowledge_item"`, `target_id=NULL`, `operation="create"`, and `status="proposed"`; an optional immutable `supersedes_item_id` plus its exact predecessor binding are included in the proposed state and proposal hash; one `learning_change_proposed` Event; the separate `experience_distillation` Task cost charge and its accounting Events. The Task's worker write scope remains exactly `["LearningChange"]`. **No KnowledgeItem, TeamPolicy, Task, Snapshot, or projection write is granted to the worker** (INV-12); application-managed TaskRuntime/ledger effects remain Kernel side effects.
- **Validation:** all records and references are same-Team/domain as applicable; Outcome/Evaluation terminal Events, proposal hashes, EvidenceLink reference keys, Snapshot hashes, and quotes are revalidated; one case permits only a narrow low-confidence `practice`; `pattern`, `method`, or `playbook` requires at least two recorded Evaluations tied to distinct source Task IDs. Supporting, challenging, and mentioning links retain their canonical stance. For create-with-successor, the predecessor must be canonical, same-Team, `active`, D7-eligible with a future UTC `review_after`, have no committed successor, and have no non-retired pending candidate. The exact predecessor pointer/version/content/full-state binding is included in the proposal hash and rechecked under the Team graph lock before commit. A stale, due, unscheduled, or `needs_review` predecessor fails closed. **R6-G v2 behavior is implemented:** a source Task may be `done` with a D9 `worked` Evaluation or terminally `failed` with a D9 `failed` Evaluation only when its exact current-attempt terminal Events and Outcome agree; a failed case remains contrary evidence relative to a positive reusable-practice candidate. The pack stores raw EvidenceLink stance separately from derived case-relative stance and persists a version marker per evidence-basis case, included in the basis hash. Historical unmarked R6-F v1 basis records are reconstructed without adding a marker; unknown, mixed or mismatched markers fail closed. The exact deterministic evidence basis/hash is recomputed after provider return before the proposal is stored. Model references outside the supplied evidence pack, stale or altered evidence, malformed output, unknown usage, or cost overrun cannot yield a proposal.
- **Provider boundary:** the provider is dependency-injected. Only a synthetic deterministic test card is allowed in this checkpoint; ADR-0031 authorizes Cloudflare for R6-E only. No production R6-F provider/model call is authorized until the separate provider decision is accepted.
- **Not permitted:** approval/rejection, KnowledgeItem create/revise/retire, TeamPolicy mutation, indexing, retrieval publication, new dispatcher, or a second runtime. Those belong to later checkpoints and remain outside this Task's grants.
### `assess_knowledge_quality` — evaluator proposal (R7-A; active)

- **Purpose:** assess one exact proposed LearningChange create state before trusted Operator acceptance. Evaluator reports structured findings; it cannot accept/reject the LearningChange.
- **Task creation:** TaskRuntime creates one ordinary same-Team assessment Task as a Kernel-managed side effect after successful create proposal finalization. Its request Event pins LearningChange, proposal/evidence hashes, rubric and evaluator identity/revision.
- **Reads:** exact proposed LearningChange and rebuilt canonical evidence basis, source Task/Outcome/Evaluation/Signal/Snapshot lineage and same-Team KnowledgeItem refs in validated basis.
- **Writes:** one untrusted typed KnowledgeQualityAssessment draft is proposed; application validates and records one immutable assessment and Task-attributed Events. Exact worker scope is `["KnowledgeQualityAssessment"]`; no LearningChange or KnowledgeItem write.
- **Validation:** rebuild/hash canonical evidence; validate references, Team, lineage, seven rubric dimensions, evaluator identity/revision, proposal hash, idempotency and Task scope. "recorded" means stored, not approved. Accepted create requires exactly one recorded assessment for exact LearningChange and completed assessment Task.
- **Task lifecycle:** TaskRuntime owns admission, attempt fencing, finalization, Outcome/Event and interrupted recovery. Three max attempts; zero tools/cost; 30-second deadline. Provider injected; tests use deterministic fakes; no production evaluator selected.
- **Not permitted:** LearningChange disposition, KnowledgeItem, TeamPolicy, projection, Context, citation or approval writes; no direct worker DB write; no autonomous acceptance.
- **Failure:** malformed, stale, cross-Team, mismatched-hash, unsupported-reference or changed-idempotency draft cannot create recorded assessment. Ordinary TaskRuntime retry/recovery applies.

### `approve_learning_change` — trusted Operator via host-invoked in-repository adapter (R6-F Checkpoint 3; R7-B B5.1 extension)
- **Purpose:** explicitly accept or reject one proposed LearningChange through the only R6-F canonical learning-commit path.
- **Caller and identity:** the host authenticates the Operator and authorizes the exact Team/action, then invokes the adapter in-process with a typed principal carrying stable issuer/subject. The adapter does not accept a bare `operator_id`, display name, email, request-body identity, or model output as proof. No deployed Watch API/CLI, login, token middleware, or user store is added.
- **Task creation:** atomically create one ordinary pending same-Team approval Task and its request Event, pinned to current TeamPolicy, with no Objective/Plan/Action links, exact `["LearningChange", "KnowledgeItem"]` scope, zero tools/cost. Host idempotency UUID resolves retries to the same Task and request fingerprint. Never insert a running Task.
- **Lifecycle:** call `TaskRuntime.admit`, invoke the narrow decision service synchronously, then call `TaskRuntime.finalize` with a typed accepted/rejected result. TaskRuntime alone changes attempt/status/completion and writes lifecycle Events/Outcome. `TaskDispatcher` remains ingestion-only.
- **Writes:** LearningChange disposition/history; KnowledgeItem changes only where supported by a validated proposal; one exact Task-attributed decision Event. Events are application-managed effects, not a worker grant. **No TeamPolicy write is permitted in R6-F.**
- **Validation:** exact Task type, same Team/current policy, current running attempt, exact write scope, host Team/action authorization, and canonical actor matching the request Event. Lock/revalidate the LearningChange, complete evidence hash/references, source hashes/quotes, operation, target version/status, and replay/concurrency preconditions.
- **Acceptance:** atomically commit KnowledgeItem state/version, LearningChange accepted disposition, previous/committed state, canonical operator identity, approval Task ID, timestamp, and acceptance Event. For an ordinary create, existing policy behavior is unchanged. For a create-with-successor, the same `create` decision rechecks the predecessor under the Team-scoped lock, requires a non-NULL future `review_after` from the approval Task's pinned TeamPolicy, and creates an active version-1 candidate with its immutable predecessor link. Candidate creation does not mutate the predecessor; the candidate remains withheld from retrieval and Context until a later accepted supersede commit establishes reciprocal links.
- **Rejection:** atomically commit LearningChange rejected disposition, non-empty reason, identity, Task ID, timestamp, and rejection Event without creating or mutating KnowledgeItem. Rejection is a successful Operator decision; approval Task ends `done`.
- **Replay and competing requests:** same host idempotency UUID and identical request return the same Task and decision. Reuse with changed actor/target/decision/reason conflicts. Different idempotency keys may create distinct approval Tasks, but the LearningChange row lock permits one canonical decision only. A losing Task is terminalized as terminal_failure with reason learning_change_already_decided, using its current-attempt start as the deterministic observation time; the failure is committed through TaskRuntime with its ordinary Outcome/Snapshot/Events. Interrupted recovery reconstructs the same failure before retry/exhaustion, and replay returns the same typed conflict without another Outcome or KnowledgeItem version.
- **Not permitted:** raw-string authentication, model-selected actor/disposition, direct Task lifecycle writes, second runtime, general dispatcher, seed/bypass path, or TeamPolicy mutation.

### `seed_knowledge` — legacy Operator Task via host application (excluded from R6-F)
- **Purpose:** explicit `manual_seed` creation of additional KnowledgeItems or a revised TeamPolicy outside the setup flow.
- **Writes:** LearningChange (`basis_kind="manual_seed"`, committed immediately), target entity, Event.
- **Validation:** same schema and version checks as F6 minus the Evaluation basis.
### `request_consultation` — model worker (or created by policy/Trigger/enqueue)
- **Purpose:** the loop asks for expert opinion (ADR-0020).
- **Reads:** subject entity and related evidence.
- **Writes:** Consultation (`status="open"`, context Snapshot + hash of exactly what the expert will be shown), Event. Any follow-up Task after the answer is enqueued by the later `answer_consultation` Task; this Task ends when it opens the Consultation.
- **Validation:** subject exists, same Team; context Snapshot stored before commit; `check_by` set when the question is time-bound.
- **Key rule:** opening the Consultation **ends this Task**. Waiting for a human happens between Tasks, never inside one.
### `answer_consultation` — Operator via host-invoked application adapter
- **Purpose:** record the expert's answer.
- **Reads:** the open Consultation.
- **Writes:** Consultation status `open → answered` (+ answer Snapshot + hash, optional structured `verdict` per team policy), Event with operator identity; optional enqueue of a follow-up update/evaluate Task so the answer enters the loop.
- **Validation:** Consultation is `open`; answer Snapshot stored before commit; the answer becomes citable as `source_kind="consultation"` evidence (INV-04 applies to any later quote of it).
### Objective creation operation — R2 contract
- **Purpose:** create one durable Objective in `draft` for the Task's Team.
- **Writes:** Objective, Event.
- **Validation:** Objective fields are schema-valid; the creating Task is running and authorized for Objective writes; Objective Team matches Task Team. Record Task attribution.
- **Commit:** Creation begins in `draft`. Commit the Objective and a durable, attributable Event atomically. This operation creates the Objective; status changes use the lifecycle-transition operation below.
- **Retry/rejection:** a same-Task retry must not double-commit the same successful creation. Rejection leaves Objective state unchanged and is recorded in an auditable Event with a stable reason/category. Literal Task/Event names and rejection retry behavior remain open.
### Objective lifecycle-transition operation — R2 contract
- **Purpose:** perform one legal Objective status transition.
- **Writes:** Objective status, Event.
- **Validation:** Objective belongs to the Task's Team; expected current status matches; target transition is in the Objective lifecycle; Task write scope and budget permit the operation.
- **Commit:** Revalidate expected state and atomically commit the transition with an attributable Event sufficient to reconstruct it. Rejected operations leave Objective unchanged and produce an auditable rejection Event with a stable reason/category.
- **Concurrency:** stale/conflicting transitions reject under INV-13 rather than silently overwrite. A same-Task retry cannot double-commit a matching successful transition. The database mechanism, exact retry identity, and reuse of rejection Events remain open.
- **Boundary:** R2 implements the Objective operations in its milestone; additional Objective mutation semantics remain subject to later design. Triggers initiate mutations through ordinary Tasks, not a parallel write path.
### `create_team` — Operator via host application integration (not implemented in Checkpoint 3)
- **Purpose:** create a Shell team for a new subject (F7).
- **Writes:** Team (`status="configuring"`), subject-brief Snapshot (+hash, referenced from the Event payload and by the subsequent TeamDraft), Event.
- **Validation:** unique team key; Domain may be any pack key including `generalist`; brief is freeform prose stored immutably.
### `configure_team` — model worker, runs on configuring teams
- **Purpose:** draft the team configuration from the subject brief and samples (F7).
- **Reads:** subject-brief Snapshot, sample manual Signals, pack defaults (vocabulary structure, templates, decay bounds, policy JSON Schema).
- **Writes:** TeamDraft (`status="draft"`, config Snapshot + hash, `advisor_notes` citing the samples), Event.
- **Validation:** proposed policy validates against the JSON Schema; vocabulary conforms to the pack's structure; candidate sources marked unverified; draft revision current.
- **Failure:** invalid model output → draft discarded with reason; Task failed.
### `activate_team` — Operator via host application integration (not implemented in Checkpoint 3)
- **Purpose:** review, edit, and activate the team (F7).
- **Writes:** TeamPolicy v1; starter Threads (through the normal commit path); Team `configuring → active`; TeamDraft `approved` (config re-snapshotted if the Operator edited it); Event with operator identity.
- **Validation:** policy against JSON Schema; vocabulary within pack structure; pack-contract conformance; draft revision current (optimistic check, INV-13); operator identity in Event payload.
- **Thread ownership boundary (accepted F2 target, 2026-11-26):** this is the canonical intended creator for Operator-approved starter Threads. The trusted host authenticates the Operator and invokes Watch; Watch validates the grant, approved TeamDraft, Team/Domain consistency, and starter definitions, then commits Team activation, starter Threads, and attributable Event through the application/Kernel boundary. The host does not write Thread rows directly. This operation remains not implemented in Checkpoint 3, and the actual deployment writer inventory is still unknown; this target contract is not evidence of deployed enforcement.
### Thread resolution — Operator-authorized Task/application operation (design target; not implemented)
- **Purpose:** explicitly resolve an existing Thread with an attributable reason; this is the accepted F2 resolution direction, not a new worker capability.
- **Authority:** trusted host authenticates the Operator; Watch validates the Operator grant against the Team derived from the locked Thread. Caller/model payload cannot fabricate authority or choose a cross-Team target.
- **Writes:** the target Thread's `status` transition to `resolved` and exactly one immutable Task-attributed Event recording the prior/new status, reason, Operator attribution, and Task identity. Both writes commit or roll back in the same TaskRuntime-owned transaction.
- **Validation and concurrency:** validate current Thread/Team state and reason under the canonical Task → Team → sorted Thread → sorted Hypothesis lock order; increment Team revision as required by RW-5; hold locks through commit. Replays return the canonical committed result without another transition/Event.
- **Boundary:** no model-worker write, direct host SQL, independent transaction/commit, generic status-update endpoint, or background resolution. This design does not introduce dormancy or alter the separately gated RW4-5 reactivation path. The operation name and exact Task envelope/type, Event schema/uniqueness, and implementation proof require a separate reviewed specification and authorization; this entry does not freeze a new `task_type`, create a second Task runtime, or authorize implementation.
## 4. Write-scope matrix
`W`/`C` identify business/domain entity mutations available for application
validation of worker proposals. `K` identifies an explicitly bounded,
Kernel-managed write, which may include a business-entity side effect only
when that Task's specification names the exact entity, fields, invariants, and
transaction boundary. Such a write is performed by trusted application code,
not proposed by a worker, and is never included in worker `allowed_writes`. The `Task (K)` column always covers the current Task's documented runtime
transitions. Superscripts there additionally permit only the named Task
enqueue operation. `—` means that the Task type cannot cause that
business/domain write through the worker-proposal channel; it does not disable
the separately governed `K` lifecycle side effects described below.
All Task, Snapshot, and Event writes are performed by application code, never by a worker. For `triage_signal`, SignalDisposition and any separately gated Thread effect are Kernel-managed (`K`), not worker-proposal writes; the Task's worker `allowed_writes` is empty. D3 is accepted: a deferred disposition is immutable/terminal in v1 and cannot be refined by `update_thread`, `operator_update`, or background processing. Therefore those two Task types have no SignalDisposition write permission. The triage `K` cell follows the accepted D5 vocabulary/reference/atomicity and D6 atomic-reactivation contracts; implementation still requires separate RW4-5 authorization and proof. **RW4-1B Decision 7 is accepted:** matched, duplicate, and deferred must be enabled together, after the D1 Control Room creator/caller-authorization boundary and D2 Task identity/FK are proven; RW-5 Task → Team → sorted Thread → sorted Hypothesis serialization, Team revision, and all `update_thread`/`operator_update`/`apply_decay` and any Thread status/domain writer retrofits pass real PostgreSQL interleavings; D4.1a canonical arbitration and D4.2 matcher evidence and durable-receipt closure/D4b actual pins, including receipt schema/uniqueness/payload bounds, the separate durable receipt transaction, Team-revision/candidate-profile fence, KnowledgeIndexService Signal-lock, KnowledgeChunk DML guard/no-TRUNCATE, stable chunk/vector-fingerprint, and finalizer revalidation proof, and accepted `assessment_receipt_stale` TaskRuntime terminal-failure/permanent-v1-identity-occupancy mapping and its implementation/replay proof; the later business-finalization bundle remains atomic pass; RW4-1 physical provenance/role/immutability proof passes; D3/D5 TaskRuntime atomicity/exact replay passes; and integrated independent review plus separate implementation authorization are complete. Production host authentication remains mandatory before production use. No partial disposition write rollout or implementation authorization is implied.

The `Outcome` column covers worker-proposed or domain-level Outcome writes,
such as the `record_outcome` operation. It does not govern the terminal
`task_execution` lifecycle record required by
[ADR-0030](decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md).
`TaskRuntime` owns terminal lifecycle finalization: it writes the terminal
`task_execution` Outcome and its immutable observation Snapshot in the same
transaction as the terminal Task status and the corresponding terminal Event.
Those are application-managed `K` lifecycle side effects, not worker-authored
writes, and they never enter a worker's `allowed_writes`. They are generic
TaskRuntime lifecycle records, distinct from the task-specific Signal Snapshot
side effect in footnote ¹; footnote ¹ grants no worker Snapshot permission.
| Task type | Team | Signal | SignalDisposition | Thread | Hypothesis | EvidenceLink | ConfidenceChange | Artifact | Outcome | Evaluation | KnowledgeItem | TeamPolicy | LearningChange | KnowledgeQualityAssessment | Trigger | Consultation | TeamDraft | Task (K) | Snapshot (K) | Event (K) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ingest_source` | — | W | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | K²⁵ | K¹ | K²⁵ |
| `manual_signal_ingest` | — | W | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | K | K¹ | K |
| `triage_signal` | — | — | K | K² | — | — | — | — | — | — | — | — | — | — | — | — | — | K | — | K |
| `update_thread` | — | — | — | W⁴ | W | W | W | — | — | — | — | — | — | — | — | — | — | K | — | K |
| `operator_update` | — | — | — | W⁴ | W | W | W | — | — | — | — | — | — | — | — | — | — | K | — | K |
| `apply_decay` | — | — | — | — | K | — | K | — | — | — | — | — | — | — | — | — | — | K | — | K |
| `check_triggers` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | W | — | — | K²⁰ | — | K |
| `review_knowledge` | — | — | — | — | — | — | — | — | — | — | W⁶ | — | — | — | — | — | — | K | — | K |
| `render_output` | — | — | — | — | — | — | — | W | — | — | — | — | — | — | — | — | — | K²¹ | K⁷ | K |
| `record_outcome` | — | — | — | — | — | — | — | — | W | — | — | — | — | — | — | — | — | K | K⁸ | K |
| `evaluate_outcome` | — | — | — | — | — | W⁹ | — | — | — | W | — | — | — | — | — | — | — | K | — | K |
| `propose_learning_change` | — | — | — | — | — | — | — | — | — | — | — | — | W | — | — | — | — | K | — | K |
| `assess_knowledge_quality` | — | — | — | — | — | — | — | — | — | — | — | — | — | W | — | — | — | K | — | K |
| `approve_learning_change` | — | — | — | — | — | — | — | — | — | — | W | — | W | — | — | — | — | K | — | K |
| `seed_knowledge` | — | — | — | — | — | — | — | — | — | — | W | W | W | — | — | — | — | K | — | K |
| `request_consultation` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | W¹⁰ | — | K | K¹¹ | K |
| `answer_consultation` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | W¹² | — | K²² | K¹³ | K |
| `create_team` | W¹⁴ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | K | K¹⁵ | K |
| `configure_team` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | W | K | K¹⁶ | K |
| `activate_team` | W¹⁷ | — | — | C | — | — | — | — | — | — | — | W | — | — | — | — | W¹⁸ | K | K¹⁹ | K |
| `transition_plan` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | K | — | K²⁴ |
¹ Store only the immutable Snapshot for the Signal created by this ingestion
operation. This footnote governs that ingestion side effect alone: it grants no
worker Snapshot permission, and it does not limit the separate terminal
`task_execution` observation Snapshot that `TaskRuntime` commits during
terminal lifecycle finalization (see the §4 preamble). That observation
Snapshot is created under the universal `Task (K)` lifecycle authority
described in footnote ¹⁹ and ADR-0030, not under this `Snapshot (K) = K¹`
cell; it is an application-managed lifecycle record committed atomically with
the Outcome, terminal Task status, and corresponding terminal Event.
² The `triage_signal` Kernel-managed effect is limited to the accepted `matched`, `duplicate`, or `deferred` disposition and its Task-attributed evidence. It never creates a Thread. Under accepted D6, a dormant winner may be matched only when the same TaskRuntime-owned transaction reactivates it and records one immutable Task-attributed `thread_reactivated` Event. Until RW4-5 implementation is separately authorized and proven, a dormant would-be winner must defer and cannot be reactivated.
⁴ Summary projection and explicit resolution only. SignalDisposition refinement is not granted to `update_thread` or `operator_update`; D3 makes deferred terminal/immutable in v1.
⁶ `active → needs_review` only.
⁷ Store only the Snapshot for the Artifact produced by this operation.
⁸ Store only the observation Snapshot when the Outcome type has an observation.
⁹ With `subject_kind="evaluation"`. ¹⁰ Create only (`open`).
¹¹ Store only the context Snapshot for the Consultation created by this
operation. ¹² `open → answered` only. ¹³ Store only the answer Snapshot for
this Consultation operation. ¹⁴ Create only (`configuring`). ¹⁵ Store only
the subject-brief Snapshot for this Team creation. ¹⁶ Store only the
configuration Snapshot for the TeamDraft produced by this operation.
¹⁷ `configuring → active` only. ¹⁸ `draft → approved` only.
¹⁹ Store a new config Snapshot only when the Operator edits the approved
configuration; do not rewrite the prior immutable Snapshot. For every row,
Task (K) also permits only the current Task's own state-machine transitions
and associated runtime metadata, never worker-authored Task changes.
²⁰ In addition to its own lifecycle, create only the target Task of a Trigger
that passed deterministic validation. ²¹ In addition to its own lifecycle,
enqueue only `request_consultation` when the documented delivery gate applies.
²² In addition to its own lifecycle, optionally enqueue only the documented
follow-up update/evaluation work after recording the consultation answer.
²⁴ Emit only this Task's own Plan lifecycle Events: `plan_completed` or
`plan_stopped` for an accepted transition, and the categorized
`plan_transition_rejected` Event for a rejected one. No other Event type, no
Snapshot, and no Task other than the current one may be written.
²⁵ On terminal finalization of a configured-source `ingest_source` Task,
TaskRuntime may create exactly one same-Team pending `evaluate_outcome` Task
and its one `evaluation_task_requested` Event in the same transaction as the
source terminal Outcome/Snapshot/Events. The new Task copies the source
policy-version pin, has no Objective/Plan/Action links, exact
`allowed_writes=["Evaluation", "EvidenceLink"]`, zero tools/cost, a
30-second deadline, and three maximum attempts. Its deterministic UUIDv5 ID
uses Team + Outcome + the fixed D9 rule identity/revision. The request Event
must bind the exact source Task/attempt/PlanAction/result, Outcome ID and
Snapshot ref/hash, evaluator identity/revision, and canonical request
fingerprint. Terminal replay verifies the exact Task/Event and never repairs
or duplicates it. This is a narrow TaskRuntime K effect, not a scheduler,
general dispatcher, or worker Task/Event grant.
#### R4 `propose_strategy` scope extension
This ordinary Task validates one transient StrategyProposal against its
same-Team active Objective and exact derived R3 assessment. It requires a
running Task, active Team, a valid Task budget, and policy version. Its worker
`allowed_writes` is empty and it has no tool capability. Model usage must be reserved and reconciled against `max_cost_usd` before this Task invokes a generation provider; usage-less responses fail closed. The application writes only one attempt-scoped generation charge record and its specified accounting Events. Unknown usage retains the full reservation, and retries are charged against the same Task-wide ceiling. No generic Event scope or existing K1/R2 Task permission is broadened.
| Task type | Business writes | Task (K) | Snapshot (K) | Event (K) | Cost ledger (K) |
|---|---|---|---|---|---|
| `propose_strategy` | — | Current Task lifecycle only | Only its immutable assembled Task Context Snapshot, written by application code | Only `context_assembled`, the attributed strategy disposition/rejection, and `generation_cost_reserved`, `generation_cost_reconciled`, `generation_cost_unknown`, or `generation_cost_overrun` and the exact attributed Strategy disposition/rejection Event for this Task | One durable per-attempt `task_generation_charges` reservation/reconciliation record for the `strategy_proposal` operation |
For the R6-E model-backed producer, `StrategyProposer` receives the exact
assembled Context artifact and provider output remains untrusted JSON. Its
submission path requires the one Task-attributed `context_assembled` Event,
checks the Snapshot reference/hash against the canonical Context document,
pins the manifest and StateAssessment basis, then delegates schema, capability,
scope, policy, and freshness validation to `StrategyService`. The resulting
strategy disposition Event records the Context Event ID, Snapshot reference,
content hash, exact assessment, and the reconciled generation charge ID. A Task with a Context manifest cannot use
the legacy context-free submission path. The proposer does not materialize a
Plan. Before each provider call, application code quotes a conservative
maximum from the exact prompt and configured output cap, then locks the Task and
reserves that amount only when all prior Task-attributed charges plus the new
reservation fit `max_cost_usd`. The initial Cloudflare quote uses a UTF-8-byte
input bound plus 128 message-framing tokens, at most 1,024 output tokens, and
the published 32K context ceiling. A unique Task/attempt/operation key prevents
duplicate calls within one attempt. Valid usage settles the charge at its
usage-derived estimated cost; invalid, missing, or ambiguous usage leaves the
maximum reserved as an `unknown` charge and cannot yield a Strategy. Usage
beyond the reserved bounds is persisted as an `overrun` and also cannot yield
a Strategy. All prior reconciled and unresolved charges remain included in the
Task-wide ceiling.

All Task lifecycle Events (`task_started`, `task_attempt_failed`,
`task_retry_scheduled`, `task_completed`, and `task_failed`) remain in the
durable audit log, but they do not change the Objective-domain StateAssessment
basis. Current Task status remains represented in the assessment's Task
projection. This distinction keeps an immutable Context reproducible when the
same running Task is retried on a later attempt. Context, Strategy disposition,
and generation-cost Events are likewise audit/protocol records rather than
Objective-domain transitions.

**R6-G typed producer completion:** after `StrategyProposer` returns an accepted or rejected disposition, the application finalizes the producer Task through `TaskRuntime` using `success_strategy_accepted` or `success_strategy_rejected`, bound to the exact Strategy disposition Event. Rejection is a completed proposal operation, not a successful Plan or Objective outcome, and creates no Plan. `create_plan` similarly finalizes through `TaskRuntime` using `success_plan_created`, bound to the exact Plan ID and `plan_created` Event. `TaskRuntime` validates these durable business records and recovers already-committed Strategy/Plan dispositions before retry exhaustion; no service writes Task status directly and no ingestion result category is reused.

The producer returns only proposed strategy data. Application code validates
and records acceptance or rejection; the worker cannot write Objective,
TeamPolicy, memory, Plan, Team structure, or enqueue Tasks. For R6-E, application
code may write exactly one content-addressed Snapshot containing the assembled
Task Context and one `context_assembled` Event containing its versioned manifest
(selected canonical references and hashes, logical core, query hash, chunk IDs,
retrieval configuration, and embedding identity). These are current-Task K effects,
not worker writes. Generation charge records and their narrowly enumerated accounting
Events are also current-Task K effects; they do not extend worker write grants.
The exact Context bytes and manifest are immutable: a matching replay
reuses the existing Snapshot/Event; conflicting reuse rejects and never replaces
the original. No arbitrary Snapshot or Event is authorized. The R4 Strategy audit
remains embedded in the disposition Event and does not gain a separate Snapshot. The redesigned
StrategyProposal is one coordinated decision for the Objective and its exact
historical assessment basis. It may contain multiple concurrent Visions,
Workstreams, Actions, and explicit Action prerequisites, including
cross-Workstream/Vision dependencies. Acceptance authorizes the complete legal
structure for one later Plan; it is not a claim of wisdom or effectiveness.
The first implementation supports only configured `ingest_source` Actions,
zero cost, no tools, and `configured_source_ingested`; this capability limit is
not the semantic scope. `max_tasks` bounds the number of authorized Actions;
it is not an exact-count requirement. The one-action case is a valid subset:
one Vision, one Workstream, one Action.
`strategy_proposal_accepted` and `strategy_proposal_rejected` preserve Task,
Team, Objective, canonical proposal/hash, and exact historical assessment
context with basis references/hash/timestamp. Event payload is audit, not
Strategy memory; it reconstructs the complete proposal without a transcript.
No Snapshot or new table is needed because the audit embeds the exact
projection payload. R5 derives one Plan from the one active accepted Strategy
and must not invent, omit, partition, or reinterpret it without explicit
authority. Team/capability changes require a separate human-reviewed proposal
path; no such mutation is authorized here.
INV-13 applies: the first disposition fixes the Task's candidate identity;
a matching retry reuses its Event after scope/budget/Team revalidation.
Conflicting attempts are rejected without overwriting history. New acceptance
revalidates the exact R3 context in a serializable transaction; stale context
is rejected. Serialization/deadlock conflicts are recorded as
`concurrent_state_conflict`, unless a matching committed disposition can be
replayed. A new attempt after a disposition uses ordinary Task semantics,
not a planner-specific retry protocol. Task lifecycle remains runtime-owned;
this service adds no Task state machine or execution runtime.
#### R5 `create_plan` operation
`create_plan` is a narrowly scoped Task operation. The worker supplies a
proposal only; application code validates it and the accepted R4 Event/hash,
Objective/Team ownership, action identity, supported action, policy and budget
constraints, and retry identity. Kernel/application code atomically creates
the Plan, its initial ordinary Task(s), and attributable creation Event(s).
The operation cannot write TeamPolicy, memory, Strategy, StateAssessment, or
arbitrary Tasks/Events. The creating Task's existing `policy_version` is
policy provenance, not a Plan policy pin. Plan/action prerequisites are
checked by the existing Task admission path under INV-16.
##### R5 bounded materialization implementation
`PlanService.create` takes a canonical accepted R4 Event identity/hash and
explicit Objective/Team references, not caller-supplied Action JSON. It
preserves the accepted Strategy's complete Action set and validates that every
Action is supported (`ingest_source`, no tools, zero cost), within the
`max_tasks` upper bound, and configured by the creating Task's policy. Every
Action prerequisite must resolve to another Action in the same accepted
Strategy; missing targets reject materialization.
The Plan durably preserves accepted Event/hash, Objective/Team ownership,
assessment basis/timestamp, budget, and completion condition. A `plan_actions`
mapping stores each Strategy-local Action UUID and its canonical Action data;
exactly one ordinary `pending` Task references each Plan/Action pair through
nullable Task provenance fields constrained by composite database keys. Plan,
all Action mappings, all Tasks, and the attributable `plan_created` Event
commit atomically. Same-Task replay reconstructs all Action-to-Task mappings;
conflicting reuse rejects. Legacy flat proposals cannot authorize creation.
The child Tasks use the supported ingestion capability with
`allowed_writes=["Signal"]` and the existing zero-tool/zero-cost 60-second
budget. Prerequisite validation and enforcement at Task admission are part of
R5-A; keep them in the existing runtime under INV-16. Missing or contradictory
records must be detected during reconstruction rather than fabricated or
silently repaired. Plan/Action immutability continues to be enforced in the
database.

Plan lifecycle transitions, completion evaluation, terminal-state protection,
and stopping/supersession behavior are assigned to **R5-B**. Replanning—the
decision and materialization of a replacement Plan—remains in a later dedicated
milestone. This split does not remove lifecycle behavior from overall R5 exit
criteria.

#### R5-B `transition_plan` operation

`transition_plan` is a narrowly scoped, application-controlled Task operation
for one Plan lifecycle transition. It runs through the ordinary Task runtime
using a running same-Team Task of type `transition_plan`, authorized
`allowed_writes=["Plan"]`, an active Team, the matching policy version, and a
valid zero-usage Task budget. A worker cannot directly write Plan lifecycle
fields or Events; application code validates and commits every transition.

The request identifies the Plan, expected current status, target status, and
any stop reason or successor reference. Legal transitions are `active →
completed` and `active → stopped`; terminal Plans cannot reopen. The expected
status is checked under a Plan row lock so stale or concurrent conflicting
transitions reject.

Completion is deterministic. Every Plan Action must have exactly one linked
Task in `done` status, and the declared completion condition must be proven
by durable records. For the current supported `configured_source_ingested`
condition, every linked ingestion Task must be `done` and have a durable
successful outcome Event such as `signal_ingested` or `fetch_no_change`.
Do not use model judgment to declare completion.

Stopping requires `stopped_reason` = `abandoned`, `invalidated`, or
`superseded`. An active or completed Plan has no stop reason or successor;
a stopped Plan must have a stop reason. When the reason is `superseded`, the
old Plan must reference an already-existing active successor Plan for the same
Objective, distinct from itself. Other stop reasons have no successor. This
operation does not create or select the successor; replanning remains a later
dedicated milestone.

Only lifecycle metadata (`status`, `stopped_reason`, successor reference)
may change; accepted proposal/assessment provenance, Action definitions and
identities, prerequisites, budget, and completion condition remain immutable.
The lifecycle state and attributable success Event commit atomically. A
matching same-Task retry replays the durable transition; conflicting requests
and failed operations do not leave partial changes and emit a categorized
rejection Event.

##### Implemented R5-B operation

`PlanService.transition` is the application-controlled entry point. An accepted
transition records `plan_completed` or `plan_stopped`, attributed to the
transitioning Task; a rejected transition records `plan_transition_rejected`
with a stable reason and leaves the Plan unchanged. Reconstruction of a Plan
must validate its persisted lifecycle state against the required attributable
Event: a terminal Plan without its matching Event, an Event that disagrees with
the persisted state, or a supersession reference that is missing or points
outside the same Objective fails clearly. Lifecycle state is never fabricated,
silently repaired, or accepted as valid without its Event.

The durable lifecycle fields (`status`, `stopped_reason`, successor Plan
reference) are mutable state, distinct from the immutable Plan intent that the
database trigger still protects. The database enforces the valid combinations:
status in `active`, `completed`, `stopped`; stop reason in `abandoned`,
`invalidated`, `superseded`; a stopped Plan carries a reason; a superseded Plan
references a successor that is not itself; and a non-stopped Plan carries
neither reason nor successor. The implementation and schema are recorded in
`core/plans.py`, `core/models.py`, and migration `0007_plan_lifecycle`.

#### R2 Objective scope extension
The following semantic operations require the Task's authorized Objective
write scope and use the existing Task lifecycle and Event scope. They describe
the R2 contract, not current runtime capabilities; concrete Task and Event
names remain implementation choices.
| Objective operation | Permitted mutation |
|---|---|
| Creation | Create one `draft` Objective for the Task's Team |
| Lifecycle transition | Perform one legal status transition on a same-Team Objective |
No other Task type may mutate an Objective. `check_triggers` may enqueue one
of these operation Tasks only after deterministic Trigger validation; it may
not write Objective state itself. R2 Objective Tasks use the common
active-Team, running-Task, write-scope, and budget checks.
For each task type, Event (K) permits only Task-attributed Events generated
by application code for its normal transition and commit outcomes, including
success, no-change where specified, and rejection with a reason. The worker
cannot choose an unrelated Event type, payload, or Task ID. Snapshot (K)
permits only the content explicitly named by the corresponding task
specification and association above. A Task cannot use its Signal permission
to create an unrelated Snapshot, nor use `render_output` to store arbitrary
world content. Task enqueue permissions are similarly limited to the named
operations; they do not authorize arbitrary Task creation. All cells and K
side effects are enforced at commit/runtime (INV-14).
The `operator_update` row remains identical to `update_thread` as the
shared target contract — this is INV-15 expressed as a table. The RW-2
implementation is the first bounded slice of that contract: it writes
Hypothesis, EvidenceLink, and ConfidenceChange only. Deferred SignalDisposition
and projection cells are not implemented by RW-2. **RW-4 reconciliation:** the legacy W³ SignalDisposition cells for `update_thread` and `operator_update` are not authority. D3 makes deferred terminal/immutable and D5 freezes the v1 disposition contract; neither Task type may refine or overwrite any disposition.
## 5. Budget defaults
Starting points, tuned during M2; per-Task values may override downward, never upward past policy ceilings (`budgets` rule group). The `update_thread` row is the approved fixed RW-3 design budget, not a generic starting point. Operator task types (`operator_update`, `answer_consultation`, `create_team`, `activate_team`, plus the other manual types) incur no model cost and have no enforced deadline (—).
| Task type | max_tool_calls | max_cost_usd | deadline_s |
|---|---|---|---|
| `ingest_source` | 0 | 0 | 60 |
| `manual_signal_ingest` | 0 | 0 | 60 |
| `triage_signal` | 0 | 0 | 60 |
| `update_thread` | 0 | 0.02 | 45 |

The `update_thread` budget is cumulative across its three maximum starts. Its fixed provider compatibility/budget baseline is the existing ADR-0031 Cloudflare model, with one synchronous non-streaming request per attempt, no tools or provider retries, at most 1,024 output tokens, and the existing 32,000-token total quoted-context ceiling. ADR-0031 authorizes Cloudflare for R6-E only; live RW-3 provider calls require a separate explicit provider-authorization decision. Until that decision is accepted, only a deterministic fake provider may be used. The provider timeout is capped at 30 seconds within the absolute 45-second Task deadline. The `$0.02` ceiling covers up to three maximum conservative reservations under the current rate card; unknown charges remain fully accounted. These values are fixed by the approved RW-3 Checkpoint 3 design and cannot be increased by per-Task override. The existing interrupted-recovery threshold is strictly greater than 60 seconds, so ordinary `TaskRuntime.recover_interrupted()` cannot encounter receipt-only state before this 45-second deadline. Receipt-only recovery is reachable only after expiry and must terminalize without materializing proposals or reinvoking the provider. Earlier recovery would require a separately designed safe lease/ownership synchronization mechanism.
| `operator_update` | 0 | 0 | — |
| `apply_decay` | 0 | 0 | 300 |
| `check_triggers` | 0 | 0 | 60 |
| `review_knowledge` | 0 | 0 | 60 |
| `render_output` | 4 | 0.75 | 240 |
| `record_outcome` | 0 | 0 | — |
| `evaluate_outcome` | 4 | 0.40 | 180 |
| `propose_learning_change` | 4 | 0.40 | 180 |
| `assess_knowledge_quality` | 0 | 0 | 30 |
| `assess_knowledge_revalidation` | 0 | 0 | 30 |
| `assess_knowledge_lifecycle` | 0 | 0 | 30 |

| `approve_learning_change` | 0 | 0 | — |
| `seed_knowledge` | 0 | 0 | — |
| `request_consultation` | 4 | 0.30 | 180 |
| `answer_consultation` | 0 | 0 | — |
| `create_team` | 0 | 0 | — |
| `configure_team` | 6 | 0.60 | 300 |
| `activate_team` | 0 | 0 | — |


## 6. R6-F Checkpoint 1–4 authority boundary

For R6-F, `approve_learning_change` is narrowed to LearningChange and KnowledgeItem writes plus exact application-managed Events; it has **no TeamPolicy write grant**. The legacy `seed_knowledge` row remains a separately documented Task type but is not implemented by R6-F. Evaluation worker output cannot set its own status: trusted application service code validates and records/rejects the proposal. ExperienceDistiller output likewise remains an untrusted candidate; Checkpoint 2 creates only proposed LearningChanges for KnowledgeItem creation. Checkpoint 3 performs explicit Operator review and canonical commit through a trusted application identity boundary and an ordinary same-Team approval Task; TaskRuntime remains the sole owner of Task lifecycle transitions. D7's interval is read-only policy input pinned to the approval Task; it does not grant a TeamPolicy write. Checkpoint 4 implements the separate `team_experience_chunks` projection, current-canonical index/rebuild and dual-core retrieval, Context v2 with per-core provenance, and canonical review-date eligibility. `review_knowledge` owns only the `active → needs_review` transition through TaskRuntime; `approve_learning_change` remains read-only on TeamPolicy and pins the rule version used to compute `review_after`.


## 7. R7 Task/write-scope matrix — phase-gated extensions

**Status:** B3.2 persistence (PR #60), B3.3 revalidation assessment (PR #62), B3.4 lifecycle assessment (PR #64), B3.5 TaskRuntime/recovery/Event integration (PR #66), and B3.6 approval-time assessment binding (PR #68) are implemented and merged. B3.7's complete integrated matrix is mapped to merged tests in `docs/development/historical-r7-b-b3-7-integrated-regression-matrix.md`. B3.8 exact-head verification passed on hosted-tested SHA `6b624310d4d3ae53153dba1b9f47e949564de079`: 238 focused tests, Ruff, Mypy (38 files), fresh disposable PostgreSQL migration/single-head checks at `0018_r7b_lifecycle_review_date`, and 946 full-suite tests; cleanup and environment restoration passed. The 113 warnings are existing Alembic deprecations; the documented Markdown-only cumulative diff-check qualification is in `docs/testing.md`. B3 is formally closed on 2026-11-10. The approval allowlist is now `create` and `revise` on merged main; B4.3 revalidate commit is implemented on PR #100; exact-head hosted CI run #923 passed (949 tests, 113 warnings), with Operator review/merge pending. B5, B6, and R7-C remain unauthorized. See `PLAN.md` and the B3 closeout record.

| Task / operation |
|---|---|---|---|---|

| **assess_knowledge_revalidation — TaskRuntime-integrated; no automatic dispatch** | Assess re-examined canonical evidence against one exact current KnowledgeItem state before an explicit revalidation decision. Existing evidence may qualify only while temporally relevant and source-valid; time-sensitive/current-condition claims, expired/changed sources, or material newer/contradictory evidence require new observations. | Untrusted typed `KnowledgeRevalidationAssessment` draft only. | TaskRuntime owns the ordinary Task lifecycle; application rebuilds/re-verifies canonical references, Team ownership, source snapshot hashes and applicable provenance/quote constraints; binds the rebuilt evidence basis to current pointer, content version/hash and evaluator identity/revision; then records one immutable assessment and Task-attributed Event. | No LearningChange disposition, KnowledgeItem, TeamPolicy, projection, Context, approval or confidence write; no autonomous reactivation. |
| **assess_knowledge_lifecycle — TaskRuntime-integrated in B3.5; no automatic dispatch** | Record operation-specific retire/supersede findings from exact proposal state, evidence references and structured Operator rationale. | No worker/model business write; no LLM scoring. | Application-authored deterministic Task validates exact target/proposal and, for supersede, exact predecessor and successor binding; it records one immutable `KnowledgeLifecycleAssessment` and Task-attributed Event. | No LearningChange disposition, KnowledgeItem, TeamPolicy, projection, Context or approval write; no autonomous lifecycle commit. |
| **propose_learning_change — R7-B create/revise/revalidate; B5.1 candidate extension** | Propose create, revise, and revalidate LearningChanges through the existing Task. B5.1 adds an optional create-with-successor candidate; retire and supersede proposals remain outside the current implementation scope. | LearningChange proposal only. | Application validates proposal/evidence; a successor candidate binds the same-Team predecessor's current pointer, version, content hash, and full-state hash in the proposal. TaskRuntime/cost-ledger effects remain on the existing path. | No KnowledgeItem, TeamPolicy, projection, approval, or direct canonical write. The worker never commits the candidate or mutates its predecessor. |
| **approve_learning_change — trusted Operator approval; B4.4 closed; B5.1 active in PR #116** | Existing trusted Operator Task, invoked through the host-authenticated typed-principal adapter. Merged main admits `create`, `revise`, and `revalidate`; B5.1 extends the existing `create` operation with create-with-successor. | No model/worker business writes. | Application commit writes the LearningChange disposition, KnowledgeItem transition, and exact Task-attributed Events. For a B5.1 candidate it rechecks the exact predecessor under the Team-scoped graph lock, requires a future review date from the approval Task's pinned TeamPolicy, creates an active candidate, and leaves the predecessor unchanged. The reciprocal publication gate keeps the candidate out of retrieval and Context until a later authorized supersede commit. | No retire/supersede canonical commit, TeamPolicy write, seed bypass, arbitrary target/version, autonomous approval, second runtime, or alternate commit path. B5.2–B5.4, B6, and R7-C remain separately gated. |
| **review_knowledge — unchanged D7 exception** | Deterministic scheduled maintenance Task. | No worker business writes. | TaskRuntime/application service may perform only status active → needs_review and its Task-attributed Event. | No content/confidence change, LearningChange lifecycle operation, review-date extension, reactivation, revision, supersession, or retirement. |
| **assess_knowledge_use** | Proposed R7-C evaluator Task for a later Task's exact exposed/cited KnowledgeItem version and terminal Outcome. | KnowledgeUseAssessment proposal only. | Application validates the exact Task, Outcome, Context Snapshot/manifest, TaskKnowledgeReference, item ID/version/hash/current-LearningChange identity, and evaluator contract before recording the assessment and Event. | No KnowledgeItem/LearningChange/TeamPolicy mutation; no inferred citation, causal claim, or decision authority. |

A TaskKnowledgeReference is not a new worker write grant or separate approval Task. It is an application-owned, Task-attributed reference recorded only after code validates a worker-nominated claim reference against the immutable Context manifest. The model cannot write a citation record directly.

The frozen R7-B design reuses `approve_learning_change`; it does not introduce a separate `approve_knowledge_lifecycle` Task type. `assess_knowledge_quality` is the existing R7-A quality-assessment Task. Both B3.3 `assess_knowledge_revalidation` and B3.5-integrated `assess_knowledge_lifecycle` have explicit TaskRuntime admission/finalization/recovery paths and narrow TaskRunner/application adapters. Neither is registered for automatic TaskDispatcher dispatch; invocation remains explicit through the application boundary. The repository has no generic Task registry, and B3.5 extends the existing explicit TaskRuntime branches. R7-C `assess_knowledge_use` remains a later, unauthorized stage. Neither assessment Task gains canonical `KnowledgeItem` or `LearningChange` write authority. Merged main admits create/revise/revalidate. B5.1 adds create-with-successor as an optional relation on the existing create operation; retire and supersede commits remain outside the current authorization.


### RW-3 contract clarifications from independent design review

The following details are normative for the proposed update_thread worker and supersede less-specific wording in its Reads/Flow/Failure bullets above:

- EvidenceLink membership is exhaustive: include every accepted EvidenceLink belonging to an active Hypothesis on the target Thread. Do not rank or discretionarily filter. Include and verify each exact immutable source Snapshot. If the complete set exceeds a bound, fail closed; do not silently choose a subset.
- Use only the policy_version pinned on the immutable Task. Never substitute the latest TeamPolicy at execution time. Missing, invalid, or cross-Team pinned policy fails closed before provider invocation.
- The provider boundary must return validated usage/model metadata and raw completion text before JSON parsing. Reconcile known usage first, then parse. Malformed JSON with valid usage retains the reconciled charge and becomes a non-retryable TaskRuntime parser failure. Invalid/missing usage follows existing unknown-cost accounting.
- The shared commit core receives either the existing canonical Operator principal or a fixed application-defined model_worker actor attributed to the admitted Task. Model output cannot supply actor identity. Preserve RW-2 Operator principal checks and Event behavior; do not add a generic actor framework.
- RW-3 successful terminal categories are success_no_change (explicit empty list, reconciled charge, no commit) and success_update_thread_committed (at least one accepted proposal committed). Both use ordinary TaskRuntime terminal Event, Outcome, replay, and recovery behavior. All-invalid batches remain failures. No other Task type's result categories change.


### RW-3 request, recovery, and actor contracts added by independent review

The immutable model-worker request is created by one narrow host-invoked application operation modeled on R6-F's Operator Task creator. The trusted host authenticates the Operator and issues `TrustedOperatorPrincipal` with the exact `OperatorGrant(team_id, action="request_update_thread")`; Watch derives Team from the locked target Thread and independently validates that grant. The request contains only Thread ID and a host idempotency UUID, never caller-supplied authoritative Team. The Task and one `update_thread_requested` Event are committed atomically. The Event binds schema version, Task/Team/Thread IDs, pinned policy version, canonical `requested_by_operator_id`, idempotency-key hash, and a domain-separated SHA-256 request fingerprint. Same key/same fingerprint/same Operator replays; a different Thread or Operator conflicts. Missing/wrong-type/malformed principal, wrong-Team/wrong-action grant, cross-Team/inactive-Team/unavailable/resolved Thread, or corrupt/missing/duplicate request evidence fails closed without creating a Task/Event or before provider invocation as applicable. The host principal is an in-process trust contract, not a credential; the repository has no production host composition root, so end-to-end authentication remains an integration proof, not a claimed completed test. The existing Task primary-key transaction arbitrates concurrent same-key creation; no partial unique index or migration is required by default. The worker loads the Event and cannot create/amend the request, and receives no Operator principal or `operator_id`. Strategy, PlanService, Plan materialization, and TaskDispatcher do not produce these Tasks. See RW-3 design §10.4.

TaskRuntime recovery owns the Task lock and attempt. Its narrow resume_update_thread_in_session(session, task, attempt) handoff reuses the locked Session, never calls the provider, and resumes the durable receipt/proposal set through the shared commit core. Transient persistence failure leaves the same proposal resumable; permanent provenance/integrity conflict writes no business state and is terminalized with update_thread_recovery_inconsistent. Only the no-durable-receipt crash window may follow ordinary new-attempt retry after the reserved charge is marked unknown. See RW-3 design §10.5.

The shared commit core receives a typed envelope and closed actor union: the existing authenticated Operator principal for RW-2, unchanged, or a fixed model_worker actor containing the admitted Task and verified request Event for RW-3. Model accepted/rejected proposal Events are Task-attributed and contain no operator_id; model and Operator terminal validators accept only their own Event families. Proposal serialization is strict and canonical: existing typed models, model_dump(mode="json"), canonical UUID/enum values, preserved proposal-array order, duplicate-key rejection, canonical UTF-8 JSON and SHA-256. Transient, all-invalid, and permanent-integrity commit failures have distinct durable dispositions. See RW-3 design §§10.6–10.8 and proof rows RW-REQ-01, RW-REC-01, RW-ACT-02, RW-SER-01, and RW-CF-01.

## RW-3 request identity and replay contract — Checkpoint 4 approved

The host request uses a fixed, dedicated UUIDv5 namespace and canonical name {team_id}:update_thread:{idempotency_key}. This is Team-scoped idempotency: same Team/key resolves the same Task; reuse with a different Thread or requesting Operator conflicts. The same UUID under another Team produces a separate Team-scoped Task identity; global cross-Team uniqueness is not promised.

Creation follows the R6-F concurrency pattern: conflict-safe Task insertion, request Event appended only by the winning transaction, and competing insert/replay resolved through the deterministic Task primary key. The request Event stores the canonical requester identity from canonical_operator_identity() and only a SHA-256 hash of the canonical idempotency UUID; it never stores the raw key.

The request fingerprint is SHA-256 over canonical compact sorted-key UTF-8 JSON, domain-separated by watch.rw3.update-thread-request.v1 and schema version 1. It binds canonical Task, Team, and Thread UUIDs, the pinned policy version, canonical requester identity, and idempotency-key hash. Replay requires exactly one valid request Event and matching Task/request/policy/Thread evidence. A newer TeamPolicy does not invalidate replay; the original Task policy pin remains authoritative. Integrity mismatches fail closed.

The proposal-set fingerprint is separate and uses watch.rw3.update-thread-proposals.v1, binding the complete typed proposal list to Task, Team, Thread, attempt, pinned policy, receipt Event, and charge. Typed values use Pydantic JSON-mode serialization; proposal order is preserved, duplicate keys rejected, and an empty list is valid. The model response is limited to eight proposals; the Operator request limit remains 64.

## Checkpoint 5 — cross-document contract alignment

For RW-3, this Task specification is authoritative for Task type, status, attempts, links, write scope, and budget. The detailed request/proposal identity and replay protocol is in [the RW-3 design and acceptance plan](development/rw-3-design-and-acceptance.md); milestone status and authorization are only in `PLAN.md`. The six-document reconciliation confirms the Checkpoint 4 rules: Team-scoped UUIDv5 identity; same-Team/key conflicts for different Thread/requester; separate identity across Teams; original Task policy pin retained after policy advancement; hashed idempotency key only; and distinct request versus proposal-set fingerprints. These requirements are normative. RW3.1–RW3.3 are implemented, accepted, and merged. RW3.4 implementation and corrective recovery/evidence integration are merged through PRs #163, #165, #167, #169, and #178; PR #178's exact head passed hosted CI #1775 with 1,303 tests. The 35-row ledger remains 28 PASS / 7 PARTIAL / 0 OPEN. Formal RW3.4 Operator acceptance is deferred; seven PARTIAL qualifications remain. Live provider invocation remains unauthorized.

## Thread lifecycle authority — accepted RW4-1B refinement (2026-11-26)

Thread creation and lifecycle writes belong to the trusted Watch application/Kernel boundary. The host authenticates the Operator and delegates; it does not write Thread rows. activate_team is the canonical intended creator for Operator-approved starter Threads. The actual deployment writer/credential inventory remains unknown and is an F2 blocker.

**Resolution uses the existing operator_update Task type.** It is a typed, mutually exclusive operation mode (resolve_thread), not a new Task type. Keep the existing OperatorUpdateRequest proposal form and its non-empty proposals unchanged; add a typed ResolveThreadRequest with thread_id, idempotency_key, and reason. The reason must contain at least one non-whitespace character and be at most 2,000 Unicode code points; preserve the submitted text exactly for fingerprinting and replay. A request is either one proposal-commit request or one resolution request; mixed requests are invalid. The resolution mode is Kernel/application-managed and is not added to allowed_writes. update_thread remains a model-worker knowledge-update Task and has no Thread lifecycle authority.

The resolution request binds the target Thread, non-empty reason, trusted Operator principal, and idempotency key in immutable Task-attributed request provenance. Control Room checks the exact resolve_thread Team grant (not merely the generic operator_update grant) using the Team derived from the locked Thread. Exact replay returns the original Task/result; the same key with a different target, reason, operation mode, or Operator principal conflicts.

Allowed transition: active → resolved or dormant → resolved; resolved is terminal. The Team must meet the existing active-Team operator_update admission rule. The operation does not change Thread.domain, does not create a Thread, and does not update last_updated_at. It uses Task → Team → Thread lock order, refreshes the Thread after acquiring its row lock, increments Team revision once for an actual transition, and appends exactly one immutable thread_resolved Event with Task/Team/Thread/Operator attribution, prior status, resolved, and reason in the same business transaction.

Reuse the existing Task identity namespace task_id_for_request(team_id, idempotency_key), operator_update_requested provenance, operator_update_committed business marker, and recovery path. The resolution terminal observation is a typed variant carrying operation, Thread ID, prior/resolved status, reason, and thread_resolved Event identity; do not fabricate proposal counts. The existing Operator update business-commit marker/recovery path is reused. The Thread status/revision/Event business transaction is not the TaskRuntime terminalization transaction: TaskRuntime separately remains the sole owner of Task terminal state, terminal Events, and recovery. Recovery after a committed business write must not repeat the transition, revision increment, or Event. Exact replay, rejected/no-op requests, and rollback do not increment Team revision.

No new Task type, TaskRuntime, dispatcher path, worker permission, generic lifecycle framework, or production implementation is authorized by this documentation refinement. The physical and executable proofs remain separately gated; F2 stays OPEN/BLOCKING until the deployment writer/credential inventory is attested.
