# RW4-1 F1 — deployment host and process-composition audit

**Status:** Source audit complete; no production host exists in the current repository. The Operator has accepted the identity-model decision: one shared core application login for the first deployable application, with indexer separation deferred unless a genuine independent worker boundary is introduced. This document records what the source can and cannot prove. It does not create that host or authorize grants.

**Audited source baseline:** PR #222 branch at the time of this audit, based on main `c648892e4896113700c8103397be01c11c0d22ed`. The identity decision is recorded in `rw4-1b-f1-deployment-identity-model-proposal.md`.

## 1. Executive finding

There is no production Watch process topology to map database identities onto today.

The repository contains:
- a Python domain/application-core package under `core/`;
- PostgreSQL/Alembic schema and migration tooling;
- test fixtures that construct SQLAlchemy engines and Session factories;
- developer-only smoke utilities;
- a Docker Compose PostgreSQL service.

It does not contain a production API/CLI host, web server, worker supervisor, scheduler, queue consumer, application composition root, runtime DSN consumer, or deployment manifest for a Watch application process.

Therefore the accepted identity model is a **future deployment contract**, not an immediately implementable credential wiring task. The first application host, when separately designed and authorized, should use one core application login for all transaction-sharing domain workflows. The current `watch_runtime` login remains SELECT-only and must not be silently promoted before the host and grant manifest exist.

## 2. Evidence inventory

### 2.1 Package and dependency manifest

Current `pyproject.toml` declares runtime dependencies:
- SQLAlchemy 2.x
- Alembic
- psycopg 3
- Pydantic 2.x

It has no declared FastAPI/Starlette, Uvicorn, Redis client, arq/Celery/Dramatiq worker runtime, or application server dependency. There is no `[project.scripts]` entrypoint.

This is consistent with the codebase being an application/domain core rather than a deployable service. It does not prove that no external deployment wrapper could exist outside this repository; that external system must be disclosed by the deployment owner before grants are finalized.

### 2.2 Compose and environment

`compose.yaml` defines only one service: PostgreSQL using `pgvector/pgvector:pg16`. It sets the local bootstrap database/user/password, publishes the PostgreSQL port, and persists a development volume.

It does not define a Watch API, application, worker, scheduler, Redis service, or indexing process. Its `watch` credential is a local PostgreSQL bootstrap credential, not an application runtime identity.

### 2.3 Executable Python entrypoints

Repository search for `if __name__ == "__main__"` found:
- `core/embedding_smoke.py`
- `core/generation_smoke.py`
- `scripts/provision_database_roles.py`

These are developer smoke/provisioning utilities. Neither smoke utility is a production application host. The disposable embedding smoke path creates its own engine/session factory from an explicit database URL and is restricted to a disposable database.

No application `main`, API factory, ASGI/WSGI app, CLI command group, worker boot function, or scheduler entrypoint was found.

### 2.4 SQLAlchemy engine and Session ownership

The production `core/` modules are constructed with caller-supplied Sessions, session factories, or service dependencies. They do not provide a single repository-owned production engine/session-factory composition root.

The tests create engines and Session factories in fixtures and pass them into services. This proves test composition and transaction contracts, not production deployment composition.

No source evidence establishes:
- which process constructs a production engine;
- how many production pools exist;
- whether application and indexing operations share a process or database pool in deployment;
- how production DSNs are injected or rotated;
- how processes are supervised, drained, or restarted.

### 2.5 TaskDispatcher and indexing

`TaskDispatcher` is a callable application component used by tests and composed with a fetcher/snapshot store. The repository has no production queue consumer or worker loop invoking it.

Search for `SignalIndexer` and `TeamExperienceIndexer` found construction in tests and the disposable embedding smoke utility; no production host invocation was found. The indexer classes' write behavior is real source behavior, but a separate deployed indexing worker is not.

Consequently:
- do not create `watch_indexer` yet;
- do not assign indexer DML to a hypothetical worker identity;
- for the first deployable host, the accepted default is one core application login for all application workflows that run under that host;
- revisit indexer isolation only when a separate process, pool, and DSN are implemented and tested.

### 2.6 Architecture documentation reconciliation

`docs/architecture.md` describes the intended conceptual system and explicitly states that no separate deployed Watch API/CLI or Watch-owned authentication system is implied. It also describes the host as the authentication root.

Historical architecture records mentioning FastAPI, Redis, arq, or a scheduler describe intended/earlier target architecture, not current implemented dependencies or deployment evidence. The current `pyproject.toml`, `compose.yaml`, executable entrypoints, and source searches are the authority for this implementation audit.

## 3. Process-to-identity map supported by current evidence

| Source component/workflow | Current repository execution evidence | Current deployment identity |
|---|---|---|
| Control Room | Session-bound core component; invoked through caller-owned transaction paths and tests | None; future core application identity |
| PlanService / ingestion | Domain services; composed by tests and caller-owned Sessions | None; future core application identity |
| TaskRuntime | Domain service with owned lifecycle transactions; tests construct it directly | None; future core application identity |
| OperatorApplication | In-process adapter/orchestrator; no deployed host authentication caller | None; future core application identity |
| WorldMemory / Learning / Evaluation | Core services, sometimes caller-Session composed; no production process root | None; future core application identity |
| TaskDispatcher | Application component exercised by tests; no production queue consumer | None; future core application identity |
| SignalIndexer | Tests and disposable smoke utility only | None; future core application identity unless a separately deployed indexer is later accepted |
| TeamExperienceIndexer | Tests only; no production worker invocation | None; future core application identity unless a separately deployed indexer is later accepted |
| Alembic | Dedicated migration CLI path verifies migrator login and SET ROLE owner | `watch_migrator` |
| Role provisioning | Explicit bootstrap/admin provisioning utility | Bootstrap administrator, provisioning-time only |
| Tests | Explicit `TEST_DATABASE_URL`, disposable PostgreSQL fixture | Test/bootstrap identity; never production runtime |
| Embedding/generation smoke utilities | Explicit developer-only invocation and separate safety boundaries | Disposable test/developer database identity only |

The phrase “future core application identity” is intentional. No application login is currently consumed by a production process.

## 4. Accepted identity decision

The Operator accepted the following design:

1. One shared core application login is the initial identity for the first deployable Watch application.
2. Do not create logins per Python class/module; transaction-sharing components are not independent security boundaries.
3. Do not create `watch_indexer` for the current source-only indexer classes. Indexer separation is deferred until an actual independent process, engine/pool, DSN, and complete transaction boundary exist.
4. `watch_owner` remains NOLOGIN object owner.
5. `watch_migrator` remains migration-only.
6. Bootstrap and maintenance credentials remain outside application processes.
7. Existing `watch_runtime` remains SELECT-only for now. Whether to retain its name as the future core login or introduce `watch_app` is a later role-provisioning decision; neither is implemented by this acceptance.

This decision accepts the **identity architecture**, not the exact DML grants, the host architecture, a credential cutover, or RW4-1 physical DDL.

## 5. What must be designed before an application identity can be consumed

A future host proposal must define:

- the initial application invocation surface (API, CLI, embedded host, or other);
- the trusted host authentication boundary and how it invokes `OperatorApplication`;
- the application composition root and ownership of engine/sessionmaker;
- whether TaskDispatcher is synchronous, queue-backed, or externally invoked;
- whether any background worker or scheduler is actually required for the first vertical slice;
- snapshot storage configuration and lifecycle;
- source fetcher and embedding provider construction/configuration;
- shutdown, connection-pool disposal, graceful drain, health checks, and credential rotation;
- secret injection and separation of bootstrap, migrator, core app, and test credentials;
- external operator, repair, import, backup, restore, and data-maintenance writers.

Do not add Redis, FastAPI, arq, a scheduler, or a separate worker merely because historical target architecture mentions them. Choose only the minimum host components required by an accepted first deployable workflow.

## 6. Next implementation sequence

| Step | Action | Scope | Acceptance evidence |
|---|---|---|---|
| 1 | Record accepted identity decision and source audit | Documentation only | Operator acceptance recorded; this audit merged after review |
| 2 | Define first host's actual use case and invocation surface | Design only | One concrete host entrypoint and trusted caller contract |
| 3 | Design minimal composition root | Design only | Engine/sessionmaker ownership, service wiring, shutdown and configuration contract |
| 4 | Decide TaskDispatcher execution model | Design only | Explicit synchronous or worker/queue boundary; no speculative infrastructure |
| 5 | Decide indexer lifecycle | Design only | Either in-process under core identity or independently deployed with a separate DSN; no hypothetical role |
| 6 | Inventory external/maintenance writers | Operator + deployment evidence | Named systems/processes, credential owners, operations and approval boundary |
| 7 | Reconcile DML and lock ledgers to accepted host topology | Design only | Every workflow mapped to core app or a proven separate identity |
| 8 | Produce exact privilege manifest and emitted-SQL proof plan | Design only | Per-login table/column grants and lock-helper map, including negative tests |
| 9 | Request separate implementation authorization | Explicit gate | Authorization for host/role/grant changes; no implicit authorization from this identity decision |

## 7. Boundaries

This audit makes no code, runtime, ORM, migration, role, grant, trigger, or database change. It does not build the host, add API/CLI authentication, introduce a worker/queue, provision `watch_app` or `watch_indexer`, or promote `watch_runtime`.

F1 remains open until the host identity is real, the complete external writer inventory is known, exact privileges/helpers are implemented under separate authorization, and PostgreSQL positive/negative workflow and lock-lifetime tests pass under the deployed login(s).

The accepted identity model does not accept RW4-1 physical DDL, enable SignalDisposition writes, close F2/F3/F4, or authorize R8-ready transition.
