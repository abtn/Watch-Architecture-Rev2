"""Narrow execution adapter for one already-enqueued R7-A assessment Task."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.experience_distiller import (
    ExperienceDistiller,
    ExperienceDistillerError,
)
from core.knowledge_quality import (
    KnowledgeQualityAssessmentDraft,
    KnowledgeQualityAssessmentError,
    KnowledgeQualityAssessmentService,
    build_case_lineage_report,
)
from core.models import Event, KnowledgeQualityAssessment, LearningChange, Outcome, Task
from core.snapshot_store import SnapshotStore
from core.task_runtime import (
    FailureObservation,
    TaskNotEligible,
    TaskNotFinalizable,
    TaskRuntime,
    TerminalObservation,
)


class KnowledgeQualityAssessmentProvider(Protocol):
    """Injected evaluator boundary. No production provider is wired by R7-A."""

    def assess(
        self,
        *,
        task_id: UUID,
        learning_change: LearningChange,
        evidence_document: dict[str, object],
        lineage_report: dict[str, object],
    ) -> KnowledgeQualityAssessmentDraft:
        """Return an untrusted structured draft for application validation."""


@dataclass(frozen=True)
class KnowledgeQualityTaskRunResult:
    task_id: UUID
    status: str
    assessment_id: UUID | None
    outcome_id: UUID | None
    replayed: bool = False


class KnowledgeQualityAssessmentTaskRunner:
    """Run one R7-A assessment Task; this is not a dispatcher or runtime."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
        provider: KnowledgeQualityAssessmentProvider,
        runtime: TaskRuntime | None = None,
    ) -> None:
        if provider is None:
            raise ValueError("knowledge_quality_assessment_provider_required")
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store
        self._provider = provider
        self._runtime = runtime or TaskRuntime(session_factory, snapshot_store)
        self._distiller = ExperienceDistiller(
            session_factory, snapshot_store, provider=None
        )
        self._service = KnowledgeQualityAssessmentService(
            session_factory, snapshot_store
        )

    def run(self, task_id: UUID) -> KnowledgeQualityTaskRunResult:
        replay_observation: TerminalObservation | None = None
        replay_assessment_id: UUID | None = None
        with self._session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise TaskNotEligible("task_not_found")
            try:
                request = TaskRuntime._validate_knowledge_quality_task_request(
                    session,
                    task,
                    require_proposed=False,
                )
            except TaskNotFinalizable as error:
                raise TaskNotEligible(str(error)) from error

            if task.status == "done":
                replay_observation = (
                    TaskRuntime._committed_knowledge_quality_assessment_observation(
                        session, task
                    )
                )
                if replay_observation is None:
                    raise TaskNotEligible(
                        "completed_knowledge_quality_assessment_missing"
                    )
                assessment = session.scalar(
                    select(KnowledgeQualityAssessment).where(
                        KnowledgeQualityAssessment.creating_task_id == task.id,
                        KnowledgeQualityAssessment.team_id == task.team_id,
                    )
                )
                replay_assessment_id = (
                    assessment.id if assessment is not None else None
                )
            elif task.status == "failed":
                outcome = session.scalar(
                    select(Outcome).where(
                        Outcome.recorded_by_task_id == task.id,
                        Outcome.outcome_type == "task_execution",
                    )
                )
                return KnowledgeQualityTaskRunResult(
                    task_id=task_id,
                    status="failed",
                    assessment_id=None,
                    outcome_id=outcome.id if outcome is not None else None,
                    replayed=True,
                )
            elif task.status != "pending":
                raise TaskNotEligible("knowledge_quality_task_already_running")
            else:
                if request.get("learning_change_id") is None:
                    raise TaskNotEligible("knowledge_quality_learning_change_missing")
                learning_change = session.get(
                    LearningChange, UUID(request["learning_change_id"])
                )
                if (
                    learning_change is None
                    or learning_change.team_id != task.team_id
                ):
                    raise TaskNotEligible(
                        "knowledge_quality_learning_change_missing"
                    )
                rejected_before_assessment = learning_change.status == "rejected"
                if learning_change.status not in {"proposed", "rejected"}:
                    raise TaskNotEligible(
                        "knowledge_quality_learning_change_already_decided"
                    )
                if not rejected_before_assessment:
                    try:
                        _, pack = self._distiller.validate_learning_change(
                            session, learning_change
                        )
                    except ExperienceDistillerError as error:
                        raise TaskNotEligible(error.reason) from error
                    lineage_report = build_case_lineage_report(
                        session, task.team_id, pack.evidence_basis
                    )
                    if pack.basis_hash != request["evidence_basis_hash"]:
                        raise TaskNotEligible(
                            "knowledge_quality_evidence_basis_stale"
                        )

        if replay_observation is not None:
            result = self._runtime.finalize(replay_observation)
            return KnowledgeQualityTaskRunResult(
                task_id=task_id,
                status=result.status,
                assessment_id=replay_assessment_id,
                outcome_id=result.outcome_id,
                replayed=True,
            )

        admission = self._runtime.admit(task_id)
        if rejected_before_assessment:
            started_at = self._attempt_started_at(
                task_id, admission.attempt_count
            )
            failed = self._runtime.finalize(
                TerminalObservation(
                    task_id=task_id,
                    attempt=admission.attempt_count,
                    result_category="terminal_failure",
                    observed_at=started_at,
                    failure_reason="learning_change_rejected_before_quality_assessment",
                )
            )
            return KnowledgeQualityTaskRunResult(
                task_id=task_id,
                status=failed.status,
                assessment_id=None,
                outcome_id=failed.outcome_id,
            )
        try:
            draft = self._provider.assess(
                task_id=task_id,
                learning_change=learning_change,
                evidence_document=pack.document,
                lineage_report=lineage_report,
            )
        except Exception:
            failure_time = datetime.now(timezone.utc)
            retry = self._runtime.report_failure(
                FailureObservation(
                    task_id=task_id,
                    attempt=admission.attempt_count,
                    reason="knowledge_quality_evaluator_unavailable",
                    retryable=True,
                    observed_at=failure_time,
                )
            )
            return KnowledgeQualityTaskRunResult(
                task_id=task_id,
                status=retry.status,
                assessment_id=None,
                outcome_id=None,
            )
        try:
            if not isinstance(draft, KnowledgeQualityAssessmentDraft):
                raise KnowledgeQualityAssessmentError(
                    "knowledge_quality_provider_output_invalid"
                )
            recorded = self._service.record(task_id, draft)
        except KnowledgeQualityAssessmentError as error:
            failed_at = datetime.now(timezone.utc)
            non_retryable = {
                "knowledge_quality_evidence_basis_stale",
                "knowledge_quality_lineage_report_mismatch",
                "knowledge_quality_task_request_mismatch",
                "learning_change_not_proposed",
                "knowledge_quality_task_start_event_invalid",
            }
            if error.reason not in non_retryable:
                retry = self._runtime.report_failure(
                    FailureObservation(
                        task_id=task_id,
                        attempt=admission.attempt_count,
                        reason=error.reason,
                        retryable=True,
                        observed_at=failed_at,
                    )
                )
                return KnowledgeQualityTaskRunResult(
                    task_id=task_id,
                    status=retry.status,
                    assessment_id=None,
                    outcome_id=(
                        retry.terminal.outcome_id
                        if retry.terminal is not None
                        else None
                    ),
                )
            failed = self._runtime.finalize(
                TerminalObservation(
                    task_id=task_id,
                    attempt=admission.attempt_count,
                    result_category="terminal_failure",
                    observed_at=failed_at,
                    failure_reason=error.reason,
                )
            )
            return KnowledgeQualityTaskRunResult(
                task_id=task_id,
                status=failed.status,
                assessment_id=None,
                outcome_id=failed.outcome_id,
            )

        finalized = self._runtime.finalize(
            TerminalObservation(
                task_id=task_id,
                attempt=admission.attempt_count,
                result_category="success_knowledge_quality_assessed",
                observed_at=recorded.recorded_at,
                knowledge_quality_assessment_id=recorded.assessment_id,
            )
        )
        return KnowledgeQualityTaskRunResult(
            task_id=task_id,
            status=finalized.status,
            assessment_id=recorded.assessment_id,
            outcome_id=finalized.outcome_id,
            replayed=recorded.replayed,
        )

    def _attempt_started_at(self, task_id: UUID, attempt: int) -> datetime:
        with self._session_factory() as session:
            started_at = session.scalar(
                select(Event.created_at).where(
                    Event.task_id == task_id,
                    Event.type == "task_started",
                    Event.payload["attempt_count"].as_integer() == attempt,
                )
            )
        if started_at is None or started_at.tzinfo is None:
            raise TaskNotFinalizable("knowledge_quality_task_start_event_missing")
        return started_at
