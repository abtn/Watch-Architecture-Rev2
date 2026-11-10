"""R6-F Checkpoint 3: host-invoked Operator approval Task creation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Barrier
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.knowledge_quality import (
    DIMENSIONS,
    EVALUATOR_IDENTITY,
    EVALUATOR_KIND,
    EVALUATOR_REVISION,
    RECORDED_EVENT_TYPE,
    REQUEST_EVENT_TYPE,
    RUBRIC_IDENTITY,
    RUBRIC_REVISION,
    assessment_payload_hash,
    assessment_record_payload,
    build_case_lineage_report,
    build_quality_task_request,
    recorded_assessment_event_payload,
    sha256_json,
)
from core.knowledge_quality import TASK_BUDGET as QUALITY_TASK_BUDGET
from core.knowledge_quality import TASK_MAX_ATTEMPTS as QUALITY_TASK_MAX_ATTEMPTS
from core.knowledge_quality import TASK_TYPE as QUALITY_TASK_TYPE
from core.learning_commit import LearningCommitCorrupt, LearningCommitService
from core.models import (
    Event,
    KnowledgeQualityAssessment,
    LearningChange,
    Outcome,
    Task,
    Team,
    TeamPolicy,
)
from core.operator_approval import build_request_fingerprint
from core.operator_application import (
    InvalidOperatorPrincipal,
    LearningChangeDecisionRequest,
    LearningChangeNotApprovable,
    OperatorApplicationAdapter,
    OperatorApplicationError,
    OperatorGrant,
    OperatorNotAuthorized,
    OperatorTaskRequestConflict,
    OperatorTaskRequestCorrupt,
    TrustedOperatorPrincipal,
)
from core.task_runtime import (
    TaskNotEligible,
    TaskNotFinalizable,
    TaskRuntime,
    TerminalObservation,
)


@dataclass(frozen=True)
class ApprovalContext:
    team_id: UUID
    other_team_id: UUID
    learning_change_id: UUID
    proposer_task_id: UUID



def _seed_quality_assessment(
    session_factory: sessionmaker[Session],
    team_id: UUID,
    proposer_task_id: UUID,
    learning_change_id: UUID,
) -> None:
    """Seed a minimal recorded assessment for Operator-adapter contract tests."""
    from datetime import datetime, timezone

    with session_factory.begin() as session:
        learning_change = session.get(LearningChange, learning_change_id)
        source_task = session.get(Task, proposer_task_id)
        assert learning_change is not None and source_task is not None
        task_id, request_payload = build_quality_task_request(
            session, source_task, learning_change
        )
        lineage = build_case_lineage_report(
            session, team_id, learning_change.evidence_basis
        )
        recorded_at = datetime.now(timezone.utc)
        dimensions = {
            name: {
                "disposition": "insufficient_evidence",
                "findings": ["Fixture records no positive quality conclusion."],
                "evidence_refs": [],
            }
            for name in DIMENSIONS
        }
        evidence_reference_hash = sha256_json([])
        payload = assessment_record_payload(
            task_id=task_id,
            team_id=team_id,
            learning_change_id=learning_change_id,
            proposal_hash=learning_change.proposed_state["proposal_hash"],
            evidence_basis_hash=learning_change.evidence_basis_hash,
            rubric_identity=RUBRIC_IDENTITY,
            rubric_revision=RUBRIC_REVISION,
            evaluator_kind=EVALUATOR_KIND,
            evaluator_identity=EVALUATOR_IDENTITY,
            evaluator_revision=EVALUATOR_REVISION,
            dimensions=dimensions,
            narrative=(
                "Fixture-only assessment: insufficient evidence for a positive "
                "conclusion."
            ),
            lineage_report=lineage,
            evidence_reference_hash=evidence_reference_hash,
            idempotency_key=request_payload["idempotency_key"],
        )
        assessment = KnowledgeQualityAssessment(
            id=uuid4(),
            team_id=team_id,
            status="recorded",
            learning_change_id=learning_change_id,
            creating_task_id=task_id,
            proposal_hash=learning_change.proposed_state["proposal_hash"],
            evidence_basis_hash=learning_change.evidence_basis_hash,
            rubric_identity=RUBRIC_IDENTITY,
            rubric_revision=RUBRIC_REVISION,
            evaluator_kind=EVALUATOR_KIND,
            evaluator_identity=EVALUATOR_IDENTITY,
            evaluator_revision=EVALUATOR_REVISION,
            dimensions=dimensions,
            narrative=payload["narrative"],
            lineage_report=lineage,
            lineage_report_hash=sha256_json(lineage),
            evidence_reference_hash=evidence_reference_hash,
            assessment_payload_hash=assessment_payload_hash(payload),
            idempotency_key=request_payload["idempotency_key"],
            recorded_at=recorded_at,
        )
        task = Task(
            id=task_id,
            team_id=team_id,
            task_type=QUALITY_TASK_TYPE,
            status="done",
            attempt_count=1,
            policy_version=source_task.policy_version,
            objective_id=None,
            plan_id=None,
            plan_action_id=None,
            allowed_writes=["KnowledgeQualityAssessment"],
            budget=dict(QUALITY_TASK_BUDGET),
            completed_at=recorded_at,
            max_attempts=QUALITY_TASK_MAX_ATTEMPTS,
        )
        outcome_id = uuid4()
        snapshot_digest = "b" * 64
        outcome = Outcome(
            id=outcome_id,
            team_id=team_id,
            subject_kind="task",
            subject_id=task_id,
            outcome_type="task_execution",
            expected=None,
            observation_snapshot_ref=f"snap://sha256/{snapshot_digest}",
            observation_hash=f"sha256:{snapshot_digest}",
            observed_at=recorded_at,
            recorded_by_task_id=task_id,
        )
        session.add(task)
        session.flush()
        session.add_all([outcome, assessment])
        session.flush()
        session.add_all(
            [
                Event(
                    id=uuid4(),
                    task_id=task_id,
                    type=REQUEST_EVENT_TYPE,
                    payload=request_payload,
                    created_at=recorded_at,
                ),
                Event(
                    id=uuid4(),
                    task_id=task_id,
                    type="task_started",
                    payload={
                        "from_status": "pending",
                        "to_status": "running",
                        "attempt_count": 1,
                    },
                    created_at=recorded_at,
                ),
                Event(
                    id=uuid4(),
                    task_id=task_id,
                    type=RECORDED_EVENT_TYPE,
                    payload=recorded_assessment_event_payload(assessment),
                    created_at=recorded_at,
                ),
                Event(
                    id=uuid4(),
                    task_id=task_id,
                    type="task_completed",
                    payload={
                        "result_category": "success_knowledge_quality_assessed",
                        "to_status": "done",
                        "attempt_count": 1,
                        "outcome_id": str(outcome_id),
                        "knowledge_quality_assessment_id": str(assessment.id),
                    },
                    created_at=recorded_at,
                ),
            ]
        )
        session.flush()


@pytest.fixture
def approval_context(
    session_factory: sessionmaker[Session],
) -> Iterator[ApprovalContext]:
    (
        team_id,
        other_team_id,
        proposer_task_id,
        learning_change_id,
        outcome_id,
        evaluation_id,
        evaluation_task_outcome_id,
    ) = (uuid4() for _ in range(7))
    policy_ids = [uuid4(), uuid4(), uuid4()]
    with session_factory.begin() as session:
        session.add_all(
            [
                Team(id=team_id, domain="operator_test", status="active"),
                Team(id=other_team_id, domain="other_operator_test", status="active"),
            ]
        )
        session.flush()
        session.add_all(
            [
                TeamPolicy(id=policy_ids[0], team_id=team_id, version=1, rules={}),
                TeamPolicy(id=policy_ids[1], team_id=team_id, version=2, rules={}),
                TeamPolicy(
                    id=policy_ids[2], team_id=other_team_id, version=1, rules={}
                ),
            ]
        )
        session.flush()
        session.add(
            Task(
                id=proposer_task_id,
                team_id=team_id,
                task_type="propose_learning_change",
                status="done",
                attempt_count=1,
                policy_version=2,
                allowed_writes=["LearningChange"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.0,
                    "deadline_seconds": 60,
                },
                completed_at=datetime.now(timezone.utc),
            )
        )
        session.flush()
        session.add(
            LearningChange(
                id=learning_change_id,
                team_id=team_id,
                target_kind="knowledge_item",
                target_id=None,
                operation="create",
                proposed_state={
                    "kind": "practice",
                    "title": "Test practice",
                    "proposal_hash": "sha256:" + "a" * 64,
                },
                previous_state=None,
                committed_state=None,
                evidence_basis=[
                    {
                        "evaluation_id": str(evaluation_id),
                        "evaluation_task_outcome_id": str(evaluation_task_outcome_id),
                        "outcome_id": str(outcome_id),
                        "source_task_id": str(proposer_task_id),
                        "source_task_provenance": {},
                        "evidence_links": [],
                    }
                ],
                evidence_basis_hash="sha256:" + "a" * 64,
                status="proposed",
                idempotency_key="operator-application-fixture",
                proposed_by_task_id=proposer_task_id,
            )
        )
        source_task = session.get(Task, proposer_task_id)
        assert source_task is not None
        source_task.completed_at = datetime.now(timezone.utc)
        session.add(
            Outcome(
                id=outcome_id,
                team_id=team_id,
                subject_kind="task",
                subject_id=proposer_task_id,
                outcome_type="task_execution",
                expected=None,
                observation_snapshot_ref="snap://sha256/" + "c" * 64,
                observation_hash="sha256:" + "c" * 64,
                observed_at=source_task.completed_at,
                recorded_by_task_id=proposer_task_id,
            )
        )
        session.flush()
        session.add_all(
            [
                Event(
                    id=uuid4(),
                    task_id=proposer_task_id,
                    type="learning_change_proposed",
                    payload={
                        "learning_change_id": str(learning_change_id),
                        "proposal_hash": "sha256:" + "a" * 64,
                        "evidence_basis_hash": "sha256:" + "a" * 64,
                    },
                    created_at=source_task.completed_at,
                ),
                Event(
                    id=uuid4(),
                    task_id=proposer_task_id,
                    type="task_completed",
                    payload={
                        "result_category": "success_learning_change_proposed",
                        "to_status": "done",
                        "attempt_count": 1,
                        "outcome_id": str(outcome_id),
                        "learning_change_id": str(learning_change_id),
                    },
                    created_at=source_task.completed_at,
                ),
            ]
        )

    _seed_quality_assessment(
        session_factory, team_id, proposer_task_id, learning_change_id
    )

    try:
        yield ApprovalContext(
            team_id=team_id,
            other_team_id=other_team_id,
            learning_change_id=learning_change_id,
            proposer_task_id=proposer_task_id,
        )
    finally:
        with session_factory.begin() as session:
            task_ids = select(Task.id).where(Task.team_id == team_id)
            session.execute(delete(Event).where(Event.task_id.in_(task_ids)))
            session.execute(
                delete(KnowledgeQualityAssessment).where(
                    KnowledgeQualityAssessment.team_id == team_id
                )
            )
            session.execute(
                delete(Outcome).where(Outcome.recorded_by_task_id.in_(task_ids))
            )
            session.execute(
                delete(LearningChange).where(LearningChange.team_id == team_id)
            )
            session.execute(delete(Task).where(Task.team_id == team_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.team_id.in_(
                [team_id, other_team_id]
            )))
            session.execute(
                delete(Team).where(Team.id.in_([team_id, other_team_id]))
            )


def _principal(
    team_id: UUID,
    *,
    subject: str = "operator-42",
    issuer: str = "https://host.example/identity",
    action: str = "approve_learning_change",
) -> TrustedOperatorPrincipal:
    return TrustedOperatorPrincipal(
        issuer=issuer,
        subject=subject,
        grants=frozenset({OperatorGrant(team_id=team_id, action=action)}),
    )


def _request(
    learning_change_id: UUID,
    *,
    decision: str = "accept",
    idempotency_key: UUID | None = None,
    rejection_reason: str | None = None,
) -> LearningChangeDecisionRequest:
    return LearningChangeDecisionRequest(
        learning_change_id=learning_change_id,
        decision=decision,  # type: ignore[arg-type]
        idempotency_key=idempotency_key or uuid4(),
        rejection_reason=rejection_reason,
    )


def test_request_creates_one_pending_task_and_one_attributed_event(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    principal = _principal(approval_context.team_id)
    request = _request(approval_context.learning_change_id)
    result = OperatorApplicationAdapter(
        session_factory
    ).request_learning_change_decision(principal, request)

    assert result.team_id == approval_context.team_id
    assert result.status == "pending"
    assert not result.replayed

    with session_factory() as session:
        task = session.get(Task, result.task_id)
        assert task is not None
        assert task.task_type == "approve_learning_change"
        assert task.status == "pending"
        assert task.attempt_count == 0
        assert task.policy_version == 2
        assert task.objective_id is None
        assert task.plan_id is None
        assert task.plan_action_id is None
        assert task.allowed_writes == ["LearningChange", "KnowledgeItem"]
        assert task.budget == {"max_tool_calls": 0, "max_cost_usd": 0.0}
        assert task.max_attempts == 3
        assert task.completed_at is None

        events = list(
            session.scalars(
                select(Event).where(Event.task_id == result.task_id)
            )
        )
        assert len(events) == 1
        assert events[0].type == "operator_task_requested"
        assert events[0].payload["operation"] == "approve_learning_change"
        assert events[0].payload["learning_change_id"] == str(
            approval_context.learning_change_id
        )
        assert events[0].payload["decision"] == "accept"
        assert events[0].payload["operator_id"] == (
            '{"iss":"https://host.example/identity","sub":"operator-42"}'
        )
        assert events[0].payload["schema_version"] == 3
        assert events[0].payload["policy_version"] == 2
        assert events[0].payload["request_fingerprint"].startswith("sha256:")
        assert events[0].payload["idempotency_key_hash"].startswith("sha256:")
        binding = events[0].payload["approval_binding"]
        assert binding["operation"] == "create"
        assert binding["team_id"] == str(approval_context.team_id)
        assert binding["learning_change_id"] == str(
            approval_context.learning_change_id
        )
        assert binding["assessment_type"] == "knowledge_quality"
        assert binding["assessment_id"] == events[0].payload[
            "knowledge_quality_assessment_id"
        ]
        assert binding["assessment_payload_hash"] == events[0].payload[
            "knowledge_quality_assessment_hash"
        ]
        assert binding["approval_policy_version"] == 2
        assert binding["operator_id"] == events[0].payload["operator_id"]
        assert not hasattr(request, "operator_id")
        assert session.scalar(
            select(func.count(Task.id)).where(
                Task.id == result.task_id
            )
        ) == 1


def test_same_request_replays_same_task_after_policy_advances(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    principal = _principal(approval_context.team_id)
    request = _request(approval_context.learning_change_id)
    adapter = OperatorApplicationAdapter(session_factory)

    first = adapter.request_learning_change_decision(principal, request)
    with session_factory.begin() as session:
        session.add(
            TeamPolicy(
                id=uuid4(),
                team_id=approval_context.team_id,
                version=3,
                rules={"new": True},
            )
        )

    replay = adapter.request_learning_change_decision(principal, request)
    assert replay.task_id == first.task_id
    assert replay.status == "pending"
    assert replay.replayed

    with session_factory() as session:
        assert session.scalar(
            select(func.count(Task.id)).where(
                Task.id == first.task_id
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == first.task_id,
                Event.type == "operator_task_requested",
            )
        ) == 1
        assert session.get(Task, first.task_id).policy_version == 2


def test_same_idempotency_key_with_changed_decision_conflicts(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    principal = _principal(approval_context.team_id)
    key = uuid4()
    adapter = OperatorApplicationAdapter(session_factory)
    adapter.request_learning_change_decision(
        principal,
        _request(approval_context.learning_change_id, idempotency_key=key),
    )

    with pytest.raises(
        OperatorTaskRequestConflict,
        match="idempotency_key_reused_with_different_request",
    ):
        adapter.request_learning_change_decision(
            principal,
            _request(
                approval_context.learning_change_id,
                decision="reject",
                idempotency_key=key,
                rejection_reason="The evidence is insufficient.",
            ),
        )


def test_same_idempotency_key_with_different_operator_conflicts(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    key = uuid4()
    adapter = OperatorApplicationAdapter(session_factory)
    adapter.request_learning_change_decision(
        _principal(approval_context.team_id, subject="operator-1"),
        _request(approval_context.learning_change_id, idempotency_key=key),
    )

    with pytest.raises(OperatorTaskRequestConflict):
        adapter.request_learning_change_decision(
            _principal(approval_context.team_id, subject="operator-2"),
            _request(approval_context.learning_change_id, idempotency_key=key),
        )


def test_host_grant_must_match_the_proposal_team_and_exact_action(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    adapter = OperatorApplicationAdapter(session_factory)
    request = _request(approval_context.learning_change_id)

    with pytest.raises(OperatorNotAuthorized):
        adapter.request_learning_change_decision(
            _principal(approval_context.other_team_id),
            request,
        )

    with pytest.raises(OperatorNotAuthorized):
        adapter.request_learning_change_decision(
            _principal(approval_context.team_id, action="activate_team"),
            request,
        )

    with session_factory() as session:
        assert session.scalar(
            select(func.count(Task.id)).where(
                Task.task_type == "approve_learning_change",
                Task.team_id == approval_context.team_id,
            )
        ) == 0


def test_raw_string_is_not_an_authenticated_principal(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    adapter = OperatorApplicationAdapter(session_factory)

    with pytest.raises(InvalidOperatorPrincipal):
        adapter.request_learning_change_decision(  # type: ignore[arg-type]
            "operator-42",
            _request(approval_context.learning_change_id),
        )


def test_malformed_identity_is_rejected_before_task_creation(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    adapter = OperatorApplicationAdapter(session_factory)
    principal = _principal(approval_context.team_id, issuer=" ")

    with pytest.raises(InvalidOperatorPrincipal, match="invalid_operator_issuer"):
        adapter.request_learning_change_decision(
            principal,
            _request(approval_context.learning_change_id),
        )

    with session_factory() as session:
        assert session.scalar(
            select(func.count(Task.id)).where(
                Task.task_type == "approve_learning_change",
                Task.team_id == approval_context.team_id,
            )
        ) == 0


def test_rejection_reason_is_required_and_acceptance_cannot_supply_one(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    adapter = OperatorApplicationAdapter(session_factory)
    principal = _principal(approval_context.team_id)

    with pytest.raises(OperatorApplicationError, match="rejection_reason_required"):
        adapter.request_learning_change_decision(
            principal,
            _request(
                approval_context.learning_change_id,
                decision="reject",
            ),
        )

    with pytest.raises(OperatorApplicationError, match="rejection_reason_not_allowed"):
        adapter.request_learning_change_decision(
            principal,
            _request(
                approval_context.learning_change_id,
                decision="accept",
                rejection_reason="Unexpected reason.",
            ),
        )


@pytest.mark.parametrize("corruption", ["missing", "modified", "duplicate"])
def test_corrupt_request_event_fails_closed(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
    corruption: str,
) -> None:
    principal = _principal(approval_context.team_id)
    request = _request(approval_context.learning_change_id)
    adapter = OperatorApplicationAdapter(session_factory)
    created = adapter.request_learning_change_decision(principal, request)

    with session_factory.begin() as session:
        event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "operator_task_requested",
            )
        )
        assert event is not None
        if corruption == "missing":
            session.delete(event)
        elif corruption == "modified":
            event.payload = {**event.payload, "operator_id": "forged"}
        else:
            session.add(
                Event(
                    id=uuid4(),
                    task_id=created.task_id,
                    type="operator_task_requested",
                    payload=dict(event.payload),
                    created_at=event.created_at,
                )
            )

    with pytest.raises(OperatorTaskRequestCorrupt):
        adapter.request_learning_change_decision(principal, request)


def test_non_proposed_learning_change_cannot_start_a_new_request(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    with session_factory.begin() as session:
        learning_change = session.get(
            LearningChange, approval_context.learning_change_id
        )
        assert learning_change is not None
        learning_change.operation = "retire"
        learning_change.target_id = uuid4()

    with pytest.raises(
        LearningChangeNotApprovable,
        match="only_knowledge_item_create_is_supported",
    ):
        OperatorApplicationAdapter(session_factory).request_learning_change_decision(
            _principal(approval_context.team_id),
            _request(approval_context.learning_change_id),
        )


def test_inactive_team_cannot_create_new_approval_task(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    with session_factory.begin() as session:
        team = session.get(Team, approval_context.team_id)
        assert team is not None
        team.status = "paused"

    with pytest.raises(OperatorApplicationError, match="team_not_active"):
        OperatorApplicationAdapter(session_factory).request_learning_change_decision(
            _principal(approval_context.team_id),
            _request(approval_context.learning_change_id),
        )


def test_concurrent_identical_requests_create_one_task_and_request_event(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    adapter = OperatorApplicationAdapter(session_factory)
    principal = _principal(approval_context.team_id)
    request = _request(approval_context.learning_change_id)
    barrier = Barrier(2)

    def invoke():
        barrier.wait()
        return adapter.request_learning_change_decision(principal, request)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: invoke(), range(2)))

    assert results[0].task_id == results[1].task_id
    assert sorted(result.replayed for result in results) == [False, True]

    with session_factory() as session:
        assert session.scalar(
            select(func.count(Task.id)).where(Task.id == results[0].task_id)
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == results[0].task_id,
                Event.type == "operator_task_requested",
            )
        ) == 1


def test_task_runtime_admits_valid_operator_task_without_deadline(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    request_result = OperatorApplicationAdapter(
        session_factory
    ).request_learning_change_decision(
        _principal(approval_context.team_id),
        _request(approval_context.learning_change_id),
    )

    result = TaskRuntime(session_factory).admit(request_result.task_id)

    assert result.task_id == request_result.task_id
    assert result.attempt_count == 1
    with session_factory() as session:
        task = session.get(Task, request_result.task_id)
        assert task is not None
        assert task.status == "running"
        assert task.attempt_count == 1
        assert task.budget == {"max_tool_calls": 0, "max_cost_usd": 0.0}
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task.id,
                Event.type == "operator_task_requested",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task.id,
                Event.type == "task_started",
            )
        ) == 1


@pytest.mark.parametrize(
    "mutation",
    ["scope", "nonzero_tools", "deadline", "attempt_limit"],
)
def test_task_runtime_rejects_malformed_operator_task_before_start(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
    mutation: str,
) -> None:
    request_result = OperatorApplicationAdapter(
        session_factory
    ).request_learning_change_decision(
        _principal(approval_context.team_id),
        _request(approval_context.learning_change_id),
    )
    with session_factory.begin() as session:
        task = session.get(Task, request_result.task_id)
        assert task is not None
        if mutation == "scope":
            task.allowed_writes = ["LearningChange"]
        elif mutation == "nonzero_tools":
            task.budget = {"max_tool_calls": 1, "max_cost_usd": 0.0}
        elif mutation == "deadline":
            task.budget = {
                "max_tool_calls": 0,
                "max_cost_usd": 0.0,
                "deadline_seconds": 30,
            }
        else:
            task.max_attempts = 4

    with pytest.raises(TaskNotEligible, match="operator_task_shape_invalid"):
        TaskRuntime(session_factory).admit(request_result.task_id)

    with session_factory() as session:
        task = session.get(Task, request_result.task_id)
        assert task is not None
        assert task.status == "pending"
        assert task.attempt_count == 0
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task.id,
                Event.type == "task_started",
            )
        ) == 0


def test_task_runtime_rejects_operator_task_without_request_event(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    request_result = OperatorApplicationAdapter(
        session_factory
    ).request_learning_change_decision(
        _principal(approval_context.team_id),
        _request(approval_context.learning_change_id),
    )
    with session_factory.begin() as session:
        session.execute(
            delete(Event).where(
                Event.task_id == request_result.task_id,
                Event.type == "operator_task_requested",
            )
        )

    with pytest.raises(
        TaskNotEligible, match="operator_task_request_event_invalid"
    ):
        TaskRuntime(session_factory).admit(request_result.task_id)


def test_task_runtime_rejects_operator_request_event_identity_tampering(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    request_result = OperatorApplicationAdapter(
        session_factory
    ).request_learning_change_decision(
        _principal(approval_context.team_id),
        _request(approval_context.learning_change_id),
    )
    with session_factory.begin() as session:
        event = session.scalar(
            select(Event).where(
                Event.task_id == request_result.task_id,
                Event.type == "operator_task_requested",
            )
        )
        assert event is not None
        payload = dict(event.payload)
        payload["operator_id"] = (
            '{"iss":"https://host.example/identity","sub":"operator-43"}'
        )
        event.payload = payload

    with pytest.raises(
        TaskNotEligible, match="operator_task_request_fingerprint_invalid"
    ):
        TaskRuntime(session_factory).admit(request_result.task_id)


@pytest.mark.parametrize(
    "operation",
    ["revise", "revalidate", "supersede", "retire"],
)
def test_request_creation_rejects_every_unauthorized_lifecycle_operation(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
    operation: str,
) -> None:
    with session_factory.begin() as session:
        learning_change = session.get(
            LearningChange, approval_context.learning_change_id
        )
        assert learning_change is not None
        learning_change.operation = operation
        learning_change.target_id = uuid4()

    with pytest.raises(
        LearningChangeNotApprovable,
        match="only_knowledge_item_create_is_supported",
    ):
        OperatorApplicationAdapter(session_factory).request_learning_change_decision(
            _principal(approval_context.team_id),
            _request(approval_context.learning_change_id),
        )

    with session_factory() as session:
        assert session.scalar(
            select(func.count(Task.id)).where(
                Task.team_id == approval_context.team_id,
                Task.task_type == "approve_learning_change",
            )
        ) == 0
        assert session.scalar(
            select(func.count(Event.id))
            .select_from(Event)
            .join(Task, Task.id == Event.task_id)
            .where(
                Task.team_id == approval_context.team_id,
                Event.type == "operator_task_requested",
            )
        ) == 0


@pytest.mark.parametrize(
    "operation",
    ["revise", "revalidate", "supersede", "retire"],
)
def test_task_runtime_rejects_every_unauthorized_lifecycle_operation(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
    operation: str,
) -> None:
    created = OperatorApplicationAdapter(
        session_factory
    ).request_learning_change_decision(
        _principal(approval_context.team_id),
        _request(approval_context.learning_change_id),
    )
    with session_factory.begin() as session:
        learning_change = session.get(
            LearningChange, approval_context.learning_change_id
        )
        assert learning_change is not None
        learning_change.operation = operation
        learning_change.target_id = uuid4()

    with pytest.raises(
        TaskNotEligible, match="operator_task_request_target_invalid"
    ):
        TaskRuntime(session_factory).admit(created.task_id)

    with session_factory() as session:
        task = session.get(Task, created.task_id)
        assert task is not None
        assert task.status == "pending"
        assert task.attempt_count == 0
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == created.task_id,
                Event.type == "task_started",
            )
        ) == 0


@pytest.mark.parametrize(
    "operation",
    ["revise", "revalidate", "supersede", "retire"],
)
def test_learning_commit_rechecks_create_only_eligibility(
    session_factory: sessionmaker[Session],
    snapshot_store,
    approval_context: ApprovalContext,
    operation: str,
) -> None:
    principal = _principal(approval_context.team_id)
    created = OperatorApplicationAdapter(
        session_factory
    ).request_learning_change_decision(
        principal, _request(approval_context.learning_change_id)
    )
    TaskRuntime(session_factory).admit(created.task_id)
    with session_factory.begin() as session:
        learning_change = session.get(
            LearningChange, approval_context.learning_change_id
        )
        assert learning_change is not None
        learning_change.operation = operation
        learning_change.target_id = uuid4()

    with pytest.raises(
        LearningCommitCorrupt, match="operator_task_request_target_invalid"
    ):
        LearningCommitService(session_factory, snapshot_store).decide(
            created.task_id, 1, principal
        )

    with session_factory() as session:
        learning_change = session.get(
            LearningChange, approval_context.learning_change_id
        )
        assert learning_change is not None
        assert learning_change.status == "proposed"
        assert learning_change.committed_by_task_id is None


@pytest.mark.parametrize(
    "operation",
    ["revise", "revalidate", "supersede", "retire"],
)
def test_finalization_rejects_every_unauthorized_lifecycle_operation(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
    operation: str,
) -> None:
    created = OperatorApplicationAdapter(
        session_factory
    ).request_learning_change_decision(
        _principal(approval_context.team_id),
        _request(approval_context.learning_change_id),
    )
    TaskRuntime(session_factory).admit(created.task_id)
    with session_factory.begin() as session:
        learning_change = session.get(
            LearningChange, approval_context.learning_change_id
        )
        assert learning_change is not None
        learning_change.operation = operation
        learning_change.target_id = uuid4()

    observation = TerminalObservation(
        task_id=created.task_id,
        attempt=1,
        result_category="success_learning_change_accepted",
        observed_at=datetime.now(timezone.utc),
        learning_change_id=approval_context.learning_change_id,
    )
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        assert task is not None
        with pytest.raises(
            TaskNotFinalizable, match="operator_task_request_event_invalid"
        ):
            TaskRuntime._validate_learning_change_decision_result(
                session, task, observation
            )


@pytest.mark.parametrize(
    "operation",
    ["revise", "revalidate", "supersede", "retire"],
)
def test_interrupted_recovery_rejects_every_unauthorized_lifecycle_operation(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
    operation: str,
) -> None:
    created = OperatorApplicationAdapter(
        session_factory
    ).request_learning_change_decision(
        _principal(approval_context.team_id),
        _request(approval_context.learning_change_id),
    )
    TaskRuntime(session_factory).admit(created.task_id)
    now = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        learning_change = session.get(
            LearningChange, approval_context.learning_change_id
        )
        assert learning_change is not None
        learning_change.operation = operation
        learning_change.target_id = uuid4()
        started = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "task_started",
            )
        )
        assert started is not None
        started.created_at = now - timedelta(seconds=61)

    with pytest.raises(
        TaskNotFinalizable, match="operator_task_request_event_invalid"
    ):
        TaskRuntime(session_factory).recover_interrupted(now=now)

    with session_factory() as session:
        task = session.get(Task, created.task_id)
        assert task is not None
        assert task.status == "running"
        assert task.attempt_count == 1


def test_task_runtime_rejects_rehashed_but_stale_approval_binding(
    session_factory: sessionmaker[Session],
    approval_context: ApprovalContext,
) -> None:
    principal = _principal(approval_context.team_id)
    created = OperatorApplicationAdapter(
        session_factory
    ).request_learning_change_decision(
        principal, _request(approval_context.learning_change_id)
    )

    with session_factory.begin() as session:
        event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "operator_task_requested",
            )
        )
        assert event is not None and isinstance(event.payload, dict)
        payload = dict(event.payload)
        binding = dict(payload["approval_binding"])
        binding["proposal_hash"] = "sha256:" + "0" * 64
        payload["approval_binding"] = binding
        payload["request_fingerprint"] = build_request_fingerprint(
            team_id=approval_context.team_id,
            learning_change_id=approval_context.learning_change_id,
            decision="accept",
            rejection_reason=None,
            operator_id=payload["operator_id"],
            quality_assessment_id=UUID(
                payload["knowledge_quality_assessment_id"]
            ),
            quality_assessment_hash=payload[
                "knowledge_quality_assessment_hash"
            ],
            approval_binding=binding,
        )
        event.payload = payload

    with pytest.raises(
        TaskNotEligible, match="operator_approval_binding_invalid"
    ):
        TaskRuntime(session_factory).admit(created.task_id)

    with session_factory() as session:
        task = session.get(Task, created.task_id)
        assert task is not None and task.status == "pending"
        assert task.attempt_count == 0
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == created.task_id,
                Event.type == "task_started",
            )
        ) == 0

