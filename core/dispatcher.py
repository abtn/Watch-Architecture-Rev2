"""R6-B dispatcher for the bounded configured-source `ingest_source` worker.

This is the first working execution path: it claims one eligible Task through
`TaskRuntime`, resolves the Task's durable configured source, fetches it with
the approved restricted fetcher, commits the bytes through the existing
`IngestionService`, and reports the result back to `TaskRuntime`.

Authority boundaries this module deliberately does not cross (ADR-0030 §1):

- `TaskRuntime` remains the only lifecycle authority. The dispatcher never
  writes Task status, `attempt_count`, `completed_at`, lifecycle Events, or
  terminal Outcomes/Snapshots; it calls `admit()`, `finalize()`,
  `report_failure()`, and `recover_interrupted()`.
- The only durable write the dispatcher causes directly is through
  `IngestionService.ingest()`, which owns the Signal/Snapshot/Event commit.
- No second runtime, scheduler, retry loop, model call, or general-purpose
  network access. One dispatch call makes at most one attempt.

Durable source identity for this slice is the Task's `PlanAction`: a
Plan-materialized `ingest_source` Task carries `plan_id` + `plan_action_id`,
and the Action JSONB holds the `(origin_url, source_type)` pair that
`TeamPolicy.rules["sources"]` must authorize. There is no separate Task
payload/input column, so a reactive `ingest_source` Task with no Plan Action
has no durable source identity and is rejected rather than guessed at.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.ingestion import (
    IngestionProposal,
    IngestionResult,
    IngestionService,
    IngestionValidationError,
)
from core.models import Event, PlanAction, Signal, Task, TeamPolicy
from core.snapshot_store import SnapshotStore
from core.source_fetch import (
    Fetcher,
    SourceFetchError,
    SourceFetchRequest,
    SourceFetchResult,
)
from core.task_runtime import (
    FailureObservation,
    RecoveryResult,
    SignalEvidence,
    TaskNotFinalizable,
    TaskRuntime,
    TerminalObservation,
)

_SUPPORTED_TASK_TYPE = "ingest_source"


class TaskNotDispatchable(ValueError):
    """Raised when a Task is not this dispatcher's supported work.

    Raised before any lifecycle transition, so an unsupported or unconfigured
    Task is not admitted and consumes no attempt.
    """


@dataclass(frozen=True)
class DispatchResult:
    """What one dispatch call did to its Task.

    `status` is the resulting Task status: `done`, `failed`, or `pending` when
    a retryable attempt failure returned the Task for redelivery.
    """

    task_id: UUID
    attempt: int
    status: str
    result_category: str | None
    failure_reason: str | None
    signal_id: UUID | None
    outcome_id: UUID | None
    event_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class SourceConfiguration:
    """The durable, policy-authorized source a Task is allowed to fetch."""

    origin_url: str
    source_type: str


class TaskDispatcher:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
        fetcher: Fetcher,
        runtime: TaskRuntime | None = None,
        ingestion: IngestionService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store
        self._fetcher = fetcher
        self._runtime = runtime or TaskRuntime(session_factory, snapshot_store)
        self._ingestion = ingestion or IngestionService(
            session_factory, snapshot_store
        )

    @property
    def runtime(self) -> TaskRuntime:
        return self._runtime

    def recover_interrupted(self) -> RecoveryResult:
        """Run interrupted-Task recovery at dispatcher startup.

        A thin, named entry point so startup wiring does not reach into the
        runtime directly; recovery itself stays owned by `TaskRuntime`.
        """
        return self._runtime.recover_interrupted()

    def find_eligible_task(self) -> UUID | None:
        """Return the oldest `pending` supported Task, or `None`.

        Read-only; it does not claim the Task. `dispatch()` re-checks
        eligibility through `TaskRuntime.admit()` under the Task-row lock, so a
        Task another dispatcher claimed first is rejected, not double-started.
        """
        with self._session_factory() as session:
            return session.scalar(
                select(Task.id)
                .where(
                    Task.status == "pending",
                    Task.task_type == _SUPPORTED_TASK_TYPE,
                )
                .order_by(Task.created_at, Task.id)
                .limit(1)
            )

    def dispatch(self, task_id: UUID) -> DispatchResult:
        """Admit, execute, and report exactly one attempt of one Task."""
        configuration = self._load_source_configuration(task_id)

        admitted = self._runtime.admit(task_id)
        attempt = admitted.attempt_count

        try:
            fetch = self._fetcher.fetch(
                SourceFetchRequest(
                    origin_url=configuration.origin_url,
                    source_type=configuration.source_type,
                )
            )
        except SourceFetchError as error:
            return self._report_attempt_failure(task_id, attempt, error)

        return self._ingest_and_finalize(task_id, attempt, configuration, fetch)

    def _load_source_configuration(self, task_id: UUID) -> SourceConfiguration:
        """Resolve the Task's durable source, authorized by its TeamPolicy.

        Validation happens before admission, so a Task with missing, malformed,
        unsupported, or unauthorized source configuration is rejected without
        consuming an attempt or emitting a lifecycle Event.
        """
        with self._session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise TaskNotDispatchable("task_not_found")
            if task.task_type != _SUPPORTED_TASK_TYPE:
                raise TaskNotDispatchable("task_type_not_supported")
            if task.allowed_writes != ["Signal"]:
                raise TaskNotDispatchable("write_scope_violation")
            if task.plan_id is None or task.plan_action_id is None:
                # No durable source identity exists for a reactive Task.
                raise TaskNotDispatchable("source_configuration_missing")

            action = session.get(PlanAction, (task.plan_id, task.plan_action_id))
            if (
                action is None
                or not isinstance(action.action, dict)
                or action.action.get("id") != str(action.action_id)
            ):
                raise TaskNotDispatchable("source_configuration_missing")

            payload = action.action
            if payload.get("task_type") != _SUPPORTED_TASK_TYPE:
                raise TaskNotDispatchable("source_configuration_unsupported")
            if payload.get("tools"):
                # This slice grants no tool capability.
                raise TaskNotDispatchable("source_configuration_unsupported")

            origin_url = payload.get("origin_url")
            source_type = payload.get("source_type")
            if (
                not isinstance(origin_url, str)
                or not origin_url
                or not isinstance(source_type, str)
                or not source_type
            ):
                raise TaskNotDispatchable("source_configuration_malformed")

            policy = session.scalar(
                select(TeamPolicy).where(
                    TeamPolicy.team_id == task.team_id,
                    TeamPolicy.version == task.policy_version,
                )
            )
            if policy is None:
                raise TaskNotDispatchable("source_configuration_missing")
            sources = policy.rules.get("sources")
            if not isinstance(sources, list) or not any(
                isinstance(source, dict)
                and source.get("origin_url") == origin_url
                and source.get("source_type") == source_type
                for source in sources
            ):
                raise TaskNotDispatchable("source_not_configured")

        return SourceConfiguration(origin_url, source_type)

    def _report_attempt_failure(
        self, task_id: UUID, attempt: int, error: SourceFetchError
    ) -> DispatchResult:
        """Route a categorized failure through the lifecycle owner.

        `observed_at` is the durable start of the attempt being reported, so a
        repeated report for the same attempt replays instead of conflicting on
        a fresh timestamp (ADR-0030 §4).
        """
        failure = FailureObservation(
            task_id=task_id,
            attempt=attempt,
            observed_at=self._attempt_started_at(task_id, attempt),
            reason=error.reason,
            retryable=error.retryable,
        )
        result = self._runtime.report_failure(failure)
        return DispatchResult(
            task_id=task_id,
            attempt=result.attempt_count,
            status=result.status,
            result_category=(
                None if result.retry_scheduled else "terminal_failure"
            ),
            failure_reason=None if result.retry_scheduled else failure.reason,
            signal_id=None,
            outcome_id=(
                result.terminal.outcome_id
                if result.terminal is not None
                else None
            ),
            event_ids=result.event_ids,
        )

    def _ingest_and_finalize(
        self,
        task_id: UUID,
        attempt: int,
        configuration: SourceConfiguration,
        fetch: SourceFetchResult,
    ) -> DispatchResult:
        """Commit fetched bytes through `IngestionService`, then finalize.

        A crash between the ingestion commit and finalization is safe: the next
        attempt replays the recorded ingestion outcome (no duplicate Signal or
        Event) and then finalizes the Task once.
        """
        proposal = IngestionProposal(
            task_id=task_id,
            origin_url=configuration.origin_url,
            source_type=configuration.source_type,
            fetched_at=fetch.fetched_at,
            content=fetch.content,
            claimed_content_hash=(
                f"sha256:{hashlib.sha256(fetch.content).hexdigest()}"
            ),
        )

        try:
            ingestion = self._ingestion.ingest(proposal)
        except IngestionValidationError as error:
            # `IngestionService` records the attributed rejection Event and
            # raises a categorized reason. Application/policy rejections are
            # non-retryable per ADR-0030 §2.
            return self._report_attempt_failure(
                task_id,
                attempt,
                SourceFetchError(error.reason, retryable=False),
            )

        observation = self._success_observation(
            task_id, attempt, ingestion
        )
        finalized = self._runtime.finalize(observation)

        return DispatchResult(
            task_id=task_id,
            attempt=attempt,
            status=finalized.status,
            result_category=observation.result_category,
            failure_reason=None,
            signal_id=ingestion.signal_id,
            outcome_id=finalized.outcome_id,
            event_ids=finalized.event_ids,
        )

    def _success_observation(
        self,
        task_id: UUID,
        attempt: int,
        ingestion: IngestionResult,
    ) -> TerminalObservation:
        """Build the deterministic success observation for the Outcome.

        The result category and `observed_at` are both derived from the
        committed ingestion Event rather than from the in-memory
        `IngestionResult.outcome`. That distinction matters after a crash: a
        replay reports `outcome="replayed"`, and the original category is only
        recoverable from the recorded Event type. Deriving both from the Event
        makes a crashed-then-replayed run produce a byte-identical canonical
        observation, so the Outcome replays instead of conflicting.
        """
        event_type, observed_at = self._ingestion_event(task_id, ingestion.event_id)
        if event_type == "signal_ingested":
            return TerminalObservation(
                task_id=task_id,
                attempt=attempt,
                result_category="success_signal_created",
                observed_at=observed_at,
                signals=(self._signal_evidence(ingestion.signal_id),),
            )
        if event_type == "fetch_no_change":
            return TerminalObservation(
                task_id=task_id,
                attempt=attempt,
                result_category="success_no_change",
                observed_at=observed_at,
            )
        raise TaskNotFinalizable("unexpected_ingestion_event_type")

    def _signal_evidence(self, signal_id: UUID) -> SignalEvidence:
        with self._session_factory() as session:
            signal = session.get(Signal, signal_id)
            if signal is None:
                raise TaskNotFinalizable("signal_not_found")
            return SignalEvidence(
                signal_id=signal.id,
                snapshot_ref=signal.snapshot_ref,
                content_hash=signal.content_hash,
            )

    def _ingestion_event(
        self, task_id: UUID, event_id: UUID
    ) -> tuple[str, datetime]:
        with self._session_factory() as session:
            row = session.execute(
                select(Event.type, Event.created_at).where(
                    Event.id == event_id, Event.task_id == task_id
                )
            ).one_or_none()
        if row is None:
            raise TaskNotFinalizable("ingestion_event_not_found")
        return row[0], row[1]

    def _attempt_started_at(self, task_id: UUID, attempt: int) -> datetime:
        """The durable `task_started` time of the attempt being reported."""
        with self._session_factory() as session:
            created_at = session.scalar(
                select(Event.created_at).where(
                    Event.task_id == task_id,
                    Event.type == "task_started",
                    Event.payload["attempt_count"].as_integer() == attempt,
                )
            )
        if created_at is None:
            raise TaskNotFinalizable("attempt_start_not_found")
        return created_at
