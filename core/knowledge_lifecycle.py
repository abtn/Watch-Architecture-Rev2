"""Deterministic R7-B lifecycle assessment contracts and immutable recording."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.experience_distiller import ExperienceDistiller, ExperienceDistillerError
from core.learning_history import (
    KNOWLEDGE_CONTENT_HASH_SCHEME,
    KnowledgeHistoryError,
    decode_state_snapshot,
    encode_state_snapshot,
    knowledge_item_content_hash,
    knowledge_item_state,
    reconstruct_knowledge_item_history,
)
from core.models import (
    Event,
    KnowledgeItem,
    KnowledgeLifecycleAssessment,
    LearningChange,
    LearningChangeOperatorProvenance,
    Outcome,
    Task,
    Team,
)
from core.snapshot_store import SnapshotStore
from core.state_assessment import _canonical_json, _timestamp

TASK_TYPE = "assess_knowledge_lifecycle"
REQUEST_EVENT_TYPE = "knowledge_lifecycle_assessment_task_requested"
RECORDED_EVENT_TYPE = "knowledge_lifecycle_assessment_recorded"
ALLOWED_WRITES = ["KnowledgeLifecycleAssessment"]
TASK_MAX_ATTEMPTS = 3
TASK_BUDGET = {
    "max_tool_calls": 0,
    "max_cost_usd": 0.0,
    "deadline_seconds": 30,
}
ASSESSMENT_VERSION = 1
TASK_ID_NAMESPACE = uuid5(
    NAMESPACE_URL, "watch.r7b.knowledge-lifecycle-task.v1"
)
PROPOSED_STATE_HASH_DOMAIN = "watch.r7b.learning-change-proposed-state.v1"
ASSESSMENT_HASH_DOMAIN = "watch.r7b.knowledge-lifecycle-assessment.v1"
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
SUCCESSOR_REQUEST_FIELDS = (
    "successor_knowledge_item_id",
    "successor_team_id",
    "successor_current_learning_change_id",
    "successor_content_version",
    "successor_content_hash",
    "successor_content_hash_scheme",
    "successor_status",
    "successor_review_after",
    "successor_state_hash",
)
LIFECYCLE_FINDING_CODES = frozenset(
    {
        "proposal_operation_valid",
        "team_ownership_valid",
        "predecessor_binding_valid",
        "operator_rationale_valid",
        "evidence_reference_valid",
        "retire_variant_shape_valid",
        "successor_state_binding_valid",
        "predecessor_successor_relationship_valid",
        "successor_status_eligible",
        "successor_review_after_eligible",
    }
)


class KnowledgeLifecycleAssessmentError(ValueError):
    """A lifecycle proposal, evidence basis, or assessment is invalid."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class OperatorRationaleReason(BaseModel):
    """One original host/Operator-supplied reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: str = Field(min_length=1, max_length=80)
    statement: str = Field(min_length=1, max_length=1200)

    @field_validator("category", "statement")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("knowledge_lifecycle_rationale_text_required")
        return value


class OperatorRationale(BaseModel):
    """Versioned structured rationale copied exactly from the proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    summary: str = Field(min_length=1, max_length=1200)
    reasons: list[OperatorRationaleReason] = Field(min_length=1, max_length=32)

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value: object) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("knowledge_lifecycle_rationale_version_invalid")
        return value

    @field_validator("summary")
    @classmethod
    def nonblank_summary(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("knowledge_lifecycle_rationale_summary_required")
        return value


class KnowledgeLifecycleFinding(BaseModel):
    """Application-authored deterministic lifecycle finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    outcome: str
    summary: str

    @field_validator("code")
    @classmethod
    def known_code(cls, value: str) -> str:
        if value not in LIFECYCLE_FINDING_CODES:
            raise ValueError("knowledge_lifecycle_finding_code_invalid")
        return value

    @field_validator("outcome")
    @classmethod
    def known_outcome(cls, value: str) -> str:
        if value not in {"passed", "failed"}:
            raise ValueError("knowledge_lifecycle_finding_outcome_invalid")
        return value

    @field_validator("summary")
    @classmethod
    def nonblank_summary(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("knowledge_lifecycle_finding_summary_required")
        return value


@dataclass(frozen=True)
class LifecycleProposalContext:
    learning_change: LearningChange
    source_task: Task
    target: KnowledgeItem
    target_state: dict[str, Any]
    target_state_hash: str
    target_content_hash: str
    proposal_hash: str
    proposed_state_hash: str
    evidence_basis_hash: str
    evidence_pack: Any
    rationale: dict[str, Any]
    operator_provenance: LearningChangeOperatorProvenance
    successor_id: UUID | None


@dataclass(frozen=True)
class LifecycleTaskContext:
    task: Task
    proposal: LifecycleProposalContext
    request_event: Event
    request_payload: dict[str, Any]
    successor_binding: dict[str, Any] | None


@dataclass(frozen=True)
class KnowledgeLifecycleAssessmentResult:
    assessment_id: UUID
    assessment_result: str
    assessment_payload_hash: str
    recorded_at: datetime
    replayed: bool = False


def _sha256_json(value: Any) -> str:
    try:
        encoded = _canonical_json(value).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_json_not_canonicalizable"
        ) from error
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _domain_hash(domain: str, value: Any) -> str:
    try:
        encoded = _canonical_json(value).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_json_not_canonicalizable"
        ) from error
    framed = domain.encode("utf-8") + b"\x00" + encoded
    return "sha256:" + hashlib.sha256(framed).hexdigest()


def _normalize_json(value: Any) -> Any:
    """Normalize typed values explicitly while preserving semantic array order."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return _normalize_json(value.value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_decimal_not_finite"
            )
        return format(value, "f")
    if isinstance(value, datetime):
        try:
            return _timestamp(value)
        except ValueError as error:
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_timestamp_not_aware"
            ) from error
    if isinstance(value, float):
        if not math.isfinite(value):
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_number_not_finite"
            )
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json(item) for item in value]
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_json_key_invalid"
            )
        return {key: _normalize_json(item) for key, item in value.items()}
    raise KnowledgeLifecycleAssessmentError("knowledge_lifecycle_json_value_invalid")


def _canonical_uuid(value: object, reason: str) -> UUID:
    if not isinstance(value, str):
        raise KnowledgeLifecycleAssessmentError(reason)
    try:
        parsed = UUID(value)
    except (TypeError, ValueError) as error:
        raise KnowledgeLifecycleAssessmentError(reason) from error
    if str(parsed) != value:
        raise KnowledgeLifecycleAssessmentError(reason)
    return parsed


def _require_sha256(value: object, reason: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in value[7:])
    ):
        raise KnowledgeLifecycleAssessmentError(reason)
    return value


def _task_id(team_id: UUID, learning_change_id: UUID) -> UUID:
    return uuid5(
        TASK_ID_NAMESPACE,
        f"{team_id}:{learning_change_id}:{TASK_TYPE}",
    )


def _idempotency_key(team_id: UUID, learning_change_id: UUID) -> str:
    identity = {
        "team_id": str(team_id),
        "learning_change_id": str(learning_change_id),
        "task_type": TASK_TYPE,
        "assessment_version": ASSESSMENT_VERSION,
    }
    return (
        "r7b-lifecycle-v1:"
        + _sha256_json(identity).removeprefix("sha256:")
    )


def validate_operator_rationale(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_operator_rationale_required"
        )
    try:
        rationale = OperatorRationale.model_validate(value)
    except Exception as error:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_operator_rationale_invalid"
        ) from error
    normalized = rationale.model_dump(mode="json")
    if normalized != value:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_operator_rationale_not_canonical"
        )
    return normalized


def _validate_proposed_state(
    learning_change: LearningChange,
) -> tuple[str, str, str, dict[str, Any], UUID | None]:
    operation = learning_change.operation
    if operation not in {"retire", "supersede"}:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_proposal_operation_invalid"
        )
    state = learning_change.proposed_state
    if not isinstance(state, dict):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_proposed_state_invalid"
        )
    expected_keys = {
        "proposal_hash",
        "evidence_basis_hash",
        "operator_rationale",
    }
    successor_id: UUID | None = None
    if operation == "supersede":
        expected_keys.add("successor_knowledge_item_id")
    if set(state) != expected_keys:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_proposed_state_shape_invalid"
        )
    proposal_hash = _require_sha256(
        state.get("proposal_hash"),
        "knowledge_lifecycle_proposal_hash_invalid",
    )
    evidence_hash = _require_sha256(
        state.get("evidence_basis_hash"),
        "knowledge_lifecycle_evidence_hash_invalid",
    )
    if evidence_hash != learning_change.evidence_basis_hash:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_proposed_evidence_hash_mismatch"
        )
    rationale = validate_operator_rationale(state.get("operator_rationale"))
    if operation == "supersede":
        successor_id = _canonical_uuid(
            state.get("successor_knowledge_item_id"),
            "knowledge_lifecycle_successor_id_invalid",
        )
    proposed_state_hash = _domain_hash(
        PROPOSED_STATE_HASH_DOMAIN,
        _normalize_json(state),
    )
    return proposal_hash, evidence_hash, proposed_state_hash, rationale, successor_id


def _validate_source_task(
    session: Session,
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    learning_change: LearningChange,
) -> Task:
    if learning_change.proposed_by_task_id is None:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_source_task_missing"
        )
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
        or source_task.attempt_count < 1
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_source_task_invalid"
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
    outcomes = list(
        session.scalars(
            select(Outcome).where(
                Outcome.recorded_by_task_id == source_task.id,
                Outcome.outcome_type == "task_execution",
            )
        )
    )
    proposal_hash = learning_change.proposed_state.get("proposal_hash")
    if (
        len(proposal_events) != 1
        or not isinstance(proposal_events[0].payload, dict)
        or len(terminal_events) != 1
        or not isinstance(terminal_events[0].payload, dict)
        or len(outcomes) != 1
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_source_terminal_invalid"
        )
    proposal_payload = proposal_events[0].payload
    terminal_payload = terminal_events[0].payload
    outcome = outcomes[0]
    if (
        proposal_payload.get("learning_change_id") != str(learning_change.id)
        or proposal_payload.get("operation") != learning_change.operation
        or proposal_payload.get("proposal_hash") != proposal_hash
        or proposal_payload.get("evidence_basis_hash")
        != learning_change.evidence_basis_hash
        or proposal_payload.get("attempt_count") != source_task.attempt_count
        or terminal_payload.get("result_category")
        != "success_learning_change_proposed"
        or terminal_payload.get("learning_change_id") != str(learning_change.id)
        or terminal_payload.get("attempt_count") != source_task.attempt_count
        or terminal_payload.get("outcome_id") != str(outcome.id)
        or outcome.team_id != learning_change.team_id
        or outcome.subject_kind != "task"
        or outcome.subject_id != source_task.id
        or outcome.recorded_by_task_id != source_task.id
        or outcome.observed_at is None
        or outcome.observation_snapshot_ref is None
        or outcome.observation_hash is None
        or terminal_payload.get("observation_snapshot_ref")
        != outcome.observation_snapshot_ref
        or terminal_payload.get("observation_hash") != outcome.observation_hash
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_source_terminal_mismatch"
        )
    try:
        snapshot = ExperienceDistiller(
            session_factory, snapshot_store, provider=None
        )._read_snapshot(
            outcome.observation_snapshot_ref,
            outcome.observation_hash,
        )
        observation = json.loads(snapshot.decode("utf-8"))
    except (
        ExperienceDistillerError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_source_observation_invalid"
        ) from error
    if (
        not isinstance(observation, dict)
        or observation.get("result_category") != "success_learning_change_proposed"
        or observation.get("learning_change_id") != str(learning_change.id)
        or observation.get("attempt") != source_task.attempt_count
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_source_observation_mismatch"
        )
    return source_task


def _build_canonical_evidence_pack(
    session: Session,
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    learning_change: LearningChange,
    source_task: Task,
) -> Any:
    basis = learning_change.evidence_basis
    if not isinstance(basis, list) or not basis:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_evidence_basis_missing"
        )
    evaluation_ids: list[UUID] = []
    marker_states: list[bool] = []
    for entry in basis:
        if not isinstance(entry, dict):
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_evidence_basis_invalid"
            )
        evaluation_ids.append(
            _canonical_uuid(
                entry.get("evaluation_id"),
                "knowledge_lifecycle_evaluation_id_invalid",
            )
        )
        marker_states.append("schema_version" in entry)
        if "schema_version" in entry and entry["schema_version"] not in {
            "r6f-experience-evidence-pack-v1",
            "r6g-experience-evidence-pack-v2",
        }:
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_evidence_schema_invalid"
            )
    if len(set(evaluation_ids)) != len(evaluation_ids):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_duplicate_evaluation"
        )
    if any(marker_states) and not all(marker_states):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_mixed_evidence_schema_markers"
        )
    team = session.get(Team, learning_change.team_id)
    if team is None or team.status != "active":
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_team_not_active"
        )
    try:
        pack = ExperienceDistiller(
            session_factory, snapshot_store, provider=None
        )._build_pack(
            session,
            source_task,
            team,
            tuple(sorted(evaluation_ids)),
            allow_completed_task=True,
            include_version_marker=bool(marker_states and marker_states[0]),
        )
    except ExperienceDistillerError as error:
        raise KnowledgeLifecycleAssessmentError(error.reason) from error
    if (
        _canonical_json(_normalize_json(basis))
        != _canonical_json(_normalize_json(pack.evidence_basis))
        or pack.basis_hash != learning_change.evidence_basis_hash
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_evidence_basis_stale"
        )
    return pack


def _proposal_context(
    session: Session,
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    learning_change: LearningChange,
    *,
    require_current: bool,
) -> LifecycleProposalContext:
    if (
        learning_change.target_kind != "knowledge_item"
        or learning_change.target_id is None
        or learning_change.status not in {"proposed", "accepted", "rejected"}
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_proposal_invalid"
        )
    (
        proposal_hash,
        evidence_hash,
        proposed_state_hash,
        rationale,
        successor_id,
    ) = _validate_proposed_state(learning_change)
    source_task = _validate_source_task(
        session, session_factory, snapshot_store, learning_change
    )
    provenance = session.get(
        LearningChangeOperatorProvenance, learning_change.id
    )
    if (
        provenance is None
        or provenance.team_id != learning_change.team_id
        or not provenance.issuer.strip()
        or not provenance.subject.strip()
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_operator_provenance_missing"
        )
    try:
        _timestamp(provenance.recorded_at)
    except ValueError as error:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_operator_provenance_timestamp_invalid"
        ) from error

    previous = learning_change.previous_state
    if (
        not isinstance(previous, dict)
        or set(previous) != {"snapshot_version", "state", "snapshot_hash"}
        or not isinstance(previous.get("state"), dict)
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_previous_state_invalid"
        )
    raw_state = previous["state"]
    pointer = _canonical_uuid(
        raw_state.get("current_learning_change_id"),
        "knowledge_lifecycle_predecessor_pointer_invalid",
    )
    try:
        target_state, reconstructed = decode_state_snapshot(
            previous,
            learning_change_id=pointer,
            operation=learning_change.operation,
            allow_legacy_root=False,
        )
    except KnowledgeHistoryError as error:
        raise KnowledgeLifecycleAssessmentError(
            f"knowledge_lifecycle_previous_state_{error.reason}"
        ) from error
    if reconstructed:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_previous_state_legacy"
        )
    if (
        target_state["id"] != str(learning_change.target_id)
        or target_state["team_id"] != str(learning_change.team_id)
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_predecessor_identity_mismatch"
        )
    target_state_hash = _require_sha256(
        previous.get("snapshot_hash"),
        "knowledge_lifecycle_target_state_hash_invalid",
    )
    if target_state["status"] not in {"active", "needs_review"}:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_predecessor_status_invalid"
        )
    if target_state["superseded_by_id"] is not None:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_predecessor_already_superseded"
        )
    target_content_hash = _domain_hash(
        KNOWLEDGE_CONTENT_HASH_SCHEME,
        {field: target_state[field] for field in CONTENT_FIELDS},
    )
    target = session.scalar(
        select(KnowledgeItem).where(
            KnowledgeItem.id == learning_change.target_id,
            KnowledgeItem.team_id == learning_change.team_id,
        ).with_for_update()
        if require_current
        else select(KnowledgeItem).where(
            KnowledgeItem.id == learning_change.target_id,
            KnowledgeItem.team_id == learning_change.team_id,
        )
    )
    if target is None:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_predecessor_not_found"
        )
    if require_current:
        try:
            live_state = knowledge_item_state(target)
            live_hash = knowledge_item_content_hash(target)
            reconstruct_knowledge_item_history(session, target)
        except KnowledgeHistoryError as error:
            raise KnowledgeLifecycleAssessmentError(
                f"knowledge_lifecycle_predecessor_{error.reason}"
            ) from error
        if (
            live_state != target_state
            or live_hash != target_content_hash
            or target.version != target_state["version"]
            or target.current_learning_change_id != pointer
        ):
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_predecessor_stale"
            )
    pack = _build_canonical_evidence_pack(
        session,
        session_factory,
        snapshot_store,
        learning_change,
        source_task,
    )
    return LifecycleProposalContext(
        learning_change=learning_change,
        source_task=source_task,
        target=target,
        target_state=target_state,
        target_state_hash=target_state_hash,
        target_content_hash=target_content_hash,
        proposal_hash=proposal_hash,
        proposed_state_hash=proposed_state_hash,
        evidence_basis_hash=evidence_hash,
        evidence_pack=pack,
        rationale=rationale,
        operator_provenance=provenance,
        successor_id=successor_id,
    )


def _successor_binding(
    session: Session,
    proposal: LifecycleProposalContext,
    *,
    require_current: bool,
) -> dict[str, Any]:
    change = proposal.learning_change
    if change.operation != "supersede":
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_successor_not_allowed"
        )
    successor_id = proposal.successor_id
    if successor_id is None:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_successor_id_invalid"
        )
    successor_query = select(KnowledgeItem).where(
        KnowledgeItem.id == successor_id
    )
    if require_current:
        successor_query = successor_query.with_for_update()
    successor = session.scalar(successor_query)
    if successor is None:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_successor_not_found"
        )
    if successor.team_id != change.team_id:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_successor_cross_team"
        )
    if successor.id == proposal.target.id:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_successor_is_predecessor"
        )
    if successor.supersedes_item_id != proposal.target.id:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_predecessor_successor_relationship_invalid"
        )
    state = knowledge_item_state(successor)
    try:
        successor_snapshot = encode_state_snapshot(state)
        content_hash = knowledge_item_content_hash(successor)
        current_pointer = _canonical_uuid(
            state.get("current_learning_change_id"),
            "knowledge_lifecycle_successor_pointer_invalid",
        )
        if require_current:
            reconstruct_knowledge_item_history(session, successor)
    except KnowledgeHistoryError as error:
        raise KnowledgeLifecycleAssessmentError(
            f"knowledge_lifecycle_successor_{error.reason}"
        ) from error
    except KnowledgeLifecycleAssessmentError:
        raise
    review_after = state.get("review_after")
    if review_after is not None:
        if not isinstance(review_after, datetime):
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_successor_review_after_invalid"
            )
        try:
            normalized_review_after = _timestamp(review_after)
        except ValueError as error:
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_successor_review_after_invalid"
            ) from error
    else:
        normalized_review_after = None
    return {
        "successor_knowledge_item_id": str(successor.id),
        "successor_team_id": str(successor.team_id),
        "successor_current_learning_change_id": str(current_pointer),
        "successor_content_version": successor.version,
        "successor_content_hash": content_hash,
        "successor_content_hash_scheme": KNOWLEDGE_CONTENT_HASH_SCHEME,
        "successor_status": successor.status,
        "successor_review_after": normalized_review_after,
        "successor_state_hash": successor_snapshot["snapshot_hash"],
    }


def _common_request_payload(
    task_id: UUID,
    proposal: LifecycleProposalContext,
) -> dict[str, Any]:
    change = proposal.learning_change
    provenance = proposal.operator_provenance
    return {
        "schema_version": 1,
        "task_type": TASK_TYPE,
        "task_id": str(task_id),
        "team_id": str(change.team_id),
        "learning_change_id": str(change.id),
        "operation": change.operation,
        "proposed_by_task_id": str(proposal.source_task.id),
        "knowledge_item_id": str(proposal.target.id),
        "current_learning_change_id": proposal.target_state[
            "current_learning_change_id"
        ],
        "target_content_version": proposal.target_state["version"],
        "target_content_hash": proposal.target_content_hash,
        "target_content_hash_scheme": KNOWLEDGE_CONTENT_HASH_SCHEME,
        "target_state_hash": proposal.target_state_hash,
        "target_status": proposal.target_state["status"],
        "proposal_hash": proposal.proposal_hash,
        "proposed_state_hash": proposal.proposed_state_hash,
        "evidence_basis_hash": proposal.evidence_basis_hash,
        "operator_issuer": provenance.issuer,
        "operator_subject": provenance.subject,
        "operator_provenance_recorded_at": _timestamp(provenance.recorded_at),
        "policy_version": proposal.source_task.policy_version,
        "idempotency_key": _idempotency_key(change.team_id, change.id),
    }


def build_lifecycle_task_request(
    session: Session,
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    learning_change: LearningChange,
) -> tuple[UUID, dict[str, Any]]:
    proposal = _proposal_context(
        session,
        session_factory,
        snapshot_store,
        learning_change,
        require_current=True,
    )
    task_id = _task_id(learning_change.team_id, learning_change.id)
    payload = _common_request_payload(task_id, proposal)
    if learning_change.operation == "supersede":
        payload.update(
            _successor_binding(session, proposal, require_current=True)
        )
    payload["request_hash"] = _sha256_json(payload)
    return task_id, payload


def validate_lifecycle_task_request(
    session: Session,
    task: Task,
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    *,
    require_proposed: bool = True,
) -> LifecycleTaskContext:
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
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_task_shape_invalid"
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
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_request_event_invalid"
        )
    payload = events[0].payload
    change_id = _canonical_uuid(
        payload.get("learning_change_id"),
        "knowledge_lifecycle_learning_change_id_invalid",
    )
    change = session.scalar(
        select(LearningChange).where(
            LearningChange.id == change_id,
            LearningChange.team_id == task.team_id,
        ).with_for_update()
    )
    if change is None:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_learning_change_missing"
        )
    if require_proposed and change.status != "proposed":
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_learning_change_not_proposed"
        )
    if not require_proposed and change.status not in {
        "proposed", "accepted", "rejected"
    }:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_learning_change_status_invalid"
        )
    task_id, expected = build_lifecycle_task_request(
        session, session_factory, snapshot_store, change
    )
    if (
        task.id != task_id
        or task.team_id != change.team_id
        or task.policy_version != expected["policy_version"]
        or payload != expected
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_task_request_mismatch"
        )
    return LifecycleTaskContext(
        task=task,
        proposal=_proposal_context(
            session,
            session_factory,
            snapshot_store,
            change,
            require_current=True,
        ),
        request_event=events[0],
        request_payload=payload,
        successor_binding=(
            {key: payload[key] for key in SUCCESSOR_REQUEST_FIELDS}
            if change.operation == "supersede"
            else None
        ),
    )


def _finding(
    code: str,
    passed: bool,
    success_summary: str,
    failure_summary: str | None = None,
) -> dict[str, str]:
    return {
        "code": code,
        "outcome": "passed" if passed else "failed",
        "summary": success_summary if passed else (failure_summary or success_summary),
    }


def derive_lifecycle_findings(
    operation: str,
    target_state: Mapping[str, Any],
    successor_binding: Mapping[str, Any] | None,
    recorded_at: datetime,
) -> tuple[list[dict[str, str]], str]:
    """Derive deterministic findings; only successor D7 eligibility is ineligible."""
    findings = [
        _finding(
            "proposal_operation_valid",
            operation in {"retire", "supersede"},
            "The proposal operation matches the lifecycle assessment.",
        ),
        _finding(
            "team_ownership_valid",
            True,
            "The proposal, predecessor, and evidence belong to one Team.",
        ),
        _finding(
            "predecessor_binding_valid",
            target_state.get("status") in {"active", "needs_review"}
            and target_state.get("superseded_by_id") is None,
            "The predecessor snapshot is current and not already superseded.",
            "The predecessor is not eligible for a new lifecycle disposition.",
        ),
        _finding(
            "operator_rationale_valid",
            True,
            "The original structured Operator rationale is bound to the proposal.",
        ),
        _finding(
            "evidence_reference_valid",
            True,
            "All evidence references resolve to the rebuilt canonical evidence basis.",
        ),
    ]
    if operation == "retire":
        findings.append(
            _finding(
                "retire_variant_shape_valid",
                successor_binding is None,
                "The retire variant contains no successor fields.",
                "The retire variant contains successor-only fields.",
            )
        )
    else:
        if successor_binding is None:
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_successor_binding_required"
            )
        review_after_raw = successor_binding.get("successor_review_after")
        review_after: datetime | None = None
        if review_after_raw is not None:
            try:
                review_after = datetime.fromisoformat(
                    str(review_after_raw).replace("Z", "+00:00")
                )
                if review_after.tzinfo is None or review_after.utcoffset() is None:
                    raise ValueError("naive_timestamp")
                review_after = review_after.astimezone(timezone.utc)
            except ValueError as error:
                raise KnowledgeLifecycleAssessmentError(
                    "knowledge_lifecycle_successor_review_after_invalid"
                ) from error
        now = recorded_at.astimezone(timezone.utc)
        findings.extend(
            [
                _finding(
                    "successor_state_binding_valid",
                    True,
                    (
                        "The exact same-Team successor state is bound by pointer, "
                        "version, content hash, and snapshot hash."
                    ),
                ),
                _finding(
                    "predecessor_successor_relationship_valid",
                    True,
                    "The successor identifies the exact predecessor.",
                ),
                _finding(
                    "successor_status_eligible",
                    successor_binding.get("successor_status") == "active",
                    "The successor is active.",
                    "The successor is not active.",
                ),
                _finding(
                    "successor_review_after_eligible",
                    review_after is not None and review_after > now,
                    (
                        "The successor review date is non-null and later than "
                        "assessment time."
                    ),
                    "The successor review date is null or due.",
                ),
            ]
        )
    result = (
        "eligible"
        if all(item["outcome"] == "passed" for item in findings)
        else "ineligible"
    )
    return findings, result


def assessment_record_payload(
    assessment: KnowledgeLifecycleAssessment,
    provenance: LearningChangeOperatorProvenance,
) -> dict[str, Any]:
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
        "operator_rationale": _normalize_json(assessment.operator_rationale),
        "operator_provenance": {
            "issuer": provenance.issuer,
            "subject": provenance.subject,
            "recorded_at": _timestamp(provenance.recorded_at),
        },
        "findings": _normalize_json(assessment.findings),
        "assessment_result": assessment.assessment_result,
        "variant_payload": _normalize_json(assessment.variant_payload),
        "successor_knowledge_item_id": (
            str(assessment.successor_knowledge_item_id)
            if assessment.successor_knowledge_item_id is not None
            else None
        ),
        "successor_current_learning_change_id": (
            str(assessment.successor_current_learning_change_id)
            if assessment.successor_current_learning_change_id is not None
            else None
        ),
        "successor_content_version": assessment.successor_content_version,
        "successor_content_hash": assessment.successor_content_hash,
        "successor_content_hash_scheme": assessment.successor_content_hash_scheme,
        "successor_status": assessment.successor_status,
        "successor_review_after": (
            _timestamp(assessment.successor_review_after)
            if assessment.successor_review_after is not None
            else None
        ),
        "successor_state_hash": assessment.successor_state_hash,
        "idempotency_key": assessment.idempotency_key,
        "request_hash": assessment.request_hash,
        "request_event_id": str(assessment.request_event_id),
        "request_event_payload_hash": assessment.request_event_payload_hash,
        "recorded_event_id": str(assessment.recorded_event_id),
        "recorded_at": _timestamp(assessment.recorded_at),
    }


def assessment_payload_hash(
    assessment: KnowledgeLifecycleAssessment,
    provenance: LearningChangeOperatorProvenance,
) -> str:
    return _domain_hash(
        ASSESSMENT_HASH_DOMAIN,
        assessment_record_payload(assessment, provenance),
    )


def recorded_assessment_event_payload(
    assessment: KnowledgeLifecycleAssessment,
) -> dict[str, Any]:
    return {
        "assessment_id": str(assessment.id),
        "team_id": str(assessment.team_id),
        "task_id": str(assessment.task_id),
        "task_attempt": assessment.task_attempt,
        "learning_change_id": str(assessment.learning_change_id),
        "operation": assessment.operation,
        "knowledge_item_id": str(assessment.knowledge_item_id),
        "current_learning_change_id": str(assessment.current_learning_change_id),
        "proposal_hash": assessment.proposal_hash,
        "proposed_state_hash": assessment.proposed_state_hash,
        "target_state_hash": assessment.target_state_hash,
        "evidence_basis_hash": assessment.evidence_basis_hash,
        "request_hash": assessment.request_hash,
        "request_event_id": str(assessment.request_event_id),
        "request_event_payload_hash": assessment.request_event_payload_hash,
        "operator_rationale": _normalize_json(assessment.operator_rationale),
        "assessment_result": assessment.assessment_result,
        "successor_knowledge_item_id": (
            str(assessment.successor_knowledge_item_id)
            if assessment.successor_knowledge_item_id is not None
            else None
        ),
        "successor_state_hash": assessment.successor_state_hash,
        "assessment_payload_hash": assessment.payload_hash,
    }


def _stored_successor_binding(
    assessment: KnowledgeLifecycleAssessment,
) -> dict[str, Any] | None:
    if assessment.operation == "retire":
        if (
            assessment.variant_payload != {}
            or assessment.successor_knowledge_item_id is not None
            or assessment.successor_current_learning_change_id is not None
            or assessment.successor_content_version is not None
            or assessment.successor_content_hash is not None
            or assessment.successor_content_hash_scheme is not None
            or assessment.successor_status is not None
            or assessment.successor_review_after is not None
            or assessment.successor_state_hash is not None
        ):
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_retire_variant_shape_invalid"
            )
        return None
    expected_team = str(assessment.team_id)
    if assessment.variant_payload != {"successor_team_id": expected_team}:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_successor_variant_shape_invalid"
        )
    if (
        assessment.successor_knowledge_item_id is None
        or assessment.successor_current_learning_change_id is None
        or assessment.successor_content_version is None
        or assessment.successor_content_hash is None
        or assessment.successor_content_hash_scheme
        != KNOWLEDGE_CONTENT_HASH_SCHEME
        or assessment.successor_status is None
        or assessment.successor_state_hash is None
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_successor_binding_invalid"
        )
    _require_sha256(
        assessment.successor_content_hash,
        "knowledge_lifecycle_successor_content_hash_invalid",
    )
    _require_sha256(
        assessment.successor_state_hash,
        "knowledge_lifecycle_successor_state_hash_invalid",
    )
    if assessment.successor_review_after is not None:
        try:
            _timestamp(assessment.successor_review_after)
        except ValueError as error:
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_successor_review_after_invalid"
            ) from error
    return {
        "successor_knowledge_item_id": str(assessment.successor_knowledge_item_id),
        "successor_team_id": expected_team,
        "successor_current_learning_change_id": str(
            assessment.successor_current_learning_change_id
        ),
        "successor_content_version": assessment.successor_content_version,
        "successor_content_hash": assessment.successor_content_hash,
        "successor_content_hash_scheme": assessment.successor_content_hash_scheme,
        "successor_status": assessment.successor_status,
        "successor_review_after": (
            _timestamp(assessment.successor_review_after)
            if assessment.successor_review_after is not None
            else None
        ),
        "successor_state_hash": assessment.successor_state_hash,
    }


def _stored_request_payload(
    task: Task,
    proposal: LifecycleProposalContext,
    assessment: KnowledgeLifecycleAssessment,
    request_event: Event,
) -> dict[str, Any]:
    payload = request_event.payload
    if not isinstance(payload, dict):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_request_event_invalid"
        )
    expected = _common_request_payload(task.id, proposal)
    successor_binding = _stored_successor_binding(assessment)
    if successor_binding is not None:
        expected.update(successor_binding)
    expected["request_hash"] = _sha256_json(expected)
    if payload != expected:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_request_event_mismatch"
        )
    return payload


def require_recorded_assessment(
    session: Session,
    learning_change: LearningChange,
    snapshot_store: SnapshotStore,
    session_factory: sessionmaker[Session],
    *,
    require_task_done: bool,
    require_current: bool,
) -> KnowledgeLifecycleAssessment:
    rows = list(
        session.scalars(
            select(KnowledgeLifecycleAssessment)
            .where(
                KnowledgeLifecycleAssessment.team_id == learning_change.team_id,
                KnowledgeLifecycleAssessment.learning_change_id
                == learning_change.id,
            )
            .with_for_update()
        )
    )
    if len(rows) != 1:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_assessment_required"
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
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_assessment_binding_invalid"
        )
    proposal = _proposal_context(
        session,
        session_factory,
        snapshot_store,
        learning_change,
        require_current=require_current,
    )
    if (
        task.id != _task_id(learning_change.team_id, learning_change.id)
        or task.policy_version != proposal.source_task.policy_version
        or assessment.operation != learning_change.operation
        or assessment.learning_change_id != learning_change.id
        or assessment.knowledge_item_id != proposal.target.id
        or assessment.current_learning_change_id
        != UUID(proposal.target_state["current_learning_change_id"])
        or assessment.target_content_version != proposal.target_state["version"]
        or assessment.target_content_hash != proposal.target_content_hash
        or assessment.target_content_hash_scheme != KNOWLEDGE_CONTENT_HASH_SCHEME
        or assessment.target_state_hash != proposal.target_state_hash
        or assessment.proposal_hash != proposal.proposal_hash
        or assessment.proposed_state_hash != proposal.proposed_state_hash
        or assessment.evidence_basis_hash != proposal.evidence_basis_hash
        or _canonical_json(_normalize_json(assessment.evidence_refs))
        != _canonical_json(_normalize_json(proposal.evidence_pack.evidence_basis))
        or _canonical_json(_normalize_json(assessment.operator_rationale))
        != _canonical_json(_normalize_json(proposal.rationale))
        or assessment.assessment_version != ASSESSMENT_VERSION
        or assessment.idempotency_key
        != _idempotency_key(learning_change.team_id, learning_change.id)
        or assessment.task_id != task.id
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_assessment_binding_invalid"
        )
    request_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
    )
    if (
        len(request_events) != 1
        or request_events[0].id != assessment.request_event_id
        or request_events[0].created_at > assessment.recorded_at
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_request_event_invalid"
        )
    request_payload = _stored_request_payload(
        task, proposal, assessment, request_events[0]
    )
    if (
        assessment.request_hash != request_payload["request_hash"]
        or assessment.request_event_payload_hash != _sha256_json(request_payload)
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_request_binding_invalid"
        )
    successor_binding = _stored_successor_binding(assessment)
    if require_current and learning_change.operation == "supersede":
        live_successor_binding = _successor_binding(
            session, proposal, require_current=True
        )
        if live_successor_binding != successor_binding:
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_successor_stale"
            )
    if learning_change.operation == "retire":
        if successor_binding is not None:
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_retire_variant_shape_invalid"
            )
    else:
        if (
            successor_binding is None
            or successor_binding["successor_knowledge_item_id"]
            == str(assessment.knowledge_item_id)
        ):
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_successor_binding_invalid"
            )
        if (
            successor_binding["successor_current_learning_change_id"]
            != request_payload.get("successor_current_learning_change_id")
            or successor_binding["successor_content_version"]
            != request_payload.get("successor_content_version")
            or successor_binding["successor_content_hash"]
            != request_payload.get("successor_content_hash")
            or successor_binding["successor_status"]
            != request_payload.get("successor_status")
            or successor_binding["successor_review_after"]
            != request_payload.get("successor_review_after")
            or successor_binding["successor_state_hash"]
            != request_payload.get("successor_state_hash")
        ):
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_successor_binding_invalid"
            )
    try:
        stored_findings = [
            KnowledgeLifecycleFinding.model_validate(item)
            for item in assessment.findings
        ]
    except Exception as error:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_recorded_findings_invalid"
        ) from error
    expected_findings, expected_result = derive_lifecycle_findings(
        learning_change.operation,
        proposal.target_state,
        successor_binding,
        assessment.recorded_at,
    )
    if (
        [item.model_dump(mode="json") for item in stored_findings]
        != expected_findings
        or assessment.assessment_result != expected_result
    ):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_recorded_result_mismatch"
        )
    provenance = proposal.operator_provenance
    if assessment.payload_hash != assessment_payload_hash(assessment, provenance):
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_assessment_payload_hash_mismatch"
        )
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
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_recorded_event_invalid"
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
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_task_start_event_invalid"
        )
    if require_task_done:
        if task.completed_at is None:
            raise KnowledgeLifecycleAssessmentError(
                "knowledge_lifecycle_task_terminal_invalid"
            )
    elif task.completed_at is not None:
        raise KnowledgeLifecycleAssessmentError(
            "knowledge_lifecycle_task_terminal_invalid"
        )
    return assessment


class KnowledgeLifecycleAssessmentService:
    """Create one narrow lifecycle Task and record its immutable assessment."""

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
                raise KnowledgeLifecycleAssessmentError(
                    "knowledge_lifecycle_learning_change_missing"
                )
            task_id = _task_id(change.team_id, change.id)
            existing = session.get(Task, task_id)
            if existing is not None:
                try:
                    if existing.status == "done":
                        require_recorded_assessment(
                            session,
                            change,
                            self._snapshot_store,
                            self._session_factory,
                            require_task_done=True,
                            require_current=False,
                        )
                    elif existing.status == "running" and session.scalar(
                        select(KnowledgeLifecycleAssessment).where(
                            KnowledgeLifecycleAssessment.task_id == existing.id,
                            KnowledgeLifecycleAssessment.team_id == existing.team_id,
                        )
                    ) is not None:
                        require_recorded_assessment(
                            session,
                            change,
                            self._snapshot_store,
                            self._session_factory,
                            require_task_done=False,
                            require_current=True,
                        )
                    else:
                        validate_lifecycle_task_request(
                            session,
                            existing,
                            self._session_factory,
                            self._snapshot_store,
                            require_proposed=True,
                        )
                except KnowledgeLifecycleAssessmentError as error:
                    raise KnowledgeLifecycleAssessmentError(
                        "knowledge_lifecycle_existing_task_corrupt"
                    ) from error
                return existing.id
            if change.status != "proposed":
                raise KnowledgeLifecycleAssessmentError(
                    "knowledge_lifecycle_learning_change_not_proposed"
                )
            task_id, payload = build_lifecycle_task_request(
                session,
                self._session_factory,
                self._snapshot_store,
                change,
            )
            task = Task(
                id=task_id,
                team_id=change.team_id,
                task_type=TASK_TYPE,
                status="pending",
                attempt_count=0,
                policy_version=payload["policy_version"],
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

    def record(self, task_id: UUID) -> KnowledgeLifecycleAssessmentResult:
        with self._session_factory.begin() as session:
            task = session.scalar(
                select(Task).where(Task.id == task_id).with_for_update()
            )
            if task is None or task.status != "running":
                raise KnowledgeLifecycleAssessmentError(
                    "knowledge_lifecycle_task_not_running"
                )
            context = validate_lifecycle_task_request(
                session,
                task,
                self._session_factory,
                self._snapshot_store,
                require_proposed=True,
            )
            existing = session.scalar(
                select(KnowledgeLifecycleAssessment).where(
                    KnowledgeLifecycleAssessment.team_id == task.team_id,
                    KnowledgeLifecycleAssessment.learning_change_id
                    == context.proposal.learning_change.id,
                )
            )
            if existing is not None:
                verified = require_recorded_assessment(
                    session,
                    context.proposal.learning_change,
                    self._snapshot_store,
                    self._session_factory,
                    require_task_done=False,
                    require_current=True,
                )
                if (
                    verified.id != existing.id
                    or verified.task_id != task.id
                    or verified.task_attempt != task.attempt_count
                ):
                    raise KnowledgeLifecycleAssessmentError(
                        "knowledge_lifecycle_assessment_conflict"
                    )
                return KnowledgeLifecycleAssessmentResult(
                    assessment_id=verified.id,
                    assessment_result=verified.assessment_result,
                    assessment_payload_hash=verified.payload_hash,
                    recorded_at=verified.recorded_at,
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
                raise KnowledgeLifecycleAssessmentError(
                    "knowledge_lifecycle_task_start_event_invalid"
                )
            recorded_at = datetime.now(timezone.utc)
            findings, result = derive_lifecycle_findings(
                context.proposal.learning_change.operation,
                context.proposal.target_state,
                context.successor_binding,
                recorded_at,
            )
            successor = context.successor_binding
            assessment = KnowledgeLifecycleAssessment(
                id=uuid4(),
                team_id=task.team_id,
                task_id=task.id,
                task_attempt=task.attempt_count,
                learning_change_id=context.proposal.learning_change.id,
                operation=context.proposal.learning_change.operation,
                knowledge_item_id=context.proposal.target.id,
                current_learning_change_id=UUID(
                    context.proposal.target_state["current_learning_change_id"]
                ),
                target_content_version=context.proposal.target_state["version"],
                target_content_hash=context.proposal.target_content_hash,
                target_content_hash_scheme=KNOWLEDGE_CONTENT_HASH_SCHEME,
                target_state_hash=context.proposal.target_state_hash,
                proposal_hash=context.proposal.proposal_hash,
                proposed_state_hash=context.proposal.proposed_state_hash,
                evidence_basis_hash=context.proposal.evidence_basis_hash,
                evidence_refs=_normalize_json(
                    context.proposal.evidence_pack.evidence_basis
                ),
                assessment_version=ASSESSMENT_VERSION,
                operator_rationale=_normalize_json(context.proposal.rationale),
                findings=findings,
                assessment_result=result,
                variant_payload=(
                    {"successor_team_id": str(task.team_id)}
                    if successor is not None
                    else {}
                ),
                successor_knowledge_item_id=(
                    UUID(successor["successor_knowledge_item_id"])
                    if successor is not None
                    else None
                ),
                successor_current_learning_change_id=(
                    UUID(successor["successor_current_learning_change_id"])
                    if successor is not None
                    else None
                ),
                successor_content_version=(
                    successor["successor_content_version"]
                    if successor is not None
                    else None
                ),
                successor_content_hash=(
                    successor["successor_content_hash"]
                    if successor is not None
                    else None
                ),
                successor_content_hash_scheme=(
                    successor["successor_content_hash_scheme"]
                    if successor is not None
                    else None
                ),
                successor_status=(
                    successor["successor_status"]
                    if successor is not None
                    else None
                ),
                successor_review_after=(
                    datetime.fromisoformat(
                        successor["successor_review_after"].replace(
                            "Z", "+00:00"
                        )
                    )
                    if successor is not None
                    and successor["successor_review_after"] is not None
                    else None
                ),
                successor_state_hash=(
                    successor["successor_state_hash"]
                    if successor is not None
                    else None
                ),
                idempotency_key=context.request_payload["idempotency_key"],
                request_hash=context.request_payload["request_hash"],
                request_event_id=context.request_event.id,
                request_event_payload_hash=_sha256_json(
                    context.request_payload
                ),
                recorded_event_id=uuid4(),
                recorded_at=recorded_at,
                payload_hash="",
            )
            assessment.payload_hash = assessment_payload_hash(
                assessment, context.proposal.operator_provenance
            )
            session.add(
                Event(
                    id=assessment.recorded_event_id,
                    task_id=task.id,
                    type=RECORDED_EVENT_TYPE,
                    payload=recorded_assessment_event_payload(assessment),
                    created_at=recorded_at,
                )
            )
            session.flush()
            session.add(assessment)
            session.flush()
            return KnowledgeLifecycleAssessmentResult(
                assessment_id=assessment.id,
                assessment_result=assessment.assessment_result,
                assessment_payload_hash=assessment.payload_hash,
                recorded_at=assessment.recorded_at,
            )
