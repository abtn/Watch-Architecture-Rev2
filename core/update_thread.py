"""Immutable request contract for the RW-3 update_thread Task."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Event, Task, TeamPolicy

TASK_TYPE = "update_thread"
REQUEST_EVENT_TYPE = "update_thread_requested"
ALLOWED_WRITES = ["EvidenceLink", "Hypothesis", "ConfidenceChange"]
MAX_ATTEMPTS = 3
TASK_BUDGET = {
    "max_tool_calls": 0,
    "max_cost_usd": 0.02,
    "deadline_seconds": 45,
}
_TASK_ID_NAMESPACE = UUID("9a0d34bd-6e51-4d87-8d87-58a1d3c5a70f")
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class UpdateThreadTaskError(ValueError):
    """The immutable update_thread Task request is invalid or inconsistent."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class UpdateThreadTaskRequest:
    """Host request; the target Team is always derived from the Thread."""

    thread_id: UUID
    idempotency_key: UUID


@dataclass(frozen=True)
class UpdateThreadTaskResult:
    task_id: UUID
    team_id: UUID
    status: str
    replayed: bool


@dataclass(frozen=True)
class UpdateThreadTaskEnvelope:
    task_id: UUID
    team_id: UUID
    thread_id: UUID
    policy_version: int
    requested_by_operator_id: str
    idempotency_key_hash: str
    request_fingerprint: str


def task_id_for_request(team_id: UUID, idempotency_key: UUID) -> UUID:
    """Return the stable Team-scoped identity for one host request key."""
    return uuid5(
        _TASK_ID_NAMESPACE,
        f"{team_id}:{TASK_TYPE}:{idempotency_key}",
    )


def _canonical_json(value: dict[str, object]) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _sha256_json(value: dict[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def build_request_event_payload(
    *,
    task_id: UUID,
    team_id: UUID,
    thread_id: UUID,
    policy_version: int,
    requested_by_operator_id: str,
    idempotency_key: UUID,
) -> dict[str, object]:
    """Build the exact versioned request Event; never persist the raw key."""
    idempotency_key_hash = (
        "sha256:" + hashlib.sha256(str(idempotency_key).encode("ascii")).hexdigest()
    )
    payload: dict[str, object] = {
        "schema_version": 1,
        "task_id": str(task_id),
        "team_id": str(team_id),
        "thread_id": str(thread_id),
        "policy_version": policy_version,
        "requested_by_operator_id": requested_by_operator_id,
        "idempotency_key_hash": idempotency_key_hash,
    }
    fingerprint_basis = {
        "domain": "watch.rw3.update-thread-request.v1",
        **payload,
    }
    payload["request_fingerprint"] = _sha256_json(fingerprint_basis)
    return payload


def validate_update_thread_policy(policy: TeamPolicy, team_id: UUID) -> None:
    """Validate the supported immutable policy pin used by this Task."""
    if (
        policy.team_id != team_id
        or isinstance(policy.version, bool)
        or not isinstance(policy.version, int)
        or policy.version < 1
        or isinstance(policy.schema_version, bool)
        or policy.schema_version not in {1, 2}
        or not isinstance(policy.rules, dict)
    ):
        raise UpdateThreadTaskError("update_thread_policy_invalid")


def validate_update_thread_task_request(
    session: Session, task: Task
) -> UpdateThreadTaskEnvelope:
    """Validate the Task shape and its one immutable request Event."""
    if (
        task.task_type != TASK_TYPE
        or task.status not in {"pending", "running", "done", "failed"}
        or task.objective_id is not None
        or task.plan_id is not None
        or task.plan_action_id is not None
        or task.allowed_writes != ALLOWED_WRITES
        or task.budget != TASK_BUDGET
        or task.max_attempts != MAX_ATTEMPTS
        or isinstance(task.policy_version, bool)
        or not isinstance(task.policy_version, int)
        or task.policy_version < 1
        or isinstance(task.attempt_count, bool)
        or not isinstance(task.attempt_count, int)
        or not 0 <= task.attempt_count <= MAX_ATTEMPTS
        or (task.status in {"running", "done", "failed"} and task.attempt_count < 1)
        or (task.completed_at is not None and task.status != "done")
    ):
        raise UpdateThreadTaskError("update_thread_task_shape_invalid")

    events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
    )
    if len(events) != 1 or not isinstance(events[0].payload, dict):
        raise UpdateThreadTaskError("update_thread_request_event_invalid")

    payload = events[0].payload
    expected_keys = {
        "schema_version",
        "task_id",
        "team_id",
        "thread_id",
        "policy_version",
        "requested_by_operator_id",
        "idempotency_key_hash",
        "request_fingerprint",
    }
    if (
        set(payload) != expected_keys
        or isinstance(payload.get("schema_version"), bool)
        or payload.get("schema_version") != 1
        or payload.get("task_id") != str(task.id)
        or payload.get("team_id") != str(task.team_id)
        or payload.get("policy_version") != task.policy_version
        or not isinstance(payload.get("thread_id"), str)
        or not isinstance(payload.get("requested_by_operator_id"), str)
        or not payload["requested_by_operator_id"]
        or len(payload["requested_by_operator_id"]) > 255
        or not isinstance(payload.get("idempotency_key_hash"), str)
        or not _HASH_PATTERN.fullmatch(payload["idempotency_key_hash"])
        or not isinstance(payload.get("request_fingerprint"), str)
        or not _HASH_PATTERN.fullmatch(payload["request_fingerprint"])
    ):
        raise UpdateThreadTaskError("update_thread_request_event_invalid")

    try:
        thread_id = UUID(payload["thread_id"])
    except (TypeError, ValueError) as error:
        raise UpdateThreadTaskError("update_thread_request_thread_invalid") from error
    if str(thread_id) != payload["thread_id"]:
        raise UpdateThreadTaskError("update_thread_request_thread_invalid")

    fingerprint_basis = {
        "domain": "watch.rw3.update-thread-request.v1",
        **{key: payload[key] for key in expected_keys if key != "request_fingerprint"},
    }
    if _sha256_json(fingerprint_basis) != payload["request_fingerprint"]:
        raise UpdateThreadTaskError("update_thread_request_fingerprint_invalid")

    return UpdateThreadTaskEnvelope(
        task_id=task.id,
        team_id=task.team_id,
        thread_id=thread_id,
        policy_version=task.policy_version,
        requested_by_operator_id=payload["requested_by_operator_id"],
        idempotency_key_hash=payload["idempotency_key_hash"],
        request_fingerprint=payload["request_fingerprint"],
    )


def load_pinned_policy(
    session: Session, team_id: UUID, policy_version: int
) -> TeamPolicy:
    policy = session.scalar(
        select(TeamPolicy).where(
            TeamPolicy.team_id == team_id,
            TeamPolicy.version == policy_version,
        )
    )
    if policy is None:
        raise UpdateThreadTaskError("update_thread_policy_missing")
    validate_update_thread_policy(policy, team_id)
    return policy
