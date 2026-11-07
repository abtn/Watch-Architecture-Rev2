"""Fail-closed migration tests for R7-B B2 projection provenance pins."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_r7b_history_migration import (
    MigrationSandbox,
    _insert_legacy_knowledge_item,
    _upgrade_to_revision,
)
from test_r7b_history_migration import (
    pre_0015_schema as _pre_0015_schema_fixture,
)

pre_0015_schema = _pre_0015_schema_fixture


@dataclass(frozen=True)
class ProjectionMigrationSandbox:
    engine: Engine
    schema: str
    item_id: UUID
    team_id: UUID
    learning_change_id: UUID
    other_learning_change_id: UUID


@pytest.fixture
def pre_0016_schema(
    pre_0015_schema: MigrationSandbox,
) -> Iterator[ProjectionMigrationSandbox]:
    """Create real 0015 canonical rows and pre-migration Team Experience data."""
    created_at = datetime(2026, 10, 20, tzinfo=timezone.utc)
    team_id, item_id, learning_change_id = uuid4(), uuid4(), uuid4()
    other_team_id, other_item_id, other_change_id = uuid4(), uuid4(), uuid4()

    _insert_legacy_knowledge_item(
        pre_0015_schema.engine,
        team_id=team_id,
        item_id=item_id,
        learning_change_id=learning_change_id,
        title="Projection migration fixture",
        created_at=created_at,
    )
    _insert_legacy_knowledge_item(
        pre_0015_schema.engine,
        team_id=other_team_id,
        item_id=other_item_id,
        learning_change_id=other_change_id,
        title="Cross-team projection fixture",
        created_at=created_at,
    )
    _upgrade_to_revision(
        pre_0015_schema.engine, pre_0015_schema.schema, "0015_r7b_history"
    )

    with pre_0015_schema.engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO team_experience_chunks (
                    id, knowledge_item_id, team_id, item_version,
                    item_content_hash, origin_learning_change_id,
                    chunk_index, chunk_text, chunk_hash, chunking_version,
                    embedding, embedding_provider, embedding_model,
                    embedding_revision, embedding_configuration,
                    embedding_dimensions, embedding_space_key
                )
                VALUES (
                    :id, :item_id, :team_id, 1,
                    :item_hash, :change_id, 0, 'preserved chunk text',
                    :chunk_hash, 'test-chunking-v1',
                    CAST('[0.1, 0.2]' AS vector), 'test-provider',
                    'test-model', 'test-revision', 'test-configuration',
                    2, :space_key
                )
                """
            ),
            {
                "id": uuid4(),
                "item_id": item_id,
                "team_id": team_id,
                "item_hash": "sha256:" + "a" * 64,
                "change_id": learning_change_id,
                "chunk_hash": "sha256:" + "b" * 64,
                "space_key": "sha256:" + "c" * 64,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO team_experience_index_state (
                    id, knowledge_item_id, team_id, item_version,
                    item_content_hash, origin_learning_change_id, status,
                    embedding_space_key, chunk_count, attempt_count,
                    indexed_at
                )
                VALUES (
                    :id, :item_id, :team_id, 1, :item_hash, :change_id,
                    'published', :space_key, 1, 1, :indexed_at
                )
                """
            ),
            {
                "id": uuid4(),
                "item_id": item_id,
                "team_id": team_id,
                "item_hash": "sha256:" + "a" * 64,
                "change_id": learning_change_id,
                "space_key": "sha256:" + "c" * 64,
                "indexed_at": created_at,
            },
        )

    yield ProjectionMigrationSandbox(
        engine=pre_0015_schema.engine,
        schema=pre_0015_schema.schema,
        item_id=item_id,
        team_id=team_id,
        learning_change_id=learning_change_id,
        other_learning_change_id=other_change_id,
    )


def _existing_projection_values(
    engine: Engine,
) -> tuple[dict[str, object], dict[str, object]]:
    with engine.connect() as connection:
        chunk = dict(
            connection.execute(
                text(
                    """
                    SELECT item_version, item_content_hash, origin_learning_change_id,
                           chunk_index, chunk_text, chunk_hash, chunking_version,
                           embedding::text AS embedding_text, embedding_provider,
                           embedding_model, embedding_revision, embedding_configuration,
                           embedding_dimensions, embedding_space_key
                    FROM team_experience_chunks
                    """
                )
            ).mappings().one()
        )
        state = dict(
            connection.execute(
                text(
                    """
                    SELECT item_version, item_content_hash, origin_learning_change_id,
                           status, embedding_space_key, chunk_count, attempt_count,
                           last_error_kind, last_attempt_at, indexed_at
                    FROM team_experience_index_state
                    """
                )
            ).mappings().one()
        )
    return chunk, state


def test_0016_preserves_legacy_projection_bytes_and_marks_them_opaque_and_stale(
    pre_0016_schema: ProjectionMigrationSandbox,
) -> None:
    before_chunk, before_state = _existing_projection_values(pre_0016_schema.engine)
    assert before_state["status"] == "published"

    _upgrade_to_revision(
        pre_0016_schema.engine,
        pre_0016_schema.schema,
        "0016_team_exp_history_pins",
    )

    after_chunk, after_state = _existing_projection_values(pre_0016_schema.engine)
    assert after_chunk == before_chunk
    assert {
        key: value for key, value in after_state.items() if key != "status"
    } == {
        key: value for key, value in before_state.items() if key != "status"
    }
    assert after_state["status"] == "stale"

    with pre_0016_schema.engine.connect() as connection:
        discoverable_rows = connection.scalar(
            text(
                """
                SELECT count(*)
                FROM team_experience_chunks AS chunk
                JOIN team_experience_index_state AS state
                  ON state.knowledge_item_id = chunk.knowledge_item_id
                 AND state.team_id = chunk.team_id
                WHERE state.status = 'published'
                """
            )
        )
    assert discoverable_rows == 0

    with pre_0016_schema.engine.connect() as connection:
        chunk_pins = connection.execute(
            text(
                "SELECT current_learning_change_id, content_hash_scheme "
                "FROM team_experience_chunks"
            )
        ).mappings().one()
        state_pins = connection.execute(
            text(
                "SELECT current_learning_change_id, content_hash_scheme "
                "FROM team_experience_index_state"
            )
        ).mappings().one()
        revision = connection.scalar(
            text(
                f'SELECT version_num FROM "{pre_0016_schema.schema}".alembic_version'
            )
        )

    assert chunk_pins["current_learning_change_id"] is None
    assert chunk_pins["content_hash_scheme"] == "legacy-opaque"
    assert state_pins["current_learning_change_id"] is None
    assert state_pins["content_hash_scheme"] == "legacy-opaque"
    assert revision == "0016_team_exp_history_pins"


def test_0016_accepts_v2_pins_and_rejects_invalid_scheme_and_cross_team_pointer(
    pre_0016_schema: ProjectionMigrationSandbox,
) -> None:
    _upgrade_to_revision(
        pre_0016_schema.engine,
        pre_0016_schema.schema,
        "0016_team_exp_history_pins",
    )
    with pre_0016_schema.engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE team_experience_chunks
                SET current_learning_change_id = :change_id,
                    content_hash_scheme = 'watch.r7b.knowledge-content.v2'
                """
            ),
            {"change_id": pre_0016_schema.learning_change_id},
        )
        connection.execute(
            text(
                """
                UPDATE team_experience_index_state
                SET current_learning_change_id = :change_id,
                    content_hash_scheme = 'watch.r7b.knowledge-content.v2'
                """
            ),
            {"change_id": pre_0016_schema.learning_change_id},
        )

    with pytest.raises(IntegrityError):
        with pre_0016_schema.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE team_experience_chunks "
                    "SET content_hash_scheme = 'unsupported-scheme'"
                )
            )

    with pytest.raises(IntegrityError):
        with pre_0016_schema.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE team_experience_index_state "
                    "SET content_hash_scheme = 'unsupported-scheme'"
                )
            )

    with pytest.raises(IntegrityError):
        with pre_0016_schema.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE team_experience_chunks "
                    "SET current_learning_change_id = :other_change_id"
                ),
                {"other_change_id": pre_0016_schema.other_learning_change_id},
            )

    with pytest.raises(IntegrityError):
        with pre_0016_schema.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE team_experience_index_state "
                    "SET current_learning_change_id = :other_change_id"
                ),
                {"other_change_id": pre_0016_schema.other_learning_change_id},
            )


def test_0016_failed_migration_rolls_back_schema_and_existing_rows(
    pre_0016_schema: ProjectionMigrationSandbox,
) -> None:
    before_chunk, before_state = _existing_projection_values(pre_0016_schema.engine)
    with pre_0016_schema.engine.begin() as connection:
        connection.execute(
            text(
                f"""
                CREATE FUNCTION "{pre_0016_schema.schema}".reject_projection_backfill()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'migration_test_abort';
                END;
                $$
                """
            )
        )
        connection.execute(
            text(
                f"""
                CREATE TRIGGER reject_projection_backfill
                BEFORE UPDATE ON "{pre_0016_schema.schema}".team_experience_chunks
                FOR EACH ROW EXECUTE FUNCTION
                "{pre_0016_schema.schema}".reject_projection_backfill()
                """
            )
        )

    with pytest.raises(DBAPIError, match="migration_test_abort"):
        _upgrade_to_revision(
            pre_0016_schema.engine,
            pre_0016_schema.schema,
            "0016_team_exp_history_pins",
        )

    after_chunk, after_state = _existing_projection_values(pre_0016_schema.engine)
    assert after_chunk == before_chunk
    assert after_state == before_state

    with pre_0016_schema.engine.connect() as connection:
        columns = set(
            connection.scalars(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = :schema
                      AND table_name = 'team_experience_chunks'
                    """
                ),
                {"schema": pre_0016_schema.schema},
            )
        )
        revision = connection.scalar(
            text(
                f'SELECT version_num FROM "{pre_0016_schema.schema}".alembic_version'
            )
        )

    assert "current_learning_change_id" not in columns
    assert "content_hash_scheme" not in columns
    assert revision == "0015_r7b_history"
