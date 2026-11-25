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
    (signal_id IS NULL) = (identity_version IS NULL)
    AND (
      task_type <> 'triage_signal'
      OR (signal_id IS NOT NULL AND length(identity_version) > 0)
    )
  );
```

Add the accepted logical-pair uniqueness constraint:

```sql
ALTER TABLE tasks
  ADD CONSTRAINT uq_tasks_team_signal_identity
  UNIQUE (team_id, signal_id, identity_version);
```

The all-or-none check prevents malformed half-identities. Non-triage Tasks retain NULL values. The check does not hard-code `triage_identity_v1`; the accepted v1 value is validated by the creator/replay contract, while any future identity generation remains subject to its separately approved transition. The database unique constraint is intentionally independent of the canonical UUID primary key: the primary key arbitrates equal UUIDs, while this constraint rejects a different UUID assigned to the same logical pair/version.

### 3.2 Request Event index

Add exactly the accepted partial unique index:

```sql
CREATE UNIQUE INDEX uq_events_triage_signal_requested_task
  ON events (task_id)
  WHERE type = 'triage_signal_requested';
```

This enforces **at most one** matching request Event per Task. It does not enforce existence. The creator's single transaction must insert Task and request Event atomically, and every replay/load must verify exactly one valid request Event. Do not describe this index as an exactly-one constraint.

### 3.3 Preflight and backfill strategy

The migration must run read-only preflight checks before adding/validating uniqueness:

1. Count existing `triage_signal` Tasks.
2. Count existing `triage_signal_requested` Events grouped by Task and detect every group with count greater than one.
3. For any existing triage Task, verify exactly one request Event exists, its payload is a valid object, its `team_id`, `signal_id`, and `identity_version` identify the same Task, the Signal exists, and the stored Task ID recomputes to the accepted UUIDv5 identity.
4. Check duplicate logical tuples after deriving/backfilling identity values.
5. Check for malformed or cross-Task request Event attribution and orphan/inconsistent identity evidence.

**No blind backfill is permitted.** The source audit found no production triage writer, so the expected new-install/upgrade case is zero historical triage Tasks and therefore no rows to backfill. That expectation must be verified against the target database, not assumed. If preflight finds any triage Task, the migration must stop before mutating data. The rows must be reviewed and a separately tested, explicit backfill mapping must be prepared from trustworthy immutable request evidence. Do not guess missing Signal IDs, identity versions, or requester provenance; do not rewrite Task IDs or Events to make the migration pass.

For duplicate request Events, stop and report the affected Task IDs/counts. Do not delete, merge, or select a "winner" automatically. Resolve the history only through an explicit data-repair decision with preserved evidence, then rerun preflight.

If all preflight checks pass with zero historical triage rows and no duplicate request Events, add the nullable columns, FK, check, composite unique constraint, and partial unique index in the migration. Keep the migration transactional. A concurrent-index deployment path is unnecessary unless production table size/availability requirements demonstrate that a normal index build is unsafe; do not add that complexity speculatively.

### 3.4 Rollout and ORM compatibility

The ORM mapping must declare both fields nullable. Existing constructors and `pg_insert(Task)` writers may omit them and will continue to insert NULL. The database check makes omission invalid only for a `triage_signal` row.

The rollout order for a future authorized implementation is:

1. Run preflight on the target database and stop on any unexpected triage history or duplicate request Event.
2. Apply the additive nullable-column/constraint/index migration.
3. Deploy the ORM mapping and tests with the existing writers unchanged.
4. Add the new Control Room triage creation operation, which must always supply both identity fields and the canonical UUIDv5 Task ID.
5. Verify PostgreSQL constraint/index behavior and atomic exactly-one creation/replay on the exact tested migration head.

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

### 4.2 Control Room boundary observation

The accepted D1 decision makes the application Control Room the single logical authority for Task creation. The source audit shows that this target is **not yet enforced as one physical write choke point**: the existing producers above construct or insert Tasks in several modules, including TaskRuntime follow-on creation. This is an existing architectural conformance gap, not a reason to reopen D1 and not something the additive schema migration can solve.

Stage B must place the new triage creation behind one named Control Room operation. That operation must preserve the RW-5 lock order and the atomic Task/Event transaction; it must not add a direct writer in a worker, matcher, ingestion path, or feature service. The Stage B contract must also state how this Control Room operation owns or participates in the caller's transaction. Do not move TaskRuntime's existing follow-on creation across transaction boundaries as an incidental schema change. A broader retrofit of the legacy producers may be separately staged, but this audit does not authorize that refactor or claim that D1 is already physically enforced.

## 5. Test and review requirements

Before the migration/creator contract can be frozen, the implementation design and later tests must prove:

1. Upgrade from the exact current Alembic head with existing rows from each representative non-triage Task type; all retain NULL identity fields and remain loadable.
2. Existing Task creation paths remain valid without adding fake identity values: all three OperatorApplication paths, PlanService materialization, TaskRuntime follow-on paths, and KnowledgeRevalidationService creation.
3. A `triage_signal` Task with either identity field missing is rejected by PostgreSQL.
4. A half-populated identity pair is rejected.
5. Two Tasks with different UUID primary keys but the same `(team_id, signal_id, identity_version)` are rejected by the composite unique constraint.
6. Reuse of the same canonical Task UUID is rejected/arbitrated by the existing primary key.
7. A duplicate `triage_signal_requested` Event for one Task is rejected by the partial unique index; a different Task may have its own request Event.
8. Migration preflight detects duplicate request Events and unexpected pre-existing triage rows before mutation; no history is silently discarded.
9. Task and request Event creation roll back together; replay rejects missing, duplicate, malformed, cross-Task, or identity-inconsistent request evidence.
10. The ORM metadata and Alembic schema agree, and the tested Alembic head is the exact reviewed migration set.

The docs-only CI run for PR #187 cannot satisfy any PostgreSQL migration, index, writer-compatibility, or concurrency proof. Those require a later code-bearing, separately authorized slice and real disposable PostgreSQL execution.

## 6. Findings and remaining Stage A work

- **Migration shape:** proposed and compatible in principle with existing non-triage Task rows.
- **Existing writer inventory:** identified; no existing production writer needs to populate triage identity fields.
- **Data preflight:** required; actual deployed database contents have not been inspected by this source audit.
- **Legacy Control Room consolidation:** architectural observation recorded; no broad refactor proposed or authorized.
- **D4b matching pins:** still open and intentionally not addressed here.
- **Stage B authorization:** remains closed. This audit does not authorize ORM/schema changes, Alembic migration, Task creator, dispatcher changes, or production behavior.

The next Stage A review should independently challenge the migration preflight/backfill failure policy, the Task/Event constraint semantics, and the complete writer inventory before D4b values are selected and the creator contract is frozen.
