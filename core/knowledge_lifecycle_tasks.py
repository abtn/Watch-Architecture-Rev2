"""B3.4 Task-side adapter for deterministic lifecycle assessment.

TaskRuntime admission/finalization/recovery activation is deliberately deferred
to B3.5. This adapter owns only the lifecycle request contract and assessment
recording boundary; it never writes KnowledgeItem or LearningChange.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.knowledge_lifecycle import (
    KnowledgeLifecycleAssessmentError,
    KnowledgeLifecycleAssessmentResult,
    KnowledgeLifecycleAssessmentService,
    require_recorded_assessment,
    validate_lifecycle_task_request,
)
from core.models import (
    Event,
    KnowledgeLifecycleAssessment,
    LearningChange,
    Outcome,
    Task,
)
from core.snapshot_store import SnapshotStore
from core.task_runtime import (
    FinalizationResult,
    TaskNotEligible,
    TaskRuntime,
    TerminalObservation,
)


class KnowledgeLifecycleAssessmentTask:
    """Narrow application adapter for one assess_knowledge_lifecycle Task."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
    ) -> None:
        self._session_factory = session_factory
        self._service = KnowledgeLifecycleAssessmentService(
            session_factory, snapshot_store
        )
        self._snapshot_store = snapshot_store

    def create(self, learning_change_id: UUID) -> UUID:
        """Create or replay the deterministic lifecycle assessment Task."""
        return self._service.create_task(learning_change_id)

    def validate(self, task_id: UUID) -> dict[str, object]:
        """Validate the persisted request before a worker is allowed to run."""
        with self._session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise KnowledgeLifecycleAssessmentError(
                    "knowledge_lifecycle_task_not_found"
                )
            context = validate_lifecycle_task_request(
                session,
                task,
                self._session_factory,
                self._snapshot_store,
                require_proposed=True,
            )
            return dict(context.request_payload)

    def record(self, task_id: UUID) -> KnowledgeLifecycleAssessmentResult:
        """Record the deterministic assessment for an already-running Task.

        The existing runtime remains the sole owner of Task admission and
        terminal state. B3.5 adds the lifecycle-specific runtime hooks.
        """
        return self._service.record(task_id)

@dataclass(frozen=True)
class KnowledgeLifecycleTaskRunResult:
    task_id: UUID
    status: str
    assessment_id: UUID | None
    assessment_result: str | None
    outcome_id: UUID | None
    replayed: bool = False


class KnowledgeLifecycleAssessmentTaskRunner:
    """Run one deterministic lifecycle assessment through the existing runtime."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
        runtime: TaskRuntime | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store
        self._runtime = runtime or TaskRuntime(session_factory, snapshot_store)
        self._task = KnowledgeLifecycleAssessmentTask(
            session_factory, snapshot_store
        )

    def run(self, task_id: UUID) -> KnowledgeLifecycleTaskRunResult:
        replay_observation: TerminalObservation | None = None
        replay_assessment_id: UUID | None = None
        replay_assessment_result: str | None = None
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
                return KnowledgeLifecycleTaskRunResult(
                    task_id=task_id,
                    status="failed",
                    assessment_id=None,
                    assessment_result=None,
                    outcome_id=outcome.id if outcome is not None else None,
                    replayed=True,
                )
            try:
                if task.status == "done":
                    learning_change_id = self._request_learning_change_id(
                        session, task
                    )
                    learning_change = session.get(
                        LearningChange, learning_change_id
                    )
                    if learning_change is None:
                        raise TaskNotEligible(
                            "knowledge_lifecycle_learning_change_missing"
                        )
                    assessment = require_recorded_assessment(
                        session,
                        learning_change,
                        self._snapshot_store,
                        self._session_factory,
                        require_task_done=True,
                        require_current=False,
                    )
                    replay_observation = self._terminal_observation(
                        task, assessment
                    )
                    replay_assessment_id = assessment.id
                    replay_assessment_result = assessment.assessment_result
                elif task.status == "pending":
                    validate_lifecycle_task_request(
                        session,
                        task,
                        self._session_factory,
                        self._snapshot_store,
                        require_proposed=True,
                    )
                elif task.status == "running":
                    assessment = session.scalar(
                        select(KnowledgeLifecycleAssessment).where(
                            KnowledgeLifecycleAssessment.task_id == task.id,
                            KnowledgeLifecycleAssessment.team_id == task.team_id,
                        )
                    )
                    if assessment is None:
                        raise TaskNotEligible(
                            "knowledge_lifecycle_task_already_running"
                        )
                    learning_change = session.get(
                        LearningChange, assessment.learning_change_id
                    )
                    if learning_change is None:
                        raise TaskNotEligible(
                            "knowledge_lifecycle_learning_change_missing"
                        )
                    verified = require_recorded_assessment(
                        session,
                        learning_change,
                        self._snapshot_store,
                        self._session_factory,
                        require_task_done=False,
                        require_current=True,
                    )
                    replay_observation = self._terminal_observation(
                        task, verified
                    )
                    replay_assessment_id = verified.id
                    replay_assessment_result = verified.assessment_result
                else:
                    raise TaskNotEligible(
                        "knowledge_lifecycle_task_not_pending"
                    )
            except KnowledgeLifecycleAssessmentError as error:
                raise TaskNotEligible(error.reason) from error

        if replay_observation is not None:
            finalized = self._runtime.finalize(replay_observation)
            return KnowledgeLifecycleTaskRunResult(
                task_id=task_id,
                status=finalized.status,
                assessment_id=replay_assessment_id,
                assessment_result=replay_assessment_result,
                outcome_id=finalized.outcome_id,
                replayed=True,
            )

        admission = self._runtime.admit(task_id)
        # Rebuild the complete proposal and successor binding after admission.
        # A change between preflight and the start transaction must not be
        # recorded as if the original proposal were still current.
        try:
            with self._session_factory() as session:
                task = session.get(Task, task_id)
                if task is None:
                    raise TaskNotEligible("task_not_found")
                validate_lifecycle_task_request(
                    session,
                    task,
                    self._session_factory,
                    self._snapshot_store,
                    require_proposed=True,
                )
        except KnowledgeLifecycleAssessmentError as error:
            failed = self._finalize_failure(
                task_id, admission.attempt_count, error.reason
            )
            return KnowledgeLifecycleTaskRunResult(
                task_id=task_id,
                status=failed.status,
                assessment_id=None,
                assessment_result=None,
                outcome_id=failed.outcome_id,
            )

        try:
            recorded = self._task.record(task_id)
        except KnowledgeLifecycleAssessmentError as error:
            failed = self._finalize_failure(
                task_id, admission.attempt_count, error.reason
            )
            return KnowledgeLifecycleTaskRunResult(
                task_id=task_id,
                status=failed.status,
                assessment_id=None,
                assessment_result=None,
                outcome_id=failed.outcome_id,
            )

        finalized = self._runtime.finalize(
            TerminalObservation(
                task_id=task_id,
                attempt=admission.attempt_count,
                result_category="success_knowledge_lifecycle_assessed",
                observed_at=recorded.recorded_at,
                knowledge_lifecycle_assessment_id=recorded.assessment_id,
            )
        )
        return KnowledgeLifecycleTaskRunResult(
            task_id=task_id,
            status=finalized.status,
            assessment_id=recorded.assessment_id,
            assessment_result=recorded.assessment_result,
            outcome_id=finalized.outcome_id,
            replayed=recorded.replayed,
        )

    @staticmethod
    def _request_learning_change_id(session: Session, task: Task) -> UUID:
        from core.knowledge_lifecycle import REQUEST_EVENT_TYPE

        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == REQUEST_EVENT_TYPE,
                )
            )
        )
        if len(events) != 1 or not isinstance(events[0].payload, dict):
            raise TaskNotEligible(
                "knowledge_lifecycle_request_event_invalid"
            )
        try:
            return UUID(events[0].payload["learning_change_id"])
        except (KeyError, TypeError, ValueError) as error:
            raise TaskNotEligible(
                "knowledge_lifecycle_learning_change_id_invalid"
            ) from error

    @staticmethod
    def _terminal_observation(
        task: Task, assessment: KnowledgeLifecycleAssessment
    ) -> TerminalObservation:
        return TerminalObservation(
            task_id=task.id,
            attempt=task.attempt_count,
            result_category="success_knowledge_lifecycle_assessed",
            observed_at=assessment.recorded_at,
            knowledge_lifecycle_assessment_id=assessment.id,
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

