"""Deterministic Operator world-memory proposal validation and commit.

The host authenticates the Operator. This module receives only the canonical
principal identity and an ordinary, admitted `operator_update` Task. It never
writes Task lifecycle state.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated, Literal, Union
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.models import (
    ConfidenceChange,
    Event,
    EvidenceLink,
    Hypothesis,
    Outcome,
    Signal,
    Task,
    TaskGenerationCharge,
    Team,
    Thread,
)
from core.snapshot_store import SnapshotIntegrityError, SnapshotStore

if TYPE_CHECKING:
    from core.task_runtime import TerminalObservation

TASK_TYPE = "operator_update"
REQUEST_EVENT_TYPE = "operator_update_requested"
COMMITTED_EVENT_TYPE = "operator_update_committed"
REJECTED_EVENT_TYPE = "operator_update_rejected"
ALLOWED_WRITES = ["EvidenceLink", "Hypothesis", "ConfidenceChange"]
MAX_ATTEMPTS = 3
TASK_BUDGET = {"max_tool_calls": 0, "max_cost_usd": 0.0}
MODEL_COMMITTED_EVENT_TYPE = "update_thread_committed"
MODEL_REJECTED_EVENT_TYPE = "update_thread_rejected"
MODEL_INCONSISTENT_EVENT_TYPE = "update_thread_recovery_inconsistent"
_TASK_ID_NAMESPACE = UUID("e17c32e7-16e0-4cc7-9c62-8cdeed0e17d1")


class WorldMemoryError(ValueError):
    """A malformed or inconsistent world-memory request or commit."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: str
    key: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_key(self):
        if not self.key.strip():
            raise ValueError("proposal_key_required")
        return self


class HypothesisCreateProposal(_Proposal):
    kind: Literal["hypothesis_create"]
    hypothesis_id: UUID
    statement: str = Field(min_length=1, max_length=4000)
    confidence: Literal["low", "moderate", "high"] = "low"

    @model_validator(mode="after")
    def validate_statement(self):
        if not self.statement.strip():
            raise ValueError("hypothesis_statement_required")
        return self


class EvidenceLinkProposal(_Proposal):
    kind: Literal["evidence_link_add"]
    hypothesis_id: UUID
    source_kind: Literal["signal", "outcome"]
    signal_id: UUID | None = None
    outcome_id: UUID | None = None
    stance: Literal["supports", "challenges", "mentions"]
    snapshot_ref: str | None = None
    snapshot_hash: str | None = None
    quote_text: str | None = Field(default=None, max_length=4000)
    quote_start: int | None = None
    quote_end: int | None = None

    @model_validator(mode="after")
    def validate_shape(self):
        if self.source_kind == "signal":
            if self.signal_id is None or self.outcome_id is not None:
                raise ValueError("signal_evidence_requires_only_signal_id")
        elif self.outcome_id is None or self.signal_id is not None:
            raise ValueError("outcome_evidence_requires_only_outcome_id")
        if (self.snapshot_ref is None) != (self.snapshot_hash is None):
            raise ValueError("snapshot_ref_and_hash_must_be_paired")
        quote = (self.quote_text, self.quote_start, self.quote_end)
        if any(value is not None for value in quote) and not all(
            value is not None for value in quote
        ):
            raise ValueError("quote_text_and_offsets_must_be_paired")
        if self.quote_start is not None and (
            self.quote_start < 0
            or self.quote_end is None
            or self.quote_end <= self.quote_start
        ):
            raise ValueError("invalid_quote_offsets")
        return self


class ConfidenceChangeProposal(_Proposal):
    kind: Literal["confidence_change"]
    hypothesis_id: UUID
    evidence_link_id: UUID
    to_confidence: Literal["low", "moderate", "high"]


class HypothesisTransitionProposal(_Proposal):
    kind: Literal["hypothesis_transition"]
    hypothesis_id: UUID
    action: Literal["reject", "supersede"]
    reason: str = Field(min_length=1, max_length=2000)
    successor_hypothesis_id: UUID | None = None

    @model_validator(mode="after")
    def validate_transition(self):
        if not self.reason.strip():
            raise ValueError("hypothesis_transition_reason_required")
        if self.action == "supersede" and self.successor_hypothesis_id is None:
            raise ValueError("hypothesis_successor_required")
        if self.action == "reject" and self.successor_hypothesis_id is not None:
            raise ValueError("hypothesis_rejection_successor_not_allowed")
        return self


Proposal = Annotated[
    Union[
        HypothesisCreateProposal,
        EvidenceLinkProposal,
        ConfidenceChangeProposal,
        HypothesisTransitionProposal,
    ],
    Field(discriminator="kind"),
]


class OperatorUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    thread_id: UUID
    idempotency_key: UUID
    proposals: list[Proposal] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_proposal_keys(self):
        keys = [proposal.key for proposal in self.proposals]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_proposal_key")
        return self


@dataclass(frozen=True)
class OperatorUpdateEnvelope:
    request: OperatorUpdateRequest
    task_id: UUID
    team_id: UUID
    operator_id: str
    policy_version: int
    request_fingerprint: str


@dataclass(frozen=True)
class OperatorActor:
    """Canonical authenticated Operator identity for the RW-2 path."""

    operator_id: str


@dataclass(frozen=True)
class ModelWorkerActor:
    """Application-constructed identity for one admitted update_thread Task."""

    actor_type: Literal["model_worker"]
    task_id: UUID
    request_event_id: UUID

    def __post_init__(self) -> None:
        if self.actor_type != "model_worker":
            raise ValueError("model_worker_actor_type_invalid")


WorldMemoryActor = OperatorActor | ModelWorkerActor


@dataclass(frozen=True)
class ModelUpdateThreadEnvelope:
    task_id: UUID
    team_id: UUID
    thread_id: UUID
    attempt: int
    policy_version: int
    request_event_id: UUID
    receipt_event_id: UUID
    proposal_event_id: UUID
    charge_id: UUID
    context_event_id: UUID
    context_snapshot_ref: str
    context_content_hash: str
    proposal_fingerprint: str
    proposals: tuple[Proposal, ...]


@dataclass(frozen=True)
class _ProposalCommitContext:
    thread_id: UUID
    proposals: tuple[Proposal, ...]
    request_fingerprint: str
    model_envelope: ModelUpdateThreadEnvelope | None = None

    @property
    def request(self) -> _ProposalCommitContext:
        return self


@dataclass(frozen=True)
class WorldMemoryCommitResult:
    task_id: UUID
    status: Literal["committed", "rejected"]
    committed_count: int
    rejected_count: int
    committed_at: datetime
    request_fingerprint: str
    replayed: bool = False
    failure_reason: str | None = None
    committed_proposal_keys: tuple[str, ...] = ()
    rejected_proposal_keys: tuple[str, ...] = ()


def _record_all_rejected(
    session: Session,
    task: Task,
    envelope: OperatorUpdateEnvelope,
    attempt: int,
    reasons: dict[str, str],
    *,
    failure_reason: str = "all_operator_update_proposals_rejected",
    created_at: datetime | None = None,
) -> WorldMemoryCommitResult:
    """Persist per-proposal rejections and the Task-level failure proof."""
    proposals = envelope.request.proposals
    if set(reasons) != {proposal.key for proposal in proposals}:
        raise WorldMemoryError("operator_update_rejection_set_incomplete")
    committed_at = created_at or datetime.now(timezone.utc)
    rejected_keys = [proposal.key for proposal in proposals]
    for proposal in proposals:
        session.add(
            Event(
                id=uuid4(),
                task_id=task.id,
                type="proposal_rejected",
                payload={
                    "task_id": str(task.id),
                    "team_id": str(task.team_id),
                    "operator_id": envelope.operator_id,
                    "request_fingerprint": envelope.request_fingerprint,
                    "proposal_key": proposal.key,
                    "reason": reasons[proposal.key],
                },
                created_at=committed_at,
            )
        )
    session.add(
        Event(
            id=uuid4(),
            task_id=task.id,
            type=REJECTED_EVENT_TYPE,
            payload={
                "schema_version": 1,
                "task_id": str(task.id),
                "team_id": str(task.team_id),
                "thread_id": str(envelope.request.thread_id),
                "attempt_count": attempt,
                "operator_id": envelope.operator_id,
                "request_fingerprint": envelope.request_fingerprint,
                "rejected_proposal_keys": rejected_keys,
                "failure_reason": failure_reason,
            },
            created_at=committed_at,
        )
    )
    session.flush()
    return WorldMemoryCommitResult(
        task_id=task.id,
        status="rejected",
        committed_count=0,
        rejected_count=len(rejected_keys),
        committed_at=committed_at,
        request_fingerprint=envelope.request_fingerprint,
        failure_reason="all_operator_update_proposals_rejected",
    )


def _actor_provenance_fields(
    actor: WorldMemoryActor, fingerprint: str
) -> dict[str, str]:
    if isinstance(actor, OperatorActor):
        return {
            "operator_id": actor.operator_id,
            "request_fingerprint": fingerprint,
        }
    return {
        "actor_type": actor.actor_type,
        "proposal_fingerprint": fingerprint,
    }


def _record_rejected_for_actor(
    session: Session,
    task: Task,
    context: _ProposalCommitContext,
    actor: WorldMemoryActor,
    attempt: int,
    reasons: dict[str, str],
    *,
    operator_envelope: OperatorUpdateEnvelope | None = None,
    created_at: datetime | None = None,
) -> WorldMemoryCommitResult:
    if isinstance(actor, OperatorActor):
        if operator_envelope is None:
            raise WorldMemoryError("operator_update_envelope_required")
        return _record_all_rejected(
            session,
            task,
            operator_envelope,
            attempt,
            reasons,
            created_at=created_at,
        )

    binding = context.model_envelope
    if binding is None or set(reasons) != {
        proposal.key for proposal in context.proposals
    }:
        raise WorldMemoryError("update_thread_rejection_set_incomplete")
    committed_at = created_at or datetime.now(timezone.utc)
    rejected_keys = [proposal.key for proposal in context.proposals]
    for proposal in context.proposals:
        session.add(
            Event(
                id=uuid4(),
                task_id=task.id,
                type="update_thread_proposal_rejected",
                payload={
                    "schema_version": 1,
                    "task_id": str(task.id),
                    "team_id": str(task.team_id),
                    "thread_id": str(context.thread_id),
                    "attempt": attempt,
                    "actor_type": actor.actor_type,
                    "proposal_key": proposal.key,
                    "proposal_fingerprint": context.request_fingerprint,
                    "reason": reasons[proposal.key],
                },
                created_at=committed_at,
            )
        )
    session.add(
        Event(
            id=uuid4(),
            task_id=task.id,
            type="update_thread_rejected",
            payload={
                "schema_version": 1,
                "task_id": str(task.id),
                "team_id": str(task.team_id),
                "thread_id": str(context.thread_id),
                "attempt": attempt,
                "actor_type": actor.actor_type,
                "request_event_id": str(binding.request_event_id),
                "generation_receipt_event_id": str(binding.receipt_event_id),
                "proposal_event_id": str(binding.proposal_event_id),
                "charge_id": str(binding.charge_id),
                "context_event_id": str(binding.context_event_id),
                "context_snapshot_ref": binding.context_snapshot_ref,
                "context_content_hash": binding.context_content_hash,
                "proposal_fingerprint": context.request_fingerprint,
                "accepted_proposal_keys": [],
                "rejected_proposal_keys": rejected_keys,
            },
            created_at=committed_at,
        )
    )
    session.flush()
    return WorldMemoryCommitResult(
        task_id=task.id,
        status="rejected",
        committed_count=0,
        rejected_count=len(rejected_keys),
        committed_at=committed_at,
        request_fingerprint=context.request_fingerprint,
        failure_reason="all_update_thread_proposals_rejected",
        rejected_proposal_keys=tuple(rejected_keys),
    )


def task_id_for_request(team_id: UUID, idempotency_key: UUID) -> UUID:
    return uuid5(
        _TASK_ID_NAMESPACE,
        f"{team_id}:{TASK_TYPE}:{idempotency_key}",
    )


def _sha256_json(value: dict[str, object]) -> str:
    raw = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def build_request_event_payload(
    *,
    task_id: UUID,
    team_id: UUID,
    policy_version: int,
    operator_id: str,
    request: OperatorUpdateRequest,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "operation": TASK_TYPE,
        "task_id": str(task_id),
        "team_id": str(team_id),
        "thread_id": str(request.thread_id),
        "policy_version": policy_version,
        "operator_id": operator_id,
        "idempotency_key": str(request.idempotency_key),
        "idempotency_key_hash": "sha256:"
        + hashlib.sha256(str(request.idempotency_key).encode("ascii")).hexdigest(),
        "proposals": [
            proposal.model_dump(mode="json") for proposal in request.proposals
        ],
    }
    payload["request_fingerprint"] = _sha256_json(payload)
    return payload


def validate_operator_update_task_request(
    session: Session,
    task: Task,
    *,
    require_thread_available: bool = False,
) -> OperatorUpdateEnvelope:
    """Validate the immutable request Event and exact ordinary Task envelope."""
    if (
        task.task_type != TASK_TYPE
        or task.objective_id is not None
        or task.plan_id is not None
        or task.plan_action_id is not None
        or task.allowed_writes != ALLOWED_WRITES
        or task.budget != TASK_BUDGET
        or task.max_attempts != MAX_ATTEMPTS
        or isinstance(task.attempt_count, bool)
        or not isinstance(task.attempt_count, int)
        or not 0 <= task.attempt_count <= MAX_ATTEMPTS
        or (task.status in {"running", "done", "failed"} and task.attempt_count < 1)
        or (task.completed_at is not None and task.status != "done")
    ):
        raise WorldMemoryError("operator_update_task_shape_invalid")

    events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
    )
    if len(events) != 1 or not isinstance(events[0].payload, dict):
        raise WorldMemoryError("operator_update_request_event_invalid")
    payload = events[0].payload
    expected_keys = {
        "schema_version",
        "operation",
        "task_id",
        "team_id",
        "thread_id",
        "policy_version",
        "operator_id",
        "idempotency_key",
        "idempotency_key_hash",
        "proposals",
        "request_fingerprint",
    }
    if (
        set(payload) != expected_keys
        or payload.get("schema_version") != 1
        or payload.get("operation") != TASK_TYPE
        or payload.get("task_id") != str(task.id)
        or payload.get("team_id") != str(task.team_id)
        or not isinstance(payload.get("thread_id"), str)
        or payload.get("policy_version") != task.policy_version
        or not isinstance(payload.get("operator_id"), str)
        or not payload["operator_id"]
        or len(payload["operator_id"]) > 255
        or not isinstance(payload.get("idempotency_key"), str)
    ):
        raise WorldMemoryError("operator_update_request_event_invalid")

    try:
        idempotency_key = UUID(payload["idempotency_key"])
        request = OperatorUpdateRequest.model_validate(
            {
                "thread_id": payload["thread_id"],
                "idempotency_key": str(idempotency_key),
                "proposals": payload["proposals"],
            }
        )
    except (TypeError, ValueError) as error:
        raise WorldMemoryError("operator_update_request_payload_invalid") from error
    if str(idempotency_key) != payload["idempotency_key"]:
        raise WorldMemoryError("operator_update_idempotency_key_invalid")
    try:
        actor = json.loads(payload["operator_id"])
        if not isinstance(actor, dict) or set(actor) != {"iss", "sub"}:
            raise ValueError("operator_identity_shape_invalid")
        from core.operator_approval import canonical_operator_identity

        canonical_actor = canonical_operator_identity(actor["iss"], actor["sub"])
        if canonical_actor != payload["operator_id"]:
            raise ValueError("operator_identity_not_canonical")
    except (TypeError, ValueError, KeyError) as error:
        raise WorldMemoryError("operator_update_operator_identity_invalid") from error
    expected_key_hash = "sha256:" + hashlib.sha256(
        str(idempotency_key).encode("ascii")
    ).hexdigest()
    if payload.get("idempotency_key_hash") != expected_key_hash:
        raise WorldMemoryError("operator_update_idempotency_hash_mismatch")
    if task.id != task_id_for_request(task.team_id, idempotency_key):
        raise WorldMemoryError("operator_update_task_id_mismatch")

    unsigned = {
        key: value
        for key, value in payload.items()
        if key != "request_fingerprint"
    }
    fingerprint = payload.get("request_fingerprint")
    if not isinstance(fingerprint, str) or fingerprint != _sha256_json(unsigned):
        raise WorldMemoryError("operator_update_request_fingerprint_mismatch")

    thread = session.get(Thread, request.thread_id)
    if (
        thread is None
        or thread.team_id != task.team_id
        or (require_thread_available and thread.status == "resolved")
    ):
        raise WorldMemoryError("operator_update_thread_not_available")
    return OperatorUpdateEnvelope(
        request=request,
        task_id=task.id,
        team_id=task.team_id,
        operator_id=payload["operator_id"],
        policy_version=task.policy_version,
        request_fingerprint=fingerprint,
    )


def _snapshot_for_source(
    session: Session,
    team: Team,
    proposal: EvidenceLinkProposal,
) -> tuple[str, str, UUID | None, UUID | None]:
    if proposal.source_kind == "signal":
        source = session.get(Signal, proposal.signal_id)
        if source is None or source.domain != team.domain:
            raise WorldMemoryError("evidence_signal_team_domain_mismatch")
        snapshot_ref, snapshot_hash = source.snapshot_ref, source.content_hash
        signal_id, outcome_id = source.id, None
    else:
        outcome_source = session.get(Outcome, proposal.outcome_id)
        if (
            outcome_source is None
            or outcome_source.team_id != team.id
            or outcome_source.observation_snapshot_ref is None
            or outcome_source.observation_hash is None
        ):
            raise WorldMemoryError("evidence_outcome_team_mismatch")
        snapshot_ref, snapshot_hash = (
            outcome_source.observation_snapshot_ref,
            outcome_source.observation_hash,
        )
        signal_id, outcome_id = None, outcome_source.id
    if (
        proposal.snapshot_ref is not None
        and (
            proposal.snapshot_ref != snapshot_ref
            or proposal.snapshot_hash != snapshot_hash
        )
    ):
        raise WorldMemoryError("source_snapshot_reference_mismatch")
    if snapshot_ref is None or snapshot_hash is None:
        raise WorldMemoryError("evidence_snapshot_required")
    return snapshot_ref, snapshot_hash, signal_id, outcome_id


def _verify_snapshot(
    snapshot_store: SnapshotStore,
    reference: str,
    expected_hash: str,
    quote: str | None,
    start: int | None,
    end: int | None,
) -> None:
    try:
        content = snapshot_store.read(reference)
    except SnapshotIntegrityError as error:
        raise WorldMemoryError(str(error)) from error
    actual_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    if actual_hash != expected_hash:
        raise WorldMemoryError("snapshot_hash_mismatch")
    if quote is not None:
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise WorldMemoryError("quoted_snapshot_not_utf8") from error
        if start is None or end is None or decoded[start:end] != quote:
            raise WorldMemoryError("quote_text_offset_mismatch")


def _attempt_event(
    session: Session,
    task: Task,
    event_type: str,
    attempt: int,
) -> Event:
    events = list(
        session.scalars(
            select(Event).where(Event.task_id == task.id, Event.type == event_type)
        )
    )
    matching: list[Event] = []
    for event in events:
        if not isinstance(event.payload, dict) or type(
            event.payload.get("attempt")
        ) is not int:
            raise WorldMemoryError("update_thread_event_corrupt")
        if event.payload["attempt"] > attempt:
            raise WorldMemoryError("update_thread_future_attempt_event")
        if event.payload["attempt"] == attempt:
            matching.append(event)
    if len(matching) != 1:
        raise WorldMemoryError("update_thread_event_missing_or_duplicate")
    return matching[0]


def _verified_model_receipt(
    session: Session,
    task: Task,
    attempt: int,
    snapshot_store: SnapshotStore,
    *,
    allow_overrun: bool = False,
):
    from core.update_thread import (
        GENERATION_RECEIPT_EVENT_TYPE,
        TASK_TYPE,
        UPDATE_THREAD_TEST_PROVIDER,
        UpdateThreadTaskError,
        load_pinned_policy,
        validate_update_thread_task_request,
    )
    from core.update_thread_context import (
        CONTEXT_EVENT_TYPE,
        AssembledUpdateThreadContext,
        UpdateThreadContextAssembler,
        UpdateThreadContextError,
    )

    if (
        task.task_type != TASK_TYPE
        or task.status not in {"running", "done", "failed"}
        or type(attempt) is not int
        or attempt < 1
        or task.attempt_count != attempt
    ):
        raise WorldMemoryError("update_thread_task_attempt_not_current")
    try:
        request = validate_update_thread_task_request(session, task)
        load_pinned_policy(session, task.team_id, task.policy_version)
    except UpdateThreadTaskError as error:
        raise WorldMemoryError(error.reason) from error
    context_event = _attempt_event(session, task, CONTEXT_EVENT_TYPE, attempt)
    context_payload = context_event.payload
    if (
        set(context_payload)
        != {
            "schema_version",
            "task_id",
            "team_id",
            "thread_id",
            "attempt",
            "policy_version",
            "snapshot_ref",
            "content_hash",
            "manifest",
        }
        or type(context_payload.get("schema_version")) is not int
        or context_payload.get("schema_version") != 1
        or context_payload.get("task_id") != str(task.id)
        or context_payload.get("team_id") != str(task.team_id)
        or context_payload.get("thread_id") != str(request.thread_id)
        or type(context_payload.get("attempt")) is not int
        or context_payload.get("attempt") != attempt
        or type(context_payload.get("policy_version")) is not int
        or context_payload.get("policy_version") != task.policy_version
        or not isinstance(context_payload.get("snapshot_ref"), str)
        or not isinstance(context_payload.get("content_hash"), str)
        or not isinstance(context_payload.get("manifest"), dict)
    ):
        raise WorldMemoryError("update_thread_context_event_invalid")
    context = AssembledUpdateThreadContext(
        task_id=task.id,
        team_id=task.team_id,
        thread_id=request.thread_id,
        attempt=attempt,
        snapshot_ref=context_payload["snapshot_ref"],
        content_hash=context_payload["content_hash"],
        event_id=context_event.id,
        manifest=context_payload["manifest"],
        document={},
        replayed=True,
    )
    try:
        verified_context = UpdateThreadContextAssembler(
            None, snapshot_store
        ).verify_context_in_session(session, task, context)
    except UpdateThreadContextError as error:
        raise WorldMemoryError(error.reason) from error

    receipt_event = _attempt_event(
        session, task, GENERATION_RECEIPT_EVENT_TYPE, attempt
    )
    receipt = receipt_event.payload
    expected_receipt_keys = {
        "schema_version",
        "task_id",
        "team_id",
        "thread_id",
        "attempt",
        "policy_version",
        "context_event_id",
        "context_snapshot_ref",
        "context_content_hash",
        "actor_type",
        "operation",
        "charge_id",
        "provider",
        "model",
        "request_id",
        "prompt_tokens",
        "completion_tokens",
        "raw_completion_text",
    }
    if (
        set(receipt) != expected_receipt_keys
        or type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
        or receipt.get("task_id") != str(task.id)
        or receipt.get("team_id") != str(task.team_id)
        or receipt.get("thread_id") != str(request.thread_id)
        or type(receipt.get("attempt")) is not int
        or receipt.get("attempt") != attempt
        or type(receipt.get("policy_version")) is not int
        or receipt.get("policy_version") != task.policy_version
        or receipt.get("context_event_id") != str(verified_context.event_id)
        or receipt.get("context_snapshot_ref") != verified_context.snapshot_ref
        or receipt.get("context_content_hash") != verified_context.content_hash
        or receipt.get("actor_type") != "model_worker"
        or receipt.get("operation") != TASK_TYPE
        or receipt.get("provider") != UPDATE_THREAD_TEST_PROVIDER
        or not isinstance(receipt.get("model"), str)
        or not receipt["model"]
        or not isinstance(receipt.get("charge_id"), str)
        or (
            receipt.get("request_id") is not None
            and not isinstance(receipt.get("request_id"), str)
        )
        or type(receipt.get("prompt_tokens")) is not int
        or receipt["prompt_tokens"] < 0
        or type(receipt.get("completion_tokens")) is not int
        or receipt["completion_tokens"] < 0
        or not isinstance(receipt.get("raw_completion_text"), str)
    ):
        raise WorldMemoryError("update_thread_generation_receipt_invalid")
    try:
        charge_id = UUID(receipt["charge_id"])
    except (TypeError, ValueError) as error:
        raise WorldMemoryError("update_thread_generation_charge_invalid") from error
    charges = list(
        session.scalars(
            select(TaskGenerationCharge)
            .where(
                TaskGenerationCharge.task_id == task.id,
                TaskGenerationCharge.attempt_count == attempt,
                TaskGenerationCharge.operation == TASK_TYPE,
            )
            .with_for_update()
        )
    )
    if len(charges) != 1 or charges[0].id != charge_id:
        raise WorldMemoryError("update_thread_generation_charge_cardinality_invalid")
    charge = charges[0]
    reconciliation_events = [
        event
        for event in session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type.in_(
                    ("generation_cost_reconciled", "generation_cost_overrun")
                ),
            )
        )
        if isinstance(event.payload, dict)
        and event.payload.get("charge_id") == str(charge_id)
    ]
    expected_event_type = (
        "generation_cost_overrun"
        if charge.status == "overrun"
        else "generation_cost_reconciled"
    )
    allowed_charge_statuses = (
        {"reconciled", "overrun"} if allow_overrun else {"reconciled"}
    )
    if (
        charge.status not in allowed_charge_statuses
        or charge.accounted_cost_usd is None
        or charge.provider != receipt["provider"]
        or charge.model != receipt["model"]
        or charge.request_id != receipt["request_id"]
        or charge.input_tokens != receipt["prompt_tokens"]
        or charge.output_tokens != receipt["completion_tokens"]
        or len(reconciliation_events) != 1
        or reconciliation_events[0].type != expected_event_type
    ):
        raise WorldMemoryError("update_thread_generation_charge_invalid")
    charge_payload = reconciliation_events[0].payload
    expected_failure_reason = (
        "provider_usage_exceeded_reserved_bound"
        if charge.status == "overrun"
        else None
    )
    if (
        charge_payload.get("attempt_count") != attempt
        or charge_payload.get("provider") != charge.provider
        or charge_payload.get("model") != charge.model
        or charge_payload.get("request_id") != charge.request_id
        or charge_payload.get("input_tokens") != charge.input_tokens
        or charge_payload.get("output_tokens") != charge.output_tokens
        or charge_payload.get("failure_reason") != expected_failure_reason
    ):
        raise WorldMemoryError("update_thread_generation_charge_event_invalid")
    return request, verified_context, receipt_event, charge


def load_model_update_thread_envelope(
    session: Session,
    task: Task,
    attempt: int,
    snapshot_store: SnapshotStore,
) -> ModelUpdateThreadEnvelope:
    """Reconstruct one fully verified model proposal envelope from durable rows."""
    from core.update_thread import PROPOSALS_EVENT_TYPE
    from core.update_thread_worker import _fingerprint, _parse_model_response

    request, verified_context, receipt_event, charge = _verified_model_receipt(
        session, task, attempt, snapshot_store
    )
    receipt = receipt_event.payload
    request_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "update_thread_requested",
            )
        )
    )
    if len(request_events) != 1:
        raise WorldMemoryError("update_thread_request_event_missing_or_duplicate")
    request_event_id = request_events[0].id

    proposal_event = _attempt_event(session, task, PROPOSALS_EVENT_TYPE, attempt)
    proposal_payload = proposal_event.payload
    proposal_keys = {
        "schema_version",
        "task_id",
        "team_id",
        "thread_id",
        "attempt",
        "policy_version",
        "generation_receipt_event_id",
        "context_event_id",
        "context_snapshot_ref",
        "context_content_hash",
        "charge_id",
        "proposal_fingerprint",
        "proposals",
    }
    if (
        set(proposal_payload) != proposal_keys
        or type(proposal_payload.get("schema_version")) is not int
        or proposal_payload.get("schema_version") != 1
        or proposal_payload.get("task_id") != str(task.id)
        or proposal_payload.get("team_id") != str(task.team_id)
        or proposal_payload.get("thread_id") != str(request.thread_id)
        or type(proposal_payload.get("attempt")) is not int
        or proposal_payload.get("attempt") != attempt
        or type(proposal_payload.get("policy_version")) is not int
        or proposal_payload.get("policy_version") != task.policy_version
        or proposal_payload.get("generation_receipt_event_id")
        != str(receipt_event.id)
        or proposal_payload.get("context_event_id")
        != str(verified_context.event_id)
        or proposal_payload.get("context_snapshot_ref")
        != verified_context.snapshot_ref
        or proposal_payload.get("context_content_hash")
        != verified_context.content_hash
        or proposal_payload.get("charge_id") != str(charge.id)
        or not isinstance(proposal_payload.get("proposals"), list)
    ):
        raise WorldMemoryError("update_thread_proposals_event_invalid")
    try:
        parsed = _parse_model_response(
            json.dumps(
                {"proposals": proposal_payload["proposals"]},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        canonical_proposals = [
            proposal.model_dump(mode="json") for proposal in parsed.proposals
        ]
        raw_parsed = _parse_model_response(receipt["raw_completion_text"])
        if canonical_proposals != proposal_payload["proposals"] or [
            proposal.model_dump(mode="json") for proposal in raw_parsed.proposals
        ] != canonical_proposals:
            raise ValueError("update_thread_proposal_payload_mismatch")
    except (TypeError, ValueError) as error:
        raise WorldMemoryError("update_thread_proposals_event_invalid") from error
    fingerprint = _fingerprint(
        task_id=task.id,
        team_id=task.team_id,
        thread_id=request.thread_id,
        attempt=attempt,
        policy_version=task.policy_version,
        receipt_event_id=receipt_event.id,
        context=verified_context,
        charge_id=charge.id,
        proposals=canonical_proposals,
    )
    if proposal_payload.get("proposal_fingerprint") != fingerprint:
        raise WorldMemoryError("update_thread_proposal_fingerprint_invalid")

    return ModelUpdateThreadEnvelope(
        task_id=task.id,
        team_id=task.team_id,
        thread_id=request.thread_id,
        attempt=attempt,
        policy_version=task.policy_version,
        request_event_id=request_event_id,
        receipt_event_id=receipt_event.id,
        proposal_event_id=proposal_event.id,
        charge_id=charge.id,
        context_event_id=verified_context.event_id,
        context_snapshot_ref=verified_context.snapshot_ref,
        context_content_hash=verified_context.content_hash,
        proposal_fingerprint=fingerprint,
        proposals=tuple(parsed.proposals),
    )


def validate_model_update_thread_envelope(
    session: Session,
    task: Task,
    attempt: int,
    envelope: ModelUpdateThreadEnvelope,
    snapshot_store: SnapshotStore,
) -> _ProposalCommitContext:
    if not isinstance(envelope, ModelUpdateThreadEnvelope):
        raise WorldMemoryError("update_thread_commit_envelope_invalid")
    durable = load_model_update_thread_envelope(
        session, task, attempt, snapshot_store
    )
    if durable != envelope:
        raise WorldMemoryError("update_thread_commit_envelope_mismatch")
    return _ProposalCommitContext(
        thread_id=durable.thread_id,
        proposals=durable.proposals,
        request_fingerprint=durable.proposal_fingerprint,
        model_envelope=durable,
    )


def validate_model_update_thread_marker(
    session: Session,
    task: Task,
    envelope: ModelUpdateThreadEnvelope,
    marker: Event,
    snapshot_store: SnapshotStore,
) -> WorldMemoryCommitResult:
    """Verify one model marker and every accepted/rejected proposal record."""
    proposal_by_key = {proposal.key: proposal for proposal in envelope.proposals}
    if marker.task_id != task.id or not isinstance(marker.payload, dict):
        raise WorldMemoryError("update_thread_commit_marker_invalid")
    payload = marker.payload
    common = {
        "schema_version",
        "task_id",
        "team_id",
        "thread_id",
        "attempt",
        "actor_type",
        "request_event_id",
        "generation_receipt_event_id",
        "proposal_event_id",
        "charge_id",
        "context_event_id",
        "context_snapshot_ref",
        "context_content_hash",
        "proposal_fingerprint",
        "accepted_proposal_keys",
        "rejected_proposal_keys",
    }
    if (
        payload.get("schema_version") != 1
        or type(payload.get("schema_version")) is not int
        or payload.get("task_id") != str(task.id)
        or payload.get("team_id") != str(task.team_id)
        or payload.get("thread_id") != str(envelope.thread_id)
        or type(payload.get("attempt")) is not int
        or payload.get("attempt") != envelope.attempt
        or payload.get("actor_type") != "model_worker"
        or payload.get("request_event_id") != str(envelope.request_event_id)
        or payload.get("generation_receipt_event_id")
        != str(envelope.receipt_event_id)
        or payload.get("proposal_event_id") != str(envelope.proposal_event_id)
        or payload.get("charge_id") != str(envelope.charge_id)
        or payload.get("context_event_id") != str(envelope.context_event_id)
        or payload.get("context_snapshot_ref") != envelope.context_snapshot_ref
        or payload.get("context_content_hash") != envelope.context_content_hash
        or payload.get("proposal_fingerprint") != envelope.proposal_fingerprint
    ):
        raise WorldMemoryError("update_thread_commit_marker_invalid")

    accepted = payload.get("accepted_proposal_keys")
    rejected = payload.get("rejected_proposal_keys")
    expected_order = [proposal.key for proposal in envelope.proposals]
    if (
        not isinstance(accepted, list)
        or not isinstance(rejected, list)
        or not all(isinstance(key, str) for key in accepted + rejected)
        or len(accepted) != len(set(accepted))
        or len(rejected) != len(set(rejected))
        or set(accepted) & set(rejected)
        or set(accepted) | set(rejected) != set(proposal_by_key)
        or accepted != [key for key in expected_order if key in accepted]
        or rejected != [key for key in expected_order if key in rejected]
    ):
        raise WorldMemoryError("update_thread_commit_key_partition_invalid")

    accepted_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "update_thread_proposal_accepted",
            )
        )
    )
    rejected_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "update_thread_proposal_rejected",
            )
        )
    )
    by_disposition: dict[str, list[Event]] = {}
    for event in accepted_events + rejected_events:
        event_payload = event.payload
        if (
            not isinstance(event_payload, dict)
            or "operator_id" in event_payload
            or type(event_payload.get("schema_version")) is not int
            or event_payload.get("schema_version") != 1
            or event_payload.get("task_id") != str(task.id)
            or event_payload.get("team_id") != str(task.team_id)
            or event_payload.get("thread_id") != str(envelope.thread_id)
            or type(event_payload.get("attempt")) is not int
            or event_payload.get("attempt") != envelope.attempt
            or event_payload.get("actor_type") != "model_worker"
            or event_payload.get("proposal_fingerprint")
            != envelope.proposal_fingerprint
            or event_payload.get("proposal_key") not in proposal_by_key
        ):
            raise WorldMemoryError("update_thread_proposal_event_invalid")
        by_disposition.setdefault(event_payload["proposal_key"], []).append(event)
    if set(by_disposition) != set(proposal_by_key) or any(
        len(events) != 1 for events in by_disposition.values()
    ):
        raise WorldMemoryError("update_thread_proposal_event_set_invalid")
    for key in expected_order:
        event = by_disposition[key][0]
        if key in accepted:
            if (
                event.type != "update_thread_proposal_accepted"
                or set(event.payload)
                != {
                    "schema_version",
                    "task_id",
                    "team_id",
                    "thread_id",
                    "attempt",
                    "actor_type",
                    "proposal_key",
                    "proposal_fingerprint",
                    "disposition",
                }
                or event.payload.get("disposition") != "accepted"
            ):
                raise WorldMemoryError("update_thread_proposal_event_invalid")
        elif (
            event.type != "update_thread_proposal_rejected"
            or set(event.payload)
            != {
                "schema_version",
                "task_id",
                "team_id",
                "thread_id",
                "attempt",
                "actor_type",
                "proposal_key",
                "proposal_fingerprint",
                "reason",
            }
            or not isinstance(event.payload.get("reason"), str)
            or not event.payload["reason"].strip()
        ):
            raise WorldMemoryError("update_thread_proposal_event_invalid")

    accepted_domain_types: dict[str, str] = {}
    for key in accepted:
        proposal = proposal_by_key[key]
        if isinstance(proposal, HypothesisCreateProposal):
            accepted_domain_types[key] = "hypothesis_created"
        elif isinstance(proposal, EvidenceLinkProposal):
            accepted_domain_types[key] = "evidence_link_added"
        elif isinstance(proposal, ConfidenceChangeProposal):
            accepted_domain_types[key] = "confidence_changed"
        elif isinstance(proposal, HypothesisTransitionProposal):
            accepted_domain_types[key] = (
                "hypothesis_rejected"
                if proposal.action == "reject"
                else "hypothesis_superseded"
            )
    domain_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type.in_(
                    (
                        "hypothesis_created",
                        "evidence_link_added",
                        "confidence_changed",
                        "hypothesis_rejected",
                        "hypothesis_superseded",
                    )
                ),
            )
        )
    )
    domain_by_key: dict[str, list[Event]] = {}
    for event in domain_events:
        item = event.payload
        if (
            not isinstance(item, dict)
            or "operator_id" in item
            or item.get("task_id") != str(task.id)
            or item.get("team_id") != str(task.team_id)
            or item.get("actor_type") != "model_worker"
            or item.get("proposal_fingerprint") != envelope.proposal_fingerprint
            or item.get("proposal_key") not in accepted_domain_types
        ):
            raise WorldMemoryError("update_thread_business_event_invalid")
        domain_by_key.setdefault(item["proposal_key"], []).append(event)
    if set(domain_by_key) != set(accepted_domain_types) or any(
        len(events) != 1 or events[0].type != accepted_domain_types[key]
        for key, events in domain_by_key.items()
    ):
        raise WorldMemoryError("update_thread_business_event_set_invalid")

    if marker.type == MODEL_REJECTED_EVENT_TYPE:
        if set(payload) != common or accepted or rejected != expected_order:
            raise WorldMemoryError("update_thread_rejection_marker_invalid")
        if (
            accepted_events
            or len(rejected_events) != len(expected_order)
            or domain_events
            or session.scalar(
                select(EvidenceLink.id)
                .where(EvidenceLink.originating_task_id == task.id)
                .limit(1)
            )
            is not None
            or session.scalar(
                select(ConfidenceChange.id)
                .where(ConfidenceChange.created_by_task_id == task.id)
                .limit(1)
            )
            is not None
        ):
            raise WorldMemoryError("update_thread_rejection_rows_invalid")
        return WorldMemoryCommitResult(
            task_id=task.id,
            status="rejected",
            committed_count=0,
            rejected_count=len(rejected),
            committed_at=marker.created_at,
            request_fingerprint=envelope.proposal_fingerprint,
            replayed=True,
            failure_reason="all_update_thread_proposals_rejected",
            rejected_proposal_keys=tuple(rejected),
        )
    if marker.type != MODEL_COMMITTED_EVENT_TYPE or set(payload) != (
        common
        | {"hypothesis_ids", "evidence_link_ids", "confidence_change_ids"}
    ) or not accepted:
        raise WorldMemoryError("update_thread_commit_marker_invalid")

    row_fields = {
        "hypothesis_ids": [
            str(item.id)
            for item in session.scalars(
                select(Hypothesis).where(
                    Hypothesis.id.in_(
                        [
                            proposal.hypothesis_id
                            for proposal in envelope.proposals
                            if isinstance(proposal, HypothesisCreateProposal)
                            and proposal.key in accepted
                        ]
                        or {UUID(int=0)}
                    ),
                    Hypothesis.team_id == task.team_id,
                    Hypothesis.thread_id == envelope.thread_id,
                )
            )
        ],
        "evidence_link_ids": [
            str(item.id)
            for item in session.scalars(
                select(EvidenceLink).where(
                    EvidenceLink.originating_task_id == task.id,
                    EvidenceLink.team_id == task.team_id,
                    EvidenceLink.subject_kind == "hypothesis",
                )
            )
        ],
        "confidence_change_ids": [
            str(item.id)
            for item in session.scalars(
                select(ConfidenceChange).where(
                    ConfidenceChange.created_by_task_id == task.id,
                    ConfidenceChange.team_id == task.team_id,
                )
            )
        ],
    }
    for field, values in row_fields.items():
        marker_values = payload.get(field)
        if (
            not isinstance(marker_values, list)
            or not all(isinstance(value, str) for value in marker_values)
            or len(marker_values) != len(set(marker_values))
            or set(marker_values) != set(values)
        ):
            raise WorldMemoryError("update_thread_committed_rows_mismatch")
    for proposal in envelope.proposals:
        if proposal.key not in accepted:
            continue
        domain_event = domain_by_key[proposal.key][0]
        if isinstance(proposal, HypothesisCreateProposal):
            hypothesis = session.get(Hypothesis, proposal.hypothesis_id)
            if (
                hypothesis is None
                or hypothesis.team_id != task.team_id
                or hypothesis.thread_id != envelope.thread_id
                or hypothesis.confidence != "low"
                or hypothesis.statement != proposal.statement.strip()
            ):
                raise WorldMemoryError("update_thread_created_hypothesis_invalid")
        elif isinstance(proposal, EvidenceLinkProposal):
            evidence_id = domain_event.payload.get("evidence_link_id")
            try:
                link = session.get(EvidenceLink, UUID(evidence_id))
            except (TypeError, ValueError) as error:
                raise WorldMemoryError(
                    "update_thread_evidence_link_invalid"
                ) from error
            if (
                link is None
                or link.originating_task_id != task.id
                or link.team_id != task.team_id
                or link.subject_kind != "hypothesis"
                or link.hypothesis_id != proposal.hypothesis_id
            ):
                raise WorldMemoryError("update_thread_evidence_link_invalid")
            team = session.get(Team, task.team_id)
            if team is None:
                raise WorldMemoryError("update_thread_team_missing")
            try:
                source_ref, source_hash, signal_id, outcome_id = (
                    _snapshot_for_source(session, team, proposal)
                )
                _verify_snapshot(
                    snapshot_store,
                    source_ref,
                    source_hash,
                    proposal.quote_text,
                    proposal.quote_start,
                    proposal.quote_end,
                )
            except WorldMemoryError:
                raise
            expected_reference_key = _sha256_json(
                {
                    "source_kind": proposal.source_kind,
                    "outcome_id": str(outcome_id) if outcome_id else None,
                    "signal_id": str(signal_id) if signal_id else None,
                    "snapshot_ref": source_ref,
                    "snapshot_hash": source_hash,
                    "stance": proposal.stance,
                    "quote_text": proposal.quote_text,
                    "quote_start": proposal.quote_start,
                    "quote_end": proposal.quote_end,
                }
            )
            if (
                link.source_kind != proposal.source_kind
                or link.signal_id != signal_id
                or link.outcome_id != outcome_id
                or link.snapshot_ref != source_ref
                or link.snapshot_hash != source_hash
                or link.stance != proposal.stance
                or link.quote_text != proposal.quote_text
                or link.quote_start != proposal.quote_start
                or link.quote_end != proposal.quote_end
                or link.reference_key != expected_reference_key
            ):
                raise WorldMemoryError("update_thread_evidence_link_invalid")
        elif isinstance(proposal, ConfidenceChangeProposal):
            change_id = domain_event.payload.get("confidence_change_id")
            try:
                change = session.get(ConfidenceChange, UUID(change_id))
            except (TypeError, ValueError) as error:
                raise WorldMemoryError(
                    "update_thread_confidence_change_invalid"
                ) from error
            if (
                change is None
                or change.created_by_task_id != task.id
                or change.team_id != task.team_id
                or change.hypothesis_id != proposal.hypothesis_id
                or change.evidence_link_id != proposal.evidence_link_id
                or change.cause_kind != "evidence"
                or change.to_confidence != proposal.to_confidence
                or change.from_confidence == change.to_confidence
                or domain_event.payload.get("confidence_change_id")
                != str(change.id)
                or domain_event.payload.get("from_confidence")
                != change.from_confidence
                or domain_event.payload.get("to_confidence")
                != change.to_confidence
            ):
                raise WorldMemoryError("update_thread_confidence_change_invalid")
            cause = session.get(EvidenceLink, change.evidence_link_id)
            if (
                cause is None
                or cause.subject_kind != "hypothesis"
                or cause.hypothesis_id != change.hypothesis_id
                or cause.team_id != task.team_id
                or cause.stance not in {"supports", "challenges"}
            ):
                raise WorldMemoryError("update_thread_confidence_cause_invalid")
        else:
            hypothesis = session.get(Hypothesis, proposal.hypothesis_id)
            expected_status = (
                "rejected" if proposal.action == "reject" else "superseded"
            )
            if (
                hypothesis is None
                or hypothesis.team_id != task.team_id
                or hypothesis.thread_id != envelope.thread_id
                or hypothesis.status != expected_status
                or domain_event.payload.get("hypothesis_id")
                != str(proposal.hypothesis_id)
                or domain_event.payload.get("reason") != proposal.reason.strip()
                or (
                    proposal.action == "supersede"
                    and domain_event.payload.get("successor_hypothesis_id")
                    != str(proposal.successor_hypothesis_id)
                )
                or (
                    proposal.action == "reject"
                    and "successor_hypothesis_id" in domain_event.payload
                )
            ):
                raise WorldMemoryError("update_thread_transition_invalid")

    return WorldMemoryCommitResult(
        task_id=task.id,
        status="committed",
        committed_count=len(accepted),
        rejected_count=len(rejected),
        committed_at=marker.created_at,
        request_fingerprint=envelope.proposal_fingerprint,
        replayed=True,
        committed_proposal_keys=tuple(accepted),
        rejected_proposal_keys=tuple(rejected),
    )


def validate_model_update_thread_terminal(
    session: Session,
    task: Task,
    observation: TerminalObservation,
    snapshot_store: SnapshotStore,
) -> None:
    from pydantic import ValidationError

    from core.update_thread import (
        GENERATION_RECEIPT_EVENT_TYPE,
        PROPOSALS_EVENT_TYPE,
        UpdateThreadTaskError,
        validate_update_thread_task_request,
    )
    from core.update_thread_worker import _parse_model_response

    attempt = observation.attempt
    if task.attempt_count != attempt:
        raise WorldMemoryError("update_thread_terminal_attempt_mismatch")
    markers = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type.in_(
                    (
                        MODEL_COMMITTED_EVENT_TYPE,
                        MODEL_REJECTED_EVENT_TYPE,
                        MODEL_INCONSISTENT_EVENT_TYPE,
                    )
                ),
            )
        )
    )
    inconsistent_markers = [
        marker
        for marker in markers
        if marker.type == MODEL_INCONSISTENT_EVENT_TYPE
    ]
    if len(inconsistent_markers) > 1:
        raise WorldMemoryError("update_thread_recovery_marker_duplicate")
    if inconsistent_markers:
        marker = inconsistent_markers[0]
        WorldMemoryCommitService._validate_inconsistent_marker(
            task, attempt, marker
        )
        if (
            observation.result_category != "terminal_failure"
            or observation.failure_reason
            != "update_thread_recovery_inconsistent"
            or observation.observed_at != marker.created_at
        ):
            raise WorldMemoryError("update_thread_inconsistent_result_invalid")
        WorldMemoryCommitService._assert_model_empty_set_has_no_writes(
            session, task
        )
        return
    try:
        validate_update_thread_task_request(session, task)
    except UpdateThreadTaskError as error:
        raise WorldMemoryError(error.reason) from error

    proposal_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == PROPOSALS_EVENT_TYPE,
            )
        )
    )
    current_proposals: list[Event] = []
    for event in proposal_events:
        if not isinstance(event.payload, dict) or type(
            event.payload.get("attempt")
        ) is not int:
            raise WorldMemoryError("update_thread_proposals_event_corrupt")
        if event.payload["attempt"] > attempt:
            raise WorldMemoryError("update_thread_proposals_event_future_attempt")
        if event.payload["attempt"] == attempt:
            current_proposals.append(event)
    if len(current_proposals) > 1:
        raise WorldMemoryError("update_thread_proposals_event_duplicate")

    if observation.result_category == "success_update_thread_committed":
        if len(markers) != 1 or markers[0].type != MODEL_COMMITTED_EVENT_TYPE:
            raise WorldMemoryError("update_thread_commit_marker_missing")
        envelope = load_model_update_thread_envelope(
            session, task, attempt, snapshot_store
        )
        result = validate_model_update_thread_marker(
            session, task, envelope, markers[0], snapshot_store
        )
        if (
            result.status != "committed"
            or result.committed_count < 1
            or result.committed_at != observation.observed_at
        ):
            raise WorldMemoryError("update_thread_committed_result_invalid")
        return

    if observation.result_category != "terminal_failure":
        raise WorldMemoryError("update_thread_result_category_invalid")
    if len(markers) > 1:
        raise WorldMemoryError("update_thread_commit_marker_count_invalid")

    if not current_proposals:
        if markers:
            raise WorldMemoryError("update_thread_terminal_marker_without_proposals")
        receipts = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == GENERATION_RECEIPT_EVENT_TYPE,
                )
            )
        )
        if not receipts:
            charges = list(
                session.scalars(
                    select(TaskGenerationCharge).where(
                        TaskGenerationCharge.task_id == task.id,
                        TaskGenerationCharge.attempt_count == attempt,
                        TaskGenerationCharge.operation == "update_thread",
                    )
                )
            )
            if any(charge.status == "reserved" for charge in charges):
                raise WorldMemoryError(
                    "update_thread_reserved_charge_not_unknown"
                )
            WorldMemoryCommitService._assert_model_empty_set_has_no_writes(
                session, task
            )
            return
        _, _, receipt_event, charge = _verified_model_receipt(
            session,
            task,
            attempt,
            snapshot_store,
            allow_overrun=True,
        )
        if charge.status == "overrun":
            if observation.failure_reason != "generation_cost_overrun":
                raise WorldMemoryError(
                    "update_thread_generation_overrun_result_invalid"
                )
            WorldMemoryCommitService._assert_model_empty_set_has_no_writes(
                session, task
            )
            return
        try:
            receipt = receipt_event.payload
            _parse_model_response(receipt["raw_completion_text"])
        except (ValidationError, ValueError, TypeError):
            if observation.failure_reason == "update_thread_model_output_invalid":
                WorldMemoryCommitService._assert_model_empty_set_has_no_writes(
                    session, task
                )
                return
            raise WorldMemoryError("update_thread_parser_failure_result_invalid")
        raise WorldMemoryError("update_thread_proposal_set_remains_resumable")

    envelope = load_model_update_thread_envelope(
        session, task, attempt, snapshot_store
    )
    if not envelope.proposals:
        raise WorldMemoryError("update_thread_empty_set_cannot_fail")
    if len(markers) != 1 or markers[0].type != MODEL_REJECTED_EVENT_TYPE:
        raise WorldMemoryError("update_thread_nonempty_failure_marker_required")
    result = validate_model_update_thread_marker(
        session, task, envelope, markers[0], snapshot_store
    )
    if (
        result.status != "rejected"
        or observation.failure_reason != "all_update_thread_proposals_rejected"
        or observation.observed_at != result.committed_at
    ):
        raise WorldMemoryError("update_thread_rejection_result_invalid")


class WorldMemoryCommitService:
    """Validate and commit one complete trusted proposal set atomically."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store

    def commit_model(self, task_id: UUID, attempt: int) -> WorldMemoryCommitResult:
        with self._session_factory.begin() as session:
            task = session.scalar(
                select(Task).where(Task.id == task_id).with_for_update()
            )
            if task is None:
                raise WorldMemoryError("update_thread_task_missing")
            envelope = load_model_update_thread_envelope(
                session, task, attempt, self._snapshot_store
            )
            return self.commit(
                task_id,
                attempt,
                None,
                session=session,
                locked_task=task,
                model_envelope=envelope,
            )

    def commit_model_in_session(
        self,
        session: Session,
        task: Task,
        attempt: int,
        envelope: ModelUpdateThreadEnvelope | None = None,
    ) -> WorldMemoryCommitResult:
        if envelope is None:
            envelope = load_model_update_thread_envelope(
                session, task, attempt, self._snapshot_store
            )
        return self.commit(
            task.id,
            attempt,
            None,
            session=session,
            locked_task=task,
            model_envelope=envelope,
        )

    def commit(
        self,
        task_id: UUID,
        attempt: int,
        operator_id: str | None,
        *,
        session: Session | None = None,
        locked_task: Task | None = None,
        model_envelope: ModelUpdateThreadEnvelope | None = None,
    ) -> WorldMemoryCommitResult:
        scope = (
            self._session_factory.begin()
            if session is None
            else nullcontext(session)
        )
        with scope as active_session:
            session = active_session
            if session is None:
                raise WorldMemoryError("world_memory_session_required")
            task = locked_task or session.scalar(
                select(Task).where(Task.id == task_id).with_for_update()
            )
            if (
                task is None
                or task.status != "running"
                or task.attempt_count != attempt
            ):
                raise WorldMemoryError(
                    "operator_update_task_not_running"
                    if operator_id is not None
                    else "update_thread_task_not_running"
                )
            if task.id != task_id:
                raise WorldMemoryError("world_memory_task_identity_mismatch")

            operator_envelope: OperatorUpdateEnvelope | None = None
            if operator_id is not None:
                if model_envelope is not None:
                    raise WorldMemoryError("world_memory_actor_envelope_conflict")
                operator_envelope = validate_operator_update_task_request(
                    session, task
                )
                if operator_envelope.operator_id != operator_id:
                    raise WorldMemoryError("operator_update_principal_mismatch")
                actor: WorldMemoryActor = OperatorActor(operator_id=operator_id)
                commit_context = _ProposalCommitContext(
                    thread_id=operator_envelope.request.thread_id,
                    proposals=tuple(operator_envelope.request.proposals),
                    request_fingerprint=operator_envelope.request_fingerprint,
                )
                prior = self._existing_result(
                    session, task, operator_envelope
                )
            else:
                if model_envelope is None:
                    raise WorldMemoryError("model_update_thread_envelope_required")
                commit_context = validate_model_update_thread_envelope(
                    session, task, attempt, model_envelope, self._snapshot_store
                )
                actor = ModelWorkerActor(
                    actor_type="model_worker",
                    task_id=task.id,
                    request_event_id=model_envelope.request_event_id,
                )
                prior = self._existing_model_result(
                    session, task, commit_context, actor
                )
            if prior is not None:
                return prior

            envelope = commit_context
            proposals = commit_context.proposals
            team = session.scalar(
                select(Team)
                .where(Team.id == task.team_id)
                .with_for_update()
            )
            thread = session.scalar(
                select(Thread)
                .where(
                    Thread.id == commit_context.thread_id,
                    Thread.team_id == task.team_id,
                )
                .with_for_update()
            )
            if team is None or team.status != "active":
                return _record_rejected_for_actor(
                    session,
                    task,
                    commit_context,
                    actor,
                    attempt,
                    {
                        proposal.key: (
                            "operator_update_team_not_active"
                            if isinstance(actor, OperatorActor)
                            else "update_thread_team_not_active"
                        )
                        for proposal in proposals
                    },
                    operator_envelope=operator_envelope,
                )
            if thread is None or thread.status == "resolved":
                return _record_rejected_for_actor(
                    session,
                    task,
                    commit_context,
                    actor,
                    attempt,
                    {
                        proposal.key: (
                            "operator_update_thread_not_available"
                            if isinstance(actor, OperatorActor)
                            else "update_thread_target_not_available"
                        )
                        for proposal in proposals
                    },
                    operator_envelope=operator_envelope,
                )

            rejected: dict[str, str] = {}
            valid_creates: dict[UUID, HypothesisCreateProposal] = {}
            for proposal in proposals:
                if not isinstance(proposal, HypothesisCreateProposal):
                    continue
                if proposal.confidence != "low":
                    rejected[proposal.key] = "initial_hypothesis_confidence_must_be_low"
                elif session.get(Hypothesis, proposal.hypothesis_id) is not None:
                    rejected[proposal.key] = "hypothesis_id_already_exists"
                elif proposal.hypothesis_id in valid_creates:
                    rejected[proposal.key] = "duplicate_hypothesis_id"
                else:
                    valid_creates[proposal.hypothesis_id] = proposal

            existing_hypothesis_ids = {
                hypothesis_id
                for proposal in proposals
                for hypothesis_id in (
                    getattr(proposal, "hypothesis_id", None),
                    getattr(proposal, "successor_hypothesis_id", None),
                )
                if hypothesis_id is not None
            }
            locked_hypotheses = {
                item.id: item
                for item in session.scalars(
                    select(Hypothesis)
                    .where(
                        Hypothesis.id.in_(existing_hypothesis_ids or {UUID(int=0)}),
                        Hypothesis.team_id == task.team_id,
                    )
                    .order_by(Hypothesis.id)
                    .with_for_update()
                )
            }

            valid_evidence: dict[str, tuple[EvidenceLink, str]] = {}
            evidence_reference_keys: set[tuple[UUID, str]] = set()
            for proposal in proposals:
                if not isinstance(proposal, EvidenceLinkProposal):
                    continue
                hypothesis = locked_hypotheses.get(proposal.hypothesis_id)
                if hypothesis is None and proposal.hypothesis_id not in valid_creates:
                    rejected[proposal.key] = (
                        "evidence_hypothesis_not_owned_by_task_thread"
                    )
                    continue
                if (
                    hypothesis is not None
                    and hypothesis.thread_id != envelope.request.thread_id
                ):
                    rejected[proposal.key] = "evidence_hypothesis_not_in_task_thread"
                    continue
                try:
                    snapshot_ref, snapshot_hash, signal_id, outcome_id = (
                        _snapshot_for_source(session, team, proposal)
                    )
                    _verify_snapshot(
                        self._snapshot_store,
                        snapshot_ref,
                        snapshot_hash,
                        proposal.quote_text,
                        proposal.quote_start,
                        proposal.quote_end,
                    )
                except WorldMemoryError as error:
                    rejected[proposal.key] = error.reason
                    continue
                normalized: dict[str, object] = {
                    "source_kind": proposal.source_kind,
                    "outcome_id": str(outcome_id) if outcome_id else None,
                    "signal_id": str(signal_id) if signal_id else None,
                    "snapshot_ref": snapshot_ref,
                    "snapshot_hash": snapshot_hash,
                    "stance": proposal.stance,
                    "quote_text": proposal.quote_text,
                    "quote_start": proposal.quote_start,
                    "quote_end": proposal.quote_end,
                }
                reference_key = _sha256_json(normalized)
                identity = (proposal.hypothesis_id, reference_key)
                if identity in evidence_reference_keys:
                    rejected[proposal.key] = "duplicate_evidence_reference_in_request"
                    continue
                evidence_reference_keys.add(identity)
                prior_link = session.scalar(
                    select(EvidenceLink.id).where(
                        EvidenceLink.subject_kind == "hypothesis",
                        EvidenceLink.hypothesis_id == proposal.hypothesis_id,
                        EvidenceLink.team_id == task.team_id,
                        EvidenceLink.reference_key == reference_key,
                    )
                )
                if prior_link is not None:
                    rejected[proposal.key] = "evidence_link_already_exists"
                    continue
                link = EvidenceLink(
                    id=uuid4(),
                    team_id=task.team_id,
                    subject_kind="hypothesis",
                    hypothesis_id=proposal.hypothesis_id,
                    originating_task_id=task.id,
                    source_kind=proposal.source_kind,
                    signal_id=signal_id,
                    outcome_id=outcome_id,
                    snapshot_ref=snapshot_ref,
                    snapshot_hash=snapshot_hash,
                    stance=proposal.stance,
                    quote_text=proposal.quote_text,
                    quote_start=proposal.quote_start,
                    quote_end=proposal.quote_end,
                    reference_key=reference_key,
                )
                valid_evidence[proposal.key] = (link, reference_key)

            valid_confidence: list[
                tuple[ConfidenceChangeProposal, Hypothesis, EvidenceLink, str]
            ] = []
            current_bands = {
                item.id: item.confidence for item in locked_hypotheses.values()
            }
            for proposal in proposals:
                if not isinstance(proposal, ConfidenceChangeProposal):
                    continue
                hypothesis = locked_hypotheses.get(proposal.hypothesis_id)
                if (
                    hypothesis is None
                    or hypothesis.thread_id != envelope.request.thread_id
                ):
                    rejected[proposal.key] = (
                        "confidence_hypothesis_not_owned_by_task_thread"
                    )
                    continue
                if hypothesis.status != "active":
                    rejected[proposal.key] = "hypothesis_not_active"
                    continue
                evidence = session.scalar(
                    select(EvidenceLink).where(
                        EvidenceLink.id == proposal.evidence_link_id,
                        EvidenceLink.subject_kind == "hypothesis",
                        EvidenceLink.hypothesis_id == hypothesis.id,
                        EvidenceLink.team_id == task.team_id,
                    )
                )
                if evidence is None:
                    rejected[proposal.key] = "confidence_evidence_not_for_hypothesis"
                    continue
                if evidence.stance == "mentions":
                    rejected[proposal.key] = (
                        "mentions_evidence_cannot_change_confidence"
                    )
                    continue
                if evidence.stance not in {"supports", "challenges"}:
                    rejected[proposal.key] = "confidence_evidence_stance_invalid"
                    continue
                from_band = current_bands[hypothesis.id]
                if from_band == proposal.to_confidence:
                    rejected[proposal.key] = "confidence_change_must_change_band"
                    continue
                valid_confidence.append((proposal, hypothesis, evidence, from_band))
                current_bands[hypothesis.id] = proposal.to_confidence

            valid_transitions: list[
                tuple[HypothesisTransitionProposal, Hypothesis, Hypothesis | None]
            ] = []
            transitioned: set[UUID] = set()
            for proposal in proposals:
                if not isinstance(proposal, HypothesisTransitionProposal):
                    continue
                hypothesis = locked_hypotheses.get(proposal.hypothesis_id)
                if (
                    hypothesis is None
                    or hypothesis.thread_id != envelope.request.thread_id
                    or hypothesis.status != "active"
                    or hypothesis.id in transitioned
                ):
                    rejected[proposal.key] = "hypothesis_transition_precondition_failed"
                    continue
                successor = None
                if proposal.action == "supersede":
                    successor_id = proposal.successor_hypothesis_id
                    if successor_id is None:
                        rejected[proposal.key] = "hypothesis_successor_required"
                        continue
                    successor = locked_hypotheses.get(successor_id)
                    if successor is None:
                        successor_create = valid_creates.get(successor_id)
                        if successor_create is None:
                            rejected[proposal.key] = (
                                "hypothesis_successor_not_owned_by_team"
                            )
                            continue
                    elif successor.thread_id != envelope.request.thread_id:
                        rejected[proposal.key] = (
                            "hypothesis_successor_not_in_task_thread"
                        )
                        continue
                    elif successor.status != "active":
                        rejected[proposal.key] = "hypothesis_successor_not_active"
                        continue
                    if successor_id == proposal.hypothesis_id:
                        rejected[proposal.key] = "hypothesis_cannot_supersede_itself"
                        continue
                valid_transitions.append((proposal, hypothesis, successor))
                transitioned.add(hypothesis.id)

            valid_proposal_keys: set[str] = set()
            valid_proposal_keys.update(
                proposal.key
                for proposal in proposals
                if isinstance(proposal, HypothesisCreateProposal)
                and proposal.hypothesis_id in valid_creates
                and proposal.key not in rejected
            )
            valid_proposal_keys.update(valid_evidence)
            valid_proposal_keys.update(item[0].key for item in valid_confidence)
            valid_proposal_keys.update(item[0].key for item in valid_transitions)
            rejected_keys = [
                proposal.key for proposal in proposals if proposal.key in rejected
            ]
            committed_keys = [
                proposal.key
                for proposal in proposals
                if proposal.key in valid_proposal_keys
            ]
            committed_at = datetime.now(timezone.utc)

            if not valid_proposal_keys:
                return _record_rejected_for_actor(
                    session,
                    task,
                    commit_context,
                    actor,
                    attempt,
                    rejected,
                    operator_envelope=operator_envelope,
                )

            for proposal in proposals:
                if proposal.key in rejected:
                    if isinstance(actor, ModelWorkerActor):
                        session.add(
                            Event(
                                id=uuid4(),
                                task_id=task.id,
                                type="update_thread_proposal_rejected",
                                payload={
                                    "schema_version": 1,
                                    "task_id": str(task.id),
                                    "team_id": str(task.team_id),
                                    "thread_id": str(commit_context.thread_id),
                                    "attempt": attempt,
                                    "actor_type": actor.actor_type,
                                    "proposal_key": proposal.key,
                                    "proposal_fingerprint": (
                                        commit_context.request_fingerprint
                                    ),
                                    "reason": rejected[proposal.key],
                                },
                                created_at=committed_at,
                            )
                        )
                        continue
                    session.add(
                        Event(
                            id=uuid4(),
                            task_id=task.id,
                            type="proposal_rejected",
                            payload={
                                "task_id": str(task.id),
                                "team_id": str(task.team_id),
                                **_actor_provenance_fields(
                                    actor, commit_context.request_fingerprint
                                ),
                                "proposal_key": proposal.key,
                                "reason": rejected[proposal.key],
                            },
                            created_at=committed_at,
                        )
                    )

            created_hypothesis_ids: list[str] = []
            evidence_link_ids: list[str] = []
            confidence_change_ids: list[str] = []
            for proposal in proposals:
                if (
                    isinstance(proposal, HypothesisCreateProposal)
                    and proposal.key in valid_proposal_keys
                ):
                    session.add(
                        Hypothesis(
                            id=proposal.hypothesis_id,
                            team_id=task.team_id,
                            thread_id=commit_context.thread_id,
                            statement=proposal.statement.strip(),
                            status="active",
                            confidence="low",
                            created_at=committed_at,
                            last_touched_at=committed_at,
                        )
                    )
                    created_hypothesis_ids.append(str(proposal.hypothesis_id))
                    session.add(
                        Event(
                            id=uuid4(),
                            task_id=task.id,
                            type="hypothesis_created",
                            payload={
                                "task_id": str(task.id),
                                "team_id": str(task.team_id),
                                **_actor_provenance_fields(
                                    actor, commit_context.request_fingerprint
                                ),
                                "proposal_key": proposal.key,
                                "hypothesis_id": str(proposal.hypothesis_id),
                                "thread_id": str(commit_context.thread_id),
                                "confidence": "low",
                            },
                            created_at=committed_at,
                        )
                    )

            if created_hypothesis_ids:
                session.flush()

            touched_hypothesis_ids: set[UUID] = set()
            for proposal in proposals:
                if proposal.key not in valid_evidence:
                    continue
                link, _ = valid_evidence[proposal.key]
                session.add(link)
                evidence_link_ids.append(str(link.id))
                if link.stance in {"supports", "challenges"}:
                    if link.hypothesis_id is not None:
                        touched_hypothesis_ids.add(link.hypothesis_id)
                session.add(
                    Event(
                        id=uuid4(),
                        task_id=task.id,
                        type="evidence_link_added",
                        payload={
                            "task_id": str(task.id),
                            "team_id": str(task.team_id),
                            **_actor_provenance_fields(
                                actor, commit_context.request_fingerprint
                            ),
                            "proposal_key": proposal.key,
                            "evidence_link_id": str(link.id),
                            "hypothesis_id": str(link.hypothesis_id),
                            "source_kind": link.source_kind,
                            "stance": link.stance,
                            "reference_key": link.reference_key,
                        },
                        created_at=committed_at,
                    )
                )

            for proposal, hypothesis, evidence, from_band in valid_confidence:
                if proposal.key not in valid_proposal_keys:
                    continue
                change = ConfidenceChange(
                    id=uuid4(),
                    team_id=task.team_id,
                    hypothesis_id=hypothesis.id,
                    from_confidence=from_band,
                    to_confidence=proposal.to_confidence,
                    cause_kind="evidence",
                    evidence_link_id=evidence.id,
                    created_by_task_id=task.id,
                    idempotency_key=proposal.key,
                    created_at=committed_at,
                )
                session.add(change)
                confidence_change_ids.append(str(change.id))
                hypothesis.confidence = proposal.to_confidence
                session.add(
                    Event(
                        id=uuid4(),
                        task_id=task.id,
                        type="confidence_changed",
                        payload={
                            "task_id": str(task.id),
                            "team_id": str(task.team_id),
                            **_actor_provenance_fields(
                                actor, commit_context.request_fingerprint
                            ),
                            "proposal_key": proposal.key,
                            "hypothesis_id": str(hypothesis.id),
                            "confidence_change_id": str(change.id),
                            "evidence_link_id": str(evidence.id),
                            "from_confidence": from_band,
                            "to_confidence": proposal.to_confidence,
                        },
                        created_at=committed_at,
                    )
                )

            for proposal, hypothesis, successor in valid_transitions:
                if proposal.key not in valid_proposal_keys:
                    continue
                hypothesis.status = (
                    "rejected" if proposal.action == "reject" else "superseded"
                )
                event_type = (
                    "hypothesis_rejected"
                    if proposal.action == "reject"
                    else "hypothesis_superseded"
                )
                payload: dict[str, object] = {
                    "task_id": str(task.id),
                    "team_id": str(task.team_id),
                    **_actor_provenance_fields(
                        actor, commit_context.request_fingerprint
                    ),
                    "proposal_key": proposal.key,
                    "hypothesis_id": str(hypothesis.id),
                    "reason": proposal.reason.strip(),
                }
                if successor is not None:
                    payload["successor_hypothesis_id"] = str(
                        proposal.successor_hypothesis_id
                    )
                session.add(
                    Event(
                        id=uuid4(),
                        task_id=task.id,
                        type=event_type,
                        payload=payload,
                        created_at=committed_at,
                    )
                )

            if isinstance(actor, ModelWorkerActor):
                for key in committed_keys:
                    session.add(
                        Event(
                            id=uuid4(),
                            task_id=task.id,
                            type="update_thread_proposal_accepted",
                            payload={
                                "schema_version": 1,
                                "task_id": str(task.id),
                                "team_id": str(task.team_id),
                                "thread_id": str(commit_context.thread_id),
                                "attempt": attempt,
                                "actor_type": actor.actor_type,
                                "proposal_key": key,
                                "proposal_fingerprint": (
                                    commit_context.request_fingerprint
                                ),
                                "disposition": "accepted",
                            },
                            created_at=committed_at,
                        )
                    )

            for hypothesis_id in touched_hypothesis_ids:
                hypothesis = locked_hypotheses.get(hypothesis_id) or session.get(
                    Hypothesis, hypothesis_id
                )
                if hypothesis is None:
                    raise WorldMemoryError("operator_update_touched_hypothesis_missing")
                hypothesis.last_touched_at = committed_at

            if isinstance(actor, OperatorActor):
                marker_type = COMMITTED_EVENT_TYPE
                marker_payload: dict[str, object] = {
                    "schema_version": 1,
                    "task_id": str(task.id),
                    "team_id": str(task.team_id),
                    "thread_id": str(commit_context.thread_id),
                    "attempt_count": attempt,
                    "operator_id": actor.operator_id,
                    "request_fingerprint": commit_context.request_fingerprint,
                    "committed_proposal_keys": committed_keys,
                    "rejected_proposal_keys": rejected_keys,
                    "hypothesis_ids": created_hypothesis_ids,
                    "evidence_link_ids": evidence_link_ids,
                    "confidence_change_ids": confidence_change_ids,
                }
            else:
                binding = commit_context.model_envelope
                if binding is None:
                    raise WorldMemoryError(
                        "update_thread_commit_envelope_missing"
                    )
                marker_type = "update_thread_committed"
                marker_payload = {
                    "schema_version": 1,
                    "task_id": str(task.id),
                    "team_id": str(task.team_id),
                    "thread_id": str(commit_context.thread_id),
                    "attempt": attempt,
                    "actor_type": actor.actor_type,
                    "request_event_id": str(binding.request_event_id),
                    "generation_receipt_event_id": str(binding.receipt_event_id),
                    "proposal_event_id": str(binding.proposal_event_id),
                    "charge_id": str(binding.charge_id),
                    "context_event_id": str(binding.context_event_id),
                    "context_snapshot_ref": binding.context_snapshot_ref,
                    "context_content_hash": binding.context_content_hash,
                    "proposal_fingerprint": commit_context.request_fingerprint,
                    "accepted_proposal_keys": committed_keys,
                    "rejected_proposal_keys": rejected_keys,
                    "hypothesis_ids": created_hypothesis_ids,
                    "evidence_link_ids": evidence_link_ids,
                    "confidence_change_ids": confidence_change_ids,
                }
            marker = Event(
                id=uuid4(),
                task_id=task.id,
                type=marker_type,
                payload=marker_payload,
                created_at=committed_at,
            )
            session.add(marker)
            session.flush()
            return WorldMemoryCommitResult(
                task_id=task.id,
                status="committed",
                committed_count=len(valid_proposal_keys),
                rejected_count=len(rejected_keys),
                committed_at=committed_at,
                request_fingerprint=commit_context.request_fingerprint,
                committed_proposal_keys=tuple(committed_keys),
                rejected_proposal_keys=tuple(rejected_keys),
            )

    def resume_update_thread_in_session(
        self, session: Session, task: Task, attempt: int
    ) -> TerminalObservation | None:
        """Resume one admitted Task attempt without opening or closing a Session."""
        from pydantic import ValidationError

        from core.generation_cost import TaskGenerationCostService
        from core.task_runtime import TerminalObservation
        from core.update_thread import (
            GENERATION_RECEIPT_EVENT_TYPE,
            PROPOSALS_EVENT_TYPE,
            TASK_TYPE,
            UpdateThreadTaskError,
            load_pinned_policy,
            validate_update_thread_task_request,
        )
        from core.update_thread_context import UpdateThreadContextError
        from core.update_thread_worker import (
            _fingerprint,
            _parse_model_response,
        )

        try:
            if (
                task.task_type != TASK_TYPE
                or task.status != "running"
                or type(attempt) is not int
                or task.attempt_count != attempt
            ):
                raise WorldMemoryError("update_thread_task_attempt_not_current")
            request = validate_update_thread_task_request(session, task)
            load_pinned_policy(session, task.team_id, task.policy_version)

            marker_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type.in_(
                            (
                                MODEL_COMMITTED_EVENT_TYPE,
                                MODEL_REJECTED_EVENT_TYPE,
                                MODEL_INCONSISTENT_EVENT_TYPE,
                            )
                        ),
                    )
                )
            )
            inconsistent_markers = [
                marker
                for marker in marker_events
                if marker.type == MODEL_INCONSISTENT_EVENT_TYPE
            ]
            if inconsistent_markers:
                if len(inconsistent_markers) != 1:
                    raise WorldMemoryError(
                        "update_thread_recovery_marker_duplicate"
                    )
                marker = inconsistent_markers[0]
                self._validate_inconsistent_marker(task, attempt, marker)
                return TerminalObservation(
                    task_id=task.id,
                    attempt=attempt,
                    result_category="terminal_failure",
                    observed_at=marker.created_at,
                    failure_reason="update_thread_recovery_inconsistent",
                )
            if len(marker_events) > 1:
                raise WorldMemoryError(
                    "update_thread_commit_marker_count_invalid"
                )
            if marker_events:
                marker = marker_events[0]
                envelope = load_model_update_thread_envelope(
                    session, task, attempt, self._snapshot_store
                )
                result = validate_model_update_thread_marker(
                    session, task, envelope, marker, self._snapshot_store
                )
                return self._model_observation(task, attempt, result)

            receipt_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == GENERATION_RECEIPT_EVENT_TYPE,
                    )
                )
            )
            current_receipts = []
            for event in receipt_events:
                if not isinstance(event.payload, dict) or type(
                    event.payload.get("attempt")
                ) is not int:
                    raise WorldMemoryError(
                        "update_thread_generation_receipt_corrupt"
                    )
                if event.payload["attempt"] > attempt:
                    raise WorldMemoryError(
                        "update_thread_generation_receipt_future_attempt"
                    )
                if event.payload["attempt"] == attempt:
                    current_receipts.append(event)

            charges = list(
                session.scalars(
                    select(TaskGenerationCharge)
                    .where(
                        TaskGenerationCharge.task_id == task.id,
                        TaskGenerationCharge.attempt_count == attempt,
                        TaskGenerationCharge.operation == TASK_TYPE,
                    )
                    .with_for_update()
                )
            )
            if not current_receipts:
                if len(charges) > 1:
                    raise WorldMemoryError(
                        "update_thread_generation_charge_duplicate"
                    )
                if charges:
                    charge = charges[0]
                    if charge.status == "reserved":
                        TaskGenerationCostService(
                            self._session_factory
                        ).mark_unknown_in_session(
                            session, task, charge, "provider_call_interrupted"
                        )
                    elif charge.status != "unknown":
                        raise WorldMemoryError(
                            "update_thread_receipt_missing_for_settled_charge"
                        )
                return None
            if len(current_receipts) != 1 or len(charges) != 1:
                raise WorldMemoryError(
                    "update_thread_receipt_charge_cardinality_invalid"
                )

            request, verified_context, receipt_event, charge = (
                _verified_model_receipt(
                    session, task, attempt, self._snapshot_store
                )
            )
            receipt = receipt_event.payload

            existing_proposals = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == PROPOSALS_EVENT_TYPE,
                    )
                )
            )
            current_proposals: list[Event] = []
            for event in existing_proposals:
                if not isinstance(event.payload, dict) or type(
                    event.payload.get("attempt")
                ) is not int:
                    raise WorldMemoryError(
                        "update_thread_proposals_event_corrupt"
                    )
                if event.payload["attempt"] > attempt:
                    raise WorldMemoryError(
                        "update_thread_proposals_event_future_attempt"
                    )
                if event.payload["attempt"] == attempt:
                    current_proposals.append(event)
            if len(current_proposals) > 1:
                raise WorldMemoryError(
                    "update_thread_proposals_event_duplicate"
                )
            if not current_proposals:
                try:
                    parsed = _parse_model_response(
                        receipt["raw_completion_text"]
                    )
                except (ValidationError, ValueError, TypeError):
                    return TerminalObservation(
                        task_id=task.id,
                        attempt=attempt,
                        result_category="terminal_failure",
                        observed_at=receipt_event.created_at,
                        failure_reason="update_thread_model_output_invalid",
                    )
                proposals = [
                    proposal.model_dump(mode="json")
                    for proposal in parsed.proposals
                ]
                fingerprint = _fingerprint(
                    task_id=task.id,
                    team_id=task.team_id,
                    thread_id=request.thread_id,
                    attempt=attempt,
                    policy_version=task.policy_version,
                    receipt_event_id=receipt_event.id,
                    context=verified_context,
                    charge_id=charge.id,
                    proposals=proposals,
                )
                proposal_event = Event(
                    id=uuid4(),
                    task_id=task.id,
                    type=PROPOSALS_EVENT_TYPE,
                    payload={
                        "schema_version": 1,
                        "task_id": str(task.id),
                        "team_id": str(task.team_id),
                        "thread_id": str(request.thread_id),
                        "attempt": attempt,
                        "policy_version": task.policy_version,
                        "generation_receipt_event_id": str(receipt_event.id),
                        "context_event_id": str(verified_context.event_id),
                        "context_snapshot_ref": verified_context.snapshot_ref,
                        "context_content_hash": verified_context.content_hash,
                        "charge_id": str(charge.id),
                        "proposal_fingerprint": fingerprint,
                        "proposals": proposals,
                    },
                    created_at=datetime.now(timezone.utc),
                )
                session.add(proposal_event)
                session.flush()
            envelope = load_model_update_thread_envelope(
                session, task, attempt, self._snapshot_store
            )
            if not envelope.proposals:
                self._assert_model_empty_set_has_no_writes(session, task)
                return TerminalObservation(
                    task_id=task.id,
                    attempt=attempt,
                    result_category="success_no_change",
                    observed_at=proposal_event.created_at
                    if not current_proposals
                    else current_proposals[0].created_at,
                )
            with session.begin_nested():
                result = self.commit_model_in_session(
                    session, task, attempt, envelope
                )
            return self._model_observation(task, attempt, result)
        except WorldMemoryError as error:
            return self._record_recovery_inconsistent(
                session, task, attempt, error.reason
            )
        except UpdateThreadContextError as error:
            return self._record_recovery_inconsistent(
                session, task, attempt, error.reason
            )
        except UpdateThreadTaskError as error:
            return self._record_recovery_inconsistent(
                session, task, attempt, error.reason
            )

    @staticmethod
    def _model_observation(
        task: Task, attempt: int, result: WorldMemoryCommitResult
    ) -> TerminalObservation:
        from core.task_runtime import TerminalObservation

        if result.status == "committed":
            return TerminalObservation(
                task_id=task.id,
                attempt=attempt,
                result_category="success_update_thread_committed",
                observed_at=result.committed_at,
            )
        return TerminalObservation(
            task_id=task.id,
            attempt=attempt,
            result_category="terminal_failure",
            observed_at=result.committed_at,
            failure_reason="all_update_thread_proposals_rejected",
        )

    @staticmethod
    def _assert_model_empty_set_has_no_writes(
        session: Session, task: Task
    ) -> None:
        if (
            session.scalar(
                select(EvidenceLink.id)
                .where(EvidenceLink.originating_task_id == task.id)
                .limit(1)
            )
            is not None
            or session.scalar(
                select(ConfidenceChange.id)
                .where(ConfidenceChange.created_by_task_id == task.id)
                .limit(1)
            )
            is not None
            or session.scalar(
                select(Event.id)
                .where(
                    Event.task_id == task.id,
                    Event.type.in_(
                        (
                            "hypothesis_created",
                            "evidence_link_added",
                            "confidence_changed",
                            "hypothesis_rejected",
                            "hypothesis_superseded",
                            "update_thread_proposal_accepted",
                            "update_thread_proposal_rejected",
                            MODEL_COMMITTED_EVENT_TYPE,
                            MODEL_REJECTED_EVENT_TYPE,
                        )
                    ),
                )
                .limit(1)
            )
            is not None
        ):
            raise WorldMemoryError("update_thread_empty_set_has_business_writes")

    @staticmethod
    def _validate_inconsistent_marker(
        task: Task, attempt: int, marker: Event
    ) -> None:
        payload = marker.payload
        if (
            marker.task_id != task.id
            or not isinstance(payload, dict)
            or set(payload)
            != {
                "schema_version",
                "task_id",
                "team_id",
                "thread_id",
                "attempt",
                "actor_type",
                "proposal_fingerprint",
                "failure_category",
            }
            or type(payload.get("schema_version")) is not int
            or payload.get("schema_version") != 1
            or payload.get("task_id") != str(task.id)
            or payload.get("team_id") != str(task.team_id)
            or (
                payload.get("thread_id") is not None
                and not isinstance(payload.get("thread_id"), str)
            )
            or type(payload.get("attempt")) is not int
            or payload.get("attempt") != attempt
            or payload.get("actor_type") != "model_worker"
            or payload.get("failure_category") != "update_thread_recovery_inconsistent"
            or (
                payload.get("proposal_fingerprint") is not None
                and (
                    not isinstance(payload.get("proposal_fingerprint"), str)
                    or len(payload["proposal_fingerprint"]) != 71
                    or not payload["proposal_fingerprint"].startswith("sha256:")
                )
            )
        ):
            raise WorldMemoryError("update_thread_recovery_marker_invalid")

    @classmethod
    def _record_recovery_inconsistent(
        cls, session: Session, task: Task, attempt: int, reason: str
    ) -> TerminalObservation:
        from core.task_runtime import TerminalObservation

        existing = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == MODEL_INCONSISTENT_EVENT_TYPE,
                )
            )
        )
        if existing:
            if len(existing) != 1:
                raise WorldMemoryError("update_thread_recovery_marker_duplicate")
            cls._validate_inconsistent_marker(task, attempt, existing[0])
            marker = existing[0]
        else:
            request_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == "update_thread_requested",
                    )
                )
            )
            proposal_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == task.id,
                        Event.type == "update_thread_proposals_validated",
                    )
                )
            )
            current = [
                event
                for event in proposal_events
                if isinstance(event.payload, dict)
                and type(event.payload.get("attempt")) is int
                and event.payload["attempt"] == attempt
            ]
            fingerprint = (
                current[0].payload.get("proposal_fingerprint")
                if len(current) == 1
                else None
            )
            if fingerprint is not None and (
                not isinstance(fingerprint, str)
                or len(fingerprint) != 71
                or not fingerprint.startswith("sha256:")
            ):
                fingerprint = None
            marker = Event(
                id=uuid4(),
                task_id=task.id,
                type=MODEL_INCONSISTENT_EVENT_TYPE,
                payload={
                    "schema_version": 1,
                    "task_id": str(task.id),
                    "team_id": str(task.team_id),
                    "thread_id": (
                        request_events[0].payload.get("thread_id")
                        if len(request_events) == 1
                        and isinstance(request_events[0].payload, dict)
                        else None
                    ),
                    "attempt": attempt,
                    "actor_type": "model_worker",
                    "proposal_fingerprint": fingerprint,
                    "failure_category": "update_thread_recovery_inconsistent",
                },
                created_at=datetime.now(timezone.utc),
            )
            session.add(marker)
            session.flush()
        return TerminalObservation(
            task_id=task.id,
            attempt=attempt,
            result_category="terminal_failure",
            observed_at=marker.created_at,
            failure_reason="update_thread_recovery_inconsistent",
        )

    @staticmethod
    def _existing_result(
        session: Session,
        task: Task,
        envelope: OperatorUpdateEnvelope,
    ) -> WorldMemoryCommitResult | None:
        committed = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == COMMITTED_EVENT_TYPE,
                )
            )
        )
        rejected = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == REJECTED_EVENT_TYPE,
                )
            )
        )
        if committed and rejected:
            raise WorldMemoryError("operator_update_commit_markers_conflict")
        if committed:
            if len(committed) != 1:
                raise WorldMemoryError("operator_update_commit_marker_count_invalid")
            payload = committed[0].payload
            if (
                not isinstance(payload, dict)
                or payload.get("request_fingerprint") != envelope.request_fingerprint
                or payload.get("attempt_count") != task.attempt_count
            ):
                raise WorldMemoryError("operator_update_commit_marker_invalid")
            return WorldMemoryCommitResult(
                task_id=task.id,
                status="committed",
                committed_count=len(payload.get("committed_proposal_keys", [])),
                rejected_count=len(payload.get("rejected_proposal_keys", [])),
                committed_at=committed[0].created_at,
                request_fingerprint=envelope.request_fingerprint,
                replayed=True,
            )
        if rejected:
            if len(rejected) != 1:
                raise WorldMemoryError("operator_update_rejection_marker_count_invalid")
            payload = rejected[0].payload
            if (
                not isinstance(payload, dict)
                or payload.get("request_fingerprint") != envelope.request_fingerprint
                or payload.get("attempt_count") != task.attempt_count
            ):
                raise WorldMemoryError("operator_update_rejection_marker_invalid")
            return WorldMemoryCommitResult(
                task_id=task.id,
                status="rejected",
                committed_count=0,
                rejected_count=len(payload.get("rejected_proposal_keys", [])),
                committed_at=rejected[0].created_at,
                request_fingerprint=envelope.request_fingerprint,
                replayed=True,
                failure_reason=payload["failure_reason"],
            )
        return None

    def _existing_model_result(
        self,
        session: Session,
        task: Task,
        context: _ProposalCommitContext,
        actor: ModelWorkerActor,
    ) -> WorldMemoryCommitResult | None:
        envelope = context.model_envelope
        if (
            envelope is None
            or actor.task_id != task.id
            or actor.request_event_id != envelope.request_event_id
        ):
            raise WorldMemoryError("update_thread_actor_envelope_mismatch")
        markers = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type.in_(
                        (
                            MODEL_COMMITTED_EVENT_TYPE,
                            MODEL_REJECTED_EVENT_TYPE,
                            MODEL_INCONSISTENT_EVENT_TYPE,
                        )
                    ),
                )
            )
        )
        if not markers:
            return None
        if len(markers) != 1:
            raise WorldMemoryError("update_thread_commit_marker_count_invalid")
        marker = markers[0]
        if marker.type == MODEL_INCONSISTENT_EVENT_TYPE:
            raise WorldMemoryError("update_thread_recovery_already_inconsistent")
        return validate_model_update_thread_marker(
            session, task, envelope, marker, self._snapshot_store
        )


def validate_operator_update_terminal(
    session: Session,
    task: Task,
    observation,
    *,
    allow_completed: bool = False,
) -> None:
    """Verify the Task result against the immutable request and committed rows."""
    envelope = validate_operator_update_task_request(session, task)
    expected_status = (
        "done"
        if allow_completed
        and observation.result_category == "success_operator_update_committed"
        else "failed"
        if allow_completed
        else "running"
    )
    if (
        task.status != expected_status
        or task.attempt_count != observation.attempt
        or observation.task_id != task.id
    ):
        raise WorldMemoryError("operator_update_terminal_task_mismatch")

    markers = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type.in_((COMMITTED_EVENT_TYPE, REJECTED_EVENT_TYPE)),
            )
        )
    )
    if len(markers) != 1 or not isinstance(markers[0].payload, dict):
        raise WorldMemoryError("operator_update_commit_marker_count_invalid")
    marker = markers[0]
    payload = marker.payload
    common = {
        "schema_version",
        "task_id",
        "team_id",
        "thread_id",
        "attempt_count",
        "operator_id",
        "request_fingerprint",
    }
    if (
        payload.get("schema_version") != 1
        or payload.get("task_id") != str(task.id)
        or payload.get("team_id") != str(task.team_id)
        or payload.get("thread_id") != str(envelope.request.thread_id)
        or payload.get("attempt_count") != task.attempt_count
        or payload.get("operator_id") != envelope.operator_id
        or payload.get("request_fingerprint") != envelope.request_fingerprint
        or marker.created_at != observation.observed_at
    ):
        raise WorldMemoryError("operator_update_commit_marker_invalid")

    proposals = {proposal.key: proposal for proposal in envelope.request.proposals}
    if observation.result_category == "success_operator_update_committed":
        if marker.type != COMMITTED_EVENT_TYPE or set(payload) != (
            common
            | {
                "committed_proposal_keys",
                "rejected_proposal_keys",
                "hypothesis_ids",
                "evidence_link_ids",
                "confidence_change_ids",
            }
        ):
            raise WorldMemoryError("operator_update_commit_marker_invalid")
        committed = payload["committed_proposal_keys"]
        rejected = payload["rejected_proposal_keys"]
        if (
            not isinstance(committed, list)
            or not isinstance(rejected, list)
            or not all(isinstance(key, str) for key in committed + rejected)
            or not committed
            or len(committed) != len(set(committed))
            or len(rejected) != len(set(rejected))
            or set(committed) & set(rejected)
            or set(committed) | set(rejected) != set(proposals)
            or not isinstance(payload.get("hypothesis_ids"), list)
            or not isinstance(payload.get("evidence_link_ids"), list)
            or not isinstance(payload.get("confidence_change_ids"), list)
            or not all(
                isinstance(value, str)
                for field in (
                    "hypothesis_ids",
                    "evidence_link_ids",
                    "confidence_change_ids",
                )
                for value in payload[field]
            )
        ):
            raise WorldMemoryError("operator_update_commit_marker_invalid")
        event_types: dict[str, str] = {}
        for key in committed:
            proposal = proposals[key]
            if isinstance(proposal, HypothesisCreateProposal):
                event_types[key] = "hypothesis_created"
            elif isinstance(proposal, EvidenceLinkProposal):
                event_types[key] = "evidence_link_added"
            elif isinstance(proposal, ConfidenceChangeProposal):
                event_types[key] = "confidence_changed"
            elif isinstance(proposal, HypothesisTransitionProposal):
                event_types[key] = (
                    "hypothesis_rejected"
                    if proposal.action == "reject"
                    else "hypothesis_superseded"
                )
        for key in rejected:
            event_types[key] = "proposal_rejected"

        proposal_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type.in_(
                        (
                            "hypothesis_created",
                            "evidence_link_added",
                            "confidence_changed",
                            "hypothesis_rejected",
                            "hypothesis_superseded",
                            "proposal_rejected",
                        )
                    ),
                )
            )
        )
        by_key: dict[str, list[Event]] = {}
        for event in proposal_events:
            event_payload = event.payload
            if not isinstance(event_payload, dict):
                raise WorldMemoryError("operator_update_proposal_event_invalid")
            key = event_payload.get("proposal_key")
            if (
                event_payload.get("task_id") != str(task.id)
                or event_payload.get("team_id") != str(task.team_id)
                or event_payload.get("operator_id") != envelope.operator_id
                or event_payload.get("request_fingerprint")
                != envelope.request_fingerprint
                or not isinstance(key, str)
            ):
                raise WorldMemoryError("operator_update_proposal_event_invalid")
            by_key.setdefault(key, []).append(event)
        if set(by_key) != set(proposals) or any(
            len(events) != 1
            or events[0].type != event_types[key]
            for key, events in by_key.items()
        ):
            raise WorldMemoryError("operator_update_proposal_event_set_invalid")

        created_hypothesis_ids = [
            event.payload["hypothesis_id"]
            for event in proposal_events
            if event.type == "hypothesis_created"
        ]
        evidence_ids = [
            str(item.id)
            for item in session.scalars(
                select(EvidenceLink).where(
                    EvidenceLink.originating_task_id == task.id,
                    EvidenceLink.team_id == task.team_id,
                    EvidenceLink.subject_kind == "hypothesis",
                )
            )
        ]
        confidence_ids = [
            str(item.id)
            for item in session.scalars(
                select(ConfidenceChange).where(
                    ConfidenceChange.created_by_task_id == task.id,
                    ConfidenceChange.team_id == task.team_id,
                )
            )
        ]
        if (
            set(payload["hypothesis_ids"]) != set(created_hypothesis_ids)
            or len(payload["hypothesis_ids"]) != len(created_hypothesis_ids)
            or set(payload["evidence_link_ids"]) != set(evidence_ids)
            or set(payload["confidence_change_ids"]) != set(confidence_ids)
            or len(payload["evidence_link_ids"]) != len(evidence_ids)
            or len(payload["confidence_change_ids"]) != len(confidence_ids)
        ):
            raise WorldMemoryError("operator_update_committed_rows_mismatch")
        for raw_id in payload["hypothesis_ids"]:
            hypothesis = session.get(Hypothesis, UUID(raw_id))
            creation_event = next(
                (
                    event
                    for event in proposal_events
                    if event.type == "hypothesis_created"
                    and event.payload.get("hypothesis_id") == raw_id
                ),
                None,
            )
            if (
                hypothesis is None
                or hypothesis.team_id != task.team_id
                or hypothesis.thread_id != envelope.request.thread_id
                or creation_event is None
                or creation_event.payload.get("thread_id")
                != str(envelope.request.thread_id)
                or creation_event.payload.get("confidence") != "low"
            ):
                raise WorldMemoryError("operator_update_created_hypothesis_invalid")
        for raw_id in payload["evidence_link_ids"]:
            link = session.get(EvidenceLink, UUID(raw_id))
            if (
                link is None
                or link.originating_task_id != task.id
                or link.team_id != task.team_id
                or link.subject_kind != "hypothesis"
            ):
                raise WorldMemoryError("operator_update_evidence_link_invalid")
        for raw_id in payload["confidence_change_ids"]:
            change = session.get(ConfidenceChange, UUID(raw_id))
            if (
                change is None
                or change.created_by_task_id != task.id
                or change.team_id != task.team_id
                or change.cause_kind != "evidence"
                or change.evidence_link_id is None
            ):
                raise WorldMemoryError("operator_update_confidence_change_invalid")
            cause = session.get(EvidenceLink, change.evidence_link_id)
            if (
                cause is None
                or cause.subject_kind != "hypothesis"
                or cause.hypothesis_id != change.hypothesis_id
                or cause.team_id != task.team_id
                or cause.stance not in {"supports", "challenges"}
            ):
                raise WorldMemoryError("operator_update_confidence_cause_invalid")
        return

    if (
        observation.result_category != "terminal_failure"
        or marker.type != REJECTED_EVENT_TYPE
        or set(payload)
        != common | {"rejected_proposal_keys", "failure_reason"}
        or observation.failure_reason not in {
            "all_operator_update_proposals_rejected", "interrupted_execution"
        }
        or payload.get("failure_reason") != observation.failure_reason
        or not isinstance(payload.get("rejected_proposal_keys"), list)
        or not all(
            isinstance(key, str) for key in payload["rejected_proposal_keys"]
        )
        or payload["rejected_proposal_keys"] != list(proposals)
    ):
        raise WorldMemoryError("operator_update_rejection_marker_invalid")
    rejection_events = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type == "proposal_rejected",
            )
        )
    )
    rejected_by_key: dict[str, Event] = {}
    for event in rejection_events:
        event_payload = event.payload
        if (
            not isinstance(event_payload, dict)
            or not isinstance(event_payload.get("proposal_key"), str)
            or not isinstance(event_payload.get("reason"), str)
            or not event_payload["reason"].strip()
            or event_payload.get("task_id") != str(task.id)
            or event_payload.get("team_id") != str(task.team_id)
            or event_payload.get("operator_id") != envelope.operator_id
            or event_payload.get("request_fingerprint") != envelope.request_fingerprint
            or (
                observation.failure_reason == "interrupted_execution"
                and event_payload["reason"] != "interrupted_execution"
            )
        ):
            raise WorldMemoryError("operator_update_rejection_event_invalid")
        rejected_by_key[event_payload["proposal_key"]] = event
    if (
        set(rejected_by_key) != set(proposals)
        or len(rejection_events) != len(proposals)
        or session.scalar(
            select(EvidenceLink.id).where(
                EvidenceLink.originating_task_id == task.id
            ).limit(1)
        )
        is not None
        or session.scalar(
            select(ConfidenceChange.id).where(
                ConfidenceChange.created_by_task_id == task.id
            ).limit(1)
        )
        is not None
        or session.scalar(
            select(Event.id).where(
                Event.task_id == task.id,
                Event.type.in_(
                    (
                        "hypothesis_created",
                        "evidence_link_added",
                        "confidence_changed",
                        "hypothesis_rejected",
                        "hypothesis_superseded",
                    )
                ),
            ).limit(1)
        ) is not None
    ):
        raise WorldMemoryError("operator_update_rejection_event_set_invalid")


def record_interrupted_operator_update_failure(
    session: Session,
    task: Task,
    observed_at: datetime,
) -> TerminalObservation:
    """Record deterministic rejection when all Operator Task attempts expire."""
    from core.task_runtime import TerminalObservation

    envelope = validate_operator_update_task_request(session, task)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise WorldMemoryError("operator_update_interruption_time_invalid")
    existing_marker = session.scalar(
        select(Event.id).where(
            Event.task_id == task.id,
            Event.type.in_((COMMITTED_EVENT_TYPE, REJECTED_EVENT_TYPE)),
        ).limit(1)
    )
    if existing_marker is not None:
        raise WorldMemoryError("operator_update_interruption_marker_already_exists")
    prior_rejections = session.scalar(
        select(Event.id).where(
            Event.task_id == task.id,
            Event.type == "proposal_rejected",
        ).limit(1)
    )
    if prior_rejections is not None:
        raise WorldMemoryError("operator_update_interruption_rejection_already_exists")
    prior_writes = session.scalar(
        select(Event.id).where(
            Event.task_id == task.id,
            Event.type.in_(
                (
                    "hypothesis_created",
                    "evidence_link_added",
                    "confidence_changed",
                    "hypothesis_rejected",
                    "hypothesis_superseded",
                )
            ),
        ).limit(1)
    )
    if prior_writes is not None:
        raise WorldMemoryError("operator_update_interrupted_with_partial_writes")

    _record_all_rejected(
        session,
        task,
        envelope,
        task.attempt_count,
        {
            proposal.key: "interrupted_execution"
            for proposal in envelope.request.proposals
        },
        failure_reason="interrupted_execution",
        created_at=observed_at,
    )
    return TerminalObservation(
        task_id=task.id,
        attempt=task.attempt_count,
        result_category="terminal_failure",
        observed_at=observed_at,
        failure_reason="interrupted_execution",
    )


def committed_operator_update_observation(
    session: Session, task: Task
) -> TerminalObservation | None:
    """Reconstruct the terminal observation after a commit before finalization."""
    from core.task_runtime import TerminalObservation

    envelope = validate_operator_update_task_request(session, task)
    markers = list(
        session.scalars(
            select(Event).where(
                Event.task_id == task.id,
                Event.type.in_((COMMITTED_EVENT_TYPE, REJECTED_EVENT_TYPE)),
            )
        )
    )
    if not markers:
        return None
    if len(markers) != 1 or not isinstance(markers[0].payload, dict):
        raise WorldMemoryError("operator_update_commit_marker_count_invalid")
    marker = markers[0]
    payload = marker.payload
    if (
        payload.get("task_id") != str(task.id)
        or payload.get("team_id") != str(task.team_id)
        or payload.get("thread_id") != str(envelope.request.thread_id)
        or payload.get("operator_id") != envelope.operator_id
        or payload.get("request_fingerprint") != envelope.request_fingerprint
        or payload.get("attempt_count") != task.attempt_count
    ):
        raise WorldMemoryError("operator_update_commit_marker_invalid")
    if marker.type == COMMITTED_EVENT_TYPE:
        committed = payload.get("committed_proposal_keys")
        rejected = payload.get("rejected_proposal_keys")
        all_keys = {proposal.key for proposal in envelope.request.proposals}
        if (
            not isinstance(committed, list)
            or not isinstance(rejected, list)
            or not committed
            or set(committed) & set(rejected)
            or set(committed) | set(rejected) != all_keys
        ):
            raise WorldMemoryError("operator_update_commit_marker_invalid")
        return TerminalObservation(
            task_id=task.id,
            attempt=task.attempt_count,
            result_category="success_operator_update_committed",
            observed_at=marker.created_at,
        )
    rejected_keys = payload.get("rejected_proposal_keys")
    if (
        not isinstance(rejected_keys, list)
        or not all(isinstance(key, str) for key in rejected_keys)
        or rejected_keys
        != [proposal.key for proposal in envelope.request.proposals]
        or payload.get("failure_reason") not in {
            "all_operator_update_proposals_rejected", "interrupted_execution"
        }
    ):
        raise WorldMemoryError("operator_update_rejection_marker_invalid")
    return TerminalObservation(
        task_id=task.id,
        attempt=task.attempt_count,
        result_category="terminal_failure",
        observed_at=marker.created_at,
        failure_reason=payload["failure_reason"],
    )
