"""R6-A Step 1: Task lifecycle metadata and Outcome schema integrity."""

from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Outcome, Task, Team, TeamPolicy
from core.plans import PlanService
from tests.test_plans import plan_request  # noqa: F401

_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64
_REF_A = f"snap://sha256/{_DIGEST_A}"
_HASH_A = f"sha256:{_DIGEST_A}"
_REF_B = f"snap://sha256/{_DIGEST_B}"
_HASH_B = f"sha256:{_DIGEST_B}"


@pytest.fixture
def outcome_context(
    session_factory: sessionmaker[Session],
) -> Iterator[dict[str, UUID]]:
    """An active Team with a running Task, for Outcome attribution."""
    team_id, policy_id, task_id = uuid4(), uuid4(), uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="outcome_test", status="active"))
        session.flush()
        session.add(TeamPolicy(id=policy_id, team_id=team_id, version=1, rules={}))
        session.flush()
        session.add(
            Task(
                id=task_id,
                team_id=team_id,
                task_type="ingest_source",
                status="running",
                policy_version=1,
                allowed_writes=["Signal"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.0,
                    "deadline_seconds": 60,
                },
            )
        )
    try:
        yield {"team_id": team_id, "task_id": task_id}
    finally:
        with session_factory.begin() as session:
            session.execute(
                delete(Outcome).where(Outcome.recorded_by_task_id == task_id)
            )
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


def _outcome_row(context: dict[str, UUID], **overrides: Any) -> Outcome:
    values: dict[str, Any] = {
        "id": uuid4(),
        "team_id": context["team_id"],
        "subject_kind": "task",
        "subject_id": context["task_id"],
        "outcome_type": "task_execution",
        "expected": None,
        "observation_snapshot_ref": _REF_A,
        "observation_hash": _HASH_A,
        "observed_at": datetime.now(timezone.utc),
        "recorded_by_task_id": context["task_id"],
    }
    values.update(overrides)
    return Outcome(**values)


def _insert(session_factory: sessionmaker[Session], row: Outcome) -> None:
    with session_factory.begin() as session:
        session.add(row)


# --- Task lifecycle metadata -------------------------------------------------


def test_task_lifecycle_columns_and_defaults(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    with session_factory() as session:
        task = session.get(Task, outcome_context["task_id"])
        assert task is not None
        assert task.created_at is not None
        assert task.created_at.tzinfo is not None
        assert task.completed_at is None
        assert task.max_attempts == 3


def test_plan_materialization_pins_max_attempts(
    request: pytest.FixtureRequest, session_factory: sessionmaker[Session]
) -> None:
    materialization = request.getfixturevalue("plan_request")
    result = PlanService(session_factory).create(**materialization)
    with session_factory() as session:
        tasks = list(
            session.scalars(select(Task).where(Task.plan_id == result.plan_id))
        )
    assert tasks
    for task in tasks:
        assert task.max_attempts == 3
        assert task.created_at is not None
        assert task.completed_at is None


# --- Observation state constraint -------------------------------------------


def test_prediction_registered_accepts_expected_with_null_observation(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    _insert(
        session_factory,
        _outcome_row(
            outcome_context,
            outcome_type="prediction_registered",
            expected={"resolution_condition": "x", "check_by": "2026-01-01"},
            observation_snapshot_ref=None,
            observation_hash=None,
            observed_at=None,
        ),
    )
    with session_factory() as session:
        stored = session.scalar(
            select(Outcome).where(
                Outcome.recorded_by_task_id == outcome_context["task_id"]
            )
        )
        assert stored is not None
        assert stored.expected is not None
        assert stored.observation_snapshot_ref is None


def test_prediction_registered_rejects_null_expected(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    with pytest.raises(DBAPIError, match="ck_outcomes_expected_present"):
        _insert(
            session_factory,
            _outcome_row(
                outcome_context,
                outcome_type="prediction_registered",
                expected=None,
                observation_snapshot_ref=None,
                observation_hash=None,
                observed_at=None,
            ),
        )


@pytest.mark.parametrize(
    "populated",
    [
        ("observation_snapshot_ref",),
        ("observation_hash",),
        ("observed_at",),
        ("observation_snapshot_ref", "observation_hash"),
        ("observation_snapshot_ref", "observed_at"),
        ("observation_hash", "observed_at"),
        ("observation_snapshot_ref", "observation_hash", "observed_at"),
    ],
)
def test_prediction_registered_rejects_partial_observation(
    session_factory: sessionmaker[Session],
    outcome_context: dict[str, UUID],
    populated: tuple[str, ...],
) -> None:
    overrides: dict[str, Any] = {
        "outcome_type": "prediction_registered",
        "expected": {"resolution_condition": "x"},
        "observation_snapshot_ref": None,
        "observation_hash": None,
        "observed_at": None,
    }
    if "observation_snapshot_ref" in populated:
        overrides["observation_snapshot_ref"] = _REF_A
    if "observation_hash" in populated:
        overrides["observation_hash"] = _HASH_A
    if "observed_at" in populated:
        overrides["observed_at"] = datetime.now(timezone.utc)
    with pytest.raises(DBAPIError, match="ck_outcomes_observation_state"):
        _insert(session_factory, _outcome_row(outcome_context, **overrides))


def test_task_execution_accepts_complete_observation(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    _insert(session_factory, _outcome_row(outcome_context))
    with session_factory() as session:
        stored = session.scalar(
            select(Outcome).where(
                Outcome.recorded_by_task_id == outcome_context["task_id"]
            )
        )
        assert stored is not None
        assert stored.outcome_type == "task_execution"
        assert stored.observation_snapshot_ref == _REF_A
        assert stored.observation_hash == _HASH_A
        assert stored.observed_at is not None


@pytest.mark.parametrize(
    "field",
    ["observation_snapshot_ref", "observation_hash", "observed_at"],
)
def test_task_execution_rejects_null_observation_field(
    session_factory: sessionmaker[Session],
    outcome_context: dict[str, UUID],
    field: str,
) -> None:
    with pytest.raises(DBAPIError, match="ck_outcomes_observation_state"):
        _insert(session_factory, _outcome_row(outcome_context, **{field: None}))


def test_other_outcome_type_accepts_complete_observation(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    _insert(
        session_factory,
        _outcome_row(
            outcome_context,
            outcome_type="prediction_check",
            expected={"registered_outcome_id": str(uuid4())},
        ),
    )
    with session_factory() as session:
        stored = session.scalar(
            select(Outcome).where(
                Outcome.recorded_by_task_id == outcome_context["task_id"]
            )
        )
        assert stored is not None
        assert stored.outcome_type == "prediction_check"


# --- Format, pair, attribution, and uniqueness constraints -------------------


def test_invalid_reference_format_is_rejected_by_ref_constraint(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    """Isolate ck_outcomes_observation_ref.

    ``split_part("x/y/z/<digest>", '/', 4)`` yields the digest, so the
    reference/hash pair agrees and only the reference format is invalid.
    """
    with pytest.raises(DBAPIError, match="ck_outcomes_observation_ref"):
        _insert(
            session_factory,
            _outcome_row(
                outcome_context,
                observation_snapshot_ref=f"x/y/z/{_DIGEST_A}",
                observation_hash=_HASH_A,
            ),
        )


def test_invalid_hash_format_is_rejected_by_hash_constraint(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    """Isolate ck_outcomes_observation_hash.

    ``split_part("md5:<digest>", ':', 2)`` yields the digest, so the
    reference/hash pair agrees and only the hash format is invalid.
    """
    with pytest.raises(DBAPIError, match="ck_outcomes_observation_hash"):
        _insert(
            session_factory,
            _outcome_row(
                outcome_context,
                observation_snapshot_ref=_REF_A,
                observation_hash=f"md5:{_DIGEST_A}",
            ),
        )


@pytest.mark.parametrize(
    "reference",
    ["snap://sha256/xyz", "snap://sha256/" + "A" * 64, "sha256:" + _DIGEST_A, "nope"],
)
def test_malformed_observation_reference_is_rejected(
    session_factory: sessionmaker[Session],
    outcome_context: dict[str, UUID],
    reference: str,
) -> None:
    # These values violate both the format and the pair constraint. PostgreSQL
    # evaluates CHECK constraints in unspecified order, so the reported name is
    # not deterministic; the isolated tests above prove each constraint alone.
    with pytest.raises(DBAPIError, match="ck_outcomes_observation_(ref|pair)"):
        _insert(
            session_factory,
            _outcome_row(outcome_context, observation_snapshot_ref=reference),
        )


@pytest.mark.parametrize(
    "digest_hash",
    ["sha256:ABC", "sha256:" + "A" * 64, "md5:" + "a" * 64, "nope"],
)
def test_malformed_observation_hash_is_rejected(
    session_factory: sessionmaker[Session],
    outcome_context: dict[str, UUID],
    digest_hash: str,
) -> None:
    # See the note above: these violate the format and pair constraints.
    with pytest.raises(DBAPIError, match="ck_outcomes_observation_(hash|pair)"):
        _insert(
            session_factory,
            _outcome_row(outcome_context, observation_hash=digest_hash),
        )


def test_observation_format_constraints_exist_in_the_database(
    session_factory: sessionmaker[Session],
) -> None:
    """The named format constraints are present, not merely implied."""
    expected = {
        "ck_outcomes_expected_present",
        "ck_outcomes_observation_hash",
        "ck_outcomes_observation_pair",
        "ck_outcomes_observation_ref",
        "ck_outcomes_observation_state",
        "ck_outcomes_task_execution_subject",
    }
    with session_factory() as session:
        names = set(
            session.scalars(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'outcomes'::regclass AND contype = 'c'"
                )
            )
        )
        unique_names = set(
            session.scalars(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'outcomes'::regclass AND contype = 'u'"
                )
            )
        )
    assert expected <= names
    assert "uq_outcomes_task_type" in unique_names


def test_mismatched_reference_and_hash_are_rejected(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    with pytest.raises(DBAPIError, match="ck_outcomes_observation_pair"):
        _insert(
            session_factory,
            _outcome_row(
                outcome_context,
                observation_snapshot_ref=_REF_A,
                observation_hash=_HASH_B,
            ),
        )


def test_matching_reference_and_hash_are_accepted(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    _insert(
        session_factory,
        _outcome_row(
            outcome_context,
            observation_snapshot_ref=_REF_B,
            observation_hash=_HASH_B,
        ),
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"subject_kind": "artifact"},
        {"subject_id": uuid4()},
    ],
)
def test_task_execution_subject_attribution_is_enforced(
    session_factory: sessionmaker[Session],
    outcome_context: dict[str, UUID],
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(DBAPIError, match="ck_outcomes_task_execution_subject"):
        _insert(session_factory, _outcome_row(outcome_context, **overrides))


def test_mismatched_task_team_attribution_is_rejected(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    other_team_id = uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=other_team_id, domain="other", status="active"))
    try:
        with pytest.raises(DBAPIError, match="fk_outcomes_task_team"):
            _insert(
                session_factory,
                _outcome_row(outcome_context, team_id=other_team_id),
            )
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Team).where(Team.id == other_team_id))


def test_duplicate_task_outcome_type_is_rejected(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    _insert(session_factory, _outcome_row(outcome_context))
    with pytest.raises(DBAPIError, match="uq_outcomes_task_type"):
        _insert(session_factory, _outcome_row(outcome_context))


def test_expected_none_is_stored_as_sql_null(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    _insert(session_factory, _outcome_row(outcome_context))
    with session_factory() as session:
        is_sql_null = session.scalar(
            select(Outcome.expected.is_(None)).where(
                Outcome.recorded_by_task_id == outcome_context["task_id"]
            )
        )
    assert is_sql_null is True


def test_outcome_requires_an_existing_task(
    session_factory: sessionmaker[Session], outcome_context: dict[str, UUID]
) -> None:
    unknown_task_id = uuid4()
    with pytest.raises(DBAPIError, match="fk_outcomes_task_team"):
        _insert(
            session_factory,
            _outcome_row(
                outcome_context,
                recorded_by_task_id=unknown_task_id,
                subject_id=unknown_task_id,
            ),
        )
