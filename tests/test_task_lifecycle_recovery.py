"""R6-A Checkpoint 2C: interrupted-task recovery (ADR-0030 §2)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from typing import Any, Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Outcome, Task, Team, TeamPolicy
from core.snapshot_store import SnapshotStore
from core.task_runtime import (
    FailureObservation,
    TaskNotFinalizable,
    TaskRuntime,
)

_BUDGET = {"max_tool_calls": 0, "max_cost_usd": 0.0, "deadline_seconds": 60}
_REASON = "interrupted_execution"
_STARTED_AT = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
# Strictly older than the 60-second interruption age.
_STALE_NOW = _STARTED_AT + timedelta(seconds=61)


@pytest.fixture
def running_task(session_factory: sessionmaker[Session]) -> Iterator[dict[str, UUID]]:
    """An active Team with a Task running on its first attempt."""
    team_id, policy_id, task_id = uuid4(), uuid4(), uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="recovery_test", status="active"))
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


def _start_event(
    session_factory: sessionmaker[Session],
    task_id: UUID,
    *,
    attempt: int,
    created_at: datetime,
) -> UUID:
    """Insert one `task_started` Event for a specific attempt."""
    event_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Event(
                id=event_id,
                task_id=task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": attempt,
                },
                created_at=created_at,
            )
        )
    return event_id


def _set_task(
    session_factory: sessionmaker[Session], task_id: UUID, **values: Any
) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, task_id)
        for name, value in values.items():
            setattr(task, name, value)


def _events(session_factory: sessionmaker[Session], task_id: UUID) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event)
                .where(Event.task_id == task_id)
                .order_by(Event.created_at, Event.type)
            )
        )


def _event_types(session_factory: sessionmaker[Session], task_id: UUID) -> list[str]:
    return [event.type for event in _events(session_factory, task_id)]


def _outcomes(session_factory: sessionmaker[Session], task_id: UUID) -> list[Outcome]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Outcome).where(Outcome.recorded_by_task_id == task_id)
            )
        )


def _task(session_factory: sessionmaker[Session], task_id: UUID) -> Task:
    with session_factory() as session:
        task = session.get(Task, task_id)
        assert task is not None
        return task


# --- Case A: stale running Task with attempts remaining ---------------------


def test_stale_running_task_with_attempts_remaining_returns_to_pending(
    session_factory, running_task
) -> None:
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )

    result = _runtime(session_factory).recover_interrupted(now=_STALE_NOW)

    assert result.retried == (running_task["task_id"],)
    assert result.failed == ()
    assert result.skipped == ()
    assert result.inconsistent == ()
    assert _task(session_factory, running_task["task_id"]).status == "pending"


def test_recovery_emits_exactly_the_required_retry_events(
    session_factory, running_task
) -> None:
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )

    _runtime(session_factory).recover_interrupted(now=_STALE_NOW)

    events = _events(session_factory, running_task["task_id"])
    assert [event.type for event in events] == [
        "task_started",
        "task_attempt_failed",
        "task_retry_scheduled",
    ]
    for event in events[1:]:
        assert event.payload["from_status"] == "running"
        assert event.payload["to_status"] == "pending"
        assert event.payload["attempt_count"] == 1
        assert event.payload["result_category"] == "retryable_failure"
        assert event.payload["failure_reason"] == _REASON


def test_retry_recovery_preserves_attempt_count_and_creates_no_terminal_record(
    session_factory, running_task, tmp_path: Path
) -> None:
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )

    _runtime(session_factory, SnapshotStore(tmp_path)).recover_interrupted(
        now=_STALE_NOW
    )

    task = _task(session_factory, running_task["task_id"])
    assert task.attempt_count == 1
    assert task.completed_at is None
    assert _outcomes(session_factory, running_task["task_id"]) == []
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


# --- Case B: age boundary ---------------------------------------------------


def test_task_younger_than_the_interruption_age_is_unchanged(
    session_factory, running_task
) -> None:
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )

    result = _runtime(session_factory).recover_interrupted(
        now=_STARTED_AT + timedelta(seconds=59)
    )

    assert result.retried == ()
    assert result.failed == ()
    assert result.skipped == ()
    assert _task(session_factory, running_task["task_id"]).status == "running"
    assert _event_types(session_factory, running_task["task_id"]) == ["task_started"]


def test_task_exactly_at_the_interruption_boundary_is_not_stale(
    session_factory, running_task
) -> None:
    """The accepted rule is strictly older than 60 seconds."""
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )

    result = _runtime(session_factory).recover_interrupted(
        now=_STARTED_AT + timedelta(seconds=60)
    )

    assert result.retried == ()
    assert _task(session_factory, running_task["task_id"]).status == "running"


# --- Case C: current-attempt evidence ---------------------------------------


def test_old_start_event_from_a_previous_attempt_does_not_make_a_new_attempt_stale(
    session_factory, running_task
) -> None:
    """Only the current attempt's start Event determines staleness."""
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )
    _set_task(session_factory, running_task["task_id"], attempt_count=2)
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=2,
        created_at=_STARTED_AT + timedelta(seconds=55),
    )

    result = _runtime(session_factory).recover_interrupted(now=_STALE_NOW)

    assert result.retried == ()
    assert result.failed == ()
    assert _task(session_factory, running_task["task_id"]).status == "running"


def test_running_task_without_a_current_attempt_start_is_reported_not_mutated(
    session_factory, running_task
) -> None:
    """A missing current-attempt start is inconsistent state, not a stale start."""
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )
    # The Task claims a second attempt that was never recorded as started.
    _set_task(session_factory, running_task["task_id"], attempt_count=2)

    result = _runtime(session_factory).recover_interrupted(now=_STALE_NOW)

    assert result.inconsistent == (running_task["task_id"],)
    assert result.retried == ()
    assert result.failed == ()
    task = _task(session_factory, running_task["task_id"])
    assert task.status == "running"
    assert task.attempt_count == 2
    assert _event_types(session_factory, running_task["task_id"]) == ["task_started"]
    assert _outcomes(session_factory, running_task["task_id"]) == []


# --- Case D: exhausted interrupted attempt ----------------------------------


def test_stale_task_at_max_attempts_terminalizes_as_failed(
    session_factory, snapshot_store, running_task
) -> None:
    _set_task(session_factory, running_task["task_id"], attempt_count=3)
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=3,
        created_at=_STARTED_AT,
    )

    result = _runtime(session_factory, snapshot_store).recover_interrupted(
        now=_STALE_NOW
    )

    assert result.failed == (running_task["task_id"],)
    assert result.retried == ()

    task = _task(session_factory, running_task["task_id"])
    assert task.status == "failed"
    assert task.completed_at is None
    assert task.attempt_count == 3

    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_started",
        "task_attempt_failed",
        "task_failed",
    ]
    outcomes = _outcomes(session_factory, running_task["task_id"])
    assert len(outcomes) == 1
    assert outcomes[0].outcome_type == "task_execution"
    assert outcomes[0].subject_kind == "task"
    assert outcomes[0].subject_id == running_task["task_id"]
    assert outcomes[0].observed_at == _STARTED_AT


# --- Case E: admission after recovery ---------------------------------------


def test_admission_after_recovery_increments_the_attempt_exactly_once(
    session_factory, running_task
) -> None:
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )
    service = _runtime(session_factory)
    service.recover_interrupted(now=_STALE_NOW)

    admitted = service.admit(running_task["task_id"])

    assert admitted.attempt_count == 2
    task = _task(session_factory, running_task["task_id"])
    assert task.status == "running"
    assert task.attempt_count == 2
    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_started",
        "task_attempt_failed",
        "task_retry_scheduled",
        "task_started",
    ]


# --- Case F: idempotency ----------------------------------------------------


def test_repeated_recovery_after_a_successful_retry_schedules_no_second_retry(
    session_factory, running_task
) -> None:
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )
    service = _runtime(session_factory)
    first = service.recover_interrupted(now=_STALE_NOW)
    second = service.recover_interrupted(now=_STALE_NOW)

    assert first.retried == (running_task["task_id"],)
    assert second.retried == ()
    assert second.failed == ()
    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_started",
        "task_attempt_failed",
        "task_retry_scheduled",
    ]
    assert _outcomes(session_factory, running_task["task_id"]) == []


def test_repeated_exhausted_recovery_reuses_the_same_terminal_record(
    session_factory, snapshot_store, running_task
) -> None:
    _set_task(session_factory, running_task["task_id"], attempt_count=3)
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=3,
        created_at=_STARTED_AT,
    )
    service = _runtime(session_factory, snapshot_store)

    first = service.recover_interrupted(now=_STALE_NOW)
    second = service.recover_interrupted(now=_STALE_NOW)

    assert first.failed == (running_task["task_id"],)
    # The Task is terminal, so it is no longer a candidate: the second call
    # neither duplicates nor conflicts with the committed record.
    assert second.failed == ()
    assert second.retried == ()
    assert second.inconsistent == ()

    outcomes = _outcomes(session_factory, running_task["task_id"])
    assert len(outcomes) == 1
    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_started",
        "task_attempt_failed",
        "task_failed",
    ]


def test_exhausted_recovery_is_stable_across_different_reference_times(
    session_factory, snapshot_store, running_task
) -> None:
    """The observation is tied to durable evidence, not the caller's clock."""
    _set_task(session_factory, running_task["task_id"], attempt_count=3)
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=3,
        created_at=_STARTED_AT,
    )
    service = _runtime(session_factory, snapshot_store)

    first = service.recover_interrupted(now=_STALE_NOW)
    second = service.recover_interrupted(now=_STALE_NOW + timedelta(hours=5))

    assert first.failed == (running_task["task_id"],)
    assert second.failed == ()
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1


# --- Case G: concurrency ----------------------------------------------------


def test_concurrent_recovery_calls_schedule_exactly_one_retry(
    session_factory, running_task
) -> None:
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )
    service = _runtime(session_factory)
    barrier = Barrier(2)

    def recover() -> Any:
        barrier.wait(timeout=5)
        try:
            return service.recover_interrupted(now=_STALE_NOW)
        except (TaskNotFinalizable, DBAPIError) as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: recover(), range(2)))

    retried = [
        r for r in results if not isinstance(r, Exception) and r.retried
    ]
    assert len(retried) == 1
    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_started",
        "task_attempt_failed",
        "task_retry_scheduled",
    ]
    assert _outcomes(session_factory, running_task["task_id"]) == []


def test_concurrent_exhausted_recovery_commits_one_terminal_record(
    session_factory, snapshot_store, running_task
) -> None:
    _set_task(session_factory, running_task["task_id"], attempt_count=3)
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=3,
        created_at=_STARTED_AT,
    )
    service = _runtime(session_factory, snapshot_store)
    barrier = Barrier(2)

    def recover() -> Any:
        barrier.wait(timeout=5)
        try:
            return service.recover_interrupted(now=_STALE_NOW)
        except (TaskNotFinalizable, DBAPIError) as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: recover(), range(2)))

    assert not [r for r in results if isinstance(r, Exception)]
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1
    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_started",
        "task_attempt_failed",
        "task_failed",
    ]
    assert _task(session_factory, running_task["task_id"]).status == "failed"


def test_concurrent_finalization_prevents_an_obsolete_recovery_overwrite(
    session_factory, snapshot_store, running_task
) -> None:
    """A newer terminal result wins; recovery must not overwrite it."""
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )
    service = _runtime(session_factory, snapshot_store)
    barrier = Barrier(2)

    def recover() -> Any:
        barrier.wait(timeout=5)
        try:
            return service.recover_interrupted(now=_STALE_NOW)
        except (TaskNotFinalizable, DBAPIError) as error:
            return error

    def finalize() -> Any:
        barrier.wait(timeout=5)
        try:
            return service.finalize(
                _terminal_observation(running_task["task_id"], attempt=1)
            )
        except (TaskNotFinalizable, DBAPIError) as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(recover), pool.submit(finalize)]
        results = [future.result() for future in futures]

    task = _task(session_factory, running_task["task_id"])
    outcomes = _outcomes(session_factory, running_task["task_id"])
    events = _event_types(session_factory, running_task["task_id"])

    # Exactly one durable disposition: either the retry or the terminal result.
    # The loser of the race is rejected rather than overwriting the winner.
    if task.status == "pending":
        assert events == [
            "task_started",
            "task_attempt_failed",
            "task_retry_scheduled",
        ]
        assert outcomes == []
        assert any(
            isinstance(r, TaskNotFinalizable) and str(r) == "task_not_running"
            for r in results
        )
    else:
        assert task.status == "failed"
        assert events == ["task_started", "task_attempt_failed", "task_failed"]
        assert len(outcomes) == 1


def test_recovery_skips_a_task_re_admitted_after_discovery(
    session_factory, running_task
) -> None:
    """A re-admission between discovery and the lock is not overwritten."""
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )
    service = _runtime(session_factory)

    # Simulate the race directly: discovery sees attempt 1, then the Task is
    # re-admitted to attempt 2 before recovery takes the row lock.
    candidates = service._interrupted_candidates(_STALE_NOW)
    assert [c.task_id for c in candidates] == [running_task["task_id"]]

    _set_task(session_factory, running_task["task_id"], attempt_count=2)
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=2,
        created_at=_STALE_NOW,
    )

    outcome = service._recover_candidate(candidates[0], _STALE_NOW)

    assert outcome == "skipped"
    task = _task(session_factory, running_task["task_id"])
    assert task.status == "running"
    assert task.attempt_count == 2
    assert _outcomes(session_factory, running_task["task_id"]) == []


# --- Case H: corruption -----------------------------------------------------


def test_corrupt_retry_events_are_reported_as_corruption(
    session_factory, running_task
) -> None:
    """An incomplete retry disposition is corruption, not silent repair."""
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )
    service = _runtime(session_factory)
    service.recover_interrupted(now=_STALE_NOW)

    with session_factory.begin() as session:
        session.execute(
            delete(Event).where(
                Event.task_id == running_task["task_id"],
                Event.type == "task_retry_scheduled",
            )
        )
    # Return the Task to `running` so the corrupt pair is re-examined.
    _set_task(session_factory, running_task["task_id"], status="running")

    with pytest.raises(TaskNotFinalizable, match="recorded_retry_events_corrupt"):
        service.recover_interrupted(now=_STALE_NOW)

    assert _outcomes(session_factory, running_task["task_id"]) == []


def test_corrupt_terminal_events_are_reported_as_corruption(
    session_factory, snapshot_store, running_task
) -> None:
    _set_task(session_factory, running_task["task_id"], attempt_count=3)
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=3,
        created_at=_STARTED_AT,
    )
    service = _runtime(session_factory, snapshot_store)
    service.recover_interrupted(now=_STALE_NOW)

    with session_factory.begin() as session:
        session.execute(
            delete(Event).where(
                Event.task_id == running_task["task_id"],
                Event.type == "task_failed",
            )
        )
    _set_task(session_factory, running_task["task_id"], status="running")

    with pytest.raises(
        TaskNotFinalizable, match="recorded_terminal_outcome_corrupt"
    ):
        service.recover_interrupted(now=_STALE_NOW)

    assert len(_outcomes(session_factory, running_task["task_id"])) == 1


def test_conflicting_terminal_observation_is_reported_as_conflict(
    session_factory, snapshot_store, running_task
) -> None:
    """A committed terminal result with different evidence is never overwritten."""
    _set_task(session_factory, running_task["task_id"], attempt_count=3)
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=3,
        created_at=_STARTED_AT,
    )
    service = _runtime(session_factory, snapshot_store)
    service.recover_interrupted(now=_STALE_NOW)

    # A different durable start time would produce a different observation.
    with session_factory.begin() as session:
        session.execute(
            delete(Event).where(
                Event.task_id == running_task["task_id"],
                Event.type == "task_started",
            )
        )
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=3,
        created_at=_STARTED_AT - timedelta(seconds=5),
    )
    _set_task(session_factory, running_task["task_id"], status="running")

    with pytest.raises(TaskNotFinalizable, match="task_outcome_conflict"):
        service.recover_interrupted(now=_STALE_NOW)

    assert len(_outcomes(session_factory, running_task["task_id"])) == 1


# --- Case I: scope boundaries -----------------------------------------------


def test_recovery_does_not_change_worker_write_scope_or_quota(
    session_factory, snapshot_store, running_task
) -> None:
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )
    with session_factory.begin() as session:
        task = session.get(Task, running_task["task_id"])
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        policy.rules = {"budgets": {"max_tasks_per_day": 2}}

    service = _runtime(session_factory, snapshot_store)
    service.recover_interrupted(now=_STALE_NOW)
    service.admit(running_task["task_id"])

    task = _task(session_factory, running_task["task_id"])
    assert task.allowed_writes == ["Signal"]
    assert task.status == "running"
    assert task.attempt_count == 2

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
    # The recovery retry is not a start; only the two admissions consume quota.
    assert starts == 2


def test_recovery_does_not_touch_a_task_owned_by_another_team(
    session_factory, running_task
) -> None:
    """Recovery is scoped to the stale Task, not to unrelated running Tasks."""
    other_team_id, other_policy_id, other_task_id = uuid4(), uuid4(), uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=other_team_id, domain="recovery_other", status="active"))
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
                attempt_count=1,
                max_attempts=3,
                policy_version=1,
                allowed_writes=["Signal"],
                budget=dict(_BUDGET),
            )
        )
    try:
        _start_event(
            session_factory,
            running_task["task_id"],
            attempt=1,
            created_at=_STARTED_AT,
        )
        _start_event(
            session_factory,
            other_task_id,
            attempt=1,
            created_at=_STARTED_AT + timedelta(seconds=30),
        )

        result = _runtime(session_factory).recover_interrupted(now=_STALE_NOW)

        assert result.retried == (running_task["task_id"],)
        assert _task(session_factory, other_task_id).status == "running"
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.task_id == other_task_id))
            session.execute(delete(Task).where(Task.id == other_task_id))
            session.execute(
                delete(TeamPolicy).where(TeamPolicy.id == other_policy_id)
            )
            session.execute(delete(Team).where(Team.id == other_team_id))


def test_recovery_requires_a_timezone_aware_reference_time(
    session_factory, running_task
) -> None:
    with pytest.raises(
        TaskNotFinalizable, match="reference_time_not_timezone_aware"
    ):
        _runtime(session_factory).recover_interrupted(
            now=datetime(2026, 10, 27, 12, 0)
        )


def test_recovery_does_not_disturb_an_ordinary_failure_report(
    session_factory, snapshot_store, running_task
) -> None:
    """Checkpoint 2B behavior is unchanged by the recovery path."""
    _start_event(
        session_factory,
        running_task["task_id"],
        attempt=1,
        created_at=_STARTED_AT,
    )
    service = _runtime(session_factory, snapshot_store)

    result = service.report_failure(
        FailureObservation(
            task_id=running_task["task_id"],
            attempt=1,
            observed_at=_STALE_NOW,
            reason="transient_connection_error",
            retryable=True,
        )
    )

    assert result.retry_scheduled is True
    assert _event_types(session_factory, running_task["task_id"]) == [
        "task_started",
        "task_attempt_failed",
        "task_retry_scheduled",
    ]
    assert _outcomes(session_factory, running_task["task_id"]) == []


def _terminal_observation(task_id: UUID, *, attempt: int):
    from core.task_runtime import TerminalObservation

    return TerminalObservation(
        task_id=task_id,
        attempt=attempt,
        result_category="terminal_failure",
        observed_at=_STARTED_AT,
        failure_reason="source_redirect_not_allowed",
    )
