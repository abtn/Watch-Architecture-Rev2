from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Sequence
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from core.context_assembly import TaskContextAssembler, TaskContextError
from core.embeddings import EmbeddingBatch, EmbeddingSpace
from core.knowledge_index import (
    HybridKnowledgeRetriever,
    KnowledgeIndexError,
    TeamExperienceIndexer,
    _accepted_learning_change_is_canonical,
    knowledge_item_content_hash,
)
from core.learning_history import (
    KNOWLEDGE_CONTENT_HASH_SCHEME,
    KnowledgeHistoryError,
    encode_state_snapshot,
    knowledge_item_state,
    reconstruct_knowledge_item_history,
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
        supersedes_item_id: UUID | None = None,
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
            "current_learning_change_id": str(learning_change_id),
            "supersedes_item_id": (
                str(supersedes_item_id) if supersedes_item_id is not None else None
            ),
            "superseded_by_id": None,
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
                        "supersedes_item_id": (
                            str(supersedes_item_id)
                            if supersedes_item_id is not None
                            else None
                        ),
                    },
                    previous_state=None,
                    committed_state=(
                        encode_state_snapshot(committed_state)
                        if supersedes_item_id is not None
                        else {
                            key: value
                            for key, value in committed_state.items()
                            if key
                            not in {
                                "current_learning_change_id",
                                "supersedes_item_id",
                                "superseded_by_id",
                            }
                        }
                    ),
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
                        current_learning_change_id=learning_change_id,
                        supersedes_item_id=supersedes_item_id,
                        superseded_by_id=None,
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
                        type="task_started",
                        payload={
                            "from_status": "pending",
                            "to_status": "running",
                            "attempt_count": 1,
                        },
                        created_at=committed_time,
                    ),
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

    def add_accepted_revision(
        self,
        item_id: UUID,
        *,
        body: str,
        committed_at: datetime | None = None,
    ) -> UUID:
        """Create a synthetic, fully-attributed accepted revision for reader tests."""
        change_id, proposer_task_id, approval_task_id = (uuid4() for _ in range(3))
        commit_time = committed_at or datetime.now(timezone.utc)
        started_at = commit_time - timedelta(seconds=1)
        operator_id = "test-host|operator-reviser"
        proposal_hash = "sha256:" + "e" * 64
        evidence_basis_hash = "sha256:" + "f" * 64
        snapshot_ref, snapshot_hash = self.snapshot_store.put(
            b'{"result_category":"success_learning_change_accepted"}'
        )

        with self.session_factory.begin() as session:
            item = session.get(KnowledgeItem, item_id)
            assert item is not None
            previous_state = knowledge_item_state(item)
            policy = session.scalar(
                select(TeamPolicy).where(
                    TeamPolicy.team_id == self.team_id,
                    TeamPolicy.version == self.policy_version,
                )
            )
            assert policy is not None
            interval_days = knowledge_item_review_interval_days(
                policy.rules, policy.schema_version
            )
            review_after = (
                commit_time + timedelta(days=interval_days)
                if interval_days is not None
                else None
            )
            committed_state = dict(previous_state)
            committed_state.update(
                {
                    "body": body,
                    "version": item.version + 1,
                    "current_learning_change_id": str(change_id),
                    "review_after": review_after.isoformat() if review_after else None,
                }
            )
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
                            "max_cost_usd": 0.0,
                            "deadline_seconds": 60,
                        },
                        created_at=started_at,
                        completed_at=commit_time,
                    ),
                    Task(
                        id=approval_task_id,
                        team_id=self.team_id,
                        task_type="approve_learning_change",
                        status="done",
                        attempt_count=1,
                        policy_version=self.policy_version,
                        allowed_writes=["LearningChange", "KnowledgeItem"],
                        budget={
                            "max_tool_calls": 0,
                            "max_cost_usd": 0.0,
                            "deadline_seconds": 30,
                        },
                        created_at=started_at,
                        completed_at=commit_time,
                    ),
                ]
            )
            session.flush()
            session.add(
                LearningChange(
                    id=change_id,
                    team_id=self.team_id,
                    target_kind="knowledge_item",
                    target_id=item.id,
                    operation="revise",
                    proposed_state={
                        "proposal_hash": proposal_hash,
                        "evidence_basis_hash": evidence_basis_hash,
                    },
                    previous_state=encode_state_snapshot(previous_state),
                    committed_state=encode_state_snapshot(committed_state),
                    evidence_basis=[],
                    evidence_basis_hash=evidence_basis_hash,
                    status="accepted",
                    idempotency_key=f"synthetic-revise-{change_id}",
                    proposed_by_task_id=proposer_task_id,
                    committed_by_task_id=approval_task_id,
                    operator_id=operator_id,
                    decision_reason=None,
                    created_at=started_at,
                    committed_at=commit_time,
                )
            )
            session.flush()
            item.body = body
            item.version += 1
            item.current_learning_change_id = change_id
            item.review_after = review_after
            item.updated_at = commit_time
            session.flush()
            outcome = Outcome(
                id=uuid4(),
                team_id=self.team_id,
                subject_kind="task",
                subject_id=approval_task_id,
                outcome_type="task_execution",
                expected=None,
                observation_snapshot_ref=snapshot_ref,
                observation_hash=snapshot_hash,
                observed_at=commit_time,
                recorded_by_task_id=approval_task_id,
            )
            session.add(outcome)
            session.flush()
            session.add_all(
                [
                    Event(
                        id=uuid4(),
                        task_id=approval_task_id,
                        type="task_started",
                        payload={
                            "from_status": "pending",
                            "to_status": "running",
                            "attempt_count": 1,
                        },
                        created_at=started_at,
                    ),
                    Event(
                        id=uuid4(),
                        task_id=approval_task_id,
                        type="learning_change_accepted",
                        payload={
                            "schema_version": 1,
                            "learning_change_id": str(change_id),
                            "operation": "revise",
                            "decision": "accept",
                            "operator_id": operator_id,
                            "approval_task_id": str(approval_task_id),
                            "attempt_count": 1,
                            "evidence_basis_hash": evidence_basis_hash,
                            "proposal_hash": proposal_hash,
                            "committed_at": commit_time.isoformat(),
                            "knowledge_item_id": str(item.id),
                            "knowledge_item_version": item.version,
                        },
                        created_at=commit_time,
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
                            "outcome_id": str(outcome.id),
                            "observation_snapshot_ref": snapshot_ref,
                            "observation_hash": snapshot_hash,
                            "learning_change_id": str(change_id),
                        },
                        created_at=commit_time,
                    ),
                ]
            )

        self.task_ids.extend([proposer_task_id, approval_task_id])
        self.learning_change_ids.append(change_id)
        return change_id


    def add_accepted_supersession(
        self,
        predecessor_id: UUID,
        successor_id: UUID,
        *,
        committed_at: datetime | None = None,
    ) -> UUID:
        """Create a synthetic accepted supersession for retrieval-gate tests."""
        change_id, proposer_task_id, approval_task_id = (uuid4() for _ in range(3))
        commit_time = committed_at or datetime.now(timezone.utc)
        started_at = commit_time - timedelta(seconds=1)
        operator_id = "test-host|operator-superseder"
        proposal_hash = "sha256:" + "3" * 64
        evidence_basis_hash = "sha256:" + "4" * 64
        snapshot_ref, snapshot_hash = self.snapshot_store.put(
            b'{"result_category":"success_learning_change_accepted"}'
        )

        with self.session_factory.begin() as session:
            predecessor = session.get(KnowledgeItem, predecessor_id)
            successor = session.get(KnowledgeItem, successor_id)
            assert predecessor is not None and successor is not None
            assert predecessor.team_id == successor.team_id == self.team_id
            assert successor.supersedes_item_id == predecessor.id
            previous_state = knowledge_item_state(predecessor)
            committed_state = dict(previous_state)
            committed_state.update(
                {
                    "status": "retired",
                    "current_learning_change_id": str(change_id),
                    "superseded_by_id": str(successor_id),
                }
            )

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
                            "max_cost_usd": 0.0,
                            "deadline_seconds": 60,
                        },
                        created_at=started_at,
                        completed_at=commit_time,
                    ),
                    Task(
                        id=approval_task_id,
                        team_id=self.team_id,
                        task_type="approve_learning_change",
                        status="done",
                        attempt_count=1,
                        policy_version=self.policy_version,
                        allowed_writes=["LearningChange", "KnowledgeItem"],
                        budget={
                            "max_tool_calls": 0,
                            "max_cost_usd": 0.0,
                            "deadline_seconds": 30,
                        },
                        created_at=started_at,
                        completed_at=commit_time,
                    ),
                ]
            )
            session.flush()
            session.add(
                LearningChange(
                    id=change_id,
                    team_id=self.team_id,
                    target_kind="knowledge_item",
                    target_id=predecessor.id,
                    operation="supersede",
                    proposed_state={
                        "proposal_hash": proposal_hash,
                        "evidence_basis_hash": evidence_basis_hash,
                    },
                    previous_state=encode_state_snapshot(previous_state),
                    committed_state=encode_state_snapshot(committed_state),
                    evidence_basis=[],
                    evidence_basis_hash=evidence_basis_hash,
                    status="accepted",
                    idempotency_key=f"synthetic-supersede-{change_id}",
                    proposed_by_task_id=proposer_task_id,
                    committed_by_task_id=approval_task_id,
                    operator_id=operator_id,
                    decision_reason=None,
                    created_at=started_at,
                    committed_at=commit_time,
                )
            )
            session.flush()
            predecessor.status = "retired"
            predecessor.current_learning_change_id = change_id
            predecessor.superseded_by_id = successor_id
            predecessor.updated_at = commit_time
            session.flush()

            outcome = Outcome(
                id=uuid4(),
                team_id=self.team_id,
                subject_kind="task",
                subject_id=approval_task_id,
                outcome_type="task_execution",
                expected=None,
                observation_snapshot_ref=snapshot_ref,
                observation_hash=snapshot_hash,
                observed_at=commit_time,
                recorded_by_task_id=approval_task_id,
            )
            session.add(outcome)
            session.flush()
            session.add_all(
                [
                    Event(
                        id=uuid4(),
                        task_id=approval_task_id,
                        type="task_started",
                        payload={
                            "from_status": "pending",
                            "to_status": "running",
                            "attempt_count": 1,
                        },
                        created_at=started_at,
                    ),
                    Event(
                        id=uuid4(),
                        task_id=approval_task_id,
                        type="learning_change_accepted",
                        payload={
                            "schema_version": 1,
                            "learning_change_id": str(change_id),
                            "operation": "supersede",
                            "decision": "accept",
                            "operator_id": operator_id,
                            "approval_task_id": str(approval_task_id),
                            "attempt_count": 1,
                            "evidence_basis_hash": evidence_basis_hash,
                            "proposal_hash": proposal_hash,
                            "committed_at": commit_time.isoformat(),
                            "knowledge_item_id": str(predecessor.id),
                            "knowledge_item_version": predecessor.version,
                        },
                        created_at=commit_time,
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
                            "outcome_id": str(outcome.id),
                            "observation_snapshot_ref": snapshot_ref,
                            "observation_hash": snapshot_hash,
                            "learning_change_id": str(change_id),
                        },
                        created_at=commit_time,
                    ),
                ]
            )

        self.task_ids.extend([proposer_task_id, approval_task_id])
        self.learning_change_ids.append(change_id)
        return change_id

    def add_accepted_revalidation(
        self,
        item_id: UUID,
        *,
        committed_at: datetime | None = None,
    ) -> UUID:
        """Create a synthetic accepted revalidation after a recorded review."""
        change_id, proposer_task_id, approval_task_id = (uuid4() for _ in range(3))
        commit_time = committed_at or datetime.now(timezone.utc)
        started_at = commit_time - timedelta(seconds=1)
        operator_id = "test-host|operator-revalidator"
        proposal_hash = "sha256:" + "1" * 64
        evidence_basis_hash = "sha256:" + "2" * 64
        snapshot_ref, snapshot_hash = self.snapshot_store.put(
            b'{"result_category":"success_learning_change_accepted"}'
        )

        with self.session_factory.begin() as session:
            item = session.get(KnowledgeItem, item_id)
            assert item is not None and item.status == "needs_review"
            previous_state = knowledge_item_state(item)
            policy = session.scalar(
                select(TeamPolicy).where(
                    TeamPolicy.team_id == self.team_id,
                    TeamPolicy.version == self.policy_version,
                )
            )
            assert policy is not None
            interval_days = knowledge_item_review_interval_days(
                policy.rules, policy.schema_version
            )
            review_after = (
                commit_time + timedelta(days=interval_days)
                if interval_days is not None
                else None
            )
            committed_state = dict(previous_state)
            committed_state.update(
                {
                    "status": "active",
                    "last_validated_at": commit_time.isoformat(),
                    "current_learning_change_id": str(change_id),
                    "review_after": review_after.isoformat() if review_after else None,
                }
            )
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
                            "max_cost_usd": 0.0,
                            "deadline_seconds": 60,
                        },
                        created_at=started_at,
                        completed_at=commit_time,
                    ),
                    Task(
                        id=approval_task_id,
                        team_id=self.team_id,
                        task_type="approve_learning_change",
                        status="done",
                        attempt_count=1,
                        policy_version=self.policy_version,
                        allowed_writes=["LearningChange", "KnowledgeItem"],
                        budget={
                            "max_tool_calls": 0,
                            "max_cost_usd": 0.0,
                            "deadline_seconds": 30,
                        },
                        created_at=started_at,
                        completed_at=commit_time,
                    ),
                ]
            )
            session.flush()
            session.add(
                LearningChange(
                    id=change_id,
                    team_id=self.team_id,
                    target_kind="knowledge_item",
                    target_id=item.id,
                    operation="revalidate",
                    proposed_state={
                        "proposal_hash": proposal_hash,
                        "evidence_basis_hash": evidence_basis_hash,
                    },
                    previous_state=encode_state_snapshot(previous_state),
                    committed_state=encode_state_snapshot(committed_state),
                    evidence_basis=[],
                    evidence_basis_hash=evidence_basis_hash,
                    status="accepted",
                    idempotency_key=f"synthetic-revalidate-{change_id}",
                    proposed_by_task_id=proposer_task_id,
                    committed_by_task_id=approval_task_id,
                    operator_id=operator_id,
                    decision_reason=None,
                    created_at=started_at,
                    committed_at=commit_time,
                )
            )
            session.flush()
            item.status = "active"
            item.last_validated_at = commit_time
            item.current_learning_change_id = change_id
            item.review_after = review_after
            item.updated_at = commit_time
            session.flush()
            outcome = Outcome(
                id=uuid4(),
                team_id=self.team_id,
                subject_kind="task",
                subject_id=approval_task_id,
                outcome_type="task_execution",
                expected=None,
                observation_snapshot_ref=snapshot_ref,
                observation_hash=snapshot_hash,
                observed_at=commit_time,
                recorded_by_task_id=approval_task_id,
            )
            session.add(outcome)
            session.flush()
            session.add_all(
                [
                    Event(
                        id=uuid4(),
                        task_id=approval_task_id,
                        type="task_started",
                        payload={
                            "from_status": "pending",
                            "to_status": "running",
                            "attempt_count": 1,
                        },
                        created_at=started_at,
                    ),
                    Event(
                        id=uuid4(),
                        task_id=approval_task_id,
                        type="learning_change_accepted",
                        payload={
                            "schema_version": 1,
                            "learning_change_id": str(change_id),
                            "operation": "revalidate",
                            "decision": "accept",
                            "operator_id": operator_id,
                            "approval_task_id": str(approval_task_id),
                            "attempt_count": 1,
                            "evidence_basis_hash": evidence_basis_hash,
                            "proposal_hash": proposal_hash,
                            "committed_at": commit_time.isoformat(),
                            "knowledge_item_id": str(item.id),
                            "knowledge_item_version": item.version,
                        },
                        created_at=commit_time,
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
                            "outcome_id": str(outcome.id),
                            "observation_snapshot_ref": snapshot_ref,
                            "observation_hash": snapshot_hash,
                            "learning_change_id": str(change_id),
                        },
                        created_at=commit_time,
                    ),
                ]
            )

        self.task_ids.extend([proposer_task_id, approval_task_id])
        self.learning_change_ids.append(change_id)
        return change_id

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



def test_canonicality_follows_current_learning_change_and_reconstructs_history(
    experience_env: TeamExperienceEnv,
) -> None:
    item_id = experience_env.add_accepted_item()
    origin_change_id = experience_env.learning_change_ids[0]
    current_change_id = experience_env.add_accepted_revision(
        item_id,
        body="A revised alpha checklist preserves contrary evidence.",
    )

    with experience_env.session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        origin = session.get(LearningChange, origin_change_id)
        current = session.get(LearningChange, current_change_id)
        assert item is not None and origin is not None and current is not None
        assert item.current_learning_change_id == current_change_id
        assert current.target_id == item_id
        assert current.operation == "revise"
        assert _accepted_learning_change_is_canonical(session, item, current)
        assert not _accepted_learning_change_is_canonical(session, item, origin)
        history = reconstruct_knowledge_item_history(session, item)
        assert history.learning_change_ids == (origin_change_id, current_change_id)


def test_indexer_and_retriever_accept_a_reconstructed_non_origin_current_change(
    experience_env: TeamExperienceEnv,
) -> None:
    item_id = experience_env.add_accepted_item()
    current_change_id = experience_env.add_accepted_revision(
        item_id,
        body="The revised alpha checklist preserves contrary evidence.",
    )
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)

    indexed = indexer.index_knowledge_item(item_id)
    assert indexed.outcome == "indexed"

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    passages = retriever.retrieve(experience_env.team_id, "alpha checklist")
    assert passages
    assert all(p.knowledge_item_id == item_id for p in passages)
    with experience_env.session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        assert item.current_learning_change_id == current_change_id


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
    assert all(
        row.current_learning_change_id == experience_env.learning_change_ids[0]
        for row in rows
    )
    assert all(row.content_hash_scheme == KNOWLEDGE_CONTENT_HASH_SCHEME for row in rows)
    with experience_env.session_factory() as session:
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item_id
            )
        )
        assert state is not None
        assert state.status == "published"
        assert state.item_version == 1
        assert state.current_learning_change_id == experience_env.learning_change_ids[0]
        assert state.content_hash_scheme == KNOWLEDGE_CONTENT_HASH_SCHEME
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
        assert all(
            row.embedding_space_key != provider.current_space().key for row in chunks
        )

    # Query embedding remains available; only the preceding index refresh failed.
    provider.fail = False
    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    assert retriever.retrieve(experience_env.team_id, "alpha practice") == ()

    provider.fail = False
    rebuilt = indexer.rebuild_all()
    assert len(rebuilt) == 1
    assert rebuilt[0].outcome == "indexed"
    calls_after_rebuild = provider.calls

    repeated_rebuild = indexer.rebuild_all()
    assert len(repeated_rebuild) == 1
    assert repeated_rebuild[0].outcome == "unchanged"
    assert provider.calls == calls_after_rebuild

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


def test_revalidation_pointer_only_transition_invalidates_old_projection(
    experience_env: TeamExperienceEnv,
) -> None:
    now = datetime.now(timezone.utc)
    item_id = experience_env.add_accepted_item(
        committed_at=now - timedelta(days=40),
        review_interval_days=30,
    )
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)
    with patch("core.knowledge_index.datetime") as mocked_datetime:
        mocked_datetime.now.return_value = now - timedelta(days=20)
        indexed = indexer.index_knowledge_item(
            item_id, now=now - timedelta(days=20)
        )
    assert indexed.outcome == "indexed"

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    # Read the valid pre-review projection at a time when the item was still eligible.
    with patch("core.knowledge_index.datetime") as mocked_datetime:
        mocked_datetime.now.return_value = now - timedelta(days=20)
        old_passages = retriever.retrieve(experience_env.team_id, "alpha practice")
    assert old_passages
    old_passage = old_passages[0]

    review_task_id = experience_env.add_review_task()
    review_result = TaskRuntime(
        experience_env.session_factory, experience_env.snapshot_store
    ).complete_knowledge_review(review_task_id)
    assert review_result.status == "done"

    old_pointer = experience_env.learning_change_ids[0]
    revalidation_time = datetime.now(timezone.utc)
    new_pointer = experience_env.add_accepted_revalidation(
        item_id, committed_at=revalidation_time
    )

    with experience_env.session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item_id
            )
        )
        chunk = session.scalar(
            select(TeamExperienceChunk).where(
                TeamExperienceChunk.knowledge_item_id == item_id
            )
        )
        assert item is not None and state is not None and chunk is not None
        assert item.version == 1
        assert item.current_learning_change_id == new_pointer
        assert item.status == "active"
        assert item.last_validated_at == revalidation_time
        assert state.current_learning_change_id == old_pointer
        assert chunk.current_learning_change_id == old_pointer
        with pytest.raises(
            TaskContextError, match="team_experience_index_not_published"
        ):
            TaskContextAssembler._validate_team_experience_passage(
                session,
                SimpleNamespace(team_id=experience_env.team_id),
                old_passage,
                revalidation_time,
            )

    # Retrieval must reject the old projection despite unchanged content and version.
    assert retriever.retrieve(experience_env.team_id, "alpha practice") == ()

    # A fresh publication carries the new pointer and becomes retrievable again.
    rebuilt = indexer.index_knowledge_item(item_id, now=now)
    assert rebuilt.outcome == "indexed"
    passages = retriever.retrieve(experience_env.team_id, "alpha practice")
    assert passages
    assert all(p.knowledge_item_id == item_id for p in passages)


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


def test_pending_supersession_candidate_is_hidden_until_reciprocal_commit(
    experience_env: TeamExperienceEnv,
) -> None:
    predecessor_id = experience_env.add_accepted_item()
    candidate_id = experience_env.add_accepted_item(
        title="Replacement alpha practice for source review",
        statement="Use the replacement alpha checklist before accepting a source.",
        body="The replacement alpha practice preserves contrary evidence.",
        supersedes_item_id=predecessor_id,
    )
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)
    assert indexer.index_knowledge_item(predecessor_id).outcome == "indexed"
    assert indexer.index_knowledge_item(candidate_id).outcome == "indexed"

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    passages = retriever.retrieve(experience_env.team_id, "alpha practice")

    assert passages
    assert {passage.knowledge_item_id for passage in passages} == {predecessor_id}


@pytest.mark.parametrize(
    "predecessor_disposition",
    ["needs_review", "due", "retired_without_successor"],
)
def test_pending_candidate_and_ineligible_predecessor_are_both_hidden(
    experience_env: TeamExperienceEnv,
    predecessor_disposition: str,
) -> None:
    predecessor_id = experience_env.add_accepted_item()
    candidate_id = experience_env.add_accepted_item(
        title="Replacement alpha practice for source review",
        statement="Use the replacement alpha checklist before accepting a source.",
        body="The replacement alpha practice preserves contrary evidence.",
        supersedes_item_id=predecessor_id,
    )
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)
    assert indexer.index_knowledge_item(predecessor_id).outcome == "indexed"
    assert indexer.index_knowledge_item(candidate_id).outcome == "indexed"

    with experience_env.session_factory.begin() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        assert predecessor is not None
        if predecessor_disposition == "needs_review":
            predecessor.status = "needs_review"
        elif predecessor_disposition == "due":
            predecessor.review_after = datetime.now(timezone.utc) - timedelta(seconds=1)
        else:
            predecessor.status = "retired"

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    assert retriever.retrieve(experience_env.team_id, "alpha practice") == ()


def test_committed_supersession_hides_predecessor_and_publishes_candidate(
    experience_env: TeamExperienceEnv,
) -> None:
    predecessor_id = experience_env.add_accepted_item()
    candidate_id = experience_env.add_accepted_item(
        title="Replacement alpha practice for source review",
        statement="Use the replacement alpha checklist before accepting a source.",
        body="The replacement alpha practice preserves contrary evidence.",
        supersedes_item_id=predecessor_id,
    )
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)
    assert indexer.index_knowledge_item(predecessor_id).outcome == "indexed"
    assert indexer.index_knowledge_item(candidate_id).outcome == "indexed"

    experience_env.add_accepted_supersession(predecessor_id, candidate_id)

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    passages = retriever.retrieve(experience_env.team_id, "alpha practice")

    assert passages
    assert {passage.knowledge_item_id for passage in passages} == {candidate_id}
    with experience_env.session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        candidate = session.get(KnowledgeItem, candidate_id)
        assert predecessor is not None and candidate is not None
        assert predecessor.status == "retired"
        assert predecessor.superseded_by_id == candidate_id
        assert candidate.supersedes_item_id == predecessor_id


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
    experience_env.add_accepted_revision(
        item_id,
        body="The revised alpha practice preserves contrary evidence.",
    )
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
    assert knowledge["team_experience"][0]["knowledge_item_version"] == 2
    assert knowledge["team_experience"][0]["current_learning_change_id"] == str(
        experience_env.learning_change_ids[-1]
    )
    assert knowledge["team_experience"][0]["content_hash_scheme"] == (
        KNOWLEDGE_CONTENT_HASH_SCHEME
    )
    selected = assembled.manifest["selected"]
    assert selected
    assert selected[0]["logical_core"] == "team_experience"
    assert selected[0]["origin_learning_change_id"] == str(
        experience_env.learning_change_ids[0]
    )
    assert selected[0]["current_learning_change_id"] == str(
        experience_env.learning_change_ids[-1]
    )
    assert selected[0]["content_hash_scheme"] == KNOWLEDGE_CONTENT_HASH_SCHEME
    assert assembled.manifest["schema_version"] == "r6e-context-manifest-v3"
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


def test_context_final_validation_rechecks_reciprocal_supersession_visibility(
    experience_env: TeamExperienceEnv,
) -> None:
    predecessor_id = experience_env.add_accepted_item()
    candidate_id = experience_env.add_accepted_item(
        title="Replacement alpha practice for source review",
        statement="Use the replacement alpha checklist before accepting a source.",
        body="The replacement alpha practice preserves contrary evidence.",
        supersedes_item_id=predecessor_id,
    )
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)
    assert indexer.index_knowledge_item(predecessor_id).outcome == "indexed"
    assert indexer.index_knowledge_item(candidate_id).outcome == "indexed"

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    predecessor_passages = retriever.retrieve(
        experience_env.team_id, "alpha practice"
    )
    predecessor_passage = next(
        passage
        for passage in predecessor_passages
        if passage.knowledge_item_id == predecessor_id
    )

    with experience_env.session_factory() as session:
        candidate = session.get(KnowledgeItem, candidate_id)
        candidate_chunk = session.scalar(
            select(TeamExperienceChunk)
            .where(TeamExperienceChunk.knowledge_item_id == candidate_id)
            .order_by(TeamExperienceChunk.chunk_index)
        )
        assert candidate is not None and candidate_chunk is not None
        candidate_passage = replace(
            predecessor_passage,
            content_hash=knowledge_item_content_hash(candidate),
            chunk_id=candidate_chunk.id,
            chunk_index=candidate_chunk.chunk_index,
            text=candidate_chunk.chunk_text,
            chunk_hash=candidate_chunk.chunk_hash,
            knowledge_item_id=candidate.id,
            knowledge_item_version=candidate.version,
            origin_learning_change_id=candidate.origin_learning_change_id,
            current_learning_change_id=candidate.current_learning_change_id,
            content_hash_scheme=candidate_chunk.content_hash_scheme,
        )
        scope = SimpleNamespace(team_id=experience_env.team_id)
        with pytest.raises(
            TaskContextError, match="team_experience_supersession_not_visible"
        ):
            TaskContextAssembler._validate_team_experience_passage(
                session, scope, candidate_passage, datetime.now(timezone.utc)
            )

    experience_env.add_accepted_supersession(predecessor_id, candidate_id)
    with experience_env.session_factory() as session:
        TaskContextAssembler._validate_team_experience_passage(
            session,
            SimpleNamespace(team_id=experience_env.team_id),
            candidate_passage,
            datetime.now(timezone.utc),
        )


def test_review_knowledge_task_atomically_marks_due_items_and_replays_once(
    experience_env: TeamExperienceEnv,
) -> None:
    now = datetime.now(timezone.utc)
    due_item = experience_env.add_accepted_item(
        title="Due alpha practice",
        committed_at=now - timedelta(days=40),
        review_interval_days=30,
    )
    current_change_id = experience_env.add_accepted_revision(
        due_item,
        body="A revised due alpha practice preserves contrary evidence.",
        committed_at=now - timedelta(days=35),
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
        assert (
            events[0].payload["items"][0]["current_learning_change_id"]
            == str(current_change_id)
        )
        history = reconstruct_knowledge_item_history(session, due)
        assert history.state["status"] == "needs_review"
        assert history.learning_change_ids == (
            due.origin_learning_change_id,
            current_change_id,
        )
        legacy_event_id = events[0].id
        outcome_count = session.scalar(
            select(Outcome.id).where(
                Outcome.recorded_by_task_id == task_id,
                Outcome.outcome_type == "task_execution",
            )
        )
        assert outcome_count is not None

    # Simulate a pre-B1 review Event without current_learning_change_id.
    with experience_env.session_factory.begin() as session:
        event = session.get(Event, legacy_event_id)
        assert event is not None
        payload = dict(event.payload)
        item_records = [dict(record) for record in payload["items"]]
        item_records[0].pop("current_learning_change_id")
        payload["items"] = item_records
        event.payload = payload

    with experience_env.session_factory() as session:
        due = session.get(KnowledgeItem, due_item)
        assert due is not None
        legacy_history = reconstruct_knowledge_item_history(session, due)
        assert legacy_history.state["status"] == "needs_review"
        assert legacy_history.applied_review_event_ids == (legacy_event_id,)


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


def test_history_loader_rejects_cross_team_change_targeting_item(
    experience_env: TeamExperienceEnv,
) -> None:
    item_id = experience_env.add_accepted_item()
    with experience_env.session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        previous = knowledge_item_state(item)

    foreign_team_id, approval_task_id, change_id = (uuid4() for _ in range(3))
    committed_at = datetime.now(timezone.utc)
    started_at = committed_at - timedelta(seconds=30)
    committed = dict(previous)
    committed.update(
        {
            "body": "A foreign-Team change targeting another Team's item.",
            "version": 2,
            "current_learning_change_id": str(change_id),
        }
    )
    operator_id = "test-host|foreign-team-operator"

    with experience_env.session_factory.begin() as session:
        session.add(
            Team(id=foreign_team_id, domain="foreign", status="active")
        )
        session.flush()
        session.add(
            TeamPolicy(
                id=uuid4(),
                team_id=foreign_team_id,
                version=1,
                schema_version=2,
                rules={"sources": []},
            )
        )
        session.flush()
        session.add(
            Task(
                id=approval_task_id,
                team_id=foreign_team_id,
                task_type="approve_learning_change",
                status="running",
                attempt_count=1,
                policy_version=1,
                allowed_writes=["LearningChange", "KnowledgeItem"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.0,
                    "deadline_seconds": 30,
                },
                created_at=started_at,
            )
        )
        session.flush()
        session.add(
            LearningChange(
                id=change_id,
                team_id=foreign_team_id,
                target_kind="knowledge_item",
                target_id=item_id,
                operation="revise",
                proposed_state={"proposal_hash": "sha256:" + ("c" * 64)},
                previous_state=encode_state_snapshot(previous),
                committed_state=encode_state_snapshot(committed),
                evidence_basis=[],
                evidence_basis_hash="sha256:" + ("d" * 64),
                status="accepted",
                idempotency_key="foreign-target-" + str(change_id),
                proposed_by_task_id=approval_task_id,
                committed_by_task_id=approval_task_id,
                operator_id=operator_id,
                created_at=started_at,
                committed_at=committed_at,
            )
        )
        session.flush()
        session.add_all(
            [
                Event(
                    id=uuid4(),
                    task_id=approval_task_id,
                    type="task_started",
                    payload={
                        "from_status": "pending",
                        "to_status": "running",
                        "attempt_count": 1,
                    },
                    created_at=started_at,
                ),
                Event(
                    id=uuid4(),
                    task_id=approval_task_id,
                    type="learning_change_accepted",
                    payload={
                        "learning_change_id": str(change_id),
                        "operation": "revise",
                        "decision": "accept",
                        "operator_id": operator_id,
                        "approval_task_id": str(approval_task_id),
                        "attempt_count": 1,
                        "committed_at": committed_at.isoformat(),
                    },
                    created_at=committed_at,
                ),
            ]
        )

    with experience_env.session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        with pytest.raises(
            KnowledgeHistoryError, match="accepted_change_cross_team"
        ):
            reconstruct_knowledge_item_history(session, item)


@pytest.mark.parametrize("mutation", ["status", "review_after", "last_validated_at"])
def test_history_rejects_unauthorized_live_status_or_date_mutation(
    experience_env: TeamExperienceEnv,
    mutation: str,
) -> None:
    item_id = experience_env.add_accepted_item()
    with experience_env.session_factory.begin() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        if mutation == "status":
            item.status = "needs_review"
        elif mutation == "review_after":
            assert item.review_after is not None
            item.review_after += timedelta(days=1)
        else:
            item.last_validated_at = datetime.now(timezone.utc)

    with experience_env.session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        with pytest.raises(
            KnowledgeHistoryError,
            match="reconstructed_history_does_not_match_live_item",
        ):
            reconstruct_knowledge_item_history(session, item)



def test_provider_space_change_at_publication_boundary_keeps_projection_stale(
    experience_env: TeamExperienceEnv,
) -> None:
    item_id = experience_env.add_accepted_item()

    class ChangesSpaceAtPublication(FakeEmbeddingProvider):
        def __init__(self) -> None:
            super().__init__()
            self.space_reads = 0

        def current_space(self) -> EmbeddingSpace:
            self.space_reads += 1
            revision = (
                "changed-at-publication"
                if self.space_reads >= 4
                else "test-revision"
            )
            return EmbeddingSpace(
                provider="checkpoint4-test",
                model="deterministic-four-dimensional",
                revision=revision,
                dimensions=4,
                configuration="checkpoint4-test-v1",
            )

    provider = ChangesSpaceAtPublication()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)

    with pytest.raises(
        KnowledgeIndexError, match="embedding_space_changed_during_indexing"
    ):
        indexer.index_knowledge_item(item_id)

    with experience_env.session_factory() as session:
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item_id
            )
        )
        chunks = list(
            session.scalars(
                select(TeamExperienceChunk).where(
                    TeamExperienceChunk.knowledge_item_id == item_id
                )
            )
        )
    assert state is not None
    assert state.status == "stale"
    assert state.last_error_kind == "KnowledgeIndexError"
    assert state.attempt_count == 1
    assert chunks == []


def test_rebuild_all_republishes_legacy_opaque_projection_and_restores_retrieval(
    experience_env: TeamExperienceEnv,
) -> None:
    item_id = experience_env.add_accepted_item()
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)
    first = indexer.index_knowledge_item(item_id)
    assert first.outcome == "indexed"

    # This is the exact post-0016 compatibility state: the historical vector
    # bytes remain present, but their pointer/hash provenance is opaque and stale.
    with experience_env.session_factory.begin() as session:
        chunks = list(
            session.scalars(
                select(TeamExperienceChunk).where(
                    TeamExperienceChunk.knowledge_item_id == item_id
                )
            )
        )
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item_id
            )
        )
        assert chunks and state is not None
        for chunk in chunks:
            chunk.current_learning_change_id = None
            chunk.content_hash_scheme = "legacy-opaque"
        state.current_learning_change_id = None
        state.content_hash_scheme = "legacy-opaque"
        state.status = "stale"

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    assert retriever.retrieve(experience_env.team_id, "alpha practice") == ()

    rebuilt = indexer.rebuild_all(now=datetime.now(timezone.utc))
    result = next(entry for entry in rebuilt if entry.knowledge_item_id == item_id)
    assert result.outcome == "indexed"

    with experience_env.session_factory() as session:
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item_id
            )
        )
        chunks = list(
            session.scalars(
                select(TeamExperienceChunk).where(
                    TeamExperienceChunk.knowledge_item_id == item_id
                )
            )
        )
        item = session.get(KnowledgeItem, item_id)
    assert state is not None and item is not None
    assert state.status == "published"
    assert state.current_learning_change_id == item.current_learning_change_id
    assert state.content_hash_scheme == KNOWLEDGE_CONTENT_HASH_SCHEME
    assert chunks
    assert all(
        chunk.current_learning_change_id == item.current_learning_change_id
        and chunk.content_hash_scheme == KNOWLEDGE_CONTENT_HASH_SCHEME
        for chunk in chunks
    )

    passages = retriever.retrieve(experience_env.team_id, "alpha practice")
    assert passages
    assert all(passage.knowledge_item_id == item_id for passage in passages)

def test_accepted_create_flows_through_v2_projection_retrieval_and_context_v3(
    experience_env: TeamExperienceEnv,
) -> None:
    item_id = experience_env.add_accepted_item()
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)

    indexed = indexer.index_knowledge_item(item_id)
    assert indexed.outcome == "indexed"

    with experience_env.session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        assert item.current_learning_change_id is not None
        assert item.origin_learning_change_id == item.current_learning_change_id
        learning_change = session.get(
            LearningChange, item.current_learning_change_id
        )
        assert learning_change is not None
        assert learning_change.status == "accepted"
        assert learning_change.operation == "create"
        assert learning_change.target_kind == "knowledge_item"
        assert learning_change.target_id is None
        assert indexed.item_content_hash == knowledge_item_content_hash(item)
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item_id
            )
        )
        chunks = list(
            session.scalars(
                select(TeamExperienceChunk).where(
                    TeamExperienceChunk.knowledge_item_id == item_id
                )
            )
        )
        assert state is not None
        assert state.current_learning_change_id == item.current_learning_change_id
        assert state.content_hash_scheme == KNOWLEDGE_CONTENT_HASH_SCHEME
        assert chunks
        assert all(
            chunk.current_learning_change_id == item.current_learning_change_id
            and chunk.content_hash_scheme == KNOWLEDGE_CONTENT_HASH_SCHEME
            for chunk in chunks
        )

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    passages = retriever.retrieve(experience_env.team_id, "alpha practice")
    assert passages
    assert all(passage.knowledge_item_id == item_id for passage in passages)
    assert all(
        passage.current_learning_change_id
        == experience_env.learning_change_ids[0]
        for passage in passages
    )

    task_id = experience_env.add_strategy_task(
        "Use the accepted alpha practice to review a new source."
    )
    assembled = TaskContextAssembler(
        experience_env.session_factory,
        experience_env.snapshot_store,
        retriever,
    ).assemble(task_id)

    entries = assembled.document["knowledge"]["team_experience"]
    assert entries
    assert entries[0]["knowledge_item_id"] == str(item_id)
    assert entries[0]["current_learning_change_id"] == str(
        experience_env.learning_change_ids[0]
    )
    assert entries[0]["content_hash_scheme"] == KNOWLEDGE_CONTENT_HASH_SCHEME
    assert assembled.manifest["schema_version"] == "r6e-context-manifest-v3"
    selected = assembled.manifest["selected"]
    assert selected
    assert any(
        entry["knowledge_item_id"] == str(item_id)
        and entry["origin_learning_change_id"]
        == str(experience_env.learning_change_ids[0])
        and entry["current_learning_change_id"]
        == str(experience_env.learning_change_ids[0])
        and entry["content_hash_scheme"] == KNOWLEDGE_CONTENT_HASH_SCHEME
        for entry in selected
    )


def test_offset_aware_d7_review_boundary_is_strict(
    experience_env: TeamExperienceEnv,
) -> None:
    offset = timezone(timedelta(hours=5, minutes=30))
    review_boundary = datetime(2026, 12, 31, 12, 0, tzinfo=offset)
    item_id = experience_env.add_accepted_item(
        committed_at=review_boundary - timedelta(days=30),
        review_interval_days=30,
    )
    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)

    before_boundary = indexer.index_knowledge_item(
        item_id, now=review_boundary - timedelta(microseconds=1)
    )
    assert before_boundary.outcome == "indexed"

    at_boundary = indexer.index_knowledge_item(item_id, now=review_boundary)
    assert at_boundary.outcome == "ineligible"

    with experience_env.session_factory() as session:
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item_id
            )
        )
    assert state is not None
    assert state.status == "ineligible"
    assert state.chunk_count == 0

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    assert retriever.retrieve(experience_env.team_id, "alpha practice") == ()

@pytest.mark.parametrize(
    "tamper",
    [
        "current_pointer",
        "wrong_team",
        "wrong_target",
        "wrong_status",
        "invalid_snapshot",
        "wrong_scheme",
        "stale_state",
        "chunk_hash",
    ],
)
def test_canonicality_tampering_blocks_retrieval_and_context_inclusion(
    experience_env: TeamExperienceEnv,
    tamper: str,
) -> None:
    item_id = experience_env.add_accepted_item()
    if tamper == "current_pointer":
        experience_env.add_accepted_revision(
            item_id,
            body="The revised alpha practice preserves contrary evidence.",
        )

    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(experience_env.session_factory, provider)
    assert indexer.index_knowledge_item(item_id).outcome == "indexed"
    task_id = experience_env.add_strategy_task(
        "Use the alpha practice to review a new source."
    )

    with experience_env.session_factory.begin() as session:
        item = session.get(KnowledgeItem, item_id)
        state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item_id
            )
        )
        chunk = session.scalar(
            select(TeamExperienceChunk).where(
                TeamExperienceChunk.knowledge_item_id == item_id
            )
        )
        assert item is not None and state is not None and chunk is not None
        learning_change = session.get(
            LearningChange, item.current_learning_change_id
        )
        assert learning_change is not None

        if tamper == "current_pointer":
            origin_id = experience_env.learning_change_ids[0]
            state.current_learning_change_id = origin_id
            chunk.current_learning_change_id = origin_id
        elif tamper == "wrong_team":
            other_team_id = uuid4()
            session.add(
                Team(id=other_team_id, domain="other", status="active")
            )
            session.flush()
            chunk.team_id = other_team_id
        elif tamper == "wrong_target":
            learning_change.target_id = item_id
        elif tamper == "wrong_status":
            item.status = "needs_review"
        elif tamper == "invalid_snapshot":
            committed_state = dict(learning_change.committed_state)
            committed_state["body"] = "Tampered committed content."
            learning_change.committed_state = committed_state
        elif tamper == "wrong_scheme":
            state.content_hash_scheme = "legacy-opaque"
            chunk.content_hash_scheme = "legacy-opaque"
        elif tamper == "stale_state":
            state.status = "stale"
        elif tamper == "chunk_hash":
            chunk.chunk_hash = "sha256:" + "f" * 64

    retriever = HybridKnowledgeRetriever(
        experience_env.session_factory, experience_env.snapshot_store, provider
    )
    assert retriever.retrieve(experience_env.team_id, "alpha practice") == ()

    assembled = TaskContextAssembler(
        experience_env.session_factory,
        experience_env.snapshot_store,
        retriever,
    ).assemble(task_id)
    assert assembled.document["knowledge"]["team_experience"] == []

