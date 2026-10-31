"""Read-only, Objective-scoped reconstruction of implemented operational state.

Tasks are related only by Task.objective_id and matching Team ownership.
Objective lifecycle Events relate independently through an exact
payload.objective_id reference and do not promote their Task into Objective
scope. Other Events relate only through directly linked Tasks. Signals are
included only as ingestion records explicitly named by a recognized ingestion
Event on a directly Objective-linked Task; they are not interpreted as evidence
or as domain-memory records.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Objective, Signal, Task, Team, TeamPolicy

_OBJECTIVE_EVENT_TYPES = ("objective_created", "objective_transitioned")
_INGESTION_EVENT_TYPES = ("signal_ingested", "fetch_no_change")
# These Events record execution protocol and proposal disposition, not
# Objective-domain changes. Task status remains projected separately; excluding
# lifecycle Events prevents attempt/recovery audit history from mutating an
# immutable Context basis across ordinary TaskRuntime retries. Cost Events and
# proposal dispositions are also audit-only in this Objective-domain projection.
_NON_DOMAIN_ASSESSMENT_EVENT_TYPES = frozenset(
    {
        "context_assembled",
        "strategy_proposal_accepted",
        "strategy_proposal_rejected",
        "generation_cost_reserved",
        "generation_cost_reconciled",
        "generation_cost_unknown",
        "generation_cost_overrun",
        "task_started",
        "task_attempt_failed",
        "task_retry_scheduled",
        "task_completed",
        "task_failed",
    }
)


class ObjectiveNotFound(LookupError):
    """Raised when an assessment is requested for an unknown Objective."""

    def __init__(self) -> None:
        super().__init__("objective_not_found")


@dataclass(frozen=True)
class AssessmentObjective:
    id: UUID
    team_id: UUID
    statement: str
    status: str


@dataclass(frozen=True)
class AssessmentTeam:
    id: UUID
    domain: str
    status: str


@dataclass(frozen=True)
class AssessmentPolicy:
    id: UUID
    team_id: UUID
    version: int
    rules_json: str


@dataclass(frozen=True)
class AssessmentTask:
    id: UUID
    task_type: str
    status: str
    policy_version: int


@dataclass(frozen=True)
class AssessmentEvent:
    id: UUID
    task_id: UUID
    event_type: str
    created_at: str
    signal_id: UUID | None


@dataclass(frozen=True)
class AssessmentSignal:
    id: UUID
    source_type: str
    origin_url: str
    fetched_at: str
    content_hash: str
    snapshot_ref: str


@dataclass(frozen=True)
class AssessmentBasis:
    objective_id: UUID
    team_id: UUID
    policy_ids: tuple[UUID, ...]
    task_ids: tuple[UUID, ...]
    event_ids: tuple[UUID, ...]
    signal_ids: tuple[UUID, ...]
    sha256: str


@dataclass(frozen=True)
class StateAssessment:
    objective: AssessmentObjective
    team: AssessmentTeam
    policies: tuple[AssessmentPolicy, ...]
    tasks: tuple[AssessmentTask, ...]
    events: tuple[AssessmentEvent, ...]
    signals: tuple[AssessmentSignal, ...]
    basis: AssessmentBasis
    created_at: str


class StateAssessmentBuilder:
    """Build a deterministic operational assessment without writing state."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def build(
        self, objective_id: UUID, *, created_at: datetime | None = None
    ) -> StateAssessment:
        with self._session_factory() as session:
            with session.begin():
                session.connection().exec_driver_sql(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                return self.build_in_session(
                    session, objective_id, created_at=created_at
                )

    def build_in_session(
        self,
        session: Session,
        objective_id: UUID,
        *,
        created_at: datetime | None = None,
    ) -> StateAssessment:
        """Build the assessment projection in an existing transaction."""
        assessment_time = _timestamp(created_at or datetime.now(timezone.utc))
        objective = session.scalar(
            select(Objective).where(Objective.id == objective_id)
        )
        if objective is None:
            raise ObjectiveNotFound()

        team = session.scalar(
            select(Team).where(
                Team.id == objective.team_id,
            )
        )
        if team is None:
            raise RuntimeError("objective_team_missing")

        lifecycle_events = list(
            session.scalars(
                select(Event)
                .join(Task, Task.id == Event.task_id)
                .where(
                    Task.team_id == objective.team_id,
                    Event.type.in_(_OBJECTIVE_EVENT_TYPES),
                    Event.payload["objective_id"].as_string() == str(objective.id),
                )
            )
        )
        linked_tasks = list(
            session.scalars(
                select(Task).where(
                    Task.team_id == objective.team_id,
                    Task.objective_id == objective.id,
                )
            )
        )
        linked_tasks.sort(key=lambda task: str(task.id))
        task_ids = {task.id for task in linked_tasks}
        direct_task_ids = task_ids
        lifecycle_event_ids = {event.id for event in lifecycle_events}

        related_events = (
            list(
                session.scalars(
                    select(Event)
                    .join(Task, Task.id == Event.task_id)
                    .where(
                        Task.team_id == objective.team_id,
                        or_(
                            Event.task_id.in_(task_ids),
                            Event.id.in_(lifecycle_event_ids),
                        ),
                    )
                )
            )
            if task_ids or lifecycle_event_ids
            else []
        )
        related_events = [
            event
            for event in related_events
            if event.type not in _NON_DOMAIN_ASSESSMENT_EVENT_TYPES
            and (
                (
                    event.type in _OBJECTIVE_EVENT_TYPES
                    and event.payload.get("objective_id") == str(objective.id)
                )
                or (
                    event.type not in _OBJECTIVE_EVENT_TYPES
                    and (
                        "objective_id" not in event.payload
                        or event.payload.get("objective_id") == str(objective.id)
                    )
                )
            )
        ]
        related_events.sort(key=lambda event: str(event.id))

        signal_ids = _signal_ids(related_events, direct_task_ids)
        signal_rows = (
            list(session.scalars(select(Signal).where(Signal.id.in_(signal_ids))))
            if signal_ids
            else []
        )
        signal_rows.sort(key=lambda signal: str(signal.id))

        policy_versions = {task.policy_version for task in linked_tasks}
        policy_rows = (
            list(
                session.scalars(
                    select(TeamPolicy).where(
                        TeamPolicy.team_id == objective.team_id,
                        TeamPolicy.version.in_(policy_versions),
                    )
                )
            )
            if policy_versions
            else []
        )
        policy_rows.sort(key=lambda policy: (policy.version, str(policy.id)))

        objective_data = AssessmentObjective(
            id=objective.id,
            team_id=objective.team_id,
            statement=objective.statement,
            status=objective.status,
        )
        team_data = AssessmentTeam(
            id=team.id,
            domain=team.domain,
            status=team.status,
        )
        policies = tuple(
            AssessmentPolicy(
                id=policy.id,
                team_id=policy.team_id,
                version=policy.version,
                rules_json=_canonical_json(policy.rules),
            )
            for policy in policy_rows
        )
        tasks = tuple(
            AssessmentTask(
                id=task.id,
                task_type=task.task_type,
                status=task.status,
                policy_version=task.policy_version,
            )
            for task in linked_tasks
        )
        events = tuple(
            AssessmentEvent(
                id=event.id,
                task_id=event.task_id,
                event_type=event.type,
                created_at=_timestamp(event.created_at),
                signal_id=_event_signal_id(event, direct_task_ids),
            )
            for event in related_events
        )
        signals = tuple(
            AssessmentSignal(
                id=signal.id,
                source_type=signal.source_type,
                origin_url=signal.origin_url,
                fetched_at=_timestamp(signal.fetched_at),
                content_hash=signal.content_hash,
                snapshot_ref=signal.snapshot_ref,
            )
            for signal in signal_rows
        )

        basis_payload = _basis_payload(
            objective_data,
            team_data,
            policies,
            tasks,
            events,
            signals,
        )
        basis_hash = hashlib.sha256(
            _canonical_json(basis_payload).encode("utf-8")
        ).hexdigest()
        basis = AssessmentBasis(
            objective_id=objective.id,
            team_id=team.id,
            policy_ids=tuple(policy.id for policy in policies),
            task_ids=tuple(task.id for task in tasks),
            event_ids=tuple(event.id for event in events),
            signal_ids=tuple(signal.id for signal in signals),
            sha256=basis_hash,
        )
        return StateAssessment(
            objective=objective_data,
            team=team_data,
            policies=policies,
            tasks=tasks,
            events=events,
            signals=signals,
            basis=basis,
            created_at=assessment_time,
        )


def _signal_ids(events: list[Event], direct_task_ids: set[UUID]) -> set[UUID]:
    return {
        signal_id
        for event in events
        if event.task_id in direct_task_ids
        and event.type in _INGESTION_EVENT_TYPES
        if (signal_id := _event_signal_id(event, direct_task_ids)) is not None
    }


def _event_signal_id(event: Event, direct_task_ids: set[UUID]) -> UUID | None:
    if event.task_id not in direct_task_ids or event.type not in _INGESTION_EVENT_TYPES:
        return None
    raw_signal_id = event.payload.get("signal_id")
    if not isinstance(raw_signal_id, str):
        return None
    try:
        return UUID(raw_signal_id)
    except ValueError:
        return None


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("assessment timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _basis_payload(
    objective: AssessmentObjective,
    team: AssessmentTeam,
    policies: tuple[AssessmentPolicy, ...],
    tasks: tuple[AssessmentTask, ...],
    events: tuple[AssessmentEvent, ...],
    signals: tuple[AssessmentSignal, ...],
) -> dict[str, Any]:
    return {
        "objective": {
            "id": str(objective.id),
            "team_id": str(objective.team_id),
            "statement": objective.statement,
            "status": objective.status,
        },
        "team": {
            "id": str(team.id),
            "domain": team.domain,
            "status": team.status,
        },
        "policies": [
            {
                "id": str(policy.id),
                "team_id": str(policy.team_id),
                "version": policy.version,
                "rules": json.loads(policy.rules_json),
            }
            for policy in policies
        ],
        "tasks": [
            {
                "id": str(task.id),
                "task_type": task.task_type,
                "status": task.status,
                "policy_version": task.policy_version,
            }
            for task in tasks
        ],
        "events": [
            {
                "id": str(event.id),
                "task_id": str(event.task_id),
                "type": event.event_type,
                "created_at": event.created_at,
                "signal_id": (
                    str(event.signal_id) if event.signal_id is not None else None
                ),
            }
            for event in events
        ],
        "signals": [
            {
                "id": str(signal.id),
                "source_type": signal.source_type,
                "origin_url": signal.origin_url,
                "fetched_at": signal.fetched_at,
                "content_hash": signal.content_hash,
                "snapshot_ref": signal.snapshot_ref,
            }
            for signal in signals
        ],
    }
