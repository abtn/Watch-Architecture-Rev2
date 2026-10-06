"""Database-backed tests for the read-only StateAssessment slice."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from conftest import ObjectivePrerequisites
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Objective, Signal, Task
from core.objectives import ObjectiveService
from core.state_assessment import (
    ObjectiveNotFound,
    StateAssessmentBuilder,
)


def _builder(session_factory: sessionmaker[Session]) -> StateAssessmentBuilder:
    return StateAssessmentBuilder(session_factory)


def _create_objective(
    session_factory: sessionmaker[Session], p: ObjectivePrerequisites
) -> UUID:
    return ObjectiveService(session_factory).create(
        p.create_task_id, p.team_id, "Assess this operational goal"
    ).objective_id


def test_builds_objective_scoped_state_and_explicit_signal_provenance(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    objective_id = _create_objective(session_factory, p)
    other_objective_id = uuid4()
    signal_id = uuid4()
    event_id = uuid4()
    other_event_id = uuid4()
    fixed_time = datetime(2026, 10, 5, 12, 30, tzinfo=timezone.utc)

    with session_factory.begin() as session:
        session.add(
            Objective(
                id=other_objective_id,
                team_id=p.team_id,
                statement="Different goal",
                status="active",
            )
        )
        ingestion_task = session.get(Task, p.transition_task_id)
        unrelated_task = session.get(Task, p.conflict_task_id)
        assert ingestion_task is not None and unrelated_task is not None
        ingestion_task.task_type = "ingest_source"
        ingestion_task.objective_id = objective_id
        ingestion_task.allowed_writes = ["Signal"]
        unrelated_task.objective_id = other_objective_id
        session.add(
            Signal(
                id=signal_id,
                domain="ignored-for-assessment",
                source_type="feed",
                origin_url="https://example.test/source",
                fetched_at=fixed_time,
                content_hash="sha256:" + "a" * 64,
                snapshot_ref="snap://sha256/" + "a" * 64,
            )
        )
        session.add_all(
            [
                Event(
                    id=event_id,
                    task_id=p.transition_task_id,
                    type="signal_ingested",
                    payload={"signal_id": str(signal_id)},
                    created_at=fixed_time,
                ),
                Event(
                    id=other_event_id,
                    task_id=p.conflict_task_id,
                    type="signal_ingested",
                    payload={"signal_id": str(uuid4())},
                    created_at=fixed_time,
                ),
            ]
        )

    try:
        result = _builder(session_factory).build(objective_id, created_at=fixed_time)
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Signal).where(Signal.id == signal_id))

    assert result.objective.id == objective_id
    assert result.objective.status == "draft"
    assert result.team.id == p.team_id
    assert [task.id for task in result.tasks] == [p.transition_task_id]
    assert p.conflict_task_id not in {task.id for task in result.tasks}
    assert event_id in {event.id for event in result.events}
    assert other_event_id not in {event.id for event in result.events}
    assert [signal.id for signal in result.signals] == [signal_id]
    assert result.basis.signal_ids == (signal_id,)
    assert result.created_at == "2026-10-05T12:30:00.000000Z"


def test_objective_lifecycle_event_links_its_task_and_current_status(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    objective_id = _create_objective(session_factory, p)
    with session_factory.begin() as session:
        task = session.get(Task, p.transition_task_id)
        assert task is not None
        task.objective_id = objective_id
    ObjectiveService(session_factory).transition(
        p.transition_task_id, objective_id, "draft", "active"
    )

    assessment = _builder(session_factory).build(objective_id)

    assert assessment.objective.status == "active"
    assert {task.id for task in assessment.tasks} == {p.transition_task_id}
    assert {event.event_type for event in assessment.events} == {
        "objective_created",
        "objective_transitioned",
    }


def test_null_objective_task_is_not_promoted_by_lifecycle_event(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    service = ObjectiveService(session_factory)
    objective_id = service.create(
        p.create_task_id, p.team_id, "Objective A"
    ).objective_id
    unrelated_event_id = uuid4()
    with session_factory.begin() as session:
        task = session.get(Task, p.transition_task_id)
        assert task is not None
        task.objective_id = None
        session.add(
            Event(
                id=unrelated_event_id,
                task_id=p.transition_task_id,
                type="task_note",
                payload={"detail": "unrelated Task history"},
                created_at=datetime(2026, 10, 5, 12, 30, tzinfo=timezone.utc),
            )
        )

    transition = service.transition(
        p.transition_task_id, objective_id, "draft", "active"
    )
    assessment = _builder(session_factory).build(objective_id)

    assert p.transition_task_id not in assessment.basis.task_ids
    assert transition.event_id in assessment.basis.event_ids
    assert unrelated_event_id not in assessment.basis.event_ids
    assert next(
        event for event in assessment.events if event.id == transition.event_id
    ).task_id == p.transition_task_id
    assert {event.event_type for event in assessment.events} == {
        "objective_created",
        "objective_transitioned",
    }


def test_cross_objective_lifecycle_event_and_signal_are_isolated(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    service = ObjectiveService(session_factory)
    objective_a = service.create(
        p.create_task_id, p.team_id, "Objective A"
    ).objective_id
    with session_factory.begin() as session:
        task_b = session.get(Task, p.conflict_task_id)
        assert task_b is not None
        task_b.task_type = "create_objective"
    objective_b = service.create(
        p.conflict_task_id, p.team_id, "Objective B"
    ).objective_id

    fixed_time = datetime(2026, 10, 5, 12, 30, tzinfo=timezone.utc)
    signal_id = uuid4()
    a_scoped_event_id = uuid4()
    b_targeted_event_id = uuid4()
    signal_event_id = uuid4()
    created_event_ids = [a_scoped_event_id, b_targeted_event_id, signal_event_id]
    try:
        with session_factory.begin() as session:
            task_a = session.get(Task, p.transition_task_id)
            task_b = session.get(Task, p.conflict_task_id)
            assert task_a is not None
            assert task_b is not None
            task_a.objective_id = objective_a
            task_b.objective_id = objective_b
            task_b.task_type = "ingest_source"
            task_b.allowed_writes = ["Signal"]
            session.add(
                Signal(
                    id=signal_id,
                    domain="objective_test",
                    source_type="feed",
                    origin_url=f"https://example.test/objective-b/{signal_id}",
                    fetched_at=fixed_time,
                    content_hash="sha256:" + "b" * 64,
                    snapshot_ref="snap://sha256/" + "b" * 64,
                )
            )
            session.add_all(
                [
                    Event(
                        id=a_scoped_event_id,
                        task_id=p.transition_task_id,
                        type="task_note",
                        payload={"detail": "A-linked Task event"},
                        created_at=fixed_time,
                    ),
                    Event(
                        id=b_targeted_event_id,
                        task_id=p.transition_task_id,
                        type="objective_provenance",
                        payload={"objective_id": str(objective_b)},
                        created_at=fixed_time,
                    ),
                    Event(
                        id=signal_event_id,
                        task_id=p.conflict_task_id,
                        type="signal_ingested",
                        payload={"signal_id": str(signal_id)},
                        created_at=fixed_time,
                    ),
                ]
            )

        transition = service.transition(
            p.transition_task_id, objective_b, "draft", "active"
        )
        created_event_ids.append(transition.event_id)
        builder = _builder(session_factory)
        assessment_a = builder.build(objective_a, created_at=fixed_time)
        assessment_b = builder.build(objective_b, created_at=fixed_time)
        assessment_a_again = builder.build(
            objective_a,
            created_at=datetime(2026, 10, 5, 13, 30, tzinfo=timezone.utc),
        )
        assessment_b_again = builder.build(
            objective_b,
            created_at=datetime(2026, 10, 5, 14, 30, tzinfo=timezone.utc),
        )
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.id.in_(created_event_ids)))
            session.execute(delete(Signal).where(Signal.id == signal_id))

    assert p.transition_task_id in assessment_a.basis.task_ids
    assert p.transition_task_id not in assessment_b.basis.task_ids
    assert p.conflict_task_id not in assessment_a.basis.task_ids
    assert transition.event_id not in assessment_a.basis.event_ids
    assert transition.event_id in assessment_b.basis.event_ids
    assert transition.event_id not in {event.id for event in assessment_a.events}
    assert a_scoped_event_id in assessment_a.basis.event_ids
    assert a_scoped_event_id not in assessment_b.basis.event_ids
    assert b_targeted_event_id not in assessment_a.basis.event_ids
    assert b_targeted_event_id not in assessment_b.basis.event_ids
    assert signal_event_id not in assessment_a.basis.event_ids
    assert signal_event_id in assessment_b.basis.event_ids
    assert next(
        event for event in assessment_b.events if event.id == transition.event_id
    ).task_id == p.transition_task_id
    assert signal_id not in assessment_a.basis.signal_ids
    assert signal_id in assessment_b.basis.signal_ids
    assert assessment_a.basis.sha256 == assessment_a_again.basis.sha256
    assert assessment_b.basis.sha256 == assessment_b_again.basis.sha256
    assert assessment_a_again.created_at != assessment_a.created_at
    assert assessment_b_again.created_at != assessment_b.created_at


def test_unknown_objective_raises_established_not_found_style_error(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(ObjectiveNotFound, match="objective_not_found"):
        _builder(session_factory).build(uuid4())


def test_empty_related_state_is_deterministic_and_read_only(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    objective_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Objective(
                id=objective_id,
                team_id=p.team_id,
                statement="A goal with no related execution records",
                status="draft",
            )
        )

    with session_factory() as session:
        counts_before = (
            session.scalar(select(func.count()).select_from(Objective)),
            session.scalar(select(func.count()).select_from(Task)),
            session.scalar(select(func.count()).select_from(Event)),
            session.scalar(select(func.count()).select_from(Signal)),
        )

    builder = _builder(session_factory)
    assessment_a = builder.build(
        objective_id,
        created_at=datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc),
    )
    assessment_b = builder.build(
        objective_id,
        created_at=datetime(2026, 10, 5, 13, 0, tzinfo=timezone.utc),
    )

    assert assessment_a.created_at != assessment_b.created_at
    assert assessment_a.basis.sha256 == assessment_b.basis.sha256
    assert assessment_a.objective == assessment_b.objective
    assert assessment_a.tasks == assessment_b.tasks == ()
    assert assessment_a.events == assessment_b.events == ()
    assert assessment_a.signals == assessment_b.signals == ()
    assert assessment_a.basis.task_ids == ()
    assert assessment_a.basis.event_ids == ()
    assert assessment_a.basis.signal_ids == ()

    with session_factory() as session:
        counts_after = (
            session.scalar(select(func.count()).select_from(Objective)),
            session.scalar(select(func.count()).select_from(Task)),
            session.scalar(select(func.count()).select_from(Event)),
            session.scalar(select(func.count()).select_from(Signal)),
        )
    assert counts_after == counts_before


def test_related_collections_have_stable_uuid_order(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    objective_id = _create_objective(session_factory, p)
    ObjectiveService(session_factory).transition(
        p.transition_task_id, objective_id, "draft", "active"
    )

    assessment = _builder(session_factory).build(objective_id)

    assert tuple(task.id for task in assessment.tasks) == tuple(
        sorted((task.id for task in assessment.tasks), key=str)
    )
    assert tuple(event.id for event in assessment.events) == tuple(
        sorted((event.id for event in assessment.events), key=str)
    )
    assert tuple(policy.id for policy in assessment.policies) == tuple(
        sorted((policy.id for policy in assessment.policies), key=str)
    )
    assert assessment.basis.task_ids == tuple(task.id for task in assessment.tasks)
    assert assessment.basis.event_ids == tuple(event.id for event in assessment.events)


def test_authoritative_objective_change_changes_assessment_basis(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    objective_id = _create_objective(session_factory, p)
    builder = _builder(session_factory)
    before = builder.build(objective_id)

    ObjectiveService(session_factory).transition(
        p.transition_task_id, objective_id, "draft", "active"
    )
    after = builder.build(objective_id)

    assert before.objective.status == "draft"
    assert after.objective.status == "active"
    assert before.basis.sha256 != after.basis.sha256
