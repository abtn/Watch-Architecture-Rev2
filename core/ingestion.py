"""Deterministic K1 Signal ingestion and its bounded Kernel side effects."""

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Signal, Task, Team, TeamPolicy
from core.snapshot_store import SnapshotStore

_EVENT_K_TASK_TYPES = frozenset(
    {
        "ingest_source",
        "manual_signal_ingest",
        "triage_signal",
        "update_thread",
        "operator_update",
        "apply_decay",
        "check_triggers",
        "review_knowledge",
        "render_output",
        "record_outcome",
        "evaluate_outcome",
        "propose_learning_change",
        "approve_learning_change",
        "seed_knowledge",
        "request_consultation",
        "answer_consultation",
        "create_team",
        "configure_team",
        "activate_team",
    }
)


@dataclass(frozen=True)
class IngestionProposal:
    task_id: UUID
    origin_url: str
    source_type: str
    fetched_at: datetime
    content: bytes
    claimed_content_hash: str
    extracted_summary: str | None = None


@dataclass(frozen=True)
class IngestionResult:
    outcome: Literal["signal_ingested", "fetch_no_change", "replayed"]
    signal_id: UUID
    snapshot_ref: str
    event_id: UUID


class IngestionValidationError(ValueError):
    def __init__(self, reason: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.payload = payload or {}


class ProposalRejected(IngestionValidationError):
    def __init__(self, reason: str, event_id: UUID) -> None:
        super().__init__(reason)
        self.event_id = event_id


class TaskNotFound(RuntimeError):
    """Raised when a proposal cannot be attributed to an existing Task."""


class EventScopeViolation(RuntimeError):
    """Raised when no documented Event K scope can attribute a rejection."""


class IngestionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store

    def ingest(self, proposal: IngestionProposal) -> IngestionResult:
        computed_hash = f"sha256:{hashlib.sha256(proposal.content).hexdigest()}"
        context = {
            "origin_url": proposal.origin_url,
            "source_type": proposal.source_type,
            "claimed_content_hash": proposal.claimed_content_hash,
            "computed_content_hash": computed_hash,
        }

        try:
            return self._commit(proposal, computed_hash)
        except IngestionValidationError as error:
            payload = {**context, **error.payload}
            event_id = self._record_rejection(proposal.task_id, error.reason, payload)
            raise ProposalRejected(error.reason, event_id) from error

    def _commit(
        self, proposal: IngestionProposal, computed_hash: str
    ) -> IngestionResult:
        with self._session_factory.begin() as session:
            task = session.scalar(
                select(Task)
                .where(Task.id == proposal.task_id)
                .with_for_update()
            )
            if task is None:
                raise TaskNotFound(f"Task {proposal.task_id} does not exist")

            if proposal.claimed_content_hash != computed_hash:
                raise IngestionValidationError("content_hash_mismatch")
            team, policy = self._validate_task_and_team(session, task)
            self._validate_fetched_at(proposal.fetched_at)

            prior_outcome = self._find_task_outcome(session, task.id)
            if prior_outcome is not None:
                event, signal_id, snapshot_ref = prior_outcome
                if not self._same_identity(event.payload, proposal, computed_hash):
                    raise IngestionValidationError("task_outcome_conflict")
                signal = session.get(Signal, signal_id)
                if (
                    signal is None
                    or signal.origin_url != proposal.origin_url
                    or signal.source_type != proposal.source_type
                    or signal.content_hash != computed_hash
                ):
                    raise RuntimeError("recorded_ingestion_outcome_corrupt")
                self._verify_signal_snapshot(signal, proposal.content)
                return IngestionResult(
                    outcome="replayed",
                    signal_id=signal_id,
                    snapshot_ref=snapshot_ref,
                    event_id=event.id,
                )

            if not self._source_is_configured(policy.rules, proposal):
                raise IngestionValidationError("source_not_configured")
            if not self._has_kernel_scope(task.task_type, "Snapshot"):
                raise IngestionValidationError("snapshot_scope_violation")
            if not self._has_kernel_scope(task.task_type, "Event"):
                raise IngestionValidationError("event_scope_violation")

            prior_signal = session.scalar(
                select(Signal).where(
                    Signal.origin_url == proposal.origin_url,
                    Signal.content_hash == computed_hash,
                )
            )
            if prior_signal is not None:
                self._verify_signal_snapshot(prior_signal, proposal.content)
                event = self._add_event(
                    session,
                    task.id,
                    "fetch_no_change",
                    self._outcome_payload(proposal, computed_hash, prior_signal),
                )
                session.flush()
                return IngestionResult(
                    outcome="fetch_no_change",
                    signal_id=prior_signal.id,
                    snapshot_ref=prior_signal.snapshot_ref,
                    event_id=event.id,
                )

            snapshot_ref, stored_hash = self._snapshot_store.put(proposal.content)
            signal_id = uuid4()
            inserted_id = session.scalar(
                insert(Signal)
                .values(
                    id=signal_id,
                    domain=team.domain,
                    source_type=proposal.source_type,
                    origin_url=proposal.origin_url,
                    fetched_at=proposal.fetched_at,
                    content_hash=stored_hash,
                    snapshot_ref=snapshot_ref,
                )
                .on_conflict_do_nothing(
                    constraint="uq_signals_origin_content_hash"
                )
                .returning(Signal.id)
            )
            if inserted_id is None:
                winning_signal = session.scalar(
                    select(Signal).where(
                        Signal.origin_url == proposal.origin_url,
                        Signal.content_hash == computed_hash,
                    )
                )
                if winning_signal is None:
                    raise RuntimeError("signal_unique_conflict_without_winner")
                self._verify_signal_snapshot(winning_signal, proposal.content)
                event = self._add_event(
                    session,
                    task.id,
                    "fetch_no_change",
                    self._outcome_payload(proposal, computed_hash, winning_signal),
                )
                session.flush()
                return IngestionResult(
                    outcome="fetch_no_change",
                    signal_id=winning_signal.id,
                    snapshot_ref=winning_signal.snapshot_ref,
                    event_id=event.id,
                )

            session.flush()
            signal = session.get(Signal, inserted_id)
            if signal is None:
                raise RuntimeError("inserted_signal_not_found")
            event = self._add_event(
                session,
                task.id,
                "signal_ingested",
                self._outcome_payload(proposal, computed_hash, signal),
            )
            session.flush()
            return IngestionResult(
                outcome="signal_ingested",
                signal_id=signal.id,
                snapshot_ref=signal.snapshot_ref,
                event_id=event.id,
            )

    def _validate_task_and_team(
        self, session: Session, task: Task
    ) -> tuple[Team, TeamPolicy]:
        if task.task_type != "ingest_source":
            raise IngestionValidationError("wrong_task_type")
        if task.status != "running":
            raise IngestionValidationError("task_not_running")
        if task.allowed_writes != ["Signal"]:
            raise IngestionValidationError("write_scope_violation")
        if not self._has_kernel_scope(task.task_type, "Snapshot"):
            raise IngestionValidationError("snapshot_scope_violation")
        if not self._has_kernel_scope(task.task_type, "Event"):
            raise IngestionValidationError("event_scope_violation")
        if not self._budget_allows_zero_usage(task.budget):
            raise IngestionValidationError("invalid_task_budget")

        team = session.scalar(
            select(Team)
            .where(Team.id == task.team_id)
            .with_for_update(read=True)
        )
        if team is None:
            raise IngestionValidationError("team_not_found")
        if team.status != "active":
            raise IngestionValidationError("team_not_active")
        policy = session.scalar(
            select(TeamPolicy)
            .where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
            .with_for_update(read=True)
        )
        if policy is None:
            raise IngestionValidationError("team_policy_missing")
        return team, policy

    @staticmethod
    def _budget_allows_zero_usage(budget: dict[str, Any]) -> bool:
        if not isinstance(budget, dict):
            return False
        tool_calls = budget.get("max_tool_calls")
        cost = budget.get("max_cost_usd")
        deadline = budget.get("deadline_seconds")
        return (
            isinstance(tool_calls, int)
            and not isinstance(tool_calls, bool)
            and tool_calls >= 0
            and isinstance(cost, (int, float))
            and not isinstance(cost, bool)
            and math.isfinite(cost)
            and cost >= 0
            and isinstance(deadline, int)
            and not isinstance(deadline, bool)
            and deadline > 0
        )

    @staticmethod
    def _source_is_configured(
        rules: dict[str, Any], proposal: IngestionProposal
    ) -> bool:
        if not isinstance(rules, dict):
            return False
        sources = rules.get("sources")
        return isinstance(sources, list) and any(
            isinstance(source, dict)
            and source.get("origin_url") == proposal.origin_url
            and source.get("source_type") == proposal.source_type
            for source in sources
        )

    @staticmethod
    def _validate_fetched_at(fetched_at: datetime) -> None:
        if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
            raise IngestionValidationError("fetched_at_not_timezone_aware")

    @staticmethod
    def _has_kernel_scope(task_type: str, entity_kind: str) -> bool:
        return task_type == "ingest_source" and entity_kind in {
            "Snapshot",
            "Event",
        }

    def _find_task_outcome(
        self, session: Session, task_id: UUID
    ) -> tuple[Event, UUID, str] | None:
        events = session.scalars(
            select(Event)
            .where(
                Event.task_id == task_id,
                Event.type.in_(("signal_ingested", "fetch_no_change")),
            )
            .order_by(Event.created_at)
        )
        for event in events:
            payload = event.payload
            signal_id = payload.get("signal_id")
            snapshot_ref = payload.get("snapshot_ref")
            if isinstance(signal_id, str) and isinstance(snapshot_ref, str):
                signal = session.get(Signal, UUID(signal_id))
                if signal is None or signal.snapshot_ref != snapshot_ref:
                    raise RuntimeError("recorded_ingestion_outcome_corrupt")
                return event, signal.id, signal.snapshot_ref
        return None

    @staticmethod
    def _same_identity(
        payload: dict[str, Any],
        proposal: IngestionProposal,
        computed_hash: str,
    ) -> bool:
        return (
            payload.get("origin_url") == proposal.origin_url
            and payload.get("source_type") == proposal.source_type
            and payload.get("content_hash") == computed_hash
        )

    def _verify_signal_snapshot(self, signal: Signal, content: bytes) -> None:
        stored_content = self._snapshot_store.read(signal.snapshot_ref)
        if stored_content != content or signal.content_hash != (
            f"sha256:{hashlib.sha256(content).hexdigest()}"
        ):
            raise RuntimeError("stored_signal_snapshot_mismatch")

    @staticmethod
    def _outcome_payload(
        proposal: IngestionProposal, content_hash: str, signal: Signal
    ) -> dict[str, Any]:
        return {
            "origin_url": proposal.origin_url,
            "source_type": proposal.source_type,
            "content_hash": content_hash,
            "signal_id": str(signal.id),
            "snapshot_ref": signal.snapshot_ref,
        }

    def _add_event(
        self,
        session: Session,
        task_id: UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> Event:
        task = session.get(Task, task_id)
        if task is None or task.task_type not in _EVENT_K_TASK_TYPES:
            raise EventScopeViolation("event_scope_violation")
        if event_type not in {
            "signal_ingested",
            "fetch_no_change",
            "proposal_rejected",
        }:
            raise EventScopeViolation("event_type_outside_k1_scope")
        event = Event(
            id=uuid4(),
            task_id=task_id,
            type=event_type,
            payload=payload,
            created_at=datetime.now(timezone.utc),
        )
        session.add(event)
        return event

    def _record_rejection(
        self, task_id: UUID, reason: str, payload: dict[str, Any]
    ) -> UUID:
        with self._session_factory.begin() as session:
            task = session.scalar(
                select(Task).where(Task.id == task_id).with_for_update()
            )
            if task is None:
                raise TaskNotFound(f"Task {task_id} does not exist")
            event = self._add_event(
                session,
                task_id,
                "proposal_rejected",
                {"reason": reason, **payload},
            )
            session.flush()
            return event.id
