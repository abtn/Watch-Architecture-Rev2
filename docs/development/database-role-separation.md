# Watch PostgreSQL role separation

**Status:** Implemented as a fresh-database bootstrap and CI proof. This does not yet switch a running Watch host process to the runtime credential; the repository still has no production host composition/runtime DSN consumer.

## Roles

| Role | Login | Purpose | Effective access |
|---|---:|---|---|
| `watch_owner` | No | Owns the database, public schema, and migrated objects | Object owner; cannot authenticate |
| `watch_migrator` | Yes | Dedicated Alembic connection | `NOINHERIT`; may explicitly `SET ROLE watch_owner` |
| `watch_runtime` | Yes | Intended application runtime identity | Schema usage and SELECT on owner-created tables/sequences only; no DML, DDL, TEMP, owner membership, or migrator membership |
| Bootstrap administrator | Yes | Provisioning and disposable test administration | Superuser in local/CI bootstrap; never the application runtime identity |

PostgreSQL roles are cluster-global, not database-local. This bootstrap uses fixed role names and therefore provisions **one Watch database per PostgreSQL cluster**. It refuses to run if any of the three Watch roles already exists; it does not alter, reset, or reuse pre-existing cluster roles. A second Watch database requires a separately designed role-naming/provisioning plan.

The bootstrap administrator and CI test connection are deliberately not the runtime role. Tests need to create/drop isolated schemas and fixtures, so they use the disposable test database's administrative credential. Do not copy that credential into a Watch runtime process. The bootstrap administrator also installs pgvector before migrations: the extension is not marked trusted by PostgreSQL, so it cannot be installed by the non-superuser migration owner. Migration 0001 therefore treats pgvector as a persistent database prerequisite and does not drop it on downgrade.

## Provision a fresh development database

The bootstrap is intentionally narrow. It refuses the persistent database named `watch`, requires a PostgreSQL superuser connection, refuses pre-existing Watch role names anywhere in the cluster, and refuses a database with non-system schemas or objects in `public`. Role creation, database ownership, extension setup, and grants run in one transaction; a failure rolls the entire bootstrap back. It is not a migration or ownership-transfer utility and must not be run against an existing database with data.

With the local Compose PostgreSQL service running, create a separate empty database:

```sh
createdb -h 127.0.0.1 -p 5432 -U watch watch_roles_dev
```

Set credentials in the shell without committing them:

```sh
export DATABASE_ADMIN_URL='postgresql+psycopg://watch:<bootstrap-password>@127.0.0.1:5432/watch_roles_dev'
export WATCH_MIGRATOR_PASSWORD='<unique-migrator-password>'
export WATCH_RUNTIME_PASSWORD='<unique-runtime-password>'
uv run python scripts/provision_database_roles.py
```

Then run Alembic using the migration login:

```sh
export DATABASE_URL='postgresql+psycopg://watch_migrator:<unique-migrator-password>@127.0.0.1:5432/watch_roles_dev'
uv run alembic upgrade head
```

Direct Alembic CLI runs require `DATABASE_URL` to authenticate as `watch_migrator`; the migration environment then executes `SET ROLE watch_owner` and verifies the effective `current_user` before running DDL. It fails closed for a direct CLI connection using the bootstrap administrator, runtime role, or another login. Programmatic migration tests that explicitly supply a connection retain responsibility for that connection's identity and privileges and continue to use their isolated administrative test connection.

The bootstrap preinstalls pgvector with the administrative connection. A read-only runtime connection can then use:

```sh
postgresql+psycopg://watch_runtime:<unique-runtime-password>@127.0.0.1:5432/watch_roles_dev
```

No production host currently consumes this URL. Do not infer that application runtime cutover is complete from successful role provisioning.

## Verification and limitations

CI provisions the roles against a fresh disposable PostgreSQL database, runs the complete Alembic chain as `watch_migrator`/`watch_owner`, and runs `tests/test_database_roles.py` using the separate administrative test URL. The test checks role attributes, membership/inheritance, database/schema privileges, and effective table/sequence privileges.

The runtime role is deliberately read-only at this stage. Do not grant broad INSERT/UPDATE/DELETE privileges to make application tests pass. Each future supported writer must receive a separately reviewed, narrow grant only after its owning application path, transaction, and physical guard are implemented and tested. In particular, do not treat a role with SELECT-only access as a working application runtime.

The bootstrap is a one-time operation for a fresh database on a fresh PostgreSQL cluster. It does not repair existing role memberships, transfer existing object ownership, or reconcile existing credentials. Existing databases require a separately reviewed DBA migration plan; do not drop a local data volume merely to make this script run.
