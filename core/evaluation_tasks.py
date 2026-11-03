"""Narrow D9 evaluator Task runner; TaskRuntime retains lifecycle authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.evaluations import EvaluationService
from core.models import Evaluation, Event, Outcome, Task
from core.rule_evaluator import IngestSourceRuleEvaluator, RuleEvaluationError
from core.snapshot_store import SnapshotStore
from core.task_runtime import (
    TaskNotEligible,
    TaskNotFinalizable,
    TaskRuntime,
    TerminalObservation,
)


@dataclass(frozen=True)
class EvaluationTaskRunResult:
    task_id: UUID
    status: str
    evaluation_id: UUID | None
    outcome_id: UUID | None
    replayed: bool = False


class RuleEvaluationTaskRunner:
    """Execute one already-enqueued D9 Task; this is not a dispatcher."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
        runtime: TaskRuntime | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store
        self._runtime = runtime or TaskRuntime(session_factory, snapshot_store)
        self._evaluator = IngestSourceRuleEvaluator(
            session_factory, snapshot_store
        )
        self._evaluations = EvaluationService(session_factory, snapshot_store)

    def run(self, task_id: UUID) -> EvaluationTaskRunResult:
        """Run one pending evaluator Task or replay a completed one."""
        with self._session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise TaskNotEligible("task_not_found")
            try:
                TaskRuntime._validate_evaluation_task_request(session, task)
            except TaskNotFinalizable as error:
                raise TaskNotEligible(str(error)) from error

            if task.status == "done":
                observation = self._runtime._committed_evaluation_observation(
                    session, task
                )
                if observation is None:
                    raise TaskNotEligible("completed_evaluation_task_result_missing")
                evaluation_id = observation.evaluation_id
            elif task.status == "failed":
                outcome = session.scalar(
                    select(Outcome).where(
                        Outcome.recorded_by_task_id == task.id,
                        Outcome.outcome_type == "task_execution",
                    )
                )
                return EvaluationTaskRunResult(
                    task_id=task.id,
                    status="failed",
                    evaluation_id=None,
                    outcome_id=outcome.id if outcome is not None else None,
                    replayed=True,
                )
            elif task.status == "pending":
                observation = None
                evaluation_id = None
            else:
                raise TaskNotEligible("evaluation_task_already_running")

        if observation is not None:
            replay = self._runtime.finalize(observation)
            return EvaluationTaskRunResult(
                task_id=task_id,
                status=replay.status,
                evaluation_id=evaluation_id,
                outcome_id=replay.outcome_id,
                replayed=True,
            )

        admission = self._runtime.admit(task_id)
        try:
            draft = self._evaluator.evaluate(task_id)
        except RuleEvaluationError as error:
            started_at = self._attempt_started_at(task_id, admission.attempt_count)
            failed = self._runtime.finalize(
                TerminalObservation(
                    task_id=task_id,
                    attempt=admission.attempt_count,
                    result_category="terminal_failure",
                    observed_at=started_at,
                    failure_reason=error.reason,
                )
            )
            return EvaluationTaskRunResult(
                task_id=task_id,
                status=failed.status,
                evaluation_id=None,
                outcome_id=failed.outcome_id,
            )

        proposed = self._evaluations.propose(
            task_id,
            draft,
            evaluator_kind="rule",
            evaluator_identity="watch.r6g.ingest-source-rules",
            evaluator_revision="1",
        )
        recorded = self._evaluations.record(task_id, proposed.evaluation_id)
        if recorded.status != "recorded":
            raise TaskNotFinalizable("evaluation_not_recorded")

        finalized = self._runtime.finalize(
            TerminalObservation(
                task_id=task_id,
                attempt=admission.attempt_count,
                result_category="success_evaluation_recorded",
                observed_at=self._attempt_started_at(
                    task_id, admission.attempt_count
                ),
                evaluation_id=proposed.evaluation_id,
            )
        )
        return EvaluationTaskRunResult(
            task_id=task_id,
            status=finalized.status,
            evaluation_id=proposed.evaluation_id,
            outcome_id=finalized.outcome_id,
        )

    def _attempt_started_at(self, task_id: UUID, attempt: int) -> datetime:
        with self._session_factory() as session:
            created_at = session.scalar(
                select(Event.created_at).where(
                    Event.task_id == task_id,
                    Event.type == "task_started",
                    Event.payload["attempt_count"].as_integer() == attempt,
                )
            )
        if created_at is None or created_at.tzinfo is None:
            raise TaskNotFinalizable("evaluation_task_start_event_missing")
        return created_at
