"""Build an isolated pre-0015 database for R7-B migration tests."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from _database_config import resolve_test_database_url


@dataclass(frozen=True)
class MigrationSandbox:
    """A PostgreSQL schema whose search path is isolated for Alembic."""

    engine: Engine
    schema: str


@pytest.fixture
def pre_0015_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[MigrationSandbox]:
    """Upgrade an empty isolated schema to the legacy 0014 database shape.

    The URL is resolved from TEST_DATABASE_URL only. Alembic receives that same
    disposable database URL, while PGOPTIONS directs every migration
    connection into a unique schema ahead of public. The schema is dropped
    after the test; no existing application tables are modified.
    """
    database_url = resolve_test_database_url(os.environ)
    schema = f"r7b_migration_{uuid4().hex}"
    admin_engine = create_engine(database_url)
    scoped_engine: Engine | None = None
    schema_created = False

    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True

        # migrations/env.py reads DATABASE_URL. Point it explicitly at the
        # fail-closed test URL, never at a developer's application URL.
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setenv("PGOPTIONS", f"-c search_path={schema},public")

        scoped_engine = create_engine(database_url)
        with scoped_engine.connect():
            pass

        config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
        command.upgrade(Config(str(config_path)), "0014_knowledge_quality")

        with scoped_engine.connect() as connection:
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert revision == "0014_knowledge_quality"

        yield MigrationSandbox(engine=scoped_engine, schema=schema)
    finally:
        if scoped_engine is not None:
            scoped_engine.dispose()

        if schema_created:
            with admin_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))

        admin_engine.dispose()


def test_pre_0015_schema_is_isolated_and_has_legacy_knowledge_shape(
    pre_0015_schema: MigrationSandbox,
) -> None:
    """Step 1: establish the exact populated-migration starting revision."""
    with pre_0015_schema.engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        columns = set(
            connection.scalars(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = :schema
                      AND table_name = 'knowledge_items'
                    """
                ),
                {"schema": pre_0015_schema.schema},
            )
        )
        tables = set(
            connection.scalars(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = :schema
                    """
                ),
                {"schema": pre_0015_schema.schema},
            )
        )

    assert revision == "0014_knowledge_quality"
    assert {"knowledge_items", "learning_changes", "teams"} <= tables
    assert {
        "current_learning_change_id",
        "supersedes_item_id",
        "superseded_by_id",
    }.isdisjoint(columns)
