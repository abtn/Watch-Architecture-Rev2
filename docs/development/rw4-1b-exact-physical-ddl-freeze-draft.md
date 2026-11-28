# RW4-1B exact physical DDL freeze — review draft

**Status:** Draft proposal for Operator and independent review. This document is not an accepted physical contract and does not authorize implementation.

**Baseline:** PR #221 merged at `c648892e4896113700c8103397be01c11c0d22ed`. The current repository includes D2 migration `0020_rw4_task_identity`; its four-column Task support key is already present. The later SignalDisposition-to-Task composite FK remains a separate migration and gate.

**Purpose:** Turn the accepted logical SignalDisposition and provenance decisions into a concrete PostgreSQL contract, identify the exact boundaries between migrations, and expose any unresolved design questions before SQL/ORM work begins.

**Strict scope:** Physical DDL, ORM, migration, trigger SQL, application runtime, role grants, and database execution remain design-only and are not implemented. The companion F1 audit adds a source inventory and a narrowly scoped regression assertion to the existing PostgreSQL role-isolation test; it does not change runtime privileges or exercise a production host. No TaskRuntime, ingestion, D4.1a, D4.2, RW-5, RW4-2 Stage B, RW4-3, RW4-4, or RW4-5 implementation is included.

---

## 1. Source reconciliation completed

The draft was checked against the current source and accepted design material:

- `core/models.py`: Team, Task, Signal, Event, Outcome mappings and D2 composite Task keys.
- `migrations/versions/0019_rw1_world_memory.py`: Thread table has `uq_threads_id_team`, so the proposed composite Thread/Team FK has a real referenced key.
- `migrations/versions/0020_rw4_task_identity.py`: `tasks.identity_version` is unbounded `VARCHAR`; D2 adds `uq_tasks_id_team_signal_identity` on `(id, team_id, signal_id, identity_version)`.
- `core/ingestion.py`: current intake Event payload has exactly the required five fields: `origin_url`, `source_type`, `content_hash`, `signal_id`, `snapshot_ref`. The writer locks Task `FOR UPDATE`, then Team `FOR SHARE`; it creates `signal_ingested` for a new Signal and `fetch_no_change` for existing/ON-CONFLICT winners. Same-Task prior-outcome replay writes no new Event.
- `scripts/provision_database_roles.py` and `migrations/env.py`: fresh disposable databases can provision owner/migrator/read-only-runtime roles; ordinary Alembic CLI authenticates as `watch_migrator` and assumes `watch_owner`. Runtime remains SELECT-only and no host consumes it.
- `docs/development/rw4-1b-physical-schema-and-integrity-design.md`, the current physical review, and accepted RW4-2 Stage A/D2 decisions.

**Important source facts:** the existing Task composite key and Thread composite key are present; the required SignalDisposition table, marker, provenance triggers, Thread-domain guard, and disposition immutability controls are not present. Source presence is not deployment proof.

## 2. Proposed SignalDisposition table DDL

The following is the proposed exact table contract. The migration should use PostgreSQL UUID, TEXT, unbounded VARCHAR, and TIMESTAMPTZ types as shown; do not introduce a PostgreSQL ENUM.

```sql
CREATE TABLE signal_dispositions (
    id UUID NOT NULL,
    team_id UUID NOT NULL,
    signal_id UUID NOT NULL,
    disposition TEXT NOT NULL,
    thread_id UUID NULL,
    duplicate_of_signal_id UUID NULL,
    reason_code TEXT NULL,
    decided_by_task_id UUID NOT NULL,
    identity_version VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT pk_signal_dispositions
        PRIMARY KEY (id),

    CONSTRAINT uq_signal_dispositions_team_signal
        UNIQUE (team_id, signal_id),

    CONSTRAINT ck_signal_dispositions_disposition
        CHECK (disposition IN ('matched', 'duplicate', 'deferred')),

    CONSTRAINT ck_signal_dispositions_reference_matrix
        CHECK (
            (disposition = 'matched'
                AND thread_id IS NOT NULL
                AND duplicate_of_signal_id IS NULL
                AND reason_code IS NULL)
            OR
            (disposition = 'duplicate'
                AND thread_id IS NULL
                AND duplicate_of_signal_id IS NOT NULL
                AND reason_code IS NULL)
            OR
            (disposition = 'deferred'
                AND thread_id IS NULL
                AND duplicate_of_signal_id IS NULL
                AND reason_code IS NOT NULL)
        ),

    CONSTRAINT ck_signal_dispositions_identity_version
        CHECK (identity_version = 'triage_identity_v1'),

    CONSTRAINT ck_signal_dispositions_not_self_duplicate
        CHECK (
            duplicate_of_signal_id IS NULL
            OR duplicate_of_signal_id <> signal_id
        ),

    CONSTRAINT ck_signal_dispositions_deferred_reason
        CHECK (
            (disposition = 'deferred'
                AND reason_code IS NOT NULL
                AND reason_code IN (
                    'no_eligible_thread',
                    'ambiguous_thread_match',
                    'insufficient_evidence',
                    'no_compatible_evidence',
                    'evidence_limit_exceeded',
                    'dormant_thread_requires_reactivation'
                ))
            OR
            (disposition IN ('matched', 'duplicate')
                AND reason_code IS NULL)
        ),

    CONSTRAINT fk_signal_dispositions_team
        FOREIGN KEY (team_id) REFERENCES teams (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,

    CONSTRAINT fk_signal_dispositions_signal
        FOREIGN KEY (signal_id) REFERENCES signals (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,

    CONSTRAINT fk_signal_dispositions_duplicate_signal
        FOREIGN KEY (duplicate_of_signal_id) REFERENCES signals (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,

    CONSTRAINT fk_signal_dispositions_thread_team
        FOREIGN KEY (thread_id, team_id) REFERENCES threads (id, team_id)
        MATCH SIMPLE
        ON UPDATE RESTRICT ON DELETE RESTRICT
);
```

The Task composite FK is intentionally **not** in this initial table DDL. It is installed only by the separate D2-dependent migration described in §5. No temporary Task-ID-only FK is proposed: the accepted four-column identity FK is the required attribution proof, and runtime INSERT remains withheld until it exists.

All FKs are non-deferrable (PostgreSQL default), with explicit RESTRICT actions. The table has no `updated_at`, no status, no Team/hash uniqueness, and no caller-selected timestamp semantics. IDs remain application-generated UUIDs, consistent with current model conventions.

### 2.1 Supporting indexes

Create these indexes transactionally in the initial migration; do not use `CONCURRENTLY`:

| Name | Exact definition | Reason |
|---|---|---|
| `uq_signal_dispositions_team_signal` | Unique constraint index on `(team_id, signal_id)` | At-most-one Team/Signal decision; Team lookup and Team FK support. |
| `ix_signal_dispositions_signal_id` | B-tree `(signal_id)` | Signal FK and subject identity guard. |
| `ix_signal_dispositions_duplicate_of_signal_id` | B-tree `(duplicate_of_signal_id) WHERE duplicate_of_signal_id IS NOT NULL` | Duplicate-target FK and identity guard. |
| `ix_signal_dispositions_thread_id_team_id` | B-tree `(thread_id, team_id) WHERE thread_id IS NOT NULL` | Composite Thread FK and matched-Thread domain guard. |
| `ix_signal_dispositions_decided_by_task_identity` | B-tree `(decided_by_task_id, team_id, signal_id, identity_version)` | Child-side lookup/support for the later Task composite FK. |

Do not add indexes on `created_at`, `reason_code`, or `disposition` absent a measured query need. The unique constraint already creates its supporting index; do not create a duplicate standalone index.

### 2.2 Timestamp enforcement

Accepted rule: PostgreSQL assigns `created_at` using `clock_timestamp()`; it is insertion time, not commit order.

**Proposed mechanism:** a `BEFORE INSERT FOR EACH ROW` trigger unconditionally sets `NEW.created_at := pg_catalog.clock_timestamp()`. The column is `NOT NULL` and has no default, so an insert that omits it is made valid by the BEFORE trigger; a supplied value is overwritten. This avoids evaluating the clock twice (once in a default and once in a trigger). The SQLAlchemy mapping should mark the value as server-generated (e.g. `FetchedValue`) and must not treat it as a caller-controlled field.

The function is owned by `watch_owner`, uses a fixed trusted search path, and is not directly executable by PUBLIC. It needs no elevated read access; prefer SECURITY INVOKER unless a reviewed implementation demonstrates otherwise.

## 3. Proposed forward-only intake witness DDL

Add exactly:

```sql
ALTER TABLE events
    ADD COLUMN intake_witness_version SMALLINT NULL;

ALTER TABLE events
    ADD CONSTRAINT ck_events_intake_witness_version
    CHECK (
        intake_witness_version IS NULL
        OR intake_witness_version = 1
    ) NOT VALID;
```

No default, no backfill, no legacy scan, and no payload rewrite. The CHECK is deliberately `NOT VALID`: adding an ordinary validated CHECK would scan the existing Events table while the cutover holds ACCESS EXCLUSIVE. Because this is a newly added nullable column with no default, every pre-cutover row reads as NULL by construction; the unvalidated CHECK still enforces NULL-or-1 on every subsequent INSERT or UPDATE. Do not run `VALIDATE CONSTRAINT` in this cutover or as an implicit follow-up; it would perform the historical scan that this design deliberately avoids. Any later request to validate the catalog flag requires a separate maintenance decision. Every pre-cutover Event remains NULL and permanently ineligible as RW4-1 provenance. A malformed legacy Event must not block cutover.

A single `BEFORE INSERT` trigger owns the marker:

- For `signal_ingested` and `fetch_no_change`, ignore/overwrite caller-supplied marker data only after validating the complete intake witness; set marker to integer `1`.
- For all other Event types, reject non-NULL caller-supplied marker values and persist NULL.
- Require the Event payload to be a JSON object with exactly these five keys and no extensions: `origin_url`, `source_type`, `content_hash`, `signal_id`, and `snapshot_ref`. Require every value to be a JSON string and equal the corresponding stored Signal field; reject missing keys, unknown keys, wrong JSON types, and mismatches.
- Require the Task to exist, be `ingest_source`, and be `running`; require its Team to exist and be active; require the Signal to exist; and require Signal.domain = Team.domain.
- Require `signal_id` to be a lowercase canonical hyphenated UUID string. Parse it only after the JSON-type check, then require the original string to equal the parsed UUID's canonical text representation; do not silently normalize uppercase, braces, compact, or otherwise non-canonical input.
- Acquire compatible row locks in exact order Task `FOR SHARE` → Team `FOR SHARE` → Signal `FOR SHARE`. The existing ingestion path already holds Task `FOR UPDATE` and Team `FOR SHARE`; do not upgrade Team to `FOR NO KEY UPDATE`.
- Preserve the current Event payload contract; do not add a new payload key as a substitute for the marker.

The trigger must reject UPDATE/DELETE of either intake Event type and reject type changes into or out of the protected set. It must also prevent marker changes. Runtime is separately denied Event UPDATE/DELETE for all Event types.

**Reuse-path implication:** an existing-Signal `fetch_no_change` or ON-CONFLICT winner whose Signal domain differs from the Task Team will fail the new Event trigger and roll back that ingestion transaction. Same-Task prior-outcome replay creates no Event and cannot manufacture a marker. These are explicit fail-closed boundaries; any desired ingestion behavior change is a separately scoped decision, not an RW4-1 silent fallback.

### 3.1 Required use of the intake witness at triage admission and finalization

The marker is not merely diagnostic metadata. It is the only accepted post-cutover proof that a Signal was associated with a particular Team through a validated intake Event. Because `signals` has no `team_id`, the association is established through the immutable Event → Task relationship:

- Before a triage Task is created, the trusted Control Room admission path must find at least one `signal_ingested` or `fetch_no_change` Event for the requested Signal with `intake_witness_version = 1`, whose immutable ingestion Task has `task_type = 'ingest_source'` and `team_id` equal to the requested Team. The Event's canonical `signal_id` payload must equal the Signal primary key. A legacy Event with a NULL marker never qualifies, even if its payload currently appears valid.
- At the D4.2 receipt transaction and again at business finalization, TaskRuntime must revalidate that same Team/Signal witness for the canonical triage Task. It must also revalidate that the Team is active, that Signal.domain equals Team.domain, and that the exact source origin/source_type and greatest supported immutable TeamPolicy/source scope remain eligible under the accepted lock protocol. The Event trigger's payload checks plus the Event, Task, Signal, and Team immutability guards make the witnessed association stable after it is established.
- The later composite Task FK binds the disposition's `decided_by_task_id`, `team_id`, `signal_id`, and `identity_version` to the exact D2 Task identity. It does not prove that the canonical request Event exists or is valid; TaskRuntime must independently validate exactly one valid `triage_signal_requested` Event and the canonical Task identity on insert and replay, as required by the accepted Stage A contract.
- A Signal with no valid post-cutover witness for the requested Team is ineligible before Task creation; do not create a Task or a deferred disposition for it. If a previously admitted Task later lacks or disagrees with its required witness, treat that as a technical/integrity failure and create no disposition. Missing, partial, mismatched, corrupt, or legacy-only provenance is never a D5 deferred reason.
- The same global Signal may qualify independently for more than one Team, but each Team requires its own marked Event → ingestion Task association. This does not select a canonical Team/hash duplicate; that remains D4.1a.

This is a trusted TaskRuntime/Control Room validation obligation over a database-attested, immutable witness. It must not be reduced to an unprotected application timestamp or a caller-supplied provenance assertion, and it must not be replaced by a new Team/Signal registry in this stage.

## 4. Proposed protected identity and history guards

The table/function/trigger names below are proposed stable names for review. Every guard must reject actual protected-value changes, not harmless no-op assignments, unless stated otherwise.

| Table | Protected operation | Proposed trigger behavior |
|---|---|---|
| `events` | UPDATE/DELETE | Reject when OLD or NEW type is `signal_ingested` or `fetch_no_change`, or either marker is non-NULL. Also reject type transitions into/out of either protected type. |
| `signals` | UPDATE/DELETE | Reject changes/deletion to referenced Signal identity when a marked intake Event or SignalDisposition references it. Protected fields: id, domain, source_type, origin_url, fetched_at, content_hash, snapshot_ref. |
| `tasks` | UPDATE | Reject actual `team_id` or `task_type` changes while a marked intake Event references the Task. Preserve the existing D2 triage-identity immutability trigger unchanged. |
| `teams` | UPDATE OF domain | Reject actual domain changes while a marked intake Event attributed through a Task or any SignalDisposition for the Team depends on the Team domain. |
| `threads` | UPDATE OF domain | Reject an actual domain change only when a matched SignalDisposition references the Thread. No-op assignments and status/title changes remain allowed. |
| `signal_dispositions` | UPDATE/DELETE | Unconditionally reject; disposition history is immutable. |
| `events`, `signals`, `signal_dispositions`, `tasks`, `teams` | TRUNCATE | Unconditionally reject with statement-level BEFORE TRUNCATE triggers. Runtime effective TRUNCATE is revoked on all application data tables, not only these five. |

The Signal guard covers both `signal_id` and `duplicate_of_signal_id` references in SignalDisposition. The duplicate target's same-Team/same-hash canonicality remains D4.1a's responsibility; this FK/guard does not decide the canonical winner.

The Team guard is based on marked intake Events and SignalDisposition rows, not untrusted legacy Events. The Thread-domain guard is narrower and conditional on a matched reference. Its function must be VOLATILE so a READ COMMITTED trigger query after waiting for the Thread row lock observes a concurrently committed matched disposition. Both lock orders require two-session proof.

**TRUNCATE and table-topology proof:** Runtime effective TRUNCATE must be revoked on every application data table, including `knowledge_chunks`, not only the five tables with unconditional rejection triggers. Under the actual runtime role, prove direct TRUNCATE attempts against each protected table fail; prove relevant `TRUNCATE ... CASCADE` paths also fail before any protected history is removed (including a Thread-to-matched-disposition cascade); and verify effective privileges through inherited roles and PUBLIC, not just direct ACL entries. Inspect `pg_partitioned_table` and `pg_inherits` during cutover. The current design expects these five protected tables to be non-partitioned and non-inherited. If that is false, stop unless every directly truncatable leaf has the rejection trigger and every partition attach/create path installs and verifies it before the leaf becomes writable. Include direct-leaf and parent/CASCADE cases in the PostgreSQL proof. The migration/owner role remains outside the application trust boundary and must be restricted to audited migrations/break-glass operations.

Do not freeze Thread.status. It is evaluated at the serialized decision point; later valid status transitions do not invalidate historical disposition or exact replay.

### 4.1 Trigger/function execution model

Proposed trigger/function pairs and execution contract:

| Trigger | Function | Event/timing | Security and visibility |
|---|---|---|---|
| `trg_events_attest_intake_witness` | `watch_attest_intake_witness()` | BEFORE INSERT, row | SECURITY DEFINER; VOLATILE; fixed `pg_catalog` search_path; schema-qualified application tables. |
| `trg_events_protect_intake_witness` | `watch_protect_intake_event()` | BEFORE UPDATE OR DELETE, row | SECURITY INVOKER; reject protected Event/marker mutation. |
| `trg_signals_protect_intake_identity` | `watch_protect_signal_identity()` | BEFORE UPDATE OR DELETE, row | SECURITY INVOKER; SELECT-only cross-table checks. |
| `trg_tasks_protect_intake_identity` | `watch_protect_ingestion_task_identity()` | BEFORE UPDATE, row | SECURITY INVOKER; SELECT-only Event reference check; preserve the separate D2 trigger. |
| `trg_teams_protect_intake_domain` | `watch_protect_team_domain()` | BEFORE UPDATE OF domain, row | SECURITY INVOKER; SELECT-only witness/disposition checks. |
| `trg_threads_protect_matched_domain` | `watch_protect_matched_thread_domain()` | BEFORE UPDATE OF domain, row | SECURITY INVOKER; explicitly VOLATILE for the post-lock READ COMMITTED visibility check. |
| `trg_signal_dispositions_assign_created_at` | `watch_assign_signal_disposition_created_at()` | BEFORE INSERT, row | SECURITY INVOKER; VOLATILE; assign `clock_timestamp()`. |
| `trg_signal_dispositions_immutable` | `watch_reject_signal_disposition_mutation()` | BEFORE UPDATE OR DELETE, row | SECURITY INVOKER; unconditional rejection. |
| `trg_<protected_table>_no_truncate` | `watch_reject_protected_truncate()` | BEFORE TRUNCATE, statement; one trigger on each of the five protected tables | SECURITY INVOKER; unconditional rejection. |

Use small purpose-specific functions rather than a generic integrity framework. The shared TRUNCATE rejection function is intentionally narrow and follows the existing repository pattern; do not build a generic configurable trigger framework.

**Proposed SQLSTATE contract:** row-local CHECK violations and invalid intake payload/state/marker/domain inputs raise `23514` (`check_violation`); a missing Task, Team, or Signal referenced by an intake Event raises `23503` (`foreign_key_violation`); attempts to mutate RW4-1-protected Event/Signal/ingestion-Task/Team/Thread/SignalDisposition history or TRUNCATE protected tables raise `55000` (`object_not_in_prerequisite_state`). The already-merged D2 triage-Task identity trigger remains unchanged and retains its existing `23514` behavior. Native PK/unique/FK constraint errors retain PostgreSQL's native `23505`/`23503` codes. The migration's NOWAIT lock conflict remains native `55P03`; roll back the entire migration transaction and do not translate it into a retry-success response. Tests must assert the SQLSTATE, not only exception text.



**Required security mode for the intake-attestation trigger:** `trg_events_attest_intake_witness` must be `SECURITY DEFINER`, owned by `watch_owner`, with `SET search_path = pg_catalog` and every application-table reference schema-qualified. PostgreSQL requires `UPDATE` privilege (in addition to `SELECT`) for `SELECT ... FOR SHARE`; the trigger must lock Task → Team → Signal, but the runtime role must not receive Signal UPDATE merely to acquire the Signal row lock. The owner function supplies the narrowly scoped lock authority inside the caller's transaction; the row locks remain held through the transaction. Revoke PUBLIC EXECUTE in the same migration transaction. Trigger firing does not require a direct runtime EXECUTE grant.

Other guards that only read protected tables may use `SECURITY INVOKER` if the runtime's audited SELECT grants suffice. The existing Python ingestion path itself also uses Task `FOR UPDATE` and Team `FOR SHARE`, which require UPDATE privilege on at least one column of those tables; F1 must explicitly resolve that pre-existing grant requirement (or a separately reviewed controlled lock helper) without silently granting broad Team/Signal mutation rights. Any other trigger that performs row-locking SELECTs must receive the same privilege/security review. Use `SECURITY DEFINER` only where that elevated operation is actually required, always with a fixed trusted search_path and schema-qualified references. Functions requiring post-wait visibility must be explicitly VOLATILE. No caller-settable GUC, session flag, temporary-table bypass, or replication-role bypass is permitted.

## 5. Migration boundaries and exact lock protocols

### 5.1 Initial RW4-1 cutover migration

One linear Alembic migration from the actual current head. One transaction. The first operation that can wait for existing application access is one ordered statement:

```sql
LOCK TABLE tasks, teams, signals, events, threads
    IN ACCESS EXCLUSIVE MODE NOWAIT;
```

Do not acquire these locks piecemeal and do not prelock at SHARE ROW EXCLUSIVE then upgrade. If NOWAIT fails, roll back the entire migration transaction so every acquired lock is released; retry in a quiet maintenance window.

While all five locks remain held: add the nullable marker and its `NOT VALID` CHECK without scanning Events; create the empty SignalDisposition table and its row-local constraints/indexes; create/attach the marker, immutability, identity, Thread-domain, timestamp, and TRUNCATE guards; set ownership and reviewed grants; verify trigger definitions, role memberships, effective privileges, and protected-table inventory; then commit. No full-table historical Event scan. No legacy update/backfill.

**Downgrade:** unconditional refusal after the forward-only cutover is committed. A migration failure before commit relies on PostgreSQL transactional rollback; there is no destructive post-commit downgrade.

### 5.2 Later D2-dependent Task FK migration

Keep separate from the initial cutover. Install only:

`fk_signal_dispositions_task_identity`:
`(decided_by_task_id, team_id, signal_id, identity_version) → tasks(id, team_id, signal_id, identity_version)`.

Use the accepted single ordered `SHARE ROW EXCLUSIVE NOWAIT` preflight lock on `tasks, events, signal_dispositions`, with locked preflight and transactional rollback. Verify the exact D2 support key exists. Require no pre-gate triage/disposition history and install the FK without a temporary Task-ID-only substitute. The FK is non-deferrable and uses `ON UPDATE RESTRICT ON DELETE RESTRICT`, consistent with every other SignalDisposition FK. Runtime disposition INSERT remains revoked until this migration and every Decision 7 prerequisite are independently verified.

## 6. Role/ownership contract — proposed, not yet grant-ready

- `watch_owner` (NOLOGIN) owns protected tables, indexes/constraints, and trigger functions.
- `watch_migrator` (LOGIN/NOINHERIT) is used only for reviewed Alembic CLI migrations and explicitly assumes `watch_owner`.
- `watch_runtime` (LOGIN) is neither owner nor member (directly/transitively) of owner/migrator or any role able to assume them; no superuser, CREATEROLE, CREATEDB, REPLICATION, or BYPASSRLS.
- Runtime cannot alter schema objects, triggers/functions, grants, ownership, or `session_replication_role`.
- Runtime has no effective TRUNCATE privilege on any application table, including PUBLIC/inherited paths. Statement-level triggers remain defense in depth on the five protected tables.
- Events: runtime SELECT/INSERT only; no UPDATE/DELETE.
- SignalDisposition: SELECT only at schema creation. SELECT/INSERT is a future write-enable grant only after the Task composite FK and every Decision 7 prerequisite; never UPDATE/DELETE/TRUNCATE.
- Other table/column grants must be derived from a complete supported-writer inventory. Do not copy a speculative blanket grant matrix into the migration while F1/F2 remain open.

The current bootstrap proves the role foundation only. It does not yet provision the complete future application DML matrix, establish a host runtime consumer, or close F1/F2.

### 6.1 External credential cutover is a separate deployment gate

The database migration and its table locks cannot atomically change an external application's connection string or revoke credentials held by already-running processes. Therefore Option A also requires an explicit stopped-writer credential cutover before any deployment that relies on these protections:

1. Provision the NOLOGIN owner, distinct migrator, and least-privilege runtime roles; configure the intended runtime DSN, but do not restart application writers yet.
2. Stop and drain every application process and worker, and terminate/drain every old application connection using the bootstrap superuser, table owner, or migration credential. No application writer may remain on a bypass-capable identity.
3. Run the cutover migration only as the reviewed migrator assuming `watch_owner`, with no application writers active. The migration verifies ownership, role membership, effective privileges, trigger inventory, and protected-table/partition topology before commit.
4. After commit, restart application processes only with the runtime DSN. Verify active application sessions through PostgreSQL session/role inspection (including `pg_stat_activity`) and verify that none uses the bootstrap superuser, `watch_owner`, or `watch_migrator`; repeat effective privilege and role-membership checks.
5. If the deployment cannot stop/drain writers and prove the post-cutover runtime identity, Option A is not acceptable for that deployment. Stop and return for a separately reviewed Option B relational-witness design; do not treat the migration's ACCESS EXCLUSIVE lock as a substitute for credential cutover.

This is an external deployment prerequisite, not something the current disposable-CI role tests or the migration can prove on their own. The repository currently has no production host/runtime DSN consumer, so F1 remains open.

### 6.2 Current source lock/writer inventory — partial evidence only

The current `watch_runtime` bootstrap role is SELECT-only, and the role tests prove table-level INSERT/UPDATE/DELETE/TRUNCATE denial. That is a privilege-isolation proof, not proof that the existing application can run under this identity. The current test uses `has_table_privilege(..., 'UPDATE')`; this does not detect a future column-level UPDATE grant. Before introducing any column-level grants, extend the test to assert `NOT has_any_column_privilege('watch_runtime', relation, 'UPDATE')` for relations expected to remain lock-helper-only, and enumerate `has_column_privilege` for every explicitly granted writer column. PostgreSQL requires UPDATE privilege on at least one column of each table used by a row-locking SELECT; the current source has existing `FOR UPDATE`/`FOR SHARE` call sites. Examples include:

- `core/ingestion.py`: Task `FOR UPDATE`, then Team `FOR SHARE`.
- `core/task_runtime.py`: Team `FOR UPDATE`, TeamPolicy `FOR SHARE`, plus Task row locks through the shared Task lock helper.
- `core/operator_application.py`: Team and existing Thread `FOR UPDATE`.
- `core/update_thread_context.py`: Task and Team `FOR UPDATE`.
- `core/context_assembly.py`: optional Task `FOR UPDATE`, Team `FOR UPDATE`, and Objective `FOR SHARE`.
- `core/knowledge_index.py`: Signal and KnowledgeItem `FOR UPDATE`.
- Additional row-locking sites exist in learning, evaluation, strategy, lifecycle, cost, and other services; this list is representative, not a complete grant matrix.

Therefore the read-only role cannot execute all current service paths as written. Do not solve this by granting blanket UPDATE on every locked table. The complete F1 inventory must classify each call site as (a) a real mutation writer needing narrowly scoped DML, (b) a lock-only read that should use a separately reviewed owner-controlled lock helper/SECURITY DEFINER operation, or (c) a test-only/admin path. Verify the resulting effective privileges and actual operations through the intended runtime identity. The RW4-1 Event attestation function's SECURITY DEFINER decision solves only its new Task/Team/Signal lock operation; it does not solve existing application lock privileges.

### 6.3 Production row-lock inventory — exact source search at current main

A source search of the following 19 production modules containing SQLAlchemy `.with_for_update()` found **114 row-lock call sites**: `core/objectives.py`, `core/strategy.py`, `core/ingestion.py`, `core/plans.py`, `core/evaluations.py`, `core/update_thread_context.py`, `core/operator_application.py`, `core/update_thread.py`, `core/learning_commit.py`, `core/context_assembly.py`, `core/update_thread_worker.py`, `core/world_memory.py`, `core/knowledge_quality.py`, `core/task_runtime.py`, `core/knowledge_index.py`, `core/knowledge_lifecycle.py`, `core/generation_cost.py`, `core/knowledge_revalidation.py`, and `core/experience_distiller.py`. This is a source inventory, not a claim that all paths have been exercised under `watch_runtime`. Default `.with_for_update()` means `FOR UPDATE`; `read=True` means `FOR SHARE`. PostgreSQL requires SELECT plus UPDATE privilege on at least one column of each locked table for both modes.

| Locked relation | Unconditional `FOR UPDATE` | Unconditional `FOR SHARE` | Conditional mode | Preliminary classification |
|---|---:|---:|---:|---|
| Task | 19 | 2 | 0 | Mixed: TaskRuntime and workers update lifecycle columns; other paths lock for validation/replay. |
| Team | 15 | 4 | 0 | Lock/serialization only in the inventoried paths; no production Team status/domain assignment or `UPDATE(Team)` was found. |
| TeamPolicy | 1 | 14 | 0 | Immutable pinned-policy reads/locks; no production policy mutation path found. |
| Objective | 5 | 1 | 0 | Mixed: ObjectiveService transitions status; strategy/validation paths also lock for read/serialization. |
| Plan | 2 | 1 | 0 | Mixed: Plan lifecycle transitions plus read/validation locks. |
| Event | 0 | 0 | 1 (`read=not exclusive`) | Read/idempotency lock; Event is append-only in application paths. |
| Evaluation | 2 | 0 | 0 | Lifecycle record/reject paths update Evaluation state. |
| Thread | 4 | 0 | 0 | Existing Operator/context/world-memory paths lock/read and validate; no production Thread lifecycle mutation path found. |
| Hypothesis | 2 | 0 | 0 | Lock/read in commit/context paths; no direct Hypothesis row update was identified in the inventoried code. |
| EvidenceLink | 1 | 0 | 0 | Lock/read in context assembly; no production update path found. |
| LearningChange | 9 | 2 | 0 | Mixed: decision/lifecycle state transitions plus immutable/request validation locks. |
| KnowledgeItem | 18 | 0 | 0 | Mixed, with real conditional state/content updates in learning/lifecycle flows. |
| TaskGenerationCharge | 5 | 0 | 0 | Real reservation/charge status and accounting updates. |
| KnowledgeQualityAssessment | 2 | 0 | 0 | Recorded-assessment validation/replay lock; no mutation in the lock-owning validation path. |
| Signal | 1 | 0 | 0 | Knowledge-index path locks the immutable Signal while reconciling derived index state; no Signal mutation. |
| TeamExperienceIndexState | 1 | 0 | 0 | Index-state upsert/update path. |
| KnowledgeLifecycleAssessment | 1 | 0 | 0 | Recorded-assessment validation/replay lock. |
| KnowledgeRevalidationAssessment | 1 | 0 | 0 | Recorded-assessment validation/replay lock. |
| **Total** | **89** | **24** | **1** | **114 call sites** |

The counts above are grouped by the relation selected at the locking query. One Event lock in `PlanService._accepted()` uses `with_for_update(read=not exclusive)`, so it is `FOR SHARE` in the ordinary path and `FOR UPDATE` in the exclusive materialization path; it is shown separately rather than counted as either unconditional mode. Some call sites are constructed through query variables; their target was resolved from the enclosing query before grouping. The table intentionally distinguishes the number of lock calls from the number of distinct business writers: several calls are helper/validation paths, and one transaction may lock multiple relations.

**Preliminary lock-only candidates** (must be confirmed at each call site before any helper API is frozen): Team, TeamPolicy, Thread, Event, Signal, EvidenceLink, KnowledgeQualityAssessment, KnowledgeLifecycleAssessment, KnowledgeRevalidationAssessment, and selected read-only locks on Objective, Plan, LearningChange, Hypothesis, and Task. For these, the runtime should not receive UPDATE merely to acquire a row lock.

**Mixed/actual-writer relations** (column-level UPDATE grants may be justified only for columns the corresponding service actually mutates): Task, Objective, Plan, Evaluation, LearningChange, KnowledgeItem, TaskGenerationCharge, and TeamExperienceIndexState. The lock inventory alone is not a complete DML grant list: every INSERT, UPDATE, DELETE, sequence use, and trigger-side write must be audited independently. For example, Signal ingestion needs INSERT on Signal and Event, while the KnowledgeIndex Signal lock is lock-only; these are different capabilities on the same table.

Do not use `GRANT UPDATE (id)` or another arbitrary column solely to satisfy row-lock permission. A column-level grant is still authority to attempt changing that column; it is not harmless unless a separately accepted database invariant makes the column immutable for this principal. Do not add fake `lock_version` columns to every table merely to satisfy PostgreSQL's privilege check.

### 6.4 Recommended F1 design — hybrid narrow DML plus owner-controlled lock functions

The least-complex viable design is a **hybrid**, not blanket UPDATE and not a SECURITY DEFINER wrapper around every query:

1. **Real application writers:** grant the runtime only the exact INSERT/UPDATE column/DELETE capabilities required by the audited service operations. Prefer column-level UPDATE where it materially narrows authority. Keep Task lifecycle writes in TaskRuntime, disposition writes withheld, and immutable Event/Signal/Thread rules enforced independently. Sequence privileges must be granted only where the relevant INSERT actually uses a sequence.
2. **Lock-only reads:** move only the identified lock-only `FOR UPDATE`/`FOR SHARE` operations behind small, static, owner-controlled functions owned by `watch_owner`. Each function should name one relation and one lock mode (or one reviewed canonical multi-relation lock sequence), accept typed primary-key inputs, use schema-qualified SQL with `SET search_path = pg_catalog`, and return only a minimal found/locked result. It must not accept caller SQL, relation names, arbitrary predicates, or dynamic SQL. The lock is transaction-scoped and remains held after the function returns; caller retains transaction ownership. Migration `0020_rw4_task_identity.py` already uses this pattern for `lock_team_for_triage_task_insert()`: SECURITY DEFINER, owner-controlled, fixed `pg_catalog` search_path, schema-qualified Team reference, PUBLIC EXECUTE revoked. Reuse that security pattern, but do not assume its Task-insert-specific function is a general-purpose runtime lock API.
3. **No generic dynamic lock function:** a `regclass`/text-driven generic helper would broaden the callable surface and make it harder to audit relation, predicate, scope, lock order, and authorization. Do not use it.
4. **Same transaction and visibility:** the helper must not open/commit a connection or transaction. The caller performs its ordinary SELECT after the helper call, in the same transaction. Any path relying on fresh post-wait visibility must explicitly require READ COMMITTED; a helper does not refresh an existing SQLAlchemy identity-map object by itself.
5. **Function hardening:** revoke PUBLIC EXECUTE in the creation transaction; grant EXECUTE only to the intended runtime identity; fixed trusted search_path; schema-qualified relation references; no caller-settable GUC/bypass; no direct runtime table UPDATE grant solely for helper use. Tests must prove the runtime cannot invoke owner-only operations outside the narrowly granted functions and that a row lock survives function return until caller rollback/commit.
6. **Preserve authority boundaries:** these helpers grant serialization, not permission to perform business writes. They must not create Tasks, mutate Team/Thread lifecycle, write Events, or bypass Control Room/TaskRuntime. Do not turn every existing lock into a database function if the operation already has a narrowly justified UPDATE grant for a real mutation.

**Important qualification:** The table above is not yet a final grant matrix. The next audit artifact must map every one of the 114 call sites to (a) transaction owner, (b) exact lock target/mode/order, (c) whether the same transaction mutates that relation and exact columns, (d) required INSERT/UPDATE/DELETE/sequence privileges, and (e) chosen direct-DML or helper mechanism. No grants or helper functions should be implemented until that matrix is reviewed and the actual host/runtime connection identity is identified.

The current role test logs in as `watch_runtime`, proves a simple SELECT plus forbidden direct SQL operations, and now checks that no table-level or column-level INSERT/UPDATE privilege has leaked onto any application table. It still does not execute any production service workflow through that identity. No production host/composition root consumes the runtime DSN in this repository. Thus the current evidence proves the SELECT-only isolation boundary, not that the application is deployable under it; the first future host integration must run representative service operations under the exact runtime login and fail closed for ungranted operations.

The detailed 114-site F1 source ledger and staged reconciliation plan are maintained in [`rw4-1b-f1-lock-and-dml-grant-matrix.md`](rw4-1b-f1-lock-and-dml-grant-matrix.md). The complete companion writer inventory is [`rw4-1b-f1-dml-writer-audit.md`](rw4-1b-f1-dml-writer-audit.md), covering all 45 production Python modules, migration-only DML, smoke-only DML, exact write columns, and transaction ownership. It distinguishes locked-row mutation from writes to other relations in the same transaction, records transaction ownership and per-site lock mode, and explicitly leaves final grants blocked on the complete writer inventory and deployed runtime identity.

The current source audit also confirms the F2 gap:

- No production `Thread()` creation/insert path exists; direct Thread creation/deletion found by repository search is in tests/fixtures.
- No production assignment to `Thread.status` or `Thread.domain` exists. `core/operator_application.py` and `core/update_thread_context.py` lock/read existing Threads and validate availability; the world-memory commit path writes Hypotheses, EvidenceLinks, and ConfidenceChanges rather than Thread lifecycle fields.
- `activate_team` as the canonical starter-Thread creator and Operator-authorized `resolve_thread` as a lifecycle writer are accepted future owners, not implemented production paths.
- No production host composition root or complete bootstrap/maintenance/external writer inventory exists in this repository.

F2 is therefore not closed by the presence of the F3 domain trigger. Before matched writes, every actual/future Thread create/status/domain writer must be brought under the accepted Team → Thread lock order and Team revision contract, and the deployed host/maintenance writer inventory must be reconciled. Until those writers exist and are proved, do not grant runtime Thread INSERT/UPDATE/DELETE merely because the table is part of the future design.

## 7. Unresolved design gates (must not be papered over)

| Gate | Current evidence | What remains before this DDL can be accepted |
|---|---|---|
| Option A feasibility / F1 | Role bootstrap exists; runtime remains SELECT-only; no host consumer. | Prove all required trigger reads/writes and effective grants under the actual runtime/migrator identities. If Option A cannot be enforced, stop and return with a separately scoped Option B design. |
| F2 Thread writers | Source audit found no production Thread create/status/domain writer; `activate_team` and Operator `resolve_thread` are accepted future owners, not implemented. No host/maintenance/external inventory exists. | Implement and inventory every authorized writer under Team → Thread locking/revision rules; reconcile deployed and maintenance identities before matched writes. |
| F3 Thread domain | Behavioral contract specified in §7.1; no function implementation or PostgreSQL race proof. | Independently review the exact PL/pgSQL body and prove both race orders at READ COMMITTED with the VOLATILE trigger; matched writes remain disabled until both pass. |
| F4 ORM freshness | Query/refresh contract specified in §7.2; no triage finalizer implementation or PostgreSQL/SQLAlchemy proof. | Implement only under separate authorization, then prove stale identity-map refresh after row-lock wait and exact replay after a later legal status transition. |
| D4.1a | Canonical Team/hash arbitration not implemented. | No duplicate disposition until separately implemented/proven. |
| D4.2 | Durable receipt and stale-receipt finalization not implemented. | Receipt schema, one-per-Task identity, recovery and fingerprint contract remain separate prerequisites. |
| RW-5 | Canonical lock helper/revision/writer retrofit not implemented. | Matched writes remain disabled until all relevant writers participate and two-session proof passes. |
| Decision 7 | All three outcomes enabled together. | No matched/deferred-only rollout; no disposition write-enable until every listed dependency is complete and independently reviewed. |

### 7.1 F3 — exact Thread-domain guard and race contract

The proposed `watch_protect_matched_thread_domain()` trigger function has this exact behavioral contract:

- Attach as `BEFORE UPDATE OF domain FOR EACH ROW` on `threads`.
- If `NEW.domain IS NOT DISTINCT FROM OLD.domain`, return `NEW` without querying dispositions. No-op assignments are not domain transfers.
- Otherwise query `signal_dispositions` for an existing row with `disposition = 'matched'`, `thread_id = OLD.id`, and `team_id = OLD.team_id`. If found, reject the domain change with SQLSTATE `55000`; otherwise return `NEW`.
- Do not block status/title changes. Duplicate and deferred dispositions do not freeze a Thread domain because neither stores a Thread reference.
- The function must be explicitly `VOLATILE` and the relevant writer/finalizer transactions must use READ COMMITTED. It does not need its own Thread row lock: PostgreSQL has acquired the Thread row lock for the UPDATE before the BEFORE trigger runs. The post-wait query must use a fresh snapshot so it can observe a matched disposition committed while the UPDATE waited. SECURITY INVOKER is preferred because this function only reads SignalDisposition; the runtime SELECT grant must be proved under F1.

Both race orders are mandatory PostgreSQL proofs:

1. **Matched finalizer wins:** finalizer acquires Thread `FOR NO KEY UPDATE`, validates active/same-Team/same-domain state, inserts the matched disposition, and commits. A concurrent domain UPDATE waits on the Thread row. After the finalizer commits, the trigger's VOLATILE query sees the matched disposition and rejects the UPDATE with `55000`.
2. **Domain UPDATE wins:** domain UPDATE acquires the Thread row first and commits the new domain. The finalizer waits, then its locked/refreshing read sees the committed domain and rejects the proposed match before any disposition or terminal evidence is written.

A status update is serialized by the same Thread row lock but is not frozen by the guard: if it commits first, a first-time finalizer sees the non-active status and cannot match; if the matched finalizer commits first, a later legal transition to dormant/resolved is allowed and does not invalidate replay.

### 7.2 F4 — exact ORM freshness contract

The current `TaskRuntime.finalize()` locks the Task and owns the terminal Outcome/Task/Event transaction, but has no triage-specific Thread finalizer yet. The future triage branch must not assume that a SQLAlchemy row lock refreshes a Thread object already present in the Session identity map.

For first-time business finalization, after Task and Team locks and before validating candidate state:

- Form the union of the receipt's candidate Thread IDs and the currently discovered bounded candidate Thread IDs.
- Lock that union in ascending UUID order with a same-session query equivalent to `SELECT ... FROM threads WHERE team_id = :team_id AND id IN (:thread_ids) ORDER BY id FOR NO KEY UPDATE`.
- Execute the locking query with SQLAlchemy `populate_existing=True` (or explicitly `Session.refresh(instance, with_for_update=...)`) so scalar values already loaded into the identity map are overwritten from the row returned after the lock is granted.
- Require the locked query to return every expected, still-required Thread row; a missing row or a Team mismatch is a stale/integrity failure, not a silently smaller candidate set.
- Validate `team_id`, `domain`, and `status` only from those refreshed instances. A matched result requires the selected Thread to be same-Team/same-domain and active at this serialized decision point.
- Keep the refreshed Thread locks in the same transaction through disposition, Outcome, terminal Task state/time, and `task_completed` commit. Continue the accepted lock order: Task → Team → sorted Thread → sorted Hypothesis → sorted Signal.

The exact replay path is different: after a prior terminal result is found, validate the immutable receipt, disposition, Outcome, Task terminal fields (including `completed_at`), the complete canonical `task_completed` payload/cardinality, and current Team/Thread domain identity. Do not require the Thread's current status to remain active; a later legal dormant/resolved transition cannot invalidate a committed historical match. The domain guard and immutable disposition preserve the historical domain relationship.

F4 remains open until real PostgreSQL/SQLAlchemy two-session tests prove at least: (a) a Thread is preloaded into Session A's identity map, Session B changes domain/status and commits while A waits, and A's post-lock `populate_existing=True` query sees the committed values and refuses stale eligibility; (b) the finalizer locks first and a concurrent domain UPDATE waits, then is rejected by F3 after disposition commit; and (c) replay succeeds after a later legal status transition without re-running current active eligibility. Assert no disposition/Outcome/terminal Event partial commit on first-finalization rejection. These are proof requirements, not evidence that the implementation exists.

**No implementation is authorized by closing this draft.** The current task is to review and freeze the physical contract. A separate explicit authorization is still required for RW4-1 implementation and, later, for write enablement.

## 8. Required review sequence for this draft

1. Validate every table/column/type/constraint against the current ORM and migration source; reconcile names and actions.
2. Independently review CHECK truth tables, FK support keys, partial-index predicates, and all child-side FK indexes.
3. Review the trigger inventory and each trigger's exact event, timing, row/statement level, function volatility, security mode, search path, SQLSTATE, and required PostgreSQL privileges for every row-locking SELECT. Prove the intake attestation trigger can acquire Task → Team → Signal locks through its owner function without granting runtime UPDATE on Signal or direct runtime EXECUTE on the helper; separately reconcile the existing ingestion Task/Team lock privileges.
4. Verify the Event trigger's Task → Team → Signal locks are compatible with all three current ingestion branches and fail closed on cross-domain reuse.
5. Review the five-table ACCESS EXCLUSIVE NOWAIT cutover and the separate Task-FK migration lock/preflight; prove no partial lock retention after NOWAIT failure.
6. Reconcile runtime grants with F1/F2 and refuse to claim Option A feasible while any supported writer can bypass the guards.
7. Check forward-only downgrade refusal and fresh-install/current-head migration ordering; verify the Event marker CHECK is installed `NOT VALID` and no historical Event scan/validation occurs.
8. Run independent review; resolve all findings; only then ask the Operator to accept/revise the physical contract.
9. Request separate implementation authorization. Do not start RW4-1 ORM, migration, trigger SQL, disposition runtime, or RW4-1 concurrency tests under this design-only step. The companion F1 role-isolation regression assertion is limited to verifying the already-provisioned SELECT-only role boundary.
