"""Focused PostgreSQL checks for the transient R4 boundary."""

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Any, Iterator, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Objective, Task, Team, TeamPolicy
from core.objectives import TaskNotFound
from core.state_assessment import StateAssessmentBuilder, _canonical_json
from core.strategy import StrategyService
from core.strategy_proposal import (
    FakeStrategyWorker,
    IntendedAction,
    StrategyConstraints,
    StrategyContext,
    StrategyProposal,
    Vision,
    Workstream,
)


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
        assert set(inspect(session.connection()).get_table_names()) >= {
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
        ({"visions": []}, "invalid_structure"),
        ({"new_entity": "Plan"}, "invalid_structure"),
        ({"policy": {"review": False}}, "invalid_structure"),
        ({"allowed_writes": ["TeamPolicy"]}, "invalid_structure"),
        ({"event": {"type": "strategy_proposal_accepted"}}, "invalid_structure"),
        ({"memory": {"write": True}}, "invalid_structure"),
        ({"plan": {}}, "invalid_structure"),
        ({"constraints": {"max_tasks": 1, "max_cost_usd": 1.0}}, "budget_escalation"),
        ({"stop_conditions": ["anything"]}, "unsupported_stop_condition"),
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
    action = raw["visions"][0]["workstreams"][0]["actions"][0]
    action[field] = value
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


def _nested_proposal(
    context: StrategyContext,
    action_count: int = 1,
    *,
    second_vision: bool = True,
    extra_workstream: bool = False,
) -> StrategyProposal:
    objective_id = context.assessment.objective.id
    actions = tuple(
        IntendedAction(
            id=uuid4(),
            purpose=f"Collect configured source {index}",
            origin_url="https://example.test/r4",
            source_type="feed",
        )
        for index in range(action_count)
    )
    workstreams: tuple[Workstream, ...] = (
        Workstream(
            id=uuid4(),
            name="Workstream A",
            purpose="Related work",
            actions=actions,
        ),
    )
    if extra_workstream:
        workstreams += (
            Workstream(
                id=uuid4(),
                name="Workstream A2",
                purpose="Additional related work",
                actions=(
                    IntendedAction(
                        id=uuid4(),
                        purpose="Another configured source",
                        origin_url="https://example.test/r4",
                        source_type="feed",
                    ),
                ),
            ),
        )
    visions: tuple[Vision, ...] = (
        Vision(
            id=uuid4(),
            name="Vision A",
            scope="Bounded A",
            boundary="Not B",
            workstreams=workstreams,
        ),
    )
    if second_vision:
        second_action = IntendedAction(
            id=uuid4(),
            purpose="Another configured source",
            origin_url="https://example.test/r4",
            source_type="feed",
            prerequisites=(actions[-1].id,) if action_count > 1 else (),
        )
        visions += (
            Vision(
                id=uuid4(),
                name="Vision B",
                scope="Bounded B",
                boundary="Not A",
                workstreams=(
                    Workstream(
                        id=uuid4(),
                        name="Workstream B",
                        purpose="Independent work",
                        actions=(second_action,),
                    ),
                ),
            ),
        )
    return StrategyProposal(
        objective_id=str(objective_id),
        approach="multi-perspective investigation",
        reason="Represent bounded concurrent work structurally.",
        visions=visions,
        constraints=StrategyConstraints(
            max_tasks=action_count + int(second_vision) + int(extra_workstream),
            max_cost_usd=0.0,
        ),
        stop_conditions=("configured_source_ingested",),
    )


def test_nested_strategy_accepts_cross_scope_dependencies(
    session_factory: sessionmaker[Session], strategy_task: UUID
) -> None:
    context = _context(session_factory, strategy_task)
    proposal = _nested_proposal(context, action_count=2, extra_workstream=True)
    result = StrategyService(session_factory).submit(
        strategy_task, proposal, context.assessment
    )
    assert result.accepted
    assert len(proposal.visions) == 2
    assert len(proposal.visions[0].workstreams) == 2
    assert len(proposal.candidate_actions) == 4
    assert proposal.visions[1].workstreams[0].actions[0].prerequisites == (
        proposal.visions[0].workstreams[0].actions[-1].id,
    )
    recovered = StrategyService(session_factory).reconstruct(result.event_id)
    assert recovered.canonical_dump() == proposal.canonical_dump()
    assert recovered.candidate_actions == proposal.candidate_actions
    with session_factory() as session:
        event = session.get(Event, result.event_id)
        assert event is not None
        assert event.payload["proposal_json"] == _canonical_json(
            proposal.canonical_dump()
        )


def test_action_prerequisite_validation(session_factory, strategy_task) -> None:
    context = _context(session_factory, strategy_task)
    proposal = _nested_proposal(context)
    base = proposal.model_dump(mode="json")
    action_a = base["visions"][0]["workstreams"][0]["actions"][0]
    action_b = base["visions"][1]["workstreams"][0]["actions"][0]

    cases = []
    missing = json.loads(json.dumps(base))
    missing["visions"][1]["workstreams"][0]["actions"][0]["prerequisites"] = [
        str(uuid4())
    ]
    cases.append((missing, "dependency_target_not_found"))
    self_link = json.loads(json.dumps(base))
    self_link["visions"][0]["workstreams"][0]["actions"][0]["prerequisites"] = [
        action_a["id"]
    ]
    cases.append((self_link, "self_dependency"))
    duplicate = json.loads(json.dumps(base))
    duplicate["visions"][1]["workstreams"][0]["actions"][0]["prerequisites"] = [
        action_a["id"],
        action_a["id"],
    ]
    cases.append((duplicate, "duplicate_dependency"))
    direct_cycle = json.loads(json.dumps(base))
    direct_cycle["visions"][0]["workstreams"][0]["actions"][0]["prerequisites"] = [
        action_b["id"]
    ]
    direct_cycle["visions"][1]["workstreams"][0]["actions"][0]["prerequisites"] = [
        action_a["id"]
    ]
    cases.append((direct_cycle, "dependency_cycle"))
    for raw, reason in cases:
        task_id = uuid4()
        with session_factory.begin() as session:
            task = session.get(Task, strategy_task)
            assert task is not None and task.objective_id is not None
            session.add(
                Task(
                    id=task_id,
                    team_id=task.team_id,
                    objective_id=task.objective_id,
                    task_type="propose_strategy",
                    status="running",
                    policy_version=task.policy_version,
                    allowed_writes=[],
                    budget=dict(task.budget),
                )
            )
        result = StrategyService(session_factory).submit(
            task_id, raw, context.assessment
        )
        assert not result.accepted and result.reason == reason
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))


def test_indirect_cycle_rejected(session_factory, strategy_task) -> None:
    context = _context(session_factory, strategy_task)
    proposal = _nested_proposal(context)
    raw = proposal.model_dump(mode="json")
    action_a = raw["visions"][0]["workstreams"][0]["actions"][0]
    action_b = raw["visions"][1]["workstreams"][0]["actions"][0]
    action_c = IntendedAction(
        id=uuid4(),
        purpose="Third source",
        origin_url="https://example.test/r4",
        source_type="feed",
        prerequisites=(UUID(action_b["id"]),),
    ).model_dump(mode="json")
    action_b["prerequisites"] = [action_a["id"]]
    action_a["prerequisites"] = [action_c["id"]]
    raw["visions"][1]["workstreams"][0]["actions"].append(action_c)
    result = StrategyService(session_factory).submit(
        strategy_task, raw, context.assessment
    )
    assert not result.accepted and result.reason == "dependency_cycle"


def test_compatibility_projection_is_read_only_and_not_serialized() -> None:
    proposal = StrategyProposal(
        objective_id=str(uuid4()),
        approach="approach",
        reason="reason",
        visions=(
            Vision(
                id=uuid4(),
                name="V",
                scope="Scope",
                boundary="Boundary",
                workstreams=(
                    Workstream(
                        id=uuid4(),
                        name="W",
                        purpose="Purpose",
                        actions=(
                            IntendedAction(
                                id=uuid4(),
                                purpose="A",
                                origin_url="https://example.test/a",
                                source_type="feed",
                            ),
                        ),
                    ),
                ),
            ),
        ),
        constraints=StrategyConstraints(max_tasks=1, max_cost_usd=0.0),
        stop_conditions=("configured_source_ingested",),
    )
    assert len(proposal.candidate_actions) == 1
    assert "candidate_actions" not in proposal.model_dump(mode="json")
    assert "candidate_actions" not in StrategyProposal.model_fields


def test_fake_strategy_identities_are_strategy_local(
    session_factory, strategy_task
) -> None:
    first = FakeStrategyWorker().propose(_context(session_factory, strategy_task))
    other_task = uuid4()
    with session_factory.begin() as session:
        source = session.get(Task, strategy_task)
        assert source is not None
        session.add(
            Task(
                id=other_task,
                team_id=source.team_id,
                objective_id=source.objective_id,
                task_type="propose_strategy",
                status="running",
                policy_version=source.policy_version,
                allowed_writes=[],
                budget=dict(source.budget),
            )
        )
    try:
        second = FakeStrategyWorker().propose(_context(session_factory, other_task))
        assert first.objective_id == second.objective_id
        assert first.visions[0].id != second.visions[0].id
        assert first.visions[0].workstreams[0].id != second.visions[0].workstreams[0].id
        assert first.candidate_actions[0].id != second.candidate_actions[0].id
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.task_id == other_task))
            session.execute(delete(Task).where(Task.id == other_task))


def test_action_count_can_be_below_max_tasks(session_factory, strategy_task) -> None:
    context = _context(session_factory, strategy_task)
    proposal = _nested_proposal(context, second_vision=False).model_copy(
        update={"constraints": StrategyConstraints(max_tasks=10, max_cost_usd=0.0)}
    )
    result = StrategyService(session_factory).submit(
        strategy_task, proposal, context.assessment
    )
    assert result.accepted


def test_legacy_accepted_strategy_is_read_only_and_explicitly_derived(
    session_factory, strategy_task
) -> None:
    context = _context(session_factory, strategy_task)
    legacy_proposal = {
        "objective_id": str(context.assessment.objective.id),
        "task_id": str(strategy_task),
        "approach": "independent_verification",
        "reason": "Use the recorded legacy proposal.",
        "candidate_actions": [
            {"task_type": "search_source", "purpose": "find a second source"},
            {"task_type": "triage_signal", "purpose": "assess the signal"},
        ],
        "constraints": {"max_tasks": 2, "max_cost_usd": 0.2},
        "stop_conditions": ["independent_evidence_found"],
        "assessment_basis": {
            "basis_hash": "legacy-basis",
            "objective_id": str(context.assessment.objective.id),
        },
    }
    digest = hashlib.sha256(_canonical_json(legacy_proposal).encode()).hexdigest()
    payload = {
        "operation": "propose_strategy",
        "objective_id": str(context.assessment.objective.id),
        "team_id": str(context.assessment.team.id),
        "task_id": str(strategy_task),
        "reason": None,
        "proposal": legacy_proposal,
        "proposal_hash": f"sha256:{digest}",
        "assessment_basis": legacy_proposal["assessment_basis"],
    }
    event_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Event(
                id=event_id,
                task_id=strategy_task,
                type="strategy_proposal_accepted",
                payload=payload,
                created_at=datetime.now(timezone.utc),
            )
        )
    service = StrategyService(session_factory)
    with pytest.raises(ValueError, match="canonical_proposal_not_found"):
        service.reconstruct(event_id)
    historical = service.reconstruct_historical(event_id)
    assert historical.record.candidate_actions[0].task_type == "search_source"
    assert historical.record.assessment_basis == legacy_proposal["assessment_basis"]
    normalized = historical.normalized_view()
    assert "No Vision scope was present" in normalized.visions[0].scope
    assert sorted(action.task_type for action in normalized.candidate_actions) == [
        "search_source",
        "triage_signal",
    ]
    assert normalized == historical.normalized_view()
    with session_factory() as session:
        stored = session.get(Event, event_id)
        assert stored is not None and stored.payload == payload
        assert "visions" not in stored.payload["proposal"]
        assert "proposal_json" not in stored.payload


def test_legacy_hash_mismatch_rejected(session_factory, strategy_task) -> None:
    context = _context(session_factory, strategy_task)
    payload = {
        "operation": "propose_strategy",
        "proposal": {
            "objective_id": str(context.assessment.objective.id),
            "task_id": str(strategy_task),
            "candidate_actions": [{"task_type": "search_source", "purpose": "look"}],
            "approach": "investigate",
            "reason": "legacy",
            "constraints": {"max_tasks": 1, "max_cost_usd": 0.0},
            "stop_conditions": ["done"],
            "assessment_basis": {
                "objective_id": str(context.assessment.objective.id),
                "basis_hash": "x",
            },
        },
        "proposal_hash": "sha256:bad",
        "team_id": str(context.assessment.team.id),
        "objective_id": str(context.assessment.objective.id),
        "task_id": str(strategy_task),
        "assessment_basis": {},
    }
    with session_factory.begin() as session:
        session.add(
            Event(
                id=uuid4(),
                task_id=strategy_task,
                type="strategy_proposal_accepted",
                payload=payload,
                created_at=datetime.now(timezone.utc),
            )
        )
        event_id = session.scalar(
            select(Event.id)
            .where(
                Event.task_id == strategy_task,
                Event.type == "strategy_proposal_accepted",
            )
            .order_by(Event.created_at.desc())
            .limit(1)
        )
    with pytest.raises(ValueError, match="proposal_hash_mismatch"):
        StrategyService(session_factory).reconstruct_historical(event_id)
    with pytest.raises(ValueError, match="canonical_proposal_not_found"):
        StrategyService(session_factory).reconstruct(event_id)


def test_nested_identity_and_canonical_ordering() -> None:
    proposal = StrategyProposal(
        objective_id=str(uuid4()),
        approach="approach",
        reason="reason",
        visions=(
            Vision(
                id=UUID(int=2),
                name="V2",
                scope="S2",
                boundary="B2",
                workstreams=(
                    Workstream(
                        id=UUID(int=20),
                        name="W2",
                        purpose="P2",
                        actions=(
                            IntendedAction(
                                id=UUID(int=200),
                                purpose="A2",
                                origin_url="https://example.test/2",
                                source_type="feed",
                            ),
                        ),
                    ),
                ),
            ),
            Vision(
                id=UUID(int=1),
                name="V1",
                scope="S1",
                boundary="B1",
                workstreams=(
                    Workstream(
                        id=UUID(int=10),
                        name="W1",
                        purpose="P1",
                        actions=(
                            IntendedAction(
                                id=UUID(int=100),
                                purpose="A1",
                                origin_url="https://example.test/1",
                                source_type="feed",
                            ),
                        ),
                    ),
                ),
            ),
        ),
        constraints=StrategyConstraints(max_tasks=2, max_cost_usd=0.0),
        stop_conditions=("configured_source_ingested",),
    )
    flat = proposal.candidate_actions
    assert [item.id for item in flat] == [UUID(int=100), UUID(int=200)]
    assert {item.vision_id for item in flat} == {UUID(int=1), UUID(int=2)}
    assert {item.workstream_id for item in flat} == {UUID(int=10), UUID(int=20)}
    canonical = proposal.canonical_dump()
    canonical_visions = cast(list[dict[str, Any]], canonical["visions"])
    assert [item["id"] for item in canonical_visions] == [
        str(UUID(int=1)),
        str(UUID(int=2)),
    ]
    reversed_proposal = proposal.model_copy(
        update={"visions": tuple(reversed(proposal.visions))}
    )
    assert reversed_proposal.canonical_dump() == canonical
    changed = proposal.model_copy(
        update={
            "visions": (
                proposal.visions[0].model_copy(update={"scope": "changed"}),
                proposal.visions[1],
            )
        }
    )
    assert changed.canonical_dump() != canonical
    changed_action = proposal.model_copy(
        update={
            "visions": (
                proposal.visions[0].model_copy(
                    update={
                        "workstreams": (
                            proposal.visions[0]
                            .workstreams[0]
                            .model_copy(
                                update={
                                    "actions": (
                                        proposal.visions[0]
                                        .workstreams[0]
                                        .actions[0]
                                        .model_copy(
                                            update={"purpose": "changed purpose"}
                                        ),
                                    )
                                }
                            ),
                        )
                    }
                ),
                proposal.visions[1],
            )
        }
    )
    assert changed_action.canonical_dump() != canonical
    linked = IntendedAction(
        id=UUID(int=300),
        purpose="dependent",
        origin_url="https://example.test/3",
        source_type="feed",
        prerequisites=(UUID(int=100),),
    )
    dependent = proposal.model_copy(
        update={
            "visions": (
                proposal.visions[0].model_copy(
                    update={
                        "workstreams": (
                            proposal.visions[0]
                            .workstreams[0]
                            .model_copy(
                                update={
                                    "actions": (
                                        *proposal.visions[0].workstreams[0].actions,
                                        linked,
                                    )
                                }
                            ),
                        )
                    }
                ),
                proposal.visions[1],
            )
        }
    )
    assert dependent.canonical_dump() != canonical
    assert "candidate_actions" not in dependent.canonical_dump()
