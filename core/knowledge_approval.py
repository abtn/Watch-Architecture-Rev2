"""Approval-time binding for immutable KnowledgeItem assessments.

This module only verifies and fingerprints existing evidence. It does not
authorize a LearningChange operation or perform a canonical write.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.models import (
    KnowledgeLifecycleAssessment,
    KnowledgeQualityAssessment,
    KnowledgeRevalidationAssessment,
    LearningChange,
    LearningChangeOperatorProvenance,
    Task,
)
from core.snapshot_store import SnapshotStore
from core.state_assessment import _canonical_json

PROPOSED_STATE_HASH_DOMAIN = "watch.r7b.learning-change-proposed-state.v1"


class KnowledgeApprovalBindingError(ValueError):
    """An approval cannot be bound to one valid, current assessment."""


def _domain_hash(domain: str, value: Any) -> str:
    from core.knowledge_revalidation import _normalize_json

    canonical = _canonical_json(_normalize_json(value))
    digest = hashlib.sha256(
        domain.encode("utf-8") + b"\0" + canonical.encode("utf-8")
    ).hexdigest()
    return "sha256:" + digest


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise KnowledgeApprovalBindingError(
            "knowledge_approval_timestamp_naive"
        )
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _assessment_counts(
    session: Session, learning_change: LearningChange
) -> tuple[int, int, int]:
    quality = list(
        session.scalars(
            select(KnowledgeQualityAssessment).where(
                KnowledgeQualityAssessment.team_id == learning_change.team_id,
                KnowledgeQualityAssessment.learning_change_id
                == learning_change.id,
            )
        )
    )
    revalidation = list(
        session.scalars(
            select(KnowledgeRevalidationAssessment).where(
                KnowledgeRevalidationAssessment.team_id == learning_change.team_id,
                KnowledgeRevalidationAssessment.learning_change_id
                == learning_change.id,
            )
        )
    )
    lifecycle = list(
        session.scalars(
            select(KnowledgeLifecycleAssessment).where(
                KnowledgeLifecycleAssessment.team_id == learning_change.team_id,
                KnowledgeLifecycleAssessment.learning_change_id
                == learning_change.id,
            )
        )
    )
    return len(quality), len(revalidation), len(lifecycle)


def build_approval_binding(
    session: Session,
    learning_change: LearningChange,
    *,
    operator_id: str,
    approval_policy_version: int,
    require_assessment: bool,
    snapshot_store: SnapshotStore | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> dict[str, Any]:
    """Rebuild the complete approval fingerprint input from canonical rows.

    For B3 operations this independently revalidates the recorded assessment,
    its Task/Event chain, current target state, evidence basis, and (for
    supersede) the full successor snapshot. It intentionally does not grant
    those operations commit eligibility.
    """
    if (
        isinstance(approval_policy_version, bool)
        or not isinstance(approval_policy_version, int)
        or approval_policy_version < 1
    ):
        raise KnowledgeApprovalBindingError(
            "knowledge_approval_policy_version_invalid"
        )
    if not isinstance(operator_id, str) or not operator_id:
        raise KnowledgeApprovalBindingError(
            "knowledge_approval_operator_identity_invalid"
        )
    if (
        learning_change.target_kind != "knowledge_item"
        or learning_change.status not in {"proposed", "accepted", "rejected"}
    ):
        raise KnowledgeApprovalBindingError(
            "knowledge_approval_learning_change_invalid"
        )

    quality_count, revalidation_count, lifecycle_count = _assessment_counts(
        session, learning_change
    )
    binding: dict[str, Any] = {
        "schema_version": 1,
        "team_id": str(learning_change.team_id),
        "learning_change_id": str(learning_change.id),
        "operation": learning_change.operation,
        "target_kind": learning_change.target_kind,
        "target_id": (
            str(learning_change.target_id)
            if learning_change.target_id is not None
            else None
        ),
        "current_learning_change_id": None,
        "target_content_version": None,
        "target_content_hash": None,
        "target_content_hash_scheme": None,
        "target_status": None,
        "target_state_hash": None,
        "proposal_hash": learning_change.proposed_state.get("proposal_hash"),
        "proposed_state_hash": _domain_hash(
            PROPOSED_STATE_HASH_DOMAIN, learning_change.proposed_state
        ),
        "evidence_refs": learning_change.evidence_basis,
        "evidence_basis_hash": learning_change.evidence_basis_hash,
        "approval_policy_version": approval_policy_version,
        "assessment_task_policy_version": None,
        "assessment_type": None,
        "assessment_id": None,
        "assessment_payload_hash": None,
        "evaluator_identity": None,
        "evaluator_revision": None,
        "operator_provenance": None,
        "successor_binding": None,
        "operator_id": operator_id,
    }

    if learning_change.operation == "create":
        if (
            learning_change.target_id is not None
            or revalidation_count
            or lifecycle_count
            or quality_count > 1
        ):
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_assessment_type_mismatch"
            )
        if require_assessment:
            from core.knowledge_quality import (
                KnowledgeQualityAssessmentError,
                require_recorded_assessment,
            )

            try:
                assessment = require_recorded_assessment(
                    session, learning_change, require_task_done=True
                )
            except KnowledgeQualityAssessmentError as error:
                raise KnowledgeApprovalBindingError(str(error)) from error
            task = session.get(Task, assessment.creating_task_id)
            if task is None:
                raise KnowledgeApprovalBindingError(
                    "knowledge_approval_assessment_task_missing"
                )
            binding.update(
                {
                    "assessment_task_policy_version": task.policy_version,
                    "assessment_type": "knowledge_quality",
                    "assessment_id": str(assessment.id),
                    "assessment_payload_hash": assessment.assessment_payload_hash,
                    "evaluator_identity": assessment.evaluator_identity,
                    "evaluator_revision": assessment.evaluator_revision,
                }
            )
        return binding

    if not require_assessment:
        raise KnowledgeApprovalBindingError(
            "knowledge_approval_assessment_required_for_operation"
        )
    if snapshot_store is None or session_factory is None:
        raise KnowledgeApprovalBindingError(
            "knowledge_approval_snapshot_context_required"
        )

    previous = learning_change.previous_state
    if (
        not isinstance(previous, dict)
        or not isinstance(previous.get("state"), dict)
    ):
        raise KnowledgeApprovalBindingError(
            "knowledge_approval_target_snapshot_missing"
        )
    target_state = previous["state"]
    binding.update(
        {
            "target_status": target_state.get("status"),
        }
    )

    if learning_change.operation == "revalidate":
        if quality_count or lifecycle_count or revalidation_count > 1:
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_assessment_type_mismatch"
            )
        from core.knowledge_revalidation import (
            KnowledgeRevalidationAssessmentError,
            require_recorded_assessment,
        )

        try:
            assessment = require_recorded_assessment(
                session,
                learning_change,
                snapshot_store,
                session_factory,
                require_task_done=True,
                require_current=True,
            )
        except KnowledgeRevalidationAssessmentError as error:
            raise KnowledgeApprovalBindingError(str(error)) from error
        task = session.get(Task, assessment.task_id)
        if task is None:
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_assessment_task_missing"
            )
        binding.update(
            {
                "current_learning_change_id": str(
                    assessment.current_learning_change_id
                ),
                "target_content_version": assessment.target_content_version,
                "target_content_hash": assessment.target_content_hash,
                "target_content_hash_scheme": assessment.target_content_hash_scheme,
                "target_state_hash": assessment.target_state_hash,
                "proposal_hash": assessment.proposal_hash,
                "proposed_state_hash": assessment.proposed_state_hash,
                "evidence_refs": assessment.evidence_refs,
                "evidence_basis_hash": assessment.evidence_basis_hash,
                "assessment_task_policy_version": task.policy_version,
                "assessment_type": "knowledge_revalidation",
                "assessment_id": str(assessment.id),
                "assessment_payload_hash": assessment.payload_hash,
                "evaluator_identity": assessment.evaluator_identity,
                "evaluator_revision": assessment.evaluator_revision,
            }
        )
        return binding

    if learning_change.operation in {"retire", "supersede"}:
        if quality_count or revalidation_count or lifecycle_count > 1:
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_assessment_type_mismatch"
            )
        from core.knowledge_lifecycle import (
            KnowledgeLifecycleAssessmentError,
            require_recorded_assessment,
        )

        try:
            assessment = require_recorded_assessment(
                session,
                learning_change,
                snapshot_store,
                session_factory,
                require_task_done=True,
                require_current=True,
            )
        except KnowledgeLifecycleAssessmentError as error:
            raise KnowledgeApprovalBindingError(str(error)) from error
        task = session.get(Task, assessment.task_id)
        provenance = session.get(
            LearningChangeOperatorProvenance, learning_change.id
        )
        if task is None or provenance is None:
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_lifecycle_provenance_missing"
            )
        binding.update(
            {
                "current_learning_change_id": str(
                    assessment.current_learning_change_id
                ),
                "target_content_version": assessment.target_content_version,
                "target_content_hash": assessment.target_content_hash,
                "target_content_hash_scheme": assessment.target_content_hash_scheme,
                "target_state_hash": assessment.target_state_hash,
                "proposal_hash": assessment.proposal_hash,
                "proposed_state_hash": assessment.proposed_state_hash,
                "evidence_refs": assessment.evidence_refs,
                "evidence_basis_hash": assessment.evidence_basis_hash,
                "assessment_task_policy_version": task.policy_version,
                "assessment_type": "knowledge_lifecycle",
                "assessment_id": str(assessment.id),
                "assessment_payload_hash": assessment.payload_hash,
                "operator_provenance": {
                    "issuer": provenance.issuer,
                    "subject": provenance.subject,
                },
            }
        )
        if learning_change.operation == "supersede":
            binding["successor_binding"] = {
                "successor_knowledge_item_id": (
                    str(assessment.successor_knowledge_item_id)
                    if assessment.successor_knowledge_item_id is not None
                    else None
                ),
                "successor_team_id": str(learning_change.team_id),
                "successor_current_learning_change_id": (
                    str(assessment.successor_current_learning_change_id)
                    if assessment.successor_current_learning_change_id is not None
                    else None
                ),
                "successor_content_version": assessment.successor_content_version,
                "successor_content_hash": assessment.successor_content_hash,
                "successor_content_hash_scheme": (
                    assessment.successor_content_hash_scheme
                ),
                "successor_status": assessment.successor_status,
                "successor_review_after": _timestamp(
                    assessment.successor_review_after
                ),
                "successor_state_hash": assessment.successor_state_hash,
            }
        return binding

    raise KnowledgeApprovalBindingError(
        "knowledge_approval_operation_not_supported"
    )
