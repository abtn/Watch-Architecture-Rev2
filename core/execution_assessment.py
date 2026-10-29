"""Read-only deterministic reassessment of a Plan's durable execution evidence.

This is a derived read model, not a persisted Evaluation and not a lifecycle
writer. It reconstructs immutable Plan intent, Task attempts, Events, terminal
Outcomes, and canonical Signal/Snapshot evidence. Rebuilding it performs no
database or Snapshot writes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Outcome, Plan, PlanAction, Signal, Task
from core.plans import PlanService
from core.snapshot_store import SnapshotIntegrityError, SnapshotStore
from core.state_assessment import _canonical_json, _timestamp

_TERMINAL_CATEGORIES = frozenset(
    {"success_signal_created", "success_no_change", "terminal_failure"}
)
_SUCCESS_CATEGORIES = frozenset({"success_signal_created", "success_no_change"})
_RETRY_EVENT_TYPES = frozenset({"task_attempt_failed", "task_retry_scheduled"})
_TERMINAL_EVENT_TYPES = frozenset({"task_completed", "task_failed"})
_BUSINESS_EVENT_TYPES = frozenset({"signal_ingested", "fetch_no_change"})


class ExecutionAssessmentError(ValueError):
    """The Plan or immutable Plan provenance cannot be reconstructed safely."""


@dataclass(frozen=True)
class PlanExecutionAssessment:
    """A deterministic, rebuildable view of execution, never an authority."""

    plan_id: UUID
    team_id: UUID
    objective_id: UUID
    conclusion: str
    integrity: str
    payload: dict[str, Any]
    assessment_hash: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-ready copy with the hash of the canonical payload."""
        return {**self.payload, "assessment_hash": self.assessment_hash}


class ExecutionAssessmentBuilder:
    """Reconstruct Plan execution evidence without creating durable records."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store

    def build(self, plan_id: UUID) -> PlanExecutionAssessment:
        """Build the same result for the same committed database/snapshot state.

        A repeatable-read database transaction ensures that Plan, Tasks, Events,
        and Outcomes are read from one consistent PostgreSQL snapshot. Snapshot
        objects are read-only and independently hash-verified.
        """
        with self._session_factory() as session:
            with session.begin():
                session.connection(
                    execution_options={"isolation_level": "REPEATABLE READ"}
                )
                try:
                    PlanService._reconstruct(session, plan_id)
                except ValueError as error:
                    raise ExecutionAssessmentError(str(error)) from error

                plan = session.get(Plan, plan_id)
                if plan is None:
                    raise ExecutionAssessmentError("plan_not_found")

                accepted_event = session.get(Event, plan.accepted_event_id)
                if (
                    accepted_event is None
                    or not isinstance(accepted_event.payload, dict)
                    or not isinstance(accepted_event.payload.get("assessment"), dict)
                ):
                    raise ExecutionAssessmentError(
                        "historical_decision_assessment_missing"
                    )
                historical_assessment = accepted_event.payload["assessment"]
                if (
                    plan.assessment_basis != historical_assessment.get("basis")
                    or plan.assessment_created_at
                    != historical_assessment.get("created_at")
                ):
                    raise ExecutionAssessmentError(
                        "historical_decision_assessment_mismatch"
                    )

                actions = list(
                    session.scalars(
                        select(PlanAction)
                        .where(PlanAction.plan_id == plan_id)
                        .order_by(PlanAction.action_id)
                    )
                )
                tasks = list(
                    session.scalars(
                        select(Task)
                        .where(Task.plan_id == plan_id)
                        .order_by(Task.plan_action_id)
                    )
                )
                task_by_action = {task.plan_action_id: task for task in tasks}
                if (
                    any(action.action_id not in task_by_action for action in actions)
                    or len(task_by_action) != len(tasks)
                    or len(actions) != len(tasks)
                    or set(task_by_action) != {action.action_id for action in actions}
                ):
                    raise ExecutionAssessmentError("plan_action_task_mapping_mismatch")

                task_ids = tuple(task.id for task in tasks)
                events_by_task: dict[UUID, list[Event]] = {
                    task_id: [] for task_id in task_ids
                }
                if task_ids:
                    task_events = list(
                        session.scalars(
                            select(Event)
                            .where(Event.task_id.in_(task_ids))
                            .order_by(Event.created_at, Event.id)
                        )
                    )
                    for event in task_events:
                        events_by_task[event.task_id].append(event)

                outcomes_by_task: dict[UUID, list[Outcome]] = {
                    task_id: [] for task_id in task_ids
                }
                if task_ids:
                    outcomes = list(
                        session.scalars(
                            select(Outcome)
                            .where(
                                Outcome.recorded_by_task_id.in_(task_ids),
                                Outcome.outcome_type == "task_execution",
                            )
                            .order_by(Outcome.recorded_by_task_id, Outcome.id)
                        )
                    )
                    for outcome in outcomes:
                        outcomes_by_task[outcome.recorded_by_task_id].append(outcome)

                plan_events = list(
                    session.scalars(
                        select(Event)
                        .where(
                            Event.type.in_(
                                ("plan_created", "plan_completed", "plan_stopped")
                            )
                        )
                        .order_by(Event.created_at, Event.id)
                    )
                )
                plan_events = [
                    event
                    for event in plan_events
                    if isinstance(event.payload, dict)
                    and event.payload.get("plan_id") == str(plan_id)
                ]

                action_payloads: list[dict[str, Any]] = []
                for action in actions:
                    task = task_by_action[action.action_id]
                    action_payloads.append(
                        self._assess_action(
                            session=session,
                            plan=plan,
                            action=action,
                            task=task,
                            events=events_by_task[task.id],
                            outcomes=outcomes_by_task[task.id],
                        )
                    )

                plan_findings: list[str] = []
                if plan.status == "completed" and any(
                    item["conclusion"] != "succeeded" for item in action_payloads
                ):
                    plan_findings.append(
                        "completed_plan_without_complete_success_evidence"
                    )

                all_findings = sorted(
                    set(plan_findings).union(
                        finding
                        for item in action_payloads
                        for finding in item["findings"]
                    )
                )
                if all_findings:
                    conclusion = "inconsistent"
                    integrity = "inconsistent"
                elif plan.status == "stopped":
                    conclusion = "stopped"
                    integrity = "consistent"
                elif any(item["conclusion"] == "failed" for item in action_payloads):
                    conclusion = "failed"
                    integrity = "consistent"
                elif action_payloads and all(
                    item["conclusion"] == "succeeded" for item in action_payloads
                ):
                    conclusion = (
                        "completed"
                        if plan.status == "completed"
                        else "execution_succeeded_plan_active"
                    )
                    integrity = "consistent"
                else:
                    conclusion = "in_progress"
                    integrity = "consistent"

                payload: dict[str, Any] = {
                    "schema": "watch.plan_execution_assessment.v1",
                    "plan": {
                        "id": str(plan.id),
                        "team_id": str(plan.team_id),
                        "objective_id": str(plan.objective_id),
                        "status": plan.status,
                        "stopped_reason": plan.stopped_reason,
                        "successor_plan_id": (
                            str(plan.successor_plan_id)
                            if plan.successor_plan_id is not None
                            else None
                        ),
                        "proposal_hash": plan.proposal_hash,
                        "budget": plan.budget,
                        "completion_condition": plan.completion_condition,
                        "accepted_event_id": str(plan.accepted_event_id),
                        "created_by_task_id": str(plan.created_by_task_id),
                        "created_event_ids": [
                            str(event.id)
                            for event in plan_events
                            if event.type == "plan_created"
                        ],
                        "lifecycle_events": [
                            self._event_reference(event) for event in plan_events
                        ],
                    },
                    "historical_decision": {
                        "assessment": historical_assessment,
                        "assessment_basis": plan.assessment_basis,
                        "assessment_created_at": plan.assessment_created_at,
                    },
                    "actions": action_payloads,
                    "conclusion": conclusion,
                    "integrity": integrity,
                    "findings": all_findings,
                }
                digest = hashlib.sha256(
                    _canonical_json(payload).encode("utf-8")
                ).hexdigest()
                return PlanExecutionAssessment(
                    plan_id=plan.id,
                    team_id=plan.team_id,
                    objective_id=plan.objective_id,
                    conclusion=conclusion,
                    integrity=integrity,
                    payload=payload,
                    assessment_hash=digest,
                )

    def _assess_action(
        self,
        *,
        session: Session,
        plan: Plan,
        action: PlanAction,
        task: Task,
        events: list[Event],
        outcomes: list[Outcome],
    ) -> dict[str, Any]:
        findings: list[str] = []
        event_payloads: list[dict[str, Any]] = []
        starts: dict[int, list[Event]] = {}
        retry_failures: dict[int, list[Event]] = {}
        retry_scheduled: dict[int, list[Event]] = {}
        completed: dict[int, list[Event]] = {}
        failed: dict[int, list[Event]] = {}
        business_events: list[Event] = []

        for event in events:
            payload = event.payload if isinstance(event.payload, dict) else {}
            if event.type == "task_started":
                attempt = self._attempt_number(payload)
                if attempt is None:
                    findings.append("task_started_attempt_invalid")
                else:
                    starts.setdefault(attempt, []).append(event)
            elif event.type == "task_attempt_failed":
                attempt = self._attempt_number(payload)
                if attempt is None:
                    findings.append("task_attempt_failed_attempt_invalid")
                else:
                    retry_failures.setdefault(attempt, []).append(event)
            elif event.type == "task_retry_scheduled":
                attempt = self._attempt_number(payload)
                if attempt is None:
                    findings.append("task_retry_scheduled_attempt_invalid")
                else:
                    retry_scheduled.setdefault(attempt, []).append(event)
            elif event.type == "task_completed":
                attempt = self._attempt_number(payload)
                if attempt is None:
                    findings.append("task_completed_attempt_invalid")
                else:
                    completed.setdefault(attempt, []).append(event)
            elif event.type == "task_failed":
                attempt = self._attempt_number(payload)
                if attempt is None:
                    findings.append("task_failed_attempt_invalid")
                else:
                    failed.setdefault(attempt, []).append(event)
            elif event.type in _BUSINESS_EVENT_TYPES:
                business_events.append(event)
            event_payloads.append(self._event_reference(event))

        if (
            isinstance(task.attempt_count, bool)
            or not isinstance(task.attempt_count, int)
            or task.attempt_count < 0
        ):
            findings.append("task_attempt_count_invalid")
        if len(outcomes) > 1:
            findings.append("duplicate_terminal_outcomes")
        outcome = outcomes[0] if len(outcomes) == 1 else None

        all_attempt_event_numbers = (
            set(starts) | set(retry_failures) | set(retry_scheduled) | set(completed) | set(failed)
        )
        if any(
            number < 1 or number > task.attempt_count
            for number in all_attempt_event_numbers
        ):
            findings.append("attempt_event_outside_recorded_history")

        attempt_rows: list[dict[str, Any]] = []
        if task.attempt_count >= 0:
            for number in range(1, task.attempt_count + 1):
                attempt_starts = starts.get(number, [])
                if len(attempt_starts) != 1:
                    findings.append(
                        "task_started_event_missing"
                        if not attempt_starts
                        else "duplicate_task_started_events"
                    )
                start_event = attempt_starts[0] if len(attempt_starts) == 1 else None
                failed_events = retry_failures.get(number, [])
                scheduled_events = retry_scheduled.get(number, [])
                completed_events = completed.get(number, [])
                failed_terminal_events = failed.get(number, [])
                disposition = "unknown"
                reason: str | None = None

                if number < task.attempt_count or (
                    task.status == "pending" and number == task.attempt_count
                ):
                    disposition = "retry_scheduled"
                    if len(failed_events) != 1 or len(scheduled_events) != 1:
                        findings.append("retry_event_pair_missing_or_duplicated")
                    elif not self._valid_retry_pair(
                        failed_events[0], scheduled_events[0], number
                    ):
                        findings.append("retry_event_pair_payload_mismatch")
                    else:
                        reason = failed_events[0].payload.get("failure_reason")
                    if completed_events or failed_terminal_events:
                        findings.append("retry_attempt_has_terminal_event")
                elif number == task.attempt_count and task.status == "running":
                    disposition = "running"
                    if (
                        failed_events
                        or scheduled_events
                        or completed_events
                        or failed_terminal_events
                    ):
                        findings.append("running_attempt_has_disposition_events")
                elif number == task.attempt_count and task.status == "done":
                    disposition = "succeeded"
                    if (
                        len(completed_events) != 1
                        or failed_events
                        or scheduled_events
                        or failed_terminal_events
                    ):
                        findings.append("successful_terminal_events_invalid")
                elif number == task.attempt_count and task.status == "failed":
                    disposition = "failed"
                    if (
                        len(failed_events) != 1
                        or len(failed_terminal_events) != 1
                        or scheduled_events
                        or completed_events
                    ):
                        findings.append("failed_terminal_events_invalid")
                    elif not self._valid_terminal_failure_pair(
                        failed_events[0], failed_terminal_events[0], number
                    ):
                        findings.append("failed_terminal_event_payload_mismatch")
                    else:
                        reason = failed_terminal_events[0].payload.get("failure_reason")
                elif task.attempt_count == 0 and task.status == "pending":
                    disposition = "not_started"
                else:
                    findings.append("task_status_attempt_history_mismatch")

                attempt_rows.append(
                    {
                        "attempt": number,
                        "started_at": (
                            _timestamp(start_event.created_at)
                            if start_event is not None
                            else None
                        ),
                        "start_event_id": (
                            str(start_event.id) if start_event is not None else None
                        ),
                        "disposition": disposition,
                        "failure_reason": reason,
                        "event_ids": sorted(
                            str(event.id)
                            for event in (
                                failed_events
                                + scheduled_events
                                + completed_events
                                + failed_terminal_events
                            )
                        ),
                    }
                )

        if task.status == "pending" and task.attempt_count == 0 and (
            starts or retry_failures or retry_scheduled or completed or failed
        ):
            findings.append("unstarted_task_has_attempt_events")
        if task.status in ("pending", "running") and outcome is not None:
            findings.append("nonterminal_task_has_terminal_outcome")
        if task.status in ("done", "failed") and outcome is None:
            findings.append("terminal_outcome_missing")

        outcome_payload: dict[str, Any] | None = None
        if outcome is not None:
            outcome_payload = self._validate_outcome(
                session=session,
                plan=plan,
                action=action,
                task=task,
                outcome=outcome,
                findings=findings,
            )

        terminal_event_refs = [
            event
            for event in events
            if event.type in ("task_completed", "task_failed")
            or (
                event.type == "task_attempt_failed"
                and self._attempt_number(
                    event.payload if isinstance(event.payload, dict) else {}
                )
                == task.attempt_count
            )
        ]
        if outcome is not None and outcome_payload is not None:
            expected_status = (
                "done"
                if outcome_payload["result_category"] in _SUCCESS_CATEGORIES
                else "failed"
            )
            expected_types = (
                ["task_completed"] if expected_status == "done"
                else ["task_attempt_failed", "task_failed"]
            )
            actual = sorted(event.type for event in terminal_event_refs)
            if sorted(expected_types) != actual:
                findings.append("terminal_event_outcome_mismatch")
            for event in terminal_event_refs:
                payload = event.payload if isinstance(event.payload, dict) else {}
                expected_event = {
                    "from_status": "running",
                    "to_status": expected_status,
                    "attempt_count": task.attempt_count,
                    "result_category": outcome_payload["result_category"],
                    "failure_reason": outcome_payload["failure_reason"],
                    "outcome_id": str(outcome.id),
                    "observation_snapshot_ref": outcome.observation_snapshot_ref,
                    "observation_hash": outcome.observation_hash,
                }
                if payload != expected_event:
                    findings.append("terminal_event_outcome_payload_mismatch")
                    break
            if task.status != expected_status:
                findings.append("terminal_task_status_outcome_mismatch")

        business_payloads = [
            self._event_reference(event) for event in business_events
        ]
        outcome_category = (
            outcome_payload["result_category"]
            if outcome_payload is not None
            else None
        )
        signal_summary = (
            outcome_payload["signals"] if outcome_payload is not None else []
        )
        if outcome_category in _SUCCESS_CATEGORIES:
            if outcome_category == "success_signal_created":
                if (
                    len(business_events) != 1
                    or business_events[0].type != "signal_ingested"
                ):
                    findings.append("signal_ingestion_evidence_missing_or_ambiguous")
                if len(signal_summary) != 1:
                    findings.append("created_signal_evidence_invalid")
                elif len(business_events) == 1:
                    self._validate_business_signal_event(
                        session, action, business_events[0], signal_summary[0], findings
                    )
            else:
                if len(signal_summary) != 0:
                    findings.append("no_change_outcome_has_signal_evidence")
                if (
                    len(business_events) != 1
                    or business_events[0].type != "fetch_no_change"
                ):
                    findings.append("no_change_ingestion_evidence_missing_or_ambiguous")
                elif len(business_events) == 1:
                    self._validate_no_change_event(
                        session, action, business_events[0], findings
                    )
        elif outcome_category == "terminal_failure" and business_events:
            findings.append("failed_task_has_successful_ingestion_event")

        if outcome is not None and outcome_payload is not None and not findings:
            conclusion = (
                "succeeded"
                if outcome_payload["result_category"] in _SUCCESS_CATEGORIES
                else "failed"
            )
        elif findings:
            conclusion = "inconsistent"
        elif task.status == "pending":
            conclusion = "not_started" if task.attempt_count == 0 else "retry_pending"
        elif task.status == "running":
            conclusion = "running"
        elif task.status == "failed":
            conclusion = "inconsistent"
            findings.append("failed_task_outcome_not_verified")
        else:
            conclusion = "inconsistent"
            findings.append("task_result_not_verified")

        return {
            "action_id": str(action.action_id),
            "action": action.action,
            "task_id": str(task.id),
            "task_status": task.status,
            "policy_version": task.policy_version,
            "created_at": _timestamp(task.created_at),
            "completed_at": (
                _timestamp(task.completed_at)
                if task.completed_at is not None
                else None
            ),
            "attempt_count": task.attempt_count,
            "attempts": attempt_rows,
            "conclusion": conclusion,
            "outcome": outcome_payload,
            "business_events": business_payloads,
            "events": event_payloads,
            "findings": sorted(set(findings)),
        }

    def _validate_outcome(
        self,
        *,
        session: Session,
        plan: Plan,
        action: PlanAction,
        task: Task,
        outcome: Outcome,
        findings: list[str],
    ) -> dict[str, Any] | None:
        if (
            outcome.team_id != plan.team_id
            or outcome.subject_kind != "task"
            or outcome.subject_id != task.id
            or outcome.recorded_by_task_id != task.id
            or outcome.outcome_type != "task_execution"
            or outcome.expected is not None
        ):
            findings.append("terminal_outcome_attribution_invalid")
        if (
            not outcome.observation_snapshot_ref
            or not outcome.observation_hash
            or outcome.observed_at is None
        ):
            findings.append("terminal_outcome_observation_metadata_missing")
            return None
        try:
            content = self._snapshot_store.read(outcome.observation_snapshot_ref)
        except (SnapshotIntegrityError, OSError, ValueError):
            findings.append("terminal_outcome_snapshot_unreadable")
            return None
        actual_hash = "sha256:" + hashlib.sha256(content).hexdigest()
        if actual_hash != outcome.observation_hash:
            findings.append("terminal_outcome_snapshot_hash_mismatch")
            return None
        expected_ref = "snap://sha256/" + actual_hash.removeprefix("sha256:")
        if outcome.observation_snapshot_ref != expected_ref:
            findings.append("terminal_outcome_snapshot_reference_mismatch")
        try:
            decoded = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            findings.append("terminal_outcome_snapshot_not_json")
            return None
        if (
            not isinstance(decoded, dict)
            or _canonical_json(decoded).encode("utf-8") != content
        ):
            findings.append("terminal_outcome_snapshot_not_canonical")
            return None
        category = decoded.get("result_category")
        if not isinstance(category, str) or category not in _TERMINAL_CATEGORIES:
            findings.append("terminal_outcome_category_invalid")
            return None
        if decoded.get("attempt") != task.attempt_count:
            findings.append("terminal_outcome_attempt_mismatch")
        observed_at_raw = decoded.get("observed_at")
        try:
            parsed_observed_at = datetime.fromisoformat(
                str(observed_at_raw).replace("Z", "+00:00")
            )
            if (
                parsed_observed_at.tzinfo is None
                or _timestamp(parsed_observed_at) != _timestamp(outcome.observed_at)
            ):
                findings.append("terminal_outcome_observed_at_mismatch")
        except (TypeError, ValueError):
            findings.append("terminal_outcome_observed_at_invalid")
        failure_reason = decoded.get("failure_reason")
        signal_rows = decoded.get("signals")
        if not isinstance(signal_rows, list):
            findings.append("terminal_outcome_signal_evidence_invalid")
            return None
        if category == "terminal_failure":
            if (
                not isinstance(failure_reason, str)
                or not failure_reason.strip()
                or signal_rows
            ):
                findings.append("terminal_failure_observation_invalid")
        elif failure_reason is not None:
            findings.append("successful_outcome_has_failure_reason")
        signals: list[dict[str, Any]] = []
        for item in signal_rows:
            if not isinstance(item, dict):
                findings.append("terminal_outcome_signal_evidence_invalid")
                continue
            raw_id = item.get("signal_id")
            raw_hash = item.get("content_hash")
            raw_ref = item.get("snapshot_ref")
            try:
                signal_id = UUID(raw_id) if isinstance(raw_id, str) else None
            except ValueError:
                signal_id = None
            signal = session.get(Signal, signal_id) if signal_id is not None else None
            if signal is None:
                findings.append("terminal_outcome_signal_missing")
                continue
            if signal.content_hash != raw_hash or signal.snapshot_ref != raw_ref:
                findings.append("terminal_outcome_signal_reference_mismatch")
            if (
                signal.origin_url != action.action.get("origin_url")
                or signal.source_type != action.action.get("source_type")
            ):
                findings.append("terminal_outcome_signal_source_mismatch")
            self._verify_signal_snapshot_integrity(signal, findings)
            signals.append(
                {
                    "signal_id": str(signal.id),
                    "content_hash": signal.content_hash,
                    "snapshot_ref": signal.snapshot_ref,
                    "origin_url": signal.origin_url,
                    "source_type": signal.source_type,
                }
            )
        if category == "success_signal_created" and not signals:
            findings.append("created_signal_evidence_missing")
        if category == "success_no_change" and signals:
            findings.append("no_change_outcome_has_signal_evidence")
        return {
            "id": str(outcome.id),
            "type": outcome.outcome_type,
            "expected": outcome.expected,
            "subject_kind": outcome.subject_kind,
            "subject_id": str(outcome.subject_id),
            "recorded_by_task_id": str(outcome.recorded_by_task_id),
            "team_id": str(outcome.team_id),
            "observed_at": _timestamp(outcome.observed_at),
            "observation_snapshot_ref": outcome.observation_snapshot_ref,
            "observation_hash": outcome.observation_hash,
            "result_category": category,
            "failure_reason": failure_reason,
            "attempt": decoded.get("attempt"),
            "signals": signals,
        }

    def _validate_business_signal_event(
        self,
        session: Session,
        action: PlanAction,
        event: Event,
        outcome_signal: dict[str, Any],
        findings: list[str],
    ) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        if (
            payload.get("signal_id") != outcome_signal["signal_id"]
            or payload.get("content_hash") != outcome_signal["content_hash"]
            or payload.get("snapshot_ref") != outcome_signal["snapshot_ref"]
        ):
            findings.append("signal_ingestion_event_outcome_mismatch")
        self._validate_source_signal(
            session,
            action,
            payload.get("signal_id"),
            payload.get("content_hash"),
            payload.get("snapshot_ref"),
            findings,
        )

    def _validate_no_change_event(
        self,
        session: Session,
        action: PlanAction,
        event: Event,
        findings: list[str],
    ) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        self._validate_source_signal(
            session,
            action,
            payload.get("signal_id"),
            payload.get("content_hash"),
            payload.get("snapshot_ref"),
            findings,
        )

    def _validate_source_signal(
        self,
        session: Session,
        action: PlanAction,
        signal_id_raw: Any,
        content_hash: Any,
        snapshot_ref: Any,
        findings: list[str],
    ) -> None:
        try:
            signal_id = UUID(signal_id_raw) if isinstance(signal_id_raw, str) else None
        except ValueError:
            signal_id = None
        signal = session.get(Signal, signal_id) if signal_id is not None else None
        if signal is None:
            findings.append("ingestion_event_signal_missing")
            return
        if (
            signal.content_hash != content_hash
            or signal.snapshot_ref != snapshot_ref
            or signal.origin_url != action.action.get("origin_url")
            or signal.source_type != action.action.get("source_type")
        ):
            findings.append("ingestion_event_signal_mismatch")
        self._verify_signal_snapshot_integrity(signal, findings)

    def _verify_signal_snapshot_integrity(
        self, signal: Signal, findings: list[str]
    ) -> None:
        try:
            content = self._snapshot_store.read(signal.snapshot_ref)
        except (SnapshotIntegrityError, OSError, ValueError):
            findings.append("signal_snapshot_unreadable")
            return
        actual_hash = "sha256:" + hashlib.sha256(content).hexdigest()
        if actual_hash != signal.content_hash:
            findings.append("signal_snapshot_hash_mismatch")

    @staticmethod
    def _valid_retry_pair(
        failed_event: Event, scheduled_event: Event, attempt: int
    ) -> bool:
        failed = failed_event.payload if isinstance(failed_event.payload, dict) else {}
        scheduled = (
            scheduled_event.payload
            if isinstance(scheduled_event.payload, dict)
            else {}
        )
        expected_keys = {
            "from_status",
            "to_status",
            "attempt_count",
            "result_category",
            "failure_reason",
        }
        return (
            set(failed) == expected_keys
            and set(scheduled) == expected_keys
            and failed == scheduled
            and failed.get("from_status") == "running"
            and failed.get("to_status") == "pending"
            and failed.get("attempt_count") == attempt
            and failed.get("result_category") == "retryable_failure"
            and isinstance(failed.get("failure_reason"), str)
            and bool(failed["failure_reason"].strip())
        )

    @staticmethod
    def _valid_terminal_failure_pair(
        failed_attempt: Event, terminal_failure: Event, attempt: int
    ) -> bool:
        first = (
            failed_attempt.payload
            if isinstance(failed_attempt.payload, dict)
            else {}
        )
        second = (
            terminal_failure.payload
            if isinstance(terminal_failure.payload, dict)
            else {}
        )
        expected = {
            "from_status", "to_status", "attempt_count", "result_category",
            "failure_reason",
            "outcome_id",
            "observation_snapshot_ref",
            "observation_hash",
        }
        return (
            set(first) == expected
            and set(second) == expected
            and first == second
            and first.get("from_status") == "running"
            and first.get("to_status") == "failed"
            and first.get("attempt_count") == attempt
            and first.get("result_category") == "terminal_failure"
            and isinstance(first.get("failure_reason"), str)
            and bool(first["failure_reason"].strip())
        )

    @staticmethod
    def _attempt_number(payload: dict[str, Any]) -> int | None:
        value = payload.get("attempt_count")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return None
        return value

    @staticmethod
    def _event_reference(event: Event) -> dict[str, Any]:
        return {
            "id": str(event.id),
            "task_id": str(event.task_id),
            "type": event.type,
            "created_at": _timestamp(event.created_at),
            "payload": event.payload,
        }
