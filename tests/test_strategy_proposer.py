"""Deterministic integration tests for the R6-E StrategyProposer boundary."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from core.context_assembly import TaskContextAssembler, TaskContextError
from core.generation import (
    GenerationProviderError,
    GenerationResult,
    GenerationUsage,
)
from core.models import Event, Objective, Plan, Task, Team, TeamPolicy
from core.snapshot_store import SnapshotStore
from core.strategy import StrategyService
from core.strategy_proposer import (
    MAX_STRATEGY_CONTEXT_CHARACTERS,
    StrategyProposer,
    StrategyProposerError,
)


class _EmptyRetriever:
    def retrieve(self, team_id: UUID, query: str) -> tuple[Any, ...]:
        return ()


@dataclass(frozen=True)
class _ProposerFixture:
    task_id: UUID
    objective_id: UUID
    source_url: str
    source_type: str
    assembler: TaskContextAssembler


@pytest.fixture
def proposer_fixture(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
) -> Iterator[_ProposerFixture]:
    team_id, policy_id, objective_id, task_id = (uuid4() for _ in range(4))
    source_url = "https://example.test/proposer-source"
    source_type = "test_feed"
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="science", status="active"))
        session.flush()
        session.add(
            TeamPolicy(
                id=policy_id,
                team_id=team_id,
                version=1,
                rules={
                    "sources": [
                        {"origin_url": source_url, "source_type": source_type}
                    ]
                },
            )
        )
        session.add(
            Objective(
                id=objective_id,
                team_id=team_id,
                statement="Gather scientific evidence about alpha.",
                status="active",
            )
        )
        session.flush()
        session.add(
            Task(
                id=task_id,
                team_id=team_id,
                objective_id=objective_id,
                task_type="propose_strategy",
                status="running",
                policy_version=1,
                allowed_writes=[],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.05,
                    "deadline_seconds": 60,
                },
            )
        )
    fixture = _ProposerFixture(
        task_id=task_id,
        objective_id=objective_id,
        source_url=source_url,
        source_type=source_type,
        assembler=TaskContextAssembler(
            session_factory, snapshot_store, _EmptyRetriever()
        ),
    )
    try:
        yield fixture
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Plan).where(Plan.created_by_task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))
            session.execute(delete(Objective).where(Objective.id == objective_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


class _FakeGenerationProvider:
    def __init__(
        self,
        content: Any,
        *,
        on_call: Callable[[], None] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.content = content
        self.on_call = on_call
        self.error = error
        self.calls: list[tuple[str, str, float]] = []

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> GenerationResult:
        self.calls.append((system_prompt, user_prompt, temperature))
        if self.on_call is not None:
            self.on_call()
        if self.error is not None:
            raise self.error
        return GenerationResult(
            content=self.content,
            model="deterministic-fake-model",
            usage=GenerationUsage(
                input_tokens=24,
                output_tokens=32,
                estimated_cost_usd=Decimal("0.00001"),
            ),
            elapsed_seconds=0.01,
            request_id="fake-request",
        )


def _valid_proposal(fixture: _ProposerFixture) -> dict[str, Any]:
    return {
        "objective_id": str(fixture.objective_id),
        "approach": "gather_configured_source",
        "reason": "Gather configured evidence relevant to the Objective.",
        "visions": [
            {
                "id": str(uuid4()),
                "name": "Evidence gathering",
                "scope": "Collect evidence from the configured source.",
                "boundary": "Do not fetch or mutate anything during proposal.",
                "workstreams": [
                    {
                        "id": str(uuid4()),
                        "name": "Configured source",
                        "purpose": "Prepare one authorized ingestion action.",
                        "actions": [
                            {
                                "id": str(uuid4()),
                                "purpose": "Ingest the configured source.",
                                "prerequisites": [],
                                "task_type": "ingest_source",
                                "origin_url": fixture.source_url,
                                "source_type": fixture.source_type,
                                "tools": [],
                            }
                        ],
                    }
                ],
            }
        ],
        "constraints": {"max_tasks": 1, "max_cost_usd": 0.0},
        "stop_conditions": ["configured_source_ingested"],
    }


def test_valid_model_proposal_is_submitted_only_through_strategy_service(
    session_factory: sessionmaker[Session],
    proposer_fixture: _ProposerFixture,
) -> None:
    fixture = proposer_fixture
    provider = _FakeGenerationProvider(_valid_proposal(fixture))
    proposer = StrategyProposer(
        session_factory, fixture.assembler, provider, StrategyService(session_factory)
    )

    result = proposer.propose(fixture.task_id)

    assert result.disposition.accepted
    assert result.disposition.reason is None
    assert result.model == "deterministic-fake-model"
    assert result.usage is not None
    assert result.usage.estimated_cost_usd == Decimal("0.00001")
    assert len(provider.calls) == 1
    system_prompt, user_prompt, temperature = provider.calls[0]
    assert "untrusted data" in system_prompt
    assert len(user_prompt) <= MAX_STRATEGY_CONTEXT_CHARACTERS
    assert '"schema_version":"r6e-task-context-v1"' in user_prompt
    assert temperature == 0.1

    with session_factory() as session:
        event = session.get(Event, result.disposition.event_id)
        assert event is not None
        assert event.type == "strategy_proposal_accepted"
        assert event.task_id == fixture.task_id
        assert event.payload["context_provenance"] == {
            "event_id": str(result.context.event_id),
            "snapshot_ref": result.context.snapshot_ref,
            "content_hash": result.context.content_hash,
        }
        assert (
            event.payload["assessment"]["basis"]["sha256"]
            == result.context.assessment.basis.sha256
        )
        assert list(
            session.scalars(select(Plan).where(Plan.created_by_task_id == fixture.task_id))
        ) == []


def test_incomplete_model_output_is_durably_rejected_without_a_plan(
    session_factory: sessionmaker[Session],
    proposer_fixture: _ProposerFixture,
) -> None:
    fixture = proposer_fixture
    provider = _FakeGenerationProvider(
        {"objective_id": str(fixture.objective_id), "approach": "incomplete"}
    )
    result = StrategyProposer(session_factory, fixture.assembler, provider).propose(
        fixture.task_id
    )

    assert not result.disposition.accepted
    assert result.disposition.reason == "invalid_structure"
    with session_factory() as session:
        event = session.get(Event, result.disposition.event_id)
        assert event is not None and event.type == "strategy_proposal_rejected"
        assert event.payload["context_provenance"]["event_id"] == str(
            result.context.event_id
        )
        assert list(
            session.scalars(select(Plan).where(Plan.created_by_task_id == fixture.task_id))
        ) == []


def test_unsupported_action_is_rejected_by_application_validation(
    session_factory: sessionmaker[Session],
    proposer_fixture: _ProposerFixture,
) -> None:
    fixture = proposer_fixture
    raw = _valid_proposal(fixture)
    raw["visions"][0]["workstreams"][0]["actions"][0]["task_type"] = "arbitrary_tool"
    provider = _FakeGenerationProvider(raw)

    result = StrategyProposer(session_factory, fixture.assembler, provider).propose(
        fixture.task_id
    )

    assert not result.disposition.accepted
    assert result.disposition.reason == "unsupported_task_type"


def test_provider_failure_does_not_create_a_strategy_disposition_or_plan(
    session_factory: sessionmaker[Session],
    proposer_fixture: _ProposerFixture,
) -> None:
    fixture = proposer_fixture
    provider = _FakeGenerationProvider(
        {},
        error=GenerationProviderError("cloudflare_http_503", retryable=True),
    )
    proposer = StrategyProposer(session_factory, fixture.assembler, provider)

    with pytest.raises(GenerationProviderError, match="cloudflare_http_503"):
        proposer.propose(fixture.task_id)

    with session_factory() as session:
        dispositions = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == fixture.task_id,
                    Event.type.in_(
                        (
                            "strategy_proposal_accepted",
                            "strategy_proposal_rejected",
                        )
                    ),
                )
            )
        )
        assert dispositions == []
        assert list(
            session.scalars(select(Plan).where(Plan.created_by_task_id == fixture.task_id))
        ) == []


def test_exact_retry_reuses_prior_disposition_without_another_provider_call(
    session_factory: sessionmaker[Session],
    proposer_fixture: _ProposerFixture,
) -> None:
    fixture = proposer_fixture
    provider = _FakeGenerationProvider(_valid_proposal(fixture))
    proposer = StrategyProposer(session_factory, fixture.assembler, provider)

    first = proposer.propose(fixture.task_id)
    replay = proposer.propose(fixture.task_id)

    assert first.disposition.accepted
    assert replay.disposition.replayed
    assert replay.disposition.event_id == first.disposition.event_id
    assert replay.usage is None
    assert len(provider.calls) == 1


def test_stale_assessment_is_rejected_after_provider_returns(
    session_factory: sessionmaker[Session],
    proposer_fixture: _ProposerFixture,
) -> None:
    fixture = proposer_fixture

    def change_objective() -> None:
        with session_factory.begin() as session:
            objective = session.get(Objective, fixture.objective_id)
            assert objective is not None
            objective.statement = "The objective changed while the provider was running."

    provider = _FakeGenerationProvider(
        _valid_proposal(fixture), on_call=change_objective
    )
    result = StrategyProposer(session_factory, fixture.assembler, provider).propose(
        fixture.task_id
    )

    assert not result.disposition.accepted
    assert result.disposition.reason == "stale_assessment"
    with session_factory() as session:
        assert list(
            session.scalars(select(Plan).where(Plan.created_by_task_id == fixture.task_id))
        ) == []


def test_context_manifest_tampering_is_rejected_by_strategy_service(
    session_factory: sessionmaker[Session],
    proposer_fixture: _ProposerFixture,
) -> None:
    fixture = proposer_fixture
    context = fixture.assembler.assemble(fixture.task_id)
    with session_factory.begin() as session:
        event = session.get(Event, context.event_id)
        assert event is not None
        event.payload = {**event.payload, "content_hash": "sha256:" + ("0" * 64)}

    result = StrategyService(session_factory).submit_from_context(
        fixture.task_id, _valid_proposal(fixture), context
    )
    assert not result.accepted
    assert result.reason == "context_manifest_event_mismatch"
    with session_factory() as session:
        event = session.get(Event, result.event_id)
        assert event is not None and event.type == "strategy_proposal_rejected"


def test_changed_context_cannot_be_used_to_replay_an_existing_strategy_disposition(
    session_factory: sessionmaker[Session],
    proposer_fixture: _ProposerFixture,
) -> None:
    fixture = proposer_fixture
    provider = _FakeGenerationProvider(_valid_proposal(fixture))
    proposer = StrategyProposer(session_factory, fixture.assembler, provider)
    first = proposer.propose(fixture.task_id)

    with session_factory.begin() as session:
        objective = session.get(Objective, fixture.objective_id)
        assert objective is not None
        objective.statement = "A changed objective must not inherit the old proposal."

    with pytest.raises(TaskContextError, match="context_replay_conflict"):
        proposer.propose(fixture.task_id)
    assert first.disposition.accepted
    assert len(provider.calls) == 1

def test_oversized_context_is_rejected_before_provider_invocation(
    session_factory: sessionmaker[Session],
    proposer_fixture: _ProposerFixture,
) -> None:
    fixture = proposer_fixture
    with session_factory.begin() as session:
        objective = session.get(Objective, fixture.objective_id)
        assert objective is not None
        objective.statement = "x" * (MAX_STRATEGY_CONTEXT_CHARACTERS + 1)
    provider = _FakeGenerationProvider(_valid_proposal(fixture))

    with pytest.raises(StrategyProposerError, match="strategy_context_too_large"):
        StrategyProposer(session_factory, fixture.assembler, provider).propose(
            fixture.task_id
        )
    assert provider.calls == []

