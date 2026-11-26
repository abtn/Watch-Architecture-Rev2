"""Provision least-privilege PostgreSQL roles for a fresh Watch database.

Run only against a fresh, disposable database before applying Alembic migrations.
The bootstrap connection must be a PostgreSQL superuser. This script deliberately
refuses the persistent database named watch and refuses databases that already
contain application tables; it is not an ownership-transfer tool.
"""

from __future__ import annotations

import os
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


def main() -> int:
    admin_url = os.environ.get("DATABASE_ADMIN_URL", "").strip()
    migrator_password = os.environ.get("WATCH_MIGRATOR_PASSWORD", "")
    runtime_password = os.environ.get("WATCH_RUNTIME_PASSWORD", "")
    if not admin_url:
        print("DATABASE_ADMIN_URL is required", file=sys.stderr)
        return 2
    if not migrator_password or not runtime_password:
        print(
            "WATCH_MIGRATOR_PASSWORD and WATCH_RUNTIME_PASSWORD are required",
            file=sys.stderr,
        )
        return 2

    try:
        parsed = make_url(admin_url)
    except Exception as exc:
        print(f"Invalid DATABASE_ADMIN_URL: {exc}", file=sys.stderr)
        return 2
    if parsed.get_backend_name() != "postgresql" or not parsed.database:
        print("DATABASE_ADMIN_URL must target a named PostgreSQL database", file=sys.stderr)
        return 2
    if parsed.database.casefold() == "watch":
        print(
            "Refusing role provisioning against the persistent database named 'watch'",
            file=sys.stderr,
        )
        return 2

    try:
        psycopg_url = parsed.set(drivername="postgresql").render_as_string(
            hide_password=False
        )
        with psycopg.connect(psycopg_url, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
                row = cursor.fetchone()
                if row is None or not row[0]:
                    raise RuntimeError("DATABASE_ADMIN_URL must connect as a superuser")

                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_class AS relation
                        JOIN pg_namespace AS namespace
                          ON namespace.oid = relation.relnamespace
                        WHERE namespace.nspname = 'public'
                          AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
                    )
                    """
                )
                if cursor.fetchone()[0]:
                    raise RuntimeError(
                        "Refusing a database that already contains public-schema "
                        "objects; this bootstrap is for a fresh database only"
                    )

                cursor.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'watch_owner') THEN
                            CREATE ROLE watch_owner NOLOGIN NOSUPERUSER NOCREATEDB
                                NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'watch_migrator') THEN
                            CREATE ROLE watch_migrator NOLOGIN NOSUPERUSER NOCREATEDB
                                NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'watch_runtime') THEN
                            CREATE ROLE watch_runtime NOLOGIN NOSUPERUSER NOCREATEDB
                                NOCREATEROLE NOREPLICATION NOBYPASSRLS;
                        END IF;
                    END
                    $$
                    """
                )
                cursor.execute(
                    "ALTER ROLE watch_owner WITH NOLOGIN NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                )
                cursor.execute(
                    sql.SQL(
                        "ALTER ROLE watch_migrator WITH LOGIN NOINHERIT NOSUPERUSER "
                        "NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
                    ).format(sql.Literal(migrator_password))
                )
                cursor.execute(
                    sql.SQL(
                        "ALTER ROLE watch_runtime WITH LOGIN NOINHERIT NOSUPERUSER "
                        "NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
                    ).format(sql.Literal(runtime_password))
                )
                cursor.execute(
                    sql.SQL("ALTER DATABASE {} OWNER TO watch_owner").format(
                        sql.Identifier(parsed.database)
                    )
                )
                # pgvector is not a trusted extension; install it with the bootstrap
                # administrator before migrations run under the non-superuser owner.
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute("ALTER SCHEMA public OWNER TO watch_owner")
                cursor.execute(
                    sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                        sql.Identifier(parsed.database)
                    )
                )
                cursor.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
                cursor.execute("GRANT USAGE ON SCHEMA public TO watch_migrator, watch_runtime")
                cursor.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO watch_migrator, watch_runtime").format(
                        sql.Identifier(parsed.database)
                    )
                )
                cursor.execute(
                    "GRANT watch_owner TO watch_migrator WITH INHERIT FALSE, SET TRUE"
                )
                cursor.execute(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE watch_owner IN SCHEMA public "
                    "GRANT SELECT ON TABLES TO watch_runtime"
                )
                cursor.execute(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE watch_owner IN SCHEMA public "
                    "GRANT SELECT ON SEQUENCES TO watch_runtime"
                )
    except Exception as exc:
        print(f"Database role provisioning failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Provisioned watch_owner, watch_migrator, and read-only watch_runtime "
        f"for fresh database {parsed.database!r}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
