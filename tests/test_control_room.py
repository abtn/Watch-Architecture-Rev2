"""Focused contract tests for the session-bound Control Room Task creators."""

from typing import cast
from uuid import uuid4

from sqlalchemy.orm import Session

from core.control_room import (
    _create_task,
    create_approve_learning_change_task,
    create_assess_knowledge_lifecycle_task,
    create_assess_knowledge_quality_task,
    create_assess_knowledge_revalidation_task,
    create_evaluate_outcome_task,
    create_ingest_source_task,
    create_operator_update_task,
    create_update_thread_task,
)
from core.models import Event, Task


class RecordingSession:
    def __init__(self, scalar_results: tuple[object, ...] = ()) -> None:
        self.added: list[object] = []
        self.statements: list[object] = []
        self.scalar_results = iter(scalar_results)
        self.flush_count = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    def scalar(self, statement: object) -> object:
        self.statements.append(statement)
        return next(self.scalar_results)

    def flush(self) -> None:
        self.flush_count += 1


def test_all_named_creators_use_the_supplied_session() -> None:
    team_id, objective_id, plan_id, action_id = (uuid4() for _ in range(4))
    task_ids = [uuid4() for _ in range(7)]
    payload = {"request": "bound"}
    session = RecordingSession((task_ids[0], task_ids[1]))
    db = cast(Session, session)

    assert create_update_thread_task(
        db,
        task_id=task_ids[0],
        team_id=team_id,
        policy_version=1,
        event_payload=payload,
    ) == task_ids[0]
    assert create_approve_learning_change_task(
        db,
        task_id=task_ids[1],
        team_id=team_id,
        policy_version=1,
        event_payload=payload,
    ) == task_ids[1]

    create_operator_update_task(
        db,
        task_id=task_ids[2],
        team_id=team_id,
        policy_version=1,
        event_payload=payload,
    )
    create_ingest_source_task(
        db,
        team_id=team_id,
        objective_id=objective_id,
        plan_id=plan_id,
        plan_action_id=action_id,
        policy_version=1,
    )
    create_assess_knowledge_quality_task(
        db,
        task_id=task_ids[3],
        team_id=team_id,
        policy_version=1,
        event_payload=payload,
    )
    create_assess_knowledge_revalidation_task(
        db,
        task_id=task_ids[4],
        team_id=team_id,
        policy_version=1,
        event_payload=payload,
    )
    create_assess_knowledge_lifecycle_task(
        db,
        task_id=task_ids[5],
        team_id=team_id,
        policy_version=1,
        event_payload=payload,
    )
    create_evaluate_outcome_task(
        db,
        task_id=task_ids[6],
        team_id=team_id,
        policy_version=1,
        event_payload=payload,
    )

    tasks = [value for value in session.added if isinstance(value, Task)]
    events = [value for value in session.added if isinstance(value, Event)]

    assert [task.task_type for task in tasks] == [
        "operator_update",
        "ingest_source",
        "assess_knowledge_quality",
        "assess_knowledge_revalidation",
        "assess_knowledge_lifecycle",
        "evaluate_outcome",
    ]
    assert len(session.statements) == 2
    assert len(events) == 7
    assert all(event.payload == payload for event in events)
    assert {event.type for event in events} == {
        "update_thread_requested",
        "operator_task_requested",
        "operator_update_requested",
        "knowledge_quality_assessment_task_requested",
        "knowledge_revalidation_assessment_task_requested",
        "knowledge_lifecycle_assessment_task_requested",
        "evaluation_task_requested",
    }
    assert session.flush_count == 12


def test_idempotent_creator_conflict_does_not_create_request_event() -> None:
    session = RecordingSession((None,))
    db = cast(Session, session)

    assert create_update_thread_task(
        db,
        task_id=uuid4(),
        team_id=uuid4(),
        policy_version=1,
        event_payload={"request": "conflict"},
    ) is None

    assert session.added == []
    assert session.flush_count == 0


def test_invalid_request_event_configuration_does_not_mutate_session() -> None:
    session = RecordingSession()
    db = cast(Session, session)

    for event_type, payload in (("task_requested", None), (None, {"request": True})):
        try:
            _create_task(
                db,
                task_id=uuid4(),
                team_id=uuid4(),
                task_type="test_task",
                policy_version=1,
                allowed_writes=[],
                budget={},
                max_attempts=1,
                request_event_type=event_type,
                request_event_payload=payload,
            )
        except ValueError as error:
            assert str(error) == (
                "request_event_type_and_payload_must_be_provided_together"
            )
        else:
            raise AssertionError("invalid request Event configuration was accepted")

        assert session.added == []
        assert session.flush_count == 0
