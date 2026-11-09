"""R6-F Checkpoint 2: bounded distillation and proposed LearningChange."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
from typing import Any, Callable, Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from core.evaluations import (
    EvaluationDraft,
    EvaluationEvidence,
    EvaluationFindings,
    EvaluationService,
)
from core.experience_distiller import (
    EXPERIENCE_DISTILLATION_OPERATION,
    ExperienceDistiller,
    ExperienceDistillerError,
)
from core.generation import (
    GenerationCostQuote,
    GenerationResult,
    GenerationUsage,
)
from core.generation_cost import TaskGenerationCostService
from core.knowledge_quality import (
    DIMENSIONS as KNOWLEDGE_QUALITY_DIMENSIONS,
)
from core.knowledge_quality import (
    RUBRIC_IDENTITY,
    RUBRIC_REVISION,
    KnowledgeQualityAssessmentDraft,
    KnowledgeQualityAssessmentService,
    KnowledgeQualityDimension,
    build_case_lineage_report,
)
from core.knowledge_quality_tasks import KnowledgeQualityAssessmentTaskRunner
from core.knowledge_revalidation import (
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
)
from core.learning_history import encode_state_snapshot, knowledge_item_state
from core.models import (
    Evaluation,
    Event,
    EvidenceLink,
    KnowledgeItem,
    KnowledgeQualityAssessment,
    KnowledgeRevalidationAssessment,
    LearningChange,
    Outcome,
    Task,
    TaskGenerationCharge,
    Team,
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


@pytest.fixture
def distillation_fixture(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
) -> Iterator[Callable[[int, bool], _Fixture]]:
    created: list[_Fixture] = []

    def build(
        case_count: int = 1,
        include_contrary: bool = False,
        include_mention: bool = False,
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
                    rules={"unchanged": True},
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
                proposal_owner = (
                    LearningChange.proposed_by_task_id
                    == fixture.distillation_task_id
                )
                approval_commit = LearningChange.committed_by_task_id.in_(
                    approval_task_ids
                )
                learning_change_ids = select(LearningChange.id).where(
                    proposal_owner | approval_commit
                )
                session.execute(
                    delete(KnowledgeItem).where(
                        KnowledgeItem.origin_learning_change_id.in_(learning_change_ids)
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
        assert team_policy is not None and team_policy.rules == {"unchanged": True}
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
    if decision == "accept":
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
        session_factory
    ).request_learning_change_decision(_approval_principal(team_id), request)
    admission = TaskRuntime(session_factory).admit(result.task_id)
    return result.task_id, admission.attempt_count, _approval_principal(team_id)






class _FakeKnowledgeRevalidationProvider:
    evaluator_identity = "r7b-revalidation-test"
    evaluator_revision = "1"

    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls = 0
        self.fail_first = fail_first

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
        return KnowledgeRevalidationAssessmentDraft(
            freshness_disposition="current",
            findings=(
                KnowledgeRevalidationFinding(
                    code="supports_revalidation",
                    summary="The rebuilt evidence basis remains relevant.",
                    evidence_refs=tuple(sorted(allowed_evidence_references)),
                ),
            ),
        )


def _create_revalidation_proposal(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    fixture: _Fixture,
    knowledge_item_id: UUID,
) -> tuple[UUID, UUID]:
    source_task_id, learning_change_id = uuid4(), uuid4()
    started_at = datetime.now(timezone.utc)
    completed_at = started_at + timedelta(seconds=2)
    proposal_hash = "sha256:" + ("c" * 64)
    observation_ref, observation_hash = snapshot_store.put(
        (
            '{"attempt":1,"learning_change_id":"'
            + str(learning_change_id)
            + '","result_category":"success_learning_change_proposed"}'
        ).encode("utf-8")
    )
    proposed_state = {
        "proposal_hash": proposal_hash,
        "evidence_basis_hash": None,
        "operator_rationale": rationale,
    }

    with session_factory.begin() as session:
        team = session.get(Team, fixture.team_id)
        item = session.get(KnowledgeItem, knowledge_item_id)
        assert team is not None and item is not None
        assert item.team_id == fixture.team_id
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
        proposed_state["evidence_basis_hash"] = pack.basis_hash
        proposed_state_hash = _domain_hash(
            PROPOSED_STATE_HASH_DOMAIN, _normalize_json(proposed_state)
        )
        change = LearningChange(
            id=learning_change_id,
            team_id=fixture.team_id,
            target_kind="knowledge_item",
            target_id=item.id,
            operation="revalidate",
            proposed_state={
                "proposal_hash": proposal_hash,
                "evidence_basis_hash": pack.basis_hash,
            },
            previous_state=encode_state_snapshot(previous_state),
            committed_state=None,
            evidence_basis=pack.evidence_basis,
            evidence_basis_hash=pack.basis_hash,
            status="proposed",
            idempotency_key=f"r7b-revalidation-test-{learning_change_id}",
            proposed_by_task_id=source_task_id,
            created_at=started_at,
        )
        session.add(change)
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
                        "operation": "revalidate",
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
    return source_task_id, learning_change_id


@pytest.mark.parametrize(
    ("crash_after_record", "fail_first_attempt"),
    [(False, False), (True, False), (False, True)],
)
def test_revalidation_task_records_once_and_recovers_without_canonical_writes(
    session_factory,
    snapshot_store,
    distillation_fixture,
    crash_after_record: bool,
    fail_first_attempt: bool,
):
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
        fail_first=fail_first_attempt
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
            KnowledgeRevalidationAssessmentDraft(
                freshness_disposition="current",
                findings=(
                    KnowledgeRevalidationFinding(
                        code="supports_revalidation",
                        summary="The rebuilt evidence basis remains relevant.",
                        evidence_refs=tuple(sorted(context.pack.reference_ids)),
                    ),
                ),
            ),
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
    else:
        first = runner.run(task_id)
        assert first.status == "done"
        assert first.assessment_id is not None

    assert revalidation_service.create_task(revalidation_change_id) == task_id
    replay = runner.run(task_id)
    assert replay.status == "done"
    assert replay.replayed
    assert replay.assessment_id is not None
    assert provider.calls == (2 if fail_first_attempt else 1)

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
        assert assessment.assessment_result == "supported"
        assert assessment.task_attempt == (2 if fail_first_attempt else 1)
        assert session.scalar(
            select(func.count(KnowledgeRevalidationAssessment.id)).where(
                KnowledgeRevalidationAssessment.learning_change_id
                == revalidation_change_id
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


def test_lifecycle_retire_assessment_records_once_without_canonical_writes(
    session_factory,
    snapshot_store,
    distillation_fixture,
):
    from core.knowledge_lifecycle import (
        PROPOSED_STATE_HASH_DOMAIN,
        _domain_hash,
        _normalize_json,
        require_recorded_assessment,
    )
    from core.knowledge_lifecycle_tasks import KnowledgeLifecycleAssessmentTask
    from core.models import (
        KnowledgeLifecycleAssessment,
        LearningChangeOperatorProvenance,
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

    task_adapter = KnowledgeLifecycleAssessmentTask(
        session_factory, snapshot_store
    )
    task_id = task_adapter.create(learning_change_id)
    assert task_adapter.create(learning_change_id) == task_id
    task_adapter.validate(task_id)
    admission = TaskRuntime(session_factory, snapshot_store).admit(task_id)
    assert admission.attempt_count == 1

    first = task_adapter.record(task_id)
    assert first.assessment_result == "eligible"
    assert not first.replayed
    replay = task_adapter.record(task_id)
    assert replay.replayed
    assert replay.assessment_id == first.assessment_id
    assert replay.assessment_payload_hash == first.assessment_payload_hash

    with session_factory() as session:
        item = session.get(KnowledgeItem, committed.knowledge_item_id)
        change = session.get(LearningChange, learning_change_id)
        task = session.get(Task, task_id)
        assessment = session.get(
            KnowledgeLifecycleAssessment, first.assessment_id
        )
        assert item is not None and change is not None and task is not None
        assert assessment is not None
        assert task.status == "running"
        assert task.allowed_writes == ["KnowledgeLifecycleAssessment"]
        assert change.status == "proposed"
        assert change.committed_by_task_id is None
        assert item.current_learning_change_id == committed.learning_change_id
        assert item.version == 1
        assert assessment.operation == "retire"
        assert assessment.assessment_result == "eligible"
        assert assessment.variant_payload == {}
        assert assessment.successor_knowledge_item_id is None
        assert assessment.payload_hash == first.assessment_payload_hash
        verified = require_recorded_assessment(
            session,
            change,
            snapshot_store,
            session_factory,
            require_task_done=False,
            require_current=True,
        )
        assert verified.id == assessment.id
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
            delete(Event).where(Event.task_id.in_([source_task_id, task_id]))
        )
        session.execute(
            delete(Outcome).where(
                Outcome.recorded_by_task_id == source_task_id
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
