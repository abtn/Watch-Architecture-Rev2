"""Task-attributed, fail-closed reservation and reconciliation for model spend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.generation import (
    CLOUDFLARE_PRICING_REVISION,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MODEL,
    INPUT_USD_PER_MILLION_TOKENS,
    MAX_MODEL_CONTEXT_TOKENS,
    OUTPUT_USD_PER_MILLION_TOKENS,
    GenerationCostQuote,
    GenerationUsage,
)
from core.models import Event, Task, TaskGenerationCharge
from core.objectives import ObjectiveService

_STRATEGY_OPERATION = "strategy_proposal"
_EXPERIENCE_OPERATION = "experience_distillation"
_EXPERIENCE_FAKE_PROVIDER = "watch_test_fake"
_EXPERIENCE_FAKE_MODEL = "watch-r6f-distillation-fake"
_EXPERIENCE_FAKE_PRICING_REVISION = "watch-r6f-fake-price-v1"
_EXPERIENCE_FAKE_INPUT_RATE = Decimal("1")
_EXPERIENCE_FAKE_OUTPUT_RATE = Decimal("1")
_EXPERIENCE_FAKE_MAX_OUTPUT_TOKENS = 512
_COST_DIVISOR = Decimal(1_000_000)


class TaskGenerationCostError(ValueError):
    """A fail-closed Task generation accounting decision."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class GenerationCostReservation:
    charge_id: UUID
    task_id: UUID
    attempt_count: int
    reserved_cost_usd: Decimal
    provider: str
    model: str
    operation: str = _STRATEGY_OPERATION


@dataclass(frozen=True)
class GenerationCostReconciliation:
    charge_id: UUID
    status: str
    usage_cost_usd: Decimal
    accounted_cost_usd: Decimal
    replayed: bool = False


class TaskGenerationCostService:
    """Reserve and settle one generation call per Task attempt.

    The Task-row lock serializes reservations and reconciliations. Unknown calls
    consume their full reservation; a later Task attempt must fit its new
    reservation on top of every prior reconciled or unresolved charge.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def reserve(
        self,
        task_id: UUID,
        quote: GenerationCostQuote,
        *,
        operation: str = _STRATEGY_OPERATION,
    ) -> GenerationCostReservation:
        self._validate_quote(quote, operation)
        reserved_cost = quote.maximum_cost_usd
        if not reserved_cost.is_finite() or reserved_cost <= 0:
            raise TaskGenerationCostError("generation_cost_quote_invalid")

        with self._session_factory.begin() as session:
            task = ObjectiveService._lock_task(session, task_id)
            if task is None:
                raise TaskGenerationCostError("task_not_found")
            expected_scope = {
                _STRATEGY_OPERATION: ("propose_strategy", []),
                _EXPERIENCE_OPERATION: ("propose_learning_change", ["LearningChange"]),
            }.get(operation)
            if expected_scope is None or task.task_type != expected_scope[0]:
                raise TaskGenerationCostError("generation_task_scope_violation")
            if task.status != "running":
                raise TaskGenerationCostError("task_not_running")
            if task.attempt_count < 1:
                raise TaskGenerationCostError("task_attempt_not_admitted")
            if task.allowed_writes != expected_scope[1]:
                raise TaskGenerationCostError(
                    "generation_task_write_scope_violation"
                )

            maximum_task_cost = self._task_cost_limit(task)
            prior_attempt = session.scalar(
                select(TaskGenerationCharge).where(
                    TaskGenerationCharge.task_id == task.id,
                    TaskGenerationCharge.attempt_count == task.attempt_count,
                    TaskGenerationCharge.operation == operation,
                )
            )
            if prior_attempt is not None:
                raise TaskGenerationCostError(
                    "generation_attempt_already_reserved_or_recorded"
                )

            charges = list(
                session.scalars(
                    select(TaskGenerationCharge).where(
                        TaskGenerationCharge.task_id == task.id
                    )
                )
            )
            already_accounted = sum(
                (
                    charge.accounted_cost_usd
                    if charge.accounted_cost_usd is not None
                    else charge.reserved_cost_usd
                    for charge in charges
                ),
                start=Decimal("0"),
            )
            if already_accounted + reserved_cost > maximum_task_cost:
                raise TaskGenerationCostError("task_generation_budget_exhausted")

            charge = TaskGenerationCharge(
                id=uuid4(),
                task_id=task.id,
                attempt_count=task.attempt_count,
                operation=operation,
                provider=quote.provider,
                model=quote.model,
                pricing_revision=quote.pricing_revision,
                max_input_tokens=quote.maximum_input_tokens,
                max_output_tokens=quote.maximum_output_tokens,
                input_usd_per_million_tokens=quote.input_usd_per_million_tokens,
                output_usd_per_million_tokens=quote.output_usd_per_million_tokens,
                reserved_cost_usd=reserved_cost,
                accounted_cost_usd=None,
                input_tokens=None,
                output_tokens=None,
                request_id=None,
                status="reserved",
                failure_reason=None,
                created_at=datetime.now(timezone.utc),
                settled_at=None,
            )
            session.add(charge)
            self._event(
                session,
                task.id,
                "generation_cost_reserved",
                {
                    "charge_id": str(charge.id),
                    "attempt_count": charge.attempt_count,
                    "operation": charge.operation,
                    "provider": charge.provider,
                    "model": charge.model,
                    "pricing_revision": charge.pricing_revision,
                    "max_input_tokens": charge.max_input_tokens,
                    "max_output_tokens": charge.max_output_tokens,
                    "reserved_cost_usd": str(charge.reserved_cost_usd),
                },
            )
            session.flush()
            return GenerationCostReservation(
                charge_id=charge.id,
                task_id=charge.task_id,
                attempt_count=charge.attempt_count,
                reserved_cost_usd=charge.reserved_cost_usd,
                provider=charge.provider,
                model=charge.model,
                operation=charge.operation,
            )

    def mark_unknown(
        self,
        reservation: GenerationCostReservation,
        reason: str,
    ) -> None:
        safe_reason = self._safe_reason(reason)
        with self._session_factory.begin() as session:
            task = ObjectiveService._lock_task(session, reservation.task_id)
            if task is None:
                raise TaskGenerationCostError("task_not_found")
            charge = self._locked_charge(session, reservation)
            if charge.status == "unknown":
                if charge.failure_reason != safe_reason:
                    raise TaskGenerationCostError(
                        "generation_charge_state_conflict"
                    )
                return
            if charge.status != "reserved":
                raise TaskGenerationCostError("generation_charge_already_settled")
            self._mark_unknown_in_session(session, task, charge, safe_reason)
            session.flush()

    def reconcile(
        self,
        reservation: GenerationCostReservation,
        *,
        model: str,
        usage: GenerationUsage,
        request_id: str | None,
    ) -> GenerationCostReconciliation:
        self._validate_usage(usage)
        if request_id is not None and (
            not isinstance(request_id, str) or len(request_id) > 255
        ):
            raise TaskGenerationCostError("generation_request_id_invalid")

        result: GenerationCostReconciliation
        model_mismatch = False
        with self._session_factory.begin() as session:
            task = ObjectiveService._lock_task(session, reservation.task_id)
            if task is None:
                raise TaskGenerationCostError("task_not_found")
            charge = self._locked_charge(session, reservation)

            usage_cost = (
                Decimal(usage.input_tokens)
                * charge.input_usd_per_million_tokens
                + Decimal(usage.output_tokens)
                * charge.output_usd_per_million_tokens
            ) / _COST_DIVISOR

            if charge.model != model:
                self._mark_unknown_in_session(
                    session, task, charge, "provider_model_mismatch"
                )
                model_mismatch = True
                result = GenerationCostReconciliation(
                    charge_id=charge.id,
                    status="unknown",
                    usage_cost_usd=usage_cost,
                    accounted_cost_usd=charge.reserved_cost_usd,
                )
            elif charge.status in {"reconciled", "overrun"}:
                if (
                    charge.input_tokens == usage.input_tokens
                    and charge.output_tokens == usage.output_tokens
                    and charge.request_id == request_id
                    and charge.accounted_cost_usd is not None
                ):
                    result = GenerationCostReconciliation(
                        charge_id=charge.id,
                        status=charge.status,
                        usage_cost_usd=usage_cost,
                        accounted_cost_usd=charge.accounted_cost_usd,
                        replayed=True,
                    )
                else:
                    raise TaskGenerationCostError(
                        "generation_reconciliation_conflict"
                    )
            elif charge.status != "reserved":
                raise TaskGenerationCostError("generation_charge_not_reconcilable")
            else:
                bounds_exceeded = (
                    usage.input_tokens > charge.max_input_tokens
                    or usage.output_tokens > charge.max_output_tokens
                )
                overrun = bounds_exceeded or usage_cost > charge.reserved_cost_usd
                accounted_cost = (
                    max(usage_cost, charge.reserved_cost_usd)
                    if overrun
                    else usage_cost
                )
                charge.input_tokens = usage.input_tokens
                charge.output_tokens = usage.output_tokens
                charge.request_id = request_id
                charge.accounted_cost_usd = accounted_cost
                charge.status = "overrun" if overrun else "reconciled"
                charge.failure_reason = (
                    "provider_usage_exceeded_reserved_bound" if overrun else None
                )
                charge.settled_at = datetime.now(timezone.utc)
                self._event(
                    session,
                    task.id,
                    "generation_cost_overrun"
                    if overrun
                    else "generation_cost_reconciled",
                    {
                        "charge_id": str(charge.id),
                        "attempt_count": charge.attempt_count,
                        "provider": charge.provider,
                        "model": charge.model,
                        "request_id": request_id,
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "usage_cost_usd": str(usage_cost),
                        "reserved_cost_usd": str(charge.reserved_cost_usd),
                        "accounted_cost_usd": str(accounted_cost),
                        "pricing_revision": charge.pricing_revision,
                        "failure_reason": charge.failure_reason,
                    },
                )
                result = GenerationCostReconciliation(
                    charge_id=charge.id,
                    status=charge.status,
                    usage_cost_usd=usage_cost,
                    accounted_cost_usd=accounted_cost,
                )
            session.flush()

        # Raise only after the transaction commits the unknown state.
        if model_mismatch:
            raise TaskGenerationCostError("provider_model_mismatch")
        return result

    @staticmethod
    def _validate_quote(quote: GenerationCostQuote, operation: str) -> None:
        if not isinstance(quote, GenerationCostQuote):
            raise TaskGenerationCostError("generation_cost_quote_invalid")
        if (
            not isinstance(quote.provider, str)
            or not isinstance(quote.model, str)
            or not isinstance(quote.pricing_revision, str)
            or isinstance(quote.maximum_input_tokens, bool)
            or not isinstance(quote.maximum_input_tokens, int)
            or quote.maximum_input_tokens < 0
            or isinstance(quote.maximum_output_tokens, bool)
            or not isinstance(quote.maximum_output_tokens, int)
            or not isinstance(quote.input_usd_per_million_tokens, Decimal)
            or not isinstance(quote.output_usd_per_million_tokens, Decimal)
            or not quote.input_usd_per_million_tokens.is_finite()
            or not quote.output_usd_per_million_tokens.is_finite()
        ):
            raise TaskGenerationCostError("generation_cost_quote_invalid")
        if operation == _STRATEGY_OPERATION:
            valid_card = (
                quote.provider == "cloudflare_workers_ai"
                and quote.model == DEFAULT_MODEL
                and quote.pricing_revision == CLOUDFLARE_PRICING_REVISION
                and quote.input_usd_per_million_tokens
                == INPUT_USD_PER_MILLION_TOKENS
                and quote.output_usd_per_million_tokens
                == OUTPUT_USD_PER_MILLION_TOKENS
                and 1 <= quote.maximum_output_tokens <= DEFAULT_MAX_OUTPUT_TOKENS
            )
            maximum_output = DEFAULT_MAX_OUTPUT_TOKENS
        elif operation == _EXPERIENCE_OPERATION:
            # This synthetic rate card exists only for deterministic CI fakes.
            # ADR-0031 does not authorize a production R6-F provider/model.
            valid_card = (
                quote.provider == _EXPERIENCE_FAKE_PROVIDER
                and quote.model == _EXPERIENCE_FAKE_MODEL
                and quote.pricing_revision == _EXPERIENCE_FAKE_PRICING_REVISION
                and quote.input_usd_per_million_tokens == _EXPERIENCE_FAKE_INPUT_RATE
                and quote.output_usd_per_million_tokens == _EXPERIENCE_FAKE_OUTPUT_RATE
                and 1
                <= quote.maximum_output_tokens
                <= _EXPERIENCE_FAKE_MAX_OUTPUT_TOKENS
            )
            maximum_output = _EXPERIENCE_FAKE_MAX_OUTPUT_TOKENS
        else:
            raise TaskGenerationCostError("generation_operation_not_authorized")
        if (
            quote.maximum_output_tokens > maximum_output
            or quote.maximum_input_tokens + quote.maximum_output_tokens
            > MAX_MODEL_CONTEXT_TOKENS
            or not valid_card
        ):
            raise TaskGenerationCostError("generation_cost_quote_invalid")

    @staticmethod
    def _validate_usage(usage: GenerationUsage) -> None:
        if (
            not isinstance(usage, GenerationUsage)
            or isinstance(usage.input_tokens, bool)
            or not isinstance(usage.input_tokens, int)
            or usage.input_tokens < 0
            or isinstance(usage.output_tokens, bool)
            or not isinstance(usage.output_tokens, int)
            or usage.output_tokens < 0
        ):
            raise TaskGenerationCostError("generation_usage_invalid")

    @staticmethod
    def _task_cost_limit(task: Task) -> Decimal:
        if not isinstance(task.budget, dict):
            raise TaskGenerationCostError("invalid_task_budget")
        raw = task.budget.get("max_cost_usd")
        if isinstance(raw, bool) or not isinstance(raw, (int, float, Decimal)):
            raise TaskGenerationCostError("invalid_task_budget")
        try:
            limit = Decimal(str(raw))
        except (InvalidOperation, ValueError) as error:
            raise TaskGenerationCostError("invalid_task_budget") from error
        if not limit.is_finite() or limit < 0:
            raise TaskGenerationCostError("invalid_task_budget")
        return limit

    @staticmethod
    def _safe_reason(reason: str) -> str:
        if (
            isinstance(reason, str)
            and 0 < len(reason) <= 96
            and all(
                character.islower() or character.isdigit() or character == "_"
                for character in reason
            )
        ):
            return reason
        return "provider_call_failed"

    @staticmethod
    def _locked_charge(
        session: Session, reservation: GenerationCostReservation
    ) -> TaskGenerationCharge:
        charge = session.scalar(
            select(TaskGenerationCharge)
            .where(
                TaskGenerationCharge.id == reservation.charge_id,
                TaskGenerationCharge.task_id == reservation.task_id,
                TaskGenerationCharge.attempt_count == reservation.attempt_count,
            )
            .with_for_update()
        )
        if charge is None or charge.operation != reservation.operation:
            raise TaskGenerationCostError("generation_charge_not_found")
        return charge

    @classmethod
    def _mark_unknown_in_session(
        cls,
        session: Session,
        task: Task,
        charge: TaskGenerationCharge,
        reason: str,
    ) -> None:
        if charge.status == "reserved":
            charge.status = "unknown"
            charge.failure_reason = reason
            charge.settled_at = datetime.now(timezone.utc)
            cls._event(
                session,
                task.id,
                "generation_cost_unknown",
                {
                    "charge_id": str(charge.id),
                    "attempt_count": charge.attempt_count,
                    "reserved_cost_usd": str(charge.reserved_cost_usd),
                    "failure_reason": reason,
                    "conservative_budget_charge_usd": str(
                        charge.reserved_cost_usd
                    ),
                },
            )

    @staticmethod
    def _event(
        session: Session,
        task_id: UUID,
        event_type: str,
        payload: dict[str, object],
    ) -> Event:
        return ObjectiveService._add_event(
            session,
            task_id,
            event_type,
            payload,
        )
