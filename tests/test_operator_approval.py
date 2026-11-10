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

def _approval_binding(
    team_id: UUID,
    learning_change_id: UUID,
    operator_id: str,
    *,
    accepted: bool,
) -> dict[str, object]:
    assessment_id = uuid4() if accepted else None
    assessment_hash = "sha256:" + "d" * 64 if accepted else None
    return {
        "schema_version": 1,
        "team_id": str(team_id),
        "learning_change_id": str(learning_change_id),
        "operation": "create",
        "target_kind": "knowledge_item",
        "target_id": None,
        "current_learning_change_id": None,
        "target_content_version": None,
        "target_content_hash": None,
        "target_content_hash_scheme": None,
        "target_status": None,
        "target_state_hash": None,
        "proposal_hash": "sha256:" + "a" * 64,
        "proposed_state_hash": "sha256:" + "b" * 64,
        "evidence_refs": [],
        "evidence_basis_hash": "sha256:" + "c" * 64,
        "approval_policy_version": 4,
        "assessment_task_policy_version": 2 if accepted else None,
        "assessment_type": "knowledge_quality" if accepted else None,
        "assessment_id": str(assessment_id) if assessment_id else None,
        "assessment_payload_hash": assessment_hash,
        "evaluator_identity": "watch.r7a.knowledge-quality" if accepted else None,
        "evaluator_revision": "1" if accepted else None,
        "operator_provenance": None,
        "successor_binding": None,
        "operator_id": operator_id,
    }


def _bound_payload(*, decision: str = "accept") -> dict[str, object]:
    team_id = uuid4()
    learning_change_id = uuid4()
    operator_id = canonical_operator_identity(
        "https://host.example/identity", "operator-42"
    )
    accepted = decision == "accept"
    binding = _approval_binding(
        team_id, learning_change_id, operator_id, accepted=accepted
    )
    assessment_id = (
        UUID(binding["assessment_id"]) if accepted else None
    )
    assessment_hash = (
        binding["assessment_payload_hash"] if accepted else None
    )
    rejection_reason = "Insufficient evidence." if decision == "reject" else None
    fingerprint = build_request_fingerprint(
        team_id=team_id,
        learning_change_id=learning_change_id,
        decision=decision,
        rejection_reason=rejection_reason,
        operator_id=operator_id,
        quality_assessment_id=assessment_id,
        quality_assessment_hash=assessment_hash,
        approval_binding=binding,
    )
    return {
        "schema_version": 3,
        "operation": "approve_learning_change",
        "learning_change_id": str(learning_change_id),
        "decision": decision,
        "rejection_reason": rejection_reason,
        "operator_id": operator_id,
        "idempotency_key_hash": "sha256:" + "e" * 64,
        "request_fingerprint": fingerprint,
        "policy_version": 4,
        "knowledge_quality_assessment_id": (
            str(assessment_id) if assessment_id else None
        ),
        "knowledge_quality_assessment_hash": assessment_hash,
        "approval_binding": binding,
        "_team_id": team_id,
    }


@pytest.mark.parametrize("decision", ["accept", "reject"])
def test_schema_v3_request_payload_round_trips_complete_approval_binding(
    decision: str,
) -> None:
    payload = _bound_payload(decision=decision)
    team_id = payload.pop("_team_id")
    parsed = parse_request_event_payload(
        payload, team_id=team_id, policy_version=4
    )

    assert parsed.schema_version == 3
    assert parsed.approval_binding == payload["approval_binding"]
    assert parsed.approval_binding["operator_id"] == parsed.operator_id
    if decision == "accept":
        assert parsed.quality_assessment_id is not None
        assert (
            parsed.approval_binding["assessment_payload_hash"]
            == parsed.quality_assessment_hash
        )
    else:
        assert parsed.quality_assessment_id is None
        assert parsed.approval_binding["assessment_type"] is None


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda p: p["approval_binding"].update(
                assessment_payload_hash="sha256:" + "f" * 64
            ),
            "operator_approval_binding_invalid",
        ),
        (
            lambda p: p["approval_binding"].update(
                operator_id='{"iss":"https://host.example/identity","sub":"other"}'
            ),
            "operator_approval_binding_invalid",
        ),
        (
            lambda p: p["approval_binding"].update(approval_policy_version=5),
            "operator_approval_binding_invalid",
        ),
        (
            lambda p: p["approval_binding"].update(
                assessment_type="knowledge_lifecycle"
            ),
            "operator_approval_binding_invalid",
        ),
        (
            lambda p: p.pop("approval_binding"),
            "operator_task_request_payload_invalid",
        ),
    ],
)
def test_schema_v3_binding_tampering_fails_closed(mutation, reason: str) -> None:
    payload = _bound_payload()
    team_id = payload.pop("_team_id")
    mutation(payload)

    with pytest.raises(OperatorApprovalValidationError) as error:
        parse_request_event_payload(payload, team_id=team_id, policy_version=4)

    assert error.value.reason == reason


def test_request_fingerprint_changes_with_assessment_hash_or_host_principal() -> None:
    payload = _bound_payload()
    team_id = payload.pop("_team_id")
    binding = payload["approval_binding"]
    first = payload["request_fingerprint"]
    changed_hash = dict(binding)
    changed_hash["assessment_payload_hash"] = "sha256:" + "f" * 64
    changed_principal = dict(binding)
    changed_principal["operator_id"] = canonical_operator_identity(
        "https://host.example/identity", "operator-43"
    )

    def fingerprint(changed: dict[str, object]) -> str:
        return build_request_fingerprint(
            team_id=team_id,
            learning_change_id=UUID(payload["learning_change_id"]),
            decision="accept",
            rejection_reason=None,
            operator_id=payload["operator_id"],
            quality_assessment_id=UUID(payload["knowledge_quality_assessment_id"]),
            quality_assessment_hash=payload["knowledge_quality_assessment_hash"],
            approval_binding=changed,
        )

    assert fingerprint(changed_hash) != first
    assert fingerprint(changed_principal) != first

def _r7_bound_payload(operation: str) -> dict[str, object]:
    team_id = uuid4()
    learning_change_id = uuid4()
    target_id = uuid4()
    operator_id = canonical_operator_identity(
        "https://host.example/identity", "operator-42"
    )
    assessment_type = (
        "knowledge_revalidation"
        if operation == "revalidate"
        else "knowledge_lifecycle"
    )
    assessment_id = uuid4()
    binding: dict[str, object] = {
        "schema_version": 1,
        "team_id": str(team_id),
        "learning_change_id": str(learning_change_id),
        "operation": operation,
        "target_kind": "knowledge_item",
        "target_id": str(target_id),
        "current_learning_change_id": str(uuid4()),
        "target_content_version": 4,
        "target_content_hash": "sha256:" + "1" * 64,
        "target_content_hash_scheme": "watch.r7b.knowledge-content.v2",
        "target_status": "active",
        "target_state_hash": "sha256:" + "2" * 64,
        "proposal_hash": "sha256:" + "3" * 64,
        "proposed_state_hash": "sha256:" + "4" * 64,
        "evidence_refs": [{"outcome_id": str(uuid4())}],
        "evidence_basis_hash": "sha256:" + "5" * 64,
        "approval_policy_version": 8,
        "assessment_task_policy_version": 6,
        "assessment_type": assessment_type,
        "assessment_id": str(assessment_id),
        "assessment_payload_hash": "sha256:" + "6" * 64,
        "evaluator_identity": (
            "watch.r7b.revalidation" if operation == "revalidate" else None
        ),
        "evaluator_revision": "1" if operation == "revalidate" else None,
        "operator_provenance": (
            {
                "issuer": "https://host.example/identity",
                "subject": "proposal-author",
            }
            if operation in {"retire", "supersede"}
            else None
        ),
        "successor_binding": None,
        "operator_id": operator_id,
    }
    if operation == "supersede":
        binding["successor_binding"] = {
            "successor_knowledge_item_id": str(uuid4()),
            "successor_team_id": str(team_id),
            "successor_current_learning_change_id": str(uuid4()),
            "successor_content_version": 2,
            "successor_content_hash": "sha256:" + "7" * 64,
            "successor_content_hash_scheme": "watch.r7b.knowledge-content.v2",
            "successor_status": "active",
            "successor_review_after": "2027-01-02T03:04:05.123456Z",
            "successor_state_hash": "sha256:" + "8" * 64,
        }
    fingerprint = build_request_fingerprint(
        team_id=team_id,
        learning_change_id=learning_change_id,
        decision="accept",
        rejection_reason=None,
        operator_id=operator_id,
        quality_assessment_id=None,
        quality_assessment_hash=None,
        approval_binding=binding,
    )
    return {
        "schema_version": 3,
        "operation": "approve_learning_change",
        "learning_change_id": str(learning_change_id),
        "decision": "accept",
        "rejection_reason": None,
        "operator_id": operator_id,
        "idempotency_key_hash": "sha256:" + "9" * 64,
        "request_fingerprint": fingerprint,
        "policy_version": 8,
        "knowledge_quality_assessment_id": None,
        "knowledge_quality_assessment_hash": None,
        "approval_binding": binding,
        "_team_id": team_id,
    }


@pytest.mark.parametrize("operation", ["revalidate", "retire", "supersede"])
def test_schema_v3_accepts_operation_specific_r7_assessment_bindings(
    operation: str,
) -> None:
    payload = _r7_bound_payload(operation)
    team_id = payload.pop("_team_id")
    parsed = parse_request_event_payload(
        payload, team_id=team_id, policy_version=8
    )

    assert parsed.schema_version == 3
    assert parsed.quality_assessment_id is None
    assert parsed.quality_assessment_hash is None
    assert parsed.approval_binding is not None
    assert parsed.approval_binding["operation"] == operation
    assert parsed.approval_binding["assessment_type"] == (
        "knowledge_revalidation"
        if operation == "revalidate"
        else "knowledge_lifecycle"
    )


def test_schema_v3_supersede_successor_is_part_of_request_fingerprint() -> None:
    payload = _r7_bound_payload("supersede")
    team_id = payload.pop("_team_id")
    binding = payload["approval_binding"]
    successor = dict(binding["successor_binding"])
    successor["successor_review_after"] = "2027-02-02T03:04:05.123456Z"
    changed_binding = dict(binding)
    changed_binding["successor_binding"] = successor
    changed_fingerprint = build_request_fingerprint(
        team_id=team_id,
        learning_change_id=UUID(payload["learning_change_id"]),
        decision="accept",
        rejection_reason=None,
        operator_id=payload["operator_id"],
        quality_assessment_id=None,
        quality_assessment_hash=None,
        approval_binding=changed_binding,
    )
    assert changed_fingerprint != payload["request_fingerprint"]

