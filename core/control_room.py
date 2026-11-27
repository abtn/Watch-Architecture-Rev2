"""Session-bound Task creation authority for supported application workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.models import Event, Task


def _create_task(
    session: Session,
    *,
    task_id: UUID,
    team_id: UUID,
    task_type: str,
    policy_version: int,
    allowed_writes: list[str],
    budget: dict[str, Any],
    max_attempts: int,
    objective_id: UUID | None = None,
    plan_id: UUID | None = None,
    plan_action_id: UUID | None = None,
    request_event_type: str | None = None,
    request_event_payload: dict[str, Any] | None = None,
    flush: bool = True,
) -> Task:
    task = Task(
        id=task_id,
        team_id=team_id,
        task_type=task_type,
        status="pending",
        attempt_count=0,
        policy_version=policy_version,
        objective_id=objective_id,
        plan_id=plan_id,
        plan_action_id=plan_action_id,
        allowed_writes=list(allowed_writes),
        budget=dict(budget),
        completed_at=None,
        max_attempts=max_attempts,
    )
    session.add(task)
    if flush:
        session.flush()
    if request_event_type is not None:
        if request_event_payload is None:
            raise ValueError("request_event_payload_required")
        session.add(
            Event(
                id=uuid4(),
                task_id=task_id,
                type=request_event_type,
                payload=request_event_payload,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.flush()
    return task


def create_update_thread_task(
    session: Session,
    *,
    task_id: UUID,
    team_id: UUID,
    policy_version: int,
    event_payload: dict[str, Any],
) -> UUID | None:
    from core.update_thread import (
        ALLOWED_WRITES,
        MAX_ATTEMPTS,
        REQUEST_EVENT_TYPE,
        TASK_BUDGET,
        TASK_TYPE,
    )

    inserted_id = session.scalar(
        pg_insert(Task)
        .values(
            id=task_id,
            team_id=team_id,
            task_type=TASK_TYPE,
            status="pending",
            attempt_count=0,
            policy_version=policy_version,
            objective_id=None,
            plan_id=None,
            plan_action_id=None,
            allowed_writes=list(ALLOWED_WRITES),
            budget=dict(TASK_BUDGET),
            completed_at=None,
            max_attempts=MAX_ATTEMPTS,
        )
        .on_conflict_do_nothing(index_elements=[Task.id])
        .returning(Task.id)
    )
    if inserted_id is not None:
        session.add(
            Event(
                id=uuid4(),
                task_id=task_id,
                type=REQUEST_EVENT_TYPE,
                payload=event_payload,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.flush()
    return inserted_id


def create_approve_learning_change_task(
    session: Session,
    *,
    task_id: UUID,
    team_id: UUID,
    policy_version: int,
    event_payload: dict[str, Any],
) -> UUID | None:
    inserted_id = session.scalar(
        pg_insert(Task)
        .values(
            id=task_id,
            team_id=team_id,
            task_type="approve_learning_change",
            status="pending",
            attempt_count=0,
            policy_version=policy_version,
            objective_id=None,
            plan_id=None,
            plan_action_id=None,
            allowed_writes=["LearningChange", "KnowledgeItem"],
            budget={"max_tool_calls": 0, "max_cost_usd": 0.0},
            completed_at=None,
            max_attempts=3,
        )
        .on_conflict_do_nothing(index_elements=[Task.id])
        .returning(Task.id)
    )
    if inserted_id is not None:
        session.add(
            Event(
                id=uuid4(),
                task_id=task_id,
                type="operator_task_requested",
                payload=event_payload,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.flush()
    return inserted_id


def create_operator_update_task(
    session: Session,
    *,
    task_id: UUID,
    team_id: UUID,
    policy_version: int,
    event_payload: dict[str, Any],
) -> Task:
    from core.world_memory import (
        ALLOWED_WRITES,
        MAX_ATTEMPTS,
        REQUEST_EVENT_TYPE,
        TASK_BUDGET,
        TASK_TYPE,
    )

    return _create_task(
        session,
        task_id=task_id,
        team_id=team_id,
        task_type=TASK_TYPE,
        policy_version=policy_version,
        allowed_writes=ALLOWED_WRITES,
        budget=TASK_BUDGET,
        max_attempts=MAX_ATTEMPTS,
        request_event_type=REQUEST_EVENT_TYPE,
        request_event_payload=event_payload,
    )


def create_ingest_source_task(
    session: Session,
    *,
    team_id: UUID,
    objective_id: UUID,
    plan_id: UUID,
    plan_action_id: UUID,
    policy_version: int,
) -> Task:
    return _create_task(
        session,
        task_id=uuid4(),
        team_id=team_id,
        task_type="ingest_source",
        policy_version=policy_version,
        objective_id=objective_id,
        plan_id=plan_id,
        plan_action_id=plan_action_id,
        allowed_writes=["Signal"],
        budget={
            "max_tool_calls": 0,
            "max_cost_usd": 0.0,
            "deadline_seconds": 60,
        },
        max_attempts=3,
        flush=False,
    )


def create_assess_knowledge_quality_task(
    session: Session,
    *,
    task_id: UUID,
    team_id: UUID,
    policy_version: int,
    event_payload: dict[str, Any],
) -> Task:
    from core.knowledge_quality import (
        ALLOWED_WRITES,
        REQUEST_EVENT_TYPE,
        TASK_BUDGET,
        TASK_MAX_ATTEMPTS,
        TASK_TYPE,
    )

    return _create_task(
        session,
        task_id=task_id,
        team_id=team_id,
        task_type=TASK_TYPE,
        policy_version=policy_version,
        allowed_writes=ALLOWED_WRITES,
        budget=TASK_BUDGET,
        max_attempts=TASK_MAX_ATTEMPTS,
        request_event_type=REQUEST_EVENT_TYPE,
        request_event_payload=event_payload,
    )


def create_assess_knowledge_revalidation_task(
    session: Session,
    *,
    task_id: UUID,
    team_id: UUID,
    policy_version: int,
    event_payload: dict[str, Any],
) -> Task:
    from core.knowledge_revalidation import (
        ALLOWED_WRITES,
        REQUEST_EVENT_TYPE,
        TASK_BUDGET,
        TASK_MAX_ATTEMPTS,
        TASK_TYPE,
    )

    return _create_task(
        session,
        task_id=task_id,
        team_id=team_id,
        task_type=TASK_TYPE,
        policy_version=policy_version,
        allowed_writes=ALLOWED_WRITES,
        budget=TASK_BUDGET,
        max_attempts=TASK_MAX_ATTEMPTS,
        request_event_type=REQUEST_EVENT_TYPE,
        request_event_payload=event_payload,
    )


def create_assess_knowledge_lifecycle_task(
    session: Session,
    *,
    task_id: UUID,
    team_id: UUID,
    policy_version: int,
    event_payload: dict[str, Any],
) -> Task:
    from core.knowledge_lifecycle import (
        ALLOWED_WRITES,
        REQUEST_EVENT_TYPE,
        TASK_BUDGET,
        TASK_MAX_ATTEMPTS,
        TASK_TYPE,
    )

    return _create_task(
        session,
        task_id=task_id,
        team_id=team_id,
        task_type=TASK_TYPE,
        policy_version=policy_version,
        allowed_writes=ALLOWED_WRITES,
        budget=TASK_BUDGET,
        max_attempts=TASK_MAX_ATTEMPTS,
        request_event_type=REQUEST_EVENT_TYPE,
        request_event_payload=event_payload,
    )


def create_evaluate_outcome_task(
    session: Session,
    *,
    task_id: UUID,
    team_id: UUID,
    policy_version: int,
    event_payload: dict[str, Any],
) -> Task:
    from core.task_runtime import (
        _EVALUATION_ALLOWED_WRITES,
        _EVALUATION_MAX_ATTEMPTS,
        _EVALUATION_REQUEST_EVENT_TYPE,
        _EVALUATION_TASK_TYPE,
        _R6G_EVALUATION_BUDGET,
    )

    return _create_task(
        session,
        task_id=task_id,
        team_id=team_id,
        task_type=_EVALUATION_TASK_TYPE,
        policy_version=policy_version,
        allowed_writes=_EVALUATION_ALLOWED_WRITES,
        budget=_R6G_EVALUATION_BUDGET,
        max_attempts=_EVALUATION_MAX_ATTEMPTS,
        request_event_type=_EVALUATION_REQUEST_EVENT_TYPE,
        request_event_payload=event_payload,
    )
