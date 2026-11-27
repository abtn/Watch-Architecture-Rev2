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
- Add a narrow `BEFORE INSERT FOR EACH ROW` trigger on `tasks` for `task_type = 'triage_signal'` that locks the referenced Team row `FOR NO KEY UPDATE` before the Task insert proceeds.

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

### 3.2 Team-lock enforcement for triage Task inserts

The creator's post-Team-lock recheck can safely classify a newly visible Task as a serialized winner only if every triage Task INSERT is guaranteed to participate in the same Team lock. Application convention alone cannot establish that: a direct SQL writer could insert the canonical row without taking the Team lock, and its row would be indistinguishable from a conforming winner when the creator later acquires Team and rechecks.

Therefore the migration design includes one narrow PostgreSQL `BEFORE INSERT FOR EACH ROW` trigger, restricted to `NEW.task_type = 'triage_signal'`. It must select the referenced Team row `FOR NO KEY UPDATE` and fail closed if no Team row exists. The trigger runs in the inserting transaction before the Task row is inserted; if it waits for another transaction's Team lock, the insert cannot pass the trigger until that lock is released. On the normal Control Room path the canonical helper already holds this same Team lock, so the trigger's acquisition is re-entrant. It does not add a second application lock helper.

This trigger enforces only the lock-participation invariant. It does not authorize a caller, prove Control Room ownership, validate Team state/domain/source policy, choose TeamPolicy, or replace any creator/replay checks. D1 is a trusted-application-code boundary, not a database-enforced authorization boundary: the current shared runtime database role does not distinguish a Control Room INSERT from direct SQL issued by another holder of that role. Out-of-band SQL writers, manual database writes, and external host writers are outside the supported threat model and must be operationally excluded. If such a writer inserts a valid-looking triage Task first, the trigger serializes it but cannot attest its origin; the Control Room cannot reliably distinguish it from a conforming row using the current schema. Treat any such write as an integrity incident, not as a supported winner or proof of Control Room authorization. If deployment requires protection against a compromised or non-conforming writer holding the runtime role, stop and design a separately reviewed database-role/function boundary; this audit does not claim one. All those remain Control Room responsibilities. The trigger must be installed and enabled by the same Task-schema migration. The migration/schema owner must be distinct from the runtime application role: the runtime role must not own `tasks`, be a superuser, be a member of the table-owner/superuser role, or have permission to alter the table or disable the trigger. If the deployed role model cannot enforce that separation, this trigger cannot be treated as a reliable guard and the design must stop for a different database-enforced boundary. PostgreSQL requires `UPDATE` privilege on at least one Team column, in addition to `SELECT`, for an invoker to execute `SELECT ... FOR NO KEY UPDATE` ([SELECT locking-clause privileges](https://www.postgresql.org/docs/current/sql-select.html)). Do not grant broad Team-update privileges solely to make the trigger work. Either prove the runtime role already has an appropriately narrow privilege or use a narrowly owned `SECURITY DEFINER` trigger function with schema-qualified references and a fixed safe `search_path`; that function must do only the Team-row lock and missing-Team check. Its ownership, grants, and search-path safety are part of the review. Its lock mode and interaction with the existing Task → Team order must be proven on the supported PostgreSQL version before implementation freeze. The supported triage creator inserts one Task per operation; bulk multi-Team triage inserts are outside this contract. Non-triage Task inserts are unaffected.

The mechanism relies on ordinary PostgreSQL trigger/locking semantics: row-level `BEFORE` triggers execute immediately before the row operation and in the same transaction as the statement ([trigger behavior](https://www.postgresql.org/docs/16/trigger-definition.html)); `INSERT ... ON CONFLICT` runs row-level `BEFORE INSERT` triggers for attempted inserts before conflict arbitration, including `DO NOTHING` ([INSERT](https://www.postgresql.org/docs/16/sql-insert.html)); and `FOR NO KEY UPDATE` conflicts with another `FOR NO KEY UPDATE` on the same Team row ([row-level lock matrix](https://www.postgresql.org/docs/16/explicit-locking.html)). The implementation proof must still verify these semantics with two real sessions on the repository's supported PostgreSQL version.

The trigger is required because otherwise the post-lock recheck cannot establish that every triage INSERT participated in Team serialization. It does not establish that the writer was Control Room. Do not infer either authorization or lock participation from Task/Event shape, `as_of`, or Team revision metadata; those values are not proof of writer identity or lock ownership.

### 3.3 Request Event index

Add exactly the accepted partial unique index:

```sql
CREATE UNIQUE INDEX uq_events_triage_signal_requested_task
  ON events (task_id)
  WHERE type = 'triage_signal_requested';
```

This enforces **at most one** matching request Event per Task. It does not enforce existence. The creator's single transaction must insert Task and request Event atomically, and every replay/load must verify exactly one valid request Event. Do not describe this index as an exactly-one constraint.

### 3.4 Preflight, migration-time guard, and backfill policy

An operator-run preflight is a read-only diagnostic gate, not the safety mechanism that authorizes DDL. A separate preflight and later migration have a time-of-check/time-of-use gap: rows could be written after the report and before the migration. Therefore the migration itself must repeat and enforce the zero-history assertion inside the same PostgreSQL transaction that applies the schema changes.

The migration transaction must:

1. Acquire explicit `ACCESS EXCLUSIVE` locks on both `tasks` and `events`, in that fixed order, before performing its authoritative checks. The locks wait for earlier writers to finish and prevent new inserts/updates/deletes on either table until the migration commits or rolls back. Do not rely on the isolation level alone or on an operator promise that writers are idle.
2. After both locks are held, enumerate the complete populations covered by the new constraints/index: every Task with `task_type = 'triage_signal'` and every Event with `type = 'triage_signal_requested'`. Run the full integrity diagnostics below, including duplicate and malformed evidence checks.
3. Abort the migration transaction before any DDL or data mutation if either population is non-empty or any violation is found. The exception must propagate so PostgreSQL rolls back the transaction and releases both locks.
4. Only after the in-transaction assertion proves zero historical triage Tasks, zero request Events, and zero violations may the migration add the nullable columns, FK, check, composite unique constraint, partial unique index, trigger function, and triage-only BEFORE INSERT trigger. Keep the normal transactional index build; do not use `CREATE INDEX CONCURRENTLY` in this transaction.
5. Keep both table locks through migration commit. The migration runner must use the repository's transactional Alembic migration behavior; if that assumption changes, stop and redesign the guard rather than splitting the assertion from DDL.

The explicit table locks close the gap for database writers that use ordinary PostgreSQL transactions, including writers outside this repository. The migration must be tested against two sessions: hold a writer open before migration lock acquisition and prove the migration waits; then prove a writer started after lock acquisition blocks until commit/rollback. If the assertion aborts, verify the schema and data are unchanged and the locks are released. The standalone operator preflight remains useful for an early human-readable report but is not sufficient to protect the migration.

The authoritative in-migration diagnostic must enumerate and check:

1. Count every Task with `task_type = 'triage_signal'`.
2. Enumerate every Event with `type = 'triage_signal_requested'`, grouped by `task_id`; detect duplicates, null/missing attribution, and malformed rows.
3. For each such Event, verify its referenced Task exists and is a `triage_signal` Task; reject orphan Events and Events attached to any other Task type.
4. Validate payload shape and required identity/provenance fields. Where a Task exists, verify exact agreement among Event attribution, Task ID, Team ID, Signal ID, identity version, and recomputed canonical UUIDv5. Verify referenced Signal existence and reject missing, malformed, cross-Task, or inconsistent evidence.
5. Report duplicate logical identity tuples and all violations that would prevent the proposed FK/check/unique constraints.

The permitted migration state is zero historical triage Tasks and zero request Events, so the additive migration performs no backfill. If the assertion finds any triage Task or request Event, including an otherwise valid-looking historical pair, stop and preserve the database unchanged. Produce a diagnostic report with affected IDs/counts. Do not delete, merge, select a winner, rewrite Task IDs, or synthesize requester provenance.

A later repair proposal must identify the trustworthy immutable source for every field, define Event cardinality/provenance treatment, preserve evidence, and include rollback procedures. Prove the repair on a disposable database copy. It requires independent review and explicit authorization.

The preflight and in-migration assertion must scan all `triage_signal_requested` Events because the partial index applies to every row of that type, including malformed Events attached to non-triage Tasks. Checking only duplicate groups or joining from triage Tasks is insufficient. The Signal FK proves only Signal existence; the composite unique constraint proves only logical-pair uniqueness. Neither proves Team eligibility, Signal-to-Team domain equality, or TeamPolicy source-allowlist membership. Those remain creator-level validations under the canonical Team lock.

### 3.5 Rollout and ORM compatibility

The ORM mapping must declare both fields nullable. Existing constructors and `pg_insert(Task)` writers may omit them and will continue to insert NULL. The database check makes omission invalid only for a `triage_signal` row.

The rollout order for a future authorized implementation is:

1. Run preflight on the target database and stop on any unexpected triage history or duplicate request Event.
2. Apply the additive nullable-column/constraint/index migration.
3. Deploy the ORM mapping and tests with the existing writers unchanged.
4. Deploy the complete Control Room Task-creation authority path described in §4.2, including all inventoried producers delegating to named Control Room operations. Do not enable only a triage-specific path while leaving legacy producers as independent Task writers.
5. Enable triage creation only after the migration is present; the operation must always supply both identity fields and the canonical UUIDv5 Task ID.
6. Verify PostgreSQL constraints/indexes, the enabled triage Team-lock trigger, writer compatibility, and atomic exactly-one creation/replay on the exact tested migration head.

Do not make the columns globally NOT NULL, add fake defaults, or retrofit unrelated Task types with fabricated Signal identity. Do not combine this schema migration with SignalDisposition persistence (RW4-1), the RW-5 lock-helper implementation, or the Stage B creator implementation.

## 4. Existing production Task-writer inventory

The audit searched the production source for `Task(`, `pg_insert(Task)`, and Task creation patterns at the audited baseline. The following direct producers were found:

| Existing producer / caller | Task type | Control Room-owned operation | Required delegation and compatibility |
|---|---|---|---|---|
| `OperatorApplicationAdapter` update_thread path (currently exposed as `create_update_thread_task`) | `update_thread` | `create_update_thread_task` | Adapter method delegates to Control Room; it is not itself the persistence authority. Leave both identity fields NULL. |
| LearningChange decision request in `OperatorApplication` | `approve_learning_change` | `create_approve_learning_change_task` | OperatorApplication delegates; Control Room owns persistence. Leave both identity fields NULL. |
| Operator update request in `OperatorApplication` | `operator_update` | `create_operator_update_task` | OperatorApplication delegates; Control Room owns persistence. Leave both identity fields NULL. |
| Plan materialization in `PlanService` | Currently `ingest_source` | `create_ingest_source_task` | PlanService delegates per child Task inside the existing plan transaction. Leave both identity fields NULL. |
| TaskRuntime follow-on evaluation | `evaluate_outcome` | `create_evaluate_outcome_task` | TaskRuntime delegates using its existing Session/transaction. Leave both identity fields NULL. |
| TaskRuntime Knowledge Quality follow-on | `assess_knowledge_quality` | `create_assess_knowledge_quality_task` | TaskRuntime delegates using its existing Session/transaction. Leave both identity fields NULL. |
| TaskRuntime Knowledge Revalidation follow-on | `assess_knowledge_revalidation` | `create_assess_knowledge_revalidation_task` | TaskRuntime delegates to the shared operation using its existing Session/transaction. Leave both identity fields NULL. |
| TaskRuntime Knowledge Lifecycle follow-on | `assess_knowledge_lifecycle` | `create_assess_knowledge_lifecycle_task` | TaskRuntime delegates using its existing Session/transaction. Leave both identity fields NULL. |
| `KnowledgeRevalidationService` task producer | `assess_knowledge_revalidation` | `create_assess_knowledge_revalidation_task` | Service delegates to the same Control Room persistence operation as TaskRuntime. Leave both identity fields NULL. |
| `KnowledgeLifecycleAssessmentService.create_task` | `assess_knowledge_lifecycle` | `create_assess_knowledge_lifecycle_task` | Service delegates only new Task/Event persistence after its existing LearningChange lock, deterministic identity, and replay validation, using its current Session/transaction. Leave both identity fields NULL. |

The Knowledge Revalidation Task type has two source-level producer workflows: the dedicated service and the TaskRuntime follow-on path. Their business workflows remain separate; this audit does not consolidate or refactor them. Both delegate Task persistence to the same named Control Room operation, and both remain compatible with the same nullable schema.

No other production Task constructor or `pg_insert(Task)` writer was found in the audited source search. This is a bounded source audit, not a proof against dynamically constructed SQL, external host code, or writes made outside this repository.



**Implementation-scope addendum (2026-11-27):** A subsequent complete producer-path review found `KnowledgeLifecycleAssessmentService.create_task` as a tenth supported Task producer that was not present in the original source inventory. It is included above because D1 covers every supported Task creator. Its workflow remains separate from the TaskRuntime lifecycle follow-on; both use the same named `create_assess_knowledge_lifecycle_task` persistence operation. The original source-audit findings above describe the historical audited baseline; implementation and proof are tracked on the separately authorized D1 branch.
### 4.1 Existing Event writers

Existing code writes many Task-attributed Events, but the audited source contains no production occurrence of Event type `triage_signal_requested`. The partial index therefore does not constrain existing Event types. The preflight is still mandatory because database contents may not exactly match the checked-in source.

### 4.2 Control Room authority and transaction boundary

D1 is an accepted architectural decision, not merely a requirement for the new triage entrypoint. The Control Room is the sole logical authority for every supported application Task creation. All ten inventoried producers in §4 must delegate to named operations owned by Control Room. This is an application-code trust boundary, not a database permission boundary: the current shared runtime role cannot distinguish a Control Room call from a direct SQL statement by other code using that role. Direct SQL, manual DB writes, and external writers are unsupported and must be operationally excluded. The trigger only serializes their INSERT if one nevertheless occurs; it cannot prove or grant Control Room authority. The source components remain callers; they do not become Control Room merely by renaming an existing method, and they must have no direct Task-persistence fallback. This was a staged conformance requirement in the original documentation-only audit. The Operator separately authorized implementation of the existing-writer D1 slice on 2026-11-27; the authorization does not include triage creation or RW4-2 Stage B.

The table in §4 is the authority mapping: its operation column names the Control Room owner, while its producer column identifies the delegating caller. In particular, the existing `OperatorApplicationAdapter.create_update_thread_task` entrypoint must delegate to the Control Room-owned `create_update_thread_task` operation; retaining the insert in the adapter or simply renaming that method does not satisfy D1. PlanService, TaskRuntime, OperatorApplication, and KnowledgeRevalidationService follow the same caller/owner split.

The two Knowledge Revalidation producer workflows remain separate and retain their existing business responsibilities. They converge only at the shared Control Room-owned `create_assess_knowledge_revalidation_task` persistence operation. This is not a proposal to consolidate their workflows. Each Control Room operation preserves the existing caller's authorization, idempotency, and transaction semantics. TaskRuntime follow-on creation delegates through Control Room using the existing Session.

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
5. A non-triage Task with either or both identity fields populated is rejected; existing non-triage writers that omit both fields remain valid.
6. Two Tasks with different UUID primary keys but the same `(team_id, signal_id, identity_version)` are rejected by the composite unique constraint.
7. Reuse of the same canonical Task UUID is rejected/arbitrated by the existing primary key.
8. A duplicate `triage_signal_requested` Event for one Task is rejected by the partial unique index; a different Task may have its own request Event.
9. The operator preflight and migration-time guard scan every triage_signal_requested Event and every triage_signal Task, report orphan, cross-Task, malformed, duplicate, and identity-inconsistent evidence, and abort without mutation on any non-zero historical population. A two-session PostgreSQL test proves ACCESS EXCLUSIVE lock waiting/blocking behavior and verifies an assertion failure leaves schema and data unchanged. Historical repair is a separate reviewed migration.
10. Control Room operations use the caller's active Session and never begin, commit, or roll back independently; Task and request Event creation roll back together. The migration-time zero-history assertion runs after ACCESS EXCLUSIVE locks on tasks then events and before DDL, within the same transactional Alembic migration. Replay rejects missing, duplicate, malformed, cross-Task, or identity-inconsistent request evidence. The triage-only BEFORE INSERT trigger acquires Team `FOR NO KEY UPDATE` for every triage Task INSERT, including direct SQL inserts that omit the application helper; a two-session PostgreSQL test proves such an insert blocks behind a creator-held Team lock. Only the protected post-Team-lock recheck returns retry-required; the outer transaction owner rolls back and reinvokes through a fresh Session/transaction, at most three total invocations. A final PK conflict after that recheck is a terminal protocol/integrity failure with no retry, replay, or request Event. Control Room never performs rollback or retries internally.
11. After a valid Task exists, change the Team to a non-active state under the canonical Team lock and prove an otherwise authorized replay fails closed without disclosing/resolving the Task; also prove replay validates the original policy pin after a newer TeamPolicy version is published.
12. Run trigger tests as the actual runtime database role. Prove it is not the table owner/superuser, is not a member of the owner/superuser role, and cannot alter/disable the trigger; prove the trigger function can acquire the Team lock without granting broader Team mutation privileges than intended. If `SECURITY DEFINER` is used, review its owner, fixed `search_path`, schema qualification, and grants.
13. The ORM metadata and Alembic schema agree, the triage Team-lock trigger is installed/enabled, the runtime application role is not the table owner/superuser, is not a member of the owner/superuser role, and cannot disable it, and the tested Alembic head is the exact reviewed migration set.
14. Every triage creator transaction is READ COMMITTED. Before any application data read, lock, or write, it executes `SHOW transaction_isolation` and rejects any value other than `read committed`. A two-session PostgreSQL test starts the losing creator's transaction and performs its initial absent Task probe before the winner commits; after the loser acquires Team, its next statement must see the winner under READ COMMITTED and return the typed retry-required result. Prove every retry uses a fresh READ COMMITTED Session/transaction. Prove REPEATABLE READ and SERIALIZABLE are rejected before application data access; do not claim this protocol supports them.
15. Add the reverse-order trigger test: a direct SQL insert takes the Team lock first, then inserts/commits a triage Task. The test demonstrates that the trigger serializes the row but does not attest Control Room origin; a later Control Room lookup cannot distinguish that valid-looking row from a conforming one under the current shared DB role/schema. Do not claim that the application rejects or safely authorizes the row—the current design has no origin signal with which to do so. The direct SQL writer is explicitly outside the supported trust boundary and must be operationally excluded; the test is a negative boundary demonstration, not an accepted creation path. Operational controls and the source-level ten-writer conformance gate must exclude such writers. If that exclusion is not acceptable for the deployment threat model, Stage A cannot be frozen until a separately reviewed database authorization boundary is designed.

The docs-only CI run for PR #187 cannot satisfy any PostgreSQL migration, index, writer-compatibility, or concurrency proof. Those require a later code-bearing, separately authorized slice and real disposable PostgreSQL execution.

## 6. Findings and remaining Stage A work

- **Migration shape:** proposed and compatible in principle with existing non-triage Task rows; it includes a triage-only Team-lock trigger so Team-lock participation is enforced rather than inferred. The trigger does not enforce Control Room-only creation.
- **Existing writer inventory:** identified; no existing production writer needs to populate triage identity fields.
- **Data preflight:** operator preflight is exhaustive and read-only, but is not the migration safety boundary. The migration repeats the zero-history assertion after taking ACCESS EXCLUSIVE locks on tasks then events and before DDL, holding both locks through transactional commit. Any historical triage Task/request Event or integrity violation aborts the transaction without schema/data mutation. Actual deployed database contents have not been inspected. Historical repair is a separate reviewed migration.
- **Control Room conformance:** D1 requires all ten supported application producers to delegate through named Control Room operations. The boundary is session-bound; callers retain commit/rollback ownership. This is trusted application-code enforcement, not a DB-level permission guarantee. Out-of-band SQL writers are unsupported and operationally excluded; the current schema cannot attest their origin if they nevertheless write. The producer mapping and staged rollout must be included in the frozen design.
- **Transaction isolation:** the triage creator/recheck protocol explicitly supports READ COMMITTED only. Higher-isolation caller transactions must be rejected before application data access; each retry uses a fresh READ COMMITTED transaction.
- **D4b matching pins:** still open and intentionally not addressed here.
- **Stage B authorization:** remains closed. This audit does not authorize ORM/schema changes, Alembic migration, Task creator, dispatcher changes, or production behavior.

The next Stage A review should independently challenge the migration preflight/backfill failure policy, the Task/Event constraint semantics, and the complete writer inventory before D4b values are selected and the creator contract is frozen.


## F2 alignment with the accepted D1 trust boundary (2026-11-26)

The Control Room is a trusted application-code authority, not a PostgreSQL identity that grants can identify. The same database principal used by Control Room code can also issue arbitrary SQL; PostgreSQL table grants and triggers cannot distinguish those call sites. Accordingly, the accepted F2 target is:

- Use a non-owner, non-superuser watch_runtime credential for Watch application processes only; keep owner/migrator credentials separate and unavailable to application runtime.
- Operationally exclude ad-hoc SQL clients, scripts, host services, and other unsupported processes from receiving or using the runtime credential. Host adapters authenticate and delegate to Watch; they do not write Thread rows.
- PostgreSQL enforces physical facts (domain guard, immutable history, constraints, protected-field guards, and TRUNCATE/bypass restrictions). Control Room enforces caller authorization, Task attribution, operation mode, and canonical application transaction use.
- If the threat model requires rejecting arbitrary SQL from a process that already holds watch_runtime, a separate credential/process or narrowly scoped database capability must be designed and reviewed. Do not claim ordinary grants solve this.
- F2 is partially resolved as of 2026-11-26: the Operator confirmed there is no production deployment, and the checked-in development/bootstrap, CI, migration, test, smoke-script, and Thread-writer inventory is recorded in [RW4-1B §10.4](rw4-1b-physical-schema-and-integrity-design.md). F2 remains OPEN/BLOCKING because the checked-in development topology uses bootstrap superusers, does not separate runtime/migration/test principals, and has no installed Thread domain/lifecycle guards or effective-privilege proof. The repository audit cannot enumerate untracked processes or manually provisioned local credentials.

The accepted resolution design is an exclusive resolve_thread operation mode within the existing operator_update Task, reusing its business-commit marker/recovery path. It does not add a Task type or runtime. The exact transition, Event, idempotency, Team-revision, and split business-commit/TaskRuntime-terminalization contract is specified in the RW4-1B design proposal §10.2.

## Development-only F2 inventory reconciliation (2026-11-26)

The Operator confirmed Watch has no production deployment. The checked-in source/configuration inventory is recorded in [RW4-1B physical design §10.4](rw4-1b-physical-schema-and-integrity-design.md#104-development-only-database-credential-process-and-thread-writer-inventory-2026-11-26). Key results:

- No production Thread row creator or `Thread.status`/`Thread.domain` writer exists in the audited application source. `activate_team` and Operator `resolve_thread` are accepted future owners, not implemented writers.
- Current application services receive injected sessions; the repository does not contain a runnable Watch host process/adapter composition that provisions a runtime database identity.
- Compose `watch`, Alembic's default `DATABASE_URL`, the local disposable runner, and CI all use bootstrap PostgreSQL superusers. CI is ephemeral, but not least-privilege.
- The main pytest fixture fails closed on `TEST_DATABASE_URL`, but migration tests need elevated disposable-database privileges. `tests/test_database.py` and `core/embedding_smoke.py` retain unsafe persistent-`watch` fallbacks through `DATABASE_URL`.
- The base Thread schema has Team FK/unique/check constraints only. No Thread domain immutability guard, lifecycle transition guard, restricted runtime grants, owner/migrator role split, or physical bypass protection has been implemented.
- Consequently, repository inventory is complete for the checked-in tree, production deployment uncertainty is resolved, but F2 remains blocking pending local process/credential reconciliation and actual PostgreSQL role/trigger implementation and proof.

The two fallback paths above are narrow developer-tool safety defects and should be hardened in a separately authorized change. This RW4-1B audit remains documentation-only; it does not silently change application, test, migration, or database behavior.



## Post-audit implementation reconciliation (2026-11-27)

This document records the source audit as it stood on 2026-11-25; its historical audit baseline and findings are not rewritten. The following delivery has since occurred:

- **D1 existing-writer migration:** all ten inventoried production Task producers now delegate to the eight named operations in `core/control_room.py`. PR [#207](https://github.com/abtn/Watch-Architecture-Rev2/pull/207) (including correction #208) merged at `d03297c2b4e3522b0dc59ce001955cda130fd14f`. Exact-head CI #2326 passed the PostgreSQL, migration, Ruff, Mypy, patch-whitespace, and full-test checks. The exact ten-producer mapping and retained caller transaction semantics are recorded in [the D1 implementation record](d1-control-room-writer-conformance-implementation.md).
- **D2 schema migration:** PR [#203](https://github.com/abtn/Watch-Architecture-Rev2/pull/203) merged at `5d3370127718cee839834b6473b8b5883be95d0b`, adding migration `0020_rw4_task_identity.py`. It installs nullable identity columns, Signal FK, triage-only identity CHECK, logical-pair unique constraint, four-column support key, partial unique request-Event index, triage-only Team-lock insert trigger, identity immutability, locked zero-history preflight, and fail-closed downgrade. PR #203 records the PostgreSQL proofs for these schema/migration properties.
- **Still not implemented:** the typed `triage_signal` creator, runtime request Event validation, Task/Event creation path, exact replay, caller authorization integration, creator race/retry handling, and creator-specific two-session PostgreSQL proofs. The D2 migration and D1 writer retrofit do not prove these behaviors.

The exact Event v1 payload/fingerprint and creator lock/retry contract are frozen for independent Stage A review in [RW4-2 Stage A contract closure](rw4-2-stage-a-contract-closure.md). The migration's locked zero-history assertion is evidence about the database state at the time that migration ran; it is not an attestation of any separate persistent or production deployment. Historical repair remains unsupported. No Stage B implementation is authorized by this reconciliation.
