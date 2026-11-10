from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core import knowledge_approval
from core.knowledge_approval import (
    KnowledgeApprovalBindingError,
    build_approval_binding,
)
from core.models import LearningChangeOperatorProvenance, Task
from core.operator_approval import (
    build_request_fingerprint,
    canonical_operator_identity,
)


def _learning_change(operation: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        target_kind="knowledge_item",
        target_id=uuid4(),
        operation=operation,
        status="proposed",
        previous_state={"state": {"status": "active"}},
        proposed_state={"proposal_hash": "sha256:" + "a" * 64},
        evidence_basis=[{"source": "fixture"}],
        evidence_basis_hash="sha256:" + "b" * 64,
    )


def _session(task: SimpleNamespace, provenance: SimpleNamespace | None = None):
    def get(model, _identity):
        if model is Task:
            return task
        if model is LearningChangeOperatorProvenance:
            return provenance
        raise AssertionError(f"unexpected session.get model: {model}")

    return SimpleNamespace(get=get)


def test_revalidation_binding_pins_current_target_evidence_and_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change = _learning_change("revalidate")
    task = SimpleNamespace(policy_version=7)
    assessment = SimpleNamespace(
        task_id=uuid4(),
        current_learning_change_id=uuid4(),
        target_content_version=5,
        target_content_hash="sha256:" + "c" * 64,
        target_content_hash_scheme="watch.r7b.knowledge-content.v2",
        target_state_hash="sha256:" + "d" * 64,
        proposal_hash="sha256:" + "e" * 64,
        proposed_state_hash="sha256:" + "f" * 64,
        evidence_refs=[{"outcome_id": str(uuid4())}],
        evidence_basis_hash="sha256:" + "1" * 64,
        id=uuid4(),
        payload_hash="sha256:" + "2" * 64,
        assessment_result="supported",
        evaluator_identity="watch.r7b.revalidation",
        evaluator_revision="1",
    )
    monkeypatch.setattr(
        knowledge_approval,
        "_assessment_counts",
        lambda _session, _change: (0, 1, 0),
    )

    def require_recorded(
        session,
        learning_change,
        snapshot_store,
        session_factory,
        *,
        require_task_done,
        require_current,
    ):
        assert learning_change is change
        assert snapshot_store is not None
        assert session_factory is not None
        assert require_task_done is True
        assert require_current is True
        return assessment

    monkeypatch.setattr(
        "core.knowledge_revalidation.require_recorded_assessment",
        require_recorded,
    )
    operator_id = canonical_operator_identity(
        "https://host.example/identity", "reviewer-1"
    )
    binding = build_approval_binding(
        _session(task),
        change,
        operator_id=operator_id,
        approval_policy_version=9,
        require_assessment=True,
        snapshot_store=object(),
        session_factory=object(),
    )

    assert binding["operation"] == "revalidate"
    assert binding["assessment_type"] == "knowledge_revalidation"
    assert binding["assessment_id"] == str(assessment.id)
    assert binding["assessment_payload_hash"] == assessment.payload_hash
    assert binding["target_content_version"] == 5
    assert binding["target_status"] == "active"
    assert binding["approval_policy_version"] == 9
    assert binding["assessment_task_policy_version"] == 7
    assert binding["operator_id"] == operator_id

    assessment.assessment_result = "indeterminate"
    with pytest.raises(
        KnowledgeApprovalBindingError,
        match="knowledge_approval_revalidation_not_supported",
    ):
        build_approval_binding(
            _session(task),
            change,
            operator_id=operator_id,
            approval_policy_version=9,
            require_assessment=True,
            snapshot_store=object(),
            session_factory=object(),
        )


def test_lifecycle_supersede_binding_includes_full_successor_snapshot_and_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change = _learning_change("supersede")
    task = SimpleNamespace(policy_version=6)
    provenance = SimpleNamespace(
        issuer="https://host.example/identity",
        subject="proposal-author",
    )
    assessment = SimpleNamespace(
        task_id=uuid4(),
        current_learning_change_id=uuid4(),
        target_content_version=3,
        target_content_hash="sha256:" + "3" * 64,
        target_content_hash_scheme="watch.r7b.knowledge-content.v2",
        target_state_hash="sha256:" + "4" * 64,
        proposal_hash="sha256:" + "5" * 64,
        proposed_state_hash="sha256:" + "6" * 64,
        evidence_refs=[{"outcome_id": str(uuid4())}],
        evidence_basis_hash="sha256:" + "7" * 64,
        id=uuid4(),
        payload_hash="sha256:" + "8" * 64,
        assessment_result="eligible",
        successor_knowledge_item_id=uuid4(),
        successor_current_learning_change_id=uuid4(),
        successor_content_version=2,
        successor_content_hash="sha256:" + "9" * 64,
        successor_content_hash_scheme="watch.r7b.knowledge-content.v2",
        successor_status="active",
        successor_review_after=datetime(
            2027, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc
        ),
        successor_state_hash="sha256:" + "a" * 64,
    )
    monkeypatch.setattr(
        knowledge_approval,
        "_assessment_counts",
        lambda _session, _change: (0, 0, 1),
    )

    def require_recorded(
        session,
        learning_change,
        snapshot_store,
        session_factory,
        *,
        require_task_done,
        require_current,
    ):
        assert learning_change is change
        assert require_task_done is True
        assert require_current is True
        return assessment

    monkeypatch.setattr(
        "core.knowledge_lifecycle.require_recorded_assessment",
        require_recorded,
    )
    operator_id = canonical_operator_identity(
        "https://host.example/identity", "reviewer-2"
    )
    binding = build_approval_binding(
        _session(task, provenance),
        change,
        operator_id=operator_id,
        approval_policy_version=11,
        require_assessment=True,
        snapshot_store=object(),
        session_factory=object(),
    )

    successor = binding["successor_binding"]
    assert isinstance(successor, dict)
    assert successor["successor_knowledge_item_id"] == str(
        assessment.successor_knowledge_item_id
    )
    assert successor["successor_current_learning_change_id"] == str(
        assessment.successor_current_learning_change_id
    )
    assert successor["successor_content_version"] == 2
    assert successor["successor_content_hash"] == assessment.successor_content_hash
    assert successor["successor_status"] == "active"
    assert successor["successor_review_after"] == "2027-01-02T03:04:05.123456Z"
    assert binding["operator_provenance"] == {
        "issuer": provenance.issuer,
        "subject": provenance.subject,
    }
    assert binding["assessment_payload_hash"] == assessment.payload_hash

    assessment.assessment_result = "ineligible"
    with pytest.raises(
        KnowledgeApprovalBindingError,
        match="knowledge_approval_lifecycle_not_eligible",
    ):
        build_approval_binding(
            _session(task, provenance),
            change,
            operator_id=operator_id,
            approval_policy_version=11,
            require_assessment=True,
            snapshot_store=object(),
            session_factory=object(),
        )


def test_assessment_type_mismatch_and_duplicate_records_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change = _learning_change("revalidate")
    monkeypatch.setattr(
        knowledge_approval,
        "_assessment_counts",
        lambda _session, _change: (0, 0, 1),
    )

    with pytest.raises(
        KnowledgeApprovalBindingError,
        match="knowledge_approval_assessment_type_mismatch",
    ):
        build_approval_binding(
            _session(SimpleNamespace(policy_version=1)),
            change,
            operator_id='{"iss":"https://host.example/identity","sub":"reviewer"}',
            approval_policy_version=1,
            require_assessment=True,
            snapshot_store=object(),
            session_factory=object(),
        )

    change.operation = "create"
    change.target_id = None
    monkeypatch.setattr(
        knowledge_approval,
        "_assessment_counts",
        lambda _session, _change: (2, 0, 0),
    )
    with pytest.raises(
        KnowledgeApprovalBindingError,
        match="knowledge_approval_assessment_type_mismatch",
    ):
        build_approval_binding(
            _session(SimpleNamespace(policy_version=1)),
            change,
            operator_id='{"iss":"https://host.example/identity","sub":"reviewer"}',
            approval_policy_version=1,
            require_assessment=False,
        )


def test_assessment_hash_principal_and_policy_are_fingerprint_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change = _learning_change("revalidate")
    task = SimpleNamespace(policy_version=2)
    assessment = SimpleNamespace(
        task_id=uuid4(),
        current_learning_change_id=uuid4(),
        target_content_version=1,
        target_content_hash="sha256:" + "c" * 64,
        target_content_hash_scheme="watch.r7b.knowledge-content.v2",
        target_state_hash="sha256:" + "d" * 64,
        proposal_hash="sha256:" + "e" * 64,
        proposed_state_hash="sha256:" + "f" * 64,
        evidence_refs=[],
        evidence_basis_hash="sha256:" + "1" * 64,
        id=uuid4(),
        payload_hash="sha256:" + "2" * 64,
        evaluator_identity="watch.r7b.revalidation",
        evaluator_revision="1",
    )
    monkeypatch.setattr(
        knowledge_approval,
        "_assessment_counts",
        lambda _session, _change: (0, 1, 0),
    )
    monkeypatch.setattr(
        "core.knowledge_revalidation.require_recorded_assessment",
        lambda *args, **kwargs: assessment,
    )
    first_operator = canonical_operator_identity(
        "https://host.example/identity", "reviewer-1"
    )
    first = build_approval_binding(
        _session(task), change, operator_id=first_operator,
        approval_policy_version=4, require_assessment=True,
        snapshot_store=object(), session_factory=object(),
    )
    changed = dict(first)
    changed["assessment_payload_hash"] = "sha256:" + "3" * 64
    first_fingerprint = build_request_fingerprint(
        team_id=change.team_id, learning_change_id=change.id,
        decision="accept", rejection_reason=None, operator_id=first_operator,
        quality_assessment_id=None, quality_assessment_hash=None,
        approval_binding=first,
    )
    changed_fingerprint = build_request_fingerprint(
        team_id=change.team_id, learning_change_id=change.id,
        decision="accept", rejection_reason=None, operator_id=first_operator,
        quality_assessment_id=None, quality_assessment_hash=None,
        approval_binding=changed,
    )
    assert first_fingerprint != changed_fingerprint

    other_operator = canonical_operator_identity(
        "https://host.example/identity", "reviewer-2"
    )
    changed_principal = dict(first)
    changed_principal["operator_id"] = other_operator
    principal_fingerprint = build_request_fingerprint(
        team_id=change.team_id,
        learning_change_id=change.id,
        decision="accept",
        rejection_reason=None,
        operator_id=other_operator,
        quality_assessment_id=None,
        quality_assessment_hash=None,
        approval_binding=changed_principal,
    )
    assert principal_fingerprint != first_fingerprint

    changed_policy = dict(first)
    changed_policy["approval_policy_version"] = 5
    policy_fingerprint = build_request_fingerprint(
        team_id=change.team_id,
        learning_change_id=change.id,
        decision="accept",
        rejection_reason=None,
        operator_id=first_operator,
        quality_assessment_id=None,
        quality_assessment_hash=None,
        approval_binding=changed_policy,
    )
    assert policy_fingerprint != first_fingerprint

def test_missing_revalidation_assessment_fails_at_approval_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change = _learning_change("revalidate")
    monkeypatch.setattr(
        knowledge_approval,
        "_assessment_counts",
        lambda _session, _change: (0, 0, 0),
    )

    def missing(*args, **kwargs):
        from core.knowledge_revalidation import KnowledgeRevalidationAssessmentError

        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_assessment_required"
        )

    monkeypatch.setattr(
        "core.knowledge_revalidation.require_recorded_assessment", missing
    )
    with pytest.raises(
        KnowledgeApprovalBindingError,
        match="knowledge_revalidation_assessment_required",
    ):
        build_approval_binding(
            _session(SimpleNamespace(policy_version=1)),
            change,
            operator_id=canonical_operator_identity(
                "https://host.example/identity", "reviewer"
            ),
            approval_policy_version=2,
            require_assessment=True,
            snapshot_store=object(),
            session_factory=object(),
        )


@pytest.mark.parametrize(
    ("operation", "error_reason"),
    [
        ("revalidate", "knowledge_revalidation_predecessor_stale"),
        ("retire", "knowledge_lifecycle_assessment_payload_hash_mismatch"),
        ("supersede", "knowledge_lifecycle_successor_stale"),
    ],
)
def test_stale_or_tampered_recorded_assessments_fail_closed_at_approval(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    error_reason: str,
) -> None:
    change = _learning_change(operation)
    if operation == "revalidate":
        monkeypatch.setattr(
            knowledge_approval,
            "_assessment_counts",
            lambda _session, _change: (0, 1, 0),
        )

        def invalid(*args, **kwargs):
            from core.knowledge_revalidation import KnowledgeRevalidationAssessmentError

            raise KnowledgeRevalidationAssessmentError(error_reason)

        monkeypatch.setattr(
            "core.knowledge_revalidation.require_recorded_assessment", invalid
        )
    else:
        monkeypatch.setattr(
            knowledge_approval,
            "_assessment_counts",
            lambda _session, _change: (0, 0, 1),
        )

        def invalid(*args, **kwargs):
            from core.knowledge_lifecycle import KnowledgeLifecycleAssessmentError

            raise KnowledgeLifecycleAssessmentError(error_reason)

        monkeypatch.setattr(
            "core.knowledge_lifecycle.require_recorded_assessment", invalid
        )

    with pytest.raises(KnowledgeApprovalBindingError, match=error_reason):
        build_approval_binding(
            _session(SimpleNamespace(policy_version=1)),
            change,
            operator_id=canonical_operator_identity(
                "https://host.example/identity", "reviewer"
            ),
            approval_policy_version=2,
            require_assessment=True,
            snapshot_store=object(),
            session_factory=object(),
        )

@pytest.mark.parametrize(
    ("operation", "error_reason"),
    [
        ("revalidate", "knowledge_revalidation_team_mismatch"),
        ("retire", "knowledge_lifecycle_team_mismatch"),
    ],
)
def test_cross_team_assessment_binding_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    error_reason: str,
) -> None:
    change = _learning_change(operation)
    if operation == "revalidate":
        monkeypatch.setattr(
            knowledge_approval,
            "_assessment_counts",
            lambda _session, _change: (0, 1, 0),
        )

        def cross_team(*args, **kwargs):
            from core.knowledge_revalidation import KnowledgeRevalidationAssessmentError

            raise KnowledgeRevalidationAssessmentError(error_reason)

        monkeypatch.setattr(
            "core.knowledge_revalidation.require_recorded_assessment",
            cross_team,
        )
    else:
        monkeypatch.setattr(
            knowledge_approval,
            "_assessment_counts",
            lambda _session, _change: (0, 0, 1),
        )

        def cross_team(*args, **kwargs):
            from core.knowledge_lifecycle import KnowledgeLifecycleAssessmentError

            raise KnowledgeLifecycleAssessmentError(error_reason)

        monkeypatch.setattr(
            "core.knowledge_lifecycle.require_recorded_assessment",
            cross_team,
        )

    with pytest.raises(KnowledgeApprovalBindingError, match=error_reason):
        build_approval_binding(
            _session(SimpleNamespace(policy_version=1)),
            change,
            operator_id=canonical_operator_identity(
                "https://host.example/identity", "reviewer"
            ),
            approval_policy_version=2,
            require_assessment=True,
            snapshot_store=object(),
            session_factory=object(),
        )

