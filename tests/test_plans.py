"""R5-04 durable boundary, database constraints, rollback, and restart checks."""

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from typing import Any, Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy import event as sa_event
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from core.ingestion import IngestionProposal, IngestionService
from core.models import (
    Event,
    Objective,
    Outcome,
    Plan,
    PlanAction,
    Signal,
    Task,
    Team,
    TeamPolicy,
)
from core.objectives import ObjectiveService, TaskNotFound
from core.plans import PlanResult, PlanService
from core.snapshot_store import SnapshotStore
from core.state_assessment import StateAssessmentBuilder, _canonical_json
from core.strategy import StrategyService
from core.strategy_proposal import FakeStrategyWorker, StrategyContext, StrategyProposal
from core.task_runtime import TaskNotEligible, TaskRuntime, TerminalObservation


@pytest.fixture
def plan_request(session_factory: sessionmaker[Session]) -> Iterator[dict[str, Any]]:
    team_id, objective_id, strategy_id, create_id = (uuid4() for _ in range(4))
    source = f"https://example.test/r5/{uuid4()}"
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="plan_test", status="active"))
        session.flush()
        session.add(
            TeamPolicy(
                id=uuid4(),
                team_id=team_id,
                version=1,
                rules={
                    "sources": [{"origin_url": source, "source_type": "feed"}],
                },
            )
        )
        session.add(
            Objective(
                id=objective_id,
                team_id=team_id,
                statement="Gather source",
                status="active",
            )
        )
        session.flush()
        session.add_all(
            [
                Task(
                    id=task_id,
                    team_id=team_id,
                    objective_id=objective_id,
                    task_type=kind,
                    status="running",
                    policy_version=1,
                    allowed_writes=writes,
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.0,
                        "deadline_seconds": 60,
                    },
                )
                for task_id, kind, writes in (
                    (strategy_id, "propose_strategy", []),
                    (create_id, "create_plan", ["Plan"]),
                )
            ]
        )
    context = StrategyContext(
        str(strategy_id), StateAssessmentBuilder(session_factory).build(objective_id)
    )
    proposal = FakeStrategyWorker().propose(context)
    accepted = StrategyService(session_factory).submit(
        strategy_id, proposal, context.assessment
    )
    assert accepted.accepted
    with session_factory() as session:
        event = session.get(Event, accepted.event_id)
        assert event is not None
        request = dict(
            task_id=create_id,
            accepted_event_id=accepted.event_id,
            proposal_hash=event.payload["proposal_hash"],
            objective_id=objective_id,
            team_id=team_id,
        )
    try:
        yield request
    finally:
        with session_factory.begin() as session:
            task_ids = select(Task.id).where(Task.team_id == team_id)
            linked_ids = select(Task.id).where(
                Task.team_id == team_id, Task.plan_id.is_not(None)
            )
            session.execute(delete(Event).where(Event.task_id.in_(linked_ids)))
            session.execute(
                delete(Task).where(Task.team_id == team_id, Task.plan_id.is_not(None))
            )
            session.execute(
                delete(PlanAction).where(
                    PlanAction.plan_id.in_(
                        select(Plan.id).where(Plan.team_id == team_id)
                    )
                )
            )
            session.execute(delete(Plan).where(Plan.team_id == team_id))
            session.execute(delete(Event).where(Event.task_id.in_(task_ids)))
            session.execute(
                delete(Outcome).where(Outcome.recorded_by_task_id.in_(task_ids))
            )
            session.execute(delete(Task).where(Task.team_id == team_id))
            session.execute(delete(Objective).where(Objective.team_id == team_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.team_id == team_id))
            session.execute(delete(Team).where(Team.id == team_id))
            session.execute(delete(Signal).where(Signal.origin_url == source))


def _add_second_action(factory: sessionmaker[Session], request: dict) -> UUID:
    with factory.begin() as session:
        event = session.get(Event, request["accepted_event_id"])
        proposal = json.loads(event.payload["proposal_json"])
        first_vision = proposal["visions"][0]
        first_workstream = first_vision["workstreams"][0]
        first_action = first_workstream["actions"][0]
        second_id = uuid4()
        second = {
            **first_action,
            "id": str(second_id),
            "purpose": "Second configured source action",
            "prerequisites": [first_action["id"]],
        }
        second_vision = {
            **first_vision,
            "id": str(uuid4()),
            "name": "Second perspective",
            "workstreams": [
                {
                    **first_workstream,
                    "id": str(uuid4()),
                    "name": "Second workstream",
                    "actions": [second],
                }
            ],
        }
        proposal["visions"].append(second_vision)
        proposal["constraints"]["max_tasks"] = 3
        canonical = _canonical_json(
            StrategyProposal.model_validate(proposal).canonical_dump()
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        event.payload = {
            **event.payload,
            "proposal_json": canonical,
            "proposal_hash": digest,
        }
        request["proposal_hash"] = digest
    return second_id


def _assert_no_materialization(factory: sessionmaker[Session], request: dict) -> None:
    with factory() as session:
        assert (
            list(
                session.scalars(select(Plan).where(Plan.team_id == request["team_id"]))
            )
            == []
        )
        assert (
            list(
                session.scalars(
                    select(Task).where(
                        Task.team_id == request["team_id"], Task.plan_id.is_not(None)
                    )
                )
            )
            == []
        )
        assert (
            list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == request["task_id"],
                        Event.type == "plan_created",
                    )
                )
            )
            == []
        )


def test_atomic_creation_and_restart(session_factory, plan_request) -> None:
    _add_second_action(session_factory, plan_request)
    result = PlanService(session_factory).create(**plan_request)
    with session_factory() as session:
        plan = session.get(Plan, result.plan_id)
        tasks = list(
            session.scalars(select(Task).where(Task.plan_id == result.plan_id))
        )
        event = session.get(Event, result.event_id)
        accepted = session.get(Event, plan_request["accepted_event_id"])
        assert plan is not None and len(tasks) == 2 and event is not None
        assert accepted is not None
        assert plan.status == "active"
        assert all(task.status == "pending" for task in tasks)
        assert all(
            task.objective_id == plan.objective_id == plan_request["objective_id"]
            and task.team_id == plan.team_id == plan_request["team_id"]
            and task.plan_id == plan.id
            and task.plan_action_id in result.action_ids
            for task in tasks
        )
        assert len(set(result.action_ids)) == len(set(result.task_ids)) == 2
        actions = {
            row.action_id: row.action
            for row in session.scalars(
                select(PlanAction).where(PlanAction.plan_id == plan.id)
            )
        }
        assert set(actions) == set(result.action_ids)
        assert all(
            action["id"] == str(action_id) for action_id, action in actions.items()
        )
        assert plan.assessment_basis == accepted.payload["assessment"]["basis"]
        assert (
            plan.assessment_created_at == accepted.payload["assessment"]["created_at"]
        )
        assert event.task_id == plan_request["task_id"]
        assert not hasattr(plan, "policy_version")
        expected_actions = actions
        expected_assessment = accepted.payload["assessment"]
    code = """
import json, os, sys
from uuid import UUID
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from core.models import Event, Plan, PlanAction, Task
from core.plans import PlanService
from core.strategy import StrategyService
engine = create_engine(os.environ['R5_DATABASE_URL'])
factory = sessionmaker(engine)
result = PlanService(factory).reconstruct(UUID(sys.argv[1]))
with factory() as session:
    plan = session.get(Plan, result.plan_id)
    actions = {str(item.action_id): item.action for item in
               session.scalars(select(PlanAction).where(PlanAction.plan_id == plan.id))}
    tasks = {
              str(item.plan_action_id): str(item.id)
              for item in session.scalars(
                  select(Task).where(Task.plan_id == plan.id)
              )
    }
    accepted = session.get(Event, plan.accepted_event_id)
    proposal = StrategyService(factory).reconstruct(plan.accepted_event_id)
    print(json.dumps({'actions': actions, 'tasks': tasks,
                     'assessment': accepted.payload['assessment'],
                     'proposal': proposal.model_dump(mode='json')}))
engine.dispose()
"""
    env = {
        **os.environ,
        "R5_DATABASE_URL": session_factory.kw["bind"].url.render_as_string(
            hide_password=False
        ),
    }
    recovered = subprocess.run(
        [sys.executable, "-c", code, str(result.plan_id)],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(recovered.stdout)
    assert payload["actions"] == {
        str(action_id): action for action_id, action in expected_actions.items()
    }
    assert payload["tasks"] == {
        str(action_id): str(task_id)
        for action_id, task_id in zip(result.action_ids, result.task_ids, strict=True)
    }
    assert payload["assessment"] == expected_assessment
    assert payload["proposal"]["objective_id"] == str(plan_request["objective_id"])


def test_multi_action_materialization_preserves_identity_and_dependencies(
    session_factory, plan_request
) -> None:
    second_id = _add_second_action(session_factory, plan_request)
    result = PlanService(session_factory).create(**plan_request)
    assert second_id in result.action_ids
    assert len(result.action_ids) == len(result.task_ids) == 2
    with session_factory() as session:
        plan = session.get(Plan, result.plan_id)
        rows = list(
            session.scalars(
                select(PlanAction).where(PlanAction.plan_id == result.plan_id)
            )
        )
        tasks = list(
            session.scalars(select(Task).where(Task.plan_id == result.plan_id))
        )
        assert plan is not None and len(rows) == len(tasks) == 2
        action_by_id = {row.action_id: row.action for row in rows}
        task_by_action = {task.plan_action_id: task for task in tasks}
        assert set(action_by_id) == set(task_by_action) == set(result.action_ids)
        dependent = action_by_id[second_id]
        predecessor_id = UUID(dependent["prerequisites"][0])
        assert predecessor_id in task_by_action
        assert (
            task_by_action[second_id].plan_id
            == task_by_action[predecessor_id].plan_id
        )
        assert task_by_action[second_id].id != task_by_action[predecessor_id].id
        assert len(
            list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == plan_request["task_id"],
                        Event.type == "plan_created",
                    )
                )
            )
        ) == 1


def test_missing_dependency_is_rejected_atomically(
    session_factory, plan_request
) -> None:
    second_id = _add_second_action(session_factory, plan_request)
    with session_factory.begin() as session:
        event = session.get(Event, plan_request["accepted_event_id"])
        proposal = json.loads(event.payload["proposal_json"])
        for vision in proposal["visions"]:
            for workstream in vision["workstreams"]:
                for action in workstream["actions"]:
                    if action["id"] != str(second_id):
                        action["prerequisites"] = [str(second_id)]
                workstream["actions"] = [
                    action
                    for action in workstream["actions"]
                    if action["id"] != str(second_id)
                ]
        proposal["visions"] = [
            {
                **vision,
                "workstreams": [
                    workstream
                    for workstream in vision["workstreams"]
                    if workstream["actions"]
                ],
            }
            for vision in proposal["visions"]
            if any(workstream["actions"] for workstream in vision["workstreams"])
        ]
        proposal["constraints"]["max_tasks"] = 2
        canonical = _canonical_json(
            StrategyProposal.model_validate(proposal).canonical_dump()
        )
        event.payload = {
            **event.payload,
            "proposal_json": canonical,
            "proposal_hash": hashlib.sha256(canonical.encode()).hexdigest(),
        }
        plan_request["proposal_hash"] = event.payload["proposal_hash"]
    with pytest.raises(ValueError, match="invalid_proposal_provenance"):
        PlanService(session_factory).create(**plan_request)
    _assert_no_materialization(session_factory, plan_request)


def test_legacy_flat_proposal_cannot_authorize_plan(
    session_factory, plan_request
) -> None:
    with session_factory() as session:
        accepted = session.get(Event, plan_request["accepted_event_id"])
        assert accepted is not None
        producer_task_id = accepted.task_id
        objective = session.get(Objective, plan_request["objective_id"])
        assert objective is not None
    legacy_proposal = {
        "objective_id": str(objective.id),
        "task_id": str(producer_task_id),
        "approach": "legacy",
        "reason": "legacy proposal",
        "candidate_actions": [{"task_type": "ingest_source", "purpose": "ingest"}],
        "constraints": {"max_tasks": 1, "max_cost_usd": 0.0},
        "stop_conditions": ["configured_source_ingested"],
        "assessment_basis": {"objective_id": str(objective.id), "basis_hash": "legacy"},
    }
    digest = hashlib.sha256(_canonical_json(legacy_proposal).encode()).hexdigest()
    event_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Event(
                id=event_id,
                task_id=producer_task_id,
                type="strategy_proposal_accepted",
                payload={
                    "operation": "propose_strategy",
                    "objective_id": str(objective.id),
                    "team_id": str(plan_request["team_id"]),
                    "task_id": str(producer_task_id),
                    "reason": None,
                    "proposal": legacy_proposal,
                    "proposal_hash": f"sha256:{digest}",
                    "assessment_basis": legacy_proposal["assessment_basis"],
                },
                created_at=datetime.now(timezone.utc),
            )
        )
    with session_factory() as session:
        with pytest.raises(ValueError, match="canonical_proposal_not_found"):
            PlanService._accepted(
                session,
                event_id,
                f"sha256:{digest}",
                objective.id,
                objective.team_id,
            )


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "rejected",
        "unrelated",
        "hash",
        "canonical",
        "objective",
        "team",
        "assessment",
        "basis",
    ],
)
def test_durable_provenance_rejection(session_factory, plan_request, change) -> None:
    request = dict(plan_request)
    if change == "missing":
        request["accepted_event_id"] = uuid4()
    elif change == "hash":
        request["proposal_hash"] = "0" * 64
    elif change in {"objective", "team"}:
        request[f"{change}_id"] = uuid4()
    else:
        with session_factory.begin() as session:
            event = session.get(Event, request["accepted_event_id"])
            payload = json.loads(json.dumps(event.payload))
            if change in {"rejected", "unrelated"}:
                event.type = (
                    "strategy_proposal_rejected"
                    if change == "rejected"
                    else "signal_ingested"
                )
            elif change == "canonical":
                payload["proposal_json"] = "{}"
            elif change == "assessment":
                payload["assessment"] = {}
            else:
                payload["assessment"]["basis"]["sha256"] = "forged"
            event.payload = payload
    with pytest.raises(ValueError):
        PlanService(session_factory).create(**request)
    _assert_no_materialization(session_factory, plan_request)


@pytest.mark.parametrize("change", ["tools", "cost", "type", "stop"])
def test_unsupported_candidate_rejected(session_factory, plan_request, change) -> None:
    with session_factory.begin() as session:
        event = session.get(Event, plan_request["accepted_event_id"])
        proposal = json.loads(event.payload["proposal_json"])
        first_action = proposal["visions"][0]["workstreams"][0]["actions"][0]
        if change == "tools":
            first_action["tools"] = ["fetch"]
        elif change == "cost":
            proposal["constraints"]["max_cost_usd"] = 1.0
        elif change == "type":
            first_action["task_type"] = "update_thread"
        else:
            proposal["stop_conditions"] = ["unknown"]
        proposal = StrategyProposal.model_validate(proposal).canonical_dump()
        canonical = _canonical_json(proposal)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        event.payload = {
            **event.payload,
            "proposal_json": canonical,
            "proposal_hash": digest,
        }
    with pytest.raises(ValueError, match="unsupported_plan_candidate"):
        PlanService(session_factory).create(**{**plan_request, "proposal_hash": digest})
    _assert_no_materialization(session_factory, plan_request)


@pytest.mark.parametrize(
    "change", ["scope", "status", "budget", "type", "source", "objective"]
)
def test_current_authority_revalidated(session_factory, plan_request, change) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, plan_request["task_id"])
        if change in {"scope", "status", "budget", "type"}:
            setattr(
                task,
                {"scope": "allowed_writes", "type": "task_type"}.get(change, change),
                {
                    "scope": ["Plan", "TeamPolicy"],
                    "status": "pending",
                    "budget": {},
                    "type": "ingest_source",
                }[change],
            )
        elif change == "objective":
            session.get(Objective, task.objective_id).status = "paused"
        else:
            policy = session.scalar(
                select(TeamPolicy).where(TeamPolicy.team_id == task.team_id)
            )
            policy.rules = {"sources": []}
    with pytest.raises(ValueError):
        PlanService(session_factory).create(**plan_request)
    _assert_no_materialization(session_factory, plan_request)


def test_missing_task_cannot_create(session_factory, plan_request) -> None:
    with pytest.raises(TaskNotFound):
        PlanService(session_factory).create(**{**plan_request, "task_id": uuid4()})
    _assert_no_materialization(session_factory, plan_request)


def test_identical_retry_and_concurrency(session_factory, plan_request) -> None:
    _add_second_action(session_factory, plan_request)
    service = PlanService(session_factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.create(**plan_request), range(2)))
    assert results[0].plan_id == results[1].plan_id
    assert results[0].action_ids == results[1].action_ids
    assert results[0].task_ids == results[1].task_ids
    assert sum(result.replayed for result in results) == 1
    replay = service.create(**plan_request)
    assert replay.replayed and replay.event_id == results[0].event_id
    with session_factory() as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(Plan).where(Plan.team_id == plan_request["team_id"])
                    )
                )
            )
            == 1
        )
        assert (
            len(
                list(
                    session.scalars(
                        select(PlanAction).where(PlanAction.plan_id == replay.plan_id)
                    )
                )
            )
            == 2
        )
        assert (
            len(
                list(
                    session.scalars(select(Task).where(Task.plan_id == replay.plan_id))
                )
            )
            == 2
        )
        assert (
            len(
                list(
                    session.scalars(
                        select(Event).where(
                            Event.task_id == plan_request["task_id"],
                            Event.type == "plan_created",
                        )
                    )
                )
            )
            == 1
        )


def test_conflicting_creation_identity(session_factory, plan_request) -> None:
    _add_second_action(session_factory, plan_request)
    result = PlanService(session_factory).create(**plan_request)
    with session_factory.begin() as session:
        accepted = session.get(Event, plan_request["accepted_event_id"])
        clone = Event(
            id=uuid4(),
            task_id=accepted.task_id,
            type=accepted.type,
            payload=dict(accepted.payload),
            created_at=accepted.created_at,
        )
        session.add(clone)
        new_id = clone.id
    with pytest.raises(ValueError, match="task_outcome_conflict"):
        PlanService(session_factory).create(
            **{**plan_request, "accepted_event_id": new_id}
        )
    reconstructed = PlanService(session_factory).reconstruct(result.plan_id)
    assert reconstructed.action_ids == result.action_ids
    assert reconstructed.task_ids == result.task_ids


@pytest.mark.parametrize("target", ["event", "task"])
def test_failure_rolls_back_complete_materialization(
    session_factory, plan_request, monkeypatch, target
) -> None:
    if target == "event":
        original = ObjectiveService._add_event

        def fail(*args, **kwargs):
            original(*args, **kwargs)
            args[0].flush()
            raise RuntimeError("injected event failure")

        monkeypatch.setattr(ObjectiveService, "_add_event", fail)
        with pytest.raises(RuntimeError, match="injected event failure"):
            PlanService(session_factory).create(**plan_request)
    else:
        engine = session_factory.kw["bind"]

        def fail_task(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO tasks"):
                raise RuntimeError("injected task failure")

        sa_event.listen(engine, "before_cursor_execute", fail_task)
        try:
            with pytest.raises(RuntimeError, match="injected task failure"):
                PlanService(session_factory).create(**plan_request)
        finally:
            sa_event.remove(engine, "before_cursor_execute", fail_task)
    _assert_no_materialization(session_factory, plan_request)


@pytest.mark.parametrize("change", ["duplicate", "action", "objective", "team", "pair"])
def test_database_mapping_constraints(session_factory, plan_request, change) -> None:
    result = PlanService(session_factory).create(**plan_request)
    with pytest.raises(IntegrityError):
        with session_factory.begin() as session:
            task = session.get(Task, result.task_id)
            if change == "duplicate":
                session.add(
                    Task(
                        id=uuid4(),
                        team_id=task.team_id,
                        objective_id=task.objective_id,
                        plan_id=task.plan_id,
                        plan_action_id=task.plan_action_id,
                        task_type="ingest_source",
                        status="pending",
                        policy_version=task.policy_version,
                        allowed_writes=["Signal"],
                        budget=dict(task.budget),
                    )
                )
            elif change == "action":
                task.plan_action_id = uuid4()
            elif change == "objective":
                objective = Objective(
                    id=uuid4(), team_id=task.team_id, statement="Other", status="active"
                )
                session.add(objective)
                session.flush()
                task.objective_id = objective.id
            elif change == "pair":
                task.plan_action_id = None
            else:
                team = Team(id=uuid4(), domain="other", status="active")
                session.add(team)
                session.flush()
                session.add(
                    TeamPolicy(id=uuid4(), team_id=team.id, version=1, rules={})
                )
                session.flush()
                task.team_id = team.id
            session.flush()


def test_plan_only_provenance_is_valid(session_factory, plan_request) -> None:
    result = PlanService(session_factory).create(**plan_request)
    with session_factory.begin() as session:
        task = session.get(Task, result.task_id)
        task.objective_id = None
        session.flush()
        assert task.plan_id == result.plan_id


@pytest.mark.parametrize("change", ["action", "hash", "team", "objective"])
def test_changed_same_task_request_rejects(
    session_factory, plan_request, change
) -> None:
    result = PlanService(session_factory).create(**plan_request)
    request = dict(plan_request)
    if change == "action":
        with session_factory.begin() as session:
            accepted = session.get(Event, request["accepted_event_id"])
            proposal = json.loads(accepted.payload["proposal_json"])
            proposal["visions"][0]["workstreams"][0]["actions"][0]["purpose"] = (
                "Changed intent"
            )
            proposal = StrategyProposal.model_validate(proposal).canonical_dump()
            canonical = _canonical_json(proposal)
            request["proposal_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
            accepted.payload = {
                **accepted.payload,
                "proposal_json": canonical,
                "proposal_hash": request["proposal_hash"],
            }
    elif change == "hash":
        request["proposal_hash"] = "changed"
    else:
        request[f"{change}_id"] = uuid4()
    with pytest.raises(ValueError):
        PlanService(session_factory).create(**request)
    with session_factory() as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(Plan).where(Plan.team_id == plan_request["team_id"])
                    )
                )
            )
            == 1
        )
        assert session.get(Plan, result.plan_id) is not None
        rejected = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == request["task_id"],
                    Event.type == "plan_creation_rejected",
                )
            )
        )
        assert len(rejected) == 1


def test_new_policy_and_historical_basis(session_factory, plan_request) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, plan_request["task_id"])
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id, TeamPolicy.version == 1
            )
        )
        session.add(
            TeamPolicy(
                id=uuid4(), team_id=task.team_id, version=2, rules=dict(policy.rules)
            )
        )
        session.flush()
        task.policy_version = 2
        session.get(
            Objective, task.objective_id
        ).statement = "Current revised statement"
    result = PlanService(session_factory).create(**plan_request)
    with session_factory() as session:
        task = session.get(Task, result.task_id)
        plan = session.get(Plan, result.plan_id)
        assert task.policy_version == 2
        assert (
            plan.assessment_basis
            == session.get(Event, plan.accepted_event_id).payload["assessment"]["basis"]
        )
    assert (
        PlanService(session_factory).reconstruct(result.plan_id).task_id
        == result.task_id
    )


@pytest.mark.parametrize(
    ("budgets", "reason"),
    [
        ({"max_cost_usd_per_day": -1}, "invalid_policy_budget"),
        ({"max_tasks_per_day": True}, "invalid_team_policy_daily_task_quota"),
        ({"max_tasks_per_day": -1}, "invalid_team_policy_daily_task_quota"),
        ({"max_tasks_per_day": 2.5}, "invalid_team_policy_daily_task_quota"),
        ({"max_tasks_per_day": "5"}, "invalid_team_policy_daily_task_quota"),
        ({"max_tasks_per_day": None}, "invalid_team_policy_daily_task_quota"),
    ],
)
def test_policy_budget_rejection(
    session_factory, plan_request, budgets, reason
) -> None:
    with session_factory.begin() as session:
        policy = session.scalar(
            select(TeamPolicy).where(TeamPolicy.team_id == plan_request["team_id"])
        )
        policy.rules = {**policy.rules, "budgets": budgets}
    with pytest.raises(ValueError, match=reason):
        PlanService(session_factory).create(**plan_request)
    _assert_no_materialization(session_factory, plan_request)


def test_zero_daily_task_quota_is_a_valid_policy_configuration(
    session_factory, plan_request
) -> None:
    """Zero is a valid quota: it permits no start on that UTC day."""
    with session_factory.begin() as session:
        policy = session.scalar(
            select(TeamPolicy).where(TeamPolicy.team_id == plan_request["team_id"])
        )
        policy.rules = {**policy.rules, "budgets": {"max_tasks_per_day": 0}}
    result = PlanService(session_factory).create(**plan_request)
    with session_factory() as session:
        plan = session.get(Plan, result.plan_id)
        tasks = list(session.scalars(select(Task).where(Task.plan_id == plan.id)))
        assert plan is not None
        assert all(task.status == "pending" for task in tasks)


@pytest.mark.parametrize(
    ("quota", "valid"),
    [
        (0, True),
        (1, True),
        (5, True),
        (True, False),
        (False, False),
        (-1, False),
        (2.5, False),
        (2.0, False),
        ("5", False),
        (None, False),
    ],
)
def test_plan_and_admission_boundaries_agree_on_quota_configuration(
    session_factory, plan_request, quota, valid
) -> None:
    """PlanService and TaskRuntime accept exactly the same quota values."""
    with session_factory.begin() as session:
        policy = session.scalar(
            select(TeamPolicy).where(TeamPolicy.team_id == plan_request["team_id"])
        )
        policy.rules = {**policy.rules, "budgets": {"max_tasks_per_day": quota}}
    if valid:
        PlanService(session_factory).create(**plan_request)
    else:
        with pytest.raises(ValueError, match="invalid_team_policy_daily_task_quota"):
            PlanService(session_factory).create(**plan_request)

    pending_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Task(
                id=pending_id,
                team_id=plan_request["team_id"],
                objective_id=plan_request["objective_id"],
                task_type="ingest_source",
                status="pending",
                policy_version=1,
                allowed_writes=["Signal"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.0,
                    "deadline_seconds": 60,
                },
            )
        )
    reason = None
    try:
        TaskRuntime(session_factory).admit(pending_id)
    except TaskNotEligible as error:
        reason = str(error)
    if valid:
        assert reason in {None, "team_daily_task_quota_exhausted"}
    else:
        assert reason == "invalid_team_policy_daily_task_quota"


def test_materialized_pending_tasks_are_not_task_starts(
    session_factory, plan_request
) -> None:
    """Materialization creates pending Tasks; it never starts one."""
    result = PlanService(session_factory).create(**plan_request)
    with session_factory() as session:
        tasks = list(
            session.scalars(select(Task).where(Task.plan_id == result.plan_id))
        )
        assert tasks
        assert all(task.status == "pending" for task in tasks)
        assert all(task.attempt_count == 0 for task in tasks)
        assert (
            list(
                session.scalars(
                    select(Event).where(
                        Event.task_id.in_([task.id for task in tasks]),
                        Event.type == "task_started",
                    )
                )
            )
            == []
        )


@pytest.mark.parametrize("target", ["plan", "action"])
def test_plan_intent_is_immutable(session_factory, plan_request, target) -> None:
    result = PlanService(session_factory).create(**plan_request)
    with pytest.raises(DBAPIError):
        with session_factory.begin() as session:
            if target == "plan":
                session.get(Plan, result.plan_id).budget = {"max_tasks": 99}
            else:
                session.get(PlanAction, (result.plan_id, result.action_id)).action = {
                    "task_type": "changed"
                }
    assert PlanService(session_factory).reconstruct(result.plan_id) == result


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_task",
        "detached_task",
        "missing_action_mapping",
        "missing_creation_event",
        "tampered_creation_event",
        "tampered_task_scope",
        "tampered_task_budget",
    ],
)
def test_incomplete_plan_state_is_rejected_not_repaired(
    session_factory, plan_request, corruption
) -> None:
    """Incomplete or inconsistent durable state fails clearly."""
    second_id = _add_second_action(session_factory, plan_request)
    result = PlanService(session_factory).create(**plan_request)
    with session_factory.begin() as session:
        if corruption == "missing_task":
            session.execute(delete(Task).where(Task.id == result.task_ids[0]))
        elif corruption == "detached_task":
            task = session.get(Task, result.task_ids[0])
            task.plan_id = None
            task.plan_action_id = None
        elif corruption == "missing_action_mapping":
            task = session.get(Task, result.task_ids[0])
            task.plan_id = None
            task.plan_action_id = None
            session.flush()
            session.execute(
                delete(PlanAction).where(
                    PlanAction.plan_id == result.plan_id,
                    PlanAction.action_id == result.action_ids[0],
                )
            )
        elif corruption == "missing_creation_event":
            session.execute(
                delete(Event).where(
                    Event.task_id == plan_request["task_id"],
                    Event.type == "plan_created",
                )
            )
        elif corruption == "tampered_creation_event":
            event = session.get(Event, result.event_id)
            event.payload = {
                **event.payload,
                "materialized_task_ids": [str(uuid4())],
            }
        elif corruption == "tampered_task_scope":
            session.get(Task, result.task_ids[0]).allowed_writes = []
        else:
            session.get(Task, result.task_ids[0]).budget = {"max_tool_calls": 9}
    with pytest.raises(ValueError, match="recorded_plan_creation_corrupt"):
        PlanService(session_factory).reconstruct(result.plan_id)
    assert second_id in result.action_ids


def test_tampered_accepted_provenance_is_rejected(
    session_factory, plan_request
) -> None:
    result = PlanService(session_factory).create(**plan_request)
    with session_factory.begin() as session:
        accepted = session.get(Event, plan_request["accepted_event_id"])
        accepted.payload = {**accepted.payload, "proposal_json": "{}"}
    with pytest.raises(ValueError):
        PlanService(session_factory).reconstruct(result.plan_id)
    with session_factory() as session:
        assert session.get(Plan, result.plan_id) is not None


def test_retry_does_not_repair_incomplete_plan_state(
    session_factory, plan_request
) -> None:
    """A retry of a corrupted materialization fails; it never re-invents rows."""
    result = PlanService(session_factory).create(**plan_request)
    with session_factory.begin() as session:
        session.execute(delete(Task).where(Task.id == result.task_ids[0]))
    with pytest.raises(ValueError, match="recorded_plan_creation_corrupt"):
        PlanService(session_factory).create(**plan_request)
    with session_factory() as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(Plan).where(Plan.team_id == plan_request["team_id"])
                    )
                )
            )
            == 1
        )
        assert (
            len(
                list(
                    session.scalars(
                        select(Task).where(Task.plan_id == result.plan_id)
                    )
                )
            )
            == 0
        )


def _add_second_create_plan_task(
    session_factory: sessionmaker[Session], request: dict
) -> UUID:
    second_task_id = uuid4()
    with session_factory.begin() as session:
        task = session.get(Task, request["task_id"])
        session.add(
            Task(
                id=second_task_id,
                team_id=task.team_id,
                objective_id=task.objective_id,
                task_type="create_plan",
                status="running",
                policy_version=task.policy_version,
                allowed_writes=["Plan"],
                budget=dict(task.budget),
            )
        )
    return second_task_id


def test_accepted_strategy_cannot_be_materialized_by_two_tasks(
    session_factory, plan_request
) -> None:
    """One accepted Strategy materializes as one Plan."""
    service = PlanService(session_factory)
    result = service.create(**plan_request)
    second_task_id = _add_second_create_plan_task(session_factory, plan_request)
    with pytest.raises(ValueError, match="accepted_proposal_already_materialized"):
        service.create(**{**plan_request, "task_id": second_task_id})
    with session_factory() as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(Plan).where(Plan.team_id == plan_request["team_id"])
                    )
                )
            )
            == 1
        )
        rejected = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == second_task_id,
                    Event.type == "plan_creation_rejected",
                )
            )
        )
        assert len(rejected) == 1
        assert (
            rejected[0].payload["reason"]
            == "accepted_proposal_already_materialized"
        )
    assert service.reconstruct(result.plan_id) == result


def test_concurrent_materialization_of_one_accepted_strategy_has_one_winner(
    session_factory, plan_request
) -> None:
    service = PlanService(session_factory)
    second_task_id = _add_second_create_plan_task(session_factory, plan_request)
    barrier = Barrier(2)

    def claim(task_id: UUID) -> object:
        barrier.wait(timeout=5)
        try:
            return service.create(**{**plan_request, "task_id": task_id})
        except ValueError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(claim, [plan_request["task_id"], second_task_id])
        )

    results = [outcome for outcome in outcomes if isinstance(outcome, PlanResult)]
    failures = [
        outcome for outcome in outcomes if isinstance(outcome, ValueError)
    ]
    assert len(results) == 1
    assert len(failures) == 1
    assert str(failures[0]) == "accepted_proposal_already_materialized"
    with session_factory() as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(Plan).where(Plan.team_id == plan_request["team_id"])
                    )
                )
            )
            == 1
        )
        assert (
            len(
                list(
                    session.scalars(
                        select(Event).where(
                            Event.task_id.in_(
                                [plan_request["task_id"], second_task_id]
                            ),
                            Event.type == "plan_created",
                        )
                    )
                )
            )
            == 1
        )


def test_materialized_task_uses_existing_ingestion(
    session_factory, plan_request, snapshot_store: SnapshotStore
) -> None:
    result = PlanService(session_factory).create(**plan_request)
    with session_factory.begin() as session:
        task = session.get(Task, result.task_id)
        assert task.status == "pending"
        task.status = "running"
        action = session.get(
            PlanAction, (result.plan_id, task.plan_action_id)
        ).action
    content = b"R5 source material"
    proposal = IngestionProposal(
        task_id=result.task_id,
        origin_url=action["origin_url"],
        source_type=action["source_type"],
        fetched_at=datetime.now(timezone.utc),
        content=content,
        claimed_content_hash=f"sha256:{hashlib.sha256(content).hexdigest()}",
    )
    service = IngestionService(session_factory, snapshot_store)
    assert service.ingest(proposal).outcome == "signal_ingested"
    assert service.ingest(proposal).outcome == "replayed"


def test_plan_creation_terminalizes_through_task_runtime_and_replays(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    plan_request: dict[str, Any],
) -> None:
    started_at = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        task = session.get(Task, plan_request["task_id"])
        assert task is not None
        task.attempt_count = 1
        session.add(
            Event(
                id=uuid4(),
                task_id=task.id,
                type="task_started",
                payload={"attempt_count": 1},
                created_at=started_at,
            )
        )

    result = PlanService(session_factory).create(**plan_request)
    observation = TerminalObservation(
        task_id=plan_request["task_id"],
        attempt=1,
        result_category="success_plan_created",
        observed_at=started_at,
        plan_id=result.plan_id,
        plan_event_id=result.event_id,
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    first = runtime.finalize(observation)
    replay = runtime.finalize(observation)

    assert first.status == "done"
    assert replay.replayed is True
    assert replay.outcome_id == first.outcome_id
    with session_factory() as session:
        task = session.get(Task, plan_request["task_id"])
        assert task is not None and task.status == "done"
        completed = session.scalar(
            select(Event).where(
                Event.task_id == task.id, Event.type == "task_completed"
            )
        )
        assert completed is not None
        assert completed.payload["result_category"] == "success_plan_created"
        assert completed.payload["plan_id"] == str(result.plan_id)
        assert completed.payload["plan_event_id"] == str(result.event_id)



def test_interrupted_plan_creation_recovers_committed_materialization(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    plan_request: dict[str, Any],
) -> None:
    started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    with session_factory.begin() as session:
        task = session.get(Task, plan_request["task_id"])
        assert task is not None
        task.attempt_count = 1
        session.add(
            Event(
                id=uuid4(),
                task_id=task.id,
                type="task_started",
                payload={"attempt_count": 1},
                created_at=started_at,
            )
        )

    plan = PlanService(session_factory).create(**plan_request)
    runtime = TaskRuntime(session_factory, snapshot_store)
    recovered = runtime.recover_interrupted(now=datetime.now(timezone.utc))

    assert plan_request["task_id"] in recovered.completed
    assert plan_request["task_id"] not in recovered.retried
    with session_factory() as session:
        task = session.get(Task, plan_request["task_id"])
        assert task is not None and task.status == "done"
        outcome = session.scalar(
            select(Outcome).where(
                Outcome.recorded_by_task_id == plan_request["task_id"],
                Outcome.outcome_type == "task_execution",
            )
        )
        assert outcome is not None
        assert outcome.observed_at == started_at
        completion = session.scalar(
            select(Event).where(
                Event.task_id == plan_request["task_id"],
                Event.type == "task_completed",
            )
        )
        assert completion is not None
        assert completion.payload["result_category"] == "success_plan_created"
        assert completion.payload["plan_id"] == str(plan.plan_id)
        assert completion.payload["plan_event_id"] == str(plan.event_id)
        assert session.scalar(
            select(Outcome.id).where(
                Outcome.recorded_by_task_id == plan_request["task_id"]
            )
        ) == outcome.id
