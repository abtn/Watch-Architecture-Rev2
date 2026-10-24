"""R5-B: Plan lifecycle transitions, durable evidence, and reconstruction."""

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from typing import Any, Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from core.ingestion import IngestionProposal, IngestionService
from core.models import Event, Objective, Plan, PlanAction, Task, Team, TeamPolicy
from core.objectives import ObjectiveService
from core.plans import PlanResult, PlanService
from core.snapshot_store import SnapshotStore
from core.state_assessment import StateAssessmentBuilder
from core.strategy import StrategyService
from core.strategy_proposal import FakeStrategyWorker, StrategyContext
from tests.test_plans import plan_request  # noqa: F401

_ZERO_BUDGET = {"max_tool_calls": 0, "max_cost_usd": 0.0, "deadline_seconds": 60}


def _add_task(
    session_factory: sessionmaker[Session],
    team_id: UUID,
    objective_id: UUID,
    policy_version: int,
    task_type: str,
    allowed_writes: list[str],
) -> UUID:
    task_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Task(
                id=task_id,
                team_id=team_id,
                objective_id=objective_id,
                task_type=task_type,
                status="running",
                policy_version=policy_version,
                allowed_writes=allowed_writes,
                budget=dict(_ZERO_BUDGET),
            )
        )
    return task_id


@pytest.fixture
def lifecycle(
    request: pytest.FixtureRequest,
    session_factory: sessionmaker[Session],
) -> Iterator[dict[str, Any]]:
    """A materialized Plan plus a running `transition_plan` Task."""
    materialization = request.getfixturevalue("plan_request")
    plan = PlanService(session_factory).create(**materialization)
    transition_task_id = _add_task(
        session_factory,
        materialization["team_id"],
        materialization["objective_id"],
        1,
        "transition_plan",
        ["Plan"],
    )
    yield {
        "plan": plan,
        "task_id": transition_task_id,
        "team_id": materialization["team_id"],
        "objective_id": materialization["objective_id"],
    }


def _materialize_plan(
    session_factory: sessionmaker[Session],
    team_id: UUID,
    objective_id: UUID,
    policy_version: int,
) -> PlanResult:
    """Materialize a Plan for one Objective from a fresh accepted Strategy."""
    strategy_id = _add_task(
        session_factory,
        team_id,
        objective_id,
        policy_version,
        "propose_strategy",
        [],
    )
    create_id = _add_task(
        session_factory,
        team_id,
        objective_id,
        policy_version,
        "create_plan",
        ["Plan"],
    )
    context = StrategyContext(
        str(strategy_id),
        StateAssessmentBuilder(session_factory).build(objective_id),
    )
    proposal = FakeStrategyWorker().propose(context)
    accepted = StrategyService(session_factory).submit(
        strategy_id, proposal, context.assessment
    )
    assert accepted.accepted
    with session_factory() as session:
        event = session.get(Event, accepted.event_id)
        assert event is not None
        proposal_hash = event.payload["proposal_hash"]
    return PlanService(session_factory).create(
        create_id,
        accepted.event_id,
        proposal_hash,
        objective_id,
        team_id,
    )


def _materialize_successor(
    session_factory: sessionmaker[Session], lifecycle: dict[str, Any]
) -> PlanResult:
    """Materialize a second Plan for the same Objective from a new Strategy."""
    return _materialize_plan(
        session_factory,
        lifecycle["team_id"],
        lifecycle["objective_id"],
        1,
    )


def _run_ingestion(
    session_factory: sessionmaker[Session],
    plan: PlanResult,
    snapshot_store: SnapshotStore,
) -> None:
    """Produce the durable ingestion outcome Events for the linked Tasks."""
    with session_factory() as session:
        actions = {
            row.action_id: row.action
            for row in session.scalars(
                select(PlanAction).where(PlanAction.plan_id == plan.plan_id)
            )
        }
        tasks = list(session.scalars(select(Task).where(Task.plan_id == plan.plan_id)))
    with session_factory.begin() as session:
        for task in session.scalars(select(Task).where(Task.plan_id == plan.plan_id)):
            task.status = "running"
    for task in tasks:
        action = actions[task.plan_action_id]
        content = b"R5-B configured source material"
        proposal = IngestionProposal(
            task_id=task.id,
            origin_url=action["origin_url"],
            source_type=action["source_type"],
            fetched_at=datetime.now(timezone.utc),
            content=content,
            claimed_content_hash=f"sha256:{hashlib.sha256(content).hexdigest()}",
        )
        IngestionService(session_factory, snapshot_store).ingest(proposal)
    with session_factory.begin() as session:
        for task in session.scalars(select(Task).where(Task.plan_id == plan.plan_id)):
            task.status = "done"


def _lifecycle_events(
    session_factory: sessionmaker[Session], task_id: UUID
) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task_id,
                    Event.type.in_(("plan_completed", "plan_stopped")),
                )
            )
        )


def _rejection_events(
    session_factory: sessionmaker[Session], task_id: UUID
) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task_id,
                    Event.type == "plan_transition_rejected",
                )
            )
        )


def test_completion_commits_state_and_event(
    session_factory, lifecycle, snapshot_store
) -> None:
    plan = lifecycle["plan"]
    _run_ingestion(session_factory, plan, snapshot_store)
    result = PlanService(session_factory).transition(
        lifecycle["task_id"], plan.plan_id, "active", "completed"
    )
    assert result.status == "completed"
    assert result.stopped_reason is None
    assert result.successor_plan_id is None
    assert not result.replayed
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        event = session.get(Event, result.event_id)
        assert stored is not None and event is not None
        assert stored.status == "completed"
        assert stored.stopped_reason is None
        assert stored.successor_plan_id is None
        assert event.type == "plan_completed"
        assert event.task_id == lifecycle["task_id"]
        assert event.payload["plan_id"] == str(plan.plan_id)
        assert event.payload["from_status"] == "active"
        assert event.payload["to_status"] == "completed"
        assert event.payload["stopped_reason"] is None
    assert PlanService(session_factory).reconstruct(plan.plan_id) == plan


def test_completion_rejected_when_a_linked_task_is_not_done(
    session_factory, lifecycle
) -> None:
    plan = lifecycle["plan"]
    with pytest.raises(ValueError, match="plan_tasks_not_done"):
        PlanService(session_factory).transition(
            lifecycle["task_id"], plan.plan_id, "active", "completed"
        )
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "active"
    assert _lifecycle_events(session_factory, lifecycle["task_id"]) == []
    rejected = _rejection_events(session_factory, lifecycle["task_id"])
    assert len(rejected) == 1
    assert rejected[0].payload["reason"] == "plan_tasks_not_done"


def test_completion_rejected_without_durable_ingestion_evidence(
    session_factory, lifecycle
) -> None:
    """A `done` Task status alone is not completion evidence."""
    plan = lifecycle["plan"]
    with session_factory.begin() as session:
        for task in session.scalars(select(Task).where(Task.plan_id == plan.plan_id)):
            task.status = "done"
    with pytest.raises(ValueError, match="completion_evidence_missing"):
        PlanService(session_factory).transition(
            lifecycle["task_id"], plan.plan_id, "active", "completed"
        )
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "active"
    assert _lifecycle_events(session_factory, lifecycle["task_id"]) == []


def test_completion_rejected_when_an_action_has_no_linked_task(
    session_factory, lifecycle, snapshot_store
) -> None:
    plan = lifecycle["plan"]
    _run_ingestion(session_factory, plan, snapshot_store)
    with session_factory.begin() as session:
        task = session.get(Task, plan.task_ids[0])
        task.plan_id = None
        task.plan_action_id = None
    with pytest.raises(ValueError, match="plan_actions_incomplete"):
        PlanService(session_factory).transition(
            lifecycle["task_id"], plan.plan_id, "active", "completed"
        )
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "active"


def test_stopping_records_reason_and_event(session_factory, lifecycle) -> None:
    plan = lifecycle["plan"]
    result = PlanService(session_factory).transition(
        lifecycle["task_id"], plan.plan_id, "active", "stopped", "abandoned"
    )
    assert result.status == "stopped"
    assert result.stopped_reason == "abandoned"
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        event = session.get(Event, result.event_id)
        assert stored is not None and event is not None
        assert stored.status == "stopped"
        assert stored.stopped_reason == "abandoned"
        assert stored.successor_plan_id is None
        assert event.type == "plan_stopped"
        assert event.payload["stopped_reason"] == "abandoned"
        assert event.payload["successor_plan_id"] is None


@pytest.mark.parametrize(
    ("reason", "expected"),
    [(None, "missing_stopped_reason"), ("cancelled", "invalid_stopped_reason")],
)
def test_stopping_requires_a_permitted_reason(
    session_factory, lifecycle, reason, expected
) -> None:
    plan = lifecycle["plan"]
    with pytest.raises(ValueError, match=expected):
        PlanService(session_factory).transition(
            lifecycle["task_id"], plan.plan_id, "active", "stopped", reason
        )
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "active"


def test_successor_is_not_allowed_for_other_stop_reasons(
    session_factory, lifecycle
) -> None:
    plan = lifecycle["plan"]
    successor = _materialize_successor(session_factory, lifecycle)
    with pytest.raises(ValueError, match="successor_not_allowed"):
        PlanService(session_factory).transition(
            lifecycle["task_id"],
            plan.plan_id,
            "active",
            "stopped",
            "invalidated",
            successor.plan_id,
        )
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "active"


def test_supersession_requires_an_active_same_objective_successor(
    session_factory, lifecycle
) -> None:
    plan = lifecycle["plan"]
    successor = _materialize_successor(session_factory, lifecycle)
    other_objective = uuid4()
    with session_factory.begin() as session:
        session.add(
            Objective(
                id=other_objective,
                team_id=lifecycle["team_id"],
                statement="Other objective",
                status="active",
            )
        )
    foreign = _materialize_plan(
        session_factory, lifecycle["team_id"], other_objective, 1
    )
    for successor_id, expected in (
        (uuid4(), "successor_not_found"),
        (foreign.plan_id, "successor_objective_mismatch"),
        (plan.plan_id, "successor_is_self"),
    ):
        with pytest.raises(ValueError, match=expected):
            PlanService(session_factory).transition(
                lifecycle["task_id"],
                plan.plan_id,
                "active",
                "stopped",
                "superseded",
                successor_id,
            )
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "active"
    assert successor.plan_id is not None


def test_supersession_requires_an_active_successor(
    session_factory, lifecycle
) -> None:
    plan = lifecycle["plan"]
    successor = _materialize_successor(session_factory, lifecycle)
    with session_factory.begin() as session:
        stored = session.get(Plan, successor.plan_id)
        stored.status = "completed"
    with pytest.raises(ValueError, match="successor_not_active"):
        PlanService(session_factory).transition(
            lifecycle["task_id"],
            plan.plan_id,
            "active",
            "stopped",
            "superseded",
            successor.plan_id,
        )
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "active"


def test_supersession_records_the_successor_reference(
    session_factory, lifecycle
) -> None:
    plan = lifecycle["plan"]
    successor = _materialize_successor(session_factory, lifecycle)
    result = PlanService(session_factory).transition(
        lifecycle["task_id"],
        plan.plan_id,
        "active",
        "stopped",
        "superseded",
        successor.plan_id,
    )
    assert result.status == "stopped"
    assert result.stopped_reason == "superseded"
    assert result.successor_plan_id == successor.plan_id
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        event = session.get(Event, result.event_id)
        assert stored is not None and event is not None
        assert stored.successor_plan_id == successor.plan_id
        assert event.type == "plan_stopped"
        assert event.payload["successor_plan_id"] == str(successor.plan_id)
    assert PlanService(session_factory).reconstruct(plan.plan_id) == plan


def test_terminal_plan_cannot_reopen(session_factory, lifecycle) -> None:
    plan = lifecycle["plan"]
    PlanService(session_factory).transition(
        lifecycle["task_id"], plan.plan_id, "active", "stopped", "abandoned"
    )
    other_task = _add_task(
        session_factory,
        lifecycle["team_id"],
        lifecycle["objective_id"],
        1,
        "transition_plan",
        ["Plan"],
    )
    with pytest.raises(ValueError, match="stale_plan_status"):
        PlanService(session_factory).transition(
            other_task, plan.plan_id, "active", "stopped", "abandoned"
        )
    with pytest.raises(ValueError, match="plan_not_active"):
        PlanService(session_factory).transition(
            other_task, plan.plan_id, "stopped", "completed"
        )
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "stopped"


def test_matching_retry_replays_the_transition(session_factory, lifecycle) -> None:
    plan = lifecycle["plan"]
    service = PlanService(session_factory)
    first = service.transition(
        lifecycle["task_id"], plan.plan_id, "active", "stopped", "abandoned"
    )
    second = service.transition(
        lifecycle["task_id"], plan.plan_id, "active", "stopped", "abandoned"
    )
    assert first.replayed is False
    assert second.replayed is True
    assert second.event_id == first.event_id
    assert second.status == "stopped"
    assert len(_lifecycle_events(session_factory, lifecycle["task_id"])) == 1


def test_conflicting_reuse_of_the_same_task_is_rejected(
    session_factory, lifecycle
) -> None:
    plan = lifecycle["plan"]
    service = PlanService(session_factory)
    service.transition(
        lifecycle["task_id"], plan.plan_id, "active", "stopped", "abandoned"
    )
    with pytest.raises(ValueError, match="task_outcome_conflict"):
        service.transition(
            lifecycle["task_id"], plan.plan_id, "active", "completed"
        )
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "stopped"
    assert len(_lifecycle_events(session_factory, lifecycle["task_id"])) == 1


def test_stale_expected_status_is_rejected(session_factory, lifecycle) -> None:
    plan = lifecycle["plan"]
    with pytest.raises(ValueError, match="stale_plan_status"):
        PlanService(session_factory).transition(
            lifecycle["task_id"], plan.plan_id, "completed", "completed"
        )
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "active"


def test_concurrent_transitions_have_one_winner(session_factory, lifecycle) -> None:
    plan = lifecycle["plan"]
    second_task = _add_task(
        session_factory,
        lifecycle["team_id"],
        lifecycle["objective_id"],
        1,
        "transition_plan",
        ["Plan"],
    )
    service = PlanService(session_factory)
    barrier = Barrier(2)

    def claim(task_id: UUID) -> object:
        barrier.wait(timeout=5)
        try:
            return service.transition(
                task_id, plan.plan_id, "active", "stopped", "abandoned"
            )
        except ValueError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(claim, [lifecycle["task_id"], second_task]))

    successes = [
        outcome for outcome in outcomes if getattr(outcome, "status", None) == "stopped"
    ]
    failures = [outcome for outcome in outcomes if isinstance(outcome, ValueError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert str(failures[0]) == "stale_plan_status"
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "stopped"
        assert (
            len(
                list(
                    session.scalars(
                        select(Event).where(
                            Event.type.in_(("plan_completed", "plan_stopped")),
                            Event.payload["plan_id"].astext == str(plan.plan_id),
                        )
                    )
                )
            )
            == 1
        )


def test_failed_transition_leaves_no_partial_state(
    session_factory, lifecycle, monkeypatch
) -> None:
    plan = lifecycle["plan"]
    original = ObjectiveService._add_event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        args[0].flush()
        raise RuntimeError("injected transition event failure")

    monkeypatch.setattr(ObjectiveService, "_add_event", fail)
    with pytest.raises(RuntimeError, match="injected transition event failure"):
        PlanService(session_factory).transition(
            lifecycle["task_id"], plan.plan_id, "active", "stopped", "abandoned"
        )
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "active"
        assert stored.stopped_reason is None
    assert _lifecycle_events(session_factory, lifecycle["task_id"]) == []


@pytest.mark.parametrize(
    ("task_type", "status", "writes", "expected"),
    [
        ("create_plan", "running", ["Plan"], "plan_event_scope_violation"),
        ("transition_plan", "pending", ["Plan"], "task_not_running"),
        ("transition_plan", "running", [], "write_scope_violation"),
    ],
)
def test_transition_task_scope_is_validated(
    request: pytest.FixtureRequest,
    session_factory,
    task_type,
    status,
    writes,
    expected,
) -> None:
    materialization = request.getfixturevalue("plan_request")
    plan = PlanService(session_factory).create(**materialization)
    task_id = _add_task(
        session_factory,
        materialization["team_id"],
        materialization["objective_id"],
        1,
        task_type,
        writes,
    )
    with session_factory.begin() as session:
        session.get(Task, task_id).status = status
    with pytest.raises(ValueError, match=expected):
        PlanService(session_factory).transition(
            task_id, plan.plan_id, "active", "stopped", "abandoned"
        )
    with session_factory() as session:
        stored = session.get(Plan, plan.plan_id)
        assert stored is not None and stored.status == "active"


def test_reconstruction_reports_missing_lifecycle_event(
    session_factory, lifecycle
) -> None:
    plan = lifecycle["plan"]
    result = PlanService(session_factory).transition(
        lifecycle["task_id"], plan.plan_id, "active", "stopped", "abandoned"
    )
    with session_factory.begin() as session:
        session.execute(delete(Event).where(Event.id == result.event_id))
    with pytest.raises(ValueError, match="recorded_plan_lifecycle_corrupt"):
        PlanService(session_factory).reconstruct(plan.plan_id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stopped_reason", "invalidated"),
        ("operation", "unrelated_operation"),
        ("expected_status", "stopped"),
        ("target_status", "completed"),
    ],
)
def test_reconstruction_reports_tampered_lifecycle_event(
    session_factory, lifecycle, field, value
) -> None:
    plan = lifecycle["plan"]
    result = PlanService(session_factory).transition(
        lifecycle["task_id"], plan.plan_id, "active", "stopped", "abandoned"
    )
    with session_factory.begin() as session:
        event = session.get(Event, result.event_id)
        event.payload = {**event.payload, field: value}
    with pytest.raises(ValueError, match="recorded_plan_lifecycle_corrupt"):
        PlanService(session_factory).reconstruct(plan.plan_id)


def test_retry_does_not_replay_a_tampered_lifecycle_event(
    session_factory, lifecycle
) -> None:
    plan = lifecycle["plan"]
    service = PlanService(session_factory)
    first = service.transition(
        lifecycle["task_id"], plan.plan_id, "active", "stopped", "abandoned"
    )
    with session_factory.begin() as session:
        event = session.get(Event, first.event_id)
        event.payload = {**event.payload, "expected_status": "stopped"}

    with pytest.raises(ValueError, match="recorded_plan_lifecycle_corrupt"):
        service.transition(
            lifecycle["task_id"], plan.plan_id, "active", "stopped", "abandoned"
        )

    assert len(_lifecycle_events(session_factory, lifecycle["task_id"])) == 1
    rejected = _rejection_events(session_factory, lifecycle["task_id"])
    assert len(rejected) == 1
    assert rejected[0].payload["reason"] == "recorded_plan_lifecycle_corrupt"


def test_reconstruction_after_restart(session_factory, lifecycle) -> None:
    plan = lifecycle["plan"]
    PlanService(session_factory).transition(
        lifecycle["task_id"], plan.plan_id, "active", "stopped", "abandoned"
    )
    code = """
import json, os, sys
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.models import Plan
from core.plans import PlanService
engine = create_engine(os.environ['R5_DATABASE_URL'])
factory = sessionmaker(engine)
result = PlanService(factory).reconstruct(UUID(sys.argv[1]))
with factory() as session:
    plan = session.get(Plan, result.plan_id)
    print(json.dumps({
        'status': plan.status,
        'stopped_reason': plan.stopped_reason,
        'successor_plan_id': str(plan.successor_plan_id)
        if plan.successor_plan_id else None,
        'action_ids': [str(item) for item in result.action_ids],
        'task_ids': [str(item) for item in result.task_ids],
    }))
engine.dispose()
"""
    env = {
        **os.environ,
        "R5_DATABASE_URL": session_factory.kw["bind"].url.render_as_string(
            hide_password=False
        ),
    }
    recovered = subprocess.run(
        [sys.executable, "-c", code, str(plan.plan_id)],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(recovered.stdout)
    assert payload["status"] == "stopped"
    assert payload["stopped_reason"] == "abandoned"
    assert payload["successor_plan_id"] is None
    assert payload["action_ids"] == [str(item) for item in plan.action_ids]
    assert payload["task_ids"] == [str(item) for item in plan.task_ids]


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"status": "stopped"}, "ck_plans_lifecycle_state"),
        ({"status": "unknown"}, "ck_plans_status"),
        ({"stopped_reason": "cancelled"}, "ck_plans_stopped_reason"),
        (
            {"status": "completed", "stopped_reason": "abandoned"},
            "ck_plans_lifecycle_state",
        ),
        ({"stopped_reason": "abandoned"}, "ck_plans_lifecycle_state"),
    ],
)
def test_database_rejects_invalid_lifecycle_combinations(
    session_factory, lifecycle, changes, expected
) -> None:
    plan = lifecycle["plan"]
    with pytest.raises(DBAPIError):
        with session_factory.begin() as session:
            stored = session.get(Plan, plan.plan_id)
            for key, value in changes.items():
                setattr(stored, key, value)


def test_database_rejects_supersession_without_a_successor(
    session_factory, lifecycle
) -> None:
    plan = lifecycle["plan"]
    with pytest.raises(DBAPIError):
        with session_factory.begin() as session:
            stored = session.get(Plan, plan.plan_id)
            stored.status = "stopped"
            stored.stopped_reason = "superseded"


def test_database_protects_immutable_intent_during_a_transition(
    session_factory, lifecycle
) -> None:
    plan = lifecycle["plan"]
    with pytest.raises(DBAPIError):
        with session_factory.begin() as session:
            session.get(Plan, plan.plan_id).budget = {"max_tasks": 99}
    with pytest.raises(DBAPIError):
        with session_factory.begin() as session:
            session.get(Plan, plan.plan_id).completion_condition = "changed"
    with pytest.raises(DBAPIError):
        with session_factory.begin() as session:
            session.get(Plan, plan.plan_id).proposal_hash = "changed"
    assert PlanService(session_factory).reconstruct(plan.plan_id) == plan


def test_transition_preserves_accepted_intent(session_factory, lifecycle) -> None:
    plan = lifecycle["plan"]
    with session_factory() as session:
        before = session.get(Plan, plan.plan_id)
        assert before is not None
        intent = (
            before.accepted_event_id,
            before.proposal_hash,
            before.assessment_basis,
            before.assessment_created_at,
            before.budget,
            before.completion_condition,
            before.objective_id,
            before.team_id,
        )
    PlanService(session_factory).transition(
        lifecycle["task_id"], plan.plan_id, "active", "stopped", "abandoned"
    )
    with session_factory() as session:
        after = session.get(Plan, plan.plan_id)
        assert after is not None
        assert (
            after.accepted_event_id,
            after.proposal_hash,
            after.assessment_basis,
            after.assessment_created_at,
            after.budget,
            after.completion_condition,
            after.objective_id,
            after.team_id,
        ) == intent
        assert after.status == "stopped"


def test_transition_rejects_a_plan_of_another_team(
    session_factory, lifecycle
) -> None:
    plan = lifecycle["plan"]
    other_team_id = uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=other_team_id, domain="other", status="active"))
        session.flush()
        session.add(
            TeamPolicy(id=uuid4(), team_id=other_team_id, version=1, rules={})
        )
    task_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Task(
                id=task_id,
                team_id=other_team_id,
                objective_id=None,
                task_type="transition_plan",
                status="running",
                policy_version=1,
                allowed_writes=["Plan"],
                budget=dict(_ZERO_BUDGET),
            )
        )
    with pytest.raises(ValueError, match="plan_team_mismatch"):
        PlanService(session_factory).transition(
            task_id, plan.plan_id, "active", "stopped", "abandoned"
        )
    with session_factory.begin() as session:
        session.execute(delete(Event).where(Event.task_id == task_id))
        session.execute(delete(Task).where(Task.id == task_id))
        session.execute(
            delete(TeamPolicy).where(TeamPolicy.team_id == other_team_id)
        )
        session.execute(delete(Team).where(Team.id == other_team_id))
