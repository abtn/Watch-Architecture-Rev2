import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

database_url = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://watch:watch@localhost:5432/watch",
)
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection, version_table_schema: str | None = None) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=version_table_schema,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Programmatic callers can supply a connection and version-table schema
    # when they need precise transaction or schema isolation.
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        _run_migrations(
            supplied_connection,
            version_table_schema=config.attributes.get("version_table_schema"),
        )
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
