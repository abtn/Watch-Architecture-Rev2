"""Operator-reviewed canonical LearningChange decisions for R6-F."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from json import dumps, loads
from typing import Literal
from unicodedata import category
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.experience_distiller import (
    ExperienceDistiller,
    ExperienceDistillerError,
)
from core.models import (
    Event,
    KnowledgeItem,
    LearningChange,
    Outcome,
    Task,
    Team,
    TeamPolicy,
)
from core.objectives import ObjectiveService, TaskNotFound
from core.operator_application import (
    TrustedOperatorPrincipal,
    _canonical_operator_identity,
    _require_team_grant,
)
from core.snapshot_store import SnapshotIntegrityError, SnapshotStore
from core.task_runtime import (
    TaskNotEligible,
    TaskNotFinalizable,
    TaskRuntime,
    TerminalObservation,
)


Decision = Literal["accept", "reject"]
_DECISION_EVENT_TYPES = ("learning_change_accepted", "learning_change_rejected")
_REQUEST_EVENT_TYPE = "operator_task_requested"
_TASK_TYPE = "approve_learning_change"
_ALLOWED_WRITES = ["LearningChange", "KnowledgeItem"]


class LearningCommitError(ValueError):
    """A canonical learning decision failed validation or conflicted."""


class LearningCommitConflict(LearningCommitError):
    """A prior or concurrent decision conflicts with this approval Task."""


class LearningCommitCorrupt(LearningCommitError):
    """Durable decision, proposal, or Task evidence is inconsistent."""


@dataclass(frozen=True)
class LearningCommitResult:
    task_id: UUID
    attempt_count: int
    learning_change_id: UUID
    decision: Decision
    status: str
    operator_id: str
    knowledge_item_id: UUID | None
    committed_at: datetime
    replayed: bool = False


class LearningCommitService:
    """Validate and atomically accept/reject a create-only LearningChange.

    The business decision and its Event commit together. TaskRuntime remains
    responsible for the separate terminal Task/Outcome transaction.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store
        # Evidence-pack rebuilding is read-only and does not require a provider.
        self._evidence_validator = ExperienceDistiller(
            session_factory, snapshot_store, provider=None
        )

    def decide(
        self,
        task_id: UUID,
        attempt: int,
        principal: TrustedOperatorPrincipal,
    ) -> LearningCommitResult:
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise LearningCommitError("invalid_attempt")
        try:
            operator_id = _canonical_operator_identity(principal)
        except (TypeError, ValueError) as error:
            raise LearningCommitError("trusted_operator_principal_invalid") from error

        with self._session_factory.begin() as session:
            task = ObjectiveService._lock_task(session, task_id)
            if task is None:
                raise TaskNotFound(f"Task {task_id} does not exist")
            if (
                task.task_type != _TASK_TYPE
                or task.status != "running"
                or task.attempt_count != attempt
                or task.allowed_writes != _ALLOWED_WRITES
                or task.objective_id is not None
                or task.plan_id is not None
                or task.plan_action_id is not None
                or task.completed_at is not None
                or task.max_attempts != 3
                or task.budget != {"max_tool_calls": 0, "max_cost_usd": 0.0}
            ):
                raise LearningCommitError("approval_task_not_eligible")

            try:
                TaskRuntime._validate_operator_admission(session, task)
            except TaskNotEligible as error:
                raise LearningCommitCorrupt(str(error)) from error

            request_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == _REQUEST_EVENT_TYPE,
                    )
                )
            )
            if len(request_events) != 1:
                raise LearningCommitCorrupt("operator_request_event_invalid")
            request_payload = request_events[0].payload
            if not isinstance(request_payload, dict):
                raise LearningCommitCorrupt("operator_request_event_invalid")

            learning_change_id_value = request_payload.get("learning_change_id")
            try:
                learning_change_id = UUID(learning_change_id_value)
            except (TypeError, ValueError) as error:
                raise LearningCommitCorrupt(
                    "operator_request_target_invalid"
                ) from error
            if str(learning_change_id) != learning_change_id_value:
                raise LearningCommitCorrupt("operator_request_target_invalid")

            decision_value = request_payload.get("decision")
            if decision_value not in ("accept", "reject"):
                raise LearningCommitCorrupt("operator_request_decision_invalid")
            decision: Decision = decision_value
            rejection_reason = request_payload.get("rejection_reason")
            if decision == "accept" and rejection_reason is not None:
                raise LearningCommitCorrupt("operator_request_reason_invalid")
            if decision == "reject" and (
                not isinstance(rejection_reason, str)
                or not rejection_reason
                or rejection_reason != rejection_reason.strip()
            ):
                raise LearningCommitCorrupt("operator_request_reason_invalid")
            stored_operator_id = request_payload.get("operator_id")
            if not isinstance(stored_operator_id, str) or len(stored_operator_id) > 255:
                raise LearningCommitCorrupt("operator_request_identity_invalid")
            try:
                stored_identity = loads(stored_operator_id)
            except (TypeError, ValueError) as error:
                raise LearningCommitCorrupt(
                    "operator_request_identity_invalid"
                ) from error
            if (
                not isinstance(stored_identity, dict)
                or set(stored_identity) != {"iss", "sub"}
                or any(
                    not isinstance(stored_identity.get(field), str)
                    or not stored_identity[field]
                    or stored_identity[field] != stored_identity[field].strip()
                    or any(
                        category(character) == "Cc"
                        for character in stored_identity[field]
                    )
                    for field in ("iss", "sub")
                )
            ):
                raise LearningCommitCorrupt("operator_request_identity_invalid")
            canonical_stored_identity = dumps(
                {"iss": stored_identity["iss"], "sub": stored_identity["sub"]},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            if (
                canonical_stored_identity != stored_operator_id
                or stored_operator_id != operator_id
            ):
                raise LearningCommitError("operator_identity_mismatch")

            try:
                _require_team_grant(principal, task.team_id)
            except ValueError as error:
                raise LearningCommitError("operator_not_authorized") from error

            learning_change = session.scalar(
                select(LearningChange)
                .where(
                    LearningChange.id == learning_change_id,
                    LearningChange.team_id == task.team_id,
                )
                .with_for_update()
            )
            if learning_change is None:
                raise LearningCommitCorrupt("learning_change_not_found_for_task_team")

            # A committed decision by this exact Task is the only replay path.
            # A second approval Task may not overwrite or reinterpret it.
            if learning_change.status in {"accepted", "rejected"}:
                return self._replay_decision(
                    session,
                    task,
                    learning_change,
                    decision,
                    operator_id,
                    rejection_reason,
                )
            if learning_change.status != "proposed":
                raise LearningCommitConflict("learning_change_not_proposed")
            if (
                learning_change.target_kind != "knowledge_item"
                or learning_change.operation != "create"
                or learning_change.target_id is not None
                or learning_change.committed_by_task_id is not None
            ):
                raise LearningCommitError("only_knowledge_item_create_is_supported")

            team = session.scalar(
                select(Team)
                .where(Team.id == task.team_id)
                .with_for_update()
            )
            if team is None or team.status != "active":
                raise LearningCommitError("team_not_active")

            current_policy = session.scalar(
                select(TeamPolicy)
                .where(TeamPolicy.team_id == team.id)
                .order_by(TeamPolicy.version.desc())
                .limit(1)
                .with_for_update(read=True)
            )
            if current_policy is None or current_policy.version != task.policy_version:
                raise LearningCommitError("approval_task_policy_is_stale")

            current_start_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == "task_started",
                        Event.payload["attempt_count"].as_integer() == attempt,
                    )
                )
            )
            if (
                len(current_start_events) != 1
                or current_start_events[0].payload
                != {
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": attempt,
                }
            ):
                raise LearningCommitCorrupt("approval_task_start_event_invalid")

            terminal_outcomes = list(
                session.scalars(
                    select(Outcome).where(
                        Outcome.recorded_by_task_id == task.id,
                        Outcome.outcome_type == "task_execution",
                    )
                )
            )
            terminal_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type.in_(("task_completed", "task_failed")),
                    )
                )
            )
            if terminal_outcomes or terminal_events:
                raise LearningCommitCorrupt("approval_task_terminal_state_exists")

            try:
                draft, pack = self._evidence_validator.validate_learning_change(
                    session, learning_change
                )
            except ExperienceDistillerError as error:
                raise LearningCommitError(error.reason) from error

            self._validate_proposer_terminal(
                session, learning_change, pack.task_id
            )
            committed_at = datetime.now(timezone.utc)

            knowledge_item_id: UUID | None = None
            committed_state: dict[str, object] | None = None
            if decision == "accept":
                prior_items = list(
                    session.scalars(
                        select(KnowledgeItem).where(
                            KnowledgeItem.origin_learning_change_id
                            == learning_change.id
                        )
                    )
                )
                if prior_items:
                    raise LearningCommitCorrupt(
                        "knowledge_item_exists_for_uncommitted_learning_change"
                    )

                knowledge_item_id = uuid4()
                confidence = Decimal(str(draft.confidence)).quantize(
                    Decimal("0.001")
                )
                applicability = draft.applicability.model_dump(mode="json")
                committed_state = {
                    "id": str(knowledge_item_id),
                    "team_id": str(team.id),
                    "kind": draft.kind,
                    "title": draft.title,
                    "statement": draft.statement,
                    "body": draft.body,
                    "applicability": applicability,
                    "preconditions": draft.preconditions,
                    "assumptions": draft.assumptions,
                    "limitations": draft.limitations,
                    "non_applicability": draft.non_applicability,
                    "failure_modes": draft.failure_modes,
                    "known_counterexamples": draft.known_counterexamples,
                    "missing_information": draft.missing_information,
                    "uncertainty": draft.uncertainty,
                    "confidence": str(confidence),
                    "status": "active",
                    "version": 1,
                    "last_validated_at": None,
                    "review_after": None,
                    "origin_learning_change_id": str(learning_change.id),
                }
                session.add(
                    KnowledgeItem(
                        id=knowledge_item_id,
                        team_id=team.id,
                        kind=draft.kind,
                        title=draft.title,
                        statement=draft.statement,
                        body=draft.body,
                        applicability=applicability,
                        preconditions=draft.preconditions,
                        assumptions=draft.assumptions,
                        limitations=draft.limitations,
                        non_applicability=draft.non_applicability,
                        failure_modes=draft.failure_modes,
                        known_counterexamples=draft.known_counterexamples,
                        missing_information=draft.missing_information,
                        uncertainty=draft.uncertainty,
                        confidence=confidence,
                        status="active",
                        version=1,
                        last_validated_at=None,
                        review_after=None,
                        origin_learning_change_id=learning_change.id,
                    )
                )

            learning_change.status = "accepted" if decision == "accept" else "rejected"
            learning_change.previous_state = None
            learning_change.committed_state = committed_state
            learning_change.committed_by_task_id = task.id
            learning_change.operator_id = operator_id
            learning_change.decision_reason = rejection_reason
            learning_change.committed_at = committed_at

            event_type = (
                "learning_change_accepted"
                if decision == "accept"
                else "learning_change_rejected"
            )
            event_payload: dict[str, object] = {
                "schema_version": 1,
                "learning_change_id": str(learning_change.id),
                "operation": "create",
                "decision": decision,
                "operator_id": operator_id,
                "approval_task_id": str(task.id),
                "attempt_count": attempt,
                "evidence_basis_hash": learning_change.evidence_basis_hash,
                "proposal_hash": str(learning_change.proposed_state["proposal_hash"]),
                "committed_at": committed_at.isoformat(),
            }
            if knowledge_item_id is not None:
                event_payload["knowledge_item_id"] = str(knowledge_item_id)
                event_payload["knowledge_item_version"] = 1
            if rejection_reason is not None:
                event_payload["reason"] = rejection_reason

            decision_event = Event(
                id=uuid4(),
                task_id=task.id,
                type=event_type,
                payload=event_payload,
                created_at=committed_at,
            )
            session.add(decision_event)
            session.flush()

            return LearningCommitResult(
                task_id=task.id,
                attempt_count=attempt,
                learning_change_id=learning_change.id,
                decision=decision,
                status=learning_change.status,
                operator_id=operator_id,
                knowledge_item_id=knowledge_item_id,
                committed_at=committed_at,
            )

    def _validate_proposer_terminal(
        self,
        session: Session,
        learning_change: LearningChange,
        proposer_task_id: UUID,
    ) -> None:
        proposer = session.scalar(
            select(Task).where(Task.id == proposer_task_id).with_for_update(read=True)
        )
        if proposer is None or proposer.team_id != learning_change.team_id:
            raise LearningCommitCorrupt("learning_change_proposer_task_invalid")
        if (
            proposer.status != "done"
            or proposer.completed_at is None
            or proposer.attempt_count < 1
        ):
            raise LearningCommitCorrupt("learning_change_proposer_not_done")

        try:
            TaskRuntime._validate_learning_change_result(
                session,
                proposer,
                TerminalObservation(
                    task_id=proposer.id,
                    attempt=proposer.attempt_count,
                    result_category="success_learning_change_proposed",
                    observed_at=proposer.completed_at,
                    learning_change_id=learning_change.id,
                ),
            )
        except TaskNotFinalizable as error:
            raise LearningCommitCorrupt(str(error)) from error

        outcomes = list(
            session.scalars(
                select(Outcome).where(
                    Outcome.recorded_by_task_id == proposer.id,
                    Outcome.outcome_type == "task_execution",
                )
            )
        )
        if len(outcomes) != 1:
            raise LearningCommitCorrupt("learning_change_proposer_outcome_invalid")
        outcome = outcomes[0]
        if (
            outcome.team_id != learning_change.team_id
            or outcome.subject_kind != "task"
            or outcome.subject_id != proposer.id
            or outcome.observation_snapshot_ref is None
            or outcome.observation_hash is None
            or outcome.observed_at is None
        ):
            raise LearningCommitCorrupt("learning_change_proposer_outcome_invalid")
        try:
            snapshot_bytes = self._snapshot_store.read(
                outcome.observation_snapshot_ref
            )
        except SnapshotIntegrityError as error:
            raise LearningCommitCorrupt(str(error)) from error
        if (
            "sha256:" + sha256(snapshot_bytes).hexdigest()
            != outcome.observation_hash
        ):
            raise LearningCommitCorrupt(
                "learning_change_proposer_snapshot_hash_mismatch"
            )

        completed_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == proposer.id,
                    Event.type == "task_completed",
                )
            )
        )
        if (
            len(completed_events) != 1
            or completed_events[0].payload.get("to_status") != "done"
            or completed_events[0].payload.get("attempt_count")
            != proposer.attempt_count
            or completed_events[0].payload.get("result_category")
            != "success_learning_change_proposed"
            or completed_events[0].payload.get("learning_change_id")
            != str(learning_change.id)
            or completed_events[0].payload.get("outcome_id") != str(outcome.id)
            or completed_events[0].payload.get("observation_snapshot_ref")
            != outcome.observation_snapshot_ref
            or completed_events[0].payload.get("observation_hash")
            != outcome.observation_hash
        ):
            raise LearningCommitCorrupt(
                "learning_change_proposer_terminal_event_invalid"
            )

    def _replay_decision(
        self,
        session: Session,
        task: Task,
        learning_change: LearningChange,
        requested_decision: Decision,
        operator_id: str,
        rejection_reason: object,
    ) -> LearningCommitResult:
        if (
            learning_change.committed_by_task_id != task.id
            or learning_change.operator_id != operator_id
        ):
            raise LearningCommitConflict("learning_change_already_decided")

        recorded_decision: Decision = (
            "accept" if learning_change.status == "accepted" else "reject"
        )
        if (
            recorded_decision != requested_decision
            or learning_change.decision_reason != rejection_reason
        ):
            raise LearningCommitConflict("learning_change_decision_request_conflict")

        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type.in_(_DECISION_EVENT_TYPES),
                )
            )
        )
        expected_type = (
            "learning_change_accepted"
            if recorded_decision == "accept"
            else "learning_change_rejected"
        )
        if len(events) != 1:
            raise LearningCommitCorrupt("learning_change_decision_event_invalid")
        event = events[0]
        payload = event.payload
        if (
            not isinstance(payload, dict)
            or payload.get("learning_change_id") != str(learning_change.id)
            or payload.get("approval_task_id") != str(task.id)
            or payload.get("decision") != recorded_decision
            or payload.get("operator_id") != operator_id
            or payload.get("evidence_basis_hash") != learning_change.evidence_basis_hash
            or payload.get("proposal_hash")
            != learning_change.proposed_state.get("proposal_hash")
            or payload.get("attempt_count", 0) > task.attempt_count
            or event.type != expected_type
        ):
            raise LearningCommitCorrupt("learning_change_decision_event_mismatch")

        item_id: UUID | None = None
        if recorded_decision == "accept":
            items = list(
                session.scalars(
                    select(KnowledgeItem).where(
                        KnowledgeItem.origin_learning_change_id
                        == learning_change.id
                    )
                )
            )
            if len(items) != 1:
                raise LearningCommitCorrupt(
                    "committed_knowledge_item_missing_or_duplicate"
                )
            item = items[0]
            item_id = item.id
            if (
                item.team_id != learning_change.team_id
                or learning_change.committed_state is None
                or learning_change.committed_state.get("id") != str(item.id)
                or payload.get("knowledge_item_id") != str(item.id)
                or learning_change.committed_state.get("version") != item.version
                or item.version != 1
            ):
                raise LearningCommitCorrupt("committed_knowledge_item_mismatch")
        else:
            if learning_change.committed_state is not None or session.scalar(
                select(KnowledgeItem.id).where(
                    KnowledgeItem.origin_learning_change_id == learning_change.id
                )
            ) is not None:
                raise LearningCommitCorrupt(
                    "rejected_learning_change_has_knowledge_item"
                )

        committed_at = learning_change.committed_at
        if committed_at is None:
            raise LearningCommitCorrupt("learning_change_commit_timestamp_missing")
        return LearningCommitResult(
            task_id=task.id,
            attempt_count=task.attempt_count,
            learning_change_id=learning_change.id,
            decision=recorded_decision,
            status=learning_change.status,
            operator_id=operator_id,
            knowledge_item_id=item_id,
            committed_at=committed_at,
            replayed=True,
        )
