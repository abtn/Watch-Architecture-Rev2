"""RW-3.1 host Task creation and bounded Context proofs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from core.models import (
    Event,
    EvidenceLink,
    Hypothesis,
    Signal,
    Task,
    Team,
    TeamPolicy,
    Thread,
)
from core.operator_application import (
    OperatorApplicationAdapter,
    OperatorGrant,
    OperatorNotAuthorized,
    OperatorTaskRequestConflict,
    TrustedOperatorPrincipal,
)
from core.snapshot_store import SnapshotStore
from core.update_thread import (
    ALLOWED_WRITES,
    MAX_ATTEMPTS,
    REQUEST_EVENT_TYPE,
    TASK_BUDGET,
    UpdateThreadTaskRequest,
)
from core.update_thread_context import (
    CONTEXT_EVENT_TYPE,
    UpdateThreadContextAssembler,
    UpdateThreadContextError,
)

_CONTENT = b"Market report: supply increased by 5 percent."
_QUOTE = "supply increased by 5 percent"


@dataclass(frozen=True)
class Fixture:
    team_id: UUID
    policy_id: UUID
    source_task_id: UUID
    signal_id: UUID
    thread_id: UUID
    snapshot_ref: str
    snapshot_hash: str


@pytest.fixture
def rw3_fixture(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
) -> Iterator[Fixture]:
    team_id, policy_id, source_task_id, signal_id, thread_id = (
        uuid4() for _ in range(5)
    )
    snapshot_ref, snapshot_hash = snapshot_store.put(_CONTENT)
    now = datetime.now(timezone.utc)
    fixture = Fixture(
        team_id=team_id,
        policy_id=policy_id,
        source_task_id=source_task_id,
        signal_id=signal_id,
        thread_id=thread_id,
        snapshot_ref=snapshot_ref,
        snapshot_hash=snapshot_hash,
    )
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="rw3_test", status="active"))
        session.flush()
        session.add(
            TeamPolicy(
                id=policy_id,
                team_id=team_id,
                version=1,
                schema_version=1,
                rules={},
            )
        )
        session.flush()
        session.add(
            Task(
                id=source_task_id,
                team_id=team_id,
                task_type="ingest_source",
                status="done",
                attempt_count=1,
                policy_version=1,
                allowed_writes=["Signal"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.0,
                    "deadline_seconds": 60,
                },
                completed_at=now,
            )
        )
        session.add(
            Signal(
                id=signal_id,
                domain="rw3_test",
                source_type="fixture",
                origin_url=f"https://example.test/{signal_id}",
                fetched_at=now,
                content_hash=snapshot_hash,
                snapshot_ref=snapshot_ref,
            )
        )
        session.add(
            Thread(
                id=thread_id,
                team_id=team_id,
                domain="rw3_test",
                title="Supply conditions",
                status="active",
            )
        )
        session.flush()

    try:
        yield fixture
    finally:
        with session_factory.begin() as session:
            task_ids = select(Task.id).where(Task.team_id == team_id)
            session.execute(delete(Event).where(Event.task_id.in_(task_ids)))
            session.execute(
                delete(EvidenceLink).where(EvidenceLink.team_id == team_id)
            )
            session.execute(
                delete(Hypothesis).where(Hypothesis.team_id == team_id)
            )
            session.execute(delete(Thread).where(Thread.team_id == team_id))
            session.execute(delete(Signal).where(Signal.id == signal_id))
            session.execute(delete(Task).where(Task.team_id == team_id))
            session.execute(
                delete(TeamPolicy).where(TeamPolicy.team_id == team_id)
            )
            session.execute(delete(Team).where(Team.id == team_id))


def _principal(
    team_id: UUID,
    *,
    subject: str = "rw3-operator",
    action: str = "request_update_thread",
) -> TrustedOperatorPrincipal:
    return TrustedOperatorPrincipal(
        issuer="https://host.example/identity",
        subject=subject,
        grants=frozenset({OperatorGrant(team_id, action)}),
    )


def _create_task(
    session_factory: sessionmaker[Session],
    fixture: Fixture,
    *,
    key: UUID | None = None,
    principal: TrustedOperatorPrincipal | None = None,
):
    request = UpdateThreadTaskRequest(
        thread_id=fixture.thread_id,
        idempotency_key=key or uuid4(),
    )
    result = OperatorApplicationAdapter(session_factory).create_update_thread_task(
        principal or _principal(fixture.team_id), request
    )
    return request, result


def _seed_hypothesis_and_link(
    session_factory: sessionmaker[Session],
    fixture: Fixture,
    *,
    hypothesis_id: UUID | None = None,
    evidence_id: UUID | None = None,
    created_at: datetime | None = None,
) -> tuple[UUID, UUID]:
    hypothesis_id = hypothesis_id or uuid4()
    evidence_id = evidence_id or uuid4()
    now = created_at or datetime.now(timezone.utc)
    with session_factory.begin() as session:
        session.add(
            Hypothesis(
                id=hypothesis_id,
                team_id=fixture.team_id,
                thread_id=fixture.thread_id,
                statement="Supply is increasing.",
                status="active",
                confidence="low",
                created_at=now,
                last_touched_at=now,
            )
        )
        session.flush()
        session.add(
            EvidenceLink(
                id=evidence_id,
                team_id=fixture.team_id,
                subject_kind="hypothesis",
                evaluation_id=None,
                hypothesis_id=hypothesis_id,
                originating_task_id=fixture.source_task_id,
                source_kind="signal",
                outcome_id=None,
                signal_id=fixture.signal_id,
                snapshot_ref=fixture.snapshot_ref,
                snapshot_hash=fixture.snapshot_hash,
                stance="supports",
                quote_text=_QUOTE,
                quote_start=_CONTENT.decode("utf-8").index(_QUOTE),
                quote_end=_CONTENT.decode("utf-8").index(_QUOTE) + len(_QUOTE),
                reference_key=f"rw3:{evidence_id}",
                created_at=now,
            )
        )
    return hypothesis_id, evidence_id


def _admit_fixture_task(
    session_factory: sessionmaker[Session], task_id: UUID
) -> None:
    # RW3.1 deliberately does not extend TaskRuntime. This fixture represents
    # the running Task state established by the later RW3 worker slice.
    with session_factory.begin() as session:
        task = session.get(Task, task_id)
        assert task is not None
        task.status = "running"
        task.attempt_count = 1


def test_host_creator_pins_policy_and_replays_without_execution(
    session_factory: sessionmaker[Session], rw3_fixture: Fixture
) -> None:
    with session_factory.begin() as session:
        session.add(
            TeamPolicy(
                id=uuid4(),
                team_id=rw3_fixture.team_id,
                version=2,
                schema_version=2,
                rules={},
            )
        )

    request, created = _create_task(session_factory, rw3_fixture)
    replayed = OperatorApplicationAdapter(session_factory).create_update_thread_task(
        _principal(rw3_fixture.team_id), request
    )

    assert created.status == "pending"
    assert created.replayed is False
    assert replayed.task_id == created.task_id
    assert replayed.status == "pending"
    assert replayed.replayed is True

    with session_factory() as session:
        task = session.get(Task, created.task_id)
        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == created.task_id,
                    Event.type == REQUEST_EVENT_TYPE,
                )
            )
        )
        assert task is not None
        assert task.task_type == "update_thread"
        assert task.status == "pending"
        assert task.attempt_count == 0
        assert task.max_attempts == MAX_ATTEMPTS
        assert task.policy_version == 2
        assert task.objective_id is None
        assert task.plan_id is None
        assert task.plan_action_id is None
        assert task.allowed_writes == ALLOWED_WRITES
        assert task.budget == TASK_BUDGET
        assert len(events) == 1
        assert set(events[0].payload) == {
            "schema_version",
            "task_id",
            "team_id",
            "thread_id",
            "policy_version",
            "requested_by_operator_id",
            "idempotency_key_hash",
            "request_fingerprint",
        }
        assert str(request.idempotency_key) not in str(events[0].payload)


def test_creator_rejects_wrong_action_without_task_or_event(
    session_factory: sessionmaker[Session], rw3_fixture: Fixture
) -> None:
    request = UpdateThreadTaskRequest(rw3_fixture.thread_id, uuid4())
    with pytest.raises(OperatorNotAuthorized):
        OperatorApplicationAdapter(session_factory).create_update_thread_task(
            _principal(rw3_fixture.team_id, action="operator_update"), request
        )
    with session_factory() as session:
        assert session.scalar(select(Task).where(Task.team_id == rw3_fixture.team_id,
                                                 Task.task_type == "update_thread")) is None


def test_same_key_replay_by_another_operator_conflicts(
    session_factory: sessionmaker[Session], rw3_fixture: Fixture
) -> None:
    request, created = _create_task(session_factory, rw3_fixture)
    with pytest.raises(OperatorTaskRequestConflict):
        OperatorApplicationAdapter(session_factory).create_update_thread_task(
            _principal(rw3_fixture.team_id, subject="different-operator"), request
        )
    with session_factory() as session:
        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == created.task_id,
                    Event.type == REQUEST_EVENT_TYPE,
                )
            )
        )
        assert len(events) == 1


def test_context_is_deterministic_bounded_and_replayable(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    _admit_fixture_task(session_factory, created.task_id)
    hypothesis_id, evidence_id = _seed_hypothesis_and_link(
        session_factory, rw3_fixture
    )

    assembler = UpdateThreadContextAssembler(session_factory, snapshot_store)
    first = assembler.assemble(created.task_id, 1)
    with session_factory.begin() as session:
        hypothesis = session.get(Hypothesis, hypothesis_id)
        assert hypothesis is not None
        hypothesis.statement = "Changed after Context assembly."

    second = assembler.assemble(created.task_id, 1)
    assert first.snapshot_ref == second.snapshot_ref
    assert first.content_hash == second.content_hash
    assert second.replayed is True
    assert first.document["hypotheses"][0]["statement"] == "Supply is increasing."
    assert first.document["evidence_links"][0]["id"] == str(evidence_id)
    assert first.document["source_snapshots"][0]["text"] == _CONTENT.decode("utf-8")

    with session_factory() as session:
        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == created.task_id,
                    Event.type == CONTEXT_EVENT_TYPE,
                )
            )
        )
        assert len(events) == 1


def test_context_fails_closed_when_active_hypothesis_bound_is_exceeded(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    _admit_fixture_task(session_factory, created.task_id)
    now = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        session.add_all(
            [
                Hypothesis(
                    id=uuid4(),
                    team_id=rw3_fixture.team_id,
                    thread_id=rw3_fixture.thread_id,
                    statement=f"Hypothesis {index}",
                    status="active",
                    confidence="low",
                    created_at=now + timedelta(microseconds=index),
                    last_touched_at=now,
                )
                for index in range(9)
            ]
        )

    with pytest.raises(
        UpdateThreadContextError,
        match="update_thread_hypothesis_bound_exceeded",
    ):
        UpdateThreadContextAssembler(session_factory, snapshot_store).assemble(
            created.task_id, 1
        )


def test_context_fails_closed_when_evidence_character_bound_is_exceeded(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    _admit_fixture_task(session_factory, created.task_id)
    hypothesis_id = uuid4()
    large_content = ("x" * 8_001).encode("utf-8")
    large_ref, large_hash = snapshot_store.put(large_content)
    now = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        signal = session.get(Signal, rw3_fixture.signal_id)
        assert signal is not None
        signal.snapshot_ref = large_ref
        signal.content_hash = large_hash
        session.add(
            Hypothesis(
                id=hypothesis_id,
                team_id=rw3_fixture.team_id,
                thread_id=rw3_fixture.thread_id,
                statement="Large evidence hypothesis.",
                status="active",
                confidence="low",
                created_at=now,
                last_touched_at=now,
            )
        )
        session.flush()
        session.add(
            EvidenceLink(
                id=uuid4(),
                team_id=rw3_fixture.team_id,
                subject_kind="hypothesis",
                evaluation_id=None,
                hypothesis_id=hypothesis_id,
                originating_task_id=rw3_fixture.source_task_id,
                source_kind="signal",
                outcome_id=None,
                signal_id=rw3_fixture.signal_id,
                snapshot_ref=large_ref,
                snapshot_hash=large_hash,
                stance="mentions",
                quote_text=None,
                quote_start=None,
                quote_end=None,
                reference_key=f"rw3:{uuid4()}",
                created_at=now,
            )
        )

    with pytest.raises(
        UpdateThreadContextError,
        match="update_thread_evidence_character_bound_exceeded",
    ):
        UpdateThreadContextAssembler(session_factory, snapshot_store).assemble(
            created.task_id, 1
        )
