from uuid import UUID

from core.triage_identity import (
    TRIAGE_IDENTITY_VERSION,
    TRIAGE_TASK_NAMESPACE,
    canonical_triage_task_id,
    canonical_triage_task_name,
)


def test_triage_task_identity_v1_golden_vector() -> None:
    team_id = UUID("00000000-0000-4000-8000-000000000001")
    signal_id = UUID("00000000-0000-4000-8000-000000000002")

    assert str(TRIAGE_TASK_NAMESPACE) == "383bbdde-37be-4895-8fb7-1afa196b5cf7"
    assert TRIAGE_IDENTITY_VERSION == "triage_identity_v1"
    assert canonical_triage_task_name(team_id, signal_id) == (
        "triage_identity_v1|triage_signal|"
        "team:00000000-0000-4000-8000-000000000001|"
        "signal:00000000-0000-4000-8000-000000000002"
    )
    assert canonical_triage_task_id(team_id, signal_id) == UUID(
        "5b45ed53-a50f-51e8-ba81-ce52512aa922"
    )


def test_triage_task_identity_is_independent_of_call_order() -> None:
    team_id = UUID("00000000-0000-4000-8000-000000000001")
    signal_id = UUID("00000000-0000-4000-8000-000000000002")

    assert canonical_triage_task_id(team_id, signal_id) == canonical_triage_task_id(
        team_id, signal_id
    )
