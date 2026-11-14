"""Approval-time binding for immutable KnowledgeItem assessments.

This module only verifies and fingerprints existing evidence. It does not
authorize a LearningChange operation or perform a canonical write.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.models import (
    KnowledgeItem,
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
    require_current: bool | None = None,
    snapshot_store: SnapshotStore | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> dict[str, Any]:
    """Rebuild the complete approval fingerprint input from canonical rows.

    For B3 operations this independently revalidates the recorded assessment,
    its Task/Event chain, target state when required, evidence basis, and (for
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
    if require_current is None:
        require_current = learning_change.status == "proposed"

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
            from core.knowledge_quality import KnowledgeQualityAssessmentError
            from core.knowledge_quality import (
                require_recorded_assessment as require_quality_assessment,
            )

            try:
                quality_assessment = require_quality_assessment(
                    session, learning_change, require_task_done=True
                )
            except KnowledgeQualityAssessmentError as error:
                raise KnowledgeApprovalBindingError(str(error)) from error
            task = session.get(Task, quality_assessment.creating_task_id)
            if task is None:
                raise KnowledgeApprovalBindingError(
                    "knowledge_approval_assessment_task_missing"
                )
            binding.update(
                {
                    "assessment_task_policy_version": task.policy_version,
                    "assessment_type": "knowledge_quality",
                    "assessment_id": str(quality_assessment.id),
                    "assessment_payload_hash": (
                        quality_assessment.assessment_payload_hash
                    ),
                    "evaluator_identity": quality_assessment.evaluator_identity,
                    "evaluator_revision": quality_assessment.evaluator_revision,
                }
            )
        return binding

    if learning_change.operation == "revise":
        if revalidation_count or lifecycle_count or quality_count > 1:
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_assessment_type_mismatch"
            )
        from core.knowledge_quality import (
            KnowledgeQualityAssessmentError,
            _assessment_target_binding,
            _revision_target_binding,
        )
        from core.knowledge_quality import (
            require_recorded_assessment as require_quality_assessment,
        )

        try:
            target_binding = _revision_target_binding(
                session,
                learning_change,
                require_current=require_current,
            )
        except KnowledgeQualityAssessmentError as error:
            raise KnowledgeApprovalBindingError(str(error)) from error
        if target_binding["target_knowledge_item_id"] != str(learning_change.target_id):
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_revision_target_mismatch"
            )
        previous_state = learning_change.previous_state
        if (
            not isinstance(previous_state, dict)
            or not isinstance(previous_state.get("state"), dict)
        ):
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_target_snapshot_missing"
            )
        binding.update(
            {
                "current_learning_change_id": target_binding[
                    "target_current_learning_change_id"
                ],
                "target_content_version": target_binding["target_content_version"],
                "target_content_hash": target_binding["target_content_hash"],
                "target_content_hash_scheme": target_binding[
                    "target_content_hash_scheme"
                ],
                "target_state_hash": target_binding["target_state_hash"],
                "target_status": previous_state["state"].get("status"),
            }
        )
        if require_assessment:
            try:
                quality_assessment = require_quality_assessment(
                    session, learning_change, require_task_done=True
                )
                recorded_target_binding = _assessment_target_binding(
                    session, quality_assessment
                )
            except KnowledgeQualityAssessmentError as error:
                raise KnowledgeApprovalBindingError(str(error)) from error
            if recorded_target_binding != target_binding:
                raise KnowledgeApprovalBindingError(
                    "knowledge_approval_revision_assessment_target_mismatch"
                )
            task = session.get(Task, quality_assessment.creating_task_id)
            if task is None:
                raise KnowledgeApprovalBindingError(
                    "knowledge_approval_assessment_task_missing"
                )
            binding.update(
                {
                    "assessment_task_policy_version": task.policy_version,
                    "assessment_type": "knowledge_quality",
                    "assessment_id": str(quality_assessment.id),
                    "assessment_payload_hash": (
                        quality_assessment.assessment_payload_hash
                    ),
                    "evaluator_identity": quality_assessment.evaluator_identity,
                    "evaluator_revision": quality_assessment.evaluator_revision,
                }
            )
        return binding

    if learning_change.operation == "revalidate":
        if quality_count or lifecycle_count or revalidation_count > 1:
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_assessment_type_mismatch"
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
        binding["target_status"] = target_state.get("status")
        if not require_assessment:
            from core.knowledge_revalidation import (
                KnowledgeRevalidationAssessmentError,
                _target_state_from_proposal,
            )
            from core.learning_history import KNOWLEDGE_CONTENT_HASH_SCHEME

            target = session.scalar(
                select(KnowledgeItem).where(
                    KnowledgeItem.id == learning_change.target_id,
                    KnowledgeItem.team_id == learning_change.team_id,
                )
            )
            if target is None:
                raise KnowledgeApprovalBindingError(
                    "knowledge_approval_revalidation_target_missing"
                )
            try:
                target_state, target_state_hash, target_content_hash = (
                    _target_state_from_proposal(
                        learning_change,
                        target,
                        require_current=learning_change.status == "proposed",
                    )
                )
            except KnowledgeRevalidationAssessmentError as error:
                raise KnowledgeApprovalBindingError(str(error)) from error
            binding.update(
                {
                    "current_learning_change_id": target_state[
                        "current_learning_change_id"
                    ],
                    "target_content_version": target_state["version"],
                    "target_content_hash": target_content_hash,
                    "target_content_hash_scheme": KNOWLEDGE_CONTENT_HASH_SCHEME,
                    "target_state_hash": target_state_hash,
                }
            )
            return binding
        if snapshot_store is None or session_factory is None:
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_snapshot_context_required"
            )
        from core.knowledge_revalidation import (
            KnowledgeRevalidationAssessmentError,
        )
        from core.knowledge_revalidation import (
            require_recorded_assessment as require_revalidation_assessment,
        )

        try:
            revalidation_assessment = require_revalidation_assessment(
                session,
                learning_change,
                snapshot_store,
                session_factory,
                require_task_done=True,
                require_current=require_current,
            )
        except KnowledgeRevalidationAssessmentError as error:
            raise KnowledgeApprovalBindingError(str(error)) from error
        task = session.get(Task, revalidation_assessment.task_id)
        if task is None:
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_assessment_task_missing"
            )
        if revalidation_assessment.assessment_result != "supported":
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_revalidation_not_supported"
            )
        binding.update(
            {
                "current_learning_change_id": str(
                    revalidation_assessment.current_learning_change_id
                ),
                "target_content_version": (
                    revalidation_assessment.target_content_version
                ),
                "target_content_hash": revalidation_assessment.target_content_hash,
                "target_content_hash_scheme": (
                    revalidation_assessment.target_content_hash_scheme
                ),
                "target_state_hash": revalidation_assessment.target_state_hash,
                "proposal_hash": revalidation_assessment.proposal_hash,
                "proposed_state_hash": revalidation_assessment.proposed_state_hash,
                "evidence_refs": revalidation_assessment.evidence_refs,
                "evidence_basis_hash": revalidation_assessment.evidence_basis_hash,
                "assessment_task_policy_version": task.policy_version,
                "assessment_type": "knowledge_revalidation",
                "assessment_id": str(revalidation_assessment.id),
                "assessment_payload_hash": revalidation_assessment.payload_hash,
                "evaluator_identity": revalidation_assessment.evaluator_identity,
                "evaluator_revision": revalidation_assessment.evaluator_revision,
            }
        )
        return binding

    if not require_assessment and learning_change.operation == "retire":
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

    if learning_change.operation in {"retire", "supersede"}:
        if quality_count or revalidation_count or lifecycle_count > 1:
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_assessment_type_mismatch"
            )
        from core.knowledge_lifecycle import KnowledgeLifecycleAssessmentError
        from core.knowledge_lifecycle import (
            require_recorded_assessment as require_lifecycle_assessment,
        )

        if not require_assessment and learning_change.operation == "retire":
            from core.knowledge_lifecycle import build_lifecycle_task_request

            try:
                _, lifecycle_request = build_lifecycle_task_request(
                    session,
                    session_factory,
                    snapshot_store,
                    learning_change,
                    require_current=False,
                )
            except KnowledgeLifecycleAssessmentError as error:
                raise KnowledgeApprovalBindingError(str(error)) from error
            binding.update(
                {
                    "current_learning_change_id": lifecycle_request[
                        "current_learning_change_id"
                    ],
                    "target_content_version": lifecycle_request[
                        "target_content_version"
                    ],
                    "target_content_hash": lifecycle_request["target_content_hash"],
                    "target_content_hash_scheme": lifecycle_request[
                        "target_content_hash_scheme"
                    ],
                    "target_state_hash": lifecycle_request["target_state_hash"],
                    "proposal_hash": lifecycle_request["proposal_hash"],
                    "proposed_state_hash": lifecycle_request["proposed_state_hash"],
                    "evidence_refs": learning_change.evidence_basis,
                    "evidence_basis_hash": lifecycle_request["evidence_basis_hash"],
                    "operator_provenance": {
                        "issuer": lifecycle_request["operator_issuer"],
                        "subject": lifecycle_request["operator_subject"],
                    },
                }
            )
            return binding

        try:
            lifecycle_assessment = require_lifecycle_assessment(
                session,
                learning_change,
                snapshot_store,
                session_factory,
                require_task_done=True,
                require_current=require_current,
            )
        except KnowledgeLifecycleAssessmentError as error:
            raise KnowledgeApprovalBindingError(str(error)) from error
        task = session.get(Task, lifecycle_assessment.task_id)
        provenance = session.get(
            LearningChangeOperatorProvenance, learning_change.id
        )
        if task is None or provenance is None:
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_lifecycle_provenance_missing"
            )
        if require_assessment and lifecycle_assessment.assessment_result != "eligible":
            raise KnowledgeApprovalBindingError(
                "knowledge_approval_lifecycle_not_eligible"
            )
        binding.update(
            {
                "current_learning_change_id": str(
                    lifecycle_assessment.current_learning_change_id
                ),
                "target_content_version": lifecycle_assessment.target_content_version,
                "target_content_hash": lifecycle_assessment.target_content_hash,
                "target_content_hash_scheme": (
                    lifecycle_assessment.target_content_hash_scheme
                ),
                "target_state_hash": lifecycle_assessment.target_state_hash,
                "proposal_hash": lifecycle_assessment.proposal_hash,
                "proposed_state_hash": lifecycle_assessment.proposed_state_hash,
                "evidence_refs": lifecycle_assessment.evidence_refs,
                "evidence_basis_hash": lifecycle_assessment.evidence_basis_hash,
                "assessment_task_policy_version": task.policy_version,
                "assessment_type": "knowledge_lifecycle",
                "assessment_id": str(lifecycle_assessment.id),
                "assessment_payload_hash": lifecycle_assessment.payload_hash,
                "operator_provenance": {
                    "issuer": provenance.issuer,
                    "subject": provenance.subject,
                },
            }
        )
        if learning_change.operation == "supersede":
            binding["successor_binding"] = {
                "successor_knowledge_item_id": (
                    str(lifecycle_assessment.successor_knowledge_item_id)
                    if lifecycle_assessment.successor_knowledge_item_id is not None
                    else None
                ),
                "successor_team_id": str(learning_change.team_id),
                "successor_current_learning_change_id": (
                    str(lifecycle_assessment.successor_current_learning_change_id)
                    if (
                        lifecycle_assessment.successor_current_learning_change_id
                        is not None
                    )
                    else None
                ),
                "successor_content_version": (
                    lifecycle_assessment.successor_content_version
                ),
                "successor_content_hash": lifecycle_assessment.successor_content_hash,
                "successor_content_hash_scheme": (
                    lifecycle_assessment.successor_content_hash_scheme
                ),
                "successor_status": lifecycle_assessment.successor_status,
                "successor_review_after": _timestamp(
                    lifecycle_assessment.successor_review_after
                ),
                "successor_state_hash": lifecycle_assessment.successor_state_hash,
            }
        return binding

    raise KnowledgeApprovalBindingError(
        "knowledge_approval_operation_not_supported"
    )
