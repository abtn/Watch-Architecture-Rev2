# RW4-1A — Current-source and persistence audit

**Status:** Source audit complete; physical schema design remains open.  
**Audited baseline:** `main` at `d2a6f7d4f939a7c18ea00ad6c77574c7b1f63ec3` (PR #197 merge).  
**Scope:** Read-only inspection of current ORM models, ingestion and TaskRuntime paths, migration history, relevant tests, and accepted D3/D5/D6 contracts.  
**Not performed:** No code or schema changes, tests, Alembic execution, database queries, provider calls, or inspection of persistent database rows. This document does not authorize implementation.

## 1. Executive result

RW4-1 can be kept narrow, but the physical design must resolve several relationships that the conceptual D5 field sketch does not settle. The most important constraint is the accepted atomicity rule: a disposition must be inserted through the active SQLAlchemy Session owned by TaskRuntime finalization. The current finalizer owns the correct transaction for terminal Task evidence, but it has no triage-specific disposition input or in-transaction persistence seam.

The audit confirms:

1. `SignalDisposition` has no ORM model, migration, repository/service, or production write path.
2. `Signal` is global rather than Team-owned. Team intake provenance is represented by a Task-attributed `signal_ingested` or `fetch_no_change` Event whose Task supplies `team_id`.
3. Existing Signal uniqueness is global `(origin_url, content_hash)`; it does not implement D4.1/D4.1a's Team-wide exact-hash canonical association across different origins.
4. Existing composite uniqueness on `Task(id, team_id)` and `Thread(id, team_id)` provides useful same-Team FK targets. It does not prove that a Task is the canonical triage Task for the same Signal, or that a Signal belongs to that Team.
5. TaskRuntime already commits the terminal `task_execution` Outcome, terminal Event, Task status, and `completed_at` in one transaction. It must be extended in a triage-specific way; a separately committed disposition would violate D3/D5.
6. D4.1a canonical Team/hash arbitration, the later D2 Task identity migration, and RW-5 locking/revision work must remain separate from the RW4-1 disposition migration unless the Operator explicitly changes the accepted sequence.

**Recommendation:** use RW4-1A as the completed source/integrity audit. Next prepare and review the physical schema, cross-record enforcement strategy, TaskRuntime integration contract, and exact PostgreSQL proof subset. Do not begin implementation until that design is reviewed and the RW4-1 implementation scope is explicitly authorized.

## 2. Current source inventory

| Surface | Current source fact | RW4-1 consequence |
|---|---|---|
| Team | `core/models.py::Team` contains `id`, `domain`, and `status`. It has no `world_memory_revision`; that belongs to the later RW-5 slice. | Do not add RW-5 revision/locking behavior to this migration. |
| Signal | `core/models.py::Signal` contains `id`, `domain`, `source_type`, `origin_url`, `fetched_at`, `content_hash`, and `snapshot_ref`. It has no `team_id` or lifecycle status. | Preserve the global Signal model. Do not add a speculative Signal status or silently make Signal Team-owned. |
| Signal uniqueness | The only Signal business uniqueness constraint is `uq_signals_origin_content_hash` on `(origin_url, content_hash)`. | This is narrower than Team/hash canonical identity. Do not treat it as D4.1a proof. |
| Event | `core/models.py::Event` stores `task_id`, `type`, JSONB `payload`, and `created_at`. It has a Task FK and non-unique `ix_events_task_id_type`; the payload's Signal ID is not a relational FK. | An Event-to-Signal/Team relationship is currently validated from payload and Task context, not guaranteed by the Event schema. |
| Task | `Task` has a Team FK and unique `(id, team_id)`; it currently has no `signal_id` or `identity_version`. | A composite FK can enforce disposition Task/Team agreement. Same-Signal canonical Task agreement still depends on the later accepted D2 Task-schema migration and/or application validation. Do not combine that migration with RW4-1. |
| Thread | `Thread` has unique `(id, team_id)`, a Team FK, `domain`, and status check for active/dormant/resolved. | A composite FK can enforce disposition Thread/Team agreement. Domain and status-at-commit require validation beyond that FK. |
| Outcome | `Outcome` has composite FK `(recorded_by_task_id, team_id)` to Task, and unique `(recorded_by_task_id, outcome_type)`. `task_execution` is constrained to a Task subject. | Reuse this established Task-attribution pattern; do not add a second terminal Outcome or independent disposition Event. |
| KnowledgeChunk | Existing Signal embeddings live in `knowledge_chunks`, with source Snapshot/hash and embedding/chunking pins. | No Thread embedding or new projection is needed for RW4-1 persistence. |
| Snapshot | `core/snapshot_store.py::SnapshotStore` stores immutable content-addressed files outside PostgreSQL. | Snapshot bytes are not part of the DB transaction. Existing behavior permits an unreferenced immutable file if a later DB commit rolls back. |
| Task execution | `core/dispatcher.py` dispatches configured-source `ingest_source` work only. `triage_signal` appearing in an Event-scope allow-list is not a creator, dispatcher, or execution path. | RW4-1 must not expand TaskDispatcher or create automatic post-ingestion triage. |
| Disposition | No `SignalDisposition` ORM model, table, migration, service, or production write path exists. | The D5 representation remains conceptual. |

### 2.1 Signal intake provenance

`core/ingestion.py::IngestionService._commit`:

1. Locks the existing ingestion Task row.
2. Validates that it is a running `ingest_source` Task, checks its Team is active, validates the pinned TeamPolicy/source, and verifies the content hash.
3. Looks up an existing Signal by exact `(origin_url, content_hash)`.
4. On an existing match, writes `fetch_no_change`; otherwise writes the immutable Snapshot, inserts the Signal, and writes `signal_ingested`.
5. Writes the Signal and success Event in the same PostgreSQL transaction.

The success Event payload carries `origin_url`, `source_type`, `content_hash`, `signal_id`, and `snapshot_ref`. The Event's `task_id` points to a Task, and that Task supplies the Team association. This is the current canonical intake path.

Important limitations:

- The Event payload is JSONB and is not protected by a FK to Signal or a DB check tying its Signal ID/hash/Snapshot to the Signal row.
- When an existing same-origin/same-hash Signal is reused, the ingestion write path does not verify that its stored domain equals the current Task Team's domain before recording `fetch_no_change`; the later rule evaluator detects this mismatch, but the ingestion transaction itself can already have committed the Event.
- Event `created_at` is assigned by application code using `datetime.now(timezone.utc)`; it is not a database commit-order watermark.
- `IngestionService._find_task_outcome` returns the first parseable matching success Event; it is not a Team/hash canonical-association registry.
- The ingestion unique constraint arbitrates same-origin/same-hash writes, not same-Team/same-hash writes across origins.

The D4.1a first-successfully-committed Team/hash winner therefore needs its own reviewed database-arbitrated representation and two-session proof. It cannot be inferred from `fetched_at`, Event timestamps, UUID ordering, or the existing origin/hash constraint. Keep that C1/D4.1a engineering gate separate from the disposition table.

There is also a current write-time domain gap: when `_commit` finds an existing Signal by `(origin_url, content_hash)`, both the ordinary `fetch_no_change` path and the `ON CONFLICT` winner path verify the stored bytes/hash but do not compare `Signal.domain` with the current Task Team's `domain` before writing the Team-attributed Event. A same-origin/same-hash Signal first created under a different-domain Team can therefore be associated by a later Team's Event. The existing `IngestSourceRuleEvaluator._signal_from_business_event` does reject that mismatch later (`signal.domain != team.domain`), but that downstream check does not prevent the ingestion Event from being committed. RW4-1 eligibility must independently fail closed on this provenance/domain mismatch. Do not silently change the ingestion path inside this audit; any ingestion correction needs its own bounded scope and proof.

### 2.2 Existing direct Signal writers and fixtures

The production ingestion path is `IngestionService`. `core/embedding_smoke.py` also inserts a temporary Signal directly for a developer-only embedding smoke test and removes it in cleanup; that temporary Signal has no ingestion Event and must not qualify as triage-eligible provenance. Test fixtures also create Signals directly to set up isolated cases.

No triage/disposition writer was found. The direct smoke/fixture inserts are not evidence of a supported production intake path.

## 3. TaskRuntime transaction boundary

`core/task_runtime.py::TaskRuntime.finalize` currently:

1. Validates a typed `TerminalObservation`.
2. Writes its immutable observation Snapshot before opening the DB transaction.
3. Opens `session_factory.begin()` and locks the Task row.
4. Validates the current Task/attempt and any supported task-specific terminal result.
5. Inserts one `task_execution` Outcome.
6. Inserts `task_completed` for a success, or the terminal failure Events for a failure.
7. Sets Task status and `completed_at` (success → `done`; terminal non-success → `failed`).
8. Flushes and commits all DB records together.

This is the correct owner and transaction boundary for D3-C/D5.4. The current implementation does not yet support the required triage write:

- `TerminalObservation.result_category` has no triage success category.
- The observation has no typed disposition ID/value/reference/reason fields.
- `_SUCCESS_CATEGORIES` does not include a triage disposition result.
- `finalize` has no triage-specific call that inserts/validates a disposition in its active Session.
- The existing terminal replay path validates the Outcome and terminal Events, but does not validate a SignalDisposition against the canonical triage request and Task identity.

The design must provide a narrow triage-specific path that persists and validates the disposition inside this same TaskRuntime-owned Session, before the terminal records are committed. It must also validate the already-committed disposition on replay. A generic callback framework is not justified by this audit; prefer the smallest explicit integration that satisfies the accepted contract.

Do not copy the current `LearningCommitService` transaction pattern for this feature. Its documented business decision/Event transaction is separate from TaskRuntime terminalization, whereas D3 requires disposition, Task attribution/reason, Outcome, Task status/completion time, and `task_completed` to commit or roll back together.

The Snapshot file remains outside PostgreSQL atomicity as in the existing TaskRuntime contract. A failed DB transaction may leave an unreferenced immutable observation file; it must not leave a disposition, Outcome, terminal Event, or terminal Task state committed independently.

## 4. Physical integrity requirements exposed by the current schema

The following are requirements for the next design review, not a frozen DDL proposal.

### 4.1 Row-local constraints

The D5 conceptual shape is:

- `id`
- `signal_id`
- `team_id`
- `thread_id` (matched only)
- `duplicate_of_signal_id` (duplicate only)
- `disposition` (`matched`, `duplicate`, `deferred`)
- `reason_code` (deferred only)
- `decided_by_task_id` (required)
- `created_at` (immutable, database-assigned)

The physical design should evaluate:

- Unique one-row-per-`(team_id, signal_id)`.
- A check limiting disposition to the three accepted values.
- A check enforcing the complete D5 reference/nullability matrix.
- A check preventing a duplicate from referencing itself.
- A check constraining deferred reason codes to the six accepted D5.3 values.
- FK from `signal_id` and `duplicate_of_signal_id` to Signal.
- Composite FK `(thread_id, team_id)` to `threads(id, team_id)`.
- Composite FK `(decided_by_task_id, team_id)` to `tasks(id, team_id)`.
- A database-assigned immutable `created_at`; no `updated_at`.
- Indexes for the unique pair and the referencing columns needed by supported lookup/delete behavior.

A simple FK to Signal proves only that the Signal exists. It does not prove that the Signal has intake provenance for this Team, that its domain matches the Team, or that `duplicate_of_signal_id` is the canonical same-Team/same-hash Signal. Likewise, a Thread/Team composite FK proves ownership but not same-domain or active-at-commit status. A Task/Team composite FK proves ownership but not that the Task is the canonical `triage_signal` Task for this Signal.

### 4.2 Cross-record integrity that still needs a design

| Relationship | Existing relational support | Remaining requirement |
|---|---|---|
| Disposition → Signal | Signal PK | Verify canonical intake provenance for the selected Team and Signal; preserve `Signal.domain == Team.domain`. Existing `fetch_no_change` reuse does not enforce this domain comparison at ingestion commit, so disposition eligibility must reject the mismatch. |
| Disposition → Team | Team PK | Ensure the Signal has an accepted intake association with this Team. |
| Disposition → Thread | `threads(id, team_id)` unique target | Verify same Team/domain and eligibility at commit. Do not encode active-only as a permanent FK/check: accepted D6 permits dormant matching only with the later RW4-5 atomic reactivation path. Until RW4-5 is implemented, dormant would-be winners remain deferred. |
| Disposition → duplicate Signal | Signal PK only | Verify same-Team exact hash and canonical-winner identity. The canonical winner needs D4.1a database arbitration; current Event history/timestamps are insufficient to prove first commit. |
| Disposition → Task | `tasks(id, team_id)` unique target | Verify `task_type='triage_signal'`, canonical Task identity, and request Event. The current Task schema has no `signal_id`/identity version; do not add the D2 migration to RW4-1. |
| Signal/Team/Thread domain | Domain columns exist independently | Decide which checks are DB-enforced (for example, a carefully designed relational witness/trigger) and which are transaction-validated. Do not claim ordinary FKs prove domain equality. |

The design should explicitly state which invariants are enforced by PostgreSQL and which are checked by the trusted persistence operation in the same transaction. A statement that “the application validates it” is not enough unless the required rows, locks, isolation assumptions, and race proof are specified. Conversely, do not introduce a new TeamSignal/canonical-hash table inside RW4-1 merely to solve D4.1a without explicitly reviewing the scope and sequencing impact.

### 4.3 Immutability and timestamp

D5 requires immutable disposition rows and a database-assigned `created_at`, with no `updated_at`. Row-local CHECK and UNIQUE constraints do not prevent UPDATE or DELETE. The physical design must choose and prove a narrow DB enforcement mechanism (for example, a table trigger rejecting mutation, or a privilege boundary that prevents mutation for the runtime role). Do not assume the deployed role model without inspecting it.

The exact database timestamp expression remains a physical-design choice. Do not conflate the disposition creation timestamp with RW-5's Task `as_of` watermark or D6's DB-timestamped reactivation Event.

## 5. Migration and compatibility boundary

- The repository's migration files form one linear chain ending at `0019_rw1_world_memory`, down-revision `0018_r7b_lifecycle_null_review_after`.
- The new disposition migration must follow the actual Alembic head when implementation is authorized; do not edit historical migrations or create a second head.
- Migration `0019` demonstrates existing conventions for composite Team FKs, named checks/uniques, and fail-closed data validation. It is a useful style reference, not a reason to copy unrelated migration logic.
- There is no existing disposition table or legacy disposition population to backfill. This is a source-tree observation only; no deployed database rows were inspected.
- Do not combine the disposition migration with the accepted D2 Task identity/request-Event migration, the D4.1a Team/hash canonical-association mechanism, or RW-5 Team revision/lock-helper changes.
- Preserve Signal, Thread, and EvidenceLink semantics. No new Signal Team column, Signal lifecycle status, Thread status/timestamp mutation, EvidenceLink redesign, new Event type, or automatic Task creation is justified by RW4-1A.

## 6. Existing proof and test coverage

| Existing proof | What it establishes | What it does not establish |
|---|---|---|
| `tests/test_ingestion.py::test_database_failure_rolls_back_signal_and_success_event` | Signal and success Event roll back together when Event insertion fails. The immutable Snapshot file remains readable. | SignalDisposition atomicity or TaskRuntime terminalization atomicity. |
| Ingestion duplicate/replay tests | Same-origin/same-hash Signal reuse; same-Task replay; concurrent same-origin ingestion converges. | D4.1a same-Team/same-hash arbitration across different origins. |
| `tests/test_world_memory.py` cross-Team Signal/domain cases | Existing RW-2 EvidenceLink commit validation rejects a foreign Signal/domain reference for an Operator Task. | SignalDisposition reference integrity or canonical duplicate association. |
| `core/embedding_smoke.py` | Developer-only direct Signal insertion and cleanup for embedding API smoke. | A valid ingestion-provenance path. |

No SignalDisposition-specific model, migration, persistence, immutability, replay, or TaskRuntime atomicity tests exist.

## 7. Required RW4-1 proof subset

The physical-design review should freeze a requirement-to-test matrix covering at least:

1. **Migration:** fresh disposable PostgreSQL install from the current head; upgrade from the current head; one Alembic head/current; transactional rollback on injected migration failure; no historical migration edits.
2. **Row checks:** all valid matched/duplicate/deferred reference combinations; every invalid/null combination; only the three accepted values; all six deferred reasons; reject unknown reasons and self-duplicate references.
3. **Uniqueness/isolation:** same Team/Signal pair rejected on second insert; same Signal may have separate dispositions for different Teams; concurrent duplicate pair inserts yield exactly one row on real PostgreSQL.
4. **Foreign keys:** missing Signal/Team/Thread/Task rejected; cross-Team Thread and Task references rejected through composite FKs.
5. **Cross-record validation:** missing or malformed intake Event; wrong Task Team; Signal/Snapshot/hash mismatch; Signal/Team domain mismatch (including a same-origin/same-hash Signal reused by a different-domain Team); Thread domain mismatch; duplicate target not associated with the same Team/hash. Canonical first-writer proof remains a separate D4.1a/C1 requirement.
6. **Task attribution:** only a valid triage Task/request basis may be attributed; prove same-Team Task FK now and same-Signal canonical Task validation when the D2 Task identity fields arrive. Do not add the D2 migration here.
7. **Immutability/timestamp:** UPDATE and DELETE refused by the selected DB mechanism; `created_at` assigned by PostgreSQL and stable; no `updated_at`.
8. **Atomic terminalization:** matched, duplicate, and deferred disposition plus Task attribution/reason, one `task_execution` Outcome, `task_completed`, Task `done`, and `completed_at` commit together. Inject failure after disposition insertion and before finalization; assert no DB record from the bundle survives.
9. **Failure and replay:** technical failure creates no disposition; retry/recovery follows TaskRuntime; committed replay validates the exact disposition and terminal evidence without a second row/Event; inconsistent disposition/Outcome/Task/Event combinations fail closed.
10. **Boundaries:** no mutation to Signal, Thread, or EvidenceLink; no dormant reactivation in RW4-1; no Task creator/dispatcher expansion; no D4.1a canonical-winner implementation hidden in the disposition migration.

All concurrency and constraint proofs must use disposable PostgreSQL, not SQLite or in-memory substitutes. The exact supported PostgreSQL version and actual Alembic behavior must be recorded when the implementation proof is run.

## 8. Recommended next sequence

1. **Resolve the relational enforcement design:** choose how Team intake association, domain equality, duplicate canonical identity, and Task/Signal identity are enforced. Keep the D4.1a canonical-winner mechanism and D2 Task migration as separately scoped dependencies.
2. **Freeze the physical row design:** columns, named constraints, composite FKs, immutability mechanism, timestamp default, and indexes. State exactly which cross-record checks remain transaction-validated.
3. **Freeze the TaskRuntime integration contract:** typed terminal disposition data; one TaskRuntime-owned Session; insert/validate disposition before Outcome/terminal Event; replay validation; no independent transaction; no disposition for technical failure.
4. **Write the focused proof matrix and migration plan:** exact test cases, failure injection points, disposable PostgreSQL interleavings, migration upgrade/rollback expectations, and compatibility boundaries.
5. **Obtain bounded independent design review and explicit Operator authorization.** Only then start RW4-1 implementation. RW4-1A itself authorizes no schema or code changes.

## 9. Explicit non-authorization

RW4-1A is an audit artifact only. It does not authorize:
- SignalDisposition ORM/schema/migration/service implementation;
- TaskRuntime changes;
- triage Task creation, request Events, dispatch, or execution;
- D2 Task identity migration;
- D4.1a Team/hash canonical association or matcher implementation;
- RW-5 locks, Team revision, decay, or writer retrofit;
- RW4-3 matching/commit or RW4-5 dormant reactivation.

The next decision is the physical relational-integrity design and proof subset, not permission to begin implementation.
