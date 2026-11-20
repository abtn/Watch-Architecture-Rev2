"""RW-3.1 host Task creation and bounded Context proofs."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from core.generation import (
    GenerationCostQuote,
    GenerationResult,
    GenerationUsage,
)
from core.models import (
    Event,
    EvidenceLink,
    Hypothesis,
    Signal,
    Task,
    TaskGenerationCharge,
    Team,
    TeamPolicy,
    Thread,
)
from core.operator_application import (
    OperatorApplicationAdapter,
    OperatorGrant,
    OperatorNotAuthorized,
    OperatorTaskRequestConflict,
    OperatorTaskRequestCorrupt,
    TrustedOperatorPrincipal,
)
from core.snapshot_store import SnapshotStore
from core.task_runtime import TaskNotEligible, TaskRuntime
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


class _FakeUpdateThreadProvider:
    provider_name = "watch_test_fake"
    model = "watch-rw3-update-thread-fake"

    def __init__(self, raw_completion: str) -> None:
        self.raw_completion = raw_completion
        self.calls = 0

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
    ) -> GenerationResult:
        self.calls += 1
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
        assert task.status == "running"
        assert task.attempt_count == 1
        assert session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "update_thread_committed",
            )
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


def test_update_thread_worker_leaves_receipted_proposals_resumable_on_write_failure(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    rw3_fixture: Fixture,
) -> None:
    _, created = _create_task(session_factory, rw3_fixture)
    provider = _FakeUpdateThreadProvider('{"proposals":[]}')
    worker = UpdateThreadWorker(session_factory, snapshot_store, provider)
    function_name = f"fail_rw3_proposals_{uuid4().hex}"
    trigger_name = f"fail_rw3_proposals_{uuid4().hex}"

    with session_factory.begin() as session:
        session.connection().exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                IF NEW.type = '{PROPOSALS_EVENT_TYPE}' THEN
                    RAISE EXCEPTION 'injected proposal Event failure';
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
        assert task is not None
        assert task.status == "running"
        assert receipt is not None
        assert proposal_event is None
        assert charge is not None
        assert charge.status == "reconciled"
        assert session.scalar(
            select(Event).where(
                Event.task_id == created.task_id,
                Event.type == "task_failed",
            )
        ) is None


def test_update_thread_worker_rejects_live_provider_until_separately_authorized(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
) -> None:
    class _LiveProvider:
        provider_name = "cloudflare_workers_ai"

    with pytest.raises(
        UpdateThreadWorkerError,
        match="update_thread_live_provider_not_authorized",
    ):
        UpdateThreadWorker(session_factory, snapshot_store, _LiveProvider())


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
