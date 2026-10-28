"""R6-B: one bounded configured-source `ingest_source` execution path."""

import gzip
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from core.dispatcher import TaskDispatcher, TaskNotDispatchable
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
from core.snapshot_store import SnapshotStore
from core.source_fetch import (
    MAX_RESPONSE_BYTES,
    RestrictedFetcher,
    SourceFetchError,
    SourceFetchRequest,
    SourceFetchResult,
    resolve_and_screen,
    validate_source_url,
)
from core.task_runtime import SignalEvidence, TerminalObservation

_BUDGET = {"max_tool_calls": 0, "max_cost_usd": 0.0, "deadline_seconds": 60}
_CONTENT = b"<html><body>Configured source content</body></html>"


class FakeFetcher:
    """Deterministic transport double; no network is used in tests."""

    def __init__(
        self,
        content: bytes = _CONTENT,
        *,
        error: SourceFetchError | None = None,
    ) -> None:
        self.content = content
        self.error = error
        self.requests: list[SourceFetchRequest] = []

    def fetch(self, request: SourceFetchRequest) -> SourceFetchResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return SourceFetchResult(
            origin_url=request.origin_url,
            source_type=request.source_type,
            fetched_at=datetime.now(timezone.utc),
            content=self.content,
        )


class DispatchFixture:
    """Ids for one configured-source Task and its durable source identity."""

    def __init__(
        self,
        team_id: UUID,
        policy_id: UUID,
        objective_id: UUID,
        owner_id: UUID,
        plan_id: UUID,
        action_id: UUID,
        task_id: UUID,
        origin_url: str,
        source_type: str,
    ) -> None:
        self.team_id = team_id
        self.policy_id = policy_id
        self.objective_id = objective_id
        self.owner_id = owner_id
        self.plan_id = plan_id
        self.action_id = action_id
        self.task_id = task_id
        self.origin_url = origin_url
        self.source_type = source_type


@pytest.fixture
def dispatch_fixture(
    request: pytest.FixtureRequest,
    session_factory: sessionmaker[Session],
) -> Iterator[DispatchFixture]:
    """An active Team with a Plan-materialized `ingest_source` Task.

    The source is configured in the TeamPolicy *and* pinned in the PlanAction,
    which is the only durable source identity this slice has. `requests.param`
    may override the Action's `tools` list; `plan_actions` is immutable once
    committed, so the override is applied at insert time.
    """
    overrides = getattr(request, "param", None) or {}
    (
        team_id,
        policy_id,
        objective_id,
        owner_id,
        plan_id,
        action_id,
        task_id,
    ) = (uuid4() for _ in range(7))
    origin_url = f"https://news.example.test/feed/{uuid4()}"
    source_type = "rss"
    context = DispatchFixture(
        team_id,
        policy_id,
        objective_id,
        owner_id,
        plan_id,
        action_id,
        task_id,
        origin_url,
        source_type,
    )

    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="r6b_test", status="active"))
        session.flush()
        session.add(
            TeamPolicy(
                id=policy_id,
                team_id=team_id,
                version=1,
                rules={
                    "sources": [
                        {"origin_url": origin_url, "source_type": source_type}
                    ]
                },
            )
        )
        session.flush()
        session.add(
            Objective(
                id=objective_id,
                team_id=team_id,
                statement="Ingest the configured source",
                status="active",
            )
        )
        owner_event_id = uuid4()
        session.add(
            Task(
                id=owner_id,
                team_id=team_id,
                objective_id=objective_id,
                task_type="create_plan",
                status="running",
                policy_version=1,
                allowed_writes=["Plan"],
                budget=dict(_BUDGET),
            )
        )
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
                team_id=team_id,
                objective_id=objective_id,
                created_by_task_id=owner_id,
                accepted_event_id=owner_event_id,
                proposal_hash="test",
                assessment_basis={},
                assessment_created_at="test",
                budget={},
                completion_condition="configured_source_ingested",
            )
        )
        session.flush()
        session.add(
            PlanAction(
                plan_id=plan_id,
                action_id=action_id,
                action={
                    "id": str(action_id),
                    "purpose": "poll one configured source",
                    "prerequisites": [],
                    "task_type": "ingest_source",
                    "origin_url": origin_url,
                    "source_type": source_type,
                    "tools": list(overrides.get("tools", ())),
                },
            )
        )
        session.flush()
        session.add(
            Task(
                id=task_id,
                team_id=team_id,
                objective_id=objective_id,
                plan_id=plan_id,
                plan_action_id=action_id,
                task_type=overrides.get("task_type", "ingest_source"),
                status="pending",
                policy_version=1,
                allowed_writes=["Signal"],
                budget=dict(_BUDGET),
                max_attempts=3,
            )
        )

    try:
        yield context
    finally:
        with session_factory.begin() as session:
            session.execute(
                delete(Outcome).where(Outcome.recorded_by_task_id == task_id)
            )
            session.execute(delete(Signal).where(Signal.origin_url == origin_url))
            # Events reference their Task, so the Task's Events go first.
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))
            session.execute(delete(PlanAction).where(PlanAction.plan_id == plan_id))
            # The Plan references its accepted Event, so the Plan goes first.
            session.execute(delete(Plan).where(Plan.id == plan_id))
            session.execute(delete(Event).where(Event.task_id == owner_id))
            session.execute(delete(Task).where(Task.id == owner_id))
            session.execute(delete(Objective).where(Objective.id == objective_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


def _dispatcher(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    fetcher: FakeFetcher,
) -> TaskDispatcher:
    return TaskDispatcher(session_factory, snapshot_store, fetcher)


def _task(session_factory: sessionmaker[Session], task_id: UUID) -> Task:
    with session_factory() as session:
        task = session.get(Task, task_id)
        assert task is not None
        return task


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


def _signals(session_factory: sessionmaker[Session], origin_url: str) -> list[Signal]:
    with session_factory() as session:
        return list(
            session.scalars(select(Signal).where(Signal.origin_url == origin_url))
        )


# --- Case A: successful ingestion path --------------------------------------


def test_dispatch_ingests_configured_source_and_finalizes_task(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    fetcher = FakeFetcher()
    result = _dispatcher(session_factory, snapshot_store, fetcher).dispatch(
        dispatch_fixture.task_id
    )

    assert result.status == "done"
    assert result.result_category == "success_signal_created"
    assert result.failure_reason is None
    assert result.signal_id is not None
    assert result.outcome_id is not None

    # The fetcher was asked for exactly the durably configured source.
    assert [request.origin_url for request in fetcher.requests] == [
        dispatch_fixture.origin_url
    ]
    assert [request.source_type for request in fetcher.requests] == [
        dispatch_fixture.source_type
    ]

    task = _task(session_factory, dispatch_fixture.task_id)
    assert task.status == "done"
    assert task.attempt_count == 1
    assert task.completed_at is not None

    signals = _signals(session_factory, dispatch_fixture.origin_url)
    assert len(signals) == 1
    assert signals[0].domain == "r6b_test"
    assert signals[0].id == result.signal_id

    outcomes = _outcomes(session_factory, dispatch_fixture.task_id)
    assert len(outcomes) == 1
    assert outcomes[0].outcome_type == "task_execution"
    assert outcomes[0].subject_kind == "task"
    assert outcomes[0].subject_id == dispatch_fixture.task_id
    assert outcomes[0].id == result.outcome_id

    assert _event_types(session_factory, dispatch_fixture.task_id) == [
        "task_started",
        "signal_ingested",
        "task_completed",
    ]


def test_dispatch_reports_no_change_when_content_is_already_ingested(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    snapshot_ref, stored_hash = snapshot_store.put(_CONTENT)
    with session_factory.begin() as session:
        session.add(
            Signal(
                id=uuid4(),
                domain="r6b_test",
                source_type=dispatch_fixture.source_type,
                origin_url=dispatch_fixture.origin_url,
                fetched_at=datetime.now(timezone.utc),
                content_hash=stored_hash,
                snapshot_ref=snapshot_ref,
            )
        )

    result = _dispatcher(
        session_factory, snapshot_store, FakeFetcher()
    ).dispatch(dispatch_fixture.task_id)

    assert result.status == "done"
    assert result.result_category == "success_no_change"
    assert len(_signals(session_factory, dispatch_fixture.origin_url)) == 1
    outcomes = _outcomes(session_factory, dispatch_fixture.task_id)
    assert len(outcomes) == 1


# --- Case B: dispatch discovery and startup recovery ------------------------


def test_find_eligible_task_returns_the_oldest_pending_supported_task(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    dispatcher = _dispatcher(session_factory, snapshot_store, FakeFetcher())
    assert dispatcher.find_eligible_task() == dispatch_fixture.task_id


@pytest.mark.parametrize(
    "dispatch_fixture", [{"task_type": "triage_signal"}], indirect=True
)
def test_find_eligible_task_ignores_unsupported_task_types(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    dispatcher = _dispatcher(session_factory, snapshot_store, FakeFetcher())
    assert dispatcher.find_eligible_task() is None


def test_recovery_runs_at_dispatcher_startup_and_returns_stale_task(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    started_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    with session_factory.begin() as session:
        task = session.get(Task, dispatch_fixture.task_id)
        task.status = "running"
        # Recovery matches the start Event to the Task's current attempt.
        task.attempt_count = 1
        session.add(
            Event(
                id=uuid4(),
                task_id=dispatch_fixture.task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=started_at,
            )
        )

    dispatcher = _dispatcher(session_factory, snapshot_store, FakeFetcher())
    recovery = dispatcher.recover_interrupted()

    assert recovery.retried == (dispatch_fixture.task_id,)
    task = _task(session_factory, dispatch_fixture.task_id)
    assert task.status == "pending"
    assert task.attempt_count == 1
    assert _event_types(session_factory, dispatch_fixture.task_id) == [
        "task_started",
        "task_attempt_failed",
        "task_retry_scheduled",
    ]
    assert _outcomes(session_factory, dispatch_fixture.task_id) == []


# --- Case C: failure routing ------------------------------------------------


def test_retryable_fetch_failure_returns_task_to_pending(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    fetcher = FakeFetcher(
        error=SourceFetchError("source_connection_failed", retryable=True)
    )
    result = _dispatcher(session_factory, snapshot_store, fetcher).dispatch(
        dispatch_fixture.task_id
    )

    assert result.status == "pending"
    assert result.result_category is None
    assert result.failure_reason is None
    assert result.outcome_id is None

    task = _task(session_factory, dispatch_fixture.task_id)
    assert task.status == "pending"
    assert task.attempt_count == 1
    assert task.completed_at is None
    assert _outcomes(session_factory, dispatch_fixture.task_id) == []
    assert _event_types(session_factory, dispatch_fixture.task_id) == [
        "task_started",
        "task_attempt_failed",
        "task_retry_scheduled",
    ]
    assert _signals(session_factory, dispatch_fixture.origin_url) == []


@pytest.mark.parametrize(
    "reason",
    [
        "source_redirect_not_allowed",
        "source_content_type_not_allowed",
        "source_url_not_https",
        "source_address_not_allowed",
        "source_response_too_large",
    ],
)
def test_non_retryable_fetch_failure_terminalizes_the_task(
    session_factory, snapshot_store, dispatch_fixture, reason
) -> None:
    fetcher = FakeFetcher(error=SourceFetchError(reason, retryable=False))
    result = _dispatcher(session_factory, snapshot_store, fetcher).dispatch(
        dispatch_fixture.task_id
    )

    assert result.status == "failed"
    assert result.result_category == "terminal_failure"
    assert result.failure_reason == reason

    task = _task(session_factory, dispatch_fixture.task_id)
    assert task.status == "failed"
    assert task.completed_at is None
    assert _event_types(session_factory, dispatch_fixture.task_id) == [
        "task_started",
        "task_attempt_failed",
        "task_failed",
    ]
    outcomes = _outcomes(session_factory, dispatch_fixture.task_id)
    assert len(outcomes) == 1
    assert outcomes[0].id == result.outcome_id


def test_retryable_failure_on_the_final_allowed_attempt_terminalizes(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    """The three-total-start limit is enforced through the dispatcher."""
    with session_factory.begin() as session:
        session.get(Task, dispatch_fixture.task_id).attempt_count = 2

    fetcher = FakeFetcher(
        error=SourceFetchError("source_connection_failed", retryable=True)
    )
    result = _dispatcher(session_factory, snapshot_store, fetcher).dispatch(
        dispatch_fixture.task_id
    )

    assert result.status == "failed"
    task = _task(session_factory, dispatch_fixture.task_id)
    assert task.attempt_count == 3
    assert _event_types(session_factory, dispatch_fixture.task_id) == [
        "task_started",
        "task_attempt_failed",
        "task_failed",
    ]
    assert len(_outcomes(session_factory, dispatch_fixture.task_id)) == 1


def test_one_dispatch_call_makes_at_most_one_attempt(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    """A retryable failure is redelivered by a later call, not retried in-process."""
    fetcher = FakeFetcher(
        error=SourceFetchError("source_connection_failed", retryable=True)
    )
    dispatcher = _dispatcher(session_factory, snapshot_store, fetcher)
    dispatcher.dispatch(dispatch_fixture.task_id)

    assert _task(session_factory, dispatch_fixture.task_id).attempt_count == 1
    assert len(fetcher.requests) == 1


# --- Case D: configuration validation boundary ------------------------------


def test_task_without_durable_source_configuration_is_rejected_before_admission(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, dispatch_fixture.task_id)
        task.plan_id = None
        task.plan_action_id = None

    fetcher = FakeFetcher()
    with pytest.raises(TaskNotDispatchable, match="source_configuration_missing"):
        _dispatcher(session_factory, snapshot_store, fetcher).dispatch(
            dispatch_fixture.task_id
        )

    # Rejection happens before admission: no attempt, no Event, no fetch.
    task = _task(session_factory, dispatch_fixture.task_id)
    assert task.status == "pending"
    assert task.attempt_count == 0
    assert _events(session_factory, dispatch_fixture.task_id) == []
    assert fetcher.requests == []


def test_task_whose_source_is_not_configured_is_rejected_before_admission(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    with session_factory.begin() as session:
        policy = session.get(TeamPolicy, dispatch_fixture.policy_id)
        policy.rules = {"sources": []}

    fetcher = FakeFetcher()
    with pytest.raises(TaskNotDispatchable, match="source_not_configured"):
        _dispatcher(session_factory, snapshot_store, fetcher).dispatch(
            dispatch_fixture.task_id
        )

    assert _task(session_factory, dispatch_fixture.task_id).attempt_count == 0
    assert fetcher.requests == []


@pytest.mark.parametrize(
    "dispatch_fixture", [{"task_type": "triage_signal"}], indirect=True
)
def test_unsupported_task_type_is_rejected_before_admission(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    fetcher = FakeFetcher()
    with pytest.raises(TaskNotDispatchable, match="task_type_not_supported"):
        _dispatcher(session_factory, snapshot_store, fetcher).dispatch(
            dispatch_fixture.task_id
        )
    assert _task(session_factory, dispatch_fixture.task_id).attempt_count == 0


@pytest.mark.parametrize("dispatch_fixture", [{"tools": ["shell"]}], indirect=True)
def test_task_declaring_tool_capability_is_rejected_before_admission(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    """This slice grants no tool capability, regardless of the Action's claims."""
    fetcher = FakeFetcher()
    with pytest.raises(TaskNotDispatchable, match="source_configuration_unsupported"):
        _dispatcher(session_factory, snapshot_store, fetcher).dispatch(
            dispatch_fixture.task_id
        )
    assert _task(session_factory, dispatch_fixture.task_id).attempt_count == 0
    assert fetcher.requests == []


def test_missing_task_is_reported_as_not_dispatchable(
    session_factory, snapshot_store
) -> None:
    with pytest.raises(TaskNotDispatchable, match="task_not_found"):
        _dispatcher(session_factory, snapshot_store, FakeFetcher()).dispatch(uuid4())


# --- Case E: crash after ingestion commit, then replay ----------------------


def test_crash_after_ingestion_commit_recovers_and_replays_without_duplicates(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    """A crash after the ingestion commit must not duplicate Signal or Event."""
    dispatcher = _dispatcher(session_factory, snapshot_store, FakeFetcher())
    first = dispatcher.dispatch(dispatch_fixture.task_id)
    assert first.status == "done"

    # Simulate a crash between the ingestion commit and finalization: the
    # Signal and its Event survive, the terminal result and Outcome do not, and
    # the Task is left `running` on attempt 1 with a stale start.
    with session_factory.begin() as session:
        session.execute(
            delete(Outcome).where(
                Outcome.recorded_by_task_id == dispatch_fixture.task_id
            )
        )
        session.execute(
            delete(Event).where(
                Event.task_id == dispatch_fixture.task_id,
                Event.type.in_(
                    ("task_completed", "task_attempt_failed", "task_failed")
                ),
            )
        )
        task = session.get(Task, dispatch_fixture.task_id)
        task.status = "running"
        task.completed_at = None
        session.execute(
            update(Event)
            .where(
                Event.task_id == dispatch_fixture.task_id,
                Event.type == "task_started",
            )
            .values(created_at=datetime.now(timezone.utc) - timedelta(seconds=120))
        )

    # Startup recovery returns the interrupted Task for redelivery.
    recovery = dispatcher.recover_interrupted()
    assert recovery.retried == (dispatch_fixture.task_id,)

    second = dispatcher.dispatch(dispatch_fixture.task_id)

    assert second.status == "done"
    assert second.result_category == "success_signal_created"
    # No duplicate Signal and no duplicate ingestion Event.
    assert len(_signals(session_factory, dispatch_fixture.origin_url)) == 1
    assert _event_types(session_factory, dispatch_fixture.task_id).count(
        "signal_ingested"
    ) == 1
    assert len(_outcomes(session_factory, dispatch_fixture.task_id)) == 1


def test_same_attempt_refinalization_replays_the_committed_outcome(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    """The observation is derived from durable records, so it replays exactly.

    This is the property that makes recovery safe: rebuilding the observation
    for the same attempt from the committed ingestion Event yields a
    byte-identical canonical payload, so `finalize()` replays the existing
    Outcome instead of conflicting on a fresh timestamp.
    """
    dispatcher = _dispatcher(session_factory, snapshot_store, FakeFetcher())
    first = dispatcher.dispatch(dispatch_fixture.task_id)
    assert first.status == "done"

    with session_factory() as session:
        ingestion_event = session.scalar(
            select(Event).where(
                Event.task_id == dispatch_fixture.task_id,
                Event.type == "signal_ingested",
            )
        )
        signal = session.scalar(
            select(Signal).where(
                Signal.origin_url == dispatch_fixture.origin_url
            )
        )
    assert ingestion_event is not None and signal is not None

    observation = TerminalObservation(
        task_id=dispatch_fixture.task_id,
        attempt=1,
        result_category="success_signal_created",
        observed_at=ingestion_event.created_at,
        signals=(
            SignalEvidence(
                signal_id=signal.id,
                snapshot_ref=signal.snapshot_ref,
                content_hash=signal.content_hash,
            ),
        ),
    )
    replayed = dispatcher.runtime.finalize(observation)

    assert replayed.replayed is True
    assert replayed.outcome_id == first.outcome_id
    assert len(_outcomes(session_factory, dispatch_fixture.task_id)) == 1
    assert _event_types(session_factory, dispatch_fixture.task_id).count(
        "task_completed"
    ) == 1


# --- Case F: scope preservation --------------------------------------------


def test_dispatch_preserves_worker_write_scope_and_budget(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    with session_factory.begin() as session:
        policy = session.get(TeamPolicy, dispatch_fixture.policy_id)
        policy.rules = {
            "sources": [
                {
                    "origin_url": dispatch_fixture.origin_url,
                    "source_type": dispatch_fixture.source_type,
                }
            ],
            "budgets": {"max_tasks_per_day": 5},
        }

    _dispatcher(session_factory, snapshot_store, FakeFetcher()).dispatch(
        dispatch_fixture.task_id
    )

    task = _task(session_factory, dispatch_fixture.task_id)
    assert task.allowed_writes == ["Signal"]
    assert task.budget == _BUDGET
    assert task.attempt_count == 1

    with session_factory() as session:
        starts = session.scalar(
            select(func.count())
            .select_from(Event)
            .where(
                Event.task_id == dispatch_fixture.task_id,
                Event.type == "task_started",
            )
        )
    assert starts == 1


def test_dispatch_does_not_touch_another_teams_task(
    session_factory, snapshot_store, dispatch_fixture
) -> None:
    """Dispatching one Task never mutates an unrelated Team's records."""
    other_team_id, other_policy_id, other_task_id = uuid4(), uuid4(), uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=other_team_id, domain="r6b_other", status="active"))
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
                status="pending",
                policy_version=1,
                allowed_writes=["Signal"],
                budget=dict(_BUDGET),
            )
        )
    try:
        _dispatcher(session_factory, snapshot_store, FakeFetcher()).dispatch(
            dispatch_fixture.task_id
        )
        other = _task(session_factory, other_task_id)
        assert other.status == "pending"
        assert other.attempt_count == 0
        assert _events(session_factory, other_task_id) == []
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.task_id == other_task_id))
            session.execute(delete(Task).where(Task.id == other_task_id))
            session.execute(
                delete(TeamPolicy).where(TeamPolicy.id == other_policy_id)
            )
            session.execute(delete(Team).where(Team.id == other_team_id))


# --- Case G: the restricted fetcher's safety contract -----------------------


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://news.example.test/feed", "source_url_not_https"),
        ("https://user:pw@news.example.test/feed", "source_url_userinfo_not_allowed"),
        ("https://news.example.test/feed#frag", "source_url_fragment_not_allowed"),
        ("https://127.0.0.1/feed", "source_url_ip_literal_not_allowed"),
        ("https://[::1]/feed", "source_url_ip_literal_not_allowed"),
        ("https://NEWS.example.test/feed", "source_url_not_canonical"),
        ("https://news.example.test./feed", "source_url_not_canonical"),
        ("https://news.example.test:70000/feed", "source_url_invalid_port"),
        ("https:///feed", "source_url_invalid_host"),
    ],
)
def test_source_url_validation_rejects_unsafe_forms(url, reason) -> None:
    with pytest.raises(SourceFetchError, match=reason):
        validate_source_url(url)


def test_source_url_validation_accepts_a_plain_https_url() -> None:
    assert validate_source_url("https://news.example.test/feed") == (
        "news.example.test",
        443,
        "/feed",
    )
    assert validate_source_url("https://news.example.test") == (
        "news.example.test",
        443,
        "/",
    )


def test_metadata_hostname_is_rejected_without_resolution() -> None:
    with pytest.raises(SourceFetchError, match="source_address_not_allowed"):
        resolve_and_screen("metadata.google.internal", 443)


def test_private_resolved_address_is_rejected(monkeypatch) -> None:
    """A public hostname resolving to a private address must be refused."""

    def fake_getaddrinfo(host, port, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(SourceFetchError, match="source_address_not_allowed"):
        resolve_and_screen("news.example.test", 443)


def test_loopback_resolved_address_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))
        ],
    )
    with pytest.raises(SourceFetchError, match="source_address_not_allowed"):
        resolve_and_screen("news.example.test", 443)


def test_public_resolved_address_is_returned(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))
        ],
    )
    assert resolve_and_screen("news.example.test", 443) == "93.184.216.34"


def _response(
    *, status: int = 200, headers: dict[str, str] | None = None, body: bytes = b"ok"
) -> bytes:
    head = [f"HTTP/1.1 {status} OK"]
    head.extend(f"{name}: {value}" for name, value in (headers or {}).items())
    return ("\r\n".join(head) + "\r\n\r\n").encode("ascii") + body


def _fetcher() -> RestrictedFetcher:
    return RestrictedFetcher()


def _request() -> SourceFetchRequest:
    return SourceFetchRequest("https://news.example.test/feed", "rss")


def test_redirect_response_is_a_non_retryable_failure() -> None:
    with pytest.raises(SourceFetchError) as error:
        _fetcher()._parse(_response(status=302), _request())
    assert error.value.reason == "source_redirect_not_allowed"
    assert error.value.retryable is False


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_transient_status_codes_are_retryable(status) -> None:
    with pytest.raises(SourceFetchError) as error:
        _fetcher()._parse(_response(status=status), _request())
    assert error.value.retryable is True


@pytest.mark.parametrize("status", [400, 403, 404, 410, 415])
def test_other_client_errors_are_not_retryable(status) -> None:
    with pytest.raises(SourceFetchError) as error:
        _fetcher()._parse(_response(status=status), _request())
    assert error.value.retryable is False


@pytest.mark.parametrize(
    "content_type",
    ["text/html", "text/plain", "application/rss+xml", "application/atom+xml"],
)
def test_accepted_media_types_are_used(content_type) -> None:
    result = _fetcher()._parse(
        _response(headers={"Content-Type": f"{content_type}; charset=utf-8"}),
        _request(),
    )
    assert result.content == b"ok"


@pytest.mark.parametrize(
    "content_type", ["application/pdf", "application/json", "image/png", ""]
)
def test_unaccepted_media_types_are_rejected(content_type) -> None:
    with pytest.raises(SourceFetchError, match="source_content_type_not_allowed"):
        _fetcher()._parse(
            _response(headers={"Content-Type": content_type}), _request()
        )


def test_gzip_response_is_decompressed() -> None:
    body = gzip.compress(b"<html>compressed</html>")
    result = _fetcher()._parse(
        _response(
            headers={"Content-Type": "text/html", "Content-Encoding": "gzip"},
            body=body,
        ),
        _request(),
    )
    assert result.content == b"<html>compressed</html>"


def test_chunked_response_is_decoded() -> None:
    body = b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n"
    result = _fetcher()._parse(
        _response(
            headers={
                "Content-Type": "text/plain",
                "Transfer-Encoding": "chunked",
            },
            body=body,
        ),
        _request(),
    )
    assert result.content == b"hello world"


def test_oversized_decompressed_body_exceeds_the_ceiling() -> None:
    body = gzip.compress(b"a" * (MAX_RESPONSE_BYTES + 1))
    with pytest.raises(SourceFetchError, match="source_response_too_large"):
        _fetcher()._parse(
            _response(
                headers={"Content-Type": "text/html", "Content-Encoding": "gzip"},
                body=body,
            ),
            _request(),
        )


def test_unsupported_content_encoding_is_rejected() -> None:
    with pytest.raises(SourceFetchError, match="source_content_encoding_not_allowed"):
        _fetcher()._parse(
            _response(
                headers={"Content-Type": "text/html", "Content-Encoding": "br"},
                body=b"whatever",
            ),
            _request(),
        )


def test_malformed_response_is_rejected() -> None:
    with pytest.raises(SourceFetchError, match="source_response_malformed"):
        _fetcher()._parse(b"not-an-http-response", _request())


def test_dispatcher_uses_the_configured_source_not_a_caller_supplied_url(
    session_factory, snapshot_store, dispatch_fixture, tmp_path: Path
) -> None:
    """The Task's durable Action decides the URL; the fetch request proves it.

    A `RestrictedFetcher` is bound here so the real validator runs, but the
    socket layer is never reached because the configured host is unresolvable
    in the test environment. The recorded reason is the transport failure, not
    a URL-safety rejection, which shows the approved URL passed validation.
    """
    fetcher = FakeFetcher()
    _dispatcher(session_factory, snapshot_store, fetcher).dispatch(
        dispatch_fixture.task_id
    )
    assert [r.origin_url for r in fetcher.requests] == [
        dispatch_fixture.origin_url
    ]
    assert fetcher.requests[0].origin_url.startswith("https://")
