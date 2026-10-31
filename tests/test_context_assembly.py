from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from core.context_assembly import TaskContextAssembler, TaskContextError
from core.embeddings import EmbeddingSpace
from core.knowledge_index import RetrievedPassage, content_hash, text_hash
from core.models import Event, Objective, Signal, Task, Team, TeamPolicy
from core.snapshot_store import SnapshotStore
from core.state_assessment import StateAssessmentBuilder


@dataclass
class _AssemblyFixture:
    task_id: UUID
    team_id: UUID
    objective_id: UUID
    policy_id: UUID
    signal_id: UUID
    source_url: str
    source_type: str
    source_text: bytes


class _FakeRetriever:
    def __init__(self, passages: tuple[RetrievedPassage, ...]) -> None:
        self.passages = passages
        self.calls: list[tuple[UUID, str]] = []

    def retrieve(self, team_id: UUID, query: str) -> tuple[RetrievedPassage, ...]:
        self.calls.append((team_id, query))
        return self.passages


@pytest.fixture
def context_fixture(
    session_factory: sessionmaker[Session], snapshot_store: SnapshotStore
):
    team_id, policy_id, objective_id, task_id, signal_id = (
        uuid4() for _ in range(5)
    )
    source_url = "https://example.test/context-assembly"
    source_type = "test_feed"
    source_text = b"Alpha evidence from the configured scientific source."
    snapshot_ref, stored_hash = snapshot_store.put(source_text)
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="science", status="active"))
        session.flush()
        session.add(
            TeamPolicy(
                id=policy_id,
                team_id=team_id,
                version=1,
                rules={
                    "sources": [
                        {"origin_url": source_url, "source_type": source_type}
                    ],
                    "review": {"update_gating": True},
                },
            )
        )
        session.flush()
        session.add(
            Objective(
                id=objective_id,
                team_id=team_id,
                statement="Gather scientific evidence about alpha.",
                status="active",
            )
        )
        session.add(
            Task(
                id=task_id,
                team_id=team_id,
                objective_id=objective_id,
                task_type="propose_strategy",
                status="running",
                policy_version=1,
                allowed_writes=[],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.05,
                    "deadline_seconds": 60,
                },
                created_at=now,
                max_attempts=3,
            )
        )
        session.add(
            Signal(
                id=signal_id,
                domain="science",
                source_type=source_type,
                origin_url=source_url,
                fetched_at=now,
                content_hash=stored_hash,
                snapshot_ref=snapshot_ref,
            )
        )

    passage_text = source_text.decode()
    space = EmbeddingSpace(
        provider="test-fake",
        model="context-test-embedding",
        revision="r1",
        dimensions=4,
        configuration="test-config-v1",
    )
    passage = RetrievedPassage(
        signal_id=signal_id,
        source_url=source_url,
        source_type=source_type,
        snapshot_ref=snapshot_ref,
        content_hash=stored_hash,
        chunk_id=uuid4(),
        chunk_index=0,
        text=passage_text,
        chunk_hash=text_hash(passage_text),
        score=1.0 / 61,
        lexical_rank=1,
        vector_rank=None,
        embedding_space_key=space.key,
        embedding_provider=space.provider,
        embedding_model=space.model,
        embedding_revision=space.revision,
        embedding_configuration=space.configuration,
        embedding_dimensions=space.dimensions,
    )
    fixture = _AssemblyFixture(
        task_id,
        team_id,
        objective_id,
        policy_id,
        signal_id,
        source_url,
        source_type,
        source_text,
    )
    try:
        yield fixture, (passage,)
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Signal).where(Signal.id == signal_id))
            session.execute(delete(Task).where(Task.id == task_id))
            session.execute(delete(Objective).where(Objective.id == objective_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


def test_assembly_persists_bounded_context_snapshot_and_manifest(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    context_fixture,
) -> None:
    fixture, passages = context_fixture
    retriever = _FakeRetriever(passages)
    assembler = TaskContextAssembler(session_factory, snapshot_store, retriever)

    result = assembler.assemble(fixture.task_id)

    assert result.replayed is False
    assert result.manifest["logical_core"] == "domain_knowledge"
    assert result.manifest["query_hash"].startswith("sha256:")
    assert result.manifest["assessment_basis_sha256"] == result.assessment.basis.sha256
    assert result.manifest["selected"][0]["signal_id"] == str(fixture.signal_id)
    assert result.manifest["selected"][0]["source_snapshot_ref"].startswith(
        "snap://sha256/"
    )
    assert result.manifest["embedding_spaces"][0]["model"] == "context-test-embedding"
    assert result.document["objective"]["statement"] == (
        "Gather scientific evidence about alpha."
    )
    assert result.document["knowledge"]["domain_knowledge"][0]["text"] == (
        fixture.source_text.decode()
    )
    assert snapshot_store.read(result.snapshot_ref) == (
        __import__("json").dumps(
            result.document,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    with session_factory() as session:
        event = session.get(Event, result.event_id)
        assert event is not None
        assert event.task_id == fixture.task_id
        assert event.type == "context_assembled"
        assert event.payload["snapshot_ref"] == result.snapshot_ref
        assert event.payload["content_hash"] == result.content_hash
        rows = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == fixture.task_id,
                    Event.type == "context_assembled",
                )
            )
        )
        assert len(rows) == 1
    assert retriever.calls == [
        (fixture.team_id, "Gather scientific evidence about alpha.")
    ]


def test_context_event_does_not_invalidate_domain_state_assessment(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    context_fixture,
) -> None:
    fixture, passages = context_fixture
    builder = StateAssessmentBuilder(session_factory)
    before = builder.build(
        fixture.objective_id,
        created_at=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
    )

    TaskContextAssembler(
        session_factory, snapshot_store, _FakeRetriever(passages)
    ).assemble(fixture.task_id)

    after = builder.build(
        fixture.objective_id,
        created_at=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
    )
    assert before == after
    assert before.basis.event_ids == after.basis.event_ids


def test_exact_context_assembly_replay_reuses_snapshot_and_event(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    context_fixture,
) -> None:
    fixture, passages = context_fixture
    assembler = TaskContextAssembler(
        session_factory, snapshot_store, _FakeRetriever(passages)
    )

    first = assembler.assemble(fixture.task_id)
    second = assembler.assemble(fixture.task_id)

    assert first.snapshot_ref == second.snapshot_ref
    assert first.content_hash == second.content_hash
    assert first.event_id == second.event_id
    assert second.replayed is True


def test_changed_context_cannot_replace_the_original_snapshot_or_manifest(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    context_fixture,
) -> None:
    fixture, passages = context_fixture
    assembler = TaskContextAssembler(
        session_factory, snapshot_store, _FakeRetriever(passages)
    )
    first = assembler.assemble(fixture.task_id)
    with session_factory.begin() as session:
        objective = session.get(Objective, fixture.objective_id)
        assert objective is not None
        objective.statement = "A different objective."

    with pytest.raises(TaskContextError, match="context_replay_conflict"):
        assembler.assemble(fixture.task_id)

    with session_factory() as session:
        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == fixture.task_id,
                    Event.type == "context_assembled",
                )
            )
        )
        assert len(events) == 1
        assert events[0].payload["snapshot_ref"] == first.snapshot_ref
        assert snapshot_store.read(first.snapshot_ref)


def test_context_rejects_retrieved_material_revoked_by_current_policy(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    context_fixture,
) -> None:
    fixture, passages = context_fixture
    with session_factory.begin() as session:
        policy = session.get(TeamPolicy, fixture.policy_id)
        assert policy is not None
        policy.rules = {"sources": []}

    assembler = TaskContextAssembler(
        session_factory, snapshot_store, _FakeRetriever(passages)
    )
    with pytest.raises(TaskContextError, match="retrieval_candidate_not_authorized"):
        assembler.assemble(fixture.task_id)


@pytest.mark.parametrize(
    ("status", "allowed_writes", "reason"),
    [
        ("pending", [], "task_not_running"),
        ("running", ["Event"], "task_write_scope_violation"),
    ],
)
def test_context_assembly_preserves_task_scope(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    context_fixture,
    status: str,
    allowed_writes: list[str],
    reason: str,
) -> None:
    fixture, passages = context_fixture
    with session_factory.begin() as session:
        task = session.get(Task, fixture.task_id)
        assert task is not None
        task.status = status
        task.allowed_writes = allowed_writes

    assembler = TaskContextAssembler(
        session_factory, snapshot_store, _FakeRetriever(passages)
    )
    with pytest.raises(TaskContextError, match=reason):
        assembler.assemble(fixture.task_id)
