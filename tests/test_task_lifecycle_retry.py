"""R6-A Checkpoint 2B: retry scheduling and the three-total-start limit."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from typing import Any, Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Outcome, Plan, Task, Team, TeamPolicy
from core.objectives import TaskNotFound
from core.plans import PlanService
from core.snapshot_store import SnapshotStore
from core.task_runtime import (
    FailureObservation,
    TaskNotEligible,
    TaskNotFinalizable,
    TaskRuntime,
)
from tests.test_plans import plan_request  # noqa: F401

_BUDGET = {"max_tool_calls": 0, "max_cost_usd": 0.0, "deadline_seconds": 60}
_REASON = "transient_connection_error"
_OBSERVED_AT = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def running_task(session_factory: sessionmaker[Session]) -> Iterator[dict[str, UUID]]:
    """An active Team with a Task running on its first attempt."""
    team_id, policy_id, task_id = uuid4(), uuid4(), uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="retry_test", status="active"))
        session.flush()
        session.add(TeamPolicy(id=policy_id, team_id=team_id, version=1, rules={}))
        session.flush()
        session.add(
            Task(
                id=task_id,
                team_id=team_id,
                task_type="ingest_source",
                status="running",
                attempt_count=1,
                max_attempts=3,
                policy_version=1,
                allowed_writes=["Signal"],
                budget=dict(_BUDGET),
            )
        )
    try:
        yield {"team_id": team_id, "task_id": task_id}
    finally:
        with session_factory.begin() as session:
            session.execute(
                delete(Outcome).where(Outcome.recorded_by_task_id == task_id)
            )
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


def _runtime(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore | None = None,
) -> TaskRuntime:
    return TaskRuntime(session_factory, snapshot_store)


def _observation(
    context: dict[str, UUID],
    *,
    attempt: int = 1,
    retryable: bool = True,
    reason: str = _REASON,
    observed_at: datetime = _OBSERVED_AT,
) -> FailureObservation:
    return FailureObservation(
        task_id=context["task_id"],
        attempt=attempt,
        observed_at=observed_at,
        reason=reason,
        retryable=retryable,
    )


def _event_types(session_factory: sessionmaker[Session], task_id: UUID) -> list[str]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event.type)
                .where(Event.task_id == task_id)
                .order_by(Event.type)
            )
        )


def _outcomes(session_factory: sessionmaker[Session], task_id: UUID) -> list[Outcome]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Outcome).where(Outcome.recorded_by_task_id == task_id)
            )
        )


def _events(session_factory: sessionmaker[Session], task_id: UUID) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event)
                .where(Event.task_id == task_id)
                .order_by(Event.created_at, Event.type)
            )
        )


def _set_task(
    session_factory: sessionmaker[Session], task_id: UUID, **values: Any
) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, task_id)
        for name, value in values.items():
            setattr(task, name, value)


# --- Case A: retryable failure with attempts remaining -----------------------


def test_retryable_failure_with_attempts_remaining_returns_task_to_pending(
    session_factory, running_task
) -> None:
    result = _runtime(session_factory).report_failure(_observation(running_task))

    assert result.retry_scheduled is True
    assert result.terminal is None
    assert result.status == "pending"
    assert result.attempt_count == 1

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "pending"


def test_retry_transition_emits_exactly_the_two_required_events(
    session_factory, running_task
) -> None:
    result = _runtime(session_factory).report_failure(_observation(running_task))

    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_attempt_failed",
        "task_retry_scheduled",
    ]
    assert len(result.event_ids) == 2

    with session_factory() as session:
        for event_id in result.event_ids:
            event = session.get(Event, event_id)
            assert event is not None
            assert event.payload["from_status"] == "running"
            assert event.payload["to_status"] == "pending"
            assert event.payload["attempt_count"] == 1
            assert event.payload["failure_reason"] == _REASON


def test_retry_transition_creates_no_outcome_or_snapshot(
    session_factory, running_task, tmp_path: Path
) -> None:
    """The retry path performs no Snapshot write and persists no Outcome."""
    result = _runtime(session_factory, SnapshotStore(tmp_path)).report_failure(
        _observation(running_task)
    )

    assert result.terminal is None
    assert _outcomes(session_factory, running_task["task_id"]) == []
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_retry_transition_leaves_attempt_count_and_completed_at_unchanged(
    session_factory, running_task
) -> None:
    _runtime(session_factory).report_failure(_observation(running_task))

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.attempt_count == 1
        assert task.completed_at is None


# --- Case B: non-retryable failure ------------------------------------------


def test_non_retryable_failure_delegates_to_terminal_finalization(
    session_factory, snapshot_store, running_task
) -> None:
    result = _runtime(session_factory, snapshot_store).report_failure(
        _observation(running_task, retryable=False)
    )

    assert result.retry_scheduled is False
    assert result.terminal is not None
    assert result.terminal.status == "failed"
    assert result.terminal.outcome_id is not None
    assert result.terminal.event_ids == result.event_ids

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "failed"
        assert task.completed_at is None
        assert task.attempt_count == 1

    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_attempt_failed",
        "task_failed",
    ]
    outcomes = _outcomes(session_factory, running_task["task_id"])
    assert len(outcomes) == 1
    assert outcomes[0].outcome_type == "task_execution"
    assert outcomes[0].subject_kind == "task"
    assert outcomes[0].subject_id == running_task["task_id"]
    assert outcomes[0].observation_snapshot_ref is not None


# --- Case C: retryable failure with attempts exhausted ----------------------


def test_retryable_failure_on_final_allowed_attempt_terminalizes_as_failed(
    session_factory, snapshot_store, running_task
) -> None:
    _set_task(session_factory, running_task["task_id"], attempt_count=3)

    result = _runtime(session_factory, snapshot_store).report_failure(
        _observation(running_task, attempt=3)
    )

    assert result.retry_scheduled is False
    assert result.terminal is not None
    assert result.status == "failed"

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "failed"
        assert task.completed_at is None

    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_attempt_failed",
        "task_failed",
    ]
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1


# --- Case D: reject admission after exhaustion ------------------------------


@pytest.mark.parametrize("attempt_count", [3, 4])
def test_admission_rejects_exhausted_pending_task(
    session_factory, running_task, attempt_count
) -> None:
    _set_task(
        session_factory,
        running_task["task_id"],
        status="pending",
        attempt_count=attempt_count,
    )

    with pytest.raises(TaskNotEligible, match="task_attempts_exhausted"):
        _runtime(session_factory).admit(running_task["task_id"])

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "pending"
        assert task.attempt_count == attempt_count
    assert _event_types(session_factory, running_task["task_id"]) == []


def test_exhausted_admission_is_rejected_before_consuming_quota(
    session_factory, running_task
) -> None:
    """A zero quota proves the exhaustion guard runs before the quota check."""
    _set_task(
        session_factory,
        running_task["task_id"],
        status="pending",
        attempt_count=3,
    )
    with session_factory.begin() as session:
        task = session.get(Task, running_task["task_id"])
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        policy.rules = {"budgets": {"max_tasks_per_day": 0}}

    # Zero quota would raise `team_daily_task_quota_exhausted`; the exhaustion
    # reason proves the attempt guard was consulted first.
    with pytest.raises(TaskNotEligible, match="task_attempts_exhausted"):
        _runtime(session_factory).admit(running_task["task_id"])

    assert _event_types(session_factory, running_task["task_id"]) == []


# --- Case E: re-admission after a legitimate retry --------------------------


def test_readmission_after_retry_increments_attempt_once(
    session_factory, running_task
) -> None:
    service = _runtime(session_factory)
    service.report_failure(_observation(running_task))

    result = service.admit(running_task["task_id"])

    assert result.attempt_count == 2
    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "running"
        assert task.attempt_count == 2

    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_attempt_failed",
        "task_retry_scheduled",
        "task_started",
    ]


def test_readmission_after_retry_consumes_quota_once(
    session_factory, running_task
) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, running_task["task_id"])
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        policy.rules = {"budgets": {"max_tasks_per_day": 2}}

    service = _runtime(session_factory)
    service.report_failure(_observation(running_task))
    service.admit(running_task["task_id"])

    with session_factory() as session:
        starts = session.scalar(
            select(func.count())
            .select_from(Event)
            .join(Task, Task.id == Event.task_id)
            .where(
                Task.team_id == running_task["team_id"],
                Event.type == "task_started",
            )
        )
    # One consumed unit: the retry transition itself consumed none.
    assert starts == 1


# --- Atomicity of the retry transition --------------------------------------


@pytest.mark.parametrize(
    "event_type", ["task_attempt_failed", "task_retry_scheduled"]
)
def test_injected_retry_event_failure_rolls_back_entire_transition(
    session_factory, database_engine, running_task, event_type
) -> None:
    suffix = uuid4().hex
    function, trigger = f"fail_evt_{suffix}", f"fail_evt_tr_{suffix}"
    with database_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE FUNCTION {function}() RETURNS trigger AS $$ BEGIN "
                "RAISE EXCEPTION 'injected retry Event failure'; END; "
                "$$ LANGUAGE plpgsql"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON events "
                f"FOR EACH ROW WHEN (NEW.type = '{event_type}') "
                f"EXECUTE FUNCTION {function}()"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            _runtime(session_factory).report_failure(_observation(running_task))

        with session_factory() as session:
            task = session.get(Task, running_task["task_id"])
            assert task is not None
            assert task.status == "running"
            assert task.attempt_count == 1
            assert task.completed_at is None
        assert _event_types(session_factory, running_task["task_id"]) == []
        assert _outcomes(session_factory, running_task["task_id"]) == []
    finally:
        with database_engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER {trigger} ON events"))
            connection.execute(text(f"DROP FUNCTION {function}()"))


# --- Idempotency, fencing, and conflicting reports --------------------------


def test_repeated_retry_report_is_rejected_without_second_retry_or_outcome(
    session_factory, running_task, tmp_path: Path
) -> None:
    """A duplicate retry report is rejected by its recorded disposition."""
    service = _runtime(session_factory, SnapshotStore(tmp_path))
    first = service.report_failure(_observation(running_task))

    with pytest.raises(TaskNotFinalizable, match="retry_already_scheduled"):
        service.report_failure(_observation(running_task))

    assert first.retry_scheduled is True
    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "pending"
        assert task.attempt_count == 1
        assert task.completed_at is None

    # The original pair is unchanged, nothing was added, and no terminal
    # record or observation Snapshot was produced.
    events = _events(session_factory, running_task["task_id"])
    assert [event.type for event in events] == [
        "task_attempt_failed",
        "task_retry_scheduled",
    ]
    assert {event.id for event in events} == set(first.event_ids)
    assert _outcomes(session_factory, running_task["task_id"]) == []
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


def test_missing_terminal_event_after_a_retry_is_reported_as_corrupt(
    session_factory, snapshot_store, running_task
) -> None:
    """The attempt filter must not hide a genuinely missing terminal Event."""
    service = _runtime(session_factory, snapshot_store)
    service.report_failure(_observation(running_task))
    service.admit(running_task["task_id"])
    terminal = _observation(running_task, attempt=2, retryable=False)
    service.report_failure(terminal)

    with session_factory.begin() as session:
        session.execute(
            delete(Event).where(
                Event.task_id == running_task["task_id"],
                Event.type == "task_failed",
            )
        )

    with pytest.raises(
        TaskNotFinalizable, match="recorded_terminal_events_corrupt"
    ):
        service.report_failure(terminal)


def test_corrupt_retry_event_pair_is_reported_as_corrupt(
    session_factory, snapshot_store, running_task
) -> None:
    """An incomplete retry disposition is corruption, not silent repair."""
    service = _runtime(session_factory, snapshot_store)
    service.report_failure(_observation(running_task))

    with session_factory.begin() as session:
        session.execute(
            delete(Event).where(
                Event.task_id == running_task["task_id"],
                Event.type == "task_retry_scheduled",
            )
        )

    with pytest.raises(TaskNotFinalizable, match="recorded_retry_events_corrupt"):
        service.report_failure(_observation(running_task))

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "pending"
        assert task.attempt_count == 1
    assert _outcomes(session_factory, running_task["task_id"]) == []


def test_terminal_replay_after_a_retry_returns_the_original_ids(
    session_factory, snapshot_store, running_task
) -> None:
    """A retried Task's terminal replay must not look like corrupted Events."""
    service = _runtime(session_factory, snapshot_store)

    # Attempt 1 fails retryably and returns to `pending`.
    retry = service.report_failure(_observation(running_task))
    assert retry.retry_scheduled is True
    with session_factory() as session:
        assert session.get(Task, running_task["task_id"]).status == "pending"
    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_attempt_failed",
        "task_retry_scheduled",
    ]

    # Attempt 2 is admitted, then fails terminally.
    admitted = service.admit(running_task["task_id"])
    assert admitted.attempt_count == 2
    terminal = _observation(
        running_task,
        attempt=2,
        retryable=False,
        reason="source_redirect_not_allowed",
    )
    first = service.report_failure(terminal)
    assert first.retry_scheduled is False
    assert first.terminal is not None
    assert first.terminal.replayed is False

    # The identical terminal report replays instead of reporting corruption.
    replay = service.report_failure(terminal)
    assert replay.terminal is not None
    assert replay.terminal.replayed is True
    assert replay.terminal.outcome_id == first.terminal.outcome_id
    assert replay.terminal.event_ids == first.terminal.event_ids
    assert replay.terminal.event_ids == replay.event_ids

    # Exactly one Outcome, one terminal `task_failed`, and one
    # `task_attempt_failed` for the terminal attempt; the earlier retry Events
    # are preserved and are not mistaken for duplicated terminal Events.
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1
    events = _events(session_factory, running_task["task_id"])
    assert [
        (event.type, event.payload["attempt_count"], event.payload["to_status"])
        for event in events
    ] == [
        ("task_attempt_failed", 1, "pending"),
        ("task_retry_scheduled", 1, "pending"),
        ("task_started", 2, "running"),
        ("task_attempt_failed", 2, "failed"),
        ("task_failed", 2, "failed"),
    ]

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "failed"
        assert task.attempt_count == 2
        assert task.completed_at is None


def test_stale_failure_report_cannot_affect_newer_attempt(
    session_factory, running_task
) -> None:
    service = _runtime(session_factory)
    service.report_failure(_observation(running_task))
    service.admit(running_task["task_id"])

    with pytest.raises(TaskNotFinalizable, match="stale_attempt"):
        service.report_failure(_observation(running_task, attempt=1))

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "running"
        assert task.attempt_count == 2
    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_attempt_failed",
        "task_retry_scheduled",
        "task_started",
    ]
    assert _outcomes(session_factory, running_task["task_id"]) == []


def test_identical_terminal_report_keeps_replay_behavior(
    session_factory, snapshot_store, running_task
) -> None:
    service = _runtime(session_factory, snapshot_store)
    observation = _observation(running_task, retryable=False)
    first = service.report_failure(observation)
    replay = service.report_failure(observation)

    assert first.terminal is not None and first.terminal.replayed is False
    assert replay.terminal is not None and replay.terminal.replayed is True
    assert replay.terminal.outcome_id == first.terminal.outcome_id
    assert replay.terminal.event_ids == first.terminal.event_ids
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1
    assert len(_events(session_factory, running_task["task_id"])) == 2


def test_conflicting_terminal_report_is_rejected_without_overwrite(
    session_factory, snapshot_store, running_task
) -> None:
    service = _runtime(session_factory, snapshot_store)
    first = service.report_failure(_observation(running_task, retryable=False))

    with pytest.raises(TaskNotFinalizable, match="task_outcome_conflict"):
        service.report_failure(
            _observation(running_task, retryable=False, reason="different_reason")
        )

    assert len(_outcomes(session_factory, running_task["task_id"])) == 1
    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "failed"
        outcome = session.get(Outcome, first.terminal.outcome_id)  # type: ignore[union-attr]
        assert outcome is not None
        assert outcome.observation_snapshot_ref is not None


def test_retryable_report_after_committed_terminal_failure_schedules_no_retry(
    session_factory, snapshot_store, running_task
) -> None:
    """A committed terminal result wins; a retry is never scheduled over it."""
    service = _runtime(session_factory, snapshot_store)
    first = service.report_failure(_observation(running_task, retryable=False))

    # Same attempt, same reason, same timestamp: the observation is identical,
    # so the report resolves through terminal replay rather than retrying.
    replay = service.report_failure(_observation(running_task))

    assert replay.retry_scheduled is False
    assert replay.terminal is not None and replay.terminal.replayed is True
    assert replay.terminal.outcome_id == first.terminal.outcome_id
    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "failed"
    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_attempt_failed",
        "task_failed",
    ]
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1


def test_conflicting_retryable_report_after_terminal_failure_is_rejected(
    session_factory, snapshot_store, running_task
) -> None:
    """Equal failure text alone does not make two reports identical."""
    service = _runtime(session_factory, snapshot_store)
    service.report_failure(_observation(running_task, retryable=False))

    with pytest.raises(TaskNotFinalizable, match="task_outcome_conflict"):
        service.report_failure(_observation(running_task, reason="different_reason"))

    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_attempt_failed",
        "task_failed",
    ]
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1


def test_terminal_task_without_outcome_is_still_reported_as_corrupt(
    session_factory, snapshot_store, running_task
) -> None:
    _set_task(session_factory, running_task["task_id"], status="failed")

    with pytest.raises(
        TaskNotFinalizable, match="recorded_terminal_outcome_corrupt"
    ):
        _runtime(session_factory, snapshot_store).report_failure(
            _observation(running_task)
        )

    assert _outcomes(session_factory, running_task["task_id"]) == []


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"reason": ""}, "failure_reason_required"),
        ({"reason": "   "}, "failure_reason_required"),
        ({"attempt": 0}, "invalid_attempt"),
        (
            {"observed_at": datetime(2026, 10, 27, 12, 0)},
            "observed_at_not_timezone_aware",
        ),
    ],
)
def test_invalid_failure_reports_are_rejected(
    session_factory, running_task, overrides, reason
) -> None:
    with pytest.raises(TaskNotFinalizable, match=reason):
        _runtime(session_factory).report_failure(
            _observation(running_task, **overrides)
        )

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "running"
    assert _event_types(session_factory, running_task["task_id"]) == []


def test_missing_task_fails(session_factory) -> None:
    observation = FailureObservation(
        task_id=uuid4(),
        attempt=1,
        observed_at=_OBSERVED_AT,
        reason=_REASON,
        retryable=True,
    )
    with pytest.raises(TaskNotFound):
        _runtime(session_factory).report_failure(observation)


# --- Concurrency ------------------------------------------------------------


def test_concurrent_retryable_reports_schedule_exactly_one_retry(
    session_factory, running_task
) -> None:
    service = _runtime(session_factory)
    barrier = Barrier(2)

    def report() -> Any:
        barrier.wait(timeout=5)
        try:
            return service.report_failure(_observation(running_task))
        except TaskNotFinalizable as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: report(), range(2)))

    winners = [r for r in results if not isinstance(r, Exception)]
    assert len(winners) == 1
    assert winners[0].retry_scheduled is True
    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_attempt_failed",
        "task_retry_scheduled",
    ]
    assert _outcomes(session_factory, running_task["task_id"]) == []


def test_concurrent_retryable_and_terminal_reports_commit_one_result(
    session_factory, snapshot_store, running_task
) -> None:
    """Either the retry or the terminal result wins, never both."""
    service = _runtime(session_factory, snapshot_store)
    barrier = Barrier(2)

    def report(retryable: bool) -> Any:
        barrier.wait(timeout=5)
        try:
            return service.report_failure(
                _observation(running_task, retryable=retryable)
            )
        except (TaskNotFinalizable, DBAPIError) as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(report, [True, False]))

    scheduled_retries = [
        r for r in results if not isinstance(r, Exception) and r.retry_scheduled
    ]
    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.completed_at is None
        status = task.status

    events = _event_types(session_factory, running_task["task_id"])
    outcomes = _outcomes(session_factory, running_task["task_id"])

    # Exactly one of the two conflicting reports may take durable effect: a
    # scheduled retry, or a terminal failure with one Outcome. Never both.
    assert len(outcomes) <= 1
    assert len(scheduled_retries) <= 1
    if scheduled_retries:
        assert status == "pending"
        assert events == ["task_attempt_failed", "task_retry_scheduled"]
        assert outcomes == []
    else:
        assert status == "failed"
        assert events == ["task_attempt_failed", "task_failed"]
        assert len(outcomes) == 1


def test_concurrent_exhausted_admissions_all_reject(
    session_factory, running_task
) -> None:
    _set_task(
        session_factory,
        running_task["task_id"],
        status="pending",
        attempt_count=3,
    )
    barrier = Barrier(2)

    def claim() -> bool:
        barrier.wait(timeout=5)
        try:
            _runtime(session_factory).admit(running_task["task_id"])
            return True
        except TaskNotEligible as error:
            assert str(error) == "task_attempts_exhausted"
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: claim(), range(2)))

    assert outcomes == [False, False]
    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.attempt_count == 3
    assert _event_types(session_factory, running_task["task_id"]) == []


# --- Scope boundaries -------------------------------------------------------


def test_retry_and_terminalization_do_not_change_worker_write_scope(
    session_factory, snapshot_store, running_task
) -> None:
    service = _runtime(session_factory, snapshot_store)
    service.report_failure(_observation(running_task))
    service.admit(running_task["task_id"])
    service.report_failure(_observation(running_task, attempt=2, retryable=False))

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.allowed_writes == ["Signal"]
        assert task.status == "failed"


def test_plan_completion_validation_is_unchanged(
    request: pytest.FixtureRequest, session_factory
) -> None:
    """The existing Plan completion validator still rejects unfinished Tasks."""
    materialization = request.getfixturevalue("plan_request")
    result = PlanService(session_factory).create(**materialization)

    with session_factory() as session:
        plan = session.get(Plan, result.plan_id)
        assert plan is not None
        with pytest.raises(ValueError, match="plan_tasks_not_done"):
            PlanService._validate_completion(session, plan)
