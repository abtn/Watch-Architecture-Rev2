"""Application-controlled Task admission, failure reporting, and finalization."""

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from core.models import (
    Evaluation,
    Event,
    EvidenceLink,
    KnowledgeItem,
    KnowledgeQualityAssessment,
    LearningChange,
    Outcome,
    Plan,
    PlanAction,
    Task,
    TaskGenerationCharge,
    Team,
    TeamPolicy,
)
from core.objectives import ObjectiveService, TaskNotFound
from core.policy import InvalidPolicyError, daily_task_quota
from core.snapshot_store import SnapshotStore
from core.state_assessment import _canonical_json, _timestamp

_TERMINAL_EVENTS = ("task_completed", "task_failed")
_RETRY_EVENTS = ("task_attempt_failed", "task_retry_scheduled")
_TERMINAL_STATUSES = frozenset({"done", "failed"})
_EVALUATION_SUCCESS_CATEGORIES = frozenset({"success_evaluation_recorded",
    "success_evaluation_rejected"})
_STRATEGY_SUCCESS_CATEGORIES = frozenset(
    {"success_strategy_accepted", "success_strategy_rejected"}
)
_PLAN_SUCCESS_CATEGORIES = frozenset({"success_plan_created"})
_CONTROL_TASK_SUCCESS_CATEGORIES = (
    _STRATEGY_SUCCESS_CATEGORIES | _PLAN_SUCCESS_CATEGORIES
)
_LEARNING_CHANGE_SUCCESS_CATEGORIES = frozenset(
    {"success_learning_change_proposed"}
)
_LEARNING_CHANGE_DECISION_SUCCESS_CATEGORIES = frozenset(
    {
        "success_learning_change_accepted",
        "success_learning_change_rejected",
    }
)
_KNOWLEDGE_REVIEW_SUCCESS_CATEGORIES = frozenset({"success_knowledge_reviewed"})
_KNOWLEDGE_QUALITY_SUCCESS_CATEGORIES = frozenset({"success_knowledge_quality_assessed"})
_KNOWLEDGE_QUALITY_TASK_TYPE = "assess_knowledge_quality"
_KNOWLEDGE_QUALITY_REQUEST_EVENT_TYPE = "knowledge_quality_assessment_task_requested"
_KNOWLEDGE_QUALITY_RECORDED_EVENT_TYPE = "knowledge_quality_assessment_recorded"
_KNOWLEDGE_QUALITY_ALLOWED_WRITES = ["KnowledgeQualityAssessment"]
_KNOWLEDGE_QUALITY_MAX_ATTEMPTS = 3
_KNOWLEDGE_QUALITY_BUDGET = {
    "max_tool_calls": 0,
    "max_cost_usd": 0.0,
    "deadline_seconds": 30,
}
_OPERATOR_DECISION_EVENT_TYPES = (
    "learning_change_accepted",
    "learning_change_rejected",
)
_SUCCESS_CATEGORIES = (
    frozenset({"success_signal_created", "success_no_change"})
    | _EVALUATION_SUCCESS_CATEGORIES
    | _LEARNING_CHANGE_SUCCESS_CATEGORIES
    | _LEARNING_CHANGE_DECISION_SUCCESS_CATEGORIES
    | _KNOWLEDGE_REVIEW_SUCCESS_CATEGORIES
    | _KNOWLEDGE_QUALITY_SUCCESS_CATEGORIES
    | _CONTROL_TASK_SUCCESS_CATEGORIES
)
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

_OPERATOR_TASK_TYPE = "approve_learning_change"
_OPERATOR_REQUEST_EVENT_TYPE = "operator_task_requested"
_OPERATOR_ALLOWED_WRITES = ["LearningChange", "KnowledgeItem"]
_OPERATOR_MAX_ATTEMPTS = 3

_EVALUATION_TASK_TYPE = "evaluate_outcome"
_EVALUATION_REQUEST_EVENT_TYPE = "evaluation_task_requested"
_EVALUATION_ALLOWED_WRITES = ["Evaluation", "EvidenceLink"]
_EVALUATION_MAX_ATTEMPTS = 3
_EVALUATION_DEADLINE_SECONDS = 30
_R6G_EVALUATOR_KIND = "rule"
_R6G_EVALUATOR_IDENTITY = "watch.r6g.ingest-source-rules"
_R6G_EVALUATOR_REVISION = "1"
_R6G_EVALUATION_NAMESPACE = UUID("b10ac39a-2c9c-5ad1-9d2e-4f6ec9bfa1de")
_R6G_EVALUATION_BUDGET = {
    "max_tool_calls": 0,
    "max_cost_usd": 0,
    "deadline_seconds": _EVALUATION_DEADLINE_SECONDS,
}
_R6G_SOURCE_RESULTS = frozenset(
    {"success_signal_created", "success_no_change", "terminal_failure"}
)


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
        "success_evaluation_rejected", "success_learning_change_proposed",
        "success_learning_change_accepted", "success_learning_change_rejected",
        "success_knowledge_reviewed", "success_knowledge_quality_assessed", "success_strategy_accepted",
        "success_strategy_rejected", "success_plan_created", "terminal_failure"
    ]
    observed_at: datetime
    signals: tuple[SignalEvidence, ...] = ()
    failure_reason: str | None = None
    evaluation_id: UUID | None = None
    learning_change_id: UUID | None = None
    strategy_event_id: UUID | None = None
    plan_id: UUID | None = None
    plan_event_id: UUID | None = None
    knowledge_quality_assessment_id: UUID | None = None


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

    `retried`, `failed`, and `completed` name Tasks this call transitioned;
    `skipped` names candidates another operation had already advanced past.
    `inconsistent` names `running` Tasks whose current attempt has no usable
    `task_started` Event; they are reported, never mutated. A completed Operator
    Task means recovery found its already committed LearningChange decision and
    finalized it through the ordinary TaskRuntime path.
    """

    retried: tuple[UUID, ...] = ()
    failed: tuple[UUID, ...] = ()
    skipped: tuple[UUID, ...] = ()
    inconsistent: tuple[UUID, ...] = ()
    completed: tuple[UUID, ...] = ()


class TaskRuntime:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store

    def complete_knowledge_review(self, task_id: UUID) -> FinalizationResult:
        """Run or replay one already-created review Task through this runtime.

        The host/scheduler only enqueues the ordinary Task. This method adds no
        scheduler or dispatch loop: it composes the existing admission and
        terminal-finalization transitions. A completed Task is replayed from
        its durable terminal Outcome rather than being admitted a second time.
        """
        with self._session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise TaskNotFound(f"Task {task_id} does not exist")
            if task.task_type != "review_knowledge":
                raise TaskNotEligible("unsupported_task_type")

            if task.status == "done":
                outcome = session.scalar(
                    select(Outcome).where(
                        Outcome.recorded_by_task_id == task.id,
                        Outcome.outcome_type == "task_execution",
                    )
                )
                completed_event = session.scalar(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == "task_completed",
                    )
                )
                if (
                    outcome is None
                    or outcome.observed_at is None
                    or completed_event is None
                    or completed_event.payload.get("result_category")
                    != "success_knowledge_reviewed"
                    or completed_event.payload.get("outcome_id") != str(outcome.id)
                ):
                    raise TaskNotEligible("review_task_not_successfully_completed")
                attempt = task.attempt_count
                observed_at = outcome.observed_at
            elif task.status == "pending":
                attempt = None
                observed_at = None
            else:
                raise TaskNotEligible("review_task_not_pending")

        if attempt is None:
            admission = self.admit(task_id)
            attempt = admission.attempt_count
            observed_at = datetime.now(timezone.utc)

        if attempt is None or observed_at is None:
            raise TaskNotFinalizable("knowledge_review_observation_missing")
        return self.finalize(
            TerminalObservation(
                task_id=task_id,
                attempt=attempt,
                result_category="success_knowledge_reviewed",
                observed_at=observed_at,
            )
        )

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

            if task.task_type == _OPERATOR_TASK_TYPE:
                self._validate_operator_admission(session, task)
            elif self._is_r6g_evaluation_task(session, task):
                try:
                    self._validate_evaluation_task_request(session, task)
                except TaskNotFinalizable as error:
                    raise TaskNotEligible(str(error)) from error
            elif self._is_knowledge_quality_task(session, task):
                try:
                    self._validate_knowledge_quality_task_request(
                        session, task, require_proposed=False
                    )
                except TaskNotFinalizable as error:
                    raise TaskNotEligible(str(error)) from error

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
            ):
                value = task.budget.get(field)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, kind)
                    or value < lower_bound
                ):
                    raise TaskNotEligible("invalid_task_budget")

            if task.task_type != _OPERATOR_TASK_TYPE:
                deadline_seconds = task.budget.get("deadline_seconds")
                if (
                    isinstance(deadline_seconds, bool)
                    or not isinstance(deadline_seconds, int)
                    or deadline_seconds < 1
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
    def _validate_operator_admission(
        session: Session, task: Task, *, allow_completed: bool = False
    ) -> None:
        """Fail closed unless this is an intact, no-deadline approval Task."""
        if (
            task.objective_id is not None
            or task.plan_id is not None
            or task.plan_action_id is not None
            or task.allowed_writes != _OPERATOR_ALLOWED_WRITES
            or task.max_attempts != _OPERATOR_MAX_ATTEMPTS
            or (task.completed_at is not None and not allow_completed)
            or not isinstance(task.budget, dict)
            or set(task.budget) != {"max_tool_calls", "max_cost_usd"}
        ):
            raise TaskNotEligible("operator_task_shape_invalid")

        max_tool_calls = task.budget.get("max_tool_calls")
        max_cost_usd = task.budget.get("max_cost_usd")
        if (
            isinstance(max_tool_calls, bool)
            or not isinstance(max_tool_calls, int)
            or max_tool_calls != 0
            or isinstance(max_cost_usd, bool)
            or not isinstance(max_cost_usd, (int, float))
            or max_cost_usd != 0
        ):
            raise TaskNotEligible("operator_task_shape_invalid")

        request_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == _OPERATOR_REQUEST_EVENT_TYPE,
                )
            )
        )
        if len(request_events) != 1 or not isinstance(
            request_events[0].payload, dict
        ):
            raise TaskNotEligible("operator_task_request_event_invalid")

        payload = request_events[0].payload
        legacy_keys = {
            "schema_version",
            "operation",
            "learning_change_id",
            "decision",
            "rejection_reason",
            "operator_id",
            "idempotency_key_hash",
            "request_fingerprint",
            "policy_version",
        }
        assessment_keys = {
            "knowledge_quality_assessment_id",
            "knowledge_quality_assessment_hash",
        }
        schema_version = payload.get("schema_version")
        is_legacy_rejection = (
            schema_version == 1
            and set(payload) == legacy_keys
            and payload.get("decision") == "reject"
        )
        is_assessment_request = (
            schema_version == 2
            and set(payload) == legacy_keys | assessment_keys
        )
        if not (is_legacy_rejection or is_assessment_request):
            raise TaskNotEligible("operator_task_request_payload_invalid")
        policy_version = payload.get("policy_version")
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or payload.get("operation") != _OPERATOR_TASK_TYPE
            or isinstance(policy_version, bool)
            or not isinstance(policy_version, int)
            or policy_version != task.policy_version
        ):
            raise TaskNotEligible("operator_task_request_payload_invalid")

        decision = payload.get("decision")
        rejection_reason = payload.get("rejection_reason")
        if decision == "accept":
            if rejection_reason is not None:
                raise TaskNotEligible("operator_task_request_payload_invalid")
        elif decision == "reject":
            if (
                not isinstance(rejection_reason, str)
                or not rejection_reason
                or rejection_reason != rejection_reason.strip()
            ):
                raise TaskNotEligible("operator_task_request_payload_invalid")
        else:
            raise TaskNotEligible("operator_task_request_payload_invalid")

        operator_id = payload.get("operator_id")
        if not isinstance(operator_id, str) or len(operator_id) > 255:
            raise TaskNotEligible("operator_task_request_identity_invalid")
        try:
            identity = json.loads(operator_id)
        except (TypeError, ValueError) as error:
            raise TaskNotEligible(
                "operator_task_request_identity_invalid"
            ) from error
        if (
            not isinstance(identity, dict)
            or set(identity) != {"iss", "sub"}
            or any(
                not isinstance(identity.get(field), str)
                or not identity[field]
                or identity[field] != identity[field].strip()
                or any(
                    unicodedata.category(character) == "Cc"
                    for character in identity[field]
                )
                for field in ("iss", "sub")
            )
        ):
            raise TaskNotEligible("operator_task_request_identity_invalid")

        canonical_operator_id = json.dumps(
            {"iss": identity["iss"], "sub": identity["sub"]},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if canonical_operator_id != operator_id:
            raise TaskNotEligible("operator_task_request_identity_invalid")

        for field in ("idempotency_key_hash", "request_fingerprint"):
            value = payload.get(field)
            if (
                not isinstance(value, str)
                or len(value) != 71
                or not value.startswith("sha256:")
                or any(character not in "0123456789abcdef" for character in value[7:])
            ):
                raise TaskNotEligible("operator_task_request_payload_invalid")

        quality_assessment_id_value = payload.get(
            "knowledge_quality_assessment_id"
        )
        quality_assessment_hash = payload.get(
            "knowledge_quality_assessment_hash"
        )
        if is_assessment_request:
            if decision == "accept":
                if (
                    not isinstance(quality_assessment_id_value, str)
                    or len(quality_assessment_id_value) != 36
                    or not isinstance(quality_assessment_hash, str)
                    or len(quality_assessment_hash) != 71
                    or not quality_assessment_hash.startswith("sha256:")
                    or any(
                        character not in "0123456789abcdef"
                        for character in quality_assessment_hash[7:]
                    )
                ):
                    raise TaskNotEligible(
                        "operator_quality_assessment_reference_invalid"
                    )
                try:
                    quality_assessment_id = UUID(quality_assessment_id_value)
                except ValueError as error:
                    raise TaskNotEligible(
                        "operator_quality_assessment_reference_invalid"
                    ) from error
                if str(quality_assessment_id) != quality_assessment_id_value:
                    raise TaskNotEligible(
                        "operator_quality_assessment_reference_invalid"
                    )
            elif quality_assessment_id_value is not None or quality_assessment_hash is not None:
                raise TaskNotEligible(
                    "operator_quality_assessment_reference_invalid"
                )
        elif decision == "accept":
            raise TaskNotEligible("operator_quality_assessment_required")

        fingerprint_payload = {
            "operation": _OPERATOR_TASK_TYPE,
            "team_id": str(task.team_id),
            "learning_change_id": payload.get("learning_change_id"),
            "decision": decision,
            "rejection_reason": rejection_reason,
            "operator_id": operator_id,
        }
        if is_assessment_request:
            fingerprint_payload["knowledge_quality_assessment_id"] = (
                quality_assessment_id_value
            )
            fingerprint_payload["knowledge_quality_assessment_hash"] = (
                quality_assessment_hash
            )
        expected_fingerprint = "sha256:" + hashlib.sha256(
            json.dumps(
                fingerprint_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if payload.get("request_fingerprint") != expected_fingerprint:
            raise TaskNotEligible("operator_task_request_fingerprint_invalid")

        learning_change_id_value = payload.get("learning_change_id")
        if not isinstance(learning_change_id_value, str):
            raise TaskNotEligible("operator_task_request_target_invalid")
        try:
            learning_change_id = UUID(learning_change_id_value)
        except ValueError as error:
            raise TaskNotEligible(
                "operator_task_request_target_invalid"
            ) from error
        if str(learning_change_id) != learning_change_id_value:
            raise TaskNotEligible("operator_task_request_target_invalid")

        learning_change = session.scalar(
            select(LearningChange)
            .where(LearningChange.id == learning_change_id)
            .with_for_update()
        )
        if (
            learning_change is None
            or learning_change.team_id != task.team_id
            or learning_change.target_kind != "knowledge_item"
            or learning_change.operation != "create"
            or learning_change.target_id is not None
        ):
            raise TaskNotEligible("operator_task_request_target_invalid")
        if decision == "accept":
            from core.knowledge_quality import (
                KnowledgeQualityAssessmentError,
                require_recorded_assessment,
            )

            try:
                assessment = require_recorded_assessment(
                    session, learning_change, require_task_done=True
                )
            except KnowledgeQualityAssessmentError as error:
                raise TaskNotEligible(str(error)) from error
            if (
                str(assessment.id) != quality_assessment_id_value
                or assessment.assessment_payload_hash != quality_assessment_hash
            ):
                raise TaskNotEligible("operator_quality_assessment_binding_invalid")

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

            if self._is_r6g_evaluation_task(session, task):
                self._validate_evaluation_task_request(session, task)
            if self._is_knowledge_quality_task(session, task):
                self._validate_knowledge_quality_task_request(
                    session,
                    task,
                    require_proposed=(
                        task.status == "running"
                        and observation.result_category
                        in _KNOWLEDGE_QUALITY_SUCCESS_CATEGORIES
                    ),
                )
            if (
                observation.result_category == "success_knowledge_reviewed"
                and task.task_type != "review_knowledge"
            ):
                raise TaskNotFinalizable("knowledge_review_result_wrong_task_type")

            review_event: Event | None = None

            if observation.result_category in _KNOWLEDGE_QUALITY_SUCCESS_CATEGORIES:
                self._validate_knowledge_quality_result(
                    session,
                    task,
                    observation,
                    allow_completed=task.status == "done",
                )
            elif observation.knowledge_quality_assessment_id is not None:
                raise TaskNotFinalizable("knowledge_quality_assessment_id_not_allowed")

            if (
                observation.result_category
                in _LEARNING_CHANGE_DECISION_SUCCESS_CATEGORIES
            ):
                self._validate_learning_change_decision_result(
                    session,
                    task,
                    observation,
                    allow_completed=task.status == "done",
                )
            elif task.task_type == _OPERATOR_TASK_TYPE:
                if observation.result_category in _SUCCESS_CATEGORIES:
                    raise TaskNotFinalizable(
                        "operator_task_requires_learning_change_decision"
                    )
                expected_operator_observation = (
                    self._committed_operator_decision_observation(session, task)
                )
                if expected_operator_observation is not None:
                    if (
                        expected_operator_observation.result_category
                        in _SUCCESS_CATEGORIES
                    ):
                        raise TaskNotFinalizable(
                            "operator_decision_requires_success_finalization"
                        )
                    if expected_operator_observation != observation:
                        raise TaskNotFinalizable(
                            "operator_conflict_failure_observation_mismatch"
                        )

            prior = self._prior_terminal(session, task.id)
            if prior is not None:
                self._verify_terminal_evaluation_request(
                    session, task, prior, observation
                )
                return self._replay(session, task, prior, payload, observation)

            # A terminal Task without its Outcome is the invariant violation
            # ADR-0030 §4 forbids, not an ordinary eligibility failure.
            if task.status in _TERMINAL_STATUSES:
                raise TaskNotFinalizable("recorded_terminal_outcome_corrupt")
            if task.status != "running":
                raise TaskNotFinalizable("task_not_running")
            if observation.attempt != task.attempt_count:
                raise TaskNotFinalizable("stale_attempt")
            if observation.result_category == "success_knowledge_reviewed":
                review_event = self._commit_due_knowledge_reviews(
                    session, task, observation
                )
                session.add(review_event)
            if (
                task.task_type == "evaluate_outcome"
                and observation.result_category in _SUCCESS_CATEGORIES
                and observation.result_category not in _EVALUATION_SUCCESS_CATEGORIES
            ):
                raise TaskNotFinalizable(
                    "evaluation_task_requires_evaluation_result"
                )
            if (
                task.task_type == "propose_learning_change"
                and observation.result_category in _SUCCESS_CATEGORIES
                and observation.result_category
                not in _LEARNING_CHANGE_SUCCESS_CATEGORIES
            ):
                raise TaskNotFinalizable(
                    "learning_change_task_requires_learning_change_result"
                )
            if (
                task.task_type == _KNOWLEDGE_QUALITY_TASK_TYPE
                and observation.result_category in _SUCCESS_CATEGORIES
                and observation.result_category
                not in _KNOWLEDGE_QUALITY_SUCCESS_CATEGORIES
            ):
                raise TaskNotFinalizable(
                    "knowledge_quality_task_requires_assessment_result"
                )
            if (
                task.task_type == "review_knowledge"
                and observation.result_category in _SUCCESS_CATEGORIES
                and observation.result_category
                not in _KNOWLEDGE_REVIEW_SUCCESS_CATEGORIES
            ):
                raise TaskNotFinalizable(
                    "review_task_requires_knowledge_review_result"
                )
            if observation.result_category in _EVALUATION_SUCCESS_CATEGORIES:
                self._validate_evaluation_result(session, task, observation)
            elif observation.evaluation_id is not None:
                raise TaskNotFinalizable("evaluation_id_not_allowed")
            if observation.result_category in _CONTROL_TASK_SUCCESS_CATEGORIES:
                self._validate_control_task_result(
                    session,
                    task,
                    observation,
                    allow_completed=task.status == "done",
                )
            elif (
                observation.strategy_event_id is not None
                or observation.plan_id is not None
                or observation.plan_event_id is not None
            ):
                raise TaskNotFinalizable("control_task_result_id_not_allowed")
            if observation.result_category in _LEARNING_CHANGE_SUCCESS_CATEGORIES:
                self._validate_learning_change_result(session, task, observation)
            elif (
                observation.result_category
                not in _LEARNING_CHANGE_DECISION_SUCCESS_CATEGORIES
                and observation.learning_change_id is not None
            ):
                raise TaskNotFinalizable("learning_change_id_not_allowed")

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
            events = (
                [review_event] if review_event is not None else []
            ) + [
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
                        **(
                            {"evaluation_id": str(observation.evaluation_id)}
                            if observation.evaluation_id is not None
                            else {}
                        ),
                        **(
                            {"learning_change_id": str(observation.learning_change_id)}
                            if observation.learning_change_id is not None
                            else {}
                        ),
                        **(
                            {"strategy_event_id": str(observation.strategy_event_id)}
                            if observation.strategy_event_id is not None
                            else {}
                        ),
                        **(
                            {"plan_id": str(observation.plan_id)}
                            if observation.plan_id is not None
                            else {}
                        ),
                        **(
                            {"plan_event_id": str(observation.plan_event_id)}
                            if observation.plan_event_id is not None
                            else {}
                        ),
                        **(
                            {
                                "knowledge_quality_assessment_id": str(
                                    observation.knowledge_quality_assessment_id
                                )
                            }
                            if observation.knowledge_quality_assessment_id is not None
                            else {}
                        ),
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

            if task.task_type == "ingest_source" and task.plan_id is not None:
                self._create_evaluation_task_request(
                    session, task, outcome, observation.result_category
                )
                session.flush()
            if (
                task.task_type == "propose_learning_change"
                and observation.result_category == "success_learning_change_proposed"
            ):
                learning_change = session.get(LearningChange, observation.learning_change_id)
                if learning_change is None:
                    raise TaskNotFinalizable("learning_change_not_found_for_quality_task")
                self._create_knowledge_quality_task_request(
                    session, task, learning_change
                )
                session.flush()

            return FinalizationResult(
                task_id=task.id,
                status=task.status,
                attempt_count=task.attempt_count,
                event_ids=tuple(event.id for event in events),
                outcome_id=outcome.id,
            )

    @staticmethod
    def _commit_due_knowledge_reviews(
        session: Session, task: Task, observation: TerminalObservation
    ) -> Event:
        """Commit due KnowledgeItem status transitions within Task finalization."""
        budget = task.budget
        if (
            task.task_type != "review_knowledge"
            or task.allowed_writes != ["KnowledgeItem"]
            or task.objective_id is not None
            or task.plan_id is not None
            or task.plan_action_id is not None
            or not isinstance(budget, dict)
            or isinstance(budget.get("max_tool_calls"), bool)
            or budget.get("max_tool_calls") != 0
            or isinstance(budget.get("max_cost_usd"), bool)
            or budget.get("max_cost_usd") != 0
            or isinstance(budget.get("deadline_seconds"), bool)
            or not isinstance(budget.get("deadline_seconds"), int)
            or budget["deadline_seconds"] < 1
        ):
            raise TaskNotFinalizable("knowledge_review_task_shape_invalid")

        team = session.scalar(
            select(Team).where(Team.id == task.team_id).with_for_update()
        )
        if team is None or team.status != "active":
            raise TaskNotFinalizable("knowledge_review_team_not_active")
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        if policy is None:
            raise TaskNotFinalizable("knowledge_review_policy_missing")

        now_utc = observation.observed_at.astimezone(timezone.utc)
        due_items = list(
            session.scalars(
                select(KnowledgeItem)
                .where(
                    KnowledgeItem.team_id == task.team_id,
                    KnowledgeItem.status == "active",
                    KnowledgeItem.review_after.is_not(None),
                    KnowledgeItem.review_after <= now_utc,
                )
                .order_by(KnowledgeItem.id)
                .with_for_update()
            )
        )

        from core.knowledge_index import _accepted_learning_change_is_canonical

        reviewed: list[dict[str, Any]] = []
        for item in due_items:
            learning_change = session.get(
                LearningChange, item.origin_learning_change_id
            )
            if learning_change is None or not _accepted_learning_change_is_canonical(
                session, item, learning_change
            ):
                raise TaskNotFinalizable("knowledge_review_canonical_state_invalid")
            review_after = item.review_after
            if (
                review_after is None
                or review_after.tzinfo is None
                or review_after.utcoffset() is None
                or review_after.astimezone(timezone.utc) > now_utc
            ):
                raise TaskNotFinalizable("knowledge_review_due_boundary_changed")
            reviewed.append(
                {
                    "knowledge_item_id": str(item.id),
                    "version": item.version,
                    "review_after": review_after.astimezone(timezone.utc).isoformat(),
                    "origin_learning_change_id": str(item.origin_learning_change_id),
                }
            )
            item.status = "needs_review"
            item.updated_at = now_utc

        return Event(
            id=uuid4(),
            task_id=task.id,
            type="knowledge_items_reviewed",
            payload={
                "schema_version": 1,
                "team_id": str(task.team_id),
                "task_id": str(task.id),
                "attempt_count": task.attempt_count,
                "reviewed_at": now_utc.isoformat(),
                "items": reviewed,
            },
            created_at=now_utc,
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
        completed: list[UUID] = []

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
            elif outcome == "completed":
                completed.append(candidate.task_id)
            else:
                skipped.append(candidate.task_id)

        return RecoveryResult(
            retried=tuple(retried),
            failed=tuple(failed),
            skipped=tuple(skipped),
            inconsistent=tuple(inconsistent),
            completed=tuple(completed),
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

        A previously committed Operator decision is finalized before considering
        retry limits. Other interrupted Tasks retain the ordinary retry/failure
        behavior. Snapshot writes and terminal commits happen after releasing
        the discovery/decision transaction.
        """
        recovered_observation: TerminalObservation | None = None
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

            if task.task_type == _OPERATOR_TASK_TYPE:
                recovered_observation = (
                    self._committed_operator_decision_observation(session, task)
                )
            elif self._is_knowledge_quality_task(session, task):
                recovered_observation = (
                    self._committed_knowledge_quality_assessment_observation(
                        session, task
                    )
                )
            elif self._is_r6g_evaluation_task(session, task):
                recovered_observation = self._committed_evaluation_observation(
                    session, task
                )
            elif task.task_type in {"propose_strategy", "create_plan"}:
                recovered_observation = self._committed_control_task_observation(
                    session, task
                )

            if (
                recovered_observation is None
                and task.attempt_count < task.max_attempts
            ):
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

        if recovered_observation is not None:
            try:
                self.finalize(recovered_observation)
            except TaskNotFinalizable as error:
                if str(error) in _SKIPPED_FINALIZATION_REASONS:
                    return "skipped"
                raise
            return (
                "failed"
                if recovered_observation.result_category == "terminal_failure"
                else "completed"
            )

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
    def _committed_knowledge_quality_assessment_observation(
        session: Session, task: Task
    ) -> TerminalObservation | None:
        from core.knowledge_quality import (
            KnowledgeQualityAssessmentError,
            require_recorded_assessment,
        )

        if not TaskRuntime._is_knowledge_quality_task(session, task):
            return None
        request = TaskRuntime._validate_knowledge_quality_task_request(
            session, task, require_proposed=False
        )
        assessment = session.scalar(
            select(KnowledgeQualityAssessment).where(
                KnowledgeQualityAssessment.creating_task_id == task.id,
                KnowledgeQualityAssessment.team_id == task.team_id,
            )
        )
        if assessment is None:
            learning_change_id = UUID(request["learning_change_id"])
            learning_change = session.get(LearningChange, learning_change_id)
            if learning_change is None:
                raise TaskNotFinalizable("knowledge_quality_learning_change_missing")
            if learning_change.status == "rejected" and task.status == "running":
                started_at = TaskRuntime._current_attempt_start(session, task)
                if started_at is None:
                    raise TaskNotFinalizable("knowledge_quality_task_start_missing")
                return TerminalObservation(
                    task_id=task.id,
                    attempt=task.attempt_count,
                    result_category="terminal_failure",
                    observed_at=started_at,
                    failure_reason="learning_change_rejected_before_quality_assessment",
                )
            if learning_change.status != "proposed":
                raise TaskNotFinalizable("knowledge_quality_assessment_missing_for_decided_change")
            return None
        learning_change = session.get(LearningChange, assessment.learning_change_id)
        if learning_change is None:
            raise TaskNotFinalizable("knowledge_quality_learning_change_missing")
        try:
            require_recorded_assessment(
                session,
                learning_change,
                require_task_done=task.status == "done",
            )
        except KnowledgeQualityAssessmentError as error:
            raise TaskNotFinalizable(str(error)) from error
        if (
            request.get("learning_change_id") != str(learning_change.id)
            or assessment.creating_task_id != task.id
        ):
            raise TaskNotFinalizable("knowledge_quality_assessment_request_mismatch")
        if task.status == "done":
            outcomes = list(
                session.scalars(
                    select(Outcome).where(
                        Outcome.recorded_by_task_id == task.id,
                        Outcome.outcome_type == "task_execution",
                    )
                )
            )
            if len(outcomes) != 1 or outcomes[0].observed_at is None:
                raise TaskNotFinalizable("knowledge_quality_task_outcome_missing")
            observed_at = outcomes[0].observed_at
        elif task.status == "running":
            observed_at = assessment.recorded_at
            if observed_at.tzinfo is None:
                raise TaskNotFinalizable("knowledge_quality_assessment_timestamp_invalid")
        else:
            return None
        return TerminalObservation(
            task_id=task.id,
            attempt=task.attempt_count,
            result_category="success_knowledge_quality_assessed",
            observed_at=observed_at,
            knowledge_quality_assessment_id=assessment.id,
        )

    @staticmethod
    def _committed_operator_decision_observation(
        session: Session, task: Task
    ) -> TerminalObservation | None:
        """Reconcile a committed Operator decision for its owner or a loser.

        The LearningChange row lock permits only one approval Task to win.
        The winning Task receives its typed success observation. A different
        Task targeting the already-decided LearningChange receives a stable,
        attempt-fenced terminal failure that can be committed by the ordinary
        TaskRuntime finalizer or reconstructed during interrupted recovery.
        """
        if task.task_type != _OPERATOR_TASK_TYPE:
            return None
        try:
            TaskRuntime._validate_operator_admission(session, task)
        except TaskNotEligible as error:
            raise TaskNotFinalizable(
                "operator_task_request_event_invalid"
            ) from error

        request_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == _OPERATOR_REQUEST_EVENT_TYPE,
                )
            )
        )
        if len(request_events) != 1 or not isinstance(
            request_events[0].payload, dict
        ):
            raise TaskNotFinalizable("operator_task_request_event_invalid")
        request_payload = request_events[0].payload
        try:
            learning_change_id = UUID(request_payload.get("learning_change_id"))
        except (TypeError, ValueError) as error:
            raise TaskNotFinalizable(
                "operator_task_request_target_invalid"
            ) from error

        learning_change = session.scalar(
            select(LearningChange)
            .where(
                LearningChange.id == learning_change_id,
                LearningChange.team_id == task.team_id,
            )
            .with_for_update()
        )
        if learning_change is None:
            raise TaskNotFinalizable("learning_change_not_found_for_task_team")

        decision_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type.in_(_OPERATOR_DECISION_EVENT_TYPES),
                )
            )
        )
        if learning_change.status == "proposed":
            if (
                decision_events
                or learning_change.committed_by_task_id is not None
                or learning_change.operator_id is not None
                or learning_change.committed_at is not None
                or learning_change.committed_state is not None
            ):
                raise TaskNotFinalizable("learning_change_decision_state_mismatch")
            return None
        if learning_change.status not in {"accepted", "rejected"}:
            raise TaskNotFinalizable("learning_change_decision_state_mismatch")
        if learning_change.committed_at is None:
            raise TaskNotFinalizable("learning_change_decision_timestamp_missing")

        result_category: Literal[
            "success_learning_change_accepted", "success_learning_change_rejected"
        ] = (
            "success_learning_change_accepted"
            if learning_change.status == "accepted"
            else "success_learning_change_rejected"
        )

        if learning_change.committed_by_task_id == task.id:
            observation = TerminalObservation(
                task_id=task.id,
                attempt=task.attempt_count,
                result_category=result_category,
                observed_at=learning_change.committed_at,
                learning_change_id=learning_change.id,
            )
            TaskRuntime._validate_learning_change_decision_result(
                session, task, observation
            )
            return observation

        # Another approval Task won. Its durable decision must itself be
        # internally valid before this Task is failed as the losing request.
        if decision_events or learning_change.committed_by_task_id is None:
            raise TaskNotFinalizable("learning_change_decision_owner_mismatch")
        winning_task = session.get(Task, learning_change.committed_by_task_id)
        if (
            winning_task is None
            or winning_task.team_id != task.team_id
            or winning_task.task_type != _OPERATOR_TASK_TYPE
            or winning_task.status not in {"running", "done"}
            or winning_task.attempt_count < 1
        ):
            raise TaskNotFinalizable("learning_change_decision_owner_invalid")

        winning_observation = TerminalObservation(
            task_id=winning_task.id,
            attempt=winning_task.attempt_count,
            result_category=result_category,
            observed_at=learning_change.committed_at,
            learning_change_id=learning_change.id,
        )
        TaskRuntime._validate_learning_change_decision_result(
            session,
            winning_task,
            winning_observation,
            allow_completed=winning_task.status == "done",
        )

        losing_started_at = TaskRuntime._current_attempt_start(session, task)
        if losing_started_at is None:
            raise TaskNotFinalizable("approval_task_start_event_invalid")
        return TerminalObservation(
            task_id=task.id,
            attempt=task.attempt_count,
            result_category="terminal_failure",
            observed_at=losing_started_at,
            failure_reason="learning_change_already_decided",
        )

    @staticmethod
    def _is_r6g_evaluation_task(session: Session, task: Task) -> bool:
        """Identify a D9 evaluator Task, including a damaged request Event.

        The exact no-cost Task shape identifies an unenqueued/missing-request
        candidate; the Event identifies a request whose Task shape was altered.
        Generic EvaluationService component fixtures with their own budgets
        remain outside this automatic R6-G Task protocol.
        """
        if task.task_type != _EVALUATION_TASK_TYPE:
            return False
        request_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == _EVALUATION_REQUEST_EVENT_TYPE,
                )
            )
        )
        exact_shape = (
            task.objective_id is None
            and task.plan_id is None
            and task.plan_action_id is None
            and task.allowed_writes == _EVALUATION_ALLOWED_WRITES
            and task.budget == _R6G_EVALUATION_BUDGET
            and task.max_attempts == _EVALUATION_MAX_ATTEMPTS
        )
        return exact_shape or bool(request_events)

    @staticmethod
    def _is_knowledge_quality_task(session: Session, task: Task) -> bool:
        if task.task_type == _KNOWLEDGE_QUALITY_TASK_TYPE:
            return True
        return session.scalar(
            select(Event.id).where(
                Event.task_id == task.id,
                Event.type == _KNOWLEDGE_QUALITY_REQUEST_EVENT_TYPE,
            )
        ) is not None

    @staticmethod
    def _validate_knowledge_quality_task_request(
        session: Session,
        task: Task,
        *,
        require_proposed: bool = True,
    ) -> dict[str, Any]:
        from core.knowledge_quality import (
            KnowledgeQualityAssessmentError,
            validate_quality_task_request,
        )

        try:
            return validate_quality_task_request(
                session, task, require_proposed=require_proposed
            )
        except KnowledgeQualityAssessmentError as error:
            raise TaskNotFinalizable(error.reason) from error

    def _create_knowledge_quality_task_request(
        self, session: Session,
        source_task: Task,
        learning_change: LearningChange,
    ) -> Task:
        from core.knowledge_quality import (
            ALLOWED_WRITES,
            REQUEST_EVENT_TYPE,
            TASK_BUDGET,
            TASK_MAX_ATTEMPTS,
            TASK_TYPE,
            build_quality_task_request,
            validate_quality_task_request,
        )
        from core.experience_distiller import (
            ExperienceDistiller,
            ExperienceDistillerError,
        )

        try:
            ExperienceDistiller(
                self._session_factory, self._snapshot_store, provider=None
            ).validate_learning_change(session, learning_change)
        except ExperienceDistillerError as error:
            raise TaskNotFinalizable(error.reason) from error

        task_id, payload = build_quality_task_request(
            session, source_task, learning_change, require_proposed=True
        )
        existing = session.get(Task, task_id)
        if existing is not None:
            try:
                validate_quality_task_request(
                    session, existing, require_proposed=True
                )
            except Exception as error:
                raise TaskNotFinalizable(
                    "knowledge_quality_task_existing_request_corrupt"
                ) from error
            return existing

        task = Task(
            id=task_id,
            team_id=source_task.team_id,
            task_type=TASK_TYPE,
            status="pending",
            attempt_count=0,
            policy_version=source_task.policy_version,
            objective_id=None,
            plan_id=None,
            plan_action_id=None,
            allowed_writes=list(ALLOWED_WRITES),
            budget=dict(TASK_BUDGET),
            completed_at=None,
            max_attempts=TASK_MAX_ATTEMPTS,
        )
        session.add(task)
        session.flush()
        session.add(
            Event(
                id=uuid4(),
                task_id=task.id,
                type=REQUEST_EVENT_TYPE,
                payload=payload,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.flush()
        return task

    @staticmethod
    def _source_action_for_evaluation(
        session: Session, source_task: Task
    ) -> PlanAction:
        if (
            source_task.task_type != "ingest_source"
            or source_task.plan_id is None
            or source_task.plan_action_id is None
            or source_task.allowed_writes != ["Signal"]
        ):
            raise TaskNotFinalizable("evaluation_source_task_shape_invalid")
        plan = session.get(Plan, source_task.plan_id)
        action = session.get(
            PlanAction, (source_task.plan_id, source_task.plan_action_id)
        )
        if (
            plan is None
            or plan.team_id != source_task.team_id
            or plan.objective_id != source_task.objective_id
            or action is None
            or not isinstance(action.action, dict)
            or action.action.get("id") != str(action.action_id)
            or action.action.get("task_type") != "ingest_source"
            or action.action.get("tools")
            or not isinstance(action.action.get("origin_url"), str)
            or not action.action.get("origin_url")
            or not isinstance(action.action.get("source_type"), str)
            or not action.action.get("source_type")
        ):
            raise TaskNotFinalizable("evaluation_source_plan_action_invalid")

        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == source_task.team_id,
                TeamPolicy.version == source_task.policy_version,
            )
        )
        if policy is None or not isinstance(policy.rules, dict):
            raise TaskNotFinalizable("evaluation_source_policy_missing")
        configured_sources = policy.rules.get("sources")
        if not isinstance(configured_sources, list) or not any(
            isinstance(item, dict)
            and item.get("origin_url") == action.action.get("origin_url")
            and item.get("source_type") == action.action.get("source_type")
            for item in configured_sources
        ):
            raise TaskNotFinalizable("evaluation_source_not_policy_configured")
        return action

    @staticmethod
    def _evaluation_request_payload(
        source_task: Task, outcome: Outcome, result_category: str
    ) -> dict[str, Any]:
        if result_category not in _R6G_SOURCE_RESULTS:
            raise TaskNotFinalizable("evaluation_source_result_unsupported")
        if (
            outcome.team_id != source_task.team_id
            or outcome.outcome_type != "task_execution"
            or outcome.subject_kind != "task"
            or outcome.subject_id != source_task.id
            or outcome.recorded_by_task_id != source_task.id
            or outcome.observation_snapshot_ref is None
            or outcome.observation_hash is None
            or outcome.observed_at is None
        ):
            raise TaskNotFinalizable("evaluation_source_outcome_invalid")
        expected_status = "failed" if result_category == "terminal_failure" else "done"
        if source_task.status != expected_status or source_task.attempt_count < 1:
            raise TaskNotFinalizable("evaluation_source_terminal_state_invalid")

        payload: dict[str, Any] = {
            "schema_version": 1,
            "operation": "evaluate_outcome",
            "team_id": str(source_task.team_id),
            "source_task_id": str(source_task.id),
            "source_attempt": source_task.attempt_count,
            "source_result_category": result_category,
            "source_plan_id": str(source_task.plan_id),
            "source_plan_action_id": str(source_task.plan_action_id),
            "policy_version": source_task.policy_version,
            "outcome_id": str(outcome.id),
            "observation_snapshot_ref": outcome.observation_snapshot_ref,
            "observation_hash": outcome.observation_hash,
            "evaluator_kind": _R6G_EVALUATOR_KIND,
            "evaluator_identity": _R6G_EVALUATOR_IDENTITY,
            "evaluator_revision": _R6G_EVALUATOR_REVISION,
        }
        payload["request_fingerprint"] = (
            "sha256:"
            + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        )
        return payload

    @staticmethod
    def _evaluation_task_id(payload: dict[str, Any]) -> UUID:
        return uuid5(
            _R6G_EVALUATION_NAMESPACE,
            "|".join(
                (
                    payload["team_id"],
                    payload["outcome_id"],
                    payload["evaluator_identity"],
                    payload["evaluator_revision"],
                )
            ),
        )

    @staticmethod
    def _validate_evaluation_task_request(
        session: Session, task: Task
    ) -> dict[str, Any]:
        if (
            task.task_type != _EVALUATION_TASK_TYPE
            or task.objective_id is not None
            or task.plan_id is not None
            or task.plan_action_id is not None
            or task.allowed_writes != _EVALUATION_ALLOWED_WRITES
            or task.budget != _R6G_EVALUATION_BUDGET
            or task.max_attempts != _EVALUATION_MAX_ATTEMPTS
            or task.status not in {"pending", "running", "done", "failed"}
            or task.attempt_count < 0
            or task.attempt_count > task.max_attempts
        ):
            raise TaskNotFinalizable("evaluation_task_shape_invalid")
        request_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == _EVALUATION_REQUEST_EVENT_TYPE,
                )
            )
        )
        if len(request_events) != 1 or not isinstance(
            request_events[0].payload, dict
        ):
            raise TaskNotFinalizable("evaluation_task_request_event_invalid")
        payload = request_events[0].payload
        expected_keys = {
            "schema_version",
            "operation",
            "team_id",
            "source_task_id",
            "source_attempt",
            "source_result_category",
            "source_plan_id",
            "source_plan_action_id",
            "policy_version",
            "outcome_id",
            "observation_snapshot_ref",
            "observation_hash",
            "evaluator_kind",
            "evaluator_identity",
            "evaluator_revision",
            "request_fingerprint",
        }
        if set(payload) != expected_keys:
            raise TaskNotFinalizable("evaluation_task_request_payload_invalid")
        fingerprint_fields = {
            key: value for key, value in payload.items()
            if key != "request_fingerprint"
        }
        expected_fingerprint = (
            "sha256:"
            + hashlib.sha256(
                _canonical_json(fingerprint_fields).encode("utf-8")
            ).hexdigest()
        )
        if payload.get("request_fingerprint") != expected_fingerprint:
            raise TaskNotFinalizable("evaluation_task_request_fingerprint_invalid")
        if (
            payload.get("schema_version") != 1
            or payload.get("operation") != _EVALUATION_TASK_TYPE
            or payload.get("evaluator_kind") != _R6G_EVALUATOR_KIND
            or payload.get("evaluator_identity") != _R6G_EVALUATOR_IDENTITY
            or payload.get("evaluator_revision") != _R6G_EVALUATOR_REVISION
            or payload.get("team_id") != str(task.team_id)
            or payload.get("policy_version") != task.policy_version
            or isinstance(payload.get("source_attempt"), bool)
            or not isinstance(payload.get("source_attempt"), int)
            or payload["source_attempt"] < 1
            or isinstance(payload.get("policy_version"), bool)
            or not isinstance(payload.get("policy_version"), int)
        ):
            raise TaskNotFinalizable("evaluation_task_request_binding_invalid")
        try:
            source_task_id = UUID(payload["source_task_id"])
            outcome_id = UUID(payload["outcome_id"])
            source_plan_id = UUID(payload["source_plan_id"])
            source_action_id = UUID(payload["source_plan_action_id"])
        except (TypeError, ValueError) as error:
            raise TaskNotFinalizable(
                "evaluation_task_request_reference_invalid"
            ) from error

        source_task = session.get(Task, source_task_id)
        outcome = session.get(Outcome, outcome_id)
        if (
            source_task is None
            or outcome is None
            or source_task.team_id != task.team_id
            or source_task.status
            != (
                "failed"
                if payload["source_result_category"] == "terminal_failure"
                else "done"
            )
            or source_task.attempt_count != payload["source_attempt"]
            or source_task.plan_id != source_plan_id
            or source_task.plan_action_id != source_action_id
            or source_task.policy_version != task.policy_version
        ):
            raise TaskNotFinalizable("evaluation_task_source_binding_invalid")
        TaskRuntime._source_action_for_evaluation(session, source_task)
        expected_payload = TaskRuntime._evaluation_request_payload(
            source_task, outcome, payload["source_result_category"]
        )
        if payload != expected_payload:
            raise TaskNotFinalizable("evaluation_task_request_mismatch")
        expected_task_id = TaskRuntime._evaluation_task_id(expected_payload)
        if task.id != expected_task_id:
            raise TaskNotFinalizable("evaluation_task_id_mismatch")
        source_terminal_types = (
            ("task_attempt_failed", "task_failed")
            if expected_payload["source_result_category"] == "terminal_failure"
            else ("task_completed",)
        )
        for event_type in source_terminal_types:
            matching = [
                event for event in session.scalars(
                    select(Event).where(
                        Event.task_id == source_task.id,
                        Event.type == event_type,
                    )
                )
                if event.payload.get("attempt_count") == source_task.attempt_count
            ]
            if len(matching) != 1:
                raise TaskNotFinalizable("evaluation_source_terminal_event_invalid")
            event_payload = matching[0].payload
            expected_status = (
                "failed"
                if expected_payload["source_result_category"] == "terminal_failure"
                else "done"
            )
            if (
                event_payload.get("from_status") != "running"
                or event_payload.get("to_status") != expected_status
                or event_payload.get("attempt_count") != source_task.attempt_count
                or event_payload.get("result_category")
                != expected_payload["source_result_category"]
                or event_payload.get("outcome_id") != str(outcome.id)
                or event_payload.get("observation_snapshot_ref")
                != outcome.observation_snapshot_ref
                or event_payload.get("observation_hash") != outcome.observation_hash
            ):
                raise TaskNotFinalizable("evaluation_source_terminal_event_mismatch")
        if (
            task.attempt_count == 0 and task.status != "pending"
        ) or (
            task.status == "done" and task.completed_at is None
        ) or (
            task.status == "failed" and task.completed_at is not None
        ):
            raise TaskNotFinalizable("evaluation_task_lifecycle_state_invalid")
        return payload

    def _create_evaluation_task_request(
        self,
        session: Session,
        source_task: Task,
        outcome: Outcome,
        result_category: str,
    ) -> UUID:
        self._source_action_for_evaluation(session, source_task)
        payload = self._evaluation_request_payload(
            source_task, outcome, result_category
        )
        task_id = self._evaluation_task_id(payload)
        if session.get(Task, task_id) is not None:
            raise TaskNotFinalizable("evaluation_task_id_conflict")
        evaluation_task = Task(
            id=task_id,
            team_id=source_task.team_id,
            task_type=_EVALUATION_TASK_TYPE,
            status="pending",
            attempt_count=0,
            policy_version=source_task.policy_version,
            objective_id=None,
            plan_id=None,
            plan_action_id=None,
            allowed_writes=list(_EVALUATION_ALLOWED_WRITES),
            budget=dict(_R6G_EVALUATION_BUDGET),
            max_attempts=_EVALUATION_MAX_ATTEMPTS,
        )
        session.add(evaluation_task)
        session.flush()
        ObjectiveService._add_event(
            session,
            evaluation_task.id,
            _EVALUATION_REQUEST_EVENT_TYPE,
            payload,
        )
        session.flush()
        self._validate_evaluation_task_request(session, evaluation_task)
        return evaluation_task.id

    def _verify_terminal_evaluation_request(
        self,
        session: Session,
        source_task: Task,
        outcome: Outcome,
        observation: TerminalObservation,
    ) -> None:
        if source_task.task_type != "ingest_source" or source_task.plan_id is None:
            return
        expected_payload = self._evaluation_request_payload(
            source_task, outcome, observation.result_category
        )
        evaluation_task = session.get(
            Task, self._evaluation_task_id(expected_payload)
        )
        if evaluation_task is None:
            raise TaskNotFinalizable("evaluation_task_request_missing")
        validated_payload = self._validate_evaluation_task_request(
            session, evaluation_task
        )
        if validated_payload != expected_payload:
            raise TaskNotFinalizable("evaluation_task_request_mismatch")

    def _committed_evaluation_observation(
        self, session: Session, task: Task
    ) -> TerminalObservation | None:
        request = self._validate_evaluation_task_request(session, task)
        evaluations = list(
            session.scalars(
                select(Evaluation).where(Evaluation.created_by_task_id == task.id)
            )
        )
        related_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type.in_(
                        (
                            "evaluation_proposed",
                            "evaluation_recorded",
                            "evaluation_rejected",
                        )
                    ),
                )
            )
        )
        if not evaluations:
            if related_events:
                raise TaskNotFinalizable("evaluation_task_history_corrupt")
            return None
        if len(evaluations) != 1:
            raise TaskNotFinalizable("evaluation_task_history_conflict")
        evaluation = evaluations[0]
        if (
            evaluation.team_id != task.team_id
            or evaluation.outcome_id != UUID(request["outcome_id"])
            or evaluation.created_by_task_id != task.id
            or evaluation.evaluator_kind != _R6G_EVALUATOR_KIND
            or evaluation.evaluator_identity != _R6G_EVALUATOR_IDENTITY
            or evaluation.evaluator_revision != _R6G_EVALUATOR_REVISION
            or evaluation.idempotency_key
            != self._r6g_evaluation_idempotency_key(request["request_fingerprint"])
        ):
            raise TaskNotFinalizable("evaluation_task_result_binding_invalid")

        links = list(
            session.scalars(
                select(EvidenceLink)
                .where(
                    EvidenceLink.subject_kind == "evaluation",
                    EvidenceLink.subject_id == evaluation.id,
                    EvidenceLink.team_id == task.team_id,
                )
                .order_by(EvidenceLink.reference_key)
            )
        )
        if not links:
            raise TaskNotFinalizable("evaluation_task_evidence_missing")
        from core.evaluations import EvaluationService, _sha256_json

        if self._snapshot_store is None:
            raise TaskNotFinalizable("snapshot_store_not_configured")
        evaluation_service = EvaluationService(
            self._session_factory, self._snapshot_store
        )
        team = session.get(Team, task.team_id)
        if team is None:
            raise TaskNotFinalizable("evaluation_task_team_missing")
        normalized_links: list[dict[str, Any]] = []
        for link in links:
            try:
                evaluation_service._revalidate_link(session, team, link)
            except (AttributeError, ValueError) as error:
                raise TaskNotFinalizable("evaluation_task_evidence_invalid") from error
            normalized_links.append(EvaluationService._link_payload(link))
        if not any(
            link["source_kind"] == "outcome"
            and link["outcome_id"] == str(evaluation.outcome_id)
            for link in normalized_links
        ):
            raise TaskNotFinalizable("evaluation_task_primary_outcome_missing")
        proposal_payload = {
            "team_id": str(task.team_id),
            "outcome_id": str(evaluation.outcome_id),
            "conclusion": evaluation.conclusion,
            "findings": evaluation.findings,
            "evidence": normalized_links,
            "evaluator_kind": evaluation.evaluator_kind,
            "evaluator_identity": evaluation.evaluator_identity,
            "evaluator_revision": evaluation.evaluator_revision,
            "idempotency_key": evaluation.idempotency_key,
        }
        if _sha256_json(proposal_payload) != evaluation.proposal_hash:
            raise TaskNotFinalizable("evaluation_task_proposal_hash_mismatch")

        proposed_events = [
            event
            for event in related_events
            if event.type == "evaluation_proposed"
        ]
        if (
            len(proposed_events) != 1
            or proposed_events[0].payload
            != {
                "evaluation_id": str(evaluation.id),
                "outcome_id": str(evaluation.outcome_id),
                "proposal_hash": evaluation.proposal_hash,
                "evaluator_kind": evaluation.evaluator_kind,
            }
        ):
            raise TaskNotFinalizable("evaluation_task_proposal_event_invalid")

        started_at = self._current_attempt_start(session, task)
        if started_at is None:
            raise TaskNotFinalizable("evaluation_task_start_event_missing")
        if evaluation.status == "proposed":
            if (
                evaluation.resolved_by_task_id is not None
                or evaluation.resolved_at is not None
                or evaluation.rejection_reason is not None
                or len(related_events) != 1
            ):
                raise TaskNotFinalizable(
                    "evaluation_task_proposal_disposition_mismatch"
                )
            return None
        if evaluation.resolved_by_task_id != task.id or evaluation.resolved_at is None:
            raise TaskNotFinalizable("evaluation_task_disposition_owner_invalid")
        if evaluation.status == "recorded":
            disposition_events = [
                event
                for event in related_events
                if event.type == "evaluation_recorded"
            ]
            expected_event = {
                "evaluation_id": str(evaluation.id),
                "outcome_id": str(evaluation.outcome_id),
                "proposal_hash": evaluation.proposal_hash,
            }
            result_category: Literal[
                "success_evaluation_recorded", "success_evaluation_rejected"
            ] = "success_evaluation_recorded"
        elif evaluation.status == "rejected":
            rejection_reason = evaluation.rejection_reason
            if not isinstance(rejection_reason, str) or not rejection_reason:
                raise TaskNotFinalizable(
                    "evaluation_rejection_reason_missing"
                )
            disposition_events = [
                event
                for event in related_events
                if event.type == "evaluation_rejected"
            ]
            expected_event = {
                "evaluation_id": str(evaluation.id),
                "outcome_id": str(evaluation.outcome_id),
                "reason": rejection_reason,
            }
            result_category = "success_evaluation_rejected"
        else:
            raise TaskNotFinalizable("evaluation_task_disposition_invalid")
        if (
            len(disposition_events) != 1
            or disposition_events[0].payload != expected_event
            or len(related_events) != 2
        ):
            raise TaskNotFinalizable("evaluation_task_disposition_event_invalid")
        return TerminalObservation(
            task_id=task.id,
            attempt=task.attempt_count,
            result_category=result_category,
            observed_at=started_at,
            evaluation_id=evaluation.id,
        )

    @staticmethod
    def _r6g_evaluation_idempotency_key(request_fingerprint: str) -> str:
        return "r6g-evaluate-v1:" + request_fingerprint.removeprefix("sha256:")

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
    def _validate_control_task_result(
        session: Session,
        task: Task,
        observation: TerminalObservation,
        *,
        allow_completed: bool = False,
    ) -> None:
        """Validate service-protocol results before TaskRuntime terminalization."""
        if task.status != "running" and not (
            allow_completed and task.status == "done"
        ):
            raise TaskNotFinalizable("task_not_running")
        if task.attempt_count != observation.attempt:
            raise TaskNotFinalizable("stale_attempt")

        if observation.result_category in _STRATEGY_SUCCESS_CATEGORIES:
            if task.task_type != "propose_strategy":
                raise TaskNotFinalizable("strategy_result_wrong_task_type")
            if task.allowed_writes != []:
                raise TaskNotFinalizable("strategy_result_write_scope_violation")
            if task.objective_id is None or any(
                value is not None
                for value in (observation.plan_id, observation.plan_event_id)
            ):
                raise TaskNotFinalizable("strategy_result_scope_invalid")
            events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type.in_(
                            ("strategy_proposal_accepted", "strategy_proposal_rejected")
                        ),
                    )
                )
            )
            expected_type = (
                "strategy_proposal_accepted"
                if observation.result_category == "success_strategy_accepted"
                else "strategy_proposal_rejected"
            )
            if (
                len(events) != 1
                or events[0].id != observation.strategy_event_id
                or events[0].type != expected_type
                or not isinstance(events[0].payload, dict)
            ):
                raise TaskNotFinalizable("strategy_disposition_event_invalid")
            payload = events[0].payload
            reason = payload.get("reason")
            proposal_json = payload.get("proposal_json")
            proposal_hash = payload.get("proposal_hash")
            assessment = payload.get("assessment")
            provenance = payload.get("context_provenance")
            if (
                payload.get("operation") != "propose_strategy"
                or payload.get("team_id") != str(task.team_id)
                or payload.get("objective_id") != str(task.objective_id)
                or payload.get("policy_version") != task.policy_version
                or (
                    expected_type == "strategy_proposal_accepted"
                    and reason is not None
                )
                or (
                    expected_type == "strategy_proposal_rejected"
                    and (not isinstance(reason, str) or not reason.strip())
                )
                or not isinstance(proposal_json, str)
                or not isinstance(proposal_hash, str)
                or hashlib.sha256(proposal_json.encode("utf-8")).hexdigest()
                != proposal_hash
                or not isinstance(assessment, dict)
                or not isinstance(assessment.get("basis"), dict)
                or not isinstance(assessment["basis"].get("sha256"), str)
                or (
                    provenance is not None
                    and (
                        not isinstance(provenance, dict)
                        or set(provenance)
                        != {"event_id", "snapshot_ref", "content_hash"}
                    )
                )
            ):
                raise TaskNotFinalizable("strategy_disposition_payload_invalid")
            charge_reference = payload.get("generation_charge_id")
            if provenance is None and charge_reference is None:
                if session.scalar(
                    select(Event.id).where(
                        Event.task_id == task.id,
                        Event.type == "context_assembled",
                    )
                ) is not None:
                    raise TaskNotFinalizable(
                        "strategy_disposition_provenance_mismatch"
                    )
            else:
                if not isinstance(provenance, dict) or set(provenance) != {
                    "event_id", "snapshot_ref", "content_hash"
                }:
                    raise TaskNotFinalizable(
                        "strategy_disposition_provenance_invalid"
                    )
                try:
                    context_event_id = UUID(provenance["event_id"])
                    charge_id = UUID(charge_reference)
                except (KeyError, TypeError, ValueError) as error:
                    raise TaskNotFinalizable(
                        "strategy_disposition_provenance_invalid"
                    ) from error
                context_event = session.get(Event, context_event_id)
                charge = session.get(TaskGenerationCharge, charge_id)
                if (
                    context_event is None
                    or context_event.task_id != task.id
                    or context_event.type != "context_assembled"
                    or context_event.payload.get("snapshot_ref")
                    != provenance["snapshot_ref"]
                    or context_event.payload.get("content_hash")
                    != provenance["content_hash"]
                    or charge is None
                    or charge.task_id != task.id
                    or charge.operation != "strategy_proposal"
                    or charge.status != "reconciled"
                    or charge.accounted_cost_usd is None
                    or charge.input_tokens is None
                    or charge.output_tokens is None
                    or charge.attempt_count > task.attempt_count
                ):
                    raise TaskNotFinalizable(
                        "strategy_disposition_provenance_mismatch"
                    )
            if session.scalar(
                select(Plan.id).where(Plan.created_by_task_id == task.id)
            ) is not None:
                raise TaskNotFinalizable("strategy_task_materialized_plan")
            return

        if observation.result_category == "success_plan_created":
            if (
                task.task_type != "create_plan"
                or task.allowed_writes != ["Plan"]
                or task.objective_id is None
                or observation.plan_id is None
                or observation.plan_event_id is None
                or observation.strategy_event_id is not None
            ):
                raise TaskNotFinalizable("plan_result_scope_invalid")
            plan = session.get(Plan, observation.plan_id)
            if (
                plan is None
                or plan.created_by_task_id != task.id
                or plan.team_id != task.team_id
                or plan.objective_id != task.objective_id
            ):
                raise TaskNotFinalizable("plan_result_not_created_by_task")
            created_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == "plan_created",
                    )
                )
            )
            if (
                len(created_events) != 1
                or created_events[0].id != observation.plan_event_id
                or created_events[0].payload.get("plan_id") != str(plan.id)
            ):
                raise TaskNotFinalizable("plan_created_event_invalid")
            # Reuse the service's complete reconstruction validator: accepted
            # Strategy provenance, immutable actions, materialized Tasks,
            # Plan lifecycle and the exact plan_created payload are all checked.
            from core.plans import PlanService

            try:
                reconstructed = PlanService._reconstruct(session, plan.id)
            except ValueError as error:
                raise TaskNotFinalizable(
                    "plan_creation_records_corrupt"
                ) from error
            if (
                reconstructed.event_id != observation.plan_event_id
                or reconstructed.plan_id != observation.plan_id
            ):
                raise TaskNotFinalizable("plan_created_reconstruction_mismatch")
            return

        raise TaskNotFinalizable("control_task_result_unsupported")

    def _committed_control_task_observation(
        self, session: Session, task: Task
    ) -> TerminalObservation | None:
        """Reconstruct a committed Strategy/Plan service result for recovery."""
        started_at = self._current_attempt_start(session, task)
        if started_at is None:
            raise TaskNotFinalizable("control_task_start_event_missing")
        if task.task_type == "propose_strategy":
            events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type.in_(
                            ("strategy_proposal_accepted", "strategy_proposal_rejected")
                        ),
                    )
                )
            )
            if not events:
                return None
            if len(events) != 1:
                raise TaskNotFinalizable("strategy_disposition_event_conflict")
            event = events[0]
            observation = TerminalObservation(
                task_id=task.id,
                attempt=task.attempt_count,
                result_category=(
                    "success_strategy_accepted"
                    if event.type == "strategy_proposal_accepted"
                    else "success_strategy_rejected"
                ),
                observed_at=started_at,
                strategy_event_id=event.id,
            )
            self._validate_control_task_result(session, task, observation)
            return observation

        if task.task_type == "create_plan":
            created = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == "plan_created",
                    )
                )
            )
            rejected = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == "plan_creation_rejected",
                    )
                )
            )
            if created and rejected:
                raise TaskNotFinalizable("plan_creation_disposition_conflict")
            if created:
                if len(created) != 1 or not isinstance(created[0].payload, dict):
                    raise TaskNotFinalizable("plan_created_event_conflict")
                try:
                    plan_id = UUID(created[0].payload["plan_id"])
                except (KeyError, TypeError, ValueError) as error:
                    raise TaskNotFinalizable("plan_created_event_invalid") from error
                observation = TerminalObservation(
                    task_id=task.id,
                    attempt=task.attempt_count,
                    result_category="success_plan_created",
                    observed_at=started_at,
                    plan_id=plan_id,
                    plan_event_id=created[0].id,
                )
                self._validate_control_task_result(session, task, observation)
                return observation
            if rejected:
                if len(rejected) != 1 or not isinstance(rejected[0].payload, dict):
                    raise TaskNotFinalizable("plan_rejection_event_conflict")
                payload = rejected[0].payload
                reason = payload.get("reason")
                if (
                    payload.get("operation") != "create_plan"
                    or payload.get("team_id") != str(task.team_id)
                    or payload.get("objective_id") != str(task.objective_id)
                    or payload.get("accepted_event_id") is None
                    or payload.get("proposal_hash") is None
                    or not isinstance(reason, str)
                    or not reason.strip()
                ):
                    raise TaskNotFinalizable("plan_rejection_event_invalid")
                return TerminalObservation(
                    task_id=task.id,
                    attempt=task.attempt_count,
                    result_category="terminal_failure",
                    observed_at=started_at,
                    failure_reason=reason,
                )
            if session.scalar(
                select(Plan.id).where(Plan.created_by_task_id == task.id)
            ) is not None:
                raise TaskNotFinalizable("plan_creation_event_missing")
            return None

        return None

    @staticmethod
    def _validate_evaluation_result(session: Session, task: Task,
        observation: TerminalObservation) -> None:
        if task.task_type != "evaluate_outcome":
            raise TaskNotFinalizable("evaluation_result_wrong_task_type")
        if TaskRuntime._is_r6g_evaluation_task(session, task):
            TaskRuntime._validate_evaluation_task_request(session, task)
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
    def _validate_knowledge_quality_result(
        session: Session,
        task: Task,
        observation: TerminalObservation,
        *,
        allow_completed: bool = False,
    ) -> None:
        from core.knowledge_quality import (
            KnowledgeQualityAssessmentError,
            require_recorded_assessment,
        )

        if (
            task.task_type != _KNOWLEDGE_QUALITY_TASK_TYPE
            or task.team_id is None
            or task.allowed_writes != _KNOWLEDGE_QUALITY_ALLOWED_WRITES
            or task.objective_id is not None
            or task.plan_id is not None
            or task.plan_action_id is not None
            or task.max_attempts != _KNOWLEDGE_QUALITY_MAX_ATTEMPTS
            or task.budget != _KNOWLEDGE_QUALITY_BUDGET
            or task.status != ("done" if allow_completed else "running")
            or task.attempt_count != observation.attempt
            or observation.knowledge_quality_assessment_id is None
        ):
            raise TaskNotFinalizable("knowledge_quality_result_task_shape_invalid")
        assessment = session.scalar(
            select(KnowledgeQualityAssessment).where(
                KnowledgeQualityAssessment.id
                == observation.knowledge_quality_assessment_id,
                KnowledgeQualityAssessment.team_id == task.team_id,
                KnowledgeQualityAssessment.creating_task_id == task.id,
            )
        )
        if assessment is None:
            raise TaskNotFinalizable("knowledge_quality_assessment_not_recorded")
        learning_change = session.get(LearningChange, assessment.learning_change_id)
        if learning_change is None or learning_change.team_id != task.team_id:
            raise TaskNotFinalizable("knowledge_quality_learning_change_missing")
        try:
            require_recorded_assessment(
                session,
                learning_change,
                require_task_done=allow_completed,
            )
        except KnowledgeQualityAssessmentError as error:
            raise TaskNotFinalizable(str(error)) from error
        if allow_completed and task.completed_at != observation.observed_at:
            raise TaskNotFinalizable("knowledge_quality_terminal_timestamp_mismatch")

    @staticmethod
    def _validate_learning_change_decision_result(
        session: Session,
        task: Task,
        observation: TerminalObservation,
        *,
        allow_completed: bool = False,
    ) -> None:
        """Validate a committed Operator decision before Task terminalization."""
        if task.task_type != _OPERATOR_TASK_TYPE:
            raise TaskNotFinalizable(
                "learning_change_decision_result_wrong_task_type"
            )
        if task.status != "running" and not (
            allow_completed and task.status == "done"
        ):
            raise TaskNotFinalizable("task_not_running")
        if task.attempt_count != observation.attempt:
            raise TaskNotFinalizable("stale_attempt")
        if task.allowed_writes != _OPERATOR_ALLOWED_WRITES:
            raise TaskNotFinalizable(
                "learning_change_decision_write_scope_violation"
            )
        if allow_completed and task.completed_at != observation.observed_at:
            raise TaskNotFinalizable("recorded_terminal_outcome_corrupt")

        try:
            TaskRuntime._validate_operator_admission(
                session, task, allow_completed=allow_completed
            )
        except TaskNotEligible as error:
            raise TaskNotFinalizable(
                "operator_task_request_event_invalid"
            ) from error

        request_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == _OPERATOR_REQUEST_EVENT_TYPE,
                )
            )
        )
        if len(request_events) != 1 or not isinstance(
            request_events[0].payload, dict
        ):
            raise TaskNotFinalizable("operator_task_request_event_invalid")
        request_payload = request_events[0].payload

        requested_decision = request_payload.get("decision")
        expected_decision = (
            "accept"
            if observation.result_category == "success_learning_change_accepted"
            else "reject"
        )
        if requested_decision != expected_decision:
            raise TaskNotFinalizable("learning_change_decision_result_mismatch")
        quality_assessment_id_value = request_payload.get(
            "knowledge_quality_assessment_id"
        )
        quality_assessment_hash = request_payload.get(
            "knowledge_quality_assessment_hash"
        )
        if expected_decision == "accept":
            from core.knowledge_quality import (
                KnowledgeQualityAssessmentError,
                require_recorded_assessment,
            )

            if (
                not isinstance(quality_assessment_id_value, str)
                or not isinstance(quality_assessment_hash, str)
            ):
                raise TaskNotFinalizable("operator_quality_assessment_required")
            try:
                quality_assessment_id = UUID(quality_assessment_id_value)
            except ValueError as error:
                raise TaskNotFinalizable(
                    "operator_quality_assessment_reference_invalid"
                ) from error
            if str(quality_assessment_id) != quality_assessment_id_value:
                raise TaskNotFinalizable(
                    "operator_quality_assessment_reference_invalid"
                )
        elif quality_assessment_id_value is not None or quality_assessment_hash is not None:
            raise TaskNotFinalizable("operator_quality_assessment_reference_invalid")
        learning_change_id_value = request_payload.get("learning_change_id")
        try:
            learning_change_id = UUID(learning_change_id_value)
        except (TypeError, ValueError) as error:
            raise TaskNotFinalizable(
                "operator_task_request_target_invalid"
            ) from error
        if (
            str(learning_change_id) != learning_change_id_value
            or observation.learning_change_id != learning_change_id
        ):
            raise TaskNotFinalizable("learning_change_decision_target_mismatch")

        learning_change = session.scalar(
            select(LearningChange)
            .where(
                LearningChange.id == learning_change_id,
                LearningChange.team_id == task.team_id,
            )
            .with_for_update()
        )
        expected_status = "accepted" if expected_decision == "accept" else "rejected"
        if learning_change is None or learning_change.team_id != task.team_id:
            raise TaskNotFinalizable("learning_change_not_found_for_task_team")
        if expected_decision == "accept":
            from core.knowledge_quality import (
                KnowledgeQualityAssessmentError,
                require_recorded_assessment,
            )

            try:
                quality_assessment = require_recorded_assessment(
                    session, learning_change, require_task_done=True
                )
            except KnowledgeQualityAssessmentError as error:
                raise TaskNotFinalizable(str(error)) from error
            if (
                str(quality_assessment.id) != quality_assessment_id_value
                or quality_assessment.assessment_payload_hash != quality_assessment_hash
            ):
                raise TaskNotFinalizable("operator_quality_assessment_binding_invalid")
        if (
            learning_change is None
            or learning_change.status != expected_status
            or learning_change.committed_by_task_id != task.id
            or learning_change.operator_id != request_payload.get("operator_id")
            or learning_change.decision_reason != request_payload.get(
                "rejection_reason"
            )
            or learning_change.previous_state is not None
            or learning_change.target_kind != "knowledge_item"
            or learning_change.target_id is not None
            or learning_change.operation != "create"
            or not isinstance(learning_change.proposed_state, dict)
            or learning_change.committed_at is None
            or learning_change.committed_at != observation.observed_at
        ):
            raise TaskNotFinalizable("learning_change_decision_state_mismatch")

        evidence_basis_hash = learning_change.evidence_basis_hash
        proposal_hash = learning_change.proposed_state.get("proposal_hash")
        for value in (evidence_basis_hash, proposal_hash):
            if (
                not isinstance(value, str)
                or len(value) != 71
                or not value.startswith("sha256:")
                or any(character not in "0123456789abcdef" for character in value[7:])
            ):
                raise TaskNotFinalizable("learning_change_decision_hash_invalid")

        decision_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type.in_(_OPERATOR_DECISION_EVENT_TYPES),
                )
            )
        )
        expected_event_type = (
            "learning_change_accepted"
            if expected_decision == "accept"
            else "learning_change_rejected"
        )
        if len(decision_events) != 1:
            raise TaskNotFinalizable("learning_change_decision_event_invalid")
        decision_event = decision_events[0]
        event_payload = decision_event.payload
        if not isinstance(event_payload, dict):
            raise TaskNotFinalizable("learning_change_decision_event_invalid")

        decision_attempt = event_payload.get("attempt_count")
        if (
            isinstance(decision_attempt, bool)
            or not isinstance(decision_attempt, int)
            or decision_attempt < 1
            or decision_attempt > task.attempt_count
        ):
            raise TaskNotFinalizable("learning_change_decision_event_mismatch")

        decision_start_event: Event | None = None
        for started_attempt in {decision_attempt, observation.attempt}:
            start_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == "task_started",
                        Event.payload["attempt_count"].as_integer()
                        == started_attempt,
                    )
                )
            )
            if (
                len(start_events) != 1
                or start_events[0].payload
                != {
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": started_attempt,
                }
            ):
                raise TaskNotFinalizable("approval_task_start_event_invalid")
            if started_attempt == decision_attempt:
                decision_start_event = start_events[0]

        expected_payload: dict[str, Any] = {
            "schema_version": 1,
            "learning_change_id": str(learning_change.id),
            "operation": "create",
            "decision": expected_decision,
            "operator_id": request_payload["operator_id"],
            "approval_task_id": str(task.id),
            "attempt_count": decision_attempt,
            "evidence_basis_hash": evidence_basis_hash,
            "proposal_hash": proposal_hash,
            "committed_at": learning_change.committed_at.isoformat(),
        }

        if expected_decision == "accept":
            expected_payload["knowledge_quality_assessment_id"] = (
                quality_assessment_id_value
            )
            expected_payload["knowledge_quality_assessment_hash"] = (
                quality_assessment_hash
            )
            items = list(
                session.scalars(
                    select(KnowledgeItem).where(
                        KnowledgeItem.origin_learning_change_id
                        == learning_change.id
                    )
                )
            )
            if len(items) != 1:
                raise TaskNotFinalizable(
                    "committed_knowledge_item_missing_or_duplicate"
                )
            item = items[0]
            expected_payload["knowledge_item_id"] = str(item.id)
            expected_payload["knowledge_item_version"] = 1
            if (
                learning_change.decision_reason is not None
                or item.team_id != task.team_id
                or item.version != 1
                or item.status != "active"
                or learning_change.committed_state
                != TaskRuntime._knowledge_item_state(item)
            ):
                raise TaskNotFinalizable("committed_knowledge_item_mismatch")
        else:
            expected_payload["reason"] = request_payload.get("rejection_reason")
            existing_item = session.scalar(
                select(KnowledgeItem.id).where(
                    KnowledgeItem.origin_learning_change_id == learning_change.id
                )
            )
            if (
                learning_change.committed_state is not None
                or existing_item is not None
                or not isinstance(request_payload.get("rejection_reason"), str)
                or not request_payload["rejection_reason"]
            ):
                raise TaskNotFinalizable(
                    "rejected_learning_change_has_knowledge_item"
                )

        if (
            decision_event.type != expected_event_type
            or event_payload != expected_payload
            or decision_event.created_at != learning_change.committed_at
            or decision_start_event is None
            or decision_event.created_at < decision_start_event.created_at
        ):
            raise TaskNotFinalizable("learning_change_decision_event_mismatch")

    @staticmethod
    def _knowledge_item_state(item: KnowledgeItem) -> dict[str, Any]:
        """Reconstruct every canonical field captured by LearningCommitService."""
        return {
            "id": str(item.id),
            "team_id": str(item.team_id),
            "kind": item.kind,
            "title": item.title,
            "statement": item.statement,
            "body": item.body,
            "applicability": item.applicability,
            "preconditions": item.preconditions,
            "assumptions": item.assumptions,
            "limitations": item.limitations,
            "non_applicability": item.non_applicability,
            "failure_modes": item.failure_modes,
            "known_counterexamples": item.known_counterexamples,
            "missing_information": item.missing_information,
            "uncertainty": item.uncertainty,
            "confidence": str(item.confidence),
            "status": item.status,
            "version": item.version,
            "last_validated_at": (
                item.last_validated_at.isoformat()
                if item.last_validated_at is not None
                else None
            ),
            "review_after": (
                item.review_after.isoformat() if item.review_after is not None else None
            ),
            "origin_learning_change_id": str(item.origin_learning_change_id),
        }

    @staticmethod
    def _validate_learning_change_result(
        session: Session, task: Task, observation: TerminalObservation
    ) -> None:
        if task.task_type != "propose_learning_change":
            raise TaskNotFinalizable("learning_change_result_wrong_task_type")
        if task.allowed_writes != ["LearningChange"]:
            raise TaskNotFinalizable("learning_change_result_write_scope_violation")
        learning_change = session.scalar(
            select(LearningChange).where(
                LearningChange.id == observation.learning_change_id,
                LearningChange.team_id == task.team_id,
            )
        )
        if (
            learning_change is None
            or learning_change.proposed_by_task_id != task.id
            or learning_change.status != "proposed"
            or learning_change.target_kind != "knowledge_item"
            or learning_change.target_id is not None
            or learning_change.operation != "create"
            or learning_change.evidence_basis_hash
            != learning_change.proposed_state.get("evidence_basis_hash")
            or len(learning_change.evidence_basis) < 1
            or len(learning_change.evidence_basis) > 8
            or learning_change.proposed_state.get("evidence_case_count")
            != len(learning_change.evidence_basis)
        ):
            raise TaskNotFinalizable("learning_change_not_proposed")
        proposal_hash = learning_change.proposed_state.get("proposal_hash")
        if (
            not isinstance(proposal_hash, str)
            or not proposal_hash.startswith("sha256:")
            or len(proposal_hash) != 71
        ):
            raise TaskNotFinalizable("learning_change_proposal_hash_invalid")
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == task.id,
                TaskGenerationCharge.attempt_count == task.attempt_count,
                TaskGenerationCharge.operation == "experience_distillation",
            )
        )
        if charge is None or charge.status != "reconciled":
            raise TaskNotFinalizable("experience_distillation_cost_not_reconciled")
        proposal_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == "learning_change_proposed",
                )
            )
        )
        if len(proposal_events) != 1:
            raise TaskNotFinalizable("learning_change_proposal_event_missing")
        payload = proposal_events[0].payload
        if (
            payload.get("learning_change_id") != str(learning_change.id)
            or payload.get("evidence_basis_hash")
            != learning_change.evidence_basis_hash
            or payload.get("proposal_hash") != proposal_hash
            or payload.get("generation_charge_id") != str(charge.id)
            or payload.get("attempt_count") != task.attempt_count
            or payload.get("operation") != "create"
            or payload.get("kind") != learning_change.proposed_state.get("kind")
            or payload.get("evaluation_ids")
            != [
                item.get("evaluation_id")
                for item in learning_change.evidence_basis
            ]
        ):
            raise TaskNotFinalizable("learning_change_proposal_event_mismatch")

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
                if observation.signals or observation.learning_change_id is not None:
                    raise TaskNotFinalizable("terminal_evidence_not_allowed")
            elif observation.result_category in (
                _LEARNING_CHANGE_SUCCESS_CATEGORIES
                | _LEARNING_CHANGE_DECISION_SUCCESS_CATEGORIES
            ):
                if observation.learning_change_id is None:
                    raise TaskNotFinalizable("learning_change_id_required")
                if observation.signals or observation.evaluation_id is not None:
                    raise TaskNotFinalizable("terminal_evidence_not_allowed")
            elif observation.result_category in _STRATEGY_SUCCESS_CATEGORIES:
                if observation.strategy_event_id is None:
                    raise TaskNotFinalizable("strategy_event_id_required")
                if (
                    observation.signals
                    or observation.evaluation_id is not None
                    or observation.learning_change_id is not None
                    or observation.plan_id is not None
                    or observation.plan_event_id is not None
                ):
                    raise TaskNotFinalizable("terminal_evidence_not_allowed")
            elif observation.result_category in _PLAN_SUCCESS_CATEGORIES:
                if observation.plan_id is None or observation.plan_event_id is None:
                    raise TaskNotFinalizable("plan_result_identity_required")
                if (
                    observation.signals
                    or observation.evaluation_id is not None
                    or observation.learning_change_id is not None
                    or observation.strategy_event_id is not None
                ):
                    raise TaskNotFinalizable("terminal_evidence_not_allowed")
            elif observation.result_category in _KNOWLEDGE_QUALITY_SUCCESS_CATEGORIES:
                if observation.knowledge_quality_assessment_id is None:
                    raise TaskNotFinalizable("knowledge_quality_assessment_id_required")
                if (
                    observation.signals
                    or observation.evaluation_id is not None
                    or observation.learning_change_id is not None
                    or observation.strategy_event_id is not None
                    or observation.plan_id is not None
                    or observation.plan_event_id is not None
                ):
                    raise TaskNotFinalizable("terminal_evidence_not_allowed")
            elif (observation.signals or observation.evaluation_id is not None
                or observation.learning_change_id is not None
                or observation.strategy_event_id is not None
                or observation.plan_id is not None
                or observation.plan_event_id is not None
                or observation.knowledge_quality_assessment_id is not None):
                raise TaskNotFinalizable("terminal_evidence_not_allowed")
            return

        if (
            observation.evaluation_id is not None
            or observation.learning_change_id is not None
            or observation.strategy_event_id is not None
            or observation.plan_id is not None
            or observation.plan_event_id is not None
            or observation.knowledge_quality_assessment_id is not None
        ):
            raise TaskNotFinalizable("terminal_evidence_not_allowed")
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
        if observation.learning_change_id is not None:
            payload["learning_change_id"] = str(observation.learning_change_id)
        if observation.strategy_event_id is not None:
            payload["strategy_event_id"] = str(observation.strategy_event_id)
        if observation.plan_id is not None:
            payload["plan_id"] = str(observation.plan_id)
        if observation.plan_event_id is not None:
            payload["plan_event_id"] = str(observation.plan_event_id)
        if observation.knowledge_quality_assessment_id is not None:
            payload["knowledge_quality_assessment_id"] = str(
                observation.knowledge_quality_assessment_id
            )
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