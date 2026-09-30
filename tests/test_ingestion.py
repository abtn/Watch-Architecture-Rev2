"""PostgreSQL integration tests for the K1 ingestion commit path."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from conftest import IngestionPrerequisites, make_proposal
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from core.ingestion import (
    IngestionProposal,
    IngestionResult,
    IngestionService,
    ProposalRejected,
    TaskNotFound,
)
from core.models import Event, Signal, Task, Team
from core.snapshot_store import SnapshotStore


def _service(
    session_factory: sessionmaker[Session], snapshot_store: SnapshotStore
) -> IngestionService:
    return IngestionService(session_factory, snapshot_store)


def _events_for_task(
    session_factory: sessionmaker[Session], task_id: UUID
) -> list[Event]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Event).where(Event.task_id == task_id).order_by(Event.type)
            )
        )


def test_successful_ingestion_commits_signal_event_and_snapshot(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    prerequisites: IngestionPrerequisites,
    tmp_path: Path,
) -> None:
    proposal = make_proposal(prerequisites)
    result = _service(session_factory, snapshot_store).ingest(proposal)

    with session_factory() as session:
        signal = session.get(Signal, result.signal_id)
        assert signal is not None
        assert signal.domain == "test_domain"
        assert signal.origin_url == proposal.origin_url
        assert signal.source_type == proposal.source_type
        assert signal.fetched_at == proposal.fetched_at
        assert signal.content_hash == proposal.claimed_content_hash
        assert signal.snapshot_ref == result.snapshot_ref
        assert session.scalar(select(func.count()).select_from(Signal)) == 1

    events = _events_for_task(session_factory, prerequisites.task_id)
    assert len(events) == 1
    assert events[0].type == "signal_ingested"
    assert events[0].task_id == prerequisites.task_id
    assert events[0].payload["signal_id"] == str(result.signal_id)
    assert events[0].payload["snapshot_ref"] == result.snapshot_ref
    assert snapshot_store.read(result.snapshot_ref) == proposal.content
    assert len([path for path in tmp_path.rglob("*") if path.is_file()]) == 1
    assert result.outcome == "signal_ingested"


def test_invalid_hash_records_rejection_without_publishing_snapshot(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    prerequisites: IngestionPrerequisites,
) -> None:
    snapshot_store = SnapshotStore(tmp_path)
    proposal = make_proposal(prerequisites, claimed_hash="sha256:" + "0" * 64)

    with pytest.raises(ProposalRejected) as raised:
        _service(session_factory, snapshot_store).ingest(proposal)

    assert raised.value.reason == "content_hash_mismatch"
    assert list(tmp_path.rglob("*")) == []
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 0
    events = _events_for_task(session_factory, prerequisites.task_id)
    assert len(events) == 1
    assert events[0].type == "proposal_rejected"
    assert events[0].payload["reason"] == "content_hash_mismatch"
    assert events[0].task_id == prerequisites.task_id


def test_database_failure_rolls_back_signal_and_success_event(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    database_engine: Engine,
    prerequisites: IngestionPrerequisites,
) -> None:
    trigger_suffix = uuid4().hex
    function_name = f"fail_event_insert_{trigger_suffix}"
    trigger_name = f"fail_event_trigger_{trigger_suffix}"
    with database_engine.begin() as connection:
        connection.execute(
            text(
                f"""
                CREATE FUNCTION {function_name}() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'injected Event persistence failure';
                END;
                $$ LANGUAGE plpgsql
                """
            )
        )
        connection.execute(
            text(
                f"""
                CREATE TRIGGER {trigger_name}
                BEFORE INSERT ON events
                FOR EACH ROW EXECUTE FUNCTION {function_name}()
                """
            )
        )

    try:
        with pytest.raises(DBAPIError):
            _service(session_factory, snapshot_store).ingest(
                make_proposal(prerequisites)
            )
    finally:
        with database_engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER {trigger_name} ON events"))
            connection.execute(text(f"DROP FUNCTION {function_name}()"))

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 0
    assert _events_for_task(session_factory, prerequisites.task_id) == []
    assert snapshot_store.read(
        f"snap://sha256/{hashlib.sha256(b'Test source content').hexdigest()}"
    ) == b"Test source content"


def test_duplicate_content_reuses_signal_and_emits_no_change(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    prerequisites: IngestionPrerequisites,
    unrelated_task,
) -> None:
    service = _service(session_factory, snapshot_store)
    first_proposal = make_proposal(prerequisites)
    first = service.ingest(first_proposal)
    with session_factory() as session:
        original_signal = session.get(Signal, first.signal_id)
        assert original_signal is not None
        original_fields = (
            original_signal.domain,
            original_signal.source_type,
            original_signal.origin_url,
            original_signal.fetched_at,
            original_signal.content_hash,
            original_signal.snapshot_ref,
        )
    second_proposal = make_proposal(prerequisites, task_id=unrelated_task)
    second = service.ingest(second_proposal)

    assert second.outcome == "fetch_no_change"
    assert second.signal_id == first.signal_id
    assert second.snapshot_ref == first.snapshot_ref
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 1
        signal = session.get(Signal, first.signal_id)
        assert signal is not None
        assert (
            signal.domain,
            signal.source_type,
            signal.origin_url,
            signal.fetched_at,
            signal.content_hash,
            signal.snapshot_ref,
        ) == original_fields
    assert snapshot_store.read(first.snapshot_ref) == first_proposal.content
    events = _events_for_task(session_factory, unrelated_task)
    assert len(events) == 1
    assert events[0].type == "fetch_no_change"
    assert events[0].payload["signal_id"] == str(first.signal_id)
    assert events[0].task_id == unrelated_task


def test_concurrent_identical_ingestion_converges_on_one_signal(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    prerequisites: IngestionPrerequisites,
    unrelated_task,
) -> None:
    service = _service(session_factory, snapshot_store)
    proposals = [
        make_proposal(prerequisites),
        make_proposal(prerequisites, task_id=unrelated_task),
    ]
    start_together = Barrier(2)

    def ingest_together(proposal: IngestionProposal) -> IngestionResult:
        start_together.wait(timeout=5)
        return service.ingest(proposal)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(ingest_together, proposals))

    assert {result.outcome for result in results} == {
        "signal_ingested",
        "fetch_no_change",
    }
    assert results[0].signal_id == results[1].signal_id
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 1
    assert len(_events_for_task(session_factory, prerequisites.task_id)) == 1
    assert len(_events_for_task(session_factory, unrelated_task)) == 1


def test_same_task_retry_reuses_existing_outcome(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    prerequisites: IngestionPrerequisites,
) -> None:
    service = _service(session_factory, snapshot_store)
    proposal = make_proposal(prerequisites)
    first = service.ingest(proposal)
    replay = service.ingest(proposal)

    assert first.outcome == "signal_ingested"
    assert replay.outcome == "replayed"
    assert replay.signal_id == first.signal_id
    assert replay.event_id == first.event_id
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 1
    assert len(_events_for_task(session_factory, prerequisites.task_id)) == 1


def test_concurrent_same_task_retry_commits_one_outcome_event(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    prerequisites: IngestionPrerequisites,
) -> None:
    service = _service(session_factory, snapshot_store)
    proposal = make_proposal(prerequisites)
    start_together = Barrier(2)

    def ingest_together() -> IngestionResult:
        start_together.wait(timeout=5)
        return service.ingest(proposal)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: ingest_together(), range(2)))

    assert {result.outcome for result in results} == {
        "signal_ingested",
        "replayed",
    }
    assert results[0].signal_id == results[1].signal_id
    assert results[0].event_id == results[1].event_id
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 1
    assert len(_events_for_task(session_factory, prerequisites.task_id)) == 1


def test_same_task_conflict_is_rejected_without_overwriting_outcome(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    prerequisites: IngestionPrerequisites,
) -> None:
    service = _service(session_factory, snapshot_store)
    first = service.ingest(make_proposal(prerequisites))
    conflict = make_proposal(
        prerequisites,
        content=b"Different content",
        origin_url=f"{prerequisites.origin_url}/other",
    )

    with pytest.raises(ProposalRejected) as raised:
        service.ingest(conflict)

    assert raised.value.reason == "task_outcome_conflict"
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 1
        assert session.get(Signal, first.signal_id) is not None
    events = _events_for_task(session_factory, prerequisites.task_id)
    assert {event.type for event in events} == {
        "signal_ingested",
        "proposal_rejected",
    }
    assert next(
        event for event in events if event.type == "proposal_rejected"
    ).payload["reason"] == "task_outcome_conflict"


@pytest.mark.parametrize(
    ("task_type", "status", "team_status", "allowed_writes", "reason"),
    [
        ("render_output", "running", "active", ["Signal"], "wrong_task_type"),
        ("ingest_source", "pending", "active", ["Signal"], "task_not_running"),
        ("ingest_source", "running", "paused", ["Signal"], "team_not_active"),
        (
            "ingest_source",
            "running",
            "active",
            ["SignalDisposition"],
            "write_scope_violation",
        ),
        (
            "ingest_source",
            "running",
            "active",
            ["Signal", "Snapshot", "Event"],
            "write_scope_violation",
        ),
    ],
)
def test_task_scope_and_provenance_failures_are_recorded(
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    prerequisites: IngestionPrerequisites,
    task_type: str,
    status: str,
    team_status: str,
    allowed_writes: list[str],
    reason: str,
) -> None:
    snapshot_store = SnapshotStore(tmp_path)
    with session_factory.begin() as session:
        task = session.get(Task, prerequisites.task_id)
        team = session.get(Team, prerequisites.team_id)
        assert task is not None and team is not None
        task.task_type = task_type
        task.status = status
        task.allowed_writes = allowed_writes
        team.status = team_status

    proposal = make_proposal(prerequisites)
    with pytest.raises(ProposalRejected) as raised:
        _service(session_factory, snapshot_store).ingest(proposal)
    assert raised.value.reason == reason
    assert list(tmp_path.rglob("*")) == []
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 0
    events = _events_for_task(session_factory, prerequisites.task_id)
    assert len(events) == 1
    assert events[0].type == "proposal_rejected"
    assert events[0].payload["reason"] == reason
    assert events[0].task_id == prerequisites.task_id


def test_missing_task_cannot_receive_rejection_event(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    prerequisites: IngestionPrerequisites,
) -> None:
    proposal = make_proposal(prerequisites, task_id=uuid4())

    with pytest.raises(TaskNotFound):
        _service(session_factory, snapshot_store).ingest(proposal)

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 0
        assert session.scalar(select(func.count()).select_from(Event)) == 0


def test_ingestion_scope_keeps_worker_write_and_kernel_effects_separate(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    prerequisites: IngestionPrerequisites,
) -> None:
    with session_factory() as session:
        task = session.get(Task, prerequisites.task_id)
        assert task is not None
        assert task.allowed_writes == ["Signal"]

    result = _service(session_factory, snapshot_store).ingest(
        make_proposal(prerequisites)
    )
    events = _events_for_task(session_factory, prerequisites.task_id)
    assert result.outcome == "signal_ingested"
    assert len(events) == 1
    assert events[0].type == "signal_ingested"
    assert snapshot_store.read(result.snapshot_ref) == b"Test source content"


def test_snapshot_store_is_content_addressed_and_never_overwrites(
    snapshot_store: SnapshotStore,
) -> None:
    content = b"immutable content"
    reference, content_hash = snapshot_store.put(content)
    duplicate_reference, duplicate_hash = snapshot_store.put(content)

    assert reference == f"snap://sha256/{hashlib.sha256(content).hexdigest()}"
    assert duplicate_reference == reference
    assert duplicate_hash == content_hash
    assert snapshot_store.read(reference) == content


def test_unconfigured_source_is_rejected_without_signal(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    prerequisites: IngestionPrerequisites,
) -> None:
    proposal = make_proposal(
        prerequisites,
        origin_url="https://example.test/not-configured",
    )

    with pytest.raises(ProposalRejected) as raised:
        _service(session_factory, snapshot_store).ingest(proposal)

    assert raised.value.reason == "source_not_configured"
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Signal)) == 0
    event = _events_for_task(session_factory, prerequisites.task_id)[0]
    assert event.type == "proposal_rejected"
    assert event.payload["reason"] == "source_not_configured"
