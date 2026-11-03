"""Database fixtures for the K1 ingestion integration tests."""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from _database_config import resolve_test_database_url
from sqlalchemy import Engine, create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from core.ingestion import IngestionProposal
from core.models import Event, Objective, Signal, Task, Team, TeamPolicy
from core.snapshot_store import SnapshotStore


@dataclass(frozen=True)
class IngestionPrerequisites:
    team_id: UUID
    policy_id: UUID
    task_id: UUID
    origin_url: str
    source_type: str


@dataclass(frozen=True)
class ObjectivePrerequisites:
    team_id: UUID
    policy_id: UUID
    create_task_id: UUID
    transition_task_id: UUID
    conflict_task_id: UUID
    other_team_id: UUID
    other_policy_id: UUID


@pytest.fixture
def database_engine() -> Iterator[Engine]:
    try:
        database_url = resolve_test_database_url(os.environ)
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc
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


@pytest.fixture
def objective_prerequisites(
    session_factory: sessionmaker[Session],
) -> Iterator[ObjectivePrerequisites]:
    (
        team_id,
        policy_id,
        create_task_id,
        transition_task_id,
        conflict_task_id,
        other_team_id,
        other_policy_id,
    ) = (uuid4() for _ in range(7))
    prerequisites = ObjectivePrerequisites(
        team_id,
        policy_id,
        create_task_id,
        transition_task_id,
        conflict_task_id,
        other_team_id,
        other_policy_id,
    )
    with session_factory.begin() as session:
        session.add_all(
            [
                Team(id=team_id, domain="objective_test", status="active"),
                Team(id=other_team_id, domain="objective_other", status="active"),
            ]
        )
        session.flush()
        session.add_all(
            [
                TeamPolicy(id=policy_id, team_id=team_id, version=1, rules={}),
                TeamPolicy(
                    id=other_policy_id, team_id=other_team_id, version=1, rules={}
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Task(
                    id=task_id,
                    team_id=team_id,
                    task_type=task_type,
                    status="running",
                    policy_version=1,
                    allowed_writes=["Objective"],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.0,
                        "deadline_seconds": 60,
                    },
                )
                for task_id, task_type in (
                    (create_task_id, "create_objective"),
                    (transition_task_id, "transition_objective"),
                    (conflict_task_id, "transition_objective"),
                )
            ]
        )
    try:
        yield prerequisites
    finally:
        with session_factory.begin() as session:
            task_ids = [create_task_id, transition_task_id, conflict_task_id]
            session.execute(delete(Event).where(Event.task_id.in_(task_ids)))
            session.execute(delete(Task).where(Task.id.in_(task_ids)))
            session.execute(delete(Objective).where(Objective.team_id == team_id))
            session.execute(
                delete(TeamPolicy).where(
                    TeamPolicy.id.in_([policy_id, other_policy_id])
                )
            )
            session.execute(delete(Team).where(Team.id.in_([team_id, other_team_id])))


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
