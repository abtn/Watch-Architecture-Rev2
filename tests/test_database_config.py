"""Regression tests for fail-closed database test configuration."""

import pytest

from _database_config import resolve_test_database_url


def test_database_url_requires_explicit_test_database_even_when_app_url_exists() -> None:
    with pytest.raises(ValueError, match="TEST_DATABASE_URL is required"):
        resolve_test_database_url(
            {"DATABASE_URL": "postgresql+psycopg://watch:secret@127.0.0.1:5432/watch"}
        )


def test_database_url_rejects_persistent_watch_database() -> None:
    with pytest.raises(ValueError, match="persistent database named 'watch'"):
        resolve_test_database_url(
            {
                "TEST_DATABASE_URL": (
                    "postgresql+psycopg://watch:secret@127.0.0.1:5432/watch"
                )
            }
        )


def test_database_url_rejects_non_postgresql_backend() -> None:
    with pytest.raises(ValueError, match="must use PostgreSQL"):
        resolve_test_database_url({"TEST_DATABASE_URL": "sqlite:///tmp/watch_test.db"})


def test_database_url_accepts_named_disposable_postgresql_database() -> None:
    database_url = (
        "postgresql+psycopg://watch:secret@127.0.0.1:55463/watch_c4_local"
    )

    assert resolve_test_database_url({"TEST_DATABASE_URL": database_url}) == database_url
