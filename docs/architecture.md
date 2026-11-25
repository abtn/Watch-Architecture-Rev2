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

### Knowledge-grounded context and experience distillation (G0 contracts recorded; implementation gated)

The architectural principles and first-slice contracts are recorded in [ADR-0028](decisions/ADR-0028-rag-backed-knowledge-cores.md), [ADR-0029](decisions/ADR-0029-llm-assisted-experience-distillation.md), and [ADR-0030](decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md). This subsection describes the accepted target, not capabilities already implemented, and does not authorize implementation.

Watch should maintain two logically distinct knowledge cores:

- **Domain Knowledge Core:** what the Team knows about the watched subject, grounded in source Snapshots, Signals, Threads, Hypotheses, EvidenceLinks, dispositions, and other accepted canonical subject records.
- **Team Experience Core:** what the Team has learned by performing work, expressed as accepted, versioned practices, patterns, methods, and playbooks supported by Outcomes, Evaluations, and evidence.

A per-task **Context** is a derived and bounded selection across those cores plus relevant current state, Objective, TeamPolicy constraints, and provenance. RAG retrieves candidate records; application code resolves them to current canonical state and enforces Team/domain scope, access, lifecycle status, and source integrity before the records are used. The two logical cores may share retrieval infrastructure, but retrieval must preserve their different meaning and permissions.

The intended cycle is:

Domain Knowledge Core + accepted Team Experience Core → RAG retrieval → bounded, traceable Task Context → LLM proposal → application validation and ordinary Task execution → durable evidence and Outcome → Evaluation and LLM-proposed abstraction → authorized learning commit → accepted Team Experience Core → refreshed retrieval projection.

Embedding vectors, summaries, rankings, and indexes are projections, not authority (INV-11). A vector match does not prove a claim. Immutable Snapshots, quote/hash validation, provenance, competing evidence, current record status, and existing commit gates remain in force. Distillation is abstraction from concrete experience, not transcript retention or automatic learning from a single success. Model output cannot directly alter Team memory or TeamPolicy (INV-12).

### Human participation

Humans enter the loop through three channels, all of which pass the same validation gates (INV-15):

| Channel | Mechanism | Effect |
|---|---|---|
| Human as worker | `operator_update` Task | RW-2 implements the deterministic human path for Hypothesis creation/transitions, EvidenceLinks, and evidence-caused ConfidenceChanges through the shared proposal/commit validation contract; model-driven `update_thread` remains RW-3 |
| Loop requests opinion | `Consultation` + `request_consultation` / `answer_consultation` | The answer is an immutable hashed snapshot, citable as evidence (`source_kind="consultation"`); waiting happens between Tasks, never inside one (ADR-0020) |
| Human administers | Manual Operator Task types, created through a host-invoked in-repository application adapter | The host authenticates and authorizes the Operator, then passes a trusted principal context; Watch creates an ordinary Task and applies the same scope/commit gates. No separate deployed Watch API/CLI or Watch-owned authentication system is implied (ADR-0011). R6-F Checkpoint 3 implements `approve_learning_change`; RW-2 adds `operator_update` through the same boundary. |

### Task creation authority — accepted D1 boundary (2026-11-24)

The application **Control Room is the single authority permitted to create and persist Tasks**. Host-facing adapters, manual Operator entrypoints, triggers, and feature-specific services may request work, but they delegate to a named Control Room operation. Workers, models, ingestion code, and domain-feature modules do not create Tasks directly and must not introduce parallel Task factories.

Control Room is the logical application boundary/owner in this decision; this does not claim that a dedicated Control Room module or service already exists in the current repository. Existing Task-creation paths must be represented as Control Room operations, but this decision alone does not authorize refactoring existing RW-3 code.

Task creation and Task execution remain separate responsibilities: Control Room validates the request and creates/resolves the durable Task and request provenance; TaskRuntime remains the sole authority for admission, attempts, retry, interruption, recovery, and finalization; Kernel/application commit paths validate and persist permitted business changes.

For RW4-2 triage, only Teams whose persisted state is exactly `active` are eligible. Production host authentication is a required prerequisite before production use and is scheduled after the R8 test; the repository does not currently prove end-to-end host authentication. RW4-2 URL normalization is also deferred until after the R8 test; exact persisted URL/source matching remains the current rule. The proposed later minimum treats DNS hostname case as insignificant while preserving scheme, port, path, query, fragment, and trailing-slash distinctions. See the [RW4-2 D1 decision](development/rw-4-2-decision-and-specification-draft.md#3-d1--trusted-host-invocation).

## 3. Entity reference

These sketches are narrative. **Migrations are the authoritative schema**; when this section and a migration disagree, the migration wins and this section is a bug.

### RW implementation state — historical post-B6 source audit

> **Historical baseline only:** this table describes the static source audit at post-B6 commit `91169b4931e48cb7b2803ed2066ec365f563a0ea`. It predates RW-1 through RW-3 implementation and must not be read as current implementation status. Current milestone status is in `PLAN.md`; the current RW-4 readiness baseline is [the RW-4 readiness and delivery plan](development/rw-4-readiness-and-delivery-plan.md). The original audit did not run tests or Alembic commands.

| Entity / flow | Implementation state | Evidence boundary |
|---|---|---|
| Signal | **Implemented — ingestion only** | ORM model and deterministic ingestion exist. This does not implement triage. |
| SignalDisposition | **Specified; not implemented** | No ORM model, triage service, or commit path in the audited source tree. |
| Thread | **Specified; not implemented** | No ORM model, repository/service, or worker in the audited source tree. |
| Hypothesis | **Specified; not implemented** | No ORM model in the audited baseline. |
| EvidenceLink | **Partial — historical audit** | This audit's Evaluation-only description is obsolete. RW-1 added typed Evaluation/Hypothesis subject references and Task provenance; Signal/Outcome are usable sources, while Artifact/Consultation remain staged until their canonical entities and validation paths exist. See `docs/tasks.md` and current migrations/models. |
| ConfidenceChange | **Specified; not implemented** | No ORM model in the audited baseline. |
| Artifact | **Specified; not implemented** | No ORM entity or rendering worker/path in the audited source tree. |
| Consultation | **Specified; not implemented** | Accepted ADR/specification exists; no ORM entity or request/answer Task path in the audited source tree. |
| F1 — ingestion and triage | **Partial** | Signal ingestion exists; triage, dispositions, and Thread matching are not implemented. |
| F2 — update / operator_update | **Partial** | RW-2 deterministic Operator commit path is accepted. RW3.1 adds host-authorized `update_thread` Task creation and bounded Context assembly; no model worker, provider, or model commit path exists yet. |
| F3 — decay / apply_decay | **Specified; not implemented** | Task contract exists; no deterministic decay service/commit path was found. |
| F4 — render / Artifact output | **Specified; not implemented** | Task contract exists; no render implementation path was found. |
| F8 — Consultation | **Specified; not implemented** | Accepted ADR/specification exists; Consultation entity and request/answer Task paths are absent. |

A Task type string in an Event-scope allow-list is not evidence that the Task implementation exists. The Task specifications below describe intended contracts; code, migrations, and tests establish implementation.


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
| `review` | what requires Operator approval; consultation requirements before delivery; `update_gating` flag (default off); and, after a forward rules-schema revision, optional `knowledge_item_interval_days` for Team Experience review scheduling |
| `knowledge_selection` | how many and which kinds of KnowledgeItems are retrieved into task context |
| `thresholds` | Trigger thresholds (e.g., "render when any hypothesis reaches high") |
| `budgets` | Team-level ceilings: per-day task count, per-day cost (aggregate limits; per-Task budgets are set at Task creation) |
| `vocabulary` | team-specific entity keys/values within the pack's default structure (generalist teams especially) |
| `sources` | per-team signal source list for parameterized connectors (e.g., generic RSS); advisor-suggested sources are unverified until first successful fetch |
| `decay` | per-team decay window/action override within pack bounds; the never-reject rule is not overridable |
| `preferences` | Domain-appropriate operating preferences within vocabulary |

Policy is not a security boundary; tool access and write permissions are enforced by application code. Initial policy is committed at `activate_team` or seeded explicitly (`seed_knowledge`). All policy changes in v1 require Operator approval (INV-12).

**RW-3 Task policy pinning (approved design; Task creator implementation in RW3.1):** TeamPolicy versions are append-only and immutable by application contract; the current schema does not enforce row immutability. There is no active-version pointer; the highest version for a Team is current. A new `update_thread` Task resolves Team from its target Thread, locks Team `FOR UPDATE`, locks/revalidates the Thread, then selects the highest TeamPolicy version with `FOR SHARE`. The selected newest version must pass its supported schema and existing `update_thread`-relevant rule validation; invalid newest policy fails closed without fallback. Task and request Event store the same version atomically. A replay or running Task uses its original pinned historical version even after a newer version is published. Any future publisher must acquire the same Team `FOR UPDATE` lock before appending a version, so PostgreSQL serializes publication against Task creation. The current repository has no production TeamPolicy publishing service; this paragraph specifies a required future integration contract, not an implemented path. `core/policy.py` currently provides narrow daily-quota and D7 review-interval parsers, not a universal TeamPolicy rules-schema validator. RW-3 must validate the supported schema version and rules it actually consumes; new policy vocabulary requires a separate decision. RW-3 does not add an active pointer, publisher, database immutability guard, or migration.

**RW-3 Task envelope and budget (approved design; RW3.1–RW3.4 implementation merged):** the new `update_thread` Task is created `pending` with zero attempts, three maximum starts, null Objective/Plan/PlanAction links, the target Team/Thread and immutable policy pin, and exact ordered write scope `[EvidenceLink, Hypothesis, ConfidenceChange]`. Its exact budget is zero tool calls, `$0.02` cumulative generation cost across all attempts, and a 45-second absolute execution deadline. The existing Cloudflare model/rate card is the fixed compatibility and budget-calculation baseline; its 32,000-token context, 1,024-token output cap, one non-streaming request per attempt, and no adapter retries remain the constraints if separately authorized. ADR-0031 authorizes Cloudflare for R6-E only; live RW-3 provider calls require a separate explicit provider-authorization decision. Until then, use a deterministic fake provider. Provider timeout is at most 30 seconds. The existing cost service receives only a narrow `update_thread` operation. The worker enforces the absolute deadline from successful TaskRuntime admission; provider timeout is capped at 30 seconds and remaining Task time, while the existing 60-second interrupted-recovery threshold remains unchanged. The integrated implementation also bounds DNS resolver concurrency and fails closed on receipt-only recovery after expiry. The exact envelope and proof requirements are in [the Task specification](tasks.md) and [RW-3 design §10.4.2](development/rw-3-design-and-acceptance.md#1042-task-shape-generation-budget-and-deadline). RW3.1–RW3.4 implementation is merged and exact-head verified without a schema change or migration. PR #167 specifically preserves already-committed business writes when a committed/rejected marker's Context tuple is corrupt, while validating stable Task/Team/attempt/model-worker identity and terminalizing the recovery failure without replay. Formal RW3.4 Operator acceptance remains pending. The repository still has no production host composition root or TeamPolicy publisher; end-to-end host authentication and publisher integration are not proven. Live provider calls remain unauthorized; deterministic fakes only.

**D7 — Knowledge review scheduling (resolved 2026-11-02):** `review.knowledge_item_interval_days` is an optional positive integer, with no default. It may be introduced only by a forward revision of the TeamPolicy rules JSON Schema; do not add it in place to the fixed v1 vocabulary. Existing policy versions without the key mean no review schedule. For a KnowledgeItem accepted by an `approve_learning_change` Task, application code reads the TeamPolicy row identified by that Task's pinned `(team_id, policy_version)`. A valid configured interval sets `review_after = committed_at + timedelta(days=N)` using timezone-aware UTC timestamps and 24-hour days. An absent key sets `review_after = NULL`; an explicitly present invalid value (including a boolean or non-positive integer) is a policy validation failure, not a fallback to NULL. A newer TeamPolicy version affects only later approval Tasks; it never rewrites existing KnowledgeItem dates. D7 does not authorize a TeamPolicy write path or retroactive date backfill. The current ORM does not expose the conceptual `schema_version` field shown above, so implementation must reconcile the actual TeamPolicy model/migration with the versioned rules-schema contract before accepting the new key.

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

Immutable. Current ingestion uniqueness on `(origin_url, content_hash)` makes an identical re-fetch from the same origin reuse its Signal. The accepted D4.1 rule is broader but Team-scoped: exact raw `content_hash` equality within one Team's intake history is a duplicate regardless of origin; equal hashes across Teams are not duplicates. D4.1a makes the first successfully committed Team/hash association canonical, with database arbitration for concurrent first arrivals. This broader Team/hash canonical association is not implemented by the current origin-scoped ingestion uniqueness; Signals are not Team-owned and Team association is represented through ingestion Events. A reviewed persistence design and real PostgreSQL proof remain required before RW4-3. Near-duplicate and semantic duplicate classification are excluded.

### `SignalDisposition`

> **Accepted business contract; physical schema not implemented.** D5.1–D5.4 were accepted on 2026-11-25. This remains a conceptual field sketch, not an approved physical schema. V1 values are only `matched`, `duplicate`, and `deferred`; there is no `new_thread`, `noise`, or `updated_at`. See the [RW-4 readiness and delivery plan](development/rw-4-readiness-and-delivery-plan.md) and [D5 decision record](https://github.com/abtn/Watch-Architecture-Rev2/issues/193).

```python
SignalDisposition
    id: UUID
    signal_id: UUID
    team_id: UUID
    thread_id: UUID | null      # required only for matched
    duplicate_of_signal_id: UUID | null  # required only for duplicate
    disposition: str            # "matched" | "duplicate" | "deferred"
    reason_code: str | null      # required only for deferred; stable D5.3 code
    decided_by_task_id: UUID    # required for every disposition
    created_at: datetime        # immutable, database-assigned
    # no updated_at: dispositions are immutable
```

Accepted D5 uniqueness scope is one row per `(signal_id, team_id)`; this is not implemented. The only v1 values are `matched`, `duplicate`, and terminal `deferred`. The accepted reference matrix makes `thread_id` required only for matched, `duplicate_of_signal_id` required only for duplicate, `reason_code` required only for deferred, and `decided_by_task_id` required for all. Deferred reason codes are `no_eligible_thread`, `ambiguous_thread_match`, `insufficient_evidence`, `no_compatible_evidence`, `evidence_limit_exceeded`, and `dormant_thread_requires_reactivation`. Every row is immutable and DB-timestamped; there is no `updated_at`. A v1 `matched` disposition may reference an active Thread directly, or a dormant Thread only under accepted D6 when the same TaskRuntime-owned transaction reactivates it and records the immutable `thread_reactivated` Event. Until separately authorized RW4-5 implementation and proof, dormant candidates continue to defer with `dormant_thread_requires_reactivation`. Cross-record Team/domain/canonical-Signal/Task consistency requires a reviewed physical design; simple foreign keys alone do not prove those relationships. The multi-Team identity principle remains: the same Signal may receive separate Team-scoped decisions. **RW4-1B Decision 7 is accepted:** `matched`, `duplicate`, and `deferred` must become available together at one write-enable point, only after the D1 Control Room creator/caller-authorization boundary and D2 Task identity/FK are proven; RW-5 Task → Team → Thread → sorted Hypothesis serialization, Team revision, and all `update_thread`/`operator_update`/`apply_decay` and any Thread status/domain writer retrofits pass real PostgreSQL interleavings; D4.1a canonical arbitration and D4.2 matcher evidence and durable-receipt closure/D4b actual pins, including receipt schema/uniqueness/payload bounds and atomic receipt-plus-finalization recovery proof (recommended same transaction; if a separate receipt transaction is selected, its Team-revision fence and stale-receipt TaskRuntime mapping must also be accepted) pass; RW4-1 physical provenance/role/immutability proof passes; D3/D5 TaskRuntime atomicity/exact replay passes; and integrated independent review plus separate implementation authorization are complete. Production host authentication remains mandatory before production use. The physical design and implementation remain separately gated; no partial rollout is permitted.

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
    # The following are obsolete conceptual target fields, not implemented
    # canonical Thread columns or an approved RW-4 prerequisite:
    summary: str                # unimplemented projection concept
    summary_basis: JSON         # unimplemented projection concept
    entities: JSON              # unimplemented projection concept
    embedding: vector           # unimplemented projection concept
    embedding_model: str        # unimplemented projection concept
```

`summary`, `summary_basis`, `entities`, `embedding`, and `embedding_model` above are historical conceptual target fields only; the current Thread model does not implement these projections. PR #176 and the current RW-4 proposal do not authorize adding them. Reconsider only after a source-backed requirement and separate design decision. The implemented Thread fields are the canonical fields actually present in `core/models.py`.

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

For the first R6 slice, the terminal Outcome type is `task_execution` and there is at most one per Task. It records a deterministic terminal observation (result category, relevant Signal/Snapshot references and hashes, terminal attempt, and observation time), not an LLM interpretation. Its immutable observation Snapshot, Outcome row, terminal Task status, and `task_completed`/`task_failed` Event commit atomically. The canonical contract and replay rules are in [ADR-0030](decisions/ADR-0030-r6-bounded-execution-source-safety-outcome.md); this is not yet implemented in the current ORM.

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
    last_validated_at: datetime | null
    review_after: datetime | null
    origin_learning_change_id: UUID
    created_at: datetime
    updated_at: datetime
```

Team-level canonical knowledge; may apply across many Threads. Never created automatically from a repeated Hypothesis (INV-12). Embeddings and chunks are not fields on this canonical record.

### Team Experience projection (Checkpoint 4)

The separate `team_experience_chunks` table is a rebuildable retrieval projection, not canonical knowledge. Each row is tied by composite Team foreign keys to the current source KnowledgeItem and its originating LearningChange, and records item version/content hash, chunk index/text/hash, chunking version, embedding provider/model/revision/configuration/dimensions/space key, and indexed time. The existing `knowledge_chunks.signal_id` projection remains Signal-only Domain Knowledge.

The separate `team_experience_index_state` row records operational publication status (`stale`, `published`, or `ineligible`), canonical item/version/hash/origin, embedding-space key, chunk and attempt counts, last error class, and timestamps. This state is disposable operational metadata; it cannot grant eligibility. Index publication marks it `published` only in the same transaction as complete chunk replacement. Failed embedding/indexing records `stale` and leaves canonical KnowledgeItem/LearningChange unchanged. NULL-dated, due, or non-active items are `ineligible`, have no retrievable chunks, and are excluded regardless of a prior projection. Both retriever and Context assembly require matching publication state and independently revalidate canonical state.

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
| — | created (`activate_team` starter Threads; no automatic RW-4 triage creation in v1) | `active` | |
| `active` | future dormancy transition (not authorized in RW-5 v1) | `dormant` | No current writer; dormant rows may be pre-existing/seeded. |
| `active` / `dormant` | explicit resolution (reason given) | `resolved` | terminal; via update commit |

> **D6 accepted; implementation gated:** RW-5 first-release decay is confidence-only and does not make active Threads dormant; D6 does not authorize a dormancy writer. A dormant Thread may be reactivated only by a valid matched triage decision under the D6 contract. The transition, immutable Task-attributed `thread_reactivated` Event, matched disposition, and TaskRuntime terminal result must commit atomically. `last_updated_at` is unchanged; Team `world_memory_revision` increments under the canonical RW-5 lock protocol. RW4-3 must not reactivate a dormant Thread until the separately authorized RW4-5 implementation and recovery path are proven.

### SignalDisposition

> **D3 lifecycle and D5 disposition semantics accepted 2026-11-25; physical persistence remains gated.** Signal has no lifecycle/status column. Eligibility is derived from canonical Signal/Snapshot integrity and provenance plus active-Team, authorization, and source/domain/policy checks. An existing Team/Signal disposition excludes another v1 decision. If the disposition exists without exactly one valid canonical Task/request Event, replay fails closed without repair or replacement. D3 makes a deferred disposition terminal and immutable in v1; its Task completes successfully as `done`. The disposition, Task attribution/reason, TaskRuntime Outcome, terminal Task status, and terminal Event commit or roll back in one TaskRuntime-owned transaction. Technical execution failure follows TaskRuntime retry/recovery and may end `failed`. D4.1/D4.1a/D4.2/D4.3 are accepted; canonical Team/hash persistence and measured matcher parameters remain evidence gates. D5.1–D5.4 freeze the three-value vocabulary, reference matrix, deferred reason codes, and TaskRuntime-owned terminal evidence. D6 owns dormant reactivation. RW4-1 owns physical persistence and still requires a reviewed design, proof subset, and explicit authorization. RW4-1B Decision 7 requires all three dispositions to be enabled together after every dependency and integrated proof passes; no partial write rollout is permitted.


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
| `active` | UTC `now >= review_after` (`review_knowledge` Task) | `needs_review` | The deterministic Task transition and Task-attributed Event are atomic. Retrieval excludes due items at the exact boundary even before this status update runs. `review_after = NULL` means unscheduled and ineligible for retrieval; it does not mean permanently valid. |
| `needs_review` | separate explicit, validated re-review operation | `active` | `last_validated_at` is updated; the scheduled `review_knowledge` Task never reactivates or extends an item. The re-review operation remains separately specified/authorized. |
| `needs_review` / `active` | accepted `retire` LearningChange | `retired` | terminal |

### TeamPolicy (version)

| From | Event | To |
|---|---|---|
| — | `activate_team` commit, seed, or accepted policy LearningChange | `active` |
| `active` | newer version activated | `superseded` |

## 5. Core flows

Flow numbers (F1–F8) are cited from `docs/tasks.md` and the walkthrough.

### F1 — Ingestion and planned triage

1. The implemented ingestion path creates an `ingest_source` Task for a configured source and commits a canonical Signal/Snapshot, or records fetch-no-change for an identical same-origin fetch. This does not create a triage Task.
2. `triage_signal`, SignalDisposition persistence, matching, and Thread reactivation are **not implemented**.
3. Accepted D4.1/D4.1a use exact raw content-hash equality within one Team regardless of origin, with the first successfully committed Team/hash association as canonical winner; cross-Team and near-duplicate classification are excluded. This canonical association needs a reviewed persistence design and PostgreSQL concurrency proof because current ingestion uniqueness is origin-scoped.
4. Accepted D4.2 uses a read-time EvidenceLink → Hypothesis → Thread profile over same-Team/same-Domain active or dormant candidates (resolved excluded), supports/challenges evidence, verified same-Team Signal/Snapshot/hash provenance, and compatible pinned KnowledgeChunk projections. Under accepted D6, a dormant Thread may receive a v1 `matched` disposition only with same-transaction reactivation and a Task-attributed `thread_reactivated` Event; until RW4-5 implementation is separately authorized and proven, a dormant would-be winner defers with `dormant_thread_requires_reactivation`. Threshold, winner margin, score serialization, candidate/evidence bounds, actual pins, and query cost remain evidence gates; ties/insufficient valid evidence defer, while missing/partial/mismatched/corrupt provenance is a technical/integrity failure.
5. Accepted D4.3 disables automatic Thread creation. No qualifying match, ambiguous/insufficient evidence, or a dormant candidate blocked by the not-yet-implemented RW4-5 path resolves to terminal deferred. No URL/model title fallback. Reactivation is limited by accepted D6 to the same triage Task's atomic matched commit; triage must not create or enqueue `update_thread` Tasks.

**Status and authority:** D1–D6 decisions are accepted, but this is a target-flow summary, not implementation evidence. RW4-1 persistence, RW4-2 creator, RW4-3 matching, and RW4-5 reactivation retain their separate design/proof/authorization gates. See [the RW-4 readiness and delivery plan](development/rw-4-readiness-and-delivery-plan.md).

### F2 — Update

1. The RW-3 `update_thread` Task is bound to one existing Thread by its immutable request and canonical database state; Team and Thread identity never come from model output.
2. Its proposed Context contains the target Thread, all active same-Thread Hypotheses ordered by `(created_at ASC, id ASC)`, every accepted EvidenceLink belonging to those Hypotheses ordered by `(hypothesis_id ASC, created_at ASC, id ASC)` without ranking or discretionary filtering, exact immutable source Snapshot references/content ordered by reference, and only the TeamPolicy version pinned by the immutable Task's `policy_version`. Missing, invalid, inconsistent, or cross-Team policy pins fail closed; never substitute the latest policy. Bound to 8 Hypotheses, 8 EvidenceLinks, 8 unique Snapshots, and 8,000 Unicode characters of evidence text; overflow fails closed rather than silently truncating. Team Experience is excluded from RW-3 because the current Task Context assembler is scoped to `propose_strategy`; SignalDisposition/triage data are excluded and remain RW-4.
3. The model proposes only EvidenceLinks (verbatim quotes + offsets), Hypothesis creation/transition, and ConfidenceChanges. Its exact business `allowed_writes` are `EvidenceLink`, `Hypothesis`, and `ConfidenceChange`; Event/Outcome remain Kernel/TaskRuntime side effects.
4. A narrow host-invoked `create_update_thread_task(principal, request)` operation creates the immutable `update_thread` Task and request Event atomically; the request contains only Thread ID and host idempotency UUID. The trusted host authenticates the Operator and issues the exact `request_update_thread` Team grant; Watch derives Team from the locked Thread and independently validates the typed principal/grant. The Event records canonical `requested_by_operator_id`, bound into the request fingerprint. The repository has no production host composition root, so end-to-end host authentication remains an integration limitation. A separate model-worker adapter consumes that existing Task, receives no Operator principal/`operator_id`, and runs with TaskRuntime admission preceding attempt-specific Context assembly. The existing cost service reserves before provider invocation and reconciles/validates the exact current-attempt charge before business commit. The current RW-2 `WorldMemoryCommitService` is Operator-specific, so RW-3 must reuse its validation/atomic transaction core through a narrow trusted actor seam rather than call the Operator service unchanged. Unknown, unreconciled, or overrun charges cannot authorize business writes.
5. Deterministic validation uses the shared RW-2 commit contract: quote offset + hash against immutable Snapshots (INV-04); stance rule (INV-06); transition legality (INV-07); cause pairing (INV-05); Team/Thread ownership and write scope (INV-14).
6. The model may return at most 8 proposals; the Operator request contract remains unchanged. Valid proposals commit atomically as one accepted set; invalid proposals receive attributable rejection Events; a Task whose proposals are all rejected fails. An explicit empty proposal list is a successful `success_no_change` result only after a durable empty proposal Event and reconciled current-attempt charge are verified; it creates no commit marker or business writes. A non-empty accepted set uses `success_update_thread_committed` only when its durable commit marker, proposal fingerprint, and reconciled charge agree. Parser/schema/authority/count failures are non-retryable TaskRuntime failures without proposal rejection Events; typed domain-invalid proposals use the existing rejection Events. `last_touched_at` changes only on Hypotheses whose evidence was accepted.

The following broader F2 behaviors are not part of the RW-3 contract and remain deferred pending their own Task scope and authorization: SignalDisposition refinement/triage (RW-4), Thread summary/retrieval projections, and Consultation gating until its canonical source and commit contract are established. `operator_update` uses the same proposal and commit-validation contract, but its human-supplied Context is not claimed to be identical to the model worker's assembled Context (ADR-0021). An unsubstantiated expert hypothesis enters at `low` like anyone else's.

### F3 — Decay

1. Scheduled `apply_decay` Task selects active Hypotheses whose `last_touched_at` is older than the Domain's (or team-overridden) `decay_window`.
2. Band lowered one step per the `decay_action`; ConfidenceChange recorded with `cause_kind="decay"` and the Task reference; Event emitted.
3. RW-5 first-release decay does not change `Thread.status`; a future dormancy transition requires a separate accepted design and implementation authorization.
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
| Ingest/Triage (F1) | fetch → hash/dedupe → snapshot → heuristic match → dispositions |
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


### RW-3 design-review clarifications

The proposed model worker uses exhaustive membership for accepted EvidenceLinks attached to active Hypotheses on the target Thread; it does not rank or heuristically filter them. Context uses the immutable Task's pinned policy_version, never a newer policy selected at execution time. Provider results expose validated usage/model metadata and raw completion text before parsing; the raw receipt and exact charge reconciliation are committed in one transaction. The complete typed proposal set is then durably fingerprinted and bound to the receipt, Task attempt, pinned policy, and charge before commit. The shared commit boundary distinguishes the existing canonical Operator principal from an application-defined, Task-attributed model_worker actor without changing RW-2 Operator Event behavior. TaskRuntime recovery resumes from durable receipts/proposals/markers without another provider call for the same attempt. RW-3 terminal success is limited to success_no_change and success_update_thread_committed, both finalized by TaskRuntime.


### RW-3 independent-review contract completion

The model-worker Task is created by a narrow host-invoked application operation modeled on R6-F: a host UUID idempotency key maps through a fixed UUIDv5 namespace to a deterministic Task ID scoped by Team and update_thread. The Task and its update_thread_requested Event commit atomically. A concurrent same-key caller resolves through the Task primary-key conflict, loads the winning Task, and validates/replays its Event without creating another. The versioned Event binds Task/Team/Thread, pinned policy, idempotency-key hash, and request fingerprint. Creation, replay, and pre-provider validation require exactly one valid Event and consistent same-Team Thread/policy state; duplicates or corrupt/missing evidence fail closed. This is an application invariant, not a required partial unique index or migration; consider DB uniqueness only if tests demonstrate a gap in the Task-PK transaction pattern. Strategy, PlanService, Plan materialization, and TaskDispatcher remain unchanged; the worker cannot create or alter the request.

TaskRuntime recovery owns the Task lock and passes its already-open Session, Task, and current attempt to a narrow resume_update_thread_in_session function. That function reads durable receipt/proposal/marker evidence and resumes the same proposal set without provider invocation or a competing transaction. Transient commit failures leave the same proposal resumable; permanent integrity conflicts fail closed with no business writes and a distinct update_thread_recovery_inconsistent marker.

The shared commit core consumes a validated proposal envelope and a closed typed actor union. The RW-2 Operator principal, Event payloads, and terminal validator remain unchanged. RW-3 uses only a fixed application-created model_worker actor attributed to the admitted Task; its accepted/rejected proposal Events and terminal markers carry Task attribution and no operator_id. The model terminal validator is separate and cannot accept Operator Event records.

Proposal identity uses strict typed-model serialization (model_dump(mode="json"), canonical UUID/enum values, preserved proposal-array order, duplicate-key rejection, canonical UTF-8 JSON with the fixed RW-3 domain tag, and SHA-256. A transient persistence failure resumes the same proposal; an all-invalid domain result uses the rejection marker; a permanent integrity/provenance failure uses the inconsistent marker; and a successful mixed batch commits rows, per-proposal Events, and its marker atomically. Full normative schemas and recovery behavior are in [RW-3 design §§10.4–10.8](development/rw-3-design-and-acceptance.md). These remain design requirements; only the RW3.1 Task-creation and bounded-Context slice is currently under implementation.

## RW-3 request identity — Checkpoint 4 approved design

RW-3 uses Team-scoped deterministic Task identity: a dedicated fixed UUIDv5 namespace over canonical Team UUID, update_thread, and canonical idempotency UUID. The R6-F conflict-safe insertion pattern ensures only one request Event is created for the winning Task. Same-Team key reuse for another Thread or requester conflicts; the same key in another Team is a separate identity. Policy advancement alone does not invalidate replay; the original Task policy pin is retained.

The immutable request Event stores canonical issuer/subject requester identity and a SHA-256 idempotency-key hash, never the raw key. Its versioned, domain-separated canonical JSON fingerprint binds Task, Team, Thread, pinned policy, requester, and key hash. Replay validates exactly one Event and the historical policy pin; policy advancement alone does not invalidate replay. Proposal-set identity is separate, attempt/receipt/charge-bound, and uses strict typed canonical serialization.

## Checkpoint 5 — reconciled RW-3 boundary

The RW-3 design, Task envelope, and milestone status have distinct authorities: the RW-3 design plan specifies protocol/recovery, `docs/tasks.md` specifies the Task envelope and write scope, and `PLAN.md` specifies current status and authorization. The reconciled Checkpoint 4 identity contract is Team-scoped; a same-Team/key request with another Thread or requester conflicts, while the same UUID in another Team is a separate identity. Policy advancement alone does not invalidate replay of the original Task. Request and proposal-set fingerprints remain separate. These documentation decisions did not themselves authorize implementation. A separate authorization was granted on 2026-11-19 for RW3.1 only; see PLAN.md for current status.
