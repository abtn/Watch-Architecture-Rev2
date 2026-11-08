from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4

import pytest

from core.operator_approval import (
    OperatorApprovalValidationError,
    build_request_fingerprint,
    canonical_operator_identity,
    is_supported_learning_change,
    parse_request_event_payload,
    validate_decision_reason,
)


def _payload(*, decision: str = "accept") -> dict[str, object]:
    team_id = uuid4()
    learning_change_id = uuid4()
    operator_id = canonical_operator_identity(
        "https://host.example/identity", "operator-42"
    )
    assessment_id = uuid4() if decision == "accept" else None
    assessment_hash = "sha256:" + "a" * 64 if decision == "accept" else None
    rejection_reason = "Insufficient evidence." if decision == "reject" else None
    fingerprint = build_request_fingerprint(
        team_id=team_id,
        learning_change_id=learning_change_id,
        decision=decision,
        rejection_reason=rejection_reason,
        operator_id=operator_id,
        quality_assessment_id=assessment_id,
        quality_assessment_hash=assessment_hash,
    )
    return {
        "schema_version": 2,
        "operation": "approve_learning_change",
        "learning_change_id": str(learning_change_id),
        "decision": decision,
        "rejection_reason": rejection_reason,
        "operator_id": operator_id,
        "idempotency_key_hash": "sha256:" + "b" * 64,
        "request_fingerprint": fingerprint,
        "policy_version": 4,
        "knowledge_quality_assessment_id": (
            str(assessment_id) if assessment_id else None
        ),
        "knowledge_quality_assessment_hash": assessment_hash,
        "_team_id": team_id,
    }


@pytest.mark.parametrize("decision", ["accept", "reject"])
def test_schema_v2_request_payload_round_trips(decision: str) -> None:
    payload = _payload(decision=decision)
    team_id = payload.pop("_team_id")
    parsed = parse_request_event_payload(
        payload, team_id=team_id, policy_version=4
    )

    assert parsed.schema_version == 2
    assert parsed.decision == decision
    assert parsed.learning_change_id == UUID(payload["learning_change_id"])
    if decision == "accept":
        assert parsed.quality_assessment_id is not None
        assert parsed.quality_assessment_hash == "sha256:" + "a" * 64
    else:
        assert parsed.quality_assessment_id is None
        assert parsed.quality_assessment_hash is None


def test_legacy_schema_v1_rejection_remains_valid() -> None:
    team_id = uuid4()
    learning_change_id = uuid4()
    operator_id = canonical_operator_identity(
        "https://host.example/identity", "operator-42"
    )
    rejection_reason = "Insufficient evidence."
    fingerprint_payload = json.dumps(
        {
            "operation": "approve_learning_change",
            "team_id": str(team_id),
            "learning_change_id": str(learning_change_id),
            "decision": "reject",
            "rejection_reason": rejection_reason,
            "operator_id": operator_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload = {
        "schema_version": 1,
        "operation": "approve_learning_change",
        "learning_change_id": str(learning_change_id),
        "decision": "reject",
        "rejection_reason": rejection_reason,
        "operator_id": operator_id,
        "idempotency_key_hash": "sha256:" + "b" * 64,
        "request_fingerprint": (
            "sha256:"
            + hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()
        ),
        "policy_version": 4,
    }

    parsed = parse_request_event_payload(
        payload, team_id=team_id, policy_version=4
    )

    assert parsed.schema_version == 1
    assert parsed.decision == "reject"
    assert parsed.quality_assessment_id is None


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda p: p.update(schema_version=True),
            "operator_task_request_payload_invalid",
        ),
        (
            lambda p: p.update(operation="revise"),
            "operator_task_request_payload_invalid",
        ),
        (
            lambda p: p.update(decision="maybe"),
            "operator_task_request_payload_invalid",
        ),
        (
            lambda p: p.update(rejection_reason="unexpected"),
            "operator_task_request_payload_invalid",
        ),
        (
            lambda p: p.update(
                operator_id='{"sub":"operator-42","iss":"https://host.example/identity"}'
            ),
            "operator_task_request_identity_invalid",
        ),
        (
            lambda p: p.update(idempotency_key_hash="not-a-hash"),
            "operator_task_request_payload_invalid",
        ),
        (
            lambda p: p.update(knowledge_quality_assessment_id="not-a-uuid"),
            "operator_quality_assessment_reference_invalid",
        ),
        (
            lambda p: p.update(learning_change_id="NOT-A-UUID"),
            "operator_task_request_target_invalid",
        ),
        (
            lambda p: p.update(policy_version=5),
            "operator_task_request_payload_invalid",
        ),
        (
            lambda p: p.update(request_fingerprint="sha256:" + "f" * 64),
            "operator_task_request_fingerprint_invalid",
        ),
    ],
)
def test_schema_v2_malformed_common_integrity_fails_closed(
    mutation, reason: str
) -> None:
    payload = _payload()
    team_id = payload.pop("_team_id")
    mutation(payload)

    with pytest.raises(OperatorApprovalValidationError) as error:
        parse_request_event_payload(payload, team_id=team_id, policy_version=4)

    assert error.value.reason == reason


@pytest.mark.parametrize(
    ("decision", "reason", "expected"),
    [
        ("accept", None, None),
        ("reject", "  insufficient evidence  ", "insufficient evidence"),
    ],
)
def test_decision_reason_is_canonicalized(
    decision: str, reason: str | None, expected: str | None
) -> None:
    assert validate_decision_reason(decision, reason) == expected


@pytest.mark.parametrize(
    ("target_kind", "operation", "target_id", "supported"),
    [
        ("knowledge_item", "create", None, True),
        ("knowledge_item", "revise", uuid4(), False),
        ("knowledge_item", "revalidate", uuid4(), False),
        ("knowledge_item", "supersede", uuid4(), False),
        ("knowledge_item", "retire", uuid4(), False),
        ("other", "create", None, False),
        ("knowledge_item", "create", uuid4(), False),
    ],
)
def test_only_knowledge_item_create_target_is_supported(
    target_kind: str, operation: str, target_id, supported: bool
) -> None:
    assert is_supported_learning_change(
        target_kind=target_kind,
        operation=operation,
        target_id=target_id,
    ) is supported


@pytest.mark.parametrize(
    ("issuer", "subject", "reason"),
    [
        (" ", "operator", "invalid_operator_issuer"),
        ("issuer", "", "invalid_operator_subject"),
        ("issuer", "operator\n42", "invalid_operator_subject"),
    ],
)
def test_operator_identity_requires_canonical_nonempty_parts(
    issuer: str, subject: str, reason: str
) -> None:
    with pytest.raises(OperatorApprovalValidationError) as error:
        canonical_operator_identity(issuer, subject)
    assert error.value.reason == reason
