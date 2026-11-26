"""PostgreSQL proof for the provisioned Watch database roles."""

from __future__ import annotations

import os

import pytest
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

            assert connection.scalar(
                text("SELECT pg_get_userbyid(datdba) = 'watch_owner' "
                     "FROM pg_database WHERE datname = current_database()")
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
                    text("SELECT has_table_privilege('watch_runtime', :table, 'SELECT')"),
                    {"table": qualified},
                ), f"runtime role cannot read {qualified}"
                for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"):
                    assert connection.scalar(
                        text(
                            "SELECT has_table_privilege('watch_runtime', :table, :privilege)"
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
                        "SELECT has_sequence_privilege('watch_runtime', :sequence, 'SELECT')"
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
        ):
            with runtime_engine.connect() as connection:
                with pytest.raises(DBAPIError):
                    connection.execute(text(statement))
    finally:
        runtime_engine.dispose()
