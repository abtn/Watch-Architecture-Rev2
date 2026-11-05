from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.learning_history import (
    LEGACY_STATE_FIELDS,
    KnowledgeHistoryError,
    ReviewMarker,
    encode_state_snapshot,
    reconstruct_history,
)


def _state(item_id, team_id, root_id, *, pointer=None, status="active", version=1):
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return {
        "id": str(item_id),
        "team_id": str(team_id),
        "kind": "practice",
        "title": "Source review checklist",
        "statement": "Preserve contrary evidence.",
        "body": "Compare the primary source with independent evidence.",
        "applicability": {"domain": "science"},
        "preconditions": ["Source is accessible."],
        "assumptions": ["The source is authentic."],
        "limitations": ["This does not establish causation."],
        "non_applicability": ["Unrelated domains."],
        "failure_modes": ["A source may be incomplete."],
        "known_counterexamples": ["Conflicting replication."],
        "missing_information": ["Independent replication."],
        "uncertainty": ["Evidence may remain incomplete."],
        "confidence": "0.800",
        "status": status,
        "version": version,
        "last_validated_at": None,
        "review_after": (now + timedelta(days=1)).isoformat(),
        "origin_learning_change_id": str(root_id),
        "current_learning_change_id": str(pointer or root_id),
        "supersedes_item_id": None,
        "superseded_by_id": None,
    }


def _change(
    change_id,
    team_id,
    operation,
    target_id,
    committed_at,
    *,
    previous_state=None,
    committed_state=None,
):
    return SimpleNamespace(
        id=change_id,
        team_id=team_id,
        target_kind="knowledge_item",
        target_id=target_id,
        operation=operation,
        status="accepted",
        previous_state=previous_state,
        committed_state=committed_state,
        committed_at=committed_at,
    )


def _legacy_root(item_id, team_id, root_id, committed_at=None):
    state = _state(item_id, team_id, root_id)
    legacy_state = {key: value for key, value in state.items() if key in LEGACY_STATE_FIELDS}
    change = _change(
        root_id,
        team_id,
        "create",
        None,
        committed_at or datetime(2026, 10, 1, tzinfo=timezone.utc),
        committed_state=legacy_state,
    )
    return change, state


def test_legacy_create_root_reconstructs_only_missing_pointer_fields():
    item_id, team_id, root_id = uuid4(), uuid4(), uuid4()
    root, state = _legacy_root(item_id, team_id, root_id)

    result = reconstruct_history(
        [root],
        item_id=item_id,
        team_id=team_id,
        origin_learning_change_id=root_id,
        current_learning_change_id=root_id,
    )

    assert result.state == state
    assert result.reconstructed_legacy_fields == {
        "current_learning_change_id",
        "supersedes_item_id",
        "superseded_by_id",
    }
    assert result.learning_change_ids == (root_id,)


def test_versioned_create_root_is_not_marked_as_legacy():
    item_id, team_id, root_id = uuid4(), uuid4(), uuid4()
    _, state = _legacy_root(item_id, team_id, root_id)
    root = _change(
        root_id,
        team_id,
        "create",
        None,
        datetime(2026, 10, 1, tzinfo=timezone.utc),
        committed_state=encode_state_snapshot(state),
    )

    result = reconstruct_history(
        [root],
        item_id=item_id,
        team_id=team_id,
        origin_learning_change_id=root_id,
        current_learning_change_id=root_id,
    )

    assert result.state == state
    assert result.reconstructed_legacy_fields == frozenset()


def test_revise_chain_uses_pointer_links_and_matches_leaf_state():
    item_id, team_id, root_id, revise_id = uuid4(), uuid4(), uuid4(), uuid4()
    root, root_state = _legacy_root(item_id, team_id, root_id)
    revised = dict(root_state)
    revised.update(
        {
            "title": "Revised source review checklist",
            "version": 2,
            "last_validated_at": None,
            "current_learning_change_id": str(revise_id),
            "review_after": datetime(2026, 11, 2, tzinfo=timezone.utc).isoformat(),
        }
    )
    revise = _change(
        revise_id,
        team_id,
        "revise",
        item_id,
        datetime(2026, 11, 2, tzinfo=timezone.utc),
        previous_state=encode_state_snapshot(root_state),
        committed_state=encode_state_snapshot(revised),
    )

    result = reconstruct_history(
        [revise, root],
        item_id=item_id,
        team_id=team_id,
        origin_learning_change_id=root_id,
        current_learning_change_id=revise_id,
    )

    assert result.state == revised
    assert result.learning_change_ids == (root_id, revise_id)


def test_missing_parent_fails_closed():
    item_id, team_id, root_id, revise_id, missing_id = (
        uuid4() for _ in range(5)
    )
    root, root_state = _legacy_root(item_id, team_id, root_id)
    previous = dict(root_state)
    previous["current_learning_change_id"] = str(missing_id)
    revised = dict(root_state)
    revised.update({"version": 2, "current_learning_change_id": str(revise_id)})
    revise = _change(
        revise_id,
        team_id,
        "revise",
        item_id,
        datetime(2026, 11, 2, tzinfo=timezone.utc),
        previous_state=encode_state_snapshot(previous),
        committed_state=encode_state_snapshot(revised),
    )

    with pytest.raises(KnowledgeHistoryError, match="history_missing_parent"):
        reconstruct_history(
            [root, revise],
            item_id=item_id,
            team_id=team_id,
            origin_learning_change_id=root_id,
            current_learning_change_id=revise_id,
        )


def test_fork_from_one_pointer_fails_closed():
    item_id, team_id, root_id, first_id, second_id = (
        uuid4() for _ in range(5)
    )
    root, root_state = _legacy_root(item_id, team_id, root_id)
    first_state = dict(root_state)
    first_state.update({"version": 2, "current_learning_change_id": str(first_id)})
    second_state = dict(root_state)
    second_state.update({"version": 2, "title": "Other branch",
                         "current_learning_change_id": str(second_id)})
    first = _change(
        first_id, team_id, "revise", item_id,
        datetime(2026, 11, 2, tzinfo=timezone.utc),
        previous_state=encode_state_snapshot(root_state),
        committed_state=encode_state_snapshot(first_state),
    )
    second = _change(
        second_id, team_id, "revise", item_id,
        datetime(2026, 11, 3, tzinfo=timezone.utc),
        previous_state=encode_state_snapshot(root_state),
        committed_state=encode_state_snapshot(second_state),
    )

    with pytest.raises(KnowledgeHistoryError, match="history_fork"):
        reconstruct_history(
            [root, first, second],
            item_id=item_id,
            team_id=team_id,
            origin_learning_change_id=root_id,
            current_learning_change_id=second_id,
        )


def test_cross_team_accepted_record_fails_closed():
    item_id, team_id, root_id, foreign_id, foreign_team = (
        uuid4() for _ in range(5)
    )
    root, root_state = _legacy_root(item_id, team_id, root_id)
    foreign_state = dict(root_state)
    foreign_state.update({"version": 2, "team_id": str(foreign_team),
                          "current_learning_change_id": str(foreign_id)})
    foreign = _change(
        foreign_id,
        foreign_team,
        "revise",
        item_id,
        datetime(2026, 11, 2, tzinfo=timezone.utc),
        previous_state=encode_state_snapshot(root_state),
        committed_state=encode_state_snapshot(foreign_state),
    )

    with pytest.raises(KnowledgeHistoryError, match="accepted_change_cross_team"):
        reconstruct_history(
            [root, foreign],
            item_id=item_id,
            team_id=team_id,
            origin_learning_change_id=root_id,
            current_learning_change_id=foreign_id,
        )


def test_previous_snapshot_must_equal_parent_snapshot():
    item_id, team_id, root_id, revise_id = uuid4(), uuid4(), uuid4(), uuid4()
    root, root_state = _legacy_root(item_id, team_id, root_id)
    forged_previous = dict(root_state)
    forged_previous["title"] = "Forged parent value"
    revised = dict(root_state)
    revised.update({"version": 2, "current_learning_change_id": str(revise_id)})
    revise = _change(
        revise_id,
        team_id,
        "revise",
        item_id,
        datetime(2026, 11, 2, tzinfo=timezone.utc),
        previous_state=encode_state_snapshot(forged_previous),
        committed_state=encode_state_snapshot(revised),
    )

    with pytest.raises(
        KnowledgeHistoryError, match="previous_snapshot_does_not_match_parent_state"
    ):
        reconstruct_history(
            [root, revise],
            item_id=item_id,
            team_id=team_id,
            origin_learning_change_id=root_id,
            current_learning_change_id=revise_id,
        )


def test_revalidation_cannot_change_confidence():
    item_id, team_id, root_id, revalidate_id = uuid4(), uuid4(), uuid4(), uuid4()
    root, root_state = _legacy_root(item_id, team_id, root_id)
    reviewed_parent = dict(root_state)
    reviewed_parent["status"] = "needs_review"
    active = dict(root_state)
    active.update(
        {
            "status": "active",
            "last_validated_at": datetime(2026, 11, 3, tzinfo=timezone.utc).isoformat(),
            "confidence": "0.900",
            "current_learning_change_id": str(revalidate_id),
        }
    )
    revalidate = _change(
        revalidate_id,
        team_id,
        "revalidate",
        item_id,
        datetime(2026, 11, 3, tzinfo=timezone.utc),
        previous_state=encode_state_snapshot(reviewed_parent),
        committed_state=encode_state_snapshot(active),
    )
    marker = ReviewMarker(
        event_id=uuid4(),
        item_id=item_id,
        current_learning_change_id=root_id,
        version=1,
        review_after=root_state["review_after"],
        origin_learning_change_id=root_id,
        reviewed_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )

    with pytest.raises(KnowledgeHistoryError, match="revalidate_transition_invalid"):
        reconstruct_history(
            [root, revalidate],
            item_id=item_id,
            team_id=team_id,
            origin_learning_change_id=root_id,
            current_learning_change_id=revalidate_id,
            review_markers=[marker],
        )


def test_verified_d7_overlay_moves_active_state_to_needs_review():
    item_id, team_id, root_id = uuid4(), uuid4(), uuid4()
    root, root_state = _legacy_root(item_id, team_id, root_id)
    marker = ReviewMarker(
        event_id=uuid4(),
        item_id=item_id,
        current_learning_change_id=root_id,
        version=1,
        review_after=root_state["review_after"],
        origin_learning_change_id=root_id,
        reviewed_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
    )

    result = reconstruct_history(
        [root],
        item_id=item_id,
        team_id=team_id,
        origin_learning_change_id=root_id,
        current_learning_change_id=root_id,
        review_markers=[marker],
    )

    assert result.state["status"] == "needs_review"
    assert result.applied_review_event_ids == (marker.event_id,)


def test_legacy_review_event_with_ambiguous_state_match_fails_closed():
    item_id, team_id, root_id, revalidate_id = uuid4(), uuid4(), uuid4(), uuid4()
    root, root_state = _legacy_root(item_id, team_id, root_id)
    reviewed_parent = dict(root_state)
    reviewed_parent["status"] = "needs_review"
    active_again = dict(root_state)
    active_again.update(
        {
            "last_validated_at": datetime(2026, 11, 3, tzinfo=timezone.utc).isoformat(),
            "current_learning_change_id": str(revalidate_id),
        }
    )
    revalidate = _change(
        revalidate_id,
        team_id,
        "revalidate",
        item_id,
        datetime(2026, 11, 3, tzinfo=timezone.utc),
        previous_state=encode_state_snapshot(reviewed_parent),
        committed_state=encode_state_snapshot(active_again),
    )
    marker = ReviewMarker(
        event_id=uuid4(),
        item_id=item_id,
        current_learning_change_id=None,
        version=1,
        review_after=root_state["review_after"],
        origin_learning_change_id=root_id,
        reviewed_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
    )

    with pytest.raises(
        KnowledgeHistoryError, match="legacy_review_event_placement_ambiguous"
    ):
        reconstruct_history(
            [root, revalidate],
            item_id=item_id,
            team_id=team_id,
            origin_learning_change_id=root_id,
            current_learning_change_id=revalidate_id,
            review_markers=[marker],
        )
