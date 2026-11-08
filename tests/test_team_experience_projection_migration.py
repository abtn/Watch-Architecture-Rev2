"""Fail-closed migration tests for R7-B B2 projection provenance pins."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker
from test_r7b_history_migration import (
    MigrationSandbox,
    _insert_legacy_knowledge_item,
    _upgrade_to_revision,
)
from test_r7b_history_migration import (
    pre_0015_schema as _pre_0015_schema_fixture,
)

from core.embeddings import EmbeddingBatch, EmbeddingSpace
from core.knowledge_index import (
    HybridKnowledgeRetriever,
    TeamExperienceIndexer,
)
from core.learning_history import KNOWLEDGE_CONTENT_HASH_SCHEME
from core.models import (
    Event,
    KnowledgeItem,
    LearningChange,
    Outcome,
    Task,
    TeamExperienceChunk,
    TeamExperienceIndexState,
)
from core.snapshot_store import SnapshotStore

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

    # Keep the legacy projection rows, but make the underlying accepted create
    # history satisfy the current canonical approval-provenance contract.
    session_factory = sessionmaker(
        bind=pre_0015_schema.engine, expire_on_commit=False
    )
    with session_factory.begin() as session:
        for current_team_id, current_item_id, current_change_id in (
            (team_id, item_id, learning_change_id),
            (other_team_id, other_item_id, other_change_id),
        ):
            change = session.get(LearningChange, current_change_id)
            assert change is not None
            approval_task = session.get(Task, change.committed_by_task_id)
            assert approval_task is not None
            approval_task.task_type = "approve_learning_change"
            approval_task.allowed_writes = ["LearningChange", "KnowledgeItem"]
            approval_task.completed_at = change.committed_at
            proposal_hash = "sha256:" + "c" * 64
            change.proposed_state = {
                **change.proposed_state,
                "proposal_hash": proposal_hash,
                "evidence_basis_hash": change.evidence_basis_hash,
            }
            observation_ref = f"migration-test:{current_item_id}"
            observation_hash = "sha256:" + "d" * 64
            outcome_id = uuid4()
            session.add(
                Outcome(
                    id=outcome_id,
                    team_id=current_team_id,
                    subject_kind="task",
                    subject_id=approval_task.id,
                    outcome_type="task_execution",
                    expected=None,
                    observation_snapshot_ref=observation_ref,
                    observation_hash=observation_hash,
                    observed_at=change.committed_at,
                    recorded_by_task_id=approval_task.id,
                )
            )
            session.add_all(
                [
                    Event(
                        id=uuid4(),
                        task_id=approval_task.id,
                        type="task_started",
                        payload={
                            "from_status": "pending",
                            "to_status": "running",
                            "attempt_count": 1,
                        },
                        created_at=approval_task.created_at,
                    ),
                    Event(
                        id=uuid4(),
                        task_id=approval_task.id,
                        type="learning_change_accepted",
                        payload={
                            "schema_version": 1,
                            "learning_change_id": str(change.id),
                            "operation": change.operation,
                            "decision": "accept",
                            "operator_id": change.operator_id,
                            "approval_task_id": str(approval_task.id),
                            "attempt_count": 1,
                            "evidence_basis_hash": change.evidence_basis_hash,
                            "proposal_hash": proposal_hash,
                            "committed_at": change.committed_at.isoformat(),
                            "knowledge_item_id": str(current_item_id),
                            "knowledge_item_version": 1,
                        },
                        created_at=change.committed_at,
                    ),
                    Event(
                        id=uuid4(),
                        task_id=approval_task.id,
                        type="task_completed",
                        payload={
                            "from_status": "running",
                            "to_status": "done",
                            "attempt_count": 1,
                            "result_category": "success_learning_change_accepted",
                            "failure_reason": None,
                            "outcome_id": str(outcome_id),
                            "observation_snapshot_ref": observation_ref,
                            "observation_hash": observation_hash,
                            "learning_change_id": str(change.id),
                        },
                        created_at=change.committed_at,
                    ),
                ]
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


class _MigrationEmbeddingProvider:
    def current_space(self) -> EmbeddingSpace:
        return EmbeddingSpace(
            provider="r7b-migration-test",
            model="deterministic-two-dimensional",
            revision="v1",
            dimensions=2,
            configuration="r7b-migration-test-v1",
        )

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        return EmbeddingBatch(
            space=self.current_space(),
            vectors=tuple((1.0, 0.0) for _ in texts),
        )


def test_real_0016_migration_blocks_legacy_projection_until_application_rebuild(
    pre_0016_schema: ProjectionMigrationSandbox,
    tmp_path: Path,
) -> None:
    _upgrade_to_revision(
        pre_0016_schema.engine,
        pre_0016_schema.schema,
        "0016_team_exp_history_pins",
    )
    session_factory = sessionmaker(
        bind=pre_0016_schema.engine, expire_on_commit=False
    )
    snapshot_store = SnapshotStore(tmp_path)
    provider = _MigrationEmbeddingProvider()
    indexer = TeamExperienceIndexer(session_factory, provider)
    retriever = HybridKnowledgeRetriever(
        session_factory, snapshot_store, provider
    )

    with session_factory() as session:
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id
                == pre_0016_schema.item_id
            )
        )
        chunks = list(
            session.scalars(
                select(TeamExperienceChunk).where(
                    TeamExperienceChunk.knowledge_item_id
                    == pre_0016_schema.item_id
                )
            )
        )
        assert state is not None
        assert state.status == "stale"
        assert state.content_hash_scheme == "legacy-opaque"
        assert state.current_learning_change_id is None
        assert chunks
        assert all(
            chunk.content_hash_scheme == "legacy-opaque"
            and chunk.current_learning_change_id is None
            for chunk in chunks
        )

    assert retriever.retrieve(
        pre_0016_schema.team_id, "Projection migration fixture"
    ) == ()

    now = datetime.now(timezone.utc)
    rebuilt = indexer.rebuild_all(now=now)
    result = next(
        entry
        for entry in rebuilt
        if entry.knowledge_item_id == pre_0016_schema.item_id
    )
    assert result.outcome == "indexed"

    with session_factory() as session:
        item = session.get(KnowledgeItem, pre_0016_schema.item_id)
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id
                == pre_0016_schema.item_id
            )
        )
        chunks = list(
            session.scalars(
                select(TeamExperienceChunk).where(
                    TeamExperienceChunk.knowledge_item_id
                    == pre_0016_schema.item_id
                )
            )
        )
    assert item is not None and state is not None
    assert item.current_learning_change_id is not None
    assert state.status == "published"
    assert state.current_learning_change_id == item.current_learning_change_id
    assert state.content_hash_scheme == KNOWLEDGE_CONTENT_HASH_SCHEME
    assert chunks
    assert all(
        chunk.current_learning_change_id == item.current_learning_change_id
        and chunk.content_hash_scheme == KNOWLEDGE_CONTENT_HASH_SCHEME
        for chunk in chunks
    )

    passages = retriever.retrieve(
        pre_0016_schema.team_id, "Projection migration fixture"
    )
    assert passages
    assert all(
        passage.knowledge_item_id == pre_0016_schema.item_id
        and passage.current_learning_change_id == item.current_learning_change_id
        and passage.content_hash_scheme == KNOWLEDGE_CONTENT_HASH_SCHEME
        for passage in passages
    )

    repeated = indexer.rebuild_all(now=now)
    repeated_result = next(
        entry
        for entry in repeated
        if entry.knowledge_item_id == pre_0016_schema.item_id
    )
    assert repeated_result.outcome == "unchanged"

