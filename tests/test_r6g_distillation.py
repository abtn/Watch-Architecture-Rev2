"""R6-G v2 distillation packs preserve failed-source cases as contrary evidence."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from core.dispatcher import TaskDispatcher
from core.evaluation_tasks import RuleEvaluationTaskRunner
from core.experience_distiller import (
    DistillationApplicability,
    DistilledExperienceDraft,
    ExperienceDistiller,
    ExperienceDistillerError,
)
from core.models import (
    Evaluation,
    Event,
    EvidenceLink,
    Outcome,
    PlanAction,
    Signal,
    Task,
    TeamPolicy,
)
from core.snapshot_store import SnapshotStore
from core.source_fetch import SourceFetchError
from tests.test_r6b_dispatcher import DispatchFixture, FakeFetcher

pytest_plugins = ["tests.test_r6b_dispatcher"]


def _add_configured_action(
    session_factory: sessionmaker[Session],
    fixture: DispatchFixture,
    *,
    origin_url: str,
) -> tuple[UUID, UUID]:
    action_id, task_id = uuid4(), uuid4()
    with session_factory.begin() as session:
        policy = session.get(TeamPolicy, fixture.policy_id)
        assert policy is not None
        rules = dict(policy.rules)
        sources = list(rules["sources"])
        sources.append({"origin_url": origin_url, "source_type": "rss"})
        rules["sources"] = sources
        policy.rules = rules
        session.add(
            PlanAction(
                plan_id=fixture.plan_id,
                action_id=action_id,
                action={
                    "id": str(action_id),
                    "purpose": "poll an additional configured source",
                    "prerequisites": [],
                    "task_type": "ingest_source",
                    "origin_url": origin_url,
                    "source_type": "rss",
                    "tools": [],
                },
            )
        )
        session.flush()
        session.add(
            Task(
                id=task_id,
                team_id=fixture.team_id,
                objective_id=fixture.objective_id,
                plan_id=fixture.plan_id,
                plan_action_id=action_id,
                task_type="ingest_source",
                status="pending",
                policy_version=1,
                allowed_writes=["Signal"],
                budget={
                    "max_tool_calls": 0,
                    "max_cost_usd": 0.0,
                    "deadline_seconds": 60,
                },
                max_attempts=3,
            )
        )
    return action_id, task_id


def _evaluation_requests(
    session_factory: sessionmaker[Session],
    source_task_ids: list[UUID],
) -> dict[UUID, UUID]:
    with session_factory() as session:
        found: dict[UUID, UUID] = {}
        for event in session.scalars(
            select(Event).where(Event.type == "evaluation_task_requested")
        ):
            source_id = UUID(event.payload["source_task_id"])
            if source_id in source_task_ids:
                assert source_id not in found
                found[source_id] = event.task_id
        assert set(found) == set(source_task_ids)
        return found


def _valid_v2_candidate(
    pack,
) -> DistilledExperienceDraft:
    supporting: set[str] = set()
    contrary: set[str] = set()
    context: set[str] = set()
    for case in pack.document["cases"]:
        failed = case["source_task"]["status"] == "failed"
        target = contrary if failed else supporting
        target.add(case["evaluation"]["reference_id"])
        target.add(case["outcome"]["reference_id"])
        for evidence in case["evidence"]:
            stance = evidence["case_relative_stance"]
            ref = evidence["reference_id"]
            if stance == "supports":
                supporting.add(ref)
            elif stance == "challenges":
                contrary.add(ref)
            else:
                context.add(ref)

    return DistilledExperienceDraft(
        kind="pattern",
        title="A bounded configured-source practice",
        statement="Preserve terminal evidence before inferring a result.",
        body=(
            "The observed source-ingestion successes support a narrow process "
            "pattern. The terminal failure remains contrary evidence and limits "
            "the claim; no causal or Objective-level conclusion is drawn."
        ),
        applicability=DistillationApplicability(
            task_class="ingest_source",
            situation="A configured source is fetched and committed as an Outcome.",
            conditions=["The source is configured in the pinned TeamPolicy."],
        ),
        preconditions=["A terminal Task Outcome and Evaluation are recorded."],
        assumptions=["The configured source identity is current."],
        limitations=["The evidence does not establish source truth or relevance."],
        non_applicability=["Tasks without a validated configured-source boundary."],
        failure_modes=["A non-retryable fetch failure prevents ingestion."],
        known_counterexamples=["One configured-source case ended in terminal failure."],
        missing_information=["Long-term transfer has not been established."],
        uncertainty=["The evidence does not establish causation."],
        confidence=0.4,
        confidence_band="moderate",
        supporting_evidence_refs=sorted(supporting),
        contrary_evidence_refs=sorted(contrary),
        context_evidence_refs=sorted(context),
    )


def test_failed_source_case_uses_v2_without_mutating_canonical_evidence(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
    dispatch_fixture: DispatchFixture,
) -> None:
    origin_b = f"https://news.example.test/feed/{uuid4()}"
    origin_c = f"https://news.example.test/feed/{uuid4()}"
    action_b, task_b = _add_configured_action(
        session_factory, dispatch_fixture, origin_url=origin_b
    )
    action_c, task_c = _add_configured_action(
        session_factory, dispatch_fixture, origin_url=origin_c
    )
    distillation_task_id = uuid4()
    with session_factory.begin() as session:
        session.add(
            Task(
                id=distillation_task_id,
                team_id=dispatch_fixture.team_id,
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

    content_b = b"Pre-existing content for the unchanged source."
    content_hash_b = "sha256:" + hashlib.sha256(content_b).hexdigest()
    snapshot_ref_b, stored_hash_b = snapshot_store.put(content_b)
    assert stored_hash_b == content_hash_b
    with session_factory.begin() as session:
        session.add(
            Signal(
                id=uuid4(),
                domain="r6b_test",
                source_type="rss",
                origin_url=origin_b,
                fetched_at=datetime.now(timezone.utc),
                content_hash=content_hash_b,
                snapshot_ref=snapshot_ref_b,
            )
        )

    source_task_ids = [dispatch_fixture.task_id, task_b, task_c]
    extra_evaluation_task_ids: list[UUID] = []
    try:
        cases = [
            (
                dispatch_fixture.task_id,
                FakeFetcher(),
            ),
            (
                task_b,
                FakeFetcher(content_b),
            ),
            (
                task_c,
                FakeFetcher(
                    error=SourceFetchError(
                        "source_forbidden", retryable=False
                    )
                ),
            ),
        ]
        for source_task_id, fetcher in cases:
            result = TaskDispatcher(
                session_factory, snapshot_store, fetcher
            ).dispatch(source_task_id)
            assert result.outcome_id is not None

        requests = _evaluation_requests(session_factory, source_task_ids)
        extra_evaluation_task_ids = list(requests.values())
        runner = RuleEvaluationTaskRunner(session_factory, snapshot_store)
        evaluation_ids: list[UUID] = []
        for source_task_id in source_task_ids:
            run = runner.run(requests[source_task_id])
            assert run.status == "done"
            assert run.evaluation_id is not None
            evaluation_ids.append(run.evaluation_id)

        distiller = ExperienceDistiller(session_factory, snapshot_store)
        pack = distiller.build_evidence_pack(
            distillation_task_id, evaluation_ids
        )
        replay = distiller.build_evidence_pack(
            distillation_task_id, list(reversed(evaluation_ids))
        )

        assert pack.document["schema_version"] == "r6g-experience-evidence-pack-v2"
        assert pack.case_count == 3
        assert pack.basis_hash == replay.basis_hash
        assert pack.document == replay.document

        failed_case = next(
            case
            for case in pack.document["cases"]
            if case["source_task"]["status"] == "failed"
        )
        assert failed_case["source_task"]["failure_reason"] == "source_forbidden"
        assert failed_case["outcome"]["observation"]["failure_reason"] == (
            "source_forbidden"
        )
        assert failed_case["evaluation"]["conclusion"] == "failed"
        assert len(failed_case["evidence"]) == 1
        assert failed_case["evidence"][0]["stance"] == "supports"
        assert failed_case["evidence"][0]["case_relative_stance"] == "challenges"
        assert (
            failed_case["evidence"][0]["reference_id"]
            in pack.contrary_reference_ids
        )

        for successful_case in (
            case
            for case in pack.document["cases"]
            if case["source_task"]["status"] == "done"
        ):
            assert successful_case["evaluation"]["conclusion"] == "worked"
            assert all(
                evidence["case_relative_stance"] == evidence["stance"]
                for evidence in successful_case["evidence"]
            )

        candidate = _valid_v2_candidate(pack)
        ExperienceDistiller._validate_references(candidate, pack)

        invalid_candidate = candidate.model_copy(
            update={
                "supporting_evidence_refs": sorted(
                    set(candidate.supporting_evidence_refs)
                    | set(candidate.contrary_evidence_refs)
                ),
                "contrary_evidence_refs": [],
            }
        )
        with pytest.raises(
            ExperienceDistillerError, match="contrary_evidence_not_preserved"
        ):
            ExperienceDistiller._validate_references(invalid_candidate, pack)

        with session_factory() as session:
            failed_evaluation_id = UUID(
                failed_case["evaluation"]["reference_id"].removeprefix(
                    "evaluation:"
                )
            )
            canonical_links = list(
                session.scalars(
                    select(EvidenceLink).where(
                        EvidenceLink.subject_kind == "evaluation",
                        EvidenceLink.subject_id == failed_evaluation_id,
                    )
                )
            )
            assert len(canonical_links) == 1
            assert canonical_links[0].stance == "supports"
    finally:
        with session_factory.begin() as session:
            evaluator_ids = list(extra_evaluation_task_ids)
            evaluator_ids.extend(
                [
                    event.task_id
                    for event in session.scalars(
                        select(Event).where(
                            Event.type == "evaluation_task_requested"
                        )
                    )
                    if event.payload.get("source_task_id")
                    == str(dispatch_fixture.task_id)
                ]
            )
            evaluator_ids = list(set(evaluator_ids))
            evaluation_ids_to_delete = (
                list(
                    session.scalars(
                        select(Evaluation.id).where(
                            Evaluation.created_by_task_id.in_(evaluator_ids)
                        )
                    )
                )
                if evaluator_ids
                else []
            )
            if evaluation_ids_to_delete:
                session.execute(
                    delete(EvidenceLink).where(
                        EvidenceLink.subject_kind == "evaluation",
                        EvidenceLink.subject_id.in_(evaluation_ids_to_delete),
                    )
                )
                session.execute(
                    delete(Evaluation).where(
                        Evaluation.id.in_(evaluation_ids_to_delete)
                    )
                )
            cleanup_task_ids = [
                *evaluator_ids,
                task_b,
                task_c,
                distillation_task_id,
            ]
            if cleanup_task_ids:
                session.execute(
                    delete(Outcome).where(
                        Outcome.recorded_by_task_id.in_(cleanup_task_ids)
                    )
                )
                session.execute(
                    delete(Event).where(Event.task_id.in_(cleanup_task_ids))
                )
                session.execute(
                    delete(Task).where(Task.id.in_(cleanup_task_ids))
                )
            session.execute(
                delete(PlanAction).where(
                    PlanAction.plan_id == dispatch_fixture.plan_id,
                    PlanAction.action_id.in_([action_b, action_c]),
                )
            )
            session.execute(
                delete(Signal).where(
                    Signal.origin_url.in_([origin_b, origin_c])
                )
            )
