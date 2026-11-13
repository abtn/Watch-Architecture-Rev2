"""Operator-reviewed canonical LearningChange decisions for R6-F."""

from __future__ import annotations  # noqa: I001

import dataclasses
import datetime
import decimal
import hashlib
import typing
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from core.experience_distiller import (
    ExperienceDistiller,
    ExperienceDistillerError,
)
from core.knowledge_quality import (
    KnowledgeQualityAssessmentError,
    require_recorded_assessment,
)
from core.learning_history import (
    KnowledgeHistoryError,
    decode_state_snapshot,
    encode_state_snapshot,
    knowledge_item_content_hash,
    knowledge_item_state,
    reconstruct_knowledge_item_history,
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
import core.operator_application
from core.operator_approval import (
    OperatorApprovalValidationError,
    is_supported_learning_change,
    parse_request_event_payload,
)
from core.policy import InvalidPolicyError, knowledge_item_review_interval_days
from core.snapshot_store import SnapshotIntegrityError, SnapshotStore
from core.task_runtime import (
    TaskNotEligible,
    TaskNotFinalizable,
    TaskRuntime,
    TerminalObservation,
)


Decision = typing.Literal["accept", "reject"]
_DECISION_EVENT_TYPES = ("learning_change_accepted", "learning_change_rejected")
_REQUEST_EVENT_TYPE = "operator_task_requested"
_TASK_TYPE = "approve_learning_change"
_ALLOWED_WRITES = ["LearningChange", "KnowledgeItem"]


def _knowledge_item_cas_statement(
    *,
    item_id: uuid.UUID,
    team_id: uuid.UUID,
    expected_pointer: uuid.UUID,
    expected_version: int,
    values: dict[str, typing.Any],
    require_needs_review: bool = False,
    expected_status: str | None = None,
) -> typing.Any:
    """Build the conditional KnowledgeItem update used by commits and CAS tests."""
    predicates: list[typing.Any] = [
        KnowledgeItem.id == item_id,
        KnowledgeItem.team_id == team_id,
        KnowledgeItem.current_learning_change_id == expected_pointer,
        KnowledgeItem.version == expected_version,
    ]
    if expected_status is not None:
        predicates.append(KnowledgeItem.status == expected_status)
    elif require_needs_review:
        predicates.append(KnowledgeItem.status == "needs_review")
    return (
        update(KnowledgeItem)
        .where(*predicates)
        .values(**values)
        .returning(KnowledgeItem.id)
    )


class LearningCommitError(ValueError):
    """A canonical learning decision failed validation or conflicted."""


class LearningCommitConflict(LearningCommitError):
    """A prior or concurrent decision conflicts with this approval Task."""


class LearningCommitCorrupt(LearningCommitError):
    """Durable decision, proposal, or Task evidence is inconsistent."""


@dataclasses.dataclass(frozen=True)
class LearningCommitResult:
    task_id: uuid.UUID
    attempt_count: int
    learning_change_id: uuid.UUID
    decision: Decision
    status: str
    operator_id: str
    knowledge_item_id: uuid.UUID | None
    committed_at: datetime.datetime
    replayed: bool = False


class LearningCommitService:
    """Validate and atomically decide a create, revise, or revalidate LearningChange.

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
        task_id: uuid.UUID,
        attempt: int,
        principal: core.operator_application.TrustedOperatorPrincipal,
    ) -> LearningCommitResult:
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise LearningCommitError("invalid_attempt")
        try:
            operator_id = (
                core.operator_application._canonical_operator_identity(principal)
            )
        except (TypeError, ValueError) as error:
            raise LearningCommitError("trusted_operator_principal_invalid") from error

        with self._session_factory.begin() as session:
            task = ObjectiveService._lock_task(session, task_id)
            if task is None:
                raise TaskNotFound(f"Task {task_id} does not exist")
            if (
                task.task_type != _TASK_TYPE
                or task.status not in {"running", "done"}
                or (task.completed_at is not None and task.status != "done")
                or task.attempt_count != attempt
                or task.allowed_writes != _ALLOWED_WRITES
                or task.objective_id is not None
                or task.plan_id is not None
                or task.plan_action_id is not None
                or task.max_attempts != 3
                or task.budget != {"max_tool_calls": 0, "max_cost_usd": 0.0}
            ):
                raise LearningCommitError("approval_task_not_eligible")

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

            try:
                approval_request = parse_request_event_payload(
                    request_payload,
                    team_id=task.team_id,
                    policy_version=task.policy_version,
                )
            except OperatorApprovalValidationError as error:
                raise LearningCommitCorrupt(error.reason) from error

            learning_change_id = approval_request.learning_change_id
            decision = approval_request.decision
            rejection_reason = approval_request.rejection_reason
            if approval_request.operator_id != operator_id:
                raise LearningCommitError("operator_identity_mismatch")

            try:
                core.operator_application._require_team_grant(principal, task.team_id)
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

            candidate_team_lock: Team | None = None
            if (
                learning_change.operation == "retire"
                or (
                    learning_change.operation == "create"
                    and "supersedes_item_id" in learning_change.proposed_state
                )
            ):
                candidate_team_lock = session.scalar(
                    select(Team)
                    .where(Team.id == task.team_id)
                    .with_for_update()
                )
                if (
                    candidate_team_lock is None
                    or candidate_team_lock.status != "active"
                ):
                    raise LearningCommitError("team_not_active")

            if approval_request.schema_version == 3:
                from core.knowledge_approval import (
                    KnowledgeApprovalBindingError,
                    build_approval_binding,
                )

                try:
                    expected_binding = build_approval_binding(
                        session,
                        learning_change,
                        operator_id=operator_id,
                        approval_policy_version=task.policy_version,
                        require_assessment=decision == "accept",
                        snapshot_store=self._snapshot_store,
                        session_factory=self._session_factory,
                    )
                except KnowledgeApprovalBindingError as error:
                    if is_supported_learning_change(
                        target_kind=learning_change.target_kind,
                        operation=learning_change.operation,
                        target_id=learning_change.target_id,
                    ):
                        raise LearningCommitCorrupt(str(error)) from error
                    # Operations beyond create/revise remain outside the
                    # approval allowlist. Let the admission guard reject them
                    # even when their assessment is missing or malformed.
                else:
                    if expected_binding != approval_request.approval_binding:
                        raise LearningCommitCorrupt(
                            "operator_approval_binding_invalid"
                        )

            try:
                TaskRuntime._validate_operator_admission(
                    session,
                    task,
                    allow_completed=task.status == "done",
                    snapshot_store=self._snapshot_store,
                    session_factory=self._session_factory,
                )
            except TaskNotEligible as error:
                raise LearningCommitCorrupt(str(error)) from error

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
            if task.status == "done":
                raise LearningCommitCorrupt(
                    "approval_task_completed_without_learning_decision"
                )
            if learning_change.status != "proposed":
                raise LearningCommitConflict("learning_change_not_proposed")
            if (
                not is_supported_learning_change(
                    target_kind=learning_change.target_kind,
                    operation=learning_change.operation,
                    target_id=learning_change.target_id,
                )
                or learning_change.committed_by_task_id is not None
            ):
                raise LearningCommitError(
                    "only_knowledge_item_create_revise_or_revalidate_is_supported"
                )

            team = candidate_team_lock or session.scalar(
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

            draft = None
            pack = None
            if learning_change.operation in {"revalidate", "retire"}:
                self._validate_proposer_terminal(
                    session,
                    learning_change,
                    learning_change.proposed_by_task_id,
                )
            else:
                try:
                    draft, pack = self._evidence_validator.validate_learning_change(
                        session, learning_change
                    )
                except ExperienceDistillerError as error:
                    raise LearningCommitError(error.reason) from error
                self._validate_proposer_terminal(
                    session, learning_change, pack.task_id
                )

            quality_assessment_id: str | None = None
            quality_assessment_hash: str | None = None
            revalidation_assessment_id: str | None = None
            revalidation_assessment_hash: str | None = None
            lifecycle_assessment_id: str | None = None
            lifecycle_assessment_hash: str | None = None
            if decision == "accept" and learning_change.operation == "revalidate":
                from core import knowledge_revalidation as revalidation

                try:
                    revalidation_assessment = revalidation.require_recorded_assessment(
                        session,
                        learning_change,
                        self._snapshot_store,
                        self._session_factory,
                        require_task_done=True,
                        require_current=True,
                    )
                except revalidation.KnowledgeRevalidationAssessmentError as error:
                    raise LearningCommitError(str(error)) from error
                approval_binding = approval_request.approval_binding
                if (
                    approval_binding is None
                    or approval_binding.get("assessment_type")
                    != "knowledge_revalidation"
                    or approval_binding.get("assessment_id")
                    != str(revalidation_assessment.id)
                    or approval_binding.get("assessment_payload_hash")
                    != revalidation_assessment.payload_hash
                    or approval_request.quality_assessment_id is not None
                    or approval_request.quality_assessment_hash is not None
                ):
                    raise LearningCommitError(
                        "operator_revalidation_assessment_binding_invalid"
                    )
                revalidation_assessment_id = str(revalidation_assessment.id)
                revalidation_assessment_hash = revalidation_assessment.payload_hash
            elif decision == "accept" and learning_change.operation == "retire":
                from core.knowledge_lifecycle import (
                    KnowledgeLifecycleAssessmentError,
                )
                from core.knowledge_lifecycle import (
                    require_recorded_assessment as require_lifecycle_assessment,
                )

                try:
                    lifecycle_assessment = require_lifecycle_assessment(
                        session,
                        learning_change,
                        self._snapshot_store,
                        self._session_factory,
                        require_task_done=True,
                        require_current=True,
                    )
                except KnowledgeLifecycleAssessmentError as error:
                    raise LearningCommitError(str(error)) from error
                approval_binding = approval_request.approval_binding
                if (
                    approval_binding is None
                    or approval_binding.get("assessment_type") != "knowledge_lifecycle"
                    or approval_binding.get("assessment_id")
                    != str(lifecycle_assessment.id)
                    or approval_binding.get("assessment_payload_hash")
                    != lifecycle_assessment.payload_hash
                    or approval_request.quality_assessment_id is not None
                    or approval_request.quality_assessment_hash is not None
                    or lifecycle_assessment.assessment_result != "eligible"
                ):
                    raise LearningCommitError(
                        "operator_lifecycle_assessment_binding_invalid"
                    )
                lifecycle_assessment_id = str(lifecycle_assessment.id)
                lifecycle_assessment_hash = lifecycle_assessment.payload_hash
            elif decision == "accept":
                try:
                    quality_assessment = require_recorded_assessment(
                        session, learning_change, require_task_done=True
                    )
                except KnowledgeQualityAssessmentError as error:
                    raise LearningCommitError(str(error)) from error
                quality_assessment_id = (
                    str(approval_request.quality_assessment_id)
                    if approval_request.quality_assessment_id is not None
                    else None
                )
                quality_assessment_hash = approval_request.quality_assessment_hash
                if (
                    quality_assessment_id != str(quality_assessment.id)
                    or quality_assessment_hash
                    != quality_assessment.assessment_payload_hash
                ):
                    raise LearningCommitError(
                        "operator_quality_assessment_binding_invalid"
                    )
            elif (
                approval_request.quality_assessment_id is not None
                or approval_request.quality_assessment_hash is not None
            ):
                raise LearningCommitError(
                    "operator_quality_assessment_not_allowed_for_rejection"
                )
            committed_at = datetime.datetime.now(datetime.timezone.utc)
            review_after: datetime.datetime | None = None
            if decision == "accept" and learning_change.operation != "retire":
                raw_predecessor_id = learning_change.proposed_state.get(
                    "supersedes_item_id"
                )
                if (
                    learning_change.operation == "create"
                    and raw_predecessor_id is not None
                ):
                    try:
                        predecessor_id = uuid.UUID(raw_predecessor_id)
                    except (TypeError, ValueError) as error:
                        raise LearningCommitCorrupt(
                            "successor_predecessor_id_invalid"
                        ) from error
                    predecessor = session.scalar(
                        select(KnowledgeItem)
                        .where(
                            KnowledgeItem.id == predecessor_id,
                            KnowledgeItem.team_id == task.team_id,
                        )
                        .with_for_update()
                    )
                    if (
                        predecessor is None
                        or predecessor.status != "active"
                        or predecessor.superseded_by_id is not None
                        or predecessor.review_after is None
                        or predecessor.review_after <= committed_at
                    ):
                        raise LearningCommitError(
                            "successor_predecessor_not_d7_eligible"
                        )
                try:
                    interval_days = knowledge_item_review_interval_days(
                        current_policy.rules, current_policy.schema_version
                    )
                except InvalidPolicyError as error:
                    raise LearningCommitError(str(error)) from error
                if interval_days is not None:
                    review_after = committed_at + datetime.timedelta(days=interval_days)
                if (
                    learning_change.operation == "create"
                    and learning_change.proposed_state.get("supersedes_item_id")
                    is not None
                    and (review_after is None or review_after <= committed_at)
                ):
                    raise LearningCommitError(
                        "successor_review_interval_required"
                    )

            knowledge_item_id: uuid.UUID | None = None
            knowledge_item_version: int | None = None
            committed_state: dict[str, object] | None = None
            if decision == "accept":
                if learning_change.operation in {"create", "revise"}:
                    if draft is None:
                        raise LearningCommitCorrupt("learning_change_draft_missing")
                    confidence = decimal.Decimal(str(draft.confidence)).quantize(
                        decimal.Decimal("0.001")
                    )
                    applicability = draft.applicability.model_dump(mode="json")
                if learning_change.operation == "create":
                    if draft is None:
                        raise LearningCommitCorrupt("learning_change_draft_missing")
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

                    knowledge_item_id = uuid.uuid4()
                    knowledge_item_version = 1
                    raw_supersedes_item_id = learning_change.proposed_state.get(
                        "supersedes_item_id"
                    )
                    try:
                        supersedes_item_id = (
                            uuid.UUID(raw_supersedes_item_id)
                            if raw_supersedes_item_id is not None
                            else None
                        )
                    except (TypeError, ValueError) as error:
                        raise LearningCommitCorrupt(
                            "successor_predecessor_id_invalid"
                        ) from error
                    if (
                        raw_supersedes_item_id is not None
                        and str(supersedes_item_id) != raw_supersedes_item_id
                    ):
                        raise LearningCommitCorrupt(
                            "successor_predecessor_id_invalid"
                        )
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
                        "review_after": (
                            review_after.isoformat()
                            if review_after is not None
                            else None
                        ),
                        "origin_learning_change_id": str(learning_change.id),
                        "current_learning_change_id": str(learning_change.id),
                        "supersedes_item_id": (
                            str(supersedes_item_id)
                            if supersedes_item_id is not None
                            else None
                        ),
                        "superseded_by_id": None,
                    }
                    committed_state = encode_state_snapshot(committed_state)
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
                            review_after=review_after,
                            origin_learning_change_id=learning_change.id,
                            current_learning_change_id=learning_change.id,
                            supersedes_item_id=supersedes_item_id,
                            superseded_by_id=None,
                        )
                    )
                elif learning_change.operation == "revise":
                    if draft is None:
                        raise LearningCommitCorrupt("learning_change_draft_missing")
                    target = session.scalar(
                        select(KnowledgeItem)
                        .where(
                            KnowledgeItem.id == learning_change.target_id,
                            KnowledgeItem.team_id == learning_change.team_id,
                        )
                        .with_for_update()
                    )
                    if target is None:
                        raise LearningCommitConflict("revision_target_missing")
                    previous = learning_change.previous_state
                    if not isinstance(previous, dict) or not isinstance(
                        previous.get("state"), dict
                    ):
                        raise LearningCommitCorrupt(
                            "revision_target_snapshot_invalid"
                        )
                    previous_state = previous["state"]
                    if (
                        knowledge_item_state(target) != previous_state
                        or target.current_learning_change_id
                        != uuid.UUID(previous_state["current_learning_change_id"])
                        or target.version != previous_state["version"]
                    ):
                        raise LearningCommitConflict(
                            "revision_target_compare_and_set_failed"
                        )

                    next_version = target.version + 1
                    knowledge_item_version = next_version
                    committed_values = {
                        "id": str(target.id),
                        "team_id": str(target.team_id),
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
                        "status": target.status,
                        "version": next_version,
                        "last_validated_at": None,
                        "review_after": (
                            review_after.isoformat()
                            if review_after is not None
                            else None
                        ),
                        "origin_learning_change_id": str(
                            target.origin_learning_change_id
                        ),
                        "current_learning_change_id": str(learning_change.id),
                        "supersedes_item_id": (
                            str(target.supersedes_item_id)
                            if target.supersedes_item_id is not None
                            else None
                        ),
                        "superseded_by_id": (
                            str(target.superseded_by_id)
                            if target.superseded_by_id is not None
                            else None
                        ),
                    }
                    committed_state = encode_state_snapshot(committed_values)
                    cas_id = session.execute(
                        _knowledge_item_cas_statement(
                            item_id=target.id,
                            team_id=target.team_id,
                            expected_pointer=uuid.UUID(
                                previous_state["current_learning_change_id"]
                            ),
                            expected_version=previous_state["version"],
                            values={
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
                                "confidence": confidence,
                                "version": next_version,
                                "last_validated_at": None,
                                "review_after": review_after,
                                "current_learning_change_id": learning_change.id,
                            },
                        ),
                        execution_options={"synchronize_session": False},
                    ).scalar_one_or_none()
                    if cas_id != target.id:
                        raise LearningCommitConflict(
                            "revision_target_compare_and_set_failed"
                        )
                    session.refresh(target)
                    knowledge_item_id = target.id
                elif learning_change.operation == "revalidate":
                    target = session.scalar(
                        select(KnowledgeItem)
                        .where(
                            KnowledgeItem.id == learning_change.target_id,
                            KnowledgeItem.team_id == learning_change.team_id,
                        )
                        .with_for_update()
                    )
                    if target is None:
                        raise LearningCommitConflict("revalidation_target_missing")
                    previous = learning_change.previous_state
                    if (
                        not isinstance(previous, dict)
                        or not isinstance(previous.get("state"), dict)
                    ):
                        raise LearningCommitCorrupt(
                            "revalidation_target_snapshot_invalid"
                        )
                    try:
                        pointer = uuid.UUID(
                            previous["state"]["current_learning_change_id"]
                        )
                        previous_state, reconstructed = decode_state_snapshot(
                            previous,
                            learning_change_id=pointer,
                            operation="revalidate",
                            allow_legacy_root=False,
                        )
                        from core.knowledge_revalidation import (
                            _target_state_from_proposal,
                        )

                        target_state, _, _ = _target_state_from_proposal(
                            learning_change, target, require_current=True
                        )
                    except (KnowledgeHistoryError, ValueError, TypeError) as error:
                        raise LearningCommitConflict(
                            "revalidation_target_compare_and_set_failed"
                        ) from error
                    if reconstructed or target_state != previous_state:
                        raise LearningCommitConflict(
                            "revalidation_target_compare_and_set_failed"
                        )

                    committed_values = dict(target_state)
                    committed_values.update(
                        {
                            "status": "active",
                            "last_validated_at": committed_at.isoformat(),
                            "review_after": (
                                review_after.isoformat()
                                if review_after is not None
                                else None
                            ),
                            "current_learning_change_id": str(learning_change.id),
                        }
                    )
                    committed_state = encode_state_snapshot(committed_values)
                    cas_id = session.execute(
                        _knowledge_item_cas_statement(
                            item_id=target.id,
                            team_id=target.team_id,
                            expected_pointer=pointer,
                            expected_version=previous_state["version"],
                            require_needs_review=True,
                            values={
                                "status": "active",
                                "last_validated_at": committed_at,
                                "review_after": review_after,
                                "current_learning_change_id": learning_change.id,
                            },
                        ),
                        execution_options={"synchronize_session": False},
                    ).scalar_one_or_none()
                    if cas_id != target.id:
                        raise LearningCommitConflict(
                            "revalidation_target_compare_and_set_failed"
                        )
                    session.refresh(target)
                    knowledge_item_id = target.id
                    knowledge_item_version = target.version
                elif learning_change.operation == "retire":
                    target = session.scalar(
                        select(KnowledgeItem)
                        .where(
                            KnowledgeItem.id == learning_change.target_id,
                            KnowledgeItem.team_id == learning_change.team_id,
                        )
                        .with_for_update()
                    )
                    if target is None:
                        raise LearningCommitConflict("retirement_target_missing")
                    previous = learning_change.previous_state
                    if not isinstance(previous, dict) or not isinstance(
                        previous.get("state"), dict
                    ):
                        raise LearningCommitCorrupt(
                            "retirement_target_snapshot_invalid"
                        )
                    try:
                        pointer = uuid.UUID(
                            previous["state"]["current_learning_change_id"]
                        )
                        previous_state, reconstructed = decode_state_snapshot(
                            previous,
                            learning_change_id=pointer,
                            operation="retire",
                            allow_legacy_root=False,
                        )
                    except (
                        KnowledgeHistoryError,
                        KeyError,
                        TypeError,
                        ValueError,
                    ) as error:
                        raise LearningCommitConflict(
                            "retirement_target_snapshot_invalid"
                        ) from error
                    if reconstructed:
                        raise LearningCommitConflict(
                            "retirement_target_legacy_snapshot"
                        )
                    try:
                        live_state = knowledge_item_state(target)
                        live_content_hash = knowledge_item_content_hash(target)
                    except KnowledgeHistoryError as error:
                        raise LearningCommitConflict(
                            "retirement_target_state_invalid"
                        ) from error

                    if (
                        target.team_id != team.id
                        or target.status not in {"active", "needs_review"}
                        or target.superseded_by_id is not None
                        or live_state != previous_state
                        or target.current_learning_change_id != pointer
                        or target.version != previous_state["version"]
                        or live_content_hash != lifecycle_assessment.target_content_hash
                    ):
                        raise LearningCommitConflict(
                            "retirement_target_compare_and_set_failed"
                        )
                    try:
                        reconstruct_knowledge_item_history(session, target)
                    except KnowledgeHistoryError as error:
                        raise LearningCommitConflict(str(error)) from error
                    committed_values = dict(live_state)
                    committed_values.update(
                        {
                            "status": "retired",
                            "current_learning_change_id": str(learning_change.id),
                        }
                    )
                    committed_state = encode_state_snapshot(committed_values)
                    cas_id = session.execute(
                        _knowledge_item_cas_statement(
                            item_id=target.id,
                            team_id=target.team_id,
                            expected_pointer=pointer,
                            expected_version=previous_state["version"],
                            expected_status=previous_state["status"],
                            values={
                                "status": "retired",
                                "current_learning_change_id": learning_change.id,
                            },
                        ),
                        execution_options={"synchronize_session": False},
                    ).scalar_one_or_none()
                    if cas_id != target.id:
                        raise LearningCommitConflict(
                            "retirement_target_compare_and_set_failed"
                        )
                    session.refresh(target)
                    knowledge_item_id = target.id
                    knowledge_item_version = target.version
                else:
                    raise LearningCommitError("learning_change_operation_not_supported")

            learning_change.status = "accepted" if decision == "accept" else "rejected"
            if learning_change.operation == "create":
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
                "operation": learning_change.operation,
                "decision": decision,
                "operator_id": operator_id,
                "approval_task_id": str(task.id),
                "attempt_count": attempt,
                "evidence_basis_hash": learning_change.evidence_basis_hash,
                "proposal_hash": str(learning_change.proposed_state["proposal_hash"]),
                "committed_at": committed_at.isoformat(),
            }
            if approval_request.schema_version == 3:
                event_payload["schema_version"] = 2
                event_payload["request_fingerprint"] = (
                    approval_request.request_fingerprint
                )
                if approval_request.approval_binding is not None:
                    event_payload["approval_binding"] = (
                        approval_request.approval_binding
                    )
            if knowledge_item_id is not None:
                event_payload["knowledge_item_id"] = str(knowledge_item_id)
                if knowledge_item_version is None:
                    raise LearningCommitCorrupt(
                        "committed_knowledge_item_version_missing"
                    )
                event_payload["knowledge_item_version"] = knowledge_item_version
                if learning_change.operation == "revalidate":
                    event_payload["knowledge_revalidation_assessment_id"] = (
                        revalidation_assessment_id
                    )
                    event_payload["knowledge_revalidation_assessment_hash"] = (
                        revalidation_assessment_hash
                    )
                elif learning_change.operation == "retire":
                    event_payload["knowledge_lifecycle_assessment_id"] = (
                        lifecycle_assessment_id
                    )
                    event_payload["knowledge_lifecycle_assessment_hash"] = (
                        lifecycle_assessment_hash
                    )
                else:
                    event_payload["knowledge_quality_assessment_id"] = (
                        quality_assessment_id
                    )
                    event_payload["knowledge_quality_assessment_hash"] = (
                        quality_assessment_hash
                    )
            if rejection_reason is not None:
                event_payload["reason"] = rejection_reason

            decision_event = Event(
                id=uuid.uuid4(),
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
        proposer_task_id: uuid.UUID,
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
            "sha256:" + hashlib.sha256(snapshot_bytes).hexdigest()
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

    @staticmethod
    def _knowledge_item_state(item: KnowledgeItem) -> dict[str, object]:
        """Return the full canonical state used by versioned history snapshots."""
        return knowledge_item_state(item)

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
        request_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == _REQUEST_EVENT_TYPE,
                )
            )
        )
        if len(request_events) != 1 or not isinstance(request_events[0].payload, dict):
            raise LearningCommitCorrupt("operator_request_event_invalid")
        request_payload = request_events[0].payload
        try:
            approval_request = parse_request_event_payload(
                request_payload,
                team_id=task.team_id,
                policy_version=task.policy_version,
            )
        except OperatorApprovalValidationError as error:
            raise LearningCommitCorrupt(error.reason) from error
        if (
            approval_request.operator_id != operator_id
            or approval_request.decision != requested_decision
            or approval_request.rejection_reason != rejection_reason
        ):
            raise LearningCommitCorrupt("operator_request_replay_binding_invalid")
        quality_assessment_id = (
            str(approval_request.quality_assessment_id)
            if approval_request.quality_assessment_id is not None
            else None
        )
        quality_assessment_hash = approval_request.quality_assessment_hash
        revalidation_assessment_id: str | None = None
        revalidation_assessment_hash: str | None = None
        lifecycle_assessment_id: str | None = None
        lifecycle_assessment_hash: str | None = None
        if recorded_decision == "accept" and learning_change.operation == "revalidate":
            from core import knowledge_revalidation as revalidation

            try:
                revalidation_assessment = revalidation.require_recorded_assessment(
                    session,
                    learning_change,
                    self._snapshot_store,
                    self._session_factory,
                    require_task_done=True,
                    require_current=False,
                )
            except revalidation.KnowledgeRevalidationAssessmentError as error:
                raise LearningCommitCorrupt(str(error)) from error
            approval_binding = approval_request.approval_binding
            if (
                approval_binding is None
                or approval_binding.get("assessment_type") != "knowledge_revalidation"
                or approval_binding.get("assessment_id")
                != str(revalidation_assessment.id)
                or approval_binding.get("assessment_payload_hash")
                != revalidation_assessment.payload_hash
                or quality_assessment_id is not None
                or quality_assessment_hash is not None
            ):
                raise LearningCommitCorrupt(
                    "operator_revalidation_assessment_binding_invalid"
                )
            revalidation_assessment_id = str(revalidation_assessment.id)
            revalidation_assessment_hash = revalidation_assessment.payload_hash
        elif recorded_decision == "accept" and learning_change.operation == "retire":
            from core.knowledge_lifecycle import (
                KnowledgeLifecycleAssessmentError,
            )
            from core.knowledge_lifecycle import (
                require_recorded_assessment as require_lifecycle_assessment,
            )

            try:
                lifecycle_assessment = require_lifecycle_assessment(
                    session,
                    learning_change,
                    self._snapshot_store,
                    self._session_factory,
                    require_task_done=True,
                    require_current=False,
                )
            except KnowledgeLifecycleAssessmentError as error:
                raise LearningCommitCorrupt(str(error)) from error
            approval_binding = approval_request.approval_binding
            if (
                approval_binding is None
                or approval_binding.get("assessment_type") != "knowledge_lifecycle"
                or approval_binding.get("assessment_id") != str(lifecycle_assessment.id)
                or approval_binding.get("assessment_payload_hash")
                != lifecycle_assessment.payload_hash
                or quality_assessment_id is not None
                or quality_assessment_hash is not None
                or lifecycle_assessment.assessment_result != "eligible"
            ):
                raise LearningCommitCorrupt(
                    "operator_lifecycle_assessment_binding_invalid"
                )
            lifecycle_assessment_id = str(lifecycle_assessment.id)
            lifecycle_assessment_hash = lifecycle_assessment.payload_hash
        elif recorded_decision == "accept":
            try:
                quality_assessment = require_recorded_assessment(
                    session, learning_change, require_task_done=True
                )
            except KnowledgeQualityAssessmentError as error:
                raise LearningCommitCorrupt(str(error)) from error
            if (
                quality_assessment_id != str(quality_assessment.id)
                or quality_assessment_hash
                != quality_assessment.assessment_payload_hash
            ):
                raise LearningCommitCorrupt(
                    "operator_quality_assessment_binding_invalid"
                )
        elif quality_assessment_id is not None or quality_assessment_hash is not None:
            raise LearningCommitCorrupt(
                "operator_quality_assessment_not_allowed_for_rejection"
            )
        if approval_request.schema_version == 3:
            from core.knowledge_approval import (
                KnowledgeApprovalBindingError,
                build_approval_binding,
            )

            try:
                expected_binding = build_approval_binding(
                    session,
                    learning_change,
                    operator_id=operator_id,
                    approval_policy_version=task.policy_version,
                    require_assessment=recorded_decision == "accept",
                    snapshot_store=self._snapshot_store,
                    session_factory=self._session_factory,
                )
            except KnowledgeApprovalBindingError as error:
                raise LearningCommitCorrupt(str(error)) from error
            if expected_binding != approval_request.approval_binding:
                raise LearningCommitCorrupt(
                    "operator_approval_binding_invalid"
                )
        if (
            recorded_decision != requested_decision
            or learning_change.decision_reason != rejection_reason
            or learning_change.target_kind != "knowledge_item"
            or (
                learning_change.operation == "create"
                and (
                    learning_change.previous_state is not None
                    or learning_change.target_id is not None
                )
            )
            or (
                learning_change.operation in {"revise", "revalidate"}
                and (
                    learning_change.previous_state is None
                    or learning_change.target_id is None
                )
            )
            or learning_change.operation
            not in {"create", "revise", "revalidate", "retire"}
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
        decision_attempt = (
            payload.get("attempt_count") if isinstance(payload, dict) else None
        )
        if (
            isinstance(decision_attempt, bool)
            or not isinstance(decision_attempt, int)
            or decision_attempt < 1
            or decision_attempt > task.attempt_count
        ):
            raise LearningCommitCorrupt("learning_change_decision_event_mismatch")

        # A replay may happen after interrupted recovery and a later admission.
        # Prove both the attempt that committed the decision and the currently
        # running attempt have their own durable start Events.
        for started_attempt in {decision_attempt, task.attempt_count}:
            start_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == "task_started",
                        Event.payload["attempt_count"].as_integer() == started_attempt,
                    )
                )
            )
            if (
                len(start_events) != 1
                or start_events[0].payload
                != {
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": started_attempt,
                }
            ):
                raise LearningCommitCorrupt("approval_task_start_event_invalid")
            if started_attempt == decision_attempt:
                decision_start_event = start_events[0]
        committed_at = learning_change.committed_at
        if committed_at is None:
            raise LearningCommitCorrupt("learning_change_commit_timestamp_missing")

        expected_payload: dict[str, object] = {
            "schema_version": 1,
            "learning_change_id": str(learning_change.id),
            "operation": learning_change.operation,
            "decision": recorded_decision,
            "operator_id": operator_id,
            "approval_task_id": str(task.id),
            "attempt_count": decision_attempt,
            "evidence_basis_hash": learning_change.evidence_basis_hash,
            "proposal_hash": learning_change.proposed_state.get("proposal_hash"),
            "committed_at": committed_at.isoformat(),
        }
        if approval_request.schema_version == 3:
            expected_payload["schema_version"] = 2
            expected_payload["request_fingerprint"] = (
                approval_request.request_fingerprint
            )
            if approval_request.approval_binding is not None:
                expected_payload["approval_binding"] = (
                    approval_request.approval_binding
                )
        item_id: uuid.UUID | None = None
        if recorded_decision == "accept":
            committed_state: dict[str, typing.Any] | None = None
            if learning_change.operation == "create":
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
                expected_version = 1
                expected_history_id = learning_change.id
            else:
                items = list(
                    session.scalars(
                        select(KnowledgeItem).where(
                            KnowledgeItem.id == learning_change.target_id,
                            KnowledgeItem.team_id == learning_change.team_id,
                        )
                    )
                )
                if len(items) != 1:
                    raise LearningCommitCorrupt(
                        "revised_knowledge_item_missing_or_duplicate"
                    )
                item = items[0]
                try:
                    committed_state, _ = decode_state_snapshot(
                        learning_change.committed_state,
                        learning_change_id=learning_change.id,
                        operation=learning_change.operation,
                    )
                except (KnowledgeHistoryError, TypeError, ValueError) as error:
                    raise LearningCommitCorrupt(
                        "revised_knowledge_item_committed_snapshot_invalid"
                    ) from error
                expected_version = committed_state["version"]
                expected_history_id = learning_change.id
            item_id = item.id
            expected_payload["knowledge_item_id"] = str(item.id)
            expected_payload["knowledge_item_version"] = expected_version
            if learning_change.operation == "revalidate":
                expected_payload["knowledge_revalidation_assessment_id"] = (
                    revalidation_assessment_id
                )
                expected_payload["knowledge_revalidation_assessment_hash"] = (
                    revalidation_assessment_hash
                )
            elif learning_change.operation == "retire":
                expected_payload["knowledge_lifecycle_assessment_id"] = (
                    lifecycle_assessment_id
                )
                expected_payload["knowledge_lifecycle_assessment_hash"] = (
                    lifecycle_assessment_hash
                )
            else:
                expected_payload["knowledge_quality_assessment_id"] = (
                    quality_assessment_id
                )
                expected_payload["knowledge_quality_assessment_hash"] = (
                    quality_assessment_hash
                )
            try:
                history = reconstruct_knowledge_item_history(session, item)
            except KnowledgeHistoryError as error:
                if error.reason == "reconstructed_history_does_not_match_live_item":
                    raise LearningCommitCorrupt(
                        "committed_knowledge_item_mismatch"
                    ) from error
                raise LearningCommitCorrupt(str(error)) from error
            if learning_change.operation == "create":
                expected_supersedes_id = learning_change.proposed_state.get(
                    "supersedes_item_id"
                )
                root_state = history.states[0]
                candidate_root_valid = (
                    root_state["supersedes_item_id"] == expected_supersedes_id
                )
                if expected_supersedes_id is not None:
                    root_review_after = root_state["review_after"]
                    try:
                        candidate_root_valid = candidate_root_valid and (
                            root_review_after is not None
                            and datetime.datetime.fromisoformat(
                                root_review_after.replace("Z", "+00:00")
                            ) > committed_at
                        )
                    except (AttributeError, TypeError, ValueError):
                        candidate_root_valid = False
            else:
                candidate_root_valid = True
            if (
                item.team_id != learning_change.team_id
                or not candidate_root_valid
                or expected_history_id not in history.learning_change_ids
                or (
                    learning_change.operation == "create"
                    and history.learning_change_ids[0] != learning_change.id
                )
                or (
                    learning_change.operation in {"revise", "revalidate"}
                    and (
                        committed_state is None
                        or history.states[
                            history.learning_change_ids.index(learning_change.id)
                        ] != committed_state
                    )
                )
            ):
                raise LearningCommitCorrupt("committed_knowledge_item_mismatch")
        else:
            expected_payload["reason"] = rejection_reason
            if learning_change.committed_state is not None:
                raise LearningCommitCorrupt(
                    "rejected_learning_change_has_committed_state"
                )
            if learning_change.operation == "create":
                if session.scalar(
                    select(KnowledgeItem.id).where(
                        KnowledgeItem.origin_learning_change_id
                        == learning_change.id
                    )
                ) is not None:
                    raise LearningCommitCorrupt(
                        "rejected_learning_change_has_knowledge_item"
                    )
            else:
                rejected_target = session.get(
                    KnowledgeItem, learning_change.target_id
                )
                if (
                    rejected_target is None
                    or rejected_target.team_id != learning_change.team_id
                ):
                    raise LearningCommitCorrupt(
                        "rejected_revision_target_missing"
                    )
                try:
                    history = reconstruct_knowledge_item_history(
                        session, rejected_target
                    )
                except KnowledgeHistoryError as error:
                    raise LearningCommitCorrupt(str(error)) from error
                if learning_change.id in history.learning_change_ids:
                    raise LearningCommitCorrupt(
                        "rejected_revision_appears_in_accepted_history"
                    )

        if (
            event.type != expected_type
            or payload != expected_payload
            or event.created_at != committed_at
            or committed_at < decision_start_event.created_at
        ):
            raise LearningCommitCorrupt("learning_change_decision_event_mismatch")

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
