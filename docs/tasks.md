# docs/tasks.md

# Task specifications

Every durable write in Watch is performed by a Task. This document is the spec for each v1 task type: what it reads, what it may write, how it runs, what is validated at commit time, and how it fails.

## 1. Task model

- Every Task has: Team, `task_type`, optional Thread, `input_refs`, `allowed_tools`, `allowed_writes`, `policy_version`, `budget` (`max_tool_calls`, `max_cost_usd`, `deadline_seconds`).
- Task statuses and transitions: see `docs/architecture.md` §4.
- **All durable writes go through core repositories/services** that enforce schema, ownership, scope, and transitions (INV-02, INV-14). Graph nodes return proposal objects; they never write.
- `allowed_writes` names the business/domain entity kinds that the Task's worker may propose to create or change, subject to this matrix. It does not grant the worker direct database or object-storage access.
- The matrix also marks `K` operations: explicitly scoped Task lifecycle or companion writes performed only by application/Kernel code. They are mandatory, conditional, or optional only as the row's specification states. `K` is an explicit scope category, not an exception to INV-14. A `K` cell authorizes only the exact Task, Event, or Snapshot operation specified for that Task type; it never permits a worker to request arbitrary Tasks, Events, or Snapshots. The application controls Task lifecycle/enqueue data and Event type, payload, and attribution, and validates Snapshot content/reference and association with the permitted business write.
- Every Task transition emits a Task-attributed Event. A commit emits its required success, no-change, or rejection Event as applicable. These Kernel-generated records are constrained by the row's `K` entries; the worker cannot write them directly. Commit-time preconditions are re-checked (INV-13).
- **Per-proposal validation:** valid proposals commit atomically as one set; invalid proposals are rejected with Events carrying reasons; a Task whose proposals all fail is marked failed.
- Retries (arq) re-execute idempotently: prior commits are detected via the Task's Events and skipped.
- Tool calls and token usage are attributed to the Task and counted against its budget.
- Most task types require an `active` Team; `create_team`, `configure_team`, and `activate_team` operate on shell/configuring teams and are the exceptions.
- **No path bypasses validation for being human** (INV-15): operator task types use the same commit kernel, and operator identity is recorded in Event payloads.

**Creation sources:** Triggers (all three types), the scheduler (ingestion, decay, review, overdue scans), Task enqueues (triage → update; consultation follow-ups), the API and CLI (manual Operator tasks), and Task retries.

## 2. Common validation rules (every commit path)

1. Task status is `running` and budget is not exhausted (operator task types: no model cost, no enforced deadline).
2. All referenced entities exist and belong to the Task's Team.
3. All worker-proposed business writes are within `allowed_writes` and the Task's scope matrix entry (§4). Kernel-managed side effects are permitted only where the same row explicitly marks `K`, and only in the documented association with that Task operation.
4. Snapshots referenced by quotes exist and hashes match (INV-03, INV-04).
5. All state transitions are legal per the architecture §4 tables.
6. The Task's Team is `active`, except for the team-setup task types.

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

### `manual_signal_ingest` — Operator via API/CLI
- **Purpose:** admit externally obtained material with provenance.
- **Writes:** same as `ingest_source`; the API/CLI call creates the Task so provenance is uniform.
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

### `operator_update` — Operator via API/CLI
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

### `review_knowledge` — deterministic, scheduled
- **Purpose:** flag KnowledgeItems whose `review_after` has passed.
- **Writes:** KnowledgeItem status `active → needs_review`; Event.
- **Validation:** status transition legality; never retires or revises (that is the learning path's job).

### `render_output` — model worker + deterministic assembly
- **Purpose:** produce an Artifact from the current world model.
- **Reads:** Thread, active Hypotheses, verified evidence packs, relevant active KnowledgeItems, current policy, prior Artifacts.
- **Writes:** Artifact (+Snapshot +hash), Event. **Not:** any world-memory entity (INV-14).
- **Flow:** F4. Delivery gating: if a policy-required Consultation on the subject is open, the Task ends after recording an Event and enqueuing `request_consultation` — it does not wait inside the Task (ADR-0020).
- **Commit-time validation:** evidence pack quotes pre-validated; deterministic post-check rejects bodies containing URL/link patterns; Snapshot stored and hashed.
- **Failure:** post-check failure → Task failed; no Artifact committed.

### `record_outcome` — Operator via API (connector later)
- **Purpose:** durably record what happened — or register a prediction before the result is known.
- **Reads:** subject entity (validates existence and Team ownership).
- **Writes:** Outcome (+observation Snapshot +hash where an observation exists), Event.
- **Validation:** predictions are two Outcomes — `prediction_registered` (`expected` validated against the fixed schema: resolution condition, `check_by`, `predicted_band`; observation fields null, permitted for this type only) and `prediction_check` (observation filled; `expected.registered_outcome_id` names the registration). Delivery outcomes on an Artifact with an open policy-required Consultation are rejected. Subject polymorphism validated.

### `evaluate_outcome` — model worker, rule, or human
- **Purpose:** assess an Outcome and the work that produced it.
- **Reads:** Outcome, subject, related Hypotheses/EvidenceLinks, `expected` for prediction checks.
- **Writes:** Evaluation; EvidenceLinks with `subject_kind="evaluation"`; Event.
- **Validation:** Outcome belongs to the Team; conclusion vocabulary; quote checks on new links (INV-04). Mechanical deadline checks may run as `evaluator_kind="rule"` with no model calls.

### `propose_learning_change` — model worker
- **Purpose:** convert recorded Evaluations into a proposed Team-memory change.
- **Reads:** one or more recorded Evaluations (same Team), the exact current target KnowledgeItem/TeamPolicy version, supporting evidence.
- **Writes:** LearningChange (`status="proposed"`), Event. **Nothing else** (INV-12).
- **Validation:** basis Evaluations exist and belong to the Team; target version recorded exactly; proposed state matches operation; policy proposals flagged as requiring approval.

### `approve_learning_change` — Operator via API
- **Purpose:** run the learning commit service on a proposal.
- **Writes:** LearningChange status; KnowledgeItem or TeamPolicy new version (on acceptance); Event.
- **Validation:** full F6 commit-service checklist: evaluation basis, evidence present, target version unchanged since proposal, proposed state schema-valid, Operator approval identity recorded in the Event payload.
- **Rejection:** recorded with reason; the proposal is never silently edited.

### `seed_knowledge` — Operator via API
- **Purpose:** explicit `manual_seed` creation of additional KnowledgeItems or a revised TeamPolicy outside the setup flow.
- **Writes:** LearningChange (`basis_kind="manual_seed"`, committed immediately), target entity, Event.
- **Validation:** same schema and version checks as F6 minus the Evaluation basis.

### `request_consultation` — model worker (or created by policy/Trigger/enqueue)
- **Purpose:** the loop asks for expert opinion (ADR-0020).
- **Reads:** subject entity and related evidence.
- **Writes:** Consultation (`status="open"`, context Snapshot + hash of exactly what the expert will be shown), Event. Any follow-up Task after the answer is enqueued by the later `answer_consultation` Task; this Task ends when it opens the Consultation.
- **Validation:** subject exists, same Team; context Snapshot stored before commit; `check_by` set when the question is time-bound.
- **Key rule:** opening the Consultation **ends this Task**. Waiting for a human happens between Tasks, never inside one.

### `answer_consultation` — Operator via API
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

### `create_team` — Operator via API/CLI
- **Purpose:** create a Shell team for a new subject (F7).
- **Writes:** Team (`status="configuring"`), subject-brief Snapshot (+hash, referenced from the Event payload and by the subsequent TeamDraft), Event.
- **Validation:** unique team key; Domain may be any pack key including `generalist`; brief is freeform prose stored immutably.

### `configure_team` — model worker, runs on configuring teams
- **Purpose:** draft the team configuration from the subject brief and samples (F7).
- **Reads:** subject-brief Snapshot, sample manual Signals, pack defaults (vocabulary structure, templates, decay bounds, policy JSON Schema).
- **Writes:** TeamDraft (`status="draft"`, config Snapshot + hash, `advisor_notes` citing the samples), Event.
- **Validation:** proposed policy validates against the JSON Schema; vocabulary conforms to the pack's structure; candidate sources marked unverified; draft revision current.
- **Failure:** invalid model output → draft discarded with reason; Task failed.

### `activate_team` — Operator via API
- **Purpose:** review, edit, and activate the team (F7).
- **Writes:** TeamPolicy v1; starter Threads (through the normal commit path); Team `configuring → active`; TeamDraft `approved` (config re-snapshotted if the Operator edited it); Event with operator identity.
- **Validation:** policy against JSON Schema; vocabulary within pack structure; pack-contract conformance; draft revision current (optimistic check, INV-13); operator identity in Event payload.

## 4. Write-scope matrix

`W`/`C` identify business/domain entity mutations available for application
validation of worker proposals. `K` identifies an explicitly bounded,
Kernel-managed operation; it is not included in the worker's `allowed_writes`
list. The `Task (K)` column always covers the current Task's documented runtime
transitions. Superscripts there additionally permit only the named Task
enqueue operation. `—` means that the Task type cannot cause that write.
All Task, Snapshot, and Event writes are performed by application code, never
by a worker.

| Task type | Team | Signal | SignalDisposition | Thread | Hypothesis | EvidenceLink | ConfidenceChange | Artifact | Outcome | Evaluation | KnowledgeItem | TeamPolicy | LearningChange | Trigger | Consultation | TeamDraft | Task (K) | Snapshot (K) | Event (K) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `ingest_source` | — | W | — | — | — | — | — | — | — | — | — | — | — | — | — | — | K | K¹ | K |
| `manual_signal_ingest` | — | W | — | — | — | — | — | — | — | — | — | — | — | — | — | — | K | K¹ | K |
| `triage_signal` | — | — | W | C/W² | — | — | — | — | — | — | — | — | — | — | — | — | K²³ | — | K |
| `update_thread` | — | — | W³ | W⁴ | W | W | W | — | — | — | — | — | — | — | — | — | K | — | K |
| `operator_update` | — | — | W³ | W⁴ | W | W | W | — | — | — | — | — | — | — | — | — | K | — | K |
| `apply_decay` | — | — | — | W⁵ | — | — | W | — | — | — | — | — | — | — | — | — | K | — | K |
| `check_triggers` | — | — | — | — | — | — | — | — | — | — | — | — | — | W | — | — | K²⁰ | — | K |
| `review_knowledge` | — | — | — | — | — | — | — | — | — | W⁶ | — | — | — | — | — | — | K | — | K |
| `render_output` | — | — | — | — | — | — | — | W | — | — | — | — | — | — | — | — | K²¹ | K⁷ | K |
| `record_outcome` | — | — | — | — | — | — | — | — | W | — | — | — | — | — | — | — | K | K⁸ | K |
| `evaluate_outcome` | — | — | — | — | — | W⁹ | — | — | — | W | — | — | — | — | — | — | K | — | K |
| `propose_learning_change` | — | — | — | — | — | — | — | — | — | — | — | — | W | — | — | — | K | — | K |
| `approve_learning_change` | — | — | — | — | — | — | — | — | — | — | W | W | W | — | — | — | K | — | K |
| `seed_knowledge` | — | — | — | — | — | — | — | — | — | — | W | W | W | — | — | — | K | — | K |
| `request_consultation` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | W¹⁰ | — | K | K¹¹ | K |
| `answer_consultation` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | W¹² | — | K²² | K¹³ | K |
| `create_team` | W¹⁴ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | K | K¹⁵ | K |
| `configure_team` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | W | K | K¹⁶ | K |
| `activate_team` | W¹⁷ | — | — | C | — | — | — | — | — | — | — | W | — | — | — | W¹⁸ | K | K¹⁹ | K |

¹ Store only the immutable Snapshot for the Signal created by this ingestion
operation. ² Create on `new_thread`; reactivate `dormant → active`.
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
| `approve_learning_change` | 0 | 0 | — |
| `seed_knowledge` | 0 | 0 | — |
| `request_consultation` | 4 | 0.30 | 180 |
| `answer_consultation` | 0 | 0 | — |
| `create_team` | 0 | 0 | — |
| `configure_team` | 6 | 0.60 | 300 |
| `activate_team` | 0 | 0 | — |