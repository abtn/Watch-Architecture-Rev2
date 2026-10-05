"""PostgreSQL integration tests for the R2 Objective commit path."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from conftest import ObjectivePrerequisites
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Objective, Task, Team
from core.objectives import (
    ObjectiveRejected,
    ObjectiveResult,
    ObjectiveService,
    TaskNotFound,
)


def _service(session_factory: sessionmaker[Session]) -> ObjectiveService:
    return ObjectiveService(session_factory)


def _events(session_factory: sessionmaker[Session], task_id: UUID) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event).where(Event.task_id == task_id).order_by(Event.created_at)
            )
        )


def _create(
    session_factory: sessionmaker[Session], p: ObjectivePrerequisites
) -> ObjectiveResult:
    return _service(session_factory).create(
        p.create_task_id, p.team_id, "Reach the goal"
    )


def test_create_objective_commits_draft_and_attributed_event(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    result = _create(session_factory, p)

    with session_factory() as session:
        objective = session.get(Objective, result.objective_id)
        assert objective is not None
        assert session.scalar(select(func.count()).select_from(Objective)) == 1
        assert (objective.team_id, objective.statement, objective.status) == (
            p.team_id,
            "Reach the goal",
            "draft",
        )
    events = _events(session_factory, p.create_task_id)
    assert len(events) == 1
    assert events[0].type == "objective_created"
    assert events[0].task_id == p.create_task_id
    assert events[0].payload["operation"] == "create_objective"
    assert events[0].payload["objective_id"] == str(result.objective_id)
    assert events[0].payload["from_status"] is None
    assert events[0].payload["to_status"] == "draft"


def test_invalid_task_cannot_be_attributed(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    with pytest.raises(TaskNotFound):
        _service(session_factory).create(uuid4(), p.team_id, "Reach the goal")
    assert _events(session_factory, p.create_task_id) == []
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Objective)) == 0


def test_create_rejections_are_auditable_and_non_mutating(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    cases = [
        ("status", "pending", "task_not_running"),
        ("team", "paused", "team_not_active"),
        ("scope", ["Signal"], "write_scope_violation"),
        ("task_type", "ingest_source", "wrong_task_type"),
        ("budget", {"max_tool_calls": -1}, "invalid_task_budget"),
    ]
    for kind, value, reason in cases:
        with session_factory.begin() as session:
            task = session.get(Task, p.create_task_id)
            team = session.get(Team, p.team_id)
            assert task is not None and team is not None
            if kind == "status":
                task.status = value
            elif kind == "team":
                team.status = value
            elif kind == "scope":
                task.allowed_writes = value
            elif kind == "task_type":
                task.task_type = value
            else:
                task.budget = value

        with pytest.raises(ObjectiveRejected) as raised:
            _service(session_factory).create(
                p.create_task_id, p.team_id, "Reach the goal"
            )
        assert raised.value.reason == reason
        assert (
            _events(session_factory, p.create_task_id)[-1].payload["reason"] == reason
        )
        with session_factory() as session:
            assert session.scalar(select(func.count()).select_from(Objective)) == 0

        with session_factory.begin() as session:
            task = session.get(Task, p.create_task_id)
            team = session.get(Team, p.team_id)
            assert task is not None and team is not None
            task.status = "running"
            task.allowed_writes = ["Objective"]
            task.budget = {
                "max_tool_calls": 0,
                "max_cost_usd": 0.0,
                "deadline_seconds": 60,
            }
            task.task_type = "create_objective"
            team.status = "active"


def test_invalid_statement_and_wrong_team_reject(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    service = _service(session_factory)
    for statement in ("", "  "):
        with pytest.raises(ObjectiveRejected) as raised:
            service.create(p.create_task_id, p.team_id, statement)
        assert raised.value.reason == "invalid_objective_statement"

    with pytest.raises(ObjectiveRejected) as raised:
        service.create(p.create_task_id, uuid4(), "Reach the goal")
    assert raised.value.reason == "objective_team_mismatch"
    assert len(_events(session_factory, p.create_task_id)) == 3
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Objective)) == 0


def test_operator_identity_is_recorded_in_success_and_rejection_events(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    service = _service(session_factory)
    created = service.create(
        p.create_task_id, p.team_id, "Reach the goal", operator_id="operator-1"
    )
    create_event = _events(session_factory, p.create_task_id)[0]
    assert create_event.payload["operator_id"] == "operator-1"

    with pytest.raises(ObjectiveRejected):
        service.create(
            p.create_task_id, p.team_id, "Different goal", operator_id="operator-1"
        )
    assert _events(session_factory, p.create_task_id)[-1].payload["operator_id"] == (
        "operator-1"
    )

    service.transition(
        p.transition_task_id,
        created.objective_id,
        "draft",
        "active",
        operator_id="operator-2",
    )
    transition_event = _events(session_factory, p.transition_task_id)[0]
    assert transition_event.payload["operator_id"] == "operator-2"


def test_same_task_creation_retry_replays_without_duplicate(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    service = _service(session_factory)
    first = service.create(p.create_task_id, p.team_id, "Reach the goal")
    replay = service.create(p.create_task_id, p.team_id, "Reach the goal")

    assert replay.replayed
    assert (replay.objective_id, replay.event_id) == (
        first.objective_id,
        first.event_id,
    )
    assert len(_events(session_factory, p.create_task_id)) == 1


def test_conflicting_same_task_creation_is_rejected(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    service = _service(session_factory)
    first = service.create(p.create_task_id, p.team_id, "Reach the goal")
    with pytest.raises(ObjectiveRejected) as raised:
        service.create(p.create_task_id, p.team_id, "Different goal")
    assert raised.value.reason == "task_outcome_conflict"
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Objective)) == 1
        assert session.get(Objective, first.objective_id).statement == "Reach the goal"
    assert [event.type for event in _events(session_factory, p.create_task_id)] == [
        "objective_created",
        "proposal_rejected",
    ]


_TRANSITIONS = {
    "draft": {"active", "cancelled"},
    "active": {"paused", "blocked", "completed", "cancelled"},
    "paused": {"active", "cancelled"},
    "blocked": {"active", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


@pytest.mark.parametrize(
    ("current", "requested"),
    [(current, requested) for current in _TRANSITIONS for requested in _TRANSITIONS],
)
def test_complete_transition_matrix(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
    current: str,
    requested: str,
) -> None:
    p = objective_prerequisites
    result = _create(session_factory, p)
    if current != "draft":
        with session_factory.begin() as session:
            objective = session.get(Objective, result.objective_id)
            assert objective is not None
            objective.status = current

    service = _service(session_factory)
    if requested in _TRANSITIONS[current]:
        transitioned = service.transition(
            p.transition_task_id, result.objective_id, current, requested
        )
        assert transitioned.status == requested
        events = _events(session_factory, p.transition_task_id)
        assert len(events) == 1 and events[0].type == "objective_transitioned"
        assert events[0].task_id == p.transition_task_id
        assert events[0].payload["operation"] == "transition_objective"
        assert events[0].payload["objective_id"] == str(result.objective_id)
        assert events[0].payload["from_status"] == current
        assert events[0].payload["to_status"] == requested
    else:
        with pytest.raises(ObjectiveRejected):
            service.transition(
                p.transition_task_id, result.objective_id, current, requested
            )
        with session_factory() as session:
            objective = session.get(Objective, result.objective_id)
            assert objective is not None and objective.status == current
        assert (
            _events(session_factory, p.transition_task_id)[0].type
            == "proposal_rejected"
        )


def test_transition_retry_and_conflicting_request(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    result = _create(session_factory, p)
    service = _service(session_factory)
    first = service.transition(
        p.transition_task_id, result.objective_id, "draft", "active"
    )
    replay = service.transition(
        p.transition_task_id, result.objective_id, "draft", "active"
    )
    assert replay.replayed and replay.event_id == first.event_id

    with pytest.raises(ObjectiveRejected) as raised:
        service.transition(
            p.transition_task_id, result.objective_id, "active", "paused"
        )
    assert raised.value.reason == "task_outcome_conflict"
    with session_factory() as session:
        assert session.get(Objective, result.objective_id).status == "active"
    assert [event.type for event in _events(session_factory, p.transition_task_id)] == [
        "objective_transitioned",
        "proposal_rejected",
    ]


def test_stale_status_and_wrong_team_are_rejected(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    result = _create(session_factory, p)
    with pytest.raises(ObjectiveRejected) as stale:
        _service(session_factory).transition(
            p.transition_task_id, result.objective_id, "active", "paused"
        )
    assert stale.value.reason == "stale_objective_status"

    with session_factory.begin() as session:
        task = session.get(Task, p.conflict_task_id)
        assert task is not None
        task.team_id = p.other_team_id
    with pytest.raises(ObjectiveRejected) as wrong_team:
        _service(session_factory).transition(
            p.conflict_task_id, result.objective_id, "draft", "active"
        )
    assert wrong_team.value.reason == "objective_team_mismatch"


def test_database_rejects_unknown_objective_status(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    with pytest.raises(IntegrityError):
        with session_factory.begin() as session:
            session.add(
                Objective(
                    id=uuid4(),
                    team_id=p.team_id,
                    statement="Invalid persisted state",
                    status="unknown",
                )
            )


def test_task_objective_team_composite_foreign_key(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    objective = _create(session_factory, p)
    with pytest.raises(IntegrityError):
        with session_factory.begin() as session:
            task = session.get(Task, p.transition_task_id)
            assert task is not None
            task.objective_id = objective.objective_id
            task.team_id = p.other_team_id


def test_conflicting_concurrent_transitions_only_commit_one(
    session_factory: sessionmaker[Session],
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    result = _create(session_factory, p)
    second_task_id = p.conflict_task_id
    barrier = Barrier(2)

    def transition(task_id: UUID, target: str) -> str:
        barrier.wait(timeout=5)
        try:
            _service(session_factory).transition(
                task_id, result.objective_id, "draft", target
            )
            return target
        except ObjectiveRejected:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                lambda args: transition(*args),
                [(p.transition_task_id, "active"), (second_task_id, "cancelled")],
            )
        )
    assert sorted(outcomes).count("rejected") == 1
    winner = next(value for value in outcomes if value != "rejected")
    with session_factory() as session:
        assert session.get(Objective, result.objective_id).status == winner
        assert (
            session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.type == "objective_transitioned")
            )
            == 1
        )
        session.execute(text("SELECT 1"))


def test_event_insert_failure_rolls_back_objective_and_transition(
    session_factory: sessionmaker[Session],
    database_engine: Engine,
    objective_prerequisites: ObjectivePrerequisites,
) -> None:
    p = objective_prerequisites
    suffix = uuid4().hex
    function_name, trigger_name = (
        f"fail_obj_event_{suffix}",
        f"fail_obj_event_tr_{suffix}",
    )
    with database_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE FUNCTION {function_name}() RETURNS trigger AS $$ BEGIN "
                "RAISE EXCEPTION 'injected Event failure'; END; $$ LANGUAGE plpgsql"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON events "
                f"FOR EACH ROW WHEN (NEW.type != 'proposal_rejected') "
                f"EXECUTE FUNCTION {function_name}()"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            _service(session_factory).create(
                p.create_task_id, p.team_id, "Reach the goal"
            )
        with session_factory() as session:
            assert session.scalar(select(func.count()).select_from(Objective)) == 0
    finally:
        with database_engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER {trigger_name} ON events"))
            connection.execute(text(f"DROP FUNCTION {function_name}()"))

    result = _create(session_factory, p)
    with database_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE FUNCTION {function_name}() RETURNS trigger AS $$ BEGIN "
                "RAISE EXCEPTION 'injected Event failure'; END; $$ LANGUAGE plpgsql"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON events "
                f"FOR EACH ROW WHEN (NEW.type != 'proposal_rejected') "
                f"EXECUTE FUNCTION {function_name}()"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            _service(session_factory).transition(
                p.transition_task_id, result.objective_id, "draft", "active"
            )
        with session_factory() as session:
            assert session.get(Objective, result.objective_id).status == "draft"
    finally:
        with database_engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER {trigger_name} ON events"))
            connection.execute(text(f"DROP FUNCTION {function_name}()"))
