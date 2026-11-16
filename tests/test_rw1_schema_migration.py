"""PostgreSQL migration proofs for the RW-1 world-memory schema."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _database_config import resolve_test_database_url
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text


@dataclass(frozen=True)
class MigrationSandbox:
    engine: Engine
    schema: str


@dataclass(frozen=True)
class LegacyEvidence:
    team_id: UUID
    task_id: UUID
    outcome_id: UUID
    evaluation_id: UUID
    link_id: UUID
    reference_key: str
    proposal_hash: str


def _run_revision(
    engine: Engine,
    schema: str,
    revision: str,
    *,
    downgrade: bool = False,
) -> None:
    config_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    with engine.begin() as connection:
        config = Config(str(config_path))
        config.attributes["connection"] = connection
        config.attributes["version_table_schema"] = schema
        if downgrade:
            command.downgrade(config, revision)
        else:
            command.upgrade(config, revision)


@pytest.fixture
def rw1_migration_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[MigrationSandbox]:
    database_url = resolve_test_database_url(os.environ)
    schema = f"rw1_migration_{uuid4().hex}"
    admin_engine = create_engine(database_url)
    scoped_engine: Engine | None = None
    created = False
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.delenv("PGOPTIONS", raising=False)
        scoped_engine = create_engine(
            database_url,
            connect_args={"options": f"-c search_path={schema},public"},
        )
        with scoped_engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == schema
        _run_revision(scoped_engine, schema, "0018_r7b_lifecycle_review_date")
        yield MigrationSandbox(scoped_engine, schema)
    finally:
        if scoped_engine is not None:
            scoped_engine.dispose()
        if created:
            with admin_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def _digest(value: dict[str, object]) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _seed_legacy_evaluation(
    sandbox: MigrationSandbox,
    *,
    valid_hash: bool = True,
) -> LegacyEvidence:
    team_id, policy_id, task_id, outcome_id, evaluation_id, link_id = (
        uuid4() for _ in range(6)
    )
    link_payload: dict[str, object] = {
        "source_kind": "outcome",
        "outcome_id": str(outcome_id),
        "signal_id": None,
        "snapshot_ref": None,
        "snapshot_hash": None,
        "stance": "supports",
        "quote_text": None,
        "quote_start": None,
        "quote_end": None,
    }
    reference_key = _digest(link_payload)
    evidence_item = {**link_payload, "reference_key": reference_key}
    findings = {
        "observed_result": "A deterministic legacy fixture.",
        "intended_result": "Preserve its exact proposal identity.",
        "method_or_process": "Migration test.",
        "context": ["PostgreSQL fixture."],
        "alternative_explanations": ["None asserted."],
        "attribution": "not established",
        "uncertainty": ["Fixture only."],
    }
    proposal_payload = {
        "team_id": str(team_id),
        "outcome_id": str(outcome_id),
        "conclusion": "worked",
        "findings": findings,
        "evidence": [evidence_item],
        "evaluator_kind": "rule",
        "evaluator_identity": "rw1-migration-test",
        "evaluator_revision": "1",
        "idempotency_key": "rw1-legacy-fixture",
    }
    proposal_hash = _digest(proposal_payload)
    if not valid_hash:
        proposal_hash = "sha256:" + ("0" * 64)

    with sandbox.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO teams (id, domain, status) "
                "VALUES (:id, 'rw1_migration_test', 'active')"
            ),
            {"id": team_id},
        )
        connection.execute(
            text(
                "INSERT INTO team_policies (id, team_id, version, rules) "
                "VALUES (:id, :team_id, 1, '{}'::jsonb)"
            ),
            {"id": policy_id, "team_id": team_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO tasks (
                    id, team_id, task_type, status, attempt_count,
                    policy_version, allowed_writes, budget, max_attempts
                )
                VALUES (
                    :id, :team_id, 'evaluate_outcome', 'running', 1, 1,
                    '["Evaluation", "EvidenceLink"]'::jsonb,
                    '{"max_tool_calls":0,"max_cost_usd":0,"deadline_seconds":30}'::jsonb,
                    3
                )
                """
            ),
            {"id": task_id, "team_id": team_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO outcomes (
                    id, team_id, subject_kind, subject_id, outcome_type,
                    expected, observation_snapshot_ref, observation_hash,
                    observed_at, recorded_by_task_id
                )
                VALUES (
                    :id, :team_id, 'task', :task_id, 'prediction_registered',
                    '{"expected":"migration fixture"}'::jsonb,
                    NULL, NULL, NULL, :task_id
                )
                """
            ),
            {"id": outcome_id, "team_id": team_id, "task_id": task_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO evaluations (
                    id, team_id, outcome_id, conclusion, findings,
                    evaluator_kind, evaluator_identity, evaluator_revision,
                    status, idempotency_key, proposal_hash, created_by_task_id,
                    resolved_by_task_id, rejection_reason
                )
                VALUES (
                    :id, :team_id, :outcome_id, 'worked',
                    CAST(:findings AS jsonb), 'rule', 'rw1-migration-test', '1',
                    'proposed', 'rw1-legacy-fixture', :proposal_hash, :task_id,
                    NULL, NULL
                )
                """
            ),
            {
                "id": evaluation_id,
                "team_id": team_id,
                "outcome_id": outcome_id,
                "findings": json.dumps(findings),
                "proposal_hash": proposal_hash,
                "task_id": task_id,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO evidence_links (
                    id, team_id, subject_kind, subject_id, source_kind,
                    outcome_id, signal_id, snapshot_ref, snapshot_hash, stance,
                    quote_text, quote_start, quote_end, reference_key
                )
                VALUES (
                    :id, :team_id, 'evaluation', :evaluation_id, 'outcome',
                    :outcome_id, NULL, NULL, NULL, 'supports',
                    NULL, NULL, NULL, :reference_key
                )
                """
            ),
            {
                "id": link_id,
                "team_id": team_id,
                "evaluation_id": evaluation_id,
                "outcome_id": outcome_id,
                "reference_key": reference_key,
            },
        )

    return LegacyEvidence(
        team_id,
        task_id,
        outcome_id,
        evaluation_id,
        link_id,
        reference_key,
        proposal_hash,
    )


def test_0019_backfills_typed_subject_and_task_without_changing_legacy_rows(
    rw1_migration_schema: MigrationSandbox,
) -> None:
    legacy = _seed_legacy_evaluation(rw1_migration_schema)
    _run_revision(
        rw1_migration_schema.engine,
        rw1_migration_schema.schema,
        "0019_rw1_world_memory",
    )
    with rw1_migration_schema.engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT id, team_id, evaluation_id, hypothesis_id,
                       originating_task_id, source_kind, outcome_id,
                       reference_key, stance
                FROM evidence_links WHERE id = :id
                """
            ),
            {"id": legacy.link_id},
        ).mappings().one()
        assert row["id"] == legacy.link_id
        assert row["team_id"] == legacy.team_id
        assert row["evaluation_id"] == legacy.evaluation_id
        assert row["hypothesis_id"] is None
        assert row["originating_task_id"] == legacy.task_id
        assert row["source_kind"] == "outcome"
        assert row["outcome_id"] == legacy.outcome_id
        assert row["reference_key"] == legacy.reference_key
        assert row["stance"] == "supports"
        assert connection.scalar(text("SELECT count(*) FROM threads")) == 0
        assert connection.scalar(text("SELECT count(*) FROM hypotheses")) == 0
        columns = set(
            connection.scalars(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = :schema AND table_name = 'evidence_links'
                    """
                ),
                {"schema": rw1_migration_schema.schema},
            )
        )
        assert {"evaluation_id", "hypothesis_id", "originating_task_id"} <= columns
        assert "subject_id" not in columns


def test_0019_refuses_proposal_hash_mismatch_and_rolls_back_schema(
    rw1_migration_schema: MigrationSandbox,
) -> None:
    _seed_legacy_evaluation(rw1_migration_schema, valid_hash=False)
    with pytest.raises(RuntimeError, match="Evaluation proposal hash mismatch"):
        _run_revision(
            rw1_migration_schema.engine,
            rw1_migration_schema.schema,
            "0019_rw1_world_memory",
        )
    with rw1_migration_schema.engine.connect() as connection:
        revision = connection.scalar(
            text(
                f'SELECT version_num FROM "{rw1_migration_schema.schema}".alembic_version'
            )
        )
        assert revision == "0018_r7b_lifecycle_review_date"
        tables = set(
            connection.scalars(
                text(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = :schema
                    """
                ),
                {"schema": rw1_migration_schema.schema},
            )
        )
        assert "threads" not in tables
        columns = set(
            connection.scalars(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = :schema AND table_name = 'evidence_links'
                    """
                ),
                {"schema": rw1_migration_schema.schema},
            )
        )
        assert "subject_id" in columns
        assert "evaluation_id" not in columns


def test_0019_downgrade_refuses_world_memory_then_restores_legacy_shape(
    rw1_migration_schema: MigrationSandbox,
) -> None:
    legacy = _seed_legacy_evaluation(rw1_migration_schema)
    _run_revision(
        rw1_migration_schema.engine,
        rw1_migration_schema.schema,
        "0019_rw1_world_memory",
    )
    with rw1_migration_schema.engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO threads (id, team_id, domain, title)
                VALUES (:id, :team_id, 'rw1_migration_test', 'Downgrade guard')
                """
            ),
            {"id": uuid4(), "team_id": legacy.team_id},
        )
    with pytest.raises(RuntimeError, match="Cannot downgrade RW-1"):
        _run_revision(
            rw1_migration_schema.engine,
            rw1_migration_schema.schema,
            "0018_r7b_lifecycle_review_date",
            downgrade=True,
        )
    with rw1_migration_schema.engine.begin() as connection:
        connection.execute(text("DELETE FROM threads"))
    _run_revision(
        rw1_migration_schema.engine,
        rw1_migration_schema.schema,
        "0018_r7b_lifecycle_review_date",
        downgrade=True,
    )
    with rw1_migration_schema.engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT subject_kind, subject_id, reference_key
                FROM evidence_links WHERE id = :id
                """
            ),
            {"id": legacy.link_id},
        ).mappings().one()
        assert row["subject_kind"] == "evaluation"
        assert row["subject_id"] == legacy.evaluation_id
        assert row["reference_key"] == legacy.reference_key
        revision = connection.scalar(
            text(
                f'SELECT version_num FROM "{rw1_migration_schema.schema}".alembic_version'
            )
        )
        assert revision == "0018_r7b_lifecycle_review_date"
