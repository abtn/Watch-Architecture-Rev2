# docs/architecture.md

# Architecture

## 1. Purpose

Watch is a framework for persistent teams. A Team is a durable unit with a mission and Domain, a current model of the world, a working policy, a history of tasks and outcomes, and accumulated knowledge about how it operates.

Agents and model calls are temporary Workers. They propose observations, assessments, actions, and learning changes. Application code validates and commits durable state. Humans participate as first-class workers and consulted experts — through the same gates as any model worker (ADR-0020, ADR-0021). The central architectural question is:

> What persistent state, feedback loops, and controlled learning mechanisms allow temporary AI workers to behave like a team that gains experience over time?

The answer is durable records with explicit transitions and provenance — not a shared transcript. The rules that make this hold are enumerated in `docs/invariants.md` and cited below as `INV-NN`.

## 2. Conceptual model

```text
                         ┌─────────────────────┐
                         │       WATCH         │
                         │ persistent team     │
                         └──────────┬──────────┘
                                    │
             ┌──────────────────────┼──────────────────────┐
             │                      │                      │
          Observe                 Reason                  Act
             │                      │                      │
          Signals                Threads                Tasks
          Snapshots              Hypotheses              Workers
          Dispositions           Evidence                Tools
             │                      │                      │
             └──────────────────────┼──────────────────────┘
                                    │
                                 Outcomes
                                    │
                                 Evaluation
                                    │
                                  Learning
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
              World memory                    Team memory
              Threads                         Practices
              Hypotheses                      Patterns
              Evidence                        Methods
                                               Playbooks
                                                    │
                                           Future task behavior
```

Two memory layers:

- **World memory** — the subject being watched: Signals, Threads, Hypotheses, EvidenceLinks, ConfidenceChanges, SignalDispositions. Intentionally revisable and decaying.
- **Team memory** — what the Team learned from its own work: Outcomes, Evaluations, KnowledgeItems, LearningChanges, TeamPolicy. Changes only through the explicit learning path (INV-12).

### Human participation

Humans enter the loop through three channels, all of which pass the same validation gates (INV-15):

| Channel | Mechanism | Effect |
|---|---|---|
| Human as worker | `operator_update` Task | The expert's own hypotheses, evidence, and confidence judgments enter world memory with identical validation to a model worker |
| Loop requests opinion | `Consultation` + `request_consultation` / `answer_consultation` | The answer is an immutable hashed snapshot, citable as evidence (`source_kind="consultation"`); waiting happens between Tasks, never inside one (ADR-0020) |
| Human administers | `seed_knowledge`, `record_outcome`, `manual_signal_ingest`, `approve_learning_change`, `create_team`, `activate_team` | Durable writes with Task provenance and identity in Event payloads (ADR-0011) |

## 3. Entity reference

These sketches are narrative. **Migrations are the authoritative schema**; when this section and a migration disagree, the migration wins and this section is a bug.

### `Team`

```python
Team
    id: UUID
    key: str                    # stable human-readable identifier
    name: str
    domain: str                 # "newsroom" | "devteam" | "generalist" | ...
    mission: str
    status: str                 # "configuring" | "active" | "paused" | "retired"
    active_policy_id: UUID | null   # null while configuring
    created_at: datetime
```

A Team owns Threads, Tasks, Outcomes, and Team memory. Signals are not owned by a Team; relevance is expressed through SignalDispositions. A Team is created as a Shell team (`configuring`) and becomes `active` through `activate_team` (flow F7).

### `TeamPolicy`

```python
TeamPolicy
    id: UUID
    team_id: UUID
    version: int
    schema_version: int         # version of the rules JSON Schema
    rules: JSON                 # validated against the schema
    status: str                 # "active" | "superseded"
    created_at: datetime
    created_by_learning_change_id: UUID | null
```

The v1 rule vocabulary (fixed; extended only via a schema-version bump):

| Rule group | Controls |
|---|---|
| `routing` | which signal/thread situations get update Tasks, and when |
| `review` | what requires Operator approval; consultation requirements before delivery; `update_gating` flag (default off — blocks update commits while a required consultation on the Thread is open) |
| `knowledge_selection` | how many and which kinds of KnowledgeItems are retrieved into task context |
| `thresholds` | Trigger thresholds (e.g., "render when any hypothesis reaches high") |
| `budgets` | Team-level ceilings: per-day task count, per-day cost (aggregate limits; per-Task budgets are set at Task creation) |
| `vocabulary` | team-specific entity keys/values within the pack's default structure (generalist teams especially) |
| `sources` | per-team signal source list for parameterized connectors (e.g., generic RSS); advisor-suggested sources are unverified until first successful fetch |
| `decay` | per-team decay window/action override within pack bounds; the never-reject rule is not overridable |
| `preferences` | Domain-appropriate operating preferences within vocabulary |

Policy is not a security boundary; tool access and write permissions are enforced by application code. Initial policy is committed at `activate_team` or seeded explicitly (`seed_knowledge`). All policy changes in v1 require Operator approval (INV-12).

### `Signal`

```python
Signal
    id: UUID
    domain: str
    source_type: str            # "rss" | "api" | "arxiv" | "github" | "manual"
    origin_url: str
    fetched_at: datetime
    content_hash: str
    snapshot_ref: str
    extracted_summary: str      # non-authoritative
    embedding: vector
    embedding_model: str        # model name/version for coherent regeneration
```

Immutable. Uniqueness on `(origin_url, content_hash)`: an identical re-fetch from the same origin creates no new Signal. Syndicated near-duplicates from *different* origins are handled at triage (dedup policy), not at ingestion.

### `SignalDisposition`

```python
SignalDisposition
    id: UUID
    signal_id: UUID
    team_id: UUID
    thread_id: UUID | null      # set when matched / new_thread
    duplicate_of_signal_id: UUID | null
    disposition: str            # "matched" | "new_thread" | "noise" | "duplicate" | "deferred"
    reason: str
    decided_by_task_id: UUID
    created_at: datetime
    updated_at: datetime
```

One row per `(signal_id, team_id)`. Makes triage explicit and queryable (INV-09), including the multi-Team case: the same Signal may be matched by one Team and dismissed as noise by another.

### `Thread`

```python
Thread
    id: UUID
    team_id: UUID
    domain: str
    title: str
    status: str                 # "active" | "dormant" | "resolved"
    created_at: datetime
    last_updated_at: datetime
    summary: str                # projection
    summary_basis: JSON         # hypothesis IDs the summary was produced from
    entities: JSON              # domain-vocabulary entities
    embedding: vector
    embedding_model: str
```

`summary` and `embedding` are Projections, never authoritative (INV-11).

### `Hypothesis`

```python
Hypothesis
    id: UUID
    thread_id: UUID
    statement: str
    status: str                 # "active" | "superseded" | "rejected"
    confidence: str             # "low" | "moderate" | "high"
    created_at: datetime
    last_touched_at: datetime   # updated only by accepted evidence
```

Multiple active Hypotheses per Thread are normal and expected (INV-07). Merge is expressed as supersession naming the surviving Hypothesis. Hypotheses may be created by model workers or by Operators (`operator_update`); provenance lives on the creating Task.

### `EvidenceLink`

```python
EvidenceLink
    id: UUID
    subject_kind: str           # "hypothesis" | "evaluation"
    subject_id: UUID
    source_kind: str            # "signal" | "outcome" | "artifact" | "consultation"
    source_id: UUID
    stance: str                 # "supports" | "challenges" | "mentions"
    quote: str
    quote_offsets: [int, int]
    added_at: datetime
    added_by_task_id: UUID
```

Polymorphic references validated at commit, including Team ownership. Quote must be the exact substring at the offsets of the source's hashed Snapshot (INV-04). A Consultation answer is a first-class source: it carries an immutable hashed snapshot and may anchor confidence like any other source.

### `ConfidenceChange`

```python
ConfidenceChange
    id: UUID
    hypothesis_id: UUID
    from_confidence: str
    to_confidence: str
    cause_kind: str             # "evidence" | "decay"
    evidence_link_id: UUID | null   # required when cause_kind="evidence"; link stance must be supports|challenges
    decay_task_id: UUID | null      # required when cause_kind="decay"; task type must be apply_decay
    created_at: datetime
```

Every confidence change has exactly one cause (INV-05, INV-06, INV-08).

### `Artifact`

```python
Artifact
    id: UUID
    team_id: UUID
    task_id: UUID
    artifact_type: str          # "article" | "briefing" | "recommendation" | ...
    title: str
    snapshot_ref: str
    content_hash: str
    status: str                 # "draft" | "delivered" | "superseded" | "discarded"
    created_at: datetime
```

In v1, acting is represented by the Task that creates or delivers an Artifact; a separate external-Action entity is deferred (see §12).

### `Consultation`

```python
Consultation
    id: UUID
    team_id: UUID
    thread_id: UUID | null
    subject_kind: str           # "hypothesis" | "artifact" | "thread" | "evaluation"
    subject_id: UUID
    question: str
    context_snapshot_ref: str   # hashed snapshot of exactly what the expert was shown
    requested_by_task_id: UUID
    requested_by_kind: str      # "policy" | "model" | "operator"
    status: str                 # "open" | "answered" | "withdrawn" | "expired"
    answer_snapshot_ref: str | null
    answer_hash: str | null
    verdict: JSON | null        # optional structured answer (shape set by team policy)
    check_by: datetime | null   # overdue scan mirrors prediction registration
    created_at: datetime
    answered_at: datetime | null
```

A durable request for expert opinion. Opening a Consultation ends the requesting Task — waiting for humans happens between Tasks, never inside one (ADR-0020). The answer is immutable and citable as evidence.

### `Outcome`

```python
Outcome
    id: UUID
    team_id: UUID
    subject_kind: str           # "task" | "artifact" | "hypothesis" | "thread"
    subject_id: UUID
    outcome_type: str           # "delivery" | "feedback" | "prediction_registered" | "prediction_check" | ...
    expected: JSON | null       # for prediction outcomes; see below
    observation_snapshot_ref: str | null
    observation_hash: str | null
    observed_at: datetime | null
    recorded_by_task_id: UUID
```

An Outcome is an observation, not an interpretation. The subject is polymorphic (mirroring EvidenceLink) so a `prediction_check` can name the exact Hypothesis it verifies.

Predictions are recorded as **two Outcomes** (ADR-0013): `prediction_registered` — committed before the result is known, with `expected` filled and observation fields null (nullable for this type only) — and `prediction_check`, whose observation is filled and whose `expected.registered_outcome_id` names the registration. The `expected` schema for registration:

```json
{
  "resolution_condition": "string — what observation resolves the check",
  "check_by": "datetime — deadline after which the check is overdue",
  "predicted_band": "low | moderate | high"
}
```

External textual material should be ingested as a Signal where possible; manual observations are stored immutably and attributed to the recording Task.

### `Evaluation`

```python
Evaluation
    id: UUID
    team_id: UUID
    outcome_id: UUID
    subject_kind: str           # "task" | "artifact" | "hypothesis" | "knowledge_item"
    subject_id: UUID
    conclusion: str             # "worked" | "mixed" | "failed" | "inconclusive"
    findings: JSON
    evaluator_kind: str         # "rule" | "human" | "model"
    status: str                 # "proposed" | "recorded" | "rejected"
    created_at: datetime
    created_by_task_id: UUID
```

An Evaluation is not an oracle: a model-generated Evaluation is a Proposal until validated and recorded. Evaluations may carry their own EvidenceLinks (`subject_kind="evaluation"`), citing immutable Outcomes, Signals, Artifacts, or Consultation answers.

### `KnowledgeItem`

```python
KnowledgeItem
    id: UUID
    team_id: UUID
    kind: str                   # "practice" | "pattern" | "method" | "playbook"
    title: str
    statement: str
    body: str
    status: str                 # "active" | "needs_review" | "retired"
    confidence: str             # "low" | "moderate" | "high"
    version: int
    last_validated_at: datetime
    review_after: datetime | null
    embedding: vector
    embedding_model: str
    origin_learning_change_id: UUID
    created_at: datetime
    updated_at: datetime
```

Team-level; may apply across many Threads. Never created automatically from a repeated Hypothesis (INV-12).

### `LearningChange`

```python
LearningChange
    id: UUID
    team_id: UUID
    basis_kind: str             # "evaluation" | "manual_seed"
    basis_id: UUID | null       # Evaluation id when basis_kind="evaluation"
    target_kind: str            # "knowledge_item" | "team_policy"
    target_id: UUID | null      # null only for create operations
    operation: str              # "create" | "revise" | "retire"
    proposed_state: JSON
    previous_state: JSON | null
    committed_state: JSON | null
    status: str                 # "proposed" | "accepted" | "rejected"
    proposed_by_task_id: UUID
    committed_by_task_id: UUID | null
    created_at: datetime
    committed_at: datetime | null
```

Agents may propose; only the commit path (`approve_learning_change` or `seed_knowledge`) may produce `accepted`. Accepted changes create a new version; previous versions remain auditable via `previous_state`.

### `TeamDraft`

```python
TeamDraft
    id: UUID
    team_id: UUID
    revision: int
    status: str                 # "draft" | "approved" | "superseded" | "discarded"
    subject_brief_snapshot_ref: str   # the operator's description, immutable
    config: JSON                # the proposed configuration (readable copy)
    config_snapshot_ref: str    # the configuration snapshot (integrity authority)
    config_hash: str
    advisor_notes: JSON         # rationale citing the sample material
    created_by_task_id: UUID
    created_at: datetime
```

A proposed team configuration produced by the setup advisor (flow F7). The approved config snapshot is the Team's birth certificate — auditable forever, and itself evaluable (advisor quality is learnable team memory).

### `Task`

```python
Task
    id: UUID
    team_id: UUID
    task_type: str              # see docs/tasks.md for the full v1 list
    thread_id: UUID | null
    input_refs: JSON
    allowed_tools: str[]
    allowed_writes: str[]       # validated against the per-type scope matrix
    policy_version: int
    status: str                 # "pending" | "running" | "done" | "failed"
    attempt_count: int
    budget: { "max_tool_calls": int, "max_cost_usd": float, "deadline_seconds": int }
    created_at: datetime
    completed_at: datetime | null
```

`allowed_writes` is enforced by application code at commit (INV-14) for worker-proposed business/domain writes. The `docs/tasks.md` scope matrix also marks bounded Kernel-managed Task lifecycle, explicitly permitted enqueue, and companion effects (`K`), including Task-attributed Events and task-specific Snapshots; these are application-authored and do not grant workers direct write access. Task types include manual Operator types, so **every durable write traces to a Task** — operator seeding, outcome recording, expert updates, consultation answers, approvals, and team setup included.

### `Trigger`

```python
Trigger
    id: UUID
    team_id: UUID
    thread_id: UUID | null
    trigger_type: str           # "threshold" | "scheduled" | "manual"
    condition: JSON             # trigger_type-specific
    schedule: JSON | null       # for scheduled triggers: interval or cron expression
    task_type: str              # Task type to create when fired (e.g., "render_output")
    last_fired_at: datetime | null
    next_fire_at: datetime | null
    status: str                 # "active" | "retired"
```

Triggers create Tasks; they never mutate world memory or publish output directly. Recurring scheduled triggers update `last_fired_at` / `next_fire_at` on each firing.

### `Event`

```python
Event
    id: UUID
    task_id: UUID               # non-null: every Event traces to a Task
    type: str
    payload: JSON
    created_at: datetime
```

Events cover, at minimum: hypothesis rejected/superseded, confidence changed, disposition recorded, outcome recorded, evaluation recorded/rejected, learning change proposed/accepted/rejected, policy version activated, decay applied, trigger fired, consultation requested/answered/withdrawn/expired, team created/activated, draft proposed/approved/discarded, commit rejected (with reason). Events are an audit trail and idempotency substrate, not a substitute for current entity state. Every Event is written by application code under the Event (K) scope of its Task type; workers cannot write arbitrary Events or choose their Task attribution. Operator identity is recorded in the payload of Events caused by manual tasks.

## 4. State machines

Transitions not listed are forbidden. Every transition emits an Event (INV-13).

### Task

| From | Event | To | Notes |
|---|---|---|---|
| — | created by Trigger, schedule, Task enqueue, or API | `pending` | |
| `pending` | worker picks up | `running` | attempt count incremented |
| `running` | success | `done` | `completed_at` set |
| `running` | error, retries remain | `pending` | arq retry; re-execution must be idempotent |
| `running` | error, retries exhausted | `failed` | Event; visible to Operator |

### Team

| From | Event | To | Notes |
|---|---|---|---|
| — | `create_team` commit | `configuring` | Shell team; no active policy yet |
| `configuring` | `activate_team` commit | `active` | Policy v1 + starter Threads committed |
| `active` | operator pause | `paused` | |
| `paused` | operator resume | `active` | |
| `active` / `paused` | retire (reason given) | `retired` | terminal |

### Hypothesis

| From | Event | To | Notes |
|---|---|---|---|
| — | created in update or operator_update commit | `active` | |
| `active` | supersede (successor named, reason given) | `superseded` | terminal; Event required |
| `active` | reject (reason given) | `rejected` | terminal; Event required; never caused by decay |

### Thread

| From | Event | To | Notes |
|---|---|---|---|
| — | created (triage, update commit, or `activate_team` starter Threads) | `active` | |
| `active` | all active Hypotheses at `low` for one decay window | `dormant` | set by `apply_decay` |
| `dormant` | matched Signal arrives | `active` | set by triage commit |
| `active` / `dormant` | explicit resolution (reason given) | `resolved` | terminal; via update commit |

### SignalDisposition

| From | Event | To |
|---|---|---|
| — | triage commit | `matched` / `new_thread` / `noise` / `duplicate` / `deferred` |
| `deferred` | update or operator_update commit decides | `matched` / `new_thread` / `noise` / `duplicate` |

All dispositions except `deferred` are terminal.

### Artifact

| From | Event | To | Notes |
|---|---|---|---|
| — | render commit | `draft` | |
| `draft` | delivered (delivery itself recorded as an Outcome) | `delivered` | rejected while a policy-required consultation is open |
| `draft` | discarded with reason | `discarded` | terminal |
| `delivered` | replaced by a newer Artifact | `superseded` | |

### Consultation

| From | Event | To | Notes |
|---|---|---|---|
| — | `request_consultation` commit | `open` | requesting Task has already ended |
| `open` | `answer_consultation` commit | `answered` | terminal; answer snapshot stored first |
| `open` | withdrawn (reason given) | `withdrawn` | terminal |
| `open` | overdue scan past `check_by` | `expired` | terminal; a new Consultation may be opened |

### TeamDraft

| From | Event | To | Notes |
|---|---|---|---|
| — | `configure_team` commit | `draft` | |
| `draft` | `activate_team` commit | `approved` | terminal; config snapshot is the birth certificate |
| `draft` | discarded (reason) | `discarded` | terminal |
| `draft` | newer revision created | `superseded` | |

### Evaluation

| From | Event | To |
|---|---|---|
| — | evaluate commit | `proposed` |
| `proposed` | validation passes | `recorded` |
| `proposed` | validation fails | `rejected` (reason in Event) |

### LearningChange

| From | Event | To |
|---|---|---|
| — | proposal or seed | `proposed` |
| `proposed` | commit service passes all checks | `accepted` |
| `proposed` | rejected by Operator or failed checks | `rejected` (reason in Event) |

### KnowledgeItem

| From | Event | To | Notes |
|---|---|---|---|
| — | accepted `create` LearningChange | `active` | version 1 |
| `active` | `review_after` passed (scheduled review task) | `needs_review` | |
| `needs_review` | validated as current | `active` | `last_validated_at` bumped, version unchanged |
| `needs_review` / `active` | accepted `retire` LearningChange | `retired` | terminal |

### TeamPolicy (version)

| From | Event | To |
|---|---|---|
| — | `activate_team` commit, seed, or accepted policy LearningChange | `active` |
| `active` | newer version activated | `superseded` |

## 5. Core flows

Flow numbers (F1–F8) are cited from `docs/tasks.md` and the walkthrough.

### F1 — Ingestion and triage

1. Scheduler creates an `ingest_source` Task for a configured source (or an Operator submits via `manual_signal_ingest`).
2. Connector fetches; content is hashed. Identical hash at the same origin → fetch-no-change Event, Task done, no new Signal.
3. New content → Snapshot stored first, then Signal row committed atomically (INV-03).
4. A `triage_signal` Task runs domain `match_heuristics` and embedding similarity against the Team's Threads and recent Signals.
5. Dispositions are written: `duplicate` (near-duplicate of a recent Signal per the domain dedup policy), `noise`, `matched` (existing Thread), `deferred` (ambiguous — an update Task is enqueued), or `new_thread` (strong deterministic match; Thread created in the same commit).
6. A disposition matching a dormant Thread reactivates it.

**Commit-time validation:** snapshot stored before Signal commit; hash match; unique `(signal, team)` disposition; task scope.

### F2 — Update

1. `update_thread` Task context is loaded from entities: the Thread, its active Hypotheses, unprocessed/deferred dispositions, relevant active KnowledgeItems (count and selection bounded by policy), current policy (INV-01).
2. The model proposes: EvidenceLinks (verbatim quotes + offsets), Hypothesis creation/transition, ConfidenceChanges, disposition refinements, and a summary update (projection only).
3. Deterministic validation: quote offset + hash against Snapshots (INV-04); stance rule (INV-06); transition legality (INV-07); cause pairing (INV-05); write scope (INV-14).
4. Valid proposals commit atomically as one set; invalid ones reject with Events carrying reasons; a Task whose proposals all fail is marked failed.
5. `last_touched_at` updated only on Hypotheses whose evidence was accepted.
6. Consultation gating: if policy `review.update_gating` is enabled and a required Consultation on the Thread is open, the commit is rejected until answered (default off).

`operator_update` follows the identical flow with a human as the worker (ADR-0021): same context, same proposals, same validation — an unsubstantiated expert hypothesis enters at `low` like anyone else's.

### F3 — Decay

1. Scheduled `apply_decay` Task selects active Hypotheses whose `last_touched_at` is older than the Domain's (or team-overridden) `decay_window`.
2. Band lowered one step per the `decay_action`; ConfidenceChange recorded with `cause_kind="decay"` and the Task reference; Event emitted.
3. When all of a Thread's active Hypotheses have been `low` for one window, the Thread becomes `dormant`.
4. Decay never rejects a Hypothesis and never touches `last_touched_at` (INV-08).

### F4 — Render

1. A Trigger fires (`threshold` / `scheduled` / `manual`) or a request arrives → `render_output` Task.
2. Delivery gating: if a policy-required Consultation on the subject is open, the Task ends after recording an Event and enqueuing `request_consultation`; it does not block inside the Task (ADR-0020).
3. Context: the Thread, active Hypotheses, verified evidence packs (quotes already validated), relevant active KnowledgeItems, current policy, prior Artifacts for continuity.
4. The model drafts prose against the structured evidence pack only (INV-11).
5. Code assembles the citation footer from the EvidenceLinks actually consumed; the model never writes citation metadata (INV-10).
6. A deterministic post-check rejects bodies containing URL/link patterns.
7. Output Snapshot stored and hashed; Artifact row committed. No world-memory writes are permitted to this task type.

### F5 — Outcome and evaluation

1. `record_outcome` (Operator API, or a connector in later milestones) stores the observation Snapshot and hashes it, then commits the Outcome against its subject.
2. Predictions are two Outcomes: `prediction_registered` first — `expected` validated against the fixed schema, committed before the result is known — then `prediction_check`, whose observation names the registration via `expected.registered_outcome_id`.
3. Delivery outcomes on an Artifact with an open policy-required Consultation are rejected by validation.
4. Overdue `prediction_check` registrations (`check_by` passed, no check recorded) and overdue Consultations are surfaced by the scheduler.
5. `evaluate_outcome` reads the Outcome, its subject, and related evidence, then proposes an Evaluation. Validation: Outcome belongs to the same Team; conclusion vocabulary; quote checks on any new links. Mechanical checks (e.g., deadline comparison) may be `evaluator_kind="rule"`.

### F6 — Learning

1. `propose_learning_change` reads one or more recorded Evaluations plus the exact current version of the target KnowledgeItem or TeamPolicy, and proposes a LearningChange: operation, target version, full proposed state, and reason.
2. `approve_learning_change` (Operator) invokes the commit service, which verifies: the Evaluation belongs to the same Team; required evidence exists; the target version has not changed since proposal (optimistic check, INV-13); the proposed state matches the operation and the target's schema; the Task has the required scope; policy changes carry recorded Operator approval (INV-12).
3. On acceptance: new KnowledgeItem or TeamPolicy version created, `previous_state` archived on the LearningChange, Events emitted.
4. `seed_knowledge` is the Operator-only `manual_seed` path, committing immediately with the same checks minus the Evaluation basis.

### F7 — Team setup (the advisor)

1. `create_team` (Operator): a Shell team is created — key, name, Domain choice (a specialized pack or `generalist`), and a freeform **subject brief** stored as an immutable snapshot.
2. The Operator ingests a few sample materials via `manual_signal_ingest`.
3. `configure_team` (model): reads the brief, the samples, and the pack defaults, and produces a **TeamDraft** — proposed mission, vocabulary, candidate sources (marked unverified until first successful fetch), decay rationale, thresholds, starter Threads, policy v1, and `advisor_notes` citing the sample material it reasoned from.
4. `activate_team` (Operator): reviews and edits the draft; if edited, the config is re-snapshotted. Validation: policy against the JSON Schema; vocabulary within the pack's structure; pack-contract conformance; draft revision current. Commit: policy v1, starter Threads (through the normal commit path), Team `configuring → active`, draft `approved`.
5. The approved config snapshot is the Team's birth certificate; advisor quality is evaluable later and itself learnable (ADR-0022).

### F8 — Consultation

1. A policy rule, Trigger, or a finished Task's Event causes `request_consultation`: subject, question, and a context snapshot of exactly what the expert will be shown; status `open`; the requesting Task has already ended (ADR-0020).
2. The scheduler flags Consultations past `check_by` (they become `expired` via the overdue scan).
3. `answer_consultation` (Operator): the answer is stored as an immutable hashed snapshot (plus optional structured verdict); status `answered`; Event with operator identity; optionally enqueues a follow-up update or evaluate Task so the answer enters the loop rather than sitting still.
4. The answer is citable: EvidenceLinks may use `source_kind="consultation"`; verified quotes against the answer snapshot may anchor ConfidenceChanges — INV-04/05/06 apply unchanged.

## 6. Concurrency, idempotency, and failure semantics

- **Optimistic transitions.** Every status change is `UPDATE ... WHERE status = <expected>`. Zero rows affected → conflict → rejection Event with reason; the worker re-proposes against fresh state. This is the hard guarantee (INV-13).
- **Queue-level serialization.** Per-Thread update Tasks are serialized by queue key where the queue supports it. This reduces conflict rate; it is an optimization, never the correctness mechanism.
- **Idempotency.** Commits are recorded as Events keyed by Task id. On retry, a Task detects its own prior commits via these Events and skips completed steps. Snapshot storage is content-addressed, so re-storing is a no-op.
- **Atomicity.** A Task's valid proposals commit all-or-nothing as one set; invalid proposals reject with Events. Partial commits are never made mid-proposal-set.
- **Ingestion races.** `(origin_url, content_hash)` uniqueness resolves concurrent identical fetches; the loser adopts the existing Signal.
- **Budget enforcement.** Tool calls and token costs are attributed to the running Task and counted live; exceeding budget halts the Task with a failure Event. Operator task types carry no model cost and no enforced deadline.
- **Deadline semantics.** `deadline_seconds` is enforced by the worker; a Task past deadline is failed, and its uncommitted proposals are discarded (never partially committed).

## 7. Projections and derived data

Projections are persisted when useful and are never authoritative (INV-11):

- Thread `summary` (+ `summary_basis` recording which Hypotheses produced it);
- embeddings on Signal, Thread, KnowledgeItem;
- dashboards, retrieval packs, cached task context;
- rendered Artifact bodies (durable identity is the Artifact record itself).

Regeneration policy: any Projection can be rebuilt from entities at any time. Embeddings record `embedding_model`; a reindex job regenerates all vectors for a given entity class under one model version so similarity comparisons stay coherent. Prompts and raw model responses may be persisted as execution records but are never read as team state.

## 8. Domain pack boundary

A Domain pack supplies: `signal_sources`, `entity_vocabulary`, `match_heuristics`, `render_templates`, `decay_window`, `decay_action`, and `dedup_policy` — specified concretely in `docs/domains.md`.

The kernel ships the **generalist pack**: manual intake plus a generic RSS connector parameterized by the team's `sources` policy rule; a default vocabulary extendable per team via `vocabulary`; keyword/alias heuristics; standard templates; 14-day decay default overridable via `decay`. It is the setup advisor's fallback for any subject (F7) and the strongest boundary pressure test: an arbitrary team must run with zero per-subject code.

Packs may provide prompt templates and normalizers. Packs **may not**: add kernel tables or columns, bypass validation or invariants, write outside Task scopes, or define decay that rejects Hypotheses. If a second Domain requires kernel changes, the abstraction is revisited rather than patched per-domain.

## 9. Agents and graphs

There are no persistent Agent entities in v1. A worker is identified through Task and Event provenance and may be: an Anthropic model call, a deterministic service, a human Operator, or a future implementation worker.

Graphs (LangGraph, resumable via checkpointer; the database remains the source of truth):

| Graph | Shape |
|---|---|
| Update (F2) | load context → select signals/hypotheses/knowledge → model proposes → deterministic validation → atomic commit |
| Render (F4) | load thread state → build evidence pack → model drafts → code assembles citations → store snapshot |
| Evaluate/Learn (F5–F6) | load Outcome → propose Evaluation → validate/record → propose LearningChange → controlled commit |
| Ingest/Triage (F1) | fetch → hash/dedupe → snapshot → heuristic match → dispositions → enqueue |
| Setup (F7) | load brief + samples + pack defaults → model drafts config → deterministic validation → operator edit/approve → activation commit |

Consultation requests are standalone tasks created by policy, Triggers, or an enqueue from a finished Task — a graph node never waits for a human (ADR-0020).

Model calls are made with the Anthropic SDK directly inside graph nodes; orchestration never delegates writes to the model. The Claude Agent SDK and Claude Managed Agents remain outside the kernel loop, revisitably, for future implementation workers.

## 10. Technology stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12+ | One runtime for kernel, agents, and API |
| Database | PostgreSQL 16 + pgvector | Durable entity store and embedding similarity |
| Migrations | Alembic | Schema changes are explicit and versioned; migrations are the authoritative schema |
| ORM | SQLAlchemy 2.x async | Typed async database access |
| Queue and scheduler | Redis + `arq` | Job dispatch, polling, decay, review, and overdue scans |
| Agent orchestration | LangGraph | Stateful, resumable graphs; execution state only (INV-01) |
| Model calls | Anthropic Python SDK in graph nodes | Model calls remain subordinate to the kernel |
| API | FastAPI | Manual signals, expert updates, outcomes, consultation answers, approvals, team setup, dashboard reads |
| Object storage | Local filesystem in dev, S3-compatible later | Immutable snapshots |
| Metrics | Event-derived counters + task cost accounting, exposed via `/metrics` | v1 observability without new infrastructure |
| Dev environment | Docker Compose | Postgres, Redis, and app together |
| Tests | pytest + pytest-asyncio | Async unit and integration tests; invariant tests in `tests/invariants/` |

Temporal remains deferred until runs genuinely span days with human waits — human-in-the-loop is implemented as waits *between* Tasks (ADR-0020), not suspended workflows.

## 11. Observability

The system is long-running and semi-autonomous; the following are first-class metrics from day one, derived from Events and task accounting:

- Task counts, success/failure rate, and duration by type;
- **validation-rejection rate by rule** — spikes are the earliest warning of prompt regressions (operator rejections tracked separately: human input passing or failing the same gates is itself a signal);
- cost per Task, per Team, per day (against policy budget ceilings);
- undispositioned/deferred Signal backlog and its age;
- confidence band distribution per Thread; decay events per window;
- open Consultations, answer latency, and expired Consultations;
- TeamDrafts by status (advisor approval rate, discard reasons);
- learning proposals by status; policy versions;
- Artifact count vs. recorded Outcomes (delivery-to-outcome lag).

## 12. Scope

### v1 commits to

One persistent Team; Domain packs including the kernel-shipped generalist pack; the setup advisor producing TeamDrafts for arbitrary subjects (F7); immutable Signals and Snapshots; SignalDispositions; Threads with competing Hypotheses maintained by model workers *and* human experts through the same commit kernel (F2, ADR-0021); evidence-linked confidence updates; scheduled decay; Consultations — the loop requesting expert opinion, answers immutable and citable as evidence, delivery gated by policy, `update_gating` reserved behind a policy flag (default off) (F8, ADR-0020); rendered Artifacts with code-assembled citations; manually recorded Outcomes including the two-Outcome prediction flow; Evaluations; controlled LearningChanges; Operator-approved policy changes; a read-only dashboard and approval endpoints.

### Do not build in v1

This list is binding. Do not add these because they seem easy; each deferral is deliberate.

- Temporal or any long-running workflow engine;
- multi-tenant authentication, RBAC UI, or per-operator permissions (single Operator role; identity in Events only);
- sensitive-data handling or redaction hooks — v1 assumes no confidential material is ingested; do not feed material you are not permitted to send to the model API;
- autonomous policy changes (all policy changes are Operator-approved in v1);
- model fine-tuning or weight updates;
- real syndication and advanced independence detection (beyond the dedup policy);
- a general external-action delivery system (no separate `Action` entity);
- a UI beyond the read-only dashboard and approval endpoints;
- push notifications beyond a scheduled digest;
- persistent agent personalities or agent-to-agent chat;
- automatic promotion of repeated Hypotheses into Team practices;
- advisor code generation (the advisor configures teams within the pack contract; it never writes new pack code).

### Future kernel extensions (not v1 — named so they are consciously deferred, not accidentally omitted)

A separate `Action` entity for external side effects with their own retry/idempotency model; full `Expectation`/`Prediction` entities with scoring; richer outcome connectors; cross-team knowledge sharing; formal knowledge-review queues; per-operator identity and permissions; stronger approval and identity records. Conceptually future: autonomous role formation, self-allocating budgets, self-modifying security boundaries, organization-wide reputation, automatic team creation, general reward models.

Repository layout lives in `AGENTS.md`; the build order lives in `PLAN.md`.