"""R6-F Checkpoint 1: Evaluation evidence, disposition, and Task finalization."""

from datetime import datetime, timezone
from typing import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from core.evaluations import (
    EvaluationDraft,
    EvaluationEvidence,
    EvaluationFindings,
    EvaluationService,
    EvaluationValidationError,
)
from core.models import (
    Evaluation,
    Event,
    EvidenceLink,
    Outcome,
    Signal,
    Task,
    Team,
    TeamPolicy,
)
from core.snapshot_store import SnapshotStore
from core.task_runtime import TaskNotFinalizable, TaskRuntime, TerminalObservation


@pytest.fixture
def evaluation_context(session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore) -> Iterator[dict[str, object]]:
    team_id, policy_id, source_task_id, eval_task_id = (uuid4() for _ in range(4))
    content = b"Observed: evidence passage."
    snapshot_ref, snapshot_hash = snapshot_store.put(content)
    outcome_id = uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="evaluation_test", status="active"))
        session.flush()
        session.add(TeamPolicy(id=policy_id, team_id=team_id, version=1, rules={}))
        session.flush()
        session.add_all([
            Task(id=source_task_id, team_id=team_id, task_type="ingest_source",
                status="done",
                 attempt_count=1, policy_version=1, allowed_writes=["Signal"],
                 budget={"max_tool_calls": 0, "max_cost_usd": 0.0,
                     "deadline_seconds": 60}),
            Task(id=eval_task_id, team_id=team_id, task_type="evaluate_outcome",
                status="running",
                 attempt_count=1, policy_version=1, allowed_writes=["Evaluation",
                     "EvidenceLink"],
                 budget={"max_tool_calls": 0, "max_cost_usd": 0.0,
                     "deadline_seconds": 60}),
        ])
        session.flush()
        session.add(Outcome(
            id=outcome_id, team_id=team_id, subject_kind="task",
                subject_id=source_task_id,
            outcome_type="task_execution", expected=None,
                observation_snapshot_ref=snapshot_ref,
            observation_hash=snapshot_hash, observed_at=datetime.now(timezone.utc),
            recorded_by_task_id=source_task_id,
        ))
    try:
        yield {"team_id": team_id, "source_task_id": source_task_id,
            "task_id": eval_task_id,
               "outcome_id": outcome_id, "content": content}
    finally:
        with session_factory.begin() as session:
            session.execute(delete(EvidenceLink).where(EvidenceLink.subject_id.in_(
                select(Evaluation.id).where(Evaluation.created_by_task_id == eval_task_id))))  # noqa: E501
            session.execute(delete(Evaluation).where(Evaluation.created_by_task_id == eval_task_id))  # noqa: E501
            session.execute(delete(Outcome).where(Outcome.recorded_by_task_id.in_([source_task_id, eval_task_id])))  # noqa: E501
            session.execute(delete(Event).where(Event.task_id.in_([source_task_id,
                eval_task_id])))
            session.execute(delete(Task).where(Task.id.in_([source_task_id,
                eval_task_id])))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


def _draft(context: dict[str, object], **updates: object) -> EvaluationDraft:
    content = context["content"]
    assert isinstance(content, bytes)
    decoded = content.decode("utf-8")
    quote = "evidence passage"
    start = decoded.index(quote)
    values: dict[str, object] = {
        "outcome_id": context["outcome_id"], "conclusion": "worked",
        "findings": EvaluationFindings(
            observed_result="The source was captured.",
                intended_result="A durable observation was expected.",
            method_or_process="Configured source ingestion.",
                context=["Deterministic fixture."],
            alternative_explanations=["The source may have changed independently."],
            attribution="not established",
                uncertainty=["One case does not prove transfer."],
        ),
        "evidence": [EvaluationEvidence(
            source_kind="outcome", outcome_id=context["outcome_id"], stance="supports",
            quote_text=quote, quote_start=start, quote_end=start + len(quote),
        )],
        "idempotency_key": "evaluation-checkpoint-1",
    }
    values.update(updates)
    return EvaluationDraft(**values)


def _propose(service: EvaluationService, context: dict[str, object],
    draft: EvaluationDraft | None = None):
    return service.propose(context["task_id"], draft or _draft(context),
        # type: ignore[arg-type]
        evaluator_kind="rule", evaluator_identity="r6f-checkpoint-1-tests",
            evaluator_revision="1")


def test_evaluation_propose_record_and_replay(session_factory, snapshot_store,
    evaluation_context):
    service = EvaluationService(session_factory, snapshot_store)
    proposed = _propose(service, evaluation_context)
    assert proposed.status == "proposed"
    replay = _propose(service, evaluation_context)
    assert replay.evaluation_id == proposed.evaluation_id and replay.replayed
    assert service.record(evaluation_context["task_id"],
        proposed.evaluation_id).status == "recorded"  # type: ignore[arg-type]
    assert service.record(evaluation_context["task_id"],
        proposed.evaluation_id).replayed  # type: ignore[arg-type]
    with session_factory() as session:
        row = session.get(Evaluation, proposed.evaluation_id)
        assert row is not None and row.status == "recorded"
        assert row.evaluator_identity == "r6f-checkpoint-1-tests" and row.evaluator_revision == "1"  # noqa: E501
        assert len(list(session.scalars(select(EvidenceLink).where(EvidenceLink.subject_id == proposed.evaluation_id)))) == 1  # noqa: E501
        events = set(session.scalars(select(Event.type).where(Event.task_id == evaluation_context["task_id"])))  # noqa: E501
        assert {"evaluation_proposed", "evaluation_recorded"} <= events


def test_recorded_evaluation_finalizes_via_task_runtime(session_factory,
    snapshot_store, evaluation_context):
    service = EvaluationService(session_factory, snapshot_store)
    proposed = _propose(service, evaluation_context)
    service.record(evaluation_context["task_id"],
        proposed.evaluation_id)  # type: ignore[arg-type]
    observation = TerminalObservation(
        task_id=evaluation_context["task_id"], attempt=1,
            result_category="success_evaluation_recorded",
        observed_at=datetime.now(timezone.utc), evaluation_id=proposed.evaluation_id,
    )
    runtime = TaskRuntime(session_factory, snapshot_store)
    assert runtime.finalize(observation).status == "done"
    assert runtime.finalize(observation).replayed


def test_rejected_evaluation_finalizes_as_review_disposition(session_factory,
    snapshot_store, evaluation_context):
    service = EvaluationService(session_factory, snapshot_store)
    proposed = _propose(service, evaluation_context)
    service.reject(evaluation_context["task_id"], proposed.evaluation_id,
        reason="Insufficient support.")  # type: ignore[arg-type]
    result = TaskRuntime(session_factory, snapshot_store).finalize(TerminalObservation(
        task_id=evaluation_context["task_id"], attempt=1,
            result_category="success_evaluation_rejected",
        observed_at=datetime.now(timezone.utc), evaluation_id=proposed.evaluation_id,
    ))
    assert result.status == "done"


def test_unrecorded_evaluation_cannot_finalize(session_factory, snapshot_store,
    evaluation_context):
    proposed = _propose(EvaluationService(session_factory, snapshot_store),
        evaluation_context)
    with pytest.raises(TaskNotFinalizable, match="evaluation_not_recorded"):
        TaskRuntime(session_factory, snapshot_store).finalize(TerminalObservation(
            task_id=evaluation_context["task_id"], attempt=1,
                result_category="success_evaluation_recorded",
            observed_at=datetime.now(timezone.utc),
                evaluation_id=proposed.evaluation_id,
        ))
    with session_factory() as session:
        task = session.get(Task, evaluation_context["task_id"])
        assert task is not None and task.status == "running"


def test_invalid_quote_creates_no_evaluation(session_factory, snapshot_store,
    evaluation_context):
    draft = _draft(evaluation_context)
    bad_evidence = draft.evidence[0].model_copy(update={"quote_text": "fabricated"})
    invalid = draft.model_copy(update={"evidence": [bad_evidence]})
    with pytest.raises(EvaluationValidationError, match="quote_text_offset_mismatch"):
        _propose(EvaluationService(session_factory, snapshot_store),
            evaluation_context, invalid)
    with session_factory() as session:
        assert session.scalar(select(Evaluation.id)) is None


def test_cross_team_outcome_reference_is_rejected(session_factory, snapshot_store,
    evaluation_context):
    team_id, policy_id, task_id = (uuid4() for _ in range(3))
    ref, digest = snapshot_store.put(b"Other Team evidence")
    outcome_id = uuid4()
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain="other", status="active"))
        session.flush()
        session.add(TeamPolicy(id=policy_id, team_id=team_id, version=1, rules={}))
        session.flush()
        session.add(Task(id=task_id, team_id=team_id, task_type="ingest_source",
            status="done",
            attempt_count=1, policy_version=1, allowed_writes=["Signal"],
            budget={"max_tool_calls": 0, "max_cost_usd": 0.0, "deadline_seconds": 60}))
        session.flush()
        session.add(Outcome(id=outcome_id, team_id=team_id, subject_kind="task",
            subject_id=task_id,
            outcome_type="task_execution", expected=None, observation_snapshot_ref=ref,
            observation_hash=digest, observed_at=datetime.now(timezone.utc),
                recorded_by_task_id=task_id))
    invalid = _draft(evaluation_context, evidence=[
        *_draft(evaluation_context).evidence,
        EvaluationEvidence(source_kind="outcome", outcome_id=outcome_id,
            stance="challenges"),
    ])
    try:
        with pytest.raises(EvaluationValidationError,
            match="evidence_outcome_team_mismatch"):
            _propose(EvaluationService(session_factory, snapshot_store),
                evaluation_context, invalid)
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Outcome).where(Outcome.recorded_by_task_id == task_id))  # noqa: E501
            session.execute(delete(Task).where(Task.id == task_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.id == policy_id))
            session.execute(delete(Team).where(Team.id == team_id))


def test_evaluation_write_scopes_are_enforced(session_factory, snapshot_store,
    evaluation_context):
    with session_factory.begin() as session:
        task = session.get(Task, evaluation_context["task_id"])
        assert task is not None
        task.allowed_writes = ["Evaluation"]
    with pytest.raises(EvaluationValidationError,
        match="evaluation_write_scope_missing"):
        _propose(EvaluationService(session_factory, snapshot_store), evaluation_context)


def test_evaluation_task_cannot_finalize_as_no_change(
    session_factory, snapshot_store, evaluation_context
):
    observation = TerminalObservation(
        task_id=evaluation_context["task_id"],
        attempt=1,
        result_category="success_no_change",
        observed_at=datetime.now(timezone.utc),
    )
    with pytest.raises(
        TaskNotFinalizable,
        match="evaluation_task_requires_evaluation_result",
    ):
        TaskRuntime(session_factory, snapshot_store).finalize(observation)
    with session_factory() as session:
        task = session.get(Task, evaluation_context["task_id"])
        assert task is not None and task.status == "running"


def test_changed_evidence_link_is_rejected_before_recording(
    session_factory, snapshot_store, evaluation_context
):
    service = EvaluationService(session_factory, snapshot_store)
    proposed = _propose(service, evaluation_context)
    with session_factory.begin() as session:
        link = session.scalar(
            select(EvidenceLink).where(
                EvidenceLink.subject_id == proposed.evaluation_id
            )
        )
        assert link is not None
        link.stance = "challenges"
    with pytest.raises(
        EvaluationValidationError,
        match="evidence_link_integrity_mismatch",
    ):
        service.record(evaluation_context["task_id"], proposed.evaluation_id)


def test_signal_evidence_from_another_domain_is_rejected(
    session_factory, snapshot_store, evaluation_context
):
    signal_id = uuid4()
    signal_content = b"Signal evidence from another domain."
    signal_ref, signal_hash = snapshot_store.put(signal_content)
    with session_factory.begin() as session:
        session.add(
            Signal(
                id=signal_id,
                domain="another_domain",
                source_type="web",
                origin_url=f"https://example.test/{signal_id}",
                fetched_at=datetime.now(timezone.utc),
                content_hash=signal_hash,
                snapshot_ref=signal_ref,
            )
        )
    base = _draft(evaluation_context)
    invalid = base.model_copy(update={
        "evidence": [
            *base.evidence,
            EvaluationEvidence(
                source_kind="signal",
                signal_id=signal_id,
                stance="challenges",
            ),
        ]
    })
    try:
        with pytest.raises(
            EvaluationValidationError,
            match="evidence_signal_team_domain_mismatch",
        ):
            _propose(
                EvaluationService(session_factory, snapshot_store),
                evaluation_context,
                invalid,
            )
    finally:
        with session_factory.begin() as session:
            session.execute(delete(Signal).where(Signal.id == signal_id))


def test_checkpoint_one_schema_constraints_exist(session_factory):
    expected = {
        "evaluations": {"ck_evaluations_conclusion",
            "ck_evaluations_evaluator_kind", "ck_evaluations_status",
            "ck_evaluations_disposition", "uq_evaluations_task_idempotency"},
        "evidence_links": {"ck_evidence_links_source",
            "ck_evidence_links_snapshot_pair", "ck_evidence_links_quote_offsets"},
        "learning_changes": {"ck_learning_changes_target_kind",
            "ck_learning_changes_operation", "ck_learning_changes_target_state",
            "ck_learning_changes_evidence_basis_hash",
            "ck_learning_changes_disposition"},
        "knowledge_items": {"ck_knowledge_items_kind", "ck_knowledge_items_status",
            "ck_knowledge_items_version_confidence",
            "ck_knowledge_items_payload_shape"},
    }
    with session_factory() as session:
        for table, required in expected.items():
            actual = set(session.scalars(text(
                "SELECT conname FROM pg_constraint WHERE "
                    "conrelid = CAST(:table AS regclass)"
            ).bindparams(table=table)))
            assert required <= actual
