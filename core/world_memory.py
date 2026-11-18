"""Deterministic Operator world-memory proposal validation and commit.

The host authenticates the Operator. This module receives only the canonical
principal identity and an ordinary, admitted `operator_update` Task. It never
writes Task lifecycle state.
"""

from __future__ import annotations

import hashlib
import json
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
class WorldMemoryCommitResult:
    task_id: UUID
    status: Literal["committed", "rejected"]
    committed_count: int
    rejected_count: int
    committed_at: datetime
    request_fingerprint: str
    replayed: bool = False
    failure_reason: str | None = None


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


class WorldMemoryCommitService:
    """Validate and commit one complete Operator proposal set atomically."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore,
    ) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store

    def commit(
        self, task_id: UUID, attempt: int, operator_id: str
    ) -> WorldMemoryCommitResult:
        with self._session_factory.begin() as session:
            task = session.scalar(
                select(Task).where(Task.id == task_id).with_for_update()
            )
            if (
                task is None
                or task.status != "running"
                or task.attempt_count != attempt
            ):
                raise WorldMemoryError("operator_update_task_not_running")
            envelope = validate_operator_update_task_request(session, task)
            if envelope.operator_id != operator_id:
                raise WorldMemoryError("operator_update_principal_mismatch")

            prior = self._existing_result(session, task, envelope)
            if prior is not None:
                return prior

            team = session.scalar(
                select(Team)
                .where(Team.id == task.team_id)
                .with_for_update()
            )
            thread = session.scalar(
                select(Thread)
                .where(
                    Thread.id == envelope.request.thread_id,
                    Thread.team_id == task.team_id,
                )
                .with_for_update()
            )
            if team is None or team.status != "active":
                return _record_all_rejected(
                    session,
                    task,
                    envelope,
                    attempt,
                    {
                        proposal.key: "operator_update_team_not_active"
                        for proposal in envelope.request.proposals
                    },
                )
            if thread is None or thread.status == "resolved":
                return _record_all_rejected(
                    session,
                    task,
                    envelope,
                    attempt,
                    {
                        proposal.key: "operator_update_thread_not_available"
                        for proposal in envelope.request.proposals
                    },
                )

            proposals = envelope.request.proposals
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
                return _record_all_rejected(
                    session, task, envelope, attempt, rejected
                )

            for proposal in proposals:
                if proposal.key in rejected:
                    session.add(
                        Event(
                            id=uuid4(),
                            task_id=task.id,
                            type="proposal_rejected",
                            payload={
                                "task_id": str(task.id),
                                "team_id": str(task.team_id),
                                "operator_id": operator_id,
                                "request_fingerprint": envelope.request_fingerprint,
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
                            thread_id=envelope.request.thread_id,
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
                                "operator_id": operator_id,
                                "request_fingerprint": envelope.request_fingerprint,
                                "proposal_key": proposal.key,
                                "hypothesis_id": str(proposal.hypothesis_id),
                                "thread_id": str(envelope.request.thread_id),
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
                            "operator_id": operator_id,
                            "request_fingerprint": envelope.request_fingerprint,
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
                            "operator_id": operator_id,
                            "request_fingerprint": envelope.request_fingerprint,
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
                    "operator_id": operator_id,
                    "request_fingerprint": envelope.request_fingerprint,
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

            for hypothesis_id in touched_hypothesis_ids:
                hypothesis = locked_hypotheses.get(hypothesis_id) or session.get(
                    Hypothesis, hypothesis_id
                )
                if hypothesis is None:
                    raise WorldMemoryError("operator_update_touched_hypothesis_missing")
                hypothesis.last_touched_at = committed_at

            session.add(
                Event(
                    id=uuid4(),
                    task_id=task.id,
                    type=COMMITTED_EVENT_TYPE,
                    payload={
                        "schema_version": 1,
                        "task_id": str(task.id),
                        "team_id": str(task.team_id),
                        "thread_id": str(envelope.request.thread_id),
                        "attempt_count": attempt,
                        "operator_id": operator_id,
                        "request_fingerprint": envelope.request_fingerprint,
                        "committed_proposal_keys": committed_keys,
                        "rejected_proposal_keys": rejected_keys,
                        "hypothesis_ids": created_hypothesis_ids,
                        "evidence_link_ids": evidence_link_ids,
                        "confidence_change_ids": confidence_change_ids,
                    },
                    created_at=committed_at,
                )
            )
            session.flush()
            return WorldMemoryCommitResult(
                task_id=task.id,
                status="committed",
                committed_count=len(valid_proposal_keys),
                rejected_count=len(rejected_keys),
                committed_at=committed_at,
                request_fingerprint=envelope.request_fingerprint,
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
            if (
                hypothesis is None
                or hypothesis.team_id != task.team_id
                or hypothesis.thread_id != envelope.request.thread_id
                or hypothesis.confidence != "low"
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
