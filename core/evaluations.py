"""Evidence-linked Evaluation proposal, validation, and disposition service."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Evaluation, EvidenceLink, Outcome, Signal, Task, Team
from core.objectives import ObjectiveService
from core.snapshot_store import SnapshotIntegrityError, SnapshotStore

Conclusion = Literal["worked", "mixed", "failed", "inconclusive"]
EvaluatorKind = Literal["rule", "human", "model"]
EvidenceKind = Literal["outcome", "signal"]
EvidenceStance = Literal["supports", "challenges", "mentions"]


class EvaluationValidationError(ValueError):
    """The Task, Outcome, or cited evidence is invalid for this Evaluation."""


class EvaluationConflict(RuntimeError):
    """An Evaluation disposition or idempotency key conflicts with prior state."""


class EvaluationFindings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    observed_result: str = Field(min_length=1, max_length=4000)
    intended_result: str | None = Field(default=None, max_length=4000)
    method_or_process: str = Field(min_length=1, max_length=4000)
    context: list[str] = Field(default_factory=list, max_length=32)
    alternative_explanations: list[str] = Field(default_factory=list, max_length=32)
    attribution: str = Field(default="not established", min_length=1, max_length=1000)
    uncertainty: list[str] = Field(default_factory=list, max_length=32)


class EvaluationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_kind: EvidenceKind
    outcome_id: UUID | None = None
    signal_id: UUID | None = None
    stance: EvidenceStance
    snapshot_ref: str | None = None
    snapshot_hash: str | None = None
    quote_text: str | None = Field(default=None, max_length=4000)
    quote_start: int | None = None
    quote_end: int | None = None

    @model_validator(mode="after")
    def validate_reference_shape(self) -> EvaluationEvidence:
        if self.source_kind == "outcome":
            if self.outcome_id is None or self.signal_id is not None:
                raise ValueError("outcome evidence requires only outcome_id")
        elif self.signal_id is None or self.outcome_id is not None:
            raise ValueError("signal evidence requires only signal_id")
        if (self.snapshot_ref is None) != (self.snapshot_hash is None):
            raise ValueError("snapshot_ref_and_hash_must_be_paired")
        quote_values = (self.quote_text, self.quote_start, self.quote_end)
        if (
            any(value is not None for value in quote_values)
            and not all(value is not None for value in quote_values)
        ):
            raise ValueError("quote_text_and_offsets_must_be_paired")
        if self.quote_start is not None and (
            self.quote_start < 0 or self.quote_end is None or self.quote_end <= self.quote_start  # noqa: E501
        ):
            raise ValueError("invalid_quote_offsets")
        return self


class EvaluationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    outcome_id: UUID
    conclusion: Conclusion
    findings: EvaluationFindings
    evidence: list[EvaluationEvidence] = Field(min_length=1, max_length=32)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def nonblank_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("idempotency_key_required")
        return value.strip()


@dataclass(frozen=True)
class EvaluationResult:
    evaluation_id: UUID
    status: str
    replayed: bool = False


class EvaluationService:
    """Record Evaluation evidence; never mutate Outcomes or canonical knowledge."""

    def __init__(self, session_factory: sessionmaker[Session],
        snapshot_store: SnapshotStore) -> None:
        self._session_factory = session_factory
        self._snapshot_store = snapshot_store

    def propose(
        self, task_id: UUID, draft: EvaluationDraft, *,
        evaluator_kind: EvaluatorKind, evaluator_identity: str, evaluator_revision: str,
    ) -> EvaluationResult:
        if evaluator_kind not in {"rule", "human", "model"}:
            raise EvaluationValidationError("invalid_evaluator_kind")
        if not evaluator_identity.strip() or not evaluator_revision.strip():
            raise EvaluationValidationError("evaluator_identity_and_revision_required")
        if (
            len(evaluator_identity.strip()) > 255
            or len(evaluator_revision.strip()) > 255
        ):
            raise EvaluationValidationError("evaluator_identity_or_revision_too_long")
        with self._session_factory.begin() as session:
            task, team = self._require_task(session, task_id)
            outcome = session.get(Outcome, draft.outcome_id)
            if outcome is None or outcome.team_id != team.id:
                raise EvaluationValidationError("outcome_not_owned_by_task_team")
            normalized = [self._normalize_evidence(session, team,
                item) for item in draft.evidence]
            if (
                not any(item["source_kind"] == "outcome"
                and item["outcome_id"] == str(draft.outcome_id) for item in normalized)
            ):
                raise EvaluationValidationError("primary_outcome_evidence_required")
            normalized.sort(key=lambda item: item["reference_key"])
            payload = {
                "team_id": str(team.id), "outcome_id": str(outcome.id),
                "conclusion": draft.conclusion,
                    "findings": draft.findings.model_dump(mode="json"),
                "evidence": normalized, "evaluator_kind": evaluator_kind,
                "evaluator_identity": evaluator_identity.strip(),
                "evaluator_revision": evaluator_revision.strip(),
                "idempotency_key": draft.idempotency_key,
            }
            proposal_hash = _sha256_json(payload)
            prior = session.scalar(select(Evaluation).where(
                Evaluation.created_by_task_id == task.id,
                Evaluation.idempotency_key == draft.idempotency_key,
            ))
            if prior is not None:
                if prior.proposal_hash != proposal_hash:
                    raise EvaluationConflict("evaluation_idempotency_conflict")
                return EvaluationResult(prior.id, prior.status, replayed=True)
            evaluation = Evaluation(
                id=uuid4(), team_id=team.id, outcome_id=outcome.id,
                conclusion=draft.conclusion,
                    findings=draft.findings.model_dump(mode="json"),
                evaluator_kind=evaluator_kind,
                    evaluator_identity=evaluator_identity.strip(),
                evaluator_revision=evaluator_revision.strip(), status="proposed",
                idempotency_key=draft.idempotency_key, proposal_hash=proposal_hash,
                created_by_task_id=task.id,
            )
            session.add(evaluation)
            session.flush()
            for item in normalized:
                session.add(EvidenceLink(
                    id=uuid4(), team_id=team.id, subject_kind="evaluation",
                    subject_id=evaluation.id, source_kind=item["source_kind"],
                    outcome_id=UUID(item["outcome_id"]) if item["outcome_id"] else None,
                    signal_id=UUID(item["signal_id"]) if item["signal_id"] else None,
                    snapshot_ref=item["snapshot_ref"],
                        snapshot_hash=item["snapshot_hash"],
                    stance=item["stance"], quote_text=item["quote_text"],
                    quote_start=item["quote_start"], quote_end=item["quote_end"],
                    reference_key=item["reference_key"],
                ))
            ObjectiveService._add_event(session, task.id, "evaluation_proposed", {
                "evaluation_id": str(evaluation.id), "outcome_id": str(outcome.id),
                "proposal_hash": proposal_hash, "evaluator_kind": evaluator_kind,
            })
            session.flush()
            return EvaluationResult(evaluation.id, "proposed")

    def record(self, task_id: UUID, evaluation_id: UUID) -> EvaluationResult:
        with self._session_factory.begin() as session:
            task, team = self._require_task(session, task_id)
            evaluation = session.scalar(select(Evaluation).where(
                Evaluation.id == evaluation_id, Evaluation.team_id == team.id
            ).with_for_update())
            if evaluation is None:
                raise EvaluationValidationError("evaluation_not_found_for_team")
            if evaluation.created_by_task_id != task.id:
                raise EvaluationValidationError("evaluation_task_mismatch")
            if (
                evaluation.status == "recorded"
                and evaluation.resolved_by_task_id == task.id
            ):
                return EvaluationResult(evaluation.id, "recorded", replayed=True)
            if evaluation.status != "proposed":
                raise EvaluationConflict("evaluation_already_dispositioned")
            outcome = session.get(Outcome, evaluation.outcome_id)
            if outcome is None or outcome.team_id != team.id:
                raise EvaluationValidationError("outcome_not_owned_by_task_team")
            links = list(session.scalars(select(EvidenceLink).where(
                EvidenceLink.subject_kind == "evaluation",
                EvidenceLink.subject_id == evaluation.id,
                EvidenceLink.team_id == team.id,
            )))
            if not links:
                raise EvaluationValidationError("evaluation_evidence_required")
            if (
                not any(link.source_kind == "outcome"
                and link.outcome_id == evaluation.outcome_id for link in links)
            ):
                raise EvaluationValidationError("primary_outcome_evidence_required")
            for link in links:
                self._revalidate_link(session, team, link)
            evaluation.status = "recorded"
            evaluation.resolved_by_task_id = task.id
            evaluation.resolved_at = datetime.now(timezone.utc)
            ObjectiveService._add_event(session, task.id, "evaluation_recorded", {
                "evaluation_id": str(evaluation.id), "outcome_id": str(outcome.id),
                "proposal_hash": evaluation.proposal_hash,
            })
            session.flush()
            return EvaluationResult(evaluation.id, "recorded")

    def reject(self, task_id: UUID, evaluation_id: UUID, *,
        reason: str) -> EvaluationResult:
        if not reason.strip():
            raise EvaluationValidationError("rejection_reason_required")
        with self._session_factory.begin() as session:
            task, team = self._require_task(session, task_id)
            evaluation = session.scalar(select(Evaluation).where(
                Evaluation.id == evaluation_id, Evaluation.team_id == team.id
            ).with_for_update())
            if evaluation is None:
                raise EvaluationValidationError("evaluation_not_found_for_team")
            if evaluation.created_by_task_id != task.id:
                raise EvaluationValidationError("evaluation_task_mismatch")
            if (evaluation.status == "rejected" and evaluation.resolved_by_task_id == task.id  # noqa: E501
                and evaluation.rejection_reason == reason.strip()):
                return EvaluationResult(evaluation.id, "rejected", replayed=True)
            if evaluation.status != "proposed":
                raise EvaluationConflict("evaluation_already_dispositioned")
            evaluation.status = "rejected"
            evaluation.resolved_by_task_id = task.id
            evaluation.resolved_at = datetime.now(timezone.utc)
            evaluation.rejection_reason = reason.strip()
            ObjectiveService._add_event(session, task.id, "evaluation_rejected", {
                "evaluation_id": str(evaluation.id),
                    "outcome_id": str(evaluation.outcome_id),
                "reason": reason.strip(),
            })
            session.flush()
            return EvaluationResult(evaluation.id, "rejected")

    @staticmethod
    def _require_task(session: Session, task_id: UUID) -> tuple[Task, Team]:
        task = session.scalar(select(Task).where(Task.id == task_id).with_for_update())
        if task is None:
            raise EvaluationValidationError("task_not_found")
        if task.status != "running":
            raise EvaluationValidationError("task_not_running")
        if task.task_type != "evaluate_outcome":
            raise EvaluationValidationError("wrong_task_type")
        if not {"Evaluation", "EvidenceLink"}.issubset(set(task.allowed_writes)):
            raise EvaluationValidationError("evaluation_write_scope_missing")
        team = session.get(Team, task.team_id)
        if team is None or team.status != "active":
            raise EvaluationValidationError("team_not_active")
        return task, team

    def _normalize_evidence(self, session: Session, team: Team,
        evidence: EvaluationEvidence) -> dict[str, Any]:
        if evidence.source_kind == "outcome":
            source = session.get(Outcome, evidence.outcome_id)
            if source is None or source.team_id != team.id:
                raise EvaluationValidationError("evidence_outcome_team_mismatch")
            source_ref = source.observation_snapshot_ref
            source_hash = source.observation_hash
            outcome_id, signal_id = str(source.id), None
        else:
            source = session.get(Signal, evidence.signal_id)
            if source is None or source.domain != team.domain:
                raise EvaluationValidationError("evidence_signal_team_domain_mismatch")
            source_ref, source_hash = source.snapshot_ref, source.content_hash
            outcome_id, signal_id = None, str(source.id)
        if evidence.snapshot_ref is not None and (
            evidence.snapshot_ref != source_ref or evidence.snapshot_hash != source_hash
        ):
            raise EvaluationValidationError("source_snapshot_reference_mismatch")
        snapshot_ref, snapshot_hash = source_ref, source_hash
        if snapshot_ref is not None and snapshot_hash is not None:
            self._verify_snapshot(snapshot_ref, snapshot_hash, evidence.quote_text,
                evidence.quote_start, evidence.quote_end)
        elif evidence.quote_text is not None:
            raise EvaluationValidationError("quote_snapshot_required")
        item = {
            "source_kind": evidence.source_kind, "outcome_id": outcome_id,
            "signal_id": signal_id, "snapshot_ref": snapshot_ref,
            "snapshot_hash": snapshot_hash, "stance": evidence.stance,
            "quote_text": evidence.quote_text, "quote_start": evidence.quote_start,
            "quote_end": evidence.quote_end,
        }
        item["reference_key"] = _sha256_json(item)
        return item

    def _revalidate_link(self, session: Session, team: Team,
        link: EvidenceLink) -> None:
        if link.source_kind == "outcome":
            source = session.get(Outcome, link.outcome_id)
            if source is None or source.team_id != team.id:
                raise EvaluationValidationError("evidence_outcome_team_mismatch")
            if (
                link.snapshot_ref != source.observation_snapshot_ref
                or link.snapshot_hash != source.observation_hash
            ):
                raise EvaluationValidationError("source_snapshot_reference_mismatch")
        elif link.source_kind == "signal":
            source = session.get(Signal, link.signal_id)
            if source is None or source.domain != team.domain:
                raise EvaluationValidationError("evidence_signal_team_domain_mismatch")
            if (
                link.snapshot_ref != source.snapshot_ref
                or link.snapshot_hash != source.content_hash
            ):
                raise EvaluationValidationError("source_snapshot_reference_mismatch")
        else:
            raise EvaluationValidationError("unsupported_evidence_source_kind")
        if link.snapshot_ref is not None and link.snapshot_hash is not None:
            self._verify_snapshot(link.snapshot_ref, link.snapshot_hash,
                link.quote_text, link.quote_start, link.quote_end)
        elif link.quote_text is not None:
            raise EvaluationValidationError("quote_snapshot_required")

    def _verify_snapshot(self, reference: str, expected_hash: str,
        quote: str | None, start: int | None, end: int | None) -> None:
        try:
            content = self._snapshot_store.read(reference)
        except SnapshotIntegrityError as error:
            raise EvaluationValidationError(str(error)) from error
        if "sha256:" + hashlib.sha256(content).hexdigest() != expected_hash:
            raise EvaluationValidationError("snapshot_hash_mismatch")
        if quote is not None:
            try:
                decoded = content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise EvaluationValidationError("quoted_snapshot_not_utf8") from error
            if start is None or end is None or decoded[start:end] != quote:
                raise EvaluationValidationError("quote_text_offset_mismatch")


def _sha256_json(value: dict[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",",
        ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()
