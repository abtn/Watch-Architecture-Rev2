"""Focused PostgreSQL checks for the transient R4 boundary."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Objective, Task, Team, TeamPolicy
from core.objectives import TaskNotFound
from core.state_assessment import StateAssessmentBuilder
from core.strategy import StrategyService
from core.strategy_proposal import FakeStrategyWorker, StrategyContext


@pytest.fixture
def strategy_task(session_factory: sessionmaker[Session]) -> Iterator[UUID]:
    team_id, policy_id, objective_id, task_id = (uuid4() for _ in range(4))
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="strategy_test", status="active"))
        session.flush()
        session.add(
            TeamPolicy(
                id=policy_id,
                team_id=team_id,
                version=1,
                rules={
                    "sources": [
                        {"origin_url": "https://example.test/r4", "source_type": "feed"}
                    ],
                    "review": {"update_gating": True},
                },
            )
        )
        session.add(
            Objective(
                id=objective_id,
                team_id=team_id,
                statement="Gather source material",
                status="active",
            )
        )
        session.flush()
        session.add(
            Task(
                id=task_id,
                team_id=team_id,
                objective_id=objective_id,
                task_type="propose_strategy",
                status="running",
                policy_version=1,
                allowed_writes=[],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.0,
                    "deadline_seconds": 60,
                },
            )
        )
    try:
        yield task_id
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))
            session.execute(delete(Objective).where(Objective.id == objective_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


def _context(factory: sessionmaker[Session], task_id: UUID) -> StrategyContext:
    with factory() as session:
        task = session.get(Task, task_id)
        assert task is not None and task.objective_id is not None
        objective_id = task.objective_id
    assessment = StateAssessmentBuilder(factory).build(
        objective_id, created_at=datetime(2026, 10, 6, tzinfo=timezone.utc)
    )
    return StrategyContext(str(task_id), assessment)


def test_acceptance_audit_restart_reconstruction_and_r5_boundary(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
) -> None:
    context = _context(session_factory, strategy_task)
    proposal = FakeStrategyWorker().propose(context)
    service = StrategyService(session_factory)
    result = service.submit(strategy_task, proposal, context.assessment)
    assert result.accepted and result.reason is None
    with session_factory() as session:
        event = session.get(Event, result.event_id)
        assert event is not None and event.task_id == strategy_task
        assert event.payload["objective_id"] == proposal.objective_id
        assert event.payload["assessment"] == json.loads(
            json.dumps(asdict(context.assessment), default=str)
        )
        assert (
            event.payload["assessment"]["basis"]["sha256"]
            == context.assessment.basis.sha256
        )
        assert event.type == "strategy_proposal_accepted"
        task = session.get(Task, strategy_task)
        assert task is not None and task.status == "running"
        assert (
            len(list(session.scalars(select(Task).where(Task.team_id == task.team_id))))
            == 1
        )
        assert set(inspect(session.connection()).get_table_names()) == {
            "alembic_version",
            "teams",
            "team_policies",
            "objectives",
            "tasks",
            "signals",
            "events",
        }
    expected = proposal.model_dump(mode="json")
    code = """
import os
import sys
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.strategy import StrategyService
engine = create_engine(os.environ["R4_DATABASE_URL"])
try:
    proposal = StrategyService(sessionmaker(engine)).reconstruct(UUID(sys.argv[1]))
    print(proposal.model_dump_json())
finally:
    engine.dispose()
"""
    bind = session_factory.kw["bind"]
    env = {
        **os.environ,
        "R4_DATABASE_URL": bind.url.render_as_string(hide_password=False),
    }
    del service, proposal, context
    process = subprocess.run(
        [sys.executable, "-c", code, str(result.event_id)],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert json.loads(process.stdout) == expected
    recovered = StrategyService(session_factory).reconstruct(result.event_id)
    assert recovered.objective_id
    assert recovered.candidate_actions[0].origin_url == "https://example.test/r4"
    # Rebuild input from durable audit, not a model transcript or live projection.
    with session_factory() as session:
        event = session.get(Event, result.event_id)
        assert event is not None
        assert recovered.model_dump(mode="json") == json.loads(
            event.payload["proposal_json"]
        )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"candidate_actions": []}, "invalid_structure"),
        ({"new_entity": "Plan"}, "invalid_structure"),
        ({"policy": {"review": False}}, "invalid_structure"),
        ({"allowed_writes": ["TeamPolicy"]}, "invalid_structure"),
        ({"event": {"type": "strategy_proposal_accepted"}}, "invalid_structure"),
        ({"memory": {"write": True}}, "invalid_structure"),
        ({"plan": {}}, "invalid_structure"),
        ({"constraints": {"max_tasks": 1, "max_cost_usd": 1.0}}, "budget_escalation"),
        ({"stop_conditions": ["anything"]}, "unsupported_stop_condition"),
        ({"constraints": {"max_tasks": 2, "max_cost_usd": 0.0}}, "task_limit_exceeded"),
        ({"objective_id": str(uuid4())}, "objective_not_found"),
        ({"reason": "   "}, "invalid_structure"),
        (
            {"constraints": {"max_tasks": True, "max_cost_usd": 0.0}},
            "invalid_structure",
        ),
    ],
)
def test_invalid_candidates_are_durably_rejected(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
    mutation: dict[str, Any],
    reason: str,
) -> None:
    context = _context(session_factory, strategy_task)
    raw = FakeStrategyWorker().propose(context).model_dump(mode="json")
    raw.update(mutation)
    result = StrategyService(session_factory).submit(
        strategy_task, raw, context.assessment
    )
    assert not result.accepted and result.reason == reason
    with session_factory() as session:
        event = session.get(Event, result.event_id)
        assert event is not None and event.task_id == strategy_task
        assert (
            event.type == "strategy_proposal_rejected"
            and event.payload["reason"] == reason
        )
    assert (
        StrategyService(session_factory)
        .submit(strategy_task, raw, context.assessment)
        .replayed
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("task_type", "update_thread", "unsupported_task_type"),
        ("tools", ["database_write"], "unauthorized_tool"),
        ("origin_url", "https://unconfigured.test", "source_not_configured"),
        ("entity_type", "Strategy", "invalid_structure"),
    ],
)
def test_capabilities_are_bounded(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
    field: str,
    value: Any,
    reason: str,
) -> None:
    context = _context(session_factory, strategy_task)
    raw = FakeStrategyWorker().propose(context).model_dump(mode="json")
    raw["candidate_actions"][0][field] = value
    result = StrategyService(session_factory).submit(
        strategy_task, raw, context.assessment
    )
    assert not result.accepted and result.reason == reason


def test_replay_conflict_and_stale_assessment(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
) -> None:
    context = _context(session_factory, strategy_task)
    proposal = FakeStrategyWorker().propose(context)
    service = StrategyService(session_factory)
    first = service.submit(strategy_task, proposal, context.assessment)
    replay = service.submit(strategy_task, proposal, context.assessment)
    assert replay.replayed and replay.event_id == first.event_id
    conflict = service.submit(
        strategy_task,
        proposal.model_copy(update={"reason": "Changed"}),
        context.assessment,
    )
    assert conflict.reason == "task_outcome_conflict"
    assert service.reconstruct(first.event_id) == proposal
    with session_factory() as session:
        events = list(
            session.scalars(select(Event).where(Event.task_id == strategy_task))
        )
        assert len([e for e in events if e.type == "strategy_proposal_accepted"]) == 1


@pytest.mark.parametrize("change", ["objective", "policy", "forged_hash"])
def test_stale_or_forged_basis_is_rejected(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
    change: str,
) -> None:
    context = _context(session_factory, strategy_task)
    proposal = FakeStrategyWorker().propose(context)
    assessment = context.assessment
    with session_factory.begin() as session:
        if change == "objective":
            objective = session.get(Objective, assessment.objective.id)
            assert objective is not None
            objective.statement = "Changed"
        elif change == "policy":
            policy = session.get(TeamPolicy, assessment.policies[0].id)
            assert policy is not None
            policy.rules = {**policy.rules, "review": {"update_gating": False}}
        else:
            assessment = replace(
                assessment, basis=replace(assessment.basis, sha256="forged")
            )
    result = StrategyService(session_factory).submit(
        strategy_task, proposal, assessment
    )
    assert result.reason == "stale_assessment"


def test_cross_team_and_missing_objective(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
) -> None:
    context = _context(session_factory, strategy_task)
    raw = FakeStrategyWorker().propose(context).model_dump(mode="json")
    other_team, other_objective = uuid4(), uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=other_team, domain="other", status="active"))
        session.flush()
        session.add(
            Objective(
                id=other_objective,
                team_id=other_team,
                statement="Other goal",
                status="active",
            )
        )
    try:
        raw["objective_id"] = str(other_objective)
        result = StrategyService(session_factory).submit(
            strategy_task, raw, context.assessment
        )
        assert result.reason == "objective_team_mismatch"
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Objective).where(Objective.id == other_objective))
            session.execute(delete(Team).where(Team.id == other_team))


def test_producer_has_only_immutable_context_and_no_durable_effects(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
) -> None:
    context = _context(session_factory, strategy_task)
    assert set(vars(context)) == {"task_id", "assessment"}
    producer = FakeStrategyWorker()
    assert vars(producer) == {}
    before = StateAssessmentBuilder(session_factory).build(
        context.assessment.objective.id,
        created_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
    )
    assert producer.propose(context) == producer.propose(context)
    assert before == StateAssessmentBuilder(session_factory).build(
        before.objective.id, created_at=datetime(2026, 10, 6, tzinfo=timezone.utc)
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("status", "pending", "task_not_running"),
        ("allowed_writes", ["Event"], "write_scope_violation"),
        ("budget", {"max_tool_calls": -1}, "invalid_task_budget"),
    ],
)
def test_task_scope_and_budget(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
    field: str,
    value: Any,
    reason: str,
) -> None:
    context = _context(session_factory, strategy_task)
    with session_factory.begin() as session:
        task = session.get(Task, strategy_task)
        assert task is not None
        setattr(task, field, value)
    result = StrategyService(session_factory).submit(
        strategy_task, FakeStrategyWorker().propose(context), context.assessment
    )
    assert result.reason == reason


def test_missing_or_wrong_task_cannot_emit_strategy_event(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
) -> None:
    context = _context(session_factory, strategy_task)
    proposal = FakeStrategyWorker().propose(context)
    with pytest.raises(TaskNotFound):
        StrategyService(session_factory).submit(uuid4(), proposal, context.assessment)
    with session_factory.begin() as session:
        task = session.get(Task, strategy_task)
        assert task is not None
        task.task_type = "ingest_source"
    with pytest.raises(ValueError, match="strategy_event_scope_violation"):
        StrategyService(session_factory).submit(
            strategy_task, proposal, context.assessment
        )
    with session_factory() as session:
        assert (
            list(session.scalars(select(Event).where(Event.task_id == strategy_task)))
            == []
        )


def test_concurrent_same_task_never_duplicates_acceptance(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
) -> None:
    context = _context(session_factory, strategy_task)
    proposal = FakeStrategyWorker().propose(context)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: StrategyService(session_factory).submit(
                    strategy_task, proposal, context.assessment
                ),
                range(2),
            )
        )
    assert any(result.accepted for result in results)
    with session_factory() as session:
        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == strategy_task,
                    Event.type == "strategy_proposal_accepted",
                )
            )
        )
        assert len(events) == 1


@pytest.mark.parametrize("change", ["scope", "team", "policy_version"])
def test_replay_revalidates_task_authority(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
    change: str,
) -> None:
    context = _context(session_factory, strategy_task)
    proposal = FakeStrategyWorker().propose(context)
    service = StrategyService(session_factory)
    accepted = service.submit(strategy_task, proposal, context.assessment)
    new_policy_id = uuid4()
    with session_factory.begin() as session:
        task = session.get(Task, strategy_task)
        assert task is not None
        if change == "scope":
            task.allowed_writes = ["Objective"]
        elif change == "team":
            team = session.get(Team, task.team_id)
            assert team is not None
            team.status = "paused"
        else:
            session.add(
                TeamPolicy(
                    id=new_policy_id,
                    team_id=task.team_id,
                    version=2,
                    rules=json.loads(context.assessment.policies[0].rules_json),
                )
            )
            session.flush()
            task.policy_version = 2
    try:
        result = service.submit(strategy_task, proposal, context.assessment)
        assert not result.accepted
        assert (
            result.reason
            == {
                "scope": "write_scope_violation",
                "team": "team_not_active",
                "policy_version": "task_outcome_conflict",
            }[change]
        )
        assert service.reconstruct(accepted.event_id) == proposal
    finally:
        if change == "policy_version":
            with session_factory.begin() as session:
                task = session.get(Task, strategy_task)
                assert task is not None
                task.policy_version = 1
                session.flush()
                session.execute(
                    delete(TeamPolicy).where(TeamPolicy.id == new_policy_id)
                )


@pytest.mark.parametrize("timestamp", ["invalid", "2026-10-06T00:00:00"])
def test_invalid_assessment_timestamp_is_audited(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
    timestamp: str,
) -> None:
    context = _context(session_factory, strategy_task)
    result = StrategyService(session_factory).submit(
        strategy_task,
        FakeStrategyWorker().propose(context),
        replace(context.assessment, created_at=timestamp),
    )
    assert result.reason == "invalid_assessment_timestamp"


def test_reconstruction_detects_tampered_or_rejected_audit(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
) -> None:
    context = _context(session_factory, strategy_task)
    service = StrategyService(session_factory)
    result = service.submit(
        strategy_task, FakeStrategyWorker().propose(context), context.assessment
    )
    with session_factory.begin() as session:
        event = session.get(Event, result.event_id)
        assert event is not None
        event.payload = {**event.payload, "proposal_json": "{}"}
    with pytest.raises(ValueError, match="proposal_hash_mismatch"):
        service.reconstruct(result.event_id)
    with pytest.raises(ValueError, match="accepted_proposal_not_found"):
        service.reconstruct(uuid4())


def test_audit_failure_is_atomic_and_does_not_mutate_objective(
    session_factory: sessionmaker[Session],
    strategy_task: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.objectives import ObjectiveService

    context = _context(session_factory, strategy_task)
    original = ObjectiveService._add_event

    def fail_after_add(*args: Any, **kwargs: Any) -> Event:
        original(*args, **kwargs)
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(ObjectiveService, "_add_event", fail_after_add)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        StrategyService(session_factory).submit(
            strategy_task, FakeStrategyWorker().propose(context), context.assessment
        )
    with session_factory() as session:
        assert (
            list(session.scalars(select(Event).where(Event.task_id == strategy_task)))
            == []
        )
        objective = session.get(Objective, context.assessment.objective.id)
        assert objective is not None
        assert (objective.statement, objective.status) == (
            context.assessment.objective.statement,
            context.assessment.objective.status,
        )
