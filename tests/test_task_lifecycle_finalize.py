"""R6-A Checkpoint 2A: terminal finalization with attempt fencing."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from typing import Any, Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Outcome, Plan, Task, Team, TeamPolicy
from core.objectives import TaskNotFound
from core.plans import PlanService
from core.snapshot_store import SnapshotStore
from core.state_assessment import _canonical_json
from core.task_runtime import (
    SignalEvidence,
    TaskNotFinalizable,
    TaskRuntime,
    TerminalObservation,
)
from tests.test_plans import plan_request  # noqa: F401

_BUDGET = {"max_tool_calls": 0, "max_cost_usd": 0.0, "deadline_seconds": 60}


@pytest.fixture
def running_task(session_factory: sessionmaker[Session]) -> Iterator[dict[str, UUID]]:
    """An active Team with a running Task admitted once (attempt_count == 1)."""
    team_id, policy_id, task_id = uuid4(), uuid4(), uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="finalize_test", status="active"))
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
    session_factory: sessionmaker[Session], snapshot_store: SnapshotStore
) -> TaskRuntime:
    return TaskRuntime(session_factory, snapshot_store)


def _success(
    context: dict[str, UUID],
    *,
    attempt: int = 1,
    category: str = "success_signal_created",
    signals: tuple[SignalEvidence, ...] | None = None,
) -> TerminalObservation:
    if signals is None:
        signals = (
            SignalEvidence(
                signal_id=uuid4(),
                snapshot_ref=f"snap://sha256/{'a' * 64}",
                content_hash=f"sha256:{'a' * 64}",
            ),
        )
    return TerminalObservation(
        task_id=context["task_id"],
        attempt=attempt,
        result_category=category,  # type: ignore[arg-type]
        observed_at=datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc),
        signals=signals,
    )


def _failure(
    context: dict[str, UUID],
    *,
    attempt: int = 1,
    reason: str = "source_redirect_not_allowed",
) -> TerminalObservation:
    return TerminalObservation(
        task_id=context["task_id"],
        attempt=attempt,
        result_category="terminal_failure",
        observed_at=datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc),
        failure_reason=reason,
    )


def _events(session_factory: sessionmaker[Session], task_id: UUID) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event).where(Event.task_id == task_id).order_by(Event.type)
            )
        )


def _outcomes(session_factory: sessionmaker[Session], task_id: UUID) -> list[Outcome]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Outcome).where(Outcome.recorded_by_task_id == task_id)
            )
        )


# --- Terminal success --------------------------------------------------------


def test_terminal_success_commits_status_event_and_outcome(
    session_factory, snapshot_store, running_task
) -> None:
    result = _runtime(session_factory, snapshot_store).finalize(_success(running_task))

    assert result.status == "done"
    assert result.replayed is False
    assert len(result.event_ids) == 1

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "done"
        assert task.completed_at is not None
        assert task.completed_at.tzinfo is not None

        outcome = session.get(Outcome, result.outcome_id)
        assert outcome is not None
        assert outcome.outcome_type == "task_execution"
        assert outcome.subject_kind == "task"
        assert outcome.subject_id == running_task["task_id"]
        assert outcome.recorded_by_task_id == running_task["task_id"]
        assert outcome.team_id == running_task["team_id"]
        assert outcome.observed_at is not None
        assert outcome.observation_snapshot_ref is not None
        assert outcome.observation_hash is not None

        event = session.get(Event, result.event_ids[0])
        assert event is not None
        assert event.type == "task_completed"
        assert event.payload["to_status"] == "done"
        assert event.payload["attempt_count"] == 1
        assert event.payload["result_category"] == "success_signal_created"

    event_types = [e.type for e in _events(session_factory, running_task["task_id"])]
    assert event_types == ["task_completed"]
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1


def test_success_no_change_is_accepted_without_signal_evidence(
    session_factory, snapshot_store, running_task
) -> None:
    observation = _success(
        running_task, category="success_no_change", signals=()
    )
    result = _runtime(session_factory, snapshot_store).finalize(observation)
    assert result.status == "done"


# --- Terminal failure --------------------------------------------------------


def test_terminal_failure_commits_status_events_and_outcome(
    session_factory, snapshot_store, running_task
) -> None:
    result = _runtime(session_factory, snapshot_store).finalize(_failure(running_task))

    assert result.status == "failed"
    assert result.replayed is False
    assert len(result.event_ids) == 2

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "failed"
        assert task.completed_at is None

        outcome = session.get(Outcome, result.outcome_id)
        assert outcome is not None
        assert outcome.outcome_type == "task_execution"

    event_types = [e.type for e in _events(session_factory, running_task["task_id"])]
    assert event_types == ["task_attempt_failed", "task_failed"]
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1


# --- Snapshot integrity ------------------------------------------------------


def test_snapshot_reproduces_canonical_bytes_and_hash(
    session_factory, snapshot_store, running_task
) -> None:
    observation = _success(running_task)
    result = _runtime(session_factory, snapshot_store).finalize(observation)

    with session_factory() as session:
        outcome = session.get(Outcome, result.outcome_id)
        assert outcome is not None
        ref = outcome.observation_snapshot_ref
        stored_hash = outcome.observation_hash
        assert ref is not None and stored_hash is not None

    content = snapshot_store.read(ref)
    assert hashlib.sha256(content).hexdigest() == stored_hash.split(":", 1)[1]
    assert ref == f"snap://sha256/{stored_hash.split(':', 1)[1]}"

    payload = _canonical_json(
        {
            "attempt": 1,
            "failure_reason": None,
            "observed_at": "2026-10-27T12:00:00.000000Z",
            "result_category": "success_signal_created",
            "signals": [
                {
                    "content_hash": observation.signals[0].content_hash,
                    "signal_id": str(observation.signals[0].signal_id),
                    "snapshot_ref": observation.signals[0].snapshot_ref,
                }
            ],
        }
    )
    assert content == payload.encode("utf-8")


# --- Fencing and state validation -------------------------------------------


def test_stale_attempt_is_rejected_without_side_effects(
    session_factory, snapshot_store, running_task
) -> None:
    with pytest.raises(TaskNotFinalizable, match="stale_attempt"):
        _runtime(session_factory, snapshot_store).finalize(
            _success(running_task, attempt=2)
        )

    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.status == "running"
        assert task.completed_at is None
    assert _events(session_factory, running_task["task_id"]) == []
    assert _outcomes(session_factory, running_task["task_id"]) == []


def test_non_running_task_cannot_be_finalized(
    session_factory, snapshot_store, running_task
) -> None:
    """A non-running, non-terminal Task is an eligibility error, not corruption."""
    with session_factory.begin() as session:
        session.get(Task, running_task["task_id"]).status = "pending"

    with pytest.raises(TaskNotFinalizable, match="task_not_running"):
        _runtime(session_factory, snapshot_store).finalize(_success(running_task))

    assert _outcomes(session_factory, running_task["task_id"]) == []


def test_missing_task_fails(session_factory, snapshot_store) -> None:
    observation = TerminalObservation(
        task_id=uuid4(),
        attempt=1,
        result_category="success_no_change",
        observed_at=datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(TaskNotFound):
        _runtime(session_factory, snapshot_store).finalize(observation)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"result_category": "unknown"}, "invalid_result_category"),
        ({"attempt": 0}, "invalid_attempt"),
        ({"failure_reason": "x"}, "failure_reason_not_allowed"),
        ({"signals": ()}, "signal_evidence_required"),
    ],
)
def test_invalid_success_observations_are_rejected(
    session_factory, snapshot_store, running_task, overrides, reason
) -> None:
    observation = _success(running_task)
    values = {
        "task_id": observation.task_id,
        "attempt": observation.attempt,
        "result_category": observation.result_category,
        "observed_at": observation.observed_at,
        "signals": observation.signals,
        "failure_reason": observation.failure_reason,
    }
    values.update(overrides)
    with pytest.raises(TaskNotFinalizable, match=reason):
        _runtime(session_factory, snapshot_store).finalize(
            TerminalObservation(**values)  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"failure_reason": None}, "failure_reason_required"),
        ({"failure_reason": "   "}, "failure_reason_required"),
    ],
)
def test_invalid_failure_observations_are_rejected(
    session_factory, snapshot_store, running_task, overrides, reason
) -> None:
    observation = _failure(running_task)
    values = {
        "task_id": observation.task_id,
        "attempt": observation.attempt,
        "result_category": observation.result_category,
        "observed_at": observation.observed_at,
        "signals": observation.signals,
        "failure_reason": observation.failure_reason,
    }
    values.update(overrides)
    with pytest.raises(TaskNotFinalizable, match=reason):
        _runtime(session_factory, snapshot_store).finalize(
            TerminalObservation(**values)  # type: ignore[arg-type]
        )


def test_naive_timestamp_is_rejected(
    session_factory, snapshot_store, running_task
) -> None:
    observation = TerminalObservation(
        task_id=running_task["task_id"],
        attempt=1,
        result_category="success_no_change",
        observed_at=datetime(2026, 10, 27, 12, 0),
    )
    with pytest.raises(TaskNotFinalizable, match="observed_at_not_timezone_aware"):
        _runtime(session_factory, snapshot_store).finalize(observation)


# --- Replay and conflicts ----------------------------------------------------


def test_identical_success_replay_returns_original_ids(
    session_factory, snapshot_store, running_task
) -> None:
    runtime = _runtime(session_factory, snapshot_store)
    observation = _success(running_task)
    first = runtime.finalize(observation)
    replay = runtime.finalize(observation)

    assert replay.replayed is True
    assert replay.outcome_id == first.outcome_id
    assert replay.event_ids == first.event_ids
    assert replay.status == "done"

    assert len(_outcomes(session_factory, running_task["task_id"])) == 1
    assert len(_events(session_factory, running_task["task_id"])) == 1


def test_identical_failure_replay_returns_both_event_ids(
    session_factory, snapshot_store, running_task
) -> None:
    runtime = _runtime(session_factory, snapshot_store)
    observation = _failure(running_task)
    first = runtime.finalize(observation)
    replay = runtime.finalize(observation)

    assert replay.replayed is True
    assert replay.outcome_id == first.outcome_id
    assert replay.event_ids == first.event_ids
    assert len(replay.event_ids) == 2

    assert len(_outcomes(session_factory, running_task["task_id"])) == 1
    assert len(_events(session_factory, running_task["task_id"])) == 2


def test_conflicting_observation_is_rejected_without_overwrite(
    session_factory, snapshot_store, running_task
) -> None:
    runtime = _runtime(session_factory, snapshot_store)
    first = runtime.finalize(_success(running_task))

    conflicting = _success(
        running_task,
        signals=(
            SignalEvidence(
                signal_id=uuid4(),
                snapshot_ref=f"snap://sha256/{'b' * 64}",
                content_hash=f"sha256:{'b' * 64}",
            ),
        ),
    )
    with pytest.raises(TaskNotFinalizable, match="task_outcome_conflict"):
        runtime.finalize(conflicting)

    with session_factory() as session:
        outcome = session.get(Outcome, first.outcome_id)
        assert outcome is not None
        assert outcome.observation_snapshot_ref is not None
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1
    assert len(_events(session_factory, running_task["task_id"])) == 1


def test_conflicting_result_category_is_rejected(
    session_factory, snapshot_store, running_task
) -> None:
    runtime = _runtime(session_factory, snapshot_store)
    runtime.finalize(_success(running_task))

    with pytest.raises(TaskNotFinalizable, match="task_outcome_conflict"):
        runtime.finalize(_failure(running_task))


@pytest.mark.parametrize("status", ["done", "failed"])
def test_terminal_task_without_outcome_is_reported_as_corrupt(
    session_factory, snapshot_store, running_task, status
) -> None:
    with session_factory.begin() as session:
        session.get(Task, running_task["task_id"]).status = status

    with pytest.raises(
        TaskNotFinalizable, match="recorded_terminal_outcome_corrupt"
    ):
        _runtime(session_factory, snapshot_store).finalize(_success(running_task))

    assert _outcomes(session_factory, running_task["task_id"]) == []


def test_terminal_outcome_without_events_is_reported_as_corrupt(
    session_factory, snapshot_store, running_task
) -> None:
    runtime = _runtime(session_factory, snapshot_store)
    observation = _success(running_task)
    result = runtime.finalize(observation)

    with session_factory.begin() as session:
        session.execute(delete(Event).where(Event.task_id == running_task["task_id"]))

    with pytest.raises(TaskNotFinalizable, match="recorded_terminal_events_corrupt"):
        runtime.finalize(observation)
    assert result.outcome_id is not None


# --- Concurrency -------------------------------------------------------------


def test_concurrent_finalization_has_one_winner(
    session_factory, snapshot_store, running_task
) -> None:
    runtime = _runtime(session_factory, snapshot_store)
    observation = _success(running_task)
    barrier = Barrier(2)

    def finalize() -> Any:
        barrier.wait(timeout=5)
        try:
            return runtime.finalize(observation)
        except TaskNotFinalizable as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: finalize(), range(2)))

    # Exactly one request commits; the other observes the committed terminal
    # state and replays it. Neither may create a second Outcome or Event.
    committed = [r for r in results if not isinstance(r, Exception) and not r.replayed]
    replayed = [r for r in results if not isinstance(r, Exception) and r.replayed]
    assert len(committed) == 1
    assert len(replayed) == 1
    assert replayed[0].outcome_id == committed[0].outcome_id
    assert replayed[0].event_ids == committed[0].event_ids
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1
    assert len(_events(session_factory, running_task["task_id"])) == 1


# --- Atomicity ---------------------------------------------------------------


def test_injected_event_failure_rolls_back_terminal_state(
    session_factory, snapshot_store, database_engine, running_task
) -> None:
    suffix = uuid4().hex
    function, trigger = f"fail_finalize_{suffix}", f"fail_finalize_tr_{suffix}"
    with database_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE FUNCTION {function}() RETURNS trigger AS $$ BEGIN "
                "RAISE EXCEPTION 'injected terminal Event failure'; END; "
                "$$ LANGUAGE plpgsql"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON events "
                f"FOR EACH ROW WHEN (NEW.type = 'task_completed') "
                f"EXECUTE FUNCTION {function}()"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            _runtime(session_factory, snapshot_store).finalize(_success(running_task))

        with session_factory() as session:
            task = session.get(Task, running_task["task_id"])
            assert task is not None
            assert task.status == "running"
            assert task.completed_at is None
        assert _events(session_factory, running_task["task_id"]) == []
        assert _outcomes(session_factory, running_task["task_id"]) == []
    finally:
        with database_engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER {trigger} ON events"))
            connection.execute(text(f"DROP FUNCTION {function}()"))


def test_injected_failure_event_rolls_back_terminal_failure_state(
    session_factory, snapshot_store, database_engine, running_task
) -> None:
    """A failure on the terminal `task_failed` Event rolls back everything."""
    suffix = uuid4().hex
    function, trigger = f"fail_term_{suffix}", f"fail_term_tr_{suffix}"
    with database_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE FUNCTION {function}() RETURNS trigger AS $$ BEGIN "
                "RAISE EXCEPTION 'injected task_failed Event failure'; END; "
                "$$ LANGUAGE plpgsql"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON events "
                f"FOR EACH ROW WHEN (NEW.type = 'task_failed') "
                f"EXECUTE FUNCTION {function}()"
            )
        )
    runtime = _runtime(session_factory, snapshot_store)
    observation = _failure(running_task)
    try:
        with pytest.raises(DBAPIError):
            runtime.finalize(observation)

        with session_factory() as session:
            task = session.get(Task, running_task["task_id"])
            assert task is not None
            assert task.status == "running"
            assert task.completed_at is None
        assert _outcomes(session_factory, running_task["task_id"]) == []
        assert _events(session_factory, running_task["task_id"]) == []
    finally:
        with database_engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER {trigger} ON events"))
            connection.execute(text(f"DROP FUNCTION {function}()"))

    # No partial terminal result may be replayed as a successful finalization.
    result = runtime.finalize(observation)
    assert result.replayed is False
    assert result.status == "failed"
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1
    event_types = [e.type for e in _events(session_factory, running_task["task_id"])]
    assert event_types == ["task_attempt_failed", "task_failed"]


def test_snapshot_orphan_is_reused_on_retry(
    session_factory, snapshot_store, database_engine, running_task
) -> None:
    suffix = uuid4().hex
    function, trigger = f"fail_once_{suffix}", f"fail_once_tr_{suffix}"
    with database_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE FUNCTION {function}() RETURNS trigger AS $$ BEGIN "
                "RAISE EXCEPTION 'injected first-attempt failure'; END; "
                "$$ LANGUAGE plpgsql"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON events "
                f"FOR EACH ROW WHEN (NEW.type = 'task_completed') "
                f"EXECUTE FUNCTION {function}()"
            )
        )
    runtime = _runtime(session_factory, snapshot_store)
    observation = _success(running_task)
    try:
        with pytest.raises(DBAPIError):
            runtime.finalize(observation)
    finally:
        with database_engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER {trigger} ON events"))
            connection.execute(text(f"DROP FUNCTION {function}()"))

    result = runtime.finalize(observation)
    assert result.replayed is False

    with session_factory() as session:
        outcome = session.get(Outcome, result.outcome_id)
        assert outcome is not None
        ref = outcome.observation_snapshot_ref
        stored_hash = outcome.observation_hash
        assert ref is not None and stored_hash is not None

    assert snapshot_store.read(ref) == _canonical_json(
        {
            "attempt": 1,
            "failure_reason": None,
            "observed_at": "2026-10-27T12:00:00.000000Z",
            "result_category": "success_signal_created",
            "signals": [
                {
                    "content_hash": observation.signals[0].content_hash,
                    "signal_id": str(observation.signals[0].signal_id),
                    "snapshot_ref": observation.signals[0].snapshot_ref,
                }
            ],
        }
    ).encode("utf-8")
    assert len(_outcomes(session_factory, running_task["task_id"])) == 1
    assert len(_events(session_factory, running_task["task_id"])) == 1


# --- Scope boundaries --------------------------------------------------------


def test_finalization_does_not_change_worker_write_scope(
    session_factory, snapshot_store, running_task
) -> None:
    _runtime(session_factory, snapshot_store).finalize(_success(running_task))
    with session_factory() as session:
        task = session.get(Task, running_task["task_id"])
        assert task is not None
        assert task.allowed_writes == ["Signal"]


def test_plan_completion_validation_is_unchanged(
    request: pytest.FixtureRequest, session_factory
) -> None:
    """The existing Plan completion validator still rejects unfinished Tasks."""
    materialization = request.getfixturevalue("plan_request")
    result = PlanService(session_factory).create(**materialization)

    with session_factory() as session:
        plan = session.get(Plan, result.plan_id)
        assert plan is not None
        # Materialized Tasks are `pending`, so completion must be rejected.
        with pytest.raises(ValueError, match="plan_tasks_not_done"):
            PlanService._validate_completion(session, plan)
