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
2. **Receipt before world-memory writer before finalization:** the receipt transaction commits; a Thread/Hypothesis/evidence writer then commits and increments Team revision; the finalizer re-acquires locks and recomputes the candidate-profile fingerprint; it fails closed with no disposition/Outcome/terminal success Event only if the relevant profile differs (an unrelated revision increment alone is not stale). It must not rerun matching or choose another candidate. Exercise the accepted `assessment_receipt_stale` TaskRuntime terminal-failure mapping and permanent v1 identity occupancy.
3. **Receipt plus finalization before world-memory writer:** the receipt commits; the finalizer acquires canonical locks before a concurrent writer, validates the same profile/revision, and commits the business bundle. The writer waits until finalization releases locks, then proceeds.
4. **KnowledgeIndex writer before receipt:** `KnowledgeIndexService.index_signal()` locks Signal `FOR UPDATE`, replaces the Signal's chunk projection, and commits; the receipt transaction then locks Signal `FOR SHARE`, reads the new stable chunk identity/metadata/vector fingerprints, and records the resulting assessment.
5. **Receipt before KnowledgeIndex writer before finalization:** the receipt transaction commits; the indexer acquires Signal `FOR UPDATE` and replaces chunks; the finalizer re-acquires Signal `FOR SHARE` and compares the stable chunk identity/metadata/vector fingerprint; it fails closed only if that stable projection changed (a surrogate row-ID replacement with identical stable content/embedding projection does not stale the receipt) without rerunning similarity or selecting replacement evidence.
6. **Receipt plus finalization before KnowledgeIndex writer:** the finalizer obtains Signal `FOR SHARE` before the indexer, validates the exact projection, and commits; the indexer waits until finalization releases the Signal locks, then replaces the projection. The committed disposition remains a valid historical decision.
7. **Decay writer interleavings:** `apply_decay` commits only the accepted confidence-band/ConfidenceChange update and one Team revision increment; it does not change `Thread.status` or create dormancy in RW-5 first release. A revision change between receipt and finalization is recorded, but only a changed candidate-profile fingerprint makes the receipt stale; confidence-only decay therefore does not stale the receipt when confidence is not an input to D4.2.
8. **Thread lifecycle/domain writer interleavings:** a separately authorized Thread-status/domain writer uses Task → Team → sorted Thread → sorted Hypothesis. If it commits before receipt, assessment observes the new state; if it commits between receipt and finalization, the finalizer recomputes the profile fingerprint and fails closed only if the relevant profile changed; if it waits until after finalization, the historical matched decision remains valid. No dormancy transition is authorized in RW-5 first release.
9. **Direct/unsupported projection writer:** prove a KnowledgeChunk INSERT/UPDATE/DELETE cannot bypass the parent Signal lock; either the database trigger enforces the lock or the runtime role is restricted to the controlled indexer path. Any relevant writer without the lock/revision protocol blocks disposition enablement.

**Thread facts are evaluated at decision time, with one identity exception:**

- `Thread.status` is a lifecycle fact, not an immutable attribute of the historical disposition. The matched disposition records that the Thread was eligible (active) at the decision's serialized commit point. A later valid transition to dormant or resolved does not invalidate or rewrite that historical decision. RW-5 first-release decay is confidence-only and does not create dormant Threads; any future dormancy writer requires separate accepted design and implementation authorization. Do not freeze status or block legitimate lifecycle transitions merely because a disposition references the Thread.
- The status and matcher-evidence checks must occur after acquiring the canonical Task → Team → sorted Thread → sorted Hypothesis locks and be held through commit. The bounded production-source audit of `core/models.py`, `core/operator_application.py`, `core/update_thread_context.py`, and `core/world_memory.py` found Thread status/domain reads and availability checks, but no production Python Thread insert/create path and no production writer assigning `Thread.status` or `Thread.domain`. `Thread` construction and direct status setup were found in test fixtures; migration `0019_rw1_world_memory.py` defines the table/schema. Architecture/Task documentation describes starter Threads as part of `activate_team`, but `docs/tasks.md` explicitly marks that operation as not implemented in Checkpoint 3 and no corresponding production writer was found. The actual production/deployment owner that populates Thread rows is therefore not established by this repository audit and must be identified before physical enforcement is implemented. Existing `update_thread`/`operator_update` evidence writers and the planned `apply_decay` confidence writer can change the Hypothesis/EvidenceLink profile used by matching, so each must use the canonical helper, lock the affected Hypotheses in sorted order, and participate in Team revision stamping before matched writes are enabled. RW-5 first-release decay changes confidence only and does not transition Thread status. This bounded search is not proof against dynamic SQL, direct SQL, external host code, or out-of-repository writers; all such writers must be inventoried before accepting the runtime-role and lock-boundary proof.
- The v1 SignalDisposition row and seven-key `signal_triage` observation do not add `Thread.status_at_decision`, `Thread.domain_at_decision`, or a Thread-status history table/column. No `thread_status_snapshot` or `thread_domain_snapshot` columns are added to SignalDisposition. The D4.2 immutable assessment receipt records the selected candidate's Team/domain/status-at-assessment, and the trusted TaskRuntime receipt/finalization under canonical locks is the authoritative assertion that the Thread was active at the decision. Replay validates that immutable receipt plus disposition/Task evidence and current Team/domain identity, but must not require the Thread's current status to remain active after the committed decision; later legitimate lifecycle changes are allowed. This is an application trust boundary backed by a Task-attributed receipt, not an independently queryable Thread-status history table. If that stronger audit requirement is later needed, it requires a separate design rather than silently expanding the accepted row shape.
- `Thread.domain` is part of the Thread's semantic identity, not a lifecycle state. At matched-disposition insertion, require `Thread.team_id = SignalDisposition.team_id` and `Thread.domain = Team.domain`. Because the disposition is immutable historical evidence, a later domain change would make that recorded same-domain decision misleading. Enforce this with a narrow database `BEFORE UPDATE OF domain` guard that rejects an actual value change (`NEW.domain IS DISTINCT FROM OLD.domain`) when a matched SignalDisposition references the Thread; do not rely on application-only checks or caller-settable bypass flags. The matched-disposition transaction must lock the Thread row in the canonical Task → Team → Thread order before validating/inserting; the domain-changing UPDATE acquires the same row lock before its guard runs. This serializes both race orders: a domain update committed first is re-read and validated by triage; a matched disposition committed first causes the waiting domain update's guard to observe the reference and reject. Prove both orders with independent PostgreSQL sessions. The guard may use a narrowly scoped owner-controlled function if runtime SELECT privileges are intentionally withheld, with the same fixed-search-path/security review required for other privileged trigger functions. Do not block ordinary status changes or title changes on this basis. If a future domain-transfer feature is needed, it requires a separately designed versioned identity/transfer path; do not silently mutate the referenced Thread.
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

Do not add a generic callback framework or a second Outcome. The current D4.2 proposal requires one immutable, versioned, Task-attributed match-assessment receipt to be durably committed in a TaskRuntime-owned transaction before the separate business-commit transaction begins. This is distinct from the D3 atomic finalization: disposition, Outcome, terminal Task state/time, and `task_completed` Event still commit together in one business-finalization transaction. TaskRuntime owns both transactions and all attempt/recovery decisions. The exact receipt schema, unique identity, inter-transaction recovery behavior, and implementation/replay proof for the accepted `assessment_receipt_stale` terminal-failure mapping remain D4.2/RW4-3 prerequisites; do not collapse the receipt into the business transaction unless the Operator explicitly reopens the D4.2 boundary. The current `TerminalObservation` is a frozen dataclass with explicit optional evidence fields; its serializer `_observation_payload()` builds the immutable Snapshot JSON. The current `_replay()` compares canonical Snapshot bytes and checks Task status plus terminal Event type/cardinality, but it does not validate the complete terminal Event payload or `Task.completed_at`. The triage extension must add `success_signal_triaged` to the existing `TerminalObservation.result_category` Literal and close those exact gaps for this category without changing unrelated replay behavior.

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

**Business-finalization transaction:** TaskRuntime starts a separate transaction, reacquires Task → Team → sorted Thread → sorted Hypothesis → sorted Signal locks (Signal rows `FOR SHARE` in sorted UUID order), revalidates Team status/source/policy/provenance, and checks the Team revision/profile fence: always recompute the bounded candidate-profile fingerprint without cosine scoring and require equality with the receipt; always require the stable Signal-projection fingerprint and chunk/vector values to match. Revalidate D4.1a canonical association and selected candidate/status/domain, then compare the receipt result with the typed `signal_triage` observation and D5.2 matrix. If the candidate profile, Signal projection, or any canonical reference changed after receipt commit, fail closed: do not rerun similarity, select replacement evidence, or silently convert the result to deferred.  **ACCEPTED Operator rule:** a changed candidate profile, Signal projection, or canonical reference is a non-retryable technical stale-receipt failure finalized through TaskRuntime's existing terminal non-success path: Task status `failed`, result category `terminal_failure`, stable technical reason `assessment_receipt_stale`. It is not a D5 deferred disposition. Do not refresh the receipt, rerun similarity, choose replacement evidence, or create a replacement Task. The failed `triage_identity_v1` Task permanently occupies the identity; no reassessment occurs under v1. This rule is accepted, but its exact TaskRuntime failure/replay implementation and PostgreSQL proof remain prerequisites before implementation. If valid, insert SignalDisposition, Outcome, terminal Task status/completion time, and `task_completed` Event together in this one transaction. A failed business-finalization transaction rolls back that business bundle but retains the committed receipt for retry. The Kernel persistence operation uses the active Session for each transaction and never commits independently; TaskRuntime owns both transactions and all attempt/recovery decisions.

Replay must load and validate the same unique receipt, verify its request and assessment fingerprints, and ensure its selected Thread/canonical duplicate reference agrees with the immutable disposition row and terminal observation. It must not rerun the matcher during replay. The receipt's exact schema, uniqueness, separate transaction boundary, recovery implementation, candidate-profile/Signal-projection fence, and accepted `assessment_receipt_stale` TaskRuntime terminal-failure/replay mapping are hard D4.2 prerequisites to enabling any of the three dispositions.

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
| Thread and matcher evidence | Wrong Team/domain; resolved; active; dormant without RW4-5; later `active → dormant` and `active → resolved` transitions after matched commit; replay after each later transition; Thread.domain change before/after matched disposition; concurrent domain update in both lock orders; `update_thread`/`operator_update` EvidenceLink/Hypothesis change first; `apply_decay` confidence change first; both triage-first and writer-first interleavings | At commit, reject wrong-Team/domain, resolved, and dormant-without-RW4-5 candidates; active is allowed only after RW-5 helper/revision retrofit and real PostgreSQL two-session proof. After commit, later legal status transitions preserve the historical disposition and exact replay remains read-only/succeeds without requiring current status=active. A domain change before the first match is allowed only if the resulting domain still matches the Team at commit; after a matched reference exists it is rejected. Concurrent domain update and match serialize: update-first is revalidated by triage; match-first makes the waiting domain update fail. EvidenceLink/Hypothesis writers serialize under Task → Team → sorted Thread → sorted Hypothesis and increment Team revision once, so stale matcher receipts cannot commit. Confidence-only decay also serializes and increments revision but does not invent a Thread-status or matcher-score change. The finalizer recomputes the bounded candidate-profile fingerprint without similarity scoring, so unrelated confidence-only changes do not stale the receipt. Dormant defers without RW4-5 reactivation. |
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

## 10.1 Independent-review corrections and executable proof contract (2026-11-26)

This section resolves the four findings from the independent review. It tightens the design and its acceptance evidence; it does not claim that the production deployment has been inspected or that PostgreSQL proofs have run. The accepted Thread lifecycle/domain decision is unchanged.

### F1 — Runtime/migration-owner separation: freeze the target role contract

The current repository configuration is not an acceptable proof topology: `compose.yaml` initializes PostgreSQL with `POSTGRES_USER=watch`, and `migrations/env.py` defaults Alembic to `watch:watch`. Under the standard PostgreSQL image, that bootstrap user is a superuser. These settings may remain a local development convenience, but no production or acceptance proof may use the same principal as both application runtime and migration owner.

The target topology has three distinct principals. Names below are illustrative stable role names; deployment-specific credentials and connection secret names belong to the deployment configuration.

| Principal | Login | Ownership / purpose | Required attributes and memberships |
|---|---|---|---|
| `watch_owner` | NOLOGIN | Owns the application schema objects whose integrity is protected: protected tables, their indexes/constraints, trigger functions and triggers; owns any sequences actually used by those tables. | NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS. No application login. |
| `watch_runtime` | LOGIN | Application/worker connection only. | NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS. No direct or transitive membership in `watch_owner`, `watch_migrator`, or any role that can assume them. No ownership of protected objects. |
| `watch_migrator` | LOGIN | Dedicated migration connection, used only with application processes stopped and drained. | NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS, NOINHERIT. It may explicitly `SET ROLE watch_owner` for reviewed migrations; membership must not be inherited by runtime. It is not supplied to application services. |

A separately controlled break-glass principal, if operationally required, is not part of routine runtime or migration access. Its use must be time-bounded, audited, and separately approved. Do not grant routine maintenance users ownership or trigger-bypass capability.

**Protected-object grant matrix**

| Object / capability | Runtime grant | Owner / migration treatment |
|---|---|---|
| Database | CONNECT only; TEMP only if a source audit proves it is required | Owner and migration credentials receive only required database access. |
| Application schema | USAGE; no CREATE, ALTER, or ownership | Owner owns schema; migrator can SET ROLE owner for migration. |
| `events` | SELECT, INSERT; no UPDATE, DELETE, TRUNCATE | Owner owns table and guards. Event UPDATE/DELETE remains unavailable to runtime, including terminal Events. |
| `signals` | Only the audited ingestion operations (currently SELECT/INSERT); no TRUNCATE. No broad UPDATE/DELETE unless a separately reviewed supported writer requires it. | Owner owns table and identity guards. |
| `signal_dispositions` | SELECT only until D2 composite FK and every Decision 7 prerequisite are installed and verified; then SELECT/INSERT only. Never UPDATE/DELETE/TRUNCATE. | Owner owns table, constraints, and immutable-history guards. |
| `tasks`, `teams` | Only source-audited DML, with protected identity columns excluded from runtime UPDATE. No TRUNCATE. | Owner owns tables and protected-field guards. |
| `threads` | Grant only the column-level DML required by inventoried Watch application operations; deny TRUNCATE and protect `domain` after a matched reference. A grant to `watch_runtime` does not distinguish Control Room code from other code using that same credential. | Owner owns table and the Thread-domain guard. Thread creation/status writer ownership remains an explicit F2 gate. |
| Trigger functions | No direct EXECUTE grant to runtime unless a function is an intentional application entry point. | Functions are owned by `watch_owner`; migration role assumes owner for DDL. Revoke PUBLIC EXECUTE at function creation. |
| Sequences | No blanket grant. Grant USAGE/SELECT only for catalog-confirmed sequences needed by runtime inserts. | Owner owns sequences; migrator changes them only under owner role. |
| Schema/object DDL, grants, ownership, trigger control, replication-role setting | None | Migration uses explicit SET ROLE owner; runtime must have no direct or inherited path. |

This is a protected-object matrix, not a claim that the entire application currently needs only these grants. Before deployment, enumerate every application table/column and sequence used by the current runtime and grant only those observed operations. In particular, do not infer that revoking broad privileges from `threads` is safe until the actual Thread creation and lifecycle writers are identified. If a supported writer needs a privilege that conflicts with this matrix, stop and revise the role design rather than widening runtime to owner-like authority.

**Function and trigger execution contract**

- Every privileged trigger function is owned by `watch_owner`, uses `SECURITY DEFINER` only where elevated reads are required, is explicitly `VOLATILE` where it must observe the current READ COMMITTED state, fixes `search_path` to trusted schemas (prefer `pg_catalog` plus the one explicitly named application schema), and schema-qualifies every non-catalog relation and function reference.
- Revoke `EXECUTE` from PUBLIC in the same transaction that creates each function. Grant EXECUTE to the migration/owner principal needed to create the trigger. Trigger firing does not justify granting runtime direct EXECUTE on a trigger-only function; prove an allowed runtime DML statement fires the trigger successfully without that unnecessary grant.
- No caller-settable GUC, session variable, application flag, temporary table, or `session_replication_role` setting may bypass a guard.
- Runtime must not own protected objects, be a member (directly or transitively) of owner/migration roles, have CREATEROLE/CREATEDB/SUPERUSER/REPLICATION/BYPASSRLS, create objects in trusted schemas, or alter grants/ownership/functions/triggers.
- Verify effective privileges, not just direct ACLs: role attributes, `pg_auth_members` membership paths, `has_table_privilege`, `has_schema_privilege`, `has_sequence_privilege`, `has_function_privilege`, ownership, PUBLIC grants, and `SET ROLE` attempts. Include inherited grants and default privileges for future objects. Revoke PUBLIC schema CREATE and any PUBLIC TEMP privilege unless specifically required; document every exception.
- A bootstrap administrator may provision the initial roles and grant the migration membership. That bootstrap identity is not an application or routine migration credential and must not be present in runtime configuration.

**Cutover proof**

Provision the roles and runtime DSN before the window. Stop and drain all application/worker processes and all old owner/superuser sessions; run the migration using `watch_migrator` with an explicit `SET ROLE watch_owner`; commit the forward-only cutover; restart application processes only with `watch_runtime`; then inspect active sessions and effective privileges. The migration cannot prove or atomically change an external service's secret/DSN. The cutover is not complete until the deployment operator verifies the restarted services use the runtime login and no application session uses owner, superuser, or migration credentials.

**F1 exit evidence:** a checked-in reproducible disposable-PostgreSQL bootstrap script or test fixture must create these roles and grants from a clean database, install the proposed objects, and assert the positive and negative privilege cases above. It must prove runtime can perform each required application operation and cannot SET ROLE owner/migrator, update/delete immutable Events or dispositions, truncate protected tables, change ownership/grants, replace/disable triggers/functions, create in the application schema, or set replication-role bypass. It must also prove the migration credential can SET ROLE owner but cannot act as superuser. A prose role diagram alone does not close F1.

### F2 — Thread writer ownership: accepted target, deployment inventory still open

**Operator decisions (2026-11-26)**
- **Creation and supported lifecycle ownership — ACCEPTED, Option A:** Watch's trusted application/Kernel boundary owns Thread creation and lifecycle writes. `activate_team` is the canonical intended creator for Operator-approved starter Threads. The trusted host authenticates the Operator and requests activation; it does not write Thread rows directly. Watch validates the approved Team configuration, starter Thread definitions, Team/Domain consistency, and authorization, then commits Team activation, starter Threads, and attributable Event through the governed application path.
- **Resolution — ACCEPTED, Option A:** resolution is an explicit Operator-authorized Task/application operation. It validates the target Thread and reason, performs the status transition through trusted Watch code, and appends one immutable Task-attributed Event in the same transaction. It is not a model-worker write, direct SQL operation, or background side effect. The operation envelope is now frozen in §10.2: a typed ResolveThreadRequest is accepted by the existing operator_update application/Control Room operation, while the existing non-empty-proposal OperatorUpdateRequest remains unchanged; the Task type and TaskRuntime do not change.
- **Actual external writer status — UNKNOWN, Option D:** the deployment inventory has not been supplied or verified. The target owner is decided, but no claim is made that the current deployment already conforms.

**Current repository evidence**
- The bounded audit found no production Python Thread INSERT/create path and no production assignment to `Thread.status` or `Thread.domain`.
- `docs/tasks.md` describes `activate_team` as the Operator path that writes approved starter Threads, but explicitly marks it not implemented in Checkpoint 3.
- `create_update_thread_task()` and `operator_update()` target an existing Thread; they are not Thread creators or general lifecycle authorities.
- `WorldMemoryCommitService` writes Hypotheses, EvidenceLinks, and ConfidenceChanges, not Thread rows/status/domain.
- RW-5 first-release `apply_decay` is confidence-only and does not create Thread dormancy. Dormancy/reactivation remains separately gated by RW4-5.
- The checked-in development database configuration is not evidence of production credentials or production writer ownership.

This source result is bounded. It does not establish that host services, seed/bootstrap jobs, importers, admin tools, direct SQL, dynamic SQL, or out-of-repository processes do not write Thread rows.

**Required deployment inventory before F2 closure**

The deployment owner must identify and attest every actual Thread writer, including application/Kernel services; host/Control Room adapters and API/CLI integrations; workers and scheduled jobs; seed/bootstrap and Team provisioning; importers, maintenance commands, admin scripts and runbooks; migrations and break-glass procedures; direct SQL/ORM paths and external processes.

For each writer record: (1) environment and deployment owner; (2) executable entry point and purpose; (3) database principal/credential and provisioning; (4) operation and exact affected columns; (5) transaction boundary and Task/Event attribution; (6) lock order, Team-revision behavior, and lock hold through commit; (7) source/configuration evidence and covering test/proof; and (8) disposition as canonical Watch writer, trusted host caller delegating to Watch, restricted bootstrap/migration-only path, or unsupported writer to deny/retire.

A repository search cannot substitute for deployment-owner confirmation of out-of-repository writers. If the deployment owner cannot provide the inventory, record the unknown writer as an unresolved blocker; do not infer absence.

**Target writer disposition**

| Path | Accepted disposition | Required boundary |
|---|---|---|
| Approved starter Thread creation | `activate_team` through Watch application/Kernel | Operator authenticated by trusted host; Watch validates and commits Team activation, approved starter Threads, and provenance. No direct host SQL. |
| Thread resolution | operator_update Task in the exclusive resolve_thread operation mode | Control Room admits the Operator-authorized request; the existing Operator update commit path validates the locked Thread and reason, updates status, and appends one immutable Task-attributed Event in the same business transaction. TaskRuntime retains sole admission, terminalization, recovery, and replay ownership. |
| `update_thread` / `operator_update` | Existing-Thread knowledge writers only | May change only their specified Hypothesis/EvidenceLink/ConfidenceChange scope; no Thread creation or lifecycle authority. |
| `apply_decay` in RW-5 first release | Confidence-only writer | No Thread status/domain change and no dormancy creation. |
| Host/Control Room | Authenticated caller/delegator | May request approved operations; must not independently write Thread rows. |
| Seed/bootstrap/import/admin | Restricted initial provisioning or separately audited maintenance only | Separate credential and explicit procedure; not an ongoing alternative lifecycle writer. Ongoing lifecycle work delegates to Watch. |
| Direct SQL or unregistered external writer | Unsupported | Operationally exclude it from the Watch runtime credential or retire it before matched writes are enabled. If it must be technically isolated despite sharing the runtime environment, design a distinct credential/process or database capability; ordinary grants cannot identify its call site. |

**Canonical transaction and authorization contract**

- Every supported status/profile writer that can affect triage eligibility or matcher evidence must use the accepted canonical Task → Team → sorted Thread → sorted Hypothesis lock order, acquire locks before reading decision-relevant state, increment Team revision in the same transaction as required by RW-5, and hold locks through commit. The exact RW-5 helper remains the only supported lock implementation; this F2 decision does not authorize implementing it early.
- The resolution operation must be Operator-authorized at the trusted application boundary. The caller cannot create authority by fabricating model output or a request payload. Watch validates the grant against the Team derived from the locked Thread.
- Resolution reason and status transition are validated by Watch. The status update and exactly one immutable Event carrying Task/Operator attribution, previous/new status, and reason commit or roll back together. Event identity/cardinality and exact replay behavior must be specified and tested before implementation.
- Resolution does not rewrite prior SignalDispositions, receipts, Outcomes, or Events. A later legal status transition does not invalidate an earlier matched decision.
- `Thread.domain` remains governed by the F3 database guard: after a matched disposition references the Thread, an actual domain change is rejected. This does not freeze status.
- No general dormancy writer is introduced. RW-5 first-release decay remains confidence-only; dormant reactivation remains the separately gated RW4-5 path.
- The host may authenticate and initiate an operation, but Watch owns validation, transaction, and durable writes. Do not create a second persistence boundary or direct host database writer.

**Database privilege and compatibility requirements**

- The generic runtime role must not have unrestricted Thread INSERT/DELETE or broad status/domain UPDATE privileges. The resolution operation's eventual database write capability is deliberately unresolved until the deployment inventory is complete; it must be a narrowly scoped capability/entry point that preserves Operator authorization, Task attribution, canonical locks, Team revision, and the atomic Event, not a broad generic-runtime UPDATE grant.
- Derive least privilege from the complete deployment writer inventory. PostgreSQL cannot distinguish an approved Control Room call from arbitrary SQL issued with the same runtime credential. The accepted D1 boundary is trusted application code: unsupported direct SQL and external writers must be operationally excluded from holding or using the runtime credential. If the deployment requires protection against a nonconforming process that holds that same credential, stop and design a separate credential/process or narrowly scoped database capability; do not claim that grants alone distinguish the callers.
- The owner-controlled F3 trigger rejects matched-referenced Thread domain changes regardless of caller.
- Bootstrap/migration access remains distinct from runtime access. No application process may use the owner or migration credential.
- Existing writers that legitimately need status/profile mutations must be migrated to the canonical lock/revision protocol before matched disposition writes are enabled.

**F2 exit evidence**

F2 closes only when all are present: (1) deployment-owner-confirmed inventory of every in-repository and out-of-repository Thread writer and credential; (2) each writer classified and reconciled with the accepted target owner; (3) exact role-to-writer/column grant matrix, including effective and inherited privileges; (4) proof unsupported external/direct-SQL writers are operationally excluded or isolated behind a distinct credential/capability, and supported operations cannot bypass application authorization, lock order, revision stamping, or provenance; (5) real disposable-PostgreSQL interleavings for each supported writer and competing matched-decision/domain-update orders; (6) exact replay and rollback proof for the resolution status/Event business transaction and its TaskRuntime recovery boundary; and (7) integrated review confirming no dormancy transition or new Thread creator was accidentally introduced.

Until then, **F2 remains OPEN/BLOCKING** and matched disposition writes remain disabled under the accepted all-three-outcomes-together gate. The decision does not freeze `Thread.status`: valid later lifecycle transitions remain permitted through the proven supported writer boundary.

### F3 — Thread.domain database guard: freeze the trigger contract

The accepted rule is conditional immutability: before any matched disposition references a Thread, its domain is not frozen by this rule; once a matched reference exists, an actual domain change is rejected. Status is not frozen.

The physical guard contract is:

1. Install a narrow row-level `BEFORE UPDATE OF domain` trigger on `threads`. If `NEW.domain IS NOT DISTINCT FROM OLD.domain`, allow the no-op update. Otherwise, test for an existing `signal_dispositions` row with `disposition = 'matched'` and the same `thread_id`; reject the update with a stable integrity exception if one exists.
2. Use one owner-controlled trigger function. It is `SECURITY DEFINER` only if the runtime role is intentionally denied SELECT on `signal_dispositions`; in that case it is owned by `watch_owner`, explicitly `VOLATILE`, has the fixed safe search_path and schema-qualified references defined under F1, and has PUBLIC EXECUTE revoked. The runtime role receives no direct execute privilege merely to fire the trigger. The function performs no writes and accepts no caller-controlled bypass.
3. Retain/use the supporting partial index `ix_signal_dispositions_thread_id_team_id` (or replace it only with an independently justified index that supports the exact `thread_id` matched-reference lookup). The guard's predicate must be exact; a deferred or duplicate disposition does not freeze Thread.domain.
4. Every matched-disposition finalizer must acquire the Thread row `FOR NO KEY UPDATE` after Team and before Hypothesis locks, refresh the locked Thread state from PostgreSQL, validate `Thread.team_id`, `Thread.domain = Team.domain`, and `Thread.status = 'active'`, insert the matched disposition, and hold the Thread lock through commit. This is the same row lock the competing domain UPDATE must obtain.
5. Use READ COMMITTED for this protocol. The guard must execute its matched-reference lookup after PostgreSQL has obtained the Thread row lock. The VOLATILE trigger's SPI query must observe the committed disposition after a wait; this is a required measured PostgreSQL property, not an assumption to infer from the design. If the test does not observe the committed row, the guard implementation is not accepted and must be redesigned before implementation.
6. The finalizer must not validate a previously loaded SQLAlchemy identity-map object after waiting for the row lock. Re-select the locked candidate with `populate_existing=True` or explicitly `Session.refresh()` the instance after the lock is acquired; then validate the refreshed `status`, `domain`, `team_id`, and matcher-profile fields. Do not rely on autoflush or object identity to refresh stale scalar values.

**Required race orders (two independent PostgreSQL sessions, actual runtime and trigger-owner roles)**

- **Match-first:** Session A locks Thread `FOR NO KEY UPDATE`, validates active/same-domain, inserts matched disposition and commits. Session B's domain UPDATE blocks on that same Thread row; after A commits, B's trigger sees the committed matched reference and rejects the domain change. Assert B receives the intended integrity error and the original domain remains.
- **Domain-update-first:** Session B locks/updates Thread.domain and commits before Session A obtains the Thread lock. Session A's lock statement waits; after it obtains the lock, its ORM refresh/reselect must read the committed new domain. If it no longer equals Team.domain, A must reject without inserting a disposition. If it still equals Team.domain, A may proceed. Assert no stale pre-wait ORM value is used.
- **No-op update:** with a matched reference present, `UPDATE threads SET domain = domain` (or equivalent equal-value assignment) succeeds; a distinct actual value change fails.
- **Pre-reference update:** a domain change before any matched reference may succeed, but a later matched insert must validate the then-current domain against Team.domain.
- **Non-matched reference:** duplicate/deferred dispositions do not activate the Thread-domain guard.
- **Status transition:** after matched commit, valid status changes to dormant/resolved remain permitted; no status immutability trigger is introduced.

### F4 — ORM locked-row freshness: explicit finalizer rule

The database row lock serializes writes; it does not automatically refresh an already-loaded SQLAlchemy identity-map object's scalar attributes. Every finalizer path that makes a matched eligibility decision must therefore:
- acquire the Thread row lock in canonical order;
- force a database refresh after the lock has been granted (`SELECT ... FOR NO KEY UPDATE` with `populate_existing=True`, or `Session.refresh(instance, with_for_update=...)` using the already held transaction);
- validate all decision-relevant values from that refreshed row, not from a candidate object loaded before a concurrent writer committed;
- ensure the refresh uses the same transaction/session and holds the lock until disposition commit.

**F4 exit evidence:** two-session test where the finalizer reads an active Thread into the identity map, another session changes status or domain and commits, and the finalizer then waits for/acquires the row lock. The finalizer must observe the committed new values. Assert both stale-domain rejection and stale-status ineligibility; also assert no disposition, Outcome, or terminal success Event is written on either rejected path.

### Exact replay after later lifecycle transitions — preserve the accepted history model

For a successfully committed matched disposition:
- replay validates the immutable D4.2 receipt, immutable SignalDisposition row and references, Task identity/attribution, typed terminal observation/Snapshot, Outcome attribution/hash, exact terminal Event payload/cardinality, and completion-time equality;
- replay does not rerun candidate search, matching, thresholding, or current lifecycle eligibility;
- replay must not require `Thread.status = 'active'`. A later valid `active → dormant` or `active → resolved` transition leaves the original matched result replayable and unchanged;
- replay does not add or require `thread_status_snapshot` or `thread_domain_snapshot` columns on SignalDisposition. The immutable receipt is the decision evidence; the Thread-domain guard preserves the identity premise after a matched reference.
- A later status transition must not rewrite the receipt, disposition, Outcome, terminal Event, or completion time. A corrupted/missing immutable record still fails closed; the lifecycle transition itself is not corruption.

### Consolidated PostgreSQL proof matrix additions

Run against the exact candidate SHA on a disposable PostgreSQL instance using the production-target role topology, not the development `watch` superuser. Use independent connections for concurrency cases and record PostgreSQL version, isolation level (READ COMMITTED for the specified interleavings), role used by each session, session count, blocking statement, commit order, observed row values, and final rows.

| ID | Proof | Required assertion |
|---|---|---|
| RW4-1B-F1-01 | Clean role bootstrap | Owner is NOLOGIN and owns protected objects; runtime is non-owner/non-superuser; migrator can SET ROLE owner but runtime cannot SET ROLE owner/migrator. |
| RW4-1B-F1-02 | Effective grants and inheritance | Assert role attributes, direct/transitive memberships, PUBLIC/default privileges, schema/table/column/sequence/function privileges; no runtime DDL, ownership, grant, trigger-control, or replication bypass. |
| RW4-1B-F1-03 | Trigger function execution | PUBLIC cannot EXECUTE privileged helpers; runtime allowed DML fires triggers successfully without unnecessary direct helper EXECUTE; fixed search_path/schema qualification verified. |
| RW4-1B-F1-04 | Runtime DML boundary | Every source-audited required operation succeeds; forbidden Event/Disposition UPDATE/DELETE and protected-table TRUNCATE fail. |
| RW4-1B-F1-05 | Cutover session identity | Stopped-writer migration with old owner sessions drained; post-restart application sessions are runtime-only. |
| RW4-1B-F2-01 | Writer inventory/role map | Checked-in development/bootstrap/CI/migration/test/smoke/application paths are inventoried; Operator confirms no production deployment; local untracked processes/roles are reconciled and every supported writer is assigned a principal and lock protocol. |
| RW4-1B-F2-02 | Unsupported writer denial | Direct/unapproved Thread INSERT/status/domain/profile writes are denied or demonstrably forced through the accepted canonical writer path. |
| RW4-1B-F2-03 | Lifecycle writer serialization | Each supported status/profile writer races with finalization in both orders and follows Task → Team → sorted Thread → sorted Hypothesis; Team revision is atomic where required. |
| RW4-1B-F3-01 | Guard no-op / predicate | Equal-value domain update succeeds; actual change after matched reference fails; duplicate/deferred references do not freeze domain. |
| RW4-1B-F3-02 | Match-first race | Matched insert commits first; waiting domain update sees committed reference and rejects. |
| RW4-1B-F3-03 | Domain-first race | Domain update commits first; waiting finalizer refreshes row, validates new domain, and rejects mismatch without writing disposition. |
| RW4-1B-F3-04 | Pre-reference domain change | Domain may change before matched reference; subsequent match checks current equality with Team.domain. |
| RW4-1B-F4-01 | Stale identity-map refresh | Finalizer preloads Thread, loses race, waits for lock, refreshes, and observes committed status/domain; stale ORM scalar values are not used. |
| RW4-1B-RP-01 | Replay after dormant | Commit matched while active; transition to dormant; replay returns the original result read-only and emits no writes. |
| RW4-1B-RP-02 | Replay after resolved | Commit matched while active; transition to resolved; replay returns the original result read-only and emits no writes. |
| RW4-1B-RP-03 | Replay integrity remains strict | Corrupt/missing/duplicate receipt, disposition, Outcome, or terminal Event still fails closed; ignoring current status does not weaken immutable evidence checks. |

These rows augment rather than replace the existing §10 proof matrix. Run all existing row constraints, FK/uniqueness, provenance marker, TRUNCATE/CASCADE/partition, migration rollback/cutover, receipt durability, KnowledgeChunk projection, TaskRuntime atomicity, and exact-replay proofs. SQLite and in-memory substitutes are not acceptable for database enforcement or concurrency.

### Finding disposition and remaining gate

- **F1:** design contract specified here; implementation-level closure requires the reproducible role bootstrap and effective-privilege proof.
- **F2:** **PARTIALLY RESOLVED; OPEN / BLOCKING.** The Operator has confirmed Watch has no production deployment. The checked-in development/bootstrap, CI, migration, test, smoke-script, and application-service paths have now been inventoried in §10.4. That closes the production-deployment uncertainty and the repository-source inventory task, but it does not establish an enforced runtime/owner boundary: the current Compose and CI bootstrap users are superusers, migration and test credentials are not separated by role, no protected Thread trigger/grant topology is installed, and no disposable-PostgreSQL privilege proof exists. Do not enable matched writes or claim F2 closure until the accepted role/credential topology and physical protections are implemented and proven. The inventory cannot enumerate untracked processes or credentials on the Operator's workstation.
- **F3:** design contract specified here; physical closure requires the actual trigger/function implementation and both independent PostgreSQL race orders.
- **F4:** design contract specified here; closure requires the ORM refresh implementation and stale-identity-map PostgreSQL/SQLAlchemy proof.

No schema, ORM, migration, application, test, database, or runtime changes are authorized by this section. The accepted distinction remains: status is historical-at-decision and may later change; domain becomes immutable after a matched reference; SignalDisposition receives no Thread status/domain snapshot columns.

## 11. Decisions requested from the Operator

This proposal intentionally separates recommendations from accepted decisions. Review the following:

1. Row shape: accept or amend the proposed one-row-per-(team_id, signal_id) shape and D5.2 reference matrix.
2. Cross-record enforcement: conditional Option A is accepted as the design direction, subject to the mandatory non-owner runtime/migration-owner role boundary and the Operator-accepted forward-only DB-attested cutover in §4.0.2. The exact marker/trigger/role implementation remains subject to physical review and PostgreSQL proof; if either prerequisite cannot be enforced, stop and return with a separately scoped Option B design.
3. **ACCEPTED:** duplicate disposition writes remain disabled until D4.1a canonical Team/hash arbitration is separately implemented and proven. Under accepted Decision 7, this is a prerequisite for enabling all three outcomes together; no matched/deferred-only partial rollout is permitted.
4. **ACCEPTED:** the separately reviewed D2 Task-identity migration is a hard prerequisite before any triage Task creation and before any SignalDisposition write or replay is enabled. Keep D2 identity columns/constraints out of the RW4-1 initial migration. Install the D2-dependent four-column composite FK only after SignalDisposition exists and a locked, transactional preflight proves the table is empty and triage Task identity data is valid; keep runtime disposition INSERT permission withheld until the FK is installed and verified. No caller/Event-only transitional substitute. Keep it separate from the RW4-1 migration; do not accept a transitional proof or caller/Event-only substitute.
5. **ACCEPTED:** database-enforced immutability and timestamp direction: reject UPDATE/DELETE on SignalDisposition; revoke effective runtime TRUNCATE privileges and reject TRUNCATE on protected tables; protect intake Events and their referenced Signal/Task/Team identity fields; assign `created_at` in the database using `clock_timestamp()` while making clear that it is insertion time, not commit order; and reserve trigger/owner maintenance for a separately controlled, audited migration/break-glass boundary. Exact triggers, grants, owner topology, partition behavior, and repository-specific timestamp conventions still require source review and real PostgreSQL proof.
6. TaskRuntime seam: accept one success_signal_triaged category for matched/duplicate/deferred; the typed observation fields, existing task_execution Outcome, task_completed Event index fields, atomic transaction, and exact replay equality rules in §8; no generic callback abstraction.
7. **ACCEPTED — all three outcomes enabled together.** Matched, duplicate, and deferred become available in one write-enable release only after every dependency below is implemented, independently reviewed, and proven. Prerequisite work may land in separate migrations/PRs; no partial disposition rollout is permitted. The bounded disposable-PostgreSQL proof matrix in §10 remains required, with the explicit additions in Decision 7 below.

The Operator has accepted the row shape, conditional Option A/forward-only cutover direction, the duplicate-write gate, the D2 Task-identity/FK prerequisite, database-enforced immutability/TRUNCATE/timestamp/maintenance direction, the triage-specific TaskRuntime terminal-evidence contract, Decision 7's all-outcomes-together rollout, and the D4.2 `assessment_receipt_stale` terminal-failure/permanent-v1-identity-occupancy rule. The Thread status/domain separation in §4.1 is an accepted Operator rule (2026-11-26): status is checked at the matched-disposition commit point and may later transition without invalidating the historical disposition; domain is immutable after a matched reference and requires a database guard; no status/domain snapshot columns are added to SignalDisposition. The physical enforcement, role boundary, lock interleavings, and PostgreSQL proofs remain subject to independent review and explicit design acceptance; implementation still requires separate authorization. No ORM, SQL, migration, TaskRuntime, ingestion, or test changes may be made.

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
4. **D4.2 matcher evidence closure and D4b pins:** fixture-supported minimum threshold, winner margin, score serialization, candidate/evidence/payload bounds, profile-size bias assessment, disposable-PostgreSQL query plan/cost, labeled positive/hard-negative fixtures, actual code-owned v1 matcher/embedding/chunking pins, and the immutable one-per-Task assessment receipt schema/unique identity/payload bounds/transaction boundary/recovery proof are accepted and proven. Current D4.2 proposal requires a separate durable receipt transaction before business finalization; its candidate-profile/Signal-projection fence and accepted `assessment_receipt_stale` TaskRuntime terminal-failure/replay mapping must be implemented and proven. A same-transaction alternative would require explicitly reopening that D4.2 contract. Matched writes remain disabled until this evidence gate closes.
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


## 10.2 Accepted Thread lifecycle operation and trust-boundary refinement (2026-11-26)

The Operator accepted the following refinement after the second architecture investigation. It resolves the previously open resolution envelope and corrects the database trust claim in F2. This is a design/documentation change only; it does not authorize code, ORM, SQL, migration, TaskRuntime, or test implementation.

### Resolution is an operation mode of the existing Operator Task

- Keep the existing task_type=operator_update. Do not add a resolve_thread Task type, a second TaskRuntime, or a parallel lifecycle service.
- Keep the existing OperatorUpdateRequest as the proposal-commit request with its existing non-empty proposal requirement. Add a separate typed ResolveThreadRequest at the same Operator application/Control Room boundary, with exactly thread_id, idempotency_key, and reason. The reason must contain at least one non-whitespace character and be at most 2,000 Unicode code points; preserve the submitted text exactly for the request fingerprint, Event, and replay comparison. The operation is a discriminated, mutually exclusive mode of the existing operator_update Task; it is not an empty-proposal workaround and cannot be combined with Hypothesis/EvidenceLink/ConfidenceChange proposals.
- The resolution mode is a Kernel/application-managed effect. It is not worker output, does not appear in allowed_writes, and does not grant a model or worker Thread lifecycle authority. update_thread remains limited to its existing Hypothesis/EvidenceLink/ConfidenceChange scope.
- The trusted host authenticates the Operator and supplies a trusted principal. Control Room validates the exact Team grant action resolve_thread against the Team derived from the locked target Thread; the existing generic operator_update grant is not a substitute. A caller-supplied Team ID, Operator ID, or permission assertion is not authoritative.
- The immutable operator_update_requested request provenance must bind operation=resolve_thread, target Thread ID, reason, trusted Operator identity, and idempotency key. Reuse task_id_for_request(team_id, idempotency_key) and the existing operator_update Task identity namespace, request fingerprint, and commit-marker/recovery mechanism; do not invent a second identity or recovery system. Exact semantic replay returns the original Task/result. Reuse of the same idempotency key with a different target, reason, operation mode, or Operator principal is a conflict.
- Keep task_type=operator_update, the existing TaskRuntime admission/attempt/recovery path, and the existing success_operator_update_committed terminal category. Add a narrowly typed resolution terminal-observation variant that records operation=resolve_thread, Thread ID, prior status, resolved status, reason, and thread_resolved Event identity. Do not fabricate proposal committed/rejected counts or broaden replay behavior for ordinary proposal-commit Tasks. The existing operator_update_committed business marker must record the resolution request fingerprint and Event identity so recovery can distinguish a committed resolution from an uncommitted request.
- Resolution is permitted only for active → resolved or dormant → resolved. resolved is terminal; repeated exact replay returns the prior result and does not append another Event. A resolved Thread cannot be reopened through this operation. The Team must satisfy the existing operator_update active-Team admission rule. The Thread must belong to that Team. Thread.domain is not changed.
- The resolution business transaction acquires the canonical Task → Team → Thread locks (no Hypothesis lock is needed because the operation does not touch Hypotheses), refreshes the locked Thread from PostgreSQL, validates its current status and Team ownership, updates Thread.status, increments Team revision exactly once, and appends exactly one immutable thread_resolved Event. Its exact payload is task_id, team_id, thread_id, operator_id, from_status, to_status=resolved, and reason. Status, revision increment, and Event commit or roll back together.
- The existing Operator update business-commit marker remains the durable recovery boundary. As in the current Operator update architecture, the business transaction that changes Thread status and writes thread_resolved is distinct from subsequent TaskRuntime terminalization. TaskRuntime remains the sole owner of Task terminal state and terminal Events; after a crash, its existing recovery path must detect the committed business marker and finish/replay without repeating the status transition, revision increment, or thread_resolved Event. Do not claim that Thread status/Event and Task terminalization are one database transaction.
- Do not update Thread.last_updated_at as a side effect unless a separate accepted contract defines that field's semantics. The immutable Event is the lifecycle chronology.
- A real status transition increments Team revision once. Exact replay, a rejected transition, a no-op, and a rolled-back transaction do not increment it. The general Team-revision rules are frozen in §10.3 below.

### Corrected D1/F2 trust model

Control Room is the single logical application authority for supported Task creation and for authorized Thread lifecycle operations. This is an application-code boundary, not a database identity boundary. PostgreSQL grants can distinguish roles and credentials; they cannot distinguish two code paths using the same database principal. Therefore:

1. watch_runtime is a non-owner, non-superuser runtime credential with only the application DML needed by the inventoried Watch paths. It cannot assume owner/migrator roles, alter schema/privileges, disable triggers, or bypass protected physical invariants.
2. The deployment must ensure that only the Watch application processes implementing the trusted Control Room/Kernel boundary receive and use that runtime credential. Host adapters authenticate and delegate; they do not connect to PostgreSQL to write Thread rows. Unsupported scripts, external processes, ad-hoc SQL clients, and administrative tools must not share the runtime credential.
3. If a deployment requirement includes protection against a hostile or nonconforming process that already possesses the same runtime credential, the shared-role model is insufficient. Stop and separately design a narrower database capability, function boundary, or distinct credential/process. Do not imply that ordinary table grants or triggers can identify the calling Python module.
4. PostgreSQL remains responsible for physical invariants that are independent of caller identity: immutable Event/disposition history, row-local constraints/FKs, the matched-Thread domain guard, protected-field guards, and effective TRUNCATE/trigger-bypass protections. Control Room/Kernel remains responsible for caller authorization, Task provenance, allowed operation mode, and use of the canonical transaction path.
5. F2 remains OPEN/BLOCKING until the complete development writer/credential inventory is reconciled with the actual local environment and the accepted enforcement proof passes. The Operator confirmed on 2026-11-26 that Watch has no production deployment; §10.4 records the checked-in development/bootstrap inventory. This closes the production-deployment-status question, not the local-machine inventory or privilege-enforcement requirements. Repository source search cannot prove absence of untracked processes, manually provisioned roles, or out-of-repository scripts.



### 10.3 Team revision for Thread lifecycle/profile changes

The canonical RW-5 world-memory lock helper remains the only Team-revision allocator. Extend its defined change set to include matcher-relevant Thread lifecycle/profile changes:

| Accepted transaction | Team revision behavior |
|---|---|
| activate_team commits approved starter Thread creation | Increment once for the activation transaction, regardless of the number of starter Threads created. |
| Operator resolve_thread mode commits an actual active/dormant → resolved transition | Increment once in the same business transaction as the status change and thread_resolved Event. |
| A separately supported pre-match Thread.domain change commits | Increment once in the same transaction; the resulting domain must still satisfy the Team/domain invariant for any later match. |
| Exact replay, rejected request, no-op assignment/transition, or rollback | No increment. |

The canonical revision protocol applies to any future supported Thread creation, status, or matcher-relevant profile writer. It does not authorize a dormancy writer in RW-5 first release, does not change the accepted D6 reactivation gate, and does not make Thread.last_updated_at a matcher input or revision substitute. A matched disposition does not freeze status; later supported lifecycle transitions remain valid historical changes. A matched disposition does freeze the referenced Thread's domain under the F3 database guard.

**Required proof addition:** test activation creating multiple starter Threads with one revision increment; resolution with one increment and one Event; exact replay with no second increment/Event; rejected/no-op/rollback with no increment; and a pre-match domain update serialized against receipt/finalization. These tests belong to the separately authorized RW-5 compatibility/Team-revision proof, not to RW4-1B physical-schema implementation.
### 10.4 Development-only database credential, process, and Thread-writer inventory (2026-11-26)

**Deployment status:** The Operator explicitly confirmed that Watch remains in development and has no production deployment. There is therefore no production host, production service credential, or production external-writer inventory to enumerate at this stage. This is an Operator-provided project fact, not an inference from the repository.

**Scope and evidence boundary:** The following inventory was performed against branch `rw4-1b-physical-persistence-design-20261125` at the audited source tree. It covers checked-in repository paths. It cannot inspect local PostgreSQL catalogs, the Operator's process list, untracked scripts, manually created roles, shell history, local environment variables, or processes outside the repository. No live database or local workstation was queried in this audit.

#### Credential and role inventory

| Purpose | Checked-in configuration / principal | Effective capability and finding |
|---|---|---|
| Development PostgreSQL bootstrap | `compose.yaml`: database `watch`, bootstrap user `watch`, password `watch` | The official PostgreSQL image's `POSTGRES_USER` bootstrap account is a superuser. It is not a least-privilege application role. The Compose file defines only PostgreSQL; it does not define a Watch application container or a separate runtime login. |
| Development migration | `migrations/env.py`: `DATABASE_URL`, defaulting to `postgresql+psycopg://watch:watch@localhost:5432/watch` | Alembic uses the same bootstrap credential by default. No `watch_owner` NOLOGIN owner, `watch_migrator` login, or separate migration DSN is provisioned in the repository. |
| Application runtime | No checked-in production or development application DSN/role bootstrap; core services receive injected SQLAlchemy `sessionmaker` instances | A future host can construct these services with any supplied credential. The repository does not prove which process constructs them or which principal it supplies. No `watch_runtime` role or restricted grant set exists in checked-in SQL/migrations. |
| PostgreSQL-backed tests | `tests/_database_config.py` requires explicit `TEST_DATABASE_URL`, PostgreSQL, and a database name other than `watch`; `tests/conftest.py` uses it | This resolver fails closed against the persistent database name `watch`. Migration tests use the test URL for schema creation/drop and migration execution, so the test principal must have elevated privileges inside the disposable test database. Tests are not using a distinct restricted runtime principal. |
| CI database | `.github/workflows/ci.yml`: `watch_ci` / `watch_ci`; both `DATABASE_URL` and `TEST_DATABASE_URL` point to `watch_ci` | CI's PostgreSQL service is ephemeral, but the image bootstrap account is also the migration/test principal. This is test isolation, not least-privilege role separation. |
| Local disposable test runner | `scripts/test-disposable-postgres.ps1`: ephemeral container, database `watch_local_disposable`, user/password `watch_test` | The runner isolates the database/container and restores environment variables. Its bootstrap user is still the database superuser; it does not prove restricted runtime privileges. |
| Embedding smoke utility | `core/embedding_smoke.py`: `TEST_DATABASE_URL` or fallback to `DATABASE_URL` | It creates a SQLAlchemy engine directly, inserts temporary Team/TeamPolicy/Signal rows, indexes/retrieves, then attempts cleanup. It has no explicit database-name guard of its own; if both variables are absent or misconfigured it can use the migration default/persistent `watch` database. It does not write Threads. |
| Database extension smoke test | `tests/test_database.py`: `DATABASE_URL` or fallback to `postgresql+psycopg://watch:watch@127.0.0.1:5432/watch` | It opens a direct engine and reads the vector extension version. Unlike the main test fixture, this test has a persistent-`watch` fallback. CI overrides it with the ephemeral CI URL; local invocations without an explicit disposable `DATABASE_URL` can target the Compose database. |

**Credential conclusion:** the checked-in environment has no separate bootstrap/owner, migration, runtime, test-maintenance, and runtime-service roles. Development Compose, Alembic, and the disposable test runner use bootstrap users with superuser capability; CI uses an ephemeral bootstrap superuser. This is a material least-privilege gap, not a merely undocumented role topology.

#### Database-capable process inventory

| Process / code group | Database access pattern | Thread write authority observed |
|---|---|---|
| Core application services (`core/ingestion.py`, `dispatcher.py`, `task_runtime.py`, `operator_application.py`, `world_memory.py`, `update_thread_context.py`, `update_thread_worker.py`, and other service modules) | Receive injected SQLAlchemy `Session`/`sessionmaker`; no engine creation or process bootstrap is defined in these modules | No production `Thread` INSERT, `Thread.status` assignment, or `Thread.domain` assignment was found. Existing paths read Thread rows, validate Team/status/domain, and update related Hypothesis/EvidenceLink/ConfidenceChange records. |
| Host / Control Room adapter | Operator application boundary exists in `core/operator_application.py`; no runnable host server/adapter composition or process entrypoint is checked in | Intended authority boundary only. The repository does not contain a production host process that provisions sessions or writes Thread lifecycle state. |
| Alembic migration process | `uv run alembic upgrade head`, using `DATABASE_URL` in `migrations/env.py` | Migration `0019_rw1_world_memory.py` creates the `threads` table and its base indexes/constraints. It does not seed Thread rows or install Thread status/domain guards. |
| Pytest process | `tests/conftest.py` creates an engine/sessionmaker from `TEST_DATABASE_URL`; tests directly insert fixture Threads and delete them during teardown | Test-only fixture writes. `tests/test_update_thread.py` also directly sets a fixture's `thread.status = "resolved"` to exercise rejection behavior. Other Thread fixtures occur in `tests/test_evaluations.py` and `tests/test_world_memory.py`. These are not supported application writers and rely on the test database's elevated principal. |
| Embedding smoke process | `python -m core.embedding_smoke`; direct engine from environment | Inserts Team, TeamPolicy, Signal, and KnowledgeChunk-related projection data; no Thread writes. |
| Local disposable-PostgreSQL PowerShell runner | Starts/removes an ephemeral PostgreSQL container, runs Alembic, Ruff, Mypy, pytest | Does not implement Watch runtime behavior. It provisions a superuser test database. |
| GitHub Actions CI runner | Starts ephemeral PostgreSQL service, runs Alembic, Ruff, Mypy, pytest | Same elevated bootstrap principal for migration and tests; no production service process. |
| Compose PostgreSQL service | Persistent local volume and host port 5432; database process only | Does not run Watch application code. |
| External/third-party processes | No checked-in host adapter, scheduler, importer, admin UI, seed service, or production worker process identified | No external writer can be inferred from source. Production deployment absence is Operator-confirmed; untracked local processes remain outside this repository audit. |

#### Thread row write-path inventory

| Writer / candidate | Insert | `status` update | `domain` update | Disposition |
|---|---:|---:|---:|---|
| Production Watch application source | None found | None found | None found | No current supported production Thread writer is implemented in this repository. |
| `activate_team` | Intended canonical creator for approved starter Threads | — | — | Accepted architecture target; not implemented in the audited source tree. |
| Operator `resolve_thread` mode | — | Intended active/dormant → resolved | — | Accepted design in §10.2; not implemented. |
| `update_thread` worker / `operator_update` proposal commit | Existing Thread only | No lifecycle assignment found | No assignment found | Reads/updates knowledge attached to an existing Thread; must not acquire lifecycle authority. |
| RW-4 triage | Explicitly prohibited in v1 | No | No | Matches existing Threads or defers; automatic Thread creation remains disabled. |
| Migration `0019_rw1_world_memory.py` | Creates table, not rows | No | No | Schema DDL only. |
| Test fixtures | Yes | Test-only direct mutation in `tests/test_update_thread.py` | No assignment found | Test setup/teardown only; isolated disposable DB required. |
| Ad hoc SQL / local admin / untracked scripts | Not discoverable from repository | Not discoverable | Not discoverable | Unsupported and not proven absent on the local workstation. Must not receive the future runtime credential. |

#### Enforcement assessment

The current schema does provide row-local checks and relational integrity: `threads.team_id → teams.id`, unique `(id, team_id)`, status membership in `active/dormant/resolved`, and non-empty `domain/title`. The composite Hypothesis-to-Thread FK protects same-Team ownership.

It does **not** currently provide the physical protections required by RW4-1B:

- No Thread `BEFORE UPDATE OF domain` guard exists. An actual `Thread.domain` change is not blocked after a matched disposition because SignalDisposition does not yet exist and no future-reference trigger is installed.
- No Thread status transition guard or lifecycle audit Event trigger exists. The CHECK constraint validates allowed status values, not who may change status or which transition is legal.
- No restricted runtime role, NOLOGIN object owner, separate migration credential, grant/revoke matrix, membership fence, or effective-privilege test exists.
- The current development bootstrap credential can bypass ordinary trigger/grant protections as superuser. A Python Control Room boundary cannot be enforced against arbitrary SQL using that same credential.
- No Event/SignalDisposition immutability or protected-table TRUNCATE protections from the proposed RW4-1B design have been installed in the migration chain.

**Required enforcement target:** provision a NOLOGIN `watch_owner`, separate `watch_migrator` credential, and non-owner/non-superuser `watch_runtime`; make the runtime DSN available only to the trusted Watch application host; isolate tests and maintenance under disposable-database credentials; install the reviewed domain/immutability/guard triggers and least-privilege grants; then prove direct forbidden DML, UPDATE/DELETE/TRUNCATE, trigger bypass, role membership, and both Thread-domain/match lock race orders on real disposable PostgreSQL using the actual runtime and migration principals.

**Specific development-tool safety defects to address before routine local use:** change `tests/test_database.py` to use the fail-closed `resolve_test_database_url` rather than its persistent `watch` fallback, and change `core/embedding_smoke.py` to require an explicit disposable test URL and reject the persistent database name rather than falling back to `DATABASE_URL`. These are separate, narrow developer-tool hardening changes; no such code change is made in this RW4-1B documentation audit.

**F2 disposition:** the repository-source inventory is complete for the checked-in tree and the Operator has confirmed no production deployment. F2 is still **OPEN / BLOCKING** because the current development topology does not enforce the accepted trusted application boundary or the PostgreSQL physical invariants, and because untracked local processes/credentials cannot be enumerated remotely. The absence of a production deployment is not equivalent to successful privilege enforcement.

**Scope:** this inventory is a source/configuration audit. It does not provision roles, modify migrations, change ORM/application/test code, inspect a live local database, or authorize matched/duplicate/deferred writes.

