# RW4-1B exact physical DDL freeze — review draft

**Status:** Draft proposal for Operator and independent review. This document is not an accepted physical contract and does not authorize implementation.

**Baseline:** PR #221 merged at `c648892e4896113700c8103397be01c11c0d22ed`. The current repository includes D2 migration `0020_rw4_task_identity`; its four-column Task support key is already present. The later SignalDisposition-to-Task composite FK remains a separate migration and gate.

**Purpose:** Turn the accepted logical SignalDisposition and provenance decisions into a concrete PostgreSQL contract, identify the exact boundaries between migrations, and expose any unresolved design questions before SQL/ORM work begins.

**Strict scope:** Documentation and design only. No ORM, migration, SQL, application code, role grants, tests, database execution, TaskRuntime, ingestion, D4.1a, D4.2, RW-5, RW4-2 Stage B, RW4-3, RW4-4, or RW4-5 implementation.

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
    );
```

No default, no backfill, no legacy scan, and no payload rewrite. Every pre-cutover Event remains NULL and permanently ineligible as RW4-1 provenance. A malformed legacy Event must not block cutover.

A single `BEFORE INSERT` trigger owns the marker:

- For `signal_ingested` and `fetch_no_change`, ignore/overwrite caller-supplied marker data only after validating the complete intake witness; set marker to integer `1`.
- For all other Event types, reject non-NULL caller-supplied marker values and persist NULL.
- Require the Task to exist, be `ingest_source`, and be `running`; require its Team to exist and be active; require the Signal to exist; require Signal.domain = Team.domain; and require the five payload fields to be JSON strings and equal the stored Signal fields.
- Parse the payload Signal UUID strictly; reject malformed/non-canonical identity rather than coercing it silently.
- Acquire compatible row locks in exact order Task `FOR SHARE` → Team `FOR SHARE` → Signal `FOR SHARE`. The existing ingestion path already holds Task `FOR UPDATE` and Team `FOR SHARE`; do not upgrade Team to `FOR NO KEY UPDATE`.
- Preserve the current Event payload contract; do not add a new payload key as a substitute for the marker.

The trigger must reject UPDATE/DELETE of either intake Event type and reject type changes into or out of the protected set. It must also prevent marker changes. Runtime is separately denied Event UPDATE/DELETE for all Event types.

**Reuse-path implication:** an existing-Signal `fetch_no_change` or ON-CONFLICT winner whose Signal domain differs from the Task Team will fail the new Event trigger and roll back that ingestion transaction. Same-Task prior-outcome replay creates no Event and cannot manufacture a marker. These are explicit fail-closed boundaries; any desired ingestion behavior change is a separately scoped decision, not an RW4-1 silent fallback.

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

Do not freeze Thread.status. It is evaluated at the serialized decision point; later valid status transitions do not invalidate historical disposition or exact replay.

### 4.1 Trigger/function execution model

Proposed names:

- `trg_events_attest_intake_witness`
- `trg_events_protect_intake_witness`
- `trg_signals_protect_intake_identity`
- `trg_tasks_protect_intake_identity`
- `trg_teams_protect_intake_domain`
- `trg_threads_protect_matched_domain`
- `trg_signal_dispositions_assign_created_at`
- `trg_signal_dispositions_immutable`
- `trg_<protected_table>_no_truncate` for each of the five protected tables.

Functions should be small and purpose-specific rather than a generic integrity framework. Use SECURITY INVOKER where runtime's audited SELECT grants suffice. Where a function genuinely needs elevated reads, use SECURITY DEFINER owned by `watch_owner`, fixed trusted search_path, schema-qualified references, explicit VOLATILE where post-wait visibility is required, and revoke PUBLIC EXECUTE in the creation transaction. Trigger firing does not imply a direct runtime EXECUTE grant. No caller-settable GUC, session flag, temporary-table bypass, or replication-role bypass is permitted.

## 5. Migration boundaries and exact lock protocols

### 5.1 Initial RW4-1 cutover migration

One linear Alembic migration from the actual current head. One transaction. The first operation that can wait for existing application access is one ordered statement:

```sql
LOCK TABLE tasks, teams, signals, events, threads
    IN ACCESS EXCLUSIVE MODE NOWAIT;
```

Do not acquire these locks piecemeal and do not prelock at SHARE ROW EXCLUSIVE then upgrade. If NOWAIT fails, roll back the entire migration transaction so every acquired lock is released; retry in a quiet maintenance window.

While all five locks remain held: add the nullable marker and CHECK; create the empty SignalDisposition table and its row-local constraints/indexes; create/attach the marker, immutability, identity, Thread-domain, timestamp, and TRUNCATE guards; set ownership and reviewed grants; verify trigger definitions, role memberships, effective privileges, and protected-table inventory; then commit. No full-table historical Event scan. No legacy update/backfill.

**Downgrade:** unconditional refusal after the forward-only cutover is committed. A migration failure before commit relies on PostgreSQL transactional rollback; there is no destructive post-commit downgrade.

### 5.2 Later D2-dependent Task FK migration

Keep separate from the initial cutover. Install only:

`fk_signal_dispositions_task_identity`:
`(decided_by_task_id, team_id, signal_id, identity_version) → tasks(id, team_id, signal_id, identity_version)`.

Use the accepted single ordered `SHARE ROW EXCLUSIVE NOWAIT` preflight lock on `tasks, events, signal_dispositions`, with locked preflight and transactional rollback. Verify the exact D2 support key exists. Require no pre-gate triage/disposition history and install the FK without a temporary Task-ID-only substitute. Runtime disposition INSERT remains revoked until this migration and every Decision 7 prerequisite are independently verified.

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

## 7. Unresolved design gates (must not be papered over)

| Gate | Current evidence | What remains before this DDL can be accepted |
|---|---|---|
| Option A feasibility / F1 | Role bootstrap exists; runtime remains SELECT-only; no host consumer. | Prove all required trigger reads/writes and effective grants under the actual runtime/migrator identities. If Option A cannot be enforced, stop and return with a separately scoped Option B design. |
| F2 Thread writers | No supported production Thread create/status/domain writer or deployment inventory. | Identify every host, worker, bootstrap, maintenance, and external writer; reconcile least privilege before matched writes. |
| F3 Thread domain | Design only. | Freeze exact function body, VOLATILE/read-committed visibility, and both concurrent race orders. |
| F4 ORM freshness | Design only. | Name the exact finalizer query and prove stale identity-map refresh after row-lock wait. |
| D4.1a | Canonical Team/hash arbitration not implemented. | No duplicate disposition until separately implemented/proven. |
| D4.2 | Durable receipt and stale-receipt finalization not implemented. | Receipt schema, one-per-Task identity, recovery and fingerprint contract remain separate prerequisites. |
| RW-5 | Canonical lock helper/revision/writer retrofit not implemented. | Matched writes remain disabled until all relevant writers participate and two-session proof passes. |
| Decision 7 | All three outcomes enabled together. | No matched/deferred-only rollout; no disposition write-enable until every listed dependency is complete and independently reviewed. |

**No implementation is authorized by closing this draft.** The current task is to review and freeze the physical contract. A separate explicit authorization is still required for RW4-1 implementation and, later, for write enablement.

## 8. Required review sequence for this draft

1. Validate every table/column/type/constraint against the current ORM and migration source; reconcile names and actions.
2. Independently review CHECK truth tables, FK support keys, partial-index predicates, and all child-side FK indexes.
3. Review the trigger inventory and each trigger's exact event, timing, row/statement level, function volatility, security mode, search path, and SQLSTATE.
4. Verify the Event trigger's Task → Team → Signal locks are compatible with all three current ingestion branches and fail closed on cross-domain reuse.
5. Review the five-table ACCESS EXCLUSIVE NOWAIT cutover and the separate Task-FK migration lock/preflight; prove no partial lock retention after NOWAIT failure.
6. Reconcile runtime grants with F1/F2 and refuse to claim Option A feasible while any supported writer can bypass the guards.
7. Check forward-only downgrade refusal and fresh-install/current-head migration ordering.
8. Run independent review; resolve all findings; only then ask the Operator to accept/revise the physical contract.
9. Request separate implementation authorization. Do not start ORM, migration, trigger SQL, or tests under this design-only step.

