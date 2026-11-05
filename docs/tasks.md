# Task specifications
Every durable write in Watch is performed by a Task. This document is the spec for each v1 task type: what it reads, what it may write, how it runs, what is validated at commit time, and how it fails.
## 1. Task model
- Every Task has: Team, `task_type`, optional Thread, `input_refs`, `allowed_tools`, `allowed_writes`, `policy_version`, `budget` (`max_tool_calls`, `max_cost_usd`, `deadline_seconds`), `created_at`, `attempt_count`, and a per-Task pinned `max_attempts` (initial default: 3 total starts). `completed_at` is nullable and set only for status `done`. These lifecycle fields are part of the R6 target; they are not all present in the current ORM baseline.
- Task statuses and transitions: see `docs/architecture.md` §4.
- **All durable writes go through core repositories/services** that enforce schema, ownership, scope, and transitions (INV-02, INV-14). Graph nodes return proposal objects; they never write.
- `allowed_writes` names the business/domain entity kinds that the Task's worker may propose to create or change, subject to this matrix. It does not grant the worker direct database or object-storage access.
- The matrix also marks `K` operations: explicitly scoped Task lifecycle or companion writes performed only by application/Kernel code. They are mandatory, conditional, or optional only as the row's specification states. `K` is an explicit scope category, not an exception to INV-14. A `K` cell authorizes only the exact Task, Event, or Snapshot operation specified for that Task type; it never permits a worker to request arbitrary Tasks, Events, or Snapshots. The application controls Task lifecycle/enqueue data and Event type, payload, and attribution, and validates Snapshot content/reference and association with the permitted business write.
- Every Task transition emits a Task-attributed Event. A commit emits its required success, no-change, or rejection Event as applicable. These Kernel-generated records are constrained by the row's `K` entries; the worker cannot write them directly. Commit-time preconditions are re-checked (INV-13).
- **Per-proposal validation:** valid proposals commit atomically as one set; invalid proposals are rejected with Events carrying reasons; a Task whose proposals all fail is marked failed.
- Retries must re-execute idempotently: prior business commits are detected through canonical idempotency keys and Task Events and skipped. R6's initial policy is three total starts per Task; retry/failure transitions, attempt fencing, and interrupted-task recovery are specified in [ADR-0030](decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md).
- `TaskRuntime.admit` is the application-controlled worker-pickup boundary: it validates a pending Task, active Team (except team setup), matching TeamPolicy version, and prerequisites; then atomically increments `attempt_count`, changes `pending → running`, and records one Task-attributed `task_started` Event. The Task-row lock serializes competing claims; non-pending claims are rejected rather than replayed as a second transition. `attempt_count` counts successful starts, including retries.
- Tool calls and token usage are attributed to the Task and counted against its budget.
- Most task types require an `active` Team; `create_team`, `configure_team`, and `activate_team` operate on shell/configuring teams and are the exceptions.
- **No path bypasses validation for being human** (INV-15): operator task types use the same commit kernel, and operator identity is recorded in Event payloads.
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
**Creation sources:** Triggers (all three types), the scheduler (ingestion, decay, review, overdue scans), Task enqueues (triage → update; consultation follow-ups), and Task retries. Manual Operator Tasks are created by a thin in-repository application adapter invoked in-process by a host after it authenticates and authorizes the Operator. This is not a separate deployed Watch API/CLI. Checkpoint 3 implements the adapter first for `approve_learning_change`; other manual Task specifications do not imply implemented callers.
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
- **Purpose:** disposition a Signal for the Team; enqueue follow-up work.
- **Reads:** Signal (+embedding), Domain `match_heuristics` and `dedup_policy`, Team's Threads (+embeddings), recent dispositions.
- **Writes:** SignalDisposition; Thread creation (`new_thread`); Thread reactivation (`dormant → active`); enqueue of `update_thread` for `deferred`/`matched` cases; Event.
- **Flow:** F1 steps 4–6.
- **Validation:** one disposition per `(signal, team)`; embedding similarity uses the recorded `embedding_model`; `new_thread` requires a strong deterministic heuristic match (per-domain threshold).
- **Failure:** heuristics error → disposition `deferred` with reason; never silent (INV-09).
### `update_thread` — model worker
- **Purpose:** incorporate new evidence into a Thread's world model.
- **Reads:** Thread, active Hypotheses, deferred/unprocessed dispositions, relevant active KnowledgeItems (bounded by `knowledge_selection` policy), current policy, source Snapshots on demand (tool calls).
- **Writes:** EvidenceLink, Hypothesis (create/supersede/reject), ConfidenceChange, SignalDisposition refinement (from `deferred` to a terminal value), Thread.summary (projection only), Event. **Not:** KnowledgeItem, TeamPolicy, Artifact, Outcome, other Threads.
- **Flow:** F2.
- **Commit-time validation:** quote offset + hash (INV-04); stance rule (INV-06); hypothesis transition legality with reasons (INV-07); confidence cause pairing (INV-05); per-proposal atomic commit; scope (INV-14). If policy `review.update_gating` is enabled and a required Consultation on the Thread is open, the commit is rejected until answered (default off).
- **Failure:** all proposals rejected → Task failed with rejection Events; partial commits never occur.
- **Invariants exercised:** INV-01, 02, 04, 05, 06, 07, 13, 14.
### `operator_update` — Operator via host-invoked application adapter
- **Purpose:** a human expert contributes directly to world memory — their own hypotheses, evidence, confidence judgments, rejections (ADR-0021).
- **Reads/Writes:** identical scope to `update_thread`.
- **Commit-time validation:** **identical to `update_thread`** — quotes checked against snapshots (INV-04), stance rule (INV-06), cause pairing (INV-05), explicit transitions (INV-07), scope (INV-14). An unsubstantiated expert hypothesis (no EvidenceLink) enters at `low` band, like any worker's.
- **Failure:** invalid proposals rejected with Events carrying reasons; human identity is never a validation exemption (INV-15).
### `apply_decay` — deterministic, scheduled
- **Purpose:** lower confidence of stale Hypotheses; flag dormant Threads.
- **Reads:** effective `decay_window` and `decay_action` (pack default or team `decay` override); Hypotheses' `last_touched_at` and bands; Thread composition.
- **Writes:** ConfidenceChange (`cause_kind="decay"` only), Thread status `active → dormant`, Event.
- **Flow:** F3.
- **Validation:** never rejects a Hypothesis; never touches `last_touched_at`; only this task type may write decay causes (INV-08).
- **Failure:** batch job; per-hypothesis errors are logged and skipped, Task completes with a summary Event.
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
### `propose_learning_change` — model worker (R6-F Checkpoint 2)
- **Purpose:** distill bounded, durable Team experience into one proposed KnowledgeItem creation; it does not commit learning.
- **Reads:** explicit IDs of one or more recorded Evaluations from the same Team; each Evaluation's terminal `task_execution` Outcome, terminal source Task Event, Evaluation-scoped EvidenceLinks, canonical Outcome/Signal Snapshots and hashes, and available Objective/Plan/Action/Context provenance.
- **Writes:** exactly one `LearningChange` with `target_kind="knowledge_item"`, `target_id=NULL`, `operation="create"`, and `status="proposed"`; one `learning_change_proposed` Event; the separate `experience_distillation` Task cost charge and its accounting Events. The Task's worker write scope is exactly `["LearningChange"]`. **No KnowledgeItem, TeamPolicy, Task, Snapshot, or projection write is granted to the worker** (INV-12); application-managed TaskRuntime/ledger effects remain Kernel side effects.
- **Validation:** all records and references are same-Team/domain as applicable; Outcome/Evaluation terminal Events, proposal hashes, EvidenceLink reference keys, Snapshot hashes, and quotes are revalidated; one case permits only a narrow low-confidence `practice`; `pattern`, `method`, or `playbook` requires at least two recorded Evaluations tied to distinct source Task IDs. Supporting, challenging, and mentioning links retain their canonical stance. **R6-G v2 behavior is implemented:** a source Task may be `done` with a D9 `worked` Evaluation or terminally `failed` with a D9 `failed` Evaluation only when its exact current-attempt terminal Events and Outcome agree; a failed case remains contrary evidence relative to a positive reusable-practice candidate. The pack stores raw EvidenceLink stance separately from derived case-relative stance and persists a version marker per evidence-basis case, included in the basis hash. Historical unmarked R6-F v1 basis records are reconstructed without adding a marker; unknown, mixed or mismatched markers fail closed. The exact deterministic evidence basis/hash is recomputed after provider return before the proposal is stored. Model references outside the supplied evidence pack, stale or altered evidence, malformed output, unknown usage, or cost overrun cannot yield a proposal.
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

### `approve_learning_change` — trusted Operator via host-invoked in-repository adapter (R6-F Checkpoint 3)
- **Purpose:** explicitly accept or reject one proposed LearningChange through the only R6-F canonical learning-commit path.
- **Caller and identity:** the host authenticates the Operator and authorizes the exact Team/action, then invokes the adapter in-process with a typed principal carrying stable issuer/subject. The adapter does not accept a bare `operator_id`, display name, email, request-body identity, or model output as proof. No deployed Watch API/CLI, login, token middleware, or user store is added.
- **Task creation:** atomically create one ordinary pending same-Team approval Task and its request Event, pinned to current TeamPolicy, with no Objective/Plan/Action links, exact `["LearningChange", "KnowledgeItem"]` scope, zero tools/cost. Host idempotency UUID resolves retries to the same Task and request fingerprint. Never insert a running Task.
- **Lifecycle:** call `TaskRuntime.admit`, invoke the narrow decision service synchronously, then call `TaskRuntime.finalize` with a typed accepted/rejected result. TaskRuntime alone changes attempt/status/completion and writes lifecycle Events/Outcome. `TaskDispatcher` remains ingestion-only.
- **Writes:** LearningChange disposition/history; KnowledgeItem changes only where supported by a validated proposal; one exact Task-attributed decision Event. Events are application-managed effects, not a worker grant. **No TeamPolicy write is permitted in R6-F.**
- **Validation:** exact Task type, same Team/current policy, current running attempt, exact write scope, host Team/action authorization, and canonical actor matching the request Event. Lock/revalidate the LearningChange, complete evidence hash/references, source hashes/quotes, operation, target version/status, and replay/concurrency preconditions.
- **Acceptance:** atomically commit KnowledgeItem state/version, LearningChange accepted disposition, previous/committed state, canonical operator identity, approval Task ID, timestamp, and acceptance Event.
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
## 4. Write-scope matrix
`W`/`C` identify business/domain entity mutations available for application
validation of worker proposals. `K` identifies an explicitly bounded,
Kernel-managed operation; it is not included in the worker's `allowed_writes`
list. The `Task (K)` column always covers the current Task's documented runtime
transitions. Superscripts there additionally permit only the named Task
enqueue operation. `—` means that the Task type cannot cause that
business/domain write through the worker-proposal channel; it does not disable
the separately governed `K` lifecycle side effects described below.
All Task, Snapshot, and Event writes are performed by application code, never
by a worker.

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
| `triage_signal` | — | — | W | C/W² | — | — | — | — | — | — | — | — | — | — | — | — | — | K²³ | — | K |
| `update_thread` | — | — | W³ | W⁴ | W | W | W | — | — | — | — | — | — | — | — | — | — | K | — | K |
| `operator_update` | — | — | W³ | W⁴ | W | W | W | — | — | — | — | — | — | — | — | — | — | K | — | K |
| `apply_decay` | — | — | — | W⁵ | — | — | W | — | — | — | — | — | — | — | — | — | — | K | — | K |
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
² Create on `new_thread`; reactivate `dormant → active`.
³ Refine `deferred` only. ⁴ Summary projection and explicit resolution only.
⁵ `active → dormant` only. ⁶ `active → needs_review` only.
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
²³ In addition to its own lifecycle, enqueue only `update_thread` for the
documented deferred/matched triage cases.
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
The `operator_update` row remains identical to `update_thread` — this is
INV-15 expressed as a table.
## 5. Budget defaults
Starting points, tuned during M2; per-Task values may override downward, never upward past policy ceilings (`budgets` rule group). Operator task types (`operator_update`, `answer_consultation`, `create_team`, `activate_team`, plus the other manual types) incur no model cost and have no enforced deadline (—).
| Task type | max_tool_calls | max_cost_usd | deadline_s |
|---|---|---|---|
| `ingest_source` | 0 | 0 | 60 |
| `manual_signal_ingest` | 0 | 0 | 60 |
| `triage_signal` | 0 | 0 | 60 |
| `update_thread` | 8 | 0.50 | 180 |
| `operator_update` | 0 | 0 | — |
| `apply_decay` | 0 | 0 | 300 |
| `check_triggers` | 0 | 0 | 60 |
| `review_knowledge` | 0 | 0 | 60 |
| `render_output` | 4 | 0.75 | 240 |
| `record_outcome` | 0 | 0 | — |
| `evaluate_outcome` | 4 | 0.40 | 180 |
| `propose_learning_change` | 4 | 0.40 | 180 |
| `assess_knowledge_quality` | 0 | 0 | 30 |

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

**Status:** `assess_knowledge_quality` is active in §§3–5 and operative §4 after PR #39 merged. All R7-B rows below—including `assess_knowledge_revalidation` and `assess_knowledge_lifecycle`—are non-active proposals; they add no Task registration, write grant or implementation authority.

| Proposed Task / operation | Purpose and authority | Proposed worker write scope | Application / TaskRuntime side effects | Explicitly forbidden |
|---|---|---|---|---|

| **assess_knowledge_revalidation — proposed R7-B Task** | Assess fresh/rechecked evidence against one exact current KnowledgeItem state before an explicit revalidation decision. | Untrusted typed `KnowledgeRevalidationAssessment` draft only. | TaskRuntime owns the ordinary Task lifecycle; application rebuilds/re-verifies the evidence basis, validates Team/item/current LearningChange pointer/content version/content hash and evaluator identity/revision, then records one immutable assessment and Task-attributed Event. | No LearningChange disposition, KnowledgeItem, TeamPolicy, projection, Context, approval or confidence write; no autonomous reactivation. |
| **assess_knowledge_lifecycle — proposed R7-B deterministic Task** | Record operation-specific retire/supersede findings from exact proposal state, evidence references and structured Operator rationale. | No worker/model business write; no LLM scoring. | Application-authored deterministic Task validates exact target/proposal and, for supersede, exact successor binding; it records one immutable `KnowledgeLifecycleAssessment` and Task-attributed Event. | No LearningChange disposition, KnowledgeItem, TeamPolicy, projection, Context or approval write; no autonomous lifecycle commit. |
| **propose_learning_change — proposed R7 extension** | Extend the existing create-only proposal Task to propose create/revise/revalidate/supersede/retire after each operation's evidence contract is accepted. | LearningChange proposal only. | Application validates proposal shape and evidence-basis hash; TaskRuntime/cost ledger effects remain managed by the existing runtime. | No KnowledgeItem, TeamPolicy, projection, approval, or direct canonical write. Until separately implemented, the delivered R6 behavior remains create-only. |
| **approve_learning_change — proposed R7 extension** | Existing trusted Operator Task, invoked through the host-authenticated typed-principal adapter; commits one exact proposed lifecycle change. | No model/worker business writes. | The application commit transaction may write the LearningChange disposition, KnowledgeItem current state/current pointer/successor link, and exact Task-attributed Events. TaskRuntime remains sole Task lifecycle authority. | No TeamPolicy write, seed bypass, arbitrary target/version, autonomous approval, or second commit path. The delivered R6 behavior remains create-only until R7-B is separately authorized and implemented. |
| **review_knowledge — unchanged D7 exception** | Deterministic scheduled maintenance Task. | No worker business writes. | TaskRuntime/application service may perform only status active → needs_review and its Task-attributed Event. | No content/confidence change, LearningChange lifecycle operation, review-date extension, reactivation, revision, supersession, or retirement. |
| **assess_knowledge_use** | Proposed R7-C evaluator Task for a later Task's exact exposed/cited KnowledgeItem version and terminal Outcome. | KnowledgeUseAssessment proposal only. | Application validates the exact Task, Outcome, Context Snapshot/manifest, TaskKnowledgeReference, item ID/version/hash/current-LearningChange identity, and evaluator contract before recording the assessment and Event. | No KnowledgeItem/LearningChange/TeamPolicy mutation; no inferred citation, causal claim, or decision authority. |

A TaskKnowledgeReference is not a new worker write grant or separate approval Task. It is an application-owned, Task-attributed reference recorded only after code validates a worker-nominated claim reference against the immutable Context manifest. The model cannot write a citation record directly.

The proposed lifecycle reuses `approve_learning_change`; it does not introduce a separate `approve_knowledge_lifecycle` Task type. The R7-A assessment Task remains the only active R7 assessment Task. R7-B proposal/approval extensions, `assess_knowledge_revalidation`, `assess_knowledge_lifecycle`, and R7-C `assess_knowledge_use` remain non-active and unauthorized. These proposals do not add rows to the active §4 write-scope matrix or activate any Task grant.
