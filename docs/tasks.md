# docs/tasks.md

# Task specifications

Every durable write in Watch is performed by a Task. This document is the spec for each v1 task type: what it reads, what it may write, how it runs, what is validated at commit time, and how it fails.

## 1. Task model

- Every Task has: Team, `task_type`, optional Thread, `input_refs`, `allowed_tools`, `allowed_writes`, `policy_version`, `budget` (`max_tool_calls`, `max_cost_usd`, `deadline_seconds`).
- Task statuses and transitions: see `docs/architecture.md` §4.
- **All durable writes go through core repositories/services** that enforce schema, ownership, scope, and transitions (INV-02, INV-14). Graph nodes return proposal objects; they never write.
- Every transition emits an Event. Commit-time preconditions are re-checked (INV-13).
- **Per-proposal validation:** valid proposals commit atomically as one set; invalid proposals are rejected with Events carrying reasons; a Task whose proposals all fail is marked failed.
- Retries (arq) re-execute idempotently: prior commits are detected via the Task's Events and skipped.
- Tool calls and token usage are attributed to the Task and counted against its budget.
- Most task types require an `active` Team; `create_team`, `configure_team`, and `activate_team` operate on shell/configuring teams and are the exceptions.
- **No path bypasses validation for being human** (INV-15): operator task types use the same commit kernel, and operator identity is recorded in Event payloads.

**Creation sources:** Triggers (all three types), the scheduler (ingestion, decay, review, overdue scans), Task enqueues (triage → update; consultation follow-ups), the API and CLI (manual Operator tasks), and Task retries.

## 2. Common validation rules (every commit path)

1. Task status is `running` and budget is not exhausted (operator task types: no model cost, no enforced deadline).
2. All referenced entities exist and belong to the Task's Team.
3. All writes are within the Task's scope matrix entry (§4).
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
- **Failure:** connector error → retry per arq policy; partial state impossible (snapshot-and-signal commit together or not at all).
- **Budget:** no model calls; see §5.

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
- **Writes:** Consultation (`status="open"`, context Snapshot + hash of exactly what the expert will be shown), Event; optionally enqueue of the follow-up work after answering.
- **Validation:** subject exists, same Team; context Snapshot stored before commit; `check_by` set when the question is time-bound.
- **Key rule:** opening the Consultation **ends this Task**. Waiting for a human happens between Tasks, never inside one.

### `answer_consultation` — Operator via API
- **Purpose:** record the expert's answer.
- **Reads:** the open Consultation.
- **Writes:** Consultation status `open → answered` (+ answer Snapshot + hash, optional structured `verdict` per team policy), Event with operator identity; optional enqueue of a follow-up update/evaluate Task so the answer enters the loop.
- **Validation:** Consultation is `open`; answer Snapshot stored before commit; the answer becomes citable as `source_kind="consultation"` evidence (INV-04 applies to any later quote of it).

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

| Task type | Team | Signal | SignalDisposition | Thread | Hypothesis | EvidenceLink | ConfidenceChange | Artifact | Outcome | Evaluation | KnowledgeItem | TeamPolicy | LearningChange | Trigger | Consultation | TeamDraft |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `ingest_source` | — | W | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `manual_signal_ingest` | — | W | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `triage_signal` | — | — | W | C/W¹ | — | — | — | — | — | — | — | — | — | — | — | — |
| `update_thread` | — | — | W² | W³ | W | W | W | — | — | — | — | — | — | — | — | — |
| `operator_update` | — | — | W² | W³ | W | W | W | — | — | — | — | — | — | — | — | — |
| `apply_decay` | — | — | — | W⁴ | — | — | W | — | — | — | — | — | — | — | — | — |
| `check_triggers` | — | — | — | — | — | — | — | — | — | — | — | — | — | W | — | — |
| `review_knowledge` | — | — | — | — | — | — | — | — | — | W⁵ | — | — | — | — | — | — |
| `render_output` | — | — | — | — | — | — | — | W | — | — | — | — | — | — | — | — |
| `record_outcome` | — | — | — | — | — | — | — | — | W | — | — | — | — | — | — | — |
| `evaluate_outcome` | — | — | — | — | — | W⁶ | — | — | — | W | — | — | — | — | — | — |
| `propose_learning_change` | — | — | — | — | — | — | — | — | — | — | — | — | W | — | — | — |
| `approve_learning_change` | — | — | — | — | — | — | — | — | — | — | W | W | W | — | — | — |
| `seed_knowledge` | — | — | — | — | — | — | — | — | — | — | W | W | W | — | — | — |
| `request_consultation` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | W⁷ | — |
| `answer_consultation` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | W⁸ | — |
| `create_team` | W⁹ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `configure_team` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | W |
| `activate_team` | W¹⁰ | — | — | C | — | — | — | — | — | — | — | W | — | — | — | W¹¹ |

¹ Create on `new_thread`; reactivate `dormant → active`. ² Refine `deferred` only. ³ Summary projection and explicit resolution only. ⁴ `active → dormant` only. ⁵ `active → needs_review` only. ⁶ With `subject_kind="evaluation"`. ⁷ Create only (`open`). ⁸ `open → answered` only. ⁹ Create only (`configuring`). ¹⁰ `configuring → active` only. ¹¹ `draft → approved` only.

Every cell is enforced at commit; attempts outside the matrix are rejected and recorded (INV-14). The `operator_update` row is intentionally identical to `update_thread` — that is INV-15 expressed as a table.

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