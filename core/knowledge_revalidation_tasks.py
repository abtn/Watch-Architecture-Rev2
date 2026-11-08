"""Injected execution adapter for one R7-B revalidation assessment Task."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.knowledge_revalidation import (
    KnowledgeRevalidationAssessmentDraft,
    KnowledgeRevalidationAssessmentError,
    KnowledgeRevalidationAssessmentService,
    require_recorded_assessment,
    validate_revalidation_task_request,
)
from core.models import Event, KnowledgeRevalidationAssessment, LearningChange, Outcome, Task
from core.snapshot_store import SnapshotStore
from core.task_runtime import (
    FailureObservation,
    FinalizationResult,
    TaskNotEligible,
    TaskNotFinalizable,
    TaskRuntime,
    TerminalObservation,
)


class KnowledgeRevalidationAssessmentProvider(Protocol):
    """Injected evaluator. No production provider is registered by B3.3."""

    evaluator_identity: str
    evaluator_revision: str

    def assess(
        self,
        *,
        task_id: UUID,
        learning_change: LearningChange,
        target_state: dict[str, object],
        evidence_document: dict[str, object],
        allowed_evidence_references: frozenset[str],
    ) -> KnowledgeRevalidationAssessmentDraft:
        """Return an untrusted typed draft over application-rebuilt evidence."""


@dataclass(frozen=True)
class KnowledgeRevalidationTaskRunResult:
    task_id: UUID
    status: str
    assessment_id: UUID | None
    outcome_id: UUID | None
    replayed: bool = False


class KnowledgeRevalidationAssessmentTaskRunner:
    """Run one already-enqueued revalidation Task through TaskRuntime."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
        provider: KnowledgeRevalidationAssessmentProvider,
        runtime: TaskRuntime | None = None,
    ) -> None:
        if provider is None:
            raise ValueError("knowledge_revalidation_assessment_provider_required")
        if (
            not isinstance(getattr(provider, "evaluator_identity", None), str)
            or not provider.evaluator_identity.strip()
            or not isinstance(getattr(provider, "evaluator_revision", None), str)
            or not provider.evaluator_revision.strip()
        ):
            raise ValueError("knowledge_revalidation_evaluator_identity_required")
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store
        self._provider = provider
        self._runtime = runtime or TaskRuntime(session_factory, snapshot_store)
        self._service = KnowledgeRevalidationAssessmentService(
            session_factory, snapshot_store
        )

    def run(self, task_id: UUID) -> KnowledgeRevalidationTaskRunResult:
        replay_observation: TerminalObservation | None = None
        replay_assessment_id: UUID | None = None
        context = None
        with self._session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise TaskNotEligible("task_not_found")
            if task.status == "failed":
                outcome = session.scalar(
                    select(Outcome).where(
                        Outcome.recorded_by_task_id == task.id,
                        Outcome.outcome_type == "task_execution",
                    )
                )
                return KnowledgeRevalidationTaskRunResult(
                    task_id=task_id,
                    status="failed",
                    assessment_id=None,
                    outcome_id=outcome.id if outcome is not None else None,
                    replayed=True,
                )
            try:
                if task.status == "done":
                    learning_change_id = self._request_learning_change_id(session, task)
                    learning_change = session.get(LearningChange, learning_change_id)
                    if learning_change is None:
                        raise TaskNotEligible(
                            "knowledge_revalidation_learning_change_missing"
                        )
                    assessment = require_recorded_assessment(
                        session,
                        learning_change,
                        self._snapshot_store,
                        self._session_factory,
                        require_task_done=True,
                        require_current=False,
                    )
                    replay_observation = self._terminal_observation(task, assessment)
                    replay_assessment_id = assessment.id
                elif task.status == "pending":
                    context = validate_revalidation_task_request(
                        session,
                        task,
                        self._session_factory,
                        self._snapshot_store,
                        require_proposed=True,
                        require_current=True,
                    )
                elif task.status == "running":
                    assessment = session.scalar(
                        select(KnowledgeRevalidationAssessment).where(
                            KnowledgeRevalidationAssessment.task_id == task.id,
                            KnowledgeRevalidationAssessment.team_id == task.team_id,
                        )
                    )
                    if assessment is None:
                        raise TaskNotEligible(
                            "knowledge_revalidation_task_already_running"
                        )
                    change = session.get(LearningChange, assessment.learning_change_id)
                    if change is None:
                        raise TaskNotEligible(
                            "knowledge_revalidation_learning_change_missing"
                        )
                    assessment = require_recorded_assessment(
                        session,
                        change,
                        self._snapshot_store,
                        self._session_factory,
                        require_task_done=False,
                        require_current=True,
                    )
                    replay_observation = self._terminal_observation(task, assessment)
                    replay_assessment_id = assessment.id
                else:
                    raise TaskNotEligible("knowledge_revalidation_task_not_pending")
            except KnowledgeRevalidationAssessmentError as error:
                raise TaskNotEligible(error.reason) from error

        if replay_observation is not None:
            finalized = self._runtime.finalize(replay_observation)
            return KnowledgeRevalidationTaskRunResult(
                task_id=task_id,
                status=finalized.status,
                assessment_id=replay_assessment_id,
                outcome_id=finalized.outcome_id,
                replayed=True,
            )

        if context is None:
            raise TaskNotEligible("knowledge_revalidation_task_context_missing")
        admission = self._runtime.admit(task_id)
        # Rebuild after admission. A source or target change between the initial
        # read and the Task-start transaction must not reach the evaluator.
        with self._session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise TaskNotEligible("task_not_found")
            try:
                context = validate_revalidation_task_request(
                    session,
                    task,
                    self._session_factory,
                    self._snapshot_store,
                    require_proposed=True,
                    require_current=True,
                )
            except KnowledgeRevalidationAssessmentError as error:
                self._finalize_failure(task_id, admission.attempt_count, error.reason)
                return KnowledgeRevalidationTaskRunResult(
                    task_id=task_id,
                    status="failed",
                    assessment_id=None,
                    outcome_id=None,
                )
        try:
            draft = self._provider.assess(
                task_id=task_id,
                learning_change=context.learning_change,
                target_state=context.target_state,
                evidence_document=context.pack.document,
                allowed_evidence_references=context.pack.reference_ids,
            )
        except Exception:
            failure = self._runtime.report_failure(
                FailureObservation(
                    task_id=task_id,
                    attempt=admission.attempt_count,
                    reason="knowledge_revalidation_evaluator_unavailable",
                    retryable=True,
                    observed_at=datetime.now(timezone.utc),
                )
            )
            return KnowledgeRevalidationTaskRunResult(
                task_id=task_id,
                status=failure.status,
                assessment_id=None,
                outcome_id=(
                    failure.terminal.outcome_id
                    if failure.terminal is not None
                    else None
                ),
            )

        try:
            recorded = self._service.record(
                task_id,
                draft,
                evaluator_identity=self._provider.evaluator_identity,
                evaluator_revision=self._provider.evaluator_revision,
            )
        except KnowledgeRevalidationAssessmentError as error:
            non_retryable = {
                "knowledge_revalidation_target_stale",
                "knowledge_revalidation_evidence_stale",
                "knowledge_revalidation_task_request_mismatch",
                "knowledge_revalidation_learning_change_not_proposed",
                "knowledge_revalidation_source_terminal_invalid",
                "knowledge_revalidation_target_not_found",
                "knowledge_revalidation_previous_state_invalid",
            }
            if error.reason in non_retryable:
                failed = self._finalize_failure(
                    task_id, admission.attempt_count, error.reason
                )
                return KnowledgeRevalidationTaskRunResult(
                    task_id=task_id,
                    status=failed.status,
                    assessment_id=None,
                    outcome_id=failed.outcome_id,
                )
            failure = self._runtime.report_failure(
                FailureObservation(
                    task_id=task_id,
                    attempt=admission.attempt_count,
                    reason=error.reason,
                    retryable=True,
                    observed_at=datetime.now(timezone.utc),
                )
            )
            return KnowledgeRevalidationTaskRunResult(
                task_id=task_id,
                status=failure.status,
                assessment_id=None,
                outcome_id=(
                    failure.terminal.outcome_id
                    if failure.terminal is not None
                    else None
                ),
            )

        finalized = self._runtime.finalize(
            TerminalObservation(
                task_id=task_id,
                attempt=admission.attempt_count,
                result_category="success_knowledge_revalidation_assessed",
                observed_at=recorded.recorded_at,
                knowledge_revalidation_assessment_id=recorded.assessment_id,
            )
        )
        return KnowledgeRevalidationTaskRunResult(
            task_id=task_id,
            status=finalized.status,
            assessment_id=recorded.assessment_id,
            outcome_id=finalized.outcome_id,
            replayed=recorded.replayed,
        )

    @staticmethod
    def _request_learning_change_id(session: Session, task: Task) -> UUID:
        from core.knowledge_revalidation import REQUEST_EVENT_TYPE

        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == REQUEST_EVENT_TYPE,
                )
            )
        )
        if len(events) != 1 or not isinstance(events[0].payload, dict):
            raise TaskNotEligible("knowledge_revalidation_request_event_invalid")
        try:
            return UUID(events[0].payload["learning_change_id"])
        except (KeyError, TypeError, ValueError) as error:
            raise TaskNotEligible(
                "knowledge_revalidation_learning_change_id_invalid"
            ) from error

    @staticmethod
    def _terminal_observation(
        task: Task, assessment: KnowledgeRevalidationAssessment
    ) -> TerminalObservation:
        return TerminalObservation(
            task_id=task.id,
            attempt=task.attempt_count,
            result_category="success_knowledge_revalidation_assessed",
            observed_at=assessment.recorded_at,
            knowledge_revalidation_assessment_id=assessment.id,
        )

    def _finalize_failure(
        self, task_id: UUID, attempt: int, reason: str
    ) -> FinalizationResult:
        return self._runtime.finalize(
            TerminalObservation(
                task_id=task_id,
                attempt=attempt,
                result_category="terminal_failure",
                observed_at=datetime.now(timezone.utc),
                failure_reason=reason,
            )
        )
