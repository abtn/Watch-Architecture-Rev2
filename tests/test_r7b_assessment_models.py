"""ORM metadata contract for R7-B B3.2 assessment persistence."""

import sqlalchemy as sa

from core.models import (
    Event,
    KnowledgeLifecycleAssessment,
    KnowledgeRevalidationAssessment,
    LearningChange,
    LearningChangeOperatorProvenance,
)


def _constraints(table, kind):
    return {
        constraint.name: constraint
        for constraint in table.constraints
        if isinstance(constraint, kind)
    }


def test_assessment_models_expose_frozen_contract_fields():
    revalidation = KnowledgeRevalidationAssessment.__table__
    lifecycle = KnowledgeLifecycleAssessment.__table__
    shared = {
        "id",
        "team_id",
        "task_id",
        "task_attempt",
        "learning_change_id",
        "knowledge_item_id",
        "current_learning_change_id",
        "target_content_version",
        "target_content_hash",
        "target_content_hash_scheme",
        "target_state_hash",
        "proposal_hash",
        "proposed_state_hash",
        "evidence_basis_hash",
        "evidence_refs",
        "assessment_version",
        "idempotency_key",
        "request_hash",
        "request_event_id",
        "request_event_payload_hash",
        "recorded_event_id",
        "recorded_at",
        "payload_hash",
    }
    assert shared <= set(revalidation.columns.keys())
    assert shared <= set(lifecycle.columns.keys())
    assert {
        "evaluator_identity",
        "evaluator_revision",
        "freshness_disposition",
        "findings",
        "assessment_result",
    } <= set(revalidation.columns.keys())
    assert {
        "operation",
        "operator_rationale",
        "findings",
        "assessment_result",
        "variant_payload",
        "successor_knowledge_item_id",
        "successor_current_learning_change_id",
        "successor_content_version",
        "successor_content_hash",
        "successor_content_hash_scheme",
        "successor_status",
        "successor_review_after",
        "successor_state_hash",
    } <= set(lifecycle.columns.keys())


def test_required_assessment_binding_columns_are_not_nullable():
    for model in (KnowledgeRevalidationAssessment, KnowledgeLifecycleAssessment):
        table = model.__table__
        for name in (
            "team_id",
            "task_id",
            "task_attempt",
            "learning_change_id",
            "knowledge_item_id",
            "current_learning_change_id",
            "target_content_version",
            "target_content_hash",
            "target_content_hash_scheme",
            "target_state_hash",
            "proposal_hash",
            "proposed_state_hash",
            "evidence_basis_hash",
            "evidence_refs",
            "assessment_version",
            "idempotency_key",
            "request_hash",
            "request_event_id",
            "request_event_payload_hash",
            "recorded_event_id",
            "recorded_at",
            "payload_hash",
        ):
            assert table.c[name].nullable is False, (table.name, name)


def test_composite_parent_keys_exist_for_assessment_foreign_keys():
    learning_change_uniques = _constraints(
        LearningChange.__table__, sa.UniqueConstraint
    )
    assert "uq_learning_changes_id_operation_team" in learning_change_uniques
    assert "uq_learning_changes_id_target_team" in learning_change_uniques

    event_uniques = _constraints(Event.__table__, sa.UniqueConstraint)
    assert "uq_events_id_task" in event_uniques

    for model in (KnowledgeRevalidationAssessment, KnowledgeLifecycleAssessment):
        foreign_keys = _constraints(model.__table__, sa.ForeignKeyConstraint)
        assert any(
            tuple(column.name for column in fk.columns) == ("task_id", "team_id")
            for fk in foreign_keys.values()
        )
        assert any(
            tuple(column.name for column in fk.columns)
            == ("learning_change_id", "operation", "team_id")
            for fk in foreign_keys.values()
        )
        assert any(
            tuple(column.name for column in fk.columns)
            == ("learning_change_id", "knowledge_item_id", "team_id")
            for fk in foreign_keys.values()
        )
        assert any(
            tuple(column.name for column in fk.columns)
            == ("request_event_id", "task_id")
            for fk in foreign_keys.values()
        )
        assert any(
            tuple(column.name for column in fk.columns)
            == ("recorded_event_id", "task_id")
            for fk in foreign_keys.values()
        )


def test_assessment_uniqueness_and_event_separation_are_declared():
    for model in (KnowledgeRevalidationAssessment, KnowledgeLifecycleAssessment):
        uniques = _constraints(model.__table__, sa.UniqueConstraint)
        unique_column_sets = {
            tuple(column.name for column in constraint.columns)
            for constraint in uniques.values()
        }
        assert ("team_id", "learning_change_id") in unique_column_sets
        assert ("task_id",) in unique_column_sets
        assert ("task_id", "idempotency_key") in unique_column_sets
        assert ("request_event_id",) in unique_column_sets
        assert ("recorded_event_id",) in unique_column_sets
        checks = _constraints(model.__table__, sa.CheckConstraint)
        assert any(
            "request_event_id <> recorded_event_id" in str(check.sqltext)
            for check in checks.values()
        )


def test_lifecycle_variant_and_closed_vocabulary_constraints_are_declared():
    table = KnowledgeLifecycleAssessment.__table__
    checks = _constraints(table, sa.CheckConstraint)
    sql = " ".join(str(check.sqltext) for check in checks.values())
    assert "operation IN ('retire', 'supersede')" in sql
    assert "variant_payload = '{}'::jsonb" in sql
    assert "variant_payload ? 'successor_team_id'" in sql
    assert "successor_knowledge_item_id <> knowledge_item_id" in sql
    assert "successor_status IN ('active', 'needs_review', 'retired')" in sql
    assert "watch.r7b.knowledge-content.v2" in sql
    assert "successor_team_id" in sql
    assert "successor_team_id" not in table.columns


def test_revalidation_closed_vocabularies_and_payload_shapes_are_declared():
    table = KnowledgeRevalidationAssessment.__table__
    checks = _constraints(table, sa.CheckConstraint)
    sql = " ".join(str(check.sqltext) for check in checks.values())
    assert "operation = 'revalidate'" in sql
    assert "'current', 'stale', 'insufficient', 'conflicting', 'unassessable'" in sql
    assert "'supported', 'not_supported', 'indeterminate'" in sql
    assert "jsonb_typeof(evidence_refs) = 'array'" in sql
    assert "watch.r7b.knowledge-content.v2" in sql


def test_lifecycle_assessment_requires_original_operator_provenance():
    table = KnowledgeLifecycleAssessment.__table__
    foreign_keys = _constraints(table, sa.ForeignKeyConstraint)
    assert any(
        tuple(column.name for column in fk.columns) == ("learning_change_id",)
        and "learning_change_operator_provenance.learning_change_id"
        in str(next(iter(fk.elements)).target_fullname)
        for fk in foreign_keys.values()
    )
    provenance = LearningChangeOperatorProvenance.__table__
    assert {"learning_change_id", "team_id", "issuer", "subject", "recorded_at"} <= set(
        provenance.columns.keys()
    )
    assert provenance.c.learning_change_id.primary_key
    assert provenance.c.issuer.nullable is False
    assert provenance.c.subject.nullable is False


def test_historical_target_pointers_are_bound_to_their_knowledge_items():
    expected_target_pointer = (
        "current_learning_change_id",
        "knowledge_item_id",
        "team_id",
    )
    for model in (KnowledgeRevalidationAssessment, KnowledgeLifecycleAssessment):
        foreign_keys = _constraints(model.__table__, sa.ForeignKeyConstraint)
        assert any(
            tuple(column.name for column in fk.columns) == expected_target_pointer
            and tuple(element.target_fullname for element in fk.elements)
            == (
                "learning_changes.id",
                "learning_changes.target_id",
                "learning_changes.team_id",
            )
            for fk in foreign_keys.values()
        )

    lifecycle_fks = _constraints(
        KnowledgeLifecycleAssessment.__table__, sa.ForeignKeyConstraint
    )
    assert any(
        tuple(column.name for column in fk.columns)
        == (
            "successor_current_learning_change_id",
            "successor_knowledge_item_id",
            "team_id",
        )
        and tuple(element.target_fullname for element in fk.elements)
        == (
            "learning_changes.id",
            "learning_changes.target_id",
            "learning_changes.team_id",
        )
        for fk in lifecycle_fks.values()
    )
