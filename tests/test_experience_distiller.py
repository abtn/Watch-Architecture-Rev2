"""R6-F Checkpoint 2: bounded distillation and proposed LearningChange."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier, Lock, local
from threading import Event as ThreadEvent
from time import monotonic
from types import SimpleNamespace
from typing import Any, Callable, Iterator, Literal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from core.embeddings import EmbeddingBatch, EmbeddingSpace
from core.evaluations import (
    EvaluationDraft,
    EvaluationEvidence,
    EvaluationFindings,
    EvaluationService,
)
from core.experience_distiller import (
    EXPERIENCE_DISTILLATION_OPERATION,
    ExperienceDistiller,
    ExperienceDistillerConflict,
    ExperienceDistillerError,
)
from core.generation import (
    GenerationCostQuote,
    GenerationResult,
    GenerationUsage,
)
from core.generation_cost import TaskGenerationCostService
from core.knowledge_index import (
    HybridKnowledgeRetriever,
    TeamExperienceIndexer,
    _supersession_publication_is_visible,
)
from core.knowledge_quality import (
    DIMENSIONS as KNOWLEDGE_QUALITY_DIMENSIONS,
)
from core.knowledge_quality import (
    RUBRIC_IDENTITY,
    RUBRIC_REVISION,
    KnowledgeQualityAssessmentDraft,
    KnowledgeQualityAssessmentError,
    KnowledgeQualityAssessmentService,
    KnowledgeQualityDimension,
    build_case_lineage_report,
    require_recorded_assessment,
)
from core.knowledge_quality_tasks import KnowledgeQualityAssessmentTaskRunner
from core.knowledge_revalidation import (
    RECORDED_EVENT_TYPE,
    REQUEST_EVENT_TYPE,
    KnowledgeRevalidationAssessmentDraft,
    KnowledgeRevalidationAssessmentService,
    KnowledgeRevalidationFinding,
    validate_revalidation_task_request,
)
from core.knowledge_revalidation_tasks import KnowledgeRevalidationAssessmentTaskRunner
from core.learning_commit import (
    LearningCommitCorrupt,
    LearningCommitError,
    LearningCommitService,
    _knowledge_item_cas_statement,
)
from core.learning_history import (
    encode_state_snapshot,
    knowledge_item_content_hash,
    knowledge_item_state,
    reconstruct_knowledge_item_history,
)
from core.models import (
    Evaluation,
    Event,
    EvidenceLink,
    KnowledgeItem,
    KnowledgeLifecycleAssessment,
    KnowledgeQualityAssessment,
    KnowledgeRevalidationAssessment,
    LearningChange,
    LearningChangeOperatorProvenance,
    Outcome,
    Task,
    TaskGenerationCharge,
    Team,
    TeamExperienceChunk,
    TeamExperienceIndexState,
    TeamPolicy,
)
from core.operator_application import (
    LearningChangeDecisionRequest,
    LearningChangeNotApprovable,
    OperatorApplicationAdapter,
    OperatorGrant,
    OperatorTaskRequestConflict,
    TrustedOperatorPrincipal,
)
from core.operator_approval import canonical_operator_identity
from core.snapshot_store import SnapshotStore
from core.task_runtime import (
    TaskNotFinalizable,
    TaskRuntime,
    TerminalObservation,
)

_FAKE_PROVIDER = "watch_test_fake"
_FAKE_MODEL = "watch-r6f-distillation-fake"
_FAKE_PRICING_REVISION = "watch-r6f-fake-price-v1"


@dataclass(frozen=True)
class _Case:
    source_task_id: UUID
    evaluation_task_id: UUID
    outcome_id: UUID
    evaluation_id: UUID


@dataclass(frozen=True)
class _Fixture:
    team_id: UUID
    policy_id: UUID
    distillation_task_id: UUID
    cases: tuple[_Case, ...]
    extra_task_ids: list[UUID]


@pytest.fixture
def distillation_fixture(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
) -> Iterator[Callable[..., _Fixture]]:
    created: list[_Fixture] = []

    def build(
        case_count: int = 1,
        include_contrary: bool = False,
        include_mention: bool = False,
        review_interval_days: int | None = None,
    ) -> _Fixture:
        team_id, policy_id, distillation_task_id = (uuid4() for _ in range(3))
        with session_factory.begin() as session:
            session.add(Team(id=team_id, domain="distillation_test", status="active"))
            session.flush()
            session.add(
                TeamPolicy(
                    id=policy_id,
                    team_id=team_id,
                    version=1,
                    schema_version=2 if review_interval_days is not None else 1,
                    rules=(
                        {
                            "sources": [],
                            "review": {
                                "knowledge_item_interval_days": review_interval_days
                            },
                        }
                        if review_interval_days is not None
                        else {"unchanged": True}
                    ),
                )
            )
            session.flush()
            session.add(
                Task(
                    id=distillation_task_id,
                    team_id=team_id,
                    task_type="propose_learning_change",
                    status="running",
                    attempt_count=1,
                    policy_version=1,
                    allowed_writes=["LearningChange"],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 1.0,
                        "deadline_seconds": 60,
                    },
                )
            )

        cases: list[_Case] = []
        for index in range(case_count):
            source_task_id, evaluation_task_id = uuid4(), uuid4()
            with session_factory.begin() as session:
                session.add_all(
                    [
                        Task(
                            id=source_task_id,
                            team_id=team_id,
                            task_type="ingest_source",
                            status="running",
                            attempt_count=1,
                            policy_version=1,
                            allowed_writes=["Signal"],
                            budget={
                                "max_tool_calls": 0,
                                "max_cost_usd": 0.0,
                                "deadline_seconds": 60,
                            },
                        ),
                        Task(
                            id=evaluation_task_id,
                            team_id=team_id,
                            task_type="evaluate_outcome",
                            status="running",
                            attempt_count=1,
                            policy_version=1,
                            allowed_writes=["Evaluation", "EvidenceLink"],
                            budget={
                                "max_tool_calls": 0,
                                "max_cost_usd": 0.0,
                                "deadline_seconds": 60,
                            },
                        ),
                    ]
                )

            source_result = TaskRuntime(
                session_factory, snapshot_store
            ).finalize(
                TerminalObservation(
                    task_id=source_task_id,
                    attempt=1,
                    result_category="success_no_change",
                    observed_at=datetime.now(timezone.utc),
                )
            )

            evidence = [
                EvaluationEvidence(
                    source_kind="outcome",
                    outcome_id=source_result.outcome_id,
                    stance="supports",
                )
            ]
            if include_contrary and index == 0:
                evidence.append(
                    EvaluationEvidence(
                        source_kind="outcome",
                        outcome_id=source_result.outcome_id,
                        stance="challenges",
                    )
                )
            if include_mention and index == 0:
                evidence.append(
                    EvaluationEvidence(
                        source_kind="outcome",
                        outcome_id=source_result.outcome_id,
                        stance="mentions",
                    )
                )

            evaluation_service = EvaluationService(session_factory, snapshot_store)
            proposed = evaluation_service.propose(
                evaluation_task_id,
                EvaluationDraft(
                    outcome_id=source_result.outcome_id,
                    conclusion="worked",
                    findings=EvaluationFindings(
                        observed_result=f"Case {index + 1} completed.",
                        intended_result="A durable execution observation was expected.",
                        method_or_process="Configured source ingestion.",
                        context=[f"Independent fixture case {index + 1}."],
                        alternative_explanations=[
                            "The source may have changed independently."
                        ],
                        attribution="not established",
                        uncertainty=[
                            "The observed sequence does not establish causation."
                        ],
                    ),
                    evidence=evidence,
                    idempotency_key=f"evaluation-{index + 1}",
                ),
                evaluator_kind="rule",
                evaluator_identity="r6f-distiller-test",
                evaluator_revision="1",
            )
            evaluation_service.record(evaluation_task_id, proposed.evaluation_id)
            TaskRuntime(session_factory, snapshot_store).finalize(
                TerminalObservation(
                    task_id=evaluation_task_id,
                    attempt=1,
                    result_category="success_evaluation_recorded",
                    observed_at=datetime.now(timezone.utc),
                    evaluation_id=proposed.evaluation_id,
                )
            )
            cases.append(
                _Case(
                    source_task_id=source_task_id,
                    evaluation_task_id=evaluation_task_id,
                    outcome_id=source_result.outcome_id,
                    evaluation_id=proposed.evaluation_id,
                )
            )

        fixture = _Fixture(
            team_id=team_id,
            policy_id=policy_id,
            distillation_task_id=distillation_task_id,
            cases=tuple(cases),
            extra_task_ids=[],
        )
        created.append(fixture)
        return fixture

    try:
        yield build
    finally:
        for fixture in reversed(created):
            evaluation_ids = [case.evaluation_id for case in fixture.cases]
            source_task_ids = [case.source_task_id for case in fixture.cases]
            evaluation_task_ids = [case.evaluation_task_id for case in fixture.cases]
            all_task_ids = [
                fixture.distillation_task_id,
                *source_task_ids,
                *evaluation_task_ids,
                *fixture.extra_task_ids,
            ]
            with session_factory.begin() as session:
                session.execute(
                    delete(EvidenceLink).where(
                        EvidenceLink.subject_id.in_(evaluation_ids)
                    )
                )
                approval_task_ids = select(Task.id).where(
                    Task.task_type == "approve_learning_change",
                    Task.team_id == fixture.team_id,
                )
                quality_task_ids = select(Task.id).where(
                    Task.task_type == "assess_knowledge_quality",
                    Task.team_id == fixture.team_id,
                )
                proposal_owner = LearningChange.proposed_by_task_id.in_(
                    all_task_ids
                )
                approval_commit = LearningChange.committed_by_task_id.in_(
                    approval_task_ids
                )
                learning_change_ids = select(LearningChange.id).where(
                    proposal_owner | approval_commit
                )
                lifecycle_change_ids = select(LearningChange.id).where(
                    proposal_owner,
                    LearningChange.operation.in_(("retire", "supersede")),
                )
                session.execute(
                    text(
                        "ALTER TABLE knowledge_lifecycle_assessments "
                        "DISABLE TRIGGER USER"
                    )
                )
                session.execute(
                    delete(KnowledgeLifecycleAssessment).where(
                        KnowledgeLifecycleAssessment.learning_change_id.in_(
                            lifecycle_change_ids
                        )
                    )
                )
                session.execute(
                    text(
                        "ALTER TABLE knowledge_lifecycle_assessments "
                        "ENABLE TRIGGER USER"
                    )
                )
                session.execute(
                    text(
                        "ALTER TABLE learning_change_operator_provenance "
                        "DISABLE TRIGGER USER"
                    )
                )
                session.execute(
                    delete(LearningChangeOperatorProvenance).where(
                        LearningChangeOperatorProvenance.learning_change_id.in_(
                            lifecycle_change_ids
                        )
                    )
                )
                session.execute(
                    text(
                        "ALTER TABLE learning_change_operator_provenance "
                        "ENABLE TRIGGER USER"
                    )
                )
                session.execute(
                    delete(KnowledgeQualityAssessment).where(
                        KnowledgeQualityAssessment.learning_change_id.in_(
                            learning_change_ids
                        )
                    )
                )
                session.execute(
                    text(
                        "ALTER TABLE knowledge_revalidation_assessments "
                        "DISABLE TRIGGER USER"
                    )
                )
                session.execute(
                    delete(KnowledgeRevalidationAssessment).where(
                        KnowledgeRevalidationAssessment.task_id.in_(all_task_ids)
                    )
                )
                session.execute(
                    text(
                        "ALTER TABLE knowledge_revalidation_assessments "
                        "ENABLE TRIGGER USER"
                    )
                )
                session.execute(
                    update(KnowledgeItem)
                    .where(
                        KnowledgeItem.origin_learning_change_id.in_(
                            learning_change_ids
                        )
                    )
                    .values(
                        current_learning_change_id=KnowledgeItem.origin_learning_change_id
                    )
                )
                session.execute(
                    delete(TeamExperienceChunk).where(
                        TeamExperienceChunk.team_id == fixture.team_id
                    )
                )
                session.execute(
                    delete(TeamExperienceIndexState).where(
                        TeamExperienceIndexState.team_id == fixture.team_id
                    )
                )
                session.execute(
                    delete(LearningChange).where(
                        (proposal_owner | approval_commit)
                        & LearningChange.target_id.is_not(None)
                    )
                )
                session.execute(
                    delete(KnowledgeItem).where(
                        KnowledgeItem.origin_learning_change_id.in_(learning_change_ids)
                    )
                )
                session.execute(
                    delete(LearningChange).where(
                        proposal_owner | approval_commit
                    )
                )
                session.execute(
                    delete(Outcome).where(
                        Outcome.recorded_by_task_id.in_(approval_task_ids)
                    )
                )
                session.execute(
                    delete(Event).where(Event.task_id.in_(approval_task_ids))
                )
                session.execute(delete(Task).where(Task.id.in_(approval_task_ids)))
                session.execute(
                    delete(Evaluation).where(Evaluation.id.in_(evaluation_ids))
                )
                session.execute(
                    delete(TaskGenerationCharge).where(
                        TaskGenerationCharge.task_id.in_(all_task_ids)
                    )
                )
                session.execute(
                    delete(Outcome).where(
                        Outcome.recorded_by_task_id.in_(quality_task_ids)
                    )
                )
                session.execute(
                    delete(Event).where(Event.task_id.in_(quality_task_ids))
                )
                session.execute(delete(Task).where(Task.id.in_(quality_task_ids)))
                session.execute(
                    delete(Outcome).where(
                        Outcome.recorded_by_task_id.in_(all_task_ids)
                    )
                )
                session.execute(delete(Event).where(Event.task_id.in_(all_task_ids)))
                session.execute(delete(Task).where(Task.id.in_(all_task_ids)))
                session.execute(
                    delete(TeamPolicy).where(TeamPolicy.team_id == fixture.team_id)
                )
                session.execute(delete(Team).where(Team.id == fixture.team_id))


class _FakeDistillationProvider:
    def __init__(
        self,
        content_factory: Callable[[str], dict[str, Any]],
        *,
        on_call: Callable[[], None] | None = None,
        error: Exception | None = None,
        output_tokens: int = 100,
        quote_barrier: Barrier | None = None,
        model: str = _FAKE_MODEL,
    ) -> None:
        self.content_factory = content_factory
        self.on_call = on_call
        self.error = error
        self.output_tokens = output_tokens
        self.quote_barrier = quote_barrier
        self.model = model
        self.calls = 0
        self.last_quote: GenerationCostQuote | None = None

    def maximum_request_cost(
        self, *, system_prompt: str, user_prompt: str
    ) -> GenerationCostQuote:
        quote = GenerationCostQuote(
            provider=_FAKE_PROVIDER,
            model=_FAKE_MODEL,
            maximum_input_tokens=(
                len(system_prompt.encode("utf-8"))
                + len(user_prompt.encode("utf-8"))
                + 128
            ),
            maximum_output_tokens=512,
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("1"),
            pricing_revision=_FAKE_PRICING_REVISION,
        )
        self.last_quote = quote
        if self.quote_barrier is not None:
            self.quote_barrier.wait(timeout=10)
        return quote

    def generate_json(
        self, *, system_prompt: str, user_prompt: str, temperature: float = 0.1
    ) -> GenerationResult:
        self.calls += 1
        if self.on_call is not None:
            self.on_call()
        if self.error is not None:
            raise self.error
        content = self.content_factory(user_prompt)
        return GenerationResult(
            content=content,
            model=self.model,
            usage=GenerationUsage(
                input_tokens=100,
                output_tokens=self.output_tokens,
                estimated_cost_usd=Decimal("0.0002"),
            ),
            elapsed_seconds=0.01,
            request_id=f"fake-request-{self.calls}",
        )


def _content_from_prompt(
    user_prompt: str,
    *,
    kind: str | None = None,
    confidence_band: str | None = None,
    omit_contrary: bool = False,
    malformed: bool = False,
) -> dict[str, Any]:
    prompt = json.loads(user_prompt)
    pack = prompt["evidence_pack"]
    evidence_refs: list[str] = []
    contrary_refs: list[str] = []
    context_refs: list[str] = []
    case_refs: list[str] = []
    for case in pack["cases"]:
        case_refs.extend(
            [
                case["evaluation"]["reference_id"],
                case["outcome"]["reference_id"],
            ]
        )
        for evidence in case["evidence"]:
            reference = evidence["reference_id"]
            if evidence["stance"] == "challenges":
                contrary_refs.append(reference)
            elif evidence["stance"] == "supports":
                evidence_refs.append(reference)
            else:
                context_refs.append(reference)
    if malformed:
        return {"not_a_distillation": True}
    if omit_contrary:
        evidence_refs.extend(contrary_refs)
        contrary_refs = []
    single_case = pack["case_count"] == 1
    return {
        "kind": kind or ("practice" if single_case else "pattern"),
        "title": "A bounded source-ingestion practice",
        "statement": "Preserve source evidence before drawing a conclusion.",
        "body": (
            "Record the observed result, retain its source references, and "
            "separate the observation from any explanation. This candidate "
            "does not claim that the task caused the result."
        ),
        "applicability": {
            "task_class": "ingest_source",
            "situation": "A configured source is captured and recorded as an Outcome.",
            "conditions": ["The source and Task belong to the same Team."],
        },
        "preconditions": ["A recorded Outcome and corresponding Evaluation exist."],
        "assumptions": ["The configured source identity was correct."],
        "limitations": ["Independent source changes may explain part of the result."],
        "non_applicability": ["Tasks without a validated source record."],
        "failure_modes": ["A changed source may invalidate the observed content."],
        "known_counterexamples": (
            ["A contrary evidence link is preserved for review."]
            if contrary_refs
            else ["No counterexample was observed in the available evidence basis."]
        ),
        "missing_information": ["Long-term transfer has not been evaluated."],
        "uncertainty": ["The evidence does not establish causation."],
        "confidence": 0.25,
        "confidence_band": confidence_band or ("low" if single_case else "moderate"),
        "supporting_evidence_refs": sorted(set(case_refs + evidence_refs)),
        "contrary_evidence_refs": (
            [] if omit_contrary else sorted(set(contrary_refs))
        ),
        "context_evidence_refs": sorted(set(context_refs)),
    }


def _provider(
    *,
    kind: str | None = None,
    confidence_band: str | None = None,
    omit_contrary: bool = False,
    malformed: bool = False,
    on_call: Callable[[], None] | None = None,
    error: Exception | None = None,
    output_tokens: int = 100,
    model: str = _FAKE_MODEL,
) -> _FakeDistillationProvider:
    return _FakeDistillationProvider(
        lambda prompt: _content_from_prompt(
            prompt,
            kind=kind,
            confidence_band=confidence_band,
            omit_contrary=omit_contrary,
            malformed=malformed,
        ),
        on_call=on_call,
        error=error,
        output_tokens=output_tokens,
        model=model,
    )


def _distiller(session_factory, snapshot_store, provider):
    return ExperienceDistiller(
        session_factory,
        snapshot_store,
        provider,
        TaskGenerationCostService(session_factory),
    )


def test_single_case_proposes_only_narrow_practice_and_replays(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    provider = _provider()
    distiller = _distiller(session_factory, snapshot_store, provider)

    pack = distiller.build_evidence_pack(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    assert pack.case_count == 1
    assert len(pack.basis_hash) == len("sha256:") + 64
    assert pack.document["schema_version"] == "r6f-experience-evidence-pack-v1"
    assert all(
        item["schema_version"] == "r6f-experience-evidence-pack-v1"
        for item in pack.evidence_basis
    )

    result = distiller.propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    assert result.status == "proposed"
    assert result.generation_charge_id is not None
    assert not result.replayed
    assert provider.calls == 1

    observation = TerminalObservation(
        task_id=fixture.distillation_task_id,
        attempt=1,
        result_category="success_learning_change_proposed",
        observed_at=datetime.now(timezone.utc),
        learning_change_id=result.learning_change_id,
    )
    assert (
        TaskRuntime(session_factory, snapshot_store).finalize(observation).status
        == "done"
    )

    replay = distiller.propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    assert replay.learning_change_id == result.learning_change_id
    assert replay.evidence_basis_hash == result.evidence_basis_hash
    assert replay.replayed
    assert provider.calls == 1

    with session_factory() as session:
        change = session.get(LearningChange, result.learning_change_id)
        assert change is not None
        assert change.status == "proposed"
        assert change.target_kind == "knowledge_item"
        assert change.target_id is None
        assert change.operation == "create"
        assert change.proposed_state["kind"] == "practice"
        assert change.proposed_state["confidence_band"] == "low"
        assert len(change.evidence_basis) == 1
        assert session.scalar(
            select(KnowledgeItem.id).where(
                KnowledgeItem.team_id == fixture.team_id
            )
        ) is None
        team_policy = session.get(TeamPolicy, fixture.policy_id)
        assert team_policy is not None
        assert team_policy.schema_version == 1
        assert team_policy.rules == {"unchanged": True}
        charge = session.get(TaskGenerationCharge, result.generation_charge_id)
        assert charge is not None
        assert charge.operation == EXPERIENCE_DISTILLATION_OPERATION
        assert charge.status == "reconciled"
        assert session.scalar(
            select(Event.id).where(
                Event.task_id == fixture.distillation_task_id,
                Event.type == "learning_change_proposed",
            )
        ) is not None


def test_legacy_v1_learning_change_reconstructs_without_new_basis_marker(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    distiller = _distiller(session_factory, snapshot_store, _provider())
    evaluation_id = fixture.cases[0].evaluation_id
    result = distiller.propose(fixture.distillation_task_id, [evaluation_id])

    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=result.learning_change_id,
        )
    )

    # Rebuild the exact pre-marker R6-F representation to model a LearningChange
    # already persisted by an earlier deployment. Its old hash must still replay.
    with session_factory.begin() as session:
        change = session.get(LearningChange, result.learning_change_id)
        proposer = session.get(Task, fixture.distillation_task_id)
        team = session.get(Team, fixture.team_id)
        assert change is not None and proposer is not None and team is not None
        legacy_pack = distiller._build_pack(
            session,
            proposer,
            team,
            (evaluation_id,),
            allow_completed_task=True,
            include_version_marker=False,
        )
        assert legacy_pack.document["schema_version"] == (
            "r6f-experience-evidence-pack-v1"
        )
        assert all("schema_version" not in item for item in legacy_pack.evidence_basis)
        change.evidence_basis = legacy_pack.evidence_basis
        change.evidence_basis_hash = legacy_pack.basis_hash
        change.proposed_state = {
            **change.proposed_state,
            "evidence_basis_hash": legacy_pack.basis_hash,
        }
        change.idempotency_key = (
            "r6f-distill-v1:" + legacy_pack.basis_hash.removeprefix("sha256:")
        )

        draft, rebuilt = distiller.validate_learning_change(session, change)
        assert draft.kind == "practice"
        assert rebuilt.document["schema_version"] == (
            "r6f-experience-evidence-pack-v1"
        )
        assert rebuilt.evidence_basis == legacy_pack.evidence_basis
        assert rebuilt.basis_hash == legacy_pack.basis_hash

        change.evidence_basis = [
            {
                **legacy_pack.evidence_basis[0],
                "schema_version": "r7-unknown-evidence-pack-v3",
            }
        ]
        with pytest.raises(
            ExperienceDistillerError,
            match="learning_change_evidence_version_invalid",
        ):
            distiller.validate_learning_change(session, change)


def test_reservation_is_committed_before_provider_call(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    seen: list[str] = []

    def inspect_reservation() -> None:
        with session_factory() as session:
            charges = list(
                session.scalars(
                    select(TaskGenerationCharge).where(
                        TaskGenerationCharge.task_id == fixture.distillation_task_id,
                        TaskGenerationCharge.operation
                        == EXPERIENCE_DISTILLATION_OPERATION,
                    )
                )
            )
            assert len(charges) == 1
            assert charges[0].status == "reserved"
            assert session.scalar(
                select(Event.id).where(
                    Event.task_id == fixture.distillation_task_id,
                    Event.type == "generation_cost_reserved",
                )
            ) is not None
            seen.append("reserved")

    provider = _provider(on_call=inspect_reservation)
    result = _distiller(session_factory, snapshot_store, provider).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    assert result.status == "proposed"
    assert seen == ["reserved"]


def test_one_case_cannot_propose_pattern(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    provider = _provider(kind="pattern", confidence_band="moderate")
    with pytest.raises(
        ExperienceDistillerError,
        match="single_case_requires_low_confidence_practice",
    ):
        _distiller(session_factory, snapshot_store, provider).propose(
            fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
        )
    with session_factory() as session:
        assert session.scalar(
            select(LearningChange.id).where(
                LearningChange.proposed_by_task_id == fixture.distillation_task_id
            )
        ) is None
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == fixture.distillation_task_id
            )
        )
        assert charge is not None and charge.status == "reconciled"


def test_unobserved_task_class_is_rejected(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)

    def overgeneralized_content(prompt: str) -> dict[str, Any]:
        content = _content_from_prompt(prompt)
        content["applicability"]["task_class"] = "all_team_work"
        return content

    provider = _FakeDistillationProvider(overgeneralized_content)
    with pytest.raises(
        ExperienceDistillerError, match="distillation_task_class_not_observed"
    ):
        _distiller(session_factory, snapshot_store, provider).propose(
            fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
        )
    with session_factory() as session:
        assert session.scalar(
            select(LearningChange.id).where(
                LearningChange.proposed_by_task_id == fixture.distillation_task_id
            )
        ) is None


def test_two_independent_outcomes_allow_cross_case_pattern(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(2, False)
    provider = _provider()
    distiller = _distiller(session_factory, snapshot_store, provider)
    pack = distiller.build_evidence_pack(
        fixture.distillation_task_id,
        [fixture.cases[1].evaluation_id, fixture.cases[0].evaluation_id],
    )
    assert pack.case_count == 2
    assert len(
        {case["source_task"]["task_id"] for case in pack.document["cases"]}
    ) == 2
    result = distiller.propose(
        fixture.distillation_task_id,
        [fixture.cases[1].evaluation_id, fixture.cases[0].evaluation_id],
    )
    with session_factory() as session:
        change = session.get(LearningChange, result.learning_change_id)
        assert change is not None
        assert change.proposed_state["kind"] == "pattern"
        assert change.proposed_state["confidence_band"] == "moderate"
        assert len(change.evidence_basis) == 2


def test_evidence_pack_hash_is_order_independent(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(2, False)
    distiller = _distiller(session_factory, snapshot_store, _provider())
    forward = distiller.build_evidence_pack(
        fixture.distillation_task_id,
        [fixture.cases[0].evaluation_id, fixture.cases[1].evaluation_id],
    )
    reverse = distiller.build_evidence_pack(
        fixture.distillation_task_id,
        [fixture.cases[1].evaluation_id, fixture.cases[0].evaluation_id],
    )
    assert forward.basis_hash == reverse.basis_hash
    assert forward.document == reverse.document
    assert forward.evidence_basis == reverse.evidence_basis


def test_contrary_evidence_must_be_retained(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, True)
    provider = _provider(omit_contrary=True)
    with pytest.raises(
        ExperienceDistillerError, match="contrary_evidence_not_preserved"
    ):
        _distiller(session_factory, snapshot_store, provider).propose(
            fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
        )
    with session_factory() as session:
        assert session.scalar(
            select(LearningChange.id).where(
                LearningChange.proposed_by_task_id == fixture.distillation_task_id
            )
        ) is None


def test_mention_evidence_is_retained_as_context_reference(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False, True)
    result = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    with session_factory() as session:
        change = session.get(LearningChange, result.learning_change_id)
        assert change is not None
        mention = next(
            link for link in change.evidence_basis[0]["evidence_links"]
            if link["stance"] == "mentions"
        )
        reference = f"evidence_link:{mention['reference_key']}"
        state = change.proposed_state
        assert reference in state["context_evidence_refs"]
        assert reference not in state["supporting_evidence_refs"]
        assert reference not in state["contrary_evidence_refs"]


def test_changed_evidence_during_provider_call_invalidates_proposal(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)

    def mutate_evidence() -> None:
        with session_factory.begin() as session:
            link = session.scalar(
                select(EvidenceLink).where(
                    EvidenceLink.subject_id == fixture.cases[0].evaluation_id
                )
            )
            assert link is not None
            link.stance = "challenges"

    provider = _provider(on_call=mutate_evidence)
    with pytest.raises(
        ExperienceDistillerError, match="evidence_link_integrity_mismatch"
    ):
        _distiller(session_factory, snapshot_store, provider).propose(
            fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
        )
    with session_factory() as session:
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == fixture.distillation_task_id
            )
        )
        assert charge is not None and charge.status == "reconciled"
        assert session.scalar(
            select(LearningChange.id).where(
                LearningChange.proposed_by_task_id == fixture.distillation_task_id
            )
        ) is None


def test_provider_model_mismatch_marks_cost_unknown_and_blocks_proposal(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    provider = _provider(model="unexpected-model")
    with pytest.raises(
        ExperienceDistillerError, match="provider_model_mismatch"
    ):
        _distiller(session_factory, snapshot_store, provider).propose(
            fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
        )
    with session_factory() as session:
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == fixture.distillation_task_id
            )
        )
        assert charge is not None and charge.status == "unknown"
        assert session.scalar(
            select(LearningChange.id).where(
                LearningChange.proposed_by_task_id == fixture.distillation_task_id
            )
        ) is None


def test_tampered_evidence_link_is_rejected(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    with session_factory.begin() as session:
        link = session.scalar(
            select(EvidenceLink).where(
                EvidenceLink.subject_id == fixture.cases[0].evaluation_id
            )
        )
        assert link is not None
        link.stance = "challenges"
    distiller = _distiller(session_factory, snapshot_store, _provider())
    with pytest.raises(
        ExperienceDistillerError, match="evidence_link_integrity_mismatch"
    ):
        distiller.build_evidence_pack(
            fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
        )


def test_provider_failure_marks_cost_unknown_and_creates_no_proposal(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    provider = _provider(error=RuntimeError("network unavailable"))
    with pytest.raises(ExperienceDistillerError, match="provider_call_failed"):
        _distiller(session_factory, snapshot_store, provider).propose(
            fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
        )
    with session_factory() as session:
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == fixture.distillation_task_id
            )
        )
        assert charge is not None and charge.status == "unknown"
        assert session.scalar(select(LearningChange.id)) is None


def test_usage_overrun_blocks_learning_change(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    provider = _provider(output_tokens=513)
    with pytest.raises(ExperienceDistillerError, match="generation_cost_overrun"):
        _distiller(session_factory, snapshot_store, provider).propose(
            fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
        )
    with session_factory() as session:
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == fixture.distillation_task_id
            )
        )
        assert charge is not None and charge.status == "overrun"
        assert session.scalar(select(LearningChange.id)) is None


def test_malformed_model_output_is_rejected_after_cost_reconciliation(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    provider = _provider(malformed=True)
    with pytest.raises(
        ExperienceDistillerError, match="distillation_proposal_schema_invalid"
    ):
        _distiller(session_factory, snapshot_store, provider).propose(
            fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
        )
    with session_factory() as session:
        charge = session.scalar(
            select(TaskGenerationCharge).where(
                TaskGenerationCharge.task_id == fixture.distillation_task_id
            )
        )
        assert charge is not None and charge.status == "reconciled"
        assert session.scalar(select(LearningChange.id)) is None


def test_taskruntime_requires_typed_proposal_and_reconciled_charge(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    with pytest.raises(
        TaskNotFinalizable,
        match="learning_change_task_requires_learning_change_result",
    ):
        TaskRuntime(session_factory, snapshot_store).finalize(
            TerminalObservation(
                task_id=fixture.distillation_task_id,
                attempt=1,
                result_category="success_no_change",
                observed_at=datetime.now(timezone.utc),
            )
        )
    with session_factory() as session:
        task = session.get(Task, fixture.distillation_task_id)
        assert task is not None and task.status == "running"

    result = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    terminal = TerminalObservation(
        task_id=fixture.distillation_task_id,
        attempt=1,
        result_category="success_learning_change_proposed",
        observed_at=datetime.now(timezone.utc),
        learning_change_id=result.learning_change_id,
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    assert runtime.finalize(terminal).status == "done"
    assert runtime.finalize(terminal).replayed


def test_cross_team_or_missing_evaluation_is_rejected_before_provider(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    foreign_fixture = distillation_fixture(1, False)
    provider = _provider()
    distiller = _distiller(session_factory, snapshot_store, provider)
    for evaluation_id in (uuid4(), foreign_fixture.cases[0].evaluation_id):
        with pytest.raises(
            ExperienceDistillerError,
            match="recorded_evaluation_not_found_for_team",
        ):
            distiller.propose(fixture.distillation_task_id, [evaluation_id])
    assert provider.calls == 0

def test_concurrent_duplicate_proposals_reserve_and_commit_exactly_once(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    provider = _provider()
    provider.quote_barrier = Barrier(2)
    distiller = _distiller(session_factory, snapshot_store, provider)

    def propose_once():
        try:
            return distiller.propose(
                fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
            )
        except ExperienceDistillerError as error:
            return error.reason

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: propose_once(), range(2)))

    successes = [item for item in results if not isinstance(item, str)]
    failures = [item for item in results if isinstance(item, str)]
    assert len(successes) == 1
    assert failures == ["generation_attempt_already_reserved_or_recorded"]
    assert provider.calls == 1

    with session_factory() as session:
        changes = list(
            session.scalars(
                select(LearningChange).where(
                    LearningChange.proposed_by_task_id == fixture.distillation_task_id
                )
            )
        )
        charges = list(
            session.scalars(
                select(TaskGenerationCharge).where(
                    TaskGenerationCharge.task_id == fixture.distillation_task_id
                )
            )
        )
        events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == fixture.distillation_task_id,
                    Event.type == "learning_change_proposed",
                )
            )
        )
        assert len(changes) == 1
        assert len(charges) == 1
        assert len(events) == 1




class _FakeKnowledgeQualityAssessmentProvider:
    def assess(
        self,
        *,
        task_id: UUID,
        learning_change: LearningChange,
        evidence_document: dict[str, object],
        lineage_report: dict[str, object],
    ) -> KnowledgeQualityAssessmentDraft:
        del task_id, evidence_document, lineage_report
        return KnowledgeQualityAssessmentDraft(
            learning_change_id=learning_change.id,
            proposal_hash=learning_change.proposed_state["proposal_hash"],
            evidence_basis_hash=learning_change.evidence_basis_hash,
            rubric_identity=RUBRIC_IDENTITY,
            rubric_revision=RUBRIC_REVISION,
            dimensions={
                name: KnowledgeQualityDimension(
                    disposition="insufficient_evidence",
                    findings=[
                        "The deterministic test evaluator records no positive claim."
                    ],
                    evidence_refs=[],
                )
                for name in KNOWLEDGE_QUALITY_DIMENSIONS
            },
            narrative=(
                "Deterministic test assessment: the quality contract is recorded "
                "without asserting a positive knowledge conclusion."
            ),
        )


def _run_quality_assessment(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    learning_change_id: UUID,
) -> UUID:
    from core.knowledge_quality import REQUEST_EVENT_TYPE, TASK_TYPE

    with session_factory() as session:
        tasks = list(
            session.scalars(
                select(Task)
                .where(Task.task_type == TASK_TYPE)
                .order_by(Task.created_at)
            )
        )
        task_id = None
        for task in tasks:
            request = session.scalar(
                select(Event).where(
                    Event.task_id == task.id,
                    Event.type == REQUEST_EVENT_TYPE,
                )
            )
            if (
                request is not None
                and request.payload.get("learning_change_id")
                == str(learning_change_id)
            ):
                task_id = task.id
                break
    if task_id is None:
        raise AssertionError("knowledge quality assessment Task was not created")
    result = KnowledgeQualityAssessmentTaskRunner(
        session_factory,
        snapshot_store,
        _FakeKnowledgeQualityAssessmentProvider(),
    ).run(task_id)
    assert result.status == "done"
    assert result.assessment_id is not None
    return result.assessment_id


def _approval_principal(team_id: UUID, subject: str = "operator-commit-1"):
    return TrustedOperatorPrincipal(
        issuer="https://host.example/identity",
        subject=subject,
        grants=frozenset(
            {OperatorGrant(team_id=team_id, action="approve_learning_change")}
        ),
    )


def _create_admitted_approval_task(
    session_factory,
    snapshot_store: SnapshotStore,
    team_id: UUID,
    learning_change_id: UUID,
    *,
    decision: str = "accept",
    reason: str | None = None,
):
    with session_factory() as session:
        learning_change = session.get(LearningChange, learning_change_id)
        assert learning_change is not None
        operation = learning_change.operation
    if decision == "accept" and operation != "revalidate":
        _run_quality_assessment(
            session_factory, snapshot_store, learning_change_id
        )
    request = LearningChangeDecisionRequest(
        learning_change_id=learning_change_id,
        decision=decision,  # type: ignore[arg-type]
        idempotency_key=uuid4(),
        rejection_reason=reason,
    )
    result = OperatorApplicationAdapter(
        session_factory, snapshot_store
    ).request_learning_change_decision(_approval_principal(team_id), request)
    admission = TaskRuntime(session_factory, snapshot_store).admit(result.task_id)
    return result.task_id, admission.attempt_count, _approval_principal(team_id)






def _create_proposal_task(
    session_factory: sessionmaker[Session],
    fixture: _Fixture,
    *,
    policy_version: int | None = None,
) -> UUID:
    task_id = uuid4()
    fixture.extra_task_ids.append(task_id)
    with session_factory.begin() as session:
        template = session.get(Task, fixture.distillation_task_id)
        assert template is not None
        session.add(
            Task(
                id=task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=(
                    template.policy_version
                    if policy_version is None
                    else policy_version
                ),
                allowed_writes=["LearningChange"],
                budget=dict(template.budget),
            )
        )
    return task_id


def _accept_learning_change(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    team_id: UUID,
    learning_change_id: UUID,
):
    task_id, attempt, principal = _create_admitted_approval_task(
        session_factory, snapshot_store, team_id, learning_change_id
    )
    result = LearningCommitService(session_factory, snapshot_store).decide(
        task_id, attempt, principal
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=task_id,
            attempt=attempt,
            result_category="success_learning_change_accepted",
            observed_at=result.committed_at,
            learning_change_id=result.learning_change_id,
        )
    )
    return result


def _create_active_knowledge_item(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    fixture: _Fixture,
    *,
    supersedes_item_id: UUID | None = None,
) -> UUID:
    task_id = _create_proposal_task(session_factory, fixture)
    proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        task_id,
        [case.evaluation_id for case in fixture.cases],
        supersedes_item_id=supersedes_item_id,
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    committed = _accept_learning_change(
        session_factory,
        snapshot_store,
        fixture.team_id,
        proposal.learning_change_id,
    )
    assert committed.knowledge_item_id is not None
    return committed.knowledge_item_id


def _prepare_retirement_assessment(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    fixture: _Fixture,
    target_id: UUID,
) -> tuple[UUID, TrustedOperatorPrincipal, UUID]:
    from core.knowledge_lifecycle_tasks import (
        KnowledgeLifecycleAssessmentTask,
        KnowledgeLifecycleAssessmentTaskRunner,
    )

    principal = _approval_principal(
        fixture.team_id, subject=f"operator-retire-{uuid4()}"
    )
    proposal_task_id = _create_proposal_task(session_factory, fixture)
    proposal = OperatorApplicationAdapter(
        session_factory, snapshot_store
    ).propose_retirement(
        principal,
        task_id=proposal_task_id,
        evaluation_ids=tuple(case.evaluation_id for case in fixture.cases),
        target_knowledge_item_id=target_id,
        operator_rationale={
            "schema_version": 1,
            "summary": "The supporting evidence no longer justifies continued use.",
            "reasons": [
                {
                    "category": "evidence_no_longer_reliable",
                    "statement": "The primary supporting source has been superseded.",
                },
                {
                    "category": "applicability_changed",
                    "statement": (
                        "The original applicability conditions no longer hold."
                    ),
                },
            ],
        },
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=proposal_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    lifecycle_task_id = KnowledgeLifecycleAssessmentTask(
        session_factory, snapshot_store
    ).create(proposal.learning_change_id)
    fixture.extra_task_ids.append(lifecycle_task_id)
    assessment_result = KnowledgeLifecycleAssessmentTaskRunner(
        session_factory, snapshot_store
    ).run(lifecycle_task_id)
    assert assessment_result.status == "done"
    assert assessment_result.assessment_result == "eligible"
    assert assessment_result.assessment_id is not None
    return (
        proposal.learning_change_id,
        principal,
        assessment_result.assessment_id,
    )


def _prepare_retirement_approval(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    fixture: _Fixture,
    target_id: UUID,
    *,
    idempotency_key: UUID | None = None,
) -> tuple[UUID, UUID, int, TrustedOperatorPrincipal, UUID]:
    learning_change_id, principal, assessment_id = _prepare_retirement_assessment(
        session_factory, snapshot_store, fixture, target_id
    )
    approval = OperatorApplicationAdapter(
        session_factory, snapshot_store
    ).request_learning_change_decision(
        principal,
        LearningChangeDecisionRequest(
            learning_change_id=learning_change_id,
            decision="accept",
            idempotency_key=idempotency_key or uuid4(),
        ),
    )
    admission = TaskRuntime(session_factory, snapshot_store).admit(approval.task_id)
    return (
        learning_change_id,
        approval.task_id,
        admission.attempt_count,
        principal,
        assessment_id,
    )


def _team_lifecycle_snapshot(session: Session, team_id: UUID) -> tuple[object, ...]:
    changes = tuple(
        (
            change.id,
            change.status,
            change.proposed_state,
            change.previous_state,
            change.committed_state,
            change.committed_by_task_id,
            change.decision_reason,
            change.committed_at,
        )
        for change in session.scalars(
            select(LearningChange)
            .where(LearningChange.team_id == team_id)
            .order_by(LearningChange.id)
        )
    )
    items = tuple(
        (
            item.id,
            knowledge_item_state(item),
            knowledge_item_content_hash(item),
        )
        for item in session.scalars(
            select(KnowledgeItem)
            .where(KnowledgeItem.team_id == team_id)
            .order_by(KnowledgeItem.id)
        )
    )
    events = tuple(
        (event.id, event.task_id, event.type, event.payload, event.created_at)
        for event in session.scalars(
            select(Event)
            .join(Task, Task.id == Event.task_id)
            .where(Task.team_id == team_id)
            .order_by(Event.id)
        )
    )
    outcomes = tuple(
        (
            outcome.id,
            outcome.recorded_by_task_id,
            outcome.outcome_type,
            outcome.expected,
            outcome.observation_snapshot_ref,
            outcome.observation_hash,
            outcome.observed_at,
        )
        for outcome in session.scalars(
            select(Outcome).where(Outcome.team_id == team_id).order_by(Outcome.id)
        )
    )
    tasks = tuple(
        (task.id, task.task_type, task.status, task.attempt_count, task.completed_at)
        for task in session.scalars(
            select(Task).where(Task.team_id == team_id).order_by(Task.id)
        )
    )
    return changes, items, events, outcomes, tasks


def _run_team_lock_ordered_race(
    database_engine,
    session_factory: sessionmaker[Session],
    first_operation: Callable[[], object],
    second_operation: Callable[[], object],
    *,
    second_after_first_commit: Callable[[str], bool] | None = None,
    first_after_query_before_second: Callable[[str], bool] | None = None,
    second_must_finish_before_first_commit: bool = False,
) -> tuple[object, object, int, int]:
    operation_role = local()
    backend_pids: dict[str, int] = {}
    backend_pids_lock = Lock()
    first_lock_acquired = ThreadEvent()
    release_first = ThreadEvent()
    first_committed = ThreadEvent()
    first_gate_reached = ThreadEvent()
    release_first_gate = ThreadEvent()
    second_start_barrier = Barrier(2)
    second_started = ThreadEvent()
    second_team_lock_requested = ThreadEvent()
    second_gate_reached = ThreadEvent()

    def is_team_lock(statement: str) -> bool:
        normalized = statement.lower()
        return "teams" in normalized and "for update" in normalized

    def before_cursor_execute(
        connection, cursor, statement, parameters, context, executemany
    ):
        if "pg_backend_pid" in statement.lower():
            return
        role = getattr(operation_role, "name", None)
        if role is None:
            return
        is_team_row_lock = is_team_lock(statement)
        gate_matches = (
            role == "second"
            and second_after_first_commit is not None
            and second_after_first_commit(statement.lower())
        )
        first_gate_matches = (
            role == "first"
            and first_after_query_before_second is not None
            and first_after_query_before_second(statement.lower())
        )
        if role == "first" and not (is_team_row_lock or first_gate_matches):
            return
        if (
            role == "second"
            and "second" in backend_pids
            and not (is_team_row_lock or gate_matches)
        ):
            return

        pid = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
        with backend_pids_lock:
            backend_pids.setdefault(role, pid)
        if role == "second":
            second_started.set()
            if is_team_row_lock:
                second_team_lock_requested.set()
            if gate_matches:
                second_gate_reached.set()
                if not first_committed.wait(timeout=30):
                    raise TimeoutError(
                        "first operation did not commit before the gated query"
                    )

    def after_cursor_execute(
        connection, cursor, statement, parameters, context, executemany
    ):
        role = getattr(operation_role, "name", None)
        if (
            role == "first"
            and first_after_query_before_second is not None
            and first_after_query_before_second(statement.lower())
        ):
            first_gate_reached.set()
            second_start_barrier.wait(timeout=30)
            if not release_first_gate.wait(timeout=30):
                raise TimeoutError("first query gate was not released")
        if (
            role == "first"
            and is_team_lock(statement)
            and not first_lock_acquired.is_set()
        ):
            first_lock_acquired.set()
            second_start_barrier.wait(timeout=30)
            if not release_first.wait(timeout=30):
                raise TimeoutError("first Team lock was not released")

    def invoke(role: str, operation: Callable[[], object]) -> object:
        operation_role.name = role
        try:
            if role == "second":
                second_start_barrier.wait(timeout=30)
            return operation()
        finally:
            operation_role.name = None

    event.listen(database_engine, "before_cursor_execute", before_cursor_execute)
    event.listen(database_engine, "after_cursor_execute", after_cursor_execute)
    executor = ThreadPoolExecutor(max_workers=2)
    try:
        first_future = executor.submit(invoke, "first", first_operation)
        if first_after_query_before_second is not None:
            if not first_gate_reached.wait(timeout=30):
                raise TimeoutError("first operation did not reach its gated query")
            second_future = executor.submit(invoke, "second", second_operation)
            second_result = second_future.result(timeout=90)
            release_first_gate.set()
            first_result = first_future.result(timeout=90)
        else:
            if not first_lock_acquired.wait(timeout=30):
                raise TimeoutError("first operation did not acquire the Team lock")
            second_future = executor.submit(invoke, "second", second_operation)

        if first_after_query_before_second is not None:
            pass
        elif second_after_first_commit is not None:
            if not second_gate_reached.wait(timeout=30):
                raise TimeoutError("second operation did not reach its gated query")
            release_first.set()
            first_result = first_future.result(timeout=90)
            first_committed.set()
            second_result = second_future.result(timeout=90)
        elif second_must_finish_before_first_commit:
            if not second_started.wait(timeout=30):
                raise TimeoutError("second operation did not start")
            second_result = second_future.result(timeout=90)
            release_first.set()
            first_result = first_future.result(timeout=90)
        else:
            if not second_team_lock_requested.wait(timeout=30):
                raise TimeoutError("second operation did not request the Team lock")
            with session_factory() as observer:
                deadline = monotonic() + 30
                while True:
                    blockers = observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"),
                        {"pid": backend_pids["second"]},
                    )
                    if backend_pids["first"] in blockers:
                        break
                    if monotonic() >= deadline:
                        raise TimeoutError(
                            "second Team lock was not blocked by the first"
                        )
                    ThreadEvent().wait(0.01)
            release_first.set()
            first_result = first_future.result(timeout=90)
            first_committed.set()
            second_result = second_future.result(timeout=90)

        first_pid = backend_pids["first"]
        second_pid = backend_pids["second"]
        assert first_pid != second_pid
        return first_result, second_result, first_pid, second_pid
    finally:
        release_first.set()
        first_committed.set()
        executor.shutdown(wait=True)
        event.remove(database_engine, "before_cursor_execute", before_cursor_execute)
        event.remove(database_engine, "after_cursor_execute", after_cursor_execute)


class _FakeKnowledgeRevalidationProvider:
    evaluator_identity = "r7b-revalidation-test"
    evaluator_revision = "1"

    def __init__(
        self,
        *,
        fail_first: bool = False,
        freshness_disposition: Literal[
            "current", "stale", "insufficient", "conflicting", "unassessable"
        ] = "current",
    ) -> None:
        self.calls = 0
        self.fail_first = fail_first
        self.freshness_disposition = freshness_disposition

    def draft_for_references(
        self, allowed_evidence_references: frozenset[str]
    ) -> KnowledgeRevalidationAssessmentDraft:
        code_by_disposition = {
            "current": "supports_revalidation",
            "stale": "temporally_stale",
            "insufficient": "insufficient_coverage",
            "conflicting": "unresolved_conflict",
            "unassessable": "freshness_unassessable",
        }
        summary_by_disposition = {
            "current": "The rebuilt evidence basis remains relevant.",
            "stale": "The evidence basis is temporally stale.",
            "insufficient": "The evidence basis does not cover the required claims.",
            "conflicting": "The evidence basis contains unresolved conflicts.",
            "unassessable": "The evidence freshness cannot be assessed.",
        }
        references = tuple(sorted(allowed_evidence_references))
        findings = [
            KnowledgeRevalidationFinding(
                code=code_by_disposition[self.freshness_disposition],
                summary=summary_by_disposition[self.freshness_disposition],
                evidence_refs=references,
            )
        ]
        if self.freshness_disposition == "stale":
            findings.append(
                KnowledgeRevalidationFinding(
                    code="new_observation_required",
                    summary=(
                        "The claim is time-sensitive and needs a new "
                        "source observation."
                    ),
                    evidence_refs=references,
                )
            )
        return KnowledgeRevalidationAssessmentDraft(
            freshness_disposition=self.freshness_disposition,
            findings=tuple(findings),
        )

    def assess(
        self,
        *,
        task_id: UUID,
        learning_change: LearningChange,
        target_state: dict[str, object],
        evidence_document: dict[str, object],
        allowed_evidence_references: frozenset[str],
    ) -> KnowledgeRevalidationAssessmentDraft:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("simulated_evaluator_unavailable")
        return self.draft_for_references(allowed_evidence_references)


def _create_revalidation_proposal(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    fixture: _Fixture,
    knowledge_item_id: UUID,
    *,
    perform_review: bool = True,
) -> tuple[UUID, UUID]:
    runtime = TaskRuntime(session_factory, snapshot_store)
    with session_factory() as session:
        item = session.get(KnowledgeItem, knowledge_item_id)
        assert item is not None and item.team_id == fixture.team_id
        review_after = item.review_after
        assert review_after is not None
        current_change = session.get(LearningChange, item.current_learning_change_id)
        assert current_change is not None
        current_change_committed_at = current_change.committed_at
        if not perform_review:
            assert item.status == "needs_review"

    if perform_review:
        review_task_id = uuid4()
        fixture.extra_task_ids.append(review_task_id)
        review_started_at = review_after - timedelta(seconds=1)
        with session_factory.begin() as session:
            session.add(
                Task(
                    id=review_task_id,
                    team_id=fixture.team_id,
                    task_type="review_knowledge",
                    status="running",
                    attempt_count=1,
                    policy_version=1,
                    objective_id=None,
                    plan_id=None,
                    plan_action_id=None,
                    allowed_writes=["KnowledgeItem"],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.0,
                        "deadline_seconds": 30,
                    },
                    created_at=review_started_at,
                    completed_at=None,
                    max_attempts=3,
                )
            )
            session.flush()
            session.add(
                Event(
                    id=uuid4(),
                    task_id=review_task_id,
                    type="task_started",
                    payload={
                        "from_status": "pending",
                        "to_status": "running",
                        "attempt_count": 1,
                    },
                    created_at=review_started_at,
                )
            )
        runtime.finalize(
            TerminalObservation(
                task_id=review_task_id,
                attempt=1,
                result_category="success_knowledge_reviewed",
                observed_at=review_after,
            )
        )

    source_task_id = uuid4()
    fixture.extra_task_ids.append(source_task_id)
    source_started_at = (
        review_after + timedelta(seconds=1)
        if perform_review
        else current_change_committed_at + timedelta(seconds=1)
    )
    with session_factory.begin() as session:
        session.add(
            Task(
                id=source_task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=1,
                objective_id=None,
                plan_id=None,
                plan_action_id=None,
                allowed_writes=["LearningChange"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.0,
                    "deadline_seconds": 30,
                },
                created_at=source_started_at,
                completed_at=None,
                max_attempts=3,
            )
        )
        session.flush()
        session.add(
            Event(
                id=uuid4(),
                task_id=source_task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=source_started_at,
            )
        )

    proposal = ExperienceDistiller(
        session_factory,
        snapshot_store,
        provider=None,
        cost_service=TaskGenerationCostService(session_factory),
    ).propose_revalidation(
        source_task_id,
        [case.evaluation_id for case in fixture.cases],
        knowledge_item_id,
        rationale="بازبینی دوباره بر پایه شواهد فعلی.",
    )
    runtime.finalize(
        TerminalObservation(
            task_id=source_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=(
                review_after + timedelta(seconds=2)
                if perform_review
                else source_started_at + timedelta(seconds=2)
            ),
            learning_change_id=proposal.learning_change_id,
        )
    )
    with session_factory() as session:
        request_event = session.scalar(
            select(Event).where(
                Event.type == REQUEST_EVENT_TYPE,
                Event.payload["learning_change_id"].as_string()
                == str(proposal.learning_change_id),
            )
        )
        assert request_event is not None
        fixture.extra_task_ids.append(request_event.task_id)
    return source_task_id, proposal.learning_change_id


def _create_additional_revalidation_proposal(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    fixture: _Fixture,
    knowledge_item_id: UUID,
) -> UUID:
    with session_factory() as session:
        item = session.get(KnowledgeItem, knowledge_item_id)
        assert item is not None and item.review_after is not None
        review_after = item.review_after

    source_task_id = uuid4()
    fixture.extra_task_ids.append(source_task_id)
    started_at = review_after + timedelta(seconds=3)
    with session_factory.begin() as session:
        session.add(
            Task(
                id=source_task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=1,
                objective_id=None,
                plan_id=None,
                plan_action_id=None,
                allowed_writes=["LearningChange"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.0,
                    "deadline_seconds": 30,
                },
                created_at=started_at,
                completed_at=None,
                max_attempts=3,
            )
        )
        session.flush()
        session.add(
            Event(
                id=uuid4(),
                task_id=source_task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=started_at,
            )
        )

    proposal = ExperienceDistiller(
        session_factory,
        snapshot_store,
        provider=None,
        cost_service=TaskGenerationCostService(session_factory),
    ).propose_revalidation(
        source_task_id,
        [case.evaluation_id for case in fixture.cases],
        knowledge_item_id,
        rationale="بازبینی دوباره بر پایه شواهد فعلی.",
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=source_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=started_at + timedelta(seconds=1),
            learning_change_id=proposal.learning_change_id,
        )
    )
    with session_factory() as session:
        request_event = session.scalar(
            select(Event).where(
                Event.type == REQUEST_EVENT_TYPE,
                Event.payload["learning_change_id"].as_string()
                == str(proposal.learning_change_id),
            )
        )
        assert request_event is not None
        fixture.extra_task_ids.append(request_event.task_id)
    return proposal.learning_change_id


def _create_revision_proposal(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    fixture: _Fixture,
    knowledge_item_id: UUID,
    *,
    body: str,
) -> UUID:
    with session_factory() as session:
        template = session.get(Task, fixture.distillation_task_id)
        assert template is not None
        task_id = uuid4()
        started_at = datetime.now(timezone.utc)
        session.expunge(template)
    fixture.extra_task_ids.append(task_id)
    with session_factory.begin() as session:
        session.add(
            Task(
                id=task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=template.policy_version,
                objective_id=None,
                plan_id=None,
                plan_action_id=None,
                allowed_writes=["LearningChange"],
                budget=dict(template.budget),
                created_at=started_at,
                completed_at=None,
                max_attempts=template.max_attempts,
            )
        )
        session.flush()
        session.add(
            Event(
                id=uuid4(),
                task_id=task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=started_at,
            )
        )

    def revised_content(prompt: str) -> dict[str, Any]:
        content = _content_from_prompt(prompt)
        content["body"] = body
        return content

    proposal = _distiller(
        session_factory,
        snapshot_store,
        _FakeDistillationProvider(revised_content),
    ).propose_revision(
        task_id,
        [case.evaluation_id for case in fixture.cases],
        knowledge_item_id,
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    return proposal.learning_change_id


def _run_concurrent_approval_decisions(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    principal: TrustedOperatorPrincipal,
    requests: list[LearningChangeDecisionRequest],
) -> list[object]:
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    barrier = Barrier(2)

    def decide_concurrently(request: LearningChangeDecisionRequest) -> object:
        barrier.wait(timeout=30)
        try:
            return adapter.decide_learning_change(principal, request)
        except LearningCommitError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(decide_concurrently, request) for request in requests
        ]
        return [future.result(timeout=60) for future in futures]


def _assert_concurrent_transition_has_one_winner(
    *,
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    fixture: _Fixture,
    operation: Literal["revise", "revalidate"],
    knowledge_item_id: UUID,
    proposal_ids: tuple[UUID, UUID],
    approval_task_ids: tuple[UUID, UUID],
    requests: list[LearningChangeDecisionRequest],
    initial_state: dict[str, Any],
    results: list[object],
) -> None:
    assert len(set(proposal_ids)) == 2
    winners = [
        result
        for result in results
        if not isinstance(result, LearningCommitError)
    ]
    errors = [
        result
        for result in results
        if isinstance(result, LearningCommitError)
    ]
    stale_reason = (
        "knowledge_quality_revision_target_stale"
        if operation == "revise"
        else "knowledge_revalidation_target_stale"
    )
    assert len(winners) == len(errors) == 1
    winner = winners[0]
    assert winner.task_status == "done"
    assert winner.learning_change_id in proposal_ids
    assert str(errors[0]) == stale_reason

    winner_index = proposal_ids.index(winner.learning_change_id)
    loser_index = 1 - winner_index
    loser_id = proposal_ids[loser_index]
    loser_task_id = approval_task_ids[loser_index]
    principal = _approval_principal(fixture.team_id)
    with pytest.raises(LearningCommitError):
        LearningCommitService(session_factory, snapshot_store).decide(
            loser_task_id, 1, principal
        )
    with pytest.raises(TaskNotFinalizable):
        TaskRuntime(session_factory, snapshot_store).finalize(
            TerminalObservation(
                task_id=loser_task_id,
                attempt=1,
                result_category="success_learning_change_accepted",
                observed_at=datetime.now(timezone.utc),
                learning_change_id=loser_id,
            )
        )

    with session_factory() as session:
        item = session.get(KnowledgeItem, knowledge_item_id)
        winner_change = session.get(LearningChange, winner.learning_change_id)
        loser_change = session.get(LearningChange, loser_id)
        winner_task = session.get(Task, approval_task_ids[winner_index])
        loser_task = session.get(Task, loser_task_id)
        assert (
            item is not None
            and winner_change is not None
            and loser_change is not None
            and winner_task is not None
            and loser_task is not None
        )
        assert winner_change.status == "accepted"
        assert winner_change.committed_by_task_id == winner_task.id
        assert winner_change.committed_state is not None
        assert loser_change.status == "proposed"
        assert loser_change.committed_by_task_id is None
        assert loser_change.committed_state is None
        assert winner_task.status == "done"
        assert loser_task.status == "failed"
        assert loser_task.completed_at is None
        assert item.current_learning_change_id == winner_change.id
        assert item.current_learning_change_id != UUID(
            initial_state["current_learning_change_id"]
        )
        assert str(item.origin_learning_change_id) == initial_state[
            "origin_learning_change_id"
        ]
        assert item.version == initial_state["version"] + (
            1 if operation == "revise" else 0
        )
        assert item.status == (
            initial_state["status"] if operation == "revise" else "active"
        )
        assert winner_change.committed_state["state"] == knowledge_item_state(item)

        history = reconstruct_knowledge_item_history(session, item)
        assert history.learning_change_ids == (
            item.origin_learning_change_id,
            winner_change.id,
        )
        assert history.state == knowledge_item_state(item)
        assert len(history.states) == 2

        accepted_changes = list(
            session.scalars(
                select(LearningChange).where(
                    LearningChange.id.in_(proposal_ids),
                    LearningChange.status == "accepted",
                )
            )
        )
        assert [change.id for change in accepted_changes] == [winner_change.id]
        assert session.scalar(
            select(func.count(LearningChange.id)).where(
                LearningChange.id.in_(proposal_ids),
                LearningChange.committed_state.is_not(None),
            )
        ) == 1
        decision_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id.in_(approval_task_ids),
                    Event.type == "learning_change_accepted",
                )
            )
        )
        assert len(decision_events) == 1
        assert decision_events[0].task_id == winner_task.id
        outcomes = list(
            session.scalars(
                select(Outcome).where(
                    Outcome.recorded_by_task_id.in_(approval_task_ids),
                    Outcome.outcome_type == "task_execution",
                )
            )
        )
        assert {outcome.recorded_by_task_id for outcome in outcomes} == set(
            approval_task_ids
        )
        loser_outcome = next(
            outcome for outcome in outcomes
            if outcome.recorded_by_task_id == loser_task_id
        )
        assert loser_outcome.observed_at is not None
        loser_failure_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == loser_task_id,
                    Event.type.in_(("task_attempt_failed", "task_failed")),
                )
            )
        )
        assert {event.type for event in loser_failure_events} == {
            "task_attempt_failed",
            "task_failed",
        }
        assert all(
            event.payload["result_category"] == "terminal_failure"
            and event.payload["failure_reason"] == stale_reason
            and event.payload["outcome_id"] == str(loser_outcome.id)
            for event in loser_failure_events
        )

    with pytest.raises(
        OperatorTaskRequestConflict,
        match=stale_reason,
    ):
        OperatorApplicationAdapter(
            session_factory, snapshot_store
        ).decide_learning_change(principal, requests[loser_index])

    with session_factory() as session:
        item = session.get(KnowledgeItem, knowledge_item_id)
        assert item is not None
        assert item.current_learning_change_id == proposal_ids[winner_index]
        assert item.version == initial_state["version"] + (
            1 if operation == "revise" else 0
        )
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id.in_(approval_task_ids),
                Event.type == "learning_change_accepted",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id.in_(approval_task_ids),
                Outcome.outcome_type == "task_execution",
            )
        ) == 2
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == loser_task_id,
                Event.type == "task_failed",
                Event.payload["failure_reason"].as_string() == stale_reason,
            )
        ) == 1
        loser_task = session.get(Task, loser_task_id)
        assert loser_task is not None and loser_task.status == "failed"
        assert session.scalar(
            select(func.count(LearningChange.id)).where(
                LearningChange.id.in_(proposal_ids),
                LearningChange.committed_state.is_not(None),
            )
        ) == 1


def _create_knowledge_item_cas_fixture(
    session_factory: sessionmaker[Session],
    operation: Literal["revise", "revalidate"],
) -> tuple[UUID, UUID, UUID, tuple[UUID, UUID], int, str]:
    team_id, policy_id, task_id, item_id, origin_change_id = (
        uuid4() for _ in range(5)
    )
    change_ids = (uuid4(), uuid4())
    now = datetime.now(timezone.utc)
    status = "active" if operation == "revise" else "needs_review"
    initial_version = 4
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="knowledge_item_cas_test", status="active"))
        session.flush()
        session.add(
            TeamPolicy(
                id=policy_id,
                team_id=team_id,
                version=1,
                schema_version=1,
                rules={"unchanged": True},
            )
        )
        session.flush()
        session.add(
            Task(
                id=task_id,
                team_id=team_id,
                task_type="propose_learning_change",
                status="done",
                attempt_count=1,
                policy_version=1,
                allowed_writes=["LearningChange"],
                budget={"max_tool_calls": 0, "max_cost_usd": 0.0},
            )
        )
        session.flush()
        session.add(
            LearningChange(
                id=origin_change_id,
                team_id=team_id,
                target_kind="knowledge_item",
                target_id=None,
                operation="create",
                proposed_state={},
                previous_state=None,
                committed_state={},
                evidence_basis=[],
                evidence_basis_hash="sha256:" + ("0" * 64),
                status="accepted",
                idempotency_key=f"cas-origin-{origin_change_id}",
                proposed_by_task_id=task_id,
                committed_by_task_id=task_id,
                operator_id="https://host.example/identity#cas-test",
                decision_reason=None,
                committed_at=now,
            )
        )
        session.flush()
        session.add(
            KnowledgeItem(
                id=item_id,
                team_id=team_id,
                kind="practice",
                title="CAS test item",
                statement="Preserve the expected state during concurrent updates.",
                body="Initial state",
                applicability={},
                preconditions=[],
                assumptions=[],
                limitations=[],
                non_applicability=[],
                failure_modes=[],
                known_counterexamples=[],
                missing_information=[],
                uncertainty=[],
                confidence=Decimal("0.8"),
                status=status,
                version=initial_version,
                last_validated_at=None,
                review_after=now if status == "needs_review" else None,
                origin_learning_change_id=origin_change_id,
                current_learning_change_id=origin_change_id,
                supersedes_item_id=None,
                superseded_by_id=None,
            )
        )
        session.add_all(
            [
                LearningChange(
                    id=change_id,
                    team_id=team_id,
                    target_kind="knowledge_item",
                    target_id=item_id,
                    operation=operation,
                    proposed_state={},
                    previous_state={"state": {"version": initial_version}},
                    committed_state=None,
                    evidence_basis=[],
                    evidence_basis_hash="sha256:" + ("0" * 64),
                    status="proposed",
                    idempotency_key=f"cas-{operation}-{change_id}",
                    proposed_by_task_id=task_id,
                )
                for change_id in change_ids
            ]
        )
    return team_id, item_id, origin_change_id, change_ids, initial_version, status


def _run_knowledge_item_cas_race(
    database_engine,
    session_factory: sessionmaker[Session],
    operation: Literal["revise", "revalidate"],
) -> None:
    team_id, item_id, initial_pointer, change_ids, version, status = (
        _create_knowledge_item_cas_fixture(session_factory, operation)
    )
    barrier = Barrier(2)
    committed_at = datetime.now(timezone.utc)

    def update_item(
        change_id: UUID,
    ) -> tuple[int, UUID, UUID | None, UUID, int, str]:
        with database_engine.connect() as connection, connection.begin():
            backend_pid = connection.exec_driver_sql(
                "SELECT pg_backend_pid()"
            ).scalar_one()
            initial = connection.execute(
                select(
                    KnowledgeItem.current_learning_change_id,
                    KnowledgeItem.version,
                    KnowledgeItem.status,
                ).where(KnowledgeItem.id == item_id)
            ).one()
            assert initial == (initial_pointer, version, status)

            values: dict[str, Any] = {"current_learning_change_id": change_id}
            if operation == "revise":
                values.update(version=version + 1, body=f"Revision {change_id}")
            else:
                values.update(status="active", last_validated_at=committed_at)

            statement = _knowledge_item_cas_statement(
                item_id=item_id,
                team_id=team_id,
                expected_pointer=initial_pointer,
                expected_version=version,
                values=values,
                require_needs_review=operation == "revalidate",
            )
            barrier.wait(timeout=30)
            updated_id = connection.execute(statement).scalar_one_or_none()
            return (
                backend_pid,
                change_id,
                updated_id,
                initial.current_learning_change_id,
                initial.version,
                initial.status,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(update_item, change_id) for change_id in change_ids]
        results = [future.result(timeout=60) for future in futures]

    assert len({result[0] for result in results}) == 2
    assert all(
        result[3:] == (initial_pointer, version, status) for result in results
    )
    winners = [result for result in results if result[2] is not None]
    losers = [result for result in results if result[2] is None]
    assert len(winners) == len(losers) == 1
    assert winners[0][2] == item_id
    winner_id = winners[0][1]
    assert winner_id in change_ids
    with session_factory() as session:
        item = session.get(KnowledgeItem, item_id)
        assert item is not None
        assert item.current_learning_change_id == winner_id
        assert item.version == (version + 1 if operation == "revise" else version)
        assert item.status == ("active" if operation == "revalidate" else status)
        assert item.body == (
            f"Revision {winner_id}" if operation == "revise" else "Initial state"
        )
        if operation == "revalidate":
            assert item.last_validated_at == committed_at


def test_concurrent_revise_knowledge_item_cas_allows_one_update(
    database_engine, session_factory
):
    _run_knowledge_item_cas_race(database_engine, session_factory, "revise")


def test_concurrent_revalidate_knowledge_item_cas_allows_one_update(
    database_engine, session_factory
):
    _run_knowledge_item_cas_race(database_engine, session_factory, "revalidate")


def test_revalidation_proposal_replays_after_task_completion(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(
        2, include_contrary=False, review_interval_days=1
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    approval_task_id, approval_attempt, principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    committed = LearningCommitService(session_factory, snapshot_store).decide(
        approval_task_id, approval_attempt, principal
    )
    assert committed.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=approval_task_id,
            attempt=approval_attempt,
            result_category="success_learning_change_accepted",
            observed_at=committed.committed_at,
            learning_change_id=committed.learning_change_id,
        )
    )

    source_task_id, change_id = _create_revalidation_proposal(
        session_factory,
        snapshot_store,
        fixture,
        committed.knowledge_item_id,
    )
    evaluation_ids = [case.evaluation_id for case in fixture.cases]
    rationale = "بازبینی دوباره بر پایه شواهد فعلی."
    with session_factory() as session:
        task = session.get(Task, source_task_id)
        assert task is not None and task.status == "done"
        before_changes = session.scalar(
            select(func.count(LearningChange.id)).where(
                LearningChange.proposed_by_task_id == source_task_id
            )
        )
        before_events = session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == source_task_id,
                Event.type == "learning_change_proposed",
            )
        )

    distiller = ExperienceDistiller(
        session_factory,
        snapshot_store,
        provider=None,
        cost_service=TaskGenerationCostService(session_factory),
    )
    replay = distiller.propose_revalidation(
        source_task_id,
        evaluation_ids,
        committed.knowledge_item_id,
        rationale=rationale,
    )
    assert replay.replayed is True
    assert replay.learning_change_id == change_id

    with pytest.raises(
        ExperienceDistillerConflict,
        match="learning_change_task_basis_conflict",
    ):
        distiller.propose_revalidation(
            source_task_id,
            evaluation_ids,
            committed.knowledge_item_id,
            rationale="A conflicting rationale must not reuse the proposal.",
        )

    with session_factory() as session:
        assert session.scalar(
            select(func.count(LearningChange.id)).where(
                LearningChange.proposed_by_task_id == source_task_id
            )
        ) == before_changes
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == source_task_id,
                Event.type == "learning_change_proposed",
            )
        ) == before_events


def test_revise_then_revalidate_rejects_stale_pre_revision_assessment(
    session_factory,
    snapshot_store,
    distillation_fixture,
    monkeypatch,
):
    fixture = distillation_fixture(
        2, include_contrary=False, review_interval_days=1
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    create_task_id, create_attempt, principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    created = LearningCommitService(session_factory, snapshot_store).decide(
        create_task_id, create_attempt, principal
    )
    assert created.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=create_task_id,
            attempt=create_attempt,
            result_category="success_learning_change_accepted",
            observed_at=created.committed_at,
            learning_change_id=created.learning_change_id,
        )
    )

    class FakeEmbeddingProvider:
        space = EmbeddingSpace(
            provider="watch_test",
            model="g4-deterministic",
            revision="1",
            dimensions=3,
            configuration="g4-regression",
        )

        def current_space(self):
            return self.space

        def embed(self, texts):
            return EmbeddingBatch(
                space=self.space,
                vectors=tuple((0.1, 0.2, 0.3) for _ in texts),
            )

    embedding_provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(session_factory, embedding_provider)
    retriever = HybridKnowledgeRetriever(
        session_factory, snapshot_store, embedding_provider
    )
    assert indexer.index_knowledge_item(created.knowledge_item_id).outcome == "indexed"
    assert retriever.retrieve(fixture.team_id, "source evidence")

    stale_source_task_id, stale_revalidation_id = _create_revalidation_proposal(
        session_factory,
        snapshot_store,
        fixture,
        created.knowledge_item_id,
    )
    stale_assessment_task_id = KnowledgeRevalidationAssessmentService(
        session_factory, snapshot_store
    ).create_task(stale_revalidation_id)
    fixture.extra_task_ids.append(stale_assessment_task_id)
    stale_assessment_result = KnowledgeRevalidationAssessmentTaskRunner(
        session_factory,
        snapshot_store,
        _FakeKnowledgeRevalidationProvider(),
    ).run(stale_assessment_task_id)
    assert stale_assessment_result.status == "done"
    assert stale_assessment_result.assessment_id is not None

    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        stale_assessment = session.get(
            KnowledgeRevalidationAssessment,
            stale_assessment_result.assessment_id,
        )
        assert item is not None and item.status == "needs_review"
        assert stale_assessment is not None
        assert stale_assessment.current_learning_change_id == created.learning_change_id
        assert stale_assessment.target_content_version == item.version == 1
        stale_target_hash = stale_assessment.target_content_hash
        stale_target_state_hash = stale_assessment.target_state_hash
        review_after = item.review_after
        assert review_after is not None

    # D7 makes the item ineligible without rewriting its existing projection.
    assert retriever.retrieve(fixture.team_id, "source evidence") == ()

    revision_id = _create_revision_proposal(
        session_factory,
        snapshot_store,
        fixture,
        created.knowledge_item_id,
        body=(
            "The revised practice preserves source evidence and records a "
            "distinct observation before drawing a conclusion."
        ),
    )
    _run_quality_assessment(session_factory, snapshot_store, revision_id)
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    revision_request = LearningChangeDecisionRequest(
        learning_change_id=revision_id,
        decision="accept",
        idempotency_key=uuid4(),
    )

    import core.learning_commit as learning_commit

    revision_committed_at = review_after + timedelta(seconds=3)

    class RevisionCommitDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return (
                revision_committed_at
                if tz is not None
                else revision_committed_at.replace(tzinfo=None)
            )

    with monkeypatch.context() as patch:
        patch.setattr(
            learning_commit,
            "datetime",
            SimpleNamespace(
                datetime=RevisionCommitDateTime,
                timezone=timezone,
                timedelta=timedelta,
            ),
        )
        revised = adapter.decide_learning_change(principal, revision_request)

    assert revised.learning_change_status == "accepted"
    assert revised.task_status == "done"
    assert revised.knowledge_item_id == created.knowledge_item_id
    assert not revised.replayed

    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        revision = session.get(LearningChange, revision_id)
        assert item is not None and revision is not None
        revised_state = knowledge_item_state(item)
        revised_hash = knowledge_item_content_hash(item)
        assert item.status == "needs_review"
        assert item.current_learning_change_id == revision_id
        assert item.version == 2
        assert item.last_validated_at is None
        assert revised_hash != stale_target_hash
        assert revision.previous_state is not None
        assert revision.previous_state["state"]["status"] == "needs_review"
        assert revision.committed_state is not None
        assert revision.committed_state["state"] == revised_state

        projection_state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item.id
            )
        )
        projection_chunk = session.scalar(
            select(TeamExperienceChunk).where(
                TeamExperienceChunk.knowledge_item_id == item.id
            )
        )
        assert projection_state is not None and projection_chunk is not None
        assert projection_state.status == "published"
        assert projection_state.current_learning_change_id == created.learning_change_id
        assert projection_chunk.current_learning_change_id == created.learning_change_id

    stale_request = LearningChangeDecisionRequest(
        learning_change_id=stale_revalidation_id,
        decision="accept",
        idempotency_key=uuid4(),
    )
    with pytest.raises(
        LearningChangeNotApprovable,
        match="knowledge_revalidation_target_stale",
    ):
        adapter.request_learning_change_decision(principal, stale_request)

    with session_factory() as session:
        stale_change = session.get(LearningChange, stale_revalidation_id)
        stale_assessment = session.get(
            KnowledgeRevalidationAssessment,
            stale_assessment_result.assessment_id,
        )
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        assert stale_change is not None and stale_assessment is not None
        assert item is not None
        assert stale_change.status == "proposed"
        assert stale_change.committed_by_task_id is None
        assert stale_change.committed_state is None
        assert stale_assessment.current_learning_change_id == created.learning_change_id
        assert stale_assessment.target_content_version == 1
        assert stale_assessment.target_content_hash == stale_target_hash
        assert stale_assessment.target_state_hash == stale_target_state_hash
        assert item.current_learning_change_id == revision_id
        assert item.version == 2
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.type == "operator_task_requested",
                Event.payload["learning_change_id"].as_string()
                == str(stale_revalidation_id),
            )
        ) == 0
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == stale_source_task_id,
                Event.type == "learning_change_accepted",
            )
        ) == 0

    _, fresh_revalidation_id = _create_revalidation_proposal(
        session_factory,
        snapshot_store,
        fixture,
        created.knowledge_item_id,
        perform_review=False,
    )
    fresh_assessment_task_id = KnowledgeRevalidationAssessmentService(
        session_factory, snapshot_store
    ).create_task(fresh_revalidation_id)
    fixture.extra_task_ids.append(fresh_assessment_task_id)
    fresh_assessment_result = KnowledgeRevalidationAssessmentTaskRunner(
        session_factory,
        snapshot_store,
        _FakeKnowledgeRevalidationProvider(),
    ).run(fresh_assessment_task_id)
    assert fresh_assessment_result.status == "done"
    assert fresh_assessment_result.assessment_id is not None

    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        fresh_assessment = session.get(
            KnowledgeRevalidationAssessment,
            fresh_assessment_result.assessment_id,
        )
        assert item is not None and fresh_assessment is not None
        assert item.status == "needs_review"
        assert fresh_assessment.current_learning_change_id == revision_id
        assert fresh_assessment.target_content_version == item.version == 2
        assert fresh_assessment.target_content_hash == revised_hash
        assert fresh_assessment.target_state_hash == encode_state_snapshot(
            revised_state
        )["snapshot_hash"]

    fresh_request = LearningChangeDecisionRequest(
        learning_change_id=fresh_revalidation_id,
        decision="accept",
        idempotency_key=uuid4(),
    )
    revalidation_committed_at = revision_committed_at + timedelta(minutes=1)

    class RevalidationCommitDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return (
                revalidation_committed_at
                if tz is not None
                else revalidation_committed_at.replace(tzinfo=None)
            )

    with monkeypatch.context() as patch:
        patch.setattr(
            learning_commit,
            "datetime",
            SimpleNamespace(
                datetime=RevalidationCommitDateTime,
                timezone=timezone,
                timedelta=timedelta,
            ),
        )
        revalidated = adapter.decide_learning_change(principal, fresh_request)

    assert revalidated.learning_change_status == "accepted"
    assert revalidated.task_status == "done"
    assert revalidated.knowledge_item_id == created.knowledge_item_id
    assert not revalidated.replayed
    assert retriever.retrieve(fixture.team_id, "revised practice") == ()

    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        fresh_change = session.get(LearningChange, fresh_revalidation_id)
        assert item is not None and fresh_change is not None
        final_state = knowledge_item_state(item)
        assert item.status == "active"
        assert item.current_learning_change_id == fresh_revalidation_id
        assert item.version == 2
        assert knowledge_item_content_hash(item) == revised_hash
        assert item.body == revised_state["body"]
        assert fresh_change.previous_state is not None
        assert fresh_change.previous_state["state"] == revised_state
        assert fresh_change.committed_state is not None
        assert fresh_change.committed_state["state"] == final_state

        history = reconstruct_knowledge_item_history(session, item)
        assert history.learning_change_ids == (
            created.learning_change_id,
            revision_id,
            fresh_revalidation_id,
        )
        assert len(history.applied_review_event_ids) == 1
        assert history.states[1]["status"] == "needs_review"
        assert history.states[2]["status"] == "active"
        assert history.state == final_state

        projection_state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item.id
            )
        )
        projection_chunk = session.scalar(
            select(TeamExperienceChunk).where(
                TeamExperienceChunk.knowledge_item_id == item.id
            )
        )
        assert projection_state is not None and projection_chunk is not None
        assert projection_state.current_learning_change_id == created.learning_change_id
        assert projection_chunk.current_learning_change_id == created.learning_change_id

    assert indexer.index_knowledge_item(created.knowledge_item_id).outcome == "indexed"
    passages = retriever.retrieve(fixture.team_id, "revised practice")
    assert passages
    assert all(
        passage.knowledge_item_id == created.knowledge_item_id
        and passage.knowledge_item_version == 2
        and passage.current_learning_change_id == fresh_revalidation_id
        for passage in passages
    )


def test_operator_commits_and_recovers_revalidation_after_finalize_crash(
    session_factory,
    snapshot_store,
    distillation_fixture,
    monkeypatch,
):
    fixture = distillation_fixture(
        2, include_contrary=False, review_interval_days=1
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    create_task_id, create_attempt, create_principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    created = LearningCommitService(session_factory, snapshot_store).decide(
        create_task_id, create_attempt, create_principal
    )
    assert created.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=create_task_id,
            attempt=create_attempt,
            result_category="success_learning_change_accepted",
            observed_at=created.committed_at,
            learning_change_id=created.learning_change_id,
        )
    )

    _, revalidation_change_id = _create_revalidation_proposal(
        session_factory,
        snapshot_store,
        fixture,
        created.knowledge_item_id,
    )
    assessment_task_id = KnowledgeRevalidationAssessmentService(
        session_factory, snapshot_store
    ).create_task(revalidation_change_id)
    fixture.extra_task_ids.append(assessment_task_id)
    assessment_result = KnowledgeRevalidationAssessmentTaskRunner(
        session_factory,
        snapshot_store,
        _FakeKnowledgeRevalidationProvider(),
    ).run(assessment_task_id)
    assert assessment_result.status == "done"

    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        assert item is not None and item.status == "needs_review"
        original_state = knowledge_item_state(item)
        original_content_hash = knowledge_item_content_hash(item)
        original_review_after = item.review_after
        assert original_review_after is not None

    principal = _approval_principal(fixture.team_id)
    request = LearningChangeDecisionRequest(
        learning_change_id=revalidation_change_id,
        decision="accept",
        idempotency_key=uuid4(),
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    request_result = adapter.request_learning_change_decision(principal, request)
    captured: list[TerminalObservation] = []

    import core.learning_commit as learning_commit

    review_commit_at = original_review_after + timedelta(seconds=3)

    class ReviewCommitDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return review_commit_at
            return review_commit_at.replace(tzinfo=None)

    def crash_before_finalize(
        task_runtime: TaskRuntime, observation: TerminalObservation
    ):
        captured.append(observation)
        raise RuntimeError("simulated process loss after revalidation commit")

    with monkeypatch.context() as patch:
        patch.setattr(
            learning_commit,
            "datetime",
            SimpleNamespace(
                datetime=ReviewCommitDateTime,
                timezone=timezone,
                timedelta=timedelta,
            ),
        )
        patch.setattr(TaskRuntime, "finalize", crash_before_finalize)
        with pytest.raises(RuntimeError, match="simulated process loss"):
            adapter.decide_learning_change(principal, request)

    assert len(captured) == 1
    assert captured[0].task_id == request_result.task_id
    assert captured[0].learning_change_id == revalidation_change_id
    assert captured[0].result_category == "success_learning_change_accepted"

    with session_factory() as session:
        task = session.get(Task, request_result.task_id)
        change = session.get(LearningChange, revalidation_change_id)
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        request_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == request_result.task_id,
                    Event.type == "operator_task_requested",
                )
            )
        )
        decision_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == request_result.task_id,
                    Event.type == "learning_change_accepted",
                )
            )
        )
        outcomes = list(
            session.scalars(
                select(Outcome).where(
                    Outcome.recorded_by_task_id == request_result.task_id,
                    Outcome.outcome_type == "task_execution",
                )
            )
        )
        assert task is not None and task.status == "running"
        assert change is not None and change.status == "accepted"
        assert change.committed_by_task_id == request_result.task_id
        assert item is not None and item.status == "active"
        assert item.current_learning_change_id == revalidation_change_id
        assert item.version == original_state["version"]
        assert knowledge_item_content_hash(item) == original_content_hash
        assert len(request_events) == 1
        assert len(decision_events) == 1
        assert outcomes == []
        original_request_payload = dict(request_events[0].payload)
        original_decision_payload = dict(decision_events[0].payload)
        binding = original_request_payload["approval_binding"]
        assert decision_events[0].payload["knowledge_revalidation_assessment_id"] == (
            binding["assessment_id"]
        )
        assert decision_events[0].payload["knowledge_revalidation_assessment_hash"] == (
            binding["assessment_payload_hash"]
        )
        committed_item_state = knowledge_item_state(item)
        committed_at = change.committed_at
        assert committed_at == review_commit_at
        assert item.last_validated_at == committed_at
        assert item.review_after == committed_at + timedelta(days=1)

    now = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        start_event = session.scalar(
            select(Event).where(
                Event.task_id == request_result.task_id,
                Event.type == "task_started",
            )
        )
        assert start_event is not None
        start_event.created_at = now - timedelta(seconds=61)

    recovery = runtime.recover_interrupted(now=now)
    assert recovery.completed == (request_result.task_id,)
    assert recovery.retried == ()
    assert recovery.failed == ()

    with session_factory() as session:
        task = session.get(Task, request_result.task_id)
        change = session.get(LearningChange, revalidation_change_id)
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        request_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == request_result.task_id,
                    Event.type == "operator_task_requested",
                )
            )
        )
        decision_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == request_result.task_id,
                    Event.type == "learning_change_accepted",
                )
            )
        )
        terminal_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == request_result.task_id,
                    Event.type.in_({"task_completed", "task_failed"}),
                )
            )
        )
        outcomes = list(
            session.scalars(
                select(Outcome).where(
                    Outcome.recorded_by_task_id == request_result.task_id,
                    Outcome.outcome_type == "task_execution",
                )
            )
        )
        assert task is not None and task.status == "done"
        assert task.attempt_count == 1
        assert change is not None and change.status == "accepted"
        assert change.committed_by_task_id == request_result.task_id
        assert item is not None
        assert knowledge_item_state(item) == committed_item_state
        assert len(request_events) == 1
        assert request_events[0].payload == original_request_payload
        assert len(decision_events) == 1
        assert decision_events[0].payload == original_decision_payload
        assert len(terminal_events) == 1
        assert terminal_events[0].type == "task_completed"
        assert len(outcomes) == 1
        outcome = outcomes[0]
        assert outcome.observation_snapshot_ref is not None
        assert outcome.observation_hash is not None
        assert snapshot_store.read(outcome.observation_snapshot_ref)

    repeated_recovery = runtime.recover_interrupted(
        now=now + timedelta(seconds=61)
    )
    assert repeated_recovery.completed == ()
    assert repeated_recovery.retried == ()
    assert repeated_recovery.failed == ()

    replay = runtime.finalize(captured[0])
    assert replay.replayed is True
    with session_factory() as session:
        assert session.scalar(
            select(func.count()).select_from(Outcome).where(
                Outcome.recorded_by_task_id == request_result.task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(Event).where(
                Event.task_id == request_result.task_id,
                Event.type == "learning_change_accepted",
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(Event).where(
                Event.task_id == request_result.task_id,
                Event.type == "task_completed",
            )
        ) == 1


def test_original_revalidation_approval_replays_after_later_history_transition(
    session_factory,
    snapshot_store,
    distillation_fixture,
    monkeypatch,
):
    fixture = distillation_fixture(
        2, include_contrary=False, review_interval_days=1
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    create_task_id, attempt, principal = _create_admitted_approval_task(
        session_factory, snapshot_store, fixture.team_id, proposal.learning_change_id
    )
    created = LearningCommitService(session_factory, snapshot_store).decide(
        create_task_id, attempt, principal
    )
    assert created.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=create_task_id,
            attempt=attempt,
            result_category="success_learning_change_accepted",
            observed_at=created.committed_at,
            learning_change_id=created.learning_change_id,
        )
    )

    _, revalidation_id = _create_revalidation_proposal(
        session_factory, snapshot_store, fixture, created.knowledge_item_id
    )
    assessment_task_id = KnowledgeRevalidationAssessmentService(
        session_factory, snapshot_store
    ).create_task(revalidation_id)
    fixture.extra_task_ids.append(assessment_task_id)
    assessment = KnowledgeRevalidationAssessmentTaskRunner(
        session_factory,
        snapshot_store,
        _FakeKnowledgeRevalidationProvider(),
    ).run(assessment_task_id)
    assert assessment.status == "done"

    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    revalidation_request = LearningChangeDecisionRequest(
        learning_change_id=revalidation_id,
        decision="accept",
        idempotency_key=uuid4(),
    )
    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        assert item is not None and item.review_after is not None
        review_after = item.review_after

    import core.learning_commit as learning_commit

    revalidation_committed_at = review_after + timedelta(seconds=3)

    class RevalidationCommitDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return (
                revalidation_committed_at
                if tz is not None
                else revalidation_committed_at.replace(tzinfo=None)
            )

    with monkeypatch.context() as patch:
        patch.setattr(
            learning_commit,
            "datetime",
            SimpleNamespace(
                datetime=RevalidationCommitDateTime,
                timezone=timezone,
                timedelta=timedelta,
            ),
        )
        original = adapter.decide_learning_change(principal, revalidation_request)

    assert original.learning_change_status == "accepted"
    assert original.task_status == "done"
    assert original.knowledge_item_id == created.knowledge_item_id
    assert not original.replayed

    revision_id = _create_revision_proposal(
        session_factory,
        snapshot_store,
        fixture,
        created.knowledge_item_id,
        body="A later accepted revision remains the current item state.",
    )
    _run_quality_assessment(session_factory, snapshot_store, revision_id)
    revision_request = LearningChangeDecisionRequest(
        learning_change_id=revision_id,
        decision="accept",
        idempotency_key=uuid4(),
    )
    later_committed_at = original.committed_at + timedelta(minutes=1)

    class LaterCommitDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return (
                later_committed_at
                if tz is not None
                else later_committed_at.replace(tzinfo=None)
            )

    with monkeypatch.context() as patch:
        patch.setattr(
            learning_commit,
            "datetime",
            SimpleNamespace(
                datetime=LaterCommitDateTime,
                timezone=timezone,
                timedelta=timedelta,
            ),
        )
        later = adapter.decide_learning_change(principal, revision_request)

    assert later.learning_change_status == "accepted"
    assert later.task_status == "done"
    assert later.knowledge_item_id == created.knowledge_item_id
    assert not later.replayed

    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        assert item is not None
        later_state = knowledge_item_state(item)
        assert item.current_learning_change_id == revision_id
        assert item.version == 2
        assert item.body == "A later accepted revision remains the current item state."

    replay = adapter.decide_learning_change(principal, revalidation_request)
    assert replay.replayed
    assert replay.task_id == original.task_id
    assert replay.learning_change_id == original.learning_change_id
    assert replay.knowledge_item_id == original.knowledge_item_id
    assert replay.committed_at == original.committed_at
    assert original.outcome_id is not None
    assert replay.outcome_id == original.outcome_id

    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        original_change = session.get(LearningChange, revalidation_id)
        later_change = session.get(LearningChange, revision_id)
        assert item is not None and original_change is not None
        assert later_change is not None
        assert knowledge_item_state(item) == later_state
        assert item.current_learning_change_id == revision_id
        assert original_change.status == later_change.status == "accepted"
        assert original_change.committed_by_task_id == original.task_id
        assert later_change.committed_by_task_id == later.task_id
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == original.task_id,
                Event.type == "operator_task_requested",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == original.task_id,
                Event.type == "learning_change_accepted",
            )
        ) == 1
        terminal_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == original.task_id,
                    Event.type.in_({"task_completed", "task_failed"}),
                )
            )
        )
        assert len(terminal_events) == 1
        assert terminal_events[0].type == "task_completed"

        original_outcomes = list(
            session.scalars(
                select(Outcome).where(
                    Outcome.recorded_by_task_id == original.task_id,
                    Outcome.outcome_type == "task_execution",
                )
            )
        )
        assert len(original_outcomes) == 1
        assert original_outcomes[0].id == original.outcome_id == replay.outcome_id
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == later.task_id,
                Event.type == "learning_change_accepted",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == later.task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) == 1


def test_concurrent_revise_approvals_advance_one_knowledge_item_once(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(2, include_contrary=False)
    runtime = TaskRuntime(session_factory, snapshot_store)
    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    create_task_id, create_attempt, principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    created = LearningCommitService(session_factory, snapshot_store).decide(
        create_task_id, create_attempt, principal
    )
    assert created.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=create_task_id,
            attempt=create_attempt,
            result_category="success_learning_change_accepted",
            observed_at=created.committed_at,
            learning_change_id=created.learning_change_id,
        )
    )

    proposal_ids = (
        _create_revision_proposal(
            session_factory,
            snapshot_store,
            fixture,
            created.knowledge_item_id,
            body="The first revision records an evidence-linked practice.",
        ),
        _create_revision_proposal(
            session_factory,
            snapshot_store,
            fixture,
            created.knowledge_item_id,
            body="The competing revision records a different evidence-linked practice.",
        ),
    )
    assessment_ids = tuple(
        _run_quality_assessment(session_factory, snapshot_store, change_id)
        for change_id in proposal_ids
    )
    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        changes = [
            session.get(LearningChange, change_id) for change_id in proposal_ids
        ]
        assert item is not None
        initial_state = knowledge_item_state(item)
        assert all(
            change is not None
            and change.status == "proposed"
            and change.previous_state is not None
            and change.previous_state["state"] == initial_state
            for change in changes
        )
        assert len(set(assessment_ids)) == 2
        assert all(
            session.get(KnowledgeQualityAssessment, assessment_id) is not None
            for assessment_id in assessment_ids
        )

    requests = [
        LearningChangeDecisionRequest(
            learning_change_id=change_id,
            decision="accept",
            idempotency_key=uuid4(),
        )
        for change_id in proposal_ids
    ]
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    approval_task_ids = tuple(
        adapter.request_learning_change_decision(principal, request).task_id
        for request in requests
    )
    for task_id in approval_task_ids:
        assert runtime.admit(task_id).attempt_count == 1
    with session_factory() as session:
        for task_id, change_id, assessment_id in zip(
            approval_task_ids, proposal_ids, assessment_ids
        ):
            request_event = session.scalar(
                select(Event).where(
                    Event.task_id == task_id,
                    Event.type == "operator_task_requested",
                )
            )
            assessment = session.get(KnowledgeQualityAssessment, assessment_id)
            assert request_event is not None and assessment is not None
            binding = request_event.payload["approval_binding"]
            assert binding["learning_change_id"] == str(change_id)
            assert binding["assessment_type"] == "knowledge_quality"
            assert binding["assessment_id"] == str(assessment.id)
            assert (
                binding["assessment_payload_hash"]
                == assessment.assessment_payload_hash
            )

    results = _run_concurrent_approval_decisions(
        session_factory,
        snapshot_store,
        principal,
        requests,
    )
    _assert_concurrent_transition_has_one_winner(
        session_factory=session_factory,
        snapshot_store=snapshot_store,
        fixture=fixture,
        operation="revise",
        knowledge_item_id=created.knowledge_item_id,
        proposal_ids=proposal_ids,
        approval_task_ids=approval_task_ids,
        requests=requests,
        initial_state=initial_state,
        results=results,
    )


def test_concurrent_revalidate_approvals_advance_one_knowledge_item_once(
    session_factory,
    snapshot_store,
    distillation_fixture,
    monkeypatch,
):
    fixture = distillation_fixture(
        2, include_contrary=False, review_interval_days=1
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    create_task_id, create_attempt, principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    created = LearningCommitService(session_factory, snapshot_store).decide(
        create_task_id, create_attempt, principal
    )
    assert created.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=create_task_id,
            attempt=create_attempt,
            result_category="success_learning_change_accepted",
            observed_at=created.committed_at,
            learning_change_id=created.learning_change_id,
        )
    )

    _, first_change_id = _create_revalidation_proposal(
        session_factory,
        snapshot_store,
        fixture,
        created.knowledge_item_id,
    )
    second_change_id = _create_additional_revalidation_proposal(
        session_factory,
        snapshot_store,
        fixture,
        created.knowledge_item_id,
    )
    proposal_ids = (first_change_id, second_change_id)
    assessment_service = KnowledgeRevalidationAssessmentService(
        session_factory, snapshot_store
    )
    assessment_runner = KnowledgeRevalidationAssessmentTaskRunner(
        session_factory,
        snapshot_store,
        _FakeKnowledgeRevalidationProvider(),
    )
    assessment_ids: list[UUID] = []
    for change_id in proposal_ids:
        assessment_task_id = assessment_service.create_task(change_id)
        fixture.extra_task_ids.append(assessment_task_id)
        assessment_result = assessment_runner.run(assessment_task_id)
        assert assessment_result.status == "done"
        assert assessment_result.assessment_id is not None
        assessment_ids.append(assessment_result.assessment_id)

    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        changes = [
            session.get(LearningChange, change_id) for change_id in proposal_ids
        ]
        assert item is not None and item.status == "needs_review"
        initial_state = knowledge_item_state(item)
        assert all(
            change is not None
            and change.status == "proposed"
            and change.previous_state is not None
            and change.previous_state["state"] == initial_state
            for change in changes
        )
        assert len(set(assessment_ids)) == 2
        assert all(
            session.get(KnowledgeRevalidationAssessment, assessment_id) is not None
            for assessment_id in assessment_ids
        )

    requests = [
        LearningChangeDecisionRequest(
            learning_change_id=change_id,
            decision="accept",
            idempotency_key=uuid4(),
        )
        for change_id in proposal_ids
    ]
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    approval_task_ids = tuple(
        adapter.request_learning_change_decision(principal, request).task_id
        for request in requests
    )
    for task_id in approval_task_ids:
        assert runtime.admit(task_id).attempt_count == 1
    with session_factory() as session:
        for task_id, change_id, assessment_id in zip(
            approval_task_ids, proposal_ids, assessment_ids
        ):
            request_event = session.scalar(
                select(Event).where(
                    Event.task_id == task_id,
                    Event.type == "operator_task_requested",
                )
            )
            assessment = session.get(
                KnowledgeRevalidationAssessment, assessment_id
            )
            assert request_event is not None and assessment is not None
            binding = request_event.payload["approval_binding"]
            assert binding["learning_change_id"] == str(change_id)
            assert binding["assessment_type"] == "knowledge_revalidation"
            assert binding["assessment_id"] == str(assessment.id)
            assert binding["assessment_payload_hash"] == assessment.payload_hash

    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        assert item is not None and item.review_after is not None
        committed_at = item.review_after + timedelta(seconds=3)

    import core.learning_commit as learning_commit

    class ReviewCommitDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return committed_at
            return committed_at.replace(tzinfo=None)

    with monkeypatch.context() as patch:
        patch.setattr(
            learning_commit,
            "datetime",
            SimpleNamespace(
                datetime=ReviewCommitDateTime,
                timezone=timezone,
                timedelta=timedelta,
            ),
        )
        results = _run_concurrent_approval_decisions(
            session_factory,
            snapshot_store,
            principal,
            requests,
        )
    _assert_concurrent_transition_has_one_winner(
        session_factory=session_factory,
        snapshot_store=snapshot_store,
        fixture=fixture,
        operation="revalidate",
        knowledge_item_id=created.knowledge_item_id,
        proposal_ids=proposal_ids,
        approval_task_ids=approval_task_ids,
        requests=requests,
        initial_state=initial_state,
        results=results,
    )


def test_rejected_revalidation_does_not_mutate_the_knowledge_item(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(
        2, include_contrary=False, review_interval_days=1
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    create_task_id, create_attempt, create_principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    created = LearningCommitService(session_factory, snapshot_store).decide(
        create_task_id, create_attempt, create_principal
    )
    assert created.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=create_task_id,
            attempt=create_attempt,
            result_category="success_learning_change_accepted",
            observed_at=created.committed_at,
            learning_change_id=created.learning_change_id,
        )
    )

    _, revalidation_change_id = _create_revalidation_proposal(
        session_factory,
        snapshot_store,
        fixture,
        created.knowledge_item_id,
    )
    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        assert item is not None
        original_state = knowledge_item_state(item)
        original_content_hash = knowledge_item_content_hash(item)

    principal = _approval_principal(fixture.team_id)
    rejection_reason = (
        "The current evidence does not justify restoring active status."
    )
    request = LearningChangeDecisionRequest(
        learning_change_id=revalidation_change_id,
        decision="reject",
        idempotency_key=uuid4(),
        rejection_reason=rejection_reason,
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    original = adapter.decide_learning_change(principal, request)

    assert original.decision == "reject"
    assert original.learning_change_status == "rejected"
    assert original.task_status == "done"
    assert original.knowledge_item_id is None
    assert original.outcome_id is not None
    assert not original.replayed

    def assert_durable_rejection():
        with session_factory() as session:
            item = session.get(KnowledgeItem, created.knowledge_item_id)
            change = session.get(LearningChange, revalidation_change_id)
            assert item is not None and change is not None
            assert knowledge_item_state(item) == original_state
            assert knowledge_item_content_hash(item) == original_content_hash
            assert change.status == "rejected"
            assert change.operation == "revalidate"
            assert change.committed_state is None
            assert change.decision_reason == rejection_reason
            assert change.committed_by_task_id == original.task_id
            assert change.operator_id == original.operator_id
            assert change.committed_at == original.committed_at

            request_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == original.task_id,
                        Event.type == "operator_task_requested",
                    )
                )
            )
            rejection_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == original.task_id,
                        Event.type == "learning_change_rejected",
                    )
                )
            )
            terminal_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == original.task_id,
                        Event.type.in_({"task_completed", "task_failed"}),
                    )
                )
            )
            outcomes = list(
                session.scalars(
                    select(Outcome).where(
                        Outcome.recorded_by_task_id == original.task_id,
                        Outcome.outcome_type == "task_execution",
                    )
                )
            )
            assert len(request_events) == 1
            assert session.scalar(
                select(func.count(Event.id)).where(
                    Event.type == "operator_task_requested",
                    Event.payload["learning_change_id"].as_string()
                    == str(revalidation_change_id),
                )
            ) == 1
            assert len(rejection_events) == 1
            assert len(terminal_events) == 1
            assert terminal_events[0].type == "task_completed"
            assert len(outcomes) == 1
            assert outcomes[0].id == original.outcome_id

            payload = rejection_events[0].payload
            assert payload["learning_change_id"] == str(revalidation_change_id)
            assert payload["decision"] == "reject"
            assert payload["operator_id"] == original.operator_id
            assert payload["approval_task_id"] == str(original.task_id)
            assert payload["reason"] == rejection_reason
            assert payload["committed_at"] == original.committed_at.isoformat()

            assert session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == original.task_id,
                    Event.type == "learning_change_accepted",
                )
            ) == 0

    assert_durable_rejection()

    replay = adapter.decide_learning_change(principal, request)
    assert replay.replayed
    assert replay.task_id == original.task_id
    assert replay.learning_change_id == original.learning_change_id
    assert replay.decision == original.decision
    assert replay.learning_change_status == original.learning_change_status
    assert replay.task_status == original.task_status
    assert replay.operator_id == original.operator_id
    assert replay.committed_at == original.committed_at
    assert replay.outcome_id == original.outcome_id

    # Re-reading the durable state after replay proves that the retry added no
    # request, decision, terminal Event, Outcome, or canonical KnowledgeItem write.
    assert_durable_rejection()



@pytest.mark.parametrize(
    ("invalid_draft_case", "expected_failure_reason"),
    [
        (
            "invented_reference",
            "knowledge_revalidation_finding_reference_not_in_basis",
        ),
        (
            "cross_team_reference",
            "knowledge_revalidation_finding_reference_not_in_basis",
        ),
        (
            "omitted_evidence_link",
            "knowledge_revalidation_evidence_link_omitted",
        ),
        (
            "freshness_mismatch",
            "knowledge_revalidation_freshness_disposition_mismatch",
        ),
        ("extra_fields", "knowledge_revalidation_draft_invalid"),
        ("malformed_shape", "knowledge_revalidation_draft_invalid"),
        ("missing_required_field", "knowledge_revalidation_draft_invalid"),
        (
            "invalid_evaluator_identity",
            "knowledge_revalidation_evaluator_identity_invalid",
        ),
        (
            "invalid_evaluator_revision",
            "knowledge_revalidation_evaluator_identity_invalid",
        ),
    ],
)
def test_revalidation_rejects_untrusted_provider_draft_without_record_and_recovers(
    session_factory,
    snapshot_store,
    distillation_fixture,
    request,
    invalid_draft_case: str,
    expected_failure_reason: str,
):
    from core.knowledge_revalidation import (
        RECORDED_EVENT_TYPE,
        assessment_payload_hash,
    )

    fixture = distillation_fixture(
        2, include_contrary=False, review_interval_days=1
    )
    foreign_fixture = distillation_fixture(1, include_contrary=False)
    with session_factory() as session:
        foreign_link = session.scalar(
            select(EvidenceLink)
            .where(
                EvidenceLink.team_id == foreign_fixture.team_id,
                EvidenceLink.subject_id == foreign_fixture.cases[0].evaluation_id,
            )
            .order_by(EvidenceLink.reference_key)
        )
        assert foreign_link is not None
        foreign_evidence_reference = f"evidence_link:{foreign_link.reference_key}"

    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    approval_task_id, approval_attempt, principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    committed = LearningCommitService(session_factory, snapshot_store).decide(
        approval_task_id, approval_attempt, principal
    )
    assert committed.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=approval_task_id,
            attempt=approval_attempt,
            result_category="success_learning_change_accepted",
            observed_at=committed.committed_at,
            learning_change_id=committed.learning_change_id,
        )
    )

    source_task_id, revalidation_change_id = _create_revalidation_proposal(
        session_factory,
        snapshot_store,
        fixture,
        committed.knowledge_item_id,
    )
    revalidation_service = KnowledgeRevalidationAssessmentService(
        session_factory, snapshot_store
    )
    task_id = revalidation_service.create_task(revalidation_change_id)

    class InventedThenValidProvider:
        evaluator_identity = "r7b-invented-reference-test"
        evaluator_revision = "1"

        def __init__(self) -> None:
            self.calls = 0

        def assess(
            self,
            *,
            task_id: UUID,
            learning_change: LearningChange,
            target_state: dict[str, object],
            evidence_document: dict[str, object],
            allowed_evidence_references: frozenset[str],
        ) -> Any:
            self.calls += 1
            references = tuple(sorted(allowed_evidence_references))
            freshness_disposition = "current"
            valid_payload: dict[str, Any] = {
                "freshness_disposition": freshness_disposition,
                "findings": [
                    {
                        "code": "supports_revalidation",
                        "summary": "The rebuilt evidence basis remains relevant.",
                        "evidence_refs": list(references),
                    }
                ],
            }
            if self.calls == 1 and invalid_draft_case == "invented_reference":
                references = (*references, "urn:watch:invented-evidence-reference")
                valid_payload["findings"][0]["evidence_refs"] = list(references)
            elif self.calls == 1 and invalid_draft_case == "cross_team_reference":
                assert foreign_evidence_reference not in allowed_evidence_references
                references = (*references, foreign_evidence_reference)
                valid_payload["findings"][0]["evidence_refs"] = list(references)
            elif (
                self.calls == 1
                and invalid_draft_case == "omitted_evidence_link"
            ):
                evidence_link_references = sorted(
                    reference
                    for reference in allowed_evidence_references
                    if reference.startswith("evidence_link:")
                )
                assert evidence_link_references
                valid_payload["findings"][0]["evidence_refs"] = [
                    reference
                    for reference in references
                    if reference != evidence_link_references[0]
                ]
            elif self.calls == 1 and invalid_draft_case == "freshness_mismatch":
                freshness_disposition = "stale"
                valid_payload["freshness_disposition"] = freshness_disposition
            elif self.calls == 1 and invalid_draft_case == "extra_fields":
                return {
                    **valid_payload,
                    "evaluator_identity": "untrusted-model-identity",
                    "evaluator_revision": "untrusted-model-revision",
                    "assessment_payload_hash": "sha256:" + ("0" * 64),
                    "target_state_hash": "sha256:" + ("0" * 64),
                }
            elif self.calls == 1 and invalid_draft_case == "malformed_shape":
                return {
                    "freshness_disposition": "current",
                    "findings": {"code": "supports_revalidation"},
                }
            elif (
                self.calls == 1
                and invalid_draft_case == "missing_required_field"
            ):
                return {"freshness_disposition": "current"}
            elif (
                self.calls == 1
                and invalid_draft_case == "invalid_evaluator_identity"
            ):
                self.evaluator_identity = ""
            elif (
                self.calls == 1
                and invalid_draft_case == "invalid_evaluator_revision"
            ):
                self.evaluator_revision = " "

            return KnowledgeRevalidationAssessmentDraft.model_validate(
                valid_payload
            )

    provider = InventedThenValidProvider()
    runner = KnowledgeRevalidationAssessmentTaskRunner(
        session_factory, snapshot_store, provider
    )

    def cleanup_revalidation_records() -> None:
        with session_factory.begin() as session:
            session.execute(
                text(
                    "ALTER TABLE knowledge_revalidation_assessments "
                    "DISABLE TRIGGER USER"
                )
            )
            session.execute(
                delete(KnowledgeRevalidationAssessment).where(
                    KnowledgeRevalidationAssessment.task_id == task_id
                )
            )
            session.execute(
                text(
                    "ALTER TABLE knowledge_revalidation_assessments "
                    "ENABLE TRIGGER USER"
                )
            )
            session.execute(
                delete(Event).where(Event.task_id.in_([source_task_id, task_id]))
            )
            session.execute(
                delete(Outcome).where(
                    Outcome.recorded_by_task_id.in_([source_task_id, task_id])
                )
            )
            session.execute(
                delete(LearningChange).where(
                    LearningChange.id == revalidation_change_id
                )
            )
            session.execute(
                delete(Task).where(Task.id.in_([source_task_id, task_id]))
            )

    request.addfinalizer(cleanup_revalidation_records)

    rejected = runner.run(task_id)
    assert rejected.status == "pending"
    assert rejected.assessment_id is None
    assert rejected.outcome_id is None

    with session_factory() as session:
        task = session.get(Task, task_id)
        change = session.get(LearningChange, revalidation_change_id)
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        assert task is not None and change is not None and item is not None
        assert task.status == "pending"
        assert task.attempt_count == 1
        assert change.status == "proposed"
        assert item.version == 1
        assert item.current_learning_change_id == committed.learning_change_id
        assert session.scalar(
            select(func.count(KnowledgeRevalidationAssessment.id)).where(
                KnowledgeRevalidationAssessment.learning_change_id
                == revalidation_change_id
            )
        ) == 0
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == RECORDED_EVENT_TYPE,
            )
        ) == 0
        failed_event = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == "task_attempt_failed",
            )
        )
        assert failed_event is not None
        assert failed_event.payload["failure_reason"] == expected_failure_reason
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == "task_attempt_failed",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == "task_retry_scheduled",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == task_id
            )
        ) == 0

    if invalid_draft_case == "invalid_evaluator_identity":
        provider.evaluator_identity = "r7b-invented-reference-test"
    elif invalid_draft_case == "invalid_evaluator_revision":
        provider.evaluator_revision = "1"

    recovered = runner.run(task_id)
    assert recovered.status == "done"
    assert recovered.assessment_id is not None
    assert recovered.outcome_id is not None
    assert not recovered.replayed
    assert provider.calls == 2

    with session_factory() as session:
        task = session.get(Task, task_id)
        change = session.get(LearningChange, revalidation_change_id)
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        assessment = session.get(
            KnowledgeRevalidationAssessment, recovered.assessment_id
        )
        assert task is not None and change is not None and item is not None
        assert assessment is not None
        assert task.status == "done"
        assert task.attempt_count == 2
        assert change.status == "proposed"
        assert item.version == 1
        assert item.current_learning_change_id == committed.learning_change_id
        assert assessment.task_attempt == 2
        assert assessment.assessment_result == "supported"
        assert assessment.evaluator_identity == "r7b-invented-reference-test"
        assert assessment.evaluator_revision == "1"
        assert assessment.payload_hash == assessment_payload_hash(assessment)
        assert session.scalar(
            select(func.count(KnowledgeRevalidationAssessment.id)).where(
                KnowledgeRevalidationAssessment.learning_change_id
                == revalidation_change_id
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == RECORDED_EVENT_TYPE,
            )
        ) == 1
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) == 1


@pytest.mark.parametrize(
    ("drift_case", "expected_failure_reason"),
    [
        ("evidence_link_stance", "evaluation_proposal_hash_mismatch"),
        ("source_outcome_hash", "source_task_outcome_event_mismatch"),
    ],
)
def test_revalidation_rebuild_rejects_changed_canonical_evidence_before_admission(
    session_factory,
    snapshot_store,
    distillation_fixture,
    request,
    drift_case: str,
    expected_failure_reason: str,
):
    fixture = distillation_fixture(
        2, include_contrary=False, review_interval_days=1
    )
    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    approval_task_id, approval_attempt, principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    committed = LearningCommitService(session_factory, snapshot_store).decide(
        approval_task_id, approval_attempt, principal
    )
    assert committed.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=approval_task_id,
            attempt=approval_attempt,
            result_category="success_learning_change_accepted",
            observed_at=committed.committed_at,
            learning_change_id=committed.learning_change_id,
        )
    )

    source_task_id, learning_change_id = _create_revalidation_proposal(
        session_factory,
        snapshot_store,
        fixture,
        committed.knowledge_item_id,
    )
    service = KnowledgeRevalidationAssessmentService(
        session_factory, snapshot_store
    )
    task_id = service.create_task(learning_change_id)
    provider = _FakeKnowledgeRevalidationProvider()
    runner = KnowledgeRevalidationAssessmentTaskRunner(
        session_factory, snapshot_store, provider
    )
    from core.task_runtime import TaskNotEligible

    link_id: UUID | None = None
    original_stance: str | None = None
    original_reference_key: str | None = None
    outcome_id: UUID | None = None
    original_outcome_hash: str | None = None
    original_outcome_snapshot_ref: str | None = None

    def cleanup_revalidation_source_drift() -> None:
        with session_factory.begin() as session:
            if link_id is not None:
                link = session.get(EvidenceLink, link_id)
                if link is not None and original_stance is not None:
                    link.stance = original_stance
                    link.reference_key = original_reference_key
            if (
                outcome_id is not None
                and original_outcome_hash is not None
                and original_outcome_snapshot_ref is not None
            ):
                source_outcome = session.get(Outcome, outcome_id)
                if source_outcome is not None:
                    source_outcome.observation_hash = original_outcome_hash
                    source_outcome.observation_snapshot_ref = (
                        original_outcome_snapshot_ref
                    )
            session.execute(
                text(
                    "ALTER TABLE knowledge_revalidation_assessments "
                    "DISABLE TRIGGER USER"
                )
            )
            session.execute(
                delete(KnowledgeRevalidationAssessment).where(
                    KnowledgeRevalidationAssessment.task_id == task_id
                )
            )
            session.execute(
                text(
                    "ALTER TABLE knowledge_revalidation_assessments "
                    "ENABLE TRIGGER USER"
                )
            )
            session.execute(
                delete(Event).where(
                    Event.task_id.in_([source_task_id, task_id])
                )
            )
            session.execute(
                delete(Outcome).where(
                    Outcome.recorded_by_task_id.in_([source_task_id, task_id])
                )
            )
            session.execute(
                delete(LearningChange).where(
                    LearningChange.id == learning_change_id
                )
            )
            session.execute(
                delete(Task).where(Task.id.in_([source_task_id, task_id]))
            )

    request.addfinalizer(cleanup_revalidation_source_drift)

    if drift_case == "evidence_link_stance":
        with session_factory() as session:
            link = session.scalar(
                select(EvidenceLink)
                .where(
                    EvidenceLink.subject_id == fixture.cases[0].evaluation_id,
                    EvidenceLink.team_id == fixture.team_id,
                )
                .order_by(EvidenceLink.reference_key)
            )
            assert link is not None
            assert link.source_kind == "outcome"
            assert link.stance == "supports"
            link_id = link.id
            original_stance = link.stance
            original_reference_key = link.reference_key
    else:
        with session_factory() as session:
            source_outcome = session.get(Outcome, fixture.cases[0].outcome_id)
            assert source_outcome is not None
            outcome_id = source_outcome.id
            original_outcome_hash = source_outcome.observation_hash
            original_outcome_snapshot_ref = source_outcome.observation_snapshot_ref

    with session_factory.begin() as session:
        if drift_case == "evidence_link_stance":
            link = session.get(EvidenceLink, link_id)
            assert link is not None
            link.stance = "mentions"
            link.reference_key = EvaluationService._link_payload(link)[
                "reference_key"
            ]
            assert link.reference_key != original_reference_key
        else:
            source_outcome = session.get(Outcome, outcome_id)
            assert source_outcome is not None
            tampered_hash = "sha256:" + "0" * 64
            source_outcome.observation_hash = tampered_hash
            source_outcome.observation_snapshot_ref = (
                "snap://sha256/" + tampered_hash.removeprefix("sha256:")
            )

    with pytest.raises(TaskNotEligible) as drift_error:
        runner.run(task_id)
    assert str(drift_error.value) == expected_failure_reason

    with session_factory.begin() as session:
        if drift_case == "evidence_link_stance":
            link = session.get(EvidenceLink, link_id)
            assert link is not None
            link.stance = original_stance
            link.reference_key = original_reference_key
        else:
            source_outcome = session.get(Outcome, outcome_id)
            assert source_outcome is not None
            source_outcome.observation_hash = original_outcome_hash
            source_outcome.observation_snapshot_ref = original_outcome_snapshot_ref

    with session_factory() as session:
        task = session.get(Task, task_id)
        change = session.get(LearningChange, learning_change_id)
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        assert task is not None and change is not None and item is not None
        assert task.status == "pending"
        assert task.attempt_count == 0
        assert provider.calls == 0
        assert change.status == "proposed"
        assert item.version == 1
        assert item.current_learning_change_id == committed.learning_change_id
        assert session.scalar(
            select(func.count(KnowledgeRevalidationAssessment.id)).where(
                KnowledgeRevalidationAssessment.learning_change_id
                == learning_change_id
            )
        ) == 0
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == "task_started",
            )
        ) == 0
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == task_id
            )
        ) == 0

    result = runner.run(task_id)
    assert result.status == "done"
    assert result.assessment_id is not None
    assert result.outcome_id is not None
    assert provider.calls == 1

    with session_factory() as session:
        task = session.get(Task, task_id)
        change = session.get(LearningChange, learning_change_id)
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        assessment = session.get(
            KnowledgeRevalidationAssessment, result.assessment_id
        )
        assert task is not None and change is not None and item is not None
        assert assessment is not None
        assert task.status == "done"
        assert task.attempt_count == 1
        assert assessment.assessment_result == "supported"
        assert change.status == "proposed"
        assert item.version == 1
        assert item.current_learning_change_id == committed.learning_change_id
        assert session.scalar(
            select(func.count(KnowledgeRevalidationAssessment.id)).where(
                KnowledgeRevalidationAssessment.learning_change_id
                == learning_change_id
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == "knowledge_revalidation_assessment_recorded",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) == 1




@pytest.mark.parametrize(
    ("drift_case", "expected_reason"),
    [
        ("target_pointer", "knowledge_revalidation_target_stale"),
        ("target_content_version", "knowledge_revalidation_target_stale"),
        ("target_content_hash", "knowledge_revalidation_target_stale"),
        ("target_full_state_hash", "knowledge_revalidation_target_stale"),
        (
            "target_content_hash_scheme",
            "knowledge_revalidation_task_request_mismatch",
        ),
        (
            "proposal_hash",
            "knowledge_revalidation_proposal_hash_mismatch",
        ),
        (
            "proposed_state_hash",
            "knowledge_revalidation_proposal_shape_invalid",
        ),
    ],
)
def test_revalidation_target_and_proposal_drift_fail_before_admission_and_approval(
    session_factory,
    snapshot_store,
    distillation_fixture,
    request,
    drift_case: str,
    expected_reason: str,
):
    from core.knowledge_approval import (
        KnowledgeApprovalBindingError,
        build_approval_binding,
    )
    from core.knowledge_revalidation import RECORDED_EVENT_TYPE
    from core.operator_approval import canonical_operator_identity
    from core.task_runtime import TaskNotEligible

    fixture = distillation_fixture(
        2, include_contrary=False, review_interval_days=1
    )
    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    approval_task_id, approval_attempt, principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    committed = LearningCommitService(session_factory, snapshot_store).decide(
        approval_task_id, approval_attempt, principal
    )
    assert committed.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=approval_task_id,
            attempt=approval_attempt,
            result_category="success_learning_change_accepted",
            observed_at=committed.committed_at,
            learning_change_id=committed.learning_change_id,
        )
    )

    source_task_id, learning_change_id = _create_revalidation_proposal(
        session_factory,
        snapshot_store,
        fixture,
        committed.knowledge_item_id,
    )
    service = KnowledgeRevalidationAssessmentService(
        session_factory, snapshot_store
    )
    task_id = service.create_task(learning_change_id)
    provider = _FakeKnowledgeRevalidationProvider()
    runner = KnowledgeRevalidationAssessmentTaskRunner(
        session_factory, snapshot_store, provider
    )

    original_item_state: dict[str, Any] = {}
    original_proposed_state: dict[str, Any] = {}
    original_request_payload: dict[str, Any] = {}

    with session_factory() as session:
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        change = session.get(LearningChange, learning_change_id)
        event = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == "knowledge_revalidation_assessment_task_requested",
            )
        )
        assert item is not None and change is not None and event is not None
        original_item_state = {
            "current_learning_change_id": item.current_learning_change_id,
            "version": item.version,
            "statement": item.statement,
            "review_after": item.review_after,
        }
        original_proposed_state = dict(change.proposed_state)
        original_request_payload = dict(event.payload)

    def apply_drift(session) -> None:
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        change = session.get(LearningChange, learning_change_id)
        event = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == "knowledge_revalidation_assessment_task_requested",
            )
        )
        assert item is not None and change is not None and event is not None
        if drift_case == "target_pointer":
            item.current_learning_change_id = learning_change_id
        elif drift_case == "target_content_version":
            item.version = original_item_state["version"] + 1
        elif drift_case == "target_content_hash":
            item.statement = f"{original_item_state['statement']} drift"
        elif drift_case == "target_full_state_hash":
            item.review_after = datetime(2027, 2, 1, tzinfo=timezone.utc)
        elif drift_case == "target_content_hash_scheme":
            event.payload = {
                **original_request_payload,
                "target_content_hash_scheme": "watch.r7b.knowledge-content.v999",
            }
        elif drift_case == "proposal_hash":
            change.proposed_state = {
                **original_proposed_state,
                "proposal_hash": "sha256:" + "d" * 64,
            }
        elif drift_case == "proposed_state_hash":
            change.proposed_state = {
                **original_proposed_state,
                "operator_supplied_extension": "changed after task creation",
            }
        else:
            raise AssertionError(f"unknown drift case: {drift_case}")

    def restore_drift(session) -> None:
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        change = session.get(LearningChange, learning_change_id)
        event = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == "knowledge_revalidation_assessment_task_requested",
            )
        )
        assert item is not None and change is not None and event is not None
        item.current_learning_change_id = original_item_state[
            "current_learning_change_id"
        ]
        item.version = original_item_state["version"]
        item.statement = original_item_state["statement"]
        item.review_after = original_item_state["review_after"]
        change.proposed_state = dict(original_proposed_state)
        event.payload = dict(original_request_payload)

    def cleanup_revalidation_drift() -> None:
        with session_factory.begin() as session:
            restore_drift(session)
            session.execute(
                text(
                    "ALTER TABLE knowledge_revalidation_assessments "
                    "DISABLE TRIGGER USER"
                )
            )
            session.execute(
                delete(KnowledgeRevalidationAssessment).where(
                    KnowledgeRevalidationAssessment.task_id == task_id
                )
            )
            session.execute(
                text(
                    "ALTER TABLE knowledge_revalidation_assessments "
                    "ENABLE TRIGGER USER"
                )
            )
            session.execute(
                delete(Event).where(
                    Event.task_id.in_([source_task_id, task_id])
                )
            )
            session.execute(
                delete(Outcome).where(
                    Outcome.recorded_by_task_id.in_([source_task_id, task_id])
                )
            )
            session.execute(
                delete(LearningChange).where(
                    LearningChange.id == learning_change_id
                )
            )
            session.execute(
                delete(Task).where(Task.id.in_([source_task_id, task_id]))
            )

    request.addfinalizer(cleanup_revalidation_drift)

    # Drift after Task creation must be rejected before TaskRuntime admission.
    with session_factory.begin() as session:
        apply_drift(session)
    with pytest.raises(TaskNotEligible) as drift_error:
        runner.run(task_id)
    assert str(drift_error.value) == expected_reason
    assert provider.calls == 0

    with session_factory() as session:
        task = session.get(Task, task_id)
        change = session.get(LearningChange, learning_change_id)
        assert task is not None and change is not None
        assert task.status == "pending"
        assert task.attempt_count == 0
        assert change.status == "proposed"
        assert session.scalar(
            select(func.count(KnowledgeRevalidationAssessment.id)).where(
                KnowledgeRevalidationAssessment.learning_change_id
                == learning_change_id
            )
        ) == 0
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == "task_started",
            )
        ) == 0
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == RECORDED_EVENT_TYPE,
            )
        ) == 0
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == task_id
            )
        ) == 0

    with session_factory.begin() as session:
        restore_drift(session)

    # The exact original request remains usable after the drift is repaired.
    result = runner.run(task_id)
    assert result.status == "done"
    assert result.assessment_id is not None
    assert result.outcome_id is not None
    assert provider.calls == 1

    with session_factory() as session:
        assessment = session.get(
            KnowledgeRevalidationAssessment, result.assessment_id
        )
        task = session.get(Task, task_id)
        assert assessment is not None and task is not None
        assert task.status == "done"
        assert task.attempt_count == 1
        assert assessment.assessment_result == "supported"
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == RECORDED_EVENT_TYPE,
            )
        ) == 1
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) == 1

    # The same target/proposal drift is independently rejected at approval time.
    with session_factory.begin() as session:
        apply_drift(session)
    with session_factory.begin() as session:
        change = session.get(LearningChange, learning_change_id)
        assert change is not None
        operator_id = canonical_operator_identity(
            "https://host.example/identity", "rv06-reviewer"
        )
        with pytest.raises(
            KnowledgeApprovalBindingError,
            match=expected_reason,
        ):
            build_approval_binding(
                session,
                change,
                operator_id=operator_id,
                approval_policy_version=1,
                require_assessment=True,
                snapshot_store=snapshot_store,
                session_factory=session_factory,
            )

    with session_factory.begin() as session:
        restore_drift(session)
    with session_factory.begin() as session:
        change = session.get(LearningChange, learning_change_id)
        assert change is not None
        binding = build_approval_binding(
            session,
            change,
            operator_id=canonical_operator_identity(
                "https://host.example/identity", "rv06-reviewer"
            ),
            approval_policy_version=1,
            require_assessment=True,
            snapshot_store=snapshot_store,
            session_factory=session_factory,
        )
        assert binding["assessment_type"] == "knowledge_revalidation"
        assert binding["assessment_payload_hash"]


@pytest.mark.parametrize(
    "freshness_disposition",
    ["current", "stale", "insufficient", "conflicting", "unassessable"],
)
@pytest.mark.parametrize(
    ("crash_after_record", "fail_first_attempt", "fail_record_first"),
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (False, False, True),
    ],
)
def test_revalidation_task_records_once_and_recovers_without_canonical_writes(
    session_factory,
    snapshot_store,
    distillation_fixture,
    freshness_disposition: Literal[
        "current", "stale", "insufficient", "conflicting", "unassessable"
    ],
    crash_after_record: bool,
    fail_first_attempt: bool,
    fail_record_first: bool,
):
    fixture = distillation_fixture(
        2, include_contrary=False, review_interval_days=1
    )
    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    approval_task_id, approval_attempt, principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    committed = LearningCommitService(session_factory, snapshot_store).decide(
        approval_task_id, approval_attempt, principal
    )
    assert committed.knowledge_item_id is not None
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=approval_task_id,
            attempt=approval_attempt,
            result_category="success_learning_change_accepted",
            observed_at=committed.committed_at,
            learning_change_id=committed.learning_change_id,
        )
    )

    source_task_id, revalidation_change_id = _create_revalidation_proposal(
        session_factory,
        snapshot_store,
        fixture,
        committed.knowledge_item_id,
    )
    revalidation_service = KnowledgeRevalidationAssessmentService(
        session_factory, snapshot_store
    )
    task_id = revalidation_service.create_task(revalidation_change_id)
    provider = _FakeKnowledgeRevalidationProvider(
        fail_first=fail_first_attempt,
        freshness_disposition=freshness_disposition,
    )

    class CrashAfterAssessmentRecordRuntime(TaskRuntime):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.crash_next_success = crash_after_record

        def finalize(self, observation):
            if (
                self.crash_next_success
                and observation.result_category
                == "success_knowledge_revalidation_assessed"
            ):
                self.crash_next_success = False
                raise RuntimeError("simulated_process_loss_after_assessment_commit")
            return super().finalize(observation)

    runner = KnowledgeRevalidationAssessmentTaskRunner(
        session_factory,
        snapshot_store,
        provider,
        runtime=CrashAfterAssessmentRecordRuntime(
            session_factory, snapshot_store
        ),
    )
    if fail_record_first:
        def fail_assessment_insert(mapper, connection, assessment) -> None:
            if assessment.task_id == task_id:
                raise IntegrityError(
                    "INSERT INTO knowledge_revalidation_assessments",
                    {},
                    RuntimeError("simulated_assessment_insert_failure"),
                )

        event.listen(
            KnowledgeRevalidationAssessment,
            "before_insert",
            fail_assessment_insert,
        )
    from core.task_runtime import TaskNotEligible

    invalid_shapes = [
        ("task_type", "unrecognized_assessment_task"),
        ("allowed_writes", ["KnowledgeItem"]),
        (
            "budget",
            {
                "max_tool_calls": 1,
                "max_cost_usd": 0.0,
                "deadline_seconds": 30,
            },
        ),
        ("max_attempts", 4),
    ]
    for attribute, invalid_value in invalid_shapes:
        with session_factory.begin() as session:
            task = session.get(Task, task_id)
            assert task is not None
            original_value = getattr(task, attribute)
            setattr(task, attribute, invalid_value)
        with pytest.raises(TaskNotEligible) as envelope_error:
            runner.run(task_id)
        assert str(envelope_error.value) == (
            "knowledge_revalidation_task_shape_invalid"
        )
        with session_factory.begin() as session:
            task = session.get(Task, task_id)
            assert task is not None
            setattr(task, attribute, original_value)

    with session_factory() as session:
        task = session.get(Task, task_id)
        assert task is not None
        assert task.status == "pending"
        assert task.attempt_count == 0
        assert provider.calls == 0
        assert session.scalar(
            select(func.count(KnowledgeRevalidationAssessment.id)).where(
                KnowledgeRevalidationAssessment.task_id == task_id
            )
        ) == 0
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == task_id
            )
        ) == 0
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == "task_started",
            )
        ) == 0

    with session_factory() as session:
        request_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task_id,
                    Event.type == REQUEST_EVENT_TYPE,
                )
            )
        )
        assert len(request_events) == 1
        request_event_id = request_events[0].id
        original_request_payload = dict(request_events[0].payload)
        request_event_created_at = request_events[0].created_at

    duplicate_request_event_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Event(
                id=duplicate_request_event_id,
                task_id=task_id,
                type=REQUEST_EVENT_TYPE,
                payload=original_request_payload,
                created_at=request_event_created_at + timedelta(seconds=1),
            )
        )
    with pytest.raises(TaskNotEligible) as duplicate_error:
        runner.run(task_id)
    assert str(duplicate_error.value) == (
        "knowledge_revalidation_request_event_invalid"
    )

    with session_factory.begin() as session:
        session.execute(
            delete(Event).where(Event.id == duplicate_request_event_id)
        )
        request_event = session.get(Event, request_event_id)
        assert request_event is not None
        request_event.payload = {
            **original_request_payload,
            "request_hash": "sha256:" + ("0" * 64),
        }
    with pytest.raises(TaskNotEligible) as request_error:
        runner.run(task_id)
    assert str(request_error.value) == (
        "knowledge_revalidation_task_request_mismatch"
    )

    with session_factory.begin() as session:
        request_event = session.get(Event, request_event_id)
        assert request_event is not None
        request_event.payload = original_request_payload

    with session_factory() as session:
        task = session.get(Task, task_id)
        assert task is not None
        assert task.status == "pending"
        assert task.attempt_count == 0
        assert provider.calls == 0
        assert session.scalar(
            select(func.count(KnowledgeRevalidationAssessment.id)).where(
                KnowledgeRevalidationAssessment.task_id == task_id
            )
        ) == 0
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == task_id
            )
        ) == 0
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == "task_started",
            )
        ) == 0

    if crash_after_record:
        with pytest.raises(
            RuntimeError,
            match="simulated_process_loss_after_assessment_commit",
        ):
            runner.run(task_id)
        with session_factory() as session:
            assessment = session.scalar(
                select(KnowledgeRevalidationAssessment).where(
                    KnowledgeRevalidationAssessment.task_id == task_id
                )
            )
            task = session.get(Task, task_id)
            assert assessment is not None
            assert task is not None and task.status == "running"
            recorded_at = assessment.recorded_at
            assert session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == task_id
                )
            ) == 0
            context = validate_revalidation_task_request(
                session,
                task,
                session_factory,
                snapshot_store,
                require_proposed=True,
                require_current=True,
            )
        replayed_record = revalidation_service.record(
            task_id,
            provider.draft_for_references(context.pack.reference_ids),
            evaluator_identity=provider.evaluator_identity,
            evaluator_revision=provider.evaluator_revision,
        )
        assert replayed_record.replayed
        assert replayed_record.assessment_id == assessment.id
        recovery = TaskRuntime(
            session_factory, snapshot_store
        ).recover_interrupted(now=recorded_at + timedelta(seconds=120))
        assert recovery.completed == (task_id,)
        assert recovery.retried == ()
        assert recovery.failed == ()
    elif fail_first_attempt:
        first = runner.run(task_id)
        assert first.status == "pending"
        assert first.assessment_id is None
        second = runner.run(task_id)
        assert second.status == "done"
        assert second.assessment_id is not None
    elif fail_record_first:
        try:
            with pytest.raises(IntegrityError):
                runner.run(task_id)
        finally:
            event.remove(
                KnowledgeRevalidationAssessment,
                "before_insert",
                fail_assessment_insert,
            )
        with session_factory() as session:
            task = session.get(Task, task_id)
            assert task is not None
            assert task.status == "running"
            assert task.attempt_count == 1
            assert session.scalar(
                select(func.count(KnowledgeRevalidationAssessment.id)).where(
                    KnowledgeRevalidationAssessment.task_id == task_id
                )
            ) == 0
            assert session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == task_id,
                    Event.type == RECORDED_EVENT_TYPE,
                )
            ) == 0
            assert session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == task_id
                )
            ) == 0
        recovery = TaskRuntime(
            session_factory, snapshot_store
        ).recover_interrupted(
            now=datetime.now(timezone.utc) + timedelta(seconds=120)
        )
        assert recovery.retried == (task_id,)
        assert recovery.completed == ()
        assert recovery.failed == ()
        second = runner.run(task_id)
        assert second.status == "done"
        assert second.assessment_id is not None
    else:
        first = runner.run(task_id)
        assert first.status == "done"
        assert first.assessment_id is not None

    assert revalidation_service.create_task(revalidation_change_id) == task_id
    replay = runner.run(task_id)
    assert replay.status == "done"
    assert replay.replayed
    assert replay.assessment_id is not None
    assert provider.calls == (2 if fail_first_attempt or fail_record_first else 1)

    with session_factory() as session:
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        change = session.get(LearningChange, revalidation_change_id)
        task = session.get(Task, task_id)
        assessment = session.get(
            KnowledgeRevalidationAssessment, replay.assessment_id
        )
        assert item is not None and change is not None and task is not None
        assert assessment is not None
        assert change.status == "proposed"
        assert item.current_learning_change_id == committed.learning_change_id
        assert item.version == 1
        assert task.status == "done"
        assert task.allowed_writes == ["KnowledgeRevalidationAssessment"]
        assert assessment.assessment_result == (
            "supported" if freshness_disposition == "current" else "indeterminate"
        )
        assert assessment.freshness_disposition == freshness_disposition
        assert assessment.task_attempt == (
            2 if fail_first_attempt or fail_record_first else 1
        )
        assert session.scalar(
            select(func.count(KnowledgeRevalidationAssessment.id)).where(
                KnowledgeRevalidationAssessment.learning_change_id
                == revalidation_change_id
            )
        ) == 1
        from core.knowledge_approval import (
            KnowledgeApprovalBindingError,
            build_approval_binding,
        )
        from core.operator_approval import canonical_operator_identity

        reviewer = canonical_operator_identity(
            "https://host.example/identity", "b37-revalidation-reviewer"
        )
        recorded_event_id = assessment.recorded_event_id
        if freshness_disposition == "current":
            binding = build_approval_binding(
                session,
                change,
                operator_id=reviewer,
                approval_policy_version=1,
                require_assessment=True,
                snapshot_store=snapshot_store,
                session_factory=session_factory,
            )
            assert binding["assessment_type"] == "knowledge_revalidation"
            assert binding["assessment_id"] == str(assessment.id)
            assert binding["assessment_payload_hash"] == assessment.payload_hash
            assert binding["target_content_version"] == item.version
            assert binding["target_content_hash"] == assessment.target_content_hash
            assert binding["current_learning_change_id"] == str(
                item.current_learning_change_id
            )
            assert binding["operator_id"] == reviewer
            assert binding["assessment_task_policy_version"] == task.policy_version
        else:
            with pytest.raises(
                KnowledgeApprovalBindingError,
                match="knowledge_approval_revalidation_not_supported",
            ):
                build_approval_binding(
                    session,
                    change,
                    operator_id=reviewer,
                    approval_policy_version=1,
                    require_assessment=True,
                    snapshot_store=snapshot_store,
                    session_factory=session_factory,
                )

    with session_factory() as session:
        recorded_event = session.get(Event, recorded_event_id)
        assert recorded_event is not None
        original_recorded_event_payload = dict(recorded_event.payload)
    with session_factory.begin() as session:
        recorded_event = session.get(Event, recorded_event_id)
        assert recorded_event is not None
        recorded_event.payload = {
            **original_recorded_event_payload,
            "assessment_payload_hash": "sha256:" + ("0" * 64),
        }
    with pytest.raises(TaskNotEligible) as tampered_replay_error:
        runner.run(task_id)
    assert str(tampered_replay_error.value) == (
        "knowledge_revalidation_recorded_event_invalid"
    )
    with session_factory() as session:
        change = session.get(LearningChange, revalidation_change_id)
        assert change is not None
        with pytest.raises(
            KnowledgeApprovalBindingError,
            match="knowledge_revalidation_recorded_event_invalid",
        ):
            build_approval_binding(
                session,
                change,
                operator_id=reviewer,
                approval_policy_version=1,
                require_assessment=True,
                snapshot_store=snapshot_store,
                session_factory=session_factory,
            )
    with session_factory.begin() as session:
        recorded_event = session.get(Event, recorded_event_id)
        assert recorded_event is not None
        recorded_event.payload = original_recorded_event_payload
        original_recorded_event_type = recorded_event.type
        recorded_event.type = "tampered_revalidation_recorded_event_type"
    with pytest.raises(TaskNotEligible) as missing_event_error:
        runner.run(task_id)
    assert str(missing_event_error.value) == (
        "knowledge_revalidation_recorded_event_invalid"
    )
    with session_factory.begin() as session:
        recorded_event = session.get(Event, recorded_event_id)
        assert recorded_event is not None
        recorded_event.type = original_recorded_event_type

    duplicate_recorded_event_id = uuid4()
    with session_factory.begin() as session:
        recorded_event = session.get(Event, recorded_event_id)
        assert recorded_event is not None
        session.add(
            Event(
                id=duplicate_recorded_event_id,
                task_id=task_id,
                type=original_recorded_event_type,
                payload=original_recorded_event_payload,
                created_at=recorded_event.created_at + timedelta(seconds=1),
            )
        )
    with pytest.raises(TaskNotEligible) as duplicate_event_error:
        runner.run(task_id)
    assert str(duplicate_event_error.value) == (
        "knowledge_revalidation_recorded_event_invalid"
    )
    with session_factory.begin() as session:
        session.execute(
            delete(Event).where(Event.id == duplicate_recorded_event_id)
        )
    replay_after_event_repair = runner.run(task_id)
    assert replay_after_event_repair.status == "done"
    assert replay_after_event_repair.replayed
    with session_factory() as session:
        assert session.scalar(
            select(func.count(KnowledgeRevalidationAssessment.id)).where(
                KnowledgeRevalidationAssessment.task_id == task_id
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == original_recorded_event_type,
            )
        ) == 1
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == task_id
            )
        ) == 1

    with pytest.raises(IntegrityError):
        with session_factory.begin() as session:
            referenced_change = session.get(
                LearningChange, revalidation_change_id
            )
            assert referenced_change is not None
            session.delete(referenced_change)
    with session_factory() as session:
        assert session.get(LearningChange, revalidation_change_id) is not None
        assert session.scalar(
            select(func.count(KnowledgeRevalidationAssessment.id)).where(
                KnowledgeRevalidationAssessment.task_id == task_id
            )
        ) == 1

    # The assessment table is intentionally immutable. Disable only user
    # triggers inside this disposable test transaction to remove its fixture.
    with session_factory.begin() as session:
        session.execute(
            text(
                "ALTER TABLE knowledge_revalidation_assessments "
                "DISABLE TRIGGER USER"
            )
        )
        session.execute(
            delete(KnowledgeRevalidationAssessment).where(
                KnowledgeRevalidationAssessment.task_id == task_id
            )
        )
        session.execute(
            text(
                "ALTER TABLE knowledge_revalidation_assessments "
                "ENABLE TRIGGER USER"
            )
        )
        session.execute(
            delete(Event).where(Event.task_id.in_([source_task_id, task_id]))
        )
        session.execute(
            delete(Outcome).where(
                Outcome.recorded_by_task_id.in_([source_task_id, task_id])
            )
        )
        session.execute(
            delete(LearningChange).where(LearningChange.id == revalidation_change_id)
        )
        session.execute(delete(Task).where(Task.id.in_([source_task_id, task_id])))


def test_quality_assessment_recovery_finalizes_same_record_without_duplicate(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(2, include_contrary=False)
    proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )

    from core.knowledge_quality import REQUEST_EVENT_TYPE, TASK_TYPE

    with session_factory() as session:
        learning_change = session.get(LearningChange, proposal.learning_change_id)
        assert learning_change is not None
        quality_task = session.scalar(
            select(Task).where(
                Task.task_type == TASK_TYPE,
                Task.team_id == fixture.team_id,
            )
        )
        assert quality_task is not None
        _, pack = ExperienceDistiller(
            session_factory, snapshot_store, provider=None
        ).validate_learning_change(session, learning_change)
        lineage = build_case_lineage_report(
            session, fixture.team_id, pack.evidence_basis
        )
        request_event = session.scalar(
            select(Event).where(
                Event.task_id == quality_task.id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
        assert request_event is not None
    admission = runtime.admit(quality_task.id)
    draft = _FakeKnowledgeQualityAssessmentProvider().assess(
        task_id=quality_task.id,
        learning_change=learning_change,
        evidence_document=pack.document,
        lineage_report=lineage,
    )
    recorded = KnowledgeQualityAssessmentService(
        session_factory, snapshot_store
    ).record(quality_task.id, draft)

    with session_factory.begin() as session:
        start_event = session.scalar(
            select(Event).where(
                Event.task_id == quality_task.id,
                Event.type == "task_started",
            )
        )
        assert start_event is not None
        start_event.created_at = recorded.recorded_at - timedelta(seconds=61)

    recovery = runtime.recover_interrupted(now=recorded.recorded_at)
    assert recovery.completed == (quality_task.id,)
    assert recovery.retried == ()
    assert recovery.failed == ()

    with session_factory() as session:
        completed = session.get(Task, quality_task.id)
        assert completed is not None and completed.status == "done"
        assert completed.attempt_count == admission.attempt_count == 1
        assert completed.completed_at == recorded.recorded_at
        assert session.scalar(
            select(func.count(KnowledgeQualityAssessment.id)).where(
                KnowledgeQualityAssessment.learning_change_id
                == proposal.learning_change_id
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == quality_task.id,
                Event.type == "knowledge_quality_assessment_recorded",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == quality_task.id,
                Outcome.outcome_type == "task_execution",
            )
        ) == 1

    replay = KnowledgeQualityAssessmentTaskRunner(
        session_factory,
        snapshot_store,
        _FakeKnowledgeQualityAssessmentProvider(),
        runtime,
    ).run(quality_task.id)
    assert replay.status == "done"
    assert replay.assessment_id == recorded.assessment_id
    assert replay.outcome_id is not None
    assert replay.replayed

def test_accepted_create_requires_recorded_quality_assessment(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(2, include_contrary=False)
    proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )

    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    principal = _approval_principal(fixture.team_id)
    with pytest.raises(
        LearningChangeNotApprovable,
        match="knowledge_quality_assessment_required",
    ):
        adapter.request_learning_change_decision(
            principal,
            LearningChangeDecisionRequest(
                learning_change_id=proposal.learning_change_id,
                decision="accept",
                idempotency_key=uuid4(),
            ),
        )

    with session_factory() as session:
        assessment_task = session.scalar(
            select(Task).where(
                Task.task_type == "assess_knowledge_quality",
                Task.team_id == fixture.team_id,
            )
        )
        assert assessment_task is not None
        assert assessment_task.status == "pending"
        assert session.scalar(
            select(Task.id).where(
                Task.task_type == "approve_learning_change",
                Task.team_id == fixture.team_id,
            )
        ) is None

    _run_quality_assessment(
        session_factory, snapshot_store, proposal.learning_change_id
    )
    approval_task_id, attempt, trusted_principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        proposal.learning_change_id,
    )
    result = LearningCommitService(
        session_factory, snapshot_store
    ).decide(approval_task_id, attempt, trusted_principal)
    assert result.status == "accepted"
    assert result.knowledge_item_id is not None

    with session_factory() as session:
        learning_change = session.get(LearningChange, proposal.learning_change_id)
        assert learning_change is not None
        assert learning_change.status == "accepted"
        item = session.get(KnowledgeItem, result.knowledge_item_id)
        assert item is not None
        assert item.version == 1
        accepted_event = session.scalar(
            select(Event).where(
                Event.task_id == approval_task_id,
                Event.type == "learning_change_accepted",
            )
        )
        assert accepted_event is not None
        assert accepted_event.payload["knowledge_quality_assessment_id"]
        assert accepted_event.payload["knowledge_quality_assessment_hash"]


@pytest.mark.parametrize("revision_kind", ["content", "confidence_only"])
@pytest.mark.parametrize("review_interval_days", [None, 7])
def test_revise_proposal_pins_exact_target_and_records_bound_assessment(
    session_factory,
    snapshot_store,
    distillation_fixture,
    revision_kind: str,
    review_interval_days: int | None,
):
    fixture = distillation_fixture(
        2,
        include_contrary=False,
        review_interval_days=review_interval_days,
    )
    runtime = TaskRuntime(session_factory, snapshot_store)

    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    approval_task_id, approval_attempt, principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    committed = LearningCommitService(session_factory, snapshot_store).decide(
        approval_task_id, approval_attempt, principal
    )
    assert committed.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=approval_task_id,
            attempt=approval_attempt,
            result_category="success_learning_change_accepted",
            observed_at=committed.committed_at,
            learning_change_id=committed.learning_change_id,
        )
    )

    with session_factory() as session:
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        template = session.get(Task, fixture.distillation_task_id)
        assert item is not None and template is not None
        assert item.status == "active"
        before_state = knowledge_item_state(item)
        before_pointer = item.current_learning_change_id

    revision_task_id = uuid4()
    fixture.extra_task_ids.append(revision_task_id)
    started_at = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        session.add(
            Task(
                id=revision_task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=template.policy_version,
                objective_id=None,
                plan_id=None,
                plan_action_id=None,
                allowed_writes=["LearningChange"],
                budget=dict(template.budget),
                created_at=started_at,
                completed_at=None,
                max_attempts=template.max_attempts,
            )
        )
        session.flush()
        session.add(
            Event(
                id=uuid4(),
                task_id=revision_task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=started_at,
            )
        )

    def revised_content(prompt: str) -> dict[str, Any]:
        content = _content_from_prompt(prompt)
        if revision_kind == "content":
            content["body"] = (
                "The revised practice preserves source evidence and records a distinct "
                "observation before drawing a conclusion."
            )
        else:
            for field in (
                "kind",
                "title",
                "statement",
                "body",
                "applicability",
                "preconditions",
                "assumptions",
                "limitations",
                "non_applicability",
                "failure_modes",
                "known_counterexamples",
                "missing_information",
                "uncertainty",
            ):
                content[field] = before_state[field]
            confidence = Decimal(str(before_state["confidence"]))
            next_confidence = confidence + Decimal("0.001")
            if next_confidence > Decimal("1"):
                next_confidence = confidence - Decimal("0.001")
            content["confidence"] = float(next_confidence)
        return content

    provider = _FakeDistillationProvider(revised_content)
    revised = _distiller(session_factory, snapshot_store, provider).propose_revision(
        revision_task_id,
        [case.evaluation_id for case in fixture.cases],
        committed.knowledge_item_id,
    )
    assert revised.status == "proposed"
    assert revised.generation_charge_id is not None
    assert provider.calls == 1

    with session_factory.begin() as session:
        change = session.get(LearningChange, revised.learning_change_id)
        assert change is not None
        original_idempotency_key = change.idempotency_key
        change.idempotency_key = "r7b-revise-v1:tampered"

    with pytest.raises(
        TaskNotFinalizable,
        match="learning_change_revise_target_invalid:revision_proposal_idempotency_mismatch",
    ):
        runtime.finalize(
            TerminalObservation(
                task_id=revision_task_id,
                attempt=1,
                result_category="success_learning_change_proposed",
                observed_at=datetime.now(timezone.utc),
                learning_change_id=revised.learning_change_id,
            )
        )

    with session_factory.begin() as session:
        change = session.get(LearningChange, revised.learning_change_id)
        assert change is not None
        change.idempotency_key = original_idempotency_key

    runtime.finalize(
        TerminalObservation(
            task_id=revision_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=revised.learning_change_id,
        )
    )

    with session_factory() as session:
        change = session.get(LearningChange, revised.learning_change_id)
        assert change is not None
        assert change.operation == "revise"
        assert change.target_id == committed.knowledge_item_id
        assert change.previous_state["state"] == before_state
        assert change.previous_state["snapshot_hash"].startswith("sha256:")

        proposal_event = session.scalar(
            select(Event).where(
                Event.task_id == revision_task_id,
                Event.type == "learning_change_proposed",
            )
        )
        assert proposal_event is not None
        target_binding = proposal_event.payload["target_binding"]
        assert target_binding["target_knowledge_item_id"] == str(
            committed.knowledge_item_id
        )
        assert target_binding["target_current_learning_change_id"] == str(
            before_pointer
        )
        assert target_binding["target_content_version"] == 1
        assert target_binding["target_content_hash"].startswith("sha256:")
        assert (
            target_binding["target_content_hash_scheme"]
            == "watch.r7b.knowledge-content.v2"
        )
        previous_state_hash = change.previous_state["snapshot_hash"]
        assert target_binding["target_state_hash"] == previous_state_hash
        quality_request = session.scalar(
            select(Event).where(
                Event.type == "knowledge_quality_assessment_task_requested",
                Event.payload["learning_change_id"].as_string()
                == str(revised.learning_change_id),
            )
        )
        assert quality_request is not None
        quality_task = session.get(Task, quality_request.task_id)
        assert quality_task is not None and quality_task.status == "pending"
        assert quality_request.payload["target_binding"] == target_binding

        unchanged_item = session.get(KnowledgeItem, committed.knowledge_item_id)
        assert unchanged_item is not None
        assert knowledge_item_state(unchanged_item) == before_state
        assert unchanged_item.current_learning_change_id == before_pointer

    assessment_id = _run_quality_assessment(
        session_factory, snapshot_store, revised.learning_change_id
    )
    with session_factory.begin() as session:
        assessment = session.get(KnowledgeQualityAssessment, assessment_id)
        assert assessment is not None
        assert assessment.learning_change_id == revised.learning_change_id
        assert assessment.assessment_payload_hash.startswith("sha256:")
        request_event = session.scalar(
            select(Event).where(
                Event.task_id == assessment.creating_task_id,
                Event.type == "knowledge_quality_assessment_task_requested",
            )
        )
        assert request_event is not None
        assert request_event.payload["target_binding"] == target_binding

        # Altering the original request pin must invalidate the recorded
        # assessment payload hash; the transaction restores the original Event.
        original_request_payload = dict(request_event.payload)
        request_event.payload = {
            **request_event.payload,
            "target_binding": {
                **target_binding,
                "target_content_version": target_binding["target_content_version"] + 1,
            },
        }
        with pytest.raises(
            KnowledgeQualityAssessmentError,
            match="knowledge_quality_assessment_binding_invalid",
        ):
            require_recorded_assessment(
                session,
                session.get(LearningChange, revised.learning_change_id),
            )
        request_event.payload = original_request_payload

        unchanged_item = session.get(KnowledgeItem, committed.knowledge_item_id)
        assert unchanged_item is not None
        assert knowledge_item_state(unchanged_item) == before_state

    with session_factory() as session:
        before_events = session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == revision_task_id,
                Event.type == "learning_change_proposed",
            )
        )
        before_changes = session.scalar(
            select(func.count(LearningChange.id)).where(
                LearningChange.proposed_by_task_id == revision_task_id
            )
        )

    replay = _distiller(
        session_factory, snapshot_store, provider=None
    ).propose_revision(
        revision_task_id,
        [case.evaluation_id for case in fixture.cases],
        committed.knowledge_item_id,
    )
    assert replay.replayed is True
    assert replay.learning_change_id == revised.learning_change_id

    with session_factory() as session:
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == revision_task_id,
                Event.type == "learning_change_proposed",
            )
        ) == before_events
        assert session.scalar(
            select(func.count(LearningChange.id)).where(
                LearningChange.proposed_by_task_id == revision_task_id
            )
        ) == before_changes

    principal = _approval_principal(fixture.team_id)
    decision_request = LearningChangeDecisionRequest(
        learning_change_id=revised.learning_change_id,
        decision="accept",
        idempotency_key=uuid4(),
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    approval_request = adapter.request_learning_change_decision(
        principal, decision_request
    )
    admission = runtime.admit(approval_request.task_id)
    revision_commit = LearningCommitService(
        session_factory, snapshot_store
    ).decide(approval_request.task_id, admission.attempt_count, principal)

    assert revision_commit.decision == "accept"
    assert revision_commit.status == "accepted"
    assert revision_commit.knowledge_item_id == committed.knowledge_item_id
    assert not revision_commit.replayed

    recovery = runtime.recover_interrupted(
        now=revision_commit.committed_at + timedelta(seconds=61)
    )
    assert approval_request.task_id in recovery.completed

    with session_factory() as session:
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        change = session.get(LearningChange, revised.learning_change_id)
        decision_event = session.scalar(
            select(Event).where(
                Event.task_id == approval_request.task_id,
                Event.type == "learning_change_accepted",
            )
        )
        assert item is not None and change is not None and decision_event is not None
        assert item.id == committed.knowledge_item_id
        assert str(item.origin_learning_change_id) == before_state[
            "origin_learning_change_id"
        ]
        assert item.current_learning_change_id == revised.learning_change_id
        assert item.version == before_state["version"] + 1
        assert item.status == before_state["status"]
        if revision_kind == "confidence_only":
            assert item.confidence != Decimal(str(before_state["confidence"]))
        assert item.last_validated_at is None
        expected_review_after = (
            None
            if review_interval_days is None
            else revision_commit.committed_at
            + timedelta(days=review_interval_days)
        )
        assert item.review_after == expected_review_after
        assert change.previous_state is not None
        assert change.previous_state["state"] == before_state
        assert change.previous_state["snapshot_hash"] == previous_state_hash
        assert change.committed_state is not None
        assert change.committed_state["state"] == knowledge_item_state(item)
        assert decision_event.payload["operation"] == "revise"
        assert decision_event.payload["knowledge_item_id"] == str(item.id)
        assert decision_event.payload["knowledge_item_version"] == item.version
        assert decision_event.payload["knowledge_quality_assessment_id"]
        assert decision_event.payload["approval_binding"]["target_content_version"] == 1
        approval_task = session.get(Task, approval_request.task_id)
        assert approval_task is not None and approval_task.status == "done"

    replay = LearningCommitService(session_factory, snapshot_store).decide(
        approval_request.task_id, admission.attempt_count, principal
    )
    assert replay.replayed
    assert replay.knowledge_item_id == committed.knowledge_item_id
    assert replay.learning_change_id == revised.learning_change_id

    rejected_revision_task_id = uuid4()
    fixture.extra_task_ids.append(rejected_revision_task_id)
    rejected_started_at = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        session.add(
            Task(
                id=rejected_revision_task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=template.policy_version,
                objective_id=None,
                plan_id=None,
                plan_action_id=None,
                allowed_writes=["LearningChange"],
                budget=dict(template.budget),
                created_at=rejected_started_at,
                completed_at=None,
                max_attempts=template.max_attempts,
            )
        )
        session.flush()
        session.add(
            Event(
                id=uuid4(),
                task_id=rejected_revision_task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=rejected_started_at,
            )
        )

    def rejected_content(prompt: str) -> dict[str, Any]:
        content = _content_from_prompt(prompt)
        content["body"] = "A second candidate revision that the Operator rejects."
        return content

    rejected_proposal = _distiller(
        session_factory,
        snapshot_store,
        _FakeDistillationProvider(rejected_content),
    ).propose_revision(
        rejected_revision_task_id,
        [case.evaluation_id for case in fixture.cases],
        committed.knowledge_item_id,
    )
    runtime.finalize(
        TerminalObservation(
            task_id=rejected_revision_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=rejected_proposal.learning_change_id,
        )
    )
    with session_factory() as session:
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        assert item is not None
        state_before_rejection = knowledge_item_state(item)

    rejection_principal = _approval_principal(fixture.team_id)
    rejection_request = LearningChangeDecisionRequest(
        learning_change_id=rejected_proposal.learning_change_id,
        decision="reject",
        idempotency_key=uuid4(),
        rejection_reason="The revised candidate is not sufficiently supported.",
    )
    rejection_adapter = OperatorApplicationAdapter(
        session_factory, snapshot_store
    )
    rejected_task = rejection_adapter.request_learning_change_decision(
        rejection_principal, rejection_request
    )
    rejected_admission = runtime.admit(rejected_task.task_id)
    rejected_commit = LearningCommitService(
        session_factory, snapshot_store
    ).decide(
        rejected_task.task_id,
        rejected_admission.attempt_count,
        rejection_principal,
    )
    assert rejected_commit.decision == "reject"
    assert rejected_commit.knowledge_item_id is None
    runtime.finalize(
        TerminalObservation(
            task_id=rejected_task.task_id,
            attempt=rejected_admission.attempt_count,
            result_category="success_learning_change_rejected",
            observed_at=rejected_commit.committed_at,
            learning_change_id=rejected_proposal.learning_change_id,
        )
    )
    with session_factory() as session:
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        rejected_change = session.get(
            LearningChange, rejected_proposal.learning_change_id
        )
        assert item is not None and rejected_change is not None
        assert knowledge_item_state(item) == state_before_rejection
        assert item.current_learning_change_id == revised.learning_change_id
        assert rejected_change.previous_state is not None
        assert rejected_change.previous_state["state"] == state_before_rejection
        assert rejected_change.committed_state is None

    rejected_replay = LearningCommitService(
        session_factory, snapshot_store
    ).decide(
        rejected_task.task_id,
        rejected_admission.attempt_count,
        rejection_principal,
    )
    assert rejected_replay.replayed
    assert rejected_replay.decision == "reject"
    assert rejected_replay.knowledge_item_id is None

    stale_revision_task_id = uuid4()
    fixture.extra_task_ids.append(stale_revision_task_id)
    stale_started_at = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        session.add(
            Task(
                id=stale_revision_task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=template.policy_version,
                objective_id=None,
                plan_id=None,
                plan_action_id=None,
                allowed_writes=["LearningChange"],
                budget=dict(template.budget),
                created_at=stale_started_at,
                completed_at=None,
                max_attempts=template.max_attempts,
            )
        )
        session.flush()
        session.add(
            Event(
                id=uuid4(),
                task_id=stale_revision_task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=stale_started_at,
            )
        )

    def stale_content(prompt: str) -> dict[str, Any]:
        content = _content_from_prompt(prompt)
        content["body"] = "A candidate that must become stale before approval."
        return content

    stale_proposal = _distiller(
        session_factory,
        snapshot_store,
        _FakeDistillationProvider(stale_content),
    ).propose_revision(
        stale_revision_task_id,
        [case.evaluation_id for case in fixture.cases],
        committed.knowledge_item_id,
    )
    runtime.finalize(
        TerminalObservation(
            task_id=stale_revision_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=stale_proposal.learning_change_id,
        )
    )
    _run_quality_assessment(
        session_factory, snapshot_store, stale_proposal.learning_change_id
    )
    stale_principal = _approval_principal(fixture.team_id)
    stale_request = OperatorApplicationAdapter(
        session_factory, snapshot_store
    ).request_learning_change_decision(
        stale_principal,
        LearningChangeDecisionRequest(
            learning_change_id=stale_proposal.learning_change_id,
            decision="accept",
            idempotency_key=uuid4(),
        ),
    )
    stale_admission = runtime.admit(stale_request.task_id)

    competing_revision_task_id = uuid4()
    fixture.extra_task_ids.append(competing_revision_task_id)
    competing_started_at = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        session.add(
            Task(
                id=competing_revision_task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=template.policy_version,
                objective_id=None,
                plan_id=None,
                plan_action_id=None,
                allowed_writes=["LearningChange"],
                budget=dict(template.budget),
                created_at=competing_started_at,
                completed_at=None,
                max_attempts=template.max_attempts,
            )
        )
        session.flush()
        session.add(
            Event(
                id=uuid4(),
                task_id=competing_revision_task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=competing_started_at,
            )
        )

    def competing_content(prompt: str) -> dict[str, Any]:
        content = _content_from_prompt(prompt)
        content["body"] = "The competing revision that wins the target compare-and-set."
        return content

    competing_proposal = _distiller(
        session_factory,
        snapshot_store,
        _FakeDistillationProvider(competing_content),
    ).propose_revision(
        competing_revision_task_id,
        [case.evaluation_id for case in fixture.cases],
        committed.knowledge_item_id,
    )
    runtime.finalize(
        TerminalObservation(
            task_id=competing_revision_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=competing_proposal.learning_change_id,
        )
    )
    competing_approval_task_id, competing_attempt, competing_principal = (
        _create_admitted_approval_task(
            session_factory,
            snapshot_store,
            fixture.team_id,
            competing_proposal.learning_change_id,
        )
    )
    competing_commit = LearningCommitService(
        session_factory, snapshot_store
    ).decide(
        competing_approval_task_id,
        competing_attempt,
        competing_principal,
    )
    assert competing_commit.decision == "accept"
    runtime.finalize(
        TerminalObservation(
            task_id=competing_approval_task_id,
            attempt=competing_attempt,
            result_category="success_learning_change_accepted",
            observed_at=competing_commit.committed_at,
            learning_change_id=competing_proposal.learning_change_id,
        )
    )

    original_revision_replay = LearningCommitService(
        session_factory, snapshot_store
    ).decide(
        approval_request.task_id,
        admission.attempt_count,
        principal,
    )
    assert original_revision_replay.replayed
    assert (
        original_revision_replay.knowledge_item_id == committed.knowledge_item_id
    )

    with pytest.raises(
        LearningCommitCorrupt,
        match="knowledge_quality_revision_target_stale",
    ):
        LearningCommitService(session_factory, snapshot_store).decide(
            stale_request.task_id,
            stale_admission.attempt_count,
            stale_principal,
        )
    with session_factory() as session:
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        change = session.get(LearningChange, stale_proposal.learning_change_id)
        decision_events = session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == stale_request.task_id,
                Event.type.in_(
                    ("learning_change_accepted", "learning_change_rejected")
                ),
            )
        )
        assert item is not None and change is not None
        assert item.status == "active"
        assert item.current_learning_change_id == competing_proposal.learning_change_id
        assert item.version == before_state["version"] + 2
        assert change.status == "proposed"
        assert change.committed_by_task_id is None
        assert decision_events == 0


def test_recorded_quality_assessment_is_completed_by_interrupted_recovery(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(2, include_contrary=False)
    proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )

    with session_factory() as session:
        request_event = session.scalar(
            select(Event).where(
                Event.type == "knowledge_quality_assessment_task_requested",
                Event.payload["learning_change_id"].as_string()
                == str(proposal.learning_change_id),
            )
        )
        assert request_event is not None
        quality_task_id = request_event.task_id

    class CrashAfterAssessmentRecordRuntime(TaskRuntime):
        def finalize(self, observation):
            if observation.result_category == "success_knowledge_quality_assessed":
                raise RuntimeError("simulated_process_loss_after_assessment_commit")
            return super().finalize(observation)

    runner = KnowledgeQualityAssessmentTaskRunner(
        session_factory,
        snapshot_store,
        _FakeKnowledgeQualityAssessmentProvider(),
        runtime=CrashAfterAssessmentRecordRuntime(
            session_factory, snapshot_store
        ),
    )
    with pytest.raises(
        RuntimeError,
        match="simulated_process_loss_after_assessment_commit",
    ):
        runner.run(quality_task_id)

    with session_factory() as session:
        assessment = session.scalar(
            select(KnowledgeQualityAssessment).where(
                KnowledgeQualityAssessment.learning_change_id
                == proposal.learning_change_id
            )
        )
        task = session.get(Task, quality_task_id)
        assert assessment is not None
        assert task is not None and task.status == "running"
        assessed_at = assessment.recorded_at
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == quality_task_id
            )
        ) == 0

    recovery = TaskRuntime(session_factory, snapshot_store).recover_interrupted(
        now=assessed_at + timedelta(seconds=120)
    )
    assert recovery.completed == (quality_task_id,)
    assert recovery.failed == ()
    assert recovery.retried == ()

    with session_factory() as session:
        assessment_rows = list(
            session.scalars(
                select(KnowledgeQualityAssessment).where(
                    KnowledgeQualityAssessment.learning_change_id
                    == proposal.learning_change_id
                )
            )
        )
        task = session.get(Task, quality_task_id)
        outcomes = list(
            session.scalars(
                select(Outcome).where(
                    Outcome.recorded_by_task_id == quality_task_id,
                    Outcome.outcome_type == "task_execution",
                )
            )
        )
        terminal_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == quality_task_id,
                    Event.type == "task_completed",
                )
            )
        )
        assert len(assessment_rows) == 1
        assert task is not None and task.status == "done"
        assert task.completed_at == assessed_at
        assert len(outcomes) == 1
        assert outcomes[0].observed_at == assessed_at
        assert len(terminal_events) == 1
        assert (
            terminal_events[0].payload["knowledge_quality_assessment_id"]
            == str(assessment_rows[0].id)
        )

def test_create_with_successor_commits_hidden_candidate_through_existing_path(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    distiller = _distiller(session_factory, snapshot_store, _provider())
    evaluation_ids = [fixture.cases[0].evaluation_id]

    predecessor_proposal = distiller.propose(
        fixture.distillation_task_id, evaluation_ids
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=predecessor_proposal.learning_change_id,
        )
    )
    predecessor_approval_id, predecessor_attempt, predecessor_principal = (
        _create_admitted_approval_task(
            session_factory,
            snapshot_store,
            fixture.team_id,
            predecessor_proposal.learning_change_id,
        )
    )
    predecessor_result = LearningCommitService(
        session_factory, snapshot_store
    ).decide(predecessor_approval_id, predecessor_attempt, predecessor_principal)
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=predecessor_approval_id,
            attempt=predecessor_attempt,
            result_category="success_learning_change_accepted",
            observed_at=predecessor_result.committed_at,
            learning_change_id=predecessor_result.learning_change_id,
        )
    )
    assert predecessor_result.knowledge_item_id is not None

    candidate_task_id = uuid4()
    fixture.extra_task_ids.append(candidate_task_id)
    with session_factory.begin() as session:
        session.add(
            Task(
                id=candidate_task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=1,
                allowed_writes=["LearningChange"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 1.0,
                    "deadline_seconds": 60,
                },
            )
        )

    candidate_proposal = distiller.propose(
        candidate_task_id,
        evaluation_ids,
        supersedes_item_id=predecessor_result.knowledge_item_id,
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=candidate_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=candidate_proposal.learning_change_id,
        )
    )
    candidate_approval_id, candidate_attempt, candidate_principal = (
        _create_admitted_approval_task(
            session_factory,
            snapshot_store,
            fixture.team_id,
            candidate_proposal.learning_change_id,
        )
    )
    candidate_result = LearningCommitService(
        session_factory, snapshot_store
    ).decide(candidate_approval_id, candidate_attempt, candidate_principal)
    assert candidate_result.knowledge_item_id is not None
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=candidate_approval_id,
            attempt=candidate_attempt,
            result_category="success_learning_change_accepted",
            observed_at=candidate_result.committed_at,
            learning_change_id=candidate_result.learning_change_id,
        )
    )

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_result.knowledge_item_id)
        candidate = session.get(KnowledgeItem, candidate_result.knowledge_item_id)
        change = session.get(LearningChange, candidate_proposal.learning_change_id)
        assert predecessor is not None and candidate is not None and change is not None
        assert change.status == "accepted"
        assert candidate.status == "active"
        assert candidate.version == 1
        assert candidate.supersedes_item_id == predecessor.id
        assert candidate.superseded_by_id is None
        assert candidate.review_after is not None
        assert candidate.review_after > candidate_result.committed_at
        assert predecessor.status == "active"
        assert predecessor.superseded_by_id is None
        assert change.proposed_state["supersedes_item_id"] == str(predecessor.id)
        assert change.proposed_state["supersedes_target_binding"][
            "target_current_learning_change_id"
        ] == str(predecessor.current_learning_change_id)
        assert knowledge_item_content_hash(candidate) == knowledge_item_content_hash(
            {
                **knowledge_item_state(candidate),
                "supersedes_item_id": None,
            }
        )
        history = reconstruct_knowledge_item_history(session, candidate)
        assert history.states[0]["supersedes_item_id"] == str(predecessor.id)
        assert not _supersession_publication_is_visible(session, candidate, {})

    replay = LearningCommitService(session_factory, snapshot_store).decide(
        candidate_approval_id, candidate_attempt, candidate_principal
    )
    assert replay.replayed
    assert replay.knowledge_item_id == candidate_result.knowledge_item_id

    second_task_id = uuid4()
    fixture.extra_task_ids.append(second_task_id)
    with session_factory.begin() as session:
        session.add(
            Task(
                id=second_task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=1,
                allowed_writes=["LearningChange"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 1.0,
                    "deadline_seconds": 60,
                },
            )
        )
    second_provider = _provider()
    with pytest.raises(
        ExperienceDistillerError, match="successor_candidate_already_pending"
    ):
        _distiller(session_factory, snapshot_store, second_provider).propose(
            second_task_id,
            evaluation_ids,
            supersedes_item_id=predecessor_result.knowledge_item_id,
        )
    assert second_provider.calls == 0


def test_concurrent_create_with_successor_commits_only_one_candidate(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    evaluation_ids = [fixture.cases[0].evaluation_id]
    runtime = TaskRuntime(session_factory, snapshot_store)
    distiller = _distiller(session_factory, snapshot_store, _provider())

    predecessor_proposal = distiller.propose(
        fixture.distillation_task_id, evaluation_ids
    )
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=predecessor_proposal.learning_change_id,
        )
    )
    predecessor = _accept_learning_change(
        session_factory,
        snapshot_store,
        fixture.team_id,
        predecessor_proposal.learning_change_id,
    )
    assert predecessor.knowledge_item_id is not None

    proposals = []
    for _ in range(2):
        task_id = _create_proposal_task(session_factory, fixture)
        proposal = distiller.propose(
            task_id,
            evaluation_ids,
            supersedes_item_id=predecessor.knowledge_item_id,
        )
        runtime.finalize(
            TerminalObservation(
                task_id=task_id,
                attempt=1,
                result_category="success_learning_change_proposed",
                observed_at=datetime.now(timezone.utc),
                learning_change_id=proposal.learning_change_id,
            )
        )
        proposals.append(proposal)

    approvals = [
        _create_admitted_approval_task(
            session_factory,
            snapshot_store,
            fixture.team_id,
            proposal.learning_change_id
        )
        for proposal in proposals
    ]
    def decide(approval):
        task_id, attempt, principal = approval
        return LearningCommitService(session_factory, snapshot_store).decide(
            task_id, attempt, principal
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(decide, approval) for approval in approvals]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except LearningCommitError as error:
                outcomes.append(error)

    successes = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], LearningCommitError)
    assert str(failures[0]) == "successor_candidate_already_pending"

    winner = successes[0]
    winner_index = next(
        index
        for index, outcome in enumerate(outcomes)
        if outcome is winner
    )
    winner_task_id, winner_attempt, _ = approvals[winner_index]
    runtime.finalize(
        TerminalObservation(
            task_id=winner_task_id,
            attempt=winner_attempt,
            result_category="success_learning_change_accepted",
            observed_at=winner.committed_at,
            learning_change_id=winner.learning_change_id,
        )
    )

    with session_factory() as session:
        predecessor_item = session.get(KnowledgeItem, predecessor.knowledge_item_id)
        candidates = list(
            session.scalars(
                select(KnowledgeItem).where(
                    KnowledgeItem.team_id == fixture.team_id,
                    KnowledgeItem.supersedes_item_id == predecessor.knowledge_item_id,
                    KnowledgeItem.status != "retired",
                )
            )
        )
        assert predecessor_item is not None
        assert predecessor_item.status == "active"
        assert predecessor_item.superseded_by_id is None
        assert len(candidates) == 1
        assert candidates[0].origin_learning_change_id == winner.learning_change_id
        loser_index = 1 - winner_index
        loser_task_id, _, _ = approvals[loser_index]
        loser = session.get(LearningChange, proposals[loser_index].learning_change_id)
        assert loser is not None and loser.status == "proposed"
        assert session.scalar(
            select(Event.id).where(
                Event.task_id == loser_task_id,
                Event.type == "learning_change_accepted",
            )
        ) is None


def test_create_with_successor_rejects_stale_predecessor_after_revision(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    evaluation_ids = [fixture.cases[0].evaluation_id]
    runtime = TaskRuntime(session_factory, snapshot_store)
    distiller = _distiller(session_factory, snapshot_store, _provider())

    predecessor_proposal = distiller.propose(
        fixture.distillation_task_id, evaluation_ids
    )
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=predecessor_proposal.learning_change_id,
        )
    )
    predecessor_approval_id, predecessor_attempt, predecessor_principal = (
        _create_admitted_approval_task(
            session_factory,
            snapshot_store,
            fixture.team_id,
            predecessor_proposal.learning_change_id,
        )
    )
    predecessor_result = LearningCommitService(
        session_factory, snapshot_store
    ).decide(predecessor_approval_id, predecessor_attempt, predecessor_principal)
    runtime.finalize(
        TerminalObservation(
            task_id=predecessor_approval_id,
            attempt=predecessor_attempt,
            result_category="success_learning_change_accepted",
            observed_at=predecessor_result.committed_at,
            learning_change_id=predecessor_result.learning_change_id,
        )
    )
    assert predecessor_result.knowledge_item_id is not None

    candidate_task_id = uuid4()
    fixture.extra_task_ids.append(candidate_task_id)
    with session_factory.begin() as session:
        template = session.get(Task, fixture.distillation_task_id)
        assert template is not None
        session.add(
            Task(
                id=candidate_task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=template.policy_version,
                allowed_writes=["LearningChange"],
                budget=dict(template.budget),
            )
        )
    candidate_proposal = distiller.propose(
        candidate_task_id,
        evaluation_ids,
        supersedes_item_id=predecessor_result.knowledge_item_id,
    )
    runtime.finalize(
        TerminalObservation(
            task_id=candidate_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=candidate_proposal.learning_change_id,
        )
    )
    candidate_approval_id, candidate_attempt, candidate_principal = (
        _create_admitted_approval_task(
            session_factory,
            snapshot_store,
            fixture.team_id,
            candidate_proposal.learning_change_id,
        )
    )

    revision_task_id = uuid4()
    fixture.extra_task_ids.append(revision_task_id)
    started_at = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        template = session.get(Task, fixture.distillation_task_id)
        assert template is not None
        session.add(
            Task(
                id=revision_task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=template.policy_version,
                allowed_writes=["LearningChange"],
                budget=dict(template.budget),
                created_at=started_at,
            )
        )
        session.flush()
        session.add(
            Event(
                id=uuid4(),
                task_id=revision_task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=started_at,
            )
        )

    def revised_content(prompt: str) -> dict[str, Any]:
        content = _content_from_prompt(prompt)
        content["body"] = (
            "A revised practice records a distinct observation "
            "before drawing a conclusion."
        )
        return content

    revision = _distiller(
        session_factory,
        snapshot_store,
        _FakeDistillationProvider(revised_content),
    ).propose_revision(
        revision_task_id,
        evaluation_ids,
        predecessor_result.knowledge_item_id,
    )
    runtime.finalize(
        TerminalObservation(
            task_id=revision_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=revision.learning_change_id,
        )
    )
    revision_approval_id, revision_attempt, revision_principal = (
        _create_admitted_approval_task(
            session_factory,
            snapshot_store,
            fixture.team_id,
            revision.learning_change_id
        )
    )
    revision_result = LearningCommitService(
        session_factory, snapshot_store
    ).decide(revision_approval_id, revision_attempt, revision_principal)
    runtime.finalize(
        TerminalObservation(
            task_id=revision_approval_id,
            attempt=revision_attempt,
            result_category="success_learning_change_accepted",
            observed_at=revision_result.committed_at,
            learning_change_id=revision_result.learning_change_id,
        )
    )

    with pytest.raises(LearningCommitError, match="successor_predecessor_stale"):
        LearningCommitService(session_factory, snapshot_store).decide(
            candidate_approval_id, candidate_attempt, candidate_principal
        )

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_result.knowledge_item_id)
        candidate_change = session.get(
            LearningChange, candidate_proposal.learning_change_id
        )
        assert predecessor is not None and candidate_change is not None
        assert predecessor.version == 2
        assert predecessor.current_learning_change_id == revision.learning_change_id
        assert candidate_change.status == "proposed"
        assert session.scalar(
            select(KnowledgeItem.id).where(
                KnowledgeItem.origin_learning_change_id == candidate_change.id
            )
        ) is None
        assert session.scalar(
            select(Event.id).where(
                Event.task_id == candidate_approval_id,
                Event.type == "learning_change_accepted",
            )
        ) is None


def test_create_with_successor_rejects_needs_review_and_due_predecessors(
    session_factory, snapshot_store, distillation_fixture, monkeypatch
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    evaluation_ids = [fixture.cases[0].evaluation_id]
    distiller = _distiller(session_factory, snapshot_store, _provider())
    proposal = distiller.propose(fixture.distillation_task_id, evaluation_ids)
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    predecessor = _accept_learning_change(
        session_factory, snapshot_store, fixture.team_id, proposal.learning_change_id
    )
    assert predecessor.knowledge_item_id is not None

    needs_review_task = _create_proposal_task(session_factory, fixture)
    with session_factory.begin() as session:
        item = session.get(KnowledgeItem, predecessor.knowledge_item_id)
        assert item is not None
        item.status = "needs_review"
    needs_review_provider = _provider()
    with pytest.raises(
        ExperienceDistillerError, match="revision_target_status_invalid"
    ):
        _distiller(session_factory, snapshot_store, needs_review_provider).propose(
            needs_review_task,
            evaluation_ids,
            supersedes_item_id=predecessor.knowledge_item_id,
        )
    assert needs_review_provider.calls == 0
    with session_factory.begin() as session:
        item = session.get(KnowledgeItem, predecessor.knowledge_item_id)
        assert item is not None
        item.status = "active"

    due_task = _create_proposal_task(session_factory, fixture)
    original_datetime = datetime

    class _FutureDatetime(original_datetime):
        @classmethod
        def now(cls, tz=None):
            return original_datetime.now(tz) + timedelta(days=2)

    monkeypatch.setattr("core.experience_distiller.datetime", _FutureDatetime)
    due_provider = _provider()
    with pytest.raises(
        ExperienceDistillerError, match="successor_predecessor_not_d7_eligible"
    ):
        _distiller(session_factory, snapshot_store, due_provider).propose(
            due_task,
            evaluation_ids,
            supersedes_item_id=predecessor.knowledge_item_id,
        )
    assert due_provider.calls == 0


def test_create_with_successor_rejects_missing_pinned_review_interval(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    distiller = _distiller(session_factory, snapshot_store, _provider())
    evaluation_ids = [fixture.cases[0].evaluation_id]

    predecessor_proposal = distiller.propose(
        fixture.distillation_task_id, evaluation_ids
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=predecessor_proposal.learning_change_id,
        )
    )
    predecessor_approval_id, predecessor_attempt, predecessor_principal = (
        _create_admitted_approval_task(
            session_factory,
            snapshot_store,
            fixture.team_id,
            predecessor_proposal.learning_change_id,
        )
    )
    predecessor_result = LearningCommitService(
        session_factory, snapshot_store
    ).decide(predecessor_approval_id, predecessor_attempt, predecessor_principal)
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=predecessor_approval_id,
            attempt=predecessor_attempt,
            result_category="success_learning_change_accepted",
            observed_at=predecessor_result.committed_at,
            learning_change_id=predecessor_result.learning_change_id,
        )
    )
    assert predecessor_result.knowledge_item_id is not None

    with session_factory.begin() as session:
        session.add(
            TeamPolicy(
                id=uuid4(),
                team_id=fixture.team_id,
                version=2,
                schema_version=1,
                rules={"unchanged": True},
            )
        )

    candidate_task_id = uuid4()
    fixture.extra_task_ids.append(candidate_task_id)
    with session_factory.begin() as session:
        session.add(
            Task(
                id=candidate_task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="running",
                attempt_count=1,
                policy_version=2,
                allowed_writes=["LearningChange"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 1.0,
                    "deadline_seconds": 60,
                },
            )
        )
    candidate_proposal = distiller.propose(
        candidate_task_id,
        evaluation_ids,
        supersedes_item_id=predecessor_result.knowledge_item_id,
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=candidate_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=candidate_proposal.learning_change_id,
        )
    )
    candidate_approval_id, candidate_attempt, candidate_principal = (
        _create_admitted_approval_task(
            session_factory,
            snapshot_store,
            fixture.team_id,
            candidate_proposal.learning_change_id,
        )
    )

    with pytest.raises(
        LearningCommitError, match="successor_review_interval_required"
    ):
        LearningCommitService(session_factory, snapshot_store).decide(
            candidate_approval_id, candidate_attempt, candidate_principal
        )

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_result.knowledge_item_id)
        change = session.get(LearningChange, candidate_proposal.learning_change_id)
        assert predecessor is not None and change is not None
        assert predecessor.status == "active"
        assert predecessor.superseded_by_id is None
        assert change.status == "proposed"
        assert session.scalar(
            select(KnowledgeItem.id).where(
                KnowledgeItem.origin_learning_change_id == change.id
            )
        ) is None
        assert session.scalar(
            select(Event.id).where(
                Event.task_id == candidate_approval_id,
                Event.type == "learning_change_accepted",
            )
        ) is None


def test_learning_commit_accepts_real_create_proposal_atomically(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    distiller = _distiller(session_factory, snapshot_store, _provider())
    proposal = distiller.propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    task_id, attempt, principal = _create_admitted_approval_task(
        session_factory, snapshot_store, fixture.team_id, proposal.learning_change_id
    )

    result = LearningCommitService(session_factory, snapshot_store).decide(
        task_id, attempt, principal
    )

    assert result.decision == "accept"
    assert result.status == "accepted"
    assert result.knowledge_item_id is not None
    assert not result.replayed
    with session_factory() as session:
        change = session.get(LearningChange, proposal.learning_change_id)
        item = session.get(KnowledgeItem, result.knowledge_item_id)
        assert change is not None and change.status == "accepted"
        assert change.committed_by_task_id == task_id
        assert change.operator_id == result.operator_id
        assert change.previous_state is None
        assert change.committed_state is not None
        assert item is not None
        assert item.origin_learning_change_id == change.id
        assert item.team_id == fixture.team_id
        assert item.kind == "practice"
        assert item.version == 1
        assert item.status == "active"
        assert item.review_after is None
        assert item.last_validated_at is None
        decision_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task_id,
                    Event.type == "learning_change_accepted",
                )
            )
        )
        assert len(decision_events) == 1
        assert decision_events[0].payload["knowledge_item_id"] == str(item.id)
        request_event = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == "operator_task_requested",
            )
        )
        assert request_event is not None
        assert request_event.payload["schema_version"] == 3
        assert decision_events[0].payload["schema_version"] == 2
        assert decision_events[0].payload["request_fingerprint"] == (
            request_event.payload["request_fingerprint"]
        )
        assert decision_events[0].payload["approval_binding"] == (
            request_event.payload["approval_binding"]
        )
        assert decision_events[0].payload["approval_binding"][
            "assessment_payload_hash"
        ] == request_event.payload["knowledge_quality_assessment_hash"]
        assert session.scalar(
            select(Task).where(Task.id == task_id)
        ).status == "running"

    try:
        replay = LearningCommitService(session_factory, snapshot_store).decide(
            task_id, attempt, principal
        )
        assert replay.replayed
        assert replay.knowledge_item_id == result.knowledge_item_id
    finally:
        with session_factory.begin() as session:
            committed_change_ids = list(
                session.scalars(
                    select(LearningChange.id).where(
                        LearningChange.committed_by_task_id == task_id
                    )
                )
            )
            if committed_change_ids:
                session.execute(
                    delete(KnowledgeItem).where(
                        KnowledgeItem.origin_learning_change_id.in_(
                            committed_change_ids
                        )
                    )
                )
                session.execute(
                    delete(KnowledgeQualityAssessment).where(
                        KnowledgeQualityAssessment.learning_change_id.in_(
                            committed_change_ids
                        )
                    )
                )
                session.execute(
                    delete(LearningChange).where(
                        LearningChange.id.in_(committed_change_ids)
                    )
                )
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))


def test_learning_commit_rejection_is_durable_without_knowledge_item(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    proposal = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    task_id, attempt, principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        proposal.learning_change_id,
        decision="reject",
        reason="The evidence is too narrow for this team's current method.",
    )
    try:
        result = LearningCommitService(session_factory, snapshot_store).decide(
            task_id, attempt, principal
        )
        assert result.decision == "reject"
        assert result.status == "rejected"
        assert result.knowledge_item_id is None
        with session_factory() as session:
            change = session.get(LearningChange, proposal.learning_change_id)
            assert change is not None
            assert change.status == "rejected"
            assert change.decision_reason == (
                "The evidence is too narrow for this team's current method."
            )
            assert change.committed_state is None
            assert session.scalar(
                select(KnowledgeItem.id).where(
                    KnowledgeItem.origin_learning_change_id == change.id
                )
            ) is None
            assert session.scalar(
                select(Event.id).where(
                    Event.task_id == task_id,
                    Event.type == "learning_change_rejected",
                )
            ) is not None
        replay = LearningCommitService(session_factory, snapshot_store).decide(
            task_id, attempt, principal
        )
        assert replay.replayed and replay.decision == "reject"
    finally:
        with session_factory.begin() as session:
            committed_change_ids = list(
                session.scalars(
                    select(LearningChange.id).where(
                        LearningChange.committed_by_task_id == task_id
                    )
                )
            )
            if committed_change_ids:
                session.execute(
                    delete(KnowledgeItem).where(
                        KnowledgeItem.origin_learning_change_id.in_(
                            committed_change_ids
                        )
                    )
                )
                session.execute(
                    delete(KnowledgeQualityAssessment).where(
                        KnowledgeQualityAssessment.learning_change_id.in_(
                            committed_change_ids
                        )
                    )
                )
                session.execute(
                    delete(LearningChange).where(
                        LearningChange.id.in_(committed_change_ids)
                    )
                )
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))


def test_learning_commit_rejects_stale_or_tampered_evidence_without_partial_state(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    proposal = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    task_id, attempt, principal = _create_admitted_approval_task(
        session_factory, snapshot_store, fixture.team_id, proposal.learning_change_id
    )
    try:
        with session_factory.begin() as session:
            link = session.scalar(
                select(EvidenceLink).where(
                    EvidenceLink.subject_id == fixture.cases[0].evaluation_id
                )
            )
            assert link is not None
            link.stance = "challenges"

        with pytest.raises(
            LearningCommitError, match="evidence_link_integrity_mismatch"
        ):
            LearningCommitService(session_factory, snapshot_store).decide(
                task_id, attempt, principal
            )
        with session_factory() as session:
            change = session.get(LearningChange, proposal.learning_change_id)
            assert change is not None and change.status == "proposed"
            assert change.committed_by_task_id is None
            assert session.scalar(
                select(KnowledgeItem.id).where(
                    KnowledgeItem.origin_learning_change_id == change.id
                )
            ) is None
            assert session.scalar(
                select(Event.id).where(
                    Event.task_id == task_id,
                    Event.type.in_(
                        ("learning_change_accepted", "learning_change_rejected")
                    ),
                )
            ) is None
    finally:
        with session_factory.begin() as session:
            committed_change_ids = list(
                session.scalars(
                    select(LearningChange.id).where(
                        LearningChange.committed_by_task_id == task_id
                    )
                )
            )
            if committed_change_ids:
                session.execute(
                    delete(KnowledgeItem).where(
                        KnowledgeItem.origin_learning_change_id.in_(
                            committed_change_ids
                        )
                    )
                )
                session.execute(
                    delete(KnowledgeQualityAssessment).where(
                        KnowledgeQualityAssessment.learning_change_id.in_(
                            committed_change_ids
                        )
                    )
                )
                session.execute(
                    delete(LearningChange).where(
                        LearningChange.id.in_(committed_change_ids)
                    )
                )
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))


def test_learning_commit_rejects_wrong_operator_and_stale_policy(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    proposal = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    task_id, attempt, principal = _create_admitted_approval_task(
        session_factory, snapshot_store, fixture.team_id, proposal.learning_change_id
    )
    try:
        wrong_principal = _approval_principal(fixture.team_id, "other-operator")
        with pytest.raises(LearningCommitError, match="operator_identity_mismatch"):
            LearningCommitService(session_factory, snapshot_store).decide(
                task_id, attempt, wrong_principal
            )

        with session_factory.begin() as session:
            session.add(
                TeamPolicy(
                    id=uuid4(),
                    team_id=fixture.team_id,
                    version=2,
                    rules={"new": "policy"},
                )
            )
        with pytest.raises(LearningCommitError, match="approval_task_policy_is_stale"):
            LearningCommitService(session_factory, snapshot_store).decide(
                task_id, attempt, principal
            )
        with session_factory() as session:
            change = session.get(LearningChange, proposal.learning_change_id)
            assert change is not None and change.status == "proposed"
            assert session.scalar(
                select(KnowledgeItem.id).where(
                    KnowledgeItem.origin_learning_change_id == change.id
                )
            ) is None
    finally:
        with session_factory.begin() as session:
            committed_change_ids = list(
                session.scalars(
                    select(LearningChange.id).where(
                        LearningChange.committed_by_task_id == task_id
                    )
                )
            )
            if committed_change_ids:
                session.execute(
                    delete(KnowledgeItem).where(
                        KnowledgeItem.origin_learning_change_id.in_(
                            committed_change_ids
                        )
                    )
                )
                session.execute(
                    delete(KnowledgeQualityAssessment).where(
                        KnowledgeQualityAssessment.learning_change_id.in_(
                            committed_change_ids
                        )
                    )
                )
                session.execute(
                    delete(LearningChange).where(
                        LearningChange.id.in_(committed_change_ids)
                    )
                )
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))


def test_learning_commit_event_failure_rolls_back_canonical_decision(
    session_factory, snapshot_store, database_engine, distillation_fixture
):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    fixture = distillation_fixture(1, False)
    proposal = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    task_id, attempt, principal = _create_admitted_approval_task(
        session_factory, snapshot_store, fixture.team_id, proposal.learning_change_id
    )
    suffix = uuid4().hex
    function = f"fail_learning_decision_{suffix}"
    trigger = f"fail_learning_decision_tr_{suffix}"
    with database_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE FUNCTION {function}() RETURNS trigger AS $$ BEGIN "
                "RAISE EXCEPTION 'injected learning decision Event failure'; "
                "END; $$ LANGUAGE plpgsql"
            )
        )
        connection.execute(
            text(
                f"CREATE TRIGGER {trigger} BEFORE INSERT ON events "
                "FOR EACH ROW WHEN (NEW.type IN "
                "('learning_change_accepted', 'learning_change_rejected')) "
                f"EXECUTE FUNCTION {function}()"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            LearningCommitService(session_factory, snapshot_store).decide(
                task_id, attempt, principal
            )
        with session_factory() as session:
            change = session.get(LearningChange, proposal.learning_change_id)
            assert change is not None and change.status == "proposed"
            assert change.committed_by_task_id is None
            assert session.scalar(
                select(KnowledgeItem.id).where(
                    KnowledgeItem.origin_learning_change_id == change.id
                )
            ) is None
    finally:
        with database_engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER {trigger} ON events"))
            connection.execute(text(f"DROP FUNCTION {function}()"))
        with session_factory.begin() as session:
            committed_change_ids = list(
                session.scalars(
                    select(LearningChange.id).where(
                        LearningChange.committed_by_task_id == task_id
                    )
                )
            )
            if committed_change_ids:
                session.execute(
                    delete(KnowledgeItem).where(
                        KnowledgeItem.origin_learning_change_id.in_(
                            committed_change_ids
                        )
                    )
                )
                session.execute(
                    delete(KnowledgeQualityAssessment).where(
                        KnowledgeQualityAssessment.learning_change_id.in_(
                            committed_change_ids
                        )
                    )
                )
                session.execute(
                    delete(LearningChange).where(
                        LearningChange.id.in_(committed_change_ids)
                    )
                )
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))


def _cleanup_operator_decision_task(
    session_factory: sessionmaker[Session], task_id: UUID
) -> None:
    with session_factory.begin() as session:
        change_ids = list(
            session.scalars(
                select(LearningChange.id).where(
                    LearningChange.committed_by_task_id == task_id
                )
            )
        )
        if change_ids:
            session.execute(
                delete(KnowledgeQualityAssessment).where(
                    KnowledgeQualityAssessment.learning_change_id.in_(change_ids)
                )
            )
            session.execute(
                delete(KnowledgeItem).where(
                    KnowledgeItem.origin_learning_change_id.in_(change_ids)
                )
            )
            session.execute(
                delete(LearningChange).where(LearningChange.id.in_(change_ids))
            )
        session.execute(
            delete(Outcome).where(Outcome.recorded_by_task_id == task_id)
        )
        session.execute(delete(Event).where(Event.task_id == task_id))
        session.execute(delete(Task).where(Task.id == task_id))


@pytest.mark.parametrize("decision", ["accept", "reject"])
def test_operator_adapter_decides_and_finalizes_the_same_task(
    session_factory, snapshot_store, distillation_fixture, decision: str
):
    fixture = distillation_fixture(1, False)
    proposal = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    if decision == "accept":
        _run_quality_assessment(
            session_factory, snapshot_store, proposal.learning_change_id
        )
    principal = _approval_principal(fixture.team_id)
    request = LearningChangeDecisionRequest(
        learning_change_id=proposal.learning_change_id,
        decision=decision,  # type: ignore[arg-type]
        idempotency_key=uuid4(),
        rejection_reason=(
            "The evidence does not justify retaining this practice."
            if decision == "reject"
            else None
        ),
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    result = adapter.decide_learning_change(principal, request)
    expected_status = "accepted" if decision == "accept" else "rejected"

    assert result.decision == decision
    assert result.learning_change_status == expected_status
    assert result.task_status == "done"
    assert result.attempt_count == 1
    assert result.outcome_id is not None
    assert not result.replayed

    with session_factory() as session:
        task = session.get(Task, result.task_id)
        change = session.get(LearningChange, proposal.learning_change_id)
        outcomes = list(
            session.scalars(
                select(Outcome).where(
                    Outcome.recorded_by_task_id == result.task_id,
                    Outcome.outcome_type == "task_execution",
                )
            )
        )
        completed = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == result.task_id,
                    Event.type == "task_completed",
                )
            )
        )
        assert task is not None and task.status == "done"
        assert change is not None and change.status == expected_status
        assert len(outcomes) == 1
        assert len(completed) == 1
        assert completed[0].payload["result_category"] == (
            "success_learning_change_accepted"
            if decision == "accept"
            else "success_learning_change_rejected"
        )
        if decision == "accept":
            assert result.knowledge_item_id is not None
            assert session.get(KnowledgeItem, result.knowledge_item_id) is not None
        else:
            assert result.knowledge_item_id is None
            assert session.scalar(
                select(KnowledgeItem.id).where(
                    KnowledgeItem.origin_learning_change_id == change.id
                )
            ) is None

    replay = adapter.decide_learning_change(principal, request)
    assert replay.replayed
    assert replay.task_id == result.task_id
    assert replay.outcome_id == result.outcome_id

    _cleanup_operator_decision_task(session_factory, result.task_id)


@pytest.mark.parametrize("reconcile_by", ["adapter", "recovery"])
def test_competing_approval_tasks_terminalize_the_losing_request(
    session_factory,
    snapshot_store,
    distillation_fixture,
    reconcile_by: str,
):
    fixture = distillation_fixture(1, False)
    proposal = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    _run_quality_assessment(
        session_factory, snapshot_store, proposal.learning_change_id
    )

    principal = _approval_principal(fixture.team_id)
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    winner_request = LearningChangeDecisionRequest(
        learning_change_id=proposal.learning_change_id,
        decision="accept",
        idempotency_key=uuid4(),
    )
    loser_request = LearningChangeDecisionRequest(
        learning_change_id=proposal.learning_change_id,
        decision="accept",
        idempotency_key=uuid4(),
    )

    winner_request_result = adapter.request_learning_change_decision(
        principal, winner_request
    )
    loser_request_result = adapter.request_learning_change_decision(
        principal, loser_request
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    winner_admission = runtime.admit(winner_request_result.task_id)
    loser_admission = runtime.admit(loser_request_result.task_id)
    assert winner_admission.attempt_count == loser_admission.attempt_count == 1

    try:
        winner = adapter.decide_learning_change(principal, winner_request)
        assert winner.task_status == "done"
        assert winner.decision == "accept"

        if reconcile_by == "adapter":
            with pytest.raises(
                OperatorTaskRequestConflict, match="learning_change_already_decided"
            ):
                adapter.decide_learning_change(principal, loser_request)
        else:
            now = datetime.now(timezone.utc)
            with session_factory.begin() as session:
                started = session.scalar(
                    select(Event).where(
                        Event.task_id == loser_request_result.task_id,
                        Event.type == "task_started",
                    )
                )
                assert started is not None
                started.created_at = now - timedelta(seconds=61)

            recovery = runtime.recover_interrupted(now=now)
            assert recovery.failed == (loser_request_result.task_id,)
            assert recovery.retried == ()
            assert recovery.completed == ()

            # The same host request replays the already-recorded failure and
            # surfaces the same decision conflict; it cannot add another Outcome.
            with pytest.raises(
                OperatorTaskRequestConflict, match="learning_change_already_decided"
            ):
                adapter.decide_learning_change(principal, loser_request)

        with session_factory() as session:
            learning_change = session.get(
                LearningChange, proposal.learning_change_id
            )
            winner_task = session.get(Task, winner_request_result.task_id)
            loser_task = session.get(Task, loser_request_result.task_id)
            assert learning_change is not None
            assert learning_change.status == "accepted"
            assert learning_change.committed_by_task_id == winner_request_result.task_id
            assert winner_task is not None and winner_task.status == "done"
            assert loser_task is not None and loser_task.status == "failed"
            assert session.scalar(
                select(KnowledgeItem.id).where(
                    KnowledgeItem.origin_learning_change_id == learning_change.id
                )
            ) == winner.knowledge_item_id
            assert session.scalar(
                select(Outcome.id).where(
                    Outcome.recorded_by_task_id == winner_request_result.task_id,
                    Outcome.outcome_type == "task_execution",
                )
            ) == winner.outcome_id
            loser_outcomes = list(
                session.scalars(
                    select(Outcome).where(
                        Outcome.recorded_by_task_id == loser_request_result.task_id,
                        Outcome.outcome_type == "task_execution",
                    )
                )
            )
            assert len(loser_outcomes) == 1
            loser_failure_events = {
                event.type: event
                for event in session.scalars(
                    select(Event).where(
                        Event.task_id == loser_request_result.task_id,
                        Event.type.in_(("task_attempt_failed", "task_failed")),
                    )
                )
            }
            assert set(loser_failure_events) == {
                "task_attempt_failed",
                "task_failed",
            }
            assert loser_failure_events["task_failed"].payload["failure_reason"] == (
                "learning_change_already_decided"
            )
            assert session.scalar(
                select(Event.id).where(
                    Event.task_id == loser_request_result.task_id,
                    Event.type.in_(
                        ("learning_change_accepted", "learning_change_rejected")
                    ),
                )
            ) is None
    finally:
        _cleanup_operator_decision_task(session_factory, loser_request_result.task_id)
        _cleanup_operator_decision_task(session_factory, winner_request_result.task_id)


def test_operator_recovery_finalizes_a_committed_decision_after_crash(
    session_factory,
    snapshot_store,
    distillation_fixture,
    monkeypatch,
):
    fixture = distillation_fixture(1, False)
    proposal = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    _run_quality_assessment(
        session_factory, snapshot_store, proposal.learning_change_id
    )
    principal = _approval_principal(fixture.team_id)
    request = LearningChangeDecisionRequest(
        learning_change_id=proposal.learning_change_id,
        decision="accept",
        idempotency_key=uuid4(),
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    request_result = adapter.request_learning_change_decision(principal, request)
    captured: list[TerminalObservation] = []

    def crash_before_finalize(
        runtime: TaskRuntime, observation: TerminalObservation
    ):
        captured.append(observation)
        raise RuntimeError("simulated process loss after decision commit")

    with monkeypatch.context() as patch:
        patch.setattr(TaskRuntime, "finalize", crash_before_finalize)
        with pytest.raises(RuntimeError, match="simulated process loss"):
            adapter.decide_learning_change(principal, request)

    assert captured and captured[0].task_id == request_result.task_id
    with session_factory() as session:
        task = session.get(Task, request_result.task_id)
        change = session.get(LearningChange, proposal.learning_change_id)
        assert task is not None and task.status == "running"
        assert change is not None and change.status == "accepted"
        assert session.scalar(
            select(Outcome.id).where(
                Outcome.recorded_by_task_id == request_result.task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) is None

    now = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        start = session.scalar(
            select(Event).where(
                Event.task_id == request_result.task_id,
                Event.type == "task_started",
            )
        )
        assert start is not None
        start.created_at = now - timedelta(seconds=61)

    recovery = TaskRuntime(session_factory, snapshot_store).recover_interrupted(
        now=now
    )
    assert recovery.completed == (request_result.task_id,)
    assert recovery.retried == ()
    with session_factory() as session:
        task = session.get(Task, request_result.task_id)
        assert task is not None and task.status == "done"
        assert task.attempt_count == 1
        assert session.scalar(
            select(Outcome.id).where(
                Outcome.recorded_by_task_id == request_result.task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) is not None

    replay = adapter.decide_learning_change(principal, request)
    assert replay.replayed and replay.task_status == "done"
    _cleanup_operator_decision_task(session_factory, request_result.task_id)


def test_operator_recovery_retries_predecision_crash_then_reuses_same_task(
    session_factory,
    snapshot_store,
    distillation_fixture,
    monkeypatch,
):
    fixture = distillation_fixture(1, False)
    proposal = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    principal = _approval_principal(fixture.team_id)
    request = LearningChangeDecisionRequest(
        learning_change_id=proposal.learning_change_id,
        decision="reject",
        idempotency_key=uuid4(),
        rejection_reason="The current evidence is insufficient.",
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    captured_task_ids: list[UUID] = []

    def crash_before_decision(
        service: LearningCommitService,
        task_id: UUID,
        attempt: int,
        trusted_principal: TrustedOperatorPrincipal,
    ):
        captured_task_ids.append(task_id)
        raise RuntimeError("simulated process loss before decision commit")

    with monkeypatch.context() as patch:
        patch.setattr(LearningCommitService, "decide", crash_before_decision)
        with pytest.raises(RuntimeError, match="before decision commit"):
            adapter.decide_learning_change(principal, request)

    assert len(captured_task_ids) == 1
    task_id = captured_task_ids[0]
    with session_factory() as session:
        task = session.get(Task, task_id)
        change = session.get(LearningChange, proposal.learning_change_id)
        assert task is not None and task.status == "running"
        assert change is not None and change.status == "proposed"

    now = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        start = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == "task_started",
            )
        )
        assert start is not None
        start.created_at = now - timedelta(seconds=61)

    recovery = TaskRuntime(session_factory, snapshot_store).recover_interrupted(
        now=now
    )
    assert recovery.retried == (task_id,)
    assert recovery.completed == ()

    result = adapter.decide_learning_change(principal, request)
    assert result.task_id == task_id
    assert result.decision == "reject"
    assert result.learning_change_status == "rejected"
    assert result.task_status == "done"
    assert result.attempt_count == 2

    with session_factory() as session:
        task = session.get(Task, task_id)
        assert task is not None and task.status == "done"
        assert task.attempt_count == 2
        starts = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task_id,
                    Event.type == "task_started",
                )
            )
        )
        retries = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task_id,
                    Event.type == "task_retry_scheduled",
                )
            )
        )
        decision = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == "learning_change_rejected",
            )
        )
        assert len(starts) == 2
        assert len(retries) == 1
        assert decision is not None
        assert decision.payload["attempt_count"] == 2

    _cleanup_operator_decision_task(session_factory, task_id)


def test_operator_terminal_result_is_fenced_and_must_match_decision(
    session_factory, snapshot_store, distillation_fixture
):
    fixture = distillation_fixture(1, False)
    proposal = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    _run_quality_assessment(
        session_factory, snapshot_store, proposal.learning_change_id
    )
    principal = _approval_principal(fixture.team_id)
    request = LearningChangeDecisionRequest(
        learning_change_id=proposal.learning_change_id,
        decision="accept",
        idempotency_key=uuid4(),
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    task_request = adapter.request_learning_change_decision(principal, request)
    runtime = TaskRuntime(session_factory, snapshot_store)
    runtime.admit(task_request.task_id)

    stale_start = datetime.now(timezone.utc) - timedelta(seconds=61)
    with session_factory.begin() as session:
        start = session.scalar(
            select(Event).where(
                Event.task_id == task_request.task_id,
                Event.type == "task_started",
            )
        )
        assert start is not None
        start.created_at = stale_start
    recovered = runtime.recover_interrupted(now=datetime.now(timezone.utc))
    assert recovered.retried == (task_request.task_id,)

    second = runtime.admit(task_request.task_id)
    commit = LearningCommitService(session_factory, snapshot_store).decide(
        task_request.task_id, second.attempt_count, principal
    )
    stale_observation = TerminalObservation(
        task_id=task_request.task_id,
        attempt=1,
        result_category="success_learning_change_accepted",
        observed_at=commit.committed_at,
        learning_change_id=commit.learning_change_id,
    )
    with pytest.raises(TaskNotFinalizable, match="stale_attempt"):
        runtime.finalize(stale_observation)

    wrong_observation = TerminalObservation(
        task_id=task_request.task_id,
        attempt=second.attempt_count,
        result_category="success_learning_change_rejected",
        observed_at=commit.committed_at,
        learning_change_id=commit.learning_change_id,
    )
    with pytest.raises(
        TaskNotFinalizable, match="learning_change_decision_result_mismatch"
    ):
        runtime.finalize(wrong_observation)

    terminal = runtime.finalize(
        TerminalObservation(
            task_id=task_request.task_id,
            attempt=second.attempt_count,
            result_category="success_learning_change_accepted",
            observed_at=commit.committed_at,
            learning_change_id=commit.learning_change_id,
        )
    )
    assert terminal.status == "done"
    with session_factory() as session:
        task = session.get(Task, task_request.task_id)
        assert task is not None and task.status == "done"
        assert task.attempt_count == 2
        assert session.scalar(
            select(Outcome.id).where(
                Outcome.recorded_by_task_id == task_request.task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) is not None

    _cleanup_operator_decision_task(session_factory, task_request.task_id)


@pytest.mark.parametrize("tamper", ["knowledge_item", "decision_event"])
def test_learning_commit_replay_rejects_tampered_canonical_records(
    session_factory, snapshot_store, distillation_fixture, tamper: str
):
    fixture = distillation_fixture(1, False)
    proposal = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    task_id, attempt, principal = _create_admitted_approval_task(
        session_factory, snapshot_store, fixture.team_id, proposal.learning_change_id
    )
    try:
        result = LearningCommitService(session_factory, snapshot_store).decide(
            task_id, attempt, principal
        )
        assert result.knowledge_item_id is not None
        with session_factory.begin() as session:
            if tamper == "knowledge_item":
                item = session.get(KnowledgeItem, result.knowledge_item_id)
                assert item is not None
                item.body = "A post-commit mutation that must not replay."
            else:
                event = session.scalar(
                    select(Event).where(
                        Event.task_id == task_id,
                        Event.type == "learning_change_accepted",
                    )
                )
                assert event is not None
                payload = dict(event.payload)
                payload["proposal_hash"] = "sha256:" + "0" * 64
                event.payload = payload

        expected = (
            "committed_knowledge_item_mismatch"
            if tamper == "knowledge_item"
            else "learning_change_decision_event_mismatch"
        )
        with pytest.raises(LearningCommitCorrupt, match=expected):
            LearningCommitService(session_factory, snapshot_store).decide(
                task_id, attempt, principal
            )
    finally:
        with session_factory.begin() as session:
            committed_change_ids = list(
                session.scalars(
                    select(LearningChange.id).where(
                        LearningChange.committed_by_task_id == task_id
                    )
                )
            )
            if committed_change_ids:
                session.execute(
                    delete(KnowledgeItem).where(
                        KnowledgeItem.origin_learning_change_id.in_(
                            committed_change_ids
                        )
                    )
                )
                session.execute(
                    delete(KnowledgeQualityAssessment).where(
                        KnowledgeQualityAssessment.learning_change_id.in_(
                            committed_change_ids
                        )
                    )
                )
                session.execute(
                    delete(LearningChange).where(
                        LearningChange.id.in_(committed_change_ids)
                    )
                )
            session.execute(delete(Event).where(Event.task_id == task_id))
            session.execute(delete(Task).where(Task.id == task_id))


def test_original_create_approval_replays_after_later_history_transition(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False)
    proposal = _distiller(session_factory, snapshot_store, _provider()).propose(
        fixture.distillation_task_id, [fixture.cases[0].evaluation_id]
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    task_id, attempt, principal = _create_admitted_approval_task(
        session_factory, snapshot_store, fixture.team_id, proposal.learning_change_id
    )
    service = LearningCommitService(session_factory, snapshot_store)
    later_task_id: UUID | None = None
    later_change_id: UUID | None = None
    try:
        original = service.decide(task_id, attempt, principal)
        assert original.knowledge_item_id is not None
        TaskRuntime(session_factory, snapshot_store).finalize(
            TerminalObservation(
                task_id=task_id,
                attempt=attempt,
                result_category="success_learning_change_accepted",
                observed_at=original.committed_at,
                learning_change_id=original.learning_change_id,
            )
        )

        later_task_id, later_change_id = uuid4(), uuid4()
        later_committed_at = original.committed_at + timedelta(minutes=1)
        later_started_at = later_committed_at - timedelta(seconds=30)
        operator_id = "test-host|later-revision-operator"
        with session_factory.begin() as session:
            item = session.get(KnowledgeItem, original.knowledge_item_id)
            assert item is not None
            previous = knowledge_item_state(item)
            committed = dict(previous)
            committed.update(
                {
                    "body": "A later accepted revision, after the original create.",
                    "version": 2,
                    "current_learning_change_id": str(later_change_id),
                }
            )
            session.add(
                Task(
                    id=later_task_id,
                    team_id=fixture.team_id,
                    task_type="approve_learning_change",
                    status="running",
                    attempt_count=1,
                    policy_version=1,
                    allowed_writes=["LearningChange", "KnowledgeItem"],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.0,
                        "deadline_seconds": 30,
                    },
                    created_at=later_started_at,
                )
            )
            session.flush()
            session.add(
                LearningChange(
                    id=later_change_id,
                    team_id=fixture.team_id,
                    target_kind="knowledge_item",
                    target_id=item.id,
                    operation="revise",
                    proposed_state={
                        "proposal_hash": "sha256:" + ("e" * 64),
                    },
                    previous_state=encode_state_snapshot(previous),
                    committed_state=encode_state_snapshot(committed),
                    evidence_basis=[],
                    evidence_basis_hash="sha256:" + ("f" * 64),
                    status="accepted",
                    idempotency_key="later-revision-" + str(later_change_id),
                    proposed_by_task_id=later_task_id,
                    committed_by_task_id=later_task_id,
                    operator_id=operator_id,
                    created_at=later_started_at,
                    committed_at=later_committed_at,
                )
            )
            session.flush()
            item.body = committed["body"]
            item.version = 2
            item.current_learning_change_id = later_change_id
            session.add_all(
                [
                    Event(
                        id=uuid4(),
                        task_id=later_task_id,
                        type="task_started",
                        payload={
                            "from_status": "pending",
                            "to_status": "running",
                            "attempt_count": 1,
                        },
                        created_at=later_started_at,
                    ),
                    Event(
                        id=uuid4(),
                        task_id=later_task_id,
                        type="learning_change_accepted",
                        payload={
                            "learning_change_id": str(later_change_id),
                            "operation": "revise",
                            "decision": "accept",
                            "operator_id": operator_id,
                            "approval_task_id": str(later_task_id),
                            "attempt_count": 1,
                            "committed_at": later_committed_at.isoformat(),
                        },
                        created_at=later_committed_at,
                    ),
                ]
            )

        replay = service.decide(task_id, attempt, principal)
        assert replay.replayed is True
        assert replay.learning_change_id == original.learning_change_id
        assert replay.knowledge_item_id == original.knowledge_item_id
        with session_factory() as session:
            item = session.get(KnowledgeItem, original.knowledge_item_id)
            assert item is not None
            assert item.version == 2
            assert item.current_learning_change_id == later_change_id
            assert item.body == "A later accepted revision, after the original create."
    finally:
        if later_task_id is not None and later_change_id is not None:
            with session_factory.begin() as session:
                # The KnowledgeItem's current pointer references this change.
                # Remove the fixture item before deleting its referenced change.
                session.execute(
                    delete(KnowledgeItem).where(
                        KnowledgeItem.id == original.knowledge_item_id
                    )
                )
                session.execute(
                    delete(LearningChange).where(LearningChange.id == later_change_id)
                )
                session.execute(delete(Event).where(Event.task_id == later_task_id))
                session.execute(delete(Task).where(Task.id == later_task_id))
        _cleanup_operator_decision_task(session_factory, task_id)


@pytest.mark.parametrize(
    (
        "assessment_result",
        "crash_after_record",
        "fail_record_first",
        "fail_finalization_first",
    ),
    [
        ("eligible", False, False, False),
        ("eligible", True, False, False),
        ("ineligible", False, False, False),
        ("ineligible", True, False, False),
        ("eligible", False, True, False),
        ("eligible", False, False, True),
    ],
)
def test_lifecycle_retire_assessment_records_once_without_canonical_writes(
    session_factory,
    snapshot_store,
    distillation_fixture,
    request,
    monkeypatch,
    assessment_result: str,
    crash_after_record: bool,
    fail_record_first: bool,
    fail_finalization_first: bool,
):
    from core.knowledge_approval import (
        KnowledgeApprovalBindingError,
        build_approval_binding,
    )
    from core.knowledge_lifecycle import (
        PROPOSED_STATE_HASH_DOMAIN,
        _domain_hash,
        _normalize_json,
        _sha256_json,
        _task_id,
        derive_lifecycle_findings,
        require_recorded_assessment,
    )
    from core.knowledge_lifecycle_tasks import (
        KnowledgeLifecycleAssessmentTask,
        KnowledgeLifecycleAssessmentTaskRunner,
    )
    from core.models import (
        Event,
        KnowledgeLifecycleAssessment,
        LearningChangeOperatorProvenance,
        Outcome,
        Task,
    )
    from core.operator_approval import canonical_operator_identity

    if assessment_result == "ineligible":
        original_derive = derive_lifecycle_findings

        def derive_ineligible(
            operation,
            target_state,
            successor_binding,
            recorded_at,
        ):
            findings, _ = original_derive(
                operation,
                target_state,
                successor_binding,
                recorded_at,
            )
            findings[2] = {
                **findings[2],
                "outcome": "failed",
                "summary": "The test injects an ineligible assessment finding.",
            }
            return findings, "ineligible"

        monkeypatch.setattr(
            "core.knowledge_lifecycle.derive_lifecycle_findings",
            derive_ineligible,
        )

    fixture = distillation_fixture(2, include_contrary=False)
    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    approval_task_id, approval_attempt, principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    committed = LearningCommitService(session_factory, snapshot_store).decide(
        approval_task_id, approval_attempt, principal
    )
    assert committed.knowledge_item_id is not None
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=approval_task_id,
            attempt=approval_attempt,
            result_category="success_learning_change_accepted",
            observed_at=committed.committed_at,
            learning_change_id=committed.learning_change_id,
        )
    )

    source_task_id, learning_change_id = uuid4(), uuid4()
    started_at = datetime.now(timezone.utc)
    completed_at = started_at + timedelta(seconds=2)
    proposal_hash = "sha256:" + ("d" * 64)
    rationale = {
        "schema_version": 1,
        "summary": "The existing procedure is no longer appropriate for this context.",
        "reasons": [
            {
                "category": "evidence_no_longer_reliable",
                "statement": "The primary supporting source has been superseded.",
            },
            {
                "category": "applicability_changed",
                "statement": "The original applicability conditions no longer hold.",
            },
        ],
    }
    observation_ref, observation_hash = snapshot_store.put(
        (
            '{"attempt":1,"learning_change_id":"'
            + str(learning_change_id)
            + '","result_category":"success_learning_change_proposed"}'
        ).encode("utf-8")
    )

    with session_factory.begin() as session:
        team = session.get(Team, fixture.team_id)
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        assert team is not None and item is not None
        source_task = Task(
            id=source_task_id,
            team_id=fixture.team_id,
            task_type="propose_learning_change",
            status="done",
            attempt_count=1,
            policy_version=1,
            objective_id=None,
            plan_id=None,
            plan_action_id=None,
            allowed_writes=["LearningChange"],
            budget={
                "max_tool_calls": 0,
                "max_cost_usd": 0.0,
                "deadline_seconds": 30,
            },
            created_at=started_at,
            completed_at=completed_at,
            max_attempts=3,
        )
        session.add(source_task)
        session.flush()
        pack = ExperienceDistiller(
            session_factory, snapshot_store, provider=None
        )._build_pack(
            session,
            source_task,
            team,
            tuple(sorted(case.evaluation_id for case in fixture.cases)),
            allow_completed_task=True,
            include_version_marker=True,
        )
        previous_state = knowledge_item_state(item)
        proposed_state = {
            "proposal_hash": proposal_hash,
            "evidence_basis_hash": pack.basis_hash,
            "operator_rationale": rationale,
        }
        proposed_state_hash = _domain_hash(
            PROPOSED_STATE_HASH_DOMAIN, _normalize_json(proposed_state)
        )
        change = LearningChange(
            id=learning_change_id,
            team_id=fixture.team_id,
            target_kind="knowledge_item",
            target_id=item.id,
            operation="retire",
            proposed_state=proposed_state,
            previous_state=encode_state_snapshot(previous_state),
            committed_state=None,
            evidence_basis=pack.evidence_basis,
            evidence_basis_hash=pack.basis_hash,
            status="proposed",
            idempotency_key=f"r7b-lifecycle-test-{learning_change_id}",
            proposed_by_task_id=source_task_id,
            committed_by_task_id=None,
            operator_id=None,
            decision_reason=None,
            created_at=started_at,
        )
        session.add(change)
        session.flush()
        session.add(
            LearningChangeOperatorProvenance(
                learning_change_id=learning_change_id,
                team_id=fixture.team_id,
                issuer="https://operator.example.test",
                subject="operator-lifecycle-test",
                recorded_at=started_at,
            )
        )
        outcome = Outcome(
            id=uuid4(),
            team_id=fixture.team_id,
            subject_kind="task",
            subject_id=source_task_id,
            outcome_type="task_execution",
            expected=None,
            observation_snapshot_ref=observation_ref,
            observation_hash=observation_hash,
            observed_at=completed_at,
            recorded_by_task_id=source_task_id,
        )
        session.add(outcome)
        session.flush()
        session.add_all(
            [
                Event(
                    id=uuid4(),
                    task_id=source_task_id,
                    type="task_started",
                    payload={
                        "from_status": "pending",
                        "to_status": "running",
                        "attempt_count": 1,
                    },
                    created_at=started_at,
                ),
                Event(
                    id=uuid4(),
                    task_id=source_task_id,
                    type="learning_change_proposed",
                    payload={
                        "learning_change_id": str(learning_change_id),
                        "operation": "retire",
                        "proposal_hash": proposal_hash,
                        "proposed_state_hash": proposed_state_hash,
                        "evidence_basis_hash": pack.basis_hash,
                        "attempt_count": 1,
                    },
                    created_at=completed_at - timedelta(seconds=1),
                ),
                Event(
                    id=uuid4(),
                    task_id=source_task_id,
                    type="task_completed",
                    payload={
                        "from_status": "running",
                        "to_status": "done",
                        "attempt_count": 1,
                        "result_category": "success_learning_change_proposed",
                        "failure_reason": None,
                        "outcome_id": str(outcome.id),
                        "observation_snapshot_ref": observation_ref,
                        "observation_hash": observation_hash,
                        "learning_change_id": str(learning_change_id),
                    },
                    created_at=completed_at,
                ),
            ]
        )

    task_id = _task_id(fixture.team_id, learning_change_id)

    failed_task_id = uuid4()
    retry_task_id = uuid4()

    def cleanup_lifecycle_records():
        task_ids = [
            source_task_id,
            task_id,
            failed_task_id,
            retry_task_id,
        ]
        with session_factory.begin() as session:
            session.execute(
                text(
                    "ALTER TABLE knowledge_lifecycle_assessments "
                    "DISABLE TRIGGER USER"
                )
            )
            session.execute(
                delete(KnowledgeLifecycleAssessment).where(
                    KnowledgeLifecycleAssessment.task_id == task_id
                )
            )
            session.execute(
                text(
                    "ALTER TABLE knowledge_lifecycle_assessments "
                    "ENABLE TRIGGER USER"
                )
            )
            session.execute(
                text(
                    "ALTER TABLE learning_change_operator_provenance "
                    "DISABLE TRIGGER USER"
                )
            )
            session.execute(
                delete(LearningChangeOperatorProvenance).where(
                    LearningChangeOperatorProvenance.learning_change_id
                    == learning_change_id
                )
            )
            session.execute(
                text(
                    "ALTER TABLE learning_change_operator_provenance "
                    "ENABLE TRIGGER USER"
                )
            )
            session.execute(
                delete(Event).where(Event.task_id.in_(task_ids))
            )
            session.execute(
                delete(Outcome).where(
                    Outcome.recorded_by_task_id.in_(task_ids)
                )
            )
            session.execute(
                delete(LearningChange).where(
                    LearningChange.id == learning_change_id
                )
            )
            session.execute(
                delete(Task).where(Task.id.in_(task_ids))
            )

    request.addfinalizer(cleanup_lifecycle_records)
    task_adapter = KnowledgeLifecycleAssessmentTask(
        session_factory, snapshot_store
    )
    from core.knowledge_lifecycle import (
        RECORDED_EVENT_TYPE,
        REQUEST_EVENT_TYPE,
        KnowledgeLifecycleAssessmentError,
    )

    with session_factory() as session:
        change = session.get(LearningChange, learning_change_id)
        proposal_event = session.scalar(
            select(Event).where(
                Event.task_id == source_task_id,
                Event.type == "learning_change_proposed",
            )
        )
        assert change is not None and proposal_event is not None
        original_proposed_state = dict(change.proposed_state)
        original_proposal_event_payload = dict(proposal_event.payload)

    invalid_rationale_variants = [
        "missing_rationale",
        "malformed_rationale",
        "missing_reason_statement",
        "retire_with_null_successor_field",
    ]
    for invalid_variant in invalid_rationale_variants:
        with session_factory.begin() as session:
            change = session.get(LearningChange, learning_change_id)
            proposal_event = session.scalar(
                select(Event).where(
                    Event.task_id == source_task_id,
                    Event.type == "learning_change_proposed",
                )
            )
            assert change is not None and proposal_event is not None
            mutated = dict(original_proposed_state)
            if invalid_variant == "missing_rationale":
                mutated.pop("operator_rationale")
            elif invalid_variant == "malformed_rationale":
                mutated["operator_rationale"] = "model supplied free-form rationale"
            elif invalid_variant == "missing_reason_statement":
                mutated["operator_rationale"] = {
                    **rationale,
                    "reasons": [{"category": "improved_evidence"}],
                }
            elif invalid_variant == "retire_with_null_successor_field":
                mutated["successor_knowledge_item_id"] = None
            change.proposed_state = mutated
            mutated_hash = _domain_hash(
                PROPOSED_STATE_HASH_DOMAIN, _normalize_json(mutated)
            )
            proposal_event.payload = {
                **original_proposal_event_payload,
                "proposed_state_hash": mutated_hash,
            }

        with pytest.raises(KnowledgeLifecycleAssessmentError):
            task_adapter.create(learning_change_id)

        with session_factory() as session:
            assert session.get(Task, task_id) is None
            assert session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == task_id,
                    Event.type == REQUEST_EVENT_TYPE,
                )
            ) == 0
            assert session.scalar(
                select(func.count(KnowledgeLifecycleAssessment.id)).where(
                    KnowledgeLifecycleAssessment.learning_change_id
                    == learning_change_id
                )
            ) == 0
            assert session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == task_id,
                    Event.type == RECORDED_EVENT_TYPE,
                )
            ) == 0
            assert session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == task_id
                )
            ) == 0

        with session_factory.begin() as session:
            change = session.get(LearningChange, learning_change_id)
            proposal_event = session.scalar(
                select(Event).where(
                    Event.task_id == source_task_id,
                    Event.type == "learning_change_proposed",
                )
            )
            assert change is not None and proposal_event is not None
            change.proposed_state = dict(original_proposed_state)
            proposal_event.payload = dict(original_proposal_event_payload)

    assert task_adapter.create(learning_change_id) == task_id
    assert task_adapter.create(learning_change_id) == task_id
    task_adapter.validate(task_id)

    from core.knowledge_lifecycle import REQUEST_EVENT_TYPE
    from core.task_runtime import TaskNotEligible

    admission_runtime = TaskRuntime(session_factory, snapshot_store)
    invalid_shapes = [
        ("task_type", "unrecognized_assessment_task"),
        ("allowed_writes", ["KnowledgeItem"]),
        (
            "budget",
            {
                "max_tool_calls": 1,
                "max_cost_usd": 0.0,
                "deadline_seconds": 30,
            },
        ),
        ("max_attempts", 4),
    ]
    for attribute, invalid_value in invalid_shapes:
        with session_factory.begin() as session:
            task = session.get(Task, task_id)
            assert task is not None
            original_value = getattr(task, attribute)
            setattr(task, attribute, invalid_value)
        with pytest.raises(TaskNotEligible):
            admission_runtime.admit(task_id)
        with session_factory.begin() as session:
            task = session.get(Task, task_id)
            assert task is not None
            setattr(task, attribute, original_value)

    with session_factory.begin() as session:
        request_event = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
        assert request_event is not None
        duplicate_request_id = uuid4()
        session.add(
            Event(
                id=duplicate_request_id,
                task_id=task_id,
                type=REQUEST_EVENT_TYPE,
                payload=dict(request_event.payload),
                created_at=request_event.created_at,
            )
        )
    with pytest.raises(
        TaskNotEligible,
        match="knowledge_lifecycle_request_event_invalid",
    ):
        admission_runtime.admit(task_id)
    with session_factory.begin() as session:
        session.execute(delete(Event).where(Event.id == duplicate_request_id))

    first_admission = admission_runtime.admit(task_id)
    assert first_admission.attempt_count == 1
    retry_recovery = admission_runtime.recover_interrupted(
        now=datetime.now(timezone.utc) + timedelta(seconds=61)
    )
    assert retry_recovery.retried == (task_id,)
    assert retry_recovery.completed == ()
    assert retry_recovery.failed == ()

    with pytest.raises(
        TaskNotFinalizable,
        match="knowledge_lifecycle_assessment_id_required",
    ):
        TaskRuntime._validate_observation(
            TerminalObservation(
                task_id=task_id,
                attempt=1,
                result_category="success_knowledge_lifecycle_assessed",
                observed_at=datetime.now(timezone.utc),
            )
        )
    with pytest.raises(
        TaskNotFinalizable,
        match="terminal_evidence_not_allowed",
    ):
        TaskRuntime._validate_observation(
            TerminalObservation(
                task_id=task_id,
                attempt=1,
                result_category="terminal_failure",
                observed_at=datetime.now(timezone.utc),
                failure_reason="invalid foreign assessment identity",
                knowledge_lifecycle_assessment_id=uuid4(),
            )
        )

    class CrashAfterAssessmentRecordRuntime(TaskRuntime):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.crash_next_success = crash_after_record

        def finalize(self, observation):
            if (
                self.crash_next_success
                and observation.result_category
                == "success_knowledge_lifecycle_assessed"
            ):
                self.crash_next_success = False
                raise RuntimeError(
                    "simulated_process_loss_after_lifecycle_assessment_commit"
                )
            return super().finalize(observation)

    crash_runtime = CrashAfterAssessmentRecordRuntime(
        session_factory, snapshot_store
    )
    runner = KnowledgeLifecycleAssessmentTaskRunner(
        session_factory,
        snapshot_store,
        runtime=crash_runtime,
    )
    if fail_record_first:
        def fail_assessment_insert(mapper, connection, assessment) -> None:
            if assessment.task_id == task_id:
                raise IntegrityError(
                    "INSERT INTO knowledge_lifecycle_assessments",
                    {},
                    RuntimeError("simulated_lifecycle_assessment_insert_failure"),
                )

        event.listen(
            KnowledgeLifecycleAssessment,
            "before_insert",
            fail_assessment_insert,
        )
    if fail_record_first:
        try:
            with pytest.raises(IntegrityError):
                runner.run(task_id)
        finally:
            event.remove(
                KnowledgeLifecycleAssessment,
                "before_insert",
                fail_assessment_insert,
            )
        with session_factory() as session:
            interrupted_task = session.get(Task, task_id)
            unchanged_change = session.get(LearningChange, learning_change_id)
            unchanged_item = session.get(KnowledgeItem, committed.knowledge_item_id)
            assert interrupted_task is not None
            assert interrupted_task.status == "running"
            assert interrupted_task.attempt_count == 2
            assert unchanged_change is not None
            assert unchanged_change.status == "proposed"
            assert unchanged_item is not None
            assert unchanged_item.status == "active"
            assert unchanged_item.version == 1
            assert unchanged_item.current_learning_change_id == (
                committed.learning_change_id
            )
            assert session.scalar(
                select(func.count(KnowledgeLifecycleAssessment.id)).where(
                    KnowledgeLifecycleAssessment.task_id == task_id
                )
            ) == 0
            assert session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == task_id,
                    Event.type == RECORDED_EVENT_TYPE,
                )
            ) == 0
            assert session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == task_id
                )
            ) == 0
        persistence_recovery = TaskRuntime(
            session_factory, snapshot_store
        ).recover_interrupted(
            now=datetime.now(timezone.utc) + timedelta(seconds=120)
        )
        assert persistence_recovery.retried == (task_id,)
        assert persistence_recovery.completed == ()
        assert persistence_recovery.failed == ()
        first_run = runner.run(task_id)
        assert first_run.status == "done"
        assert first_run.assessment_result == assessment_result
        assert first_run.assessment_id is not None
        assert first_run.outcome_id is not None
        assert not first_run.replayed
    elif fail_finalization_first:
        def fail_terminal_event_insert(mapper, connection, event_record) -> None:
            if (
                event_record.task_id == task_id
                and event_record.type == "task_completed"
            ):
                raise IntegrityError(
                    "INSERT INTO events",
                    {},
                    RuntimeError("simulated_lifecycle_finalization_event_failure"),
                )

        event.listen(Event, "before_insert", fail_terminal_event_insert)
        try:
            with pytest.raises(IntegrityError):
                runner.run(task_id)
        finally:
            event.remove(Event, "before_insert", fail_terminal_event_insert)

        with session_factory() as session:
            interrupted_task = session.get(Task, task_id)
            recorded_assessment = session.scalar(
                select(KnowledgeLifecycleAssessment).where(
                    KnowledgeLifecycleAssessment.task_id == task_id
                )
            )
            assert interrupted_task is not None
            assert interrupted_task.status == "running"
            assert interrupted_task.attempt_count == 2
            assert recorded_assessment is not None
            assert session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == task_id,
                    Event.type == RECORDED_EVENT_TYPE,
                )
            ) == 1
            assert session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == task_id
                )
            ) == 0
            assert session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == task_id,
                    Event.type == "task_completed",
                )
            ) == 0
            unchanged_change = session.get(LearningChange, learning_change_id)
            unchanged_item = session.get(KnowledgeItem, committed.knowledge_item_id)
            assert unchanged_change is not None
            assert unchanged_change.status == "proposed"
            assert unchanged_item is not None
            assert unchanged_item.status == "active"
            assert unchanged_item.version == 1
            assert unchanged_item.current_learning_change_id == (
                committed.learning_change_id
            )

        event.listen(Event, "before_insert", fail_terminal_event_insert)
        try:
            with pytest.raises(IntegrityError):
                TaskRuntime(session_factory, snapshot_store).recover_interrupted(
                    now=datetime.now(timezone.utc) + timedelta(seconds=120)
                )
        finally:
            event.remove(Event, "before_insert", fail_terminal_event_insert)

        with session_factory() as session:
            still_running = session.get(Task, task_id)
            assert still_running is not None
            assert still_running.status == "running"
            assert session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == task_id
                )
            ) == 0
            assert session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == task_id,
                    Event.type == "task_completed",
                )
            ) == 0
            assert session.scalar(
                select(func.count(KnowledgeLifecycleAssessment.id)).where(
                    KnowledgeLifecycleAssessment.task_id == task_id
                )
            ) == 1
            assert session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == task_id,
                    Event.type == RECORDED_EVENT_TYPE,
                )
            ) == 1

        final_recovery = TaskRuntime(
            session_factory, snapshot_store
        ).recover_interrupted(
            now=datetime.now(timezone.utc) + timedelta(seconds=180)
        )
        assert final_recovery.completed == (task_id,)
        assert final_recovery.retried == ()
        assert final_recovery.failed == ()
        first_run = runner.run(task_id)
        assert first_run.status == "done"
        assert first_run.assessment_result == assessment_result
        assert first_run.assessment_id is not None
        assert first_run.outcome_id is not None
        assert first_run.replayed
    elif crash_after_record:
        with pytest.raises(
            RuntimeError,
            match="simulated_process_loss_after_lifecycle_assessment_commit",
        ):
            runner.run(task_id)
    else:
        first_run = runner.run(task_id)
        assert first_run.status == "done"
        assert first_run.assessment_result == assessment_result
        assert first_run.assessment_id is not None
        assert first_run.outcome_id is not None
        assert first_run.replayed is fail_finalization_first

    with session_factory() as session:
        committed_assessment = session.scalar(
            select(KnowledgeLifecycleAssessment).where(
                KnowledgeLifecycleAssessment.task_id == task_id
            )
        )
        recorded_task = session.get(Task, task_id)
        assert committed_assessment is not None
        assert recorded_task is not None
        assert recorded_task.status == ("running" if crash_after_record else "done")
        recorded_at = committed_assessment.recorded_at
        expected_outcomes = 0 if crash_after_record else 1
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == task_id
            )
        ) == expected_outcomes

    if crash_after_record:
        recovery_at = recorded_at + timedelta(seconds=61)
        with session_factory.begin() as session:
            recorded_event = session.get(
                Event, committed_assessment.recorded_event_id
            )
            assert recorded_event is not None
            original_recorded_payload = dict(recorded_event.payload)
            recorded_event.payload = {
                **original_recorded_payload,
                "assessment_payload_hash": "sha256:" + ("0" * 64),
            }
        with pytest.raises(
            TaskNotFinalizable,
            match="knowledge_lifecycle_recorded_event_invalid",
        ):
            TaskRuntime(session_factory, snapshot_store).recover_interrupted(
                now=recovery_at
            )
        with session_factory() as session:
            still_running = session.get(Task, task_id)
            assert still_running is not None and still_running.status == "running"
            assert session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == task_id
                )
            ) == 0
        with session_factory.begin() as session:
            recorded_event = session.get(
                Event, committed_assessment.recorded_event_id
            )
            assert recorded_event is not None
            recorded_event.payload = original_recorded_payload
            original_recorded_type = recorded_event.type
            recorded_event.type = "tampered_lifecycle_recorded_event_type"
        with pytest.raises(
            TaskNotFinalizable,
            match="knowledge_lifecycle_recorded_event_invalid",
        ):
            TaskRuntime(session_factory, snapshot_store).recover_interrupted(
                now=recovery_at
            )
        with session_factory() as session:
            still_running = session.get(Task, task_id)
            assert still_running is not None
            assert still_running.status == "running"
            assert session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == task_id
                )
            ) == 0
        with session_factory.begin() as session:
            recorded_event = session.get(
                Event, committed_assessment.recorded_event_id
            )
            assert recorded_event is not None
            recorded_event.type = original_recorded_type

        duplicate_recorded_event_id = uuid4()
        with session_factory.begin() as session:
            recorded_event = session.get(
                Event, committed_assessment.recorded_event_id
            )
            assert recorded_event is not None
            session.add(
                Event(
                    id=duplicate_recorded_event_id,
                    task_id=task_id,
                    type=original_recorded_type,
                    payload=original_recorded_payload,
                    created_at=recorded_event.created_at + timedelta(seconds=1),
                )
            )
        with pytest.raises(
            TaskNotFinalizable,
            match="knowledge_lifecycle_recorded_event_invalid",
        ):
            TaskRuntime(session_factory, snapshot_store).recover_interrupted(
                now=recovery_at
            )
        with session_factory() as session:
            still_running = session.get(Task, task_id)
            assert still_running is not None
            assert still_running.status == "running"
            assert session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == task_id
                )
            ) == 0
        with session_factory.begin() as session:
            session.execute(
                delete(Event).where(Event.id == duplicate_recorded_event_id)
            )

        first = task_adapter.record(task_id)
        assert first.assessment_result == assessment_result
        assert first.replayed
        assert first.assessment_id == committed_assessment.id
        assert first.assessment_payload_hash == committed_assessment.payload_hash

        recovery = TaskRuntime(session_factory, snapshot_store).recover_interrupted(
            now=recovery_at
        )
        assert recovery.completed == (task_id,)
        assert recovery.retried == ()
        assert recovery.failed == ()
        first_assessment_id = first.assessment_id
        first_assessment_result = first.assessment_result
        first_payload_hash = first.assessment_payload_hash
    else:
        first_assessment_id = first_run.assessment_id
        first_assessment_result = first_run.assessment_result
        first_payload_hash = committed_assessment.payload_hash

    with session_factory.begin() as session:
        terminal_event = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == "task_completed",
            )
        )
        assert terminal_event is not None
        original_terminal_payload = dict(terminal_event.payload)
        terminal_event.payload = {
            **original_terminal_payload,
            "knowledge_lifecycle_assessment_id": str(uuid4()),
        }
    with pytest.raises(
        TaskNotFinalizable,
        match="knowledge_lifecycle_terminal_event_invalid",
    ):
        runner.run(task_id)
    with session_factory.begin() as session:
        terminal_event = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == "task_completed",
            )
        )
        assert terminal_event is not None
        terminal_event.payload = original_terminal_payload

    replay = runner.run(task_id)
    assert replay.status == "done"
    assert replay.replayed
    assert replay.assessment_id == first_assessment_id
    assert replay.assessment_result == assessment_result
    assert first_assessment_result == assessment_result
    assert replay.outcome_id is not None

    # Build a second, valid lifecycle Task whose execution terminates in failure.
    # Its request Event is copied from the valid task and rebound to a new Task ID.
    failure_started_at = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        original_task = session.get(Task, task_id)
        original_request = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
        assert original_task is not None and original_request is not None
        failed_request_payload = dict(original_request.payload)
        failed_request_payload["task_id"] = str(failed_task_id)
        unsigned_request = {
            key: value
            for key, value in failed_request_payload.items()
            if key != "request_hash"
        }
        failed_request_payload["request_hash"] = _sha256_json(unsigned_request)
        failed_task = Task(
            id=failed_task_id,
            team_id=original_task.team_id,
            task_type=original_task.task_type,
            status="running",
            attempt_count=1,
            policy_version=original_task.policy_version,
            objective_id=None,
            plan_id=None,
            plan_action_id=None,
            allowed_writes=list(original_task.allowed_writes),
            budget=dict(original_task.budget),
            created_at=failure_started_at,
            completed_at=None,
            max_attempts=original_task.max_attempts,
        )
        session.add(failed_task)
        session.flush()
        session.add_all(
            [
                Event(
                    id=uuid4(),
                    task_id=failed_task_id,
                    type=REQUEST_EVENT_TYPE,
                    payload=failed_request_payload,
                    created_at=failure_started_at,
                ),
                Event(
                    id=uuid4(),
                    task_id=failed_task_id,
                    type="task_started",
                    payload={
                        "from_status": "pending",
                        "to_status": "running",
                        "attempt_count": 1,
                    },
                    created_at=failure_started_at,
                ),
            ]
        )

    failure_finalization = TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=failed_task_id,
            attempt=1,
            result_category="terminal_failure",
            observed_at=failure_started_at,
            failure_reason="injected_lifecycle_assessment_failure",
        )
    )
    with session_factory() as session:
        failed_outcome = session.get(Outcome, failure_finalization.outcome_id)
        assert failed_outcome is not None
        failed_outcome_values = {
            "id": failed_outcome.id,
            "team_id": failed_outcome.team_id,
            "subject_kind": failed_outcome.subject_kind,
            "subject_id": failed_outcome.subject_id,
            "outcome_type": failed_outcome.outcome_type,
            "expected": failed_outcome.expected,
            "observation_snapshot_ref": failed_outcome.observation_snapshot_ref,
            "observation_hash": failed_outcome.observation_hash,
            "observed_at": failed_outcome.observed_at,
            "recorded_by_task_id": failed_outcome.recorded_by_task_id,
        }

    failed_replay = runner.run(failed_task_id)
    assert failed_replay.status == "failed"
    assert failed_replay.replayed
    assert failed_replay.outcome_id == failure_finalization.outcome_id

    # Failed replay must reject an unrelated Task type.
    with session_factory.begin() as session:
        failed_task = session.get(Task, failed_task_id)
        assert failed_task is not None
        failed_task.task_type = "unrelated_task"
    with pytest.raises(TaskNotEligible, match="knowledge_lifecycle_task_wrong_type"):
        runner.run(failed_task_id)
    with session_factory.begin() as session:
        failed_task = session.get(Task, failed_task_id)
        assert failed_task is not None
        failed_task.task_type = "assess_knowledge_lifecycle"

    # A missing or duplicated terminal Outcome is corruption, not a replay.
    with session_factory.begin() as session:
        session.execute(
            delete(Outcome).where(Outcome.id == failure_finalization.outcome_id)
        )
    with pytest.raises(
        TaskNotEligible, match="knowledge_lifecycle_terminal_outcome_invalid"
    ):
        runner.run(failed_task_id)
    with session_factory.begin() as session:
        session.add(Outcome(**failed_outcome_values))
        session.add(
            Outcome(
                **{
                    **failed_outcome_values,
                    "id": uuid4(),
                    "outcome_type": "secondary_task_execution",
                }
            )
        )
    with pytest.raises(
        TaskNotEligible, match="knowledge_lifecycle_terminal_outcome_invalid"
    ):
        runner.run(failed_task_id)
    with session_factory.begin() as session:
        session.execute(
            delete(Outcome).where(
                Outcome.recorded_by_task_id == failed_task_id,
                Outcome.id != failure_finalization.outcome_id,
            )
        )
        failed_outcome = session.get(Outcome, failure_finalization.outcome_id)
        assert failed_outcome is not None
        failed_outcome.subject_kind = "signal"
        failed_outcome.outcome_type = "secondary_task_execution"
    with pytest.raises(
        TaskNotEligible, match="knowledge_lifecycle_terminal_outcome_invalid"
    ):
        runner.run(failed_task_id)
    with session_factory.begin() as session:
        failed_outcome = session.get(Outcome, failure_finalization.outcome_id)
        assert failed_outcome is not None
        failed_outcome.subject_kind = "task"
        failed_outcome.outcome_type = "task_execution"

    # A missing terminal Event must also fail closed.
    with session_factory.begin() as session:
        attempt_failed_event = session.scalar(
            select(Event).where(
                Event.task_id == failed_task_id,
                Event.type == "task_attempt_failed",
            )
        )
        assert attempt_failed_event is not None
        original_attempt_failed_payload = dict(attempt_failed_event.payload)
        attempt_failed_event.payload = {
            **original_attempt_failed_payload,
            "failure_reason": "tampered",
        }
    with pytest.raises(
        TaskNotEligible, match="knowledge_lifecycle_terminal_events_invalid"
    ):
        runner.run(failed_task_id)
    with session_factory.begin() as session:
        attempt_failed_event = session.scalar(
            select(Event).where(
                Event.task_id == failed_task_id,
                Event.type == "task_attempt_failed",
            )
        )
        assert attempt_failed_event is not None
        attempt_failed_event.payload = original_attempt_failed_payload
        session.execute(
            delete(Event).where(
                Event.task_id == failed_task_id,
                Event.type == "task_attempt_failed",
            )
        )
    with pytest.raises(
        TaskNotEligible, match="knowledge_lifecycle_terminal_events_invalid"
    ):
        runner.run(failed_task_id)
    with session_factory.begin() as session:
        session.add(
            Event(
                id=uuid4(),
                task_id=failed_task_id,
                type="task_attempt_failed",
                payload=original_attempt_failed_payload,
                created_at=failure_started_at,
            )
        )
    assert runner.run(failed_task_id).replayed

    # A retryable interrupted attempt and a later terminal failure are distinct
    # attempt failures. Failed replay must select the terminal attempt while
    # validating the earlier retry transition independently.
    retry_started_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    first_attempt_failed_at = retry_started_at + timedelta(seconds=1)
    second_attempt_started_at = first_attempt_failed_at + timedelta(seconds=1)
    retry_payload = {
        "from_status": "running",
        "to_status": "pending",
        "attempt_count": 1,
        "result_category": "retryable_failure",
        "failure_reason": "interrupted_attempt_recovered",
    }
    with session_factory.begin() as session:
        original_failed_task = session.get(Task, failed_task_id)
        original_request = session.scalar(
            select(Event).where(
                Event.task_id == failed_task_id,
                Event.type == REQUEST_EVENT_TYPE,
            )
        )
        assert original_failed_task is not None and original_request is not None
        retry_request_payload = dict(original_request.payload)
        retry_request_payload["task_id"] = str(retry_task_id)
        unsigned_retry_request = {
            key: value
            for key, value in retry_request_payload.items()
            if key != "request_hash"
        }
        retry_request_payload["request_hash"] = _sha256_json(
            unsigned_retry_request
        )
        session.add(
            Task(
                id=retry_task_id,
                team_id=original_failed_task.team_id,
                task_type=original_failed_task.task_type,
                status="running",
                attempt_count=2,
                policy_version=original_failed_task.policy_version,
                objective_id=None,
                plan_id=None,
                plan_action_id=None,
                allowed_writes=list(original_failed_task.allowed_writes),
                budget=dict(original_failed_task.budget),
                created_at=retry_started_at,
                completed_at=None,
                max_attempts=original_failed_task.max_attempts,
            )
        )
        session.flush()
        session.add_all(
            [
                Event(
                    id=uuid4(),
                    task_id=retry_task_id,
                    type=REQUEST_EVENT_TYPE,
                    payload=retry_request_payload,
                    created_at=retry_started_at - timedelta(seconds=1),
                ),
                Event(
                    id=uuid4(),
                    task_id=retry_task_id,
                    type="task_started",
                    payload={
                        "from_status": "pending",
                        "to_status": "running",
                        "attempt_count": 1,
                    },
                    created_at=retry_started_at,
                ),
                Event(
                    id=uuid4(),
                    task_id=retry_task_id,
                    type="task_attempt_failed",
                    payload=retry_payload,
                    created_at=first_attempt_failed_at,
                ),
                Event(
                    id=uuid4(),
                    task_id=retry_task_id,
                    type="task_retry_scheduled",
                    payload=retry_payload,
                    created_at=first_attempt_failed_at,
                ),
                Event(
                    id=uuid4(),
                    task_id=retry_task_id,
                    type="task_started",
                    payload={
                        "from_status": "pending",
                        "to_status": "running",
                        "attempt_count": 2,
                    },
                    created_at=second_attempt_started_at,
                ),
            ]
        )

    retry_failure = TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=retry_task_id,
            attempt=2,
            result_category="terminal_failure",
            observed_at=second_attempt_started_at,
            failure_reason="terminal_failure_after_retry",
        )
    )
    first_retry_replay = runner.run(retry_task_id)
    second_retry_replay = runner.run(retry_task_id)
    assert first_retry_replay.status == "failed"
    assert first_retry_replay.replayed
    assert first_retry_replay.outcome_id == retry_failure.outcome_id
    assert second_retry_replay.status == "failed"
    assert second_retry_replay.replayed
    assert second_retry_replay.outcome_id == retry_failure.outcome_id
    with session_factory() as session:
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == retry_task_id
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == retry_task_id,
                Event.type == "task_attempt_failed",
            )
        ) == 2
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == retry_task_id,
                Event.type == "task_retry_scheduled",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == retry_task_id,
                Event.type == "task_failed",
            )
        ) == 1

    historical_payload = TaskRuntime._observation_payload(
        TerminalObservation(
            task_id=task_id,
            attempt=1,
            result_category="terminal_failure",
            observed_at=datetime.now(timezone.utc),
            failure_reason="historical_failure",
        )
    )
    assert "knowledge_lifecycle_assessment_id" not in historical_payload

    with session_factory() as session:
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        change = session.get(LearningChange, learning_change_id)
        task = session.get(Task, task_id)
        assessment = session.get(
            KnowledgeLifecycleAssessment, first_assessment_id
        )
        assert item is not None and change is not None and task is not None
        assert assessment is not None
        assert task.status == "done"
        assert task.allowed_writes == ["KnowledgeLifecycleAssessment"]
        assert change.status == "proposed"
        assert change.committed_by_task_id is None
        assert item.current_learning_change_id == committed.learning_change_id
        assert item.version == 1
        assert assessment.operation == "retire"
        assert assessment.assessment_result == assessment_result
        assert assessment.variant_payload == {}
        assert assessment.successor_knowledge_item_id is None
        assert assessment.payload_hash == first_payload_hash
        verified = require_recorded_assessment(
            session,
            change,
            snapshot_store,
            session_factory,
            require_task_done=True,
            require_current=False,
        )
        assert verified.id == assessment.id
        reviewer = canonical_operator_identity(
            "https://host.example/identity", "b37-retire-reviewer"
        )
        if assessment_result == "eligible":
            binding = build_approval_binding(
                session,
                change,
                operator_id=reviewer,
                approval_policy_version=1,
                require_assessment=True,
                snapshot_store=snapshot_store,
                session_factory=session_factory,
            )
            provenance = session.get(
                LearningChangeOperatorProvenance, learning_change_id
            )
            assert provenance is not None
            assert binding["operation"] == "retire"
            assert binding["assessment_type"] == "knowledge_lifecycle"
            assert binding["assessment_id"] == str(assessment.id)
            assert binding["assessment_payload_hash"] == assessment.payload_hash
            assert binding["assessment_task_policy_version"] == task.policy_version
            assert binding["current_learning_change_id"] == str(
                item.current_learning_change_id
            )
            assert binding["target_content_version"] == item.version
            assert binding["target_content_hash"] == assessment.target_content_hash
            assert binding["target_state_hash"] == assessment.target_state_hash
            assert binding["proposal_hash"] == assessment.proposal_hash
            assert binding["proposed_state_hash"] == assessment.proposed_state_hash
            assert binding["evidence_basis_hash"] == assessment.evidence_basis_hash
            assert binding["operator_id"] == reviewer
            assert binding["operator_provenance"] == {
                "issuer": provenance.issuer,
                "subject": provenance.subject,
            }
            assert binding["successor_binding"] is None
        else:
            with pytest.raises(
                KnowledgeApprovalBindingError,
                match="knowledge_approval_lifecycle_not_eligible",
            ):
                build_approval_binding(
                    session,
                    change,
                    operator_id=reviewer,
                    approval_policy_version=1,
                    require_assessment=True,
                    snapshot_store=snapshot_store,
                    session_factory=session_factory,
                )
        assert session.scalar(
            select(func.count(KnowledgeLifecycleAssessment.id)).where(
                KnowledgeLifecycleAssessment.learning_change_id
                == learning_change_id
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == task_id,
                Event.type == "knowledge_lifecycle_assessment_recorded",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) == 1
        terminal_events = list(
            session.scalars(
                select(Event).where(
                    Event.task_id == task_id,
                    Event.type == "task_completed",
                )
            )
        )
        assert len(terminal_events) == 1
        assert terminal_events[0].payload["knowledge_lifecycle_assessment_id"] == str(
            assessment.id
        )

    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        with session_factory.begin() as session:
            session.execute(
                text(
                    "UPDATE knowledge_lifecycle_assessments "
                    "SET assessment_result = 'ineligible' WHERE id = :id"
                ),
                {"id": first_assessment_id},
            )
    with pytest.raises(DBAPIError):
        with session_factory.begin() as session:
            session.execute(
                text(
                    "DELETE FROM knowledge_lifecycle_assessments WHERE id = :id"
                ),
                {"id": first_assessment_id},
            )


def test_b37_supersede_assessment_round_trips_successor_and_rechecks_approval_binding(
    session_factory,
    snapshot_store,
    distillation_fixture,
    request,
):
    """Exercise supersede assessment, immutable recording, and B3.6 recheck."""
    from core.knowledge_approval import (
        KnowledgeApprovalBindingError,
        build_approval_binding,
    )
    from core.knowledge_lifecycle import (
        PROPOSED_STATE_HASH_DOMAIN,
        RECORDED_EVENT_TYPE,
        _domain_hash,
        _normalize_json,
        _task_id,
        recorded_assessment_event_payload,
    )
    from core.knowledge_lifecycle_tasks import (
        KnowledgeLifecycleAssessmentTask,
        KnowledgeLifecycleAssessmentTaskRunner,
    )
    from core.learning_history import (
        KNOWLEDGE_CONTENT_HASH_SCHEME,
        knowledge_item_content_hash,
    )
    from core.models import (
        KnowledgeLifecycleAssessment,
        LearningChangeOperatorProvenance,
    )
    from core.operator_approval import canonical_operator_identity
    from core.state_assessment import _timestamp

    fixture = distillation_fixture(2, include_contrary=False)
    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    predecessor_approval_task_id, predecessor_attempt, principal = (
        _create_admitted_approval_task(
            session_factory,
            snapshot_store,
            fixture.team_id,
            create_proposal.learning_change_id,
        )
    )
    predecessor_result = LearningCommitService(
        session_factory, snapshot_store
    ).decide(predecessor_approval_task_id, predecessor_attempt, principal)
    assert predecessor_result.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=predecessor_approval_task_id,
            attempt=predecessor_attempt,
            result_category="success_learning_change_accepted",
            observed_at=predecessor_result.committed_at,
            learning_change_id=predecessor_result.learning_change_id,
        )
    )

    candidate_id = uuid4()
    candidate_origin_change_id = uuid4()
    candidate_approval_task_id = uuid4()
    candidate_started_at = datetime.now(timezone.utc) - timedelta(seconds=3)
    candidate_committed_at = candidate_started_at + timedelta(seconds=1)
    candidate_review_after = candidate_committed_at + timedelta(days=30)
    candidate_policy_id = uuid4()
    proposal_source_task_id = uuid4()
    supersede_change_id = uuid4()
    lifecycle_task_id = _task_id(fixture.team_id, supersede_change_id)
    proposal_started_at = datetime.now(timezone.utc)
    proposal_completed_at = proposal_started_at + timedelta(seconds=2)
    rationale = {
        "schema_version": 1,
        "summary": "A validated successor replaces the predecessor.",
        "reasons": [
            {
                "category": "improved_evidence",
                "statement": "The successor incorporates the updated evidence.",
            }
        ],
    }
    observation_ref, observation_hash = snapshot_store.put(
        (
            '{"attempt":1,"learning_change_id":"'
            + str(supersede_change_id)
            + '","result_category":"success_learning_change_proposed"}'
        ).encode("utf-8")
    )

    task_ids = [
        candidate_approval_task_id,
        proposal_source_task_id,
        lifecycle_task_id,
    ]

    def cleanup_b37_supersede_records():
        with session_factory.begin() as session:
            session.execute(
                text(
                    "ALTER TABLE knowledge_lifecycle_assessments "
                    "DISABLE TRIGGER USER"
                )
            )
            session.execute(
                delete(KnowledgeLifecycleAssessment).where(
                    KnowledgeLifecycleAssessment.task_id == lifecycle_task_id
                )
            )
            session.execute(
                text(
                    "ALTER TABLE knowledge_lifecycle_assessments "
                    "ENABLE TRIGGER USER"
                )
            )
            session.execute(
                text(
                    "ALTER TABLE learning_change_operator_provenance "
                    "DISABLE TRIGGER USER"
                )
            )
            session.execute(
                delete(LearningChangeOperatorProvenance).where(
                    LearningChangeOperatorProvenance.learning_change_id
                    == supersede_change_id
                )
            )
            session.execute(
                text(
                    "ALTER TABLE learning_change_operator_provenance "
                    "ENABLE TRIGGER USER"
                )
            )
            session.execute(delete(Event).where(Event.task_id.in_(task_ids)))
            session.execute(
                delete(Outcome).where(
                    Outcome.recorded_by_task_id.in_(task_ids)
                )
            )
            session.execute(
                delete(LearningChange).where(
                    LearningChange.id == supersede_change_id
                )
            )
            session.execute(
                delete(KnowledgeItem).where(KnowledgeItem.id == candidate_id)
            )
            session.execute(
                delete(LearningChange).where(
                    LearningChange.id == candidate_origin_change_id
                )
            )
            session.execute(delete(Task).where(Task.id.in_(task_ids)))
            session.execute(
                delete(TeamPolicy).where(TeamPolicy.id == candidate_policy_id)
            )

    request.addfinalizer(cleanup_b37_supersede_records)

    with session_factory.begin() as session:
        predecessor = session.get(
            KnowledgeItem, predecessor_result.knowledge_item_id
        )
        assert predecessor is not None
        session.add(
            TeamPolicy(
                id=candidate_policy_id,
                team_id=fixture.team_id,
                version=2,
                schema_version=2,
                rules={"review": {"knowledge_item_interval_days": 30}},
            )
        )
        session.flush()
        candidate_state = {
            "id": str(candidate_id),
            "team_id": str(fixture.team_id),
            "kind": "practice",
            "title": "Validated successor practice",
            "statement": "The successor statement is supported by newer evidence.",
            "body": "The successor body records the updated procedure.",
            "applicability": {"domain": "science"},
            "preconditions": ["The source remains available."],
            "assumptions": [],
            "limitations": [],
            "non_applicability": [],
            "failure_modes": [],
            "known_counterexamples": [],
            "missing_information": [],
            "uncertainty": [],
            "confidence": Decimal("0.850"),
            "status": "active",
            "version": 1,
            "last_validated_at": None,
            "review_after": candidate_review_after,
            "origin_learning_change_id": str(candidate_origin_change_id),
            "current_learning_change_id": str(candidate_origin_change_id),
            "supersedes_item_id": str(predecessor.id),
            "superseded_by_id": None,
        }
        candidate_snapshot = encode_state_snapshot(candidate_state)
        candidate_approval_task = Task(
            id=candidate_approval_task_id,
            team_id=fixture.team_id,
            task_type="approve_learning_change",
            status="running",
            attempt_count=1,
            policy_version=2,
            allowed_writes=["LearningChange", "KnowledgeItem"],
            budget={
                "max_tool_calls": 0,
                "max_cost_usd": 0.0,
                "deadline_seconds": 30,
            },
            created_at=candidate_started_at,
            max_attempts=3,
        )
        session.add(candidate_approval_task)
        session.flush()
        candidate_origin_change = LearningChange(
            id=candidate_origin_change_id,
            team_id=fixture.team_id,
            target_kind="knowledge_item",
            target_id=None,
            operation="create",
            proposed_state={},
            previous_state=None,
            committed_state=candidate_snapshot,
            evidence_basis=[],
            evidence_basis_hash="sha256:" + ("0" * 64),
            status="accepted",
            idempotency_key=f"b37-candidate-create-{candidate_id}",
            proposed_by_task_id=fixture.distillation_task_id,
            committed_by_task_id=candidate_approval_task_id,
            operator_id="https://host.example/identity#candidate-author",
            decision_reason=None,
            created_at=candidate_started_at,
            committed_at=candidate_committed_at,
        )
        session.add(candidate_origin_change)
        session.flush()
        session.add(
            KnowledgeItem(
                id=candidate_id,
                team_id=fixture.team_id,
                kind=candidate_state["kind"],
                title=candidate_state["title"],
                statement=candidate_state["statement"],
                body=candidate_state["body"],
                applicability=candidate_state["applicability"],
                preconditions=candidate_state["preconditions"],
                assumptions=candidate_state["assumptions"],
                limitations=candidate_state["limitations"],
                non_applicability=candidate_state["non_applicability"],
                failure_modes=candidate_state["failure_modes"],
                known_counterexamples=candidate_state["known_counterexamples"],
                missing_information=candidate_state["missing_information"],
                uncertainty=candidate_state["uncertainty"],
                confidence=candidate_state["confidence"],
                status="active",
                version=1,
                last_validated_at=None,
                review_after=candidate_review_after,
                origin_learning_change_id=candidate_origin_change_id,
                current_learning_change_id=candidate_origin_change_id,
                supersedes_item_id=predecessor.id,
                superseded_by_id=None,
                created_at=candidate_committed_at,
                updated_at=candidate_committed_at,
            )
        )
        session.add_all(
            [
                Event(
                    id=uuid4(),
                    task_id=candidate_approval_task_id,
                    type="task_started",
                    payload={
                        "from_status": "pending",
                        "to_status": "running",
                        "attempt_count": 1,
                    },
                    created_at=candidate_started_at,
                ),
                Event(
                    id=uuid4(),
                    task_id=candidate_approval_task_id,
                    type="learning_change_accepted",
                    payload={
                        "learning_change_id": str(candidate_origin_change_id),
                        "operation": "create",
                        "decision": "accept",
                        "operator_id": candidate_origin_change.operator_id,
                        "approval_task_id": str(candidate_approval_task_id),
                        "attempt_count": 1,
                        "committed_at": candidate_committed_at.isoformat(),
                    },
                    created_at=candidate_committed_at,
                ),
            ]
        )
        session.add(
            Task(
                id=proposal_source_task_id,
                team_id=fixture.team_id,
                task_type="propose_learning_change",
                status="done",
                attempt_count=1,
                policy_version=1,
                allowed_writes=["LearningChange"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.0,
                    "deadline_seconds": 30,
                },
                created_at=proposal_started_at,
                completed_at=proposal_completed_at,
                max_attempts=3,
            )
        )
        session.flush()
        team = session.get(Team, fixture.team_id)
        proposal_source_task = session.get(Task, proposal_source_task_id)
        assert team is not None and proposal_source_task is not None
        evidence_pack = ExperienceDistiller(
            session_factory, snapshot_store, provider=None
        )._build_pack(
            session,
            proposal_source_task,
            team,
            tuple(sorted(case.evaluation_id for case in fixture.cases)),
            allow_completed_task=True,
            include_version_marker=True,
        )
        from core.evaluations import _sha256_json

        predecessor_state = knowledge_item_state(predecessor)
        predecessor_snapshot = encode_state_snapshot(predecessor_state)
        predecessor_binding = {
            "target_knowledge_item_id": str(predecessor.id),
            "target_current_learning_change_id": str(
                predecessor.current_learning_change_id
            ),
            "target_content_version": predecessor.version,
            "target_content_hash": knowledge_item_content_hash(predecessor),
            "target_content_hash_scheme": KNOWLEDGE_CONTENT_HASH_SCHEME,
            "target_state_hash": predecessor_snapshot["snapshot_hash"],
        }
        candidate = session.get(KnowledgeItem, candidate_id)
        assert candidate is not None
        successor_binding = {
            "successor_knowledge_item_id": str(candidate.id),
            "successor_team_id": str(candidate.team_id),
            "successor_current_learning_change_id": str(
                candidate.current_learning_change_id
            ),
            "successor_content_version": candidate.version,
            "successor_content_hash": knowledge_item_content_hash(candidate),
            "successor_content_hash_scheme": KNOWLEDGE_CONTENT_HASH_SCHEME,
            "successor_status": candidate.status,
            "successor_review_after": _timestamp(candidate.review_after),
            "successor_state_hash": candidate_snapshot["snapshot_hash"],
        }
        unsigned_state = {
            "evidence_basis_hash": evidence_pack.basis_hash,
            "operator_rationale": rationale,
            **successor_binding,
        }
        proposal_hash = _sha256_json({
            "predecessor_binding": predecessor_binding,
            **unsigned_state,
        })
        proposed_state = {"proposal_hash": proposal_hash, **unsigned_state}
        idempotency_key = "r7b-supersede-v1:" + _sha256_json({
            "team_id": str(fixture.team_id),
            "task_id": str(proposal_source_task_id),
            "predecessor_binding": predecessor_binding,
            "successor_binding": successor_binding,
            "evidence_basis_hash": evidence_pack.basis_hash,
            "operator_rationale": rationale,
            "operator_id": canonical_operator_identity(
                "https://operator.example.test", "operator-b37-supersede"
            ),
        }).removeprefix("sha256:")
        proposed_state_hash = _domain_hash(
            PROPOSED_STATE_HASH_DOMAIN, _normalize_json(proposed_state)
        )
        supersede_change = LearningChange(
            id=supersede_change_id,
            team_id=fixture.team_id,
            target_kind="knowledge_item",
            target_id=predecessor.id,
            operation="supersede",
            proposed_state=proposed_state,
            previous_state=predecessor_snapshot,
            committed_state=None,
            evidence_basis=evidence_pack.evidence_basis,
            evidence_basis_hash=evidence_pack.basis_hash,
            status="proposed",
            idempotency_key=idempotency_key,
            proposed_by_task_id=proposal_source_task_id,
            committed_by_task_id=None,
            operator_id=None,
            decision_reason=None,
            created_at=proposal_started_at,
        )
        session.add(supersede_change)
        session.flush()
        session.add(
            LearningChangeOperatorProvenance(
                learning_change_id=supersede_change_id,
                team_id=fixture.team_id,
                issuer="https://operator.example.test",
                subject="operator-b37-supersede",
                recorded_at=proposal_started_at,
            )
        )
        source_outcome = Outcome(
            id=uuid4(),
            team_id=fixture.team_id,
            subject_kind="task",
            subject_id=proposal_source_task_id,
            outcome_type="task_execution",
            expected=None,
            observation_snapshot_ref=observation_ref,
            observation_hash=observation_hash,
            observed_at=proposal_completed_at,
            recorded_by_task_id=proposal_source_task_id,
        )
        session.add(source_outcome)
        session.flush()
        session.add_all(
            [
                Event(
                    id=uuid4(),
                    task_id=proposal_source_task_id,
                    type="task_started",
                    payload={
                        "from_status": "pending",
                        "to_status": "running",
                        "attempt_count": 1,
                    },
                    created_at=proposal_started_at,
                ),
                Event(
                    id=uuid4(),
                    task_id=proposal_source_task_id,
                    type="learning_change_proposed",
                    payload={
                        "learning_change_id": str(supersede_change_id),
                        "operation": "supersede",
                        "proposal_hash": proposal_hash,
                        "proposed_state_hash": proposed_state_hash,
                        "evidence_basis_hash": evidence_pack.basis_hash,
                        "target_binding": predecessor_binding,
                        "successor_binding": successor_binding,
                        "attempt_count": 1,
                    },
                    created_at=proposal_completed_at - timedelta(seconds=1),
                ),
                Event(
                    id=uuid4(),
                    task_id=proposal_source_task_id,
                    type="task_completed",
                    payload={
                        "from_status": "running",
                        "to_status": "done",
                        "attempt_count": 1,
                        "result_category": "success_learning_change_proposed",
                        "failure_reason": None,
                        "outcome_id": str(source_outcome.id),
                        "observation_snapshot_ref": observation_ref,
                        "observation_hash": observation_hash,
                        "learning_change_id": str(supersede_change_id),
                    },
                    created_at=proposal_completed_at,
                ),
            ]
        )

    lifecycle_adapter = KnowledgeLifecycleAssessmentTask(
        session_factory, snapshot_store
    )
    assert lifecycle_adapter.create(supersede_change_id) == lifecycle_task_id
    runner = KnowledgeLifecycleAssessmentTaskRunner(
        session_factory, snapshot_store
    )
    result = runner.run(lifecycle_task_id)
    assert result.status == "done"
    assert result.assessment_id is not None
    assert result.assessment_result == "eligible"
    assert result.outcome_id is not None

    with session_factory() as session:
        predecessor = session.get(
            KnowledgeItem, predecessor_result.knowledge_item_id
        )
        candidate = session.get(KnowledgeItem, candidate_id)
        change = session.get(LearningChange, supersede_change_id)
        task = session.get(Task, lifecycle_task_id)
        assessment = session.get(
            KnowledgeLifecycleAssessment, result.assessment_id
        )
        assert predecessor is not None and candidate is not None
        assert change is not None and task is not None and assessment is not None
        assert task.status == "done"
        assert task.allowed_writes == ["KnowledgeLifecycleAssessment"]
        assert change.status == "proposed"
        assert change.committed_by_task_id is None
        assert predecessor.status == "active"
        assert predecessor.superseded_by_id is None
        assert candidate.status == "active"
        assert candidate.supersedes_item_id == predecessor.id
        assert assessment.operation == "supersede"
        assert assessment.assessment_result == "eligible"
        assert assessment.successor_knowledge_item_id == candidate.id
        assert assessment.successor_current_learning_change_id == (
            candidate_origin_change_id
        )
        assert assessment.successor_content_version == candidate.version
        assert assessment.successor_content_hash == knowledge_item_content_hash(
            candidate
        )
        assert assessment.successor_status == "active"
        assert assessment.successor_review_after == candidate_review_after
        assert assessment.successor_state_hash == candidate_snapshot["snapshot_hash"]
        recorded_event = session.get(Event, assessment.recorded_event_id)
        assert recorded_event is not None
        assert recorded_event.task_id == lifecycle_task_id
        assert recorded_event.type == RECORDED_EVENT_TYPE
        assert recorded_event.created_at == assessment.recorded_at
        assert recorded_event.payload == recorded_assessment_event_payload(
            assessment
        )
        assert session.scalar(
            select(func.count(KnowledgeLifecycleAssessment.id)).where(
                KnowledgeLifecycleAssessment.learning_change_id
                == supersede_change_id
            )
        ) == 1
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == lifecycle_task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) == 1
        principal_id = canonical_operator_identity(
            "https://host.example/identity", "b37-reviewer"
        )
        binding = build_approval_binding(
            session,
            change,
            operator_id=principal_id,
            approval_policy_version=1,
            require_assessment=True,
            snapshot_store=snapshot_store,
            session_factory=session_factory,
        )
        assert binding["assessment_type"] == "knowledge_lifecycle"
        assert binding["assessment_id"] == str(assessment.id)
        assert binding["assessment_payload_hash"] == assessment.payload_hash
        assert binding["operator_provenance"] == {
            "issuer": "https://operator.example.test",
            "subject": "operator-b37-supersede",
        }
        assert binding["successor_binding"] == {
            "successor_knowledge_item_id": str(candidate.id),
            "successor_team_id": str(candidate.team_id),
            "successor_current_learning_change_id": str(
                candidate.current_learning_change_id
            ),
            "successor_content_version": candidate.version,
            "successor_content_hash": knowledge_item_content_hash(candidate),
            "successor_content_hash_scheme": KNOWLEDGE_CONTENT_HASH_SCHEME,
            "successor_status": "active",
            "successor_review_after": _timestamp(candidate.review_after),
            "successor_state_hash": candidate_snapshot["snapshot_hash"],
        }
        original_recorded_event_payload = dict(recorded_event.payload)
        original_successor_state = {
            "current_learning_change_id": candidate.current_learning_change_id,
            "version": candidate.version,
            "statement": candidate.statement,
            "status": candidate.status,
            "review_after": candidate.review_after,
            "last_validated_at": candidate.last_validated_at,
            "supersedes_item_id": candidate.supersedes_item_id,
        }
        original_supersede_proposed_state = dict(change.proposed_state)

    with session_factory.begin() as session:
        tampered_event = session.get(Event, assessment.recorded_event_id)
        assert tampered_event is not None
        tampered_event.payload = {
            **tampered_event.payload,
            "assessment_payload_hash": "sha256:" + ("0" * 64),
        }

    with session_factory() as session:
        change = session.get(LearningChange, supersede_change_id)
        assert change is not None
        with pytest.raises(
            KnowledgeApprovalBindingError,
            match="knowledge_lifecycle_recorded_event_invalid",
        ):
            build_approval_binding(
                session,
                change,
                operator_id=principal_id,
                approval_policy_version=1,
                require_assessment=True,
                snapshot_store=snapshot_store,
                session_factory=session_factory,
            )

    with session_factory.begin() as session:
        tampered_event = session.get(Event, assessment.recorded_event_id)
        assert tampered_event is not None
        tampered_event.payload = original_recorded_event_payload

    successor_drift_cases = [
        "successor_pointer",
        "successor_content_version",
        "successor_content_hash",
        "successor_status",
        "successor_review_after",
        "successor_full_state_hash",
        "successor_predecessor_relationship",
        "successor_hash_scheme",
        "proposed_state_hash",
    ]
    for drift_case in successor_drift_cases:
        with session_factory.begin() as session:
            candidate = session.get(KnowledgeItem, candidate_id)
            change = session.get(LearningChange, supersede_change_id)
            assert candidate is not None and change is not None
            if drift_case == "successor_pointer":
                candidate.current_learning_change_id = supersede_change_id
            elif drift_case == "successor_content_version":
                candidate.version = original_successor_state["version"] + 1
            elif drift_case == "successor_content_hash":
                candidate.statement = (
                    f"{original_successor_state['statement']} drift"
                )
            elif drift_case == "successor_status":
                candidate.status = "needs_review"
            elif drift_case == "successor_review_after":
                candidate.review_after = (
                    original_successor_state["review_after"]
                    + timedelta(days=1)
                )
            elif drift_case == "successor_full_state_hash":
                candidate.last_validated_at = datetime(
                    2027, 1, 1, tzinfo=timezone.utc
                )
            elif drift_case == "successor_predecessor_relationship":
                candidate.supersedes_item_id = None
            elif drift_case == "successor_hash_scheme":
                change.proposed_state = {
                    **original_supersede_proposed_state,
                    "successor_content_hash_scheme": (
                        "watch.r7b.knowledge-content.v999"
                    ),
                }
            elif drift_case == "proposed_state_hash":
                change.proposed_state = {
                    **original_supersede_proposed_state,
                    "operator_supplied_extension": "changed after assessment",
                }
            else:
                raise AssertionError(f"unknown successor drift case: {drift_case}")

        with session_factory() as session:
            change = session.get(LearningChange, supersede_change_id)
            assert change is not None
            with pytest.raises(KnowledgeApprovalBindingError):
                build_approval_binding(
                    session,
                    change,
                    operator_id=principal_id,
                    approval_policy_version=1,
                    require_assessment=True,
                    snapshot_store=snapshot_store,
                    session_factory=session_factory,
                )

        with session_factory.begin() as session:
            candidate = session.get(KnowledgeItem, candidate_id)
            change = session.get(LearningChange, supersede_change_id)
            assert candidate is not None and change is not None
            candidate.current_learning_change_id = original_successor_state[
                "current_learning_change_id"
            ]
            candidate.version = original_successor_state["version"]
            candidate.statement = original_successor_state["statement"]
            candidate.status = original_successor_state["status"]
            candidate.review_after = original_successor_state["review_after"]
            candidate.last_validated_at = original_successor_state[
                "last_validated_at"
            ]
            candidate.supersedes_item_id = original_successor_state[
                "supersedes_item_id"
            ]
            change.proposed_state = dict(original_supersede_proposed_state)


    with session_factory() as session:
        predecessor = session.get(
            KnowledgeItem, predecessor_result.knowledge_item_id
        )
        candidate = session.get(KnowledgeItem, candidate_id)
        change = session.get(LearningChange, supersede_change_id)
        assert predecessor is not None and candidate is not None and change is not None
        assert predecessor.status == "active"
        assert predecessor.superseded_by_id is None
        assert candidate.status == "active"
        assert change.status == "proposed"
        assert change.committed_by_task_id is None

def test_accepted_revise_preserves_needs_review_and_retrieval_ineligibility(
    session_factory,
    snapshot_store,
    distillation_fixture,
    monkeypatch,
):
    fixture = distillation_fixture(
        2, include_contrary=False, review_interval_days=1
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    create_proposal = _distiller(
        session_factory, snapshot_store, _provider()
    ).propose(
        fixture.distillation_task_id,
        [case.evaluation_id for case in fixture.cases],
    )
    runtime.finalize(
        TerminalObservation(
            task_id=fixture.distillation_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=create_proposal.learning_change_id,
        )
    )
    create_task_id, create_attempt, principal = _create_admitted_approval_task(
        session_factory,
        snapshot_store,
        fixture.team_id,
        create_proposal.learning_change_id,
    )
    created = LearningCommitService(session_factory, snapshot_store).decide(
        create_task_id, create_attempt, principal
    )
    assert created.knowledge_item_id is not None
    runtime.finalize(
        TerminalObservation(
            task_id=create_task_id,
            attempt=create_attempt,
            result_category="success_learning_change_accepted",
            observed_at=created.committed_at,
            learning_change_id=created.learning_change_id,
        )
    )

    class FakeEmbeddingProvider:
        space = EmbeddingSpace(
            provider="watch_test",
            model="g6-deterministic",
            revision="1",
            dimensions=3,
            configuration="g6-regression",
        )

        def current_space(self):
            return self.space

        def embed(self, texts):
            return EmbeddingBatch(
                space=self.space,
                vectors=tuple((0.1, 0.2, 0.3) for _ in texts),
            )

    embedding_provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(session_factory, embedding_provider)
    retriever = HybridKnowledgeRetriever(
        session_factory, snapshot_store, embedding_provider
    )
    assert indexer.index_knowledge_item(created.knowledge_item_id).outcome == "indexed"
    assert retriever.retrieve(fixture.team_id, "source evidence")

    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        template = session.get(Task, fixture.distillation_task_id)
        assert item is not None and template is not None
        assert item.status == "active"
        review_after = item.review_after
        assert review_after is not None
        pinned_policy_version = template.policy_version

    # Record the ordinary D7 review transition; do not create a revalidation
    # proposal or introduce another lifecycle operation into this proof.
    review_task_id = uuid4()
    fixture.extra_task_ids.append(review_task_id)
    review_started_at = review_after - timedelta(seconds=1)
    with session_factory.begin() as session:
        session.add(
            Task(
                id=review_task_id,
                team_id=fixture.team_id,
                task_type="review_knowledge",
                status="running",
                attempt_count=1,
                policy_version=pinned_policy_version,
                objective_id=None,
                plan_id=None,
                plan_action_id=None,
                allowed_writes=["KnowledgeItem"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.0,
                    "deadline_seconds": 30,
                },
                created_at=review_started_at,
                completed_at=None,
                max_attempts=3,
            )
        )
        session.flush()
        session.add(
            Event(
                id=uuid4(),
                task_id=review_task_id,
                type="task_started",
                payload={
                    "from_status": "pending",
                    "to_status": "running",
                    "attempt_count": 1,
                },
                created_at=review_started_at,
            )
        )
    runtime.finalize(
        TerminalObservation(
            task_id=review_task_id,
            attempt=1,
            result_category="success_knowledge_reviewed",
            observed_at=review_after,
        )
    )

    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        review_event = session.scalar(
            select(Event).where(
                Event.task_id == review_task_id,
                Event.type == "knowledge_items_reviewed",
            )
        )
        assert item is not None and item.status == "needs_review"
        assert review_event is not None
        before_state = knowledge_item_state(item)
        before_pointer = item.current_learning_change_id
        before_version = item.version
        before_hash = knowledge_item_content_hash(item)
        assert before_pointer == created.learning_change_id
        assert item.last_validated_at is None
        reviewed_at = review_after

        projection_state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item.id
            )
        )
        projection_chunk = session.scalar(
            select(TeamExperienceChunk).where(
                TeamExperienceChunk.knowledge_item_id == item.id
            )
        )
        assert projection_state is not None and projection_chunk is not None
        assert projection_state.status == "published"
        assert projection_state.current_learning_change_id == before_pointer
        assert projection_chunk.current_learning_change_id == before_pointer

    # The retained pre-review projection is already hidden by canonical D7 state.
    assert retriever.retrieve(fixture.team_id, "source evidence") == ()

    revision_id = _create_revision_proposal(
        session_factory,
        snapshot_store,
        fixture,
        created.knowledge_item_id,
        body=(
            "The revised practice preserves source evidence and records a "
            "distinct observation before drawing a conclusion."
        ),
    )
    _run_quality_assessment(session_factory, snapshot_store, revision_id)

    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    revision_request = LearningChangeDecisionRequest(
        learning_change_id=revision_id,
        decision="accept",
        idempotency_key=uuid4(),
    )

    import core.learning_commit as learning_commit

    revision_committed_at = reviewed_at + timedelta(seconds=3)

    class RevisionCommitDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return (
                revision_committed_at
                if tz is not None
                else revision_committed_at.replace(tzinfo=None)
            )

    with monkeypatch.context() as patch:
        patch.setattr(
            learning_commit,
            "datetime",
            SimpleNamespace(
                datetime=RevisionCommitDateTime,
                timezone=timezone,
                timedelta=timedelta,
            ),
        )
        revised = adapter.decide_learning_change(principal, revision_request)

    assert revised.learning_change_status == "accepted"
    assert revised.task_status == "done"
    assert revised.knowledge_item_id == created.knowledge_item_id
    assert not revised.replayed
    assert revised.outcome_id is not None

    with session_factory() as session:
        item = session.get(KnowledgeItem, created.knowledge_item_id)
        revision = session.get(LearningChange, revision_id)
        approval_task = session.get(Task, revised.task_id)
        decision_event = session.scalar(
            select(Event).where(
                Event.task_id == revised.task_id,
                Event.type == "learning_change_accepted",
            )
        )
        assert item is not None and revision is not None
        assert approval_task is not None and approval_task.status == "done"
        assert decision_event is not None
        revised_state = knowledge_item_state(item)
        revised_hash = knowledge_item_content_hash(item)

        assert item.status == "needs_review"
        assert item.current_learning_change_id == revision_id
        assert item.current_learning_change_id != before_pointer
        assert item.version == before_version + 1
        assert item.body == (
            "The revised practice preserves source evidence and records a "
            "distinct observation before drawing a conclusion."
        )
        assert revised_hash != before_hash
        assert item.last_validated_at is None
        assert approval_task.policy_version == pinned_policy_version
        assert revision.committed_at == revision_committed_at
        assert item.review_after == revision_committed_at + timedelta(days=1)
        assert revision.committed_by_task_id == revised.task_id
        assert decision_event.payload["operation"] == "revise"
        assert decision_event.payload["operator_id"] == revised.operator_id
        assert decision_event.payload["knowledge_item_id"] == str(item.id)
        assert revision.previous_state is not None
        assert revision.previous_state["state"] == before_state
        assert revision.committed_state is not None
        assert revision.committed_state["state"] == revised_state

        history = reconstruct_knowledge_item_history(session, item)
        assert history.learning_change_ids == (
            created.learning_change_id,
            revision_id,
        )
        assert history.applied_review_event_ids == (review_event.id,)
        assert history.state == revised_state
        assert history.state["status"] == "needs_review"

        # The old projection remains physically present but is no longer current.
        projection_state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == item.id
            )
        )
        projection_chunk = session.scalar(
            select(TeamExperienceChunk).where(
                TeamExperienceChunk.knowledge_item_id == item.id
            )
        )
        assert projection_state is not None and projection_chunk is not None
        assert projection_state.status == "published"
        assert projection_state.current_learning_change_id == before_pointer
        assert projection_chunk.current_learning_change_id == before_pointer
        assert (
            projection_state.current_learning_change_id
            != item.current_learning_change_id
        )
        assert projection_chunk.item_content_hash == before_hash

    # Retrieval must recheck canonical status and pointer, not trust the old row.
    assert retriever.retrieve(fixture.team_id, "revised practice") == ()

    # The ordinary indexer must not republish a needs_review item.
    indexed = indexer.index_knowledge_item(created.knowledge_item_id)
    assert indexed.outcome == "ineligible"
    assert retriever.retrieve(fixture.team_id, "revised practice") == ()
    with session_factory() as session:
        projection_state = session.scalar(
            select(TeamExperienceIndexState).where(
                TeamExperienceIndexState.knowledge_item_id == created.knowledge_item_id
            )
        )
        projection_chunks = list(
            session.scalars(
                select(TeamExperienceChunk).where(
                    TeamExperienceChunk.knowledge_item_id == created.knowledge_item_id
                )
            )
        )
        assert projection_state is not None
        assert projection_state.status == "ineligible"
        assert projection_chunks == []



def test_b5_2_integrated_retirement_candidate_lifecycle_sequences(
    session_factory,
    snapshot_store,
    distillation_fixture,
    request,
    monkeypatch,
):
    from core.knowledge_lifecycle_tasks import (
        KnowledgeLifecycleAssessmentTask,
        KnowledgeLifecycleAssessmentTaskRunner,
    )
    from core.models import (
        KnowledgeLifecycleAssessment,
        LearningChangeOperatorProvenance,
    )

    fixture = distillation_fixture(1, False, review_interval_days=1)
    evaluation_ids = tuple(case.evaluation_id for case in fixture.cases)
    runtime = TaskRuntime(session_factory, snapshot_store)
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    lifecycle_task_ids: list[UUID] = []
    retirement_change_ids: list[UUID] = []

    def cleanup_lifecycle_records():
        with session_factory.begin() as session:
            session.execute(
                text(
                    "ALTER TABLE knowledge_lifecycle_assessments "
                    "DISABLE TRIGGER USER"
                )
            )
            if retirement_change_ids:
                session.execute(
                    delete(KnowledgeLifecycleAssessment).where(
                        KnowledgeLifecycleAssessment.learning_change_id.in_(
                            retirement_change_ids
                        )
                    )
                )
            session.execute(
                text(
                    "ALTER TABLE knowledge_lifecycle_assessments "
                    "ENABLE TRIGGER USER"
                )
            )
            session.execute(
                text(
                    "ALTER TABLE learning_change_operator_provenance "
                    "DISABLE TRIGGER USER"
                )
            )
            if retirement_change_ids:
                session.execute(
                    delete(LearningChangeOperatorProvenance).where(
                        LearningChangeOperatorProvenance.learning_change_id.in_(
                            retirement_change_ids
                        )
                    )
                )
            session.execute(
                text(
                    "ALTER TABLE learning_change_operator_provenance "
                    "ENABLE TRIGGER USER"
                )
            )
            if lifecycle_task_ids:
                session.execute(
                    delete(Outcome).where(
                        Outcome.recorded_by_task_id.in_(lifecycle_task_ids)
                    )
                )
                session.execute(
                    delete(Event).where(Event.task_id.in_(lifecycle_task_ids))
                )
                session.execute(
                    delete(Task).where(Task.id.in_(lifecycle_task_ids))
                )

    request.addfinalizer(cleanup_lifecycle_records)

    def create_item(supersedes_item_id: UUID | None = None) -> UUID:
        task_id = _create_proposal_task(session_factory, fixture)
        proposal = _distiller(
            session_factory, snapshot_store, _provider()
        ).propose(
            task_id,
            evaluation_ids,
            supersedes_item_id=supersedes_item_id,
        )
        runtime.finalize(
            TerminalObservation(
                task_id=task_id,
                attempt=1,
                result_category="success_learning_change_proposed",
                observed_at=datetime.now(timezone.utc),
                learning_change_id=proposal.learning_change_id,
            )
        )
        committed = _accept_learning_change(
            session_factory,
            snapshot_store,
            fixture.team_id,
            proposal.learning_change_id,
        )
        assert committed.knowledge_item_id is not None
        return committed.knowledge_item_id

    def mark_needs_review(item_id: UUID) -> None:
        with session_factory() as session:
            item = session.get(KnowledgeItem, item_id)
            assert item is not None and item.status == "active"
            review_after = item.review_after
            assert review_after is not None
        review_task_id = uuid4()
        fixture.extra_task_ids.append(review_task_id)
        review_started_at = review_after - timedelta(seconds=1)
        with session_factory.begin() as session:
            session.add(
                Task(
                    id=review_task_id,
                    team_id=fixture.team_id,
                    task_type="review_knowledge",
                    status="running",
                    attempt_count=1,
                    policy_version=1,
                    allowed_writes=["KnowledgeItem"],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.0,
                        "deadline_seconds": 30,
                    },
                    created_at=review_started_at,
                )
            )
            session.flush()
            session.add(
                Event(
                    id=uuid4(),
                    task_id=review_task_id,
                    type="task_started",
                    payload={
                        "from_status": "pending",
                        "to_status": "running",
                        "attempt_count": 1,
                    },
                    created_at=review_started_at,
                )
            )
        runtime.finalize(
            TerminalObservation(
                task_id=review_task_id,
                attempt=1,
                result_category="success_knowledge_reviewed",
                observed_at=review_after,
            )
        )

    rationale = {
        "schema_version": 1,
        "summary": "The supporting evidence no longer justifies continued use.",
        "reasons": [
            {
                "category": "evidence_no_longer_reliable",
                "statement": "The primary supporting source has been superseded.",
            },
            {
                "category": "applicability_changed",
                "statement": "The original applicability conditions no longer hold.",
            },
        ],
    }

    def retire(target_id: UUID):
        with session_factory() as session:
            target = session.get(KnowledgeItem, target_id)
            assert target is not None
            target_status = target.status
            target_review_after = target.review_after

        principal = _approval_principal(
            fixture.team_id, subject=f"operator-retire-{target_id}"
        )
        proposal_task_id = _create_proposal_task(session_factory, fixture)
        proposal = adapter.propose_retirement(
            principal,
            task_id=proposal_task_id,
            evaluation_ids=evaluation_ids,
            target_knowledge_item_id=target_id,
            operator_rationale=rationale,
        )
        retirement_change_ids.append(proposal.learning_change_id)
        runtime.finalize(
            TerminalObservation(
                task_id=proposal_task_id,
                attempt=1,
                result_category="success_learning_change_proposed",
                observed_at=datetime.now(timezone.utc),
                learning_change_id=proposal.learning_change_id,
            )
        )

        lifecycle_adapter = KnowledgeLifecycleAssessmentTask(
            session_factory, snapshot_store
        )
        lifecycle_task_id = lifecycle_adapter.create(proposal.learning_change_id)
        lifecycle_task_ids.append(lifecycle_task_id)
        assessment = KnowledgeLifecycleAssessmentTaskRunner(
            session_factory, snapshot_store
        ).run(lifecycle_task_id)
        assert assessment.status == "done"
        assert assessment.assessment_id is not None
        assert assessment.assessment_result == "eligible"

        approval_request = adapter.request_learning_change_decision(
            principal,
            LearningChangeDecisionRequest(
                learning_change_id=proposal.learning_change_id,
                decision="accept",
                idempotency_key=uuid4(),
            ),
        )
        admission = runtime.admit(approval_request.task_id)
        commit_service = LearningCommitService(
            session_factory, snapshot_store
        )
        if target_status == "needs_review":
            assert target_review_after is not None
            retirement_commit_at = target_review_after + timedelta(seconds=1)

            import core.learning_commit as learning_commit

            class RetirementCommitDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    if tz is not None:
                        return retirement_commit_at
                    return retirement_commit_at.replace(tzinfo=None)

            # The review helper records its event at the due date. Keep the
            # canonical retirement commit later than that event instead of
            # moving the production clock backwards to wall-clock "now".
            with monkeypatch.context() as patch:
                patch.setattr(
                    learning_commit,
                    "datetime",
                    SimpleNamespace(
                        datetime=RetirementCommitDateTime,
                        timezone=timezone,
                        timedelta=timedelta,
                    ),
                )
                committed = commit_service.decide(
                    approval_request.task_id,
                    admission.attempt_count,
                    principal,
                )
        else:
            committed = commit_service.decide(
                approval_request.task_id,
                admission.attempt_count,
                principal,
            )
        runtime.finalize(
            TerminalObservation(
                task_id=approval_request.task_id,
                attempt=admission.attempt_count,
                result_category="success_learning_change_accepted",
                observed_at=committed.committed_at,
                learning_change_id=committed.learning_change_id,
            )
        )
        return (
            committed,
            approval_request.task_id,
            admission.attempt_count,
            principal,
        )

    def assert_retired_without_semantic_mutation(
        item_id: UUID,
        before_state: dict[str, Any],
        before_hash: str,
    ) -> None:
        with session_factory() as session:
            item = session.get(KnowledgeItem, item_id)
            assert item is not None
            after_state = knowledge_item_state(item)
            assert item.status == "retired"
            assert item.version == before_state["version"]
            assert knowledge_item_content_hash(item) == before_hash
            immutable_keys = set(before_state) - {
                "status",
                "current_learning_change_id",
            }
            assert {
                key: after_state[key] for key in immutable_keys
            } == {key: before_state[key] for key in immutable_keys}
            history = reconstruct_knowledge_item_history(session, item)
            assert history.states[-1]["status"] == "retired"
            assert history.states[-1]["current_learning_change_id"] == str(
                item.current_learning_change_id
            )

    # Sequence 1: ordinary create -> retire.
    ordinary_item_id = create_item()
    with session_factory() as session:
        ordinary_item = session.get(KnowledgeItem, ordinary_item_id)
        assert ordinary_item is not None
        ordinary_before = knowledge_item_state(ordinary_item)
        ordinary_hash = knowledge_item_content_hash(ordinary_item)

    (
        ordinary_retirement,
        ordinary_approval_task,
        ordinary_attempt,
        ordinary_principal,
    ) = (
        retire(ordinary_item_id)
    )
    assert ordinary_retirement.decision == "accept"
    assert ordinary_retirement.knowledge_item_id == ordinary_item_id
    assert_retired_without_semantic_mutation(
        ordinary_item_id, ordinary_before, ordinary_hash
    )

    with session_factory() as session:
        event_count_before_replay = session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == ordinary_approval_task
            )
        )
        outcome_count_before_replay = session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == ordinary_approval_task
            )
        )
    replay = LearningCommitService(session_factory, snapshot_store).decide(
        ordinary_approval_task, ordinary_attempt, ordinary_principal
    )
    assert replay.replayed
    assert replay.learning_change_id == ordinary_retirement.learning_change_id
    with session_factory() as session:
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == ordinary_approval_task
            )
        ) == event_count_before_replay
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == ordinary_approval_task
            )
        ) == outcome_count_before_replay

    retired_retry_task_id = _create_proposal_task(session_factory, fixture)
    with pytest.raises(
        ExperienceDistillerError,
        match="revision_target_status_invalid",
    ):
        adapter.propose_retirement(
            _approval_principal(fixture.team_id),
            task_id=retired_retry_task_id,
            evaluation_ids=evaluation_ids,
            target_knowledge_item_id=ordinary_item_id,
            operator_rationale=rationale,
        )
    with session_factory() as session:
        assert session.scalar(
            select(func.count(LearningChange.id)).where(
                LearningChange.proposed_by_task_id == retired_retry_task_id
            )
        ) == 0

    needs_review_item_id = create_item()
    mark_needs_review(needs_review_item_id)
    with session_factory() as session:
        needs_review_item = session.get(KnowledgeItem, needs_review_item_id)
        assert needs_review_item is not None
        assert needs_review_item.status == "needs_review"
        needs_review_before = knowledge_item_state(needs_review_item)
        needs_review_hash = knowledge_item_content_hash(needs_review_item)
    needs_review_retirement, _, _, _ = retire(needs_review_item_id)
    assert needs_review_retirement.knowledge_item_id == needs_review_item_id
    assert_retired_without_semantic_mutation(
        needs_review_item_id, needs_review_before, needs_review_hash
    )

    # Sequence 2: create candidate -> retire candidate -> replace candidate.
    predecessor_id = create_item()
    candidate_id = create_item(predecessor_id)
    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        candidate = session.get(KnowledgeItem, candidate_id)
        assert predecessor is not None and candidate is not None
        assert predecessor.status == "active"
        assert candidate.status == "active"
        assert candidate.supersedes_item_id == predecessor_id
        assert candidate.superseded_by_id is None
        assert not _supersession_publication_is_visible(session, candidate, {})

    blocked_task_id = _create_proposal_task(session_factory, fixture)
    with pytest.raises(
        ExperienceDistillerError,
        match="successor_candidate_already_pending",
    ):
        _distiller(
            session_factory, snapshot_store, _provider()
        ).propose(
            blocked_task_id,
            evaluation_ids,
            supersedes_item_id=predecessor_id,
        )

    with session_factory() as session:
        candidate = session.get(KnowledgeItem, candidate_id)
        assert candidate is not None
        candidate_before = knowledge_item_state(candidate)
        candidate_hash = knowledge_item_content_hash(candidate)

    (
        candidate_retirement,
        candidate_retirement_task,
        candidate_retirement_attempt,
        candidate_retirement_principal,
    ) = retire(candidate_id)
    assert candidate_retirement.knowledge_item_id == candidate_id
    assert_retired_without_semantic_mutation(
        candidate_id, candidate_before, candidate_hash
    )
    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        candidate = session.get(KnowledgeItem, candidate_id)
        assert predecessor is not None and candidate is not None
        assert predecessor.status == "active"
        assert predecessor.superseded_by_id is None
        assert candidate.status == "retired"
        assert candidate.supersedes_item_id == predecessor_id
        assert candidate.superseded_by_id is None

    replacement_id = create_item(predecessor_id)
    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        replacement = session.get(KnowledgeItem, replacement_id)
        assert predecessor is not None and replacement is not None
        assert predecessor.status == "active"
        assert predecessor.superseded_by_id is None
        assert replacement.status == "active"
        assert replacement.supersedes_item_id == predecessor_id
        assert replacement.superseded_by_id is None
        assert not _supersession_publication_is_visible(session, replacement, {})

    # Sequence 3: retiring a predecessor never implicitly mutates its candidate.
    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        replacement = session.get(KnowledgeItem, replacement_id)
        assert predecessor is not None and replacement is not None
        predecessor_before = knowledge_item_state(predecessor)
        predecessor_hash = knowledge_item_content_hash(predecessor)
        replacement_before = knowledge_item_state(replacement)

    predecessor_retirement, _, _, _ = retire(predecessor_id)
    assert predecessor_retirement.knowledge_item_id == predecessor_id
    assert_retired_without_semantic_mutation(
        predecessor_id, predecessor_before, predecessor_hash
    )
    with session_factory() as session:
        replacement = session.get(KnowledgeItem, replacement_id)
        assert replacement is not None
        assert knowledge_item_state(replacement) == replacement_before
        assert replacement.status == "active"
        assert replacement.supersedes_item_id == predecessor_id
        assert replacement.superseded_by_id is None
        assert not _supersession_publication_is_visible(session, replacement, {})

    with session_factory() as session:
        replacement = session.get(KnowledgeItem, replacement_id)
        assert replacement is not None
        replacement_before_retirement = knowledge_item_state(replacement)
        replacement_hash = knowledge_item_content_hash(replacement)
    replacement_retirement, _, _, _ = retire(replacement_id)
    assert replacement_retirement.knowledge_item_id == replacement_id
    assert_retired_without_semantic_mutation(
        replacement_id, replacement_before_retirement, replacement_hash
    )
    with session_factory() as session:
        replacement = session.get(KnowledgeItem, replacement_id)
        predecessor = session.get(KnowledgeItem, predecessor_id)
        assert replacement is not None and predecessor is not None
        assert replacement.status == "retired"
        assert replacement.supersedes_item_id == predecessor_id
        assert predecessor.status == "retired"
        assert predecessor.superseded_by_id is None

        before_replay = (
            session.scalar(
                select(func.count(LearningChange.id)).where(
                    LearningChange.team_id == fixture.team_id
                )
            ),
            session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == candidate_retirement_task
                )
            ),
            session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == candidate_retirement_task
                )
            ),
            tuple(
                (item.id, item.status, item.current_learning_change_id)
                for item in session.scalars(
                    select(KnowledgeItem)
                    .where(KnowledgeItem.team_id == fixture.team_id)
                    .order_by(KnowledgeItem.id)
                )
            ),
        )

    later_replay = LearningCommitService(session_factory, snapshot_store).decide(
        candidate_retirement_task,
        candidate_retirement_attempt,
        candidate_retirement_principal,
    )
    assert later_replay.replayed
    assert later_replay.learning_change_id == candidate_retirement.learning_change_id
    with session_factory() as session:
        after_replay = (
            session.scalar(
                select(func.count(LearningChange.id)).where(
                    LearningChange.team_id == fixture.team_id
                )
            ),
            session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == candidate_retirement_task
                )
            ),
            session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == candidate_retirement_task
                )
            ),
            tuple(
                (item.id, item.status, item.current_learning_change_id)
                for item in session.scalars(
                    select(KnowledgeItem)
                    .where(KnowledgeItem.team_id == fixture.team_id)
                    .order_by(KnowledgeItem.id)
                )
            ),
        )
        assert after_replay == before_replay


def test_concurrent_retirements_of_one_item_commit_one_transition(
    database_engine,
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    target_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    retirements = [
        _prepare_retirement_approval(
            session_factory, snapshot_store, fixture, target_id
        )
        for _ in range(2)
    ]
    with session_factory() as session:
        initial = session.get(KnowledgeItem, target_id)
        assert initial is not None
        initial_pointer = initial.current_learning_change_id
        initial_version = initial.version
        initial_content_hash = knowledge_item_content_hash(initial)

    barrier = Barrier(2)
    backend_pids: set[int] = set()
    backend_pids_lock = Lock()

    def capture_backend_pid(connection):
        pid = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
        with backend_pids_lock:
            backend_pids.add(pid)

    event.listen(database_engine, "begin", capture_backend_pid)

    def decide(retirement):
        learning_change_id, task_id, attempt, principal, _ = retirement
        barrier.wait(timeout=30)
        try:
            result = LearningCommitService(
                session_factory, snapshot_store
            ).decide(task_id, attempt, principal)
            return learning_change_id, task_id, result
        except LearningCommitError as error:
            return learning_change_id, task_id, error

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(decide, retirements))
    finally:
        event.remove(database_engine, "begin", capture_backend_pid)

    assert len(backend_pids) == 2
    winners = [result for result in results if not isinstance(result[2], Exception)]
    losers = [result for result in results if isinstance(result[2], Exception)]
    assert len(winners) == len(losers) == 1
    assert str(losers[0][2]) == "knowledge_lifecycle_predecessor_stale"
    winner = winners[0]
    winner_task_id = winner[1]
    winner_result = winner[2]
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=winner_task_id,
            attempt=winner_result.attempt_count,
            result_category="success_learning_change_accepted",
            observed_at=winner_result.committed_at,
            learning_change_id=winner_result.learning_change_id,
        )
    )

    with session_factory() as session:
        item = session.get(KnowledgeItem, target_id)
        accepted = list(
            session.scalars(
                select(Event).where(
                    Event.type == "learning_change_accepted",
                    Event.payload["operation"].as_string() == "retire",
                    Event.payload["knowledge_item_id"].as_string()
                    == str(target_id),
                )
            )
        )
        assert item is not None
        assert item.status == "retired"
        assert item.current_learning_change_id == winner_result.learning_change_id
        assert item.current_learning_change_id != initial_pointer
        assert item.version == initial_version
        assert knowledge_item_content_hash(item) == initial_content_hash
        history = reconstruct_knowledge_item_history(session, item)
        assert history.learning_change_ids == (
            initial_pointer,
            winner_result.learning_change_id,
        )
        assert len(accepted) == 1
        assert accepted[0].task_id == winner_task_id
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == winner_task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == winner_task_id,
                Event.type == "task_completed",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == losers[0][1],
                Event.type == "learning_change_accepted",
            )
        ) == 0
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == losers[0][1]
            )
        ) == 0
        losing_change = session.get(LearningChange, losers[0][0])
        assert losing_change is not None
        assert losing_change.status == "proposed"
        assert losing_change.committed_by_task_id is None


@pytest.mark.parametrize("ordering", ["retirement_first", "candidate_proposal_first"])
def test_predecessor_retirement_and_candidate_proposal_are_serialized(
    database_engine,
    session_factory,
    snapshot_store,
    distillation_fixture,
    ordering: str,
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    predecessor_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    retirement = _prepare_retirement_approval(
        session_factory, snapshot_store, fixture, predecessor_id
    )
    candidate_task_id = _create_proposal_task(session_factory, fixture)
    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        assert predecessor is not None
        assert predecessor.status == "active"
        original_state = knowledge_item_state(predecessor)
        original_hash = knowledge_item_content_hash(predecessor)
        initial_learning_change_count = session.scalar(
            select(func.count(LearningChange.id)).where(
                LearningChange.team_id == fixture.team_id
            )
        )
        initial_candidate_event_count = session.scalar(
            select(func.count(Event.id)).where(Event.task_id == candidate_task_id)
        )
        initial_candidate_outcome_count = session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == candidate_task_id
            )
        )

    def retire_predecessor():
        _, task_id, attempt, principal, _ = retirement
        return LearningCommitService(session_factory, snapshot_store).decide(
            task_id, attempt, principal
        )

    def propose_candidate():
        try:
            proposal = _distiller(
                session_factory, snapshot_store, _provider()
            ).propose(
                candidate_task_id,
                [case.evaluation_id for case in fixture.cases],
                supersedes_item_id=predecessor_id,
            )
            if ordering == "candidate_proposal_first":
                TaskRuntime(session_factory, snapshot_store).finalize(
                    TerminalObservation(
                        task_id=candidate_task_id,
                        attempt=1,
                        result_category="success_learning_change_proposed",
                        observed_at=datetime.now(timezone.utc),
                        learning_change_id=proposal.learning_change_id,
                    )
                )
            return proposal
        except ExperienceDistillerError as error:
            return error

    def team_lock_query(statement: str) -> bool:
        return "teams" in statement and "for update" in statement

    first_operation, second_operation = (
        (retire_predecessor, propose_candidate)
        if ordering == "retirement_first"
        else (propose_candidate, retire_predecessor)
    )
    first_result, second_result, first_pid, second_pid = _run_team_lock_ordered_race(
        database_engine,
        session_factory,
        first_operation,
        second_operation,
        # When retirement owns the Team lock first, the second proposal must
        # actually block on that lock. The helper observes pg_blocking_pids()
        # before releasing the first transaction. In the reverse ordering,
        # gate the second retirement at its Team-lock statement until the
        # proposal transaction has committed.
        second_after_first_commit=(
            None if ordering == "retirement_first" else team_lock_query
        ),
    )
    assert first_pid != second_pid
    retirement_result, candidate_result = (
        (first_result, second_result)
        if ordering == "retirement_first"
        else (second_result, first_result)
    )

    assert not isinstance(retirement_result, Exception)
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=retirement[1],
            attempt=retirement[2],
            result_category="success_learning_change_accepted",
            observed_at=retirement_result.committed_at,
            learning_change_id=retirement_result.learning_change_id,
        )
    )
    if isinstance(candidate_result, ExperienceDistillerError):
        assert ordering == "retirement_first"
        assert str(candidate_result) == "revision_target_status_invalid"
    else:
        assert not isinstance(candidate_result, Exception)
        assert ordering == "candidate_proposal_first"

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        assert predecessor is not None
        assert predecessor.status == "retired"
        assert predecessor.superseded_by_id is None
        assert predecessor.current_learning_change_id == retirement[0]
        assert predecessor.version == original_state["version"]
        assert knowledge_item_content_hash(predecessor) == original_hash
        assert (
            knowledge_item_state(predecessor)["supersedes_item_id"]
            == original_state["supersedes_item_id"]
        )
        assert session.get(LearningChange, retirement[0]).status == "accepted"
        assert (
            session.scalar(
                select(func.count(Event.id)).where(
                    Event.type == "learning_change_accepted",
                    Event.payload["operation"].as_string() == "retire",
                    Event.payload["knowledge_item_id"].as_string()
                    == str(predecessor_id),
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == retirement[1],
                    Outcome.outcome_type == "task_execution",
                )
            )
            == 1
        )
        candidate_changes = list(
            session.scalars(
                select(LearningChange).where(
                    LearningChange.proposed_by_task_id == candidate_task_id
                )
            )
        )
        if isinstance(candidate_result, ExperienceDistillerError):
            assert candidate_changes == []
            if str(candidate_result) == "revision_target_status_invalid":
                # The proposal passed its initial read, paid for generation,
                # then lost the Team-lock race. Cost accounting is durable;
                # no LearningChange proposal or task-execution Outcome exists.
                event_types = list(
                    session.scalars(
                        select(Event.type)
                        .where(Event.task_id == candidate_task_id)
                        .order_by(Event.id)
                    )
                )
                assert len(event_types) == 2
                assert set(event_types) == {
                    "generation_cost_reserved",
                    "generation_cost_reconciled",
                }
            else:
                assert (
                    session.scalar(
                        select(func.count(Event.id)).where(
                            Event.task_id == candidate_task_id
                        )
                    )
                    == initial_candidate_event_count
                )
            assert (
                session.scalar(
                    select(func.count(Outcome.id)).where(
                        Outcome.recorded_by_task_id == candidate_task_id
                    )
                )
                == initial_candidate_outcome_count
            )
        else:
            assert len(candidate_changes) == 1
            candidate_change = candidate_changes[0]
            assert candidate_change.status == "proposed"
            assert candidate_change.committed_by_task_id is None
            assert candidate_change.proposed_state["supersedes_item_id"] == str(
                predecessor_id
            )
            assert (
                session.scalar(
                    select(func.count(KnowledgeItem.id)).where(
                        KnowledgeItem.origin_learning_change_id == candidate_change.id
                    )
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count(Event.id)).where(
                        Event.task_id == candidate_task_id,
                        Event.type == "learning_change_proposed",
                    )
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count(Outcome.id)).where(
                        Outcome.recorded_by_task_id == candidate_task_id,
                        Outcome.outcome_type == "task_execution",
                    )
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count(LearningChange.id)).where(
                        LearningChange.team_id == fixture.team_id
                    )
                )
                == initial_learning_change_count + 1
            )


@pytest.mark.parametrize(
    "ordering", ["replacement_first", "candidate_retirement_first"]
)
def test_retiring_pending_candidate_and_replacement_proposal_are_serialized(
    database_engine,
    session_factory,
    snapshot_store,
    distillation_fixture,
    ordering: str,
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    predecessor_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    candidate_id = _create_active_knowledge_item(
        session_factory,
        snapshot_store,
        fixture,
        supersedes_item_id=predecessor_id,
    )
    retirement = _prepare_retirement_approval(
        session_factory, snapshot_store, fixture, candidate_id
    )
    replacement_task_id = _create_proposal_task(session_factory, fixture)
    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        candidate = session.get(KnowledgeItem, candidate_id)
        assert predecessor is not None and candidate is not None
        assert predecessor.status == candidate.status == "active"
        assert not _supersession_publication_is_visible(session, candidate, {})
        original_predecessor_state = knowledge_item_state(predecessor)
        original_predecessor_hash = knowledge_item_content_hash(predecessor)
        original_candidate_state = knowledge_item_state(candidate)
        original_candidate_hash = knowledge_item_content_hash(candidate)
        initial_learning_change_count = session.scalar(
            select(func.count(LearningChange.id)).where(
                LearningChange.team_id == fixture.team_id
            )
        )
        initial_replacement_event_count = session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == replacement_task_id
            )
        )
        initial_replacement_outcome_count = session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == replacement_task_id
            )
        )

    def retire_candidate():
        _, task_id, attempt, principal, _ = retirement
        return LearningCommitService(session_factory, snapshot_store).decide(
            task_id, attempt, principal
        )

    def propose_replacement():
        try:
            return _distiller(
                session_factory, snapshot_store, _provider()
            ).propose(
                replacement_task_id,
                [case.evaluation_id for case in fixture.cases],
                supersedes_item_id=predecessor_id,
            )
        except ExperienceDistillerError as error:
            return error

    def pending_candidate_query(statement: str) -> bool:
        return (
            "from knowledge_items" in statement
            and "where" in statement
            and "supersedes_item_id =" in statement
            and "for update" not in statement
        )

    if ordering == "replacement_first":
        # Pause after the proposal has read the pending candidate. Retirement
        # then commits before the proposal consumes that read result.
        replacement_result, retirement_result, first_pid, second_pid = (
            _run_team_lock_ordered_race(
                database_engine,
                session_factory,
                propose_replacement,
                retire_candidate,
                first_after_query_before_second=pending_candidate_query,
            )
        )
    else:
        # Retirement commits before the proposal performs its pending-candidate
        # read, so the replacement is allowed to proceed.
        retirement_result, replacement_result, first_pid, second_pid = (
            _run_team_lock_ordered_race(
                database_engine,
                session_factory,
                retire_candidate,
                propose_replacement,
                second_after_first_commit=pending_candidate_query,
            )
        )
    assert first_pid != second_pid
    assert not isinstance(retirement_result, Exception)
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=retirement[1],
            attempt=retirement[2],
            result_category="success_learning_change_accepted",
            observed_at=retirement_result.committed_at,
            learning_change_id=retirement_result.learning_change_id,
        )
    )

    if isinstance(replacement_result, ExperienceDistillerError):
        assert ordering == "replacement_first"
        assert str(replacement_result) == "successor_candidate_already_pending"
    else:
        assert not isinstance(replacement_result, Exception)
        TaskRuntime(session_factory, snapshot_store).finalize(
            TerminalObservation(
                task_id=replacement_task_id,
                attempt=1,
                result_category="success_learning_change_proposed",
                observed_at=datetime.now(timezone.utc),
                learning_change_id=replacement_result.learning_change_id,
            )
        )

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        candidate = session.get(KnowledgeItem, candidate_id)
        assert predecessor is not None and candidate is not None
        assert predecessor.status == "active"
        assert predecessor.superseded_by_id is None
        assert predecessor.current_learning_change_id == UUID(
            original_predecessor_state["current_learning_change_id"]
        )
        assert knowledge_item_state(predecessor) == original_predecessor_state
        assert knowledge_item_content_hash(predecessor) == original_predecessor_hash
        assert predecessor.review_after is not None
        assert predecessor.review_after.utcoffset() == timedelta(0)
        assert predecessor.review_after > datetime.now(timezone.utc)
        assert candidate.status == "retired"
        assert candidate.supersedes_item_id == predecessor_id
        assert candidate.current_learning_change_id == retirement[0]
        assert candidate.version == original_candidate_state["version"]
        assert knowledge_item_content_hash(candidate) == original_candidate_hash
        assert not _supersession_publication_is_visible(session, candidate, {})
        assert (
            session.scalar(
                select(func.count(KnowledgeItem.id)).where(
                    KnowledgeItem.team_id == fixture.team_id,
                    KnowledgeItem.supersedes_item_id == predecessor_id,
                    KnowledgeItem.status != "retired",
                )
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count(Event.id)).where(
                    Event.type == "learning_change_accepted",
                    Event.payload["operation"].as_string() == "retire",
                    Event.payload["knowledge_item_id"].as_string() == str(candidate_id),
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == retirement[1],
                    Outcome.outcome_type == "task_execution",
                )
            )
            == 1
        )
        replacement_changes = list(
            session.scalars(
                select(LearningChange).where(
                    LearningChange.proposed_by_task_id == replacement_task_id
                )
            )
        )
        if isinstance(replacement_result, ExperienceDistillerError):
            assert replacement_changes == []
            assert (
                session.scalar(
                    select(func.count(Event.id)).where(
                        Event.task_id == replacement_task_id
                    )
                )
                == initial_replacement_event_count
            )
            assert (
                session.scalar(
                    select(func.count(Outcome.id)).where(
                        Outcome.recorded_by_task_id == replacement_task_id
                    )
                )
                == initial_replacement_outcome_count
            )
            assert (
                session.scalar(
                    select(func.count(LearningChange.id)).where(
                        LearningChange.team_id == fixture.team_id
                    )
                )
                == initial_learning_change_count
            )
        else:
            assert len(replacement_changes) == 1
            replacement_change = replacement_changes[0]
            assert replacement_change.status == "proposed"
            assert replacement_change.committed_by_task_id is None
            assert replacement_change.proposed_state["supersedes_item_id"] == str(
                predecessor_id
            )
            assert (
                session.scalar(
                    select(func.count(KnowledgeItem.id)).where(
                        KnowledgeItem.origin_learning_change_id == replacement_change.id
                    )
                )
                == 0
            )
            assert (
                session.scalar(
                    select(func.count(Event.id)).where(
                        Event.task_id == replacement_task_id,
                        Event.type == "learning_change_proposed",
                    )
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count(Outcome.id)).where(
                        Outcome.recorded_by_task_id == replacement_task_id
                    )
                )
                == 1
            )
            assert (
                session.scalar(
                    select(func.count(LearningChange.id)).where(
                        LearningChange.team_id == fixture.team_id
                    )
                )
                == initial_learning_change_count + 1
            )
            target_binding = replacement_change.proposed_state[
                "supersedes_target_binding"
            ]
            assert target_binding["target_current_learning_change_id"] == str(
                predecessor.current_learning_change_id
            )
            assert target_binding["target_content_version"] == predecessor.version
            assert target_binding["target_content_hash"] == (
                knowledge_item_content_hash(predecessor)
            )
            assert (
                target_binding["target_state_hash"]
                == encode_state_snapshot(knowledge_item_state(predecessor))[
                    "snapshot_hash"
                ]
            )
            ancestors: set[UUID] = set()
            ancestor_id: UUID | None = predecessor_id
            while ancestor_id is not None:
                assert ancestor_id not in ancestors
                ancestors.add(ancestor_id)
                ancestor = session.get(KnowledgeItem, ancestor_id)
                assert ancestor is not None
                ancestor_id = ancestor.supersedes_item_id


def test_competing_replacement_candidates_after_cancellation_have_one_winner(
    database_engine,
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    predecessor_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    cancelled_id = _create_active_knowledge_item(
        session_factory,
        snapshot_store,
        fixture,
        supersedes_item_id=predecessor_id,
    )
    cancellation = _prepare_retirement_approval(
        session_factory, snapshot_store, fixture, cancelled_id
    )
    _, task_id, attempt, principal, _ = cancellation
    cancellation_result = LearningCommitService(
        session_factory, snapshot_store
    ).decide(task_id, attempt, principal)
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=task_id,
            attempt=attempt,
            result_category="success_learning_change_accepted",
            observed_at=cancellation_result.committed_at,
            learning_change_id=cancellation_result.learning_change_id,
        )
    )

    proposals = []
    for _ in range(2):
        proposal_task_id = _create_proposal_task(session_factory, fixture)
        proposal = _distiller(
            session_factory, snapshot_store, _provider()
        ).propose(
            proposal_task_id,
            [case.evaluation_id for case in fixture.cases],
            supersedes_item_id=predecessor_id,
        )
        TaskRuntime(session_factory, snapshot_store).finalize(
            TerminalObservation(
                task_id=proposal_task_id,
                attempt=1,
                result_category="success_learning_change_proposed",
                observed_at=datetime.now(timezone.utc),
                learning_change_id=proposal.learning_change_id,
            )
        )
        proposals.append(proposal)
    approvals = [
        _create_admitted_approval_task(
            session_factory,
            snapshot_store,
            fixture.team_id,
            proposal.learning_change_id,
        )
        for proposal in proposals
    ]

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        cancelled = session.get(KnowledgeItem, cancelled_id)
        assert predecessor is not None and cancelled is not None
        assert predecessor.status == "active"
        assert predecessor.review_after is not None
        assert predecessor.review_after.utcoffset() == timedelta(0)
        assert predecessor.review_after > datetime.now(timezone.utc)
        assert predecessor.superseded_by_id is None
        assert cancelled.status == "retired"
        assert cancelled.supersedes_item_id == predecessor_id
        predecessor_pointer = predecessor.current_learning_change_id
        predecessor_version = predecessor.version
        predecessor_state = knowledge_item_state(predecessor)

    barrier = Barrier(2)

    def decide(approval):
        task_id, approval_attempt, approval_principal = approval
        barrier.wait(timeout=30)
        try:
            return LearningCommitService(
                session_factory, snapshot_store
            ).decide(task_id, approval_attempt, approval_principal)
        except LearningCommitError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(decide, approval) for approval in approvals]
        results = [future.result(timeout=90) for future in futures]

    successes = [result for result in results if not isinstance(result, Exception)]
    failures = [result for result in results if isinstance(result, Exception)]
    assert len(successes) == len(failures) == 1
    assert str(failures[0]) == "successor_candidate_already_pending"
    winner_index = results.index(successes[0])
    loser_task_id = approvals[1 - winner_index][0]
    loser_change_id = proposals[1 - winner_index].learning_change_id
    winner_task_id, winner_attempt, _ = approvals[winner_index]
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=winner_task_id,
            attempt=winner_attempt,
            result_category="success_learning_change_accepted",
            observed_at=successes[0].committed_at,
            learning_change_id=successes[0].learning_change_id,
        )
    )

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        cancelled = session.get(KnowledgeItem, cancelled_id)
        candidates = list(
            session.scalars(
                select(KnowledgeItem).where(
                    KnowledgeItem.team_id == fixture.team_id,
                    KnowledgeItem.supersedes_item_id == predecessor_id,
                    KnowledgeItem.status != "retired",
                )
            )
        )
        assert predecessor is not None and cancelled is not None
        assert predecessor.status == "active"
        assert predecessor.current_learning_change_id == predecessor_pointer
        assert predecessor.version == predecessor_version
        assert knowledge_item_state(predecessor) == predecessor_state
        assert predecessor.superseded_by_id is None
        assert cancelled.status == "retired"
        assert len(candidates) == 1
        assert (
            candidates[0].origin_learning_change_id
            == successes[0].learning_change_id
        )
        assert candidates[0].supersedes_item_id == predecessor_id
        assert candidates[0].status == "active"
        assert candidates[0].team_id == predecessor.team_id
        assert predecessor.review_after is not None
        assert predecessor.review_after.utcoffset() == timedelta(0)
        assert predecessor.review_after > datetime.now(timezone.utc)
        assert not _supersession_publication_is_visible(session, candidates[0], {})
        lineage: set[UUID] = set()
        ancestor_id: UUID | None = candidates[0].id
        while ancestor_id is not None:
            assert ancestor_id not in lineage
            lineage.add(ancestor_id)
            ancestor = session.get(KnowledgeItem, ancestor_id)
            assert ancestor is not None
            ancestor_id = ancestor.supersedes_item_id
        winner_change = session.get(LearningChange, successes[0].learning_change_id)
        assert winner_change is not None
        target_binding = winner_change.proposed_state["supersedes_target_binding"]
        assert target_binding["target_current_learning_change_id"] == str(
            predecessor_pointer
        )
        assert target_binding["target_content_version"] == predecessor_version
        assert target_binding["target_content_hash"] == knowledge_item_content_hash(
            predecessor
        )
        assert target_binding["target_state_hash"] == encode_state_snapshot(
            predecessor_state
        )["snapshot_hash"]
        loser = session.get(LearningChange, loser_change_id)
        assert loser is not None and loser.status == "proposed"
        assert loser.committed_by_task_id is None
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == loser_task_id,
                Event.type == "learning_change_accepted",
            )
        ) == 0
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == loser_task_id
            )
        ) == 0


@pytest.mark.parametrize("drift_point", ["before_approval", "before_commit"])
@pytest.mark.parametrize(
    "dimension",
    [
        "current_pointer",
        "content_version",
        "semantic_content_hash",
        "full_state_hash",
        "candidate_predecessor_relation",
        "lifecycle_assessment_binding",
    ],
)
def test_retirement_stale_bindings_reject_without_rewriting_evidence(
    session_factory,
    snapshot_store,
    distillation_fixture,
    drift_point: str,
    dimension: str,
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    if dimension == "candidate_predecessor_relation":
        predecessor_id = _create_active_knowledge_item(
            session_factory, snapshot_store, fixture
        )
        target_id = _create_active_knowledge_item(
            session_factory,
            snapshot_store,
            fixture,
            supersedes_item_id=predecessor_id,
        )
        alternate_id = _create_active_knowledge_item(
            session_factory, snapshot_store, fixture
        )
    else:
        target_id = _create_active_knowledge_item(
            session_factory, snapshot_store, fixture
        )
        alternate_id = _create_active_knowledge_item(
            session_factory, snapshot_store, fixture
        )

    learning_change_id, principal, assessment_id = _prepare_retirement_assessment(
        session_factory, snapshot_store, fixture, target_id
    )
    approval_task_id: UUID | None = None
    if drift_point == "before_commit":
        approval_key = uuid4()
        approval = OperatorApplicationAdapter(
            session_factory, snapshot_store
        ).request_learning_change_decision(
            principal,
            LearningChangeDecisionRequest(
                learning_change_id=learning_change_id,
                decision="accept",
                idempotency_key=approval_key,
            ),
        )
        approval_task_id = approval.task_id
        TaskRuntime(session_factory, snapshot_store).admit(approval_task_id)

    with session_factory() as session:
        item = session.get(KnowledgeItem, target_id)
        change = session.get(LearningChange, learning_change_id)
        assessment = session.get(KnowledgeLifecycleAssessment, assessment_id)
        assert item is not None and change is not None and assessment is not None
        original_item_state = knowledge_item_state(item)
        original_item_content_hash = knowledge_item_content_hash(item)
        original_change = (
            change.status,
            change.proposed_state,
            change.previous_state,
            change.committed_state,
            change.committed_by_task_id,
        )
        original_assessment = (
            assessment.payload_hash,
            assessment.findings,
            assessment.assessment_result,
            assessment.recorded_at,
            assessment.current_learning_change_id,
            assessment.target_content_version,
            assessment.target_content_hash,
            assessment.target_state_hash,
        )

    if dimension == "lifecycle_assessment_binding":
        table = "knowledge_lifecycle_assessments"
        statement = update(KnowledgeLifecycleAssessment).where(
            KnowledgeLifecycleAssessment.id == assessment_id
        )
        drift_value = "sha256:" + "0" * 64
        restore_value = original_assessment[0]
        update_statement = statement.values(payload_hash=drift_value)
        restore_statement = statement.where(
            KnowledgeLifecycleAssessment.payload_hash == drift_value
        ).values(payload_hash=restore_value)
    else:
        table = "knowledge_items"
        statement = update(KnowledgeItem).where(KnowledgeItem.id == target_id)
        original_state = original_item_state
        if dimension == "current_pointer":
            drift_value = learning_change_id
            update_statement = statement.values(current_learning_change_id=drift_value)
            restore_statement = statement.where(
                KnowledgeItem.current_learning_change_id == drift_value
            ).values(
                current_learning_change_id=UUID(
                    original_state["current_learning_change_id"]
                )
            )
        elif dimension == "content_version":
            drift_value = original_state["version"] + 1
            update_statement = statement.values(version=original_state["version"] + 1)
            restore_statement = statement.where(
                KnowledgeItem.version == drift_value
            ).values(version=original_state["version"])
        elif dimension == "semantic_content_hash":
            drift_value = "A changed semantic claim."
            update_statement = statement.values(body="A changed semantic claim.")
            restore_statement = statement.where(
                KnowledgeItem.body == drift_value
            ).values(body=original_state["body"])
        elif dimension == "full_state_hash":
            drift_value = "needs_review"
            update_statement = statement.values(status="needs_review")
            restore_statement = statement.where(
                KnowledgeItem.status == drift_value
            ).values(status=original_state["status"])
        else:
            drift_value = alternate_id
            update_statement = statement.values(supersedes_item_id=alternate_id)
            restore_statement = statement.where(
                KnowledgeItem.supersedes_item_id == drift_value
            ).values(supersedes_item_id=UUID(original_state["supersedes_item_id"]))

    def apply_statement(sql_statement) -> None:
        with session_factory.begin() as session:
            session.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
            session.execute(sql_statement)
            session.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))

    drift_applied = False
    try:
        apply_statement(update_statement)
        drift_applied = True
        with session_factory() as session:
            item = session.get(KnowledgeItem, target_id)
            assessment = session.get(KnowledgeLifecycleAssessment, assessment_id)
            assert item is not None and assessment is not None
            drifted_item_state = knowledge_item_state(item)
            drifted_item_hash = knowledge_item_content_hash(item)
            drifted_assessment_hash = assessment.payload_hash
            if dimension == "full_state_hash":
                assert drifted_item_hash == original_item_content_hash
            changed_fields = {
                key
                for key, value in drifted_item_state.items()
                if value != original_item_state[key]
            }
            expected_changed_fields = {
                "current_pointer": {"current_learning_change_id"},
                "content_version": {"version"},
                "semantic_content_hash": {"body"},
                "full_state_hash": {"status"},
                "candidate_predecessor_relation": {"supersedes_item_id"},
                "lifecycle_assessment_binding": set(),
            }
            assert changed_fields == expected_changed_fields[dimension]
            if dimension == "lifecycle_assessment_binding":
                assert drifted_assessment_hash != original_assessment[0]

        if drift_point == "before_approval":
            with session_factory() as session:
                team_event_count = session.scalar(
                    select(func.count(Event.id)).join(
                        Task, Task.id == Event.task_id
                    ).where(Task.team_id == fixture.team_id)
                )
                team_outcome_count = session.scalar(
                    select(func.count(Outcome.id)).where(
                        Outcome.team_id == fixture.team_id
                    )
                )
            with pytest.raises(LearningChangeNotApprovable) as rejection:
                OperatorApplicationAdapter(
                    session_factory, snapshot_store
                ).request_learning_change_decision(
                    principal,
                    LearningChangeDecisionRequest(
                        learning_change_id=learning_change_id,
                        decision="accept",
                        idempotency_key=uuid4(),
                    ),
                )
            assert str(rejection.value).startswith("knowledge_lifecycle_")
            with session_factory() as session:
                assert session.scalar(
                    select(func.count(Event.id)).where(
                        Event.type == "operator_task_requested",
                        Event.payload["learning_change_id"].as_string()
                        == str(learning_change_id),
                    )
                ) == 0
                assert session.scalar(
                    select(func.count(Event.id)).join(
                        Task, Task.id == Event.task_id
                    ).where(Task.team_id == fixture.team_id)
                ) == team_event_count
                assert session.scalar(
                    select(func.count(Outcome.id)).where(
                        Outcome.team_id == fixture.team_id
                    )
                ) == team_outcome_count
        else:
            assert approval_task_id is not None
            with session_factory() as session:
                event_count = session.scalar(
                    select(func.count(Event.id)).where(
                        Event.task_id == approval_task_id
                    )
                )
                outcome_count = session.scalar(
                    select(func.count(Outcome.id)).where(
                        Outcome.recorded_by_task_id == approval_task_id
                    )
                )
                request_event = session.scalar(
                    select(Event).where(
                        Event.task_id == approval_task_id,
                        Event.type == "operator_task_requested",
                    )
                )
                assert request_event is not None
                original_approval_payload = request_event.payload

            with pytest.raises(LearningCommitError) as rejection:
                LearningCommitService(session_factory, snapshot_store).decide(
                    approval_task_id, 1, principal
                )
            assert str(rejection.value).startswith("knowledge_lifecycle_")
            with session_factory() as session:
                assert session.scalar(
                    select(func.count(Event.id)).where(
                        Event.task_id == approval_task_id
                    )
                ) == event_count
                assert session.scalar(
                    select(func.count(Outcome.id)).where(
                        Outcome.recorded_by_task_id == approval_task_id
                    )
                ) == outcome_count
                request_event = session.scalar(
                    select(Event).where(
                        Event.task_id == approval_task_id,
                        Event.type == "operator_task_requested",
                    )
                )
                assert request_event is not None
                assert request_event.payload == original_approval_payload

        with session_factory() as session:
            item = session.get(KnowledgeItem, target_id)
            change = session.get(LearningChange, learning_change_id)
            assessment = session.get(KnowledgeLifecycleAssessment, assessment_id)
            assert item is not None and change is not None and assessment is not None
            assert knowledge_item_state(item) == drifted_item_state
            assert knowledge_item_content_hash(item) == drifted_item_hash
            assert (
                change.status,
                change.proposed_state,
                change.previous_state,
                change.committed_state,
                change.committed_by_task_id,
            ) == original_change
            assert (
                assessment.payload_hash,
                assessment.findings,
                assessment.assessment_result,
                assessment.recorded_at,
                assessment.current_learning_change_id,
                assessment.target_content_version,
                assessment.target_content_hash,
                assessment.target_state_hash,
            ) == (
                drifted_assessment_hash,
                *original_assessment[1:],
            )
    finally:
        if drift_applied:
            apply_statement(restore_statement)
            with session_factory() as session:
                item = session.get(KnowledgeItem, target_id)
                assessment = session.get(KnowledgeLifecycleAssessment, assessment_id)
                assert item is not None and assessment is not None
                assert knowledge_item_state(item) == original_item_state
                assert knowledge_item_content_hash(item) == original_item_content_hash
                assert (
                    assessment.payload_hash,
                    assessment.findings,
                    assessment.assessment_result,
                    assessment.recorded_at,
                    assessment.current_learning_change_id,
                    assessment.target_content_version,
                    assessment.target_content_hash,
                    assessment.target_state_hash,
                ) == original_assessment


def test_retirement_replay_conflicts_on_different_proposal_identity(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    target_id = _create_active_knowledge_item(session_factory, snapshot_store, fixture)
    first_change_id, principal, _ = _prepare_retirement_assessment(
        session_factory, snapshot_store, fixture, target_id
    )
    second_change_id, _, _ = _prepare_retirement_assessment(
        session_factory, snapshot_store, fixture, target_id
    )
    assert first_change_id != second_change_id
    idempotency_key = uuid4()
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    rejection_reason = "The current evidence does not justify retirement."
    first_request = LearningChangeDecisionRequest(
        learning_change_id=first_change_id,
        decision="reject",
        idempotency_key=idempotency_key,
        rejection_reason=rejection_reason,
    )
    original = adapter.decide_learning_change(principal, first_request)
    replay = adapter.decide_learning_change(principal, first_request)
    assert original.learning_change_status == "rejected"
    assert replay.replayed
    with session_factory() as session:
        first_change = session.get(LearningChange, first_change_id)
        second_change = session.get(LearningChange, second_change_id)
        assert first_change is not None and second_change is not None
        assert first_change.target_id == second_change.target_id == target_id
        before_conflict = _team_lifecycle_snapshot(session, fixture.team_id)

    with pytest.raises(
        OperatorTaskRequestConflict,
        match="idempotency_key_reused_with_different_request",
    ):
        adapter.decide_learning_change(
            principal,
            LearningChangeDecisionRequest(
                learning_change_id=second_change_id,
                decision="reject",
                idempotency_key=idempotency_key,
                rejection_reason=rejection_reason,
            ),
        )

    with session_factory() as session:
        first_change = session.get(LearningChange, first_change_id)
        second_change = session.get(LearningChange, second_change_id)
        assert first_change is not None and second_change is not None
        assert first_change.status == "rejected"
        assert second_change.status == "proposed"
        assert _team_lifecycle_snapshot(session, fixture.team_id) == before_conflict


def test_retirement_replay_conflicts_on_different_target(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    first_target_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    second_target_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    first_change_id, principal, _ = _prepare_retirement_assessment(
        session_factory, snapshot_store, fixture, first_target_id
    )
    second_change_id, _, _ = _prepare_retirement_assessment(
        session_factory, snapshot_store, fixture, second_target_id
    )
    assert first_change_id != second_change_id
    idempotency_key = uuid4()
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    rejection_reason = "The current evidence does not justify retirement."
    first_request = LearningChangeDecisionRequest(
        learning_change_id=first_change_id,
        decision="reject",
        idempotency_key=idempotency_key,
        rejection_reason=rejection_reason,
    )
    original = adapter.decide_learning_change(principal, first_request)
    replay = adapter.decide_learning_change(principal, first_request)
    assert original.learning_change_status == "rejected"
    assert replay.replayed
    with session_factory() as session:
        first_change = session.get(LearningChange, first_change_id)
        second_change = session.get(LearningChange, second_change_id)
        assert first_change is not None and second_change is not None
        assert first_change.target_id == first_target_id
        assert second_change.target_id == second_target_id
        before_conflict = _team_lifecycle_snapshot(session, fixture.team_id)

    with pytest.raises(
        OperatorTaskRequestConflict,
        match="idempotency_key_reused_with_different_request",
    ):
        adapter.decide_learning_change(
            principal,
            LearningChangeDecisionRequest(
                learning_change_id=second_change_id,
                decision="reject",
                idempotency_key=idempotency_key,
                rejection_reason=rejection_reason,
            ),
        )

    with session_factory() as session:
        first_change = session.get(LearningChange, first_change_id)
        second_change = session.get(LearningChange, second_change_id)
        assert first_change is not None and second_change is not None
        assert first_change.status == "rejected"
        assert second_change.status == "proposed"
        assert _team_lifecycle_snapshot(session, fixture.team_id) == before_conflict


def test_retirement_replay_conflicts_on_different_approval_binding(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    target_id = _create_active_knowledge_item(session_factory, snapshot_store, fixture)
    learning_change_id, principal, _ = _prepare_retirement_assessment(
        session_factory, snapshot_store, fixture, target_id
    )
    other_principal = _approval_principal(
        fixture.team_id, subject=f"operator-retire-conflict-{uuid4()}"
    )
    request = LearningChangeDecisionRequest(
        learning_change_id=learning_change_id,
        decision="reject",
        idempotency_key=uuid4(),
        rejection_reason="The current evidence does not justify retirement.",
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    original = adapter.decide_learning_change(principal, request)
    replay = adapter.decide_learning_change(principal, request)
    assert original.learning_change_status == "rejected"
    assert replay.replayed
    with session_factory() as session:
        approval_event = session.scalar(
            select(Event).where(
                Event.task_id == original.task_id,
                Event.type == "operator_task_requested",
            )
        )
        assert approval_event is not None
        original_binding = approval_event.payload["approval_binding"]
        before_conflict = _team_lifecycle_snapshot(session, fixture.team_id)

    assert original_binding["operator_id"] != (
        canonical_operator_identity(other_principal.issuer, other_principal.subject)
    )
    with pytest.raises(
        OperatorTaskRequestConflict,
        match="idempotency_key_reused_with_different_request",
    ):
        adapter.decide_learning_change(other_principal, request)

    with session_factory() as session:
        change = session.get(LearningChange, learning_change_id)
        assert change is not None and change.status == "rejected"
        assert _team_lifecycle_snapshot(session, fixture.team_id) == before_conflict


def test_rejected_retirement_replay_keeps_disposition_after_later_retirement(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    target_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    rejected_change_id, principal, _ = _prepare_retirement_assessment(
        session_factory, snapshot_store, fixture, target_id
    )
    rejection_request = LearningChangeDecisionRequest(
        learning_change_id=rejected_change_id,
        decision="reject",
        idempotency_key=uuid4(),
        rejection_reason="The current evidence does not justify retirement.",
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    rejected = adapter.decide_learning_change(principal, rejection_request)
    assert rejected.decision == "reject"
    assert rejected.learning_change_status == "rejected"

    accepted_change_id, accepted_task_id, accepted_attempt, accepted_principal, _ = (
        _prepare_retirement_approval(
            session_factory, snapshot_store, fixture, target_id
        )
    )
    accepted = LearningCommitService(session_factory, snapshot_store).decide(
        accepted_task_id, accepted_attempt, accepted_principal
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=accepted_task_id,
            attempt=accepted_attempt,
            result_category="success_learning_change_accepted",
            observed_at=accepted.committed_at,
            learning_change_id=accepted.learning_change_id,
        )
    )
    with session_factory() as session:
        target = session.get(KnowledgeItem, target_id)
        rejected_change = session.get(LearningChange, rejected_change_id)
        assert target is not None and rejected_change is not None
        assert target.status == "retired"
        assert target.current_learning_change_id == accepted_change_id
        assert rejected_change.status == "rejected"
        before_replay = (
            rejected_change.committed_state,
            rejected_change.committed_by_task_id,
            target.current_learning_change_id,
            target.status,
            session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == rejected.task_id
                )
            ),
            session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == rejected.task_id
                )
            ),
        )

    replay = adapter.decide_learning_change(principal, rejection_request)
    assert replay.replayed
    assert replay.decision == "reject"
    assert replay.learning_change_id == rejected_change_id
    with session_factory() as session:
        target = session.get(KnowledgeItem, target_id)
        rejected_change = session.get(LearningChange, rejected_change_id)
        assert target is not None and rejected_change is not None
        assert (
            rejected_change.committed_state,
            rejected_change.committed_by_task_id,
            target.current_learning_change_id,
            target.status,
            session.scalar(
                select(func.count(Event.id)).where(
                    Event.task_id == rejected.task_id
                )
            ),
            session.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.recorded_by_task_id == rejected.task_id
                )
            ),
        ) == before_replay


def test_stale_retirement_replay_preserves_disposition_after_state_restoration(
    database_engine,
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False, review_interval_days=1)
    target_id = _create_active_knowledge_item(session_factory, snapshot_store, fixture)
    learning_change_id, principal, assessment_id = _prepare_retirement_assessment(
        session_factory, snapshot_store, fixture, target_id
    )
    idempotency_key = uuid4()
    request = LearningChangeDecisionRequest(
        learning_change_id=learning_change_id,
        decision="accept",
        idempotency_key=idempotency_key,
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    approval = adapter.request_learning_change_decision(principal, request)
    TaskRuntime(session_factory, snapshot_store).admit(approval.task_id)
    with session_factory() as session:
        target = session.get(KnowledgeItem, target_id)
        change = session.get(LearningChange, learning_change_id)
        assessment = session.get(KnowledgeLifecycleAssessment, assessment_id)
        assert target is not None and change is not None and assessment is not None
        original_item_state = knowledge_item_state(target)
        original_content_hash = knowledge_item_content_hash(target)
        original_change = (
            change.status,
            change.proposed_state,
            change.previous_state,
            change.committed_state,
            change.committed_by_task_id,
        )
        original_assessment_hash = assessment.payload_hash

    def set_target_status(expected: str, replacement: str) -> None:
        with session_factory.begin() as session:
            session.execute(text("ALTER TABLE knowledge_items DISABLE TRIGGER USER"))
            result = session.execute(
                update(KnowledgeItem)
                .where(
                    KnowledgeItem.id == target_id,
                    KnowledgeItem.status == expected,
                )
                .values(status=replacement)
            )
            session.execute(text("ALTER TABLE knowledge_items ENABLE TRIGGER USER"))
            assert result.rowcount == 1

    team_lock_count = 0
    drift_applied = False
    drift_injected = ThreadEvent()
    first_error: LearningCommitError | None = None
    first_result = None
    stale_task_state = None
    stale_failure_events = ()
    stale_outcome_count = 0

    def inject_stale_state_after_commit_team_lock(
        connection, cursor, statement, parameters, context, executemany
    ):
        nonlocal team_lock_count, drift_applied
        normalized = statement.lower()
        if "teams" not in normalized or "for update" not in normalized:
            return
        team_lock_count += 1
        if team_lock_count == 2:
            set_target_status("active", "needs_review")
            drift_applied = True
            drift_injected.set()

    try:
        event.listen(
            database_engine,
            "after_cursor_execute",
            inject_stale_state_after_commit_team_lock,
        )
        try:
            try:
                first_result = adapter.decide_learning_change(principal, request)
            except LearningCommitError as error:
                first_error = error
            assert drift_injected.is_set()
            with session_factory() as session:
                task = session.get(Task, approval.task_id)
                target = session.get(KnowledgeItem, target_id)
                change = session.get(LearningChange, learning_change_id)
                assessment = session.get(KnowledgeLifecycleAssessment, assessment_id)
                assert (
                    task is not None
                    and target is not None
                    and change is not None
                    and assessment is not None
                )
                stale_task_state = (
                    task.status,
                    task.attempt_count,
                    task.completed_at,
                )
                stale_failure_events = tuple(
                    (
                        item.type,
                        item.payload,
                    )
                    for item in session.scalars(
                        select(Event).where(
                            Event.task_id == approval.task_id,
                            Event.type.in_(("task_attempt_failed", "task_failed")),
                        )
                    )
                )
                stale_outcome_count = session.scalar(
                    select(func.count(Outcome.id)).where(
                        Outcome.recorded_by_task_id == approval.task_id
                    )
                )
                assert knowledge_item_state(target)["status"] == "needs_review"
                assert knowledge_item_content_hash(target) == original_content_hash
                assert (
                    change.status,
                    change.proposed_state,
                    change.previous_state,
                    change.committed_state,
                    change.committed_by_task_id,
                ) == original_change
                assert assessment.payload_hash == original_assessment_hash
        finally:
            event.remove(
                database_engine,
                "after_cursor_execute",
                inject_stale_state_after_commit_team_lock,
            )
    finally:
        if drift_applied:
            set_target_status("needs_review", "active")
            with session_factory() as session:
                target = session.get(KnowledgeItem, target_id)
                assert target is not None
                assert knowledge_item_state(target) == original_item_state
                assert knowledge_item_content_hash(target) == original_content_hash

    with session_factory() as session:
        before_replay = _team_lifecycle_snapshot(session, fixture.team_id)
        target = session.get(KnowledgeItem, target_id)
        change = session.get(LearningChange, learning_change_id)
        assessment = session.get(KnowledgeLifecycleAssessment, assessment_id)
        assert target is not None and change is not None and assessment is not None
        assert knowledge_item_state(target) == original_item_state
        assert (
            change.status,
            change.proposed_state,
            change.previous_state,
            change.committed_state,
            change.committed_by_task_id,
        ) == original_change
        assert assessment.payload_hash == original_assessment_hash

    stale_reason = (
        "knowledge_lifecycle_predecessor_reconstructed_history_does_not_match_live_item"
    )
    assert str(first_error) == stale_reason
    assert first_result is None
    assert stale_task_state is not None and stale_task_state[0] == "failed"
    assert len(stale_failure_events) == 2
    assert all(
        payload["failure_reason"] == stale_reason
        for _, payload in stale_failure_events
    )
    assert stale_outcome_count == 1

    replay_error: Exception | None = None
    replay_result = None
    try:
        replay_result = adapter.decide_learning_change(principal, request)
    except (LearningCommitError, OperatorTaskRequestConflict) as error:
        replay_error = error
    with session_factory() as session:
        assert _team_lifecycle_snapshot(session, fixture.team_id) == before_replay

    assert isinstance(replay_error, OperatorTaskRequestConflict)
    assert str(replay_error) == stale_reason
    assert replay_result is None



def test_b5_3_supersede_proposal_assessment_and_atomic_predecessor_commit(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    from core.knowledge_lifecycle import _task_id
    from core.knowledge_lifecycle_tasks import KnowledgeLifecycleAssessmentTaskRunner
    from core.learning_commit import LearningCommitService
    from core.learning_history import (
        knowledge_item_content_hash,
        knowledge_item_state,
        reconstruct_knowledge_item_history,
    )
    from core.models import Event, KnowledgeItem, LearningChange
    from core.operator_application import (
        LearningChangeDecisionRequest,
        OperatorApplicationAdapter,
    )

    fixture = distillation_fixture(1, False, review_interval_days=30)
    evaluation_ids = tuple(case.evaluation_id for case in fixture.cases)
    runtime = TaskRuntime(session_factory, snapshot_store)
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)

    predecessor_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    successor_id = _create_active_knowledge_item(
        session_factory,
        snapshot_store,
        fixture,
        supersedes_item_id=predecessor_id,
    )
    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        successor = session.get(KnowledgeItem, successor_id)
        assert predecessor is not None and successor is not None
        predecessor_before = knowledge_item_state(predecessor)
        predecessor_content_hash = knowledge_item_content_hash(predecessor)
        successor_before = knowledge_item_state(successor)
        successor_content_hash = knowledge_item_content_hash(successor)
        assert successor.supersedes_item_id == predecessor_id
        assert successor.status == "active"

    principal = _approval_principal(
        fixture.team_id, subject=f"operator-supersede-{uuid4()}"
    )
    proposal_task_id = _create_proposal_task(session_factory, fixture)
    rationale = {
        "schema_version": 1,
        "summary": "The accepted successor replaces the predecessor.",
        "reasons": [
            {
                "category": "improved_evidence",
                "statement": "The successor incorporates newer validated evidence.",
            },
            {
                "category": "applicability_changed",
                "statement": "The predecessor's original conditions no longer apply.",
            },
        ],
    }
    proposal = adapter.propose_supersede(
        principal,
        task_id=proposal_task_id,
        evaluation_ids=evaluation_ids,
        target_knowledge_item_id=predecessor_id,
        successor_knowledge_item_id=successor_id,
        operator_rationale=rationale,
    )
    runtime.finalize(
        TerminalObservation(
            task_id=proposal_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )

    lifecycle_task_id = _task_id(fixture.team_id, proposal.learning_change_id)
    fixture.extra_task_ids.append(lifecycle_task_id)
    assessment = KnowledgeLifecycleAssessmentTaskRunner(
        session_factory, snapshot_store
    ).run(lifecycle_task_id)
    assert assessment.status == "done"
    assert assessment.assessment_result == "eligible"
    assert assessment.assessment_id is not None

    approval = adapter.request_learning_change_decision(
        principal,
        LearningChangeDecisionRequest(
            learning_change_id=proposal.learning_change_id,
            decision="accept",
            idempotency_key=uuid4(),
        ),
    )
    admission = runtime.admit(approval.task_id)
    commit_service = LearningCommitService(session_factory, snapshot_store)
    committed = commit_service.decide(
        approval.task_id, admission.attempt_count, principal
    )
    assert committed.decision == "accept"
    assert committed.knowledge_item_id == predecessor_id

    runtime.finalize(
        TerminalObservation(
            task_id=approval.task_id,
            attempt=admission.attempt_count,
            result_category="success_learning_change_accepted",
            observed_at=committed.committed_at,
            learning_change_id=committed.learning_change_id,
        )
    )

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        successor = session.get(KnowledgeItem, successor_id)
        change = session.get(LearningChange, proposal.learning_change_id)
        event = session.scalar(
            select(Event).where(
                Event.task_id == approval.task_id,
                Event.type == "learning_change_accepted",
            )
        )
        assert predecessor is not None and successor is not None
        assert change is not None and event is not None
        assert predecessor.status == "retired"
        assert predecessor.superseded_by_id == successor_id
        assert predecessor.current_learning_change_id == proposal.learning_change_id
        assert predecessor.version == predecessor_before["version"]
        assert knowledge_item_content_hash(predecessor) == predecessor_content_hash
        assert knowledge_item_state(successor) == successor_before
        assert knowledge_item_content_hash(successor) == successor_content_hash
        assert event.payload["successor_knowledge_item_id"] == str(successor_id)
        predecessor_history = reconstruct_knowledge_item_history(
            session, predecessor
        )
        successor_history = reconstruct_knowledge_item_history(session, successor)
        assert predecessor_history.states[-1]["status"] == "retired"
        assert (
            predecessor_history.states[-1]["superseded_by_id"] == str(successor_id)
        )
        assert (
            predecessor_history.learning_change_ids[-1]
            == proposal.learning_change_id
        )
        assert proposal.learning_change_id not in successor_history.learning_change_ids
        assert change.committed_state is not None

    replayed = commit_service.decide(
        approval.task_id, admission.attempt_count, principal
    )
    assert replayed.replayed is True
    assert replayed.knowledge_item_id == predecessor_id


def _prepare_supersede_assessment(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    fixture: _Fixture,
    predecessor_id: UUID,
    successor_id: UUID,
    *,
    principal: TrustedOperatorPrincipal | None = None,
) -> tuple[UUID, TrustedOperatorPrincipal, UUID]:
    from core.knowledge_lifecycle_tasks import (
        KnowledgeLifecycleAssessmentTask,
        KnowledgeLifecycleAssessmentTaskRunner,
    )

    operator = principal or _approval_principal(
        fixture.team_id, subject=f"operator-supersede-{uuid4()}"
    )
    proposal_task_id = _create_proposal_task(session_factory, fixture)
    proposal = OperatorApplicationAdapter(
        session_factory, snapshot_store
    ).propose_supersede(
        operator,
        task_id=proposal_task_id,
        evaluation_ids=tuple(case.evaluation_id for case in fixture.cases),
        target_knowledge_item_id=predecessor_id,
        successor_knowledge_item_id=successor_id,
        operator_rationale={
            "schema_version": 1,
            "summary": "The accepted successor replaces the predecessor.",
            "reasons": [
                {
                    "category": "improved_evidence",
                    "statement": "The successor incorporates newer validated evidence.",
                },
                {
                    "category": "applicability_changed",
                    "statement": (
                        "The predecessor's original conditions no longer apply."
                    ),
                },
            ],
        },
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=proposal_task_id,
            attempt=1,
            result_category="success_learning_change_proposed",
            observed_at=datetime.now(timezone.utc),
            learning_change_id=proposal.learning_change_id,
        )
    )
    lifecycle_task_id = KnowledgeLifecycleAssessmentTask(
        session_factory, snapshot_store
    ).create(proposal.learning_change_id)
    fixture.extra_task_ids.append(lifecycle_task_id)
    assessment = KnowledgeLifecycleAssessmentTaskRunner(
        session_factory, snapshot_store
    ).run(lifecycle_task_id)
    assert assessment.status == "done"
    assert assessment.assessment_result == "eligible"
    assert assessment.assessment_id is not None
    return proposal.learning_change_id, operator, assessment.assessment_id


def _prepare_supersede_approval(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    fixture: _Fixture,
    predecessor_id: UUID,
    successor_id: UUID,
    *,
    principal: TrustedOperatorPrincipal | None = None,
    idempotency_key: UUID | None = None,
) -> tuple[UUID, UUID, int, TrustedOperatorPrincipal, UUID]:
    learning_change_id, operator, assessment_id = _prepare_supersede_assessment(
        session_factory,
        snapshot_store,
        fixture,
        predecessor_id,
        successor_id,
        principal=principal,
    )
    approval = OperatorApplicationAdapter(
        session_factory, snapshot_store
    ).request_learning_change_decision(
        operator,
        LearningChangeDecisionRequest(
            learning_change_id=learning_change_id,
            decision="accept",
            idempotency_key=idempotency_key or uuid4(),
        ),
    )
    admission = TaskRuntime(session_factory, snapshot_store).admit(approval.task_id)
    return (
        learning_change_id,
        approval.task_id,
        admission.attempt_count,
        operator,
        assessment_id,
    )


def test_b5_3_4_reciprocal_publication_is_shared_by_projection_retrieval_and_context(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    from core.context_assembly import TaskContextAssembler, TaskContextError

    fixture = distillation_fixture(1, False, review_interval_days=30)
    predecessor_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    successor_id = _create_active_knowledge_item(
        session_factory,
        snapshot_store,
        fixture,
        supersedes_item_id=predecessor_id,
    )

    class FakeEmbeddingProvider:
        space = EmbeddingSpace(
            provider="watch_test",
            model="b53-reciprocal-publication",
            revision="1",
            dimensions=3,
            configuration="b53-consumer-proof",
        )

        def current_space(self):
            return self.space

        def embed(self, texts):
            return EmbeddingBatch(
                space=self.space,
                vectors=tuple((0.1, 0.2, 0.3) for _ in texts),
            )

    provider = FakeEmbeddingProvider()
    indexer = TeamExperienceIndexer(session_factory, provider)
    retriever = HybridKnowledgeRetriever(session_factory, snapshot_store, provider)
    assert indexer.index_knowledge_item(predecessor_id).outcome == "indexed"
    assert indexer.index_knowledge_item(successor_id).outcome == "indexed"

    before = retriever.retrieve(fixture.team_id, "validated source evidence")
    before_ids = {passage.knowledge_item_id for passage in before}
    assert predecessor_id in before_ids
    assert successor_id not in before_ids

    supersede = _prepare_supersede_approval(
        session_factory,
        snapshot_store,
        fixture,
        predecessor_id,
        successor_id,
    )
    learning_change_id, approval_task_id, attempt, principal, _ = supersede
    commit = LearningCommitService(session_factory, snapshot_store).decide(
        approval_task_id, attempt, principal
    )
    assert commit.decision == "accept"
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=approval_task_id,
            attempt=attempt,
            result_category="success_learning_change_accepted",
            observed_at=commit.committed_at,
            learning_change_id=learning_change_id,
        )
    )

    after = retriever.retrieve(fixture.team_id, "validated source evidence")
    after_ids = {passage.knowledge_item_id for passage in after}
    assert successor_id in after_ids
    assert predecessor_id not in after_ids
    successor_passage = next(
        passage for passage in after if passage.knowledge_item_id == successor_id
    )

    scope = SimpleNamespace(team_id=fixture.team_id)
    with session_factory() as session:
        TaskContextAssembler._validate_team_experience_passage(
            session, scope, successor_passage, datetime.now(timezone.utc)
        )
        predecessor = session.get(KnowledgeItem, predecessor_id)
        assert predecessor is not None
        original_pointer = predecessor.superseded_by_id
        assert original_pointer == successor_id

    # A one-sided link must fail closed in both consumers.
    with session_factory.begin() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        assert predecessor is not None
        predecessor.superseded_by_id = None
    assert successor_id not in {
        passage.knowledge_item_id
        for passage in retriever.retrieve(fixture.team_id, "validated source evidence")
    }
    with session_factory() as session:
        with pytest.raises(
            TaskContextError, match="team_experience_supersession_not_visible"
        ):
            TaskContextAssembler._validate_team_experience_passage(
                session, scope, successor_passage, datetime.now(timezone.utc)
            )
    with session_factory.begin() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        assert predecessor is not None
        predecessor.superseded_by_id = successor_id

    # The canonical decision Event must name the same successor as the graph.
    with session_factory() as session:
        decision_event = session.scalar(
            select(Event).where(
                Event.task_id == approval_task_id,
                Event.type == "learning_change_accepted",
            )
        )
        assert decision_event is not None
        original_payload = dict(decision_event.payload)
    with session_factory.begin() as session:
        decision_event = session.scalar(
            select(Event).where(
                Event.task_id == approval_task_id,
                Event.type == "learning_change_accepted",
            )
        )
        assert decision_event is not None
        decision_event.payload = {
            **decision_event.payload,
            "successor_knowledge_item_id": str(uuid4()),
        }
    assert successor_id not in {
        passage.knowledge_item_id
        for passage in retriever.retrieve(fixture.team_id, "validated source evidence")
    }
    with session_factory() as session:
        with pytest.raises(
            TaskContextError, match="team_experience_supersession_not_visible"
        ):
            TaskContextAssembler._validate_team_experience_passage(
                session, scope, successor_passage, datetime.now(timezone.utc)
            )
    with session_factory.begin() as session:
        decision_event = session.scalar(
            select(Event).where(
                Event.task_id == approval_task_id,
                Event.type == "learning_change_accepted",
            )
        )
        assert decision_event is not None
        decision_event.payload = original_payload

    with session_factory() as session:
        successor = session.get(KnowledgeItem, successor_id)
        assert successor is not None
        original_review_after = successor.review_after
        assert original_review_after is not None

    ineligible_states = (
        ("due", original_review_after - timedelta(seconds=1), "active"),
        ("unscheduled", None, "active"),
        ("needs_review", original_review_after, "needs_review"),
    )
    for _, review_after, status in ineligible_states:
        with session_factory.begin() as session:
            successor = session.get(KnowledgeItem, successor_id)
            assert successor is not None
            successor.review_after = review_after
            successor.status = status
        assert successor_id not in {
            passage.knowledge_item_id
            for passage in retriever.retrieve(
                fixture.team_id, "validated source evidence"
            )
        }
        with session_factory() as session:
            with pytest.raises(
                TaskContextError,
                match="team_experience_item_not_current_or_eligible",
            ):
                TaskContextAssembler._validate_team_experience_passage(
                    session, scope, successor_passage, datetime.now(timezone.utc)
                )
        with session_factory.begin() as session:
            successor = session.get(KnowledgeItem, successor_id)
            assert successor is not None
            successor.review_after = original_review_after
            successor.status = "active"

    with session_factory() as session:
        successor = session.get(KnowledgeItem, successor_id)
        predecessor = session.get(KnowledgeItem, predecessor_id)
        assert successor is not None and predecessor is not None
        assert successor.supersedes_item_id == predecessor.id
        assert predecessor.superseded_by_id == successor.id
        TaskContextAssembler._validate_team_experience_passage(
            session, scope, successor_passage, datetime.now(timezone.utc)
        )


def test_b5_3_5_competing_supersede_approvals_have_one_canonical_winner(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False, review_interval_days=30)
    predecessor_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    successor_id = _create_active_knowledge_item(
        session_factory,
        snapshot_store,
        fixture,
        supersedes_item_id=predecessor_id,
    )
    principal = _approval_principal(
        fixture.team_id, subject=f"operator-competing-supersede-{uuid4()}"
    )
    approvals = [
        _prepare_supersede_approval(
            session_factory,
            snapshot_store,
            fixture,
            predecessor_id,
            successor_id,
            principal=principal,
        )
        for _ in range(2)
    ]
    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        successor = session.get(KnowledgeItem, successor_id)
        assert predecessor is not None and successor is not None
        predecessor_before = knowledge_item_state(predecessor)
        successor_before = knowledge_item_state(successor)
        assert predecessor_before["status"] == "active"
        successor_hash = knowledge_item_content_hash(successor)

    barrier = Barrier(2)

    def decide(approval):
        _, task_id, attempt, operator, _ = approval
        barrier.wait(timeout=30)
        try:
            return LearningCommitService(session_factory, snapshot_store).decide(
                task_id, attempt, operator
            )
        except LearningCommitError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(decide, approval) for approval in approvals]
        results = [future.result(timeout=90) for future in futures]

    winners = [
        result for result in results if not isinstance(result, LearningCommitError)
    ]
    losers = [
        result for result in results if isinstance(result, LearningCommitError)
    ]
    assert len(winners) == 1
    assert len(losers) == 1
    winner_index = next(
        index
        for index, result in enumerate(results)
        if not isinstance(result, LearningCommitError)
    )
    winner_change_id, winner_task_id, winner_attempt, _, _ = approvals[winner_index]
    loser_change_id, loser_task_id, _, _, _ = approvals[1 - winner_index]
    winner = winners[0]
    assert winner.learning_change_id == winner_change_id
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=winner_task_id,
            attempt=winner_attempt,
            result_category="success_learning_change_accepted",
            observed_at=winner.committed_at,
            learning_change_id=winner_change_id,
        )
    )

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        successor = session.get(KnowledgeItem, successor_id)
        winner_change = session.get(LearningChange, winner_change_id)
        loser_change = session.get(LearningChange, loser_change_id)
        assert predecessor is not None and successor is not None
        assert winner_change is not None and loser_change is not None
        assert predecessor.status == "retired"
        assert predecessor.superseded_by_id == successor_id
        assert predecessor.current_learning_change_id == winner_change_id
        assert knowledge_item_state(successor) == successor_before
        assert knowledge_item_content_hash(successor) == successor_hash
        assert winner_change.status == "accepted"
        assert loser_change.status == "proposed"
        assert loser_change.committed_by_task_id is None
        assert reconstruct_knowledge_item_history(
            session, predecessor
        ).learning_change_ids[-1] == winner_change_id
        assert winner_change_id not in reconstruct_knowledge_item_history(
            session, successor
        ).learning_change_ids
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == winner_task_id,
                Event.type == "learning_change_accepted",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == winner_task_id,
                Outcome.outcome_type == "task_execution",
            )
        ) == 1
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == loser_task_id,
                Event.type == "learning_change_accepted",
            )
        ) == 0
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == loser_task_id
            )
        ) == 0


def test_b5_3_5_supersede_and_predecessor_retirement_race_has_one_winner(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False, review_interval_days=30)
    predecessor_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    successor_id = _create_active_knowledge_item(
        session_factory,
        snapshot_store,
        fixture,
        supersedes_item_id=predecessor_id,
    )
    retirement = _prepare_retirement_approval(
        session_factory, snapshot_store, fixture, predecessor_id
    )
    supersede = _prepare_supersede_approval(
        session_factory,
        snapshot_store,
        fixture,
        predecessor_id,
        successor_id,
    )
    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        successor = session.get(KnowledgeItem, successor_id)
        assert predecessor is not None and successor is not None
        successor_before = knowledge_item_state(successor)
        successor_hash = knowledge_item_content_hash(successor)

    barrier = Barrier(2)

    def decide(task_id, attempt, operator):
        barrier.wait(timeout=30)
        try:
            return LearningCommitService(session_factory, snapshot_store).decide(
                task_id, attempt, operator
            )
        except LearningCommitError as error:
            return error

    operations = (
        (retirement[0], retirement[1], retirement[2], retirement[3]),
        (supersede[0], supersede[1], supersede[2], supersede[3]),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(decide, task_id, attempt, operator)
            for _, task_id, attempt, operator in operations
        ]
        results = [future.result(timeout=90) for future in futures]

    winners = [
        result for result in results if not isinstance(result, LearningCommitError)
    ]
    losers = [result for result in results if isinstance(result, LearningCommitError)]
    assert len(winners) == 1
    assert len(losers) == 1
    winner_index = next(
        index
        for index, result in enumerate(results)
        if not isinstance(result, LearningCommitError)
    )
    winner_change_id, winner_task_id, winner_attempt, _ = operations[winner_index]
    loser_change_id, loser_task_id, _, _ = operations[1 - winner_index]
    winner = winners[0]
    assert winner.learning_change_id == winner_change_id
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=winner_task_id,
            attempt=winner_attempt,
            result_category="success_learning_change_accepted",
            observed_at=winner.committed_at,
            learning_change_id=winner_change_id,
        )
    )

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        successor = session.get(KnowledgeItem, successor_id)
        winning_change = session.get(LearningChange, winner_change_id)
        losing_change = session.get(LearningChange, loser_change_id)
        assert predecessor is not None and successor is not None
        assert winning_change is not None and losing_change is not None
        assert predecessor.status == "retired"
        assert predecessor.current_learning_change_id == winner_change_id
        assert predecessor.superseded_by_id == (
            successor_id if winning_change.operation == "supersede" else None
        )
        assert knowledge_item_state(successor) == successor_before
        assert knowledge_item_content_hash(successor) == successor_hash
        assert winning_change.status == "accepted"
        assert losing_change.status == "proposed"
        assert losing_change.committed_by_task_id is None
        assert reconstruct_knowledge_item_history(
            session, predecessor
        ).learning_change_ids[-1] == winner_change_id
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == loser_task_id,
                Event.type == "learning_change_accepted",
            )
        ) == 0
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == loser_task_id
            )
        ) == 0


def test_b5_3_5_original_supersede_replays_after_successor_retirement(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False, review_interval_days=30)
    predecessor_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    successor_id = _create_active_knowledge_item(
        session_factory,
        snapshot_store,
        fixture,
        supersedes_item_id=predecessor_id,
    )
    supersede = _prepare_supersede_approval(
        session_factory,
        snapshot_store,
        fixture,
        predecessor_id,
        successor_id,
    )
    supersede_change_id, supersede_task_id, supersede_attempt, principal, _ = supersede
    commit_service = LearningCommitService(session_factory, snapshot_store)
    accepted = commit_service.decide(
        supersede_task_id, supersede_attempt, principal
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=supersede_task_id,
            attempt=supersede_attempt,
            result_category="success_learning_change_accepted",
            observed_at=accepted.committed_at,
            learning_change_id=supersede_change_id,
        )
    )

    retirement = _prepare_retirement_approval(
        session_factory, snapshot_store, fixture, successor_id
    )
    (
        retirement_change_id,
        retirement_task_id,
        retirement_attempt,
        retirement_principal,
        _,
    ) = retirement
    retired = commit_service.decide(
        retirement_task_id, retirement_attempt, retirement_principal
    )
    TaskRuntime(session_factory, snapshot_store).finalize(
        TerminalObservation(
            task_id=retirement_task_id,
            attempt=retirement_attempt,
            result_category="success_learning_change_accepted",
            observed_at=retired.committed_at,
            learning_change_id=retirement_change_id,
        )
    )

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        successor = session.get(KnowledgeItem, successor_id)
        assert predecessor is not None and successor is not None
        assert predecessor.superseded_by_id == successor_id
        assert successor.status == "retired"
        assert successor.supersedes_item_id == predecessor_id
        assert retirement_change_id in reconstruct_knowledge_item_history(
            session, successor
        ).learning_change_ids
        before_replay = _team_lifecycle_snapshot(session, fixture.team_id)

    replay = commit_service.decide(
        supersede_task_id, supersede_attempt, principal
    )
    assert replay.replayed is True
    assert replay.learning_change_id == supersede_change_id
    assert replay.knowledge_item_id == predecessor_id
    with session_factory() as session:
        assert _team_lifecycle_snapshot(session, fixture.team_id) == before_replay
        predecessor = session.get(KnowledgeItem, predecessor_id)
        successor = session.get(KnowledgeItem, successor_id)
        assert predecessor is not None and successor is not None
        assert reconstruct_knowledge_item_history(
            session, predecessor
        ).learning_change_ids[-1] == supersede_change_id
        assert retirement_change_id in reconstruct_knowledge_item_history(
            session, successor
        ).learning_change_ids


def test_b5_3_5_rejected_supersede_replay_survives_later_acceptance_and_conflicts(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False, review_interval_days=30)
    predecessor_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    successor_id = _create_active_knowledge_item(
        session_factory,
        snapshot_store,
        fixture,
        supersedes_item_id=predecessor_id,
    )
    principal = _approval_principal(
        fixture.team_id, subject=f"operator-supersede-replay-{uuid4()}"
    )
    rejected_change_id, _, _ = _prepare_supersede_assessment(
        session_factory,
        snapshot_store,
        fixture,
        predecessor_id,
        successor_id,
        principal=principal,
    )
    rejection_request = LearningChangeDecisionRequest(
        learning_change_id=rejected_change_id,
        decision="reject",
        idempotency_key=uuid4(),
        rejection_reason="The current evidence does not justify supersession.",
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    rejected = adapter.decide_learning_change(principal, rejection_request)
    assert rejected.decision == "reject"
    assert rejected.learning_change_status == "rejected"

    accepted_change_id, _, _ = _prepare_supersede_assessment(
        session_factory,
        snapshot_store,
        fixture,
        predecessor_id,
        successor_id,
        principal=principal,
    )
    acceptance = adapter.decide_learning_change(
        principal,
        LearningChangeDecisionRequest(
            learning_change_id=accepted_change_id,
            decision="accept",
            idempotency_key=uuid4(),
        ),
    )
    assert acceptance.decision == "accept"
    assert acceptance.learning_change_status == "accepted"

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        assert predecessor is not None
        assert predecessor.status == "retired"
        assert predecessor.superseded_by_id == successor_id
        before_replay = _team_lifecycle_snapshot(session, fixture.team_id)

    replay = adapter.decide_learning_change(principal, rejection_request)
    assert replay.replayed is True
    assert replay.decision == "reject"
    assert replay.learning_change_id == rejected_change_id
    with session_factory() as session:
        assert _team_lifecycle_snapshot(session, fixture.team_id) == before_replay

    with pytest.raises(
        OperatorTaskRequestConflict,
        match="idempotency_key_reused_with_different_request",
    ):
        adapter.decide_learning_change(
            principal,
            LearningChangeDecisionRequest(
                learning_change_id=accepted_change_id,
                decision="reject",
                idempotency_key=rejection_request.idempotency_key,
                rejection_reason=rejection_request.rejection_reason,
            ),
        )


def test_b5_3_5_stale_supersede_replay_preserves_disposition_after_candidate_restore(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    fixture = distillation_fixture(1, False, review_interval_days=30)
    predecessor_id = _create_active_knowledge_item(
        session_factory, snapshot_store, fixture
    )
    successor_id = _create_active_knowledge_item(
        session_factory,
        snapshot_store,
        fixture,
        supersedes_item_id=predecessor_id,
    )
    learning_change_id, principal, assessment_id = _prepare_supersede_assessment(
        session_factory,
        snapshot_store,
        fixture,
        predecessor_id,
        successor_id,
    )
    request = LearningChangeDecisionRequest(
        learning_change_id=learning_change_id,
        decision="accept",
        idempotency_key=uuid4(),
    )
    adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
    approval = adapter.request_learning_change_decision(principal, request)
    admission = TaskRuntime(session_factory, snapshot_store).admit(approval.task_id)

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        successor = session.get(KnowledgeItem, successor_id)
        change = session.get(LearningChange, learning_change_id)
        assessment = session.get(KnowledgeLifecycleAssessment, assessment_id)
        assert (
            predecessor is not None
            and successor is not None
            and change is not None
            and assessment is not None
        )
        predecessor_before = knowledge_item_state(predecessor)
        successor_before = knowledge_item_state(successor)
        original_review_after = successor.review_after
        assert original_review_after is not None
        original_change = (
            change.status,
            change.proposed_state,
            change.previous_state,
            change.committed_state,
            change.committed_by_task_id,
        )
        original_assessment_hash = assessment.payload_hash

    stale_review_after = original_review_after + timedelta(days=1)
    with session_factory.begin() as session:
        successor = session.get(KnowledgeItem, successor_id)
        assert successor is not None
        successor.review_after = stale_review_after

    stale_error: LearningCommitError | None = None
    try:
        LearningCommitService(session_factory, snapshot_store).decide(
            approval.task_id, admission.attempt_count, principal
        )
    except LearningCommitError as error:
        stale_error = error
    assert stale_error is not None
    assert str(stale_error) == "knowledge_lifecycle_successor_stale"

    runtime = TaskRuntime(session_factory, snapshot_store)
    with session_factory() as session:
        task = session.get(Task, approval.task_id)
        assert task is not None and task.status == "running"
        started_at = TaskRuntime._current_attempt_start(session, task)
        assert started_at is not None
    failed = runtime.finalize(
        TerminalObservation(
            task_id=approval.task_id,
            attempt=admission.attempt_count,
            result_category="terminal_failure",
            observed_at=started_at,
            failure_reason=str(stale_error),
        )
    )
    assert failed.status == "failed"

    with session_factory.begin() as session:
        successor = session.get(KnowledgeItem, successor_id)
        assert successor is not None
        successor.review_after = original_review_after

    with session_factory() as session:
        predecessor = session.get(KnowledgeItem, predecessor_id)
        successor = session.get(KnowledgeItem, successor_id)
        change = session.get(LearningChange, learning_change_id)
        assessment = session.get(KnowledgeLifecycleAssessment, assessment_id)
        task = session.get(Task, approval.task_id)
        assert (
            predecessor is not None
            and successor is not None
            and change is not None
            and assessment is not None
            and task is not None
        )
        assert knowledge_item_state(predecessor) == predecessor_before
        assert knowledge_item_state(successor) == successor_before
        assert (
            change.status,
            change.proposed_state,
            change.previous_state,
            change.committed_state,
            change.committed_by_task_id,
        ) == original_change
        assert assessment.payload_hash == original_assessment_hash
        assert task.status == "failed"
        assert session.scalar(
            select(func.count(Event.id)).where(
                Event.task_id == approval.task_id,
                Event.type.in_(("task_attempt_failed", "task_failed")),
            )
        ) == 2
        assert session.scalar(
            select(func.count(Outcome.id)).where(
                Outcome.recorded_by_task_id == approval.task_id
            )
        ) == 1
        before_replay = _team_lifecycle_snapshot(session, fixture.team_id)

    with pytest.raises(
        OperatorTaskRequestConflict,
        match="knowledge_lifecycle_successor_stale",
    ):
        adapter.decide_learning_change(principal, request)

    with session_factory() as session:
        assert _team_lifecycle_snapshot(session, fixture.team_id) == before_replay
