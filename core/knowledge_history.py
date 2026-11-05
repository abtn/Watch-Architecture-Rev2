"""Versioned KnowledgeItem snapshots and deterministic lifecycle reconstruction.

B1 keeps immutable LearningChange snapshots as the lifecycle history. The live
KnowledgeItem row is checked against the chain tip; D7 review Events are the
only permitted status overlay that does not advance the current pointer.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Event, KnowledgeItem, LearningChange, Outcome, Task
from core.state_assessment import _canonical_json


SNAPSHOT_VERSION = 1
SNAPSHOT_DOMAIN_SEPARATOR = "watch.r7b.knowledge-item-state.v1"

_LEGACY_STATE_KEYS = frozenset(
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
    }
)
_STATE_KEYS = _LEGACY_STATE_KEYS | frozenset(
    {
        "current_learning_change_id",
        "supersedes_item_id",
        "superseded_by_id",
    }
)
_SEMANTIC_KEYS = (
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
_LIFECYCLE_OPERATIONS = frozenset(
    {"revise", "revalidate", "supersede", "retire"}
)


class KnowledgeHistoryError(ValueError):
    """A canonical KnowledgeItem history is incomplete or inconsistent."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class DecodedKnowledgeSnapshot:
    state: dict[str, Any]
    snapshot_version: int
    reconstructed_legacy_fields: tuple[str, ...]
    snapshot_hash: str | None


@dataclass(frozen=True)
class KnowledgeItemHistory:
    knowledge_item_id: UUID
    team_id: UUID
    pointer_order: tuple[UUID, ...]
    states_by_pointer: dict[UUID, dict[str, Any]]
    current_state: dict[str, Any]
    reconstructed_legacy_fields: tuple[str, ...]


def _uuid_text(value: object, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise KnowledgeHistoryError("knowledge_snapshot_uuid_invalid") from error
    normalized = str(parsed)
    if str(value) != normalized:
        raise KnowledgeHistoryError("knowledge_snapshot_uuid_not_canonical")
    return normalized


def _timestamp_text(value: object, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise KnowledgeHistoryError("knowledge_snapshot_timestamp_invalid") from error
    else:
        raise KnowledgeHistoryError("knowledge_snapshot_timestamp_invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KnowledgeHistoryError("knowledge_snapshot_timestamp_naive")
    return (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _confidence_text(value: object) -> str:
    if isinstance(value, bool):
        raise KnowledgeHistoryError("knowledge_snapshot_confidence_invalid")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise KnowledgeHistoryError("knowledge_snapshot_confidence_invalid") from error
    if not parsed.is_finite():
        raise KnowledgeHistoryError("knowledge_snapshot_confidence_invalid")
    return format(parsed, "f")


def _normalize_state(state: object) -> dict[str, Any]:
    if not isinstance(state, dict) or set(state) != _STATE_KEYS:
        raise KnowledgeHistoryError("knowledge_snapshot_state_shape_invalid")
    normalized = dict(state)
    normalized["id"] = _uuid_text(normalized["id"])
    normalized["team_id"] = _uuid_text(normalized["team_id"])
    normalized["origin_learning_change_id"] = _uuid_text(
        normalized["origin_learning_change_id"]
    )
    normalized["current_learning_change_id"] = _uuid_text(
        normalized["current_learning_change_id"]
    )
    normalized["supersedes_item_id"] = _uuid_text(
        normalized["supersedes_item_id"], nullable=True
    )
    normalized["superseded_by_id"] = _uuid_text(
        normalized["superseded_by_id"], nullable=True
    )
    normalized["confidence"] = _confidence_text(normalized["confidence"])
    normalized["last_validated_at"] = _timestamp_text(
        normalized["last_validated_at"], nullable=True
    )
    normalized["review_after"] = _timestamp_text(
        normalized["review_after"], nullable=True
    )
    if (
        isinstance(normalized["version"], bool)
        or not isinstance(normalized["version"], int)
        or normalized["version"] < 1
    ):
        raise KnowledgeHistoryError("knowledge_snapshot_version_invalid")
    if normalized["status"] not in {"active", "needs_review", "retired"}:
        raise KnowledgeHistoryError("knowledge_snapshot_status_invalid")
    if normalized["supersedes_item_id"] == normalized["id"]:
        raise KnowledgeHistoryError("knowledge_snapshot_self_supersession")
    if normalized["superseded_by_id"] == normalized["id"]:
        raise KnowledgeHistoryError("knowledge_snapshot_self_supersession")
    return normalized


def knowledge_item_snapshot_state(item: KnowledgeItem) -> dict[str, Any]:
    """Return every persisted lifecycle and semantic field in canonical form."""
    raw = {
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
        "confidence": format(item.confidence, "f"),
        "status": item.status,
        "version": item.version,
        "last_validated_at": item.last_validated_at,
        "review_after": item.review_after,
        "origin_learning_change_id": str(item.origin_learning_change_id),
        "current_learning_change_id": str(item.current_learning_change_id),
        "supersedes_item_id": (
            str(item.supersedes_item_id) if item.supersedes_item_id else None
        ),
        "superseded_by_id": (
            str(item.superseded_by_id) if item.superseded_by_id else None
        ),
    }
    return _normalize_state(raw)


def _snapshot_digest(snapshot_without_hash: dict[str, Any]) -> str:
    payload = _canonical_json(snapshot_without_hash).encode("utf-8")
    digest = hashlib.sha256(
        SNAPSHOT_DOMAIN_SEPARATOR.encode("utf-8") + b"\x00" + payload
    ).hexdigest()
    return "sha256:" + digest


def build_knowledge_item_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """Create the immutable B1 state envelope and its domain-separated hash."""
    normalized = _normalize_state(state)
    envelope: dict[str, Any] = {
        "snapshot_version": SNAPSHOT_VERSION,
        "state": normalized,
    }
    envelope["snapshot_hash"] = _snapshot_digest(envelope)
    return envelope


def decode_knowledge_item_snapshot(
    payload: object, *, root_learning_change_id: UUID
) -> DecodedKnowledgeSnapshot:
    """Decode a B1 envelope or the exact immutable R6 legacy create shape."""
    if not isinstance(payload, dict):
        raise KnowledgeHistoryError("knowledge_snapshot_payload_invalid")

    if set(payload) == {"snapshot_version", "state", "snapshot_hash"}:
        if payload.get("snapshot_version") != SNAPSHOT_VERSION:
            raise KnowledgeHistoryError("knowledge_snapshot_version_unsupported")
        state = _normalize_state(payload.get("state"))
        digest_value = payload.get("snapshot_hash")
        expected = _snapshot_digest(
            {
                "snapshot_version": SNAPSHOT_VERSION,
                "state": state,
            }
        )
        if digest_value != expected:
            raise KnowledgeHistoryError("knowledge_snapshot_hash_mismatch")
        return DecodedKnowledgeSnapshot(
            state=state,
            snapshot_version=SNAPSHOT_VERSION,
            reconstructed_legacy_fields=(),
            snapshot_hash=expected,
        )

    if set(payload) != _LEGACY_STATE_KEYS:
        raise KnowledgeHistoryError("knowledge_snapshot_legacy_shape_invalid")

    legacy = dict(payload)
    legacy["current_learning_change_id"] = str(root_learning_change_id)
    legacy["supersedes_item_id"] = None
    legacy["superseded_by_id"] = None
    state = _normalize_state(legacy)
    return DecodedKnowledgeSnapshot(
        state=state,
        snapshot_version=0,
        reconstructed_legacy_fields=(
            "current_learning_change_id",
            "supersedes_item_id",
            "superseded_by_id",
        ),
        snapshot_hash=None,
    )


def _parse_uuid(value: object, reason: str) -> UUID:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise KnowledgeHistoryError(reason) from error
    if str(parsed) != str(value):
        raise KnowledgeHistoryError(reason)
    return parsed


def _parse_time(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise KnowledgeHistoryError("knowledge_review_event_timestamp_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KnowledgeHistoryError("knowledge_review_event_timestamp_naive")
    return parsed.astimezone(timezone.utc)


def _validate_learning_change_provenance(
    session: Session,
    change: LearningChange,
    state: dict[str, Any],
) -> None:
    """Verify the trusted Operator decision and terminal Task evidence for one node."""
    task = session.get(Task, change.committed_by_task_id)
    if (
        task is None
        or task.team_id != change.team_id
        or task.task_type != "approve_learning_change"
        or task.status not in {"running", "done"}
        or task.attempt_count < 1
        or task.allowed_writes != ["LearningChange", "KnowledgeItem"]
        or change.operator_id is None
        or not change.operator_id
        or change.decision_reason is not None
        or change.committed_at is None
        or change.committed_state is None
        or (
            task.status == "done"
            and (
                task.completed_at is None
                or _parse_time(task.completed_at) != _parse_time(change.committed_at)
            )
        )
        or (task.status == "running" and task.completed_at is not None)
    ):
        raise KnowledgeHistoryError("knowledge_history_operator_provenance_invalid")

    starts = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "task_started",
                Event.payload["attempt_count"].as_integer() == task.attempt_count,
            )
        )
    )
    decisions = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "learning_change_accepted",
            )
        )
    )
    completions = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "task_completed",
            )
        )
    )
    outcomes = list(
        session.scalars(
            select(Outcome).where(
                Outcome.recorded_by_task_id == task.id,
                Outcome.outcome_type == "task_execution",
            )
        )
    )
    if (
        len(starts) != 1
        or starts[0].payload
        != {
            "from_status": "pending",
            "to_status": "running",
            "attempt_count": task.attempt_count,
        }
        or len(decisions) != 1
    ):
        raise KnowledgeHistoryError("knowledge_history_operator_task_events_invalid")
    if task.status == "done" and (len(completions) != 1 or len(outcomes) != 1):
        raise KnowledgeHistoryError("knowledge_history_operator_task_events_invalid")
    if task.status == "running" and (completions or outcomes):
        raise KnowledgeHistoryError("knowledge_history_operator_task_events_invalid")

    payload = decisions[0].payload
    proposal_hash = (
        change.proposed_state.get("proposal_hash")
        if isinstance(change.proposed_state, dict)
        else None
    )
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("learning_change_id") != str(change.id)
        or payload.get("operation") != change.operation
        or payload.get("decision") != "accept"
        or payload.get("operator_id") != change.operator_id
        or payload.get("approval_task_id") != str(task.id)
        or payload.get("attempt_count") != task.attempt_count
        or payload.get("evidence_basis_hash") != change.evidence_basis_hash
        or payload.get("proposal_hash") != proposal_hash
        or payload.get("knowledge_item_id") != state["id"]
        or payload.get("knowledge_item_version") != state["version"]
        or _parse_time(decisions[0].created_at) != _parse_time(change.committed_at)
    ):
        raise KnowledgeHistoryError("knowledge_history_operator_decision_event_invalid")

    if task.status == "done":
        completion_payload = completions[0].payload
        outcome = outcomes[0]
        if (
            not isinstance(completion_payload, dict)
            or completion_payload.get("from_status") != "running"
            or completion_payload.get("to_status") != "done"
            or completion_payload.get("result_category")
            != "success_learning_change_accepted"
            or completion_payload.get("learning_change_id") != str(change.id)
            or completion_payload.get("outcome_id") != str(outcome.id)
            or outcome.team_id != task.team_id
            or outcome.subject_kind != "task"
            or outcome.subject_id != task.id
            or _parse_time(outcome.observed_at) != _parse_time(task.completed_at)
        ):
            raise KnowledgeHistoryError("knowledge_history_operator_terminal_invalid")


def _review_event_task_is_valid(
    session: Session, event: Event, payload: dict[str, Any]
) -> tuple[Task, datetime]:
    task = session.get(Task, event.task_id)
    if (
        task is None
        or task.task_type != "review_knowledge"
        or task.team_id is None
        or task.status != "done"
        or task.completed_at is None
        or task.attempt_count < 1
        or task.allowed_writes != ["KnowledgeItem"]
        or task.objective_id is not None
        or task.plan_id is not None
        or task.plan_action_id is not None
        or not isinstance(task.budget, dict)
        or task.budget.get("max_tool_calls") != 0
        or task.budget.get("max_cost_usd") != 0
        or isinstance(task.budget.get("deadline_seconds"), bool)
        or not isinstance(task.budget.get("deadline_seconds"), int)
        or task.budget["deadline_seconds"] < 1
    ):
        raise KnowledgeHistoryError("knowledge_review_task_provenance_invalid")

    reviewed_at = _parse_time(payload.get("reviewed_at"))
    if (
        payload.get("task_id") != str(task.id)
        or payload.get("team_id") != str(task.team_id)
        or payload.get("attempt_count") != task.attempt_count
        or _parse_time(event.created_at) != reviewed_at
        or _parse_time(task.completed_at) != reviewed_at
    ):
        raise KnowledgeHistoryError("knowledge_review_event_task_mismatch")

    start_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "task_started",
                Event.payload["attempt_count"].as_integer() == task.attempt_count,
            )
        )
    )
    if (
        len(start_events) != 1
        or start_events[0].payload
        != {
            "from_status": "pending",
            "to_status": "running",
            "attempt_count": task.attempt_count,
        }
    ):
        raise KnowledgeHistoryError("knowledge_review_task_start_invalid")

    terminal_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "task_completed",
            )
        )
    )
    outcomes = list(
        session.scalars(
            select(Outcome).where(
                Outcome.recorded_by_task_id == task.id,
                Outcome.outcome_type == "task_execution",
            )
        )
    )
    if (
        len(terminal_events) != 1
        or len(outcomes) != 1
        or terminal_events[0].payload.get("to_status") != "done"
        or terminal_events[0].payload.get("result_category")
        != "success_knowledge_reviewed"
        or terminal_events[0].payload.get("outcome_id") != str(outcomes[0].id)
        or outcomes[0].team_id != task.team_id
        or outcomes[0].subject_kind != "task"
        or outcomes[0].subject_id != task.id
        or _parse_time(outcomes[0].observed_at) != reviewed_at
    ):
        raise KnowledgeHistoryError("knowledge_review_task_terminal_invalid")

    review_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "knowledge_items_reviewed",
            )
        )
    )
    if len(review_events) != 1 or review_events[0].id != event.id:
        raise KnowledgeHistoryError("knowledge_review_event_duplicate_or_missing")
    return task, reviewed_at


@dataclass(frozen=True)
class _ReviewEntry:
    item_id: UUID
    version: int
    review_after: datetime
    origin_learning_change_id: UUID
    current_learning_change_id: UUID | None
    reviewed_at: datetime
    event_id: UUID


def _load_review_entries(
    session: Session, team_id: UUID, item_id: UUID
) -> tuple[_ReviewEntry, ...]:
    events = list(
        session.scalars(
            select(Event)
            .join(Task, Task.id == Event.task_id)
            .where(
                Event.type == "knowledge_items_reviewed",
                Task.team_id == team_id,
            )
        )
    )
    result: list[_ReviewEntry] = []
    for event in events:
        payload = event.payload
        if not isinstance(payload, dict) or payload.get("schema_version") not in {1, 2}:
            raise KnowledgeHistoryError("knowledge_review_event_schema_invalid")
        task, reviewed_at = _review_event_task_is_valid(session, event, payload)
        entries = payload.get("items")
        if not isinstance(entries, list):
            raise KnowledgeHistoryError("knowledge_review_event_items_invalid")
        seen: set[UUID] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise KnowledgeHistoryError("knowledge_review_event_entry_invalid")
            expected_keys = (
                {
                    "knowledge_item_id",
                    "version",
                    "review_after",
                    "origin_learning_change_id",
                }
                if payload["schema_version"] == 1
                else {
                    "knowledge_item_id",
                    "version",
                    "review_after",
                    "origin_learning_change_id",
                    "current_learning_change_id",
                }
            )
            if set(entry) != expected_keys:
                raise KnowledgeHistoryError("knowledge_review_event_entry_shape_invalid")
            entry_item_id = _parse_uuid(
                entry.get("knowledge_item_id"),
                "knowledge_review_event_item_id_invalid",
            )
            if entry_item_id in seen:
                raise KnowledgeHistoryError("knowledge_review_event_duplicate_item")
            seen.add(entry_item_id)
            if entry_item_id != item_id:
                continue
            version = entry.get("version")
            if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                raise KnowledgeHistoryError("knowledge_review_event_version_invalid")
            origin_id = _parse_uuid(
                entry.get("origin_learning_change_id"),
                "knowledge_review_event_origin_invalid",
            )
            current_id = (
                _parse_uuid(
                    entry.get("current_learning_change_id"),
                    "knowledge_review_event_current_pointer_invalid",
                )
                if payload["schema_version"] == 2
                else None
            )
            review_after = _parse_time(entry.get("review_after"))
            if review_after > reviewed_at:
                raise KnowledgeHistoryError("knowledge_review_event_not_due")
            if task.team_id != team_id:
                raise KnowledgeHistoryError("knowledge_review_event_cross_team")
            result.append(
                _ReviewEntry(
                    item_id=entry_item_id,
                    version=version,
                    review_after=review_after,
                    origin_learning_change_id=origin_id,
                    current_learning_change_id=current_id,
                    reviewed_at=reviewed_at,
                    event_id=event.id,
                )
            )
    return tuple(result)


def _state_matches_review_entry(
    state: dict[str, Any], entry: _ReviewEntry
) -> bool:
    return (
        state["id"] == str(entry.item_id)
        and state["version"] == entry.version
        and state["review_after"] == _timestamp_text(entry.review_after)
        and state["origin_learning_change_id"]
        == str(entry.origin_learning_change_id)
        and state["status"] == "active"
    )


def _same_semantic_content(
    left: dict[str, Any], right: dict[str, Any]
) -> bool:
    return all(left[key] == right[key] for key in _SEMANTIC_KEYS)


def _validate_transition(
    operation: str, previous: dict[str, Any], committed: dict[str, Any]
) -> None:
    if operation not in _LIFECYCLE_OPERATIONS:
        raise KnowledgeHistoryError("knowledge_history_operation_unsupported")
    if (
        previous["id"] != committed["id"]
        or previous["team_id"] != committed["team_id"]
        or previous["origin_learning_change_id"]
        != committed["origin_learning_change_id"]
        or previous["supersedes_item_id"] != committed["supersedes_item_id"]
    ):
        raise KnowledgeHistoryError("knowledge_history_identity_changed")

    if operation == "revise":
        if (
            committed["version"] != previous["version"] + 1
            or committed["status"] != previous["status"]
            or committed["last_validated_at"] is not None
            or _same_semantic_content(previous, committed) and
            previous["review_after"] == committed["review_after"]
        ):
            raise KnowledgeHistoryError("knowledge_history_revise_transition_invalid")
    elif operation == "revalidate":
        if (
            previous["status"] != "needs_review"
            or committed["status"] != "active"
            or committed["version"] != previous["version"]
            or not _same_semantic_content(previous, committed)
            or committed["last_validated_at"] is None
            or committed["superseded_by_id"] != previous["superseded_by_id"]
        ):
            raise KnowledgeHistoryError("knowledge_history_revalidate_transition_invalid")
    elif operation == "supersede":
        if (
            previous["status"] not in {"active", "needs_review"}
            or committed["status"] != "retired"
            or committed["version"] != previous["version"]
            or not _same_semantic_content(previous, committed)
            or previous["superseded_by_id"] is not None
            or committed["superseded_by_id"] is None
        ):
            raise KnowledgeHistoryError("knowledge_history_supersede_transition_invalid")
    elif operation == "retire":
        if (
            previous["status"] not in {"active", "needs_review"}
            or committed["status"] != "retired"
            or committed["version"] != previous["version"]
            or not _same_semantic_content(previous, committed)
            or committed["superseded_by_id"] != previous["superseded_by_id"]
        ):
            raise KnowledgeHistoryError("knowledge_history_retire_transition_invalid")

    if operation != "revalidate" and (
        operation not in {"revise"}
        and committed["last_validated_at"] != previous["last_validated_at"]
    ):
        raise KnowledgeHistoryError("knowledge_history_validation_date_mutated")


def _validate_supersession_references(
    session: Session, item: KnowledgeItem, state: dict[str, Any]
) -> None:
    predecessor_id = state["supersedes_item_id"]
    successor_id = state["superseded_by_id"]
    if predecessor_id is not None:
        predecessor = session.get(KnowledgeItem, UUID(predecessor_id))
        if predecessor is None or predecessor.team_id != item.team_id:
            raise KnowledgeHistoryError("knowledge_history_predecessor_invalid")
        if predecessor.id == item.id:
            raise KnowledgeHistoryError("knowledge_history_supersession_cycle")
    if successor_id is not None:
        successor = session.get(KnowledgeItem, UUID(successor_id))
        if (
            successor is None
            or successor.team_id != item.team_id
            or successor.supersedes_item_id != item.id
        ):
            raise KnowledgeHistoryError("knowledge_history_successor_not_reciprocal")

    seen: set[UUID] = {item.id}
    cursor = item
    while cursor.supersedes_item_id is not None:
        predecessor_id_value = cursor.supersedes_item_id
        if predecessor_id_value in seen:
            raise KnowledgeHistoryError("knowledge_history_supersession_cycle")
        seen.add(predecessor_id_value)
        cursor = session.get(KnowledgeItem, predecessor_id_value)
        if cursor is None or cursor.team_id != item.team_id:
            raise KnowledgeHistoryError("knowledge_history_predecessor_invalid")


def reconstruct_knowledge_item_history(
    session: Session, item: KnowledgeItem
) -> KnowledgeItemHistory:
    """Reconstruct the unique accepted pointer chain plus verified D7 overlays."""
    root_id = item.origin_learning_change_id
    root = session.get(LearningChange, root_id)
    if (
        root is None
        or root.team_id != item.team_id
        or root.target_kind != "knowledge_item"
        or root.target_id is not None
        or root.operation != "create"
        or root.status != "accepted"
        or root.committed_by_task_id is None
        or root.committed_at is None
    ):
        raise KnowledgeHistoryError("knowledge_history_root_invalid")

    try:
        root_decoded = decode_knowledge_item_snapshot(
            root.committed_state, root_learning_change_id=root.id
        )
    except KnowledgeHistoryError:
        raise
    root_state = root_decoded.state
    _validate_learning_change_provenance(session, root, root_state)
    if (
        root_state["id"] != str(item.id)
        or root_state["team_id"] != str(item.team_id)
        or root_state["origin_learning_change_id"] != str(root.id)
        or root_state["current_learning_change_id"] != str(root.id)
        or root_state["version"] != 1
    ):
        raise KnowledgeHistoryError("knowledge_history_root_snapshot_mismatch")

    changes = list(
        session.scalars(
            select(LearningChange).where(
                LearningChange.team_id == item.team_id,
                LearningChange.target_kind == "knowledge_item",
                LearningChange.status == "accepted",
            )
        )
    )
    by_id: dict[UUID, LearningChange] = {root.id: root}
    for change in changes:
        if change.id == root.id:
            continue
        if change.target_id != item.id:
            # A create root is identified by the immutable origin pointer.
            # Another accepted create snapshot naming this item is a duplicate root.
            try:
                candidate_state = decode_knowledge_item_snapshot(
                    change.committed_state, root_learning_change_id=change.id
                ).state
            except KnowledgeHistoryError:
                candidate_state = None
            if (
                change.operation == "create"
                and candidate_state is not None
                and candidate_state["id"] == str(item.id)
            ):
                raise KnowledgeHistoryError("knowledge_history_duplicate_root")
            continue
        if change.operation not in _LIFECYCLE_OPERATIONS:
            raise KnowledgeHistoryError("knowledge_history_operation_unsupported")
        if change.committed_by_task_id is None or change.committed_at is None:
            raise KnowledgeHistoryError("knowledge_history_commit_provenance_missing")
        by_id[change.id] = change

    decoded_commits: dict[UUID, dict[str, Any]] = {root.id: root_state}
    decoded_previous: dict[UUID, dict[str, Any]] = {}
    parent_by_child: dict[UUID, UUID] = {}
    for change_id, change in by_id.items():
        if change_id == root.id:
            continue
        try:
            previous = decode_knowledge_item_snapshot(
                change.previous_state, root_learning_change_id=root.id
            ).state
            committed = decode_knowledge_item_snapshot(
                change.committed_state, root_learning_change_id=root.id
            ).state
        except KnowledgeHistoryError:
            raise
        if (
            previous["id"] != str(item.id)
            or previous["team_id"] != str(item.team_id)
            or committed["id"] != str(item.id)
            or committed["team_id"] != str(item.team_id)
            or committed["origin_learning_change_id"] != str(root.id)
            or committed["current_learning_change_id"] != str(change.id)
        ):
            raise KnowledgeHistoryError("knowledge_history_snapshot_identity_mismatch")
        parent_id = _parse_uuid(
            previous["current_learning_change_id"],
            "knowledge_history_parent_pointer_invalid",
        )
        if parent_id not in by_id:
            raise KnowledgeHistoryError("knowledge_history_missing_parent")
        parent_by_child[change_id] = parent_id
        decoded_previous[change_id] = previous
        decoded_commits[change_id] = committed
        _validate_learning_change_provenance(session, change, committed)
        _validate_transition(change.operation, previous, committed)

    children: dict[UUID, list[UUID]] = {}
    for child_id, parent_id in parent_by_child.items():
        children.setdefault(parent_id, []).append(child_id)
    if any(len(child_ids) > 1 for child_ids in children.values()):
        raise KnowledgeHistoryError("knowledge_history_fork_detected")

    review_entries = _load_review_entries(session, item.team_id, item.id)
    reviews_by_pointer: dict[UUID, _ReviewEntry] = {}
    for entry in review_entries:
        candidates: list[UUID] = []
        for pointer_id, state in decoded_commits.items():
            if entry.current_learning_change_id is not None:
                if pointer_id != entry.current_learning_change_id:
                    continue
            if _state_matches_review_entry(state, entry):
                candidates.append(pointer_id)
        if len(candidates) != 1:
            reason = (
                "knowledge_history_legacy_review_ambiguous"
                if entry.current_learning_change_id is None and len(candidates) > 1
                else "knowledge_history_review_unplaceable"
            )
            raise KnowledgeHistoryError(reason)
        pointer_id = candidates[0]
        if pointer_id in reviews_by_pointer:
            raise KnowledgeHistoryError("knowledge_history_duplicate_review_overlay")
        node = by_id[pointer_id]
        committed_at = node.committed_at
        if committed_at is None or entry.reviewed_at < _parse_time(committed_at):
            raise KnowledgeHistoryError("knowledge_history_review_before_commit")
        reviews_by_pointer[pointer_id] = entry

    effective_states: dict[UUID, dict[str, Any]] = {}
    for pointer_id, base_state in decoded_commits.items():
        effective = dict(base_state)
        if pointer_id in reviews_by_pointer:
            effective["status"] = "needs_review"
        effective_states[pointer_id] = effective

    # The pointer graph, not timestamps, defines the order. Timestamps below
    # are used only to reject impossible provenance after a node is identified.
    pointer_order: list[UUID] = []
    cursor = root.id
    visited: set[UUID] = set()
    while True:
        if cursor in visited:
            raise KnowledgeHistoryError("knowledge_history_cycle_detected")
        visited.add(cursor)
        pointer_order.append(cursor)
        next_ids = children.get(cursor, [])
        if not next_ids:
            break
        child_id = next_ids[0]
        child = by_id[child_id]
        if decoded_previous[child_id] != effective_states[cursor]:
            raise KnowledgeHistoryError("knowledge_history_previous_state_mismatch")
        parent_commit_time = _parse_time(by_id[cursor].committed_at)
        child_commit_time = _parse_time(child.committed_at)
        if child_commit_time < parent_commit_time:
            raise KnowledgeHistoryError("knowledge_history_commit_time_regressed")
        review = reviews_by_pointer.get(cursor)
        if review is not None and review.reviewed_at > child_commit_time:
            raise KnowledgeHistoryError("knowledge_history_review_after_child_commit")
        cursor = child_id

    if visited != set(by_id):
        raise KnowledgeHistoryError("knowledge_history_disconnected_change")
    if item.current_learning_change_id != pointer_order[-1]:
        raise KnowledgeHistoryError("knowledge_history_current_pointer_mismatch")

    final_state = effective_states[pointer_order[-1]]
    if final_state != knowledge_item_snapshot_state(item):
        raise KnowledgeHistoryError("knowledge_history_final_state_mismatch")

    _validate_supersession_references(session, item, final_state)
    reconstructed = set(root_decoded.reconstructed_legacy_fields)
    for pointer_id in pointer_order[1:]:
        change = by_id[pointer_id]
        previous_decoded = decode_knowledge_item_snapshot(
            change.previous_state, root_learning_change_id=root.id
        )
        committed_decoded = decode_knowledge_item_snapshot(
            change.committed_state, root_learning_change_id=root.id
        )
        reconstructed.update(previous_decoded.reconstructed_legacy_fields)
        reconstructed.update(committed_decoded.reconstructed_legacy_fields)
    return KnowledgeItemHistory(
        knowledge_item_id=item.id,
        team_id=item.team_id,
        pointer_order=tuple(pointer_order),
        states_by_pointer=effective_states,
        current_state=final_state,
        reconstructed_legacy_fields=tuple(sorted(reconstructed)),
    )
