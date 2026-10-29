"""R6-C: deterministic, read-only reconstruction of Plan execution evidence."""

import hashlib
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.execution_assessment import ExecutionAssessmentBuilder
from core.ingestion import IngestionProposal, IngestionService
from core.models import Event, Outcome, PlanAction, Signal, Task
from core.plans import PlanResult, PlanService
from core.snapshot_store import SnapshotStore
from core.task_runtime import (
    FailureObservation,
    SignalEvidence,
    TaskRuntime,
    TerminalObservation,
)
from tests.test_plans import plan_request  # noqa: F401


@pytest.fixture
def materialized_plan(
    request: pytest.FixtureRequest,
    session_factory: sessionmaker[Session],
):
    plan_request_data = request.getfixturevalue("plan_request")
    result: PlanResult = PlanService(session_factory).create(**plan_request_data)
    try:
        yield {**plan_request_data, "plan_id": result.plan_id, "result": result}
    finally:
        # This fixture tears down before the imported plan_request fixture
        # removes its Tasks, so its Outcome foreign keys must be removed first.
        with session_factory.begin() as session:
            session.execute(
                delete(Outcome).where(
                    Outcome.recorded_by_task_id.in_(result.task_ids),
                    Outcome.outcome_type == "task_execution",
                )
            )


def _builder(session_factory, snapshot_store) -> ExecutionAssessmentBuilder:
    return ExecutionAssessmentBuilder(session_factory, snapshot_store)


def _task_id(materialized_plan: dict) -> UUID:
    return materialized_plan["result"].task_ids[0]


def _complete_success(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    materialized_plan: dict,
) -> UUID:
    task_id = _task_id(materialized_plan)
    runtime = TaskRuntime(session_factory, snapshot_store)
    admitted = runtime.admit(task_id)

    with session_factory() as session:
        task = session.get(Task, task_id)
        assert task is not None
        assert task.plan_id is not None and task.plan_action_id is not None
        action = session.get(PlanAction, (task.plan_id, task.plan_action_id))
        assert action is not None
        origin_url = action.action["origin_url"]
        source_type = action.action["source_type"]

    content = b"R6-C deterministic assessment fixture"
    fetched_at = datetime.now(timezone.utc)
    ingestion = IngestionService(session_factory, snapshot_store).ingest(
        IngestionProposal(
            task_id=task_id,
            origin_url=origin_url,
            source_type=source_type,
            fetched_at=fetched_at,
            content=content,
            claimed_content_hash="sha256:" + hashlib.sha256(content).hexdigest(),
        )
    )
    with session_factory() as session:
        signal = session.get(Signal, ingestion.signal_id)
        event = session.get(Event, ingestion.event_id)
        assert signal is not None and event is not None
        evidence = SignalEvidence(
            signal_id=signal.id,
            snapshot_ref=signal.snapshot_ref,
            content_hash=signal.content_hash,
        )
        observed_at = event.created_at
    runtime.finalize(
        TerminalObservation(
            task_id=task_id,
            attempt=admitted.attempt_count,
            result_category="success_signal_created",
            observed_at=observed_at,
            signals=(evidence,),
        )
    )
    return task_id


def _counts(session_factory, task_id: UUID) -> tuple[int, int]:
    with session_factory() as session:
        event_count = session.scalar(
            select(func.count(Event.id)).where(Event.task_id == task_id)
        )
        outcome_count = session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == task_id
            )
        )
    return int(event_count or 0), int(outcome_count or 0)


def test_pending_plan_reassessment_preserves_original_decision_basis(
    session_factory, snapshot_store, materialized_plan
) -> None:
    first = _builder(session_factory, snapshot_store).build(
        materialized_plan["plan_id"]
    )
    second = _builder(session_factory, snapshot_store).build(
        materialized_plan["plan_id"]
    )

    assert first.conclusion == "in_progress"
    assert first.integrity == "consistent"
    assert first.as_dict() == second.as_dict()
    assert first.payload["historical_decision"]["assessment_basis"]
    assert first.payload["historical_decision"]["assessment"]["created_at"] == (
        first.payload["historical_decision"]["assessment_created_at"]
    )
    action = first.payload["actions"][0]
    assert action["conclusion"] == "not_started"
    assert action["outcome"] is None


def test_success_reassessment_is_deterministic_and_read_only_after_rebuild(
    session_factory, snapshot_store, materialized_plan
) -> None:
    task_id = _complete_success(
        session_factory, snapshot_store, materialized_plan
    )
    before = _counts(session_factory, task_id)

    first = _builder(session_factory, snapshot_store).build(
        materialized_plan["plan_id"]
    )
    second = _builder(session_factory, snapshot_store).build(
        materialized_plan["plan_id"]
    )

    assert first.conclusion == "execution_succeeded_plan_active"
    assert first.integrity == "consistent"
    assert first.assessment_hash == second.assessment_hash
    assert first.as_dict() == second.as_dict()
    action = first.payload["actions"][0]
    assert action["conclusion"] == "succeeded"
    assert action["outcome"]["result_category"] == "success_signal_created"
    assert len(action["business_events"]) == 1
    assert action["business_events"][0]["type"] == "signal_ingested"
    assert _counts(session_factory, task_id) == before
    assert before[1] == 1


def test_retry_then_terminal_failure_is_reconstructed_from_attempt_events(
    session_factory, snapshot_store, materialized_plan
) -> None:
    task_id = _task_id(materialized_plan)
    runtime = TaskRuntime(session_factory, snapshot_store)
    first_admission = runtime.admit(task_id)
    with session_factory() as session:
        first_start = session.scalar(
            select(Event.created_at).where(
                Event.task_id == task_id,
                Event.type == "task_started",
                Event.payload["attempt_count"].as_integer() == 1,
            )
        )
    assert first_start is not None
    runtime.report_failure(
        FailureObservation(
            task_id=task_id,
            attempt=first_admission.attempt_count,
            observed_at=first_start,
            reason="temporary_source_timeout",
            retryable=True,
        )
    )

    second_admission = runtime.admit(task_id)
    with session_factory() as session:
        second_start = session.scalar(
            select(Event.created_at).where(
                Event.task_id == task_id,
                Event.type == "task_started",
                Event.payload["attempt_count"].as_integer() == 2,
            )
        )
    assert second_start is not None
    runtime.report_failure(
        FailureObservation(
            task_id=task_id,
            attempt=second_admission.attempt_count,
            observed_at=second_start,
            reason="source_not_configured",
            retryable=False,
        )
    )

    assessed = _builder(session_factory, snapshot_store).build(
        materialized_plan["plan_id"]
    )
    action = assessed.payload["actions"][0]
    assert assessed.conclusion == "failed"
    assert assessed.integrity == "consistent"
    assert action["conclusion"] == "failed"
    assert [attempt["disposition"] for attempt in action["attempts"]] == [
        "retry_scheduled",
        "failed",
    ]
    assert action["attempts"][0]["failure_reason"] == "temporary_source_timeout"
    assert action["outcome"]["failure_reason"] == "source_not_configured"
    assert action["outcome"]["result_category"] == "terminal_failure"


def test_terminal_event_without_its_outcome_is_inconsistent(
    session_factory, snapshot_store, materialized_plan
) -> None:
    task_id = _complete_success(
        session_factory, snapshot_store, materialized_plan
    )
    with session_factory.begin() as session:
        session.execute(
            delete(Outcome).where(
                Outcome.recorded_by_task_id == task_id,
                Outcome.outcome_type == "task_execution",
            )
        )

    assessed = _builder(session_factory, snapshot_store).build(
        materialized_plan["plan_id"]
    )
    action = assessed.payload["actions"][0]
    assert assessed.conclusion == "inconsistent"
    assert assessed.integrity == "inconsistent"
    assert action["conclusion"] == "inconsistent"
    assert "terminal_outcome_missing" in action["findings"]


def test_unreadable_terminal_snapshot_is_reported_not_assumed_successful(
    session_factory, snapshot_store, tmp_path, materialized_plan
) -> None:
    task_id = _complete_success(
        session_factory, snapshot_store, materialized_plan
    )
    with session_factory() as session:
        outcome = session.scalar(
            select(Outcome).where(
                Outcome.recorded_by_task_id == task_id,
                Outcome.outcome_type == "task_execution",
            )
        )
        assert outcome is not None
        assert outcome.observation_hash is not None
        digest = outcome.observation_hash.removeprefix("sha256:")
    snapshot_path = tmp_path / "sha256" / digest[:2] / digest
    snapshot_path.unlink()

    assessed = _builder(session_factory, snapshot_store).build(
        materialized_plan["plan_id"]
    )
    action = assessed.payload["actions"][0]
    assert assessed.conclusion == "inconsistent"
    assert "terminal_outcome_snapshot_unreadable" in action["findings"]
