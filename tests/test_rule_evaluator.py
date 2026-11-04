"""R6-G D9 deterministic configured-source evaluation rules."""

import hashlib
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.dispatcher import TaskDispatcher
from core.models import Evaluation, Event, Signal
from core.rule_evaluator import IngestSourceRuleEvaluator, RuleEvaluationError
from core.snapshot_store import SnapshotStore
from core.source_fetch import SourceFetchError
from core.task_runtime import TaskRuntime
from tests.test_r6b_dispatcher import (
    DispatchFixture,
    FakeFetcher,
)
from tests.test_r6b_dispatcher import (
    dispatch_fixture as base_dispatch_fixture,  # noqa: F401
)


@pytest.fixture
def dispatch_fixture(base_dispatch_fixture: DispatchFixture) -> DispatchFixture:  # noqa: F811
    return base_dispatch_fixture


def _evaluator_task_id(
    session_factory: sessionmaker[Session], source_task_id: UUID
) -> UUID:
    with session_factory() as session:
        requests = [
            event
            for event in session.scalars(
                select(Event).where(Event.type == "evaluation_task_requested")
            )
            if event.payload.get("source_task_id") == str(source_task_id)
        ]
        assert len(requests) == 1
        return requests[0].task_id


def _dispatch(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    fixture: DispatchFixture,
    fetcher: FakeFetcher,
) -> UUID:
    dispatcher = TaskDispatcher(session_factory, snapshot_store, fetcher)
    result = dispatcher.dispatch(fixture.task_id)
    assert result.outcome_id is not None
    assert result.status in {"done", "failed"}
    evaluator_task_id = _evaluator_task_id(
        session_factory, fixture.task_id
    )
    TaskRuntime(session_factory, snapshot_store).admit(evaluator_task_id)
    return evaluator_task_id


def test_created_signal_produces_deterministic_worked_evaluation(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    dispatch_fixture: DispatchFixture,
) -> None:
    evaluator_task_id = _dispatch(
        session_factory, snapshot_store, dispatch_fixture, FakeFetcher()
    )

    draft = IngestSourceRuleEvaluator(
        session_factory, snapshot_store
    ).evaluate(evaluator_task_id)

    assert draft.conclusion == "worked"
    assert draft.findings.attribution == "not established"
    assert len(draft.evidence) == 2
    assert {item.source_kind for item in draft.evidence} == {"outcome", "signal"}
    assert draft.idempotency_key.startswith("r6g-evaluate-v1:")

    replayed = IngestSourceRuleEvaluator(
        session_factory, snapshot_store
    ).evaluate(evaluator_task_id)
    assert replayed.model_dump(mode="json") == draft.model_dump(mode="json")


def test_existing_identical_signal_produces_worked_no_change_evaluation(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    dispatch_fixture: DispatchFixture,
) -> None:
    content = b"Existing configured-source content"
    content_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    snapshot_ref, stored_hash = snapshot_store.put(content)
    assert stored_hash == content_hash
    with session_factory.begin() as session:
        session.add(
            Signal(
                id=uuid4(),
                domain="r6b_test",
                source_type=dispatch_fixture.source_type,
                origin_url=dispatch_fixture.origin_url,
                fetched_at=datetime.now(timezone.utc),
                content_hash=content_hash,
                snapshot_ref=snapshot_ref,
            )
        )

    evaluator_task_id = _dispatch(
        session_factory,
        snapshot_store,
        dispatch_fixture,
        FakeFetcher(content),
    )
    draft = IngestSourceRuleEvaluator(
        session_factory, snapshot_store
    ).evaluate(evaluator_task_id)

    assert draft.conclusion == "worked"
    assert len(draft.evidence) == 2
    assert "no duplicate Signal" in draft.findings.observed_result


def test_terminal_source_failure_produces_failed_evaluation(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    dispatch_fixture: DispatchFixture,
) -> None:
    evaluator_task_id = _dispatch(
        session_factory,
        snapshot_store,
        dispatch_fixture,
        FakeFetcher(error=SourceFetchError("source_blocked", retryable=False)),
    )
    draft = IngestSourceRuleEvaluator(
        session_factory, snapshot_store
    ).evaluate(evaluator_task_id)

    assert draft.conclusion == "failed"
    assert "source_blocked" in draft.findings.observed_result
    assert len(draft.evidence) == 1
    assert draft.evidence[0].source_kind == "outcome"


def test_terminal_event_mismatch_fails_closed_without_evaluation(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    dispatch_fixture: DispatchFixture,
) -> None:
    evaluator_task_id = _dispatch(
        session_factory, snapshot_store, dispatch_fixture, FakeFetcher()
    )
    with session_factory() as session:
        request = session.scalar(
            select(Event).where(
                Event.task_id == evaluator_task_id,
                Event.type == "evaluation_task_requested",
            )
        )
        assert request is not None
        source_task_id = UUID(request.payload["source_task_id"])
    with session_factory.begin() as session:
        terminal = session.scalar(
            select(Event).where(
                Event.task_id == source_task_id,
                Event.type == "task_completed",
            )
        )
        assert terminal is not None
        payload = dict(terminal.payload)
        payload["observation_hash"] = "sha256:" + ("f" * 64)
        terminal.payload = payload

    with pytest.raises(RuleEvaluationError, match="evaluation_terminal_event_mismatch"):
        IngestSourceRuleEvaluator(
            session_factory, snapshot_store
        ).evaluate(evaluator_task_id)

    with session_factory() as session:
        assert session.scalar(
            select(Evaluation.id).where(
                Evaluation.created_by_task_id == evaluator_task_id
            )
        ) is None


def test_cross_domain_signal_fails_closed_without_evaluation(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    dispatch_fixture: DispatchFixture,
) -> None:
    evaluator_task_id = _dispatch(
        session_factory, snapshot_store, dispatch_fixture, FakeFetcher()
    )
    with session_factory() as session:
        request = session.scalar(
            select(Event).where(
                Event.task_id == evaluator_task_id,
                Event.type == "evaluation_task_requested",
            )
        )
        assert request is not None
        source_task_id = UUID(request.payload["source_task_id"])
        ingestion = session.scalar(
            select(Event).where(
                Event.task_id == source_task_id,
                Event.type == "signal_ingested",
            )
        )
        assert ingestion is not None
        signal_id = UUID(ingestion.payload["signal_id"])
    with session_factory.begin() as session:
        signal = session.get(Signal, signal_id)
        assert signal is not None
        signal.domain = "another_domain"

    with pytest.raises(
        RuleEvaluationError, match="evaluation_signal_business_record_mismatch"
    ):
        IngestSourceRuleEvaluator(
            session_factory, snapshot_store
        ).evaluate(evaluator_task_id)

    with session_factory() as session:
        assert session.scalar(
            select(Evaluation.id).where(
                Evaluation.created_by_task_id == evaluator_task_id
            )
        ) is None


def test_contradictory_success_business_event_fails_closed(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    dispatch_fixture: DispatchFixture,
) -> None:
    evaluator_task_id = _dispatch(
        session_factory, snapshot_store, dispatch_fixture, FakeFetcher()
    )
    with session_factory() as session:
        request = session.scalar(
            select(Event).where(
                Event.task_id == evaluator_task_id,
                Event.type == "evaluation_task_requested",
            )
        )
        assert request is not None
        source_task_id = UUID(request.payload["source_task_id"])
    with session_factory.begin() as session:
        session.add(
            Event(
                id=uuid4(),
                task_id=source_task_id,
                type="fetch_no_change",
                payload={},
                created_at=datetime.now(timezone.utc),
            )
        )

    with pytest.raises(
        RuleEvaluationError, match="evaluation_ingestion_event_set_invalid"
    ):
        IngestSourceRuleEvaluator(
            session_factory, snapshot_store
        ).evaluate(evaluator_task_id)
