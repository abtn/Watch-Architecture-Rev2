"""R6-G integrated vertical slice from Strategy through canonical Team Experience."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from core.context_assembly import TaskContextAssembler
from core.dispatcher import TaskDispatcher
from core.evaluation_tasks import RuleEvaluationTaskRunner
from core.execution_assessment import ExecutionAssessmentBuilder
from core.experience_distiller import ExperienceDistiller
from core.generation_cost import TaskGenerationCostService
from core.knowledge_index import (
    HybridKnowledgeRetriever,
    SignalIndexer,
    TeamExperienceIndexer,
)
from core.models import (
    Evaluation,
    Event,
    EvidenceLink,
    KnowledgeChunk,
    KnowledgeItem,
    LearningChange,
    Objective,
    Outcome,
    Plan,
    PlanAction,
    Signal,
    Task,
    TaskGenerationCharge,
    Team,
    TeamExperienceChunk,
    TeamExperienceIndexState,
    TeamPolicy,
)
from core.operator_application import (
    LearningChangeDecisionRequest,
    OperatorApplicationAdapter,
    OperatorGrant,
    TrustedOperatorPrincipal,
)
from core.plans import PlanService
from core.snapshot_store import SnapshotStore
from core.source_fetch import SourceFetchError
from core.strategy import StrategyService
from core.strategy_proposer import StrategyProposer
from core.task_runtime import TaskRuntime, TerminalObservation
from tests.test_experience_distiller import _FakeDistillationProvider
from tests.test_r6b_dispatcher import FakeFetcher
from tests.test_strategy_proposer import _FakeGenerationProvider
from tests.test_team_experience import FakeEmbeddingProvider


def _strategy_candidate(
    objective_id: UUID, sources: tuple[tuple[str, str], ...]
) -> dict:
    actions = [
        {
            "id": str(uuid4()),
            "purpose": f"Ingest configured source {index + 1}.",
            "prerequisites": [],
            "task_type": "ingest_source",
            "origin_url": origin_url,
            "source_type": source_type,
            "tools": [],
        }
        for index, (origin_url, source_type) in enumerate(sources)
    ]
    return {
        "objective_id": str(objective_id),
        "approach": "Collect and compare configured source evidence.",
        "reason": "The Objective needs independently recorded source observations.",
        "visions": [
            {
                "id": str(uuid4()),
                "name": "Configured-source evidence",
                "scope": "Collect three independent configured-source observations.",
                "boundary": (
                    "Do not infer source truth or Objective achievement from ingestion."
                ),
                "workstreams": [
                    {
                        "id": str(uuid4()),
                        "name": "Source collection",
                        "purpose": "Ingest each configured source once.",
                        "actions": actions,
                    }
                ],
            }
        ],
        "constraints": {"max_tasks": 3, "max_cost_usd": 0.0},
        "stop_conditions": ["all_configured_sources_observed"],
    }


def _distillation_candidate(user_prompt: str) -> dict:
    payload = json.loads(user_prompt)
    pack = payload["evidence_pack"]
    is_v2 = pack["schema_version"] == "r6g-experience-evidence-pack-v2"
    single_case = pack["case_count"] == 1
    supporting: set[str] = set()
    contrary: set[str] = set()
    context: set[str] = set()

    for case in pack["cases"]:
        failed = case["source_task"].get("status") == "failed"
        target = contrary if failed else supporting
        target.add(case["evaluation"]["reference_id"])
        target.add(case["outcome"]["reference_id"])
        for evidence in case["evidence"]:
            stance = (
                evidence["case_relative_stance"]
                if is_v2
                else evidence["stance"]
            )
            reference = evidence["reference_id"]
            if stance == "supports":
                supporting.add(reference)
            elif stance == "challenges":
                contrary.add(reference)
            else:
                context.add(reference)

    practice = single_case
    body = (
        "One recorded configured-source observation is insufficient to establish "
        "a transferable rule. Preserve its provenance and keep this practice "
        "low-confidence until independent cases are available."
        if practice
        else (
            "Record each configured source outcome and preserve its evidence. "
            "Two successful ingestion observations support this bounded process "
            "pattern; the terminal failure remains contrary evidence. The cases "
            "do not establish source truth, relevance, causation, or Objective success."
        )
    )
    return {
        "kind": "practice" if practice else "pattern",
        "title": "Configured-source outcome verification",
        "statement": (
            "Verify terminal source-ingestion evidence before accepting a practice."
        ),
        "body": body,
        "applicability": {
            "task_class": "ingest_source",
            "situation": "A Plan-materialized Task ingests a Team-configured source.",
            "conditions": [
                "The source identity is pinned in the Plan and TeamPolicy.",
                "The Task has a terminal Outcome and recorded Evaluation.",
            ],
        },
        "preconditions": ["The source is configured in the pinned TeamPolicy."],
        "assumptions": ["The configured source identity is current."],
        "limitations": [
            "Ingestion conformance does not establish source truth or relevance."
        ],
        "non_applicability": [
            "Tasks that do not use the configured-source ingestion boundary."
        ],
        "failure_modes": [
            "A non-retryable source fetch failure prevents ingestion."
        ],
        "known_counterexamples": (
            ["A configured-source case ended in terminal failure."]
            if contrary
            else ["No counterexample was observed in the available evidence basis."]
        ),
        "missing_information": ["Long-term transfer has not been established."],
        "uncertainty": ["The cases do not establish causation."],
        "confidence": 0.2 if practice else 0.4,
        "confidence_band": "low" if practice else "moderate",
        "supporting_evidence_refs": sorted(supporting),
        "contrary_evidence_refs": sorted(contrary),
        "context_evidence_refs": sorted(context),
    }


def _task_start_time(
    session_factory: sessionmaker[Session], task_id: UUID
) -> datetime:
    with session_factory() as session:
        event = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == "task_started",
            )
        )
        assert event is not None
        return event.created_at


def _new_distillation_task(
    session_factory: sessionmaker[Session],
    team_id: UUID,
    policy_version: int,
) -> UUID:
    task_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Task(
                id=task_id,
                team_id=team_id,
                task_type="propose_learning_change",
                status="pending",
                attempt_count=0,
                policy_version=policy_version,
                allowed_writes=["LearningChange"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 1.0,
                    "deadline_seconds": 180,
                },
            )
        )
    TaskRuntime(session_factory).admit(task_id)
    return task_id


def _approval_principal(team_id: UUID) -> TrustedOperatorPrincipal:
    return TrustedOperatorPrincipal(
        issuer="https://host.e2e.example/identity",
        subject="r6g-integrated-test-operator",
        grants=frozenset(
            {OperatorGrant(team_id=team_id, action="approve_learning_change")}
        ),
    )


def test_r6g_integrated_strategy_ingestion_evaluation_and_team_experience(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
) -> None:
    embedding_provider = FakeEmbeddingProvider()
    team_id, policy_id, objective_id = (uuid4() for _ in range(3))
    baseline_url = f"https://knowledge.example.test/baseline/{uuid4()}"
    source_urls = tuple(
        (f"https://news.example.test/feed/{uuid4()}", "rss")
        for _ in range(3)
    )
    source_list = (
        {"origin_url": baseline_url, "source_type": "rss"},
        *(
            {"origin_url": origin_url, "source_type": source_type}
            for origin_url, source_type in source_urls
        ),
    )
    objective_statement = (
        "Gather scientific source evidence from configured feed monitoring."
    )
    strategy_task_id = uuid4()
    plan_task_id = uuid4()
    baseline_signal_id = uuid4()
    plan_id: UUID | None = None
    approved_item_id: UUID | None = None
    accepted_change_id: UUID | None = None
    rejected_change_id: UUID | None = None
    later_task_id: UUID | None = None
    later_objective_id: UUID | None = None

    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="science", status="active"))
        session.flush()
        session.add(
            TeamPolicy(
                id=policy_id,
                team_id=team_id,
                version=1,
                schema_version=2,
                rules={
                    "sources": list(source_list),
                    "review": {"knowledge_item_interval_days": 30},
                },
            )
        )
        session.add(
            Objective(
                id=objective_id,
                team_id=team_id,
                statement=objective_statement,
                status="active",
            )
        )
        session.flush()
        baseline_text = (
            b"Gather scientific source evidence from configured feed monitoring. "
            b"Reliable source evidence requires preserving provenance and comparing "
            b"independent observations before making a claim."
        )
        baseline_ref, baseline_hash = snapshot_store.put(baseline_text)
        session.add(
            Signal(
                id=baseline_signal_id,
                domain="science",
                source_type="rss",
                origin_url=baseline_url,
                fetched_at=datetime.now(timezone.utc),
                content_hash=baseline_hash,
                snapshot_ref=baseline_ref,
            )
        )
        session.add_all(
            [
                Task(
                    id=strategy_task_id,
                    team_id=team_id,
                    objective_id=objective_id,
                    task_type="propose_strategy",
                    status="pending",
                    attempt_count=0,
                    policy_version=1,
                    allowed_writes=[],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.5,
                        "deadline_seconds": 180,
                    },
                ),
                Task(
                    id=plan_task_id,
                    team_id=team_id,
                    objective_id=objective_id,
                    task_type="create_plan",
                    status="pending",
                    attempt_count=0,
                    policy_version=1,
                    allowed_writes=["Plan"],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.0,
                        "deadline_seconds": 60,
                    },
                ),
            ]
        )

    source_task_ids: list[UUID] = []

    try:
        SignalIndexer(
            session_factory, snapshot_store, embedding_provider
        ).index_signal(baseline_signal_id)

        retriever = HybridKnowledgeRetriever(
            session_factory, snapshot_store, embedding_provider
        )
        assembler = TaskContextAssembler(
            session_factory, snapshot_store, retriever
        )
        runtime = TaskRuntime(session_factory, snapshot_store)
        runtime.admit(strategy_task_id)
        strategy_result = StrategyProposer(
            session_factory,
            assembler,
            _FakeGenerationProvider(
                _strategy_candidate(objective_id, source_urls)
            ),
            StrategyService(session_factory),
        ).propose(strategy_task_id)
        assert strategy_result.disposition.accepted
        assert strategy_result.context.document["knowledge"]["domain_knowledge"]

        strategy_terminal = runtime.finalize(
            TerminalObservation(
                task_id=strategy_task_id,
                attempt=1,
                result_category="success_strategy_accepted",
                observed_at=_task_start_time(session_factory, strategy_task_id),
                strategy_event_id=strategy_result.disposition.event_id,
            )
        )
        assert strategy_terminal.status == "done"

        runtime.admit(plan_task_id)
        with session_factory() as session:
            strategy_event = session.get(
                Event, strategy_result.disposition.event_id
            )
            assert strategy_event is not None
            strategy_proposal_hash = strategy_event.payload["proposal_hash"]
        plan_result = PlanService(session_factory).create(
            task_id=plan_task_id,
            accepted_event_id=strategy_result.disposition.event_id,
            proposal_hash=strategy_proposal_hash,
            objective_id=objective_id,
            team_id=team_id,
        )
        plan_terminal = runtime.finalize(
            TerminalObservation(
                task_id=plan_task_id,
                attempt=1,
                result_category="success_plan_created",
                observed_at=_task_start_time(session_factory, plan_task_id),
                plan_id=plan_result.plan_id,
                plan_event_id=plan_result.event_id,
            )
        )
        assert plan_terminal.status == "done"
        plan_id = plan_result.plan_id
        assert plan_id is not None
        assert len(plan_result.task_ids) == 3
        with session_factory() as session:
            plan_actions = list(
                session.scalars(
                    select(PlanAction).where(PlanAction.plan_id == plan_id)
                )
            )
        task_by_url = {
            action.action["origin_url"]: task_id
            for action_id, task_id in zip(
                plan_result.action_ids, plan_result.task_ids, strict=True
            )
            for action in plan_actions
            if action.action_id == action_id
        }
        source_task_ids = [task_by_url[url] for url, _ in source_urls]

        unchanged_content = b"Pre-existing configured source content for no change."
        unchanged_hash = "sha256:" + hashlib.sha256(unchanged_content).hexdigest()
        unchanged_ref, stored_hash = snapshot_store.put(unchanged_content)
        assert stored_hash == unchanged_hash
        with session_factory.begin() as session:
            session.add(
                Signal(
                    id=uuid4(),
                    domain="science",
                    source_type="rss",
                    origin_url=source_urls[1][0],
                    fetched_at=datetime.now(timezone.utc),
                    content_hash=unchanged_hash,
                    snapshot_ref=unchanged_ref,
                )
            )

        fetchers = (
            FakeFetcher(b"New configured-source content with verified provenance."),
            FakeFetcher(unchanged_content),
            FakeFetcher(
                error=SourceFetchError("source_forbidden", retryable=False)
            ),
        )
        dispatch_results = []
        for task_id, fetcher in zip(source_task_ids, fetchers, strict=True):
            result = TaskDispatcher(
                session_factory, snapshot_store, fetcher
            ).dispatch(task_id)
            assert result.outcome_id is not None
            dispatch_results.append(result)
        assert [item.status for item in dispatch_results] == ["done", "done", "failed"]

        with session_factory() as session:
            request_events = list(
                session.scalars(
                    select(Event).where(
                        Event.type == "evaluation_task_requested"
                    )
                )
            )
            requested_by_source = {
                UUID(event.payload["source_task_id"]): event.task_id
                for event in request_events
                if event.payload.get("source_task_id")
                in {str(item) for item in source_task_ids}
            }
        assert set(requested_by_source) == set(source_task_ids)

        runner = RuleEvaluationTaskRunner(session_factory, snapshot_store)
        evaluations = [
            runner.run(requested_by_source[source_task_id])
            for source_task_id in source_task_ids
        ]
        assert all(item.status == "done" and item.evaluation_id for item in evaluations)
        evaluation_ids = [
            item.evaluation_id for item in evaluations if item.evaluation_id is not None
        ]
        assert len(evaluation_ids) == 3
        with session_factory() as session:
            recorded_evaluations = list(
                session.scalars(
                    select(Evaluation).where(Evaluation.id.in_(evaluation_ids))
                )
            )
        assert {item.conclusion for item in recorded_evaluations} == {
            "worked", "failed"
        }
        assert len(recorded_evaluations) == 3

        assessment_builder = ExecutionAssessmentBuilder(
            session_factory, snapshot_store
        )
        assessment_a = assessment_builder.build(plan_id)
        assessment_b = assessment_builder.build(plan_id)
        assert assessment_a.assessment_hash == assessment_b.assessment_hash
        assert assessment_a.conclusion == "failed"
        assert assessment_a.integrity == "consistent"
        with session_factory() as session:
            plan = session.get(Plan, plan_id)
            assert plan is not None and plan.status == "active"

        distillation_task_id = _new_distillation_task(
            session_factory, team_id, 1
        )
        proposal_provider = _FakeDistillationProvider(_distillation_candidate)
        distiller = ExperienceDistiller(
            session_factory,
            snapshot_store,
            proposal_provider,
            TaskGenerationCostService(session_factory),
        )
        accepted_proposal = distiller.propose(
            distillation_task_id, [item for item in evaluation_ids if item is not None]
        )
        accepted_change_id = accepted_proposal.learning_change_id
        assert accepted_change_id is not None
        proposal_terminal = runtime.finalize(
            TerminalObservation(
                task_id=distillation_task_id,
                attempt=1,
                result_category="success_learning_change_proposed",
                observed_at=_task_start_time(session_factory, distillation_task_id),
                learning_change_id=accepted_change_id,
            )
        )
        assert proposal_terminal.status == "done"

        single_case_task_id = _new_distillation_task(
            session_factory, team_id, 1
        )
        low_provider = _FakeDistillationProvider(_distillation_candidate)
        low_result = ExperienceDistiller(
            session_factory,
            snapshot_store,
            low_provider,
            TaskGenerationCostService(session_factory),
        ).propose(single_case_task_id, [evaluation_ids[0]])
        rejected_change_id = low_result.learning_change_id
        assert rejected_change_id is not None
        low_terminal = runtime.finalize(
            TerminalObservation(
                task_id=single_case_task_id,
                attempt=1,
                result_category="success_learning_change_proposed",
                observed_at=_task_start_time(session_factory, single_case_task_id),
                learning_change_id=rejected_change_id,
            )
        )
        assert low_terminal.status == "done"

        operator = OperatorApplicationAdapter(session_factory, snapshot_store)
        principal = _approval_principal(team_id)
        rejected = operator.decide_learning_change(
            principal,
            LearningChangeDecisionRequest(
                learning_change_id=rejected_change_id,
                decision="reject",
                idempotency_key=uuid4(),
                rejection_reason=(
                    "Single-case evidence remains low-confidence practice."
                ),
            ),
        )
        assert rejected.learning_change_status == "rejected"
        assert rejected.knowledge_item_id is None

        accepted = operator.decide_learning_change(
            principal,
            LearningChangeDecisionRequest(
                learning_change_id=accepted_change_id,
                decision="accept",
                idempotency_key=uuid4(),
            ),
        )
        assert accepted.learning_change_status == "accepted"
        assert accepted.knowledge_item_id is not None
        approved_item_id = accepted.knowledge_item_id
        assert approved_item_id is not None

        with session_factory() as session:
            low_change = session.get(LearningChange, rejected_change_id)
            assert low_change is not None
            assert low_change.status == "rejected"
            assert session.scalar(
                select(KnowledgeItem.id).where(
                    KnowledgeItem.origin_learning_change_id == rejected_change_id
                )
            ) is None
            item = session.get(KnowledgeItem, approved_item_id)
            assert item is not None
            assert item.origin_learning_change_id == accepted_change_id
            assert item.status == "active"

        indexer = TeamExperienceIndexer(session_factory, embedding_provider)
        indexed = indexer.index_knowledge_item(
            approved_item_id, now=datetime.now(timezone.utc)
        )
        assert indexed.outcome == "indexed"
        replayed_index = indexer.index_knowledge_item(
            approved_item_id, now=datetime.now(timezone.utc)
        )
        assert replayed_index.outcome == "unchanged"

        later_objective_id, later_task_id = uuid4(), uuid4()
        later_objective_statement = "Configured source outcome verification."
        with session_factory.begin() as session:
            session.add(
                Objective(
                    id=later_objective_id,
                    team_id=team_id,
                    statement=later_objective_statement,
                    status="active",
                )
            )
            session.flush()
            session.add(
                Task(
                    id=later_task_id,
                    team_id=team_id,
                    objective_id=later_objective_id,
                    task_type="propose_strategy",
                    status="pending",
                    attempt_count=0,
                    policy_version=1,
                    allowed_writes=[],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.5,
                        "deadline_seconds": 180,
                    },
                )
            )
        runtime.admit(later_task_id)
        later_context = TaskContextAssembler(
            session_factory,
            snapshot_store,
            HybridKnowledgeRetriever(
                session_factory, snapshot_store, embedding_provider
            ),
        ).assemble(later_task_id)
        selected_experience = later_context.document["knowledge"]["team_experience"]
        assert any(
            item["knowledge_item_id"] == str(approved_item_id)
            and item["knowledge_item_version"] == 1
            for item in selected_experience
        )
        assert any(
            item["logical_core"] == "team_experience"
            and item["origin_learning_change_id"] == str(accepted_change_id)
            for item in later_context.manifest["selected"]
        )

    finally:
        with session_factory.begin() as session:
            team_task_ids = list(
                session.scalars(select(Task.id).where(Task.team_id == team_id))
            )
            task_id_set = set(team_task_ids)
            plan_ids = list(
                session.scalars(select(Plan.id).where(Plan.team_id == team_id))
            )
            signal_ids = list(
                session.scalars(
                    select(Signal.id).where(
                        Signal.origin_url.in_(
                            [baseline_url, *(url for url, _ in source_urls)]
                        )
                    )
                )
            )

            session.execute(
                delete(EvidenceLink).where(EvidenceLink.team_id == team_id)
            )
            session.execute(
                delete(TeamExperienceChunk).where(
                    TeamExperienceChunk.team_id == team_id
                )
            )
            session.execute(
                delete(TeamExperienceIndexState).where(
                    TeamExperienceIndexState.team_id == team_id
                )
            )
            session.execute(
                delete(KnowledgeItem).where(KnowledgeItem.team_id == team_id)
            )
            session.execute(
                delete(LearningChange).where(LearningChange.team_id == team_id)
            )
            session.execute(
                delete(Evaluation).where(Evaluation.team_id == team_id)
            )
            session.execute(
                delete(TaskGenerationCharge).where(
                    TaskGenerationCharge.task_id.in_(task_id_set)
                )
            )
            session.execute(
                delete(Outcome).where(Outcome.recorded_by_task_id.in_(task_id_set))
            )

            if plan_ids:
                plan_task_ids = list(
                    session.scalars(
                        select(Task.id).where(Task.plan_id.in_(plan_ids))
                    )
                )
                if plan_task_ids:
                    session.execute(
                        delete(Event).where(Event.task_id.in_(plan_task_ids))
                    )
                    session.execute(
                        delete(Task).where(Task.id.in_(plan_task_ids))
                    )
                session.execute(
                    delete(PlanAction).where(PlanAction.plan_id.in_(plan_ids))
                )
                session.execute(delete(Plan).where(Plan.id.in_(plan_ids)))

            session.execute(delete(Event).where(Event.task_id.in_(task_id_set)))
            session.execute(delete(Task).where(Task.id.in_(task_id_set)))
            session.execute(
                delete(Objective).where(Objective.team_id == team_id)
            )
            if signal_ids:
                session.execute(
                    delete(KnowledgeChunk).where(
                        KnowledgeChunk.signal_id.in_(signal_ids)
                    )
                )
                session.execute(delete(Signal).where(Signal.id.in_(signal_ids)))
            session.execute(
                delete(TeamPolicy).where(TeamPolicy.team_id == team_id)
            )
            session.execute(delete(Team).where(Team.id == team_id))
