"""Application-controlled Task admission at the existing runtime boundary."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, PlanAction, Task, Team, TeamPolicy
from core.objectives import ObjectiveService, TaskNotFound
from core.policy import InvalidPolicyError, daily_task_quota


@dataclass(frozen=True)
class AdmissionResult:
    task_id: UUID
    attempt_count: int
    event_id: UUID
    replayed: bool = False


class TaskNotEligible(ValueError):
    pass


class TaskRuntime:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def admit(self, task_id: UUID) -> AdmissionResult:
        with self._session_factory.begin() as session:
            task = ObjectiveService._lock_task(session, task_id)
            if task is None:
                raise TaskNotFound(f"Task {task_id} does not exist")

            if task.status != "pending":
                raise TaskNotEligible("task_not_pending")

            self._require_prerequisites(session, task)

            # Serialize admissions for this Team. A shared/read lock would
            # allow concurrent admissions to count the same remaining quota.
            team = session.scalar(
                select(Team)
                .where(Team.id == task.team_id)
                .with_for_update()
            )
            if team is None:
                raise TaskNotEligible("team_not_found")

            if team.status != "active" and task.task_type not in {
                "create_team",
                "configure_team",
                "activate_team",
            }:
                raise TaskNotEligible("team_not_active")

            policy = session.scalar(
                select(TeamPolicy)
                .where(
                    TeamPolicy.team_id == task.team_id,
                    TeamPolicy.version == task.policy_version,
                )
                .with_for_update(read=True)
            )
            if policy is None:
                raise TaskNotEligible("team_policy_missing")

            if not isinstance(task.budget, dict):
                raise TaskNotEligible("invalid_task_budget")

            for field, kind, lower_bound in (
                ("max_tool_calls", int, 0),
                ("max_cost_usd", (int, float), 0),
                ("deadline_seconds", int, 1),
            ):
                value = task.budget.get(field)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, kind)
                    or value < lower_bound
                ):
                    raise TaskNotEligible("invalid_task_budget")

            # A missing daily quota preserves the existing unlimited behavior.
            # If the quota is explicitly configured, validate it strictly.
            # The same parser is used by the Plan boundary so that both
            # agree on which quota configurations are valid.
            try:
                daily_limit = daily_task_quota(policy.rules)
            except InvalidPolicyError as error:
                raise TaskNotEligible(str(error)) from error

            admission_time: datetime | None = None

            if daily_limit is not None:
                # Use one timestamp for both the quota window and this
                # successful start Event, avoiding UTC-midnight boundary drift.
                admission_time = datetime.now(timezone.utc)
                day_start = admission_time.replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                next_day_start = day_start + timedelta(days=1)

                started_count = session.scalar(
                    select(func.count(Event.id))
                    .join(Task, Task.id == Event.task_id)
                    .where(
                        Task.team_id == task.team_id,
                        Event.type == "task_started",
                        Event.created_at >= day_start,
                        Event.created_at < next_day_start,
                    )
                ) or 0

                if started_count >= daily_limit:
                    raise TaskNotEligible(
                        "team_daily_task_quota_exhausted"
                    )

            # All changes below belong to the same transaction as the quota
            # check. If admission fails or commit raises, they roll back.
            task.status = "running"
            task.attempt_count += 1

            event = ObjectiveService._add_event(
                session,
                task.id,
                "task_started",
                {
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": task.attempt_count,
                },
            )

            if admission_time is not None:
                event.created_at = admission_time

            session.flush()

            return AdmissionResult(task.id, task.attempt_count, event.id)

    @staticmethod
    def _require_prerequisites(session: Session, task: Task) -> None:
        if task.plan_id is None:
            if task.plan_action_id is not None:
                raise TaskNotEligible("plan_action_without_plan")
            return

        if task.plan_action_id is None:
            raise TaskNotEligible("plan_action_not_found")

        current = session.get(PlanAction, (task.plan_id, task.plan_action_id))
        if (
            current is None
            or not isinstance(current.action, dict)
            or current.action.get("id") != str(current.action_id)
        ):
            raise TaskNotEligible("plan_action_not_found")

        prerequisites = current.action.get("prerequisites")
        if not isinstance(prerequisites, list):
            raise TaskNotEligible("invalid_plan_action_prerequisites")

        for action_id in prerequisites:
            try:
                action_id = UUID(action_id)
            except (TypeError, ValueError) as error:
                raise TaskNotEligible(
                    "invalid_plan_action_prerequisites"
                ) from error

            prerequisite = session.get(PlanAction, (task.plan_id, action_id))

            predecessor = session.scalar(
                select(Task)
                .where(
                    Task.plan_id == task.plan_id,
                    Task.plan_action_id == action_id,
                )
                .with_for_update(read=True)
            )

            if (
                prerequisite is None
                or not isinstance(prerequisite.action, dict)
                or prerequisite.action.get("id") != str(action_id)
                or predecessor is None
                or predecessor.status != "done"
            ):
                raise TaskNotEligible("plan_prerequisite_not_done")