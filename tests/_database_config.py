"""Fail-closed configuration for PostgreSQL-backed tests."""

from collections.abc import Mapping

from sqlalchemy.engine import make_url


def resolve_test_database_url(environ: Mapping[str, str]) -> str:
    """Return an explicit, non-persistent PostgreSQL test database URL.

    Tests deliberately do not fall back to DATABASE_URL: that variable may
    point to the developer's persistent application database.
    """
    database_url = environ.get("TEST_DATABASE_URL")
    if database_url is None or not database_url.strip():
        raise ValueError(
            "TEST_DATABASE_URL is required for database-backed tests. "
            "Set it to a disposable PostgreSQL database; tests will not fall "
            "back to DATABASE_URL or the persistent 'watch' database."
        )

    try:
        parsed_url = make_url(database_url)
    except Exception as exc:
        raise ValueError("TEST_DATABASE_URL is not a valid SQLAlchemy URL.") from exc

    if parsed_url.get_backend_name() != "postgresql":
        raise ValueError("TEST_DATABASE_URL must use PostgreSQL.")

    if not parsed_url.database:
        raise ValueError("TEST_DATABASE_URL must name a disposable database.")

    if parsed_url.database.casefold() == "watch":
        raise ValueError(
            "TEST_DATABASE_URL targets the persistent database named 'watch'. "
            "Use a separately created disposable database instead."
        )

    return database_url
