"""R6-F Checkpoint 3: host-invoked Operator approval Task creation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Barrier
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, LearningChange, Task, Team, TeamPolicy
from core.operator_application import (
    InvalidOperatorPrincipal,
    LearningChangeDecisionRequest,
    LearningChangeNotApprovable,
    OperatorApplicationAdapter,
    OperatorGrant,
    OperatorNotAuthorized,
    OperatorTaskRequestConflict,
    OperatorTaskRequestCorrupt,
    TrustedOperatorPrincipal,
)


@dataclass(frozen=True)
class ApprovalContext:
    team_id: UUID
    other_team_id: UUID
    learning_change_id: UUID
    proposer_task_id: UUID


@pytest.fixture
def approval_context(
    session_factory: sessionmaker[Session],
) -> Iterator[ApprovalContext]:
    team_id, other_team_id, proposer_task_id, learning_change_id = (
        uuid4() for _ in range(4)
    )
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
                proposed_state={"kind": "practice", "title": "Test practice"},
                previous_state=None,
                committed_state=None,
                evidence_basis=[{"evaluation_id": str(uuid4())}],
                evidence_basis_hash="sha256:" + "a" * 64,
                status="proposed",
                idempotency_key="operator-application-fixture",
                proposed_by_task_id=proposer_task_id,
            )
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
    result = OperatorApplicationAdapter(session_factory).request_learning_change_decision(
        principal, request
    )

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
                select(Event).where(
                    Event.task_id == result.task_id,
                    Event.type == "operator_task_requested",
                )
            )
        )
        assert len(events) == 1
        assert events[0].payload["operation"] == "approve_learning_change"
        assert events[0].payload["learning_change_id"] == str(
            approval_context.learning_change_id
        )
        assert events[0].payload["decision"] == "accept"
        assert events[0].payload["operator_id"] == (
            '{"iss":"https://host.example/identity","sub":"operator-42"}'
        )
        assert events[0].payload["policy_version"] == 2
        assert events[0].payload["request_fingerprint"].startswith("sha256:")
        assert events[0].payload["idempotency_key_hash"].startswith("sha256:")
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
