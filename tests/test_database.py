import os

from sqlalchemy import create_engine, text


def test_postgresql_has_vector_extension() -> None:
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://watch:watch@127.0.0.1:5432/watch",
    )
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
