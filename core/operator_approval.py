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
SUPPORTED_LEARNING_CHANGE_OPERATION = "create"
SUPPORTED_LEARNING_CHANGE_TARGET_KIND = "knowledge_item"
Decision = Literal["accept", "reject"]


class OperatorApprovalValidationError(ValueError):
    """A pure Operator approval request contract is malformed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class OperatorApprovalRequestPayload:
    """Validated immutable fields from one persisted approval request Event."""

    schema_version: Literal[1, 2]
    learning_change_id: UUID
    decision: Decision
    rejection_reason: str | None
    operator_id: str
    idempotency_key_hash: str
    request_fingerprint: str
    policy_version: int
    quality_assessment_id: UUID | None
    quality_assessment_hash: str | None


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
) -> str:
    """Build the current schema-v2 fingerprint, including assessment pins."""
    canonical = json.dumps(
        {
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
        },
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
    """Return whether the currently authorized create-only target shape matches."""
    return (
        target_kind == SUPPORTED_LEARNING_CHANGE_TARGET_KIND
        and operation == SUPPORTED_LEARNING_CHANGE_OPERATION
        and target_id is None
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


def parse_request_event_payload(
    payload: object, *, team_id: UUID, policy_version: int
) -> OperatorApprovalRequestPayload:
    """Validate schema, identity, decision, idempotency and fingerprint pins.

    Schema v1 is retained only for historical rejection requests. Schema v2
    binds the completed KnowledgeQualityAssessment for accepted requests.
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
    if not (is_legacy_rejection or is_assessment_request):
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
    if is_assessment_request:
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
        )
    if request_fingerprint != expected_fingerprint:
        raise OperatorApprovalValidationError(
            "operator_task_request_fingerprint_invalid"
        )

    return OperatorApprovalRequestPayload(
        schema_version=1 if is_legacy_rejection else 2,
        learning_change_id=learning_change_id,
        decision=decision,
        rejection_reason=canonical_reason,
        operator_id=operator_id,
        idempotency_key_hash=idempotency_key_hash,
        request_fingerprint=request_fingerprint,
        policy_version=cast(int, stored_policy_version),
        quality_assessment_id=quality_assessment_id,
        quality_assessment_hash=quality_assessment_hash,
    )
