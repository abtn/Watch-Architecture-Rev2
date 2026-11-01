"""Application-controlled Task admission, failure reporting, and finalization."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Evaluation, Event, Outcome, PlanAction, Task, Team, TeamPolicy
from core.objectives import ObjectiveService, TaskNotFound
from core.policy import InvalidPolicyError, daily_task_quota
from core.snapshot_store import SnapshotStore
from core.state_assessment import _canonical_json, _timestamp

_TERMINAL_EVENTS = ("task_completed", "task_failed")
_RETRY_EVENTS = ("task_attempt_failed", "task_retry_scheduled")
_TERMINAL_STATUSES = frozenset({"done", "failed"})
_EVALUATION_SUCCESS_CATEGORIES = frozenset({"success_evaluation_recorded",
    "success_evaluation_rejected"})
_SUCCESS_CATEGORIES = frozenset({"success_signal_created",
    "success_no_change"}) | _EVALUATION_SUCCESS_CATEGORIES
_RESULT_CATEGORIES = _SUCCESS_CATEGORIES | {"terminal_failure"}

# ADR-0030 §2: a `running` Task whose latest `task_started` Event is older than
# this is interrupted. The comparison is strict, so a start exactly at the
# boundary is not yet stale.
_INTERRUPTION_AGE = timedelta(seconds=60)
_INTERRUPTION_REASON = "interrupted_execution"

# Recovery resolves per-Task races into its result instead of aborting the whole
# scan, so one Task another caller already advanced cannot block dispatcher
# startup. These are the finalization reasons that describe a lost race rather
# than recorded-state corruption; corruption and conflicts propagate unchanged.
_SKIPPED_FINALIZATION_REASONS = frozenset({"stale_attempt", "task_not_running"})


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
        "success_signal_created", "success_no_change", "success_evaluation_recorded",
        "success_evaluation_rejected", "terminal_failure"
    ]
    observed_at: datetime
    signals: tuple[SignalEvidence, ...] = ()
    failure_reason: str | None = None
    evaluation_id: UUID | None = None


@dataclass(frozen=True)
class FinalizationResult:
    task_id: UUID
    status: str
    attempt_count: int
    event_ids: tuple[UUID, ...]
    outcome_id: UUID
    replayed: bool = False


@dataclass(frozen=True)
class FailureObservation:
    """One worker-reported attempt failure.

    `retryable` is the caller's transport-level classification; `TaskRuntime`
    decides only whether the retry limit permits another start. `reason` is
    recorded verbatim, because accepted documents require a categorized reason
    but prescribe no closed failure-reason vocabulary.
    """

    task_id: UUID
    attempt: int
    observed_at: datetime
    reason: str
    retryable: bool


@dataclass(frozen=True)
class FailureResult:
    """The outcome of one failure report.

    `retry_scheduled` separates a retry transition from a terminal
    finalization. `terminal` is populated only when an Outcome was created.
    """

    task_id: UUID
    retry_scheduled: bool
    status: str
    attempt_count: int
    event_ids: tuple[UUID, ...]
    terminal: FinalizationResult | None = None


class TaskNotEligible(ValueError):
    pass


class TaskNotFinalizable(ValueError):
    """Raised when a failure report or finalization request is invalid."""


@dataclass(frozen=True)
class InterruptedTask:
    """One `running` Task and the latest start of its current attempt.

    `started_at` is `None` when the current attempt has no `task_started`
    Event. That is inconsistent recorded state, not a stale start, so it is
    reported rather than assigned a fabricated time.
    """

    task_id: UUID
    attempt: int
    started_at: datetime | None


@dataclass(frozen=True)
class RecoveryResult:
    """What one `recover_interrupted()` call actually changed.

    `retried` and `failed` name the Tasks this call transitioned; `skipped`
    names candidates another operation had already advanced past. `inconsistent`
    names `running` Tasks whose current attempt has no usable `task_started`
    Event; they are reported, never mutated.
    """

    retried: tuple[UUID, ...] = ()
    failed: tuple[UUID, ...] = ()
    skipped: tuple[UUID, ...] = ()
    inconsistent: tuple[UUID, ...] = ()


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

            # A Task returned to `pending` by a retry must not be started again
            # once the pinned start limit is reached. Checked before the quota
            # window and before any start side effect, so a rejected exhausted
            # admission consumes nothing (ADR-0030 §1).
            if task.attempt_count >= task.max_attempts:
                raise TaskNotEligible("task_attempts_exhausted")

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
            if observation.result_category in _EVALUATION_SUCCESS_CATEGORIES:
                self._validate_evaluation_result(session, task, observation)
            elif observation.evaluation_id is not None:
                raise TaskNotFinalizable("evaluation_id_not_allowed")

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
                        **({"evaluation_id": str(observation.evaluation_id)} if observation.evaluation_id is not None else {}),  # noqa: E501
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

    def report_failure(self, failure: FailureObservation) -> FailureResult:
        """Record one worker-reported attempt failure.

        A retryable failure with starts remaining returns the Task to `pending`
        with `task_attempt_failed` and `task_retry_scheduled` in one atomic
        transaction, and creates no Outcome or Snapshot. Every other case
        delegates to `finalize()`, the single terminal Outcome path, so the
        terminal Outcome, Snapshot, Events, and status are never written here.

        The retry decision is taken under the Task-row lock, so competing
        reports cannot both schedule a retry or schedule a retry after a
        terminal result has been committed. The decision transaction is
        released before delegating, because writing the observation Snapshot
        must not happen inside an open database transaction; `finalize()`
        revalidates status and attempt under its own lock.
        """
        self._validate_failure(failure)

        with self._session_factory.begin() as session:
            task = ObjectiveService._lock_task(session, failure.task_id)
            if task is None:
                raise TaskNotFound(f"Task {failure.task_id} does not exist")

            terminal_recorded = self._prior_terminal(session, task.id) is not None
            # A retry is possible only for a running Task on the attempt that
            # was admitted, with the pinned start limit not yet reached.
            retry_possible = (
                failure.retryable
                and failure.attempt == task.attempt_count
                and task.attempt_count < task.max_attempts
            )

            # A committed terminal result wins, and a terminal status with no
            # Outcome is recorded-state corruption. Both are reported by the
            # terminal path below, never repaired or retried here.
            if not terminal_recorded and task.status not in _TERMINAL_STATUSES:
                # A Task still `pending` at the reported attempt may already
                # carry the durable retry disposition for that attempt. That is
                # a duplicate report, not a generic non-running state, so it is
                # rejected distinctly and never schedules a second retry.
                if task.status == "pending" and failure.attempt == task.attempt_count:
                    disposition = self._retry_disposition(
                        session, task.id, failure.attempt
                    )
                    if disposition == "corrupt":
                        raise TaskNotFinalizable("recorded_retry_events_corrupt")
                    if disposition == "committed":
                        raise TaskNotFinalizable("retry_already_scheduled")
                if task.status != "running":
                    raise TaskNotFinalizable("task_not_running")
                if failure.attempt != task.attempt_count:
                    raise TaskNotFinalizable("stale_attempt")
                if retry_possible:
                    task.status = "pending"
                    payload = {
                        "from_status": "running",
                        "to_status": "pending",
                        "attempt_count": task.attempt_count,
                        "result_category": "retryable_failure",
                        "failure_reason": failure.reason,
                    }
                    events = [
                        ObjectiveService._add_event(
                            session, task.id, event_type, payload
                        )
                        for event_type in _RETRY_EVENTS
                    ]
                    session.flush()

                    return FailureResult(
                        task_id=task.id,
                        retry_scheduled=True,
                        status=task.status,
                        attempt_count=task.attempt_count,
                        event_ids=tuple(event.id for event in events),
                    )

        # Non-retryable failures, exhausted retries, terminal-state corruption,
        # and repeats of a committed terminal result all resolve through the
        # single Checkpoint 2A finalization path. The decision transaction is
        # released first so no Snapshot write happens inside it.
        terminal = self.finalize(self._terminal_observation(failure))
        return FailureResult(
            task_id=terminal.task_id,
            retry_scheduled=False,
            status=terminal.status,
            attempt_count=terminal.attempt_count,
            event_ids=terminal.event_ids,
            terminal=terminal,
        )

    def recover_interrupted(
        self, *, now: datetime | None = None
    ) -> RecoveryResult:
        """Recover `running` Tasks whose current attempt is stale (ADR-0030 §2).

        A `running` Task whose latest `task_started` Event for its current
        attempt is strictly older than 60 seconds is interrupted. With starts
        remaining it returns to `pending` through the same durable retry
        disposition `report_failure()` uses; with attempts exhausted it
        terminalizes through the single `finalize()` path. This is a
        compare-and-set lifecycle operation on the existing runtime, not a
        second runtime or scheduler.

        Discovery is read-only. Every candidate is rechecked under the Task-row
        lock before any change, so a Task that completed, was re-admitted, or
        was already recovered by another caller is skipped rather than
        overwritten. `now` is injectable so the age comparison is deterministic
        in tests; it defaults to the current UTC time.
        """
        reference = now if now is not None else datetime.now(timezone.utc)
        if reference.tzinfo is None or reference.utcoffset() is None:
            raise TaskNotFinalizable("reference_time_not_timezone_aware")

        retried: list[UUID] = []
        failed: list[UUID] = []
        skipped: list[UUID] = []
        inconsistent: list[UUID] = []

        for candidate in self._interrupted_candidates(reference):
            if candidate.started_at is None:
                # A `running` Task with no start Event for its current attempt
                # is inconsistent recorded state. It is surfaced, never reset
                # or given a fabricated start time.
                inconsistent.append(candidate.task_id)
                continue

            outcome = self._recover_candidate(candidate, reference)
            if outcome == "retried":
                retried.append(candidate.task_id)
            elif outcome == "failed":
                failed.append(candidate.task_id)
            elif outcome == "inconsistent":
                inconsistent.append(candidate.task_id)
            else:
                skipped.append(candidate.task_id)

        return RecoveryResult(
            retried=tuple(retried),
            failed=tuple(failed),
            skipped=tuple(skipped),
            inconsistent=tuple(inconsistent),
        )

    def _interrupted_candidates(self, reference: datetime) -> list[InterruptedTask]:
        """Read-only discovery of `running` Tasks with a stale current attempt.

        The start is matched to the Task's current `attempt_count`, so an older
        start from a previous attempt cannot make a newly admitted attempt look
        stale. A `running` Task with no start for its current attempt is
        returned with `started_at=None` so it is surfaced as inconsistent.
        """
        with self._session_factory() as session:
            current_start = (
                select(
                    Event.task_id.label("task_id"),
                    func.max(Event.created_at).label("started_at"),
                )
                .join(
                    Task,
                    (Task.id == Event.task_id)
                    & (
                        Event.payload["attempt_count"].as_integer()
                        == Task.attempt_count
                    ),
                )
                .where(Event.type == "task_started")
                .group_by(Event.task_id)
                .subquery()
            )
            rows = session.execute(
                select(Task.id, Task.attempt_count, current_start.c.started_at)
                .outerjoin(current_start, current_start.c.task_id == Task.id)
                .where(Task.status == "running")
            ).all()

        candidates: list[InterruptedTask] = []
        for task_id, attempt_count, started_at in rows:
            if started_at is None:
                candidates.append(InterruptedTask(task_id, attempt_count, None))
            elif reference - started_at > _INTERRUPTION_AGE:
                candidates.append(InterruptedTask(task_id, attempt_count, started_at))
        return candidates

    def _recover_candidate(
        self, candidate: InterruptedTask, reference: datetime
    ) -> str:
        """Recheck one candidate under the Task-row lock and recover it.

        Returns ``"retried"``, ``"failed"``, ``"inconsistent"``, or
        ``"skipped"``. The decision transaction is released before any terminal
        finalization, because writing the observation Snapshot must not happen
        inside an open database transaction.
        """
        with self._session_factory.begin() as session:
            task = ObjectiveService._lock_task(session, candidate.task_id)
            if task is None:
                return "skipped"

            # Recheck under the lock: another caller may have completed,
            # re-admitted, or already recovered this Task since discovery.
            if task.status != "running":
                return "skipped"
            if task.attempt_count != candidate.attempt:
                return "skipped"

            started_at = self._current_attempt_start(session, task)
            if started_at is None:
                return "inconsistent"
            if reference - started_at <= _INTERRUPTION_AGE:
                return "skipped"

            if task.attempt_count < task.max_attempts:
                disposition = self._retry_disposition(
                    session, task.id, task.attempt_count
                )
                if disposition == "corrupt":
                    raise TaskNotFinalizable("recorded_retry_events_corrupt")
                if disposition == "committed":
                    # A concurrent recovery already scheduled this retry.
                    return "skipped"

                task.status = "pending"
                payload = {
                    "from_status": "running",
                    "to_status": "pending",
                    "attempt_count": task.attempt_count,
                    "result_category": "retryable_failure",
                    "failure_reason": _INTERRUPTION_REASON,
                }
                for event_type in _RETRY_EVENTS:
                    ObjectiveService._add_event(session, task.id, event_type, payload)
                session.flush()
                return "retried"

            attempt = task.attempt_count
            observed_at = started_at

        # Attempts are exhausted: resolve through the single terminal path.
        # `observed_at` is the durable current-attempt start, so repeated or
        # concurrent recovery derives the same canonical observation and
        # replays instead of conflicting on a fresh timestamp.
        observation = TerminalObservation(
            task_id=candidate.task_id,
            attempt=attempt,
            result_category="terminal_failure",
            observed_at=observed_at,
            failure_reason=_INTERRUPTION_REASON,
        )
        try:
            self.finalize(observation)
        except TaskNotFinalizable as error:
            # A lost race is a skip; recorded-state corruption and conflicts
            # propagate unchanged, exactly as they do from `report_failure()`.
            if str(error) in _SKIPPED_FINALIZATION_REASONS:
                return "skipped"
            raise
        return "failed"

    @staticmethod
    def _current_attempt_start(session: Session, task: Task) -> datetime | None:
        """The latest `task_started` Event for the Task's current attempt.

        `attempt_count` counts successful admissions, so the current attempt's
        start is the newest `task_started` Event carrying that attempt number.
        """
        return session.scalar(
            select(func.max(Event.created_at)).where(
                Event.task_id == task.id,
                Event.type == "task_started",
                Event.payload["attempt_count"].as_integer() == task.attempt_count,
            )
        )

    @staticmethod
    def _validate_evaluation_result(session: Session, task: Task,
        observation: TerminalObservation) -> None:
        if task.task_type != "evaluate_outcome":
            raise TaskNotFinalizable("evaluation_result_wrong_task_type")
        if not {"Evaluation", "EvidenceLink"}.issubset(set(task.allowed_writes)):
            raise TaskNotFinalizable("evaluation_result_write_scope_missing")
        expected_status = "recorded" if observation.result_category == "success_evaluation_recorded" else "rejected"  # noqa: E501
        evaluation = session.scalar(select(Evaluation).where(
            Evaluation.id == observation.evaluation_id,
                Evaluation.team_id == task.team_id
        ))
        if (evaluation is None or evaluation.created_by_task_id != task.id
            or evaluation.resolved_by_task_id != task.id or evaluation.status != expected_status):  # noqa: E501
            raise TaskNotFinalizable("evaluation_not_recorded")

    @staticmethod
    def _validate_failure(failure: FailureObservation) -> None:
        if failure.observed_at.tzinfo is None or (
            failure.observed_at.utcoffset() is None
        ):
            raise TaskNotFinalizable("observed_at_not_timezone_aware")
        if isinstance(failure.attempt, bool) or failure.attempt < 1:
            raise TaskNotFinalizable("invalid_attempt")
        if not isinstance(failure.reason, str) or not failure.reason.strip():
            raise TaskNotFinalizable("failure_reason_required")

    @staticmethod
    def _terminal_observation(
        failure: FailureObservation,
    ) -> TerminalObservation:
        """Adapt a failure report to the single terminal finalization path."""
        return TerminalObservation(
            task_id=failure.task_id,
            attempt=failure.attempt,
            result_category="terminal_failure",
            observed_at=failure.observed_at,
            failure_reason=failure.reason,
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
                if observation.evaluation_id is not None:
                    raise TaskNotFinalizable("evaluation_id_not_allowed")
            elif observation.result_category in _EVALUATION_SUCCESS_CATEGORIES:
                if observation.evaluation_id is None:
                    raise TaskNotFinalizable("evaluation_id_required")
                if observation.signals:
                    raise TaskNotFinalizable("signal_evidence_not_allowed")
            elif observation.signals or observation.evaluation_id is not None:
                raise TaskNotFinalizable("terminal_evidence_not_allowed")
            return

        if observation.evaluation_id is not None:
            raise TaskNotFinalizable("evaluation_id_not_allowed")
        if not observation.failure_reason or not observation.failure_reason.strip():
            raise TaskNotFinalizable("failure_reason_required")
        if observation.signals:
            raise TaskNotFinalizable("signal_evidence_not_allowed")

    @staticmethod
    def _observation_payload(observation: TerminalObservation) -> dict[str, Any]:
        payload = {
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
        if observation.evaluation_id is not None:
            payload["evaluation_id"] = str(observation.evaluation_id)
        return payload

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

    @staticmethod
    def _retry_disposition(session: Session, task_id: UUID, attempt: int) -> str:
        """Classify the durable retry record for one attempt.

        Returns ``"absent"`` when the attempt has no retry Event, ``"committed"``
        when exactly one complete ``task_attempt_failed``/``task_retry_scheduled``
        pair exists, and ``"corrupt"`` when the pair is incomplete or duplicated.
        The committed Events are the durable record; no separate marker is added.
        """
        counts: dict[str, int] = {}
        for event in session.scalars(
            select(Event).where(
                Event.task_id == task_id,
                Event.type.in_(_RETRY_EVENTS),
                Event.payload["attempt_count"].as_integer() == attempt,
            )
        ):
            counts[event.type] = counts.get(event.type, 0) + 1

        if not counts:
            return "absent"
        if counts == {"task_attempt_failed": 1, "task_retry_scheduled": 1}:
            return "committed"
        return "corrupt"

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
        stored = self._snapshot_store.read(prior.observation_snapshot_ref)  # type: ignore[union-attr]  # noqa: E501
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
        #
        # Only the Events of the recorded terminal attempt define the terminal
        # disposition. Earlier retryable attempts also emit `task_attempt_failed`
        # with a lower `attempt_count`, so the attempt filter is what keeps a
        # legitimately retried Task from looking like duplicated terminal Events.
        # `observation.attempt` is the recorded attempt: the canonical payload
        # comparison above already proved it matches the committed observation.
        by_type: dict[str, Event] = {}
        for event in session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type.in_(_TERMINAL_EVENTS + ("task_attempt_failed",)),
                Event.payload["attempt_count"].as_integer() == observation.attempt,
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