"""Disposable PostgreSQL concurrency spike for the proposed RW-5 lock protocol.

These tests use isolated per-test schemas and real concurrent sessions. They prove
PostgreSQL lock behavior, not production-writer coverage or the future shared helper.
"""

from __future__ import annotations

from queue import Queue
from threading import Event, Thread
from time import monotonic, sleep
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError


def _sqlstate(error: DBAPIError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


def _wait_until_blocked(engine: Engine, pid: int) -> None:
    deadline = monotonic() + 8
    while monotonic() < deadline:
        with engine.connect() as monitor:
            blockers = monitor.scalar(
                text("SELECT cardinality(pg_blocking_pids(:pid))"),
                {"pid": pid},
            )
        if blockers:
            return
        sleep(0.01)
    raise AssertionError(f"backend {pid} did not enter a lock wait")


@pytest.fixture
def spike_schema(database_engine: Engine):
    schema = f"rw5_spike_{uuid4().hex}"
    q = f'"{schema}"'
    with database_engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {q}"))
        connection.execute(
            text(
                f"CREATE TABLE {q}.teams "
                "(id integer PRIMARY KEY)"
            )
        )
        connection.execute(
            text(
                f"CREATE TABLE {q}.hypotheses ("
                "id integer PRIMARY KEY, "
                f"team_id integer NOT NULL REFERENCES {q}.teams(id), "
                "confidence text NOT NULL)"
            )
        )
        connection.execute(
            text(
                f"CREATE TABLE {q}.evidence_links ("
                "id integer PRIMARY KEY, "
                f"team_id integer NOT NULL REFERENCES {q}.teams(id), "
                f"hypothesis_id integer NOT NULL REFERENCES {q}.hypotheses(id))"
            )
        )
        connection.execute(
            text(
                f"CREATE TABLE {q}.fk_children ("
                "id integer PRIMARY KEY, "
                f"hypothesis_id integer NOT NULL REFERENCES {q}.hypotheses(id))"
            )
        )
        connection.execute(text(f"INSERT INTO {q}.teams VALUES (1)"))
        connection.execute(
            text(
                f"INSERT INTO {q}.hypotheses VALUES "
                "(1, 1, 'low'), (2, 1, 'low')"
            )
        )
    try:
        yield q
    finally:
        with database_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {q} CASCADE"))


@pytest.mark.parametrize("parent", ["teams", "hypotheses"])
@pytest.mark.parametrize(
    ("lock_mode", "should_block"),
    [("FOR NO KEY UPDATE", False), ("FOR UPDATE", True)],
)
def test_fk_child_insert_lock_compatibility(
    database_engine: Engine,
    spike_schema: str,
    parent: str,
    lock_mode: str,
    should_block: bool,
) -> None:
    """NO KEY UPDATE permits FK KEY SHARE; UPDATE conflicts with it."""
    with database_engine.connect() as owner, database_engine.connect() as writer:
        owner_tx = owner.begin()
        writer_tx = writer.begin()
        try:
            owner.execute(
                text(
                    f"SELECT id FROM {spike_schema}.{parent} "
                    f"WHERE id = 1 {lock_mode}"
                )
            )
            writer.execute(text("SET LOCAL lock_timeout = '500ms'"))
            statement = text(
                f"INSERT INTO {spike_schema}.evidence_links "
                "(id, team_id, hypothesis_id) VALUES (10, 1, 1)"
            )
            if should_block:
                with pytest.raises(DBAPIError) as caught:
                    writer.execute(statement)
                assert _sqlstate(caught.value) == "55P03"
            else:
                writer.execute(statement)
        finally:
            writer_tx.rollback()
            owner_tx.rollback()


def test_fk_lock_inversion_reproduces_deadlock(
    database_engine: Engine,
    spike_schema: str,
) -> None:
    """Child-first FK locking plus Team-first FOR UPDATE forms a real cycle."""
    child_ready = Event()
    child_result: Queue[tuple[str, str | None]] = Queue()
    child_pid_result: Queue[int] = Queue()

    with database_engine.connect() as owner:
        owner_tx = owner.begin()
        owner.execute(
            text(f"SELECT id FROM {spike_schema}.teams WHERE id = 1 FOR UPDATE")
        )

        def child_first_writer() -> None:
            with database_engine.connect() as child:
                child_tx = child.begin()
                try:
                    child.execute(text("SET LOCAL lock_timeout = '8s'"))
                    pid = child.scalar(text("SELECT pg_backend_pid()"))
                    child.execute(
                        text(
                            f"INSERT INTO {spike_schema}.fk_children "
                            "(id, hypothesis_id) VALUES (20, 1)"
                        )
                    )
                    child_pid_result.put(pid)
                    child_ready.set()
                    child.execute(
                        text(
                            f"SELECT id FROM {spike_schema}.teams "
                            "WHERE id = 1 FOR UPDATE"
                        )
                    )
                    child_tx.commit()
                    child_result.put(("committed", None))
                except DBAPIError as error:
                    child_tx.rollback()
                    child_result.put(("error", _sqlstate(error)))

        worker = Thread(target=child_first_writer)
        worker.start()
        assert child_ready.wait(5), "child insert did not acquire its FK lock"
        child_pid = child_pid_result.get(timeout=1)
        _wait_until_blocked(database_engine, child_pid)

        owner_outcome: tuple[str, str | None]
        try:
            owner.execute(
                text(
                    f"SELECT id FROM {spike_schema}.hypotheses "
                    "WHERE id = 1 FOR UPDATE"
                )
            )
            owner_tx.commit()
            owner_outcome = ("committed", None)
        except DBAPIError as error:
            owner_tx.rollback()
            owner_outcome = ("error", _sqlstate(error))

        worker.join(timeout=8)
        assert not worker.is_alive(), "deadlock victim did not exit"
        child_outcome = child_result.get(timeout=1)

    outcomes = [owner_outcome, child_outcome]
    assert [state for state, code in outcomes if code == "40P01"]
    assert sum(code == "40P01" for _, code in outcomes) == 1


def test_read_committed_reads_after_team_lock_wait(
    database_engine: Engine,
    spike_schema: str,
) -> None:
    """A statement after the Team-lock wait sees the preceding commit."""
    waiting = Event()
    result: Queue[str] = Queue()
    waiter_pid_result: Queue[int] = Queue()
    with database_engine.connect() as owner:
        owner_tx = owner.begin()
        owner.execute(
            text(
                f"SELECT id FROM {spike_schema}.teams "
                "WHERE id = 1 FOR NO KEY UPDATE"
            )
        )
        owner.execute(
            text(
                f"UPDATE {spike_schema}.hypotheses "
                "SET confidence = 'moderate' WHERE id = 1"
            )
        )

        def waiting_writer() -> None:
            with database_engine.connect() as waiter:
                waiter_tx = waiter.begin()
                try:
                    waiter.execute(
                        text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                    )
                    waiter.execute(text("SET LOCAL lock_timeout = '8s'"))
                    pid = waiter.scalar(text("SELECT pg_backend_pid()"))
                    waiter_pid_result.put(pid)
                    waiting.set()
                    waiter.execute(
                        text(
                            f"SELECT id FROM {spike_schema}.teams "
                            "WHERE id = 1 FOR NO KEY UPDATE"
                        )
                    )
                    value = waiter.scalar(
                        text(
                            f"SELECT confidence FROM {spike_schema}.hypotheses "
                            "WHERE id = 1"
                        )
                    )
                    waiter_tx.commit()
                    result.put(value)
                except Exception as error:
                    waiter_tx.rollback()
                    result.put(f"error:{error!r}")

        worker = Thread(target=waiting_writer)
        worker.start()
        assert waiting.wait(5)
        waiter_pid = waiter_pid_result.get(timeout=1)
        _wait_until_blocked(database_engine, waiter_pid)
        owner_tx.commit()
        worker.join(timeout=8)
        assert not worker.is_alive(), "waiting writer did not finish"
        assert result.get(timeout=1) == "moderate"


def test_opposite_input_orders_use_one_sorted_lock_order(
    database_engine: Engine,
    spike_schema: str,
) -> None:
    """Opposite candidate order converges when IDs are locked one by one sorted."""
    waiting = Event()
    result: Queue[str] = Queue()
    second_pid_result: Queue[int] = Queue()

    def lock_hypotheses(connection, ids: list[int]) -> None:
        for hypothesis_id in sorted(set(ids)):
            connection.execute(
                text(
                    f"SELECT id FROM {spike_schema}.hypotheses "
                    "WHERE id = :id FOR NO KEY UPDATE"
                ),
                {"id": hypothesis_id},
            )

    with database_engine.connect() as first:
        first_tx = first.begin()
        first.execute(
            text(
                f"SELECT id FROM {spike_schema}.hypotheses "
                "WHERE id = 1 FOR NO KEY UPDATE"
            )
        )

        def reverse_order_writer() -> None:
            with database_engine.connect() as second:
                second_tx = second.begin()
                try:
                    second.execute(text("SET LOCAL lock_timeout = '8s'"))
                    pid = second.scalar(text("SELECT pg_backend_pid()"))
                    second_pid_result.put(pid)
                    waiting.set()
                    lock_hypotheses(second, [2, 1])
                    second_tx.commit()
                    result.put("committed")
                except Exception as error:
                    second_tx.rollback()
                    result.put(f"error:{error!r}")

        worker = Thread(target=reverse_order_writer)
        worker.start()
        assert waiting.wait(5)
        second_pid = second_pid_result.get(timeout=1)
        _wait_until_blocked(database_engine, second_pid)
        first.execute(
            text(
                f"SELECT id FROM {spike_schema}.hypotheses "
                "WHERE id = 2 FOR NO KEY UPDATE"
            )
        )
        first_tx.commit()
        worker.join(timeout=8)
        assert not worker.is_alive(), "sorted writer did not finish"
        assert result.get(timeout=1) == "committed"
