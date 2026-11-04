"""R6-G: durable D9 evaluator-Task request and recovery protocol."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from typing import Literal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.evaluation_tasks import RuleEvaluationTaskRunner
from core.evaluations import (
    EvaluationDraft,
    EvaluationEvidence,
    EvaluationFindings,
    EvaluationService,
)
from core.models import Event, Outcome, Task
from core.task_runtime import (
    FinalizationResult,
    TaskNotEligible,
    TaskRuntime,
    TerminalObservation,
)
from tests.test_r6b_dispatcher import DispatchFixture
from tests.test_r6b_dispatcher import (
    dispatch_fixture as base_dispatch_fixture,  # noqa: F401
)


@pytest.fixture
def dispatch_fixture(base_dispatch_fixture: DispatchFixture) -> DispatchFixture:  # noqa: F811
    return base_dispatch_fixture


def _request_for_source(
    session_factory: sessionmaker[Session], source_task_id: UUID
) -> tuple[Task, Event]:
    with session_factory() as session:
        requests = [
            event
            for event in session.scalars(
                select(Event).where(Event.type == "evaluation_task_requested")
            )
            if event.payload.get("source_task_id") == str(source_task_id)
        ]
        assert len(requests) == 1
        request = requests[0]
        task = session.get(Task, request.task_id)
        assert task is not None
        return task, request


def _finalize_source(
    runtime: TaskRuntime,
    fixture: DispatchFixture,
    *,
    result_category: Literal["success_no_change", "terminal_failure"] = (
        "success_no_change"
    ),
) -> tuple[TerminalObservation, FinalizationResult]:
    admission = runtime.admit(fixture.task_id)
    if result_category == "terminal_failure":
        observation = TerminalObservation(
            task_id=fixture.task_id,
            attempt=admission.attempt_count,
            result_category="terminal_failure",
            observed_at=datetime.now(timezone.utc),
            failure_reason="source_fetch_non_retryable",
        )
    else:
        observation = TerminalObservation(
            task_id=fixture.task_id,
            attempt=admission.attempt_count,
            result_category="success_no_change",
            observed_at=datetime.now(timezone.utc),
        )
    return observation, runtime.finalize(observation)


def test_terminal_source_finalization_atomically_requests_evaluation(
    session_factory: sessionmaker[Session],
    snapshot_store,
    dispatch_fixture: DispatchFixture,
) -> None:
    runtime = TaskRuntime(session_factory, snapshot_store)
    observation, finalization = _finalize_source(runtime, dispatch_fixture)

    assert finalization.status == "done"
    evaluator_task, request = _request_for_source(
        session_factory, dispatch_fixture.task_id
    )
    assert evaluator_task.status == "pending"
    assert evaluator_task.attempt_count == 0
    assert evaluator_task.max_attempts == 3
    assert evaluator_task.team_id == dispatch_fixture.team_id
    assert evaluator_task.policy_version == 1
    assert evaluator_task.objective_id is None
    assert evaluator_task.plan_id is None
    assert evaluator_task.plan_action_id is None
    assert evaluator_task.allowed_writes == ["Evaluation", "EvidenceLink"]
    assert evaluator_task.budget == {
        "max_tool_calls": 0,
        "max_cost_usd": 0,
        "deadline_seconds": 30,
    }
    assert request.task_id == evaluator_task.id
    assert request.payload["source_task_id"] == str(dispatch_fixture.task_id)
    assert request.payload["source_attempt"] == observation.attempt
    assert request.payload["source_result_category"] == "success_no_change"
    assert request.payload["source_plan_id"] == str(dispatch_fixture.plan_id)
    assert request.payload["source_plan_action_id"] == str(dispatch_fixture.action_id)
    assert request.payload["policy_version"] == 1
    assert request.payload["outcome_id"] == str(finalization.outcome_id)
    assert request.payload["evaluator_kind"] == "rule"
    assert request.payload["evaluator_identity"] == "watch.r6g.ingest-source-rules"
    assert request.payload["evaluator_revision"] == "1"
    assert request.payload["request_fingerprint"].startswith("sha256:")

    replay = runtime.finalize(observation)
    assert replay.replayed is True
    assert replay.outcome_id == finalization.outcome_id
    replay_task, replay_request = _request_for_source(
        session_factory, dispatch_fixture.task_id
    )
    assert replay_task.id == evaluator_task.id
    assert replay_request.id == request.id


def test_concurrent_terminal_replay_creates_one_evaluation_request(
    session_factory: sessionmaker[Session],
    snapshot_store,
    dispatch_fixture: DispatchFixture,
) -> None:
    runtime = TaskRuntime(session_factory, snapshot_store)
    admission = runtime.admit(dispatch_fixture.task_id)
    observation = TerminalObservation(
        task_id=dispatch_fixture.task_id,
        attempt=admission.attempt_count,
        result_category="success_no_change",
        observed_at=datetime.now(timezone.utc),
    )
    barrier = Barrier(2)

    def finalize() -> FinalizationResult:
        barrier.wait(timeout=10)
        return runtime.finalize(observation)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(finalize) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]

    assert {result.outcome_id for result in results} == {results[0].outcome_id}
    assert sum(not result.replayed for result in results) == 1
    evaluator_task, request = _request_for_source(
        session_factory, dispatch_fixture.task_id
    )
    with session_factory() as session:
        source_outcomes = list(
            session.scalars(
                select(Outcome).where(
                    Outcome.subject_kind == "task",
                    Outcome.subject_id == dispatch_fixture.task_id,
                    Outcome.outcome_type == "task_execution",
                )
            )
        )
        requests = [
            event
            for event in session.scalars(
                select(Event).where(Event.type == "evaluation_task_requested")
            )
            if event.payload.get("source_task_id") == str(dispatch_fixture.task_id)
        ]
        evaluator = session.get(Task, evaluator_task.id)

    assert len(source_outcomes) == 1
    assert source_outcomes[0].id == results[0].outcome_id
    assert len(requests) == 1
    assert requests[0].id == request.id
    assert evaluator is not None
    assert evaluator.status == "pending"
    assert evaluator.attempt_count == 0


def test_evaluator_enqueue_failure_rolls_back_source_terminalization(
    session_factory: sessionmaker[Session],
    snapshot_store,
    dispatch_fixture: DispatchFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = TaskRuntime(session_factory, snapshot_store)
    admission = runtime.admit(dispatch_fixture.task_id)
    observation = TerminalObservation(
        task_id=dispatch_fixture.task_id,
        attempt=admission.attempt_count,
        result_category="success_no_change",
        observed_at=datetime.now(timezone.utc),
    )

    def fail_enqueue(self, session, source_task, outcome, result_category):
        raise RuntimeError("injected evaluator enqueue failure")

    monkeypatch.setattr(
        TaskRuntime, "_create_evaluation_task_request", fail_enqueue
    )
    with pytest.raises(RuntimeError, match="injected evaluator enqueue failure"):
        runtime.finalize(observation)

    with session_factory() as session:
        source = session.get(Task, dispatch_fixture.task_id)
        source_outcomes = list(
            session.scalars(
                select(Outcome).where(
                    Outcome.subject_kind == "task",
                    Outcome.subject_id == dispatch_fixture.task_id,
                    Outcome.outcome_type == "task_execution",
                )
            )
        )
        terminal_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == dispatch_fixture.task_id,
                    Event.type.in_(("task_completed", "task_failed")),
                )
            )
        )
        request_events = list(
            session.scalars(
                select(Event).where(Event.type == "evaluation_task_requested")
            )
        )

    assert source is not None
    assert source.status == "running"
    assert source.completed_at is None
    assert source_outcomes == []
    assert terminal_events == []
    assert request_events == []


def test_terminal_failure_also_creates_one_evaluator_request(
    session_factory: sessionmaker[Session],
    snapshot_store,
    dispatch_fixture: DispatchFixture,
) -> None:
    runtime = TaskRuntime(session_factory, snapshot_store)
    _, finalization = _finalize_source(
        runtime, dispatch_fixture, result_category="terminal_failure"
    )

    assert finalization.status == "failed"
    evaluator_task, request = _request_for_source(
        session_factory, dispatch_fixture.task_id
    )
    assert evaluator_task.status == "pending"
    assert request.payload["source_result_category"] == "terminal_failure"


def test_tampered_evaluator_request_is_rejected_before_admission(
    session_factory: sessionmaker[Session],
    snapshot_store,
    dispatch_fixture: DispatchFixture,
) -> None:
    runtime = TaskRuntime(session_factory, snapshot_store)
    _finalize_source(runtime, dispatch_fixture)
    evaluator_task, request = _request_for_source(
        session_factory, dispatch_fixture.task_id
    )

    with session_factory.begin() as session:
        stored = session.get(Event, request.id)
        assert stored is not None
        payload = dict(stored.payload)
        payload["evaluator_revision"] = "2"
        stored.payload = payload

    with pytest.raises(TaskNotEligible, match="evaluation_task_request"):
        runtime.admit(evaluator_task.id)

    with session_factory() as session:
        unchanged = session.get(Task, evaluator_task.id)
        assert unchanged is not None
        assert unchanged.status == "pending"
        assert unchanged.attempt_count == 0
        starts = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == evaluator_task.id,
                    Event.type == "task_started",
                )
            )
        )
        assert starts == []


def test_recovery_finalizes_a_recorded_evaluation_before_retry(
    session_factory: sessionmaker[Session],
    snapshot_store,
    dispatch_fixture: DispatchFixture,
) -> None:
    runtime = TaskRuntime(session_factory, snapshot_store)
    _, source_finalization = _finalize_source(runtime, dispatch_fixture)
    evaluator_task, request = _request_for_source(
        session_factory, dispatch_fixture.task_id
    )
    runtime.admit(evaluator_task.id)

    service = EvaluationService(session_factory, snapshot_store)
    draft = EvaluationDraft(
        outcome_id=source_finalization.outcome_id,
        conclusion="worked",
        findings=EvaluationFindings(
            observed_result="The configured source produced no new Signal.",
            method_or_process="The ingestion commit detected identical source content.",
            uncertainty=["This is execution-contract evidence only."],
        ),
        evidence=[
            EvaluationEvidence(
                source_kind="outcome",
                outcome_id=source_finalization.outcome_id,
                stance="supports",
            )
        ],
        idempotency_key=TaskRuntime._r6g_evaluation_idempotency_key(
            request.payload["request_fingerprint"]
        ),
    )
    proposed = service.propose(
        evaluator_task.id,
        draft,
        evaluator_kind="rule",
        evaluator_identity="watch.r6g.ingest-source-rules",
        evaluator_revision="1",
    )
    service.record(evaluator_task.id, proposed.evaluation_id)

    with session_factory() as session:
        started = session.scalar(
            select(Event.created_at).where(
                Event.task_id == evaluator_task.id,
                Event.type == "task_started",
            )
        )
    assert started is not None
    recovered = runtime.recover_interrupted(now=started + timedelta(seconds=61))

    assert evaluator_task.id in recovered.completed
    assert evaluator_task.id not in recovered.retried
    with session_factory() as session:
        terminal_task = session.get(Task, evaluator_task.id)
        assert terminal_task is not None
        assert terminal_task.status == "done"
        completion = session.scalar(
            select(Event).where(
                Event.task_id == evaluator_task.id,
                Event.type == "task_completed",
            )
        )
        assert completion is not None
        assert completion.payload["result_category"] == "success_evaluation_recorded"
        assert completion.payload["evaluation_id"] == str(proposed.evaluation_id)
        evaluator_outcome = session.scalar(
            select(Outcome).where(Outcome.recorded_by_task_id == evaluator_task.id)
        )
        assert evaluator_outcome is not None
        assert evaluator_outcome.observed_at == started



def test_runner_records_evaluation_and_replays_terminal_task(
    session_factory: sessionmaker[Session],
    snapshot_store,
    dispatch_fixture: DispatchFixture,
) -> None:
    from core.dispatcher import TaskDispatcher
    from tests.test_r6b_dispatcher import FakeFetcher

    TaskDispatcher(
        session_factory, snapshot_store, FakeFetcher()
    ).dispatch(dispatch_fixture.task_id)
    evaluator_task, _ = _request_for_source(
        session_factory, dispatch_fixture.task_id
    )

    runner = RuleEvaluationTaskRunner(session_factory, snapshot_store)
    first = runner.run(evaluator_task.id)
    second = runner.run(evaluator_task.id)

    assert first.status == "done"
    assert first.evaluation_id is not None
    assert first.outcome_id is not None
    assert first.replayed is False
    assert second.status == "done"
    assert second.evaluation_id == first.evaluation_id
    assert second.outcome_id == first.outcome_id
    assert second.replayed is True
