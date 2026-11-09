"""R7-B B3.4 deterministic lifecycle assessment contract tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.knowledge_lifecycle import (
    ALLOWED_WRITES,
    ASSESSMENT_HASH_DOMAIN,
    PROPOSED_STATE_HASH_DOMAIN,
    KnowledgeLifecycleAssessmentError,
    OperatorRationale,
    _domain_hash,
    _normalize_json,
    _validate_proposed_state,
    derive_lifecycle_findings,
    validate_operator_rationale,
)


def _rationale() -> dict[str, object]:
    return {
        "schema_version": 1,
        "summary": "The existing procedure is no longer appropriate for this context.",
        "reasons": [
            {
                "category": "evidence_no_longer_reliable",
                "statement": "The primary supporting source has been superseded.",
            },
            {
                "category": "applicability_changed",
                "statement": "The original applicability conditions no longer hold.",
            },
        ],
    }


def _change(operation: str, proposed_state: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        operation=operation,
        team_id=uuid4(),
        evidence_basis_hash="sha256:" + "b" * 64,
        proposed_state=proposed_state,
    )


def test_operator_rationale_preserves_original_structure_and_order():
    raw = _rationale()

    validated = validate_operator_rationale(raw)

    assert validated == raw
    assert OperatorRationale.model_validate(raw).model_dump(mode="json") == raw
    assert [item["category"] for item in validated["reasons"]] == [
        "evidence_no_longer_reliable",
        "applicability_changed",
    ]


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {
            "schema_version": 2,
            "summary": "A reason",
            "reasons": [{"category": "x", "statement": "y"}],
        },
        {
            "schema_version": 1,
            "summary": " ",
            "reasons": [{"category": "x", "statement": "y"}],
        },
        {"schema_version": 1, "summary": "A reason", "reasons": []},
        {
            "schema_version": 1,
            "summary": "A reason",
            "reasons": [{"category": "x", "statement": "y", "model_score": 0.9}],
        },
        {
            "schema_version": 1,
            "summary": "A reason",
            "reasons": [{"category": " ", "statement": "y"}],
        },
    ],
)
def test_operator_rationale_rejects_malformed_or_untrusted_fields(invalid):
    with pytest.raises(KnowledgeLifecycleAssessmentError):
        validate_operator_rationale(invalid)


def test_retire_proposal_requires_exact_rationale_and_no_successor_fields():
    team_id = uuid4()
    proposal = {
        "proposal_hash": "sha256:" + "a" * 64,
        "evidence_basis_hash": "sha256:" + "b" * 64,
        "operator_rationale": _rationale(),
    }
    change = SimpleNamespace(
        operation="retire",
        team_id=team_id,
        evidence_basis_hash="sha256:" + "b" * 64,
        proposed_state=proposal,
    )

    proposal_hash, evidence_hash, proposed_hash, rationale, successor_id = (
        _validate_proposed_state(change)
    )

    assert proposal_hash == "sha256:" + "a" * 64
    assert evidence_hash == change.evidence_basis_hash
    assert proposed_hash.startswith("sha256:")
    assert rationale == _rationale()
    assert successor_id is None

    with pytest.raises(
        KnowledgeLifecycleAssessmentError,
        match="knowledge_lifecycle_proposed_state_shape_invalid",
    ):
        _validate_proposed_state(
            SimpleNamespace(
                **{
                    **change.__dict__,
                    "proposed_state": {
                        **proposal,
                        "successor_knowledge_item_id": str(uuid4()),
                    },
                }
            )
        )


def test_supersede_proposal_requires_same_team_successor_identity():
    team_id = uuid4()
    successor_id = uuid4()
    proposal = {
        "proposal_hash": "sha256:" + "a" * 64,
        "evidence_basis_hash": "sha256:" + "b" * 64,
        "operator_rationale": _rationale(),
        "successor_knowledge_item_id": str(successor_id),
    }
    change = SimpleNamespace(
        operation="supersede",
        team_id=team_id,
        evidence_basis_hash="sha256:" + "b" * 64,
        proposed_state=proposal,
    )

    _, _, _, rationale, parsed_successor_id = _validate_proposed_state(change)

    assert rationale == _rationale()
    assert parsed_successor_id == successor_id

    missing_successor = {
        key: value
        for key, value in proposal.items()
        if key != "successor_knowledge_item_id"
    }
    with pytest.raises(
        KnowledgeLifecycleAssessmentError,
        match="knowledge_lifecycle_proposed_state_shape_invalid",
    ):
        _validate_proposed_state(
            SimpleNamespace(
                operation="supersede",
                team_id=team_id,
                evidence_basis_hash="sha256:" + "b" * 64,
                proposed_state=missing_successor,
            )
        )


def test_wrong_operation_and_mismatched_evidence_hash_are_rejected():
    proposal = {
        "proposal_hash": "sha256:" + "a" * 64,
        "evidence_basis_hash": "sha256:" + "b" * 64,
        "operator_rationale": _rationale(),
    }
    with pytest.raises(
        KnowledgeLifecycleAssessmentError,
        match="knowledge_lifecycle_proposal_operation_invalid",
    ):
        _validate_proposed_state(
            SimpleNamespace(
                operation="revalidate",
                team_id=uuid4(),
                evidence_basis_hash="sha256:" + "b" * 64,
                proposed_state=proposal,
            )
        )
    with pytest.raises(
        KnowledgeLifecycleAssessmentError,
        match="knowledge_lifecycle_proposed_evidence_hash_mismatch",
    ):
        _validate_proposed_state(
            SimpleNamespace(
                operation="retire",
                team_id=uuid4(),
                evidence_basis_hash="sha256:" + "c" * 64,
                proposed_state=proposal,
            )
        )


def test_retire_findings_are_deterministic_and_eligible():
    recorded_at = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    target_state = {
        "status": "active",
        "superseded_by_id": None,
    }

    findings, result = derive_lifecycle_findings(
        "retire",
        target_state,
        None,
        recorded_at,
    )

    assert result == "eligible"
    assert [item["code"] for item in findings] == [
        "proposal_operation_valid",
        "team_ownership_valid",
        "predecessor_binding_valid",
        "operator_rationale_valid",
        "evidence_reference_valid",
        "retire_variant_shape_valid",
    ]
    assert all(item["outcome"] == "passed" for item in findings)


@pytest.mark.parametrize(
    ("status", "review_after", "expected_failed_codes"),
    [
        ("needs_review", "2026-11-10T12:00:00.000000Z", {"successor_status_eligible"}),
        ("active", None, {"successor_review_after_eligible"}),
        ("active", "2026-11-09T12:00:00.000000Z", {"successor_review_after_eligible"}),
        ("active", "2026-11-09T11:59:59.000000Z", {"successor_review_after_eligible"}),
        (
            "retired",
            None,
            {"successor_status_eligible", "successor_review_after_eligible"},
        ),
    ],
)
def test_supersede_ineligible_when_successor_status_or_review_date_blocks_d7(
    status, review_after, expected_failed_codes
):
    recorded_at = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    successor = {
        "successor_knowledge_item_id": str(uuid4()),
        "successor_team_id": str(uuid4()),
        "successor_current_learning_change_id": str(uuid4()),
        "successor_content_version": 1,
        "successor_content_hash": "sha256:" + "a" * 64,
        "successor_content_hash_scheme": "watch.r7b.knowledge-content.v2",
        "successor_status": status,
        "successor_review_after": review_after,
        "successor_state_hash": "sha256:" + "c" * 64,
    }

    findings, result = derive_lifecycle_findings(
        "supersede",
        {"status": "active", "superseded_by_id": None},
        successor,
        recorded_at,
    )

    failed_codes = {
        item["code"] for item in findings if item["outcome"] == "failed"
    }
    assert result == "ineligible"
    assert failed_codes == expected_failed_codes


def test_supersede_eligible_only_with_active_successor_and_future_review_date():
    recorded_at = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    successor = {
        "successor_knowledge_item_id": str(uuid4()),
        "successor_team_id": str(uuid4()),
        "successor_current_learning_change_id": str(uuid4()),
        "successor_content_version": 2,
        "successor_content_hash": "sha256:" + "a" * 64,
        "successor_content_hash_scheme": "watch.r7b.knowledge-content.v2",
        "successor_status": "active",
        "successor_review_after": "2026-11-10T12:00:00.000000Z",
        "successor_state_hash": "sha256:" + "c" * 64,
    }

    findings, result = derive_lifecycle_findings(
        "supersede",
        {"status": "needs_review", "superseded_by_id": None},
        successor,
        recorded_at,
    )

    assert result == "eligible"
    assert all(item["outcome"] == "passed" for item in findings)


def test_assessment_and_proposed_state_hash_domains_are_distinct():
    payload = {
        "proposal_hash": "sha256:" + "a" * 64,
        "proposed_state_hash": "sha256:" + "b" * 64,
        "operator_rationale": _rationale(),
        "optional": None,
    }

    proposed = _domain_hash(PROPOSED_STATE_HASH_DOMAIN, payload)
    assessment = _domain_hash(ASSESSMENT_HASH_DOMAIN, payload)
    changed = _domain_hash(
        PROPOSED_STATE_HASH_DOMAIN,
        {**payload, "optional": "not-null"},
    )

    assert proposed != assessment
    assert proposed != changed


def test_normalization_preserves_array_order_and_exact_decimal_and_utc_values():
    instant = datetime(2026, 11, 9, 12, 30, 15, 123456, tzinfo=timezone.utc)

    normalized = _normalize_json(
        {
            "id": uuid4(),
            "amount": Decimal("1.2300"),
            "recorded_at": instant,
            "reasons": ["first", "second"],
        }
    )

    assert normalized["amount"] == "1.2300"
    assert normalized["recorded_at"] == "2026-11-09T12:30:15.123456Z"
    assert normalized["reasons"] == ["first", "second"]


@pytest.mark.parametrize("invalid", [float("inf"), float("nan"), Decimal("NaN")])
def test_normalization_rejects_nonfinite_numbers(invalid):
    with pytest.raises(KnowledgeLifecycleAssessmentError):
        _normalize_json(invalid)


def test_assessment_task_has_only_its_own_typed_write_scope():
    assert ALLOWED_WRITES == ["KnowledgeLifecycleAssessment"]
    assert "KnowledgeItem" not in ALLOWED_WRITES
    assert "LearningChange" not in ALLOWED_WRITES
