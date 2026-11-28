# RW4-1 F1 — production DML writer audit

**Status:** source-level audit complete; deployment identity and runtime privilege proof remain open
**Audited revision:** `3ec965148385608f0edaf6e7d99c168239ee830f` (PR #222 branch)
**Scope:** all 45 `core/*.py` modules, all 20 checked-in Alembic version files, the role bootstrap script, and the disposable embedding smoke utility. Tests and migration DML are classified separately from production application DML.

This document is an inventory, not an accepted grant manifest. It does not authorize role grants, SECURITY DEFINER functions, migrations, runtime changes, or a production cutover.

## 1. Executive result

The production application source has **21 tables with application DML** and a further set of tables that are read/locked but have no application writer. The write surface is not equivalent to the lock surface:

- The 114-site row-lock ledger remains 89 unconditional `FOR UPDATE`, 24 unconditional `FOR SHARE`, and one conditional Event lock.
- The application writes Events in many transactions, but Events are append-only in application source; the one conditional Event lock is not an Event update.
- Ingestion inserts Signals; the indexer locks and reads Signals but does not update them.
- World Memory inserts EvidenceLinks and later locks/reads them; it does not update or delete them.
- Several assessment tables are immutable insert-only records, although they have lock/read call sites.
- The indexing subsystem performs real DELETE+INSERT replacement of projection rows.
- There are no production application writers for Team, TeamPolicy, or Thread in the audited source. A disposable smoke utility does create/delete Team and TeamPolicy rows, but it uses the explicit test database URL and is not a production writer.

Therefore, the clean reconciliation is a **table/column DML ledger plus a separate lock-capability ledger**. Do not assign UPDATE to a table merely because a call site uses `FOR UPDATE`.

## 2. Scope and audit method

Inspected all 45 Python modules under `core/`, all 20 migration version files, `scripts/provision_database_roles.py`, and `core/embedding_smoke.py` at the audited revision. The source pass included:

- ORM `Session.add/add_all/delete` and implicit-flush mutations of loaded mapped objects;
- SQLAlchemy Core `insert/update/delete` statements and PostgreSQL `ON CONFLICT` inserts;
- DML in Alembic migrations and the database-role bootstrap;
- disposable smoke-test writes and cleanup;
- transaction boundaries (`session_factory.begin()`) and caller-owned Session helpers.

The audit excludes test fixture DML from application privileges. Tests use disposable/admin test connections and are not evidence that the production runtime role needs those privileges.

The model inventory in `core/models.py` contains 24 mapped tables. The application writer findings below distinguish direct application writes from test/smoke and migration-only operations.

## 3. Application DML writer matrix

“Insert columns” means the application constructs or supplies these values. Database-generated/defaulted columns may be omitted from the SQL INSERT and must be confirmed from emitted SQL before freezing column-level INSERT grants. “Update columns” is the union of columns mutated by application code; it is not permission to update every column in the row.

| Table | Application DML | Writer / transaction owner | Insert columns or update columns |
|---|---|---|---|
| `tasks` | INSERT, UPDATE | INSERT: Control Room helpers, inside caller-owned transaction (PlanService, OperatorApplication, TaskRuntime follow-on paths). UPDATE: TaskRuntime-owned admission/finalize/retry transactions. | INSERT: `id, team_id, task_type, status, attempt_count, policy_version, objective_id, plan_id, plan_action_id, allowed_writes, budget, completed_at, max_attempts`. UPDATE: `status, attempt_count, completed_at`. |
| `events` | INSERT only | ObjectiveService `_add_event` helper and direct Event construction by Control Room, Context, Ingestion, TaskRuntime, WorldMemory, assessment services, GenerationCost, and other domain services. Insert is part of each caller's transaction. | `id, task_id, type, payload, created_at`. No application UPDATE or DELETE found. |
| `signals` | INSERT only | IngestionService `_commit`, in its own transaction. | `id, domain, source_type, origin_url, fetched_at, content_hash, snapshot_ref`. No application UPDATE or DELETE found. |
| `objectives` | INSERT, UPDATE | ObjectiveService `_create/_transition`, each own transaction. | INSERT: `id, team_id, statement, status` (status has a Python-side mapped default as well as a server default). UPDATE: `status`. |
| `plans` | INSERT, UPDATE | PlanService `_create/transition`, own transaction. | INSERT: `id, team_id, objective_id, created_by_task_id, accepted_event_id, proposal_hash, assessment_basis, assessment_created_at, budget, completion_condition` (status/default fields are model defaults). UPDATE: `status, stopped_reason, successor_plan_id`. |
| `plan_actions` | INSERT only | PlanService, same transaction as Plan and materialized Tasks. | `plan_id, action_id, action`. |
| `outcomes` | INSERT only | TaskRuntime `finalize`, same transaction as Task terminal state and Events. | `id, team_id, subject_kind, subject_id, outcome_type, expected, observation_snapshot_ref, observation_hash, observed_at, recorded_by_task_id`. |
| `evaluations` | INSERT, UPDATE | EvaluationService `propose/record/reject`, each own transaction. | INSERT: `id, team_id, outcome_id, conclusion, findings, evaluator_kind, evaluator_identity, evaluator_revision, status, idempotency_key, proposal_hash, created_by_task_id`. UPDATE: `status, resolved_by_task_id, resolved_at, rejection_reason`. |
| `evidence_links` | INSERT only | EvaluationService proposal transaction and WorldMemoryCommitService proposal transaction. | `id, team_id, subject_kind, evaluation_id, hypothesis_id, originating_task_id, source_kind, outcome_id, signal_id, snapshot_ref, snapshot_hash, stance, quote_text, quote_start, quote_end, reference_key`. No application UPDATE or DELETE found. |
| `learning_changes` | INSERT, UPDATE | INSERT: ExperienceDistiller proposal transactions. UPDATE: LearningCommitService decision transaction. | INSERT fields include `id, team_id, target_kind, target_id, operation, proposed_state, previous_state, committed_state, evidence_basis, evidence_basis_hash, status, idempotency_key, proposed_by_task_id, committed_by_task_id, operator_id, decision_reason, created_at, committed_at`. UPDATE: `status, previous_state, committed_state, committed_by_task_id, operator_id, decision_reason, committed_at`. |
| `learning_change_operator_provenance` | INSERT only | ExperienceDistiller operator-proposal transaction. | `learning_change_id, team_id, issuer, subject, recorded_at`. |
| `knowledge_items` | INSERT, UPDATE | INSERT and compare-and-set UPDATE: LearningCommitService decision transaction. Additional review-state UPDATE: TaskRuntime finalization transaction. | INSERT: all business fields explicitly supplied by the create path: `id, team_id, kind, title, statement, body, applicability, preconditions, assumptions, limitations, non_applicability, failure_modes, known_counterexamples, missing_information, uncertainty, confidence, status, version, last_validated_at, review_after, origin_learning_change_id, current_learning_change_id, supersedes_item_id, superseded_by_id`. UPDATE union: `kind, title, statement, body, applicability, preconditions, assumptions, limitations, non_applicability, failure_modes, known_counterexamples, missing_information, uncertainty, confidence, status, version, last_validated_at, review_after, current_learning_change_id, superseded_by_id, updated_at`. |
| `task_generation_charges` | INSERT, UPDATE | GenerationCostService reserve/reconcile/mark-unknown transactions. | INSERT: `id, task_id, attempt_count, operation, provider, model, pricing_revision, max_input_tokens, max_output_tokens, input_usd_per_million_tokens, output_usd_per_million_tokens, reserved_cost_usd, accounted_cost_usd, input_tokens, output_tokens, request_id, status, failure_reason, created_at, settled_at`. UPDATE: `input_tokens, output_tokens, request_id, accounted_cost_usd, status, failure_reason, settled_at`. |
| `knowledge_chunks` | INSERT, DELETE | SignalIndexer projection replacement transaction. | INSERT: `id, signal_id, chunk_index, chunk_text, chunk_hash, source_snapshot_ref, source_content_hash, chunking_version, embedding, embedding_provider, embedding_model, embedding_revision, embedding_configuration, embedding_dimensions, embedding_space_key`. DELETE: rows by `signal_id`. No application UPDATE found. |
| `team_experience_chunks` | INSERT, DELETE | TeamExperienceIndexer projection replacement/ineligibility transactions. | INSERT: `id, knowledge_item_id, team_id, item_version, item_content_hash, origin_learning_change_id, current_learning_change_id, content_hash_scheme, chunk_index, chunk_text, chunk_hash, chunking_version, embedding, embedding_provider, embedding_model, embedding_revision, embedding_configuration, embedding_dimensions, embedding_space_key`. DELETE: rows by `knowledge_item_id`. No application UPDATE found. |
| `team_experience_index_state` | INSERT, UPDATE | TeamExperienceIndexer `_upsert_index_state`, own transaction. | INSERT fields: `id, knowledge_item_id, team_id, item_version, item_content_hash, origin_learning_change_id, current_learning_change_id, content_hash_scheme, status, embedding_space_key, chunk_count, attempt_count, last_error_kind, last_attempt_at, indexed_at`. UPDATE: `item_version, item_content_hash, origin_learning_change_id, current_learning_change_id, content_hash_scheme, status, embedding_space_key, chunk_count, last_error_kind, attempt_count, last_attempt_at, indexed_at, updated_at`. |
| `hypotheses` | INSERT, UPDATE | WorldMemoryCommitService; transaction is opened by `commit_model`/default `commit`, or supplied by the caller and then caller-owned. | INSERT: `id, team_id, thread_id, statement, status, confidence, created_at, last_touched_at`. UPDATE: `confidence, status, last_touched_at`. |
| `confidence_changes` | INSERT only | WorldMemoryCommitService, same transaction as Hypothesis mutation and Events. | `id, team_id, hypothesis_id, from_confidence, to_confidence, cause_kind, evidence_link_id, created_by_task_id, idempotency_key, created_at`. |
| `knowledge_quality_assessments` | INSERT only | KnowledgeQualityAssessmentService `record`, own transaction. | Assessment identity, Task/Team/LearningChange bindings, proposal/evidence/rubric/evaluator hashes and revisions, dimensions, narrative, lineage report and hashes, idempotency key, and recorded timestamp. Immutable after insert by migration guard. |
| `knowledge_revalidation_assessments` | INSERT only | KnowledgeRevalidationAssessmentService `record`, own transaction; inserts its recorded Event first, then assessment in the same transaction. | Assessment identity, Task/Team/attempt/LearningChange/KnowledgeItem bindings, target and proposal hashes, evidence refs, evaluator/freshness/findings/result, idempotency/request/recorded-Event bindings, timestamp and payload hash. Immutable after insert by migration guard. |
| `knowledge_lifecycle_assessments` | INSERT only | KnowledgeLifecycleAssessmentService `record`, own transaction; inserts its recorded Event first, then assessment in the same transaction. | Assessment identity, Task/Team/attempt/LearningChange/KnowledgeItem bindings, target/proposal/evidence hashes, rationale/findings/result, successor binding fields, idempotency/request/recorded-Event bindings, timestamp and payload hash. Immutable after insert by migration guard. |

### 3.1 Explicitly no production application DML found

| Table | Finding | Lock relevance |
|---|---|---|
| `teams` | No production application INSERT/UPDATE/DELETE writer found. | Team is locked by multiple services; needs a lock capability without granting speculative UPDATE. |
| `team_policies` | No production application INSERT/UPDATE/DELETE writer found. Configuration/bootstrap ownership is not represented by a production service. | TeamPolicy has multiple `FOR SHARE` lock sites; lock-only. |
| `threads` | No production application INSERT/UPDATE/DELETE lifecycle writer found. | Thread is locked by Operator/WorldMemory paths; F2 writer ownership remains open. |
| `knowledge_quality_assessments`, `knowledge_revalidation_assessments`, `knowledge_lifecycle_assessments` | Application inserts only; migration 0017 installs immutable row/truncate guards. | Existing lock sites are read/serialization behavior, not update workflows. |
| `events`, `signals`, `evidence_links` | Application inserts only. | Their row-lock sites do not justify UPDATE grants. |

No application DELETE was found outside the two derived projection tables `knowledge_chunks` and `team_experience_chunks`. No application sequence use was found: mapped primary keys are UUIDs, not database sequences.

## 4. Transaction ownership and cross-service composition

The DML authority must follow the actual transaction owner:

1. **Control Room is a Session-bound helper, not a transaction owner.** `core/control_room.py` accepts a caller-owned Session and inserts Task plus optional request Event. Callers include PlanService, OperatorApplication, and TaskRuntime follow-on request creation. Its writes must stay in the caller's transaction.
2. **TaskRuntime owns admission/finalization/retry transactions.** Admission updates Task status/attempt and inserts `task_started`; finalization inserts Outcome/Event rows and updates Task terminal fields; retry changes Task status and appends retry Events. Its finalization path also marks due KnowledgeItems `needs_review`.
3. **WorldMemoryCommitService supports both ownership modes.** `commit_model` opens a transaction; `commit(..., session=...)` uses the caller's transaction. Do not create a second transaction around the supplied Session.
4. **LearningCommitService deliberately separates business decision from Task terminalization.** It commits LearningChange/KnowledgeItem/Event in its own transaction; TaskRuntime owns the later Task/Outcome/terminal Event transaction.
5. **Indexing is a separate writer workflow.** SignalIndexer and TeamExperienceIndexer own projection transactions. Their DELETE+INSERT operations are not TaskRuntime writes and should not be attributed to the runtime role until the deployed worker/process identity is chosen.
6. **Assessment recorders own their assessment+recorded-Event transactions.** These records are immutable after insert; do not grant UPDATE/DELETE to make their lock sites work.
7. **OperatorApplication is a composition/orchestration layer.** It opens request/task transactions, delegates Task insertion to Control Room, then invokes TaskRuntime and WorldMemory. It has no separate direct ORM writer for Team/Thread lifecycle.

The application currently exposes a shared `session_factory` pattern in services; there is no checked-in production host/composition root selecting distinct database logins for Operator, TaskRuntime, indexing, or maintenance. Thus a source-level service matrix cannot yet be translated into independently enforced service identities.

## 5. Separate administrative, smoke, and migration DML

### 5.1 Disposable embedding smoke utility

`core/embedding_smoke.py` inserts temporary Team, TeamPolicy, and Signal rows, runs SignalIndexer (which writes KnowledgeChunk), then deletes KnowledgeChunk, Signal, TeamPolicy, and Team rows. Its module instructions and `resolve_test_database_url` require explicit `TEST_DATABASE_URL`; it is intended for a disposable database, not the production runtime. These writes must not be used to justify Team/TeamPolicy DML grants on `watch_runtime`.

### 5.2 Database-role bootstrap

`scripts/provision_database_roles.py` uses the bootstrap administrator to create `watch_owner`, `watch_migrator`, and `watch_runtime`, change database/schema ownership, revoke PUBLIC privileges, and establish default SELECT privileges. This is administrative provisioning, not an application writer. The bootstrap administrator must remain separate from application credentials.

### 5.3 Alembic migrations

Migrations run under `watch_migrator`, which uses `SET ROLE watch_owner` for the online CLI path. The historical data-changing migrations include:

- `0005_multi_action_plans.py`: INSERT into `plan_actions`; UPDATE `tasks` and `plans` while migrating the old action representation.
- `0009_task_lifecycle_outcome.py`: UPDATE `tasks.created_at` from historical `task_started` Events.
- `0015_r7b_history_pointer.py`: UPDATE `knowledge_items` to populate history pointers.
- `0016_team_experience_history_pins.py`: UPDATE `team_experience_chunks` and `team_experience_index_state` to populate history pins.
- `0019_rw1_world_memory.py`: UPDATE `evidence_links` during the controlled legacy-shape migration.
- Other migration `op.execute` occurrences include DDL, trigger/function definitions, or validation SELECTs rather than ongoing application DML.

Migration privileges belong to the migrator/owner path and do not imply runtime grants. These one-time transformations are not recurring production writer capabilities.

## 6. Reconciled privilege design

### 6.1 Actual writer privileges

- Use column-level INSERT grants where the SQL emitted by the ORM/statement uses a bounded explicit column set.
- Use column-level UPDATE grants for the exact union of changed columns in §3. This also supplies PostgreSQL's UPDATE privilege prerequisite for `SELECT ... FOR UPDATE` / `FOR SHARE` on those relations.
- Do not grant UPDATE on `teams`, `team_policies`, `threads`, `events`, `signals`, `evidence_links`, immutable assessment tables, or insert/delete-only projection tables merely to satisfy row locking.
- DELETE is table-level, not column-level. Prefer narrowly scoped owner-controlled delete functions for projection replacement (fixed table and predicate, typed parent ID, no dynamic SQL) over broad direct DELETE on projection tables. If direct DELETE is retained, isolate the indexer in a separate login and grant DELETE only to that login.
- No sequence grants are required by the UUID-backed model inventory.

### 6.2 Lock-only capabilities

With no UPDATE privilege on a relation, a direct SQLAlchemy `SELECT ... FOR UPDATE` or `FOR SHARE` cannot be authorized by SELECT alone. Use fixed, owner-controlled lock helpers for relations whose application DML has no UPDATE columns:

- `teams`, `team_policies`, `threads`;
- `events`, `signals`, `evidence_links`;
- immutable assessment tables that have lock sites.

Each helper should have a fixed relation, fixed lock mode, typed primary-key input, no dynamic SQL/predicate, `SECURITY DEFINER` only where needed, ownership by `watch_owner`, fixed trusted search path, schema-qualified relation references, and PUBLIC EXECUTE revoked. The helper acquires the lock in the caller's existing transaction; the caller performs its ordinary SELECT afterward. Preserve READ COMMITTED where a post-wait statement snapshot is part of the concurrency contract. Do not make the helper commit or start another transaction.

For tables with real application UPDATE columns (`tasks`, `objectives`, `plans`, `evaluations`, `learning_changes`, `knowledge_items`, `task_generation_charges`, `team_experience_index_state`, `hypotheses`), the exact UPDATE allow-list provides the needed row-lock privilege. A lock helper is not a meaningful per-callsite isolation boundary if the same login already has UPDATE on that table for another workflow.

### 6.3 One login versus multiple writer identities

A single shared `watch_runtime` login can only receive the **union** of the application DML capabilities in §3. Column-level grants limit which columns may change, but cannot distinguish which Python service issued the statement. A lock helper does not prevent another service using that same login from exercising an already-granted UPDATE privilege.

True per-service isolation requires separate login roles / pools / DSNs (for example, application core, indexing worker, and any maintenance writer), with explicit ownership of each workflow and verified host wiring. No such production composition root or deployed DSN consumer is present in this repository. Do not invent role splits or grants before that runtime topology is accepted.

Recommended current path: keep `watch_runtime` SELECT-only; complete the deployment identity and external writer inventory; then decide whether the first deployable runtime is one shared least-privilege role or distinct writer identities. Only after that freeze the grant manifest and positive/negative runtime tests.

## 7. Remaining evidence required before F1 can close

1. Confirm the production host/composition root, exact DSN consumer(s), and whether Operator, TaskRuntime, indexing, and maintenance run under one or multiple PostgreSQL logins.
2. Inventory external writers not represented in this repository: provisioning/configuration tools, operations scripts, data repair, scheduled workers, backups/restores, and deployment automation. Identify which ones connect as owner, migrator, runtime, or a separate maintenance identity.
3. Capture SQL emitted by representative ORM INSERT/UPDATE paths to verify exact INSERT columns and that column-level UPDATE grants suffice for each flush/CAS path.
4. Decide the bounded DELETE mechanism for `knowledge_chunks` and `team_experience_chunks`; verify the parent-key predicate and worker identity.
5. Implement fixed lock helpers only for relations with no UPDATE allow-list; verify lock acquisition and subsequent SELECT on the same connection/transaction, including post-wait visibility.
6. Add per-login privilege assertions:
   - `has_any_column_privilege` must detect accidental INSERT/UPDATE grants;
   - `has_column_privilege` must assert each allowed and denied column;
   - table-level DELETE/INSERT/UPDATE/TRUNCATE and sequence privileges must be checked;
   - runtime must not SET ROLE owner, disable triggers, or use replication-role bypass.
7. Run real service workflows using the exact deployed runtime login(s), including both successful and rejected/rollback paths. Existing role tests only prove isolation of the current SELECT-only role; they do not prove application runnability.
8. Verify migration role, runtime roles, helper ownership, PUBLIC execute revocation, schema/table/sequence ACLs, and session role identity on a fresh disposable PostgreSQL instance.

## 8. Scope and non-authorization

This audit does not implement any role grant, helper function, migration, ORM change, application DML change, or database operation. It does not create SignalDisposition, enable disposition writes, close F1, close F2, accept the RW4-1 physical design, or authorize RW4-1 implementation. The exact physical DDL draft in PR #222 remains a draft pending independent review and separate Operator acceptance/authorization.


## 9. Deployment identity decision follow-up

The deployment identity question is now documented separately in [the F1 deployment identity model proposal](rw4-1b-f1-deployment-identity-model-proposal.md). Its recommendation is one shared core application login for transaction-sharing domain services, with a conditional separate indexer login only if SignalIndexer and TeamExperienceIndexer are proven to run in a distinct process with their own engine/pool/DSN. Do not split identities by Python class or create unused roles.

The DML inventory is source-complete but is not yet a grant manifest. The exact initial topology, external/maintenance writers, indexer process boundary, emitted INSERT SQL, and runtime positive/negative workflow proofs remain open. Keep watch_runtime SELECT-only until the Operator accepts the deployment topology and a separate implementation authorization is issued.
