# RW4-1 F1 — deployment database identity model (decision proposal)

**Status:** Proposed deployment identity model; requires Operator acceptance. This is not a grant manifest and does not authorize role provisioning changes, grants, helper functions, migrations, runtime wiring, or database cutover.

**Baseline:** PR #222 F1 DML writer audit, audited revision `3ec965148385608f0edaf6e7d99c168239ee830f`; current `main` baseline remains PR #221 merge `c648892e4896113700c8103397be01c11c0d22ed`.

## 1. Decision to make

The source audit identifies application write capabilities, but the repository has no production host/composition root or runtime DSN consumer. Therefore the next decision is not a list of PostgreSQL grants. It is the deployment topology that determines which code executes under each login.

The design must preserve transaction ownership. A role boundary is useful only when the corresponding code has a real process/connection boundary and can use a separate engine/pool/DSN for the complete transaction.

## 2. Source facts

The current repository supports these findings:

1. `watch_owner` is NOLOGIN and owns protected database objects.
2. `watch_migrator` is a LOGIN/NOINHERIT role that may SET ROLE to `watch_owner` for the ordinary Alembic CLI path.
3. `watch_runtime` is LOGIN and SELECT-only. No production host consumes it.
4. Control Room is Session-bound and does not own transactions. Task creation occurs inside transactions owned by PlanService, OperatorApplication, and TaskRuntime follow-on paths.
5. TaskRuntime owns Task admission, retry, and finalization transactions. It may invoke other domain components inside those same transaction boundaries.
6. OperatorApplication is an orchestration layer; it is not an independent database transaction/security boundary.
7. WorldMemoryCommitService can either own a transaction or participate in a caller-supplied Session. The latter remains caller-owned.
8. LearningCommitService and TaskRuntime intentionally own different transactions for business decision and Task terminalization.
9. SignalIndexer and TeamExperienceIndexer have distinct projection-writing workflows. They write derived projection state, including DELETE+INSERT replacement in `knowledge_chunks` and `team_experience_chunks`, and state upserts in `team_experience_index_state`.
10. No production deployment entrypoint, worker supervisor, runtime DSN consumer, or documented production process topology exists in the repository. `compose.yaml` is a PostgreSQL development service; its `watch` bootstrap credential is not an application identity.
11. The embedding smoke utility is explicitly disposable/test-database-only. Its temporary Team/TeamPolicy/Signal writes do not justify production runtime privileges.
12. No production Team, TeamPolicy, or Thread lifecycle writer exists in the audited application source. Those capabilities must not be assigned speculatively.

## 3. Options considered

### Option A — one shared application login

One application login is used by every in-process service and worker.

**Advantages**
- Matches the current shared `session_factory`/Session composition.
- Does not pretend that service classes sharing one transaction are separate trust boundaries.
- Simplest first deployable host model.
- Allows column-level DML and lock-helper capabilities to be tested against one actual application identity.

**Disadvantages**
- The login receives the union of every application workflow's DML permissions.
- PostgreSQL cannot distinguish whether a statement came from OperatorApplication, TaskRuntime, IngestionService, or LearningCommitService.
- A compromised component can exercise any privilege granted to the shared login.
- Projection DELETE/INSERT permissions become available to the core application if indexing remains in the same identity.

**Assessment:** Correct baseline when those workflows run in one process or share one database engine/connection pool. It is not per-service isolation.

### Option B — one login per Python service/class

Create separate logins for Control Room, TaskRuntime, OperatorApplication, IngestionService, WorldMemory, and each other service.

**Advantages**
- Superficially narrow per-service grants.

**Disadvantages**
- Most of these are not independently deployed processes.
- Caller-owned Sessions and cross-service atomic transactions cannot safely switch database identities halfway through a transaction.
- It would require pervasive engine/session plumbing or transaction fragmentation.
- It would falsely imply isolation that the runtime does not actually provide.
- It risks breaking atomicity and accepted transaction ownership.

**Assessment:** Reject. A class/module is not a deployment identity boundary.

### Option C — core application plus independently deployed indexer

Use one core application login for the current transaction-sharing domain services. Use a second login for indexing only if the indexers run as a separate process with its own engine, pool, and DSN.

**Advantages**
- Preserves current transaction boundaries.
- Isolates the two real projection replacement writers from the core application's DML authority.
- Gives the indexer only the projection write surface it needs.
- Can be introduced at a genuine deployment boundary without splitting TaskRuntime/Control Room transactions.

**Disadvantages**
- Requires an actual worker entrypoint and deployment configuration, neither of which currently exists.
- Requires verifying whether indexer calls are currently in-process, scheduled by another component, or intended for a separate worker.
- Requires a complete read allow-list for the indexer and positive/negative workflow tests.

**Assessment:** Recommended target evolution, conditional on proving a real separate worker boundary. Do not provision or grant the indexer role until that boundary exists.

## 4. Recommended identity topology

The following is the proposed target model. Role names are design labels; only the currently provisioned roles in §2 exist today.

| Identity | Login? | Purpose | DML authority |
|---|---:|---|---|
| Bootstrap administrator | Yes, external/provisioning only | Fresh database/cluster bootstrap, extension install, initial role creation, emergency DBA operations | Administrative; never supplied to application processes |
| `watch_owner` | No | Owns application schema objects, tables, functions, triggers, and protected indexes | Object ownership; never used as an application connection |
| `watch_migrator` | Yes | Runs reviewed Alembic migrations and SET ROLE to owner | Migration-only; never used by app or workers |
| `watch_app` (proposed; current `watch_runtime` is SELECT-only) | Yes | Core application composition: Control Room, TaskRuntime, OperatorApplication, ingestion, Plan/Objective/Evaluation, WorldMemory, learning and assessment workflows | Exact union of the approved core application DML matrix; no schema/role administration |
| `watch_indexer` (conditional, future) | Yes | SignalIndexer and TeamExperienceIndexer only, when deployed as a separate process | Projection writes only: `knowledge_chunks`, `team_experience_chunks`, and `team_experience_index_state`; read access only to required source tables |
| Maintenance/repair operator | Not provisioned by this application bootstrap | Human-approved, audited break-glass repair, backup/restore, or controlled data maintenance | External DBA/operations policy; no standing application membership and no shared app DSN |

### 4.1 Core application identity

The core application identity is deliberately shared across domain services that currently share transaction ownership. It covers the actual workflows in the DML audit, not a fictional per-module role split.

The eventual grant manifest must be generated from the DML writer audit and actual emitted SQL. It must not include:
- UPDATE on lock-only tables merely to make `FOR UPDATE` / `FOR SHARE` work;
- Team, TeamPolicy, or Thread lifecycle writes before their owners are implemented and accepted;
- Event UPDATE/DELETE;
- Signal identity UPDATE/DELETE;
- assessment UPDATE/DELETE;
- SignalDisposition INSERT before the accepted D2 composite FK and Decision 7 gates;
- schema DDL, role membership, trigger-disable, replication bypass, or TRUNCATE authority.

Lock-only reads must use the reviewed fixed lock-helper design where no real UPDATE allow-list exists. Helpers retain the caller's transaction and do not create a new transaction.

### 4.2 Conditional indexer identity

The indexer role is justified only if deployment proves all of the following:

1. SignalIndexer and TeamExperienceIndexer execute in a separately supervised process (or an independently managed worker with its own pool).
2. The worker receives a distinct secret/DSN and cannot fall back to the core application DSN.
3. Each indexer operation owns a complete transaction on that worker connection; no caller-owned application Session crosses the boundary.
4. The worker has SELECT on the exact source relations required by the indexers.
5. Its DML is limited to the two projection tables' INSERT/DELETE paths and the index-state INSERT/UPDATE path.
6. DELETE is constrained to the fixed projection parent-key predicate; no arbitrary table DELETE, cascade, TRUNCATE, DDL, or role switching is granted.
7. PostgreSQL tests execute real indexing success, replacement, ineligibility, rollback, and failure paths under `watch_indexer`, while proving those writes fail under `watch_app`.

If these conditions are not met, keep indexing under `watch_app` for the initial deployment and document the union privilege trade-off. Do not create a nominal `watch_indexer` login that the host does not actually use.

### 4.3 Identities explicitly not split

Do not create separate logins for:
- Control Room: it receives a caller-owned Session and is not a transaction owner.
- TaskRuntime vs OperatorApplication: orchestration and TaskRuntime participate in the same end-to-end application workflows; no independent host/connection boundary is present.
- IngestionService, WorldMemoryCommitService, EvaluationService, or LearningCommitService solely because they are separate Python classes. Their transactions are nested/composed according to the source contract.
- Thread lifecycle: no accepted production lifecycle writer exists yet.
- Team/TeamPolicy administration: no production writer or deployment owner exists yet.

If a future architecture introduces independently deployed services with explicit transaction and connection boundaries, revisit the identity split as a separate design change.

## 5. Credential and connection rules

1. Each LOGIN role has a distinct secret. No shared password between bootstrap, migrator, core app, and indexer.
2. The application host receives only the core app DSN. An isolated indexer receives only its own DSN if §4.2 is satisfied.
3. Alembic receives only the migrator DSN. The migration process must verify `session_user = 'watch_migrator'` and `current_user = 'watch_owner'` after SET ROLE.
4. The bootstrap administrator credential is supplied only to the provisioning/deployment operation and must not be present in application or worker environments after provisioning.
5. No process may silently fall back from its assigned DSN to a bootstrap, migrator, owner, or test DSN.
6. Tests and smoke tools continue to use explicit `TEST_DATABASE_URL` against disposable databases. They do not inherit production runtime credentials.
7. Each engine/pool must have a documented owner and lifecycle. A connection is not switched between identities within an open transaction.
8. Deployment health checks should report `session_user` and `current_user` (without credentials) and fail closed when a process is running under an unexpected identity.
9. Runtime credentials must not be members of owner/migrator roles and must not have SUPERUSER, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS, schema CREATE, trigger-disable, or replication-role bypass capabilities.
10. Maintenance access is explicit, time-bounded, separately audited, and never obtained by granting the application login owner membership.

## 6. Consequences for the F1 grant matrix

The DML audit should be interpreted in two stages:

- **Current source model:** one core application identity owns the union of core service DML. The indexer writes remain part of that identity unless a separate deployment boundary is demonstrated.
- **Target isolated model:** move only the projection writer rows to `watch_indexer` after the host split and workflow tests exist. Do not split transaction-sharing domain services.

The DML audit's column inventory is a candidate grant source, not a ready-to-apply SQL manifest. Before grants are frozen:
- capture SQL emitted by representative ORM INSERT/UPDATE paths to verify exact INSERT columns and server/Python defaults;
- prove every flush and compare-and-set path works with column-level UPDATE privileges;
- decide whether projection DELETE uses fixed owner-controlled functions or direct DELETE under the isolated indexer login;
- inventory external deployment/maintenance writers with the Operator;
- test actual logins, effective inherited/PUBLIC privileges, and all positive/negative workflows.

The current `watch_runtime` name may either be retained and explicitly designated as the core app login, or replaced by `watch_app` in a separately reviewed provisioning change. Do not rename or provision roles as part of this design-only step.

## 7. Deployment topology acceptance checklist

Before approving any grant implementation, the deployment owner must confirm:

- [ ] Is the first deployable Watch host a single process, or are there separately supervised API/Operator, task worker, and indexing worker processes?
- [ ] Which process constructs each `session_factory` and engine?
- [ ] Can any workflow pass a Session/connection into another component or retain it across a worker boundary?
- [ ] Are SignalIndexer and TeamExperienceIndexer invoked in-process, by a scheduler, or by a separate worker? Provide the actual entrypoint and invocation path.
- [ ] Which external tools perform configuration, imports, repairs, backup/restore, and operational data changes?
- [ ] Can old processes/connections be drained before a credential cutover?
- [ ] Where are each process's DSN secrets stored, rotated, and injected?
- [ ] What operational identity is permitted for break-glass repair, and what audit/approval is required?
- [ ] Does the first deployment accept the union privilege of a single core application login, or is a separate indexer process a required initial boundary?

No database grant can be considered complete while these answers are unknown.

## 8. Sequenced actions after Operator disposition

| Step | Action | Acceptance evidence |
|---|---|---|
| 1 | Accept/revise the core-app + conditional-indexer identity model | Explicit decision on initial shared core identity and whether indexer is separate at first deployment |
| 2 | Inspect/define the actual host and worker composition | Entry points, process boundaries, engine/session ownership, DSN consumers |
| 3 | Map each source workflow to a process identity | Every DML writer and lock callsite assigned to a real login; no unassigned/external writer |
| 4 | Finalize per-login privilege manifests | Exact table/column INSERT/UPDATE, DELETE mechanism, SELECT and lock-helper EXECUTE |
| 5 | Capture emitted SQL and prove ORM flush compatibility | PostgreSQL integration tests under each exact login |
| 6 | Implement roles/grants/helpers in a separately authorized change | Migration/bootstrap diff, no broad lock-only UPDATE grants |
| 7 | Prove effective privilege boundaries and service workflows | Positive/negative workflow tests under actual logins; concurrency/lock-lifetime proofs |
| 8 | Execute controlled credential cutover | Drain old sessions, migrate with migrator, start each process with its assigned DSN, inspect active sessions |
| 9 | Close F1 only after complete proof | Independent review, exact-head CI, deployment verification and no unknown writer |

## 9. Current disposition and boundaries

**Recommendation:** accept Option C as the target direction, with Option A as the only honest initial topology until an independently connected indexer process is evidenced. Do not split services by Python class. Do not create a role that no host consumes.

This document is a proposal only. It does not change `scripts/provision_database_roles.py`, `migrations/env.py`, `core/database_config.py`, application runtime, ORM mappings, grants, triggers, migrations, or database state. It does not close F1/F2/F3/F4, accept the RW4-1 physical DDL, enable SignalDisposition writes, or authorize RW4-1 implementation.
