"""Host-invoked application boundary for manual Operator Tasks.

The host authenticates and authorizes the human. This module accepts the
resulting typed principal context; it does not authenticate request data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from core.knowledge_approval import (
    KnowledgeApprovalBindingError,
    build_approval_binding,
)
from core.models import Event, LearningChange, Task, Team, TeamPolicy
from core.operator_approval import (
    OperatorApprovalValidationError,
    build_request_fingerprint,
    canonical_operator_identity,
    is_supported_learning_change,
    parse_request_event_payload,
    validate_decision_reason,
)
from core.snapshot_store import SnapshotStore

_APPROVAL_ACTION = "approve_learning_change"
_APPROVAL_TASK_TYPE = "approve_learning_change"
_REQUEST_EVENT_TYPE = "operator_task_requested"
_ALLOWED_WRITES = ["LearningChange", "KnowledgeItem"]
_TASK_BUDGET = {"max_tool_calls": 0, "max_cost_usd": 0.0}
_TASK_MAX_ATTEMPTS = 3

# Fixed namespace: the same host request key maps to the same Task after restart.
_TASK_ID_NAMESPACE = UUID("a0ad72d4-3d4c-4a32-8d1e-61c4b36d0ec2")


class OperatorApplicationError(ValueError):
    """The host-invoked Operator Task request is invalid or unauthorized."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidOperatorPrincipal(OperatorApplicationError):
    """The host did not supply a valid typed Operator principal."""


class OperatorNotAuthorized(OperatorApplicationError):
    """The host principal lacks the exact Team/action grant."""


class LearningChangeNotApprovable(OperatorApplicationError):
    """The LearningChange is not an eligible Checkpoint 3 create proposal."""


class OperatorTaskRequestConflict(OperatorApplicationError):
    """An idempotency key was reused for a different approval request."""


class OperatorTaskRequestCorrupt(OperatorApplicationError):
    """The deterministic Task or its request Event is inconsistent."""


@dataclass(frozen=True)
class OperatorGrant:
    """One Team-scoped action already authorized by the host application."""

    team_id: UUID
    action: str


@dataclass(frozen=True)
class TrustedOperatorPrincipal:
    """Stable host-authenticated identity plus host-authorized action grants.

    This value is an in-process contract, not a credential. Only the trusted
    host composition root may construct/pass it to this adapter.
    """

    issuer: str
    subject: str
    grants: frozenset[OperatorGrant]


@dataclass(frozen=True)
class LearningChangeDecisionRequest:
    """A human decision request; actor identity is deliberately not a field."""

    learning_change_id: UUID
    decision: Literal["accept", "reject"]
    idempotency_key: UUID
    rejection_reason: str | None = None


@dataclass(frozen=True)
class OperatorTaskRequestResult:
    """The durable approval Task created or resolved by one host request."""

    task_id: UUID
    team_id: UUID
    status: str
    replayed: bool


@dataclass(frozen=True)
class OperatorDecisionResult:
    """The canonical LearningChange decision and its finalized ordinary Task."""

    task_id: UUID
    team_id: UUID
    attempt_count: int
    learning_change_id: UUID
    decision: Literal["accept", "reject"]
    learning_change_status: Literal["accepted", "rejected"]
    task_status: Literal["done"]
    operator_id: str
    knowledge_item_id: UUID | None
    committed_at: datetime
    outcome_id: UUID
    replayed: bool = False


class OperatorApplicationAdapter:
    """Run trusted Operator decisions through the ordinary Task lifecycle.

    Request creation is available without a SnapshotStore for host-side
    idempotent Task setup. The synchronous `decide_learning_change` path
    requires the configured SnapshotStore and composes TaskRuntime admission,
    canonical decision commit, and TaskRuntime terminal finalization.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store

    def request_learning_change_decision(
        self,
        principal: TrustedOperatorPrincipal,
        request: LearningChangeDecisionRequest,
    ) -> OperatorTaskRequestResult:
        """Create one immutable, assessment-bound approval request or replay it."""
        canonical_operator_id = _canonical_operator_identity(principal)
        rejection_reason = _validate_request(request)

        with self._session_factory.begin() as session:
            learning_change = session.scalar(
                select(LearningChange)
                .where(LearningChange.id == request.learning_change_id)
                .with_for_update(read=True)
            )
            if learning_change is None:
                raise LearningChangeNotApprovable("learning_change_not_found")

            # B3 remains create-only. The broader binding resolver is shared
            # with the later R7-B operation gates, but this adapter does not
            # create approval Tasks for lifecycle operations.
            if not is_supported_learning_change(
                target_kind=learning_change.target_kind,
                operation=learning_change.operation,
                target_id=learning_change.target_id,
            ):
                raise LearningChangeNotApprovable(
                    "only_knowledge_item_create_is_supported"
                )

            team_id = learning_change.team_id
            _require_team_grant(principal, team_id)
            task_id = _approval_task_id(team_id, request.idempotency_key)
            idempotency_key_hash = _sha256(str(request.idempotency_key))

            existing_task = session.scalar(
                select(Task).where(Task.id == task_id)
            )
            if existing_task is not None:
                try:
                    approval_binding = build_approval_binding(
                        session,
                        learning_change,
                        operator_id=canonical_operator_id,
                        approval_policy_version=existing_task.policy_version,
                        require_assessment=request.decision == "accept",
                        snapshot_store=self._snapshot_store,
                        session_factory=self._session_factory,
                    )
                except KnowledgeApprovalBindingError as error:
                    raise LearningChangeNotApprovable(str(error)) from error
                quality_assessment_id = (
                    UUID(approval_binding["assessment_id"])
                    if approval_binding["assessment_type"] == "knowledge_quality"
                    else None
                )
                quality_assessment_hash = (
                    approval_binding["assessment_payload_hash"]
                    if approval_binding["assessment_type"] == "knowledge_quality"
                    else None
                )
                return _verify_existing_request(
                    session=session,
                    task=existing_task,
                    team_id=team_id,
                    request=request,
                    rejection_reason=rejection_reason,
                    operator_id=canonical_operator_id,
                    idempotency_key_hash=idempotency_key_hash,
                    approval_binding=approval_binding,
                    quality_assessment_id=quality_assessment_id,
                    quality_assessment_hash=quality_assessment_hash,
                )

            if learning_change.status != "proposed":
                raise LearningChangeNotApprovable(
                    "learning_change_not_proposed"
                )

            team = session.scalar(
                select(Team)
                .where(Team.id == team_id)
                .with_for_update()
            )
            if team is None:
                raise OperatorApplicationError("team_not_found")
            if team.status != "active":
                raise OperatorApplicationError("team_not_active")

            # TeamPolicy has immutable versioned rows and no active-version
            # pointer; the latest version is the current policy pin.
            policy = session.scalar(
                select(TeamPolicy)
                .where(TeamPolicy.team_id == team_id)
                .order_by(TeamPolicy.version.desc())
                .limit(1)
                .with_for_update(read=True)
            )
            if policy is None:
                raise OperatorApplicationError("team_policy_missing")

            try:
                approval_binding = build_approval_binding(
                    session,
                    learning_change,
                    operator_id=canonical_operator_id,
                    approval_policy_version=policy.version,
                    require_assessment=request.decision == "accept",
                    snapshot_store=self._snapshot_store,
                    session_factory=self._session_factory,
                )
            except KnowledgeApprovalBindingError as error:
                raise LearningChangeNotApprovable(str(error)) from error

            quality_assessment_id = (
                UUID(approval_binding["assessment_id"])
                if approval_binding["assessment_type"] == "knowledge_quality"
                else None
            )
            quality_assessment_hash = (
                approval_binding["assessment_payload_hash"]
                if approval_binding["assessment_type"] == "knowledge_quality"
                else None
            )
            request_fingerprint = _request_fingerprint(
                team_id=team_id,
                learning_change_id=learning_change.id,
                decision=request.decision,
                rejection_reason=rejection_reason,
                operator_id=canonical_operator_id,
                quality_assessment_id=quality_assessment_id,
                quality_assessment_hash=quality_assessment_hash,
                approval_binding=approval_binding,
            )

            event_payload = _request_event_payload(
                learning_change_id=learning_change.id,
                decision=request.decision,
                rejection_reason=rejection_reason,
                operator_id=canonical_operator_id,
                idempotency_key_hash=idempotency_key_hash,
                request_fingerprint=request_fingerprint,
                policy_version=policy.version,
                quality_assessment_id=quality_assessment_id,
                quality_assessment_hash=quality_assessment_hash,
                approval_binding=approval_binding,
            )

            inserted_task_id = session.scalar(
                pg_insert(Task)
                .values(
                    id=task_id,
                    team_id=team_id,
                    task_type=_APPROVAL_TASK_TYPE,
                    status="pending",
                    attempt_count=0,
                    policy_version=policy.version,
                    objective_id=None,
                    plan_id=None,
                    plan_action_id=None,
                    allowed_writes=_ALLOWED_WRITES,
                    budget=_TASK_BUDGET,
                    completed_at=None,
                    max_attempts=_TASK_MAX_ATTEMPTS,
                )
                .on_conflict_do_nothing(index_elements=[Task.id])
                .returning(Task.id)
            )

            if inserted_task_id is None:
                concurrent_task = session.scalar(
                    select(Task).where(Task.id == task_id)
                )
                if concurrent_task is None:
                    raise OperatorTaskRequestCorrupt(
                        "task_missing_after_idempotency_conflict"
                    )
                try:
                    concurrent_binding = build_approval_binding(
                        session,
                        learning_change,
                        operator_id=canonical_operator_id,
                        approval_policy_version=concurrent_task.policy_version,
                        require_assessment=request.decision == "accept",
                        snapshot_store=self._snapshot_store,
                        session_factory=self._session_factory,
                    )
                except KnowledgeApprovalBindingError as error:
                    raise LearningChangeNotApprovable(str(error)) from error
                concurrent_quality_id = (
                    UUID(concurrent_binding["assessment_id"])
                    if concurrent_binding["assessment_type"] == "knowledge_quality"
                    else None
                )
                concurrent_quality_hash = (
                    concurrent_binding["assessment_payload_hash"]
                    if concurrent_binding["assessment_type"] == "knowledge_quality"
                    else None
                )
                return _verify_existing_request(
                    session=session,
                    task=concurrent_task,
                    team_id=team_id,
                    request=request,
                    rejection_reason=rejection_reason,
                    operator_id=canonical_operator_id,
                    idempotency_key_hash=idempotency_key_hash,
                    approval_binding=concurrent_binding,
                    quality_assessment_id=concurrent_quality_id,
                    quality_assessment_hash=concurrent_quality_hash,
                )

            session.add(
                Event(
                    id=uuid4(),
                    task_id=task_id,
                    type=_REQUEST_EVENT_TYPE,
                    payload=event_payload,
                    created_at=datetime.now(timezone.utc),
                )
            )
            session.flush()

            return OperatorTaskRequestResult(
                task_id=task_id,
                team_id=team_id,
                status="pending",
                replayed=False,
            )

    def decide_learning_change(
        self,
        principal: TrustedOperatorPrincipal,
        request: LearningChangeDecisionRequest,
    ) -> OperatorDecisionResult:
        """Run request creation, admission, decision, and Task finalization.

        A running Task is resumed rather than admitted a second time. A pending
        Task is admitted through TaskRuntime. Replays after recovery or after a
        lost response resolve through the same deterministic Task and decision
        records; this method never writes Task lifecycle state directly.
        """
        if self._snapshot_store is None:
            raise OperatorApplicationError(
                "snapshot_store_required_for_decision_execution"
            )

        request_result = self.request_learning_change_decision(principal, request)

        # Import at call time to keep the application boundary below the
        # learning-commit module without creating a module-import cycle.
        from core.learning_commit import LearningCommitConflict, LearningCommitService
        from core.task_runtime import TaskNotEligible, TaskRuntime, TerminalObservation

        task_runtime = TaskRuntime(self._session_factory, self._snapshot_store)
        with self._session_factory() as session:
            task = session.get(Task, request_result.task_id)
            if task is None:
                raise OperatorTaskRequestCorrupt("approval_task_disappeared")
            task_status = task.status
            attempt = task.attempt_count

        if task_status == "pending":
            try:
                admission = task_runtime.admit(request_result.task_id)
                attempt = admission.attempt_count
            except TaskNotEligible as error:
                # A concurrent caller may have won admission. Continue only
                # when the authoritative row now proves an active/final Task.
                if str(error) != "task_not_pending":
                    raise
                with self._session_factory() as session:
                    task = session.get(Task, request_result.task_id)
                    if task is None or task.status not in {"running", "done"}:
                        raise OperatorApplicationError(
                            "approval_task_admission_race_lost"
                        ) from error
                    task_status = task.status
                    attempt = task.attempt_count
        elif task_status == "failed":
            # A distinct approval Task may lose a race to another Task that
            # already committed this LearningChange. Recovery terminalizes
            # that loser as a deterministic failure; replay the same outcome
            # and return the same typed conflict rather than treating it as an
            # unexplained non-executable Task.
            with self._session_factory.begin() as session:
                task = session.scalar(
                    select(Task)
                    .where(Task.id == request_result.task_id)
                    .with_for_update()
                )
                if task is None:
                    raise OperatorTaskRequestCorrupt("approval_task_disappeared")
                conflict_observation = (
                    TaskRuntime._committed_operator_decision_observation(
                        session, task
                    )
                )
            if (
                conflict_observation is None
                or conflict_observation.result_category != "terminal_failure"
                or conflict_observation.failure_reason
                != "learning_change_already_decided"
            ):
                raise OperatorApplicationError("approval_task_not_executable")
            replayed_failure = task_runtime.finalize(conflict_observation)
            if replayed_failure.status != "failed":
                raise OperatorApplicationError(
                    "approval_task_conflict_failure_not_replayed"
                )
            raise OperatorTaskRequestConflict("learning_change_already_decided")
        elif task_status not in {"running", "done"}:
            raise OperatorApplicationError("approval_task_not_executable")

        try:
            commit = LearningCommitService(
                self._session_factory, self._snapshot_store
            ).decide(request_result.task_id, attempt, principal)
        except LearningCommitConflict as error:
            if str(error) != "learning_change_already_decided":
                raise
            # The LearningChange row lock serializes distinct approval Tasks.
            # Once another Task wins, this Task must become terminal through
            # the existing runtime, not remain running after losing the race.
            with self._session_factory.begin() as session:
                task = session.scalar(
                    select(Task)
                    .where(Task.id == request_result.task_id)
                    .with_for_update()
                )
                if task is None:
                    raise OperatorTaskRequestCorrupt("approval_task_disappeared")
                conflict_observation = (
                    TaskRuntime._committed_operator_decision_observation(
                        session, task
                    )
                )
            if (
                conflict_observation is None
                or conflict_observation.result_category != "terminal_failure"
                or conflict_observation.failure_reason
                != "learning_change_already_decided"
            ):
                raise OperatorApplicationError(
                    "approval_task_conflict_could_not_be_reconciled"
                ) from error
            finalization = task_runtime.finalize(conflict_observation)
            if finalization.status != "failed":
                raise OperatorApplicationError(
                    "approval_task_conflict_failure_not_recorded"
                ) from error
            raise OperatorTaskRequestConflict(
                "learning_change_already_decided"
            ) from error
        result_category: Literal[
            "success_learning_change_accepted", "success_learning_change_rejected"
        ] = (
            "success_learning_change_accepted"
            if commit.decision == "accept"
            else "success_learning_change_rejected"
        )
        learning_change_status: Literal["accepted", "rejected"] = (
            "accepted" if commit.decision == "accept" else "rejected"
        )
        finalization = task_runtime.finalize(
            TerminalObservation(
                task_id=commit.task_id,
                attempt=commit.attempt_count,
                result_category=result_category,
                observed_at=commit.committed_at,
                learning_change_id=commit.learning_change_id,
            )
        )
        if finalization.status != "done":
            raise OperatorApplicationError(
                "approval_task_did_not_finalize_successfully"
            )

        return OperatorDecisionResult(
            task_id=commit.task_id,
            team_id=request_result.team_id,
            attempt_count=finalization.attempt_count,
            learning_change_id=commit.learning_change_id,
            decision=commit.decision,
            learning_change_status=learning_change_status,
            task_status="done",
            operator_id=commit.operator_id,
            knowledge_item_id=commit.knowledge_item_id,
            committed_at=commit.committed_at,
            outcome_id=finalization.outcome_id,
            replayed=(
                request_result.replayed
                or commit.replayed
                or finalization.replayed
            ),
        )


def _validate_request(
    request: LearningChangeDecisionRequest,
) -> str | None:
    if not isinstance(request, LearningChangeDecisionRequest):
        raise OperatorApplicationError("typed_decision_request_required")
    if not isinstance(request.learning_change_id, UUID):
        raise OperatorApplicationError("invalid_learning_change_id")
    if not isinstance(request.idempotency_key, UUID):
        raise OperatorApplicationError("invalid_idempotency_key")
    if request.decision not in ("accept", "reject"):
        raise OperatorApplicationError("invalid_decision")

    try:
        return validate_decision_reason(request.decision, request.rejection_reason)
    except OperatorApprovalValidationError as error:
        raise OperatorApplicationError(error.reason) from error


def _canonical_operator_identity(
    principal: TrustedOperatorPrincipal,
) -> str:
    if not isinstance(principal, TrustedOperatorPrincipal):
        raise InvalidOperatorPrincipal("trusted_operator_principal_required")
    if not isinstance(principal.grants, frozenset) or any(
        not isinstance(grant, OperatorGrant) for grant in principal.grants
    ):
        raise InvalidOperatorPrincipal("invalid_operator_grants")

    try:
        return canonical_operator_identity(principal.issuer, principal.subject)
    except OperatorApprovalValidationError as error:
        raise InvalidOperatorPrincipal(error.reason) from error


def _require_team_grant(
    principal: TrustedOperatorPrincipal,
    team_id: UUID,
) -> None:
    if OperatorGrant(team_id=team_id, action=_APPROVAL_ACTION) not in principal.grants:
        raise OperatorNotAuthorized("operator_not_authorized_for_team_action")


def _approval_task_id(team_id: UUID, idempotency_key: UUID) -> UUID:
    name = f"{team_id}:{_APPROVAL_TASK_TYPE}:{idempotency_key}"
    return uuid5(_TASK_ID_NAMESPACE, name)


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request_fingerprint(
    *,
    team_id: UUID,
    learning_change_id: UUID,
    decision: str,
    rejection_reason: str | None,
    operator_id: str,
    quality_assessment_id: UUID | None,
    quality_assessment_hash: str | None,
    approval_binding: dict[str, object] | None = None,
) -> str:
    return build_request_fingerprint(
        team_id=team_id,
        learning_change_id=learning_change_id,
        decision=decision,
        rejection_reason=rejection_reason,
        operator_id=operator_id,
        quality_assessment_id=quality_assessment_id,
        quality_assessment_hash=quality_assessment_hash,
        approval_binding=approval_binding,
    )


def _request_event_payload(
    *,
    learning_change_id: UUID,
    decision: str,
    rejection_reason: str | None,
    operator_id: str,
    idempotency_key_hash: str,
    request_fingerprint: str,
    policy_version: int,
    quality_assessment_id: UUID | None,
    quality_assessment_hash: str | None,
    approval_binding: dict[str, object] | None = None,
    schema_version: int = 3,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": schema_version,
        "operation": _APPROVAL_ACTION,
        "learning_change_id": str(learning_change_id),
        "decision": decision,
        "rejection_reason": rejection_reason,
        "operator_id": operator_id,
        "idempotency_key_hash": idempotency_key_hash,
        "request_fingerprint": request_fingerprint,
        "policy_version": policy_version,
        "knowledge_quality_assessment_id": (
            str(quality_assessment_id) if quality_assessment_id else None
        ),
        "knowledge_quality_assessment_hash": quality_assessment_hash,
    }
    if schema_version == 3:
        if approval_binding is None:
            raise OperatorTaskRequestCorrupt("approval_binding_missing")
        payload["approval_binding"] = approval_binding
    return payload


def _verify_existing_request(
    *,
    session: Session,
    task: Task,
    team_id: UUID,
    request: LearningChangeDecisionRequest,
    rejection_reason: str | None,
    operator_id: str,
    idempotency_key_hash: str,
    approval_binding: dict[str, object],
    quality_assessment_id: UUID | None,
    quality_assessment_hash: str | None,
) -> OperatorTaskRequestResult:
    if (
        task.id != _approval_task_id(team_id, request.idempotency_key)
        or task.team_id != team_id
        or task.task_type != _APPROVAL_TASK_TYPE
        or task.status not in {"pending", "running", "done", "failed"}
        or task.objective_id is not None
        or task.plan_id is not None
        or task.plan_action_id is not None
        or task.allowed_writes != _ALLOWED_WRITES
        or task.budget != _TASK_BUDGET
        or task.max_attempts != _TASK_MAX_ATTEMPTS
        or task.attempt_count < 0
        or task.attempt_count > task.max_attempts
    ):
        raise OperatorTaskRequestCorrupt("approval_task_shape_mismatch")

    events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == _REQUEST_EVENT_TYPE,
            )
        )
    )
    if len(events) != 1 or not isinstance(events[0].payload, dict):
        raise OperatorTaskRequestCorrupt("approval_request_event_count_invalid")

    payload = events[0].payload
    if payload.get("idempotency_key_hash") != idempotency_key_hash:
        raise OperatorTaskRequestCorrupt("approval_request_key_hash_mismatch")

    policy_version = payload.get("policy_version")
    if (
        isinstance(policy_version, bool)
        or not isinstance(policy_version, int)
        or task.policy_version != policy_version
    ):
        raise OperatorTaskRequestCorrupt("approval_request_policy_pin_mismatch")

    try:
        parsed = parse_request_event_payload(
            payload, team_id=team_id, policy_version=task.policy_version
        )
    except OperatorApprovalValidationError as error:
        raise OperatorTaskRequestCorrupt(error.reason) from error

    if parsed.schema_version == 1:
        if request.decision != "reject" or (
            quality_assessment_id is not None
            or quality_assessment_hash is not None
        ):
            raise OperatorTaskRequestCorrupt(
                "legacy_acceptance_request_missing_quality_assessment"
            )
        legacy_fingerprint_payload = json.dumps(
            {
                "operation": _APPROVAL_ACTION,
                "team_id": str(team_id),
                "learning_change_id": str(request.learning_change_id),
                "decision": request.decision,
                "rejection_reason": rejection_reason,
                "operator_id": operator_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        legacy_fingerprint = _sha256(legacy_fingerprint_payload)
        expected_legacy_payload = {
            "schema_version": 1,
            "operation": _APPROVAL_ACTION,
            "learning_change_id": str(request.learning_change_id),
            "decision": request.decision,
            "rejection_reason": rejection_reason,
            "operator_id": operator_id,
            "idempotency_key_hash": idempotency_key_hash,
            "request_fingerprint": legacy_fingerprint,
            "policy_version": policy_version,
        }
        if payload != expected_legacy_payload:
            raise OperatorTaskRequestCorrupt(
                "legacy_approval_request_event_payload_mismatch"
            )
    else:
        stored_binding = (
            approval_binding if parsed.schema_version == 3 else None
        )
        expected_fingerprint = _request_fingerprint(
            team_id=team_id,
            learning_change_id=request.learning_change_id,
            decision=request.decision,
            rejection_reason=rejection_reason,
            operator_id=operator_id,
            quality_assessment_id=quality_assessment_id,
            quality_assessment_hash=quality_assessment_hash,
            approval_binding=stored_binding,
        )
        if parsed.request_fingerprint != expected_fingerprint:
            raise OperatorTaskRequestConflict(
                "idempotency_key_reused_with_different_request"
            )
        expected_payload = _request_event_payload(
            learning_change_id=request.learning_change_id,
            decision=request.decision,
            rejection_reason=rejection_reason,
            operator_id=operator_id,
            idempotency_key_hash=idempotency_key_hash,
            request_fingerprint=expected_fingerprint,
            policy_version=policy_version,
            quality_assessment_id=quality_assessment_id,
            quality_assessment_hash=quality_assessment_hash,
            approval_binding=stored_binding,
            schema_version=parsed.schema_version,
        )
        if payload != expected_payload:
            raise OperatorTaskRequestCorrupt(
                "approval_request_event_payload_mismatch"
            )

    return OperatorTaskRequestResult(
        task_id=task.id,
        team_id=team_id,
        status=task.status,
        replayed=True,
    )
