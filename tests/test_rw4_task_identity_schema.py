"""PostgreSQL proofs for the D2 canonical Task identity schema."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import json

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Signal, Task, Team, TeamPolicy
from core.triage_identity import TRIAGE_IDENTITY_VERSION, canonical_triage_task_id


@dataclass(frozen=True)
class TriageSchemaContext:
    team_id: UUID
    policy_id: UUID
    signal_id: UUID


@pytest.fixture
def triage_schema_context(
    session_factory: sessionmaker[Session],
) -> Iterator[TriageSchemaContext]:
    team_id, policy_id, signal_id = uuid4(), uuid4(), uuid4()
    digest = "a" * 64
    context = TriageSchemaContext(team_id, policy_id, signal_id)
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="triage_schema_test", status="active"))
        session.flush()
        session.add(
            TeamPolicy(id=policy_id, team_id=team_id, version=1, rules={})
        )
        session.add(
            Signal(
                id=signal_id,
                domain="triage_schema_test",
                source_type="test_feed",
                origin_url=f"https://example.test/{signal_id}",
                fetched_at=datetime.now(timezone.utc),
                content_hash=f"sha256:{digest}",
                snapshot_ref=f"snap://sha256/{digest}",
            )
        )
    try:
        yield context
    finally:
        with session_factory.begin() as session:
            task_ids = session.scalars(
                select(Task.id).where(Task.team_id == team_id)
            ).all()
            if task_ids:
                session.execute(delete(Event).where(Event.task_id.in_(task_ids)))
                session.execute(delete(Task).where(Task.id.in_(task_ids)))
            session.execute(delete(Signal).where(Signal.id == signal_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


def _triage_task(context: TriageSchemaContext, *, task_id: UUID | None = None) -> Task:
    return Task(
        id=task_id or canonical_triage_task_id(context.team_id, context.signal_id),
        team_id=context.team_id,
        task_type="triage_signal",
        status="pending",
        policy_version=1,
        signal_id=context.signal_id,
        identity_version=TRIAGE_IDENTITY_VERSION,
        allowed_writes=[],
        budget={
            "max_tool_calls": 0,
            "max_cost_usd": 0,
            "deadline_seconds": 30,
        },
    )


def test_existing_non_triage_task_keeps_null_identity_fields(
    session_factory: sessionmaker[Session],
    triage_schema_context: TriageSchemaContext,
) -> None:
    tasks = [
        Task(
            id=uuid4(),
            team_id=triage_schema_context.team_id,
            task_type="ingest_source",
            status="pending",
            policy_version=1,
            allowed_writes=["Signal"],
            budget={
                "max_tool_calls": 0,
                "max_cost_usd": 0,
                "deadline_seconds": 30,
            },
        )
        for _ in range(2)
    ]
    with session_factory.begin() as session:
        session.add_all(tasks)
    with session_factory() as session:
        for task in tasks:
            stored = session.get(Task, task.id)
            assert stored is not None
            assert stored.signal_id is None
            assert stored.identity_version is None


@pytest.mark.parametrize("field", ["signal_id", "identity_version"])
def test_triage_task_rejects_each_missing_identity_field(
    session_factory: sessionmaker[Session],
    triage_schema_context: TriageSchemaContext,
    field: str,
) -> None:
    task = _triage_task(triage_schema_context)
    setattr(task, field, None)

    with pytest.raises(DBAPIError, match="ck_tasks_triage_identity"):
        with session_factory.begin() as session:
            session.add(task)


def test_triage_task_rejects_empty_identity_version(
    session_factory: sessionmaker[Session],
    triage_schema_context: TriageSchemaContext,
) -> None:
    task = _triage_task(triage_schema_context)
    task.identity_version = ""

    with pytest.raises(DBAPIError, match="ck_tasks_triage_identity"):
        with session_factory.begin() as session:
            session.add(task)


def test_task_signal_foreign_key_rejects_missing_signal(
    session_factory: sessionmaker[Session],
    triage_schema_context: TriageSchemaContext,
) -> None:
    task = _triage_task(triage_schema_context)
    task.signal_id = uuid4()

    with pytest.raises(DBAPIError, match="fk_tasks_signal"):
        with session_factory.begin() as session:
            session.add(task)


def test_non_triage_task_cannot_carry_triage_identity(
    session_factory: sessionmaker[Session],
    triage_schema_context: TriageSchemaContext,
) -> None:
    task = Task(
        id=uuid4(),
        team_id=triage_schema_context.team_id,
        task_type="ingest_source",
        status="pending",
        policy_version=1,
        signal_id=triage_schema_context.signal_id,
        identity_version=TRIAGE_IDENTITY_VERSION,
        allowed_writes=["Signal"],
        budget={"max_tool_calls": 0, "max_cost_usd": 0, "deadline_seconds": 30},
    )

    with pytest.raises(DBAPIError, match="ck_tasks_triage_identity"):
        with session_factory.begin() as session:
            session.add(task)


def test_composite_constraint_rejects_second_uuid_for_same_logical_identity(
    session_factory: sessionmaker[Session],
    triage_schema_context: TriageSchemaContext,
) -> None:
    with session_factory.begin() as session:
        session.add(_triage_task(triage_schema_context))

    second_task = _triage_task(triage_schema_context, task_id=uuid4())
    with pytest.raises(DBAPIError, match="uq_tasks_team_signal_identity"):
        with session_factory.begin() as session:
            session.add(second_task)


def test_partial_unique_index_limits_request_event_per_task(
    session_factory: sessionmaker[Session],
    triage_schema_context: TriageSchemaContext,
) -> None:
    task = _triage_task(triage_schema_context)
    with session_factory.begin() as session:
        session.add(task)

    with session_factory.begin() as session:
        session.add(
            Event(
                id=uuid4(),
                task_id=task.id,
                type="triage_signal_requested",
                payload={},
                created_at=datetime.now(timezone.utc),
            )
        )

    with pytest.raises(DBAPIError, match="uq_events_triage_signal_requested_task"):
        with session_factory.begin() as session:
            session.add(
                Event(
                    id=uuid4(),
                    task_id=task.id,
                    type="triage_signal_requested",
                    payload={},
                    created_at=datetime.now(timezone.utc),
                )
            )


def test_partial_unique_index_does_not_constrain_other_event_types(
    session_factory: sessionmaker[Session],
    triage_schema_context: TriageSchemaContext,
) -> None:
    task = _triage_task(triage_schema_context)
    with session_factory.begin() as session:
        session.add(task)

    with session_factory.begin() as session:
        session.add_all(
            [
                Event(
                    id=uuid4(),
                    task_id=task.id,
                    type="task_started",
                    payload={"attempt_count": 1},
                    created_at=datetime.now(timezone.utc),
                ),
                Event(
                    id=uuid4(),
                    task_id=task.id,
                    type="task_started",
                    payload={"attempt_count": 2},
                    created_at=datetime.now(timezone.utc),
                ),
            ]
        )


def test_triage_insert_trigger_uses_security_definer_and_safe_search_path(
    database_engine,
) -> None:
    with database_engine.connect() as connection:
        trigger = connection.execute(
            text(
                """
                SELECT trg.tgenabled,
                       proc.prosecdef,
                       proc.proconfig,
                       pg_get_userbyid(proc.proowner) AS owner_name
                FROM pg_trigger AS trg
                JOIN pg_class AS relation ON relation.oid = trg.tgrelid
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                JOIN pg_proc AS proc ON proc.oid = trg.tgfoid
                WHERE namespace.nspname = current_schema()
                  AND relation.relname = 'tasks'
                  AND trg.tgname = 'trg_tasks_triage_team_lock'
                  AND NOT trg.tgisinternal
                """
            )
        ).mappings().one()
        assert trigger["tgenabled"] == "O"
        assert trigger["prosecdef"] is True
        assert "search_path=pg_catalog" in trigger["proconfig"]
        owner_exists = connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'watch_owner')")
        )
        if owner_exists:
            assert trigger["owner_name"] == "watch_owner"



def test_triage_before_insert_trigger_locks_team_even_for_on_conflict(
    database_engine,
    session_factory: sessionmaker[Session],
    triage_schema_context: TriageSchemaContext,
) -> None:
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    task = _triage_task(triage_schema_context)
    with session_factory.begin() as session:
        session.add(task)

    other_signal_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Signal(
                id=other_signal_id,
                domain="triage_schema_test",
                source_type="test_feed",
                origin_url=f"https://example.test/{other_signal_id}",
                fetched_at=datetime.now(timezone.utc),
                content_hash=f"sha256:{'b' * 64}",
                snapshot_ref=f"snap://sha256/{'b' * 64}",
            )
        )

    application_name = f"rw4-triage-lock-{uuid4().hex}"
    worker_engine = create_engine(
        database_engine.url,
        connect_args={"application_name": application_name},
    )
    started = threading.Event()
    statement = text(
        """
        INSERT INTO tasks (
            id, team_id, task_type, status, policy_version,
            signal_id, identity_version, allowed_writes, budget
        )
        VALUES (
            :id, :team_id, 'triage_signal', 'pending', 1,
            :signal_id, :identity_version, '[]'::jsonb,
            CAST(:budget AS jsonb)
        )
        ON CONFLICT (id) DO NOTHING
        """
    )
    params = {
        "id": task.id,
        "team_id": triage_schema_context.team_id,
        "signal_id": other_signal_id,
        "identity_version": TRIAGE_IDENTITY_VERSION,
        "budget": json.dumps(
            {
                "max_tool_calls": 0,
                "max_cost_usd": 0,
                "deadline_seconds": 30,
            }
        ),
    }

    def attempt_conflicting_insert() -> int:
        with worker_engine.begin() as connection:
            started.set()
            result = connection.execute(statement, params)
            return result.rowcount

    try:
        with database_engine.connect() as blocker:
            transaction = blocker.begin()
            blocker.execute(
                text(
                    "SELECT id FROM teams WHERE id = :team_id "
                    "FOR UPDATE"
                ),
                {"team_id": triage_schema_context.team_id},
            )
            blocker_pid = blocker.scalar(text("SELECT pg_backend_pid()"))
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(attempt_conflicting_insert)
                waiting_for_lock = False
                try:
                    assert started.wait(timeout=5)
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        with database_engine.connect() as observer:
                            wait_event = observer.execute(
                                text(
                                    "SELECT state, wait_event_type, query, "
                                    "pg_blocking_pids(pid) "
                                    "FROM pg_stat_activity "
                                    "WHERE application_name = :application_name"
                                ),
                                {"application_name": application_name},
                            ).one_or_none()
                        # pg_blocking_pids() is the authoritative proof that
                        # this backend is waiting on the blocker. PostgreSQL may
                        # report different wait-event details across versions and
                        # execution phases, so do not make those incidental fields
                        # part of the concurrency assertion.
                        if wait_event is not None and blocker_pid in wait_event[3]:
                            waiting_for_lock = True
                            break
                        time.sleep(0.02)
                finally:
                    transaction.commit()
                assert waiting_for_lock, (
                    "triage INSERT was not blocked by the Team-row lock; "
                    f"worker_done={future.done()}, "
                    f"worker_error={future.exception() if future.done() else None}"
                )
                assert future.result(timeout=5) == 0
        with session_factory() as session:
            assert session.scalar(
                select(Task.id).where(Task.id == task.id)
            ) == task.id
    finally:
        worker_engine.dispose()
        with session_factory.begin() as session:
            session.execute(delete(Signal).where(Signal.id == other_signal_id))


def test_direct_sql_winner_with_team_lock_is_not_origin_attested(
    session_factory: sessionmaker[Session],
    triage_schema_context: TriageSchemaContext,
) -> None:
    """This is an unsupported writer demonstration, not an accepted creator path."""
    task_id = canonical_triage_task_id(
        triage_schema_context.team_id, triage_schema_context.signal_id
    )
    now = datetime.now(timezone.utc)
    digest = "a" * 64
    payload = {
        "schema_version": "triage_request_v1",
        "task_id": str(task_id),
        "team_id": str(triage_schema_context.team_id),
        "signal_id": str(triage_schema_context.signal_id),
        "signal_snapshot_ref": f"snap://sha256/{digest}",
        "signal_content_hash": f"sha256:{digest}",
        "as_of": now.isoformat(),
        "team_revision_watermark": 0,
        "policy_version": 1,
        "matcher_id": "test-matcher",
        "matcher_version": "1",
        "embedding_space_key": "test-space",
        "chunking_version": "test-chunking",
        "requested_by_principal": {
            "issuer": "untrusted-direct-sql",
            "subject": "forged-requester",
        },
        "request_fingerprint": f"sha256:{'b' * 64}",
        "matching_pins": {"schema_version": 1},
        "matching_pins_hash": f"sha256:{'c' * 64}",
    }

    with session_factory.begin() as session:
        session.execute(
            text(
                "SELECT id FROM teams WHERE id = :team_id FOR NO KEY UPDATE"
            ),
            {"team_id": triage_schema_context.team_id},
        )
        session.execute(
            text(
                """
                INSERT INTO tasks (
                    id, team_id, task_type, status, policy_version,
                    signal_id, identity_version, allowed_writes, budget
                )
                VALUES (
                    :id, :team_id, 'triage_signal', 'pending', 1,
                    :signal_id, :identity_version, '[]'::jsonb, '{}'::jsonb
                )
                """
            ),
            {
                "id": task_id,
                "team_id": triage_schema_context.team_id,
                "signal_id": triage_schema_context.signal_id,
                "identity_version": TRIAGE_IDENTITY_VERSION,
            },
        )
        session.add(
            Event(
                id=uuid4(),
                task_id=task_id,
                type="triage_signal_requested",
                payload=payload,
                created_at=now,
            )
        )

    with session_factory() as session:
        stored_task = session.get(Task, task_id)
        stored_event = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == "triage_signal_requested",
            )
        )
        assert stored_task is not None
        assert stored_task.signal_id == triage_schema_context.signal_id
        assert stored_event is not None
        assert stored_event.payload["requested_by_principal"] == payload[
            "requested_by_principal"
        ]
        # The database accepts this shape but does not validate its fingerprint or
        # record whether Control Room created it. A future creator must validate
        # request evidence; this trigger alone cannot attest writer origin.
        assert "created_by_control_room" not in Task.__table__.columns
        assert "created_by_control_room" not in Event.__table__.columns


def test_triage_task_rejects_unaccepted_identity_version(
    session_factory: sessionmaker[Session],
    triage_schema_context: TriageSchemaContext,
) -> None:
    task = _triage_task(triage_schema_context)
    task.identity_version = "triage_identity_v2"

    with pytest.raises(DBAPIError, match="ck_tasks_triage_identity"):
        with session_factory.begin() as session:
            session.add(task)


def test_task_identity_support_key_exists_for_disposition_composite_fk(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        definition = session.scalar(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid = 'tasks'::regclass
                  AND conname = 'uq_tasks_id_team_signal_identity'
                  AND contype = 'u'
                """
            )
        )

    assert definition is not None
    assert "(id, team_id, signal_id, identity_version)" in definition


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("id", uuid4()),
        ("team_id", uuid4()),
        ("task_type", "ingest_source"),
        ("signal_id", uuid4()),
        ("identity_version", "triage_identity_v2"),
    ],
)
def test_triage_task_identity_cannot_be_mutated(
    session_factory: sessionmaker[Session],
    triage_schema_context: TriageSchemaContext,
    field: str,
    replacement: object,
) -> None:
    task = _triage_task(triage_schema_context)
    with session_factory.begin() as session:
        session.add(task)

    with pytest.raises(DBAPIError, match="triage Task identity is immutable"):
        with session_factory.begin() as session:
            session.execute(
                text(f"UPDATE tasks SET {field} = :replacement WHERE id = :task_id"),
                {"replacement": replacement, "task_id": task.id},
            )

    with session_factory() as session:
        stored = session.get(Task, task.id)
        assert stored is not None
        assert stored.team_id == triage_schema_context.team_id
        assert stored.task_type == "triage_signal"
        assert stored.signal_id == triage_schema_context.signal_id
        assert stored.identity_version == TRIAGE_IDENTITY_VERSION
