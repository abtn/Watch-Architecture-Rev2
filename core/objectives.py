"""Task-attributed Objective creation and lifecycle commits."""

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Objective, Task, Team, TeamPolicy

_TRANSITIONS = {
    "draft": frozenset({"active", "cancelled"}),
    "active": frozenset({"paused", "blocked", "completed", "cancelled"}),
    "paused": frozenset({"active", "cancelled"}),
    "blocked": frozenset({"active", "cancelled"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
}
_SUCCESS_EVENTS = frozenset({"objective_created", "objective_transitioned"})


@dataclass(frozen=True)
class ObjectiveResult:
    objective_id: UUID
    status: str
    event_id: UUID
    replayed: bool = False


class ObjectiveValidationError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ObjectiveRejected(ObjectiveValidationError):
    def __init__(self, reason: str, event_id: UUID) -> None:
        super().__init__(reason)
        self.event_id = event_id


class TaskNotFound(RuntimeError):
    """Raised when a mutation cannot be attributed to an existing Task."""


class ObjectiveService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(
        self,
        task_id: UUID,
        team_id: UUID,
        statement: str,
        *,
        operator_id: str | None = None,
    ) -> ObjectiveResult:
        try:
            return self._create(task_id, team_id, statement, operator_id)
        except ObjectiveValidationError as error:
            event_id = self._record_rejection(
                task_id,
                error.reason,
                {
                    "operation": "create_objective",
                    "team_id": str(team_id),
                    "statement": statement,
                    "operator_id": operator_id,
                },
            )
            raise ObjectiveRejected(error.reason, event_id) from error

    def transition(
        self,
        task_id: UUID,
        objective_id: UUID,
        expected_status: str,
        new_status: str,
        *,
        operator_id: str | None = None,
    ) -> ObjectiveResult:
        try:
            return self._transition(
                task_id, objective_id, expected_status, new_status, operator_id
            )
        except ObjectiveValidationError as error:
            event_id = self._record_rejection(
                task_id,
                error.reason,
                {
                    "operation": "transition_objective",
                    "objective_id": str(objective_id),
                    "from_status": expected_status,
                    "to_status": new_status,
                    "operator_id": operator_id,
                },
            )
            raise ObjectiveRejected(error.reason, event_id) from error

    def _create(
        self,
        task_id: UUID,
        team_id: UUID,
        statement: str,
        operator_id: str | None,
    ) -> ObjectiveResult:
        with self._session_factory.begin() as session:
            task = self._lock_task(session, task_id)
            if task is None:
                raise TaskNotFound(f"Task {task_id} does not exist")
            team = self._validate_task(session, task, "create_objective")
            prior = self._prior_success(session, task.id)
            if prior is not None:
                if (
                    prior.type != "objective_created"
                    or prior.payload.get("operation") != "create_objective"
                    or prior.payload.get("team_id") != str(team_id)
                    or prior.payload.get("statement") != statement
                    or prior.payload.get("operator_id") != operator_id
                ):
                    raise ObjectiveValidationError("task_outcome_conflict")
                objective_id = UUID(prior.payload["objective_id"])
                objective = session.scalar(
                    select(Objective)
                    .where(Objective.id == objective_id)
                    .with_for_update()
                )
                if (
                    objective is None
                    or objective.team_id != team.id
                    or objective.team_id != team_id
                    or objective.statement != statement
                ):
                    raise RuntimeError("recorded_objective_creation_corrupt")
                return ObjectiveResult(
                    objective.id, prior.payload["to_status"], prior.id, True
                )

            if team_id != team.id:
                raise ObjectiveValidationError("objective_team_mismatch")
            self._validate_statement(statement)
            objective = Objective(id=uuid4(), team_id=team.id, statement=statement)
            session.add(objective)
            event = self._add_event(
                session,
                task.id,
                "objective_created",
                {
                    "operation": "create_objective",
                    "objective_id": str(objective.id),
                    "team_id": str(team.id),
                    "statement": statement,
                    "from_status": None,
                    "to_status": "draft",
                    "operator_id": operator_id,
                },
            )
            session.flush()
            return ObjectiveResult(objective.id, objective.status, event.id)

    def _transition(
        self,
        task_id: UUID,
        objective_id: UUID,
        expected_status: str,
        new_status: str,
        operator_id: str | None,
    ) -> ObjectiveResult:
        with self._session_factory.begin() as session:
            task = self._lock_task(session, task_id)
            if task is None:
                raise TaskNotFound(f"Task {task_id} does not exist")
            team = self._validate_task(session, task, "transition_objective")
            prior = self._prior_success(session, task.id)
            if prior is not None:
                objective = session.scalar(
                    select(Objective)
                    .where(Objective.id == objective_id)
                    .with_for_update()
                )
                if objective is None:
                    raise ObjectiveValidationError("objective_not_found")
                if objective.team_id != team.id:
                    raise ObjectiveValidationError("objective_team_mismatch")
                if (
                    prior.type != "objective_transitioned"
                    or prior.payload.get("operation") != "transition_objective"
                    or prior.payload.get("objective_id") != str(objective_id)
                    or prior.payload.get("from_status") != expected_status
                    or prior.payload.get("to_status") != new_status
                    or prior.payload.get("operator_id") != operator_id
                ):
                    raise ObjectiveValidationError("task_outcome_conflict")
                return ObjectiveResult(objective_id, new_status, prior.id, True)

            objective = session.scalar(
                select(Objective).where(Objective.id == objective_id).with_for_update()
            )
            if objective is None:
                raise ObjectiveValidationError("objective_not_found")
            if objective.team_id != team.id:
                raise ObjectiveValidationError("objective_team_mismatch")
            if objective.status != expected_status:
                raise ObjectiveValidationError("stale_objective_status")
            if new_status not in _TRANSITIONS.get(expected_status, frozenset()):
                raise ObjectiveValidationError("invalid_objective_transition")

            objective.status = new_status
            event = self._add_event(
                session,
                task.id,
                "objective_transitioned",
                {
                    "operation": "transition_objective",
                    "objective_id": str(objective.id),
                    "from_status": expected_status,
                    "to_status": new_status,
                    "operator_id": operator_id,
                },
            )
            session.flush()
            return ObjectiveResult(objective.id, objective.status, event.id)

    @staticmethod
    def _lock_task(session: Session, task_id: UUID) -> Task | None:
        return session.scalar(select(Task).where(Task.id == task_id).with_for_update())

    @staticmethod
    def _validate_task(session: Session, task: Task, operation: str) -> Team:
        if task.task_type != operation:
            raise ObjectiveValidationError("wrong_task_type")
        if task.status != "running":
            raise ObjectiveValidationError("task_not_running")
        if "Objective" not in task.allowed_writes:
            raise ObjectiveValidationError("write_scope_violation")
        if not ObjectiveService._budget_allows_zero_usage(task.budget):
            raise ObjectiveValidationError("invalid_task_budget")
        team = session.scalar(
            select(Team).where(Team.id == task.team_id).with_for_update(read=True)
        )
        if team is None:
            raise ObjectiveValidationError("team_not_found")
        if team.status != "active":
            raise ObjectiveValidationError("team_not_active")
        policy = session.scalar(
            select(TeamPolicy)
            .where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
            .with_for_update(read=True)
        )
        if policy is None:
            raise ObjectiveValidationError("team_policy_missing")
        return team

    @staticmethod
    def _budget_allows_zero_usage(budget: dict[str, Any]) -> bool:
        if not isinstance(budget, dict):
            return False
        tool_calls = budget.get("max_tool_calls")
        cost = budget.get("max_cost_usd")
        deadline = budget.get("deadline_seconds")
        return (
            isinstance(tool_calls, int)
            and not isinstance(tool_calls, bool)
            and tool_calls >= 0
            and isinstance(cost, (int, float))
            and not isinstance(cost, bool)
            and math.isfinite(cost)
            and cost >= 0
            and isinstance(deadline, int)
            and not isinstance(deadline, bool)
            and deadline > 0
        )

    @staticmethod
    def _validate_statement(statement: str) -> None:
        if not isinstance(statement, str) or not statement.strip():
            raise ObjectiveValidationError("invalid_objective_statement")

    @staticmethod
    def _prior_success(session: Session, task_id: UUID) -> Event | None:
        return session.scalar(
            select(Event)
            .where(Event.task_id == task_id, Event.type.in_(_SUCCESS_EVENTS))
            .order_by(Event.created_at)
            .limit(1)
        )

    @staticmethod
    def _add_event(
        session: Session, task_id: UUID, event_type: str, payload: dict[str, Any]
    ) -> Event:
        event = Event(
            id=uuid4(),
            task_id=task_id,
            type=event_type,
            payload=payload,
            created_at=datetime.now(timezone.utc),
        )
        session.add(event)
        return event

    def _record_rejection(
        self, task_id: UUID, reason: str, details: dict[str, Any]
    ) -> UUID:
        with self._session_factory.begin() as session:
            task = self._lock_task(session, task_id)
            if task is None:
                raise TaskNotFound(f"Task {task_id} does not exist")
            event = self._add_event(
                session,
                task_id,
                "proposal_rejected",
                {"reason": reason, **details},
            )
            session.flush()
            return event.id
