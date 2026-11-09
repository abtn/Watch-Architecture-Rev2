"""B3.4 lifecycle assessment adapter and B3.5 TaskRuntime execution path.

The adapter records only the immutable lifecycle assessment. The TaskRunner
composes it with the existing TaskRuntime; neither component writes
KnowledgeItem or LearningChange.
"""

from __future__ import annotations

from dataclasses import dataclass
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

        TaskRuntime remains the sole owner of admission, attempt fencing,
        terminal state, Outcomes, and lifecycle Events.
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
            try:
                if task.status == "failed":
                    replay_observation = self._replay_failed_task(session, task)
                elif task.status == "done":
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
                    running_assessment = session.scalar(
                        select(KnowledgeLifecycleAssessment).where(
                            KnowledgeLifecycleAssessment.task_id == task.id,
                            KnowledgeLifecycleAssessment.team_id == task.team_id,
                        )
                    )
                    if running_assessment is None:
                        raise TaskNotEligible(
                            "knowledge_lifecycle_task_already_running"
                        )
                    learning_change = session.get(
                        LearningChange, running_assessment.learning_change_id
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
            if self._runtime._is_knowledge_lifecycle_recording_corruption(
                error.reason
            ):
                raise TaskNotEligible(error.reason) from error
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

    def _replay_failed_task(
        self, session: Session, task: Task
    ) -> TerminalObservation:
        """Rebuild a failed terminal observation only from a complete record."""
        if task.task_type != "assess_knowledge_lifecycle":
            raise TaskNotEligible("knowledge_lifecycle_task_wrong_type")

        outcomes = list(
            session.scalars(
                select(Outcome).where(
                    (Outcome.recorded_by_task_id == task.id)
                    | (
                        (Outcome.subject_kind == "task")
                        & (Outcome.subject_id == task.id)
                    )
                )
            )
        )
        if len(outcomes) != 1:
            raise TaskNotEligible("knowledge_lifecycle_terminal_outcome_invalid")
        outcome = outcomes[0]
        if (
            outcome.team_id != task.team_id
            or outcome.subject_kind != "task"
            or outcome.subject_id != task.id
            or outcome.recorded_by_task_id != task.id
            or outcome.outcome_type != "task_execution"
            or outcome.observed_at is None
            or outcome.observation_snapshot_ref is None
            or outcome.observation_hash is None
        ):
            raise TaskNotEligible("knowledge_lifecycle_terminal_outcome_invalid")

        history_events = list(
            session.scalars(
                select(Event)
                .where(
                    Event.task_id == task.id,
                    Event.type.in_(
                        (
                            "task_started",
                            "task_attempt_failed",
                            "task_retry_scheduled",
                            "task_failed",
                        )
                    ),
                )
                .order_by(Event.created_at, Event.id)
            )
        )
        started_by_attempt: dict[int, Event] = {}
        failed_by_attempt: dict[int, Event] = {}
        retry_by_attempt: dict[int, Event] = {}
        terminal_events: list[Event] = []
        for event in history_events:
            event_payload = event.payload
            if not isinstance(event_payload, dict):
                raise TaskNotEligible(
                    "knowledge_lifecycle_terminal_events_invalid"
                )
            if event.type == "task_failed":
                terminal_events.append(event)
                continue
            attempt = event_payload.get("attempt_count")
            if (
                isinstance(attempt, bool)
                or not isinstance(attempt, int)
                or attempt < 1
            ):
                raise TaskNotEligible(
                    "knowledge_lifecycle_terminal_events_invalid"
                )
            destination = {
                "task_started": started_by_attempt,
                "task_attempt_failed": failed_by_attempt,
                "task_retry_scheduled": retry_by_attempt,
            }[event.type]
            if attempt in destination:
                raise TaskNotEligible(
                    "knowledge_lifecycle_terminal_events_invalid"
                )
            destination[attempt] = event

        if (
            len(terminal_events) != 1
            or set(started_by_attempt) != set(range(1, task.attempt_count + 1))
            or set(failed_by_attempt)
            != set(range(1, task.attempt_count + 1))
            or set(retry_by_attempt) != set(range(1, task.attempt_count))
        ):
            raise TaskNotEligible("knowledge_lifecycle_terminal_events_invalid")

        start_fields = {"from_status", "to_status", "attempt_count"}
        retry_fields = {
            "from_status",
            "to_status",
            "attempt_count",
            "result_category",
            "failure_reason",
        }
        for attempt in range(1, task.attempt_count + 1):
            started = started_by_attempt[attempt]
            started_payload = started.payload
            if (
                set(started_payload) != start_fields
                or started_payload.get("from_status") != "pending"
                or started_payload.get("to_status") != "running"
                or started_payload.get("attempt_count") != attempt
            ):
                raise TaskNotEligible(
                    "knowledge_lifecycle_terminal_events_invalid"
                )
            failed = failed_by_attempt[attempt]
            if attempt < task.attempt_count:
                retry = retry_by_attempt[attempt]
                retry_payload = retry.payload
                if (
                    set(failed.payload) != retry_fields
                    or failed.payload.get("from_status") != "running"
                    or failed.payload.get("to_status") != "pending"
                    or failed.payload.get("result_category")
                    != "retryable_failure"
                    or not isinstance(failed.payload.get("failure_reason"), str)
                    or not failed.payload["failure_reason"].strip()
                    or retry_payload != failed.payload
                    or not (
                        started.created_at
                        <= failed.created_at
                        <= retry.created_at
                        <= started_by_attempt[attempt + 1].created_at
                    )
                ):
                    raise TaskNotEligible(
                        "knowledge_lifecycle_terminal_events_invalid"
                    )
            elif failed.payload.get("attempt_count") != task.attempt_count:
                raise TaskNotEligible(
                    "knowledge_lifecycle_terminal_events_invalid"
                )

        terminal_attempt_failed = failed_by_attempt[task.attempt_count]
        terminal_event = terminal_events[0]
        payload = terminal_event.payload
        expected_fields = {
            "from_status",
            "to_status",
            "attempt_count",
            "result_category",
            "failure_reason",
            "outcome_id",
            "observation_snapshot_ref",
            "observation_hash",
        }
        if (
            not isinstance(payload, dict)
            or set(payload) != expected_fields
            or payload.get("from_status") != "running"
            or payload.get("to_status") != "failed"
            or payload.get("result_category") != "terminal_failure"
            or payload.get("attempt_count") != task.attempt_count
            or isinstance(payload.get("attempt_count"), bool)
            or not isinstance(payload.get("failure_reason"), str)
            or not payload["failure_reason"].strip()
            or payload.get("outcome_id") != str(outcome.id)
            or payload.get("observation_snapshot_ref")
            != outcome.observation_snapshot_ref
            or payload.get("observation_hash") != outcome.observation_hash
            or terminal_attempt_failed.payload != payload
            or not (
                started_by_attempt[task.attempt_count].created_at
                <= terminal_attempt_failed.created_at
                <= terminal_event.created_at
            )
            or terminal_attempt_failed.created_at < outcome.observed_at
            or terminal_event.created_at < outcome.observed_at
        ):
            raise TaskNotEligible("knowledge_lifecycle_terminal_events_invalid")

        return TerminalObservation(
            task_id=task.id,
            attempt=task.attempt_count,
            result_category="terminal_failure",
            observed_at=outcome.observed_at,
            failure_reason=payload["failure_reason"],
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
        with self._session_factory() as session:
            task = session.get(Task, task_id)
            if (
                task is None
                or task.status != "running"
                or task.attempt_count != attempt
            ):
                raise TaskNotEligible(
                    "knowledge_lifecycle_failure_attempt_stale"
                )
            started_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task_id,
                        Event.type == "task_started",
                        Event.payload["attempt_count"].as_integer() == attempt,
                    )
                )
            )
            if (
                len(started_events) != 1
                or started_events[0].payload
                != {
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": attempt,
                }
            ):
                raise TaskNotEligible(
                    "knowledge_lifecycle_task_start_event_invalid"
                )
            observed_at = started_events[0].created_at
        return self._runtime.finalize(
            TerminalObservation(
                task_id=task_id,
                attempt=attempt,
                result_category="terminal_failure",
                observed_at=observed_at,
                failure_reason=reason,
            )
        )
