import os

from _database_config import resolve_test_database_url
from sqlalchemy import create_engine, text


def test_postgresql_has_vector_extension() -> None:
    database_url = resolve_test_database_url(os.environ)
    engine = create_engine(database_url)

    try:
        with engine.connect() as connection:
            extension_version = connection.scalar(
                text(
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
                )
            )

        assert extension_version is not None
    finally:
        engine.dispose()
