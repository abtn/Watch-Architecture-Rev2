"""PostgreSQL proof for the provisioned Watch database roles."""

from __future__ import annotations

import os
import subprocess
import sys
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from core.database_config import resolve_test_database_url


def test_database_roles_have_separated_effective_privileges() -> None:
    try:
        database_url = resolve_test_database_url(os.environ)
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            roles = connection.execute(
                text(
                    """
                    SELECT rolname, rolsuper, rolinherit, rolcreaterole,
                           rolcreatedb, rolreplication, rolbypassrls, rolcanlogin
                    FROM pg_roles
                    WHERE rolname IN (
                        'watch_owner', 'watch_migrator', 'watch_runtime'
                    )
                    """
                )
            ).mappings().all()
            by_name = {row["rolname"]: row for row in roles}
            if set(by_name) != {"watch_owner", "watch_migrator", "watch_runtime"}:
                pytest.skip("Watch database roles have not been provisioned")

            owner = by_name["watch_owner"]
            migrator = by_name["watch_migrator"]
            runtime = by_name["watch_runtime"]

            assert owner["rolcanlogin"] is False
            assert migrator["rolcanlogin"] is True
            assert migrator["rolinherit"] is False
            assert runtime["rolcanlogin"] is True
            for role in (owner, migrator, runtime):
                assert role["rolsuper"] is False
                assert role["rolcreaterole"] is False
                assert role["rolcreatedb"] is False
                assert role["rolreplication"] is False
                assert role["rolbypassrls"] is False

            assert connection.scalar(
                text("SELECT pg_has_role('watch_migrator', 'watch_owner', 'MEMBER')")
            )
            assert connection.scalar(
                text("SELECT pg_has_role('watch_migrator', 'watch_owner', 'USAGE')")
            ) is False
            assert connection.scalar(
                text("SELECT pg_has_role('watch_runtime', 'watch_owner', 'MEMBER')")
            ) is False
            assert connection.scalar(
                text("SELECT pg_has_role('watch_runtime', 'watch_migrator', 'MEMBER')")
            ) is False
            memberships = connection.execute(
                text(
                    """
                    SELECT granted.rolname, member.rolname,
                           membership.admin_option, membership.inherit_option,
                           membership.set_option
                    FROM pg_auth_members AS membership
                    JOIN pg_roles AS granted ON granted.oid = membership.roleid
                    JOIN pg_roles AS member ON member.oid = membership.member
                    WHERE granted.rolname IN (
                        'watch_owner', 'watch_migrator', 'watch_runtime'
                    )
                       OR member.rolname IN (
                        'watch_owner', 'watch_migrator', 'watch_runtime'
                    )
                    """
                )
            ).all()
            assert memberships == [
                ("watch_owner", "watch_migrator", False, False, True)
            ]

            assert connection.scalar(
                text("SELECT pg_get_userbyid(datdba) = 'watch_owner' "
                     "FROM pg_database WHERE datname = current_database()")
            )
            assert connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_extension "
                    "WHERE extname = 'vector')"
                )
            )
            assert connection.scalar(
                text(
                    "SELECT pg_get_userbyid(extowner) <> 'watch_owner' "
                    "FROM pg_extension WHERE extname = 'vector'"
                )
            )
            assert connection.scalar(
                text("SELECT has_schema_privilege('watch_runtime', 'public', 'USAGE')")
            )
            assert connection.scalar(
                text("SELECT has_schema_privilege('watch_runtime', 'public', 'CREATE')")
            ) is False
            assert connection.scalar(
                text("SELECT has_database_privilege('watch_runtime', "
                     "current_database(), 'CREATE')")
            ) is False
            assert connection.scalar(
                text("SELECT has_database_privilege('watch_runtime', "
                     "current_database(), 'TEMP')")
            ) is False

            tables = connection.scalars(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' ORDER BY tablename"
                )
            ).all()
            assert tables, "migrations should have created application tables"
            for table in tables:
                qualified = f"public.{table}"
                assert connection.scalar(
                    text(
                        "SELECT has_table_privilege("
                        "'watch_runtime', :table, 'SELECT')"
                    ),
                    {"table": qualified},
                ), f"runtime role cannot read {qualified}"
                for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"):
                    assert connection.scalar(
                        text(
                            "SELECT has_table_privilege("
                            "'watch_runtime', :table, :privilege)"
                        ),
                        {"table": qualified, "privilege": privilege},
                    ) is False, f"runtime unexpectedly has {privilege} on {qualified}"

            sequences = connection.scalars(
                text(
                    "SELECT sequence_name FROM information_schema.sequences "
                    "WHERE sequence_schema = 'public'"
                )
            ).all()
            for sequence in sequences:
                qualified = f"public.{sequence}"
                assert connection.scalar(
                    text(
                        "SELECT has_sequence_privilege("
                        "'watch_runtime', :sequence, 'SELECT')"
                    ),
                    {"sequence": qualified},
                )
                for privilege in ("USAGE", "UPDATE"):
                    assert connection.scalar(
                        text(
                            "SELECT has_sequence_privilege("
                            "'watch_runtime', :sequence, :privilege)"
                        ),
                        {"sequence": qualified, "privilege": privilege},
                    ) is False
    finally:
        engine.dispose()

    runtime_password = os.environ.get("WATCH_RUNTIME_PASSWORD")
    if not runtime_password:
        pytest.skip("WATCH_RUNTIME_PASSWORD is not configured for login verification")

    admin_url = os.environ.get("DATABASE_ADMIN_URL")
    if admin_url:
        parsed_admin_url = make_url(admin_url)
        probe_database = f"watch_role_probe_{uuid4().hex[:12]}"
        admin_psycopg_url = parsed_admin_url.set(drivername="postgresql").render_as_string(
            hide_password=False
        )
        with psycopg.connect(admin_psycopg_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(probe_database))
            )
        try:
            probe_env = os.environ.copy()
            probe_env["DATABASE_ADMIN_URL"] = parsed_admin_url.set(
                database=probe_database
            ).render_as_string(hide_password=False)
            probe_env["WATCH_MIGRATOR_PASSWORD"] = "must-not-replace-existing-password"
            probe_env["WATCH_RUNTIME_PASSWORD"] = "must-not-replace-existing-password"
            result = subprocess.run(
                [sys.executable, "scripts/provision_database_roles.py"],
                env=probe_env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 1
            assert "pre-existing cluster-global Watch roles" in result.stderr
        finally:
            with psycopg.connect(admin_psycopg_url, autocommit=True) as connection:
                connection.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                        sql.Identifier(probe_database)
                    )
                )

    runtime_url = make_url(database_url).set(
        username="watch_runtime", password=runtime_password
    )
    runtime_engine = create_engine(runtime_url)
    try:
        with runtime_engine.connect() as connection:
            assert connection.scalar(text("SELECT current_user")) == "watch_runtime"
            connection.execute(text("SELECT count(*) FROM teams")).scalar_one()

        for statement in (
            "UPDATE teams SET status = status WHERE false",
            "DELETE FROM teams WHERE false",
            "TRUNCATE TABLE teams",
            "CREATE TABLE public.watch_runtime_forbidden (id integer)",
            "ALTER TABLE teams DISABLE TRIGGER ALL",
            "SET ROLE watch_owner",
            "SET session_replication_role = replica",
        ):
            with runtime_engine.connect() as connection:
                with pytest.raises(DBAPIError):
                    connection.execute(text(statement))
    finally:
        runtime_engine.dispose()


def test_alembic_cli_rejects_non_migrator_login() -> None:
    try:
        database_url = resolve_test_database_url(os.environ)
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc

    with create_engine(database_url).connect() as connection:
        roles = connection.scalar(
            text(
                "SELECT count(*) FROM pg_roles "
                "WHERE rolname IN ('watch_owner', 'watch_migrator', 'watch_runtime')"
            )
        )
    if roles != 3:
        pytest.skip("Watch database roles have not been provisioned")

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "requires DATABASE_URL to authenticate as watch_migrator" in result.stderr
