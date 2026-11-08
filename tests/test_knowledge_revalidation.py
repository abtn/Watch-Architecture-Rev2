"""R7-B B3.3 revalidation assessment contract tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.knowledge_revalidation import (
    KnowledgeRevalidationAssessmentDraft,
    KnowledgeRevalidationAssessmentError,
    KnowledgeRevalidationFinding,
    _domain_hash,
    _normalize_json,
    _target_state_from_proposal,
    derive_assessment_result,
    derive_freshness_disposition,
    validate_revalidation_draft,
)
from core.learning_history import encode_state_snapshot
from core.task_runtime import TaskNotFinalizable, TaskRuntime, TerminalObservation


def _finding(
    code: str,
    references: list[str],
) -> KnowledgeRevalidationFinding:
    return KnowledgeRevalidationFinding(
        code=code,
        summary=f"Finding: {code}",
        evidence_refs=references,
    )


def _draft(
    disposition: str,
    findings: list[KnowledgeRevalidationFinding],
) -> KnowledgeRevalidationAssessmentDraft:
    return KnowledgeRevalidationAssessmentDraft(
        freshness_disposition=disposition,
        findings=findings,
    )


def test_freshness_disposition_requires_current_support_for_supported_result():
    findings = [_finding("supports_revalidation", ["evaluation:one"])]
    disposition = derive_freshness_disposition(findings)

    assert disposition == "current"
    assert derive_assessment_result(disposition, findings) == "supported"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("temporally_stale", "stale"),
        ("new_observation_required", "stale"),
        ("insufficient_coverage", "insufficient"),
        ("unresolved_conflict", "conflicting"),
        ("freshness_unassessable", "unassessable"),
    ],
)
def test_noncurrent_freshness_never_supports_revalidation(code, expected):
    findings = [_finding(code, ["evaluation:one"])]

    disposition = derive_freshness_disposition(findings)

    assert disposition == expected
    assert derive_assessment_result(disposition, findings) == "indeterminate"


def test_current_substantive_contradiction_is_not_supported():
    findings = [_finding("contradicts_revalidation", ["evaluation:one"])]

    disposition = derive_freshness_disposition(findings)

    assert disposition == "current"
    assert derive_assessment_result(disposition, findings) == "not_supported"


def test_support_and_contradiction_derive_conflicting_indeterminate_result():
    findings = [
        _finding("supports_revalidation", ["evaluation:support"]),
        _finding("contradicts_revalidation", ["evaluation:challenge"]),
    ]

    disposition = derive_freshness_disposition(findings)

    assert disposition == "conflicting"
    assert derive_assessment_result(disposition, findings) == "indeterminate"


def test_draft_must_use_only_rebuilt_references_and_cover_evidence_links():
    pack = SimpleNamespace(
        reference_ids=frozenset({"evaluation:one", "evidence_link:one"}),
        evidence_link_reference_ids=frozenset({"evidence_link:one"}),
        contrary_reference_ids=frozenset(),
    )
    draft = _draft(
        "current",
        [
            _finding(
                "supports_revalidation",
                ["evaluation:one", "evidence_link:one"],
            )
        ],
    )

    findings, disposition, result = validate_revalidation_draft(draft, pack)

    assert disposition == "current"
    assert result == "supported"
    assert findings[0]["evidence_refs"] == [
        "evaluation:one",
        "evidence_link:one",
    ]


def test_draft_rejects_evaluator_invented_reference():
    pack = SimpleNamespace(
        reference_ids=frozenset({"evaluation:one"}),
        evidence_link_reference_ids=frozenset(),
        contrary_reference_ids=frozenset(),
    )
    draft = _draft(
        "current",
        [_finding("supports_revalidation", ["evaluation:not-in-pack"])],
    )

    with pytest.raises(
        KnowledgeRevalidationAssessmentError,
        match="knowledge_revalidation_finding_reference_not_in_basis",
    ):
        validate_revalidation_draft(draft, pack)


def test_draft_must_account_for_all_canonical_evidence_links():
    pack = SimpleNamespace(
        reference_ids=frozenset({"evaluation:one", "evidence_link:one"}),
        evidence_link_reference_ids=frozenset({"evidence_link:one"}),
        contrary_reference_ids=frozenset(),
    )
    draft = _draft(
        "current",
        [_finding("supports_revalidation", ["evaluation:one"])],
    )

    with pytest.raises(
        KnowledgeRevalidationAssessmentError,
        match="knowledge_revalidation_evidence_link_omitted",
    ):
        validate_revalidation_draft(draft, pack)


def test_draft_must_classify_canonical_contrary_evidence():
    pack = SimpleNamespace(
        reference_ids=frozenset({"evaluation:one", "evidence_link:challenge"}),
        evidence_link_reference_ids=frozenset({"evidence_link:challenge"}),
        contrary_reference_ids=frozenset({"evidence_link:challenge"}),
    )
    draft = _draft(
        "current",
        [
            _finding(
                "supports_revalidation",
                ["evaluation:one", "evidence_link:challenge"],
            )
        ],
    )

    with pytest.raises(
        KnowledgeRevalidationAssessmentError,
        match="knowledge_revalidation_contrary_evidence_omitted",
    ):
        validate_revalidation_draft(draft, pack)


def test_application_rejects_evaluator_disposition_that_disagrees_with_findings():
    pack = SimpleNamespace(
        reference_ids=frozenset({"evaluation:one"}),
        evidence_link_reference_ids=frozenset(),
        contrary_reference_ids=frozenset(),
    )
    draft = _draft(
        "current",
        [_finding("temporally_stale", ["evaluation:one"])],
    )

    with pytest.raises(
        KnowledgeRevalidationAssessmentError,
        match="knowledge_revalidation_freshness_disposition_mismatch",
    ):
        validate_revalidation_draft(draft, pack)


def test_finding_rejects_duplicate_or_empty_evidence_references():
    with pytest.raises(ValidationError):
        KnowledgeRevalidationFinding(
            code="supports_revalidation",
            summary="A finding",
            evidence_refs=["evaluation:one", "evaluation:one"],
        )
    with pytest.raises(ValidationError):
        KnowledgeRevalidationFinding(
            code="supports_revalidation",
            summary="A finding",
            evidence_refs=[" "],
        )


def test_finding_rejects_unrecognized_fields_and_codes():
    with pytest.raises(ValidationError):
        KnowledgeRevalidationFinding.model_validate(
            {
                "code": "invented",
                "summary": "A finding",
                "evidence_refs": ["evaluation:one"],
                "target_id": str(uuid4()),
            }
        )


def test_normalization_preserves_order_and_uses_fixed_point_decimal_and_utc():
    instant = datetime(2026, 11, 8, 12, 30, 15, 123456, tzinfo=timezone.utc)
    normalized = _normalize_json(
        {
            "uuid": uuid4(),
            "decimal": Decimal("1.2300"),
            "timestamp": instant,
            "sequence": ["first", "second"],
        }
    )

    assert normalized["decimal"] == "1.2300"
    assert normalized["timestamp"] == "2026-11-08T12:30:15.123456Z"
    assert normalized["sequence"] == ["first", "second"]
    assert normalized["uuid"]


def test_normalization_rejects_naive_timestamps_and_nonfinite_numbers():
    with pytest.raises(
        KnowledgeRevalidationAssessmentError,
        match="knowledge_revalidation_timestamp_not_aware",
    ):
        _normalize_json(datetime(2026, 11, 8, 12, 0))
    with pytest.raises(
        KnowledgeRevalidationAssessmentError,
        match="knowledge_revalidation_number_not_finite",
    ):
        _normalize_json(float("inf"))
    with pytest.raises(
        KnowledgeRevalidationAssessmentError,
        match="knowledge_revalidation_decimal_not_finite",
    ):
        _normalize_json(Decimal("NaN"))


def test_hash_domains_are_distinct_and_include_the_complete_payload():
    payload = {
        "proposal_hash": "sha256:" + "1" * 64,
        "evidence_basis_hash": "sha256:" + "2" * 64,
        "optional": None,
    }

    first = _domain_hash(
        "watch.r7b.learning-change-proposed-state.v1", payload
    )
    second = _domain_hash(
        "watch.r7b.knowledge-revalidation-assessment.v1", payload
    )
    changed = _domain_hash(
        "watch.r7b.learning-change-proposed-state.v1",
        {**payload, "optional": "omitted-is-not-null"},
    )

    assert first != second
    assert first != changed


def test_target_binding_uses_the_historical_team_current_pointer():
    team_id = uuid4()
    item_id = uuid4()
    create_change_id = uuid4()
    proposed_change_id = uuid4()
    state = {
        "id": str(item_id),
        "team_id": str(team_id),
        "kind": "practice",
        "title": "A stable claim",
        "statement": "A stable statement.",
        "body": "A stable body.",
        "applicability": {"domain": "science"},
        "preconditions": ["source is available"],
        "assumptions": [],
        "limitations": [],
        "non_applicability": [],
        "failure_modes": [],
        "known_counterexamples": [],
        "missing_information": [],
        "uncertainty": [],
        "confidence": "0.800",
        "status": "active",
        "version": 1,
        "last_validated_at": None,
        "review_after": None,
        "origin_learning_change_id": str(create_change_id),
        "current_learning_change_id": str(create_change_id),
        "supersedes_item_id": None,
        "superseded_by_id": None,
    }
    snapshot = encode_state_snapshot(state)
    change = SimpleNamespace(
        id=proposed_change_id,
        team_id=team_id,
        target_id=item_id,
        previous_state=snapshot,
    )
    target = SimpleNamespace(id=item_id, team_id=team_id)

    decoded, target_hash, content_hash = _target_state_from_proposal(
        change, target, require_current=False
    )

    assert decoded == state
    assert target_hash == snapshot["snapshot_hash"]
    assert content_hash.startswith("sha256:")


def test_target_binding_rejects_wrong_target_and_noncanonical_pointer():
    team_id = uuid4()
    item_id = uuid4()
    create_change_id = uuid4()
    state = {
        "id": str(item_id),
        "team_id": str(team_id),
        "kind": "practice",
        "title": "A stable claim",
        "statement": "A stable statement.",
        "body": "A stable body.",
        "applicability": {},
        "preconditions": [],
        "assumptions": [],
        "limitations": [],
        "non_applicability": [],
        "failure_modes": [],
        "known_counterexamples": [],
        "missing_information": [],
        "uncertainty": [],
        "confidence": "0.800",
        "status": "active",
        "version": 1,
        "last_validated_at": None,
        "review_after": None,
        "origin_learning_change_id": str(create_change_id),
        "current_learning_change_id": str(create_change_id),
        "supersedes_item_id": None,
        "superseded_by_id": None,
    }
    snapshot = encode_state_snapshot(state)
    change = SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        target_id=uuid4(),
        previous_state=snapshot,
    )

    with pytest.raises(
        KnowledgeRevalidationAssessmentError,
        match="knowledge_revalidation_target_identity_mismatch",
    ):
        _target_state_from_proposal(
            change,
            SimpleNamespace(id=item_id, team_id=team_id),
            require_current=False,
        )

    state["current_learning_change_id"] = "NOT-A-CANONICAL-UUID"
    invalid = SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        target_id=item_id,
        previous_state=encode_state_snapshot(state),
    )
    with pytest.raises(
        KnowledgeRevalidationAssessmentError,
        match="knowledge_revalidation_previous_pointer_invalid",
    ):
        _target_state_from_proposal(
            invalid,
            SimpleNamespace(id=item_id, team_id=team_id),
            require_current=False,
        )


def test_task_runtime_requires_revalidation_assessment_id_for_success():
    observation = TerminalObservation(
        task_id=uuid4(),
        attempt=1,
        result_category="success_knowledge_revalidation_assessed",
        observed_at=datetime.now(timezone.utc),
    )

    with pytest.raises(
        TaskNotFinalizable,
        match="knowledge_revalidation_assessment_id_required",
    ):
        TaskRuntime._validate_observation(observation)


def test_task_runtime_rejects_assessment_id_on_failure():
    observation = TerminalObservation(
        task_id=uuid4(),
        attempt=1,
        result_category="terminal_failure",
        observed_at=datetime.now(timezone.utc),
        failure_reason="evidence_stale",
        knowledge_revalidation_assessment_id=uuid4(),
    )

    with pytest.raises(
        TaskNotFinalizable,
        match="terminal_evidence_not_allowed",
    ):
        TaskRuntime._validate_observation(observation)
