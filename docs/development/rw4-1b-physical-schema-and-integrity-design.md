# RW4-1B — SignalDisposition physical schema and relational-integrity design

**Status:** Proposed physical design for review. Operator-accepted decisions include the logical SignalDisposition row shape; conditional Option A with a forward-only DB-attested provenance cutover; the duplicate-write gate; the D2 Task-identity/FK prerequisite; and database-enforced immutability, truncation protection, and timestamp assignment as a design direction. Exact physical enforcement remains subject to source review and PostgreSQL proof.  
**Depends on:** accepted D3-A/B/C, D5.1–D5.4, D6.1–D6.6; completed RW4-1A source audit.  
**Design baseline:** RW4-1A audited main baseline d2a6f7d4f939a7c18ea00ad6c77574c7b1f63ec3; implementation must re-audit the actual merge base and current Alembic head.  
**Scope:** SignalDisposition row representation, database constraints, cross-record integrity strategy, immutable evidence, TaskRuntime transaction/replay seam, migration boundary, and a bounded PostgreSQL proof matrix.  
**Not in scope:** code, ORM, migration, SQL, test implementation, database execution, Task creation/dispatch, D2 Task identity migration, D4.1a canonical Team/hash arbitration, RW-5 locks/revision/writer retrofit, RW4-2 Stage B, RW4-3 matching, or RW4-5 reactivation.  
**Authorization:** This proposal does not authorize implementation.

## 1. Purpose and design rule

RW4-1 persists one immutable business disposition for a Team's intake of a Signal. It must not turn the global Signal model into a Team-owned record, infer canonical first-commit order from application timestamps, weaken accepted Task identity, or create a second Task lifecycle authority.

The physical design must distinguish row-local facts enforceable by PostgreSQL constraints, cross-record facts requiring a relational witness/trigger or transaction validation with a proved lock/isolation protocol, independent prerequisites that RW4-1 must not reimplement, and terminal atomicity owned by TaskRuntime.

The preferred solution is the smallest design that proves the accepted invariants. Do not add a generic integrity framework or a new TeamSignal registry merely to avoid specifying the actual relationship.

## 2. Accepted contract to preserve

- Exactly three dispositions: matched, duplicate, deferred.
- D5.2 reference matrix:
  - matched: thread_id required; duplicate_of_signal_id and reason_code NULL.
  - duplicate: duplicate_of_signal_id required; thread_id and reason_code NULL.
  - deferred: reason_code required; thread_id and duplicate_of_signal_id NULL.
  - decided_by_task_id required for all.
- Six accepted deferred reason codes only. Use the exact D5.3 vocabulary from the accepted specification; do not create aliases or add a seventh reason.
- One immutable disposition per Team/Signal pair.
- Deferred is a successful terminal business result; TaskRuntime completes the Task as done.
- Disposition, Task attribution/reason, one task_execution Outcome, Task terminal state/completion time, and one task_completed Event commit or roll back together.
- TaskRuntime alone owns Task lifecycle and terminal Event writes.
- Human-readable explanation and complete terminal result belong in immutable Task-attributed observation/Outcome evidence. The disposition row stores the stable machine-readable reason code. Outcome fields must agree exactly with the persisted disposition value, reason, and reference.
- Technical/integrity failures do not create a disposition.
- Dormant Thread matching does not reactivate in RW4-1. Until separately authorized and proven RW4-5, dormant would-be winner remains deferred with dormant_thread_requires_reactivation.
- No Signal status, Signal Team column, Thread timestamp mutation, new Thread, new Task creator, or TaskDispatcher expansion.

## 3. Proposed row shape

Recommended logical row (names illustrative until review):

| Column | Type / nullability | Purpose |
|---|---|---|
| id | UUID primary key | Stable disposition record identity. |
| team_id | UUID NOT NULL | Team whose intake is being decided. |
| signal_id | UUID NOT NULL | Global Signal being decided. |
| disposition | TEXT NOT NULL | One of the three accepted values; use CHECK, not a PostgreSQL ENUM, so future separately accepted vocabulary changes do not require enum-type surgery. |
| thread_id | UUID NULL | Required only for matched. |
| duplicate_of_signal_id | UUID NULL | Required only for duplicate. |
| reason_code | text NULL | Required only for deferred; exact D5.3 values. |
| decided_by_task_id | UUID NOT NULL | Canonical triage Task attribution. |
| identity_version | text NOT NULL | Fixed to `triage_identity_v1`; binds this disposition to the D2 Task identity contract. |
| created_at | timestamptz NOT NULL | Database-assigned immutable creation timestamp. |

Required row-local constraints and names:

- `pk_signal_dispositions` — primary key on `id`.
- `uq_signal_dispositions_team_signal` — unique `(team_id, signal_id)`.
- `ck_signal_dispositions_disposition` — exact three disposition values.
- `ck_signal_dispositions_reference_matrix` — complete D5.2 nullability/reference matrix.
- `ck_signal_dispositions_identity_version` — `identity_version = 'triage_identity_v1'`.
- `ck_signal_dispositions_not_self_duplicate` — `duplicate_of_signal_id IS NULL OR duplicate_of_signal_id <> signal_id`.
- `ck_signal_dispositions_deferred_reason` — exact six accepted D5.3 codes only for deferred and NULL otherwise.
- `fk_signal_dispositions_team` — `team_id → teams.id`.
- `fk_signal_dispositions_signal` — `signal_id → signals.id`.
- `fk_signal_dispositions_duplicate_signal` — `duplicate_of_signal_id → signals.id`.
- `fk_signal_dispositions_thread_team` — `(thread_id, team_id) → threads(id, team_id)`.
- `fk_signal_dispositions_task_identity` — `(decided_by_task_id, team_id, signal_id, identity_version) → tasks(id, team_id, signal_id, identity_version)`. This FK is installed by the separate D2-dependent migration after its referenced columns and unique support key exist.
- All foreign keys use restrictive delete/update behavior; no cascade deletion or key rewrite of immutable decision history.
- No `updated_at`.

The unique pair enforces at most one row per Team/Signal. A same Signal may have separate rows for different Teams. The composite Thread FK proves the matched Thread belongs to the same Team, but it does not prove same-domain or active-at-decision; the trusted Kernel finalizer must validate `Thread.domain = Team.domain` and `Thread.status = 'active'` under the canonical locks immediately before insert and hold those locks through commit. The composite Task FK proves the attributed Task belongs to this exact Team/Signal/identity-version tuple, not merely to the same Team; it does not prove which application component issued the INSERT or that TaskRuntime owns the surrounding transaction. TaskRuntime ownership, atomic Outcome/Task/Event finalization, and exact replay remain trusted-application obligations enforced by the single TaskRuntime path and proven by integration tests; arbitrary out-of-band SQL writers are outside that application trust boundary. A Signal FK alone still does not prove Team intake provenance, domain equality, or duplicate canonicality.

**Required supporting indexes on the new table:**

- `uq_signal_dispositions_team_signal` — unique B-tree `(team_id, signal_id)`; also supports Team-scoped lookup and Team FK checks.
- `ix_signal_dispositions_signal_id` — B-tree `(signal_id)` for Signal FK checks and Signal identity-immutability lookups.
- `ix_signal_dispositions_duplicate_of_signal_id` — partial B-tree `(duplicate_of_signal_id) WHERE duplicate_of_signal_id IS NOT NULL` for duplicate-target FK checks and identity-immutability lookups.
- `ix_signal_dispositions_thread_id_team_id` — partial B-tree `(thread_id, team_id) WHERE thread_id IS NOT NULL` for the composite Thread FK and the matched-Thread domain guard.
- `ix_signal_dispositions_decided_by_task_identity` — B-tree `(decided_by_task_id, team_id, signal_id, identity_version)` for the D2-dependent composite Task FK.

Do not add indexes for `created_at`, `reason_code`, or disposition alone without a demonstrated query requirement. The indexes above exist to support the declared foreign keys and narrow cross-record guards; they are not a general query-optimization project.

### 3.1 Deferred vocabulary source

The normative authority is [RW4-2 Stage A specification, D5.3 — Stable deferred reason codes](rw-4-2-decision-and-specification-draft.md), also recorded in [accepted decision issue #193](https://github.com/abtn/Watch-Architecture-Rev2/issues/193).

The exact permitted literals are:
- `no_eligible_thread`
- `ambiguous_thread_match`
- `insufficient_evidence`
- `no_compatible_evidence`
- `evidence_limit_exceeded`
- `dormant_thread_requires_reactivation`

This list is a review convenience, not a second authority. The migration CHECK and tests must match the D5.3 normative list exactly; any future change requires a new accepted decision and coordinated migration/test review. No aliases or additional values are permitted.

## 4. Cross-record integrity: options and recommendation

The hard relationships are: Team has an intake association to Signal; Signal and Team domains agree; matched Thread belongs to the same Team/domain and is eligible; duplicate target is the canonical same-Team/same-hash Signal; attributed Task is the canonical triage Task for this Signal.

### Option A — database-enforced existing-event witness

The current Event/Task relationship can remain the provenance source only if the database makes the relevant facts durable. A SELECT followed by application validation is not sufficient.

The source audit establishes that Event has a Task FK, JSONB payload, and no typed Signal FK. It does not establish a database append-only rule for Event or immutability for the Signal/Team fields on which the relationship depends. Therefore the current schema, by itself, does **not** satisfy Option A.

To retain Option A, the physical design and migration must include all of the following database protections:

1. **Intake Event insert validation:** a PostgreSQL trigger for signal_ingested and fetch_no_change validates that the referenced Task exists and is an ingest_source Task; the payload contains a valid Signal ID; the Signal exists; and payload origin_url, source_type, content_hash, and snapshot_ref agree with the stored Signal. It also validates Signal.domain == Task.team.domain. The trigger rejects malformed or cross-domain new intake Events from the ordinary fetch_no_change and ON CONFLICT-winner paths. The prior_outcome replay path creates no new Event; it relies on the original Event having passed this validation (or the exhaustive migration preflight) and on the protected Event, Signal, Task, and Team fields remaining immutable.
2. **Intake Event immutability:** a PostgreSQL trigger rejects UPDATE and DELETE of either intake Event type. It must also prevent changing an Event into or out of either protected type. The trigger is exercised under the actual runtime role, which must not own the table, be superuser, or be able to disable/replace the trigger or set `session_replication_role` to bypass it.
3. **Referenced identity stability:** database enforcement prevents changing the Signal provenance fields used by the witness (domain, source_type, origin_url, content_hash, and snapshot_ref) after an intake Event exists. It also prevents changing the owning Task's team_id or task_type while a protected intake Event exists, prevents deleting a Signal while any protected intake Event references it, and prevents changing Team.domain while protected intake provenance or a disposition exists. If the repository requires legitimate domain or Signal corrections, those require a separately designed versioned correction path; silently updating the witness is not permitted.
4. **Locking:** ingestion Event insertion follows Task → Team → Signal ordering. The current `_commit()` path already holds Task `FOR UPDATE` and Team `FOR SHARE` (`with_for_update(read=True)`). The Event trigger must use compatible, non-upgrading row locks: Task `FOR SHARE`, Team `FOR SHARE`, then Signal `FOR SHARE`. Reacquiring a compatible lock already held by the same transaction does not upgrade Team from SHARE to NO KEY UPDATE. `FOR SHARE` conflicts with updates to protected non-key identity fields, keeping those values stable through Event insertion. Do not use Team `FOR NO KEY UPDATE` in this trigger: concurrent same-Team ingestions can each hold SHARE and then deadlock trying to upgrade. Disposition assessment/finalization follows Task → Team → sorted Thread → sorted Hypothesis under canonical RW-5 modes/order and does not lock Signal between Team and Thread.
5. **Role boundary:** document the trigger owner/function security model, fixed search_path, schema-qualified references, and runtime grants. A table owner/superuser can bypass ordinary trigger protection; operationally excluding that principal from application runtime is part of the proof.
6. **TRUNCATE protection:** row-level DELETE triggers do not run for PostgreSQL `TRUNCATE`. Protect the intake witness and disposition history against this separate operation:
   - Explicitly revoke `TRUNCATE` on `events`, `signals`, and `signal_dispositions` from the application runtime role and every role it can inherit, including PUBLIC where applicable. Also revoke it on `tasks` and `teams` because their identity fields are part of the witness. The runtime role must not own these tables or be able to assume the migration/table-owner role.
   - Install a statement-level `BEFORE TRUNCATE` trigger that unconditionally raises an integrity exception on each protected table: `events`, `signals`, `signal_dispositions`, `tasks`, and `teams`. The trigger must not have a caller-settable GUC, session flag, or application-controlled bypass. Protect every partition/leaf that can be truncated directly; verify parent/partition behavior on the actual PostgreSQL version.
   - Treat `TRUNCATE ... CASCADE` as prohibited too. The proof must attempt direct TRUNCATE on each protected table and CASCADE paths that would reach them; every operation must fail and all witness/history rows must remain. Check effective privileges (including inherited grants) with PostgreSQL privilege inspection and `has_table_privilege(runtime_role, table, 'TRUNCATE')`, not only the direct ACL entry.
   - The migration/table-owner principal and superusers remain technically capable of disabling triggers or changing grants. They are outside the application runtime trust boundary, must never be used by the application, and must be restricted to audited, reviewed migrations/break-glass operations. No ordinary maintenance workflow may truncate protected history. If the operational boundary cannot be enforced, Option A is not acceptable; use a separately reviewed relational witness/retention design instead.
   - Include trigger definitions, effective grants, role membership, and the protected-table inventory in migration verification. Do not treat a row-level DELETE trigger or the migration's preflight table locks as TRUNCATE protection.

**Advantages:** preserves the current Task-attributed intake Event as the source of provenance and avoids a second Team/Signal association registry.

**Costs:** requires DB trigger/privilege design and ingestion-path regression proof. It is not merely a service-layer validation change.

### 4.0.1 Current-source and deployment feasibility audit (2026-11-25)

This audit was performed against the merged-main source following PR #198. It is source/configuration inspection only; no deployed database, live role catalog, or historical rows were inspected.

**Observed writer and lock path**

- The only production writer found for `signal_ingested` and `fetch_no_change` is `IngestionService._commit()` in `core/ingestion.py`.
- It opens one transaction, locks the Task `FOR UPDATE`, then locks the Team `FOR SHARE` through `with_for_update(read=True)`. It validates the running `ingest_source` Task, active Team, and pinned TeamPolicy.
- On a new Signal, it inserts the Signal first and then the `signal_ingested` Event in the same transaction. Existing-Signal and ON CONFLICT winner paths insert `fetch_no_change` Events in that transaction. A same-Task `prior_outcome` replay inserts no new Event and relies on the original committed Event.
- The Event payload currently contains `origin_url`, `source_type`, `content_hash`, `signal_id`, and `snapshot_ref`. `Event.created_at` is supplied by application code using `datetime.now(timezone.utc)`; it is not a database commit-order witness.
- The Event model has only its Task FK, type, JSONB payload, and timestamp. It has no typed Signal FK and no Event immutability trigger in the current migration chain.
- Signal has no Team FK or Team ID. Its provenance fields are ordinary mutable columns with no current immutability trigger. Team.domain and Task.team_id/task_type likewise have no current database immutability trigger.

**Observed database protection and role topology**

- Migration `0017_r7b_assessments` demonstrates a reusable PostgreSQL trigger pattern: a shared rejecting trigger function plus row-level UPDATE/DELETE and statement-level TRUNCATE triggers. It applies only to three R7-B assessment/provenance tables; it does not protect Events, Signals, Tasks, or Teams.
- That migration does not establish a runtime-versus-migration role split or grant/revoke policy.
- Checked-in `compose.yaml` creates PostgreSQL user `watch` as `POSTGRES_USER`. The checked-in Alembic environment defaults to `postgresql+psycopg://watch:watch@localhost:5432/watch`. The repository does not define a distinct least-privilege application runtime role and migration owner role. With the standard PostgreSQL image, the initial `POSTGRES_USER` is a superuser. Therefore the checked-in development topology cannot demonstrate that the application runtime is unable to disable triggers, change grants, or bypass the protections.
- No production deployment role catalog or production connection configuration is present in this repository. We cannot claim the production role boundary exists.

**Historical provenance limitation and accepted resolution**

The forward-only cutover removes the need to establish event-time truth for legacy intake Events. Every Event that exists before cutover remains unmarked (`intake_witness_version IS NULL`) and is ineligible as RW4-1 provenance, regardless of whether its current payload appears valid. Do not infer that a legacy Event was immutable, validate it into eligibility, or use its present-day values as a provenance witness. A malformed or historically modified legacy Event is still untrusted legacy history; it is not a reason to block the new provenance boundary.

The bounded source search found no production code path that updates Signal provenance fields or rewrites an intake Event after insertion. This remains useful for identifying supported writers that must continue to work after cutover, but it is not evidence about historical rows and is no longer a prerequisite for trusting them. Post-cutover trust comes only from the database marker assigned after trigger validation and from the protected identity fields remaining stable thereafter.

**Conclusion and design consequence**

Option A is **not presently proven feasible in the checked-in deployment topology**. Its trigger design is technically plausible, and the current ingestion lock order offers a compatible starting point. The historical boundary is now decided: only post-cutover DB-attested intake Events are eligible; all legacy Events remain NULL/untrusted and are not subject to a retroactive validity test. The remaining feasibility prerequisite is the real role boundary: a non-owner, non-superuser runtime role with no membership or privilege path to the migration/table-owner role, no trigger-disabling capability, and no ability to set replication-role bypass. Migrations must use a separate restricted owner role. The same role model must be used in disposable PostgreSQL proof.

The minimum-change recommendation remains **conditional Option A**, subject to proving the runtime/migration-owner role boundary and the already-accepted forward-only marker cutover. Do not accept Option A on the current `watch`-superuser development topology or on a preflight-only argument. If the role split or marker protection cannot be enforced, stop and return with a separately scoped Option B design. Option B still requires a non-owner runtime role and immutable database enforcement; it is not a bypass around the role boundary.

No schema, ORM, migration, application, test, database, or runtime change was made by this audit.

### 4.0.2 Operator-accepted historical boundary: forward-only DB-attested cutover

**Decision:** On 2026-11-25, the Operator accepted the forward-only cutover recommendation. Do not rely on an unverified trusted-history assumption and do not retroactively attest legacy intake Events.

This acceptance selects the historical-boundary direction within conditional Option A. It does not prove the runtime-role prerequisite, accept every physical trigger detail, or authorize implementation.

**Proposed physical mechanism for detailed review:**

- Add a nullable, database-owned witness-version column to `events`: `intake_witness_version SMALLINT NULL`, with no default and no backfill. This is provenance metadata on the existing Event witness, not a Team/Signal registry and not a SignalDisposition field.
- A `BEFORE INSERT` trigger recognizes only `signal_ingested` and `fetch_no_change`. Under compatible `Task FOR SHARE → Team FOR SHARE → Signal FOR SHARE` row locks (the existing ingestion path already holds Task `FOR UPDATE` and Team `FOR SHARE`), it validates `Task.task_type = 'ingest_source'`, `Task.status = 'running'`, the Task's Team exists and has `Team.status = 'active'`, the referenced Signal exists, the exact payload fields (`signal_id`, `origin_url`, `source_type`, `content_hash`, `snapshot_ref`) agree with the stored Signal, and `Signal.domain = Team.domain`. Only after every check succeeds does it set the v1 witness version to exactly `1`; future marker versions require a forward migration and review. The trigger must not upgrade Team's lock mode; it must preserve the audited Task → Team → Signal order.
- The trigger owns the marker value. For these protected Event types it overwrites any caller-supplied value with `1`; for every other Event type it rejects a non-NULL caller-supplied marker and stores NULL. Callers cannot choose a version, suppress attestation, or mark an unrelated Event. The migration installs the column and trigger atomically. Events committed before that cutover remain NULL; there is no UPDATE/backfill that labels legacy rows as attested.
- An intake Event with NULL or unsupported witness version cannot establish RW4-1 Team–Signal provenance. Eligibility also requires all protected Event, Task, Team, and Signal identity checks to pass; a marker is not a substitute for those checks.
- Protect the marker against UPDATE, and protect both intake Event types against UPDATE, DELETE, and type changes into or out of the protected set. Protect actual changes to the referenced Signal identity fields (`domain`, `source_type`, `origin_url`, `fetched_at`, `content_hash`, and `snapshot_ref`; `id` is already a primary key) while a DB-marked intake Event or any SignalDisposition references the Signal as its subject or duplicate target; protect actual changes to Task `team_id`/`task_type` while a DB-marked intake Event references the Task (the D2 check and composite FK protect triage Task identity after disposition creation); protect actual changes to Team `domain` while a DB-marked intake Event or any immutable SignalDisposition for that Team depends on it. Legacy unmarked Events do not activate these identity fences. Runtime must not own these objects or bypass their triggers.
- Existing ingestion `prior_outcome` replay remains an ingestion idempotency behavior; it must not manufacture a marker for a legacy Event. A legacy replay may still return its original ingestion result, but that Event remains ineligible as RW4-1 provenance. New triage eligibility must require the DB marker.
- The migration must not rewrite historical Event payloads or infer a marker from application-supplied `created_at`. It must retain legacy rows and their original timestamps unchanged.

**Cutover semantics:** the least-privilege role boundary is a deployment prerequisite, not something DDL can make atomic with an external application-connection change. Provision the NOLOGIN owner, distinct runtime login, and separate migration credential; configure the application to use the runtime login for its next start; stop all application processes/workers and drain every old owner/superuser connection before migration. Do not leave an application process running on the migration credential. The cutover migration then runs with no application writers, installs the nullable marker, validation/immutability triggers, constraints, ownership/grants, and verifies effective role memberships/privileges under the ACCESS EXCLUSIVE table locks. Only after commit may application processes restart, using the runtime login; verify active application sessions are runtime-only and cannot assume owner/migration roles. No writer can insert an unmarked protected Event after the trigger is active and no runtime caller can assign a trusted marker directly. If the deployment cannot perform this stopped-writer cutover and prove the post-migration runtime identity, stop Option A and return to the Operator with the separately scoped Option B design.

**Role topology required for the proof:**

- The role/connection rollout brackets the cutover: provision roles and configure the runtime DSN; stop/drain all application processes and old owner/superuser sessions; run the migration with no application writers; then restart the application only with the runtime login and verify through `pg_stat_activity`/effective privilege checks that no application session uses owner, superuser, or migration credentials. The migration cannot change or prove an external service's DSN merely by creating database roles.
- A `NOLOGIN` owner role owns protected tables and trigger functions; it is not used by application processes.
- A distinct runtime login is neither a table owner nor superuser and has only required application DML privileges. It has no direct or inherited membership that permits `SET ROLE` to owner/migration roles.
- A separate migration credential may assume the narrowly scoped owner role for reviewed migrations; it is never supplied to runtime services.
- Grant the runtime role only `SELECT` and `INSERT` on `events`; do not grant `UPDATE` or `DELETE`. The bounded production-source search found no production Event update/delete path (matches were test corruption/cleanup fixtures only). This makes all TaskRuntime terminal Events append-only for runtime, including triage `task_completed`; test cleanup must use the isolated owner/test-maintenance role, never the runtime role.
- Runtime has no ability to alter protected tables/functions, create/replace/disable triggers, grant/revoke privileges, change ownership, or set `session_replication_role` to bypass triggers. Effective privileges and all membership paths must be checked in PostgreSQL.
- Trigger functions that need elevated read access use a narrowly scoped `SECURITY DEFINER` function owned by the non-login owner, with a fixed safe `search_path` and schema-qualified object references. Revoke default `PUBLIC` EXECUTE in the same transaction that creates each function; grant EXECUTE to the migration/owner role that creates the trigger, and to the runtime role only if application code directly calls that function. Trigger firing itself must not be treated as requiring a direct runtime EXECUTE grant. No caller-controlled GUC or bypass flag is permitted.
- Revoke effective runtime `TRUNCATE` on all application data tables, explicitly including `knowledge_chunks`, `events`, `signals`, `signal_dispositions`, `tasks`, and `teams`, including inherited/PUBLIC grants. Retain unconditional statement-level `BEFORE TRUNCATE` rejection triggers on the five D5.5 protected tables. Verify direct, CASCADE, and partition/leaf attempts under the runtime role; the migration/maintenance owner is outside the runtime boundary.

**Required PostgreSQL proof additions:**

1. Runtime role is not superuser/table owner; cannot SET ROLE to owner; cannot alter/drop/disable triggers or functions, grant privileges, change ownership, or set replication-role bypass. `PUBLIC` cannot directly execute privileged trigger helpers; the migration owner has the required EXECUTE privilege to create triggers; the runtime can successfully perform an allowed INSERT through the trigger without receiving unnecessary direct EXECUTE on a SECURITY DEFINER helper.
2. All application processes are stopped and old owner/superuser sessions drained during migration; the runtime DSN is configured for restart, the migration role installs the cutover using the restricted owner role, and post-commit application sessions use only the runtime login.
3. New valid intake Events receive the current DB marker even if the caller supplies NULL or a forged version; non-intake Events cannot acquire the marker.
4. Invalid Task type, missing/malformed Signal reference, mismatched origin/source/hash/Snapshot, and domain mismatch are rejected and leave no Event.
5. Legacy Events remain NULL after migration and are rejected as RW4-1 provenance; newly inserted valid Events are marked and eligible only after the full witness validation.
6. Runtime cannot change marker, Event type/payload, protected Signal identity/delete, Task team/type, or Team domain; runtime cannot TRUNCATE any application data table, including `knowledge_chunks`.
7. Migration-first and writer-first interleavings prove no insertion gap: the migration holds the required table locks through commit; a conflicting writer either completes before migration lock acquisition or waits until the protected trigger is committed. The existing NOWAIT preflight policy must fail cleanly rather than hold partial locks.
8. Repeat role, marker, and immutability tests after migration from a populated legacy fixture containing both valid and malformed historical Events. Legacy rows are retained, not silently repaired or promoted.

The marker column name/type/version and exact function/trigger SQL remain design details for the independent review; this accepted direction must not be mistaken for their physical acceptance.

### Option B — relational intake-witness representation

If the Option A trigger/immutability boundary cannot be made reliable under the actual runtime-role model, stop and propose a separate typed relational intake-witness relation. It must carry explicit Team, Signal, Task, and source Event references with enforceable FKs and immutable association semantics.

That relation must **not** add a Team/content-hash uniqueness rule or choose the D4.1a canonical duplicate. It records which Team intake associated which Signal; D4.1a separately decides which Signal is canonical for a Team and exact content hash. The witness relation would require an ingestion-writer retrofit and its own migration, concurrency proof, and sequencing approval. It is not silently included in RW4-1.

### Recommendation — retain Option A only with the specified database protections

Option A is the preferred minimum only if all five protections above are implementable and proved. The current source does not yet prove them. If any protection cannot be enforced for every supported runtime writer, Option A is rejected and RW4-1 must stop for a separately reviewed Option B design. Application-only validation is not an acceptable fallback.

For either option:
- Require the intake Event to be exactly signal_ingested or fetch_no_change, attributed to the same Team through its Task.
- Validate Event Signal ID, origin, source type, content hash, and Snapshot reference against the persisted Signal.
- Validate Signal.domain == Team.domain.
- Validate Thread.team_id == team_id, Thread.domain == Team.domain, and status under the lifecycle lock protocol. Active is eligible; dormant remains deferred until RW4-5 is implemented and proven; resolved is ineligible.
- Do not accept caller-supplied provenance assertions.

### 4.1 Active-Thread lifecycle fence and RW-5 dependency

An active status read is not sufficient. A concurrent lifecycle writer could make the Thread dormant or otherwise ineligible before the disposition commits.

The RW-4/RW-5 sequencing decision already places the RW-5 canonical lock-helper, Team-revision, and writer-compatibility retrofit after RW4-1 but before RW4-2 Stage B and RW4-3. Preserve that sequence; do not move the whole RW-5 decay implementation ahead of RW4-1.

Instead, distinguish schema preparation from write enablement:

- RW4-1 may prepare the disposition schema and triage-specific persistence boundary before RW-5.
- No triage disposition writes are enabled until the D2 identity prerequisite is present and the canonical RW-5 helper plus the relevant existing-writer retrofit have landed.
- Matched writes remain disabled until every supported world-memory writer that can change Thread status/domain or matcher-relevant EvidenceLink/Hypothesis membership/lifecycle/confidence uses the canonical Team lock, sorted Thread/Hypothesis locks, and one Team revision increment. This includes `update_thread`, `operator_update`, `apply_decay`, and any future Thread status/domain writer. RW-5 decay execution itself remains in its accepted later position; this gate requires the helper and compatibility retrofit, not premature decay implementation.
- `KnowledgeIndexService.index_signal()` is a separate global projection writer: current source locks the parent Signal `FOR UPDATE`, deletes the old `KnowledgeChunk` rows, and inserts a new projection in one transaction; it does not increment Team revision. D4.2 must therefore lock every incoming/evidence Signal `FOR SHARE` in sorted UUID order and record stable chunk-identity/vector fingerprints. Any future KnowledgeChunk writer must serialize on the same parent Signal row; in-place vector mutation must not bypass that lock.
- The current indexer only deletes/recreates chunks for one Signal and already holds that parent lock. To close direct-DML bypass, require a `BEFORE INSERT/UPDATE/DELETE` KnowledgeChunk trigger that locks the parent Signal `FOR UPDATE` (reject `signal_id` changes in place; any future multi-Signal statement must pre-lock parent Signals in sorted order), or restrict all KnowledgeChunk DML to a controlled writer that demonstrably takes the same lock. Runtime must have no `TRUNCATE` privilege on `knowledge_chunks` or other application data tables. The D4.2 read locks are trailing after Hypothesis locks; the indexer holds only Signal, so this does not introduce a reverse lock dependency.

For both the receipt transaction and the later business-finalization transaction, TaskRuntime holds Task `FOR UPDATE` → Team `FOR NO KEY UPDATE` → sorted candidate/selected Thread `FOR NO KEY UPDATE` → sorted Hypothesis `FOR NO KEY UPDATE` following the frozen RW-5 order. D4.2 then acquires the incoming/evidence Signal rows `FOR SHARE` in sorted UUID order as trailing projection-read locks; this does not change the RW-5 helper's Team/Thread/Hypothesis order. Use PostgreSQL READ COMMITTED. The receipt records Team revision plus candidate/evidence and Signal-projection fingerprints; the finalizer reacquires the same locks and validates them. Do not reverse the order.

Required two-session proof across the separate receipt/business-commit boundary:
1. **World-memory writer before receipt:** an `update_thread`/`operator_update` Task acquires the canonical lock chain, commits an EvidenceLink/Hypothesis membership or lifecycle change and one Team revision increment; the receipt transaction observes the new revision/profile and records that assessment. The finalizer succeeds only if the relevant profile remains valid.
2. **Receipt before world-memory writer before finalization:** the receipt transaction commits; a Thread/Hypothesis/evidence writer then commits and increments Team revision; the finalizer re-acquires locks and recomputes the candidate-profile fingerprint; it fails closed with no disposition/Outcome/terminal success Event only if the relevant profile differs (an unrelated revision increment alone is not stale). It must not rerun matching or choose another candidate. Exercise the accepted stale-receipt TaskRuntime mapping.
3. **Receipt plus finalization before world-memory writer:** the receipt commits; the finalizer acquires canonical locks before a concurrent writer, validates the same profile/revision, and commits the business bundle. The writer waits until finalization releases locks, then proceeds.
4. **KnowledgeIndex writer before receipt:** `KnowledgeIndexService.index_signal()` locks Signal `FOR UPDATE`, replaces the Signal's chunk projection, and commits; the receipt transaction then locks Signal `FOR SHARE`, reads the new stable chunk identity/metadata/vector fingerprints, and records the resulting assessment.
5. **Receipt before KnowledgeIndex writer before finalization:** the receipt transaction commits; the indexer acquires Signal `FOR UPDATE` and replaces chunks; the finalizer re-acquires Signal `FOR SHARE` and compares the stable chunk identity/metadata/vector fingerprint; it fails closed only if that stable projection changed (a surrogate row-ID replacement with identical stable content/embedding projection does not stale the receipt) without rerunning similarity or selecting replacement evidence.
6. **Receipt plus finalization before KnowledgeIndex writer:** the finalizer obtains Signal `FOR SHARE` before the indexer, validates the exact projection, and commits; the indexer waits until finalization releases the Signal locks, then replaces the projection. The committed disposition remains a valid historical decision.
7. **Decay writer interleavings:** `apply_decay` commits only the accepted confidence-band/ConfidenceChange update and one Team revision increment; it does not change `Thread.status` or create dormancy in RW-5 first release. A revision change between receipt and finalization is recorded, but only a changed candidate-profile fingerprint makes the receipt stale; confidence-only decay therefore does not stale the receipt when confidence is not an input to D4.2.
8. **Thread lifecycle/domain writer interleavings:** a separately authorized Thread-status/domain writer uses Task → Team → sorted Thread → sorted Hypothesis. If it commits before receipt, assessment observes the new state; if it commits between receipt and finalization, the finalizer recomputes the profile fingerprint and fails closed only if the relevant profile changed; if it waits until after finalization, the historical matched decision remains valid. No dormancy transition is authorized in RW-5 first release.
9. **Direct/unsupported projection writer:** prove a KnowledgeChunk INSERT/UPDATE/DELETE cannot bypass the parent Signal lock; either the database trigger enforces the lock or the runtime role is restricted to the controlled indexer path. Any relevant writer without the lock/revision protocol blocks disposition enablement.

**Thread facts are evaluated at decision time, with one identity exception:**

- `Thread.status` is a lifecycle fact, not an immutable attribute of the historical disposition. The matched disposition records that the Thread was eligible (active) at the decision's serialized commit point. A later valid transition to dormant or resolved does not invalidate or rewrite that historical decision. RW-5 first-release decay is confidence-only and does not create dormant Threads; any future dormancy writer requires separate accepted design and implementation authorization. Do not freeze status or block legitimate lifecycle transitions merely because a disposition references the Thread.
- The status and matcher-evidence checks must occur after acquiring the canonical Task → Team → sorted Thread → sorted Hypothesis locks and be held through commit. The current bounded source search found reads and Thread creation but no production writer assigning `Thread.status` or `Thread.domain`; test fixtures do directly set status. Existing `update_thread`/`operator_update` evidence writers and the planned `apply_decay` confidence writer can change the Hypothesis/EvidenceLink profile used by matching, so each must use the canonical helper, lock the affected Hypotheses in sorted order, and participate in Team revision stamping before matched writes are enabled. RW-5 first-release decay changes confidence only and does not transition Thread status. This source search is not proof against dynamic SQL or out-of-repository writers.
- The v1 SignalDisposition row and seven-key `signal_triage` observation do not add a separate `Thread.status_at_decision` field or a Thread-status history table. The D4.2 immutable assessment receipt records the selected candidate's Team/domain/status-at-assessment, and the trusted TaskRuntime receipt/finalization under canonical locks is the authoritative assertion that the Thread was active at the decision. Replay validates that immutable receipt plus disposition/Task evidence and current Team/domain identity, but must not require the Thread's current status to remain active after the committed decision; later legitimate lifecycle changes are allowed. This is an application trust boundary backed by a Task-attributed receipt, not an independently queryable Thread-status history table. If that stronger audit requirement is later needed, it requires a separate design rather than silently expanding the accepted row shape.
- `Thread.domain` is part of the Thread's semantic identity, not a lifecycle state. At matched-disposition insertion, require `Thread.team_id = SignalDisposition.team_id` and `Thread.domain = Team.domain`. Because the disposition is immutable historical evidence, a later domain change would make that recorded same-domain decision misleading. Enforce this with a narrow database `BEFORE UPDATE OF domain` guard that rejects an actual value change (`NEW.domain IS DISTINCT FROM OLD.domain`) when a matched SignalDisposition references the Thread; do not rely on application-only checks or caller-settable bypass flags. The guard may use a narrowly scoped owner-controlled function if runtime SELECT privileges are intentionally withheld, with the same fixed-search-path/security review required for other privileged trigger functions. Do not block ordinary status changes or title changes on this basis. If a future domain-transfer feature is needed, it requires a separately designed versioned identity/transfer path; do not silently mutate the referenced Thread.
- Keep the Team domain protected under the accepted intake-witness rules. The Thread-domain fence is narrower: it is conditional on an existing matched disposition reference and does not impose blanket immutability on every Thread from creation.

This is a release gate for matched dispositions, not a request to implement RW-5 decay early. Dormant matching remains deferred in RW4-1; RW4-5 owns any later reactivation.

## 5. Keep D4.1a duplicate canonicality outside this slice

A duplicate disposition requires more than a valid Signal FK and matching hash. It must point to the first successfully committed Signal for the same Team and exact raw content hash, regardless of origin.

The current Event timestamps, fetched_at, UUID order, and (origin_url, content_hash) uniqueness do not establish that winner.

Recommendation:
- Keep the duplicate_of_signal_id column and row constraint in the proposed shape.
- Do not enable duplicate disposition writes until D4.1a's separately reviewed database arbitration/stable-association mechanism and two-session PostgreSQL proof are complete.
- RW4-1 design must state this dependency explicitly. Do not create a partial canonical-hash registry, second winner algorithm, or surrogate timestamp ordering in this migration.
- The RW4-1 schema may reference the eventual canonical witness only if that dependency's exact interface is already accepted; otherwise keep canonical validation outside the frozen DDL and block duplicate execution.

## 6. D2 Task identity is a hard write-enable prerequisite

The current Task schema lacks persisted signal_id and identity_version. The accepted [D2 identity contract](https://github.com/abtn/Watch-Architecture-Rev2/issues/186) requires both, unique (team_id, signal_id, identity_version), and recomputation of the canonical UUIDv5 Task ID from persisted request data.

A composite FK to (tasks.id, tasks.team_id) proves same-Team Task ownership, not that this is the canonical Task for this Signal. The disposition must carry `identity_version='triage_identity_v1'` and reference the four-column Task key `(id, team_id, signal_id, identity_version)`. The separate D2 migration must enforce that `task_type='triage_signal'` if and only if the D2 identity fields are populated with the supported identity version, create a unique support key on those four Task columns in addition to the accepted unique `(team_id, signal_id, identity_version)` identity key, then install the composite FK from SignalDisposition. This is a separately versioned D2-dependent migration step, not a change to the RW4-1 initial migration. There is no acceptable caller-supplied, request-Event-only, or unpersisted transitional substitute for the accepted D2 identity contract.

Required boundary:
- Do not add D2 columns/indexes in the RW4-1 disposition migration.
- The initial RW4-1 migration must not grant the application runtime role INSERT permission on `signal_dispositions`; the table is schema-prepared but write-disabled until the D2 composite FK is installed and all other write-enable gates are met.
- The D2-dependent FK-install migration is constraint-only: it adds no columns and must not run the RW4-1 cutover's AccessExclusive DDL protocol. In one transaction acquire `LOCK TABLE tasks, events, signal_dispositions IN SHARE ROW EXCLUSIVE MODE NOWAIT` in that order. This matches the Task → Event writer order and obtains the `SHARE ROW EXCLUSIVE` level required for adding the FK on both referenced `tasks` and referencing `signal_dispositions`; it does not need a later lock upgrade. While held, reassert that `signal_dispositions` is empty, no triage Task/request Event was created before the creator gate, and all existing Task identity tuples satisfy the D2 constraints; then add the composite FK and commit atomically. If any lock conflicts or preflight is nonzero, abort the whole transaction without mutation and retry fresh. Runtime INSERT permission remains withheld until the FK is committed and verified.
- Do not weaken Task attribution to caller-provided IDs or a task-type-only check.
- The accepted D2 Task identity migration is a hard prerequisite before any triage Task can be created and before any disposition write or replay can be enabled. It must enforce the triage-task/identity-field CHECK, add `UNIQUE (id, team_id, signal_id, identity_version)` as the composite-FK support key, and install the later D2-dependent FK from `signal_dispositions(decided_by_task_id, team_id, signal_id, identity_version)` to `tasks(id, team_id, signal_id, identity_version)`. Install the FK only after a preflight confirms no pre-existing disposition rows or malformed triage Tasks; the write gate remains closed until the migration commits.
- At disposition insert and replay, the composite FK enforces Task/Team/Signal/identity-version equality. TaskRuntime must additionally verify `task_type='triage_signal'`, recompute and verify canonical Task UUIDv5 ID and operation, and validate exactly one valid triage_signal_requested Event from persisted data. The FK enforces relational correspondence; application validation enforces deterministic UUID identity.
- The D2 migration remains a separately reviewed and separately authorized migration. Sequence it as a required schema/preflight step before RW4-2 Stage B enables the triage creator. RW4-1 may prepare its own schema and persistence code earlier, but that path remains disabled until D2 identity is present and verified.
- Do not reopen a transitional-proof alternative in implementation. If the accepted D2 schema contract itself is changed, that requires a new Operator decision before implementation.

This preserves the approved serial order: RW4-1 design/schema preparation → RW-5 helper and writer retrofit → D2 identity migration as a Stage B prerequisite → RW4-2 Stage B creator → RW4-3 disposition execution. The D2 migration does not become part of the RW4-1 migration.

## 7. Immutability and timestamp

**SignalDisposition immutability:** install an unconditional database trigger that rejects every UPDATE and DELETE on `signal_dispositions`; also withhold runtime UPDATE/DELETE privileges. The trigger is defense in depth against accidental grants and all supported runtime writers. No caller-controlled bypass or maintenance exception is exposed to the application. Any repair is a separately audited owner/break-glass operation and does not rewrite immutable history.

**Timestamp:** `created_at TIMESTAMPTZ NOT NULL` is assigned by a `BEFORE INSERT` trigger using `clock_timestamp()`. The trigger overwrites any caller-supplied value. Do not rely on a DEFAULT alone because an INSERT caller can supply a value. This records database insertion time, not commit order; it is not the D2 immutable Task `as_of`, the D4.1a first-commit arbitration key, or the RW-5 Team revision watermark.

**TRUNCATE:** revoke effective runtime TRUNCATE from runtime, inherited roles, and PUBLIC on `events`, `signals`, `signal_dispositions`, `tasks`, and `teams`; install unconditional statement-level `BEFORE TRUNCATE` rejection triggers on each. Prove direct and CASCADE paths. For `threads`, a matched disposition's restrictive composite FK prevents direct TRUNCATE; `TRUNCATE threads CASCADE` must reach the protected `signal_dispositions` table and be rejected by its trigger. PostgreSQL fires all `BEFORE TRUNCATE` triggers for the complete truncate set, including cascaded tables, before any table is truncated; the rejection therefore aborts the whole statement before Thread or disposition rows are removed. The runtime cannot disable/replace these triggers or assume the owner role.

**Partitions/inheritance:** at cutover, inspect `pg_partitioned_table` and `pg_inherits` for all protected tables. The current design expects these tables to be non-partitioned/non-inherited. If any protected table has partitions or inheritance children, stop unless every leaf has the unconditional rejection trigger and the partition-creation/attach workflow installs and verifies the trigger before a new leaf becomes writable. Test direct leaf TRUNCATE as well as parent/CASCADE attempts.

No cascading deletes. Every SignalDisposition FK uses restrictive delete/update behavior so referenced Signal, Team, Thread, or Task history cannot be destroyed or have its key rewritten. The Event/Signal identity guards cover relationships that are not expressible as ordinary FKs (notably Event payload → Signal).

## 8. TaskRuntime integration and terminal evidence contract

Do not add a generic callback framework or a second Outcome. The current D4.2 proposal requires one immutable, versioned, Task-attributed match-assessment receipt to be durably committed in a TaskRuntime-owned transaction before the separate business-commit transaction begins. This is distinct from the D3 atomic finalization: disposition, Outcome, terminal Task state/time, and `task_completed` Event still commit together in one business-finalization transaction. TaskRuntime owns both transactions and all attempt/recovery decisions. The exact receipt schema, unique identity, inter-transaction recovery behavior, and stale-receipt failure mapping remain D4.2/RW4-3 prerequisites; do not collapse the receipt into the business transaction unless the Operator explicitly reopens the D4.2 boundary. The current `TerminalObservation` is a frozen dataclass with explicit optional evidence fields; its serializer `_observation_payload()` builds the immutable Snapshot JSON. The current `_replay()` compares canonical Snapshot bytes and checks Task status plus terminal Event type/cardinality, but it does not validate the complete terminal Event payload or `Task.completed_at`. The triage extension must add `success_signal_triaged` to the existing `TerminalObservation.result_category` Literal and close those exact gaps for this category without changing unrelated replay behavior.

### 8.1 One triage success category and typed member

Use one TaskRuntime success category for all three successful business dispositions: `success_signal_triaged`. Add it to the `TerminalObservation.result_category` Literal and the TaskRuntime `_SUCCESS_CATEGORIES` set so the existing finalizer maps it to Task status `done`. Permit this category if and only if `task.task_type == 'triage_signal'` and the typed `signal_triage` member is present. The disposition value distinguishes matched, duplicate, and deferred. Deferred is successful and ends with Task status `done`. Technical failures and stale-pin supersession remain on the existing non-success path and create no disposition.

Add an optional typed `signal_triage` member to the frozen `TerminalObservation`, represented by a frozen `SignalTriageObservation` value. It is required if and only if `result_category == "success_signal_triaged"`; it is forbidden for every other result category. It contains:
- `schema_version: Literal[1]` (fixed to 1)
- `signal_id: UUID`
- `disposition: Literal["matched", "duplicate", "deferred"]`
- `thread_id: UUID | None`
- `duplicate_of_signal_id: UUID | None`
- `reason_code: str | None`
- `explanation: str`

The nested serialized JSON member is named exactly `signal_triage` and has schema version 1. Its exact object shape is:
```json
{
  "schema_version": 1,
  "signal_id": "lowercase-canonical-uuid",
  "disposition": "matched",
  "thread_id": null,
  "duplicate_of_signal_id": null,
  "reason_code": null,
  "explanation": "non-empty human-readable explanation"
}
```
All seven keys are always present. UUIDs use lowercase canonical hyphenated text. Inapplicable references/reason are JSON null, never omitted or encoded as empty strings. `explanation` is trimmed only for validation; preserve the supplied human-readable text in the stored evidence. No additional nested keys are allowed. The typed value enforces the D5.2 reference/nullability matrix and exact D5.3 deferred reason set before snapshot storage.

### 8.1.1 D4.2 durable match-assessment receipt

Before the business commit, TaskRuntime must persist one immutable, versioned, Task-attributed match-assessment Event in a separate committed transaction, as required by the current D4.2 proposal. The receipt is a recovery/audit record, not an informational log and not a second Outcome. It is separate from the exact seven-key `signal_triage` member and from the terminal `task_completed` Event.

The receipt contract comes from D4.2 and must contain, within a hard payload bound:

- the exact input Signal/Snapshot identity and immutable Task request fingerprint;
- matcher identifier/version, embedding-space identity, and chunking version;
The matcher version must uniquely bind the fixture-approved threshold, winner margin, score precision/rounding, and candidate/evidence bounds. If any of those values are independently configurable, their exact values must be included in the receipt and canonical fingerprint; they cannot drift behind an unchanged matcher pin.
- the Team `world_memory_revision` observed under the canonical lock and used for the assessment;
- the assessment disposition and reason;
- a bounded, deterministically ordered candidate Thread set, including each candidate's Team/domain/status-at-assessment;
- for each retained candidate, supporting Evidence Signal/Snapshot identity, chunk index/hash, embedding-space/chunking metadata, canonical embedding-vector fingerprint, and score (a `KnowledgeChunk.id` may be diagnostic only, never the semantic identity);
- the selected Thread or canonical duplicate Signal reference, if any;
- a candidate-profile fingerprint over candidate Thread/domain/status and eligible EvidenceLink/Hypothesis membership/lifecycle;
- a Signal-projection fingerprint over the input/evidence Signal IDs and stable chunk identity/metadata/vector fingerprints (not surrogate row IDs);
- a canonical assessment fingerprint over the request, pins, Team revision, candidate-profile/projection fingerprints, scores, and selected result.

Candidate evidence must obey the Task's immutable creation-time `as_of` and `world_memory_revision` watermark stored in its request Event. `assessment_team_revision` is a separate current-state serialization fence captured under the Team lock; it does not replace or rewrite the Task's immutable creation watermark.

Use `assessment_team_revision` as an immutable assessment watermark, not as the sole stale decision. The business finalizer always recomputes the bounded candidate-profile fingerprint under the canonical locks without recomputing similarity and requires equality with the receipt. This catches relevant profile changes even if a writer failed to increment Team revision, while unrelated changes (including confidence-only decay when confidence is not a matcher input) do not stale the receipt. The finalizer also always revalidates Signal projection fingerprints because `KnowledgeIndexService` does not increment Team revision. D4.2 must freeze exactly which fields enter both fingerprints; any future matcher input requires a matcher-version change and corresponding fingerprint field.

Scores are canonical decimal strings with a fixed precision/rounding rule. Do not store vectors or copy source text into the receipt. A vector fingerprint must use a frozen canonical byte encoding (dimension, float width, endianness, and rounding); do not hash Python `repr()` or an unstable database text rendering. The exact encoding is a D4.2 prerequisite. Candidate Thread, evidence Signal, chunk, and total payload bounds, plus the finalizer's candidate-profile/projection revalidation query cost, must be measured and frozen by the D4.2 evidence gate. Deterministic candidate/evidence serialization order is for stable fingerprinting only; it must never break a semantic score tie. UUID ordering is not a winner-selection rule, and a score tie/insufficient winner margin remains ambiguous under D4.2.

The receipt identity is derived from Task ID plus a fixed assessment kind/schema version, not attempt number. The database must enforce at most one canonical receipt per triage Task. The exact Event type and the single authorized Kernel write operation must be scoped to a running `triage_signal` TaskRuntime attempt; the operation validates the immutable Task/request and receives the active Session. Workers, host adapters, and generic Event writers cannot create or replace this receipt, and no generic Event allow-list is widened. `Event.created_at` is application-generated and is not proof of receipt/business commit order; the separate committed transaction and subsequent visibility of the receipt row establish that ordering. Concurrent attempts that race to insert must load the winner and verify Task ID, request fingerprint, schema version, and assessment fingerprint; mismatch, multiple receipts, or corruption is an integrity failure. The exact Event type, schema/version keys, unique-index predicate/name, and receipt payload limit remain D4.2/RW4-3 prerequisites and must be accepted before implementation; do not invent them in the RW4-1 disposition migration. If a candidate/evidence/query bound is reached, the receipt must record that the assessment was bounded/incomplete and use only the accepted D5 deferred reason; never silently score a truncated candidate set. Missing, partial, or mismatched provenance remains an integrity/technical failure, not deferred. A candidate Thread whose evidence projection is incompatible may be excluded under D4.2; if no eligible candidate remains, use the accepted deferred matrix. By contrast, if the required incoming Signal projection is unavailable/stale/inconsistent after admission while its immutable pins remain supported, the TaskRuntime outcome/recovery mapping remains an RW4-3 prerequisite; do not invent a deferred, superseded, or terminal-failure classification here.

**Receipt transaction:** TaskRuntime acquires Task `FOR UPDATE`, verifies the Task is exactly `running` on the current admitted attempt, then acquires Team `FOR NO KEY UPDATE`; revalidates Team status exactly active, exact `origin_url`/`source_type`, Team domain/source scope, the greatest supported immutable TeamPolicy version, and the DB-attested intake witness; captures the current Team revision; and resolves the D4.1a canonical Team/hash association. A duplicate records its canonical Signal, locks the input/canonical Signal rows `FOR SHARE` in sorted order, and skips Thread matching. For a canonical Signal, discover the bounded candidate Thread set, lock candidate Threads in sorted order `FOR NO KEY UPDATE`, then required Hypotheses in sorted order `FOR NO KEY UPDATE`, then all input/evidence Signal rows `FOR SHARE` in sorted order; evaluate the bounded D4.2 matcher against the locked KnowledgeChunk projections. Persist the immutable assessment receipt, including stable chunk-identity/metadata/vector fingerprints (surrogate row IDs are diagnostic only), and commit only that receipt Event. A crash after receipt commit but before business finalization leaves the receipt durable and the Task recoverable. No receipt means assessment was not durably completed and TaskRuntime follows the existing assessment/retry policy. One valid receipt means recovery reuses that exact assessment without rerunning similarity. A corrupt/multiple/mismatched receipt fails closed.

**Business-finalization transaction:** TaskRuntime starts a separate transaction, reacquires Task → Team → sorted Thread → sorted Hypothesis → sorted Signal locks (Signal rows `FOR SHARE` in sorted UUID order), revalidates Team status/source/policy/provenance, and checks the Team revision/profile fence: always recompute the bounded candidate-profile fingerprint without cosine scoring and require equality with the receipt; always require the stable Signal-projection fingerprint and chunk/vector values to match. Revalidate D4.1a canonical association and selected candidate/status/domain, then compare the receipt result with the typed `signal_triage` observation and D5.2 matrix. If the candidate profile, Signal projection, or any canonical reference changed after receipt commit, fail closed: do not rerun similarity, select replacement evidence, or silently convert the result to deferred. The exact TaskRuntime terminal/retry mapping for this stale-receipt failure must be accepted in D4.2/RW4-3 before implementation. A relevant stale receipt cannot be refreshed under the same Task; a terminal failure leaves the failed `triage_identity_v1` Task occupying the identity, with no replacement Task or reassessment. This can permanently block triage for that Signal and must be explicitly accepted or redesigned before implementation. If valid, insert SignalDisposition, Outcome, terminal Task status/completion time, and `task_completed` Event together in this one transaction. A failed business-finalization transaction rolls back that business bundle but retains the committed receipt for retry. The Kernel persistence operation uses the active Session for each transaction and never commits independently; TaskRuntime owns both transactions and all attempt/recovery decisions.

Replay must load and validate the same unique receipt, verify its request and assessment fingerprints, and ensure its selected Thread/canonical duplicate reference agrees with the immutable disposition row and terminal observation. It must not rerun the matcher during replay. The receipt's exact schema, uniqueness, separate transaction boundary, recovery implementation, Team-revision/reference fence, and stale-receipt TaskRuntime mapping are hard D4.2 prerequisites to enabling any of the three dispositions.

### 8.2 Canonical outer observation and Outcome

The outer observation continues to use the existing TaskRuntime fields and serializer conventions. Its exact triage-specific additions and values are represented by this shape (UUID/time values are illustrative):
```json
{
  "attempt": 1,
  "failure_reason": null,
  "observed_at": "2026-11-25T12:00:00+00:00",
  "result_category": "success_signal_triaged",
  "signals": [],
  "signal_triage": {
    "schema_version": 1,
    "signal_id": "00000000-0000-4000-8000-000000000002",
    "disposition": "matched",
    "thread_id": "00000000-0000-4000-8000-000000000003",
    "duplicate_of_signal_id": null,
    "reason_code": null,
    "explanation": "Matched an eligible existing Thread."
  }
}
```
The nested `signal_triage` object has exactly the seven keys defined in §8.1; the example shows the matched variant. For duplicate and deferred, only the D5.2 fields change according to the same fixed key set. `signals` remains the existing serializer's empty array. No other optional outer evidence member is permitted for this category. `observed_at` must be timezone-aware and is serialized using the existing UTC timestamp serializer.

The existing Outcome remains the only terminal Outcome: `subject_kind=task`, `subject_id=Task.id`, `outcome_type=task_execution`, `recorded_by_task_id=Task.id`, and `team_id=Task.team_id`. Its `observation_snapshot_ref` and `observation_hash` identify the exact canonical JSON bytes above plus the existing outer fields. The disposition row stores disposition, reference, reason, and Task attribution; the human explanation remains in the immutable observation Snapshot.

### 8.3 Exact triage task_completed Event payload

For this category, emit exactly one `task_completed` Event with the following payload keys and no triage-specific omissions or extras:
- `schema_version`: integer `1`
- `from_status`: `"running"`
- `to_status`: `"done"`
- `attempt_count`: the same positive integer as the outer observation `attempt`
- `result_category`: `"success_signal_triaged"`
- `failure_reason`: JSON null
- `outcome_id`: lowercase canonical UUID of the one task_execution Outcome
- `observation_snapshot_ref`: exact Outcome snapshot reference
- `observation_hash`: exact Outcome observation hash
- `signal_id`: same UUID as `signal_triage.signal_id`
- `disposition`: same value as `signal_triage.disposition`
- `completed_at`: the same UTC timestamp as outer `observed_at`

The Event's `created_at` remains the Event-record insertion timestamp and is not the semantic completion timestamp. Do not require it to equal `completed_at`; the durable completion instant is `Task.completed_at = Outcome.observed_at = task_completed.payload.completed_at`. The Event payload's outcome/snapshot/signal/disposition fields must equal the referenced Outcome, its parsed immutable Snapshot, and the persisted SignalDisposition row.

### 8.4 Atomic finalization and exact replay

Inside the existing TaskRuntime business-finalization transaction:
1. Lock and validate the Task/attempt using the existing TaskRuntime path; require persisted Task status exactly `running` and the current admitted attempt.
2. For `success_signal_triaged`, verify D2 canonical Task identity, the D2 composite identity fields, and exactly one valid `triage_signal_requested` Event.
3. Load exactly one committed D4.2 assessment receipt; verify Task request fingerprint, schema/version, canonical assessment fingerprint, Task creation watermark, and selected disposition/reference. If no receipt exists, return to the TaskRuntime assessment/recovery path; do not finalize without one. A receipt without the matching business result is the expected recovery state under the D4.2 separate-transaction contract; corrupt/multiple/mismatched receipts fail closed.
4. Acquire the Team row `FOR NO KEY UPDATE`; revalidate Team status exactly active, exact `origin_url`/`source_type`, allowed Team domain/source scope, the greatest supported immutable TeamPolicy version, and the DB-attested intake-provenance witness. Read the current `world_memory_revision`; a revision difference is diagnostic and is not by itself a stale result. The current candidate-profile comparison in the next step determines whether matcher-relevant state changed. A policy/source/provenance mismatch fails closed.
5. Resolve/revalidate the D4.1a canonical Team/hash association. If the receipt is duplicate, verify its canonical duplicate target remains the accepted Team/hash winner and lock the input/canonical Signal rows `FOR SHARE` in sorted UUID order. If it is canonical, rediscover the current bounded candidate Thread set using the Task creation watermark; lock the union of receipt and current candidate Thread rows in sorted order `FOR NO KEY UPDATE`, then the relevant Hypothesis rows in sorted order `FOR NO KEY UPDATE`, then the union of receipt and current-profile input/evidence Signal rows `FOR SHARE` in sorted UUID order. Recompute the current candidate-profile fingerprint from the current Thread/domain/status and eligible EvidenceLink/Hypothesis membership/lifecycle, and compare it to the receipt. Verify the stable KnowledgeChunk projection identity/metadata/vector fingerprints remain unchanged (surrogate row-ID changes alone do not stale the receipt); for a matched result, the selected Thread must still be same-Team/domain and active. Do not recompute similarity scores. Matched writes remain gated on the RW-5 helper and writer retrofit in §4.1. Dormant Thread remains deferred in RW4-1.
6. Compare the receipt's disposition/reason/selected reference with the typed `signal_triage` observation and D5.2 matrix. Do not rerun the matcher, choose a replacement candidate, or silently convert stale/corrupt evidence to deferred.
7. Insert the disposition row through the active Session.
8. Create the existing `task_execution` Outcome from the canonical typed observation Snapshot.
9. Insert the exact `task_completed` payload above and set Task status `done` plus `completed_at=observed_at`.
10. Commit disposition, Outcome, terminal Task state/time, and `task_completed` Event together. The already committed assessment receipt remains immutable.

For triage replay, first require `task.task_type == 'triage_signal'` and `result_category == 'success_signal_triaged'`; compare canonical Snapshot bytes exactly; validate the typed nested schema/version and D5 matrix; load and validate exactly one committed D4.2 assessment receipt and its request/assessment fingerprints; require the receipt result and selected reference to agree with the typed observation and single disposition row; validate the disposition row and all of its references; validate Outcome subject/type/Team/Task attribution and snapshot ref/hash; require exactly one terminal `task_completed` Event for the recorded attempt; compare its complete payload key set and every value to the canonical expected payload; and require Task status `done` plus `Task.completed_at == Outcome.observed_at == Event.payload.completed_at`. Also require Event signal/disposition fields to equal the Snapshot and disposition row. Event `created_at` is checked only for a valid persisted timestamp, not equality with semantic completion time. Exact replay is read-only and never reruns matching. Any missing, duplicate, malformed, extra, or inconsistent record fails closed; do not repair, synthesize, overwrite, or create replacement history.

These are triage-specific replay requirements. Do not silently broaden the behavior or rewrite legacy replay validation for other Task types in this design slice.

The immutable observation Snapshot is stored outside PostgreSQL. A failed DB transaction may leave an unreferenced immutable file; no disposition, Outcome, terminal Event, or terminal Task state may survive independently.

## 9. Migration boundary

- The migration must follow the actual Alembic head on its implementation base; the audit's 0019 head is a historical source observation, not a promise that no later migration exists.
- One linear Alembic head only. No historical migration edits.
- Transactional DDL; no concurrent index build unless the repository's migration/rollback contract is explicitly redesigned. The cutover is forward-only after commit: `downgrade()` must refuse to drop the marker, triggers, role protections, or SignalDisposition table. Application rollback may use an older application against the retained schema (the DB trigger still stamps new intake Events); schema correction is by a new forward migration. The only guaranteed rollback is PostgreSQL transaction rollback before the cutover migration commits.
- Fresh install, upgrade from current head, downgrade policy, injected failure rollback, and post-migration schema inspection are part of proof.
- The RW4-1 migration must add the nullable witness marker with no default and no backfill. PostgreSQL therefore treats every pre-cutover Event as NULL for the new column; no legacy-row scan or payload validation is needed to establish that boundary. Do not make a full-table inventory/count scan part of the locked migration. If operational counts are useful, collect them in a separate read-only audit outside the cutover transaction. Do not abort cutover because legacy rows are malformed, missing references, cross-domain, or historically inconsistent. Do not repair, rewrite, delete, or promote legacy history. The disposable-PostgreSQL fixture must contain both valid-looking and malformed legacy intake Events and prove they remain unchanged, NULL, and ineligible after migration. Validate the post-cutover trigger/writer contract separately: only newly inserted intake Events that pass DB validation receive the marker. Audit the supported current writer paths so no supported post-cutover writer bypasses that trigger; a historical source/migration audit cannot retroactively establish old event-time provenance and is not a substitute for the marker.
- **Exact preflight lock protocol:** because the cutover adds a column to `events` and installs triggers on existing identity/provenance tables, acquire the DDL lock level up front in one PostgreSQL migration transaction, with this single statement and exact order: `LOCK TABLE tasks, teams, signals, events, threads IN ACCESS EXCLUSIVE MODE NOWAIT`. `ALTER TABLE ... ADD COLUMN` requires `ACCESS EXCLUSIVE` unless a subform explicitly specifies a weaker mode; `CREATE TRIGGER` requires `SHARE ROW EXCLUSIVE`, which is covered by the stronger lock. A weaker `SHARE ROW EXCLUSIVE` prelock is not sufficient: it is compatible with `ROW SHARE` held by `SELECT ... FOR UPDATE/SHARE`, while later `ALTER TABLE ... ADD COLUMN` must upgrade to `ACCESS EXCLUSIVE`; an in-flight writer can then wait on the migration's DML fence while the migration waits on the writer's `ROW SHARE` lock. Acquiring `ACCESS EXCLUSIVE` with `NOWAIT` up front prevents that lock-upgrade deadlock by failing immediately if any reader, row-locking reader, or writer already holds a conflicting table lock. The ordered list follows the audited ingestion access path (Task → Team → Signal → Event) and includes `threads` for the matched-Thread domain guard. If any lock cannot be acquired, PostgreSQL aborts the statement; roll back the whole migration transaction so any earlier table locks are released, then retry in a quiet maintenance window. Once acquired, the locks block all concurrent access to those existing tables until commit; the migration must retain them through marker addition, trigger/constraint/grant installation, and verification. Do not acquire the locks piecemeal.
- While all locks are held, add the nullable marker with no default (without a full-table scan or backfill); install trigger functions/triggers, constraints, grants, and the Thread-domain guard; verify their definitions and effective privileges within the same transaction; then commit. The disposable-PostgreSQL fixture proof, not a production legacy-row scan, demonstrates that pre-existing rows remain unchanged and NULL. On any schema, role, trigger, or verification failure, roll back the entire migration, releasing locks without partial protection or schema mutation.
- No deployed database rows were inspected by RW4-1A. Recheck live schema/role assumptions in the implementation preflight; legacy row contents are not promoted to RW4-1 provenance and are not a cutover-validity gate.
- Do not combine with D2 Task identity, D4.1a canonical association, RW-5 Team revision/lock helper, or RW4-5 Thread reactivation migrations.

## 10. Bounded PostgreSQL proof matrix

| Proof group | Required cases | Expected result |
|---|---|---|
| Migration | Fresh disposable DB; upgrade from current head; one head/current; injected DDL failure before commit; attempted downgrade after cutover | Correct schema; failed transaction leaves no partial objects; linear history; destructive downgrade is refused and the committed cutover protections remain installed. |
| Row checks | Every valid D5 matrix row; every invalid/null combination; unknown disposition/reason; self-duplicate | Valid rows accepted; invalid rows rejected by PostgreSQL. |
| Uniqueness | Same Team/Signal twice; same Signal in two Teams; concurrent same-pair insert | One row per pair; cross-Team rows independent; exactly one concurrent winner. |
| FK ownership | Missing Signal/Team/Thread/Task; cross-Team Thread; Task has same Team but different Signal; wrong identity_version; missing D2 composite key | FK rejection; no cascading history deletion; disposition cannot point at a different same-Team triage Task. |
| Provenance | Populated legacy fixture containing both valid and malformed intake Events; assert all remain NULL and unchanged and do not block cutover; valid/invalid post-cutover Event inserts; runtime UPDATE/DELETE attempts against any Event including triage `task_completed`; protected intake Event-type rewrite attempts; wrong Task type, non-running Task, inactive Team, or wrong Task Team; missing Signal and Signal/Snapshot/hash mismatch; domain mismatch; Signal UPDATE/DELETE when referenced by a marked Event; Task/Team identity mutation when referenced by a marked Event; runtime-role trigger bypass and `session_replication_role` attempts; migration-first and reader/writer-first lock interleavings | Cutover succeeds without scanning/validating legacy payloads; legacy rows remain unchanged, unmarked, and ineligible; invalid new Events/mutations are rejected; runtime cannot UPDATE/DELETE Event history or bypass protections; migration-first blocks access through commit; any pre-existing table lock makes `ACCESS EXCLUSIVE NOWAIT` abort and cleanly release all locks for retry. |
| TRUNCATE protection | Direct `TRUNCATE` on events, signals, signal_dispositions, tasks, teams, and `knowledge_chunks`; `TRUNCATE threads` with a matched disposition; `TRUNCATE ... CASCADE` paths including threads→signal_dispositions; runtime role with inherited memberships; partition/leaf direct truncation; inspect effective grants on all application tables and statement-trigger definitions on the five D5.5 protected tables | Every attempt is denied by privilege, restrictive FK, and/or statement-level trigger; no protected row, matcher projection, or matched Thread history is removed; runtime cannot assume owner/migration role or disable triggers. |
| Ingestion reuse regression | fetch_no_change, ON CONFLICT winner, and prior_outcome replay with cross-domain Signal reuse | All three rejected for RW4-1 eligibility; ingestion correction, if any, remains separately scoped. |
| Thread and matcher evidence | Wrong Team/domain; resolved; active; dormant without RW4-5; later status transition after matched disposition; Thread.domain update before/after matched disposition; concurrent domain update; `update_thread`/`operator_update` EvidenceLink/Hypothesis change first; `apply_decay` confidence change first; both triage-first and writer-first interleavings | Decision-time status/domain and full evidence-profile checks reject ineligible/stale candidates; active is allowed only after RW-5 helper/revision retrofit and real PostgreSQL two-session proof; later status changes preserve historical disposition; referenced Thread.domain change is rejected; EvidenceLink/Hypothesis writers serialize under Task → Team → sorted Thread → sorted Hypothesis and increment Team revision once, so stale matcher receipts cannot commit. Confidence-only decay also serializes and increments revision but does not invent a Thread-status or matcher-score change. The finalizer recomputes the bounded candidate-profile fingerprint without similarity scoring, so unrelated confidence-only changes do not stale the receipt. Dormant defers without RW4-5 reactivation. |
| KnowledgeChunk projection concurrency | `KnowledgeIndexService` indexer-before-receipt; receipt→indexer→finalizer; finalizer→indexer; stable projection rebuilt with new surrogate IDs; changed chunk/vector/embedding metadata; direct KnowledgeChunk INSERT/UPDATE/DELETE; runtime `TRUNCATE knowledge_chunks` | Parent Signal `FOR UPDATE` writer serializes against sorted Signal `FOR SHARE` receipt/finalizer locks; stable projection fingerprint decides validity (surrogate row-ID changes alone do not stale); changed projection fails closed without similarity rerun; direct DML obtains the parent Signal lock; runtime TRUNCATE is denied. |
| Assessment receipt/recovery | One receipt per Task; receipt commits in its own TaskRuntime-owned transaction; crash after receipt and before business commit; business transaction rollback; lost response; retry/recovery; corrupt/duplicate/mismatched receipt; changed candidate profile; changed Signal projection | Receipt remains durable across business rollback/crash; retry validates and reuses it without rerunning similarity; business bundle remains atomic; all mismatches fail closed under the separately accepted TaskRuntime mapping. |
| Duplicate | Cross-Team target; different hash; noncanonical target; same hash but D4.1a winner unavailable | No duplicate disposition until canonical proof is available. |
| Task identity | Wrong Task type/Team/Signal/identity; D2 task_type/identity-field CHECK violation; mismatched disposition Task/Signal tuple; malformed or duplicate request Event; canonical UUID mismatch; absent D2 support key/FK | FK or TaskRuntime validation rejects; D2 migration is prerequisite for persisted identity check. |
| Immutability | UPDATE and DELETE under actual runtime role; privileged path if applicable | Mutation rejected by selected DB enforcement. |
| Timestamp | Omitted timestamp; explicit caller timestamp; repeat read | PostgreSQL assigns stable timestamp; caller-supplied value is ignored/rejected by the selected enforcement mechanism. |
| Atomic success | Matched and deferred paths; duplicate only after D4.1a gate | Disposition + Outcome + Task + terminal Event commit together. |
| Atomic rollback | Inject failure after disposition insert and before Outcome/Event/Task terminalization | No DB row from terminal bundle survives. |
| Terminal evidence/replay | Exact JSON member/version; UUID casing; null-versus-omitted fields; extra keys; invalid D5 matrix; Event payload key/value mismatch; Outcome/Snapshot mismatch; Task.completed_at mismatch; duplicate/missing terminal Event | Canonical serialization is deterministic; exact replay is read-only; every mismatch fails closed. |
| Concurrency | Two concurrent same-Team ingestions both holding Team FOR SHARE before Event trigger; conflicting Team.domain/Signal identity update; migration-first writer blocking; writer-first NOWAIT abort/retry; concurrent disposition inserts; triage-first and lifecycle-first Team/Thread lock interleavings; receipt/finalizer sorted Signal `FOR SHARE` versus KnowledgeIndexService Signal `FOR UPDATE` interleavings | No SHARE→NO KEY UPDATE upgrade/deadlock; identity update waits or is rejected; preflight has no write gap; unique disposition winner; active Thread remains eligible through commit. Use real PostgreSQL sessions and record blocking/commit order. |
| Boundaries | No Signal/Thread/EvidenceLink business mutation; no new Task/dispatcher path; no RW-5 helper/revision/decay implementation or RW4-5 reactivation inside RW4-1 | No out-of-scope writes. Later write-enable proof consumes the already-implemented RW-5 helper; it does not implement it. |

All constraint, concurrency, lock, trigger, and transaction claims require disposable PostgreSQL. SQLite/in-memory substitutes are not accepted for those proofs. Record PostgreSQL version, Alembic head, exact tested SHA, isolation level, session count, and observed blocking/commit outcomes.

## 11. Decisions requested from the Operator

This proposal intentionally separates recommendations from accepted decisions. Review the following:

1. Row shape: accept or amend the proposed one-row-per-(team_id, signal_id) shape and D5.2 reference matrix.
2. Cross-record enforcement: conditional Option A is accepted as the design direction, subject to the mandatory non-owner runtime/migration-owner role boundary and the Operator-accepted forward-only DB-attested cutover in §4.0.2. The exact marker/trigger/role implementation remains subject to physical review and PostgreSQL proof; if either prerequisite cannot be enforced, stop and return with a separately scoped Option B design.
3. **ACCEPTED:** duplicate disposition writes remain disabled until D4.1a canonical Team/hash arbitration is separately implemented and proven. Under accepted Decision 7, this is a prerequisite for enabling all three outcomes together; no matched/deferred-only partial rollout is permitted.
4. **ACCEPTED:** the separately reviewed D2 Task-identity migration is a hard prerequisite before any triage Task creation and before any SignalDisposition write or replay is enabled. Keep D2 identity columns/constraints out of the RW4-1 initial migration. Install the D2-dependent four-column composite FK only after SignalDisposition exists and a locked, transactional preflight proves the table is empty and triage Task identity data is valid; keep runtime disposition INSERT permission withheld until the FK is installed and verified. No caller/Event-only transitional substitute. Keep it separate from the RW4-1 migration; do not accept a transitional proof or caller/Event-only substitute.
5. **ACCEPTED:** database-enforced immutability and timestamp direction: reject UPDATE/DELETE on SignalDisposition; revoke effective runtime TRUNCATE privileges and reject TRUNCATE on protected tables; protect intake Events and their referenced Signal/Task/Team identity fields; assign `created_at` in the database using `clock_timestamp()` while making clear that it is insertion time, not commit order; and reserve trigger/owner maintenance for a separately controlled, audited migration/break-glass boundary. Exact triggers, grants, owner topology, partition behavior, and repository-specific timestamp conventions still require source review and real PostgreSQL proof.
6. TaskRuntime seam: accept one success_signal_triaged category for matched/duplicate/deferred; the typed observation fields, existing task_execution Outcome, task_completed Event index fields, atomic transaction, and exact replay equality rules in §8; no generic callback abstraction.
7. **ACCEPTED — all three outcomes enabled together.** Matched, duplicate, and deferred become available in one write-enable release only after every dependency below is implemented, independently reviewed, and proven. Prerequisite work may land in separate migrations/PRs; no partial disposition rollout is permitted. The bounded disposable-PostgreSQL proof matrix in §10 remains required, with the explicit additions in Decision 7 below.

The Operator has accepted the row shape, conditional Option A/forward-only cutover direction, the duplicate-write gate, the D2 Task-identity/FK prerequisite, database-enforced immutability/TRUNCATE/timestamp/maintenance direction, the triage-specific TaskRuntime terminal-evidence contract, and Decision 7's all-outcomes-together rollout. The Thread historical-fact rules in §4.1 are the proposed physical interpretation for independent review. The complete physical design must still receive independent review and explicit acceptance; implementation still requires separate authorization. No ORM, SQL, migration, TaskRuntime, ingestion, or test changes may be made.

### Decision 3 — duplicate disposition write gate (ACCEPTED)

**Operator decision (2026-11-25):** duplicate disposition writes remain disabled until the accepted D4.1a canonical Team/hash arbitration is separately implemented and proven.

This gate is one prerequisite of the overall rollout rule in Decision 7. Because all three outcomes must be enabled together, no SignalDisposition writes are enabled while D4.1a canonical arbitration remains unimplemented or unproven. Do not invent a new deferred reason or silently classify would-be duplicates as non-duplicates to work around this gate.

**Hard rules while the gate is closed:**

- No `SignalDisposition` row with `disposition='duplicate'` may be inserted.
- No `duplicate_of_signal_id` reference may be written or inferred by RW4-1.
- Do not choose a canonical Signal by `origin_url`, `fetched_at`, application `Event.created_at`, UUID ordering, query return order, or "first row seen".
- Exact raw `content_hash` equality is the duplicate criterion, scoped to the same Team; origin equality is not required and cross-Team equality is not a duplicate.
- A candidate duplicate must not be treated as safely classified until D4.1a can resolve the stable canonical Team/hash Signal.
- RW4-1 must consume the D4.1a canonical result; it must not implement a parallel registry, winner-selection algorithm, or fallback arbitration path.

**D4.1a exit evidence required before enabling duplicate writes:**

1. A database-enforced arbitration mechanism makes the first successfully committed Signal association for a given Team and exact content hash the canonical winner, independent of origin.
2. Two concurrent first arrivals for the same Team/hash, using different origins, cannot commit two canonical winners. The loser resolves to the committed winner after the appropriate transaction retry/re-read.
3. A failed/rolled-back first attempt does not become the winner; the first successful commit does.
4. Later arrivals for the same Team/hash resolve to the same winner, and the association remains stable.
5. The same hash in different Teams remains independently canonicalized and is not cross-Team duplicate evidence.
6. Tests cover exact hash equality only; no near-duplicate or semantic matching is introduced.
7. Real disposable PostgreSQL two-session tests record transaction order, blocking/unique-conflict behavior, retries, and final committed associations. Application-only or in-memory concurrency tests are insufficient.
8. The proof includes different-origin same-hash cases and verifies that application timestamps, `fetched_at`, and query ordering cannot determine the winner.

**Enablement sequence:** D4.1a persistence/arbitration design and implementation must be independently reviewed and authorized; its exact-head migration and writer changes must pass the two-session PostgreSQL proof; only then may the duplicate-write gate be reconsidered and explicitly enabled. D4.1a acceptance by itself is not proof of implementation, and implementation proof alone does not silently change RW4-1 rollout policy.

No D4.1a implementation or duplicate disposition write is authorized by this decision. It records a hard dependency and gate only.

### Decision 4 — D2 Task identity migration prerequisite (ACCEPTED)

**Operator decision (2026-11-25):** the accepted D2 Task identity migration is a hard prerequisite before any `triage_signal` Task can be created and before any SignalDisposition write or replay can be enabled. The D2 migration remains separate from the RW4-1 initial migration.

**Required migration boundary and sequence:**

1. The RW4-1 initial migration may create the SignalDisposition table and its row-local constraints, but must not add D2 Task identity columns/indexes and must not grant the runtime role disposition INSERT permission.
2. The separately reviewed D2 migration adds `tasks.signal_id` and `tasks.identity_version`, enforces the accepted triage-task/identity-field CHECK, creates the accepted unique `(team_id, signal_id, identity_version)` key, and adds the four-column unique support key `(id, team_id, signal_id, identity_version)`.
3. A later D2-dependent FK-install migration adds the composite FK from `signal_dispositions(decided_by_task_id, team_id, signal_id, identity_version)` to `tasks(id, team_id, signal_id, identity_version)`. It must use its own reviewed transactional lock/preflight protocol, acquire a write-blocking `SHARE ROW EXCLUSIVE NOWAIT` lock on `signal_dispositions`, and assert that the table is empty before installing the FK. It must also validate the relevant Task identity invariants. A lock conflict, non-empty disposition table, malformed triage Task, or other preflight violation aborts the migration without schema/data mutation.
4. Keep runtime disposition INSERT permission withheld until the composite FK has committed and its definition/support key have been verified. Task creation remains disabled until the D2 identity migration has committed and its identity constraints have been verified. Disposition replay is also disabled until the composite FK and all replay integrity checks are installed.
5. No caller-supplied ID, request-Event-only proof, task-type-only check, temporary application validation, or other transitional substitute may bypass the accepted D2 identity contract.

The D2 migration's own preflight, transactional behavior, rollback, single-head Alembic ordering, and exact PostgreSQL proof remain implementation/review requirements. D2 migration implementation is not authorized by this RW4-1B decision. This decision accepts the dependency and sequencing only; it does not authorize any schema, migration, Task creator, disposition, or runtime implementation.

### Decision 5 — immutable history, TRUNCATE protection, timestamp, and maintenance boundary (ACCEPTED)

**Operator decision (2026-11-25):** accept the database-enforced direction below. This is a design decision, not acceptance of exact DDL or proof that the current deployment roles satisfy it.

1. **SignalDisposition immutability:** unconditional database enforcement rejects UPDATE and DELETE. No application convention or service-layer check substitutes for the database rule.
2. **TRUNCATE:** revoke effective TRUNCATE from the runtime role and every inherited/PUBLIC path on `events`, `signals`, `signal_dispositions`, `tasks`, and `teams`; install unconditional statement-level `BEFORE TRUNCATE` rejection triggers on those protected tables. Direct, CASCADE, partition, and leaf-table attempts must be tested. Runtime must not own the objects or be able to disable/replace protections.
3. **Witness immutability:** protect intake Event type/payload/marker and the referenced Signal identity, Task `team_id`/`task_type`, and Team `domain` fields required by the accepted Option A witness. Protect the witness marker against caller assignment or later mutation.
4. **Timestamp:** the database assigns SignalDisposition `created_at` using `clock_timestamp()` and overwrites or rejects caller-supplied values. This is the database insertion timestamp only; it is not transaction commit order and must never be used to choose the D4.1a canonical duplicate winner.
5. **Privileged maintenance:** table/trigger ownership and maintenance privileges stay outside the application runtime. A separately controlled migration credential may perform reviewed migrations; any break-glass maintenance is audited. No ordinary runtime or maintenance workflow may bypass immutable-history protections.
6. **Proof and remaining conditions:** inspect repository timestamp/trigger conventions and prove effective grants, role memberships, owner separation, trigger definitions, partition behavior, direct/CASCADE TRUNCATE rejection, and surviving rows using real disposable PostgreSQL. The checked-in development topology's `watch` superuser arrangement is not evidence of a valid runtime boundary. If the required role boundary cannot be established, conditional Option A is not viable and work must stop for a separately scoped alternative.

This acceptance does not prove production role separation, approve exact trigger/function SQL, grant a privileged maintenance exception, or authorize any implementation. It does not change D4.1a's first-successful-commit rule or permit timestamp-based winner selection.
### Decision 6 — TaskRuntime terminal evidence and replay contract (ACCEPTED)

**Operator decision (2026-11-25):** accept the existing §8 contract as written, with the explicit boundary that the new behavior is triage-specific and must not broaden or rewrite replay behavior for other Task types.

Accepted requirements:
1. Use one success category, `success_signal_triaged`, for matched, duplicate, and deferred. The typed observation carries the disposition; deferred remains successful and completes the Task as `done`.
2. Add the frozen typed `SignalTriageObservation` and exact seven-key `signal_triage` JSON object, schema version 1, canonical lowercase UUIDs, explicit nulls for inapplicable fields, exact D5.2 reference matrix, and exact D5.3 deferred reason vocabulary.
3. Reuse the existing `task_execution` Outcome and immutable observation Snapshot. Do not add a second Outcome or generic callback framework.
4. Emit exactly one triage-specific `task_completed` Event with the §8.3 payload. Require `Task.completed_at = Outcome.observed_at = Event.payload.completed_at`; Event `created_at` remains a separate insertion timestamp.
5. TaskRuntime owns the existing Session and finalization transaction. Disposition, Outcome, Task terminal state/completion timestamp, and terminal Event commit or roll back together.
6. Triage replay validates canonical observation bytes, typed nested shape, disposition row and references, Outcome attribution/hash, complete terminal Event key set and values, Event cardinality, and completion-time equality. Replay is read-only; missing, duplicated, malformed, extra, or inconsistent evidence fails closed without repair or synthesis.
7. Apply the stricter validation only to `triage_signal` and `success_signal_triaged`; do not silently change legacy replay behavior for unrelated Task types.

This acceptance is a design decision only. It does not authorize TaskRuntime code, schema, migration, tests, or runtime changes. The existing RW4-1 implementation gates and separate implementation authorization still apply.
### Decision 7 — all disposition outcomes enabled together (ACCEPTED)

**Operator decision (2026-11-25):** accept Option B: `matched`, `duplicate`, and `deferred` become available together. Do not enable matched/deferred while duplicate classification remains gated, and do not invent a deferred reason or alternate classification for a would-be duplicate.

The three outcomes may have separate prerequisite implementation PRs and migrations, but the write-enable point is one release gate. No SignalDisposition writes or successful triage Task finalization may be enabled until all of the following are complete and independently verified:

1. **D1/D2 Task creation and authorization:** the single Control Room creator boundary, per-caller authorization/replay checks, accepted D2 identity schema/constraints, and later composite disposition-to-Task FK are implemented and proven. Production host authentication is integrated before production use. No triage Task creator is enabled before D2 identity is verified.
2. **RW-5 serialization and evidence-writer retrofit:** the canonical Task → Team → sorted Thread → sorted Hypothesis lock helper, Team revision protocol, and every relevant `update_thread`/`operator_update`/`apply_decay` and any Thread status/domain writer retrofit are implemented and proven with real PostgreSQL interleavings. No matched writes while any matcher-evidence writer can bypass the protocol.
3. **D4.1a duplicate arbitration:** the database makes the first successfully committed Team/exact-hash Signal association canonical. Two-session, different-origin concurrency, rollback, stable subsequent association, and Team-isolation proofs pass. Duplicate writes consume this canonical result; no timestamp or query-order fallback is permitted.
4. **D4.2 matcher evidence closure and D4b pins:** fixture-supported minimum threshold, winner margin, score serialization, candidate/evidence/payload bounds, profile-size bias assessment, disposable-PostgreSQL query plan/cost, labeled positive/hard-negative fixtures, actual code-owned v1 matcher/embedding/chunking pins, and the immutable one-per-Task assessment receipt schema/unique identity/payload bounds/transaction boundary/recovery proof are accepted and proven. Current D4.2 proposal requires a separate durable receipt transaction before business finalization; its Team-revision/reference fence and stale-receipt TaskRuntime failure mapping must be accepted and proven. A same-transaction alternative would require explicitly reopening that D4.2 contract. Matched writes remain disabled until this evidence gate closes.
5. **RW4-1 physical persistence:** the SignalDisposition schema, row constraints/indexes, forward-only DB-attested intake witness, protected identity fields, non-owner runtime/migration-owner role separation, TRUNCATE/immutability controls, and forward-only migration protocol are implemented and proven on disposable PostgreSQL. Legacy intake Events remain unmarked and ineligible.
6. **D3/D5 TaskRuntime atomicity and replay:** the accepted triage-only typed observation, D4.2 receipt uniqueness/recovery/validation, Outcome, terminal Event, completion-time equality, separate receipt recovery/validation, candidate-profile/Signal-projection fingerprint fence, KnowledgeIndexService Signal-lock and KnowledgeChunk DML/no-TRUNCATE proof, atomic business-finalization transaction, and exact read-only replay checks are implemented and proven. No generic replay behavior change for unrelated Task types. Dormant would-be winners remain deferred until separately authorized RW4-5; RW4-5 is not a prerequisite for active-Thread matched outcomes in this release.
7. **Integrated proof and review:** all three outcomes pass end-to-end with their reference matrices and failure/rollback cases; concurrency and migration proofs run against the exact candidate SHA; independent review finds no actionable blockers; the Operator separately authorizes implementation/write enablement.

If any dependency is missing, unsupported, or fails proof, keep all three disposition outcomes disabled. A technical/integrity failure remains a TaskRuntime failure and must not be converted into `deferred`. This decision does not authorize any prerequisite implementation, triage Task creation, disposition writes, or runtime enablement.

## 12. Explicit non-authorization

RW4-1B is a design proposal only. It does not authorize:
- SignalDisposition model/table/migration/service implementation;
- TaskRuntime or ingestion code changes;
- D2 Task identity migration;
- D4.1a canonical Team/hash arbitration;
- RW-5 locks, Team revision, decay, or writer retrofit;
- RW4-2 Stage B creator implementation;
- RW4-3 matching/commit;
- RW4-5 dormant Thread reactivation.
