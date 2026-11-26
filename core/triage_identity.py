"""Frozen v1 identity contract for Team-specific Signal triage Tasks."""

from uuid import UUID, uuid5

TRIAGE_TASK_NAMESPACE = UUID("383bbdde-37be-4895-8fb7-1afa196b5cf7")
TRIAGE_IDENTITY_VERSION = "triage_identity_v1"
TRIAGE_TASK_TYPE = "triage_signal"


def canonical_triage_task_name(team_id: UUID, signal_id: UUID) -> str:
    """Return the frozen, unambiguous UUIDv5 name for a Team/Signal pair."""
    return (
        f"{TRIAGE_IDENTITY_VERSION}|{TRIAGE_TASK_TYPE}|"
        f"team:{str(team_id).lower()}|signal:{str(signal_id).lower()}"
    )


def canonical_triage_task_id(team_id: UUID, signal_id: UUID) -> UUID:
    """Return the canonical Task primary key for the v1 Team/Signal identity."""
    return uuid5(TRIAGE_TASK_NAMESPACE, canonical_triage_task_name(team_id, signal_id))
