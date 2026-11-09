"""B3.4 Task-side adapter for deterministic lifecycle assessment.

TaskRuntime admission/finalization/recovery activation is deliberately deferred
to B3.5. This adapter owns only the lifecycle request contract and assessment
recording boundary; it never writes KnowledgeItem or LearningChange.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from core.knowledge_lifecycle import (
    KnowledgeLifecycleAssessmentResult,
    KnowledgeLifecycleAssessmentService,
    LifecycleTaskContext,
    validate_lifecycle_task_request,
)
from core.models import Task
from core.snapshot_store import SnapshotStore


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

    def validate(self, task_id: UUID) -> LifecycleTaskContext:
        """Validate the persisted request before a worker is allowed to run."""
        with self._session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise ValueError("knowledge_lifecycle_task_not_found")
            return validate_lifecycle_task_request(
                session,
                task,
                self._session_factory,
                self._snapshot_store,
                require_proposed=True,
            )

    def record(self, task_id: UUID) -> KnowledgeLifecycleAssessmentResult:
        """Record the deterministic assessment for an already-running Task.

        The existing runtime remains the sole owner of Task admission and
        terminal state. B3.5 adds the lifecycle-specific runtime hooks.
        """
        return self._service.record(task_id)
