from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.knowledge_index import knowledge_item_content_hash as index_content_hash
from core.learning_history import (
    KNOWLEDGE_CONTENT_HASH_SCHEME,
    KnowledgeHistoryError,
    knowledge_item_content_hash,
)


def _item(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "team_id": uuid4(),
        "kind": "practice",
        "title": "Source review checklist",
        "statement": "Preserve contrary evidence.",
        "body": "Compare the primary source with independent evidence.",
        "applicability": {"domain": "science"},
        "preconditions": ["Source is accessible.", "Primary source is retained."],
        "assumptions": ["The source is authentic.", "The observation is independent."],
        "limitations": [
            "This does not establish causation.",
            "The sample may be incomplete.",
        ],
        "non_applicability": ["Unrelated domains.", "Unsupported decision contexts."],
        "failure_modes": ["A source may be incomplete.", "A comparison may be biased."],
        "known_counterexamples": ["Conflicting replication.", "A failed replication."],
        "missing_information": ["Independent replication.", "Longitudinal evidence."],
        "uncertainty": ["Evidence may remain incomplete.", "The sample may be narrow."],
        "confidence": Decimal("0.800"),
        "status": "active",
        "version": 1,
        "last_validated_at": None,
        "review_after": datetime(2026, 12, 1, tzinfo=timezone.utc),
        "origin_learning_change_id": uuid4(),
        "current_learning_change_id": uuid4(),
        "supersedes_item_id": None,
        "superseded_by_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_v2_hash_matches_frozen_domain_separated_vector() -> None:
    item = _item()

    assert KNOWLEDGE_CONTENT_HASH_SCHEME == "watch.r7b.knowledge-content.v2"
    # The fixed vector uses the exact semantic content in _item(), with
    # confidence normalized to the fixed-point string "0.800".
    # UUIDs, Team identity, lifecycle state, dates and pointers are excluded.
    assert knowledge_item_content_hash(item) == (
        "sha256:2e9c15d1e9c4d90961bbca396046a73f8f44379a8778dcb6d5978abb37b22a18"
    )


@pytest.mark.parametrize(
    "field",
    [
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
    ],
)
def test_every_semantic_field_changes_the_hash(field: str) -> None:
    original = _item()
    changed = _item()
    value = deepcopy(getattr(changed, field))

    if field == "confidence":
        value = Decimal("0.801")
    elif isinstance(value, str):
        value = value + " changed"
    elif isinstance(value, dict):
        value["additional"] = "changed"
    elif isinstance(value, list):
        value.append("changed")
    else:
        raise AssertionError(f"Unhandled semantic field type: {field}")

    setattr(changed, field, value)
    assert knowledge_item_content_hash(changed) != knowledge_item_content_hash(original)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", uuid4()),
        ("team_id", uuid4()),
        ("status", "needs_review"),
        ("version", 99),
        ("last_validated_at", datetime(2026, 10, 1, tzinfo=timezone.utc)),
        ("review_after", datetime(2027, 1, 1, tzinfo=timezone.utc)),
        ("origin_learning_change_id", uuid4()),
        ("current_learning_change_id", uuid4()),
        ("supersedes_item_id", uuid4()),
        ("superseded_by_id", uuid4()),
    ],
)
def test_lifecycle_and_identity_fields_do_not_change_the_hash(
    field: str, value: object
) -> None:
    original = _item()
    changed = _item()
    setattr(changed, field, value)

    assert knowledge_item_content_hash(changed) == knowledge_item_content_hash(original)


@pytest.mark.parametrize(
    "field",
    [
        "preconditions",
        "assumptions",
        "limitations",
        "non_applicability",
        "failure_modes",
        "known_counterexamples",
        "missing_information",
        "uncertainty",
    ],
)
def test_array_order_is_semantic(field: str) -> None:
    original = _item()
    changed = _item()
    setattr(changed, field, list(reversed(getattr(changed, field))))

    assert knowledge_item_content_hash(changed) != knowledge_item_content_hash(original)


def test_confidence_only_change_changes_the_hash() -> None:
    original = _item()
    changed = _item(confidence=Decimal("0.9"))

    assert knowledge_item_content_hash(changed) != knowledge_item_content_hash(original)


def test_confidence_string_and_decimal_share_fixed_point_normalization() -> None:
    decimal_value = _item(confidence=Decimal("0.800"))
    string_value = _item(confidence="0.800")

    assert knowledge_item_content_hash(string_value) == knowledge_item_content_hash(
        decimal_value
    )


def test_json_object_key_order_does_not_change_the_hash() -> None:
    original = _item(applicability={"domain": "science", "region": "global"})
    reordered = _item(applicability={"region": "global", "domain": "science"})

    assert knowledge_item_content_hash(reordered) == knowledge_item_content_hash(
        original
    )


@pytest.mark.parametrize(
    "confidence",
    [True, 0.8, Decimal("NaN"), Decimal("Infinity"), "not-a-number"],
)
def test_invalid_confidence_fails_closed(confidence: object) -> None:
    with pytest.raises(
        KnowledgeHistoryError, match="content_hash_confidence_invalid"
    ):
        knowledge_item_content_hash(_item(confidence=confidence))


def test_team_experience_hash_entrypoint_uses_the_v2_contract() -> None:
    item = _item()

    assert index_content_hash(item) == knowledge_item_content_hash(item)
