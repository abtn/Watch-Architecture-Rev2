"""R7-A deterministic lineage and knowledge-quality contract tests."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from core.knowledge_quality import (
    DIMENSIONS,
    RUBRIC_IDENTITY,
    RUBRIC_REVISION,
    KnowledgeQualityAssessmentDraft,
    KnowledgeQualityAssessmentError,
    KnowledgeQualityDimension,
    build_case_lineage_report,
    sha256_json,
    validate_dimension_draft,
)
from core.models import Outcome, Plan, PlanAction, Signal, Task, Team


def _digest(character: str) -> str:
    return f"sha256:{character * 64}"


def _snapshot(character: str) -> tuple[str, str]:
    digest = _digest(character)
    return f"snap://sha256/{character * 64}", digest


class _LineageSession:
    def __init__(self, team_id: UUID) -> None:
        self.team = SimpleNamespace(id=team_id, domain="lineage-tests")
        self.rows: dict[tuple[type[object], object], object] = {
            (Team, team_id): self.team
        }

    def add(self, model: type[object], key: object, value: object) -> None:
        self.rows[(model, key)] = value

    def get(self, model: type[object], key: object) -> object | None:
        return self.rows.get((model, key))


def _case(
    *,
    task_id: UUID | None = None,
    evaluation_id: UUID | None = None,
    outcome_id: UUID | None = None,
    evidence_links: list[dict[str, object]] | None = None,
    plan_id: UUID | None = None,
    action_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "source_task_id": str(task_id or uuid4()),
        "evaluation_id": str(evaluation_id or uuid4()),
        "outcome_id": str(outcome_id or uuid4()),
        "source_task_provenance": {},
        "evidence_links": evidence_links or [],
        "_plan_id": plan_id,
        "_action_id": action_id,
    }


def _register_case_task(
    session: _LineageSession,
    team_id: UUID,
    case: dict[str, object],
) -> None:
    task_id = UUID(str(case["source_task_id"]))
    session.add(
        Task,
        task_id,
        SimpleNamespace(
            id=task_id,
            team_id=team_id,
            plan_id=case.get("_plan_id"),
            plan_action_id=case.get("_action_id"),
        ),
    )


def _add_secondary_outcome(
    session: _LineageSession,
    team_id: UUID,
    outcome_id: UUID,
    character: str,
) -> tuple[str, str]:
    ref, digest = _snapshot(character)
    session.add(
        Outcome,
        outcome_id,
        SimpleNamespace(
            id=outcome_id,
            team_id=team_id,
            observation_snapshot_ref=ref,
            observation_hash=digest,
        ),
    )
    return ref, digest


def _outcome_link(outcome_id: UUID, ref: str, digest: str) -> dict[str, object]:
    return {
        "source_kind": "outcome",
        "outcome_id": str(outcome_id),
        "snapshot_ref": ref,
        "snapshot_hash": digest,
        "reference_key": f"outcome-{outcome_id}",
    }


def _signal_link(signal_id: UUID, ref: str, digest: str) -> dict[str, object]:
    return {
        "source_kind": "signal",
        "signal_id": str(signal_id),
        "snapshot_ref": ref,
        "snapshot_hash": digest,
        "reference_key": f"signal-{signal_id}",
    }


def _report(
    session: _LineageSession,
    team_id: UUID,
    cases: list[dict[str, object]],
) -> dict[str, object]:
    for case in cases:
        _register_case_task(session, team_id, case)
    return build_case_lineage_report(session, team_id, cases)


def test_case_lineage_marks_cases_unknown_without_upstream_anchors():
    team_id = uuid4()
    session = _LineageSession(team_id)
    report = _report(session, team_id, [_case(), _case()])

    assert len(report["pairs"]) == 1
    assert report["pairs"][0]["relationship"] == "unknown"
    assert report["pairs"][0]["shared_anchor_reasons"] == []


def test_case_lineage_marks_disjoint_complete_outcome_anchors_independent():
    team_id = uuid4()
    session = _LineageSession(team_id)
    cases = []
    for character in ("a", "b"):
        secondary_id = uuid4()
        ref, digest = _add_secondary_outcome(
            session, team_id, secondary_id, character
        )
        cases.append(
            _case(evidence_links=[_outcome_link(secondary_id, ref, digest)])
        )

    report = _report(session, team_id, cases)

    assert report["pairs"][0]["relationship"] == "independent"
    assert report["pairs"][0]["shared_anchor_reasons"] == []


def test_case_lineage_marks_shared_non_primary_outcome_related():
    team_id = uuid4()
    session = _LineageSession(team_id)
    secondary_id = uuid4()
    ref, digest = _add_secondary_outcome(session, team_id, secondary_id, "c")
    cases = [
        _case(evidence_links=[_outcome_link(secondary_id, ref, digest)]),
        _case(evidence_links=[_outcome_link(secondary_id, ref, digest)]),
    ]

    report = _report(session, team_id, cases)

    assert report["pairs"][0]["relationship"] == "related"
    assert f"outcome:{secondary_id}" in report["pairs"][0]["shared_anchor_reasons"]


def test_case_lineage_marks_shared_snapshot_hash_related():
    team_id = uuid4()
    session = _LineageSession(team_id)
    ref, digest = _snapshot("d")
    first_id, second_id = uuid4(), uuid4()
    for outcome_id in (first_id, second_id):
        session.add(
            Outcome,
            outcome_id,
            SimpleNamespace(
                id=outcome_id,
                team_id=team_id,
                observation_snapshot_ref=ref,
                observation_hash=digest,
            ),
        )
    cases = [
        _case(evidence_links=[_outcome_link(first_id, ref, digest)]),
        _case(evidence_links=[_outcome_link(second_id, ref, digest)]),
    ]

    report = _report(session, team_id, cases)

    assert report["pairs"][0]["relationship"] == "related"
    assert f"snapshot:{digest}" in report["pairs"][0]["shared_anchor_reasons"]


def test_case_lineage_marks_shared_signal_related():
    team_id = uuid4()
    session = _LineageSession(team_id)
    signal_id = uuid4()
    ref, digest = _snapshot("e")
    session.add(
        Signal,
        signal_id,
        SimpleNamespace(
            id=signal_id,
            domain="lineage-tests",
            snapshot_ref=ref,
            content_hash=digest,
        ),
    )
    cases = [
        _case(evidence_links=[_signal_link(signal_id, ref, digest)]),
        _case(evidence_links=[_signal_link(signal_id, ref, digest)]),
    ]

    report = _report(session, team_id, cases)

    assert report["pairs"][0]["relationship"] == "related"
    assert f"signal:{signal_id}" in report["pairs"][0]["shared_anchor_reasons"]


def test_disjoint_complete_plan_actions_are_independent():
    team_id = uuid4()
    session = _LineageSession(team_id)
    cases = []
    for _ in range(2):
        plan_id, action_id = uuid4(), uuid4()
        session.add(Plan, plan_id, SimpleNamespace(id=plan_id, team_id=team_id))
        session.add(
            PlanAction,
            (plan_id, action_id),
            SimpleNamespace(plan_id=plan_id, action_id=action_id),
        )
        cases.append(_case(plan_id=plan_id, action_id=action_id))

    report = _report(session, team_id, cases)

    assert report["pairs"][0]["relationship"] == "independent"


def test_case_lineage_marks_shared_plan_action_related():
    team_id, plan_id, action_id = uuid4(), uuid4(), uuid4()
    session = _LineageSession(team_id)
    session.add(Plan, plan_id, SimpleNamespace(id=plan_id, team_id=team_id))
    session.add(
        PlanAction,
        (plan_id, action_id),
        SimpleNamespace(plan_id=plan_id, action_id=action_id),
    )
    cases = [
        _case(plan_id=plan_id, action_id=action_id),
        _case(plan_id=plan_id, action_id=action_id),
    ]

    report = _report(session, team_id, cases)

    assert report["pairs"][0]["relationship"] == "related"
    assert f"plan_action:{plan_id}:{action_id}" in report["pairs"][0]["shared_anchor_reasons"]


def test_case_lineage_report_order_and_hash_are_deterministic():
    team_id = uuid4()
    session = _LineageSession(team_id)
    cases = [_case(), _case(), _case()]
    first = _report(session, team_id, cases)
    second = build_case_lineage_report(session, team_id, cases)

    assert first == second
    assert sha256_json(first) == sha256_json(second)
    assert [case["evaluation_id"] for case in first["cases"]] == sorted(
        case["evaluation_id"] for case in first["cases"]
    )


def test_case_lineage_rejects_repeated_source_task_id():
    team_id = uuid4()
    session = _LineageSession(team_id)
    repeated_task_id = uuid4()
    cases = [
        _case(task_id=repeated_task_id),
        _case(task_id=repeated_task_id),
    ]
    for case in cases:
        _register_case_task(session, team_id, case)

    with pytest.raises(
        KnowledgeQualityAssessmentError,
        match="knowledge_quality_evidence_case_invalid",
    ):
        build_case_lineage_report(session, team_id, cases)


def _valid_draft(
    *,
    dimensions: dict[str, KnowledgeQualityDimension] | None = None,
) -> KnowledgeQualityAssessmentDraft:
    assessment_dimensions = dimensions or {
        name: KnowledgeQualityDimension(
            disposition="insufficient_evidence",
            findings=["The available basis is insufficient for this dimension."],
            evidence_refs=[],
        )
        for name in DIMENSIONS
    }
    return KnowledgeQualityAssessmentDraft(
        learning_change_id=uuid4(),
        proposal_hash=_digest("1"),
        evidence_basis_hash=_digest("2"),
        rubric_identity=RUBRIC_IDENTITY,
        rubric_revision=RUBRIC_REVISION,
        dimensions=assessment_dimensions,
        narrative="The evidence is insufficient for a positive quality conclusion.",
    )


def test_quality_draft_accepts_exact_seven_dimension_rubric():
    draft = _valid_draft()
    result = validate_dimension_draft(draft, frozenset({"evaluation:" + str(uuid4())}))

    assert set(result) == set(DIMENSIONS)
    assert result["novelty_overlap"]["disposition"] == "insufficient_evidence"
    assert result["novelty_overlap"]["evidence_refs"] == []


def test_quality_draft_rejects_missing_or_extra_dimension():
    draft = _valid_draft()
    dimensions = dict(draft.dimensions)
    dimensions.pop("specificity_actionability")
    with pytest.raises(ValidationError):
        KnowledgeQualityAssessmentDraft.model_validate(
            {
                **draft.model_dump(),
                "dimensions": dimensions,
            }
        )

    dimensions = dict(draft.dimensions)
    dimensions["unrecognized"] = dimensions["novelty_overlap"]
    with pytest.raises(ValidationError):
        KnowledgeQualityAssessmentDraft.model_validate(
            {
                **draft.model_dump(),
                "dimensions": dimensions,
            }
        )


def test_quality_draft_rejects_supported_finding_without_evidence():
    draft = _valid_draft()
    dimensions = dict(draft.dimensions)
    dimensions["evidence_fidelity"] = KnowledgeQualityDimension(
        disposition="supported",
        findings=["Claim is supported."],
        evidence_refs=[],
    )
    updated = _valid_draft(dimensions=dimensions)

    with pytest.raises(
        KnowledgeQualityAssessmentError,
        match="knowledge_quality_evidence_reference_required",
    ):
        validate_dimension_draft(updated, frozenset())


def test_quality_draft_rejects_reference_outside_canonical_basis():
    draft = _valid_draft()
    dimensions = dict(draft.dimensions)
    dimensions["evidence_fidelity"] = KnowledgeQualityDimension(
        disposition="limited",
        findings=["Only one source supports the claim."],
        evidence_refs=["signal:" + str(uuid4())],
    )
    updated = _valid_draft(dimensions=dimensions)

    with pytest.raises(
        KnowledgeQualityAssessmentError,
        match="knowledge_quality_reference_not_in_basis",
    ):
        validate_dimension_draft(updated, frozenset())


def test_quality_draft_rejects_novelty_claim_without_validated_knowledge_item():
    draft = _valid_draft()
    dimensions = dict(draft.dimensions)
    novelty_reference = "evaluation:" + str(uuid4())
    dimensions["novelty_overlap"] = KnowledgeQualityDimension(
        disposition="supported",
        findings=["This candidate is novel."],
        evidence_refs=[novelty_reference],
    )
    updated = _valid_draft(dimensions=dimensions)

    with pytest.raises(
        KnowledgeQualityAssessmentError,
        match="knowledge_quality_novelty_requires_validated_knowledge_item",
    ):
        validate_dimension_draft(updated, frozenset({novelty_reference}))
