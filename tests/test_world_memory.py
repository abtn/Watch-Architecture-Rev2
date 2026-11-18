"""RW-2 deterministic Operator world-memory commit proofs."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from core.models import (
    ConfidenceChange,
    Event,
    EvidenceLink,
    Hypothesis,
    Outcome,
    Signal,
    Task,
    Team,
    TeamPolicy,
    Thread,
)
from core.operator_application import (
    OperatorApplicationAdapter,
    OperatorGrant,
    TrustedOperatorPrincipal,
)
from core.operator_approval import canonical_operator_identity
from core.snapshot_store import SnapshotStore
from core.task_runtime import TaskRuntime, TerminalObservation
from core.world_memory import (
    ConfidenceChangeProposal,
    EvidenceLinkProposal,
    HypothesisCreateProposal,
    HypothesisTransitionProposal,
    OperatorUpdateRequest,
    WorldMemoryCommitService,
    build_request_event_payload,
    task_id_for_request,
)

_CONTENT = b"Market report: supply increased by 5 percent."
_QUOTE = "supply increased by 5 percent"


@dataclass(frozen=True)
class WorldMemoryContext:
    team_id: UUID
    policy_id: UUID
    source_task_id: UUID
    signal_id: UUID
    thread_id: UUID
    snapshot_ref: str
    snapshot_hash: str
    content: bytes


@pytest.fixture
def world_memory_context(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
) -> Iterator[WorldMemoryContext]:
    team_id, policy_id, source_task_id, signal_id, thread_id = (
        uuid4() for _ in range(5)
    )
    snapshot_ref, snapshot_hash = snapshot_store.put(_CONTENT)
    now = datetime.now(timezone.utc)
    context = WorldMemoryContext(
        team_id=team_id,
        policy_id=policy_id,
        source_task_id=source_task_id,
        signal_id=signal_id,
        thread_id=thread_id,
        snapshot_ref=snapshot_ref,
        snapshot_hash=snapshot_hash,
        content=_CONTENT,
    )
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="world_memory_test", status="active"))
        session.flush()
        session.add(
            TeamPolicy(id=policy_id, team_id=team_id, version=1, rules={})
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
        session.flush()
        session.add(
            Signal(
                id=signal_id,
                domain="world_memory_test",
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
                domain="world_memory_test",
                title="Supply conditions",
                status="active",
            )
        )
        session.flush()

    try:
        yield context
    finally:
        with session_factory.begin() as session:
            session.execute(
                delete(ConfidenceChange).where(
                    ConfidenceChange.team_id == team_id
                )
            )
            session.execute(
                delete(EvidenceLink).where(EvidenceLink.team_id == team_id)
            )
            session.execute(
                delete(Hypothesis).where(Hypothesis.team_id == team_id)
            )
            session.execute(delete(Thread).where(Thread.team_id == team_id))
            session.execute(delete(Outcome).where(Outcome.team_id == team_id))
            session.execute(delete(Signal).where(Signal.id == signal_id))
            task_ids = select(Task.id).where(Task.team_id == team_id)
            session.execute(delete(Event).where(Event.task_id.in_(task_ids)))
            session.execute(delete(Task).where(Task.team_id == team_id))
            session.execute(
                delete(TeamPolicy).where(TeamPolicy.team_id == team_id)
            )
            session.execute(delete(Team).where(Team.id == team_id))


def _principal(team_id: UUID) -> TrustedOperatorPrincipal:
    return TrustedOperatorPrincipal(
        issuer="https://host.example/identity",
        subject="operator-rw2",
        grants=frozenset({OperatorGrant(team_id, "operator_update")}),
    )


def _quote_proposal(
    context: WorldMemoryContext,
    hypothesis_id: UUID,
    *,
    key: str = "evidence-1",
    stance: str = "supports",
    quote: str = _QUOTE,
) -> EvidenceLinkProposal:
    start = context.content.decode("utf-8").index(_QUOTE)
    return EvidenceLinkProposal(
        kind="evidence_link_add",
        key=key,
        hypothesis_id=hypothesis_id,
        source_kind="signal",
        signal_id=context.signal_id,
        stance=stance,
        quote_text=quote,
        quote_start=start,
        quote_end=start + len(quote),
    )


def _seed_hypothesis_and_evidence(
    session_factory: sessionmaker[Session],
    context: WorldMemoryContext,
    *,
    stance: str = "supports",
) -> tuple[UUID, UUID]:
    hypothesis_id, evidence_id = uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        session.add(
            Hypothesis(
                id=hypothesis_id,
                team_id=context.team_id,
                thread_id=context.thread_id,
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
                team_id=context.team_id,
                subject_kind="hypothesis",
                evaluation_id=None,
                hypothesis_id=hypothesis_id,
                originating_task_id=context.source_task_id,
                source_kind="signal",
                signal_id=context.signal_id,
                outcome_id=None,
                snapshot_ref=context.snapshot_ref,
                snapshot_hash=context.snapshot_hash,
                stance=stance,
                quote_text=_QUOTE,
                quote_start=context.content.decode("utf-8").index(_QUOTE),
                quote_end=(
                    context.content.decode("utf-8").index(_QUOTE) + len(_QUOTE)
                ),
                reference_key="sha256:" + "a" * 64,
                created_at=now,
            )
        )
    return hypothesis_id, evidence_id


def test_operator_update_creates_low_hypothesis_and_verified_evidence(
    session_factory, snapshot_store, world_memory_context
):
    context = world_memory_context
    hypothesis_id = uuid4()
    request = OperatorUpdateRequest(
        thread_id=context.thread_id,
        idempotency_key=uuid4(),
        proposals=[
            HypothesisCreateProposal(
                kind="hypothesis_create",
                key="create-hypothesis",
                hypothesis_id=hypothesis_id,
                statement="Supply is increasing.",
            ),
            _quote_proposal(context, hypothesis_id),
        ],
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)

    result = adapter.operator_update(_principal(context.team_id), request)

    assert result.task_status == "done"
    assert result.committed_count == 2
    assert result.rejected_count == 0
    assert result.attempt_count == 1
    with session_factory() as session:
        hypothesis = session.get(Hypothesis, hypothesis_id)
        assert hypothesis is not None
        assert hypothesis.confidence == "low"
        assert hypothesis.status == "active"
        link = session.scalar(
            select(EvidenceLink).where(
                EvidenceLink.originating_task_id == result.task_id
            )
        )
        assert link is not None
        assert link.hypothesis_id == hypothesis_id
        assert link.stance == "supports"
        assert link.quote_text == _QUOTE
        assert link.snapshot_hash == context.snapshot_hash
        assert hypothesis.last_touched_at == link.created_at
        assert session.scalar(
            select(Event.id).where(
                Event.task_id == result.task_id,
                Event.type == "operator_update_committed",
            )
        ) is not None
        assert session.scalar(
            select(Outcome.id).where(
                Outcome.recorded_by_task_id == result.task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) is not None

    replay = adapter.operator_update(_principal(context.team_id), request)
    assert replay.replayed
    assert replay.task_id == result.task_id
    assert replay.outcome_id == result.outcome_id
    with session_factory() as session:
        assert session.scalar(
            select(ConfidenceChange.id).where(
                ConfidenceChange.created_by_task_id == result.task_id
            )
        ) is None
        assert len(
            list(
                session.scalars(
                    select(EvidenceLink).where(
                        EvidenceLink.originating_task_id == result.task_id
                    )
                )
            )
        ) == 1


def test_invalid_quote_is_rejected_without_discarding_valid_proposal(
    session_factory, snapshot_store, world_memory_context
):
    context = world_memory_context
    hypothesis_id = uuid4()
    request = OperatorUpdateRequest(
        thread_id=context.thread_id,
        idempotency_key=uuid4(),
        proposals=[
            HypothesisCreateProposal(
                kind="hypothesis_create",
                key="create-hypothesis",
                hypothesis_id=hypothesis_id,
                statement="Supply is increasing.",
            ),
            _quote_proposal(
                context, hypothesis_id, key="bad-evidence", quote="fabricated quote"
            ),
        ],
    )

    result = OperatorApplicationAdapter(
        session_factory, snapshot_store
    ).operator_update(_principal(context.team_id), request)

    assert result.task_status == "done"
    assert result.committed_count == 1
    assert result.rejected_count == 1
    with session_factory() as session:
        hypothesis = session.get(Hypothesis, hypothesis_id)
        assert hypothesis is not None and hypothesis.confidence == "low"
        assert session.scalar(
            select(EvidenceLink.id).where(
                EvidenceLink.originating_task_id == result.task_id
            )
        ) is None
        rejection = session.scalar(
            select(Event).where(
                Event.task_id == result.task_id,
                Event.type == "proposal_rejected",
            )
        )
        assert rejection is not None
        assert rejection.payload["reason"] == "quote_text_offset_mismatch"


def test_all_invalid_proposals_fail_task_and_write_no_business_state(
    session_factory, snapshot_store, world_memory_context
):
    context = world_memory_context
    hypothesis_id = uuid4()
    request = OperatorUpdateRequest(
        thread_id=context.thread_id,
        idempotency_key=uuid4(),
        proposals=[
            HypothesisCreateProposal(
                kind="hypothesis_create",
                key="elevated-initial-confidence",
                hypothesis_id=hypothesis_id,
                statement="Unsupported high-confidence claim.",
                confidence="high",
            )
        ],
    )

    result = OperatorApplicationAdapter(
        session_factory, snapshot_store
    ).operator_update(_principal(context.team_id), request)

    assert result.task_status == "failed"
    assert result.committed_count == 0
    assert result.rejected_count == 1
    with session_factory() as session:
        assert session.get(Hypothesis, hypothesis_id) is None
        assert session.scalar(
            select(Event.id).where(
                Event.task_id == result.task_id,
                Event.type == "operator_update_rejected",
            )
        ) is not None
        assert session.scalar(
            select(Outcome.id).where(
                Outcome.recorded_by_task_id == result.task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) is not None


def test_mentions_evidence_cannot_anchor_confidence_change(
    session_factory, snapshot_store, world_memory_context
):
    context = world_memory_context
    hypothesis_id, evidence_id = _seed_hypothesis_and_evidence(
        session_factory, context, stance="mentions"
    )
    request = OperatorUpdateRequest(
        thread_id=context.thread_id,
        idempotency_key=uuid4(),
        proposals=[
            ConfidenceChangeProposal(
                kind="confidence_change",
                key="mentions-cause",
                hypothesis_id=hypothesis_id,
                evidence_link_id=evidence_id,
                to_confidence="moderate",
            )
        ],
    )

    result = OperatorApplicationAdapter(
        session_factory, snapshot_store
    ).operator_update(_principal(context.team_id), request)

    assert result.task_status == "failed"
    with session_factory() as session:
        hypothesis = session.get(Hypothesis, hypothesis_id)
        assert hypothesis is not None and hypothesis.confidence == "low"
        assert session.scalar(
            select(ConfidenceChange.id).where(
                ConfidenceChange.created_by_task_id == result.task_id
            )
        ) is None
        rejection = session.scalar(
            select(Event).where(
                Event.task_id == result.task_id,
                Event.type == "proposal_rejected",
            )
        )
        assert rejection is not None
        assert rejection.payload["reason"] == (
            "mentions_evidence_cannot_change_confidence"
        )


def test_later_confidence_change_uses_one_valid_evidence_cause(
    session_factory, snapshot_store, world_memory_context
):
    context = world_memory_context
    hypothesis_id, evidence_id = _seed_hypothesis_and_evidence(
        session_factory, context, stance="supports"
    )
    request = OperatorUpdateRequest(
        thread_id=context.thread_id,
        idempotency_key=uuid4(),
        proposals=[
            ConfidenceChangeProposal(
                kind="confidence_change",
                key="supported-confidence-change",
                hypothesis_id=hypothesis_id,
                evidence_link_id=evidence_id,
                to_confidence="moderate",
            )
        ],
    )

    result = OperatorApplicationAdapter(
        session_factory, snapshot_store
    ).operator_update(_principal(context.team_id), request)

    assert result.task_status == "done"
    with session_factory() as session:
        hypothesis = session.get(Hypothesis, hypothesis_id)
        change = session.scalar(
            select(ConfidenceChange).where(
                ConfidenceChange.created_by_task_id == result.task_id
            )
        )
        assert hypothesis is not None and hypothesis.confidence == "moderate"
        assert change is not None
        assert change.from_confidence == "low"
        assert change.to_confidence == "moderate"
        assert change.cause_kind == "evidence"
        assert change.evidence_link_id == evidence_id


def test_hypothesis_supersession_requires_successor_and_reason(
    session_factory, snapshot_store, world_memory_context
):
    context = world_memory_context
    target_id, successor_id = uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        session.add_all(
            [
                Hypothesis(
                    id=target_id,
                    team_id=context.team_id,
                    thread_id=context.thread_id,
                    statement="Earlier explanation.",
                    status="active",
                    confidence="low",
                    created_at=now,
                    last_touched_at=now,
                ),
                Hypothesis(
                    id=successor_id,
                    team_id=context.team_id,
                    thread_id=context.thread_id,
                    statement="Surviving explanation.",
                    status="active",
                    confidence="low",
                    created_at=now,
                    last_touched_at=now,
                ),
            ]
        )
    request = OperatorUpdateRequest(
        thread_id=context.thread_id,
        idempotency_key=uuid4(),
        proposals=[
            HypothesisTransitionProposal(
                kind="hypothesis_transition",
                key="supersede-earlier",
                hypothesis_id=target_id,
                action="supersede",
                successor_hypothesis_id=successor_id,
                reason="The successor explains the same observations more completely.",
            )
        ],
    )

    result = OperatorApplicationAdapter(
        session_factory, snapshot_store
    ).operator_update(_principal(context.team_id), request)

    assert result.task_status == "done"
    with session_factory() as session:
        target = session.get(Hypothesis, target_id)
        successor = session.get(Hypothesis, successor_id)
        event = session.scalar(
            select(Event).where(
                Event.task_id == result.task_id,
                Event.type == "hypothesis_superseded",
            )
        )
        assert target is not None and target.status == "superseded"
        assert successor is not None and successor.status == "active"
        assert event is not None
        assert event.payload["successor_hypothesis_id"] == str(successor_id)


def test_concurrent_operator_updates_serialize_competing_transitions(
    session_factory, snapshot_store, world_memory_context
):
    context = world_memory_context
    hypothesis_id, _ = _seed_hypothesis_and_evidence(session_factory, context)
    operator_id = canonical_operator_identity(
        "https://host.example/identity", "operator-rw2"
    )
    requests = [
        OperatorUpdateRequest(
            thread_id=context.thread_id,
            idempotency_key=uuid4(),
            proposals=[
                HypothesisTransitionProposal(
                    kind="hypothesis_transition",
                    key=f"reject-{index}",
                    hypothesis_id=hypothesis_id,
                    action="reject",
                    reason=f"Operator review {index}.",
                )
            ],
        )
        for index in range(2)
    ]
    task_ids: list[UUID] = []
    for request in requests:
        task_id = task_id_for_request(context.team_id, request.idempotency_key)
        payload = build_request_event_payload(
            task_id=task_id,
            team_id=context.team_id,
            policy_version=1,
            operator_id=operator_id,
            request=request,
        )
        with session_factory.begin() as session:
            session.add(
                Task(
                    id=task_id,
                    team_id=context.team_id,
                    task_type="operator_update",
                    status="pending",
                    attempt_count=0,
                    policy_version=1,
                    objective_id=None,
                    plan_id=None,
                    plan_action_id=None,
                    allowed_writes=[
                        "EvidenceLink",
                        "Hypothesis",
                        "ConfidenceChange",
                    ],
                    budget={"max_tool_calls": 0, "max_cost_usd": 0.0},
                    max_attempts=3,
                )
            )
            session.flush()
            session.add(
                Event(
                    id=uuid4(),
                    task_id=task_id,
                    type="operator_update_requested",
                    payload=payload,
                    created_at=datetime.now(timezone.utc),
                )
            )
        TaskRuntime(session_factory, snapshot_store).admit(task_id)
        task_ids.append(task_id)

    barrier = Barrier(2)

    def commit_one(index: int):
        barrier.wait(timeout=10)
        return WorldMemoryCommitService(
            session_factory, snapshot_store
        ).commit(task_ids[index], 1, operator_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(commit_one, range(2)))

    assert sorted(result.status for result in results) == ["committed", "rejected"]
    runtime = TaskRuntime(session_factory, snapshot_store)
    for task_id, result in zip(task_ids, results, strict=True):
        runtime.finalize(
            TerminalObservation(
                task_id=task_id,
                attempt=1,
                result_category=(
                    "success_operator_update_committed"
                    if result.status == "committed"
                    else "terminal_failure"
                ),
                observed_at=result.committed_at,
                failure_reason=(
                    None
                    if result.status == "committed"
                    else "all_operator_update_proposals_rejected"
                ),
            )
        )
    with session_factory() as session:
        target = session.get(Hypothesis, hypothesis_id)
        assert target is not None and target.status == "rejected"
        transitions = list(
            session.scalars(
                select(Event).where(
                    Event.task_id.in_(task_ids),
                    Event.type == "hypothesis_rejected",
                )
            )
        )
        rejections = list(
            session.scalars(
                select(Event).where(
                    Event.task_id.in_(task_ids),
                    Event.type == "proposal_rejected",
                )
            )
        )
        assert len(transitions) == 1
        assert len(rejections) == 1
