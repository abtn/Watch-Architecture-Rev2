"""Snapshot-first reconstruction and validation for KnowledgeItem lifecycle history.

The accepted LearningChange graph is the history authority. D7 review Events are
an explicit, provenance-checked overlay because they change status without
advancing the LearningChange pointer.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import hashlib
import re
import uuid
from collections import defaultdict
from typing import Any, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Event, KnowledgeItem, LearningChange, Outcome, Task, TeamPolicy
from core.policy import InvalidPolicyError, knowledge_item_review_interval_days
from core.state_assessment import _canonical_json, _timestamp

SNAPSHOT_VERSION = 1
SNAPSHOT_HASH_DOMAIN_SEPARATOR = "watch.r7b.knowledge-item-state.v1"

KNOWLEDGE_CONTENT_HASH_SCHEME = "watch.r7b.knowledge-content.v2"

STATE_FIELDS = frozenset(
    {
        "id",
        "team_id",
        "kind",
        "title",
        "statement",
        "body",
        "applicability",
        "preconditions",
        "assumptions",
        "limitations",
        "non_applicability",
        "failure_modes",
        "known_counterexamples",
        "missing_information",
        "uncertainty",
        "confidence",
        "status",
        "version",
        "last_validated_at",
        "review_after",
        "origin_learning_change_id",
        "current_learning_change_id",
        "supersedes_item_id",
        "superseded_by_id",
    }
)
LEGACY_STATE_FIELDS = STATE_FIELDS - {
    "current_learning_change_id",
    "supersedes_item_id",
    "superseded_by_id",
}
_CONTENT_FIELDS = (
    "kind",
    "title",
    "statement",
    "body",
    "applicability",
    "preconditions",
    "assumptions",
    "limitations",
    "non_applicability",
    "failure_modes",
    "known_counterexamples",
    "missing_information",
    "uncertainty",
    "confidence",
)
_UUID_FIELDS = (
    "id",
    "team_id",
    "origin_learning_change_id",
    "current_learning_change_id",
)
_OPTIONAL_UUID_FIELDS = ("supersedes_item_id", "superseded_by_id")
_DATETIME_FIELDS = ("last_validated_at", "review_after")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REVIEW_ITEM_FIELDS = {
    "knowledge_item_id",
    "version",
    "review_after",
    "origin_learning_change_id",
}
_REVIEW_TOP_LEVEL_FIELDS = {
    "schema_version",
    "team_id",
    "task_id",
    "attempt_count",
    "reviewed_at",
    "items",
}


class KnowledgeHistoryError(ValueError):
    """A durable KnowledgeItem history cannot be reconstructed unambiguously."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclasses.dataclass(frozen=True)
class ReviewMarker:
    event_id: uuid.UUID
    item_id: uuid.UUID
    current_learning_change_id: uuid.UUID | None
    version: int
    review_after: str
    origin_learning_change_id: uuid.UUID
    reviewed_at: dt.datetime


@dataclasses.dataclass(frozen=True)
class KnowledgeHistoryResult:
    state: dict[str, Any]
    learning_change_ids: tuple[uuid.UUID, ...]
    reconstructed_legacy_fields: frozenset[str]
    applied_review_event_ids: tuple[uuid.UUID, ...]
    states: tuple[dict[str, Any], ...]


def knowledge_item_state(item: KnowledgeItem) -> dict[str, Any]:
    """Return the full KnowledgeItem state in B0.3 canonical value form."""
    return _normalize_snapshot_state(
        {
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
            "confidence": item.confidence,
            "status": item.status,
            "version": item.version,
            "last_validated_at": item.last_validated_at,
            "review_after": item.review_after,
            "origin_learning_change_id": str(item.origin_learning_change_id),
            "current_learning_change_id": str(item.current_learning_change_id),
            "supersedes_item_id": (
                str(item.supersedes_item_id)
                if item.supersedes_item_id is not None
                else None
            ),
            "superseded_by_id": (
                str(item.superseded_by_id)
                if item.superseded_by_id is not None
                else None
            ),
        }
    )


def _normalize_snapshot_uuid(value: object, field: str) -> str:
    if isinstance(value, uuid.UUID):
        return str(value)
    if not isinstance(value, str):
        raise KnowledgeHistoryError(f"{field}_uuid_invalid")
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise KnowledgeHistoryError(f"{field}_uuid_invalid") from error


def _normalize_snapshot_state(state: dict[str, Any]) -> dict[str, Any]:
    """Normalize every B0.3 field before canonical JSON serialization."""
    _validate_state_shape(state, exact=True)
    normalized = dict(state)

    for field in _UUID_FIELDS:
        normalized[field] = _normalize_snapshot_uuid(normalized.get(field), field)
    for field in _OPTIONAL_UUID_FIELDS:
        value = normalized.get(field)
        normalized[field] = (
            None if value is None else _normalize_snapshot_uuid(value, field)
        )

    confidence = normalized.get("confidence")
    if isinstance(confidence, bool) or not isinstance(
        confidence, (str, decimal.Decimal)
    ):
        raise KnowledgeHistoryError("snapshot_confidence_invalid")
    try:
        confidence_value = decimal.Decimal(confidence)
    except decimal.InvalidOperation as error:
        raise KnowledgeHistoryError("snapshot_confidence_invalid") from error
    if not confidence_value.is_finite():
        raise KnowledgeHistoryError("snapshot_confidence_invalid")
    normalized["confidence"] = format(confidence_value, "f")

    for field in _DATETIME_FIELDS:
        value = normalized.get(field)
        if value is None:
            continue
        if isinstance(value, dt.datetime):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise KnowledgeHistoryError(
                    f"{field}_timestamp_invalid"
                ) from error
        else:
            raise KnowledgeHistoryError(f"{field}_timestamp_invalid")
        try:
            normalized[field] = _timestamp(parsed)
        except ValueError as error:
            raise KnowledgeHistoryError(
                f"{field}_timestamp_not_aware"
            ) from error

    _validate_state_values(normalized)
    try:
        _canonical_json(normalized)
    except (TypeError, ValueError) as error:
        raise KnowledgeHistoryError("snapshot_state_not_json_serializable") from error
    return normalized


def knowledge_item_content_hash(
    item: KnowledgeItem | Mapping[str, Any],
) -> str:
    """Hash B2 semantic fields from a row or a decoded KnowledgeItem state."""
    content_state = (
        {field: item[field] for field in _CONTENT_FIELDS}
        if isinstance(item, Mapping)
        else {field: getattr(item, field) for field in _CONTENT_FIELDS}
    )

    confidence = content_state["confidence"]
    if isinstance(confidence, bool) or not isinstance(
        confidence, (str, decimal.Decimal)
    ):
        raise KnowledgeHistoryError("content_hash_confidence_invalid")
    try:
        confidence_value = decimal.Decimal(confidence)
    except decimal.InvalidOperation as error:
        raise KnowledgeHistoryError("content_hash_confidence_invalid") from error
    if not confidence_value.is_finite():
        raise KnowledgeHistoryError("content_hash_confidence_invalid")
    content_state["confidence"] = format(confidence_value, "f")

    try:
        canonical = _canonical_json(content_state).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise KnowledgeHistoryError(
            "content_hash_state_not_json_serializable"
        ) from error

    framed = (
        KNOWLEDGE_CONTENT_HASH_SCHEME.encode("utf-8")
        + b"\x00"
        + canonical
    )
    return "sha256:" + hashlib.sha256(framed).hexdigest()


def _snapshot_hash(payload_without_hash: Mapping[str, Any]) -> str:
    try:
        canonical = _canonical_json(dict(payload_without_hash)).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise KnowledgeHistoryError("snapshot_state_not_json_serializable") from error
    framed = (
        SNAPSHOT_HASH_DOMAIN_SEPARATOR.encode("utf-8")
        + b"\x00"
        + canonical
    )
    return "sha256:" + hashlib.sha256(framed).hexdigest()


def encode_state_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    """Encode a complete B0.3 full-state envelope with a deterministic hash."""
    normalized = _normalize_snapshot_state(dict(state))
    payload: dict[str, Any] = {
        "snapshot_version": SNAPSHOT_VERSION,
        "state": normalized,
    }
    return {**payload, "snapshot_hash": _snapshot_hash(payload)}


def decode_state_snapshot(
    payload: object,
    *,
    learning_change_id: uuid.UUID,
    operation: str,
    allow_legacy_root: bool = False,
) -> tuple[dict[str, Any], frozenset[str]]:
    """Decode B0.3 envelopes or the exact immutable legacy create-root shape.

    Legacy values are synthesized only in memory for the root create node. The
    original stored JSON is never rewritten or represented as a new envelope.
    """
    if not isinstance(payload, dict):
        raise KnowledgeHistoryError("snapshot_not_object")

    reconstructed: frozenset[str] = frozenset()
    envelope_fields = {"snapshot_version", "state", "snapshot_hash"}
    if set(payload) == envelope_fields:
        version = payload["snapshot_version"]
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version != SNAPSHOT_VERSION
            or not isinstance(payload["state"], dict)
        ):
            raise KnowledgeHistoryError("snapshot_envelope_invalid")
        raw_state = dict(payload["state"])
        state = _normalize_snapshot_state(raw_state)
        if state != raw_state:
            raise KnowledgeHistoryError("snapshot_state_not_canonical")
        expected_hash = _snapshot_hash(
            {
                "snapshot_version": SNAPSHOT_VERSION,
                "state": state,
            }
        )
        if payload["snapshot_hash"] != expected_hash:
            raise KnowledgeHistoryError("snapshot_hash_mismatch")
    else:
        if not allow_legacy_root or operation != "create":
            raise KnowledgeHistoryError("legacy_snapshot_not_allowed")
        if set(payload) != LEGACY_STATE_FIELDS:
            raise KnowledgeHistoryError("legacy_root_snapshot_shape_invalid")
        state = dict(payload)
        missing = {
            "current_learning_change_id",
            "supersedes_item_id",
            "superseded_by_id",
        }
        state["current_learning_change_id"] = str(learning_change_id)
        state["supersedes_item_id"] = None
        state["superseded_by_id"] = None
        reconstructed = frozenset(missing)
        # Normalize only the decoded in-memory view. The immutable historical
        # committed_state JSON remains byte-for-byte unchanged in the database.
        state = _normalize_snapshot_state(state)

    if state["current_learning_change_id"] != str(learning_change_id):
        raise KnowledgeHistoryError("snapshot_pointer_does_not_match_change")
    return state, reconstructed


def reconstruct_history(
    changes: Iterable[Any],
    *,
    item_id: uuid.UUID,
    team_id: uuid.UUID,
    origin_learning_change_id: uuid.UUID,
    current_learning_change_id: uuid.UUID,
    review_markers: Iterable[ReviewMarker] = (),
) -> KnowledgeHistoryResult:
    """Reconstruct a single item by pointer links, then apply verified D7 overlays.

    Timestamps validate ordering only after the pointer graph and state evidence
    identify a unique node. They are never used to choose the "latest" parent.
    """
    accepted = [
        change for change in changes if getattr(change, "status", None) == "accepted"
    ]
    by_id: dict[uuid.UUID, Any] = {}
    for change in accepted:
        if change.team_id != team_id:
            raise KnowledgeHistoryError("accepted_change_cross_team")
        if change.id in by_id:
            raise KnowledgeHistoryError("duplicate_learning_change_id")
        by_id[change.id] = change

    root = by_id.get(origin_learning_change_id)
    if (
        root is None
        or root.operation != "create"
        or root.target_id is not None
        or root.target_kind != "knowledge_item"
    ):
        raise KnowledgeHistoryError("accepted_create_root_missing_or_invalid")

    root_state, reconstructed = decode_state_snapshot(
        root.committed_state,
        learning_change_id=root.id,
        operation="create",
        allow_legacy_root=True,
    )
    _validate_root_state(root, root_state, item_id=item_id, team_id=team_id)

    children: dict[uuid.UUID, list[Any]] = defaultdict(list)
    decoded_previous: dict[uuid.UUID, dict[str, Any]] = {}
    decoded_committed: dict[uuid.UUID, dict[str, Any]] = {}

    for change in accepted:
        if change.id == root.id:
            continue
        if (
            change.operation not in {"revise", "revalidate", "supersede", "retire"}
            or change.target_kind != "knowledge_item"
            or change.target_id != item_id
        ):
            raise KnowledgeHistoryError("accepted_change_target_or_operation_invalid")
        previous, previous_legacy = decode_state_snapshot(
            change.previous_state,
            learning_change_id=_previous_pointer(change.previous_state),
            operation=change.operation,
            allow_legacy_root=False,
        )
        if previous_legacy:
            raise KnowledgeHistoryError("non_root_legacy_snapshot")
        committed, committed_legacy = decode_state_snapshot(
            change.committed_state,
            learning_change_id=change.id,
            operation=change.operation,
            allow_legacy_root=False,
        )
        if committed_legacy:
            raise KnowledgeHistoryError("non_root_legacy_snapshot")
        parent_id = _uuid(previous["current_learning_change_id"])
        if parent_id == change.id:
            raise KnowledgeHistoryError("history_self_parent")
        decoded_previous[change.id] = previous
        decoded_committed[change.id] = committed
        children[parent_id].append(change)

    for parent_id, child_changes in children.items():
        if parent_id not in by_id or len(child_changes) != 1:
            raise KnowledgeHistoryError(
                "history_missing_parent" if parent_id not in by_id else "history_fork"
            )

    ordered: list[Any] = [root]
    visited = {root.id}
    while children.get(ordered[-1].id):
        child = children[ordered[-1].id][0]
        if child.id in visited:
            raise KnowledgeHistoryError("history_cycle")
        visited.add(child.id)
        ordered.append(child)

    if visited != set(by_id):
        raise KnowledgeHistoryError("history_disconnected_or_unreachable_change")
    if ordered[-1].id != current_learning_change_id:
        raise KnowledgeHistoryError("current_pointer_is_not_history_leaf")

    states: list[dict[str, Any]] = [root_state]
    legacy_fields = set(reconstructed)
    for position, change in enumerate(ordered[1:], start=1):
        state = decoded_committed[change.id]
        if (
            state["id"] != str(item_id)
            or state["team_id"] != str(team_id)
            or state["origin_learning_change_id"] != str(origin_learning_change_id)
            or state["current_learning_change_id"] != str(change.id)
        ):
            raise KnowledgeHistoryError("committed_snapshot_identity_mismatch")
        parent_time = _aware_datetime(
            ordered[position - 1].committed_at, "learning_change_committed_at"
        )
        child_time = _aware_datetime(
            change.committed_at, "learning_change_committed_at"
        )
        if child_time < parent_time:
            raise KnowledgeHistoryError("history_commit_timestamp_order_invalid")
        states.append(state)

    markers = sorted(
        review_markers,
        key=lambda marker: _aware_datetime(marker.reviewed_at, "reviewed_at"),
    )
    overlays: dict[uuid.UUID, ReviewMarker] = {}
    node_index = {change.id: index for index, change in enumerate(ordered)}
    for marker in markers:
        if (
            marker.item_id != item_id
            or marker.origin_learning_change_id != origin_learning_change_id
        ):
            raise KnowledgeHistoryError("review_event_item_identity_mismatch")
        if marker.current_learning_change_id is not None:
            index = node_index.get(marker.current_learning_change_id)
            if index is None:
                raise KnowledgeHistoryError("review_event_pointer_not_in_history")
            candidates = [index]
        else:
            candidates = [
                index
                for index, state in enumerate(states)
                if state["status"] == "active"
                and ordered[index].id not in overlays
                and state["version"] == marker.version
                and state["review_after"] == marker.review_after
                and state["origin_learning_change_id"]
                == str(marker.origin_learning_change_id)
            ]
            if len(candidates) != 1:
                raise KnowledgeHistoryError("legacy_review_event_placement_ambiguous")

        if len(candidates) != 1:
            raise KnowledgeHistoryError("review_event_placement_ambiguous")
        index = candidates[0]
        state = states[index]
        if (
            state["status"] != "active"
            or state["version"] != marker.version
            or state["review_after"] != marker.review_after
            or state["origin_learning_change_id"]
            != str(marker.origin_learning_change_id)
        ):
            raise KnowledgeHistoryError("review_event_state_binding_mismatch")
        if ordered[index].id in overlays:
            raise KnowledgeHistoryError("duplicate_review_overlay_for_history_node")
        reviewed_at = _aware_datetime(marker.reviewed_at, "reviewed_at")
        review_after = _parse_timestamp(marker.review_after, "review_after")
        if review_after > reviewed_at:
            raise KnowledgeHistoryError("review_event_before_due_date")
        node_committed_at = _aware_datetime(
            ordered[index].committed_at, "learning_change_committed_at"
        )
        if reviewed_at < node_committed_at:
            raise KnowledgeHistoryError("review_event_precedes_history_node")
        if index + 1 < len(ordered):
            next_committed_at = _aware_datetime(
                ordered[index + 1].committed_at, "learning_change_committed_at"
            )
            if reviewed_at >= next_committed_at:
                raise KnowledgeHistoryError("review_event_after_successor_commit")
        overlays[ordered[index].id] = marker

    for index, change in enumerate(ordered[1:], start=1):
        previous = decoded_previous[change.id]
        expected_previous = dict(states[index - 1])
        if ordered[index - 1].id in overlays:
            expected_previous["status"] = "needs_review"
        if previous != expected_previous:
            raise KnowledgeHistoryError("previous_snapshot_does_not_match_parent_state")
        _validate_transition(
            change.operation,
            expected_previous,
            states[index],
            change_id=change.id,
            committed_at=change.committed_at,
        )

    final_state = dict(states[-1])
    if ordered[-1].id in overlays:
        final_state["status"] = "needs_review"
    if final_state["current_learning_change_id"] != str(current_learning_change_id):
        raise KnowledgeHistoryError("reconstructed_current_pointer_mismatch")

    return KnowledgeHistoryResult(
        state=final_state,
        learning_change_ids=tuple(change.id for change in ordered),
        reconstructed_legacy_fields=frozenset(legacy_fields),
        applied_review_event_ids=tuple(marker.event_id for marker in markers),
        states=tuple(dict(state) for state in states),
    )


def reconstruct_knowledge_item_history(
    session: Session, item: KnowledgeItem
) -> KnowledgeHistoryResult:
    """Load durable rows, validate approval/D7 provenance, and match the live row."""
    changes = list(
        session.scalars(
            select(LearningChange).where(
                (
                    (LearningChange.id == item.origin_learning_change_id)
                    | (LearningChange.target_id == item.id)
                ),
                LearningChange.status == "accepted",
            )
        )
    )
    if any(change.team_id != item.team_id for change in changes):
        raise KnowledgeHistoryError("accepted_change_cross_team")

    approval_tasks: dict[uuid.UUID, Task] = {}
    for change in changes:
        approval_tasks[change.id] = _validate_learning_change_approval(session, change)

    rows = session.execute(
        select(Event, Task)
        .join(Task, Task.id == Event.task_id)
        .where(
            Event.type == "knowledge_items_reviewed",
            Task.team_id == item.team_id,
        )
    ).all()
    markers: list[ReviewMarker] = []
    for event, task in rows:
        markers.extend(_validated_review_markers(session, event, task, item.id))

    result = reconstruct_history(
        changes,
        item_id=item.id,
        team_id=item.team_id,
        origin_learning_change_id=item.origin_learning_change_id,
        current_learning_change_id=item.current_learning_change_id,
        review_markers=markers,
    )
    if result.state != knowledge_item_state(item):
        raise KnowledgeHistoryError("reconstructed_history_does_not_match_live_item")

    changes_by_id = {change.id: change for change in changes}
    for change_id, state in zip(result.learning_change_ids, result.states):
        change = changes_by_id[change_id]
        if change.operation not in {"create", "revise", "revalidate"}:
            continue
        task = approval_tasks[change_id]
        policy = session.scalar(
            select(TeamPolicy).where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
        )
        if policy is None:
            raise KnowledgeHistoryError("history_approval_policy_missing")
        try:
            interval_days = knowledge_item_review_interval_days(
                policy.rules, policy.schema_version
            )
        except InvalidPolicyError as error:
            raise KnowledgeHistoryError("history_approval_policy_invalid") from error
        committed_at = _aware_datetime(
            change.committed_at, "learning_change_committed_at"
        )
        expected_review_after = (
            committed_at + dt.timedelta(days=interval_days)
            if interval_days is not None
            else None
        )
        actual_review_after = (
            _parse_timestamp(state["review_after"], "review_after")
            if state["review_after"] is not None
            else None
        )
        expected_review_after_utc = (
            _aware_datetime(expected_review_after, "expected_review_after")
            if expected_review_after is not None
            else None
        )
        if actual_review_after != expected_review_after_utc:
            raise KnowledgeHistoryError("history_review_after_policy_mismatch")
        if change.operation == "revalidate":
            validated_at = _parse_timestamp(
                state["last_validated_at"], "last_validated_at"
            )
            if validated_at != _aware_datetime(
                change.committed_at, "learning_change_committed_at"
            ):
                raise KnowledgeHistoryError("history_revalidation_timestamp_mismatch")

    _validate_live_supersession_links(session, item)
    return result


def _validate_learning_change_approval(
    session: Session, change: LearningChange
) -> Task:
    if (
        change.status != "accepted"
        or change.committed_by_task_id is None
        or not isinstance(change.operator_id, str)
        or not change.operator_id
        or change.committed_at is None
    ):
        raise KnowledgeHistoryError("accepted_change_decision_metadata_invalid")
    task = session.get(Task, change.committed_by_task_id)
    if (
        task is None
        or task.team_id != change.team_id
        or task.task_type != "approve_learning_change"
        or task.status not in {"running", "done"}
        or task.attempt_count < 1
        or task.allowed_writes != ["LearningChange", "KnowledgeItem"]
        or task.objective_id is not None
        or task.plan_id is not None
        or task.plan_action_id is not None
    ):
        raise KnowledgeHistoryError("accepted_change_approval_task_invalid")
    events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "learning_change_accepted",
            )
        )
    )
    if len(events) != 1:
        raise KnowledgeHistoryError(
            "accepted_change_decision_event_missing_or_duplicate"
        )
    payload = events[0].payload
    if (
        not isinstance(payload, dict)
        or payload.get("learning_change_id") != str(change.id)
        or payload.get("operation") != change.operation
        or payload.get("decision") != "accept"
        or payload.get("operator_id") != change.operator_id
        or payload.get("approval_task_id") != str(task.id)
        or payload.get("committed_at") != change.committed_at.isoformat()
        or events[0].created_at != change.committed_at
    ):
        raise KnowledgeHistoryError("accepted_change_decision_event_mismatch")
    attempt = payload.get("attempt_count")
    if (
        isinstance(attempt, bool)
        or not isinstance(attempt, int)
        or attempt < 1
        or attempt > task.attempt_count
    ):
        raise KnowledgeHistoryError("accepted_change_decision_attempt_invalid")
    start_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "task_started",
                Event.payload["attempt_count"].as_integer() == attempt,
            )
        )
    )
    if (
        len(start_events) != 1
        or start_events[0].payload
        != {
            "from_status": "pending",
            "to_status": "running",
            "attempt_count": attempt,
        }
        or start_events[0].created_at > change.committed_at
    ):
        raise KnowledgeHistoryError("accepted_change_task_start_provenance_invalid")

    if task.status == "done":
        outcomes = list(
            session.scalars(
                select(Outcome).where(
                    Outcome.recorded_by_task_id == task.id,
                    Outcome.outcome_type == "task_execution",
                )
            )
        )
        completed = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == "task_completed",
                )
            )
        )
        if len(outcomes) != 1 or len(completed) != 1:
            raise KnowledgeHistoryError("accepted_change_terminal_provenance_missing")
        outcome = outcomes[0]
        terminal_payload = completed[0].payload
        if (
            outcome.team_id != change.team_id
            or outcome.subject_kind != "task"
            or outcome.subject_id != task.id
            or not isinstance(terminal_payload, dict)
            or terminal_payload.get("to_status") != "done"
            or terminal_payload.get("result_category")
            != "success_learning_change_accepted"
            or terminal_payload.get("attempt_count") != task.attempt_count
            or terminal_payload.get("learning_change_id") != str(change.id)
            or terminal_payload.get("outcome_id") != str(outcome.id)
            or terminal_payload.get("observation_snapshot_ref")
            != outcome.observation_snapshot_ref
            or terminal_payload.get("observation_hash") != outcome.observation_hash
            or task.completed_at is None
        ):
            raise KnowledgeHistoryError("accepted_change_terminal_provenance_invalid")
    return task


def _validated_review_markers(
    session: Session,
    event: Event,
    task: Task,
    item_id: uuid.UUID,
) -> list[ReviewMarker]:
    payload = event.payload
    if not isinstance(payload, dict) or set(payload) != _REVIEW_TOP_LEVEL_FIELDS:
        raise KnowledgeHistoryError("review_event_payload_shape_invalid")
    if (
        isinstance(payload.get("schema_version"), bool)
        or payload.get("schema_version") != 1
        or payload.get("team_id") != str(task.team_id)
        or payload.get("task_id") != str(task.id)
        or task.task_type != "review_knowledge"
        or task.status != "done"
        or task.completed_at is None
        or task.allowed_writes != ["KnowledgeItem"]
        or task.objective_id is not None
        or task.plan_id is not None
        or task.plan_action_id is not None
        or not isinstance(task.budget, dict)
        or isinstance(task.budget.get("max_tool_calls"), bool)
        or task.budget.get("max_tool_calls") != 0
        or isinstance(task.budget.get("max_cost_usd"), bool)
        or task.budget.get("max_cost_usd") != 0
        or isinstance(task.budget.get("deadline_seconds"), bool)
        or not isinstance(task.budget.get("deadline_seconds"), int)
        or task.budget["deadline_seconds"] < 1
    ):
        raise KnowledgeHistoryError("review_event_task_provenance_invalid")

    reviewed_at = _parse_timestamp(payload.get("reviewed_at"), "reviewed_at")
    if event.created_at != reviewed_at or task.completed_at != reviewed_at:
        raise KnowledgeHistoryError("review_event_timestamp_provenance_invalid")
    attempt = payload.get("attempt_count")
    if (
        isinstance(attempt, bool)
        or not isinstance(attempt, int)
        or attempt < 1
        or attempt != task.attempt_count
    ):
        raise KnowledgeHistoryError("review_event_attempt_invalid")
    if not isinstance(payload.get("items"), list):
        raise KnowledgeHistoryError("review_event_items_invalid")

    outcomes = list(
        session.scalars(
            select(Outcome).where(
                Outcome.recorded_by_task_id == task.id,
                Outcome.outcome_type == "task_execution",
            )
        )
    )
    completed_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "task_completed",
            )
        )
    )
    started_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "task_started",
                Event.payload["attempt_count"].as_integer() == attempt,
            )
        )
    )
    if (
        len(outcomes) != 1
        or len(completed_events) != 1
        or len(started_events) != 1
        or started_events[0].payload
        != {
            "from_status": "pending",
            "to_status": "running",
            "attempt_count": attempt,
        }
    ):
        raise KnowledgeHistoryError("review_event_terminal_provenance_missing")
    outcome = outcomes[0]
    completion = completed_events[0]
    completion_payload = completion.payload
    if (
        outcome.team_id != task.team_id
        or outcome.subject_kind != "task"
        or outcome.subject_id != task.id
        or outcome.observed_at != reviewed_at
        or outcome.observation_snapshot_ref is None
        or not isinstance(outcome.observation_hash, str)
        or _SHA256_RE.fullmatch(outcome.observation_hash) is None
        or not isinstance(completion_payload, dict)
        or completion_payload.get("from_status") != "running"
        or completion_payload.get("to_status") != "done"
        or completion_payload.get("attempt_count") != attempt
        or completion_payload.get("result_category") != "success_knowledge_reviewed"
        or completion_payload.get("outcome_id") != str(outcome.id)
        or completion_payload.get("observation_snapshot_ref")
        != outcome.observation_snapshot_ref
        or completion_payload.get("observation_hash") != outcome.observation_hash
    ):
        raise KnowledgeHistoryError("review_event_outcome_provenance_invalid")

    matched: list[ReviewMarker] = []
    seen_item_ids: set[str] = set()
    for record in payload["items"]:
        if not isinstance(record, dict):
            raise KnowledgeHistoryError("review_event_item_record_invalid")
        keys = set(record)
        if (
            keys != _REVIEW_ITEM_FIELDS
            and keys != (_REVIEW_ITEM_FIELDS | {"current_learning_change_id"})
        ):
            raise KnowledgeHistoryError("review_event_item_record_shape_invalid")
        record_item_id = _canonical_uuid(record.get("knowledge_item_id"))
        if record_item_id in seen_item_ids:
            raise KnowledgeHistoryError("review_event_duplicate_item")
        seen_item_ids.add(record_item_id)
        if record_item_id != str(item_id):
            continue
        version = record.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise KnowledgeHistoryError("review_event_item_version_invalid")
        review_after = record.get("review_after")
        if not isinstance(review_after, str):
            raise KnowledgeHistoryError("review_event_item_review_after_invalid")
        review_after = _timestamp(
            _parse_timestamp(review_after, "review_after")
        )
        origin_id = _canonical_uuid(record.get("origin_learning_change_id"))
        pointer = (
            _canonical_uuid(record.get("current_learning_change_id"))
            if "current_learning_change_id" in record
            else None
        )
        matched.append(
            ReviewMarker(
                event_id=event.id,
                item_id=item_id,
                current_learning_change_id=(
                    uuid.UUID(pointer) if pointer is not None else None
                ),
                version=version,
                review_after=review_after,
                origin_learning_change_id=uuid.UUID(origin_id),
                reviewed_at=reviewed_at,
            )
        )
    return matched


def _validate_live_supersession_links(session: Session, item: KnowledgeItem) -> None:
    """Validate both directions of the same-Team supersession chain.

    A candidate may point at its predecessor before supersession is committed,
    so a predecessor's reciprocal successor link may be NULL. Once a reciprocal
    successor link exists, it must point back to the candidate and the
    predecessor must already be retired. Walk the full ancestor and successor
    chains so cycles longer than one edge cannot evade the local foreign-key
    and uniqueness constraints.
    """
    team_id = item.team_id

    ancestors = {item.id}
    current = item
    while current.supersedes_item_id is not None:
        predecessor_id = current.supersedes_item_id
        if predecessor_id in ancestors:
            raise KnowledgeHistoryError("supersession_cycle")
        predecessor = session.get(KnowledgeItem, predecessor_id)
        if (
            predecessor is None
            or predecessor.team_id != team_id
            or predecessor.id == current.id
            or (
                predecessor.superseded_by_id is not None
                and (
                    predecessor.superseded_by_id != current.id
                    or predecessor.status != "retired"
                )
            )
        ):
            raise KnowledgeHistoryError("supersession_predecessor_link_invalid")
        ancestors.add(predecessor.id)
        current = predecessor

    successors = {item.id}
    current = item
    while current.superseded_by_id is not None:
        successor_id = current.superseded_by_id
        if successor_id in successors:
            raise KnowledgeHistoryError("supersession_cycle")
        successor = session.get(KnowledgeItem, successor_id)
        if (
            successor is None
            or successor.team_id != team_id
            or successor.id == current.id
            or successor.supersedes_item_id != current.id
            or current.status != "retired"
        ):
            raise KnowledgeHistoryError("supersession_successor_link_invalid")
        successors.add(successor.id)
        current = successor


def _validate_root_state(
    root: Any,
    state: dict[str, Any],
    *,
    item_id: uuid.UUID,
    team_id: uuid.UUID,
) -> None:
    if (
        root.team_id != team_id
        or state["id"] != str(item_id)
        or state["team_id"] != str(team_id)
        or state["origin_learning_change_id"] != str(root.id)
        or state["current_learning_change_id"] != str(root.id)
        or state["version"] != 1
        or state["status"] != "active"
        or state["last_validated_at"] is not None
        or state["superseded_by_id"] is not None
    ):
        raise KnowledgeHistoryError("create_root_state_invalid")


def _validate_transition(
    operation: str,
    previous: dict[str, Any],
    committed: dict[str, Any],
    *,
    change_id: uuid.UUID,
    committed_at: dt.datetime,
) -> None:
    if (
        previous["id"] != committed["id"]
        or previous["team_id"] != committed["team_id"]
        or previous["origin_learning_change_id"]
        != committed["origin_learning_change_id"]
        or committed["current_learning_change_id"] != str(change_id)
        or previous["current_learning_change_id"] == str(change_id)
    ):
        raise KnowledgeHistoryError("transition_identity_or_pointer_invalid")

    if operation == "revise":
        content_changed = any(
            previous[field] != committed[field] for field in _CONTENT_FIELDS
        )
        if (
            previous["status"] not in {"active", "needs_review"}
            or committed["version"] != previous["version"] + 1
            or committed["status"] != previous["status"]
            or not content_changed
            or committed["last_validated_at"] is not None
            or committed["supersedes_item_id"] != previous["supersedes_item_id"]
            or committed["superseded_by_id"] != previous["superseded_by_id"]
        ):
            raise KnowledgeHistoryError("revise_transition_invalid")
        return

    unchanged_content = all(
        previous[field] == committed[field] for field in _CONTENT_FIELDS
    )
    if operation == "revalidate":
        if (
            previous["status"] != "needs_review"
            or committed["status"] != "active"
            or committed["version"] != previous["version"]
            or not unchanged_content
            or committed["last_validated_at"] is None
            or _parse_timestamp(
                committed["last_validated_at"], "last_validated_at"
            ) != _aware_datetime(committed_at, "learning_change_committed_at")
            or committed["supersedes_item_id"] != previous["supersedes_item_id"]
            or committed["superseded_by_id"] != previous["superseded_by_id"]
        ):
            raise KnowledgeHistoryError("revalidate_transition_invalid")
        _parse_timestamp(committed["last_validated_at"], "last_validated_at")
        return

    if operation == "retire":
        if (
            previous["status"] not in {"active", "needs_review"}
            or committed["status"] != "retired"
            or committed["version"] != previous["version"]
            or not unchanged_content
            or committed["last_validated_at"] != previous["last_validated_at"]
            or committed["review_after"] != previous["review_after"]
            or committed["supersedes_item_id"] != previous["supersedes_item_id"]
            or committed["superseded_by_id"] != previous["superseded_by_id"]
            or committed["superseded_by_id"] is not None
        ):
            raise KnowledgeHistoryError("retire_transition_invalid")
        return

    if operation == "supersede":
        successor_id = committed["superseded_by_id"]
        if (
            previous["status"] not in {"active", "needs_review"}
            or committed["status"] != "retired"
            or committed["version"] != previous["version"]
            or not unchanged_content
            or committed["last_validated_at"] != previous["last_validated_at"]
            or committed["review_after"] != previous["review_after"]
            or committed["supersedes_item_id"] != previous["supersedes_item_id"]
            or previous["superseded_by_id"] is not None
            or successor_id is None
            or successor_id == committed["id"]
        ):
            raise KnowledgeHistoryError("supersede_transition_invalid")
        _canonical_uuid(successor_id)
        return

    raise KnowledgeHistoryError("unsupported_lifecycle_operation")


def _validate_state_shape(state: dict[str, Any], *, exact: bool) -> None:
    keys = set(state)
    if exact and keys != STATE_FIELDS:
        raise KnowledgeHistoryError("snapshot_state_fields_invalid")
    if not exact and not LEGACY_STATE_FIELDS.issubset(keys):
        raise KnowledgeHistoryError("snapshot_state_fields_incomplete")


def _validate_state_values(state: dict[str, Any]) -> None:
    for field in _UUID_FIELDS:
        _canonical_uuid(state.get(field))
    for field in _OPTIONAL_UUID_FIELDS:
        value = state.get(field)
        if value is not None:
            _canonical_uuid(value)
    version = state.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise KnowledgeHistoryError("snapshot_version_invalid")
    if state.get("status") not in {"active", "needs_review", "retired"}:
        raise KnowledgeHistoryError("snapshot_status_invalid")
    confidence = state.get("confidence")
    if not isinstance(confidence, str):
        raise KnowledgeHistoryError("snapshot_confidence_invalid")
    try:
        value = decimal.Decimal(confidence)
    except decimal.InvalidOperation as error:
        raise KnowledgeHistoryError("snapshot_confidence_invalid") from error
    if not value.is_finite() or value < 0 or value > 1:
        raise KnowledgeHistoryError("snapshot_confidence_invalid")
    for field in _DATETIME_FIELDS:
        value = state.get(field)
        if value is not None:
            _parse_timestamp(value, field)


def _previous_pointer(payload: object) -> uuid.UUID:
    if (
        isinstance(payload, dict)
        and set(payload) == {"snapshot_version", "state", "snapshot_hash"}
        and isinstance(payload.get("state"), dict)
    ):
        value = payload["state"].get("current_learning_change_id")
    else:
        value = None
    return uuid.UUID(_canonical_uuid(value))


def _canonical_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise KnowledgeHistoryError("snapshot_uuid_invalid")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as error:
        raise KnowledgeHistoryError("snapshot_uuid_invalid") from error
    if str(parsed) != value:
        raise KnowledgeHistoryError("snapshot_uuid_not_canonical")
    return value


def _uuid(value: object) -> uuid.UUID:
    return uuid.UUID(_canonical_uuid(value))


def _parse_timestamp(value: object, field: str) -> dt.datetime:
    if not isinstance(value, str):
        raise KnowledgeHistoryError(f"{field}_timestamp_invalid")
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as error:
        raise KnowledgeHistoryError(f"{field}_timestamp_invalid") from error
    return _aware_datetime(parsed, field)


def _aware_datetime(value: object, field: str) -> dt.datetime:
    if (
        not isinstance(value, dt.datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise KnowledgeHistoryError(f"{field}_timestamp_not_aware")
    return value.astimezone(dt.timezone.utc)
