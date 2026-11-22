"""RW-3.1 host Task creation and bounded Context proofs."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

import core.update_thread_worker as worker_module
from core.generation import (
    GenerationCostQuote,
    GenerationProviderError,
    GenerationResult,
    GenerationUsage,
)
from core.generation_cost import (
    GenerationCostReservation,
    TaskGenerationCostService,
)
from core.models import (
    Event,
    EvidenceLink,
    Hypothesis,
    Outcome,
    Signal,
    Task,
    TaskGenerationCharge,
    Team,
    TeamPolicy,
    Thread,
)
from core.operator_application import (
    InvalidOperatorPrincipal,
    OperatorApplicationAdapter,
    OperatorApplicationError,
    OperatorGrant,
    OperatorNotAuthorized,
    OperatorTaskRequestConflict,
    OperatorTaskRequestCorrupt,
    TrustedOperatorPrincipal,
)
from core.snapshot_store import SnapshotStore
from core.task_runtime import (
    AdmissionResult,
    FailureObservation,
    FailureResult,
    TaskNotEligible,
    TaskRuntime,
)
from core.update_thread import (
    ALLOWED_WRITES,
    MAX_ATTEMPTS,
    REQUEST_EVENT_TYPE,
    TASK_BUDGET,
    UpdateThreadTaskError,
    UpdateThreadTaskRequest,
    build_request_event_payload,
    task_id_for_request,
    validate_update_thread_task_request,
)
from core.update_thread_context import (
    CONTEXT_EVENT_TYPE,
    UpdateThreadContextAssembler,
    UpdateThreadContextError,
)
from core.update_thread_worker import (
    PROPOSALS_EVENT_TYPE,
    RECEIPT_EVENT_TYPE,
    UpdateThreadProposalPersistencePending,
    UpdateThreadWorker,
    UpdateThreadWorkerError,
)
from core.world_memory import HypothesisCreateProposal, OperatorUpdateRequest

_CONTENT = b"Market report: supply increased by 5 percent."
_QUOTE = "supply increased by 5 percent"


@dataclass(frozen=True)
class Fixture:
    team_id: UUID
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
    team_id, source_task_id, signal_id, thread_id = (
        uuid4() for _ in range(4)
    )
    policy_id = uuid4()
    snapshot_ref, snapshot_hash = snapshot_store.put(_CONTENT)
    now = datetime.now(timezone.utc)
    fixture = Fixture(
        team_id=team_id,
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
                delete(Outcome).where(Outcome.recorded_by_task_id.in_(task_ids))
            )
            session.execute(
                delete(TaskGenerationCharge).where(
                    TaskGenerationCharge.task_id.in_(task_ids)
                )
            )
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
    admission = TaskRuntime(session_factory).admit(task_id)
    assert admission.task_id == task_id
    assert admission.attempt_count == 1


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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_tool_calls", False),
        ("max_tool_calls", 0.0),
        ("deadline_seconds", True),
        ("deadline_seconds", 45.0),
    ],
)
def test_task_request_rejects_budget_integer_type_substitution(
    session_factory: sessionmaker[Session],
    rw3_fixture: Fixture,
    field: str,
    value: bool | float,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    tampered_budget = {**TASK_BUDGET, field: value}
    with session_factory.begin() as session:
        session.execute(
            update(Task)
            .where(Task.id == created.task_id)
            .values(budget=tampered_budget)
        )

    with session_factory() as session:
        task = session.get(Task, created.task_id)
        assert task is not None
        assert type(task.budget[field]) is type(value)
        with pytest.raises(
            UpdateThreadTaskError,
            match="update_thread_task_shape_invalid",
        ):
            validate_update_thread_task_request(session, task)


def test_creator_rejects_wrong_action_without_task_or_event(
    session_factory: sessionmaker[Session], rw3_fixture: Fixture
) -> None:
    request = UpdateThreadTaskRequest(rw3_fixture.thread_id, uuid4())
    with pytest.raises(OperatorNotAuthorized):
        OperatorApplicationAdapter(session_factory).create_update_thread_task(
            _principal(rw3_fixture.team_id, action="operator_update"), request
        )
    with session_factory() as session:
        task = session.scalar(
            select(Task).where(
                Task.team_id == rw3_fixture.team_id,
                Task.task_type == "update_thread",
            )
        )
        assert task is None


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
    now = datetime.now(timezone.utc)
    first_hypothesis_id, first_evidence_id = _seed_hypothesis_and_link(
        session_factory, rw3_fixture, created_at=now
    )
    second_hypothesis_id, second_evidence_id = _seed_hypothesis_and_link(
        session_factory, rw3_fixture, created_at=now
    )

    assembler = UpdateThreadContextAssembler(session_factory, snapshot_store)
    first = assembler.assemble(created.task_id, 1)
    with session_factory.begin() as session:
        hypothesis = session.get(Hypothesis, first_hypothesis_id)
        assert hypothesis is not None
        hypothesis.statement = "Changed after Context assembly."

    second = assembler.assemble(created.task_id, 1)
    expected_hypothesis_ids = sorted(
        [first_hypothesis_id, second_hypothesis_id]
    )
    evidence_id_by_hypothesis = {
        first_hypothesis_id: first_evidence_id,
        second_hypothesis_id: second_evidence_id,
    }
    expected_evidence_ids = [
        str(evidence_id_by_hypothesis[hypothesis_id])
        for hypothesis_id in expected_hypothesis_ids
    ]
    assert first.snapshot_ref == second.snapshot_ref
    assert first.content_hash == second.content_hash
    assert second.replayed is True
    assert [item["id"] for item in first.document["hypotheses"]] == [
        str(item) for item in expected_hypothesis_ids
    ]
    assert [item["id"] for item in first.document["evidence_links"]] == (
        expected_evidence_ids
    )
    assert next(
        item["statement"]
        for item in first.document["hypotheses"]
        if item["id"] == str(first_hypothesis_id)
    ) == "Supply is increasing."
    assert len(first.document["source_snapshots"]) == 1
    assert first.manifest["evidence_characters"] == 2 * len(_QUOTE)
    assert first.document["source_snapshots"][0]["snapshot_ref"] == (
        rw3_fixture.snapshot_ref
    )
    assert first.document["source_snapshots"][0]["snapshot_hash"] == (
        rw3_fixture.snapshot_hash
    )

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


@pytest.mark.parametrize(
    ("location", "field"),
    [
        ("event_manifest", "attempt"),
        ("event_manifest", "policy_version"),
        ("event_manifest", "evidence_characters"),
        ("snapshot_task", "attempt"),
        ("snapshot_task", "policy_version"),
        ("snapshot_policy", "version"),
    ],
)
def test_context_replay_rejects_boolean_substitution_for_integer_fields(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    location: str,
    field: str,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    _admit_fixture_task(session_factory, created.task_id)
    assembler = UpdateThreadContextAssembler(session_factory, snapshot_store)
    assembled = assembler.assemble(created.task_id, 1)
    assert assembled.replayed is False

    with session_factory.begin() as session:
        event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == CONTEXT_EVENT_TYPE,
            )
        )
        assert event is not None
        payload = dict(event.payload)

        if location == "event_manifest":
            payload["manifest"] = {
                **payload["manifest"],
                field: True,
            }
        else:
            document = json.loads(snapshot_store.read(payload["snapshot_ref"]))
            document_key = "task" if location == "snapshot_task" else "policy"
            document[document_key][field] = True
            snapshot_bytes = json.dumps(
                document,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            snapshot_ref, content_hash = snapshot_store.put(snapshot_bytes)
            payload["snapshot_ref"] = snapshot_ref
            payload["content_hash"] = content_hash

        session.execute(
            update(Event)
            .where(Event.id == event.id)
            .values(payload=payload)
        )

    if location == "event_manifest":
        with session_factory() as session:
            persisted_event = session.scalar(
                select(Event).where(
                    Event.task_id == created.task_id,
                    Event.type == CONTEXT_EVENT_TYPE,
                )
            )
            assert persisted_event is not None
            assert persisted_event.payload["manifest"][field] is True

    with pytest.raises(
        UpdateThreadContextError,
        match="update_thread_context_manifest_corrupt",
    ):
        assembler.assemble(created.task_id, 1)


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
    large_text = "x" * 8_001
    large_content = large_text.encode("utf-8")
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
                quote_text=large_text,
                quote_start=0,
                quote_end=len(large_text),
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




def test_request_identity_and_fingerprint_golden_vector() -> None:
    team_id = UUID("11111111-1111-4111-8111-111111111111")
    thread_id = UUID("33333333-3333-4333-8333-333333333333")
    idempotency_key = UUID("22222222-2222-4222-8222-222222222222")
    task_id = task_id_for_request(team_id, idempotency_key)
    assert str(task_id) == "446a9da6-8b5b-528b-a510-9a59388f10af"

    payload = build_request_event_payload(
        task_id=task_id,
        team_id=team_id,
        thread_id=thread_id,
        policy_version=2,
        requested_by_operator_id=(
            '{"iss":"https://host.example/identity","sub":"rw3-operator"}'
        ),
        idempotency_key=idempotency_key,
    )
    assert payload["idempotency_key_hash"] == (
        "sha256:b454f82c5857ebabf342b7258e5cf7def78b7cd975814119462973de9a38df10"
    )
    assert payload["request_fingerprint"] == (
        "sha256:53bde7957a90f3622b5773dd544f4e5e1033f3a41ec0093c4a8d930ca1c89529"
    )


def test_request_task_identity_is_stable_and_team_scoped(
    rw3_fixture: Fixture,
) -> None:
    key = uuid4()
    first = task_id_for_request(rw3_fixture.team_id, key)
    second = task_id_for_request(rw3_fixture.team_id, key)
    other_team = task_id_for_request(uuid4(), key)
    assert first == second
    assert first != other_team


def test_replay_keeps_original_policy_after_policy_advancement(
    session_factory: sessionmaker[Session], rw3_fixture: Fixture
) -> None:
    request, created = _create_task(session_factory, rw3_fixture)
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
    replayed = OperatorApplicationAdapter(session_factory).create_update_thread_task(
        _principal(rw3_fixture.team_id), request
    )
    assert replayed.task_id == created.task_id
    assert replayed.replayed is True
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        assert task is not None
        assert task.policy_version == 1


def test_same_key_for_another_thread_conflicts(
    session_factory: sessionmaker[Session], rw3_fixture: Fixture
) -> None:
    key = uuid4()
    request, _ = _create_task(session_factory, rw3_fixture, key=key)
    other_thread_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Thread(
                id=other_thread_id,
                team_id=rw3_fixture.team_id,
                domain="rw3_test",
                title="Different target",
                status="active",
            )
        )
    conflicting_request = UpdateThreadTaskRequest(other_thread_id, key)
    with pytest.raises(OperatorTaskRequestConflict):
        OperatorApplicationAdapter(session_factory).create_update_thread_task(
            _principal(rw3_fixture.team_id), conflicting_request
        )


def test_concurrent_same_key_creation_writes_one_request_event(
    session_factory: sessionmaker[Session], rw3_fixture: Fixture
) -> None:
    request = UpdateThreadTaskRequest(rw3_fixture.thread_id, uuid4())
    barrier = Barrier(2)

    def create():
        barrier.wait()
        return OperatorApplicationAdapter(session_factory).create_update_thread_task(
            _principal(rw3_fixture.team_id), request
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create(), range(2)))

    assert results[0].task_id == results[1].task_id
    assert sorted(result.replayed for result in results) == [False, True]
    with session_factory() as session:
        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == results[0].task_id,
                    Event.type == REQUEST_EVENT_TYPE,
                )
            )
        )
        assert len(events) == 1


def test_context_fails_closed_when_evidence_link_bound_is_exceeded(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    _admit_fixture_task(session_factory, created.task_id)
    hypothesis_id = uuid4()
    now = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        session.add(
            Hypothesis(
                id=hypothesis_id,
                team_id=rw3_fixture.team_id,
                thread_id=rw3_fixture.thread_id,
                statement="Evidence overflow hypothesis.",
                status="active",
                confidence="low",
                created_at=now,
                last_touched_at=now,
            )
        )
        session.flush()
        session.add_all(
            [
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
                    snapshot_ref=rw3_fixture.snapshot_ref,
                    snapshot_hash=rw3_fixture.snapshot_hash,
                    stance="mentions",
                    quote_text=None,
                    quote_start=None,
                    quote_end=None,
                    reference_key=f"rw3:{uuid4()}",
                    created_at=now + timedelta(microseconds=index),
                )
                for index in range(9)
            ]
        )

    with pytest.raises(
        UpdateThreadContextError,
        match="update_thread_evidence_link_bound_exceeded",
    ):
        UpdateThreadContextAssembler(session_factory, snapshot_store).assemble(
            created.task_id, 1
        )
    with session_factory() as session:
        event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == CONTEXT_EVENT_TYPE,
            )
        )
        assert event is None


def test_creator_fails_closed_on_tampered_request_fingerprint(
    session_factory: sessionmaker[Session], rw3_fixture: Fixture
) -> None:
    request, created = _create_task(session_factory, rw3_fixture)
    with session_factory.begin() as session:
        event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
        assert event is not None
        event.payload = {
            **event.payload,
            "request_fingerprint": "sha256:" + "0" * 64,
        }

    with pytest.raises(OperatorTaskRequestCorrupt):
        OperatorApplicationAdapter(session_factory).create_update_thread_task(
            _principal(rw3_fixture.team_id), request
        )


def test_context_rejects_quote_offsets_outside_source_snapshot(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    _admit_fixture_task(session_factory, created.task_id)
    _, evidence_id = _seed_hypothesis_and_link(session_factory, rw3_fixture)
    with session_factory.begin() as session:
        link = session.get(EvidenceLink, evidence_id)
        assert link is not None
        link.quote_start = len(_CONTENT) + 10
        link.quote_end = link.quote_start + len(_QUOTE)

    with pytest.raises(
        UpdateThreadContextError,
        match="update_thread_evidence_quote_mismatch",
    ):
        UpdateThreadContextAssembler(session_factory, snapshot_store).assemble(
            created.task_id, 1
        )
    with session_factory() as session:
        event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == CONTEXT_EVENT_TYPE,
            )
        )
        assert event is None


def test_context_is_reloaded_from_its_verified_snapshot_before_provider_use(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    _admit_fixture_task(session_factory, created.task_id)
    assembler = UpdateThreadContextAssembler(session_factory, snapshot_store)
    assembled = assembler.assemble(created.task_id, 1)

    # The dataclass is frozen, but its nested dictionaries are not. A caller
    # must not be able to mutate the provider input after Context verification.
    assembled.document["thread"]["title"] = "Forged in-memory title"
    verified = assembler.verify_context(assembled)

    assert verified.event_id == assembled.event_id
    assert verified.snapshot_ref == assembled.snapshot_ref
    assert verified.content_hash == assembled.content_hash
    assert verified.document["thread"]["title"] == "Supply conditions"
    assert verified.replayed is True


def test_task_runtime_admission_rejects_tampered_update_thread_request(
    session_factory: sessionmaker[Session],
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    with session_factory.begin() as session:
        event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
        assert event is not None
        payload = dict(event.payload)
        payload["thread_id"] = str(uuid4())
        session.execute(
            update(Event).where(Event.id == event.id).values(payload=payload)
        )
        task = session.get(Task, created.task_id)
        assert task is not None
        task.status = "pending"
        task.attempt_count = 0

    with pytest.raises(
        TaskNotEligible,
        match="update_thread_request_fingerprint_invalid",
    ):
        TaskRuntime(session_factory).admit(created.task_id)

    with session_factory() as session:
        task = session.get(Task, created.task_id)
        starts = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == created.task_id,
                    Event.type == "task_started",
                )
            )
        )
        assert task is not None
        assert task.status == "pending"
        assert task.attempt_count == 0
        assert starts == []


class _FixedAdmissionRuntime(TaskRuntime):
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
        admitted_monotonic: float,
    ) -> None:
        super().__init__(session_factory, snapshot_store)
        self._admitted_monotonic = admitted_monotonic

    def admit(self, task_id: UUID) -> AdmissionResult:
        admission = super().admit(task_id)
        return replace(
            admission,
            admitted_monotonic=self._admitted_monotonic,
        )


def test_retryable_provider_interruption_schedules_task_retry(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    class _InterruptedProvider(_FakeUpdateThreadProvider):
        def generate_raw(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            temperature: float = 0.1,
            timeout_seconds: float | None = None,
            deadline_monotonic: float | None = None,
        ) -> GenerationResult:
            self.calls += 1
            raise GenerationProviderError(
                "cloudflare_connection_or_timeout",
                retryable=True,
            )

    _, created = _create_task(session_factory, rw3_fixture)
    provider = _InterruptedProvider('{"proposals":[]}')

    with pytest.raises(
        UpdateThreadWorkerError,
        match="cloudflare_connection_or_timeout",
    ):
        UpdateThreadWorker(
            session_factory,
            snapshot_store,
            provider,
        ).run(created.task_id)

    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == created.task_id
            )
        )
        retry_events = set(
            session.scalars(
                select(Event.type).where(
                    Event.task_id == created.task_id,
                    Event.type.in_(
                        ["task_attempt_failed", "task_retry_scheduled"]
                    ),
                )
            )
        )
        assert task is not None
        assert task.status == "pending"
        assert task.attempt_count == 1
        assert charge is not None and charge.status == "unknown"
        assert retry_events == {
            "task_attempt_failed",
            "task_retry_scheduled",
        }


class _FakeUpdateThreadProvider:
    provider_name = "watch_test_fake"
    model = "watch-rw3-update-thread-fake"

    def __init__(self, raw_completion: str) -> None:
        self.raw_completion = raw_completion
        self.calls = 0
        self.timeout_seconds: float | None = None
        self.deadline_monotonic: float | None = None

    def maximum_request_cost(
        self, *, system_prompt: str, user_prompt: str
    ) -> GenerationCostQuote:
        input_tokens = (
            len(system_prompt.encode("utf-8"))
            + len(user_prompt.encode("utf-8"))
            + 128
        )
        return GenerationCostQuote(
            provider=self.provider_name,
            model=self.model,
            maximum_input_tokens=input_tokens,
            maximum_output_tokens=128,
            input_usd_per_million_tokens=Decimal("0.152"),
            output_usd_per_million_tokens=Decimal("0.287"),
            pricing_revision="watch-rw3-update-thread-fake-v1",
        )

    def generate_raw(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        timeout_seconds: float | None = None,
        deadline_monotonic: float | None = None,
    ) -> GenerationResult:
        self.calls += 1
        self.timeout_seconds = timeout_seconds
        self.deadline_monotonic = deadline_monotonic
        return GenerationResult(
            content={},
            model=self.model,
            usage=GenerationUsage(
                input_tokens=100,
                output_tokens=20,
                estimated_cost_usd=Decimal("0"),
            ),
            elapsed_seconds=0.001,
            request_id="rw3-fake-request",
            raw_content=self.raw_completion,
        )


def test_provider_timeout_at_task_deadline_is_terminal_and_keeps_charge_unknown(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        worker_module, "time", SimpleNamespace(monotonic=lambda: clock["now"])
    )

    class _DeadlineTimeoutProvider(_FakeUpdateThreadProvider):
        def generate_raw(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            temperature: float = 0.1,
            timeout_seconds: float | None = None,
            deadline_monotonic: float | None = None,
        ) -> GenerationResult:
            self.calls += 1
            self.timeout_seconds = timeout_seconds
            self.deadline_monotonic = deadline_monotonic
            assert deadline_monotonic is not None
            clock["now"] = deadline_monotonic
            raise GenerationProviderError(
                "cloudflare_connection_or_timeout",
                retryable=True,
            )

    _, created = _create_task(session_factory, rw3_fixture)
    provider = _DeadlineTimeoutProvider('{"proposals":[]}')

    with pytest.raises(
        UpdateThreadWorkerError,
        match="update_thread_deadline_exceeded",
    ):
        UpdateThreadWorker(
            session_factory,
            snapshot_store,
            provider,
            runtime=_FixedAdmissionRuntime(session_factory, snapshot_store, 100.0),
        ).run(created.task_id)

    assert provider.calls == 1
    assert provider.timeout_seconds == 30.0
    assert provider.deadline_monotonic == 145.0
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == created.task_id
            )
        )
        failed = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "task_failed",
            )
        )
        terminal_attempt_failed = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "task_attempt_failed",
            )
        )
        retry_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == created.task_id,
                    Event.type == "task_retry_scheduled",
                )
            )
        )
        durable_generation_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == created.task_id,
                    Event.type.in_(
                        [
                            RECEIPT_EVENT_TYPE,
                            PROPOSALS_EVENT_TYPE,
                            "update_thread_committed",
                            "update_thread_rejected",
                        ]
                    ),
                )
            )
        )
        assert task is not None and task.status == "failed"
        assert task.attempt_count == 1
        assert charge is not None and charge.status == "unknown"
        assert failed is not None
        assert failed.payload["failure_reason"] == "update_thread_deadline_exceeded"
        assert terminal_attempt_failed is not None
        assert retry_events == []
        assert durable_generation_events == []


def test_update_thread_worker_caps_provider_timeout_at_thirty_seconds(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        worker_module, "time", SimpleNamespace(monotonic=lambda: clock["now"])
    )
    _, created = _create_task(session_factory, rw3_fixture)
    provider = _FakeUpdateThreadProvider('{"proposals":[]}')

    UpdateThreadWorker(
        session_factory,
        snapshot_store,
        provider,
        runtime=_FixedAdmissionRuntime(session_factory, snapshot_store, 100.0),
    ).run(created.task_id)

    assert provider.calls == 1
    assert provider.timeout_seconds == 30.0
    assert provider.deadline_monotonic == 145.0


def test_update_thread_worker_provider_timeout_is_capped_by_remaining_deadline(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        worker_module, "time", SimpleNamespace(monotonic=lambda: clock["now"])
    )
    _, created = _create_task(session_factory, rw3_fixture)

    class _AdvancingCostService(TaskGenerationCostService):
        def reserve(
            self,
            task_id: UUID,
            quote: GenerationCostQuote,
            *,
            operation: str = "propose_strategy",
        ) -> GenerationCostReservation:
            reservation = super().reserve(
                task_id, quote, operation=operation
            )
            clock["now"] = 137.0
            return reservation

    provider = _FakeUpdateThreadProvider('{"proposals":[]}')
    worker = UpdateThreadWorker(
        session_factory,
        snapshot_store,
        provider,
        runtime=_FixedAdmissionRuntime(session_factory, snapshot_store, 100.0),
        cost_service=_AdvancingCostService(session_factory),
    )

    worker.run(created.task_id)

    assert provider.calls == 1
    assert provider.timeout_seconds == 8.0


def test_update_thread_worker_does_not_invoke_provider_after_deadline(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        worker_module, "time", SimpleNamespace(monotonic=lambda: clock["now"])
    )
    _, created = _create_task(session_factory, rw3_fixture)

    class _ExpiredCostService(TaskGenerationCostService):
        def reserve(
            self,
            task_id: UUID,
            quote: GenerationCostQuote,
            *,
            operation: str = "propose_strategy",
        ) -> GenerationCostReservation:
            reservation = super().reserve(
                task_id, quote, operation=operation
            )
            clock["now"] = 146.0
            return reservation

    provider = _FakeUpdateThreadProvider('{"proposals":[]}')
    worker = UpdateThreadWorker(
        session_factory,
        snapshot_store,
        provider,
        runtime=_FixedAdmissionRuntime(session_factory, snapshot_store, 100.0),
        cost_service=_ExpiredCostService(session_factory),
    )

    with pytest.raises(
        UpdateThreadWorkerError, match="update_thread_deadline_exceeded"
    ):
        worker.run(created.task_id)

    assert provider.calls == 0
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == created.task_id
            )
        )
        assert task is not None and task.status == "failed"
        assert charge is not None and charge.status == "unknown"


def test_update_thread_worker_discards_provider_result_returned_after_deadline(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        worker_module, "time", SimpleNamespace(monotonic=lambda: clock["now"])
    )

    class _LateProvider(_FakeUpdateThreadProvider):
        def generate_raw(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            temperature: float = 0.1,
            timeout_seconds: float | None = None,
            deadline_monotonic: float | None = None,
        ) -> GenerationResult:
            result = super().generate_raw(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
            )
            clock["now"] = 146.0
            return result

    _, created = _create_task(session_factory, rw3_fixture)
    provider = _LateProvider('{"proposals":[]}')
    with pytest.raises(
        UpdateThreadWorkerError, match="update_thread_deadline_exceeded"
    ):
        UpdateThreadWorker(
            session_factory,
            snapshot_store,
            provider,
            runtime=_FixedAdmissionRuntime(session_factory, snapshot_store, 100.0),
        ).run(created.task_id)

    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        receipt = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == RECEIPT_EVENT_TYPE,
            )
        )
        proposals = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        marker = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_committed",
            )
        )
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == created.task_id
            )
        )
        assert task is not None and task.status == "failed"
        assert receipt is None
        assert proposals is None
        assert marker is None
        assert charge is not None and charge.status == "unknown"


def test_update_thread_worker_checks_deadline_after_parsing(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        worker_module, "time", SimpleNamespace(monotonic=lambda: clock["now"])
    )

    original_parser = worker_module._parse_model_response

    def late_parser(raw_completion: str):
        parsed = original_parser(raw_completion)
        clock["now"] = 146.0
        return parsed

    monkeypatch.setattr(worker_module, "_parse_model_response", late_parser)
    _, created = _create_task(session_factory, rw3_fixture)
    provider = _FakeUpdateThreadProvider('{"proposals":[]}')

    with pytest.raises(
        UpdateThreadWorkerError, match="update_thread_deadline_exceeded"
    ):
        UpdateThreadWorker(
            session_factory,
            snapshot_store,
            provider,
            runtime=_FixedAdmissionRuntime(session_factory, snapshot_store, 100.0),
        ).run(created.task_id)

    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        proposals = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        assert task is not None and task.status == "failed"
        assert proposals is None


def test_update_thread_worker_rechecks_deadline_after_commit_lock(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        worker_module, "time", SimpleNamespace(monotonic=lambda: clock["now"])
    )
    _, created = _create_task(session_factory, rw3_fixture)
    provider = _FakeUpdateThreadProvider('{"proposals":[]}')
    worker = UpdateThreadWorker(
        session_factory,
        snapshot_store,
        provider,
        runtime=_FixedAdmissionRuntime(session_factory, snapshot_store, 100.0),
    )
    original_check = worker._check_deadline
    checks = {"count": 0}

    def expire_at_commit_gate(deadline: float) -> None:
        checks["count"] += 1
        if checks["count"] == 12:
            clock["now"] = 146.0
        original_check(deadline)

    monkeypatch.setattr(worker, "_check_deadline", expire_at_commit_gate)

    with pytest.raises(
        UpdateThreadProposalPersistencePending,
        match="update_thread_deadline_commit_recovery_pending",
    ):
        worker.run(created.task_id)

    assert provider.calls == 1
    assert checks["count"] == 12
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        proposals = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        marker = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_committed",
            )
        )
        assert task is not None and task.status == "running"
        assert proposals is not None
        assert marker is None


def test_update_thread_worker_leaves_persisted_proposals_for_recovery_after_deadline(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        worker_module, "time", SimpleNamespace(monotonic=lambda: clock["now"])
    )
    _, created = _create_task(session_factory, rw3_fixture)
    provider = _FakeUpdateThreadProvider('{"proposals":[]}')

    worker = UpdateThreadWorker(
        session_factory,
        snapshot_store,
        provider,
        runtime=_FixedAdmissionRuntime(session_factory, snapshot_store, 100.0),
    )
    record_proposals = worker._record_proposals

    def record_then_expire(*args: object, **kwargs: object):
        result = record_proposals(*args, **kwargs)
        clock["now"] = 146.0
        return result

    monkeypatch.setattr(worker, "_record_proposals", record_then_expire)

    with pytest.raises(
        UpdateThreadProposalPersistencePending,
        match="update_thread_deadline_commit_recovery_pending",
    ):
        worker.run(created.task_id)

    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        proposals = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        marker = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_committed",
            )
        )
        assert task is not None and task.status == "running"
        assert proposals is not None
        assert marker is None


@pytest.mark.parametrize(
    "deadline_check",
    [7, 8, 10],
)
def test_update_thread_worker_rechecks_deadline_during_proposal_persistence(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
    deadline_check: int,
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        worker_module, "time", SimpleNamespace(monotonic=lambda: clock["now"])
    )
    _, created = _create_task(session_factory, rw3_fixture)
    provider = _FakeUpdateThreadProvider('{"proposals":[]}')
    worker = UpdateThreadWorker(
        session_factory,
        snapshot_store,
        provider,
        runtime=_FixedAdmissionRuntime(session_factory, snapshot_store, 100.0),
    )
    original_check = worker._check_deadline
    checks = {"count": 0}

    def expire_during_proposal_persistence(deadline: float) -> None:
        checks["count"] += 1
        if checks["count"] == deadline_check:
            clock["now"] = 146.0
        original_check(deadline)

    monkeypatch.setattr(
        worker, "_check_deadline", expire_during_proposal_persistence
    )

    with pytest.raises(
        UpdateThreadWorkerError, match="update_thread_deadline_exceeded"
    ):
        worker.run(created.task_id)

    assert checks["count"] == deadline_check
    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        receipt = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == RECEIPT_EVENT_TYPE,
            )
        )
        proposals = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == created.task_id
            )
        )
        assert task is not None and task.status == "failed"
        assert receipt is not None
        assert proposals is None
        assert charge is not None and charge.status == "reconciled"


@pytest.mark.parametrize("proposal_seconds", [45, 46])
def test_update_thread_recovery_rejects_proposal_event_persisted_at_or_after_deadline(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
    proposal_seconds: int,
) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(
        worker_module, "time", SimpleNamespace(monotonic=lambda: clock["now"])
    )
    _, created = _create_task(session_factory, rw3_fixture)
    proposal_values = [
        {
            "kind": "hypothesis_create",
            "key": "late",
            "hypothesis_id": str(uuid4()),
            "statement": "A proposal persisted after the Task deadline.",
            "confidence": "low",
        }
    ]
    provider = _FakeUpdateThreadProvider(
        json.dumps({"proposals": proposal_values}, separators=(",", ":"))
    )
    worker = UpdateThreadWorker(
        session_factory,
        snapshot_store,
        provider,
        runtime=_FixedAdmissionRuntime(session_factory, snapshot_store, 100.0),
    )
    record_proposals = worker._record_proposals

    def record_then_expire(*args: object, **kwargs: object):
        result = record_proposals(*args, **kwargs)
        clock["now"] = 146.0
        return result

    monkeypatch.setattr(worker, "_record_proposals", record_then_expire)
    with pytest.raises(
        UpdateThreadProposalPersistencePending,
        match="update_thread_deadline_commit_recovery_pending",
    ):
        worker.run(created.task_id)

    with session_factory.begin() as session:
        started = session.scalar(
            select(Event.created_at).where(
                Event.task_id == created.task_id,
                Event.type == "task_started",
            )
        )
        proposal_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        assert started is not None
        assert proposal_event is not None
        proposal_event.created_at = started + timedelta(seconds=proposal_seconds)

    recovered = TaskRuntime(
        session_factory, snapshot_store
    ).recover_interrupted(now=started + timedelta(seconds=61))

    assert recovered.failed == (created.task_id,)
    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        assert task is not None and task.status == "failed"
        assert session.scalar(
            select(Hypothesis.id).where(
                Hypothesis.team_id == rw3_fixture.team_id
            )
        ) is None
        assert session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_committed",
            )
        ) is None
        assert session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type.in_(
                    (
                        "update_thread_proposal_accepted",
                        "update_thread_proposal_rejected",
                        "update_thread_committed",
                        "update_thread_rejected",
                    )
                ),
            )
        ) is None


@pytest.mark.parametrize(
    "tamper",
    [
        "attempt_zero",
        "attempt_negative",
        "attempt_boolean",
        "duplicate",
        "malformed",
        "future",
    ],
)
def test_update_thread_receipt_history_validation_rejects_invalid_history(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    tamper: str,
) -> None:
    from core.world_memory import (
        WorldMemoryError,
        _validate_update_thread_receipt_history,
    )

    _, created = _create_task(session_factory, rw3_fixture)
    UpdateThreadWorker(
        session_factory, snapshot_store, _FakeUpdateThreadProvider('{"proposals":[]}')
    ).run(created.task_id)

    with session_factory.begin() as session:
        task = session.get(Task, created.task_id)
        assert task is not None
        receipt = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == RECEIPT_EVENT_TYPE,
            )
        )
        assert receipt is not None
        payload = dict(receipt.payload)
        if tamper == "attempt_zero":
            payload["attempt"] = 0
        elif tamper == "attempt_negative":
            payload["attempt"] = -1
        elif tamper == "attempt_boolean":
            payload["attempt"] = True
        elif tamper == "malformed":
            payload.pop("raw_completion_text")
        elif tamper == "future":
            payload["attempt"] = task.attempt_count + 1
        elif tamper == "duplicate":
            session.add(
                Event(
                    id=uuid4(),
                    task_id=created.task_id,
                    type=RECEIPT_EVENT_TYPE,
                    payload=payload,
                    created_at=datetime.now(timezone.utc),
                )
            )
        if tamper != "duplicate":
            session.execute(
                update(Event).where(Event.id == receipt.id).values(payload=payload)
            )

        with pytest.raises(WorldMemoryError):
            _validate_update_thread_receipt_history(session, task)


def test_update_thread_task_contract_keeps_two_cent_budget_and_three_starts() -> None:
    assert TASK_BUDGET["max_cost_usd"] == 0.02
    assert MAX_ATTEMPTS == 3


def test_update_thread_worker_counts_reconciled_and_unknown_charges_before_next_call(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The production contract's $0.02 ceiling is intentionally non-binding
    # under the three-start maximum quote. A smaller test-only ceiling makes
    # the cumulative-exhaustion branch reachable without changing production
    # policy or the accepted Task shape.
    test_budget = {
        **TASK_BUDGET,
        "max_cost_usd": 0.0099,
    }
    monkeypatch.setattr("core.update_thread.TASK_BUDGET", test_budget)
    _, created = _create_task(session_factory, rw3_fixture)
    with session_factory.begin() as session:
        task = session.get(Task, created.task_id)
        assert task is not None
        task.budget = test_budget

    class _RetryableRuntime(TaskRuntime):
        def report_failure(self, failure: FailureObservation) -> FailureResult:
            return super().report_failure(
                FailureObservation(
                    task_id=failure.task_id,
                    attempt=failure.attempt,
                    observed_at=failure.observed_at,
                    reason=failure.reason,
                    retryable=True,
                )
            )

    class _CumulativeCostProvider(_FakeUpdateThreadProvider):
        def maximum_request_cost(
            self, *, system_prompt: str, user_prompt: str
        ) -> GenerationCostQuote:
            return GenerationCostQuote(
                provider=self.provider_name,
                model=self.model,
                maximum_input_tokens=31_872,
                maximum_output_tokens=128,
                input_usd_per_million_tokens=Decimal("0.152"),
                output_usd_per_million_tokens=Decimal("0.287"),
                pricing_revision="watch-rw3-update-thread-fake-v1",
            )

        def generate_raw(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            temperature: float = 0.1,
            timeout_seconds: float | None = None,
            deadline_monotonic: float | None = None,
        ) -> GenerationResult:
            self.calls += 1
            if self.calls == 1:
                return GenerationResult(
                    content={},
                    model=self.model,
                    usage=GenerationUsage(
                        input_tokens=31_872,
                        output_tokens=128,
                        estimated_cost_usd=Decimal("0"),
                    ),
                    elapsed_seconds=0.001,
                    request_id="rw3-cost-reconciled",
                    raw_content="not-json",
                )
            if self.calls == 2:
                raise GenerationProviderError(
                    "provider_temporarily_unavailable",
                    retryable=True,
                )
            raise AssertionError("provider_invoked_after_budget_exhaustion")

    provider = _CumulativeCostProvider('{"proposals":[]}')
    worker = UpdateThreadWorker(
        session_factory,
        snapshot_store,
        provider,
        runtime=_RetryableRuntime(session_factory, snapshot_store),
    )

    with pytest.raises(
        UpdateThreadWorkerError, match="update_thread_model_output_invalid"
    ):
        worker.run(created.task_id)
    with pytest.raises(
        UpdateThreadWorkerError, match="provider_temporarily_unavailable"
    ):
        worker.run(created.task_id)
    with pytest.raises(
        UpdateThreadWorkerError, match="task_generation_budget_exhausted"
    ):
        worker.run(created.task_id)

    assert provider.calls == 2
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        charges = list(
            session.scalars(
                select(TaskGenerationCharge)
                .where(TaskGenerationCharge.task_id == created.task_id)
                .order_by(TaskGenerationCharge.attempt_count)
            )
        )
        assert task is not None
        assert task.status == "failed"
        assert task.attempt_count == 3
        assert len(charges) == 2
        assert [charge.attempt_count for charge in charges] == [1, 2]
        assert [charge.operation for charge in charges] == [
            "update_thread",
            "update_thread",
        ]
        assert charges[0].status == "reconciled"
        assert charges[0].accounted_cost_usd == charges[0].reserved_cost_usd
        assert charges[1].status == "unknown"
        assert charges[1].accounted_cost_usd is None
        assert charges[1].reserved_cost_usd == charges[0].reserved_cost_usd
        cumulative_exposure = sum(
            (
                charge.accounted_cost_usd
                if charge.accounted_cost_usd is not None
                else charge.reserved_cost_usd
                for charge in charges
            ),
            start=Decimal("0"),
        )
        next_reservation = charges[0].reserved_cost_usd
        assert cumulative_exposure <= Decimal("0.0099")
        assert cumulative_exposure + next_reservation > Decimal("0.0099")
        assert session.scalar(
            select(Hypothesis.id).where(Hypothesis.team_id == rw3_fixture.team_id)
        ) is None
        assert session.scalar(
            select(EvidenceLink.id).where(
                EvidenceLink.team_id == rw3_fixture.team_id
            )
        ) is None
        assert session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        ) is None
        assert session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_committed",
            )
        ) is None




def test_update_thread_worker_records_context_identity_and_empty_proposal_set(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    provider = _FakeUpdateThreadProvider('{"proposals":[]}')
    worker = UpdateThreadWorker(
        session_factory, snapshot_store, provider
    )

    result = worker.run(created.task_id)

    assert provider.calls == 1
    assert result.proposals == ()
    assert result.reconciliation.status == "reconciled"
    with session_factory() as session:
        receipt = session.get(Event, result.receipt_event_id)
        proposal_event = session.get(Event, result.proposals_event_id)
        charge = session.get(TaskGenerationCharge, result.charge_id)
        context_event = session.get(Event, result.context.event_id)
        task = session.get(Task, created.task_id)
        assert receipt is not None
        assert proposal_event is not None
        assert charge is not None
        assert context_event is not None
        assert task is not None
        identity = {
            "context_event_id": str(context_event.id),
            "context_snapshot_ref": context_event.payload["snapshot_ref"],
            "context_content_hash": context_event.payload["content_hash"],
        }
        assert {
            key: receipt.payload[key] for key in identity
        } == identity
        assert {
            key: proposal_event.payload[key] for key in identity
        } == identity
        assert receipt.payload["raw_completion_text"] == '{"proposals":[]}'
        assert receipt.payload["actor_type"] == "model_worker"
        assert receipt.payload["operation"] == "update_thread"
        assert proposal_event.payload["proposals"] == []
        assert proposal_event.payload["proposal_fingerprint"] == (
            result.proposal_fingerprint
        )
        assert charge.operation == "update_thread"
        assert charge.status == "reconciled"
        assert task.status == "done"
        assert task.attempt_count == 1
        outcome = session.scalar(
            select(Outcome).where(
                Outcome.recorded_by_task_id == created.task_id,
                Outcome.outcome_type == "task_execution",
            )
        )
        completed_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "task_completed",
            )
        )
        assert outcome is not None
        assert completed_event is not None
        assert completed_event.payload["result_category"] == "success_no_change"
        assert session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_committed",
            )
        ) is None
        assert session.scalar(
            select(Hypothesis).where(Hypothesis.team_id == rw3_fixture.team_id)
        ) is None


@pytest.mark.parametrize(
    "raw_completion",
    ["not-json", '{"proposals":[],"proposals":[]}'],
)
def test_update_thread_worker_persists_valid_usage_before_parser_failure(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    raw_completion: str,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    provider = _FakeUpdateThreadProvider(raw_completion)
    worker = UpdateThreadWorker(
        session_factory, snapshot_store, provider
    )

    with pytest.raises(
        UpdateThreadWorkerError,
        match="update_thread_model_output_invalid",
    ):
        worker.run(created.task_id)

    assert provider.calls == 1
    with session_factory() as session:
        receipt = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == RECEIPT_EVENT_TYPE,
            )
        )
        proposal_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == created.task_id
            )
        )
        task = session.get(Task, created.task_id)
        assert receipt is not None
        assert receipt.payload["raw_completion_text"] == raw_completion
        assert proposal_event is None
        assert charge is not None
        assert charge.status == "reconciled"
        assert task is not None
        assert task.status == "failed"


def test_interrupted_provider_call_marks_reserved_charge_unknown_before_retry(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    class _InterruptedProvider(_FakeUpdateThreadProvider):
        def generate_raw(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            temperature: float = 0.1,
            timeout_seconds: float | None = None,
            deadline_monotonic: float | None = None,
        ) -> GenerationResult:
            self.calls += 1
            self.timeout_seconds = timeout_seconds
            raise KeyboardInterrupt

    _, created = _create_task(session_factory, rw3_fixture)
    provider = _InterruptedProvider('{"proposals":[]}')
    worker = UpdateThreadWorker(session_factory, snapshot_store, provider)

    with pytest.raises(KeyboardInterrupt):
        worker.run(created.task_id)

    with session_factory() as session:
        started = session.scalar(
            select(Event.created_at).where(
                Event.task_id == created.task_id,
                Event.type == "task_started",
            )
        )
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == created.task_id
            )
        )
        task = session.get(Task, created.task_id)
        assert started is not None
        assert charge is not None and charge.status == "reserved"
        assert task is not None and task.status == "running"
    recovered = TaskRuntime(
        session_factory, snapshot_store
    ).recover_interrupted(now=started + timedelta(seconds=61))

    assert recovered.retried == (created.task_id,)
    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == created.task_id
            )
        )
        unknown_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "generation_cost_unknown",
            )
        )
        receipt = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == RECEIPT_EVENT_TYPE,
            )
        )
        assert task is not None and task.status == "pending"
        assert charge is not None and charge.status == "unknown"
        assert unknown_event is not None
        assert receipt is None


@pytest.mark.parametrize(
    "output",
    [
        {"actor_type": "operator", "proposals": []},
        {
            "proposals": [
                {
                    "kind": "hypothesis_create",
                    "key": "forged",
                    "hypothesis_id": str(uuid4()),
                    "statement": "A proposal cannot provide its actor.",
                    "confidence": "low",
                    "operator_id": "forged-operator",
                }
            ]
        },
    ],
)
def test_model_output_cannot_supply_actor_identity(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    output: dict[str, object],
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    provider = _FakeUpdateThreadProvider(
        json.dumps(output, separators=(",", ":"))
    )

    with pytest.raises(
        UpdateThreadWorkerError,
        match="update_thread_model_output_invalid",
    ):
        UpdateThreadWorker(session_factory, snapshot_store, provider).run(
            created.task_id
        )

    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        assert task is not None and task.status == "failed"
        assert session.scalar(
            select(Hypothesis.id).where(
                Hypothesis.team_id == rw3_fixture.team_id
            )
        ) is None
        assert session.scalar(
            select(Event.id).where(
                Event.task_id == created.task_id,
                Event.type.in_(
                    (
                        "update_thread_proposal_accepted",
                        "update_thread_proposal_rejected",
                        "update_thread_committed",
                        "update_thread_rejected",
                    )
                ),
            )
        ) is None


@pytest.mark.parametrize(
    ("location", "field"),
    [
        ("event_manifest", "attempt"),
        ("event_manifest", "policy_version"),
        ("event_manifest", "evidence_characters"),
        ("snapshot_task", "attempt"),
        ("snapshot_task", "policy_version"),
        ("snapshot_policy", "version"),
    ],
)
def test_update_thread_worker_never_calls_provider_for_boolean_context_fields(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    location: str,
    field: str,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    _admit_fixture_task(session_factory, created.task_id)
    assembler = UpdateThreadContextAssembler(session_factory, snapshot_store)
    assembler.assemble(created.task_id, 1)

    with session_factory.begin() as session:
        event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == CONTEXT_EVENT_TYPE,
            )
        )
        assert event is not None
        payload = dict(event.payload)
        if location == "event_manifest":
            payload["manifest"] = {**payload["manifest"], field: True}
        else:
            document = json.loads(snapshot_store.read(payload["snapshot_ref"]))
            document_key = "task" if location == "snapshot_task" else "policy"
            document[document_key][field] = True
            snapshot_ref, content_hash = snapshot_store.put(
                json.dumps(
                    document,
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            )
            payload["snapshot_ref"] = snapshot_ref
            payload["content_hash"] = content_hash
        session.execute(
            update(Event).where(Event.id == event.id).values(payload=payload)
        )
        task = session.get(Task, created.task_id)
        assert task is not None
        task.status = "pending"
        task.attempt_count = 0

    provider = _FakeUpdateThreadProvider('{"proposals":[]}')
    with pytest.raises(UpdateThreadWorkerError):
        UpdateThreadWorker(session_factory, snapshot_store, provider).run(
            created.task_id
        )
    assert provider.calls == 0


@pytest.mark.parametrize(
    "tamper",
    ["boolean_manifest", "snapshot_hash", "duplicate_event", "future_attempt"],
)
def test_update_thread_worker_never_calls_provider_for_invalid_context(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    tamper: str,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    # Seed an attempt-bound Context, then return the Task to pending to model
    # a worker restart before provider invocation.
    with session_factory.begin() as session:
        task = session.get(Task, created.task_id)
        assert task is not None
        task.status = "running"
        task.attempt_count = 1
    assembler = UpdateThreadContextAssembler(session_factory, snapshot_store)
    assembled = assembler.assemble(created.task_id, 1)

    with session_factory.begin() as session:
        event = session.get(Event, assembled.event_id)
        assert event is not None
        if tamper == "boolean_manifest":
            payload = dict(event.payload)
            payload["manifest"] = {
                **payload["manifest"],
                "attempt": True,
            }
            session.execute(
                update(Event).where(Event.id == event.id).values(payload=payload)
            )
        elif tamper == "snapshot_hash":
            payload = dict(event.payload)
            payload["content_hash"] = "sha256:" + ("0" * 64)
            session.execute(
                update(Event).where(Event.id == event.id).values(payload=payload)
            )
        elif tamper == "duplicate_event":
            session.add(
                Event(
                    id=uuid4(),
                    task_id=created.task_id,
                    type=CONTEXT_EVENT_TYPE,
                    payload=dict(event.payload),
                    created_at=datetime.now(timezone.utc),
                )
            )
        else:
            payload = dict(event.payload)
            payload["attempt"] = 2
            session.execute(
                update(Event).where(Event.id == event.id).values(payload=payload)
            )
        task = session.get(Task, created.task_id)
        assert task is not None
        task.status = "pending"
        task.attempt_count = 0

    provider = _FakeUpdateThreadProvider('{"proposals":[]}')
    worker = UpdateThreadWorker(
        session_factory, snapshot_store, provider
    )
    with pytest.raises(UpdateThreadWorkerError):
        worker.run(created.task_id)

    assert provider.calls == 0
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        charges = list(
            session.scalars(
                select(TaskGenerationCharge).where(
                    TaskGenerationCharge.task_id == created.task_id
                )
            )
        )
        assert task is not None
        assert task.status == "failed"
        assert charges == []


@pytest.mark.parametrize("receipt_offset_seconds", [45, 46])
def test_update_thread_worker_does_not_materialize_receipt_only_recovery_after_deadline(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    receipt_offset_seconds: int,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    provider = _FakeUpdateThreadProvider('{"proposals":[]}')
    worker = UpdateThreadWorker(session_factory, snapshot_store, provider)
    function_name = f"fail_rw3_proposals_{uuid4().hex}"
    trigger_name = f"fail_rw3_proposals_{uuid4().hex}"

    with session_factory.begin() as session:
        session.connection().exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $fn$
            BEGIN
                IF NEW.type = '{PROPOSALS_EVENT_TYPE}' THEN
                    RAISE EXCEPTION 'injected proposal Event failure';
                END IF;
                RETURN NEW;
            END;
            $fn$ LANGUAGE plpgsql
            """
        )
        session.connection().exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON events
            FOR EACH ROW EXECUTE FUNCTION {function_name}()
            """
        )

    try:
        with pytest.raises(
            UpdateThreadProposalPersistencePending,
            match="update_thread_proposal_persistence_pending",
        ):
            worker.run(created.task_id)
    finally:
        with session_factory.begin() as session:
            session.connection().exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON events"
            )
            session.connection().exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )

    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        receipt = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == RECEIPT_EVENT_TYPE,
            )
        )
        proposal_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == created.task_id
            )
        )
        assert task is not None and task.status == "running"
        assert receipt is not None
        assert proposal_event is None
        assert charge is not None and charge.status == "reconciled"

    with session_factory() as session:
        started = session.scalar(
            select(Event.created_at).where(
                Event.task_id == created.task_id,
                Event.type == "task_started",
            )
        )
    assert started is not None
    receipt_timestamp = started + timedelta(seconds=receipt_offset_seconds)
    with session_factory.begin() as session:
        session.execute(
            update(Event)
            .where(
                Event.task_id == created.task_id,
                Event.type == RECEIPT_EVENT_TYPE,
            )
            .values(created_at=receipt_timestamp)
        )
    recovered = TaskRuntime(
        session_factory, snapshot_store
    ).recover_interrupted(now=started + timedelta(seconds=61))

    assert recovered.failed == (created.task_id,)
    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        failed_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "task_failed",
            )
        )
        proposal_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        assert task is not None and task.status == "failed"
        assert failed_event is not None
        assert failed_event.payload["failure_reason"] == (
            "update_thread_deadline_exceeded"
        )
        assert proposal_event is None
        receipt = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == RECEIPT_EVENT_TYPE,
            )
        )
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == created.task_id
            )
        )
        inconsistent_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_recovery_inconsistent",
            )
        )
        assert receipt is not None and receipt.created_at == receipt_timestamp
        assert charge is not None and charge.status == "reconciled"
        assert inconsistent_event is None
        assert session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_committed",
            )
        ) is None


def test_transient_model_commit_failure_rolls_back_and_recovers_same_proposals(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    proposal_values = [
        {
            "kind": "hypothesis_create",
            "key": key,
            "hypothesis_id": str(uuid4()),
            "statement": f"Durable proposal {key}.",
            "confidence": "low",
        }
        for key in ("first", "second")
    ]
    provider = _FakeUpdateThreadProvider(
        json.dumps({"proposals": proposal_values}, separators=(",", ":"))
    )
    worker = UpdateThreadWorker(session_factory, snapshot_store, provider)
    function_name = f"fail_rw3_commit_{uuid4().hex}"
    trigger_name = f"fail_rw3_commit_{uuid4().hex}"

    with session_factory.begin() as session:
        session.connection().exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'injected model commit failure';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        session.connection().exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON hypotheses
            FOR EACH ROW EXECUTE FUNCTION {function_name}()
            """
        )

    try:
        with pytest.raises(
            UpdateThreadProposalPersistencePending,
            match="update_thread_commit_or_finalization_pending",
        ):
            worker.run(created.task_id)
    finally:
        with session_factory.begin() as session:
            session.connection().exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON hypotheses"
            )
            session.connection().exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )

    assert provider.calls == 1
    with session_factory() as session:
        proposal_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        task = session.get(Task, created.task_id)
        assert proposal_event is not None
        assert task is not None and task.status == "running"
        assert session.scalar(
            select(Hypothesis.id).where(
                Hypothesis.team_id == rw3_fixture.team_id
            )
        ) is None
        assert session.scalar(
            select(Event.id).where(
                Event.task_id == created.task_id,
                Event.type.in_(
                    (
                        "update_thread_proposal_accepted",
                        "update_thread_proposal_rejected",
                        "update_thread_committed",
                        "update_thread_rejected",
                    )
                ),
            )
        ) is None
        fingerprint = proposal_event.payload["proposal_fingerprint"]
        started = session.scalar(
            select(Event.created_at).where(
                Event.task_id == created.task_id,
                Event.type == "task_started",
            )
        )
    assert started is not None

    recovered = TaskRuntime(
        session_factory, snapshot_store
    ).recover_interrupted(now=started + timedelta(seconds=61))

    assert recovered.completed == (created.task_id,)
    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        proposal_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        marker = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_committed",
            )
        )
        assert task is not None and task.status == "done"
        assert proposal_event is not None
        assert proposal_event.payload["proposal_fingerprint"] == fingerprint
        assert marker is not None
        assert marker.payload["proposal_fingerprint"] == fingerprint
        assert marker.payload["accepted_proposal_keys"] == ["first", "second"]
        assert len(
            list(
                session.scalars(
                    select(Hypothesis).where(
                        Hypothesis.team_id == rw3_fixture.team_id
                    )
                )
            )
        ) == 2


def test_marker_recovery_reconstructs_terminal_result_without_reapplying(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    hypothesis_id = uuid4()
    provider = _FakeUpdateThreadProvider(
        json.dumps(
            {
                "proposals": [
                    {
                        "kind": "hypothesis_create",
                        "key": "create",
                        "hypothesis_id": str(hypothesis_id),
                        "statement": "Recover the durable model commit.",
                        "confidence": "low",
                    }
                ]
            },
            separators=(",", ":"),
        )
    )
    worker = UpdateThreadWorker(session_factory, snapshot_store, provider)
    monkeypatch.setattr(worker._runtime, "finalize", lambda observation: None)

    worker.run(created.task_id)

    with session_factory() as session:
        task = session.get(Task, created.task_id)
        marker = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_committed",
            )
        )
        hypothesis_count = len(
            list(
                session.scalars(
                    select(Hypothesis).where(
                        Hypothesis.id == hypothesis_id
                    )
                )
            )
        )
        started = session.scalar(
            select(Event.created_at).where(
                Event.task_id == created.task_id,
                Event.type == "task_started",
            )
        )
        assert task is not None and task.status == "running"
        assert marker is not None
        assert hypothesis_count == 1
    assert started is not None

    recovered = TaskRuntime(
        session_factory, snapshot_store
    ).recover_interrupted(now=started + timedelta(seconds=61))

    assert recovered.completed == (created.task_id,)
    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        completed_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "task_completed",
            )
        )
        assert task is not None and task.status == "done"
        assert completed_event is not None
        assert (
            completed_event.payload["result_category"]
            == "success_update_thread_committed"
        )
        assert len(
            list(
                session.scalars(
                    select(Hypothesis).where(
                        Hypothesis.id == hypothesis_id
                    )
                )
            )
        ) == 1


@pytest.mark.parametrize(
    "tamper",
    [
        "context_snapshot_ref",
        "context_content_hash",
        "context_event_id",
        "task_id",
        "team_id",
        "thread_id",
        "policy_version",
        "attempt",
        "duplicate_proposals",
        "missing_context",
    ],
)
def test_permanent_provenance_conflict_records_inconsistent_without_writes(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    tamper: str,
) -> None:
    from sqlalchemy.exc import OperationalError

    from core.world_memory import WorldMemoryCommitService

    _, created = _create_task(session_factory, rw3_fixture)
    hypothesis_id = uuid4()
    provider = _FakeUpdateThreadProvider(
        json.dumps(
            {
                "proposals": [
                    {
                        "kind": "hypothesis_create",
                        "key": "create",
                        "hypothesis_id": str(hypothesis_id),
                        "statement": "A proposal with corrupted provenance.",
                        "confidence": "low",
                    }
                ]
            },
            separators=(",", ":"),
        )
    )

    def transient_commit_failure(
        self: WorldMemoryCommitService,
        session: Session,
        task: Task,
        attempt: int,
    ) -> None:
        raise OperationalError(
            "injected serialization failure", {}, RuntimeError("retry")
        )

    monkeypatch.setattr(
        WorldMemoryCommitService,
        "resume_update_thread_in_session",
        transient_commit_failure,
    )
    worker = UpdateThreadWorker(session_factory, snapshot_store, provider)
    with pytest.raises(UpdateThreadProposalPersistencePending):
        worker.run(created.task_id)
    monkeypatch.undo()

    with session_factory.begin() as session:
        proposal_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        assert proposal_event is not None
        if tamper == "missing_context":
            session.execute(
                delete(Event).where(
                    Event.id == UUID(proposal_event.payload["context_event_id"])
                )
            )
        elif tamper == "duplicate_proposals":
            session.add(
                Event(
                    id=uuid4(),
                    task_id=created.task_id,
                    type=PROPOSALS_EVENT_TYPE,
                    payload=dict(proposal_event.payload),
                    created_at=datetime.now(timezone.utc),
                )
            )
        else:
            tampered_payload = dict(proposal_event.payload)
            if tamper in {
                "context_snapshot_ref",
                "context_event_id",
            }:
                tampered_payload[tamper] = str(uuid4())
            elif tamper == "context_content_hash":
                tampered_payload[tamper] = "sha256:" + ("0" * 64)
            elif tamper in {"task_id", "team_id", "thread_id"}:
                tampered_payload[tamper] = str(uuid4())
            elif tamper in {"policy_version", "attempt"}:
                tampered_payload[tamper] += 1
            else:
                raise AssertionError(f"unhandled tamper case: {tamper}")
            session.execute(
                update(Event)
                .where(Event.id == proposal_event.id)
                .values(payload=tampered_payload)
            )
        started = session.scalar(
            select(Event.created_at).where(
                Event.task_id == created.task_id,
                Event.type == "task_started",
            )
        )
    assert started is not None

    recovered = TaskRuntime(
        session_factory, snapshot_store
    ).recover_interrupted(now=started + timedelta(seconds=61))

    assert recovered.failed == (created.task_id,)
    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        inconsistent = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_recovery_inconsistent",
            )
        )
        assert task is not None and task.status == "failed"
        assert inconsistent is not None
        assert (
            inconsistent.payload["failure_category"]
            == "update_thread_recovery_inconsistent"
        )
        assert session.scalar(
            select(Hypothesis.id).where(Hypothesis.id == hypothesis_id)
        ) is None
        assert session.scalar(
            select(Event.id).where(
                Event.task_id == created.task_id,
                Event.type.in_(
                    (
                        "update_thread_proposal_accepted",
                        "update_thread_proposal_rejected",
                        "update_thread_committed",
                        "update_thread_rejected",
                    )
                ),
            )
        ) is None


def test_missing_request_provenance_terminalizes_as_recovery_inconsistent(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    TaskRuntime(session_factory, snapshot_store).admit(created.task_id)
    with session_factory.begin() as session:
        session.execute(
            delete(Event).where(
                Event.task_id == created.task_id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
        started = session.scalar(
            select(Event.created_at).where(
                Event.task_id == created.task_id,
                Event.type == "task_started",
            )
        )
    assert started is not None

    recovered = TaskRuntime(
        session_factory, snapshot_store
    ).recover_interrupted(now=started + timedelta(seconds=61))

    assert recovered.failed == (created.task_id,)
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        marker = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_recovery_inconsistent",
            )
        )
        failed_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "task_failed",
            )
        )
        assert task is not None and task.status == "failed"
        assert marker is not None
        assert marker.payload["thread_id"] is None
        assert failed_event is not None
        assert session.scalar(
            select(Hypothesis.id).where(
                Hypothesis.team_id == rw3_fixture.team_id
            )
        ) is None


def test_update_thread_worker_rejects_live_provider_until_separately_authorized(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
) -> None:
    class _LiveProvider:
        provider_name = "cloudflare_workers_ai"

        def maximum_request_cost(
            self, *, system_prompt: str, user_prompt: str
        ) -> GenerationCostQuote:
            raise AssertionError("live provider must not be called")

        def generate_raw(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            temperature: float = 0.1,
            timeout_seconds: float | None = None,
            deadline_monotonic: float | None = None,
        ) -> GenerationResult:
            raise AssertionError("live provider must not be called")

    with pytest.raises(
        UpdateThreadWorkerError,
        match="update_thread_live_provider_not_authorized",
    ):
        UpdateThreadWorker(session_factory, snapshot_store, _LiveProvider())


def test_update_thread_committed_result_is_rejected_for_other_task_types(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    from core.task_runtime import TaskNotFinalizable, TerminalObservation

    with pytest.raises(
        TaskNotFinalizable,
        match="update_thread_result_wrong_task_type",
    ):
        TaskRuntime(session_factory, snapshot_store).finalize(
            TerminalObservation(
                task_id=rw3_fixture.source_task_id,
                attempt=1,
                result_category="success_update_thread_committed",
                observed_at=datetime.now(timezone.utc),
            )
        )


def test_update_thread_worker_receipt_and_charge_reconciliation_are_atomic(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    provider = _FakeUpdateThreadProvider('{"proposals":[]}')
    worker = UpdateThreadWorker(session_factory, snapshot_store, provider)
    function_name = f"fail_rw3_receipt_{uuid4().hex}"
    trigger_name = f"fail_rw3_receipt_{uuid4().hex}"

    with session_factory.begin() as session:
        session.connection().exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                IF NEW.type = '{RECEIPT_EVENT_TYPE}' THEN
                    RAISE EXCEPTION 'injected receipt Event failure';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        session.connection().exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON events
            FOR EACH ROW EXECUTE FUNCTION {function_name}()
            """
        )

    try:
        with pytest.raises(UpdateThreadWorkerError):
            worker.run(created.task_id)
    finally:
        with session_factory.begin() as session:
            session.connection().exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON events"
            )
            session.connection().exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )

    assert provider.calls == 1
    with session_factory() as session:
        receipt = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == RECEIPT_EVENT_TYPE,
            )
        )
        reconciled_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "generation_cost_reconciled",
            )
        )
        unknown_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "generation_cost_unknown",
            )
        )
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == created.task_id
            )
        )
        task = session.get(Task, created.task_id)
        assert receipt is None
        assert reconciled_event is None
        assert unknown_event is not None
        assert charge is not None
        assert charge.status == "unknown"
        assert charge.accounted_cost_usd is None
        assert task is not None
        assert task.status == "failed"


def test_update_thread_worker_commits_typed_proposal_with_model_actor(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    hypothesis_id = uuid4()
    raw_completion = json.dumps(
        {
            "proposals": [
                {
                    "kind": "hypothesis_create",
                    "key": "create-hypothesis-supply-pressure",
                    "hypothesis_id": str(hypothesis_id),
                    "statement": "Supply pressure is likely to persist.",
                    "confidence": "low",
                }
            ]
        },
        separators=(",", ":"),
    )
    provider = _FakeUpdateThreadProvider(raw_completion)
    worker = UpdateThreadWorker(session_factory, snapshot_store, provider)

    result = worker.run(created.task_id)

    assert provider.calls == 1
    assert len(result.proposals) == 1
    assert result.proposals[0].hypothesis_id == hypothesis_id
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        proposal_event = session.get(Event, result.proposals_event_id)
        receipt_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == RECEIPT_EVENT_TYPE,
            )
        )
        context_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == CONTEXT_EVENT_TYPE,
            )
        )
        assert task is not None
        assert task.status == "done"
        assert proposal_event is not None
        assert receipt_event is not None
        assert context_event is not None
        assert len(proposal_event.payload["proposals"]) == 1
        assert proposal_event.payload["proposals"][0]["hypothesis_id"] == str(
            hypothesis_id
        )
        hypothesis = session.scalar(
            select(Hypothesis).where(
                Hypothesis.team_id == rw3_fixture.team_id
            )
        )
        assert hypothesis is not None
        assert hypothesis.id == hypothesis_id
        marker = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_committed",
            )
        )
        assert marker is not None
        assert marker.payload["accepted_proposal_keys"] == [
            "create-hypothesis-supply-pressure"
        ]
        assert marker.payload["rejected_proposal_keys"] == []
        context_identity = {
            "context_event_id": str(context_event.id),
            "context_snapshot_ref": context_event.payload["snapshot_ref"],
            "context_content_hash": context_event.payload["content_hash"],
        }
        assert {
            key: receipt_event.payload[key] for key in context_identity
        } == context_identity
        assert {
            key: proposal_event.payload[key] for key in context_identity
        } == context_identity
        assert {
            key: marker.payload[key] for key in context_identity
        } == context_identity
        assert (
            marker.payload["proposal_fingerprint"]
            == proposal_event.payload["proposal_fingerprint"]
        )
        model_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == created.task_id,
                    Event.type.in_(
                        (
                            "update_thread_proposal_accepted",
                            "update_thread_proposal_rejected",
                            "update_thread_committed",
                            "hypothesis_created",
                        )
                    ),
                )
            )
        )
        assert model_events
        assert all("operator_id" not in event.payload for event in model_events)
        completed_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "task_completed",
            )
        )
        assert completed_event is not None
        assert (
            completed_event.payload["result_category"]
            == "success_update_thread_committed"
        )


@pytest.mark.parametrize(
    ("invalid_confidences", "expected_accepted", "expected_rejected"),
    [
        ({"second"}, ["first"], ["second"]),
        ({"first", "second"}, [], ["first", "second"]),
    ],
)
def test_update_thread_model_commit_partitions_proposals_exhaustively(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    invalid_confidences: set[str],
    expected_accepted: list[str],
    expected_rejected: list[str],
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    proposals = [
        {
            "kind": "hypothesis_create",
            "key": key,
            "hypothesis_id": str(uuid4()),
            "statement": f"Proposal {key}.",
            "confidence": "moderate" if key in invalid_confidences else "low",
        }
        for key in ("first", "second")
    ]
    provider = _FakeUpdateThreadProvider(
        json.dumps({"proposals": proposals}, separators=(",", ":"))
    )

    UpdateThreadWorker(session_factory, snapshot_store, provider).run(
        created.task_id
    )

    with session_factory() as session:
        task = session.get(Task, created.task_id)
        marker_type = (
            "update_thread_rejected"
            if not expected_accepted
            else "update_thread_committed"
        )
        marker = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == marker_type,
            )
        )
        assert task is not None
        assert task.status == ("failed" if not expected_accepted else "done")
        assert marker is not None
        assert marker.payload["accepted_proposal_keys"] == expected_accepted
        assert marker.payload["rejected_proposal_keys"] == expected_rejected
        assert len(
            list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == created.task_id,
                        Event.type == "update_thread_proposal_accepted",
                    )
                )
            )
        ) == len(expected_accepted)
        assert len(
            list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == created.task_id,
                        Event.type == "update_thread_proposal_rejected",
                    )
                )
            )
        ) == len(expected_rejected)
        assert len(
            list(
                session.scalars(
                    select(Hypothesis).where(
                        Hypothesis.team_id == rw3_fixture.team_id
                    )
                )
            )
        ) == len(expected_accepted)


def test_update_thread_worker_terminalizes_generation_cost_overrun_without_writes(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    class _OverrunProvider(_FakeUpdateThreadProvider):
        def generate_raw(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            temperature: float = 0.1,
            timeout_seconds: float | None = None,
            deadline_monotonic: float | None = None,
        ) -> GenerationResult:
            self.calls += 1
            self.timeout_seconds = timeout_seconds
            return GenerationResult(
                content={},
                model=self.model,
                usage=GenerationUsage(
                    input_tokens=100,
                    output_tokens=129,
                    estimated_cost_usd=Decimal("0"),
                ),
                elapsed_seconds=0.001,
                request_id="rw3-overrun-request",
                raw_content=self.raw_completion,
            )

    _, created = _create_task(session_factory, rw3_fixture)
    provider = _OverrunProvider('{"proposals":[]}')
    worker = UpdateThreadWorker(session_factory, snapshot_store, provider)

    with pytest.raises(
        UpdateThreadWorkerError,
        match="generation_cost_overrun",
    ):
        worker.run(created.task_id)

    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == created.task_id
            )
        )
        receipt = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == RECEIPT_EVENT_TYPE,
            )
        )
        overrun_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "generation_cost_overrun",
            )
        )
        failed_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "task_failed",
            )
        )
        assert task is not None and task.status == "failed"
        assert charge is not None and charge.status == "overrun"
        assert receipt is not None
        assert overrun_event is not None
        assert failed_event is not None
        assert failed_event.payload["failure_reason"] == "generation_cost_overrun"
        assert session.scalar(
            select(Event.id).where(
                Event.task_id == created.task_id,
                Event.type.in_(
                    (
                        PROPOSALS_EVENT_TYPE,
                        "update_thread_proposal_accepted",
                        "update_thread_proposal_rejected",
                        "update_thread_committed",
                        "update_thread_rejected",
                        "update_thread_recovery_inconsistent",
                    )
                ),
            )
        ) is None
        assert session.scalar(
            select(Hypothesis.id).where(
                Hypothesis.team_id == rw3_fixture.team_id
            )
        ) is None
        assert session.scalar(
            select(EvidenceLink.id).where(
                EvidenceLink.originating_task_id == created.task_id
            )
        ) is None


def test_model_commit_savepoint_rolls_back_staged_writes_before_inconsistent_marker(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    from core.models import ConfidenceChange
    from core.world_memory import WorldMemoryCommitService, WorldMemoryError

    _, created = _create_task(session_factory, rw3_fixture)
    hypothesis_id = uuid4()
    provider = _FakeUpdateThreadProvider(
        json.dumps(
            {
                "proposals": [
                    {
                        "kind": "hypothesis_create",
                        "key": "stage-then-fail",
                        "hypothesis_id": str(hypothesis_id),
                        "statement": "This staged row must be rolled back.",
                        "confidence": "low",
                    }
                ]
            },
            separators=(",", ":"),
        )
    )
    original_commit = WorldMemoryCommitService.commit_model_in_session

    def commit_then_raise(
        self: WorldMemoryCommitService,
        session: Session,
        task: Task,
        attempt: int,
        envelope=None,
    ):
        original_commit(self, session, task, attempt, envelope)
        raise WorldMemoryError("injected_post_stage_integrity_failure")

    monkeypatch.setattr(
        WorldMemoryCommitService,
        "commit_model_in_session",
        commit_then_raise,
    )

    UpdateThreadWorker(session_factory, snapshot_store, provider).run(
        created.task_id
    )

    assert provider.calls == 1
    with session_factory() as session:
        task = session.get(Task, created.task_id)
        receipt = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == RECEIPT_EVENT_TYPE,
            )
        )
        proposal_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
        inconsistent = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_recovery_inconsistent",
            )
        )
        assert task is not None and task.status == "failed"
        assert receipt is not None
        assert proposal_event is not None
        assert inconsistent is not None
        assert session.get(Hypothesis, hypothesis_id) is None
        assert session.scalar(
            select(EvidenceLink.id).where(
                EvidenceLink.originating_task_id == created.task_id
            )
        ) is None
        assert session.scalar(
            select(ConfidenceChange.id).where(
                ConfidenceChange.created_by_task_id == created.task_id
            )
        ) is None
        assert session.scalar(
            select(Event.id).where(
                Event.task_id == created.task_id,
                Event.type.in_(
                    (
                        "hypothesis_created",
                        "evidence_link_added",
                        "confidence_changed",
                        "hypothesis_rejected",
                        "hypothesis_superseded",
                        "update_thread_proposal_accepted",
                        "update_thread_proposal_rejected",
                        "update_thread_committed",
                        "update_thread_rejected",
                    )
                ),
            )
        ) is None


@pytest.mark.parametrize("field", ["schema_version", "attempt"])
def test_model_proposal_disposition_event_rejects_boolean_integer_substitution(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
    field: str,
) -> None:
    from core.world_memory import (
        WorldMemoryError,
        load_model_update_thread_envelope,
        validate_model_update_thread_marker,
    )

    _, created = _create_task(session_factory, rw3_fixture)
    hypothesis_id = uuid4()
    provider = _FakeUpdateThreadProvider(
        json.dumps(
            {
                "proposals": [
                    {
                        "kind": "hypothesis_create",
                        "key": "strict-integer-fields",
                        "hypothesis_id": str(hypothesis_id),
                        "statement": "Boolean integers are not valid provenance.",
                        "confidence": "low",
                    }
                ]
            },
            separators=(",", ":"),
        )
    )
    UpdateThreadWorker(session_factory, snapshot_store, provider).run(
        created.task_id
    )

    with session_factory.begin() as session:
        accepted_event = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_proposal_accepted",
            )
        )
        assert accepted_event is not None
        payload = dict(accepted_event.payload)
        payload[field] = True
        session.execute(
            update(Event)
            .where(Event.id == accepted_event.id)
            .values(payload=payload)
        )

    with session_factory() as session:
        task = session.get(Task, created.task_id)
        marker = session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_committed",
            )
        )
        assert task is not None
        assert marker is not None
        envelope = load_model_update_thread_envelope(
            session, task, 1, snapshot_store
        )
        with pytest.raises(
            WorldMemoryError,
            match="update_thread_proposal_event_invalid",
        ):
            validate_model_update_thread_marker(
                session, task, envelope, marker, snapshot_store
            )



# RW3.4 test-only proof obligations: model proposal boundaries and fingerprint.

def _model_proposal(index: int) -> dict[str, object]:
    return {
        "kind": "hypothesis_create",
        "key": f"hypothesis-{index}",
        "hypothesis_id": str(UUID(int=index + 1)),
        "statement": f"Hypothesis {index}",
        "confidence": "low",
    }


def test_model_proposal_count_accepts_eight_and_rejects_nine() -> None:
    accepted = worker_module._parse_model_response(
        json.dumps({"proposals": [_model_proposal(i) for i in range(8)]})
    )
    assert len(accepted.proposals) == 8

    with pytest.raises(ValidationError):
        worker_module._parse_model_response(
            json.dumps({"proposals": [_model_proposal(i) for i in range(9)]})
        )


def test_operator_update_proposal_count_remains_sixty_four() -> None:
    proposals = [
        HypothesisCreateProposal(
            kind="hypothesis_create",
            key=f"operator-hypothesis-{index}",
            hypothesis_id=UUID(int=index + 1),
            statement=f"Operator hypothesis {index}",
            confidence="low",
        )
        for index in range(64)
    ]
    request = OperatorUpdateRequest(
        thread_id=UUID(int=1000),
        idempotency_key=UUID(int=1001),
        proposals=proposals,
    )
    assert len(request.proposals) == 64

    with pytest.raises(ValidationError):
        OperatorUpdateRequest(
            thread_id=UUID(int=1000),
            idempotency_key=UUID(int=1002),
            proposals=[
                *proposals,
                HypothesisCreateProposal(
                    kind="hypothesis_create",
                    key="operator-hypothesis-64",
                    hypothesis_id=UUID(int=65),
                    statement="Operator hypothesis 64",
                    confidence="low",
                ),
            ],
        )


def test_model_proposal_fingerprint_has_canonical_golden_vector() -> None:
    context = SimpleNamespace(
        event_id=UUID("00000000-0000-0000-0000-000000000006"),
        snapshot_ref="sha256:context-snapshot",
        content_hash="sha256:" + "a" * 64,
    )
    proposal = _model_proposal(6)
    proposal["key"] = "create-one"
    proposal["statement"] = "Supply pressure persists."
    proposals = [proposal]
    actual = worker_module._fingerprint(
        task_id=UUID("00000000-0000-0000-0000-000000000001"),
        team_id=UUID("00000000-0000-0000-0000-000000000002"),
        thread_id=UUID("00000000-0000-0000-0000-000000000003"),
        attempt=1,
        policy_version=2,
        receipt_event_id=UUID("00000000-0000-0000-0000-000000000004"),
        context=context,
        charge_id=UUID("00000000-0000-0000-0000-000000000005"),
        proposals=proposals,
    )
    assert actual == (
        "sha256:57921c654b93a07f8d30065377d8e77b109394676482359c2007cb005d546893"
    )
    assert worker_module._canonical_json(
        {
            "z": "آخر",
            "a": ["first", "second"],
        }
    ) == '{"a":["first","second"],"z":"آخر"}'.encode("utf-8")


def test_model_proposal_fingerprint_preserves_proposal_array_order() -> None:
    context = SimpleNamespace(
        event_id=UUID("00000000-0000-0000-0000-000000000006"),
        snapshot_ref="sha256:context-snapshot",
        content_hash="sha256:" + "a" * 64,
    )
    proposals = [_model_proposal(1), _model_proposal(2)]
    arguments = {
        "task_id": UUID("00000000-0000-0000-0000-000000000001"),
        "team_id": UUID("00000000-0000-0000-0000-000000000002"),
        "thread_id": UUID("00000000-0000-0000-0000-000000000003"),
        "attempt": 1,
        "policy_version": 2,
        "receipt_event_id": UUID("00000000-0000-0000-0000-000000000004"),
        "context": context,
        "charge_id": UUID("00000000-0000-0000-0000-000000000005"),
    }
    forward = worker_module._fingerprint(**arguments, proposals=proposals)
    reverse = worker_module._fingerprint(
        **arguments, proposals=list(reversed(proposals))
    )
    assert forward != reverse


@pytest.mark.parametrize(
    ("principal", "error_type"),
    [
        (None, InvalidOperatorPrincipal),
        (
            TrustedOperatorPrincipal(
                issuer="https://host.example/identity",
                subject="",
                grants=frozenset(),
            ),
            InvalidOperatorPrincipal,
        ),
    ],
)
def test_creator_rejects_missing_or_malformed_principal_without_task_or_event(
    session_factory: sessionmaker[Session],
    rw3_fixture: Fixture,
    principal: TrustedOperatorPrincipal | None,
    error_type: type[Exception],
) -> None:
    request = UpdateThreadTaskRequest(rw3_fixture.thread_id, uuid4())
    with pytest.raises(error_type):
        OperatorApplicationAdapter(session_factory).create_update_thread_task(
            principal, request  # type: ignore[arg-type]
        )
    with session_factory() as session:
        assert session.scalar(
            select(Task.id).where(
                Task.team_id == rw3_fixture.team_id,
                Task.task_type == "update_thread",
            )
        ) is None
        assert session.scalar(
            select(Event.id).where(
                Event.type == REQUEST_EVENT_TYPE,
                Event.payload["team_id"].as_string() == str(rw3_fixture.team_id),
            )
        ) is None


def test_creator_rejects_wrong_team_grant_without_task_or_event(
    session_factory: sessionmaker[Session],
    rw3_fixture: Fixture,
) -> None:
    request = UpdateThreadTaskRequest(rw3_fixture.thread_id, uuid4())
    principal = TrustedOperatorPrincipal(
        issuer="https://host.example/identity",
        subject="rw3-operator",
        grants=frozenset({OperatorGrant(uuid4(), "request_update_thread")}),
    )
    with pytest.raises(OperatorNotAuthorized):
        OperatorApplicationAdapter(session_factory).create_update_thread_task(
            principal, request
        )
    with session_factory() as session:
        assert session.scalar(
            select(Task.id).where(
                Task.team_id == rw3_fixture.team_id,
                Task.task_type == "update_thread",
            )
        ) is None
        assert session.scalar(
            select(Event.id).where(
                Event.type == REQUEST_EVENT_TYPE,
                Event.task_id.in_(
                    select(Task.id).where(Task.team_id == rw3_fixture.team_id)
                ),
            )
        ) is None


def test_creator_rejects_inactive_team_without_task_or_event(
    session_factory: sessionmaker[Session],
    rw3_fixture: Fixture,
) -> None:
    with session_factory.begin() as session:
        team = session.get(Team, rw3_fixture.team_id)
        assert team is not None
        team.status = "inactive"
    request = UpdateThreadTaskRequest(rw3_fixture.thread_id, uuid4())
    with pytest.raises(
        OperatorApplicationError, match="update_thread_team_not_active"
    ):
        OperatorApplicationAdapter(session_factory).create_update_thread_task(
            _principal(rw3_fixture.team_id), request
        )
    with session_factory() as session:
        assert session.scalar(
            select(Task.id).where(Task.team_id == rw3_fixture.team_id)
        ) is not None  # The source fixture Task remains; no update_thread Task exists.
        assert session.scalar(
            select(Task.id).where(
                Task.team_id == rw3_fixture.team_id,
                Task.task_type == "update_thread",
            )
        ) is None


def test_creator_rejects_resolved_thread_without_task_or_event(
    session_factory: sessionmaker[Session],
    rw3_fixture: Fixture,
) -> None:
    with session_factory.begin() as session:
        thread = session.get(Thread, rw3_fixture.thread_id)
        assert thread is not None
        thread.status = "resolved"
    request = UpdateThreadTaskRequest(rw3_fixture.thread_id, uuid4())
    with pytest.raises(
        OperatorApplicationError, match="update_thread_target_not_available"
    ):
        OperatorApplicationAdapter(session_factory).create_update_thread_task(
            _principal(rw3_fixture.team_id), request
        )
    with session_factory() as session:
        assert session.scalar(
            select(Task.id).where(
                Task.team_id == rw3_fixture.team_id,
                Task.task_type == "update_thread",
            )
        ) is None


@pytest.mark.parametrize(
    "field",
    [
        "operator_id",
        "actor_type",
        "task_id",
        "team_id",
        "thread_id",
        "policy_version",
        "budget",
        "charge_id",
        "write_scope",
        "authority",
    ],
)
def test_model_proposal_rejects_forged_authority_fields(field: str) -> None:
    proposal = _model_proposal(0)
    proposal[field] = "forged"
    with pytest.raises(ValidationError):
        worker_module._parse_model_response(
            json.dumps({"proposals": [proposal]})
        )


def test_creator_rejects_cross_team_thread_without_task_or_event(
    session_factory: sessionmaker[Session],
    rw3_fixture: Fixture,
) -> None:
    foreign_team_id, foreign_thread_id = uuid4(), uuid4()
    with session_factory.begin() as session:
        session.add(
            Team(id=foreign_team_id, domain="foreign_rw3_test", status="active")
        )
        session.flush()
        session.add(
            TeamPolicy(
                id=uuid4(),
                team_id=foreign_team_id,
                version=1,
                schema_version=1,
                rules={},
            )
        )
        session.add(
            Thread(
                id=foreign_thread_id,
                team_id=foreign_team_id,
                domain="foreign_rw3_test",
                title="Foreign Thread",
                status="active",
            )
        )
        session.flush()

    request = UpdateThreadTaskRequest(foreign_thread_id, uuid4())
    with pytest.raises(OperatorNotAuthorized):
        OperatorApplicationAdapter(session_factory).create_update_thread_task(
            _principal(rw3_fixture.team_id), request
        )

    with session_factory() as session:
        assert session.scalar(
            select(Task.id).where(
                Task.team_id == foreign_team_id,
                Task.task_type == "update_thread",
            )
        ) is None
        assert session.scalar(
            select(Event.id).where(
                Event.type == REQUEST_EVENT_TYPE,
                Event.task_id.in_(
                    select(Task.id).where(
                        Task.team_id == foreign_team_id,
                        Task.task_type == "update_thread",
                    )
                ),
            )
        ) is None

    with session_factory.begin() as session:
        session.execute(delete(Thread).where(Thread.id == foreign_thread_id))
        session.execute(
            delete(TeamPolicy).where(TeamPolicy.team_id == foreign_team_id)
        )
        session.execute(delete(Team).where(Team.id == foreign_team_id))
