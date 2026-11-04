"""Deterministic D9 rule evaluation for configured-source Task Outcomes."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.evaluations import (
    Conclusion,
    EvaluationDraft,
    EvaluationEvidence,
    EvaluationFindings,
)
from core.models import Event, Outcome, Signal, Task, Team
from core.snapshot_store import SnapshotIntegrityError, SnapshotStore
from core.state_assessment import _canonical_json, _timestamp
from core.task_runtime import TaskNotFinalizable, TaskRuntime

_EVALUATOR_KIND = "rule"
_EVALUATOR_IDENTITY = "watch.r6g.ingest-source-rules"
_EVALUATOR_REVISION = "1"
_BUSINESS_EVENT_TYPES = ("signal_ingested", "fetch_no_change")
_TERMINAL_EVENT_TYPES = (
    "task_completed",
    "task_attempt_failed",
    "task_failed",
)
_COMMON_UNCERTAINTY = [
    "This evaluation checks internal execution-contract consistency only.",
    "It does not establish source truth, completeness, or relevance.",
    "It does not establish causation or Objective achievement.",
]


class RuleEvaluationError(ValueError):
    """A categorized, fail-closed D9 evidence or integrity error."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class IngestSourceRuleEvaluator:
    """Evaluate one immutable, configured-source Task Outcome without writes."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store

    def evaluate(self, evaluator_task_id: UUID) -> EvaluationDraft:
        with self._session_factory() as session:
            task = session.get(Task, evaluator_task_id)
            if task is None:
                raise RuleEvaluationError("evaluation_task_not_found")
            try:
                request = TaskRuntime._validate_evaluation_task_request(
                    session, task
                )
            except TaskNotFinalizable as error:
                raise RuleEvaluationError(str(error)) from error

            if task.status not in {"running", "done"}:
                raise RuleEvaluationError("evaluation_task_not_terminal_or_running")

            source_task = session.get(Task, UUID(request["source_task_id"]))
            outcome = session.get(Outcome, UUID(request["outcome_id"]))
            team = session.get(Team, task.team_id)
            if source_task is None or outcome is None or team is None:
                raise RuleEvaluationError("evaluation_source_records_missing")

            try:
                action = TaskRuntime._source_action_for_evaluation(
                    session, source_task
                )
            except TaskNotFinalizable as error:
                raise RuleEvaluationError(str(error)) from error

            observation = self._read_observation(outcome)
            self._validate_terminal_events(
                session, source_task, outcome, observation
            )
            origin_url = action.action["origin_url"]
            source_type = action.action["source_type"]
            result_category = request["source_result_category"]

            business_events = list(
                session.scalars(
                    select(Event)
                    .where(
                        Event.task_id == source_task.id,
                        Event.type.in_(_BUSINESS_EVENT_TYPES),
                    )
                    .order_by(Event.created_at, Event.id)
                )
            )

            signal: Signal | None = None
            conclusion: Conclusion = "inconclusive"
            if result_category == "success_signal_created":
                signal = self._validate_created_signal(
                    session,
                    business_events,
                    observation,
                    team,
                    origin_url,
                    source_type,
                )
                conclusion = "worked"
                observed_result = (
                    "The configured-source Task committed one new Signal."
                )
                method = (
                    "The terminal Outcome, task completion Event, "
                    "signal_ingested Event, Signal identity, and immutable "
                    "Snapshot agree."
                )
            elif result_category == "success_no_change":
                signal = self._validate_no_change(
                    session,
                    business_events,
                    observation,
                    team,
                    origin_url,
                    source_type,
                )
                conclusion = "worked"
                observed_result = (
                    "The configured-source Task detected existing identical "
                    "content and created no duplicate Signal."
                )
                method = (
                    "The terminal Outcome, task completion Event, "
                    "fetch_no_change Event, existing Signal identity, and "
                    "immutable Snapshot agree."
                )
            elif result_category == "terminal_failure":
                self._validate_terminal_failure(
                    business_events, observation
                )
                conclusion = "failed"
                reason = observation["failure_reason"]
                observed_result = (
                    "The configured-source Task ended in terminal execution "
                    f"failure ({reason})."
                )
                method = (
                    "The terminal failure Events and immutable Outcome agree; "
                    "no successful ingestion business Event exists for this Task."
                )
            else:
                raise RuleEvaluationError("evaluation_result_unsupported")

            evidence = [
                EvaluationEvidence(
                    source_kind="outcome",
                    outcome_id=outcome.id,
                    stance="supports",
                )
            ]
            if signal is not None:
                evidence.append(
                    EvaluationEvidence(
                        source_kind="signal",
                        signal_id=signal.id,
                        stance="supports",
                    )
                )

            return EvaluationDraft(
                outcome_id=outcome.id,
                conclusion=conclusion,
                findings=EvaluationFindings(
                    observed_result=observed_result,
                    method_or_process=method,
                    context=[
                        "Task type: ingest_source.",
                        f"Configured source type: {source_type}.",
                    ],
                    alternative_explanations=[
                        "Execution consistency does not prove that the source "
                        "content is correct or useful."
                    ],
                    attribution="not established",
                    uncertainty=list(_COMMON_UNCERTAINTY),
                ),
                evidence=evidence,
                idempotency_key=TaskRuntime._r6g_evaluation_idempotency_key(
                    request["request_fingerprint"]
                ),
            )

    def _read_observation(self, outcome: Outcome) -> dict[str, object]:
        if (
            outcome.observation_snapshot_ref is None
            or outcome.observation_hash is None
            or outcome.observed_at is None
        ):
            raise RuleEvaluationError("evaluation_outcome_snapshot_missing")
        try:
            content = self._snapshot_store.read(
                outcome.observation_snapshot_ref
            )
        except SnapshotIntegrityError as error:
            raise RuleEvaluationError(
                "evaluation_outcome_snapshot_unreadable"
            ) from error
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if digest != outcome.observation_hash:
            raise RuleEvaluationError("evaluation_outcome_snapshot_hash_mismatch")
        try:
            observation = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuleEvaluationError("evaluation_outcome_not_json") from error
        if not isinstance(observation, dict):
            raise RuleEvaluationError("evaluation_outcome_shape_invalid")
        if _canonical_json(observation).encode("utf-8") != content:
            raise RuleEvaluationError("evaluation_outcome_not_canonical")
        if (
            observation.get("attempt") is None
            or observation.get("result_category") is None
            or observation.get("observed_at") != _timestamp(outcome.observed_at)
            or observation.get("signals") is None
            or set(observation)
            != {
                "attempt",
                "failure_reason",
                "observed_at",
                "result_category",
                "signals",
            }
        ):
            raise RuleEvaluationError("evaluation_outcome_payload_invalid")
        return observation

    @staticmethod
    def _validate_terminal_events(
        session: Session,
        source_task: Task,
        outcome: Outcome,
        observation: dict[str, object],
    ) -> None:
        result_category = observation.get("result_category")
        attempt = observation.get("attempt")
        if (
            isinstance(attempt, bool)
            or not isinstance(attempt, int)
            or attempt != source_task.attempt_count
            or result_category
            not in {
                "success_signal_created",
                "success_no_change",
                "terminal_failure",
            }
        ):
            raise RuleEvaluationError("evaluation_terminal_attempt_invalid")

        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == source_task.id,
                    Event.type.in_(_TERMINAL_EVENT_TYPES),
                )
            )
        )
        current_events = [
            event
            for event in events
            if event.payload.get("attempt_count") == attempt
        ]
        expected_types = (
            {"task_attempt_failed", "task_failed"}
            if result_category == "terminal_failure"
            else {"task_completed"}
        )
        if {event.type for event in current_events} != expected_types or (
            len(current_events) != len(expected_types)
        ):
            raise RuleEvaluationError("evaluation_terminal_event_set_invalid")

        expected_status = (
            "failed" if result_category == "terminal_failure" else "done"
        )
        if source_task.status != expected_status:
            raise RuleEvaluationError("evaluation_terminal_task_status_mismatch")
        for event in current_events:
            payload = event.payload
            if (
                payload.get("from_status") != "running"
                or payload.get("to_status") != expected_status
                or payload.get("attempt_count") != attempt
                or payload.get("result_category") != result_category
                or payload.get("outcome_id") != str(outcome.id)
                or payload.get("observation_snapshot_ref")
                != outcome.observation_snapshot_ref
                or payload.get("observation_hash") != outcome.observation_hash
            ):
                raise RuleEvaluationError("evaluation_terminal_event_mismatch")

        failure_reason = observation.get("failure_reason")
        if result_category == "terminal_failure":
            if not isinstance(failure_reason, str) or not failure_reason.strip():
                raise RuleEvaluationError("evaluation_failure_reason_missing")
            if any(
                event.payload.get("failure_reason") != failure_reason
                for event in current_events
            ):
                raise RuleEvaluationError("evaluation_failure_reason_mismatch")
        elif failure_reason is not None:
            raise RuleEvaluationError("evaluation_success_has_failure_reason")

    def _validate_created_signal(
        self,
        session: Session,
        events: list[Event],
        observation: dict[str, object],
        team: Team,
        origin_url: str,
        source_type: str,
    ) -> Signal:
        signals = observation.get("signals")
        if not isinstance(signals, list) or len(signals) != 1:
            raise RuleEvaluationError("evaluation_created_signal_evidence_invalid")
        signal_ref = signals[0]
        if not isinstance(signal_ref, dict) or set(signal_ref) != {
            "signal_id",
            "snapshot_ref",
            "content_hash",
        }:
            raise RuleEvaluationError("evaluation_created_signal_evidence_invalid")
        if len(events) != 1 or events[0].type != "signal_ingested":
            raise RuleEvaluationError("evaluation_ingestion_event_set_invalid")
        signal = self._signal_from_business_event(
            session, events[0], team, origin_url, source_type
        )
        if (
            signal_ref.get("signal_id") != str(signal.id)
            or signal_ref.get("snapshot_ref") != signal.snapshot_ref
            or signal_ref.get("content_hash") != signal.content_hash
        ):
            raise RuleEvaluationError("evaluation_signal_observation_mismatch")
        return signal

    def _validate_no_change(
        self,
        session: Session,
        events: list[Event],
        observation: dict[str, object],
        team: Team,
        origin_url: str,
        source_type: str,
    ) -> Signal:
        signals = observation.get("signals")
        if signals != []:
            raise RuleEvaluationError("evaluation_no_change_has_signal_evidence")
        if len(events) != 1 or events[0].type != "fetch_no_change":
            raise RuleEvaluationError("evaluation_ingestion_event_set_invalid")
        return self._signal_from_business_event(
            session, events[0], team, origin_url, source_type
        )

    @staticmethod
    def _validate_terminal_failure(
        events: list[Event], observation: dict[str, object]
    ) -> None:
        if observation.get("signals") != [] or events:
            raise RuleEvaluationError(
                "evaluation_failure_has_successful_ingestion_event"
            )

    def _signal_from_business_event(
        self,
        session: Session,
        event: Event,
        team: Team,
        origin_url: str,
        source_type: str,
    ) -> Signal:
        payload = event.payload
        if not isinstance(payload, dict) or set(payload) != {
            "origin_url",
            "source_type",
            "content_hash",
            "signal_id",
            "snapshot_ref",
        }:
            raise RuleEvaluationError("evaluation_ingestion_event_payload_invalid")
        try:
            signal_id = UUID(payload["signal_id"])
        except (TypeError, ValueError) as error:
            raise RuleEvaluationError(
                "evaluation_ingestion_signal_id_invalid"
            ) from error
        signal = session.get(Signal, signal_id)
        if (
            signal is None
            or signal.domain != team.domain
            or signal.origin_url != origin_url
            or signal.source_type != source_type
            or payload.get("origin_url") != origin_url
            or payload.get("source_type") != source_type
            or payload.get("content_hash") != signal.content_hash
            or payload.get("snapshot_ref") != signal.snapshot_ref
        ):
            raise RuleEvaluationError("evaluation_signal_business_record_mismatch")
        try:
            content = self._snapshot_store.read(signal.snapshot_ref)
        except SnapshotIntegrityError as error:
            raise RuleEvaluationError(
                "evaluation_signal_snapshot_unreadable"
            ) from error
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if (
            digest != signal.content_hash
            or signal.snapshot_ref != (
                "snap://sha256/" + digest.removeprefix("sha256:")
            )
        ):
            raise RuleEvaluationError("evaluation_signal_snapshot_hash_mismatch")
        return signal
