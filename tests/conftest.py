"""Database fixtures for the K1 ingestion integration tests."""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from core.ingestion import IngestionProposal
from core.models import Event, Signal, Task, Team, TeamPolicy
from core.snapshot_store import SnapshotStore


@dataclass(frozen=True)
class IngestionPrerequisites:
    team_id: UUID
    policy_id: UUID
    task_id: UUID
    origin_url: str
    source_type: str


@pytest.fixture
def database_engine() -> Iterator[Engine]:
    database_url = os.environ.get(
        "TEST_DATABASE_URL",
        os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://watch:watch@localhost:5432/watch",
        ),
    )
    engine = create_engine(database_url)
    with engine.connect():
        pass
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(database_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(database_engine, expire_on_commit=False)


@pytest.fixture
def snapshot_store(tmp_path: Path) -> SnapshotStore:
    return SnapshotStore(tmp_path)


@pytest.fixture
def prerequisites(
    session_factory: sessionmaker[Session],
) -> Iterator[IngestionPrerequisites]:
    team_id = uuid4()
    policy_id = uuid4()
    task_id = uuid4()
    origin_url = f"https://example.test/articles/{uuid4()}"
    source_type = "test_feed"
    prerequisite = IngestionPrerequisites(
        team_id=team_id,
        policy_id=policy_id,
        task_id=task_id,
        origin_url=origin_url,
        source_type=source_type,
    )

    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="test_domain", status="active"))
        session.flush()
        session.add(
            TeamPolicy(
                id=policy_id,
                team_id=team_id,
                version=1,
                rules={
                    "sources": [
                        {
                            "origin_url": origin_url,
                            "source_type": source_type,
                        }
                    ]
                },
            )
        )
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
        yield prerequisite
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Signal).where(Signal.origin_url == origin_url))
            session.execute(delete(Task).where(Task.id == task_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


def make_proposal(
    prerequisites: IngestionPrerequisites,
    content: bytes = b"Test source content",
    *,
    task_id: UUID | None = None,
    origin_url: str | None = None,
    source_type: str | None = None,
    claimed_hash: str | None = None,
) -> IngestionProposal:
    import hashlib

    digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
    return IngestionProposal(
        task_id=task_id if task_id is not None else prerequisites.task_id,
        origin_url=origin_url if origin_url is not None else prerequisites.origin_url,
        source_type=(
            source_type if source_type is not None else prerequisites.source_type
        ),
        fetched_at=datetime.now(timezone.utc),
        content=content,
        claimed_content_hash=claimed_hash if claimed_hash is not None else digest,
    )


@pytest.fixture
def unrelated_task(
    session_factory: sessionmaker[Session],
    prerequisites: IngestionPrerequisites,
) -> Iterator[UUID]:
    task_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Task(
                id=task_id,
                team_id=prerequisites.team_id,
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
        yield task_id
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))
