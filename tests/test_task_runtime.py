"""Application-controlled pending-to-running Task admission tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Objective, Plan, PlanAction, Task, Team, TeamPolicy
from core.objectives import TaskNotFound
from core.task_runtime import TaskNotEligible, TaskRuntime


@pytest.fixture
def pending_task(session_factory: sessionmaker[Session]) -> Iterator[UUID]:
    team_id, policy_id, task_id = uuid4(), uuid4(), uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="runtime_test", status="active"))
        session.flush()
        session.add(TeamPolicy(id=policy_id, team_id=team_id, version=1, rules={}))
        session.flush()
        session.add(
            Task(
                id=task_id,
                team_id=team_id,
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
    try:
        yield task_id
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


@pytest.fixture
def linked_task_graph(request, session_factory, pending_task) -> Iterator[dict]:
    scenario = request.param
    prerequisite_ids = [uuid4(), uuid4()]
    dependent_action_id, plan_id, objective_id, owner_id = (uuid4() for _ in range(4))
    owner_event_id = uuid4()
    statuses = {
        "completed": ["done", "done"],
        "pending": ["pending"],
        "failed": ["failed"],
        "multiple": ["done", "pending"],
        "unresolved": ["done"],
    }[scenario]
    prerequisites = prerequisite_ids[:len(statuses)]
    if scenario == "unresolved":
        prerequisites = prerequisite_ids

    with session_factory.begin() as session:
        dependent = session.get(Task, pending_task)
        objective = Objective(
            id=objective_id,
            team_id=dependent.team_id,
            statement="Test Plan prerequisites",
            status="active",
        )
        owner = Task(
            id=owner_id,
            team_id=dependent.team_id,
            objective_id=objective_id,
            task_type="create_plan",
            status="running",
            policy_version=dependent.policy_version,
            allowed_writes=["Plan"],
            budget=dependent.budget,
        )
        session.add(objective)
        session.add(owner)
        session.flush()
        session.add(
            Event(
                id=owner_event_id,
                task_id=owner_id,
                type="plan_created",
                payload={},
                created_at=datetime.now(timezone.utc),
            )
        )
        session.flush()
        session.add(
            Plan(
                id=plan_id,
                team_id=dependent.team_id,
                objective_id=objective_id,
                created_by_task_id=owner_id,
                accepted_event_id=owner_event_id,
                proposal_hash="test",
                assessment_basis={},
                assessment_created_at="test",
                budget={},
                completion_condition="test",
                status="active",
            )
        )
        session.flush()
        session.add_all(
            [
                PlanAction(
                    plan_id=plan_id,
                    action_id=action_id,
                    action={"id": str(action_id), "prerequisites": []},
                )
                for action_id in prerequisite_ids
            ]
            + [
                PlanAction(
                    plan_id=plan_id,
                    action_id=dependent_action_id,
                    action={
                        "id": str(dependent_action_id),
                        "prerequisites": [
                            str(action_id) for action_id in prerequisites
                        ],
                    },
                )
            ]
        )
        session.flush()
        linked_ids = prerequisite_ids[:len(statuses)]
        session.add_all(
            [
                Task(
                    id=uuid4(),
                    team_id=dependent.team_id,
                    objective_id=objective_id,
                    plan_id=plan_id,
                    plan_action_id=action_id,
                    task_type="ingest_source",
                    status=status,
                    policy_version=dependent.policy_version,
                    allowed_writes=["Signal"],
                    budget=dependent.budget,
                )
                for action_id, status in zip(linked_ids, statuses, strict=True)
            ]
        )
        dependent.objective_id = objective_id
        dependent.plan_id = plan_id
        dependent.plan_action_id = dependent_action_id
        session.flush()

    try:
        yield {"task_id": pending_task, "plan_id": plan_id, "owner_id": owner_id}
    finally:
        with session_factory.begin() as session:
            dependent = session.get(Task, pending_task)
            dependent.plan_id = None
            dependent.plan_action_id = None
            dependent.objective_id = None
            session.flush()
            session.execute(
                delete(Task).where(Task.plan_id == plan_id, Task.id != pending_task)
            )
            session.execute(delete(PlanAction).where(PlanAction.plan_id == plan_id))
            session.execute(delete(Plan).where(Plan.id == plan_id))
            session.execute(
                delete(Event).where(Event.task_id.in_([pending_task, owner_id]))
            )
            session.execute(delete(Task).where(Task.id == owner_id))
            session.execute(delete(Objective).where(Objective.id == objective_id))


@pytest.mark.parametrize("linked_task_graph", ["completed"], indirect=True)
def test_admission_accepts_plan_task_after_all_prerequisites_complete(
    session_factory, linked_task_graph
) -> None:
    TaskRuntime(session_factory).admit(linked_task_graph["task_id"])
    with session_factory() as session:
        task = session.get(Task, linked_task_graph["task_id"])
        assert task.status == "running" and task.attempt_count == 1


@pytest.mark.parametrize(
    "linked_task_graph",
    ["pending", "failed", "multiple", "unresolved"],
    indirect=True,
)
def test_admission_rejects_incomplete_plan_prerequisites(
    session_factory, linked_task_graph
) -> None:
    task_id = linked_task_graph["task_id"]
    with pytest.raises(TaskNotEligible, match="plan_prerequisite_not_done"):
        TaskRuntime(session_factory).admit(task_id)
    with session_factory() as session:
        task = session.get(Task, task_id)
        assert task.status == "pending" and task.attempt_count == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.task_id == task_id, Event.type == "task_started")
            )
            == 0
        )


def test_admission_transitions_and_audits(session_factory, pending_task) -> None:
    result = TaskRuntime(session_factory).admit(pending_task)
    with session_factory() as session:
        task = session.get(Task, pending_task)
        events = list(
            session.scalars(select(Event).where(Event.task_id == pending_task))
        )
        assert task is not None and task.status == "running" and task.attempt_count == 1
        assert len(events) == 1 and events[0].id == result.event_id
        assert events[0].type == "task_started"
        assert events[0].payload == {
            "from_status": "pending",
            "to_status": "running",
            "attempt_count": 1,
        }


@pytest.mark.parametrize("status", ["running", "done", "failed", "unknown"])
def test_non_pending_task_cannot_be_admitted(
    session_factory, pending_task, status
) -> None:
    with session_factory.begin() as session:
        session.get(Task, pending_task).status = status
    with pytest.raises(TaskNotEligible, match="task_not_pending"):
        TaskRuntime(session_factory).admit(pending_task)
    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.task_id == pending_task)
            )
            == 0
        )


def test_missing_task_fails(session_factory) -> None:
    with pytest.raises(TaskNotFound):
        TaskRuntime(session_factory).admit(uuid4())


@pytest.mark.parametrize("mutation", ["inactive_team", "bad_budget"])
def test_eligibility_prerequisites(session_factory, pending_task, mutation) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, pending_task)
        if mutation == "inactive_team":
            session.get(Team, task.team_id).status = "paused"
        else:
            task.budget = {
                "max_tool_calls": -1,
                "max_cost_usd": 0.0,
                "deadline_seconds": 60,
            }
    with pytest.raises(TaskNotEligible):
        TaskRuntime(session_factory).admit(pending_task)
    with session_factory() as session:
        task = session.get(Task, pending_task)
        assert task.status == "pending" and task.attempt_count == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.task_id == pending_task)
            )
            == 0
        )


def test_concurrent_admission_has_one_winner(session_factory, pending_task) -> None:
    barrier = Barrier(2)

    def claim() -> bool:
        barrier.wait(timeout=5)
        try:
            TaskRuntime(session_factory).admit(pending_task)
            return True
        except TaskNotEligible:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: claim(), range(2)))
    assert outcomes.count(True) == 1
    with session_factory() as session:
        task = session.get(Task, pending_task)
        assert task.status == "running" and task.attempt_count == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.task_id == pending_task, Event.type == "task_started")
            )
            == 1
        )


def test_transaction_failure_rolls_back_task_and_event(
    session_factory, database_engine, pending_task
) -> None:
    from uuid import uuid4

    from sqlalchemy import text

    suffix = uuid4().hex
    function, trigger = f"fail_task_start_{suffix}", f"fail_task_start_tr_{suffix}"
    with database_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE FUNCTION {function}() RETURNS trigger AS $$ BEGIN "
                "RAISE EXCEPTION 'injected Event failure'; END; $$ LANGUAGE plpgsql"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON events "
                f"FOR EACH ROW WHEN (NEW.type = 'task_started') "
                f"EXECUTE FUNCTION {function}()"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            TaskRuntime(session_factory).admit(pending_task)
        with session_factory() as session:
            task = session.get(Task, pending_task)
            assert task.status == "pending" and task.attempt_count == 0
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Event)
                    .where(Event.task_id == pending_task)
                )
                == 0
            )
    finally:
        with database_engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER {trigger} ON events"))
            connection.execute(text(f"DROP FUNCTION {function}()"))


def test_retry_requires_runtime_redelivery_not_second_claim(
    session_factory, pending_task
) -> None:
    service = TaskRuntime(session_factory)
    first = service.admit(pending_task)
    with pytest.raises(TaskNotEligible, match="task_not_pending"):
        service.admit(pending_task)
    with session_factory() as session:
        task = session.get(Task, pending_task)
        assert task.attempt_count == 1 and task.status == "running"
        assert (
            session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.task_id == pending_task, Event.type == "task_started")
            )
            == 1
        )
    assert first.attempt_count == 1
    
def test_daily_task_quota_allows_admission_below_limit(
    session_factory, pending_task
) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, pending_task)
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        policy.rules = {"budgets": {"max_tasks_per_day": 2}}

    result = TaskRuntime(session_factory).admit(pending_task)

    with session_factory() as session:
        task = session.get(Task, pending_task)
        assert task.status == "running"
        assert task.attempt_count == 1
        assert session.get(Event, result.event_id).type == "task_started"


def test_daily_task_quota_rejects_without_partial_changes(
    session_factory, pending_task
) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, pending_task)
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        policy.rules = {"budgets": {"max_tasks_per_day": 1}}
        session.add(
            Event(
                id=uuid4(),
                task_id=pending_task,
                type="task_started",
                payload={"test": "quota already consumed"},
                created_at=datetime.now(timezone.utc),
            )
        )

    with pytest.raises(
        TaskNotEligible, match="team_daily_task_quota_exhausted"
    ):
        TaskRuntime(session_factory).admit(pending_task)

    with session_factory() as session:
        task = session.get(Task, pending_task)
        assert task.status == "pending"
        assert task.attempt_count == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.task_id == pending_task,
                    Event.type == "task_started",
                )
            )
            == 1
        )


def test_daily_task_quota_counts_successful_retries_as_new_starts(
    session_factory, pending_task
) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, pending_task)
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        policy.rules = {"budgets": {"max_tasks_per_day": 2}}

    service = TaskRuntime(session_factory)
    first = service.admit(pending_task)

    # Simulate a retry being made eligible again by the existing runtime.
    with session_factory.begin() as session:
        task = session.get(Task, pending_task)
        task.status = "pending"

    second = service.admit(pending_task)

    assert first.attempt_count == 1
    assert second.attempt_count == 2

    with session_factory() as session:
        task = session.get(Task, pending_task)
        assert task.status == "running"
        assert task.attempt_count == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.task_id == pending_task,
                    Event.type == "task_started",
                )
            )
            == 2
        )


def test_concurrent_admissions_cannot_exceed_daily_team_quota(
    session_factory, pending_task
) -> None:
    second_task_id = uuid4()

    with session_factory.begin() as session:
        first_task = session.get(Task, pending_task)
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == first_task.team_id,
                TeamPolicy.version == first_task.policy_version,
            )
        )
        policy.rules = {"budgets": {"max_tasks_per_day": 1}}

        second_task = Task(
            id=second_task_id,
            team_id=first_task.team_id,
            task_type=first_task.task_type,
            status="pending",
            policy_version=first_task.policy_version,
            allowed_writes=list(first_task.allowed_writes),
            budget=dict(first_task.budget),
        )
        session.add(second_task)

    barrier = Barrier(2)

    def claim(task_id: UUID) -> bool:
        barrier.wait(timeout=5)
        try:
            TaskRuntime(session_factory).admit(task_id)
            return True
        except TaskNotEligible as error:
            if str(error) == "team_daily_task_quota_exhausted":
                return False
            raise

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(
                pool.map(claim, [pending_task, second_task_id])
            )

        assert outcomes.count(True) == 1
        assert outcomes.count(False) == 1

        with session_factory() as session:
            tasks = list(
                session.scalars(
                    select(Task).where(
                        Task.id.in_([pending_task, second_task_id])
                    )
                )
            )
            assert sum(task.status == "running" for task in tasks) == 1
            assert sum(task.attempt_count for task in tasks) == 1
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Event)
                    .join(Task, Task.id == Event.task_id)
                    .where(
                        Task.team_id == tasks[0].team_id,
                        Event.type == "task_started",
                    )
                )
                == 1
            )
    finally:
        with session_factory.begin() as session:
            session.execute(
                delete(Event).where(Event.task_id == second_task_id)
            )
            session.execute(delete(Task).where(Task.id == second_task_id))


def test_missing_daily_task_quota_preserves_unlimited_admission(
    session_factory, pending_task
) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, pending_task)
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        policy.rules = {}

    result = TaskRuntime(session_factory).admit(pending_task)

    with session_factory() as session:
        task = session.get(Task, pending_task)
        assert task.status == "running"
        assert task.attempt_count == 1
        assert session.get(Event, result.event_id).type == "task_started"


def test_zero_daily_task_quota_permits_no_start(
    session_factory, pending_task
) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, pending_task)
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        policy.rules = {"budgets": {"max_tasks_per_day": 0}}

    with pytest.raises(
        TaskNotEligible, match="team_daily_task_quota_exhausted"
    ):
        TaskRuntime(session_factory).admit(pending_task)

    with session_factory() as session:
        task = session.get(Task, pending_task)
        assert task.status == "pending"
        assert task.attempt_count == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.task_id == pending_task, Event.type == "task_started")
            )
            == 0
        )


@pytest.mark.parametrize("quota", [True, False, -1, 2.5, 2.0, "5", None])
def test_invalid_daily_task_quota_is_rejected(
    session_factory, pending_task, quota
) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, pending_task)
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        policy.rules = {"budgets": {"max_tasks_per_day": quota}}

    with pytest.raises(
        TaskNotEligible, match="invalid_team_policy_daily_task_quota"
    ):
        TaskRuntime(session_factory).admit(pending_task)

    with session_factory() as session:
        task = session.get(Task, pending_task)
        assert task.status == "pending"
        assert task.attempt_count == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.task_id == pending_task, Event.type == "task_started")
            )
            == 0
        )


def test_daily_task_quota_window_is_the_current_utc_day(
    session_factory, pending_task
) -> None:
    """A start before the current UTC day does not consume today's quota."""
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with session_factory.begin() as session:
        task = session.get(Task, pending_task)
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        policy.rules = {"budgets": {"max_tasks_per_day": 1}}
        session.add(
            Event(
                id=uuid4(),
                task_id=pending_task,
                type="task_started",
                payload={"from": "previous_utc_day"},
                created_at=day_start - timedelta(microseconds=1),
            )
        )

    result = TaskRuntime(session_factory).admit(pending_task)

    with session_factory() as session:
        task = session.get(Task, pending_task)
        assert task.status == "running" and task.attempt_count == 1
        assert session.get(Event, result.event_id).created_at >= day_start


def test_daily_task_quota_counts_a_start_at_the_utc_day_boundary(
    session_factory, pending_task
) -> None:
    """A start at exactly 00:00:00 UTC belongs to the current UTC day."""
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with session_factory.begin() as session:
        task = session.get(Task, pending_task)
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        policy.rules = {"budgets": {"max_tasks_per_day": 1}}
        session.add(
            Event(
                id=uuid4(),
                task_id=pending_task,
                type="task_started",
                payload={"from": "utc_day_start"},
                created_at=day_start,
            )
        )

    with pytest.raises(
        TaskNotEligible, match="team_daily_task_quota_exhausted"
    ):
        TaskRuntime(session_factory).admit(pending_task)

    with session_factory() as session:
        task = session.get(Task, pending_task)
        assert task.status == "pending"
        assert task.attempt_count == 0


def test_daily_task_quota_counts_only_the_owning_team(
    session_factory, pending_task
) -> None:
    """Another Team's starts never consume this Team's quota."""
    other_team_id, other_policy_id, other_task_id = uuid4(), uuid4(), uuid4()
    with session_factory.begin() as session:
        task = session.get(Task, pending_task)
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        policy.rules = {"budgets": {"max_tasks_per_day": 1}}
        session.add(Team(id=other_team_id, domain="other", status="active"))
        session.flush()
        session.add(
            TeamPolicy(id=other_policy_id, team_id=other_team_id, version=1, rules={})
        )
        session.flush()
        session.add(
            Task(
                id=other_task_id,
                team_id=other_team_id,
                task_type="ingest_source",
                status="running",
                policy_version=1,
                allowed_writes=["Signal"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.0,
                    "deadline_seconds": 60,
                },
            )
        )
        session.flush()
        session.add(
            Event(
                id=uuid4(),
                task_id=other_task_id,
                type="task_started",
                payload={"from": "other_team"},
                created_at=datetime.now(timezone.utc),
            )
        )
    try:
        TaskRuntime(session_factory).admit(pending_task)
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.task_id == other_task_id))
            session.execute(delete(Task).where(Task.id == other_task_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == other_policy_id))
            session.execute(delete(Team).where(Team.id == other_team_id))

    with session_factory() as session:
        task = session.get(Task, pending_task)
        assert task.status == "running" and task.attempt_count == 1