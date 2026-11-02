from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Sequence
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from core.context_assembly import TaskContextAssembler
from core.embeddings import EmbeddingBatch, EmbeddingSpace
from core.knowledge_index import (
    HybridKnowledgeRetriever,
    TeamExperienceIndexer,
)
from core.models import (
    Event,
    KnowledgeItem,
    LearningChange,
    Objective,
    Outcome,
    Task,
    Team,
    TeamExperienceChunk,
    TeamExperienceIndexState,
    TeamPolicy,
)
from core.policy import InvalidPolicyError, knowledge_item_review_interval_days
from core.snapshot_store import SnapshotStore
from core.task_runtime import TaskNotFinalizable, TaskRuntime, TerminalObservation


class FakeEmbeddingProvider:
    def __init__(self, revision: str = "test-revision") -> None:
        self.revision = revision
        self.calls = 0
        self.fail = False

    def current_space(self) -> EmbeddingSpace:
        return EmbeddingSpace(
            provider="checkpoint4-test",
            model="deterministic-four-dimensional",
            revision=self.revision,
            dimensions=4,
            configuration="checkpoint4-test-v1",
        )

    def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        self.calls += 1
        if self.fail:
            raise RuntimeError("embedding service unavailable")
        vector = (1.0, 0.1, 0.1, 0.1)
        return EmbeddingBatch(
            space=self.current_space(),
            vectors=tuple(vector for _ in texts),
        )


@dataclass
class TeamExperienceEnv:
    session_factory: sessionmaker[Session]
    snapshot_store: SnapshotStore
    team_id: UUID = field(default_factory=uuid4)
    policy_id: UUID = field(default_factory=uuid4)
    policy_version: int = 1
    schema_version: int = 2
    review_interval_days: int | None = 30
    task_ids: list[UUID] = field(default_factory=list)
    learning_change_ids: list[UUID] = field(default_factory=list)
    item_ids: list[UUID] = field(default_factory=list)
    objective_ids: list[UUID] = field(default_factory=list)

    def create(self) -> None:
        rules: dict[str, Any] = {"sources": []}
        if self.review_interval_days is not None:
            rules["review"] = {
                "knowledge_item_interval_days": self.review_interval_days
            }
        with self.session_factory.begin() as session:
            session.add(
                Team(id=self.team_id, domain="science", status="active")
            )
            session.flush()
            session.add(
                TeamPolicy(
                    id=self.policy_id,
                    team_id=self.team_id,
                    version=self.policy_version,
                    schema_version=self.schema_version,
                    rules=rules,
                )
            )

    def add_accepted_item(
        self,
        *,
        title: str = "Alpha practice for repeatable source review",
        statement: str = "Use the alpha checklist before accepting a source.",
        body: str = "Alpha source reviews should preserve contrary evidence.",
        committed_at: datetime | None = None,
        review_interval_days: int | None | object = ...,
        status: str = "active",
    ) -> UUID:
        committed_time = committed_at or datetime.now(timezone.utc)
        interval = (
            self.review_interval_days
            if review_interval_days is ...
            else review_interval_days
        )
        review_after = (
            committed_time + timedelta(days=interval)
            if interval is not None
            else None
        )
        item_id, learning_change_id, proposer_task_id, approval_task_id = (
            uuid4() for _ in range(4)
        )
        proposal_hash = "sha256:" + "a" * 64
        evidence_basis_hash = "sha256:" + "b" * 64
        operator_id = "test-host|operator-1"
        confidence = Decimal("0.800")
        applicability = {"domain": "science", "situation": "source review"}
        preconditions = ["The source is within the Team's configured scope."]
        assumptions = ["The source text is available."]
        limitations = ["The checklist does not establish causation."]
        non_applicability = ["Do not use for unrelated domains."]
        failure_modes = ["A missing counterexample may be overlooked."]
        known_counterexamples = ["A source may be incomplete."]
        missing_information = ["Independent replication may be unavailable."]
        uncertainty = ["Evidence may remain inconclusive."]

        committed_state = {
            "id": str(item_id),
            "team_id": str(self.team_id),
            "kind": "practice",
            "title": title,
            "statement": statement,
            "body": body,
            "applicability": applicability,
            "preconditions": preconditions,
            "assumptions": assumptions,
            "limitations": limitations,
            "non_applicability": non_applicability,
            "failure_modes": failure_modes,
            "known_counterexamples": known_counterexamples,
            "missing_information": missing_information,
            "uncertainty": uncertainty,
            "confidence": str(confidence),
            "status": "active",
            "version": 1,
            "last_validated_at": None,
            "review_after": review_after.isoformat() if review_after else None,
            "origin_learning_change_id": str(learning_change_id),
        }
        snapshot_ref, snapshot_hash = self.snapshot_store.put(
            b'{"result_category":"success_learning_change_accepted"}'
        )

        with self.session_factory.begin() as session:
            session.add_all(
                [
                    Task(
                        id=proposer_task_id,
                        team_id=self.team_id,
                        task_type="propose_learning_change",
                        status="done",
                        attempt_count=1,
                        policy_version=self.policy_version,
                        allowed_writes=["LearningChange"],
                        budget={
                            "max_tool_calls": 0,
                            "max_cost_usd": 0.4,
                            "deadline_seconds": 180,
                        },
                        completed_at=committed_time,
                    ),
                    Task(
                        id=approval_task_id,
                        team_id=self.team_id,
                        task_type="approve_learning_change",
                        status="done",
                        attempt_count=1,
                        policy_version=self.policy_version,
                        allowed_writes=["LearningChange", "KnowledgeItem"],
                        budget={"max_tool_calls": 0, "max_cost_usd": 0.0},
                        completed_at=committed_time,
                    ),
                ]
            )
            session.flush()
            session.add(
                LearningChange(
                    id=learning_change_id,
                    team_id=self.team_id,
                    target_kind="knowledge_item",
                    target_id=None,
                    operation="create",
                    proposed_state={
                        "kind": "practice",
                        "proposal_hash": proposal_hash,
                        "evidence_basis_hash": evidence_basis_hash,
                    },
                    previous_state=None,
                    committed_state=committed_state,
                    evidence_basis=[],
                    evidence_basis_hash=evidence_basis_hash,
                    status="accepted",
                    idempotency_key=f"test-{learning_change_id}",
                    proposed_by_task_id=proposer_task_id,
                    committed_by_task_id=approval_task_id,
                    operator_id=operator_id,
                    decision_reason=None,
                    committed_at=committed_time,
                )
            )
            session.flush()
            session.add_all(
                [
                    KnowledgeItem(
                        id=item_id,
                        team_id=self.team_id,
                        kind="practice",
                        title=title,
                        statement=statement,
                        body=body,
                        applicability=applicability,
                        preconditions=preconditions,
                        assumptions=assumptions,
                        limitations=limitations,
                        non_applicability=non_applicability,
                        failure_modes=failure_modes,
                        known_counterexamples=known_counterexamples,
                        missing_information=missing_information,
                        uncertainty=uncertainty,
                        confidence=confidence,
                        status=status,
                        version=1,
                        last_validated_at=None,
                        review_after=review_after,
                        origin_learning_change_id=learning_change_id,
                    ),
                    Outcome(
                        id=uuid4(),
                        team_id=self.team_id,
                        subject_kind="task",
                        subject_id=approval_task_id,
                        outcome_type="task_execution",
                        expected=None,
                        observation_snapshot_ref=snapshot_ref,
                        observation_hash=snapshot_hash,
                        observed_at=committed_time,
                        recorded_by_task_id=approval_task_id,
                    ),
                ]
            )
            session.flush()
            outcome_id = session.scalar(
                select(Outcome.id).where(
                    Outcome.recorded_by_task_id == approval_task_id,
                    Outcome.outcome_type == "task_execution",
                )
            )
            assert outcome_id is not None
            session.add_all(
                [
                    Event(
                        id=uuid4(),
                        task_id=approval_task_id,
                        type="learning_change_accepted",
                        payload={
                            "schema_version": 1,
                            "learning_change_id": str(learning_change_id),
                            "operation": "create",
                            "decision": "accept",
                            "operator_id": operator_id,
                            "approval_task_id": str(approval_task_id),
                            "attempt_count": 1,
                            "evidence_basis_hash": evidence_basis_hash,
                            "proposal_hash": proposal_hash,
                            "committed_at": committed_time.isoformat(),
                            "knowledge_item_id": str(item_id),
                            "knowledge_item_version": 1,
                        },
                        created_at=committed_time,
                    ),
                    Event(
                        id=uuid4(),
                        task_id=approval_task_id,
                        type="task_completed",
                        payload={
                            "from_status": "running",
                            "to_status": "done",
                            "attempt_count": 1,
                            "result_category": "success_learning_change_accepted",
                            "failure_reason": None,
                            "outcome_id": str(outcome_id),
                            "observation_snapshot_ref": snapshot_ref,
                            "observation_hash": snapshot_hash,
                            "learning_change_id": str(learning_change_id),
                        },
                        created_at=committed_time,
                    ),
                ]
            )

        self.task_ids.extend([proposer_task_id, approval_task_id])
        self.learning_change_ids.append(learning_change_id)
        self.item_ids.append(item_id)
        return item_id

    def add_strategy_task(self, statement: str = "Apply the alpha practice.") -> UUID:
        objective_id, task_id = uuid4(), uuid4()
        with self.session_factory.begin() as session:
            session.add(
                Objective(
                    id=objective_id,
                    team_id=self.team_id,
                    statement=statement,
                    status="active",
                )
            )
            session.flush()
            session.add(
                Task(
                    id=task_id,
                    team_id=self.team_id,
                    task_type="propose_strategy",
                    status="running",
                    attempt_count=1,
                    policy_version=self.policy_version,
                    objective_id=objective_id,
                    allowed_writes=[],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.05,
                        "deadline_seconds": 60,
                    },
                )
            )
        self.objective_ids.append(objective_id)
        self.task_ids.append(task_id)
        return task_id

    def add_review_task(self) -> UUID:
        task_id = uuid4()
        with self.session_factory.begin() as session:
            session.add(
                Task(
                    id=task_id,
                    team_id=self.team_id,
                    task_type="review_knowledge",
                    status="pending",
                    attempt_count=0,
                    policy_version=self.policy_version,
                    allowed_writes=["KnowledgeItem"],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.0,
                        "deadline_seconds": 60,
                    },
                )
            )
        self.task_ids.append(task_id)
        return task_id

    def cleanup(self) -> None:
        with self.session_factory.begin() as session:
            if self.task_ids:
                session.execute(delete(Event).where(Event.task_id.in_(self.task_ids)))
                session.execute(
                    delete(Outcome).where(
                        Outcome.recorded_by_task_id.in_(self.task_ids)
                    )
                )
            if self.item_ids:
                session.execute(
                    delete(TeamExperienceChunk).where(
                        TeamExperienceChunk.knowledge_item_id.in_(self.item_ids)
                    )
                )
                session.execute(
                    delete(KnowledgeItem).where(KnowledgeItem.id.in_(self.item_ids))
                )
            if self.learning_change_ids:
                session.execute(
                    delete(LearningChange).where(
                        LearningChange.id.in_(self.learning_change_ids)
                    )
                )
            if self.task_ids:
                session.execute(delete(Task).where(Task.id.in_(self.task_ids)))
            if self.objective_ids:
                session.execute(
                    delete(Objective).where(Objective.id.in_(self.objective_ids))
                )
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == self.policy_id))
            session.execute(delete(Team).where(Team.id == self.team_id))


@pytest.fixture
def experience_env(
    session_factory: sessionmaker[Session], snapshot_store: SnapshotStore
) -> TeamExperienceEnv:
    env = TeamExperienceEnv(session_factory, snapshot_store)
    env.create()
    try:
        yield env
    finally:
        env.cleanup()


def test_review_interval_is_strictly_versioned_and_has_no_default() -> None:
    assert knowledge_item_review_interval_days({}, 1) is None
    assert knowledge_item_review_interval_days({}, 2) is None
    assert knowledge_item_review_interval_days(
        {"review": {"knowledge_item_interval_days": 30}}, 2
    ) == 30
    with pytest.raises(InvalidPolicyError, match="requires_team_policy_schema_v2"):
        knowledge_item_review_interval_days(
            {"review": {"knowledge_item_interval_days": 30}}, 1
        )
    for invalid in (True, False, 0, -1, 1.5, "30"):
        with pytest.raises(
            InvalidPolicyError, match="invalid_knowledge_item_review_interval"
        ):
            knowledge_item_review_interval_days(
                {"review": {"knowledge_item_interval_days": invalid}}, 2
            )
    with pytest.raises(
        InvalidPolicyError, match="unsupported_team_policy_schema_version"
    ):
        knowledge_item_review_interval_days({}, 3)


def test_separate_team_experience_projection_is_idempotent_and_retrievable(
    experience_env: TeamExperienceEnv,
) -> None:
    item_id = experience_env.add_accepted_item()
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)

    first = indexer.index_knowledge_item(item_id)
    calls_after_first = provider.calls
    second = indexer.index_knowledge_item(item_id)

    assert first.outcome == "indexed"
    assert first.chunk_count > 0
    assert first.embedding_space_key == provider.current_space().key
    assert first.item_content_hash is not None
    assert second.outcome == "unchanged"
    assert provider.calls == calls_after_first

    with experience_env.session_factory() as session:
        rows = list(
            session.scalars(
                select(TeamExperienceChunk).where(
                    TeamExperienceChunk.knowledge_item_id == item_id
                )
            )
        )
    assert rows
    assert all(row.team_id == experience_env.team_id for row in rows)
    with experience_env.session_factory() as session:
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item_id
            )
        )
        assert state is not None
        assert state.status == "published"
        assert state.item_version == 1
        assert state.chunk_count == len(rows)
        assert state.attempt_count == 1

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    passages = retriever.retrieve(experience_env.team_id, "alpha practice")

    assert passages
    assert all(p.logical_core == "team_experience" for p in passages)
    assert all(p.knowledge_item_id == item_id for p in passages)
    assert all(p.knowledge_item_version == 1 for p in passages)
    assert all(
        p.origin_learning_change_id == experience_env.learning_change_ids[0]
        for p in passages
    )
    assert sum(len(p.text) for p in passages) <= 8000
    assert len(passages) <= 8


def test_failed_publication_records_staleness_and_rebuilds(
    experience_env: TeamExperienceEnv,
) -> None:
    item_id = experience_env.add_accepted_item()
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)
    first = indexer.index_knowledge_item(item_id)
    assert first.outcome == "indexed"

    with experience_env.session_factory() as session:
        prior_chunks = list(
            session.scalars(
                select(TeamExperienceChunk).where(
                    TeamExperienceChunk.knowledge_item_id == item_id
                )
            )
        )
    assert prior_chunks

    # Force a new embedding space so the indexer must refresh the old
    # publication. A provider failure must make old chunks undiscoverable.
    provider.revision = "test-revision-2"
    provider.fail = True
    with pytest.raises(RuntimeError, match="embedding service unavailable"):
        indexer.index_knowledge_item(item_id)

    with experience_env.session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item_id
            )
        )
        learning_change = session.get(
            LearningChange, experience_env.learning_change_ids[0]
        )
        chunks = list(
            session.scalars(
                select(TeamExperienceChunk).where(
                    TeamExperienceChunk.knowledge_item_id == item_id
                )
            )
        )
        assert item is not None and item.status == "active"
        assert learning_change is not None and learning_change.status == "accepted"
        assert state is not None
        assert state.status == "stale"
        assert state.last_error_kind == "RuntimeError"
        assert state.attempt_count == 2
        assert chunks
        assert all(row.embedding_space_key != provider.current_space().key for row in chunks)

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    assert retriever.retrieve(experience_env.team_id, "alpha practice") == ()

    provider.fail = False
    rebuilt = indexer.rebuild_all()
    assert len(rebuilt) == 1
    assert rebuilt[0].outcome == "indexed"

    with experience_env.session_factory() as session:
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item_id
            )
        )
        assert state is not None
        assert state.status == "published"
        assert state.last_error_kind is None
        assert state.attempt_count == 3
        assert state.embedding_space_key == provider.current_space().key

    passages = retriever.retrieve(experience_env.team_id, "alpha practice")
    assert passages
    assert all(p.logical_core == "team_experience" for p in passages)


def test_unconfigured_review_date_is_not_indexed(
    experience_env: TeamExperienceEnv,
) -> None:
    with experience_env.session_factory.begin() as session:
        policy = session.get(TeamPolicy, experience_env.policy_id)
        assert policy is not None
        policy.rules = {"sources": []}
    experience_env.review_interval_days = None
    item_id = experience_env.add_accepted_item(review_interval_days=None)
    provider = FakeEmbeddingProvider()

    result = TeamExperienceIndexer(
        experience_env.session_factory, provider
    ).index_knowledge_item(item_id)

    assert result.outcome == "ineligible"
    assert provider.calls == 0
    with experience_env.session_factory() as session:
        assert session.scalar(
            select(TeamExperienceChunk.id).where(
                TeamExperienceChunk.knowledge_item_id == item_id
            )
        ) is None


def test_review_expired_knowledge_is_not_indexed(
    experience_env: TeamExperienceEnv,
) -> None:
    now = datetime.now(timezone.utc)
    item_id = experience_env.add_accepted_item(
        committed_at=now - timedelta(days=40),
        review_interval_days=30,
    )
    provider = FakeEmbeddingProvider()

    result = TeamExperienceIndexer(
        experience_env.session_factory, provider
    ).index_knowledge_item(item_id, now=now)

    assert result.outcome == "ineligible"
    assert provider.calls == 0
    with experience_env.session_factory() as session:
        assert session.scalar(
            select(TeamExperienceChunk.id).where(
                TeamExperienceChunk.knowledge_item_id == item_id
            )
        ) is None


def test_needs_review_item_is_not_retrievable_even_if_projection_remains(
    experience_env: TeamExperienceEnv,
) -> None:
    item_id = experience_env.add_accepted_item()
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)
    indexer.index_knowledge_item(item_id)

    with experience_env.session_factory.begin() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        item.status = "needs_review"

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    assert retriever.retrieve(experience_env.team_id, "alpha practice") == ()


def test_tampered_projection_is_discarded_by_canonical_retrieval(
    experience_env: TeamExperienceEnv,
) -> None:
    item_id = experience_env.add_accepted_item()
    provider = FakeEmbeddingProvider()
    TeamExperienceIndexer(
        experience_env.session_factory, provider
    ).index_knowledge_item(item_id)
    with experience_env.session_factory.begin() as session:
        chunk = session.scalar(
            select(TeamExperienceChunk).where(
                TeamExperienceChunk.knowledge_item_id == item_id
            )
        )
        assert chunk is not None
        chunk.chunk_text = "tampered alpha content"

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    assert retriever.retrieve(experience_env.team_id, "alpha") == ()


def test_changed_canonical_item_invalidates_existing_projection(
    experience_env: TeamExperienceEnv,
) -> None:
    item_id = experience_env.add_accepted_item()
    provider = FakeEmbeddingProvider()
    TeamExperienceIndexer(
        experience_env.session_factory, provider
    ).index_knowledge_item(item_id)
    with experience_env.session_factory.begin() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        item.body = "A changed statement absent from the committed LearningChange."

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    assert retriever.retrieve(experience_env.team_id, "alpha") == ()


def test_later_task_receives_team_experience_in_immutable_context(
    experience_env: TeamExperienceEnv,
) -> None:
    item_id = experience_env.add_accepted_item()
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)
    indexer.index_knowledge_item(item_id)
    task_id = experience_env.add_strategy_task(
        "Use the alpha practice to check source quality."
    )
    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )

    assembled = TaskContextAssembler(
        experience_env.session_factory,
        experience_env.snapshot_store,
        retriever,
    ).assemble(task_id)

    knowledge = assembled.document["knowledge"]
    assert knowledge["domain_knowledge"] == []
    assert knowledge["team_experience"]
    assert knowledge["team_experience"][0]["knowledge_item_id"] == str(item_id)
    assert knowledge["team_experience"][0]["knowledge_item_version"] == 1
    selected = assembled.manifest["selected"]
    assert selected
    assert selected[0]["logical_core"] == "team_experience"
    assert selected[0]["origin_learning_change_id"] == str(
        experience_env.learning_change_ids[0]
    )
    stored = experience_env.snapshot_store.read(assembled.snapshot_ref)
    assert b'"team_experience"' in stored
    assert assembled.event_id is not None

    replay = TaskContextAssembler(
        experience_env.session_factory,
        experience_env.snapshot_store,
        retriever,
    ).assemble(task_id)
    assert replay.replayed is True
    assert replay.snapshot_ref == assembled.snapshot_ref
    assert replay.event_id == assembled.event_id


def test_review_knowledge_task_atomically_marks_due_items_and_replays_once(
    experience_env: TeamExperienceEnv,
) -> None:
    now = datetime.now(timezone.utc)
    due_item = experience_env.add_accepted_item(
        title="Due alpha practice",
        committed_at=now - timedelta(days=40),
        review_interval_days=30,
    )
    future_item = experience_env.add_accepted_item(
        title="Future beta practice",
        statement="A future beta rule is not due yet.",
        body="This knowledge item is not due.",
        committed_at=now - timedelta(hours=3),
        review_interval_days=30,
    )
    task_id = experience_env.add_review_task()
    runtime = TaskRuntime(experience_env.session_factory, experience_env.snapshot_store)
    result = runtime.complete_knowledge_review(task_id)
    replay = runtime.complete_knowledge_review(task_id)

    assert result.status == "done"
    assert replay.replayed is True
    with experience_env.session_factory() as session:
        due = session.get(KnowledgeItem, due_item)
        future = session.get(KnowledgeItem, future_item)
        assert due is not None and due.status == "needs_review"
        assert future is not None and future.status == "active"
        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task_id,
                    Event.type == "knowledge_items_reviewed",
                )
            )
        )
        assert len(events) == 1
        assert [entry["knowledge_item_id"] for entry in events[0].payload["items"]] == [
            str(due_item)
        ]
        outcome_count = session.scalar(
            select(Outcome.id).where(
                Outcome.recorded_by_task_id == task_id,
                Outcome.outcome_type == "task_execution",
            )
        )
        assert outcome_count is not None


def test_review_knowledge_task_rejects_a_different_success_result(
    experience_env: TeamExperienceEnv,
) -> None:
    task_id = experience_env.add_review_task()
    runtime = TaskRuntime(experience_env.session_factory, experience_env.snapshot_store)
    admission = runtime.admit(task_id)
    with pytest.raises(
        TaskNotFinalizable, match="review_task_requires_knowledge_review_result"
    ):
        runtime.finalize(
            TerminalObservation(
                task_id=task_id,
                attempt=admission.attempt_count,
                result_category="success_no_change",
                observed_at=datetime.now(timezone.utc),
            )
        )
    with experience_env.session_factory() as session:
        task = session.get(Task, task_id)
        assert task is not None and task.status == "running"
        assert session.scalar(
            select(Event.id).where(
                Event.task_id == task_id,
                Event.type == "knowledge_items_reviewed",
            )
        ) is None
