"""Evidence lineage and typed knowledge-quality assessments for R7-A."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.experience_distiller import (
    ExperienceDistiller,
    ExperienceDistillerError,
    ExperienceEvidencePack,
)
from core.models import (
    Event,
    KnowledgeQualityAssessment,
    LearningChange,
    Outcome,
    Plan,
    PlanAction,
    Signal,
    Task,
    Team,
)
from core.snapshot_store import SnapshotStore


RUBRIC_IDENTITY = "watch.r7a.knowledge-quality"
RUBRIC_REVISION = "1"
EVALUATOR_KIND = "model"
EVALUATOR_IDENTITY = "watch.r7a.knowledge-quality"
EVALUATOR_REVISION = "1"
TASK_TYPE = "assess_knowledge_quality"
REQUEST_EVENT_TYPE = "knowledge_quality_assessment_task_requested"
RECORDED_EVENT_TYPE = "knowledge_quality_assessment_recorded"
ALLOWED_WRITES = ["KnowledgeQualityAssessment"]
TASK_BUDGET = {
    "max_tool_calls": 0,
    "max_cost_usd": 0.0,
    "deadline_seconds": 30,
}
TASK_MAX_ATTEMPTS = 3
_TASK_ID_NAMESPACE = UUID("f15af579-4f1d-5ed9-8c7a-7d1d5e6c30c7")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

DIMENSIONS = (
    "evidence_fidelity",
    "case_coverage_relationship",
    "contradiction_handling",
    "applicability_boundaries",
    "uncertainty_calibration",
    "specificity_actionability",
    "novelty_overlap",
)
DISPOSITIONS = frozenset(
    {"supported", "limited", "contradicted", "insufficient_evidence"}
)


class KnowledgeQualityAssessmentError(ValueError):
    """A knowledge-quality assessment failed deterministic validation."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class KnowledgeQualityConflict(KnowledgeQualityAssessmentError):
    """An assessment or idempotency key conflicts with durable state."""


class KnowledgeQualityDimension(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    disposition: Literal[
        "supported", "limited", "contradicted", "insufficient_evidence"
    ]
    findings: list[str] = Field(min_length=1, max_length=8)
    evidence_refs: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("findings")
    @classmethod
    def nonblank_findings(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() if isinstance(value, str) else value for value in values]
        if any(not isinstance(value, str) or not value for value in normalized):
            raise ValueError("knowledge_quality_finding_required")
        return normalized

    @field_validator("evidence_refs")
    @classmethod
    def unique_nonblank_references(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() if isinstance(value, str) else value for value in values]
        if any(not isinstance(value, str) or not value for value in normalized):
            raise ValueError("knowledge_quality_evidence_reference_required")
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate_knowledge_quality_evidence_reference")
        return normalized


class KnowledgeQualityAssessmentDraft(BaseModel):
    """Untrusted assessment proposal; lineage/evaluator identity are application-owned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    learning_change_id: UUID
    proposal_hash: str
    evidence_basis_hash: str
    rubric_identity: str
    rubric_revision: str
    dimensions: dict[str, KnowledgeQualityDimension] = Field(
        min_length=7, max_length=7
    )
    narrative: str = Field(min_length=1, max_length=4000)

    @field_validator(
        "proposal_hash",
        "evidence_basis_hash",
    )
    @classmethod
    def valid_sha256(cls, value: str) -> str:
        if not _HASH_RE.fullmatch(value):
            raise ValueError("knowledge_quality_hash_invalid")
        return value

    @field_validator("rubric_identity", "rubric_revision", "narrative")
    @classmethod
    def nonblank_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("knowledge_quality_value_required")
        return normalized

    @field_validator("dimensions")
    @classmethod
    def exact_dimensions(
        cls, value: dict[str, KnowledgeQualityDimension]
    ) -> dict[str, KnowledgeQualityDimension]:
        if set(value) != set(DIMENSIONS):
            raise ValueError("knowledge_quality_dimensions_invalid")
        return value


@dataclass(frozen=True)
class KnowledgeQualityAssessmentResult:
    assessment_id: UUID
    status: str
    assessment_payload_hash: str
    recorded_at: datetime
    replayed: bool = False


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_uuid(value: object) -> str | None:
    if not isinstance(value, str) or not _UUID_RE.fullmatch(value):
        return None
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return value if str(parsed) == value else None


def _complete_snapshot(ref: object, digest: object) -> bool:
    if not isinstance(ref, str) or not isinstance(digest, str):
        return False
    if not ref.startswith("snap://sha256/") or not _HASH_RE.fullmatch(digest):
        return False
    return ref.rsplit("/", 1)[-1] == digest.removeprefix("sha256:")


def build_case_lineage_report(
    session: Session,
    team_id: UUID,
    evidence_basis: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify pairs from canonical source lineage, never worker-provided labels."""
    if not isinstance(evidence_basis, list) or not evidence_basis or len(evidence_basis) > 8:
        raise KnowledgeQualityAssessmentError("knowledge_quality_evidence_basis_invalid")

    cases: list[dict[str, Any]] = []
    seen_tasks: set[str] = set()
    for basis in evidence_basis:
        if not isinstance(basis, dict):
            raise KnowledgeQualityAssessmentError("knowledge_quality_evidence_case_invalid")
        evaluation_id = _canonical_uuid(basis.get("evaluation_id"))
        outcome_id = _canonical_uuid(basis.get("outcome_id"))
        source_task_id = _canonical_uuid(basis.get("source_task_id"))
        provenance = basis.get("source_task_provenance")
        evidence_links = basis.get("evidence_links")
        if (
            evaluation_id is None
            or outcome_id is None
            or source_task_id is None
            or not isinstance(provenance, dict)
            or not isinstance(evidence_links, list)
            or source_task_id in seen_tasks
        ):
            raise KnowledgeQualityAssessmentError("knowledge_quality_evidence_case_invalid")
        seen_tasks.add(source_task_id)
        source_task = session.get(Task, UUID(source_task_id))
        if source_task is None or source_task.team_id != team_id:
            raise KnowledgeQualityAssessmentError("knowledge_quality_source_task_invalid")

        snapshot_anchors: set[str] = set()
        related_anchors: set[str] = set()
        incomplete = False
        for link in evidence_links:
            if not isinstance(link, dict):
                incomplete = True
                continue
            source_kind = link.get("source_kind")
            source_id: str | None = None
            if source_kind == "outcome":
                source_id = _canonical_uuid(link.get("outcome_id"))
                if source_id is None:
                    incomplete = True
                    continue
                # The case's primary Outcome is not an upstream independence anchor.
                if source_id == outcome_id:
                    continue
                source = session.get(Outcome, UUID(source_id))
                if (
                    source is None
                    or source.team_id != team_id
                    or not _complete_snapshot(
                        source.observation_snapshot_ref, source.observation_hash
                    )
                ):
                    incomplete = True
                    continue
                related_anchors.add(f"outcome:{source_id}")
                snapshot_anchors.add(f"snapshot:{source.observation_hash}")
                link_ref = link.get("snapshot_ref")
                link_hash = link.get("snapshot_hash")
                if (link_ref is None) != (link_hash is None) or (
                    link_ref is not None and not _complete_snapshot(link_ref, link_hash)
                ):
                    incomplete = True
                elif link_ref is not None and (
                    link_ref != source.observation_snapshot_ref
                    or link_hash != source.observation_hash
                ):
                    incomplete = True
                elif isinstance(link_hash, str):
                    snapshot_anchors.add(f"snapshot:{link_hash}")
            elif source_kind == "signal":
                source_id = _canonical_uuid(link.get("signal_id"))
                if source_id is None:
                    incomplete = True
                    continue
                signal = session.get(Signal, UUID(source_id))
                team = session.get(Team, team_id)
                if (
                    signal is None
                    or team is None
                    or signal.domain != team.domain
                    or not _complete_snapshot(signal.snapshot_ref, signal.content_hash)
                ):
                    incomplete = True
                    continue
                related_anchors.add(f"signal:{source_id}")
                snapshot_anchors.add(f"snapshot:{signal.content_hash}")
                link_ref = link.get("snapshot_ref")
                link_hash = link.get("snapshot_hash")
                if (link_ref is None) != (link_hash is None) or (
                    link_ref is not None and not _complete_snapshot(link_ref, link_hash)
                ):
                    incomplete = True
                elif link_ref is not None and (
                    link_ref != signal.snapshot_ref
                    or link_hash != signal.content_hash
                ):
                    incomplete = True
                elif isinstance(link_hash, str):
                    snapshot_anchors.add(f"snapshot:{link_hash}")
            else:
                incomplete = True

        plan_action_anchor: str | None = None
        if (source_task.plan_id is None) != (source_task.plan_action_id is None):
            incomplete = True
        elif source_task.plan_id is not None and source_task.plan_action_id is not None:
            plan = session.get(Plan, source_task.plan_id)
            action = session.get(
                PlanAction, (source_task.plan_id, source_task.plan_action_id)
            )
            if (
                plan is None
                or plan.team_id != team_id
                or action is None
                or action.plan_id != source_task.plan_id
                or action.action_id != source_task.plan_action_id
            ):
                incomplete = True
            else:
                plan_action_anchor = (
                    f"plan_action:{source_task.plan_id}:{source_task.plan_action_id}"
                )

        cases.append(
            {
                "evaluation_id": evaluation_id,
                "outcome_id": outcome_id,
                "source_task_id": source_task_id,
                "snapshot_anchors": sorted(snapshot_anchors),
                "related_anchors": sorted(related_anchors),
                "plan_action_anchor": plan_action_anchor,
                "lineage_complete": bool(snapshot_anchors) and not incomplete,
            }
        )

    cases.sort(key=lambda item: item["evaluation_id"])
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(cases):
        for right in cases[left_index + 1 :]:
            shared = sorted(
                set(left["related_anchors"]) & set(right["related_anchors"])
            )
            shared_snapshots = sorted(
                set(left["snapshot_anchors"]) & set(right["snapshot_anchors"])
            )
            shared_plan_action = (
                left["plan_action_anchor"]
                if left["plan_action_anchor"] is not None
                and left["plan_action_anchor"] == right["plan_action_anchor"]
                else None
            )
            shared_reasons = (
                shared
                + shared_snapshots
                + ([shared_plan_action] if shared_plan_action is not None else [])
            )
            if shared_reasons:
                relationship = "related"
            elif (
                not left["lineage_complete"]
                or not right["lineage_complete"]
            ):
                relationship = "unknown"
            else:
                relationship = "independent"
            pairs.append(
                {
                    "left_evaluation_id": left["evaluation_id"],
                    "right_evaluation_id": right["evaluation_id"],
                    "relationship": relationship,
                    "shared_anchor_reasons": shared_reasons,
                }
            )

    return {
        "schema_version": "r7a-case-lineage-v1",
        "cases": cases,
        "pairs": pairs,
    }


def evidence_reference_set(
    learning_change: LearningChange,
    pack: ExperienceEvidencePack,
) -> frozenset[str]:
    """Build the assessment's allowed evidence keys from verified canonical basis."""
    references: set[str] = set()
    evidence_basis = (
        pack if isinstance(pack, list) else pack.evidence_basis
    )
    for item in evidence_basis:
        evaluation_id = _canonical_uuid(item.get("evaluation_id"))
        outcome_id = _canonical_uuid(item.get("outcome_id"))
        source_task_id = _canonical_uuid(item.get("source_task_id"))
        if not all((evaluation_id, outcome_id, source_task_id)):
            raise KnowledgeQualityAssessmentError("knowledge_quality_reference_basis_invalid")
        references.update(
            {
                f"evaluation:{evaluation_id}",
                f"outcome:{outcome_id}",
                f"source_task:{source_task_id}",
            }
        )
        for digest in (item.get("outcome_snapshot_hash"), item.get("evaluation_task_snapshot_hash")):
            if isinstance(digest, str) and _HASH_RE.fullmatch(digest):
                references.add(f"snapshot:{digest}")
        for link in item.get("evidence_links", []):
            if not isinstance(link, dict):
                raise KnowledgeQualityAssessmentError("knowledge_quality_reference_basis_invalid")
            reference_key = link.get("reference_key")
            source_kind = link.get("source_kind")
            source_id = (
                _canonical_uuid(link.get("outcome_id"))
                if source_kind == "outcome"
                else _canonical_uuid(link.get("signal_id"))
                if source_kind == "signal"
                else None
            )
            if not isinstance(reference_key, str) or not reference_key:
                raise KnowledgeQualityAssessmentError("knowledge_quality_reference_basis_invalid")
            references.add(f"evidence_link:{reference_key}")
            if source_id is not None:
                references.add(f"{source_kind}:{source_id}")
            digest = link.get("snapshot_hash")
            if isinstance(digest, str) and _HASH_RE.fullmatch(digest):
                references.add(f"snapshot:{digest}")
    return frozenset(references)


def quality_task_id(
    team_id: UUID,
    learning_change_id: UUID,
) -> UUID:
    key = (
        f"{team_id}:{learning_change_id}:{RUBRIC_IDENTITY}:"
        f"{RUBRIC_REVISION}:{EVALUATOR_IDENTITY}:{EVALUATOR_REVISION}"
    )
    return uuid5(_TASK_ID_NAMESPACE, key)


def quality_request_payload(
    *,
    task_id: UUID,
    team_id: UUID,
    learning_change: LearningChange,
    lineage_report: dict[str, Any],
    policy_version: int,
) -> dict[str, Any]:
    proposal_hash = learning_change.proposed_state.get("proposal_hash")
    if not isinstance(proposal_hash, str) or not _HASH_RE.fullmatch(proposal_hash):
        raise KnowledgeQualityAssessmentError("learning_change_proposal_hash_invalid")
    if not _HASH_RE.fullmatch(learning_change.evidence_basis_hash):
        raise KnowledgeQualityAssessmentError("learning_change_evidence_hash_invalid")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "task_type": TASK_TYPE,
        "task_id": str(task_id),
        "team_id": str(team_id),
        "learning_change_id": str(learning_change.id),
        "proposed_by_task_id": str(learning_change.proposed_by_task_id),
        "proposal_hash": proposal_hash,
        "evidence_basis_hash": learning_change.evidence_basis_hash,
        "rubric_identity": RUBRIC_IDENTITY,
        "rubric_revision": RUBRIC_REVISION,
        "evaluator_kind": EVALUATOR_KIND,
        "evaluator_identity": EVALUATOR_IDENTITY,
        "evaluator_revision": EVALUATOR_REVISION,
        "lineage_report_hash": sha256_json(lineage_report),
        "policy_version": policy_version,
    }
    payload["idempotency_key"] = (
        "r7a-quality-v1:" + sha256_json(payload).removeprefix("sha256:")
    )
    payload["request_fingerprint"] = sha256_json(payload)
    return payload



def build_quality_task_request(
    session: Session,
    source_task: Task,
    learning_change: LearningChange,
    *,
    require_proposed: bool = True,
) -> tuple[UUID, dict[str, Any]]:
    if (
        source_task.task_type != "propose_learning_change"
        or source_task.status != "done"
        or source_task.completed_at is None
        or source_task.allowed_writes != ["LearningChange"]
        or source_task.team_id != learning_change.team_id
        or learning_change.proposed_by_task_id != source_task.id
        or (require_proposed and learning_change.status != "proposed")
        or (not require_proposed and learning_change.status not in {"proposed", "accepted", "rejected"})
        or learning_change.operation != "create"
        or learning_change.target_kind != "knowledge_item"
        or learning_change.target_id is not None
    ):
        raise KnowledgeQualityAssessmentError("knowledge_quality_source_proposal_invalid")
    lineage = build_case_lineage_report(
        session, learning_change.team_id, learning_change.evidence_basis
    )
    task_id = quality_task_id(source_task.team_id, learning_change.id)
    payload = quality_request_payload(
        task_id=task_id,
        team_id=source_task.team_id,
        learning_change=learning_change,
        lineage_report=lineage,
        policy_version=source_task.policy_version,
    )
    return task_id, payload


def validate_quality_task_request(
    session: Session,
    task: Task,
    *,
    require_proposed: bool,
) -> dict[str, Any]:
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
        or (task.completed_at is not None and task.status != "done")
    ):
        raise KnowledgeQualityAssessmentError("knowledge_quality_task_shape_invalid")
    events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
    )
    if len(events) != 1 or not isinstance(events[0].payload, dict):
        raise KnowledgeQualityAssessmentError("knowledge_quality_task_request_event_invalid")
    payload = events[0].payload
    try:
        learning_change_id = UUID(payload.get("learning_change_id"))
    except (TypeError, ValueError) as error:
        raise KnowledgeQualityAssessmentError("knowledge_quality_task_target_invalid") from error
    learning_change = session.scalar(
        select(LearningChange).where(
            LearningChange.id == learning_change_id,
            LearningChange.team_id == task.team_id,
        )
    )
    if (
        learning_change is None
        or learning_change.operation != "create"
        or learning_change.target_kind != "knowledge_item"
        or learning_change.target_id is not None
        or learning_change.proposed_by_task_id is None
        or learning_change.status not in {"proposed", "accepted", "rejected"}
        or (require_proposed and learning_change.status != "proposed")
    ):
        raise KnowledgeQualityAssessmentError("knowledge_quality_learning_change_invalid")
    source_task = session.get(Task, learning_change.proposed_by_task_id)
    if (
        source_task is None
        or source_task.team_id != task.team_id
        or source_task.task_type != "propose_learning_change"
        or source_task.status != "done"
        or source_task.completed_at is None
        or source_task.policy_version != task.policy_version
        or source_task.allowed_writes != ["LearningChange"]
    ):
        raise KnowledgeQualityAssessmentError("knowledge_quality_source_task_invalid")
    task_id, expected = build_quality_task_request(
        session, source_task, learning_change, require_proposed=require_proposed
    )
    if task.id != task_id or task.team_id != learning_change.team_id:
        raise KnowledgeQualityAssessmentError("knowledge_quality_task_identity_invalid")
    if task.policy_version != source_task.policy_version:
        raise KnowledgeQualityAssessmentError("knowledge_quality_task_policy_mismatch")
    if payload != expected:
        raise KnowledgeQualityAssessmentError("knowledge_quality_task_request_mismatch")
    proposal_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == source_task.id,
                Event.type == "learning_change_proposed",
            )
        )
    )
    if len(proposal_events) != 1:
        raise KnowledgeQualityAssessmentError("knowledge_quality_proposal_event_missing")
    proposal = proposal_events[0].payload
    if (
        not isinstance(proposal, dict)
        or proposal.get("learning_change_id") != str(learning_change.id)
        or proposal.get("proposal_hash")
        != learning_change.proposed_state.get("proposal_hash")
        or proposal.get("evidence_basis_hash") != learning_change.evidence_basis_hash
    ):
        raise KnowledgeQualityAssessmentError("knowledge_quality_proposal_event_mismatch")
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
        len(terminal_events) != 1
        or terminal_events[0].payload.get("result_category")
        != "success_learning_change_proposed"
        or terminal_events[0].payload.get("learning_change_id")
        != str(learning_change.id)
        or len(source_outcomes) != 1
    ):
        raise KnowledgeQualityAssessmentError("knowledge_quality_source_terminal_invalid")
    return payload


def require_recorded_assessment(
    session: Session,
    learning_change: LearningChange,
    *,
    require_task_done: bool = True,
) -> KnowledgeQualityAssessment:
    assessments = list(
        session.scalars(
            select(KnowledgeQualityAssessment)
            .where(
                KnowledgeQualityAssessment.learning_change_id == learning_change.id,
                KnowledgeQualityAssessment.team_id == learning_change.team_id,
            )
            .with_for_update()
        )
    )
    if len(assessments) != 1:
        raise KnowledgeQualityAssessmentError("knowledge_quality_assessment_required")
    assessment = assessments[0]
    task = session.get(Task, assessment.creating_task_id)
    expected_statuses = {"done"} if require_task_done else {"running", "done"}
    if (
        task is None
        or task.team_id != learning_change.team_id
        or task.status not in expected_statuses
        or (task.completed_at is None and task.status == "done")
        or assessment.status != "recorded"
        or task.task_type != TASK_TYPE
        or task.allowed_writes != ALLOWED_WRITES
        or task.objective_id is not None
        or task.plan_id is not None
        or task.plan_action_id is not None
        or task.max_attempts != TASK_MAX_ATTEMPTS
        or task.budget != TASK_BUDGET
        or assessment.proposal_hash
        != learning_change.proposed_state.get("proposal_hash")
        or assessment.evidence_basis_hash != learning_change.evidence_basis_hash
        or assessment.rubric_identity != RUBRIC_IDENTITY
        or assessment.rubric_revision != RUBRIC_REVISION
        or assessment.evaluator_kind != EVALUATOR_KIND
        or assessment.evaluator_identity != EVALUATOR_IDENTITY
        or assessment.evaluator_revision != EVALUATOR_REVISION
        or assessment.assessment_payload_hash
        != assessment_payload_hash(assessment_payload_from_row(assessment))
        or assessment.lineage_report_hash != sha256_json(assessment.lineage_report)
    ):
        raise KnowledgeQualityAssessmentError("knowledge_quality_assessment_binding_invalid")
    try:
        stored_draft = KnowledgeQualityAssessmentDraft(
            learning_change_id=assessment.learning_change_id,
            proposal_hash=assessment.proposal_hash,
            evidence_basis_hash=assessment.evidence_basis_hash,
            rubric_identity=assessment.rubric_identity,
            rubric_revision=assessment.rubric_revision,
            dimensions=assessment.dimensions,
            narrative=assessment.narrative,
        )
        allowed_references = evidence_reference_set(
            learning_change, learning_change.evidence_basis
        )
        validated_dimensions = validate_dimension_draft(
            stored_draft, allowed_references
        )
    except (ValidationError, KnowledgeQualityAssessmentError) as error:
        raise KnowledgeQualityAssessmentError(
            "knowledge_quality_assessment_payload_invalid"
        ) from error
    if validated_dimensions != assessment.dimensions:
        raise KnowledgeQualityAssessmentError(
            "knowledge_quality_assessment_dimensions_mismatch"
        )
    referenced_keys = sorted(
        {
            reference
            for dimension in validated_dimensions.values()
            for reference in dimension["evidence_refs"]
        }
    )
    if assessment.evidence_reference_hash != sha256_json(referenced_keys):
        raise KnowledgeQualityAssessmentError(
            "knowledge_quality_assessment_reference_hash_mismatch"
        )

    request = validate_quality_task_request(session, task, require_proposed=False)
    if (
        request.get("learning_change_id") != str(learning_change.id)
        or request.get("proposal_hash") != assessment.proposal_hash
        or request.get("evidence_basis_hash") != assessment.evidence_basis_hash
        or request.get("lineage_report_hash") != assessment.lineage_report_hash
    ):
        raise KnowledgeQualityAssessmentError("knowledge_quality_assessment_request_mismatch")
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
        raise KnowledgeQualityAssessmentError(
            "knowledge_quality_assessment_task_start_event_invalid"
        )
    recorded = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == RECORDED_EVENT_TYPE,
            )
        )
    )
    if (
        len(recorded) != 1
        or recorded[0].payload != recorded_assessment_event_payload(assessment)
        or recorded[0].created_at != assessment.recorded_at
    ):
        raise KnowledgeQualityAssessmentError("knowledge_quality_assessment_record_event_invalid")
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
            len(terminal) != 1
            or len(outcomes) != 1
            or terminal[0].payload.get("result_category")
            != "success_knowledge_quality_assessed"
            or terminal[0].payload.get("knowledge_quality_assessment_id")
            != str(assessment.id)
            or terminal[0].payload.get("outcome_id") != str(outcomes[0].id)
            or terminal[0].payload.get("to_status") != "done"
            or terminal[0].payload.get("attempt_count") != task.attempt_count
            or outcomes[0].recorded_by_task_id != task.id
            or outcomes[0].observed_at is None
            or task.completed_at != outcomes[0].observed_at
        ):
            raise KnowledgeQualityAssessmentError("knowledge_quality_assessment_task_incomplete")
    elif terminal or outcomes:
        raise KnowledgeQualityAssessmentError("knowledge_quality_assessment_task_already_terminal")
    return assessment


def validate_dimension_draft(
    draft: KnowledgeQualityAssessmentDraft,
    allowed_references: frozenset[str],
) -> dict[str, Any]:
    if set(draft.dimensions) != set(DIMENSIONS):
        raise KnowledgeQualityAssessmentError("knowledge_quality_dimensions_invalid")
    dimensions: dict[str, Any] = {}
    for name in DIMENSIONS:
        dimension = draft.dimensions[name]
        if dimension.disposition not in DISPOSITIONS:
            raise KnowledgeQualityAssessmentError("knowledge_quality_disposition_invalid")
        if any(ref not in allowed_references for ref in dimension.evidence_refs):
            raise KnowledgeQualityAssessmentError("knowledge_quality_reference_not_in_basis")
        if (
            dimension.disposition != "insufficient_evidence"
            and not dimension.evidence_refs
        ):
            raise KnowledgeQualityAssessmentError("knowledge_quality_evidence_reference_required")
        if name == "novelty_overlap" and (
            dimension.disposition != "insufficient_evidence"
            or dimension.evidence_refs
        ):
            raise KnowledgeQualityAssessmentError(
                "knowledge_quality_novelty_requires_validated_knowledge_item"
            )
        dimensions[name] = dimension.model_dump(mode="json")
    return dimensions


def assessment_payload_hash(payload: dict[str, Any]) -> str:
    return sha256_json(payload)


def recorded_assessment_event_payload(
    assessment: KnowledgeQualityAssessment,
) -> dict[str, Any]:
    return {
        "assessment_id": str(assessment.id),
        "learning_change_id": str(assessment.learning_change_id),
        "proposal_hash": assessment.proposal_hash,
        "evidence_basis_hash": assessment.evidence_basis_hash,
        "rubric_identity": assessment.rubric_identity,
        "rubric_revision": assessment.rubric_revision,
        "lineage_report_hash": assessment.lineage_report_hash,
        "evidence_reference_hash": assessment.evidence_reference_hash,
        "assessment_payload_hash": assessment.assessment_payload_hash,
        "evaluator_kind": assessment.evaluator_kind,
        "evaluator_identity": assessment.evaluator_identity,
        "evaluator_revision": assessment.evaluator_revision,
    }


def assessment_record_payload(
    *,
    task_id: UUID,
    team_id: UUID,
    learning_change_id: UUID,
    proposal_hash: str,
    evidence_basis_hash: str,
    rubric_identity: str,
    rubric_revision: str,
    evaluator_kind: str,
    evaluator_identity: str,
    evaluator_revision: str,
    dimensions: dict[str, Any],
    narrative: str,
    lineage_report: dict[str, Any],
    evidence_reference_hash: str,
    idempotency_key: str,
) -> dict[str, Any]:
    return {
        "creating_task_id": str(task_id),
        "team_id": str(team_id),
        "learning_change_id": str(learning_change_id),
        "proposal_hash": proposal_hash,
        "evidence_basis_hash": evidence_basis_hash,
        "rubric_identity": rubric_identity,
        "rubric_revision": rubric_revision,
        "evaluator_kind": evaluator_kind,
        "evaluator_identity": evaluator_identity,
        "evaluator_revision": evaluator_revision,
        "dimensions": dimensions,
        "narrative": narrative,
        "lineage_report": lineage_report,
        "lineage_report_hash": sha256_json(lineage_report),
        "evidence_reference_hash": evidence_reference_hash,
        "idempotency_key": idempotency_key,
    }


def assessment_payload_from_row(
    assessment: KnowledgeQualityAssessment,
) -> dict[str, Any]:
    return assessment_record_payload(
        task_id=assessment.creating_task_id,
        team_id=assessment.team_id,
        learning_change_id=assessment.learning_change_id,
        proposal_hash=assessment.proposal_hash,
        evidence_basis_hash=assessment.evidence_basis_hash,
        rubric_identity=assessment.rubric_identity,
        rubric_revision=assessment.rubric_revision,
        evaluator_kind=assessment.evaluator_kind,
        evaluator_identity=assessment.evaluator_identity,
        evaluator_revision=assessment.evaluator_revision,
        dimensions=assessment.dimensions,
        narrative=assessment.narrative,
        lineage_report=assessment.lineage_report,
        evidence_reference_hash=assessment.evidence_reference_hash,
        idempotency_key=assessment.idempotency_key,
    )


def require_recorded_assessment(
    session: Session,
    learning_change: LearningChange,
) -> KnowledgeQualityAssessment:
    assessments = list(
        session.scalars(
            select(KnowledgeQualityAssessment)
            .where(
                KnowledgeQualityAssessment.learning_change_id == learning_change.id,
                KnowledgeQualityAssessment.team_id == learning_change.team_id,
            )
            .with_for_update()
        )
    )
    if len(assessments) != 1:
        raise KnowledgeQualityAssessmentError("knowledge_quality_assessment_required")
    assessment = assessments[0]
    task = session.get(Task, assessment.creating_task_id)
    if (
        task is None
        or task.team_id != learning_change.team_id
        or task.task_type != TASK_TYPE
        or task.status != "done"
        or task.completed_at is None
        or task.allowed_writes != ALLOWED_WRITES
        or task.objective_id is not None
        or task.plan_id is not None
        or task.plan_action_id is not None
        or task.max_attempts != TASK_MAX_ATTEMPTS
        or task.budget != TASK_BUDGET
        or assessment.proposal_hash
        != learning_change.proposed_state.get("proposal_hash")
        or assessment.evidence_basis_hash != learning_change.evidence_basis_hash
        or assessment.rubric_identity != RUBRIC_IDENTITY
        or assessment.rubric_revision != RUBRIC_REVISION
        or assessment.evaluator_kind != EVALUATOR_KIND
        or assessment.evaluator_identity != EVALUATOR_IDENTITY
        or assessment.evaluator_revision != EVALUATOR_REVISION
        or assessment.assessment_payload_hash
        != assessment_payload_hash(assessment_payload_from_row(assessment))
        or assessment.lineage_report_hash != sha256_json(assessment.lineage_report)
    ):
        raise KnowledgeQualityAssessmentError("knowledge_quality_assessment_binding_invalid")
    requested = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
    )
    recorded = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == RECORDED_EVENT_TYPE,
            )
        )
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
    if (
        len(requested) != 1
        or requested[0].payload.get("learning_change_id") != str(learning_change.id)
        or requested[0].payload.get("proposal_hash") != assessment.proposal_hash
        or requested[0].payload.get("evidence_basis_hash") != assessment.evidence_basis_hash
        or len(recorded) != 1
        or recorded[0].payload != recorded_assessment_event_payload(assessment)
        or len(terminal) != 1
        or terminal[0].payload.get("result_category")
        != "success_knowledge_quality_assessed"
        or terminal[0].payload.get("knowledge_quality_assessment_id")
        != str(assessment.id)
        or len(outcomes) != 1
        or terminal[0].payload.get("outcome_id") != str(outcomes[0].id)
        or outcomes[0].recorded_by_task_id != task.id
        or outcomes[0].observed_at is None
        or task.completed_at != outcomes[0].observed_at
    ):
        raise KnowledgeQualityAssessmentError("knowledge_quality_assessment_task_incomplete")
    return assessment


class KnowledgeQualityAssessmentService:
    """Revalidate canonical evidence and record one immutable assessment."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store
        self._distiller = ExperienceDistiller(
            session_factory, snapshot_store, provider=None
        )

    def record(
        self,
        task_id: UUID,
        draft: KnowledgeQualityAssessmentDraft,
    ) -> KnowledgeQualityAssessmentResult:
        from core.task_runtime import TaskNotFinalizable, TaskRuntime

        with self._session_factory.begin() as session:
            task = session.scalar(
                select(Task).where(Task.id == task_id).with_for_update()
            )
            if task is None:
                raise KnowledgeQualityAssessmentError("knowledge_quality_task_not_found")
            if (
                task.task_type != TASK_TYPE
                or task.status != "running"
                or task.allowed_writes != ALLOWED_WRITES
                or task.objective_id is not None
                or task.plan_id is not None
                or task.plan_action_id is not None
                or task.max_attempts != TASK_MAX_ATTEMPTS
                or task.budget != TASK_BUDGET
            ):
                raise KnowledgeQualityAssessmentError("knowledge_quality_task_not_eligible")
            try:
                request = TaskRuntime._validate_knowledge_quality_task_request(
                    session, task, require_proposed=True
                )
            except TaskNotFinalizable as error:
                raise KnowledgeQualityAssessmentError(str(error)) from error

            learning_change_id = UUID(request["learning_change_id"])
            learning_change = session.scalar(
                select(LearningChange)
                .where(
                    LearningChange.id == learning_change_id,
                    LearningChange.team_id == task.team_id,
                )
                .with_for_update()
            )
            if learning_change is None or learning_change.status != "proposed":
                raise KnowledgeQualityAssessmentError("learning_change_not_proposed")
            if (
                draft.learning_change_id != learning_change.id
                or draft.proposal_hash != request["proposal_hash"]
                or draft.evidence_basis_hash != request["evidence_basis_hash"]
                or draft.rubric_identity != request["rubric_identity"]
                or draft.rubric_revision != request["rubric_revision"]
            ):
                raise KnowledgeQualityAssessmentError("knowledge_quality_draft_request_mismatch")

            try:
                _, pack = self._distiller.validate_learning_change(
                    session, learning_change
                )
            except ExperienceDistillerError as error:
                raise KnowledgeQualityAssessmentError(error.reason) from error
            if pack.basis_hash != learning_change.evidence_basis_hash:
                raise KnowledgeQualityAssessmentError("knowledge_quality_evidence_basis_stale")
            lineage = build_case_lineage_report(
                session, task.team_id, pack.evidence_basis
            )
            if sha256_json(lineage) != request["lineage_report_hash"]:
                raise KnowledgeQualityAssessmentError("knowledge_quality_lineage_report_mismatch")
            allowed_references = evidence_reference_set(learning_change, pack)
            dimensions = validate_dimension_draft(draft, allowed_references)
            used_references = sorted(
                {
                    reference
                    for dimension in dimensions.values()
                    for reference in dimension["evidence_refs"]
                }
            )
            evidence_reference_hash = sha256_json(used_references)
            payload = assessment_record_payload(
                task_id=task.id,
                team_id=task.team_id,
                learning_change_id=learning_change.id,
                proposal_hash=request["proposal_hash"],
                evidence_basis_hash=request["evidence_basis_hash"],
                rubric_identity=request["rubric_identity"],
                rubric_revision=request["rubric_revision"],
                evaluator_kind=request["evaluator_kind"],
                evaluator_identity=request["evaluator_identity"],
                evaluator_revision=request["evaluator_revision"],
                dimensions=dimensions,
                narrative=draft.narrative,
                lineage_report=lineage,
                evidence_reference_hash=evidence_reference_hash,
                idempotency_key=request["idempotency_key"],
            )
            payload_hash = assessment_payload_hash(payload)
            prior = session.scalar(
                select(KnowledgeQualityAssessment)
                .where(
                    KnowledgeQualityAssessment.learning_change_id
                    == learning_change.id
                )
                .with_for_update()
            )
            if prior is not None:
                if (
                    prior.creating_task_id == task.id
                    and prior.idempotency_key == request["idempotency_key"]
                    and prior.assessment_payload_hash == payload_hash
                ):
                    return KnowledgeQualityAssessmentResult(
                        assessment_id=prior.id,
                        status="recorded",
                        assessment_payload_hash=prior.assessment_payload_hash,
                        recorded_at=prior.recorded_at,
                        replayed=True,
                    )
                raise KnowledgeQualityConflict("knowledge_quality_assessment_already_recorded")

            assessment = KnowledgeQualityAssessment(
                id=uuid4(),
                team_id=task.team_id,
                learning_change_id=learning_change.id,
                creating_task_id=task.id,
                proposal_hash=request["proposal_hash"],
                evidence_basis_hash=request["evidence_basis_hash"],
                rubric_identity=request["rubric_identity"],
                rubric_revision=request["rubric_revision"],
                evaluator_kind=request["evaluator_kind"],
                evaluator_identity=request["evaluator_identity"],
                evaluator_revision=request["evaluator_revision"],
                dimensions=dimensions,
                narrative=draft.narrative,
                lineage_report=lineage,
                lineage_report_hash=sha256_json(lineage),
                evidence_reference_hash=evidence_reference_hash,
                assessment_payload_hash=payload_hash,
                idempotency_key=request["idempotency_key"],
                recorded_at=datetime.now(timezone.utc),
            )
            session.add(assessment)
            session.flush()
            session.add(
                Event(
                    id=uuid4(),
                    task_id=task.id,
                    type=RECORDED_EVENT_TYPE,
                    payload=recorded_assessment_event_payload(assessment),
                    created_at=assessment.recorded_at,
                )
            )
            session.flush()
            return KnowledgeQualityAssessmentResult(
                assessment_id=assessment.id,
                status="recorded",
                assessment_payload_hash=assessment.assessment_payload_hash,
                recorded_at=assessment.recorded_at,
            )
