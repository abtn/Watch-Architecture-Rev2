"""Build isolated pre-0015 databases for R7-B migration tests."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _database_config import resolve_test_database_url
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text


@dataclass(frozen=True)
class MigrationSandbox:
    """A PostgreSQL schema whose search path is isolated for Alembic."""

    engine: Engine
    schema: str


def _upgrade_to_revision(
    engine: Engine,
    schema: str,
    revision: str,
) -> None:
    """Run Alembic against the explicitly scoped test connection."""
    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    with engine.begin() as connection:
        config = Config(str(config_path))
        config.attributes["connection"] = connection
        config.attributes["version_table_schema"] = schema
        command.upgrade(config, revision)


@pytest.fixture
def pre_0015_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[MigrationSandbox]:
    """Upgrade an empty isolated schema to the legacy 0014 database shape.

    The URL is resolved from TEST_DATABASE_URL only. Migration and verification
    use the same explicitly schema-scoped connection and version table. The
    schema is dropped after the test; no existing application tables change.
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

        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.delenv("PGOPTIONS", raising=False)

        scoped_engine = create_engine(
            database_url,
            connect_args={"options": f"-c search_path={schema},public"},
        )
        with scoped_engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == schema

        _upgrade_to_revision(scoped_engine, schema, "0014_knowledge_quality")

        with scoped_engine.connect() as connection:
            revision = connection.scalar(
                text(f'SELECT version_num FROM "{schema}".alembic_version')
            )
        assert revision == "0014_knowledge_quality"

        yield MigrationSandbox(engine=scoped_engine, schema=schema)
    finally:
        if scoped_engine is not None:
            scoped_engine.dispose()

        if schema_created:
            with admin_engine.begin() as connection:
                connection.execute(
                    text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                )

        admin_engine.dispose()


def _legacy_snapshot(
    item_id: UUID,
    team_id: UUID,
    learning_change_id: UUID,
    title: str,
) -> dict[str, object]:
    """Return the exact unwrapped create-snapshot shape written before B1."""
    review_after = datetime(2026, 12, 1, tzinfo=timezone.utc)
    return {
        "id": str(item_id),
        "team_id": str(team_id),
        "kind": "practice",
        "title": title,
        "statement": f"Preserve contrary evidence for {title}.",
        "body": f"Compare the primary source with independent evidence for {title}.",
        "applicability": {"domain": "science"},
        "preconditions": ["The source is accessible."],
        "assumptions": ["The source is authentic."],
        "limitations": ["This does not establish causation."],
        "non_applicability": ["Unrelated domains."],
        "failure_modes": ["A source may be incomplete."],
        "known_counterexamples": ["A conflicting independent replication."],
        "missing_information": ["Further independent replication."],
        "uncertainty": ["The evidence may remain incomplete."],
        "confidence": "0.875",
        "status": "active",
        "version": 1,
        "last_validated_at": None,
        "review_after": review_after.isoformat(),
        "origin_learning_change_id": str(learning_change_id),
    }


def _insert_legacy_knowledge_item(
    engine: Engine,
    *,
    team_id: UUID,
    item_id: UUID,
    learning_change_id: UUID,
    title: str,
    created_at: datetime,
) -> dict[str, object]:
    """Insert a realistic accepted create and its pre-B1 KnowledgeItem row."""
    proposer_task_id = uuid4()
    approval_task_id = uuid4()
    snapshot = _legacy_snapshot(item_id, team_id, learning_change_id, title)
    committed_at = created_at + timedelta(minutes=5)
    task_budget = json.dumps(
        {"max_tool_calls": 0, "max_cost_usd": 0.0, "deadline_seconds": 60}
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO teams (id, domain, status)
                VALUES (:id, 'migration_test', 'active')
                """
            ),
            {"id": team_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO team_policies (id, team_id, version, rules)
                VALUES (:id, :team_id, 1, CAST(:rules AS jsonb))
                """
            ),
            {
                "id": uuid4(),
                "team_id": team_id,
                "rules": json.dumps({"sources": []}),
            },
        )

        for task_id, task_type in (
            (proposer_task_id, "distill_experience"),
            (approval_task_id, "operator_decision"),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO tasks (
                        id, team_id, task_type, status, attempt_count,
                        policy_version, allowed_writes, budget, created_at,
                        max_attempts
                    )
                    VALUES (
                        :id, :team_id, :task_type, 'done', 1,
                        1, CAST(:allowed_writes AS jsonb),
                        CAST(:budget AS jsonb), :created_at, 3
                    )
                    """
                ),
                {
                    "id": task_id,
                    "team_id": team_id,
                    "task_type": task_type,
                    "allowed_writes": json.dumps(["LearningChange"]),
                    "budget": task_budget,
                    "created_at": created_at,
                },
            )

        connection.execute(
            text(
                """
                INSERT INTO learning_changes (
                    id, team_id, target_kind, target_id, operation,
                    proposed_state, previous_state, committed_state,
                    evidence_basis, evidence_basis_hash, status,
                    idempotency_key, proposed_by_task_id,
                    committed_by_task_id, operator_id, decision_reason,
                    created_at, committed_at
                )
                VALUES (
                    :id, :team_id, 'knowledge_item', NULL, 'create',
                    CAST(:proposed_state AS jsonb), NULL,
                    CAST(:committed_state AS jsonb),
                    '[]'::jsonb, :evidence_basis_hash, 'accepted',
                    :idempotency_key, :proposed_by_task_id,
                    :committed_by_task_id, 'operator:migration-test', NULL,
                    :created_at, :committed_at
                )
                """
            ),
            {
                "id": learning_change_id,
                "team_id": team_id,
                "proposed_state": json.dumps(snapshot),
                "committed_state": json.dumps(snapshot),
                "evidence_basis_hash": "sha256:" + ("a" * 64),
                "idempotency_key": f"legacy-create-{item_id}",
                "proposed_by_task_id": proposer_task_id,
                "committed_by_task_id": approval_task_id,
                "created_at": created_at,
                "committed_at": committed_at,
            },
        )

        connection.execute(
            text(
                """
                INSERT INTO knowledge_items (
                    id, team_id, kind, title, statement, body,
                    applicability, preconditions, assumptions, limitations,
                    non_applicability, failure_modes, known_counterexamples,
                    missing_information, uncertainty, confidence, status,
                    version, last_validated_at, review_after,
                    origin_learning_change_id, created_at, updated_at
                )
                VALUES (
                    :id, :team_id, :kind, :title, :statement, :body,
                    CAST(:applicability AS jsonb),
                    CAST(:preconditions AS jsonb),
                    CAST(:assumptions AS jsonb),
                    CAST(:limitations AS jsonb),
                    CAST(:non_applicability AS jsonb),
                    CAST(:failure_modes AS jsonb),
                    CAST(:known_counterexamples AS jsonb),
                    CAST(:missing_information AS jsonb),
                    CAST(:uncertainty AS jsonb),
                    :confidence, :status, :version, :last_validated_at,
                    :review_after, :origin_learning_change_id,
                    :created_at, :updated_at
                )
                """
            ),
            {
                "id": item_id,
                "team_id": team_id,
                "kind": snapshot["kind"],
                "title": snapshot["title"],
                "statement": snapshot["statement"],
                "body": snapshot["body"],
                "applicability": json.dumps(snapshot["applicability"]),
                "preconditions": json.dumps(snapshot["preconditions"]),
                "assumptions": json.dumps(snapshot["assumptions"]),
                "limitations": json.dumps(snapshot["limitations"]),
                "non_applicability": json.dumps(snapshot["non_applicability"]),
                "failure_modes": json.dumps(snapshot["failure_modes"]),
                "known_counterexamples": json.dumps(
                    snapshot["known_counterexamples"]
                ),
                "missing_information": json.dumps(snapshot["missing_information"]),
                "uncertainty": json.dumps(snapshot["uncertainty"]),
                "confidence": snapshot["confidence"],
                "status": snapshot["status"],
                "version": snapshot["version"],
                "last_validated_at": None,
                "review_after": datetime.fromisoformat(
                    str(snapshot["review_after"])
                ),
                "origin_learning_change_id": learning_change_id,
                "created_at": created_at,
                "updated_at": created_at,
            },
        )

    return snapshot


def test_pre_0015_schema_is_isolated_and_has_legacy_knowledge_shape(
    pre_0015_schema: MigrationSandbox,
) -> None:
    """Step 1: establish the exact populated-migration starting revision."""
    with pre_0015_schema.engine.connect() as connection:
        revision = connection.scalar(
            text(
                f'SELECT version_num FROM "{pre_0015_schema.schema}".alembic_version'
            )
        )
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


def test_0015_backfills_populated_legacy_items_without_rewriting_snapshots(
    pre_0015_schema: MigrationSandbox,
) -> None:
    """Step 2: migrate actual 0014 rows and prove lossless pointer backfill."""
    created_at = datetime(2026, 10, 20, tzinfo=timezone.utc)
    records = [
        (
            uuid4(),
            uuid4(),
            uuid4(),
            "Legacy source-review practice A",
            created_at,
        ),
        (
            uuid4(),
            uuid4(),
            uuid4(),
            "Legacy source-review practice B",
            created_at + timedelta(days=1),
        ),
    ]

    snapshots: dict[UUID, dict[str, object]] = {}
    for team_id, item_id, learning_change_id, title, item_created_at in records:
        snapshots[item_id] = _insert_legacy_knowledge_item(
            pre_0015_schema.engine,
            team_id=team_id,
            item_id=item_id,
            learning_change_id=learning_change_id,
            title=title,
            created_at=item_created_at,
        )

    expected_snapshots = {
        learning_change_id: snapshots[item_id]
        for _, item_id, learning_change_id, _, _ in records
    }

    with pre_0015_schema.engine.connect() as connection:
        before_snapshots = dict(
            connection.execute(
                text(
                    """
                    SELECT id, committed_state
                    FROM learning_changes
                    ORDER BY id
                    """
                )
            ).all()
        )
        before_items = {
            row["id"]: dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT id, team_id, kind, title, statement, body,
                           applicability, preconditions, assumptions,
                           limitations, non_applicability, failure_modes,
                           known_counterexamples, missing_information,
                           uncertainty, confidence, status, version,
                           last_validated_at, review_after,
                           origin_learning_change_id, created_at, updated_at
                    FROM knowledge_items
                    ORDER BY id
                    """
                )
            ).mappings()
        }

    assert len(before_items) == 2
    assert before_snapshots == expected_snapshots

    _upgrade_to_revision(
        pre_0015_schema.engine,
        pre_0015_schema.schema,
        "0015_r7b_history",
    )

    with pre_0015_schema.engine.connect() as connection:
        revision = connection.scalar(
            text(
                f'SELECT version_num FROM "{pre_0015_schema.schema}".alembic_version'
            )
        )
        after_items = {
            row["id"]: dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT id, team_id, kind, title, statement, body,
                           applicability, preconditions, assumptions,
                           limitations, non_applicability, failure_modes,
                           known_counterexamples, missing_information,
                           uncertainty, confidence, status, version,
                           last_validated_at, review_after,
                           origin_learning_change_id, current_learning_change_id,
                           supersedes_item_id, superseded_by_id,
                           created_at, updated_at
                    FROM knowledge_items
                    ORDER BY id
                    """
                )
            ).mappings()
        }
        after_snapshots = dict(
            connection.execute(
                text(
                    """
                    SELECT id, committed_state
                    FROM learning_changes
                    ORDER BY id
                    """
                )
            ).all()
        )
        pointer_nullable = connection.scalar(
            text(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_schema = :schema
                  AND table_name = 'knowledge_items'
                  AND column_name = 'current_learning_change_id'
                """
            ),
            {"schema": pre_0015_schema.schema},
        )

    assert revision == "0015_r7b_history"
    assert pointer_nullable == "NO"
    assert set(after_items) == set(before_items)
    assert after_snapshots == before_snapshots

    for item_id, before in before_items.items():
        after = after_items[item_id]
        assert (
            after["current_learning_change_id"]
            == before["origin_learning_change_id"]
        )
        assert after["supersedes_item_id"] is None
        assert after["superseded_by_id"] is None
        for field, value in before.items():
            assert after[field] == value, f"migration changed {field} for {item_id}"

    for _, item_id, learning_change_id, _, _ in records:
        assert (
            after_items[item_id]["current_learning_change_id"]
            == learning_change_id
        )


def _drop_legacy_origin_team_constraint(engine: Engine) -> None:
    """Allow a test-only orphan or cross-Team origin in the isolated schema."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE knowledge_items "
                "DROP CONSTRAINT fk_knowledge_items_origin_learning_change_team"
            )
        )


@pytest.mark.parametrize(
    "invalid_case",
    [
        "missing_origin",
        "rejected_origin",
        "non_create_origin",
        "cross_team_origin",
        "snapshot_item_mismatch",
        "snapshot_team_mismatch",
    ],
)
def test_0015_refuses_invalid_legacy_origins_without_partial_migration(
    pre_0015_schema: MigrationSandbox,
    invalid_case: str,
) -> None:
    """Step 3: fail closed for missing, unaccepted, wrong-Team, or mismatched roots."""
    created_at = datetime(2026, 10, 20, tzinfo=timezone.utc)
    team_id = uuid4()
    item_id = uuid4()
    learning_change_id = uuid4()
    snapshot = _insert_legacy_knowledge_item(
        pre_0015_schema.engine,
        team_id=team_id,
        item_id=item_id,
        learning_change_id=learning_change_id,
        title=f"Invalid legacy origin: {invalid_case}",
        created_at=created_at,
    )

    if invalid_case in {"missing_origin", "cross_team_origin"}:
        # The normal composite FK correctly prevents these states. Remove it
        # only in this disposable schema to represent pre-existing corruption.
        _drop_legacy_origin_team_constraint(pre_0015_schema.engine)

    with pre_0015_schema.engine.begin() as connection:
        if invalid_case == "missing_origin":
            connection.execute(
                text(
                    "UPDATE knowledge_items "
                    "SET origin_learning_change_id = :missing_id "
                    "WHERE id = :item_id"
                ),
                {"missing_id": uuid4(), "item_id": item_id},
            )
        elif invalid_case == "rejected_origin":
            connection.execute(
                text(
                    """
                    UPDATE learning_changes
                    SET status = 'rejected',
                        committed_state = NULL,
                        decision_reason = 'Rejected legacy origin fixture'
                    WHERE id = :learning_change_id
                    """
                ),
                {"learning_change_id": learning_change_id},
            )
        elif invalid_case == "non_create_origin":
            connection.execute(
                text(
                    """
                    UPDATE learning_changes
                    SET operation = 'revise', target_id = :target_id
                    WHERE id = :learning_change_id
                    """
                ),
                {
                    "target_id": uuid4(),
                    "learning_change_id": learning_change_id,
                },
            )
        elif invalid_case == "cross_team_origin":
            other_team_id = uuid4()
            other_learning_change_id = uuid4()
            _insert_legacy_knowledge_item(
                pre_0015_schema.engine,
                team_id=other_team_id,
                item_id=uuid4(),
                learning_change_id=other_learning_change_id,
                title="Valid create in another Team",
                created_at=created_at + timedelta(days=1),
            )
            connection.execute(
                text(
                    "UPDATE knowledge_items "
                    "SET origin_learning_change_id = :other_origin_id "
                    "WHERE id = :item_id"
                ),
                {
                    "other_origin_id": other_learning_change_id,
                    "item_id": item_id,
                },
            )
        elif invalid_case in {
            "snapshot_item_mismatch",
            "snapshot_team_mismatch",
        }:
            invalid_snapshot = dict(snapshot)
            if invalid_case == "snapshot_item_mismatch":
                invalid_snapshot["id"] = str(uuid4())
            else:
                invalid_snapshot["team_id"] = str(uuid4())
            connection.execute(
                text(
                    """
                    UPDATE learning_changes
                    SET committed_state = CAST(:snapshot AS jsonb)
                    WHERE id = :learning_change_id
                    """
                ),
                {
                    "snapshot": json.dumps(invalid_snapshot),
                    "learning_change_id": learning_change_id,
                },
            )

    with pytest.raises(
        RuntimeError,
        match=f"invalid KnowledgeItem origin for item {item_id}",
    ):
        _upgrade_to_revision(
            pre_0015_schema.engine,
            pre_0015_schema.schema,
            "0015_r7b_history",
        )

    with pre_0015_schema.engine.connect() as connection:
        revision = connection.scalar(
            text(
                f'SELECT version_num FROM "{pre_0015_schema.schema}".alembic_version'
            )
        )
        pointer_column_exists = connection.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = :schema
                      AND table_name = 'knowledge_items'
                      AND column_name = 'current_learning_change_id'
                )
                """
            ),
            {"schema": pre_0015_schema.schema},
        )

    assert revision == "0014_knowledge_quality"
    assert not pointer_column_exists

