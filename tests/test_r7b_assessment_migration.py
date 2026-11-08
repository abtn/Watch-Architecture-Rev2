"""PostgreSQL migration and immutability tests for R7-B B3.2."""

from __future__ import annotations

import hashlib
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
from sqlalchemy.exc import DBAPIError


@dataclass(frozen=True)
class AssessmentMigrationSandbox:
    engine: Engine
    schema: str


@dataclass(frozen=True)
class AssessmentRows:
    provenance_id: UUID
    revalidation_id: UUID
    lifecycle_id: UUID


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
def assessment_migration_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[AssessmentMigrationSandbox]:
    database_url = resolve_test_database_url(os.environ)
    schema = f"r7b_assessment_migration_{uuid4().hex}"
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

        _run_revision(scoped_engine, schema, "0016_team_exp_history_pins")
        yield AssessmentMigrationSandbox(scoped_engine, schema)
    finally:
        if scoped_engine is not None:
            scoped_engine.dispose()
        if schema_created:
            with admin_engine.begin() as connection:
                connection.execute(
                    text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                )
        admin_engine.dispose()


def _postgres_constraint_name(name: str) -> str:
    if len(name) <= 63:
        return name
    return f"{name[:54]}_{hashlib.md5(name.encode()).hexdigest()[-4:]}"


def _upgrade_assessment_schema(
    sandbox: AssessmentMigrationSandbox,
) -> None:
    _run_revision(
        sandbox.engine, sandbox.schema, "0017_r7b_assessments"
    )


def _seed_assessment_rows(
    sandbox: AssessmentMigrationSandbox,
) -> AssessmentRows:
    team_id = uuid4()
    policy_id = uuid4()
    proposal_task_id = uuid4()
    revalidation_task_id = uuid4()
    lifecycle_task_id = uuid4()
    item_id = uuid4()
    create_change_id = uuid4()
    revalidation_change_id = uuid4()
    lifecycle_change_id = uuid4()
    revalidation_request_event_id = uuid4()
    revalidation_recorded_event_id = uuid4()
    lifecycle_request_event_id = uuid4()
    lifecycle_recorded_event_id = uuid4()
    revalidation_id = uuid4()
    lifecycle_id = uuid4()
    now = datetime.now(timezone.utc)
    review_after = now + timedelta(days=30)
    digest = "sha256:" + ("a" * 64)
    budget = json.dumps(
        {"max_tool_calls": 0, "max_cost_usd": 0, "deadline_seconds": 60}
    )

    with sandbox.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO teams (id, domain, status) "
                "VALUES (:id, 'assessment_migration_test', 'active')"
            ),
            {"id": team_id},
        )
        connection.execute(
            text(
                "INSERT INTO team_policies (id, team_id, version, schema_version, rules) "
                "VALUES (:id, :team_id, 1, 2, CAST(:rules AS jsonb))"
            ),
            {
                "id": policy_id,
                "team_id": team_id,
                "rules": json.dumps({}),
            },
        )
        for task_id, task_type in (
            (proposal_task_id, "proposal_test"),
            (revalidation_task_id, "assess_knowledge_revalidation"),
            (lifecycle_task_id, "assess_knowledge_lifecycle"),
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
                        :id, :team_id, :task_type, 'running', 1, 1,
                        '[]'::jsonb, CAST(:budget AS jsonb), :created_at, 3
                    )
                    """
                ),
                {
                    "id": task_id,
                    "team_id": team_id,
                    "task_type": task_type,
                    "budget": budget,
                    "created_at": now,
                },
            )

        committed_snapshot = {
            "id": str(item_id),
            "team_id": str(team_id),
            "kind": "practice",
            "title": "Assessment migration fixture",
            "statement": "A valid historical KnowledgeItem fixture.",
            "body": "The fixture exists to exercise immutable assessment rows.",
            "applicability": {"domain": "testing"},
            "preconditions": [],
            "assumptions": [],
            "limitations": [],
            "non_applicability": [],
            "failure_modes": [],
            "known_counterexamples": [],
            "missing_information": [],
            "uncertainty": [],
            "confidence": "0.900",
            "status": "active",
            "version": 1,
            "last_validated_at": None,
            "review_after": review_after.isoformat(),
            "origin_learning_change_id": str(create_change_id),
        }
        connection.execute(
            text(
                """
                INSERT INTO learning_changes (
                    id, team_id, target_kind, target_id, operation,
                    proposed_state, previous_state, committed_state,
                    evidence_basis, evidence_basis_hash, status,
                    idempotency_key, proposed_by_task_id, committed_by_task_id,
                    operator_id, decision_reason, created_at, committed_at
                )
                VALUES (
                    :id, :team_id, 'knowledge_item', NULL, 'create',
                    CAST(:snapshot AS jsonb), NULL, CAST(:snapshot AS jsonb),
                    '[]'::jsonb, :evidence_hash, 'accepted',
                    'assessment-migration-create', :proposal_task_id,
                    :proposal_task_id, 'operator:migration-test', NULL, :now, :now
                )
                """
            ),
            {
                "id": create_change_id,
                "team_id": team_id,
                "snapshot": json.dumps(committed_snapshot),
                "evidence_hash": digest,
                "proposal_task_id": proposal_task_id,
                "now": now,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO knowledge_items (
                    id, team_id, kind, title, statement, body, applicability,
                    preconditions, assumptions, limitations, non_applicability,
                    failure_modes, known_counterexamples, missing_information,
                    uncertainty, confidence, status, version, last_validated_at,
                    review_after, origin_learning_change_id,
                    current_learning_change_id, supersedes_item_id,
                    superseded_by_id, created_at, updated_at
                )
                VALUES (
                    :id, :team_id, 'practice', 'Assessment migration fixture',
                    'A valid historical KnowledgeItem fixture.',
                    'The fixture exists to exercise immutable assessment rows.',
                    '{"domain":"testing"}'::jsonb, '[]'::jsonb, '[]'::jsonb,
                    '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                    '[]'::jsonb, '[]'::jsonb, 0.900, 'active', 1, NULL,
                    :review_after, :create_change_id, :create_change_id,
                    NULL, NULL, :now, :now
                )
                """
            ),
            {
                "id": item_id,
                "team_id": team_id,
                "review_after": review_after,
                "create_change_id": create_change_id,
                "now": now,
            },
        )

        for change_id, operation, key in (
            (revalidation_change_id, "revalidate", "assessment-migration-revalidate"),
            (lifecycle_change_id, "retire", "assessment-migration-retire"),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO learning_changes (
                        id, team_id, target_kind, target_id, operation,
                        proposed_state, previous_state, committed_state,
                        evidence_basis, evidence_basis_hash, status,
                        idempotency_key, proposed_by_task_id, committed_by_task_id,
                        operator_id, decision_reason, created_at, committed_at
                    )
                    VALUES (
                        :id, :team_id, 'knowledge_item', :item_id, :operation,
                        '{"rationale":"operator supplied"}'::jsonb, NULL, NULL,
                        '[]'::jsonb, :evidence_hash, 'proposed',
                        :idempotency_key, :proposal_task_id, NULL,
                        NULL, NULL, :now, NULL
                    )
                    """
                ),
                {
                    "id": change_id,
                    "team_id": team_id,
                    "item_id": item_id,
                    "operation": operation,
                    "evidence_hash": digest,
                    "idempotency_key": key,
                    "proposal_task_id": proposal_task_id,
                    "now": now,
                },
            )

        connection.execute(
            text(
                """
                INSERT INTO learning_change_operator_provenance (
                    learning_change_id, team_id, issuer, subject, recorded_at
                )
                VALUES (
                    :learning_change_id, :team_id,
                    'https://host.example.test', 'operator-123', :now
                )
                """
            ),
            {
                "learning_change_id": lifecycle_change_id,
                "team_id": team_id,
                "now": now,
            },
        )

        for task_id, request_id, recorded_id in (
            (
                revalidation_task_id,
                revalidation_request_event_id,
                revalidation_recorded_event_id,
            ),
            (
                lifecycle_task_id,
                lifecycle_request_event_id,
                lifecycle_recorded_event_id,
            ),
        ):
            for event_id, event_type in (
                (request_id, "assessment.requested"),
                (recorded_id, "assessment.recorded"),
            ):
                connection.execute(
                    text(
                        """
                        INSERT INTO events (id, task_id, type, payload, created_at)
                        VALUES (:id, :task_id, :type, '{}'::jsonb, :created_at)
                        """
                    ),
                    {
                        "id": event_id,
                        "task_id": task_id,
                        "type": event_type,
                        "created_at": now,
                    },
                )

        connection.execute(
            text(
                """
                INSERT INTO knowledge_revalidation_assessments (
                    id, team_id, task_id, task_attempt, learning_change_id,
                    operation, knowledge_item_id, current_learning_change_id,
                    target_content_version, target_content_hash,
                    target_content_hash_scheme, target_state_hash, proposal_hash,
                    proposed_state_hash, evidence_basis_hash, evidence_refs,
                    assessment_version, evaluator_identity, evaluator_revision,
                    freshness_disposition, findings, assessment_result,
                    idempotency_key, request_hash, request_event_id,
                    request_event_payload_hash, recorded_event_id, recorded_at,
                    payload_hash
                )
                VALUES (
                    :id, :team_id, :task_id, 1, :learning_change_id,
                    'revalidate', :item_id, :current_change_id,
                    1, :digest, 'watch.r7b.knowledge-content.v2', :digest,
                    :digest, :digest, :digest, '[]'::jsonb, 1,
                    'test-evaluator', 'test-revision', 'current', '[]'::jsonb,
                    'supported', 'revalidation-idempotency', :digest,
                    :request_event_id, :digest, :recorded_event_id, :now, :digest
                )
                """
            ),
            {
                "id": revalidation_id,
                "team_id": team_id,
                "task_id": revalidation_task_id,
                "learning_change_id": revalidation_change_id,
                "item_id": item_id,
                "current_change_id": create_change_id,
                "digest": digest,
                "request_event_id": revalidation_request_event_id,
                "recorded_event_id": revalidation_recorded_event_id,
                "now": now,
            },
        )

        connection.execute(
            text(
                """
                INSERT INTO knowledge_lifecycle_assessments (
                    id, team_id, task_id, task_attempt, learning_change_id,
                    operation, knowledge_item_id, current_learning_change_id,
                    target_content_version, target_content_hash,
                    target_content_hash_scheme, target_state_hash, proposal_hash,
                    proposed_state_hash, evidence_basis_hash, evidence_refs,
                    assessment_version, operator_rationale, findings,
                    assessment_result, variant_payload,
                    successor_knowledge_item_id,
                    successor_current_learning_change_id, successor_content_version,
                    successor_content_hash, successor_content_hash_scheme,
                    successor_status, successor_review_after, successor_state_hash,
                    idempotency_key, request_hash, request_event_id,
                    request_event_payload_hash, recorded_event_id, recorded_at,
                    payload_hash
                )
                VALUES (
                    :id, :team_id, :task_id, 1, :learning_change_id,
                    'retire', :item_id, :current_change_id,
                    1, :digest, 'watch.r7b.knowledge-content.v2', :digest,
                    :digest, :digest, :digest, '[]'::jsonb, 1,
                    '{"source":"operator"}'::jsonb, '[]'::jsonb, 'eligible',
                    '{}'::jsonb, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                    'lifecycle-idempotency', :digest, :request_event_id, :digest,
                    :recorded_event_id, :now, :digest
                )
                """
            ),
            {
                "id": lifecycle_id,
                "team_id": team_id,
                "task_id": lifecycle_task_id,
                "learning_change_id": lifecycle_change_id,
                "item_id": item_id,
                "current_change_id": create_change_id,
                "digest": digest,
                "request_event_id": lifecycle_request_event_id,
                "recorded_event_id": lifecycle_recorded_event_id,
                "now": now,
            },
        )

    return AssessmentRows(
        provenance_id=lifecycle_change_id,
        revalidation_id=revalidation_id,
        lifecycle_id=lifecycle_id,
    )


def test_0017_creates_contract_constraints_and_immutability_triggers(
    assessment_migration_schema: AssessmentMigrationSandbox,
) -> None:
    sandbox = assessment_migration_schema
    _upgrade_assessment_schema(sandbox)

    expected_tables = {
        "learning_change_operator_provenance",
        "knowledge_revalidation_assessments",
        "knowledge_lifecycle_assessments",
    }
    expected_constraints = {
        "fk_learning_change_operator_provenance_learning_change_team",
        "ck_learning_change_operator_provenance_identity",
        "fk_knowledge_revalidation_assessments_task_team",
        "fk_knowledge_revalidation_assessments_learning_change_operation_team",
        "fk_knowledge_revalidation_assessments_learning_change_target_team",
        "fk_knowledge_revalidation_assessments_knowledge_item_team",
        "fk_knowledge_revalidation_assessments_current_change_team",
        "fk_knowledge_revalidation_assessments_request_event_task",
        "fk_knowledge_revalidation_assessments_recorded_event_task",
        "ck_knowledge_revalidation_assessments_operation",
        "ck_knowledge_revalidation_assessments_hashes",
        "ck_knowledge_revalidation_assessments_payload_shape",
        "fk_knowledge_lifecycle_assessments_task_team",
        "fk_knowledge_lifecycle_assessments_learning_change_operation_team",
        "fk_knowledge_lifecycle_assessments_learning_change_target_team",
        "fk_knowledge_lifecycle_assessments_knowledge_item_team",
        "fk_knowledge_lifecycle_assessments_current_change_team",
        "fk_knowledge_lifecycle_assessments_successor_item_team",
        "fk_knowledge_lifecycle_assessments_successor_current_change_team",
        "fk_knowledge_lifecycle_assessments_operator_provenance",
        "fk_knowledge_lifecycle_assessments_request_event_task",
        "fk_knowledge_lifecycle_assessments_recorded_event_task",
        "ck_knowledge_lifecycle_assessments_operation",
        "ck_knowledge_lifecycle_assessments_variant_shape",
        "ck_knowledge_lifecycle_assessments_no_self_supersession",
    }
    expected_constraints = {
        _postgres_constraint_name(name) for name in expected_constraints
    }
    expected_triggers = {
        "trg_operator_provenance_immutable_row",
        "trg_operator_provenance_immutable_truncate",
        "trg_revalidation_assessment_immutable_row",
        "trg_revalidation_assessment_immutable_truncate",
        "trg_lifecycle_assessment_immutable_row",
        "trg_lifecycle_assessment_immutable_truncate",
    }

    with sandbox.engine.connect() as connection:
        revision = connection.scalar(
            text(
                f'SELECT version_num FROM "{sandbox.schema}".alembic_version'
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
                {"schema": sandbox.schema},
            )
        )
        constraints = set(
            connection.scalars(
                text(
                    """
                    SELECT conname
                    FROM pg_constraint
                    WHERE connamespace = to_regnamespace(:schema)
                    """
                ),
                {"schema": sandbox.schema},
            )
        )
        triggers = set(
            connection.scalars(
                text(
                    """
                    SELECT tgname
                    FROM pg_trigger
                    WHERE tgrelid IN (
                        SELECT oid FROM pg_class
                        WHERE relnamespace = to_regnamespace(:schema)
                    )
                      AND NOT tgisinternal
                    """
                ),
                {"schema": sandbox.schema},
            )
        )

    assert revision == "0017_r7b_assessments"
    assert expected_tables <= tables
    assert expected_constraints <= constraints
    assert expected_triggers <= triggers


def test_0017_row_and_truncate_mutations_are_rejected(
    assessment_migration_schema: AssessmentMigrationSandbox,
) -> None:
    sandbox = assessment_migration_schema
    _upgrade_assessment_schema(sandbox)
    rows = _seed_assessment_rows(sandbox)

    row_targets = (
        (
            "learning_change_operator_provenance",
            "learning_change_id",
            rows.provenance_id,
        ),
        (
            "knowledge_revalidation_assessments",
            "id",
            rows.revalidation_id,
        ),
        (
            "knowledge_lifecycle_assessments",
            "id",
            rows.lifecycle_id,
        ),
    )
    for table, key_column, key_value in row_targets:
        with pytest.raises(DBAPIError, match="immutable"):
            with sandbox.engine.begin() as connection:
                connection.execute(
                    text(
                        f"UPDATE {table} SET recorded_at = recorded_at "
                        f"WHERE {key_column} = :key"
                    ),
                    {"key": key_value},
                )
        with pytest.raises(DBAPIError, match="immutable"):
            with sandbox.engine.begin() as connection:
                connection.execute(
                    text(f"DELETE FROM {table} WHERE {key_column} = :key"),
                    {"key": key_value},
                )
        with pytest.raises(DBAPIError, match="immutable"):
            with sandbox.engine.begin() as connection:
                connection.execute(text(f"TRUNCATE TABLE {table}"))


def test_0017_downgrade_refuses_to_drop_persisted_assessment_history(
    assessment_migration_schema: AssessmentMigrationSandbox,
) -> None:
    sandbox = assessment_migration_schema
    _upgrade_assessment_schema(sandbox)
    _seed_assessment_rows(sandbox)

    with pytest.raises(RuntimeError, match="immutable provenance or assessment"):
        _run_revision(
            sandbox.engine,
            sandbox.schema,
            "0016_team_exp_history_pins",
            downgrade=True,
        )

    with sandbox.engine.connect() as connection:
        revision = connection.scalar(
            text(
                f'SELECT version_num FROM "{sandbox.schema}".alembic_version'
            )
        )
        table_exists = connection.scalar(
            text(
                """
                SELECT to_regclass(:qualified_name) IS NOT NULL
                """
            ),
            {
                "qualified_name": (
                    f"{sandbox.schema}.knowledge_revalidation_assessments"
                )
            },
        )

    assert revision == "0017_r7b_assessments"
    assert table_exists is True


def test_0017_empty_downgrade_removes_assessment_schema_objects(
    assessment_migration_schema: AssessmentMigrationSandbox,
) -> None:
    sandbox = assessment_migration_schema
    _upgrade_assessment_schema(sandbox)
    _run_revision(
        sandbox.engine,
        sandbox.schema,
        "0016_team_exp_history_pins",
        downgrade=True,
    )

    with sandbox.engine.connect() as connection:
        revision = connection.scalar(
            text(
                f'SELECT version_num FROM "{sandbox.schema}".alembic_version'
            )
        )
        remaining_tables = set(
            connection.scalars(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = :schema
                    """
                ),
                {"schema": sandbox.schema},
            )
        )
        remaining_triggers = set(
            connection.scalars(
                text(
                    """
                    SELECT tgname
                    FROM pg_trigger
                    WHERE tgrelid IN (
                        SELECT oid FROM pg_class
                        WHERE relnamespace = to_regnamespace(:schema)
                    )
                      AND NOT tgisinternal
                    """
                ),
                {"schema": sandbox.schema},
            )
        )

    assert revision == "0016_team_exp_history_pins"
    assert {
        "learning_change_operator_provenance",
        "knowledge_revalidation_assessments",
        "knowledge_lifecycle_assessments",
    }.isdisjoint(remaining_tables)
    assert not {
        "trg_operator_provenance_immutable_row",
        "trg_operator_provenance_immutable_truncate",
        "trg_revalidation_assessment_immutable_row",
        "trg_revalidation_assessment_immutable_truncate",
        "trg_lifecycle_assessment_immutable_row",
        "trg_lifecycle_assessment_immutable_truncate",
    } & remaining_triggers
