"""Database-backed tests for Task-attributed generation cost accounting."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from threading import Barrier
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from core.generation import (
    CLOUDFLARE_PRICING_REVISION,
    DEFAULT_MODEL,
    INPUT_USD_PER_MILLION_TOKENS,
    OUTPUT_USD_PER_MILLION_TOKENS,
    GenerationCostQuote,
    GenerationUsage,
)
from core.generation_cost import (
    TaskGenerationCostError,
    TaskGenerationCostService,
)
from core.models import (
    Event,
    Objective,
    Task,
    TaskGenerationCharge,
    Team,
    TeamPolicy,
)


@dataclass(frozen=True)
class _CostTask:
    task_id: UUID
    team_id: UUID
    objective_id: UUID
    policy_id: UUID


@pytest.fixture
def cost_task(
    session_factory: sessionmaker[Session],
) -> Iterator[_CostTask]:
    team_id, policy_id, objective_id, task_id = (uuid4() for _ in range(4))
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="science", status="active"))
        session.flush()
        session.add(
            TeamPolicy(
                id=policy_id,
                team_id=team_id,
                version=1,
                rules={"sources": []},
            )
        )
        session.add(
            Objective(
                id=objective_id,
                team_id=team_id,
                statement="Account for one generation call.",
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
                attempt_count=1,
                policy_version=1,
                allowed_writes=[],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.00025,
                    "deadline_seconds": 60,
                },
            )
        )
    fixture = _CostTask(task_id, team_id, objective_id, policy_id)
    try:
        yield fixture
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(
                delete(TaskGenerationCharge).where(
                    TaskGenerationCharge.task_id == task_id
                )
            )
            session.execute(delete(Task).where(Task.id == task_id))
            session.execute(delete(Objective).where(Objective.id == objective_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


def _quote(
    *,
    maximum_input_tokens: int = 1024,
    maximum_output_tokens: int = 128,
) -> GenerationCostQuote:
    return GenerationCostQuote(
        provider="cloudflare_workers_ai",
        model=DEFAULT_MODEL,
        maximum_input_tokens=maximum_input_tokens,
        maximum_output_tokens=maximum_output_tokens,
        input_usd_per_million_tokens=INPUT_USD_PER_MILLION_TOKENS,
        output_usd_per_million_tokens=OUTPUT_USD_PER_MILLION_TOKENS,
        pricing_revision=CLOUDFLARE_PRICING_REVISION,
    )


def test_reservation_is_persisted_before_reconciliation_and_settled_from_usage(
    session_factory: sessionmaker[Session],
    cost_task: _CostTask,
) -> None:
    service = TaskGenerationCostService(session_factory)
    quote = _quote()
    reservation = service.reserve(cost_task.task_id, quote)

    with session_factory() as session:
        charge = session.get(TaskGenerationCharge, reservation.charge_id)
        assert charge is not None
        assert charge.status == "reserved"
        assert charge.reserved_cost_usd == quote.maximum_cost_usd
        assert charge.accounted_cost_usd is None
        reserve_event = session.scalar(
            select(Event).where(
                Event.task_id == cost_task.task_id,
                Event.type == "generation_cost_reserved",
            )
        )
        assert reserve_event is not None
        assert reserve_event.payload["charge_id"] == str(charge.id)

    result = service.reconcile(
        reservation,
        model=DEFAULT_MODEL,
        usage=GenerationUsage(
            input_tokens=10,
            output_tokens=20,
            estimated_cost_usd=Decimal("999"),
        ),
        request_id="test-request-1",
    )

    expected_usage_cost = (
        Decimal(10) * Decimal("0.152")
        + Decimal(20) * Decimal("0.287")
    ) / Decimal(1_000_000)
    assert result.status == "reconciled"
    assert result.usage_cost_usd == expected_usage_cost
    assert result.accounted_cost_usd == expected_usage_cost

    with session_factory() as session:
        charge = session.get(TaskGenerationCharge, reservation.charge_id)
        assert charge is not None
        assert charge.status == "reconciled"
        assert charge.input_tokens == 10
        assert charge.output_tokens == 20
        assert charge.request_id == "test-request-1"
        assert charge.accounted_cost_usd == expected_usage_cost
        assert session.scalar(
            select(Event).where(
                Event.task_id == cost_task.task_id,
                Event.type == "generation_cost_reconciled",
            )
        ) is not None


def test_unknown_usage_keeps_full_reservation_and_blocks_same_attempt_replay(
    session_factory: sessionmaker[Session],
    cost_task: _CostTask,
) -> None:
    service = TaskGenerationCostService(session_factory)
    quote = _quote()
    reservation = service.reserve(cost_task.task_id, quote)

    service.mark_unknown(reservation, "provider_timeout")

    with pytest.raises(
        TaskGenerationCostError,
        match="generation_attempt_already_reserved_or_recorded",
    ):
        service.reserve(cost_task.task_id, quote)

    with session_factory.begin() as session:
        task = session.get(Task, cost_task.task_id)
        assert task is not None
        task.attempt_count = 2

    # The prior unknown attempt still consumes its full maximum. A second
    # maximum reservation would exceed this Task's total monetary ceiling.
    with pytest.raises(
        TaskGenerationCostError, match="task_generation_budget_exhausted"
    ):
        service.reserve(cost_task.task_id, quote)

    with session_factory() as session:
        charge = session.get(TaskGenerationCharge, reservation.charge_id)
        assert charge is not None
        assert charge.status == "unknown"
        assert charge.accounted_cost_usd is None
        assert charge.failure_reason == "provider_timeout"
        assert charge.reserved_cost_usd == quote.maximum_cost_usd
        unknown_event = session.scalar(
            select(Event).where(
                Event.task_id == cost_task.task_id,
                Event.type == "generation_cost_unknown",
            )
        )
        assert unknown_event is not None
        assert unknown_event.payload["conservative_budget_charge_usd"] == str(
            quote.maximum_cost_usd
        )
        assert "accounted_cost_usd" not in unknown_event.payload


def test_usage_above_reserved_bounds_is_recorded_as_an_overrun(
    session_factory: sessionmaker[Session],
    cost_task: _CostTask,
) -> None:
    with session_factory.begin() as session:
        task = session.get(Task, cost_task.task_id)
        assert task is not None
        task.budget = {
            "max_tool_calls": 0,
            "max_cost_usd": 0.001,
            "deadline_seconds": 60,
        }

    service = TaskGenerationCostService(session_factory)
    quote = _quote(maximum_input_tokens=100, maximum_output_tokens=10)
    reservation = service.reserve(cost_task.task_id, quote)
    usage = GenerationUsage(
        input_tokens=2_000,
        output_tokens=100,
        estimated_cost_usd=Decimal("0"),
    )

    result = service.reconcile(
        reservation,
        model=DEFAULT_MODEL,
        usage=usage,
        request_id="test-request-overrun",
    )

    expected_cost = (
        Decimal(2_000) * Decimal("0.152")
        + Decimal(100) * Decimal("0.287")
    ) / Decimal(1_000_000)
    assert result.status == "overrun"
    assert result.usage_cost_usd == expected_cost
    assert result.accounted_cost_usd == expected_cost

    with session_factory() as session:
        charge = session.get(TaskGenerationCharge, reservation.charge_id)
        assert charge is not None
        assert charge.status == "overrun"
        assert charge.failure_reason == "provider_usage_exceeded_reserved_bound"
        assert charge.accounted_cost_usd == expected_cost
        assert session.scalar(
            select(Event).where(
                Event.task_id == cost_task.task_id,
                Event.type == "generation_cost_overrun",
            )
        ) is not None


def test_budget_exhaustion_writes_no_charge_or_reservation_event(
    session_factory: sessionmaker[Session],
    cost_task: _CostTask,
) -> None:
    service = TaskGenerationCostService(session_factory)
    quote = _quote()

    with session_factory.begin() as session:
        task = session.get(Task, cost_task.task_id)
        assert task is not None
        task.budget = {
            "max_tool_calls": 0,
            "max_cost_usd": 0.000001,
            "deadline_seconds": 60,
        }

    with pytest.raises(
        TaskGenerationCostError, match="task_generation_budget_exhausted"
    ):
        service.reserve(cost_task.task_id, quote)

    with session_factory() as session:
        assert list(
            session.scalars(
                select(TaskGenerationCharge).where(
                    TaskGenerationCharge.task_id == cost_task.task_id
                )
            )
        ) == []
        assert list(
            session.scalars(
                select(Event).where(
                    Event.task_id == cost_task.task_id,
                    Event.type == "generation_cost_reserved",
                )
            )
        ) == []


def test_generation_charge_is_reconciled_idempotently(
    session_factory: sessionmaker[Session],
    cost_task: _CostTask,
) -> None:
    service = TaskGenerationCostService(session_factory)
    reservation = service.reserve(cost_task.task_id, _quote())
    usage = GenerationUsage(
        input_tokens=24,
        output_tokens=32,
        estimated_cost_usd=Decimal("0"),
    )

    first = service.reconcile(
        reservation,
        model=DEFAULT_MODEL,
        usage=usage,
        request_id="stable-request-id",
    )
    replay = service.reconcile(
        reservation,
        model=DEFAULT_MODEL,
        usage=usage,
        request_id="stable-request-id",
    )

    assert first.status == "reconciled"
    assert not first.replayed
    assert replay.replayed
    assert replay.charge_id == first.charge_id
    with session_factory() as session:
        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == cost_task.task_id,
                    Event.type == "generation_cost_reconciled",
                )
            )
        )
        assert len(events) == 1


def test_untrusted_quote_cannot_lower_the_selected_model_price_card(
    session_factory: sessionmaker[Session],
    cost_task: _CostTask,
) -> None:
    service = TaskGenerationCostService(session_factory)
    quote = GenerationCostQuote(
        provider="cloudflare_workers_ai",
        model=DEFAULT_MODEL,
        maximum_input_tokens=100,
        maximum_output_tokens=64,
        input_usd_per_million_tokens=Decimal("0.000001"),
        output_usd_per_million_tokens=Decimal("0.000001"),
        pricing_revision=CLOUDFLARE_PRICING_REVISION,
    )

    with pytest.raises(
        TaskGenerationCostError, match="generation_cost_quote_invalid"
    ):
        service.reserve(cost_task.task_id, quote)

    with session_factory() as session:
        assert list(
            session.scalars(
                select(TaskGenerationCharge).where(
                    TaskGenerationCharge.task_id == cost_task.task_id
                )
            )
        ) == []


def test_concurrent_same_attempt_reservations_commit_exactly_once(
    session_factory: sessionmaker[Session],
    cost_task: _CostTask,
) -> None:
    service = TaskGenerationCostService(session_factory)
    quote = _quote()
    with session_factory.begin() as session:
        task = session.get(Task, cost_task.task_id)
        assert task is not None
        task.budget = {
            "max_tool_calls": 0,
            "max_cost_usd": 0.001,
            "deadline_seconds": 60,
        }

    barrier = Barrier(2)

    def reserve_once() -> object:
        barrier.wait(timeout=10)
        try:
            return service.reserve(cost_task.task_id, quote)
        except TaskGenerationCostError as error:
            return error.reason

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: reserve_once(), range(2)))

    successful = [result for result in results if not isinstance(result, str)]
    rejected = [result for result in results if isinstance(result, str)]
    assert len(successful) == 1
    assert rejected == ["generation_attempt_already_reserved_or_recorded"]

    with session_factory() as session:
        charges = list(
            session.scalars(
                select(TaskGenerationCharge).where(
                    TaskGenerationCharge.task_id == cost_task.task_id
                )
            )
        )
        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == cost_task.task_id,
                    Event.type == "generation_cost_reserved",
                )
            )
        )
        assert len(charges) == 1
        assert len(events) == 1


def test_reconciliation_event_failure_keeps_reservation_and_can_be_marked_unknown(
    session_factory: sessionmaker[Session],
    cost_task: _CostTask,
) -> None:
    service = TaskGenerationCostService(session_factory)
    quote = _quote()
    reservation = service.reserve(cost_task.task_id, quote)
    function_name = f"fail_generation_reconcile_{uuid4().hex}"
    trigger_name = f"fail_generation_reconcile_{uuid4().hex}"

    with session_factory.begin() as session:
        session.connection().exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                IF NEW.type = 'generation_cost_reconciled' THEN
                    RAISE EXCEPTION 'injected reconciliation Event failure';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        session.connection().exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON events
            FOR EACH ROW EXECUTE FUNCTION {function_name}()
            """
        )

    try:
        with pytest.raises(DBAPIError):
            service.reconcile(
                reservation,
                model=DEFAULT_MODEL,
                usage=GenerationUsage(
                    input_tokens=10,
                    output_tokens=20,
                    estimated_cost_usd=Decimal("0"),
                ),
                request_id="reconcile-failure-request",
            )
    finally:
        with session_factory.begin() as session:
            session.connection().exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON events"
            )
            session.connection().exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )

    with session_factory() as session:
        charge = session.get(TaskGenerationCharge, reservation.charge_id)
        assert charge is not None
        assert charge.status == "reserved"
        assert charge.accounted_cost_usd is None
        assert charge.input_tokens is None
        assert charge.output_tokens is None

    # The proposer follows the same fail-closed recovery after an ambiguous
    # reconciliation commit: keep the full reservation charged as unknown.
    service.mark_unknown(reservation, "generation_reconciliation_failed")

    with session_factory() as session:
        charge = session.get(TaskGenerationCharge, reservation.charge_id)
        assert charge is not None
        assert charge.status == "unknown"
        assert charge.accounted_cost_usd is None
        unknown_event = session.scalar(
            select(Event).where(
                Event.task_id == cost_task.task_id,
                Event.type == "generation_cost_unknown",
            )
        )
        assert unknown_event is not None
        assert unknown_event.payload["conservative_budget_charge_usd"] == str(
            quote.maximum_cost_usd
        )
