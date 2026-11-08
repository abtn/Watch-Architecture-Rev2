"""Evidence-bound R7-B revalidation assessment contracts and persistence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Mapping
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.experience_distiller import ExperienceDistiller, ExperienceDistillerError
from core.learning_history import (
    KNOWLEDGE_CONTENT_HASH_SCHEME,
    KnowledgeHistoryError,
    decode_state_snapshot,
    knowledge_item_content_hash,
    knowledge_item_state,
    reconstruct_knowledge_item_history,
)
from core.models import (
    Event,
    KnowledgeItem,
    KnowledgeRevalidationAssessment,
    LearningChange,
    Outcome,
    Task,
    Team,
)
from core.snapshot_store import SnapshotStore
from core.state_assessment import _canonical_json, _timestamp

TASK_TYPE = "assess_knowledge_revalidation"
REQUEST_EVENT_TYPE = "knowledge_revalidation_assessment_task_requested"
RECORDED_EVENT_TYPE = "knowledge_revalidation_assessment_recorded"
ALLOWED_WRITES = ["KnowledgeRevalidationAssessment"]
TASK_MAX_ATTEMPTS = 3
TASK_BUDGET = {
    "max_tool_calls": 0,
    "max_cost_usd": 0.0,
    "deadline_seconds": 30,
}
ASSESSMENT_VERSION = 1
TASK_ID_NAMESPACE = uuid5(
    NAMESPACE_URL, "watch.r7b.knowledge-revalidation-task.v1"
)
PROPOSED_STATE_HASH_DOMAIN = "watch.r7b.learning-change-proposed-state.v1"
ASSESSMENT_HASH_DOMAIN = "watch.r7b.knowledge-revalidation-assessment.v1"
FRESHNESS_DISPOSITIONS = frozenset(
    {"current", "stale", "insufficient", "conflicting", "unassessable"}
)
ASSESSMENT_RESULTS = frozenset({"supported", "not_supported", "indeterminate"})
CONTENT_FIELDS = (
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
_FINDING_CODES = frozenset(
    {
        "supports_revalidation",
        "contradicts_revalidation",
        "temporally_stale",
        "insufficient_coverage",
        "unresolved_conflict",
        "new_observation_required",
        "freshness_unassessable",
    }
)
_REVALIDATION_FAILURES = frozenset(
    {
        "knowledge_revalidation_target_stale",
        "knowledge_revalidation_evidence_stale",
        "knowledge_revalidation_proposal_invalid",
        "knowledge_revalidation_task_request_mismatch",
    }
)


class KnowledgeRevalidationAssessmentError(ValueError):
    """A revalidation proposal, evidence pack, or assessment is invalid."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class KnowledgeRevalidationFinding(BaseModel):
    """Untrusted finding whose references must resolve into the rebuilt pack."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Literal[
        "supports_revalidation",
        "contradicts_revalidation",
        "temporally_stale",
        "insufficient_coverage",
        "unresolved_conflict",
        "new_observation_required",
        "freshness_unassessable",
    ]
    summary: str = Field(min_length=1, max_length=1200)
    evidence_refs: list[str] = Field(min_length=1, max_length=256)

    @field_validator("summary")
    @classmethod
    def nonblank_summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("knowledge_revalidation_finding_summary_required")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def unique_references(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() if isinstance(value, str) else value for value in values]
        if any(not isinstance(value, str) or not value for value in normalized):
            raise ValueError("knowledge_revalidation_evidence_reference_required")
        if len(set(normalized)) != len(normalized):
            raise ValueError("knowledge_revalidation_duplicate_evidence_reference")
        return normalized


class KnowledgeRevalidationAssessmentDraft(BaseModel):
    """Untrusted evaluator output; canonical bindings are application-owned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    freshness_disposition: Literal[
        "current", "stale", "insufficient", "conflicting", "unassessable"
    ]
    findings: list[KnowledgeRevalidationFinding] = Field(min_length=1, max_length=256)


@dataclass(frozen=True)
class RevalidationTaskContext:
    task: Task
    learning_change: LearningChange
    target: KnowledgeItem
    target_state: dict[str, Any]
    target_state_hash: str
    target_content_hash: str
    proposal_hash: str
    proposed_state_hash: str
    evidence_basis_hash: str
    pack: Any
    request_event: Event
    request_payload: dict[str, Any]


@dataclass(frozen=True)
class KnowledgeRevalidationAssessmentResult:
    assessment_id: UUID
    status: str
    assessment_payload_hash: str
    recorded_at: datetime
    replayed: bool = False


def _sha256_json(value: Any) -> str:
    try:
        encoded = _canonical_json(value).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_json_not_canonicalizable"
        ) from error
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _domain_hash(domain: str, value: Any) -> str:
    try:
        encoded = _canonical_json(value).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_json_not_canonicalizable"
        ) from error
    framed = domain.encode("utf-8") + b"\x00" + encoded
    return "sha256:" + hashlib.sha256(framed).hexdigest()


def _normalize_json(value: Any) -> Any:
    """Normalize JSON-bound values without introducing float semantics."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise KnowledgeRevalidationAssessmentError(
                "knowledge_revalidation_decimal_not_finite"
            )
        return format(value, "f")
    if isinstance(value, datetime):
        try:
            return _timestamp(value)
        except ValueError as error:
            raise KnowledgeRevalidationAssessmentError(
                "knowledge_revalidation_timestamp_not_aware"
            ) from error
    if isinstance(value, float):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_json_float_forbidden"
        )
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json(item) for item in value]
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise KnowledgeRevalidationAssessmentError(
                "knowledge_revalidation_json_key_invalid"
            )
        return {key: _normalize_json(item) for key, item in value.items()}
    raise KnowledgeRevalidationAssessmentError(
        "knowledge_revalidation_json_value_invalid"
    )


def _canonical_uuid(value: object, reason: str) -> UUID:
    if not isinstance(value, str):
        raise KnowledgeRevalidationAssessmentError(reason)
    try:
        parsed = UUID(value)
    except (TypeError, ValueError) as error:
        raise KnowledgeRevalidationAssessmentError(reason) from error
    if str(parsed) != value:
        raise KnowledgeRevalidationAssessmentError(reason)
    return parsed


def _require_sha256(value: object, reason: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in value[7:])
    ):
        raise KnowledgeRevalidationAssessmentError(reason)
    return value


def _task_id(team_id: UUID, learning_change_id: UUID) -> UUID:
    return uuid5(TASK_ID_NAMESPACE, f"{team_id}:{learning_change_id}:{TASK_TYPE}")


def _idempotency_key(team_id: UUID, learning_change_id: UUID) -> str:
    identity = {
        "team_id": str(team_id),
        "learning_change_id": str(learning_change_id),
        "task_type": TASK_TYPE,
        "assessment_version": ASSESSMENT_VERSION,
    }
    return "r7b-revalidation-v1:" + _sha256_json(identity).removeprefix("sha256:")


def _target_state_from_proposal(
    learning_change: LearningChange,
    target: KnowledgeItem,
    *,
    require_current: bool,
) -> tuple[dict[str, Any], str, str]:
    payload = learning_change.previous_state
    if (
        not isinstance(payload, dict)
        or set(payload) != {"snapshot_version", "state", "snapshot_hash"}
        or not isinstance(payload.get("state"), dict)
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_previous_state_invalid"
        )
    raw_pointer = payload["state"].get("current_learning_change_id")
    pointer = _canonical_uuid(
        raw_pointer, "knowledge_revalidation_previous_pointer_invalid"
    )
    try:
        state, reconstructed = decode_state_snapshot(
            payload,
            learning_change_id=pointer,
            operation="revalidate",
            allow_legacy_root=False,
        )
    except KnowledgeHistoryError as error:
        raise KnowledgeRevalidationAssessmentError(
            f"knowledge_revalidation_previous_state_{error.reason}"
        ) from error
    if reconstructed:
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_previous_state_legacy"
        )
    if (
        state["id"] != str(target.id)
        or state["team_id"] != str(learning_change.team_id)
        or learning_change.target_id != target.id
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_target_identity_mismatch"
        )
    target_state_hash = _require_sha256(
        payload.get("snapshot_hash"),
        "knowledge_revalidation_target_state_hash_invalid",
    )
    content_state = {field: state[field] for field in CONTENT_FIELDS}
    target_content_hash = _domain_hash(
        KNOWLEDGE_CONTENT_HASH_SCHEME, content_state
    )
    if require_current:
        try:
            live_state = knowledge_item_state(target)
            live_hash = knowledge_item_content_hash(target)
        except KnowledgeHistoryError as error:
            raise KnowledgeRevalidationAssessmentError(
                f"knowledge_revalidation_target_{error.reason}"
            ) from error
        if (
            live_state != state
            or live_hash != target_content_hash
            or target.version != state["version"]
            or target.current_learning_change_id != pointer
        ):
            raise KnowledgeRevalidationAssessmentError(
                "knowledge_revalidation_target_stale"
            )
    return state, target_state_hash, target_content_hash


def _build_canonical_pack(
    session: Session,
    snapshot_store: SnapshotStore,
    learning_change: LearningChange,
    source_task: Task,
) -> Any:
    basis = learning_change.evidence_basis
    if not isinstance(basis, list) or not basis:
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_evidence_basis_missing"
        )
    evaluation_ids: list[UUID] = []
    marker_states: list[bool] = []
    for item in basis:
        if not isinstance(item, dict):
            raise KnowledgeRevalidationAssessmentError(
                "knowledge_revalidation_evidence_basis_invalid"
            )
        evaluation_ids.append(
            _canonical_uuid(
                item.get("evaluation_id"),
                "knowledge_revalidation_evaluation_id_invalid",
            )
        )
        marker_states.append("schema_version" in item)
        if "schema_version" in item and item["schema_version"] not in {
            "r6f-experience-evidence-pack-v1",
            "r6g-experience-evidence-pack-v2",
        }:
            raise KnowledgeRevalidationAssessmentError(
                "knowledge_revalidation_evidence_schema_invalid"
            )
    if len(set(evaluation_ids)) != len(evaluation_ids):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_duplicate_evaluation"
        )
    if any(marker_states) and not all(marker_states):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_mixed_evidence_schema_markers"
        )
    team = session.get(Team, learning_change.team_id)
    if team is None or team.status != "active":
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_team_not_active"
        )
    try:
        pack = ExperienceDistiller(
            session.get_bind(), snapshot_store, provider=None
        )._build_pack(
            session,
            source_task,
            team,
            tuple(sorted(evaluation_ids)),
            allow_completed_task=True,
            include_version_marker=bool(marker_states and marker_states[0]),
        )
    except ExperienceDistillerError as error:
        raise KnowledgeRevalidationAssessmentError(error.reason) from error
    try:
        stored_basis = _normalize_json(basis)
        rebuilt_basis = _normalize_json(pack.evidence_basis)
    except KnowledgeRevalidationAssessmentError:
        raise
    if (
        _canonical_json(stored_basis) != _canonical_json(rebuilt_basis)
        or pack.basis_hash != learning_change.evidence_basis_hash
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_evidence_stale"
        )
    return pack


def _proposal_context(
    session: Session,
    snapshot_store: SnapshotStore,
    learning_change: LearningChange,
    *,
    require_current: bool,
) -> tuple[KnowledgeItem, Task, dict[str, Any], str, str, str, str, Any]:
    if (
        learning_change.operation != "revalidate"
        or learning_change.target_kind != "knowledge_item"
        or learning_change.target_id is None
        or learning_change.proposed_by_task_id is None
        or learning_change.status not in {"proposed", "accepted", "rejected"}
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_proposal_invalid"
        )
    proposal_hash = learning_change.proposed_state.get("proposal_hash")
    if not isinstance(proposal_hash, str):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_proposal_hash_invalid"
        )
    _require_sha256(
        proposal_hash, "knowledge_revalidation_proposal_hash_invalid"
    )
    evidence_basis_hash = _require_sha256(
        learning_change.evidence_basis_hash,
        "knowledge_revalidation_evidence_hash_invalid",
    )
    if learning_change.proposed_state.get("evidence_basis_hash") != evidence_basis_hash:
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_proposed_evidence_hash_mismatch"
        )
    try:
        proposed_state_hash = _domain_hash(
            PROPOSED_STATE_HASH_DOMAIN,
            _normalize_json(learning_change.proposed_state),
        )
    except KnowledgeRevalidationAssessmentError:
        raise
    source_task = session.get(Task, learning_change.proposed_by_task_id)
    if (
        source_task is None
        or source_task.team_id != learning_change.team_id
        or source_task.task_type != "propose_learning_change"
        or source_task.status != "done"
        or source_task.completed_at is None
        or source_task.allowed_writes != ["LearningChange"]
        or source_task.objective_id is not None
        or source_task.plan_id is not None
        or source_task.plan_action_id is not None
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_source_task_invalid"
        )
    proposal_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == source_task.id,
                Event.type == "learning_change_proposed",
            )
        )
    )
    terminal_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == source_task.id,
                Event.type == "task_completed",
            )
        )
    )
    source_outcomes = list(
        session.scalars(
            select(Outcome).where(
                Outcome.recorded_by_task_id == source_task.id,
                Outcome.outcome_type == "task_execution",
            )
        )
    )
    if (
        len(proposal_events) != 1
        or not isinstance(proposal_events[0].payload, dict)
        or len(terminal_events) != 1
        or not isinstance(terminal_events[0].payload, dict)
        or len(source_outcomes) != 1
        or terminal_events[0].payload.get("result_category")
        != "success_learning_change_proposed"
        or terminal_events[0].payload.get("learning_change_id")
        != str(learning_change.id)
        or terminal_events[0].payload.get("attempt_count") != source_task.attempt_count
        or terminal_events[0].payload.get("outcome_id") != str(source_outcomes[0].id)
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_source_terminal_invalid"
        )
    proposal_event = proposal_events[0].payload
    if (
        proposal_event.get("learning_change_id") != str(learning_change.id)
        or proposal_event.get("operation") != "revalidate"
        or proposal_event.get("proposal_hash") != proposal_hash
        or proposal_event.get("evidence_basis_hash") != evidence_basis_hash
        or proposal_event.get("attempt_count") != source_task.attempt_count
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_proposal_event_mismatch"
        )
    target = session.scalar(
        select(KnowledgeItem)
        .where(
            KnowledgeItem.id == learning_change.target_id,
            KnowledgeItem.team_id == learning_change.team_id,
        )
        .with_for_update()
        if require_current
        else select(KnowledgeItem).where(
            KnowledgeItem.id == learning_change.target_id,
            KnowledgeItem.team_id == learning_change.team_id,
        )
    )
    if target is None:
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_target_not_found"
        )
    target_state, target_state_hash, target_content_hash = (
        _target_state_from_proposal(
            learning_change, target, require_current=require_current
        )
    )
    if require_current:
        try:
            reconstruct_knowledge_item_history(session, target)
        except KnowledgeHistoryError as error:
            raise KnowledgeRevalidationAssessmentError(
                f"knowledge_revalidation_target_history_{error.reason}"
            ) from error
    pack = _build_canonical_pack(
        session, snapshot_store, learning_change, source_task
    )
    return (
        target,
        source_task,
        target_state,
        target_state_hash,
        target_content_hash,
        proposal_hash,
        proposed_state_hash,
        pack,
    )


def build_revalidation_task_request(
    session: Session,
    snapshot_store: SnapshotStore,
    learning_change: LearningChange,
    *,
    require_current: bool = True,
) -> tuple[UUID, dict[str, Any]]:
    (
        target,
        source_task,
        _,
        target_state_hash,
        target_content_hash,
        proposal_hash,
        proposed_state_hash,
        pack,
    ) = _proposal_context(
        session,
        snapshot_store,
        learning_change,
        require_current=require_current,
    )
    task_id = _task_id(learning_change.team_id, learning_change.id)
    idempotency_key = _idempotency_key(
        learning_change.team_id, learning_change.id
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "task_type": TASK_TYPE,
        "task_id": str(task_id),
        "team_id": str(learning_change.team_id),
        "learning_change_id": str(learning_change.id),
        "proposed_by_task_id": str(source_task.id),
        "knowledge_item_id": str(target.id),
        "current_learning_change_id": str(
            learning_change.previous_state["state"]["current_learning_change_id"]
        ),
        "target_content_version": int(learning_change.previous_state["state"]["version"]),
        "target_content_hash": target_content_hash,
        "target_content_hash_scheme": KNOWLEDGE_CONTENT_HASH_SCHEME,
        "target_state_hash": target_state_hash,
        "proposal_hash": proposal_hash,
        "proposed_state_hash": proposed_state_hash,
        "evidence_basis_hash": pack.basis_hash,
        "policy_version": source_task.policy_version,
        "idempotency_key": idempotency_key,
    }
    payload["request_hash"] = _sha256_json(payload)
    return task_id, payload


def validate_revalidation_task_request(
    session: Session,
    task: Task,
    snapshot_store: SnapshotStore,
    *,
    require_proposed: bool = True,
    require_current: bool = True,
) -> RevalidationTaskContext:
    if (
        task.task_type != TASK_TYPE
        or task.objective_id is not None
        or task.plan_id is not None
        or task.plan_action_id is not None
        or task.allowed_writes != ALLOWED_WRITES
        or task.budget != TASK_BUDGET
        or task.max_attempts != TASK_MAX_ATTEMPTS
        or task.attempt_count < 0
        or task.attempt_count > task.max_attempts
        or (
            task.status in {"running", "done", "failed"}
            and task.attempt_count < 1
        )
        or (task.completed_at is not None and task.status != "done")
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_task_shape_invalid"
        )
    events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
    )
    if len(events) != 1 or not isinstance(events[0].payload, dict):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_request_event_invalid"
        )
    payload = events[0].payload
    try:
        learning_change_id = _canonical_uuid(
            payload.get("learning_change_id"),
            "knowledge_revalidation_learning_change_id_invalid",
        )
    except KnowledgeRevalidationAssessmentError:
        raise
    change_query = select(LearningChange).where(
        LearningChange.id == learning_change_id,
        LearningChange.team_id == task.team_id,
    )
    if require_current:
        change_query = change_query.with_for_update()
    learning_change = session.scalar(change_query)
    if learning_change is None:
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_learning_change_missing"
        )
    if require_proposed and learning_change.status != "proposed":
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_learning_change_not_proposed"
        )
    if not require_proposed and learning_change.status not in {
        "proposed", "accepted", "rejected"
    }:
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_learning_change_status_invalid"
        )
    (
        target,
        source_task,
        target_state,
        target_state_hash,
        target_content_hash,
        proposal_hash,
        proposed_state_hash,
        pack,
    ) = _proposal_context(
        session,
        snapshot_store,
        learning_change,
        require_current=require_current,
    )
    expected_task_id = _task_id(task.team_id, learning_change.id)
    idempotency_key = _idempotency_key(task.team_id, learning_change.id)
    expected: dict[str, Any] = {
        "schema_version": 1,
        "task_type": TASK_TYPE,
        "task_id": str(expected_task_id),
        "team_id": str(learning_change.team_id),
        "learning_change_id": str(learning_change.id),
        "proposed_by_task_id": str(source_task.id),
        "knowledge_item_id": str(target.id),
        "current_learning_change_id": target_state["current_learning_change_id"],
        "target_content_version": target_state["version"],
        "target_content_hash": target_content_hash,
        "target_content_hash_scheme": KNOWLEDGE_CONTENT_HASH_SCHEME,
        "target_state_hash": target_state_hash,
        "proposal_hash": proposal_hash,
        "proposed_state_hash": proposed_state_hash,
        "evidence_basis_hash": pack.basis_hash,
        "policy_version": source_task.policy_version,
        "idempotency_key": idempotency_key,
    }
    expected["request_hash"] = _sha256_json(expected)
    if (
        task.id != expected_task_id
        or task.team_id != learning_change.team_id
        or task.policy_version != source_task.policy_version
        or payload != expected
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_task_request_mismatch"
        )
    return RevalidationTaskContext(
        task=task,
        learning_change=learning_change,
        target=target,
        target_state=target_state,
        target_state_hash=target_state_hash,
        target_content_hash=target_content_hash,
        proposal_hash=proposal_hash,
        proposed_state_hash=proposed_state_hash,
        evidence_basis_hash=pack.basis_hash,
        pack=pack,
        request_event=events[0],
        request_payload=payload,
    )


def derive_freshness_disposition(
    findings: list[KnowledgeRevalidationFinding],
) -> str:
    codes = {finding.code for finding in findings}
    has_support = "supports_revalidation" in codes
    has_contradiction = "contradicts_revalidation" in codes
    if "unresolved_conflict" in codes or (has_support and has_contradiction):
        return "conflicting"
    if {"temporally_stale", "new_observation_required"} & codes:
        return "stale"
    if "insufficient_coverage" in codes:
        return "insufficient"
    if "freshness_unassessable" in codes:
        return "unassessable"
    return "current"


def derive_assessment_result(
    freshness_disposition: str,
    findings: list[KnowledgeRevalidationFinding],
) -> str:
    if freshness_disposition != "current":
        return "indeterminate"
    codes = {finding.code for finding in findings}
    if "supports_revalidation" in codes and "contradicts_revalidation" not in codes:
        return "supported"
    if "contradicts_revalidation" in codes and "supports_revalidation" not in codes:
        return "not_supported"
    return "indeterminate"


def validate_revalidation_draft(
    draft: KnowledgeRevalidationAssessmentDraft,
    pack: Any,
) -> tuple[list[dict[str, Any]], str, str]:
    allowed = set(pack.reference_ids)
    seen: set[str] = set()
    for finding in draft.findings:
        if not set(finding.evidence_refs).issubset(allowed):
            raise KnowledgeRevalidationAssessmentError(
                "knowledge_revalidation_finding_reference_not_in_basis"
            )
        seen.update(finding.evidence_refs)
    if not set(pack.evidence_link_reference_ids).issubset(seen):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_evidence_link_omitted"
        )
    contrary_findings = {
        reference
        for finding in draft.findings
        if finding.code in {"contradicts_revalidation", "unresolved_conflict"}
        for reference in finding.evidence_refs
    }
    if not set(pack.contrary_reference_ids).issubset(contrary_findings):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_contrary_evidence_omitted"
        )
    derived_freshness = derive_freshness_disposition(draft.findings)
    if draft.freshness_disposition != derived_freshness:
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_freshness_disposition_mismatch"
        )
    result = derive_assessment_result(derived_freshness, draft.findings)
    findings = [finding.model_dump(mode="json") for finding in draft.findings]
    return findings, derived_freshness, result


def assessment_record_payload(assessment: KnowledgeRevalidationAssessment) -> dict[str, Any]:
    return {
        "assessment_version": assessment.assessment_version,
        "id": str(assessment.id),
        "team_id": str(assessment.team_id),
        "task_id": str(assessment.task_id),
        "task_attempt": assessment.task_attempt,
        "learning_change_id": str(assessment.learning_change_id),
        "operation": assessment.operation,
        "knowledge_item_id": str(assessment.knowledge_item_id),
        "current_learning_change_id": str(assessment.current_learning_change_id),
        "target_content_version": assessment.target_content_version,
        "target_content_hash": assessment.target_content_hash,
        "target_content_hash_scheme": assessment.target_content_hash_scheme,
        "target_state_hash": assessment.target_state_hash,
        "proposal_hash": assessment.proposal_hash,
        "proposed_state_hash": assessment.proposed_state_hash,
        "evidence_basis_hash": assessment.evidence_basis_hash,
        "evidence_refs": _normalize_json(assessment.evidence_refs),
        "evaluator_identity": assessment.evaluator_identity,
        "evaluator_revision": assessment.evaluator_revision,
        "freshness_disposition": assessment.freshness_disposition,
        "findings": _normalize_json(assessment.findings),
        "assessment_result": assessment.assessment_result,
        "idempotency_key": assessment.idempotency_key,
        "request_hash": assessment.request_hash,
        "request_event_id": str(assessment.request_event_id),
        "request_event_payload_hash": assessment.request_event_payload_hash,
        "recorded_event_id": str(assessment.recorded_event_id),
        "recorded_at": _timestamp(assessment.recorded_at),
    }


def assessment_payload_hash(assessment: KnowledgeRevalidationAssessment) -> str:
    return _domain_hash(ASSESSMENT_HASH_DOMAIN, assessment_record_payload(assessment))


def recorded_assessment_event_payload(
    assessment: KnowledgeRevalidationAssessment,
) -> dict[str, Any]:
    return {
        "assessment_id": str(assessment.id),
        "team_id": str(assessment.team_id),
        "task_id": str(assessment.task_id),
        "task_attempt": assessment.task_attempt,
        "learning_change_id": str(assessment.learning_change_id),
        "knowledge_item_id": str(assessment.knowledge_item_id),
        "current_learning_change_id": str(assessment.current_learning_change_id),
        "proposal_hash": assessment.proposal_hash,
        "proposed_state_hash": assessment.proposed_state_hash,
        "target_state_hash": assessment.target_state_hash,
        "evidence_basis_hash": assessment.evidence_basis_hash,
        "request_hash": assessment.request_hash,
        "request_event_id": str(assessment.request_event_id),
        "request_event_payload_hash": assessment.request_event_payload_hash,
        "freshness_disposition": assessment.freshness_disposition,
        "assessment_result": assessment.assessment_result,
        "evaluator_identity": assessment.evaluator_identity,
        "evaluator_revision": assessment.evaluator_revision,
        "assessment_payload_hash": assessment.payload_hash,
    }


class KnowledgeRevalidationAssessmentService:
    """Create a narrow Task request and record one immutable assessment."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store

    def create_task(self, learning_change_id: UUID) -> UUID:
        with self._session_factory.begin() as session:
            change = session.scalar(
                select(LearningChange)
                .where(LearningChange.id == learning_change_id)
                .with_for_update()
            )
            if change is None:
                raise KnowledgeRevalidationAssessmentError(
                    "knowledge_revalidation_learning_change_missing"
                )
            task_id, payload = build_revalidation_task_request(
                session, self._snapshot_store, change, require_current=True
            )
            existing = session.get(Task, task_id)
            if existing is not None:
                try:
                    validate_revalidation_task_request(
                        session, existing, self._snapshot_store,
                        require_proposed=True, require_current=True,
                    )
                except KnowledgeRevalidationAssessmentError as error:
                    raise KnowledgeRevalidationAssessmentError(
                        "knowledge_revalidation_existing_task_corrupt"
                    ) from error
                return existing.id
            task = Task(
                id=task_id,
                team_id=change.team_id,
                task_type=TASK_TYPE,
                status="pending",
                attempt_count=0,
                policy_version=change.proposed_by_task_id
                and session.get(Task, change.proposed_by_task_id).policy_version,
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
            return task.id

    def record(
        self,
        task_id: UUID,
        draft: KnowledgeRevalidationAssessmentDraft,
        *,
        evaluator_identity: str,
        evaluator_revision: str,
    ) -> KnowledgeRevalidationAssessmentResult:
        identity = evaluator_identity.strip() if isinstance(evaluator_identity, str) else ""
        revision = evaluator_revision.strip() if isinstance(evaluator_revision, str) else ""
        if not identity or not revision or len(identity) > 255 or len(revision) > 255:
            raise KnowledgeRevalidationAssessmentError(
                "knowledge_revalidation_evaluator_identity_invalid"
            )
        if not isinstance(draft, KnowledgeRevalidationAssessmentDraft):
            raise KnowledgeRevalidationAssessmentError(
                "knowledge_revalidation_draft_invalid"
            )
        with self._session_factory.begin() as session:
            task = session.scalar(
                select(Task).where(Task.id == task_id).with_for_update()
            )
            if task is None or task.status != "running":
                raise KnowledgeRevalidationAssessmentError(
                    "knowledge_revalidation_task_not_running"
                )
            context = validate_revalidation_task_request(
                session, task, self._snapshot_store,
                require_proposed=True, require_current=True,
            )
            existing = session.scalar(
                select(KnowledgeRevalidationAssessment).where(
                    KnowledgeRevalidationAssessment.team_id == task.team_id,
                    KnowledgeRevalidationAssessment.learning_change_id
                    == context.learning_change.id,
                )
            )
            if existing is not None:
                if (
                    existing.task_id != task.id
                    or existing.task_attempt != task.attempt_count
                    or existing.evaluator_identity != identity
                    or existing.evaluator_revision != revision
                    or existing.findings
                    != [finding.model_dump(mode="json") for finding in draft.findings]
                    or existing.freshness_disposition != draft.freshness_disposition
                ):
                    raise KnowledgeRevalidationAssessmentError(
                        "knowledge_revalidation_assessment_conflict"
                    )
                return KnowledgeRevalidationAssessmentResult(
                    assessment_id=existing.id,
                    status=existing.assessment_result,
                    assessment_payload_hash=existing.payload_hash,
                    recorded_at=existing.recorded_at,
                    replayed=True,
                )
            started = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == "task_started",
                        Event.payload["attempt_count"].as_integer()
                        == task.attempt_count,
                    )
                )
            )
            if (
                len(started) != 1
                or started[0].payload
                != {
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": task.attempt_count,
                }
            ):
                raise KnowledgeRevalidationAssessmentError(
                    "knowledge_revalidation_task_start_event_invalid"
                )
            findings, freshness, result = validate_revalidation_draft(
                draft, context.pack
            )
            now = datetime.now(timezone.utc)
            request_payload_hash = _sha256_json(context.request_payload)
            assessment = KnowledgeRevalidationAssessment(
                id=uuid4(),
                team_id=task.team_id,
                task_id=task.id,
                task_attempt=task.attempt_count,
                learning_change_id=context.learning_change.id,
                operation="revalidate",
                knowledge_item_id=context.target.id,
                current_learning_change_id=UUID(
                    context.target_state["current_learning_change_id"]
                ),
                target_content_version=context.target_state["version"],
                target_content_hash=context.target_content_hash,
                target_content_hash_scheme=KNOWLEDGE_CONTENT_HASH_SCHEME,
                target_state_hash=context.target_state_hash,
                proposal_hash=context.proposal_hash,
                proposed_state_hash=context.proposed_state_hash,
                evidence_basis_hash=context.evidence_basis_hash,
                evidence_refs=_normalize_json(context.pack.evidence_basis),
                assessment_version=ASSESSMENT_VERSION,
                evaluator_identity=identity,
                evaluator_revision=revision,
                freshness_disposition=freshness,
                findings=findings,
                assessment_result=result,
                idempotency_key=context.request_payload["idempotency_key"],
                request_hash=context.request_payload["request_hash"],
                request_event_id=context.request_event.id,
                request_event_payload_hash=request_payload_hash,
                recorded_event_id=uuid4(),
                recorded_at=now,
                payload_hash="",
            )
            assessment.payload_hash = assessment_payload_hash(assessment)
            session.add(assessment)
            session.flush()
            session.add(
                Event(
                    id=assessment.recorded_event_id,
                    task_id=task.id,
                    type=RECORDED_EVENT_TYPE,
                    payload=recorded_assessment_event_payload(assessment),
                    created_at=now,
                )
            )
            session.flush()
            return KnowledgeRevalidationAssessmentResult(
                assessment_id=assessment.id,
                status=assessment.assessment_result,
                assessment_payload_hash=assessment.payload_hash,
                recorded_at=assessment.recorded_at,
            )


def require_recorded_assessment(
    session: Session,
    learning_change: LearningChange,
    snapshot_store: SnapshotStore,
    *,
    require_task_done: bool,
    require_current: bool,
) -> KnowledgeRevalidationAssessment:
    rows = list(
        session.scalars(
            select(KnowledgeRevalidationAssessment)
            .where(
                KnowledgeRevalidationAssessment.team_id == learning_change.team_id,
                KnowledgeRevalidationAssessment.learning_change_id == learning_change.id,
            )
            .with_for_update()
        )
    )
    if len(rows) != 1:
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_assessment_required"
        )
    assessment = rows[0]
    task = session.get(Task, assessment.task_id)
    expected_statuses = {"done"} if require_task_done else {"running"}
    if (
        task is None
        or task.team_id != learning_change.team_id
        or task.status not in expected_statuses
        or task.task_type != TASK_TYPE
        or task.allowed_writes != ALLOWED_WRITES
        or task.objective_id is not None
        or task.plan_id is not None
        or task.plan_action_id is not None
        or task.max_attempts != TASK_MAX_ATTEMPTS
        or task.budget != TASK_BUDGET
        or assessment.task_attempt != task.attempt_count
        or assessment.status if hasattr(assessment, "status") else False
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_assessment_binding_invalid"
        )
    context = validate_revalidation_task_request(
        session, task, snapshot_store,
        require_proposed=not require_task_done,
        require_current=require_current,
    )
    if (
        assessment.operation != "revalidate"
        or assessment.learning_change_id != learning_change.id
        or assessment.knowledge_item_id != context.target.id
        or assessment.current_learning_change_id
        != UUID(context.target_state["current_learning_change_id"])
        or assessment.target_content_version != context.target_state["version"]
        or assessment.target_content_hash != context.target_content_hash
        or assessment.target_content_hash_scheme != KNOWLEDGE_CONTENT_HASH_SCHEME
        or assessment.target_state_hash != context.target_state_hash
        or assessment.proposal_hash != context.proposal_hash
        or assessment.proposed_state_hash != context.proposed_state_hash
        or assessment.evidence_basis_hash != context.evidence_basis_hash
        or _canonical_json(_normalize_json(assessment.evidence_refs))
        != _canonical_json(_normalize_json(context.pack.evidence_basis))
        or assessment.idempotency_key != context.request_payload["idempotency_key"]
        or assessment.request_hash != context.request_payload["request_hash"]
        or assessment.request_event_id != context.request_event.id
        or assessment.request_event_payload_hash
        != _sha256_json(context.request_payload)
        or assessment.payload_hash != assessment_payload_hash(assessment)
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_assessment_binding_invalid"
        )
    try:
        stored_findings = [
            KnowledgeRevalidationFinding.model_validate(item)
            for item in assessment.findings
        ]
    except Exception as error:
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_recorded_findings_invalid"
        ) from error
    derived_freshness = derive_freshness_disposition(stored_findings)
    derived_result = derive_assessment_result(derived_freshness, stored_findings)
    if (
        derived_freshness != assessment.freshness_disposition
        or derived_result != assessment.assessment_result
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_recorded_result_mismatch"
        )
    # Re-run reference completeness and contrary-evidence checks against the
    # independently rebuilt canonical basis.
    findings_draft = KnowledgeRevalidationAssessmentDraft(
        freshness_disposition=assessment.freshness_disposition,
        findings=stored_findings,
    )
    validate_revalidation_draft(findings_draft, context.pack)
    recorded_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == RECORDED_EVENT_TYPE,
            )
        )
    )
    if (
        len(recorded_events) != 1
        or recorded_events[0].id != assessment.recorded_event_id
        or recorded_events[0].payload != recorded_assessment_event_payload(assessment)
        or recorded_events[0].created_at != assessment.recorded_at
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_recorded_event_invalid"
        )
    started = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "task_started",
                Event.payload["attempt_count"].as_integer() == task.attempt_count,
            )
        )
    )
    if (
        len(started) != 1
        or started[0].payload
        != {
            "from_status": "pending",
            "to_status": "running",
            "attempt_count": task.attempt_count,
        }
        or started[0].created_at > assessment.recorded_at
    ):
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_task_start_event_invalid"
        )
    terminal = list(
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
    if require_task_done:
        if (
            task.completed_at is None
            or len(terminal) != 1
            or len(outcomes) != 1
            or terminal[0].payload.get("result_category")
            != "success_knowledge_revalidation_assessed"
            or terminal[0].payload.get("knowledge_revalidation_assessment_id")
            != str(assessment.id)
            or terminal[0].payload.get("outcome_id") != str(outcomes[0].id)
            or terminal[0].payload.get("attempt_count") != task.attempt_count
            or outcomes[0].observed_at != assessment.recorded_at
            or outcomes[0].recorded_by_task_id != task.id
            or task.completed_at != outcomes[0].observed_at
        ):
            raise KnowledgeRevalidationAssessmentError(
                "knowledge_revalidation_task_terminal_invalid"
            )
    elif terminal or outcomes:
        raise KnowledgeRevalidationAssessmentError(
            "knowledge_revalidation_task_already_terminal"
        )
    return assessment
