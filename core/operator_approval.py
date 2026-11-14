"""Pure request-integrity contracts for host-invoked Operator approvals.

Database ownership and operation eligibility remain with the application,
TaskRuntime, and LearningCommitService boundaries. This module validates only
the immutable request envelope and its canonical bindings.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID

APPROVAL_ACTION = "approve_learning_change"
SUPPORTED_LEARNING_CHANGE_TARGET_KIND = "knowledge_item"
Decision = Literal["accept", "reject"]
_STALE_OPERATOR_APPROVAL_REASONS = frozenset(
    {
        "knowledge_quality_revision_target_stale",
        "knowledge_revalidation_target_stale",
        "knowledge_lifecycle_predecessor_reconstructed_history_does_not_match_live_item",
        "knowledge_lifecycle_successor_stale",
    }
)


class OperatorApprovalValidationError(ValueError):
    """A pure Operator approval request contract is malformed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class OperatorApprovalRequestPayload:
    """Validated immutable fields from one persisted approval request Event."""

    schema_version: Literal[1, 2, 3]
    learning_change_id: UUID
    decision: Decision
    rejection_reason: str | None
    operator_id: str
    idempotency_key_hash: str
    request_fingerprint: str
    policy_version: int
    quality_assessment_id: UUID | None
    quality_assessment_hash: str | None
    approval_binding: dict[str, object] | None


def canonical_operator_identity(issuer: object, subject: object) -> str:
    """Serialize a host-authenticated issuer/subject pair canonically."""
    for label, value in (("issuer", issuer), ("subject", subject)):
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(unicodedata.category(character) == "Cc" for character in value)
        ):
            raise OperatorApprovalValidationError(f"invalid_operator_{label}")

    canonical = json.dumps(
        {"iss": issuer, "sub": subject},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(canonical) > 255:
        raise OperatorApprovalValidationError("operator_identity_too_long")
    return canonical


def validate_decision_reason(
    decision: object, rejection_reason: object
) -> str | None:
    """Validate the common accept/reject shape and return its canonical reason."""
    if decision not in ("accept", "reject"):
        raise OperatorApprovalValidationError("invalid_decision")
    if decision == "reject":
        if not isinstance(rejection_reason, str) or not rejection_reason.strip():
            raise OperatorApprovalValidationError("rejection_reason_required")
        return rejection_reason.strip()
    if rejection_reason is not None:
        raise OperatorApprovalValidationError("rejection_reason_not_allowed")
    return None


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_request_fingerprint(
    *,
    team_id: UUID,
    learning_change_id: UUID,
    decision: str,
    rejection_reason: str | None,
    operator_id: str,
    quality_assessment_id: UUID | None,
    quality_assessment_hash: str | None,
    approval_binding: dict[str, object] | None = None,
) -> str:
    """Build a schema-v2 or schema-v3 fingerprint with immutable assessment pins."""
    payload: dict[str, object] = {
        "operation": APPROVAL_ACTION,
        "team_id": str(team_id),
        "learning_change_id": str(learning_change_id),
        "decision": decision,
        "rejection_reason": rejection_reason,
        "operator_id": operator_id,
        "knowledge_quality_assessment_id": (
            str(quality_assessment_id) if quality_assessment_id else None
        ),
        "knowledge_quality_assessment_hash": quality_assessment_hash,
    }
    if approval_binding is not None:
        payload["approval_binding"] = approval_binding
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256(canonical)


def _build_legacy_request_fingerprint(
    *,
    team_id: UUID,
    learning_change_id: UUID,
    decision: str,
    rejection_reason: str | None,
    operator_id: str,
) -> str:
    canonical = json.dumps(
        {
            "operation": APPROVAL_ACTION,
            "team_id": str(team_id),
            "learning_change_id": str(learning_change_id),
            "decision": decision,
            "rejection_reason": rejection_reason,
            "operator_id": operator_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256(canonical)


def is_supported_learning_change(
    *, target_kind: object, operation: object, target_id: object
) -> bool:
    """Return whether an authorized KnowledgeItem decision has a valid target."""
    return (
        target_kind == SUPPORTED_LEARNING_CHANGE_TARGET_KIND
        and (
            (operation == "create" and target_id is None)
            or (
                operation in {"revise", "revalidate", "retire", "supersede"}
                and target_id is not None
            )
        )
    )


def _require_sha256(value: object, reason: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise OperatorApprovalValidationError(reason)
    return value


def _parse_canonical_uuid(value: object, reason: str) -> UUID:
    if not isinstance(value, str):
        raise OperatorApprovalValidationError(reason)
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as error:
        raise OperatorApprovalValidationError(reason) from error
    if str(parsed) != value:
        raise OperatorApprovalValidationError(reason)
    return parsed


_APPROVAL_BINDING_KEYS = {
    "schema_version",
    "team_id",
    "learning_change_id",
    "operation",
    "target_kind",
    "target_id",
    "current_learning_change_id",
    "target_content_version",
    "target_content_hash",
    "target_content_hash_scheme",
    "target_status",
    "target_state_hash",
    "proposal_hash",
    "proposed_state_hash",
    "evidence_refs",
    "evidence_basis_hash",
    "approval_policy_version",
    "assessment_task_policy_version",
    "assessment_type",
    "assessment_id",
    "assessment_payload_hash",
    "evaluator_identity",
    "evaluator_revision",
    "operator_provenance",
    "successor_binding",
    "operator_id",
}


def _validate_approval_binding(
    value: object,
    *,
    team_id: UUID,
    learning_change_id: UUID,
    operator_id: str,
    policy_version: int,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != _APPROVAL_BINDING_KEYS:
        raise OperatorApprovalValidationError(
            "operator_approval_binding_invalid"
        )
    binding = value
    if (
        binding.get("schema_version") != 1
        or isinstance(binding.get("schema_version"), bool)
        or binding.get("team_id") != str(team_id)
        or binding.get("learning_change_id") != str(learning_change_id)
        or binding.get("operator_id") != operator_id
        or binding.get("approval_policy_version") != policy_version
        or isinstance(binding.get("approval_policy_version"), bool)
        or binding.get("target_kind") != SUPPORTED_LEARNING_CHANGE_TARGET_KIND
        or binding.get("operation") not in {
            "create", "revise", "revalidate", "retire", "supersede"
        }
    ):
        raise OperatorApprovalValidationError(
            "operator_approval_binding_invalid"
        )

    operation = binding["operation"]
    target_id = binding.get("target_id")
    if target_id is None:
        if any(
            binding.get(key) is not None
            for key in (
                "current_learning_change_id",
                "target_content_version",
                "target_content_hash",
                "target_content_hash_scheme",
                "target_status",
                "target_state_hash",
            )
        ):
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
        if operation != "create":
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
    else:
        _parse_canonical_uuid(
            target_id, "operator_approval_binding_invalid"
        )
        _parse_canonical_uuid(
            binding.get("current_learning_change_id"),
            "operator_approval_binding_invalid",
        )
        version = binding.get("target_content_version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
        _require_sha256(
            binding.get("target_content_hash"),
            "operator_approval_binding_invalid",
        )
        _require_sha256(
            binding.get("target_state_hash"),
            "operator_approval_binding_invalid",
        )
        if (
            binding.get("target_content_hash_scheme")
            != "watch.r7b.knowledge-content.v2"
            or binding.get("target_status") not in {"active", "needs_review"}
        ):
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )

    for key in ("proposal_hash", "proposed_state_hash", "evidence_basis_hash"):
        _require_sha256(binding.get(key), "operator_approval_binding_invalid")
    if not isinstance(binding.get("evidence_refs"), list):
        raise OperatorApprovalValidationError(
            "operator_approval_binding_invalid"
        )

    assessment_type = binding.get("assessment_type")
    assessment_id = binding.get("assessment_id")
    assessment_hash = binding.get("assessment_payload_hash")
    assessment_policy = binding.get("assessment_task_policy_version")
    expected_types = {
        "create": "knowledge_quality",
        "revise": "knowledge_quality",
        "revalidate": "knowledge_revalidation",
        "retire": "knowledge_lifecycle",
        "supersede": "knowledge_lifecycle",
    }
    if assessment_type is None:
        if assessment_id is not None or assessment_hash is not None:
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
        if assessment_policy is not None:
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
    else:
        if assessment_type != expected_types[operation]:
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
        _parse_canonical_uuid(assessment_id, "operator_approval_binding_invalid")
        _require_sha256(assessment_hash, "operator_approval_binding_invalid")
        if (
            isinstance(assessment_policy, bool)
            or not isinstance(assessment_policy, int)
            or assessment_policy < 1
        ):
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )

    evaluator_identity = binding.get("evaluator_identity")
    evaluator_revision = binding.get("evaluator_revision")
    if assessment_type in {"knowledge_quality", "knowledge_revalidation"}:
        if (
            not isinstance(evaluator_identity, str)
            or not evaluator_identity.strip()
            or not isinstance(evaluator_revision, str)
            or not evaluator_revision.strip()
        ):
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
    elif evaluator_identity is not None or evaluator_revision is not None:
        raise OperatorApprovalValidationError(
            "operator_approval_binding_invalid"
        )

    provenance = binding.get("operator_provenance")
    if operation in {"retire", "supersede"}:
        if (
            not isinstance(provenance, dict)
            or set(provenance) != {"issuer", "subject"}
            or not isinstance(provenance.get("issuer"), str)
            or not provenance["issuer"].strip()
            or not isinstance(provenance.get("subject"), str)
            or not provenance["subject"].strip()
        ):
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
    elif provenance is not None:
        raise OperatorApprovalValidationError(
            "operator_approval_binding_invalid"
        )

    successor = binding.get("successor_binding")
    if operation == "supersede":
        successor_keys = {
            "successor_knowledge_item_id",
            "successor_team_id",
            "successor_current_learning_change_id",
            "successor_content_version",
            "successor_content_hash",
            "successor_content_hash_scheme",
            "successor_status",
            "successor_review_after",
            "successor_state_hash",
        }
        if not isinstance(successor, dict) or set(successor) != successor_keys:
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
        _parse_canonical_uuid(
            successor.get("successor_knowledge_item_id"),
            "operator_approval_binding_invalid",
        )
        _parse_canonical_uuid(
            successor.get("successor_current_learning_change_id"),
            "operator_approval_binding_invalid",
        )
        if successor.get("successor_team_id") != str(team_id):
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
        successor_version = successor.get("successor_content_version")
        if (
            isinstance(successor_version, bool)
            or not isinstance(successor_version, int)
            or successor_version < 1
        ):
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
        _require_sha256(
            successor.get("successor_content_hash"),
            "operator_approval_binding_invalid",
        )
        _require_sha256(
            successor.get("successor_state_hash"),
            "operator_approval_binding_invalid",
        )
        if (
            successor.get("successor_content_hash_scheme")
            != "watch.r7b.knowledge-content.v2"
            or successor.get("successor_status") != "active"
            or not isinstance(successor.get("successor_review_after"), str)
        ):
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
    elif successor is not None:
        raise OperatorApprovalValidationError(
            "operator_approval_binding_invalid"
        )

    return binding


def parse_request_event_payload(
    payload: object, *, team_id: UUID, policy_version: int
) -> OperatorApprovalRequestPayload:
    """Validate schema, identity, decision, idempotency and fingerprint pins.

    Schema v1 is retained for historical rejection requests. Schema v2 binds
    the KnowledgeQualityAssessment; schema v3 adds the complete approval binding.
    """
    if not isinstance(payload, dict):
        raise OperatorApprovalValidationError("operator_task_request_event_invalid")

    legacy_keys = {
        "schema_version",
        "operation",
        "learning_change_id",
        "decision",
        "rejection_reason",
        "operator_id",
        "idempotency_key_hash",
        "request_fingerprint",
        "policy_version",
    }
    assessment_keys = {
        "knowledge_quality_assessment_id",
        "knowledge_quality_assessment_hash",
    }
    binding_keys = {"approval_binding"}
    schema_version = payload.get("schema_version")
    is_legacy_rejection = (
        schema_version == 1
        and isinstance(schema_version, int)
        and not isinstance(schema_version, bool)
        and set(payload) == legacy_keys
        and payload.get("decision") == "reject"
    )
    is_assessment_request = (
        schema_version == 2
        and isinstance(schema_version, int)
        and not isinstance(schema_version, bool)
        and set(payload) == legacy_keys | assessment_keys
    )
    is_bound_assessment_request = (
        schema_version == 3
        and isinstance(schema_version, int)
        and not isinstance(schema_version, bool)
        and set(payload) == legacy_keys | assessment_keys | binding_keys
    )
    if not (
        is_legacy_rejection
        or is_assessment_request
        or is_bound_assessment_request
    ):
        raise OperatorApprovalValidationError(
            "operator_task_request_payload_invalid"
        )

    stored_policy_version = payload.get("policy_version")
    if (
        payload.get("operation") != APPROVAL_ACTION
        or isinstance(stored_policy_version, bool)
        or not isinstance(stored_policy_version, int)
        or stored_policy_version != policy_version
    ):
        raise OperatorApprovalValidationError(
            "operator_task_request_payload_invalid"
        )

    decision_value = payload.get("decision")
    rejection_reason = payload.get("rejection_reason")
    try:
        canonical_reason = validate_decision_reason(
            decision_value, rejection_reason
        )
    except OperatorApprovalValidationError as error:
        raise OperatorApprovalValidationError(
            "operator_task_request_payload_invalid"
        ) from error
    if rejection_reason != canonical_reason:
        raise OperatorApprovalValidationError(
            "operator_task_request_payload_invalid"
        )
    decision = cast(Decision, decision_value)

    operator_id = payload.get("operator_id")
    if not isinstance(operator_id, str) or len(operator_id) > 255:
        raise OperatorApprovalValidationError(
            "operator_task_request_identity_invalid"
        )
    try:
        identity = json.loads(operator_id)
        if not isinstance(identity, dict) or set(identity) != {"iss", "sub"}:
            raise ValueError("identity_shape")
        canonical_identity = canonical_operator_identity(
            identity.get("iss"), identity.get("sub")
        )
    except (TypeError, ValueError) as error:
        raise OperatorApprovalValidationError(
            "operator_task_request_identity_invalid"
        ) from error
    if canonical_identity != operator_id:
        raise OperatorApprovalValidationError(
            "operator_task_request_identity_invalid"
        )

    idempotency_key_hash = _require_sha256(
        payload.get("idempotency_key_hash"),
        "operator_task_request_payload_invalid",
    )
    request_fingerprint = _require_sha256(
        payload.get("request_fingerprint"),
        "operator_task_request_payload_invalid",
    )

    quality_assessment_id: UUID | None = None
    quality_assessment_hash: str | None = None
    approval_binding: dict[str, object] | None = None
    if is_bound_assessment_request:
        assessment_id_value = payload.get("knowledge_quality_assessment_id")
        assessment_hash_value = payload.get("knowledge_quality_assessment_hash")
        if decision == "accept":
            if assessment_id_value is not None:
                quality_assessment_id = _parse_canonical_uuid(
                    assessment_id_value,
                    "operator_quality_assessment_reference_invalid",
                )
            if assessment_hash_value is not None:
                quality_assessment_hash = _require_sha256(
                    assessment_hash_value,
                    "operator_quality_assessment_reference_invalid",
                )
        elif assessment_id_value is not None or assessment_hash_value is not None:
            raise OperatorApprovalValidationError(
                "operator_quality_assessment_reference_invalid"
            )
    elif is_assessment_request:
        assessment_id_value = payload.get("knowledge_quality_assessment_id")
        assessment_hash_value = payload.get("knowledge_quality_assessment_hash")
        if decision == "accept":
            quality_assessment_id = _parse_canonical_uuid(
                assessment_id_value,
                "operator_quality_assessment_reference_invalid",
            )
            quality_assessment_hash = _require_sha256(
                assessment_hash_value,
                "operator_quality_assessment_reference_invalid",
            )
        elif assessment_id_value is not None or assessment_hash_value is not None:
            raise OperatorApprovalValidationError(
                "operator_quality_assessment_reference_invalid"
            )
    elif decision == "accept":
        raise OperatorApprovalValidationError("operator_quality_assessment_required")

    learning_change_id = _parse_canonical_uuid(
        payload.get("learning_change_id"),
        "operator_task_request_target_invalid",
    )

    if is_bound_assessment_request:
        approval_binding = _validate_approval_binding(
            payload.get("approval_binding"),
            team_id=team_id,
            learning_change_id=learning_change_id,
            operator_id=operator_id,
            policy_version=cast(int, stored_policy_version),
        )
        binding_assessment_type = approval_binding.get("assessment_type")
        if binding_assessment_type == "knowledge_quality":
            if (
                quality_assessment_id is None
                or quality_assessment_hash is None
                or approval_binding.get("assessment_id") != str(quality_assessment_id)
                or approval_binding.get("assessment_payload_hash")
                != quality_assessment_hash
            ):
                raise OperatorApprovalValidationError(
                    "operator_approval_binding_invalid"
                )
        elif quality_assessment_id is not None or quality_assessment_hash is not None:
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )
        if decision == "accept" and binding_assessment_type is None:
            raise OperatorApprovalValidationError(
                "operator_quality_assessment_required"
            )
        if decision == "reject" and binding_assessment_type is not None:
            raise OperatorApprovalValidationError(
                "operator_approval_binding_invalid"
            )

    if is_legacy_rejection:
        expected_fingerprint = _build_legacy_request_fingerprint(
            team_id=team_id,
            learning_change_id=learning_change_id,
            decision=decision,
            rejection_reason=canonical_reason,
            operator_id=operator_id,
        )
    else:
        expected_fingerprint = build_request_fingerprint(
            team_id=team_id,
            learning_change_id=learning_change_id,
            decision=decision,
            rejection_reason=canonical_reason,
            operator_id=operator_id,
            quality_assessment_id=quality_assessment_id,
            quality_assessment_hash=quality_assessment_hash,
            approval_binding=(
                approval_binding if is_bound_assessment_request else None
            ),
        )
    if request_fingerprint != expected_fingerprint:
        raise OperatorApprovalValidationError(
            "operator_task_request_fingerprint_invalid"
        )

    return OperatorApprovalRequestPayload(
        schema_version=(
            1 if is_legacy_rejection else 3 if is_bound_assessment_request else 2
        ),
        learning_change_id=learning_change_id,
        decision=decision,
        rejection_reason=canonical_reason,
        operator_id=operator_id,
        idempotency_key_hash=idempotency_key_hash,
        request_fingerprint=request_fingerprint,
        policy_version=cast(int, stored_policy_version),
        quality_assessment_id=quality_assessment_id,
        quality_assessment_hash=quality_assessment_hash,
        approval_binding=approval_binding,
    )
