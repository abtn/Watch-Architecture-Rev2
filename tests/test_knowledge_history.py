from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from core.knowledge_history import (
    KnowledgeHistoryError,
    build_knowledge_item_snapshot,
    decode_knowledge_item_snapshot,
    knowledge_item_snapshot_state,
    reconstruct_knowledge_item_history,
)
from core.models import Event, KnowledgeItem, LearningChange, Outcome, Task, Team, TeamPolicy


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _state(
    *,
    item_id: UUID,
    team_id: UUID,
    root_id: UUID,
    current_id: UUID,
    review_after: datetime,
    title: str = "History root practice",
    status: str = "active",
    version: int = 1,
    statement: str = "Preserve evidence and counterexamples.",
    last_validated_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "id": str(item_id),
        "team_id": str(team_id),
        "kind": "practice",
        "title": title,
        "statement": statement,
        "body": "Keep each conclusion tied to its observed conditions.",
        "applicability": {"domain": "research"},
        "preconditions": ["A source record is available."],
        "assumptions": ["The source is within the Team scope."],
        "limitations": ["This does not establish causation."],
        "non_applicability": ["Do not transfer to unrelated domains."],
        "failure_modes": ["Counterexamples may be missed."],
        "known_counterexamples": ["A source may be incomplete."],
        "missing_information": ["Independent replication may be unavailable."],
        "uncertainty": ["The available evidence may remain inconclusive."],
        "confidence": "0.800",
        "status": status,
        "version": version,
        "last_validated_at": last_validated_at,
        "review_after": review_after,
        "origin_learning_change_id": str(root_id),
        "current_learning_change_id": str(current_id),
        "supersedes_item_id": None,
        "superseded_by_id": None,
    }


def _legacy_state(state: dict[str, object]) -> dict[str, object]:
    legacy = dict(state)
    for field in ("last_validated_at", "review_after"):
        value = legacy[field]
        if isinstance(value, datetime):
            legacy[field] = value.isoformat()
    legacy.pop("current_learning_change_id")
    legacy.pop("supersedes_item_id")
    legacy.pop("superseded_by_id")
    return legacy


def _add_approval_task_and_events(
    session: Session,
    *,
    team_id: UUID,
    policy_version: int,
    learning_change_id: UUID,
    item_id: UUID,
    operation: str,
    state: dict[str, object],
    committed_at: datetime,
) -> None:
    proposal_task_id = uuid4()
    approval_task_id = uuid4()
    proposal_outcome_id = uuid4()
    approval_outcome_id = uuid4()
    proposal_digest = "d" * 64
    approval_digest = "c" * 64
    proposal_snapshot_ref = f"snap://sha256/{proposal_digest}"
    approval_snapshot_ref = f"snap://sha256/{approval_digest}"
    proposal_observation_hash = f"sha256:{proposal_digest}"
    approval_observation_hash = f"sha256:{approval_digest}"
    proposal_hash = "sha256:" + "a" * 64
    evidence_hash = "sha256:" + "b" * 64
    quality_assessment_id = uuid4()
    quality_assessment_hash = "sha256:" + "f" * 64
    idempotency_key_hash = "sha256:" + "9" * 64
    operator_id = "test-host|operator-1"
    fingerprint_payload = json.dumps(
        {
            "operation": "approve_learning_change",
            "team_id": str(team_id),
            "learning_change_id": str(learning_change_id),
            "decision": "accept",
            "rejection_reason": None,
            "operator_id": operator_id,
            "knowledge_quality_assessment_id": str(quality_assessment_id),
            "knowledge_quality_assessment_hash": quality_assessment_hash,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_fingerprint = "sha256:" + hashlib.sha256(
        fingerprint_payload.encode("utf-8")
    ).hexdigest()

    session.add_all(
        [
            Task(
                id=proposal_task_id,
                team_id=team_id,
                task_type="propose_learning_change",
                status="done",
                attempt_count=1,
                policy_version=policy_version,
                allowed_writes=["LearningChange"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.1,
                    "deadline_seconds": 60,
                },
                completed_at=committed_at,
            ),
            Task(
                id=approval_task_id,
                team_id=team_id,
                task_type="approve_learning_change",
                status="done",
                attempt_count=1,
                policy_version=policy_version,
                allowed_writes=["LearningChange", "KnowledgeItem"],
                budget={"max_tool_calls": 0, "max_cost_usd": 0.0},
                completed_at=committed_at,
            ),
        ]
    )
    session.flush()

    # The caller inserts the LearningChange with these Task IDs using the
    # returned metadata below; IDs are exposed on the helper for that purpose.
    session.add_all(
        [
            Event(
                id=uuid4(),
                task_id=proposal_task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=committed_at - timedelta(seconds=2),
            ),
            Outcome(
                id=proposal_outcome_id,
                team_id=team_id,
                subject_kind="task",
                subject_id=proposal_task_id,
                outcome_type="task_execution",
                expected=None,
                observation_snapshot_ref=proposal_snapshot_ref,
                observation_hash=proposal_observation_hash,
                observed_at=committed_at,
                recorded_by_task_id=proposal_task_id,
            ),
            Event(
                id=uuid4(),
                task_id=proposal_task_id,
                type="task_completed",
                payload={
                    "from_status": "running",
                    "to_status": "done",
                    "attempt_count": 1,
                    "result_category": "success_learning_change_proposed",
                    "failure_reason": None,
                    "outcome_id": str(proposal_outcome_id),
                    "observation_snapshot_ref": proposal_snapshot_ref,
                    "observation_hash": proposal_observation_hash,
                    "learning_change_id": str(learning_change_id),
                },
                created_at=committed_at,
            ),
            Event(
                id=uuid4(),
                task_id=approval_task_id,
                type="operator_task_requested",
                payload={
                    "schema_version": 2,
                    "operation": "approve_learning_change",
                    "learning_change_id": str(learning_change_id),
                    "decision": "accept",
                    "rejection_reason": None,
                    "operator_id": operator_id,
                    "idempotency_key_hash": idempotency_key_hash,
                    "request_fingerprint": request_fingerprint,
                    "policy_version": policy_version,
                    "knowledge_quality_assessment_id": str(quality_assessment_id),
                    "knowledge_quality_assessment_hash": quality_assessment_hash,
                },
                created_at=committed_at - timedelta(seconds=1),
            ),
            Event(
                id=uuid4(),
                task_id=approval_task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=committed_at - timedelta(seconds=1),
            ),
            Event(
                id=uuid4(),
                task_id=approval_task_id,
                type="learning_change_accepted",
                payload={
                    "schema_version": 1,
                    "learning_change_id": str(learning_change_id),
                    "operation": operation,
                    "decision": "accept",
                    "operator_id": operator_id,
                    "approval_task_id": str(approval_task_id),
                    "attempt_count": 1,
                    "evidence_basis_hash": evidence_hash,
                    "proposal_hash": proposal_hash,
                    "committed_at": committed_at.isoformat(),
                    "knowledge_item_id": str(item_id),
                    "knowledge_item_version": state["version"],
                    "knowledge_quality_assessment_id": str(quality_assessment_id),
                    "knowledge_quality_assessment_hash": quality_assessment_hash,
                },
                created_at=committed_at,
            ),
            Outcome(
                id=approval_outcome_id,
                team_id=team_id,
                subject_kind="task",
                subject_id=approval_task_id,
                outcome_type="task_execution",
                expected=None,
                observation_snapshot_ref=approval_snapshot_ref,
                observation_hash=approval_observation_hash,
                observed_at=committed_at,
                recorded_by_task_id=approval_task_id,
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
                    "outcome_id": str(approval_outcome_id),
                    "observation_snapshot_ref": approval_snapshot_ref,
                    "observation_hash": approval_observation_hash,
                    "learning_change_id": str(learning_change_id),
                },
                created_at=committed_at,
            ),
        ]
    )
    session.info.setdefault("history_task_ids", {})[learning_change_id] = (
        proposal_task_id,
        approval_task_id,
        operator_id,
        proposal_hash,
        evidence_hash,
        quality_assessment_id,
        quality_assessment_hash,
    )


def _add_learning_change(
    session: Session,
    *,
    team_id: UUID,
    policy_version: int,
    item_id: UUID,
    change_id: UUID,
    operation: str,
    target_id: UUID | None,
    previous_state: dict[str, object] | None,
    committed_state: dict[str, object] | None,
    committed_at: datetime,
    legacy_root: bool = False,
) -> None:
    _add_approval_task_and_events(
        session,
        team_id=team_id,
        policy_version=policy_version,
        learning_change_id=change_id,
        item_id=item_id,
        operation=operation,
        state=committed_state or previous_state or {},
        committed_at=committed_at,
    )
    (
        proposal_task_id,
        approval_task_id,
        operator_id,
        proposal_hash,
        evidence_hash,
        quality_assessment_id,
        quality_assessment_hash,
    ) = session.info["history_task_ids"][change_id]
    stored_committed = (
        _legacy_state(committed_state)
        if legacy_root and committed_state is not None
        else (
            build_knowledge_item_snapshot(committed_state)
            if committed_state is not None
            else None
        )
    )
    stored_previous = (
        build_knowledge_item_snapshot(previous_state)
        if previous_state is not None
        else None
    )
    session.add(
        LearningChange(
            id=change_id,
            team_id=team_id,
            target_kind="knowledge_item",
            target_id=target_id,
            operation=operation,
            proposed_state={"proposal_hash": proposal_hash},
            previous_state=stored_previous,
            committed_state=stored_committed,
            evidence_basis=[],
            evidence_basis_hash=evidence_hash,
            status="accepted",
            idempotency_key=f"history-{change_id}",
            proposed_by_task_id=proposal_task_id,
            committed_by_task_id=approval_task_id,
            operator_id=operator_id,
            decision_reason=None,
            committed_at=committed_at,
        )
    )
    session.flush()


def _add_review_task(
    session: Session,
    *,
    team_id: UUID,
    policy_version: int,
    item_id: UUID,
    root_id: UUID,
    current_id: UUID | None,
    version: int,
    review_after: datetime,
    reviewed_at: datetime,
    schema_version: int,
) -> None:
    task_id = uuid4()
    outcome_id = uuid4()
    snapshot_digest = "d" * 64
    snapshot_ref = f"snap://sha256/{snapshot_digest}"
    observation_hash = f"sha256:{snapshot_digest}"
    session.add(
        Task(
            id=task_id,
            team_id=team_id,
            task_type="review_knowledge",
            status="done",
            attempt_count=1,
            policy_version=policy_version,
            allowed_writes=["KnowledgeItem"],
            budget={
                "max_tool_calls": 0,
                "max_cost_usd": 0.0,
                "deadline_seconds": 60,
            },
            completed_at=reviewed_at,
        )
    )
    session.flush()
    entry: dict[str, object] = {
        "knowledge_item_id": str(item_id),
        "version": version,
        "review_after": review_after.isoformat(),
        "origin_learning_change_id": str(root_id),
    }
    if schema_version == 2:
        assert current_id is not None
        entry["current_learning_change_id"] = str(current_id)
    session.add_all(
        [
            Event(
                id=uuid4(),
                task_id=task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=reviewed_at - timedelta(seconds=1),
            ),
            Event(
                id=uuid4(),
                task_id=task_id,
                type="knowledge_items_reviewed",
                payload={
                    "schema_version": schema_version,
                    "team_id": str(team_id),
                    "task_id": str(task_id),
                    "attempt_count": 1,
                    "reviewed_at": reviewed_at.isoformat(),
                    "items": [entry],
                },
                created_at=reviewed_at,
            ),
            Outcome(
                id=outcome_id,
                team_id=team_id,
                subject_kind="task",
                subject_id=task_id,
                outcome_type="task_execution",
                expected=None,
                observation_snapshot_ref=snapshot_ref,
                observation_hash=observation_hash,
                observed_at=reviewed_at,
                recorded_by_task_id=task_id,
            ),
            Event(
                id=uuid4(),
                task_id=task_id,
                type="task_completed",
                payload={
                    "from_status": "running",
                    "to_status": "done",
                    "attempt_count": 1,
                    "result_category": "success_knowledge_reviewed",
                    "failure_reason": None,
                    "outcome_id": str(outcome_id),
                    "observation_snapshot_ref": snapshot_ref,
                    "observation_hash": observation_hash,
                },
                created_at=reviewed_at,
            ),
        ]
    )


@pytest.fixture
def history_env(
    session_factory: sessionmaker[Session],
) -> dict[str, object]:
    team_id = uuid4()
    policy_id = uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="history_test", status="active"))
        session.flush()
        session.add(
            TeamPolicy(
                id=policy_id,
                team_id=team_id,
                version=1,
                schema_version=2,
                rules={
                    "sources": [],
                    "review": {"knowledge_item_interval_days": 2},
                },
            )
        )
    env: dict[str, object] = {
        "session_factory": session_factory,
        "team_id": team_id,
        "policy_id": policy_id,
        "task_ids": [],
        "learning_change_ids": [],
        "item_ids": [],
    }
    try:
        yield env
    finally:
        with session_factory.begin() as session:
            session.execute(
                delete(Event).where(
                    Event.task_id.in_(
                        session.query(Task.id).filter(Task.team_id == team_id)
                    )
                )
            )
            session.execute(
                delete(Outcome).where(Outcome.team_id == team_id)
            )
            session.execute(
                delete(KnowledgeItem).where(KnowledgeItem.team_id == team_id)
            )
            session.execute(
                delete(LearningChange).where(LearningChange.team_id == team_id)
            )
            session.execute(delete(Task).where(Task.team_id == team_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


def _create_root(
    env: dict[str, object], *, legacy: bool, now: datetime | None = None
) -> tuple[UUID, UUID, datetime, dict[str, object]]:
    session_factory = env["session_factory"]
    team_id = env["team_id"]
    assert isinstance(session_factory, sessionmaker)
    assert isinstance(team_id, UUID)
    item_id, root_id = uuid4(), uuid4()
    committed_at = now or (datetime.now(timezone.utc) - timedelta(days=10))
    review_after = committed_at + timedelta(days=2)
    state = _state(
        item_id=item_id,
        team_id=team_id,
        root_id=root_id,
        current_id=root_id,
        review_after=review_after,
    )
    with session_factory.begin() as session:
        _add_learning_change(
            session,
            team_id=team_id,
            policy_version=1,
            item_id=item_id,
            change_id=root_id,
            operation="create",
            target_id=None,
            previous_state=None,
            committed_state=state,
            committed_at=committed_at,
            legacy_root=legacy,
        )
        session.add(
            KnowledgeItem(
                id=item_id,
                team_id=team_id,
                kind="practice",
                title=str(state["title"]),
                statement=str(state["statement"]),
                body=str(state["body"]),
                applicability=state["applicability"],
                preconditions=state["preconditions"],
                assumptions=state["assumptions"],
                limitations=state["limitations"],
                non_applicability=state["non_applicability"],
                failure_modes=state["failure_modes"],
                known_counterexamples=state["known_counterexamples"],
                missing_information=state["missing_information"],
                uncertainty=state["uncertainty"],
                confidence=Decimal("0.800"),
                status="active",
                version=1,
                last_validated_at=None,
                review_after=review_after,
                origin_learning_change_id=root_id,
                current_learning_change_id=root_id,
                supersedes_item_id=None,
                superseded_by_id=None,
            )
        )
    return item_id, root_id, review_after, state


def test_legacy_create_snapshot_decodes_without_rewriting_history():
    root_id = uuid4()
    item_id = uuid4()
    team_id = uuid4()
    review_after = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = _state(
        item_id=item_id,
        team_id=team_id,
        root_id=root_id,
        current_id=root_id,
        review_after=review_after,
    )
    original = _legacy_state(state)
    decoded = decode_knowledge_item_snapshot(
        original, root_learning_change_id=root_id
    )

    assert decoded.snapshot_version == 0
    assert decoded.state["current_learning_change_id"] == str(root_id)
    assert decoded.state["supersedes_item_id"] is None
    assert decoded.state["superseded_by_id"] is None
    assert set(decoded.reconstructed_legacy_fields) == {
        "current_learning_change_id",
        "supersedes_item_id",
        "superseded_by_id",
    }
    assert original == _legacy_state(state)


def test_versioned_snapshot_hash_is_verified_and_covers_lifecycle_fields():
    root_id, item_id, team_id = uuid4(), uuid4(), uuid4()
    state = _state(
        item_id=item_id,
        team_id=team_id,
        root_id=root_id,
        current_id=root_id,
        review_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    snapshot = build_knowledge_item_snapshot(state)
    decoded = decode_knowledge_item_snapshot(
        snapshot, root_learning_change_id=root_id
    )
    assert decoded.snapshot_version == 1
    assert decoded.state["current_learning_change_id"] == str(root_id)
    assert decoded.snapshot_hash == snapshot["snapshot_hash"]

    changed = dict(snapshot)
    changed["state"] = dict(snapshot["state"])
    changed["state"]["superseded_by_id"] = str(uuid4())
    with pytest.raises(
        KnowledgeHistoryError, match="knowledge_snapshot_hash_mismatch"
    ):
        decode_knowledge_item_snapshot(changed, root_learning_change_id=root_id)


def test_reconstructs_legacy_review_event_as_a_d7_overlay(history_env):
    item_id, root_id, review_after, _ = _create_root(history_env, legacy=True)
    reviewed_at = review_after + timedelta(hours=1)
    session_factory = history_env["session_factory"]
    team_id = history_env["team_id"]
    assert isinstance(session_factory, sessionmaker)
    assert isinstance(team_id, UUID)

    with session_factory.begin() as session:
        _add_review_task(
            session,
            team_id=team_id,
            policy_version=1,
            item_id=item_id,
            root_id=root_id,
            current_id=None,
            version=1,
            review_after=review_after,
            reviewed_at=reviewed_at,
            schema_version=1,
        )
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        item.status = "needs_review"

    with session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        history = reconstruct_knowledge_item_history(session, item)

    assert history.pointer_order == (root_id,)
    assert history.current_state["status"] == "needs_review"
    assert history.states_by_pointer[root_id]["status"] == "needs_review"
    assert "current_learning_change_id" in history.reconstructed_legacy_fields


def test_reconstructs_review_then_later_revise_and_preserves_pointer_order(history_env):
    item_id, root_id, review_after, _ = _create_root(history_env, legacy=False)
    reviewed_at = review_after + timedelta(hours=1)
    session_factory = history_env["session_factory"]
    team_id = history_env["team_id"]
    assert isinstance(session_factory, sessionmaker)
    assert isinstance(team_id, UUID)

    with session_factory.begin() as session:
        _add_review_task(
            session,
            team_id=team_id,
            policy_version=1,
            item_id=item_id,
            root_id=root_id,
            current_id=root_id,
            version=1,
            review_after=review_after,
            reviewed_at=reviewed_at,
            schema_version=2,
        )
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        item.status = "needs_review"

    revised_at = reviewed_at + timedelta(hours=2)
    next_review = revised_at + timedelta(days=2)
    child_id = uuid4()
    with session_factory.begin() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        previous = knowledge_item_snapshot_state(item)
        committed = dict(previous)
        committed.update(
            {
                "title": "Revised history practice",
                "version": 2,
                "review_after": next_review,
                "current_learning_change_id": str(child_id),
                "last_validated_at": None,
            }
        )
        _add_learning_change(
            session,
            team_id=team_id,
            policy_version=1,
            item_id=item_id,
            change_id=child_id,
            operation="revise",
            target_id=item_id,
            previous_state=previous,
            committed_state=committed,
            committed_at=revised_at,
        )
        item.title = str(committed["title"])
        item.version = 2
        item.review_after = next_review
        item.current_learning_change_id = child_id

    with session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        history = reconstruct_knowledge_item_history(session, item)

    assert history.pointer_order == (root_id, child_id)
    assert history.states_by_pointer[root_id]["status"] == "needs_review"
    assert history.current_state["title"] == "Revised history practice"
    assert history.current_state["status"] == "needs_review"


def test_reconstruction_rejects_missing_parent(history_env):
    item_id, root_id, review_after, _ = _create_root(history_env, legacy=False)
    session_factory = history_env["session_factory"]
    team_id = history_env["team_id"]
    assert isinstance(session_factory, sessionmaker)
    assert isinstance(team_id, UUID)
    child_id = uuid4()
    unknown_parent = uuid4()
    committed_at = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        previous = _state(
            item_id=item_id,
            team_id=team_id,
            root_id=root_id,
            current_id=unknown_parent,
            review_after=review_after,
        )
        committed = dict(previous)
        committed["current_learning_change_id"] = str(child_id)
        committed["version"] = 2
        committed["title"] = "A disconnected revision"
        committed["review_after"] = committed_at + timedelta(days=2)
        _add_learning_change(
            session,
            team_id=team_id,
            policy_version=1,
            item_id=item_id,
            change_id=child_id,
            operation="revise",
            target_id=item_id,
            previous_state=previous,
            committed_state=committed,
            committed_at=committed_at,
        )

    with session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        with pytest.raises(
            KnowledgeHistoryError, match="knowledge_history_missing_parent"
        ):
            reconstruct_knowledge_item_history(session, item)


def test_reconstruction_rejects_fork_from_one_predecessor(history_env):
    item_id, root_id, review_after, _ = _create_root(history_env, legacy=False)
    session_factory = history_env["session_factory"]
    team_id = history_env["team_id"]
    assert isinstance(session_factory, sessionmaker)
    assert isinstance(team_id, UUID)
    first_id, second_id = uuid4(), uuid4()
    committed_at = datetime.now(timezone.utc)

    with session_factory.begin() as session:
        root_state = _state(
            item_id=item_id,
            team_id=team_id,
            root_id=root_id,
            current_id=root_id,
            review_after=review_after,
        )
        for offset, (change_id, title) in enumerate(
            ((first_id, "Fork one"), (second_id, "Fork two")), start=1
        ):
            child_commit_at = committed_at + timedelta(seconds=offset)
            committed = dict(root_state)
            committed.update(
                {
                    "current_learning_change_id": str(change_id),
                    "version": 2,
                    "title": title,
                    "review_after": child_commit_at + timedelta(days=2),
                }
            )
            _add_learning_change(
                session,
                team_id=team_id,
                policy_version=1,
                item_id=item_id,
                change_id=change_id,
                operation="revise",
                target_id=item_id,
                previous_state=root_state,
                committed_state=committed,
                committed_at=child_commit_at,
            )

    with session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        with pytest.raises(
            KnowledgeHistoryError, match="knowledge_history_fork_detected"
        ):
            reconstruct_knowledge_item_history(session, item)


def test_legacy_review_event_ambiguity_fails_closed(history_env):
    item_id, root_id, review_after, _ = _create_root(history_env, legacy=False)
    reviewed_at = review_after + timedelta(hours=1)
    session_factory = history_env["session_factory"]
    team_id = history_env["team_id"]
    assert isinstance(session_factory, sessionmaker)
    assert isinstance(team_id, UUID)
    child_id = uuid4()
    with session_factory.begin() as session:
        _add_review_task(
            session,
            team_id=team_id,
            policy_version=1,
            item_id=item_id,
            root_id=root_id,
            current_id=None,
            version=1,
            review_after=review_after,
            reviewed_at=reviewed_at,
            schema_version=1,
        )
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        item.status = "needs_review"
        previous = knowledge_item_snapshot_state(item)
        committed = dict(previous)
        ambiguous_commit_at = review_after - timedelta(days=2)
        committed.update(
            {
                "status": "active",
                "last_validated_at": ambiguous_commit_at,
                "current_learning_change_id": str(child_id),
                # Deliberately retain the same version/date so the old Event
                # has two plausible lifecycle positions and must fail closed.
            }
        )
        _add_learning_change(
            session,
            team_id=team_id,
            policy_version=1,
            item_id=item_id,
            change_id=child_id,
            operation="revalidate",
            target_id=item_id,
            previous_state=previous,
            committed_state=committed,
            committed_at=ambiguous_commit_at,
        )
        item.status = "active"
        item.last_validated_at = ambiguous_commit_at
        item.current_learning_change_id = child_id

    with session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        with pytest.raises(
            KnowledgeHistoryError, match="knowledge_history_legacy_review_ambiguous"
        ):
            reconstruct_knowledge_item_history(session, item)


def test_reconstruction_rejects_unrecorded_live_state_mutation(history_env):
    item_id, _, _, _ = _create_root(history_env, legacy=False)
    session_factory = history_env["session_factory"]
    assert isinstance(session_factory, sessionmaker)
    with session_factory.begin() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        item.title = "Unrecorded direct mutation"

    with session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        with pytest.raises(
            KnowledgeHistoryError, match="knowledge_history_final_state_mismatch"
        ):
            reconstruct_knowledge_item_history(session, item)



def test_learning_change_operation_target_constraint_accepts_every_frozen_pair(
    history_env,
):
    session_factory = history_env["session_factory"]
    team_id = history_env["team_id"]
    assert isinstance(session_factory, sessionmaker)
    assert isinstance(team_id, UUID)
    target_id = uuid4()
    cases = (
        ("create", None),
        ("revise", target_id),
        ("revalidate", target_id),
        ("supersede", target_id),
        ("retire", target_id),
    )
    with session_factory.begin() as session:
        for operation, proposed_target in cases:
            task_id = uuid4()
            session.add(
                Task(
                    id=task_id,
                    team_id=team_id,
                    task_type="propose_learning_change",
                    status="pending",
                    attempt_count=0,
                    policy_version=1,
                    allowed_writes=["LearningChange"],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.1,
                        "deadline_seconds": 60,
                    },
                )
            )
            session.flush()
            session.add(
                LearningChange(
                    id=uuid4(),
                    team_id=team_id,
                    target_kind="knowledge_item",
                    target_id=proposed_target,
                    operation=operation,
                    proposed_state={"proposal_hash": "sha256:" + "e" * 64},
                    previous_state=None,
                    committed_state=None,
                    evidence_basis=[],
                    evidence_basis_hash="sha256:" + "f" * 64,
                    status="proposed",
                    idempotency_key=f"valid-{operation}-{task_id}",
                    proposed_by_task_id=task_id,
                    committed_by_task_id=None,
                    operator_id=None,
                    decision_reason=None,
                    committed_at=None,
                )
            )
        session.flush()


@pytest.mark.parametrize(
    ("operation", "target_id"),
    [
        ("create", uuid4()),
        ("revise", None),
        ("revalidate", None),
        ("supersede", None),
        ("retire", None),
    ],
)
def test_learning_change_operation_target_constraint_rejects_invalid_pairs(
    history_env, operation, target_id
):
    session_factory = history_env["session_factory"]
    team_id = history_env["team_id"]
    assert isinstance(session_factory, sessionmaker)
    assert isinstance(team_id, UUID)
    with session_factory.begin() as session:
        task_id = uuid4()
        session.add(
            Task(
                id=task_id,
                team_id=team_id,
                task_type="propose_learning_change",
                status="pending",
                attempt_count=0,
                policy_version=1,
                allowed_writes=["LearningChange"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.1,
                    "deadline_seconds": 60,
                },
            )
        )
        session.flush()
        with pytest.raises(DBAPIError, match="ck_learning_changes_target_state"):
            with session.begin_nested():
                session.add(
                    LearningChange(
                        id=uuid4(),
                        team_id=team_id,
                        target_kind="knowledge_item",
                        target_id=target_id,
                        operation=operation,
                        proposed_state={"proposal_hash": "sha256:" + "e" * 64},
                        previous_state=None,
                        committed_state=None,
                        evidence_basis=[],
                        evidence_basis_hash="sha256:" + "f" * 64,
                        status="proposed",
                        idempotency_key=f"invalid-{operation}-{task_id}",
                        proposed_by_task_id=task_id,
                        committed_by_task_id=None,
                        operator_id=None,
                        decision_reason=None,
                        committed_at=None,
                    )
                )
                session.flush()
