"""Application-controlled Task admission and terminal finalization."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Outcome, PlanAction, Task, Team, TeamPolicy
from core.objectives import ObjectiveService, TaskNotFound
from core.policy import InvalidPolicyError, daily_task_quota
from core.snapshot_store import SnapshotStore
from core.state_assessment import _canonical_json, _timestamp

_TERMINAL_EVENTS = ("task_completed", "task_failed")
_TERMINAL_STATUSES = frozenset({"done", "failed"})
_SUCCESS_CATEGORIES = frozenset({"success_signal_created", "success_no_change"})
_RESULT_CATEGORIES = _SUCCESS_CATEGORIES | {"terminal_failure"}


@dataclass(frozen=True)
class AdmissionResult:
    task_id: UUID
    attempt_count: int
    event_id: UUID
    replayed: bool = False


@dataclass(frozen=True)
class SignalEvidence:
    """One Signal's contribution to a terminal observation."""

    signal_id: UUID
    snapshot_ref: str
    content_hash: str


@dataclass(frozen=True)
class TerminalObservation:
    """A deterministic terminal observation for a `task_execution` Outcome."""

    task_id: UUID
    attempt: int
    result_category: Literal[
        "success_signal_created", "success_no_change", "terminal_failure"
    ]
    observed_at: datetime
    signals: tuple[SignalEvidence, ...] = ()
    failure_reason: str | None = None


@dataclass(frozen=True)
class FinalizationResult:
    task_id: UUID
    status: str
    attempt_count: int
    event_ids: tuple[UUID, ...]
    outcome_id: UUID
    replayed: bool = False


class TaskNotEligible(ValueError):
    pass


class TaskNotFinalizable(ValueError):
    """Raised when a terminal finalization request is invalid or stale."""


class TaskRuntime:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store

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

    def finalize(self, observation: TerminalObservation) -> FinalizationResult:
        """Commit one terminal `task_execution` Outcome for a running Task.

        The Outcome, terminal Task status, `completed_at`, and terminal Events
        commit in one transaction. Attempt-number fencing rejects stale results.
        """
        self._validate_observation(observation)
        payload = self._observation_payload(observation)
        content = _canonical_json(payload).encode("utf-8")

        # Snapshot storage is content-addressed and immutable, so writing it
        # before the transaction is safe: a failed commit may leave an
        # unreferenced object, and a retry reuses it (ADR-0030 §4).
        snapshot_ref, observation_hash = self._store_snapshot(content)

        with self._session_factory.begin() as session:
            task = ObjectiveService._lock_task(session, observation.task_id)
            if task is None:
                raise TaskNotFound(f"Task {observation.task_id} does not exist")

            prior = self._prior_terminal(session, task.id)
            if prior is not None:
                return self._replay(session, task, prior, payload, observation)

            # A terminal Task without its Outcome is the invariant violation
            # ADR-0030 §4 forbids, not an ordinary eligibility failure.
            if task.status in _TERMINAL_STATUSES:
                raise TaskNotFinalizable("recorded_terminal_outcome_corrupt")
            if task.status != "running":
                raise TaskNotFinalizable("task_not_running")
            if observation.attempt != task.attempt_count:
                raise TaskNotFinalizable("stale_attempt")

            outcome = Outcome(
                id=uuid4(),
                team_id=task.team_id,
                subject_kind="task",
                subject_id=task.id,
                outcome_type="task_execution",
                expected=None,
                observation_snapshot_ref=snapshot_ref,
                observation_hash=observation_hash,
                observed_at=observation.observed_at,
                recorded_by_task_id=task.id,
            )
            session.add(outcome)

            event_types = (
                ("task_completed",)
                if observation.result_category in _SUCCESS_CATEGORIES
                else ("task_attempt_failed", "task_failed")
            )
            events = [
                ObjectiveService._add_event(
                    session,
                    task.id,
                    event_type,
                    {
                        "from_status": "running",
                        "to_status": (
                            "done"
                            if observation.result_category in _SUCCESS_CATEGORIES
                            else "failed"
                        ),
                        "attempt_count": task.attempt_count,
                        "result_category": observation.result_category,
                        "failure_reason": observation.failure_reason,
                        "outcome_id": str(outcome.id),
                        "observation_snapshot_ref": snapshot_ref,
                        "observation_hash": observation_hash,
                    },
                )
                for event_type in event_types
            ]

            if observation.result_category in _SUCCESS_CATEGORIES:
                task.status = "done"
                task.completed_at = observation.observed_at
            else:
                task.status = "failed"
                task.completed_at = None

            session.flush()

            return FinalizationResult(
                task_id=task.id,
                status=task.status,
                attempt_count=task.attempt_count,
                event_ids=tuple(event.id for event in events),
                outcome_id=outcome.id,
            )

    @staticmethod
    def _validate_observation(observation: TerminalObservation) -> None:
        if observation.result_category not in _RESULT_CATEGORIES:
            raise TaskNotFinalizable("invalid_result_category")
        if observation.observed_at.tzinfo is None or (
            observation.observed_at.utcoffset() is None
        ):
            raise TaskNotFinalizable("observed_at_not_timezone_aware")
        if isinstance(observation.attempt, bool) or observation.attempt < 1:
            raise TaskNotFinalizable("invalid_attempt")

        if observation.result_category in _SUCCESS_CATEGORIES:
            if observation.failure_reason is not None:
                raise TaskNotFinalizable("failure_reason_not_allowed")
            if observation.result_category == "success_signal_created":
                if not observation.signals:
                    raise TaskNotFinalizable("signal_evidence_required")
            elif observation.signals:
                raise TaskNotFinalizable("signal_evidence_not_allowed")
            return

        if not observation.failure_reason or not observation.failure_reason.strip():
            raise TaskNotFinalizable("failure_reason_required")
        if observation.signals:
            raise TaskNotFinalizable("signal_evidence_not_allowed")

    @staticmethod
    def _observation_payload(observation: TerminalObservation) -> dict[str, Any]:
        return {
            "attempt": observation.attempt,
            "failure_reason": observation.failure_reason,
            "observed_at": _timestamp(observation.observed_at),
            "result_category": observation.result_category,
            "signals": [
                {
                    "content_hash": evidence.content_hash,
                    "signal_id": str(evidence.signal_id),
                    "snapshot_ref": evidence.snapshot_ref,
                }
                for evidence in observation.signals
            ],
        }

    def _store_snapshot(self, content: bytes) -> tuple[str, str]:
        if self._snapshot_store is None:
            raise TaskNotFinalizable("snapshot_store_not_configured")
        return self._snapshot_store.put(content)

    @staticmethod
    def _prior_terminal(session: Session, task_id: UUID) -> Outcome | None:
        return session.scalar(
            select(Outcome).where(
                Outcome.recorded_by_task_id == task_id,
                Outcome.outcome_type == "task_execution",
            )
        )

    def _replay(
        self,
        session: Session,
        task: Task,
        prior: Outcome,
        payload: dict[str, Any],
        observation: TerminalObservation,
    ) -> FinalizationResult:
        """Return the committed terminal result, or reject a conflict."""
        if prior.observation_snapshot_ref is None:
            raise TaskNotFinalizable("recorded_terminal_outcome_corrupt")
        stored = self._snapshot_store.read(prior.observation_snapshot_ref)  # type: ignore[union-attr]
        if _canonical_json(payload).encode("utf-8") != stored:
            raise TaskNotFinalizable("task_outcome_conflict")

        expected_status = (
            "done"
            if observation.result_category in _SUCCESS_CATEGORIES
            else "failed"
        )
        if task.status != expected_status:
            raise TaskNotFinalizable("recorded_terminal_outcome_corrupt")

        expected_types = (
            ("task_completed",)
            if expected_status == "done"
            else ("task_attempt_failed", "task_failed")
        )
        # Both failure Events may share a timestamp, so match by type rather
        # than relying on insertion order.
        by_type: dict[str, Event] = {}
        for event in session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type.in_(_TERMINAL_EVENTS + ("task_attempt_failed",)),
            )
        ):
            if event.type in by_type:
                raise TaskNotFinalizable("recorded_terminal_events_corrupt")
            by_type[event.type] = event
        if set(by_type) != set(expected_types):
            raise TaskNotFinalizable("recorded_terminal_events_corrupt")

        return FinalizationResult(
            task_id=task.id,
            status=task.status,
            attempt_count=task.attempt_count,
            event_ids=tuple(by_type[name].id for name in expected_types),
            outcome_id=prior.id,
            replayed=True,
        )

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