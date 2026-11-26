"""Migration-time zero-history guard for the D2 triage Task schema."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from core.database_config import resolve_test_database_url
from core.triage_identity import TRIAGE_IDENTITY_VERSION, canonical_triage_task_id


@pytest.fixture(scope="module")
def legacy_triage_schema() -> Iterator[tuple[Engine, str]]:
    database_url = resolve_test_database_url(os.environ)
    schema = f"rw4_triage_preflight_{uuid4().hex}"
    admin_engine = create_engine(database_url)
    scoped_engine: Engine | None = None
    created = False
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setenv("DATABASE_URL", database_url)
            monkeypatch.delenv("PGOPTIONS", raising=False)
            scoped_engine = create_engine(
                database_url,
                connect_args={"options": f"-c search_path={schema},public"},
            )
            with scoped_engine.begin() as connection:
                config = Config(
                    str(Path(__file__).resolve().parents[1] / "alembic.ini")
                )
                config.attributes["connection"] = connection
                config.attributes["version_table_schema"] = schema
                command.upgrade(config, "0019_rw1_world_memory")
            yield scoped_engine, schema
    finally:
        if scoped_engine is not None:
            scoped_engine.dispose()
        if created:
            with admin_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def test_migration_refuses_any_existing_triage_task_and_request_event(
    legacy_triage_schema: tuple[Engine, str],
) -> None:
    engine, schema = legacy_triage_schema
    team_id, policy_id, task_id, other_task_id = uuid4(), uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO teams (id, domain, status) "
                "VALUES (:id, 'rw4_preflight_test', 'active')"
            ),
            {"id": team_id},
        )
        connection.execute(
            text(
                "INSERT INTO team_policies (id, team_id, version, rules) "
                "VALUES (:id, :team_id, 1, '{}'::jsonb)"
            ),
            {"id": policy_id, "team_id": team_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO tasks (
                    id, team_id, task_type, status, policy_version,
                    allowed_writes, budget
                )
                VALUES (
                    :id, :team_id, 'triage_signal', 'pending', 1,
                    '[]'::jsonb, '{}'::jsonb
                )
                """
            ),
            {"id": task_id, "team_id": team_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO tasks (
                    id, team_id, task_type, status, policy_version,
                    allowed_writes, budget
                )
                VALUES (
                    :id, :team_id, 'ingest_source', 'pending', 1,
                    '[]'::jsonb, '{}'::jsonb
                )
                """
            ),
            {"id": other_task_id, "team_id": team_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO events (id, task_id, type, payload, created_at)
                VALUES
                    (
                        :event_one, :task_id, 'triage_signal_requested',
                        '{}'::jsonb, now()
                    ),
                    (
                        :event_two, :task_id, 'triage_signal_requested',
                        '{}'::jsonb, now()
                    ),
                    (
                        :event_three, :other_task_id, 'triage_signal_requested',
                        '{}'::jsonb, now()
                    )
                """
            ),
            {
                "event_one": uuid4(),
                "event_two": uuid4(),
                "event_three": uuid4(),
                "task_id": task_id,
                "other_task_id": other_task_id,
            },
        )

    with pytest.raises(
        RuntimeError,
        match=(
            "RW4 D2 migration refuses historical triage data.*"
            "duplicate_request_events_for_task.*"
            "request_event_on_non_triage_task"
        ),
    ):
        with engine.begin() as connection:
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.attributes["connection"] = connection
            config.attributes["version_table_schema"] = schema
            command.upgrade(config, "0020_rw4_task_identity")

    with engine.connect() as connection:
        revision = connection.scalar(
            text(f'SELECT version_num FROM "{schema}".alembic_version')
        )
        assert revision == "0019_rw1_world_memory"
        columns = set(
            connection.scalars(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name = 'tasks'"
                ),
                {"schema": schema},
            )
        )
        assert "signal_id" not in columns
        assert "identity_version" not in columns
        assert connection.scalar(
            text("SELECT count(*) FROM tasks WHERE id = :id"),
            {"id": task_id},
        ) == 1
        assert connection.scalar(
            text("SELECT count(*) FROM events WHERE type = 'triage_signal_requested'")
        ) == 3

    # ACCESS EXCLUSIVE locks acquired by the failed migration must be released.
    with engine.begin() as connection:
        connection.execute(text("LOCK TABLE tasks IN ACCESS EXCLUSIVE MODE NOWAIT"))
        connection.execute(text("LOCK TABLE events IN ACCESS EXCLUSIVE MODE NOWAIT"))

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM events WHERE task_id IN (:task_id, :other_task_id)"),
            {"task_id": task_id, "other_task_id": other_task_id},
        )
        connection.execute(
            text("DELETE FROM tasks WHERE id IN (:task_id, :other_task_id)"),
            {"task_id": task_id, "other_task_id": other_task_id},
        )
        connection.execute(
            text("DELETE FROM team_policies WHERE id = :id"), {"id": policy_id}
        )
        connection.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})


def _wait_for_database_lock(engine: Engine, application_name: str) -> bool:
    import time

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            wait_event = connection.scalar(
                text(
                    "SELECT wait_event_type FROM pg_stat_activity "
                    "WHERE application_name = :application_name AND state = 'active'"
                ),
                {"application_name": application_name},
            )
        if wait_event == "Lock":
            return True
        time.sleep(0.02)
    return False


def test_migration_lock_waits_for_prior_writer_and_blocks_later_writer(
    legacy_triage_schema: tuple[Engine, str],
) -> None:
    import threading
    from concurrent.futures import ThreadPoolExecutor

    engine, schema = legacy_triage_schema
    migration_name = f"rw4-migration-{uuid4().hex}"
    prior_team_id, prior_policy_id, prior_task_id = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO teams (id, domain, status) "
                "VALUES (:id, 'rw4_prior_writer', 'active')"
            ),
            {"id": prior_team_id},
        )
        connection.execute(
            text(
                "INSERT INTO team_policies (id, team_id, version, rules) "
                "VALUES (:id, :team_id, 1, '{}'::jsonb)"
            ),
            {"id": prior_policy_id, "team_id": prior_team_id},
        )
    migration_engine = create_engine(
        engine.url,
        connect_args={
            "options": f"-c search_path={schema},public",
            "application_name": migration_name,
        },
    )
    prior_writer = engine.connect()
    prior_transaction = prior_writer.begin()
    started = threading.Event()

    def migrate() -> None:
        with migration_engine.begin() as connection:
            started.set()
            config = Config(
                str(Path(__file__).resolve().parents[1] / "alembic.ini")
            )
            config.attributes["connection"] = connection
            config.attributes["version_table_schema"] = schema
            command.upgrade(config, "0020_rw4_task_identity")

    try:
        prior_writer.execute(
            text(
                """
                INSERT INTO tasks (
                    id, team_id, task_type, status, policy_version,
                    allowed_writes, budget
                )
                VALUES (
                    :id, :team_id, 'ingest_source', 'pending', 1,
                    '[]'::jsonb, '{}'::jsonb
                )
                """
            ),
            {"id": prior_task_id, "team_id": prior_team_id},
        )
        prior_writer.execute(
            text(
                """
                INSERT INTO events (id, task_id, type, payload, created_at)
                VALUES (:id, :task_id, 'task_started',
                        CAST(:payload AS jsonb), now())
                """
            ),
            {
                "id": uuid4(),
                "task_id": prior_task_id,
                "payload": '{"attempt_count":1}',
            },
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(migrate)
            try:
                assert started.wait(timeout=5)
                assert _wait_for_database_lock(engine, migration_name), (
                    "migration did not wait for the earlier tasks/events writer"
                )
            finally:
                prior_transaction.commit()
                prior_writer.close()
            future.result(timeout=15)
    finally:
        if prior_transaction.is_active:
            prior_transaction.rollback()
        prior_writer.close()
        migration_engine.dispose()

    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM events WHERE task_id = :id"), {"id": prior_task_id}
        )
        connection.execute(
            text("DELETE FROM tasks WHERE id = :id"), {"id": prior_task_id}
        )
        connection.execute(
            text("DELETE FROM team_policies WHERE id = :id"), {"id": prior_policy_id}
        )
        connection.execute(
            text("DELETE FROM teams WHERE id = :id"), {"id": prior_team_id}
        )

    # Writers started after ACCESS EXCLUSIVE is held must wait on their own table.
    team_id, policy_id, task_id, existing_task_id, event_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO teams (id, domain, status) "
                "VALUES (:id, 'rw4_lock_test', 'active')"
            ),
            {"id": team_id},
        )
        connection.execute(
            text(
                "INSERT INTO team_policies (id, team_id, version, rules) "
                "VALUES (:id, :team_id, 1, '{}'::jsonb)"
            ),
            {"id": policy_id, "team_id": team_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO tasks (
                    id, team_id, task_type, status, policy_version,
                    allowed_writes, budget
                )
                VALUES (
                    :id, :team_id, 'ingest_source', 'pending', 1,
                    '[]'::jsonb, '{}'::jsonb
                )
                """
            ),
            {"id": existing_task_id, "team_id": team_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO events (id, task_id, type, payload, created_at)
                VALUES (
                    :id, :task_id, 'task_started',
                    CAST(:payload AS jsonb), now()
                )
                """
            ),
            {
                "id": event_id,
                "task_id": existing_task_id,
                "payload": '{"attempt_count":1}',
            },
        )

    lock_holder = engine.connect()
    lock_transaction = lock_holder.begin()
    lock_holder.execute(text("LOCK TABLE tasks IN ACCESS EXCLUSIVE MODE"))
    lock_holder.execute(text("LOCK TABLE events IN ACCESS EXCLUSIVE MODE"))
    task_writer_name = f"rw4-later-task-writer-{uuid4().hex}"
    event_writer_name = f"rw4-later-event-writer-{uuid4().hex}"
    task_writer_engine = create_engine(
        engine.url,
        connect_args={
            "options": f"-c search_path={schema},public",
            "application_name": task_writer_name,
        },
    )
    event_writer_engine = create_engine(
        engine.url,
        connect_args={
            "options": f"-c search_path={schema},public",
            "application_name": event_writer_name,
        },
    )
    task_started = threading.Event()
    event_started = threading.Event()

    def insert_non_triage_task() -> None:
        with task_writer_engine.begin() as connection:
            task_started.set()
            connection.execute(
                text(
                    """
                    INSERT INTO tasks (
                        id, team_id, task_type, status, policy_version,
                        allowed_writes, budget
                    )
                    VALUES (
                        :id, :team_id, 'ingest_source', 'pending', 1,
                        '[]'::jsonb, '{}'::jsonb
                    )
                    """
                ),
                {"id": task_id, "team_id": team_id},
            )

    def update_existing_event() -> None:
        with event_writer_engine.begin() as connection:
            event_started.set()
            connection.execute(
                text(
                    "UPDATE events SET payload = CAST(:payload AS jsonb) "
                    "WHERE id = :event_id"
                ),
                {"event_id": event_id, "payload": '{"attempt_count":2}'},
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            task_future = executor.submit(insert_non_triage_task)
            event_future = executor.submit(update_existing_event)
            try:
                assert task_started.wait(timeout=5)
                assert event_started.wait(timeout=5)
                assert _wait_for_database_lock(engine, task_writer_name), (
                    "Task writer did not block behind the tasks migration lock"
                )
                assert _wait_for_database_lock(engine, event_writer_name), (
                    "Event writer did not block behind the events migration lock"
                )
            finally:
                lock_transaction.commit()
                lock_holder.close()
            task_future.result(timeout=10)
            event_future.result(timeout=10)
    finally:
        if lock_transaction.is_active:
            lock_transaction.rollback()
        lock_holder.close()
        task_writer_engine.dispose()
        event_writer_engine.dispose()
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM events WHERE id = :id"), {"id": event_id}
            )
            connection.execute(
                text("DELETE FROM tasks WHERE id = :id"), {"id": task_id}
            )
            connection.execute(
                text("DELETE FROM tasks WHERE id = :id"), {"id": existing_task_id}
            )
            connection.execute(
                text("DELETE FROM team_policies WHERE id = :id"), {"id": policy_id}
            )
            connection.execute(
                text("DELETE FROM teams WHERE id = :id"), {"id": team_id}
            )

    with engine.begin() as connection:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = connection
        config.attributes["version_table_schema"] = schema
        command.downgrade(config, "0019_rw1_world_memory")


def test_downgrade_refuses_to_discard_triage_identity_or_request_history(
    legacy_triage_schema: tuple[Engine, str],
) -> None:
    engine, schema = legacy_triage_schema
    team_id, policy_id, signal_id = uuid4(), uuid4(), uuid4()
    task_id = canonical_triage_task_id(team_id, signal_id)
    digest = "d" * 64
    with engine.begin() as connection:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = connection
        config.attributes["version_table_schema"] = schema
        command.upgrade(config, "0020_rw4_task_identity")
        connection.execute(
            text(
                "INSERT INTO teams (id, domain, status) "
                "VALUES (:id, 'rw4_downgrade_test', 'active')"
            ),
            {"id": team_id},
        )
        connection.execute(
            text(
                "INSERT INTO team_policies (id, team_id, version, rules) "
                "VALUES (:id, :team_id, 1, '{}'::jsonb)"
            ),
            {"id": policy_id, "team_id": team_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO signals (
                    id, domain, source_type, origin_url, fetched_at,
                    content_hash, snapshot_ref
                )
                VALUES (
                    :id, 'rw4_downgrade_test', 'test_feed', :origin_url,
                    :fetched_at, :content_hash, :snapshot_ref
                )
                """
            ),
            {
                "id": signal_id,
                "origin_url": f"https://example.test/{signal_id}",
                "fetched_at": datetime.now(timezone.utc),
                "content_hash": f"sha256:{digest}",
                "snapshot_ref": f"snap://sha256/{digest}",
            },
        )
        connection.execute(
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
                "team_id": team_id,
                "signal_id": signal_id,
                "identity_version": TRIAGE_IDENTITY_VERSION,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO events (id, task_id, type, payload, created_at)
                VALUES (:id, :task_id, 'triage_signal_requested',
                        '{}'::jsonb, now())
                """
            ),
            {"id": uuid4(), "task_id": task_id},
        )

    with pytest.raises(
        RuntimeError,
        match="RW4 D2 downgrade refuses to discard triage identity",
    ):
        with engine.begin() as connection:
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.attributes["connection"] = connection
            config.attributes["version_table_schema"] = schema
            command.downgrade(config, "0019_rw1_world_memory")

    with engine.connect() as connection:
        revision = connection.scalar(
            text(f'SELECT version_num FROM "{schema}".alembic_version')
        )
        assert revision == "0020_rw4_task_identity"
        assert connection.scalar(
            text(
                "SELECT count(*) FROM tasks "
                "WHERE id = :id AND signal_id = :signal_id"
            ),
            {"id": task_id, "signal_id": signal_id},
        ) == 1
        assert connection.scalar(
            text(
                "SELECT count(*) FROM events "
                "WHERE task_id = :task_id AND type = 'triage_signal_requested'"
            ),
            {"task_id": task_id},
        ) == 1
        assert connection.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_trigger AS trg
                    JOIN pg_class AS relation ON relation.oid = trg.tgrelid
                    JOIN pg_namespace AS namespace
                      ON namespace.oid = relation.relnamespace
                    WHERE namespace.nspname = :schema
                      AND relation.relname = 'tasks'
                      AND trg.tgname = 'trg_tasks_triage_team_lock'
                      AND NOT trg.tgisinternal
                )
                """
            ),
            {"schema": schema},
        )
        assert connection.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_constraint AS con
                    JOIN pg_class AS relation
                      ON relation.oid = con.conrelid
                    JOIN pg_namespace AS namespace
                      ON namespace.oid = relation.relnamespace
                    WHERE namespace.nspname = :schema
                      AND relation.relname = 'tasks'
                      AND con.conname = 'uq_tasks_id_team_signal_identity'
                      AND con.contype = 'u'
                )
                """
            ),
            {"schema": schema},
        )
        assert connection.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_trigger AS trg
                    JOIN pg_class AS relation ON relation.oid = trg.tgrelid
                    JOIN pg_namespace AS namespace
                      ON namespace.oid = relation.relnamespace
                    WHERE namespace.nspname = :schema
                      AND relation.relname = 'tasks'
                      AND trg.tgname = 'trg_tasks_triage_identity_immutable'
                      AND NOT trg.tgisinternal
                )
                """
            ),
            {"schema": schema},
        )

    # Once the protected records are explicitly removed, the empty-schema
    # downgrade is allowed and removes the D2 objects cleanly.
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM events WHERE task_id = :id"), {"id": task_id}
        )
        connection.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task_id})
        connection.execute(
            text("DELETE FROM signals WHERE id = :id"), {"id": signal_id}
        )
        connection.execute(
            text("DELETE FROM team_policies WHERE id = :id"), {"id": policy_id}
        )
        connection.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = connection
        config.attributes["version_table_schema"] = schema
        command.downgrade(config, "0019_rw1_world_memory")

    with engine.connect() as connection:
        assert connection.scalar(
            text(f'SELECT version_num FROM "{schema}".alembic_version')
        ) == "0019_rw1_world_memory"
        columns = set(
            connection.scalars(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name = 'tasks'"
                ),
                {"schema": schema},
            )
        )
        assert "signal_id" not in columns
        assert "identity_version" not in columns
