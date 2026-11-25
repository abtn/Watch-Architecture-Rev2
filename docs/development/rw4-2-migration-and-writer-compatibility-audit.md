# RW4-2 Stage A — Task migration and existing-writer compatibility audit

**Status:** Source audit and proposed migration design, 2026-11-25. This is a documentation-only Stage A artifact. D1 and all six D2 decisions remain accepted and unchanged. No schema, migration, ORM, Task writer, or runtime implementation is authorized by this audit.

**Repository baseline:** `main` at `3fd27167e7e77eeed2110d9a2028a9ecaa005bc3`, the base of PR #187 at audit time.

## 1. Executive result

The accepted D2 schema can be added without changing the required shape of existing non-triage Tasks:

- Add nullable `tasks.signal_id UUID` and `tasks.identity_version` columns with no default.
- Add a foreign key from `tasks.signal_id` to `signals.id`.
- Add a database check requiring both identity fields for `task_type = 'triage_signal'`; also reject a half-populated pair.
- Add unique `(team_id, signal_id, identity_version)`.
- Add a partial unique index on `events(task_id)` for `type = 'triage_signal_requested'`.

Existing Task types keep both new columns NULL. PostgreSQL's ordinary unique-constraint NULL semantics allow any number of such non-triage rows while still enforcing uniqueness for populated triage identity tuples.

No existing production code path or migration currently creates `triage_signal` Tasks or `triage_signal_requested` Events. This is a source-code observation, not proof that a deployed database contains no manually seeded or historical rows. The migration must inspect actual database contents and fail closed if it finds triage history that cannot be safely reconciled.

## 2. Current schema and migration facts

At the audited baseline:

- `core/models.py::Task` has no `signal_id` or `identity_version` mapping.
- `Task.id` is already the primary key, so the accepted UUIDv5 identity remains directly enforceable by the existing primary-key constraint.
- `Task.team_id` and `Task.policy_version` already reference the selected TeamPolicy pair.
- `signals` is created before any proposed new migration and has UUID primary key `signals.id`.
- `events` has Task attribution and non-unique index `ix_events_task_id_type`; there is no existing request-event uniqueness constraint.
- The current migration chain ends at `0019_rw1_world_memory`. The new migration must follow that actual head; do not reuse an old proposed revision number or assume an earlier migration head.
- The original Task and Event tables are created in `0002_ingestion_kernel.py`. Task lifecycle columns and `uq_tasks_id_team` were added in `0009_task_lifecycle_outcome.py`. Later migrations add other tables/constraints but do not add triage identity.

## 3. Proposed migration shape

### 3.1 Task columns and constraints

Add the two nullable columns without defaults:

```sql
ALTER TABLE tasks ADD COLUMN signal_id uuid NULL;
ALTER TABLE tasks ADD COLUMN identity_version varchar NULL;
```

Add the Signal foreign key:

```sql
ALTER TABLE tasks
  ADD CONSTRAINT fk_tasks_signal
  FOREIGN KEY (signal_id) REFERENCES signals(id);
```

Add a check that makes the pair all-or-none and requires it for triage Tasks:

```sql
ALTER TABLE tasks
  ADD CONSTRAINT ck_tasks_triage_identity
  CHECK (
    (
      task_type = 'triage_signal'
      AND signal_id IS NOT NULL
      AND identity_version IS NOT NULL
      AND length(identity_version) > 0
    )
    OR (
      task_type <> 'triage_signal'
      AND signal_id IS NULL
      AND identity_version IS NULL
    )
  );
```

Add the accepted logical-pair uniqueness constraint:

```sql
ALTER TABLE tasks
  ADD CONSTRAINT uq_tasks_team_signal_identity
  UNIQUE (team_id, signal_id, identity_version);
```

The check assigns these identity columns exclusively to triage_signal: triage Tasks require both fields and a non-empty version; every other Task type must keep both fields NULL. It rejects half-populated pairs and prevents unrelated Task types from acquiring triage identity. The check does not hard-code triage_identity_v1; the accepted v1 value is validated by the creator/replay contract, while any future identity generation remains subject to its separately approved transition. The database unique constraint is intentionally independent of the canonical UUID primary key: the primary key arbitrates equal UUIDs, while this constraint rejects a different UUID assigned to the same logical pair/version.

### 3.2 Request Event index

Add exactly the accepted partial unique index:

```sql
CREATE UNIQUE INDEX uq_events_triage_signal_requested_task
  ON events (task_id)
  WHERE type = 'triage_signal_requested';
```

This enforces **at most one** matching request Event per Task. It does not enforce existence. The creator's single transaction must insert Task and request Event atomically, and every replay/load must verify exactly one valid request Event. Do not describe this index as an exactly-one constraint.

### 3.3 Preflight and backfill policy

The migration preflight is a read-only diagnostic gate, not an opportunity to backfill legacy triage rows. The migration may proceed only when the target database contains zero triage_signal Tasks and zero triage_signal_requested Events. Any non-zero result aborts before schema or data mutation. Historical repair/backfill requires a separate reviewed data-repair decision and migration; it must not be hidden inside this additive schema migration.

Preflight must enumerate the complete population covered by the partial index, not merely Events already associated with known triage Tasks:

1. Count every Task with task_type = triage_signal.
2. Enumerate every Event with type = triage_signal_requested, grouped by task_id; detect duplicates, null/missing attribution, and malformed rows.
3. For each such Event, verify its referenced Task exists and is a triage_signal Task; reject orphan Events and Events attached to any other Task type.
4. Validate payload shape and required identity/provenance fields. Where a Task exists, verify exact agreement among Event attribution, Task ID, Team ID, Signal ID, identity version, and recomputed canonical UUIDv5. Verify referenced Signal existence and reject missing, malformed, cross-Task, or inconsistent evidence.
5. Report duplicate logical identity tuples and all violations that would prevent the proposed FK/check/unique constraints.

Because the permitted migration state is zero historical triage Tasks and zero request Events, the additive migration performs no backfill. If preflight finds any triage Task or request Event, including an otherwise valid-looking historical pair, stop and preserve the database unchanged. Produce a diagnostic report with affected IDs/counts. Do not delete, merge, select a winner, rewrite Task IDs, or synthesize requester provenance.

A later repair proposal must identify the trustworthy immutable source for every field, define Event cardinality/provenance treatment, preserve evidence, and include rollback procedures. Prove the repair on a disposable database copy. It requires independent review and explicit authorization.

The preflight must scan all triage_signal_requested Events because the partial index applies to every row of that type, including malformed Events attached to non-triage Tasks. Checking only duplicate groups or joining from triage Tasks is insufficient. The Signal FK proves only Signal existence; the composite unique constraint proves only logical-pair uniqueness. Neither proves Team eligibility, Signal-to-Team domain equality, or TeamPolicy source-allowlist membership. Those remain creator-level validations under the canonical Team lock.

If all preflight queries return zero historical triage Tasks, zero request Events, and zero constraint violations, add the nullable columns, FK, check, composite unique constraint, and partial unique index transactionally. A concurrent-index path is unnecessary unless production scale/availability evidence requires it.

### 3.4 Rollout and ORM compatibility

The ORM mapping must declare both fields nullable. Existing constructors and `pg_insert(Task)` writers may omit them and will continue to insert NULL. The database check makes omission invalid only for a `triage_signal` row.

The rollout order for a future authorized implementation is:

1. Run preflight on the target database and stop on any unexpected triage history or duplicate request Event.
2. Apply the additive nullable-column/constraint/index migration.
3. Deploy the ORM mapping and tests with the existing writers unchanged.
4. Deploy the complete Control Room Task-creation authority path described in §4.2, including all inventoried producers delegating to named Control Room operations. Do not enable only a triage-specific path while leaving legacy producers as independent Task writers.
5. Enable triage creation only after the migration is present; the operation must always supply both identity fields and the canonical UUIDv5 Task ID.
6. Verify PostgreSQL constraints/indexes, writer compatibility, and atomic exactly-one creation/replay on the exact tested migration head.

Do not make the columns globally NOT NULL, add fake defaults, or retrofit unrelated Task types with fabricated Signal identity. Do not combine this schema migration with SignalDisposition persistence (RW4-1), the RW-5 lock-helper implementation, or the Stage B creator implementation.

## 4. Existing production Task-writer inventory

The audit searched the production source for `Task(`, `pg_insert(Task)`, and Task creation patterns at the audited baseline. The following direct producers were found:

| Source | Creation path | Task type(s) | Required compatibility |
|---|---|---|---|
| `core/operator_application.py` | `OperatorApplicationAdapter.create_update_thread_task` | `update_thread` | Leave both identity fields NULL |
| `core/operator_application.py` | LearningChange decision request insert | `approve_learning_change` | Leave both identity fields NULL |
| `core/operator_application.py` | Operator update request creation | `operator_update` | Leave both identity fields NULL |
| `core/plans.py` | Plan materialization creates child Tasks | Currently `ingest_source` | Leave both identity fields NULL |
| `core/task_runtime.py` | Follow-on evaluation creation during terminal finalization | `evaluate_outcome` | Leave both identity fields NULL |
| `core/task_runtime.py` | Follow-on Knowledge Quality assessment creation | `assess_knowledge_quality` | Leave both identity fields NULL |
| `core/task_runtime.py` | Follow-on Knowledge Revalidation assessment creation | `assess_knowledge_revalidation` | Leave both identity fields NULL |
| `core/task_runtime.py` | Follow-on Knowledge Lifecycle assessment creation | `assess_knowledge_lifecycle` | Leave both identity fields NULL |
| `core/knowledge_revalidation.py` | `KnowledgeRevalidationService.create_task` | `assess_knowledge_revalidation` | Leave both identity fields NULL |

The Knowledge Revalidation Task type has two source-level creation paths: the dedicated service and the TaskRuntime follow-on path. They must remain compatible with the same nullable schema; this audit does not consolidate or refactor them.

No other production Task constructor or `pg_insert(Task)` writer was found in the audited source search. This is a bounded source audit, not a proof against dynamically constructed SQL, external host code, or writes made outside this repository.

### 4.1 Existing Event writers

Existing code writes many Task-attributed Events, but the audited source contains no production occurrence of Event type `triage_signal_requested`. The partial index therefore does not constrain existing Event types. The preflight is still mandatory because database contents may not exactly match the checked-in source.

### 4.2 Control Room authority and transaction boundary

D1 is an accepted architectural decision, not merely a requirement for the new triage entrypoint. The Control Room is the sole logical authority for every application Task creation. All nine inventoried producers in §4 must therefore become named Control Room operations. This is a staged conformance requirement, not a reopening of D1 and not permission to refactor code in this documentation-only PR.

Before Stage A can freeze, provide a producer-to-operation mapping for all nine paths: the three OperatorApplication paths (update_thread, approve_learning_change, operator_update); PlanService ingest_source materialization; the four TaskRuntime follow-on paths (evaluate_outcome, assess_knowledge_quality, assess_knowledge_revalidation, assess_knowledge_lifecycle); and KnowledgeRevalidationService assess_knowledge_revalidation. Each named operation must preserve the existing caller's authorization, idempotency, and transaction semantics. TaskRuntime follow-on creation must delegate through Control Room using the existing Session.

Every Control Room operation is session-bound. It receives the caller's active SQLAlchemy Session and does not create a Session, begin an independent transaction, commit, or roll back. The outer workflow/transaction owner remains responsible for commit or rollback. The operation validates and authorizes, obtains operation-required locks, performs Task/Event writes, and flushes as needed. Flush is not commit and does not make writes durable.

For triage creation, Task and triage_signal_requested Event are inserted in the same caller-owned transaction; they either both commit or both roll back. A failure after either insert but before commit must leave neither row durable. The Control Room operation must not catch an error and independently commit partial work.

TaskRuntime follow-on Task creation must use the existing Session in the transaction that owns the originating Task's terminal/follow-on work. It must not open or commit a separate transaction. This preserves atomicity between originating Task finalization and follow-on Task creation. Control Room centralizes Task-creation authority; it does not take transaction ownership away from the caller or TaskRuntime workflow.

Illustrative shape (not an API implementation commitment):

```python
with session_factory.begin() as session:
    result = control_room.create_triage_signal_task(
        session=session,
        principal=principal,
        request=request,
    )
```

The outer context commits or rolls back. The operation must not call session.commit() or session.rollback(). Equivalent named operations for legacy producers follow the same session-bound rule and preserve their existing transaction scopes.

The Control Room may be a small logical application module/facade; D1 does not require a new service, framework, generic factory, or separate database layer. The invariant is that no production producer persists a Task except through a named Control Room operation. Workers, models, ingestion, plans, and feature services may request work but may not independently construct/persist Tasks. TaskRuntime remains the sole lifecycle authority; centralizing Task creation does not authorize direct lifecycle mutation.

The schema must be deployed before any triage creator is enabled. Existing non-triage producers may omit the new nullable fields, but must delegate Task persistence through Control Room.

## 5. Test and review requirements

Before the migration/creator contract can be frozen, the implementation design and later tests must prove:

1. Upgrade from the exact current Alembic head with existing rows from each representative non-triage Task type; all retain NULL identity fields and remain loadable.
2. All nine inventoried producers delegate to named Control Room operations; each preserves prior authorization and transaction behavior, and existing non-triage Tasks retain NULL identity fields.
3. A `triage_signal` Task with either identity field missing is rejected by PostgreSQL.
4. A half-populated identity pair is rejected.
5. Two Tasks with different UUID primary keys but the same `(team_id, signal_id, identity_version)` are rejected by the composite unique constraint.
6. Reuse of the same canonical Task UUID is rejected/arbitrated by the existing primary key.
7. A duplicate `triage_signal_requested` Event for one Task is rejected by the partial unique index; a different Task may have its own request Event.
8. Migration preflight scans every triage_signal_requested Event and every triage_signal Task, aborts without mutation on any non-zero historical population, and reports orphan, cross-Task, malformed, duplicate, and identity-inconsistent evidence. Historical repair is a separate reviewed migration.
9. Control Room operations use the caller's active Session and never commit/rollback independently; Task and request Event creation roll back together; replay rejects missing, duplicate, malformed, cross-Task, or identity-inconsistent request evidence.
10. The ORM metadata and Alembic schema agree, and the tested Alembic head is the exact reviewed migration set.

The docs-only CI run for PR #187 cannot satisfy any PostgreSQL migration, index, writer-compatibility, or concurrency proof. Those require a later code-bearing, separately authorized slice and real disposable PostgreSQL execution.

## 6. Findings and remaining Stage A work

- **Migration shape:** proposed and compatible in principle with existing non-triage Task rows.
- **Existing writer inventory:** identified; no existing production writer needs to populate triage identity fields.
- **Data preflight:** exhaustive and read-only; migration aborts on any historical triage Task or request Event. Actual deployed database contents have not been inspected. Historical repair is a separate reviewed migration.
- **Control Room conformance:** D1 requires all nine existing producers to delegate through named Control Room operations. The boundary is session-bound; callers retain commit/rollback ownership. The producer mapping and staged rollout must be included in the frozen design.
- **D4b matching pins:** still open and intentionally not addressed here.
- **Stage B authorization:** remains closed. This audit does not authorize ORM/schema changes, Alembic migration, Task creator, dispatcher changes, or production behavior.

The next Stage A review should independently challenge the migration preflight/backfill failure policy, the Task/Event constraint semantics, and the complete writer inventory before D4b values are selected and the creator contract is frozen.
