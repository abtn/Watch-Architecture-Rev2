"""Direct PostgreSQL negative proofs for the RW-1 schema constraints."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from core.models import (
    ConfidenceChange,
    Evaluation,
    EvidenceLink,
    Hypothesis,
    Outcome,
    Signal,
    Task,
    Team,
    Thread,
)


@pytest.fixture
def rw1_schema_context(session_factory, snapshot_store):
    team_id, other_team_id = uuid4(), uuid4()
    task_id, other_task_id = uuid4(), uuid4()
    outcome_id, other_outcome_id = uuid4(), uuid4()
    evaluation_id = uuid4()
    thread_id, other_thread_id = uuid4(), uuid4()
    hypothesis_id, other_hypothesis_id = uuid4(), uuid4()
    signal_id = uuid4()
    now = datetime.now(timezone.utc)
    content = b"RW-1 schema constraint fixture."
    snapshot_ref, snapshot_hash = snapshot_store.put(content)

    with session_factory.begin() as session:
        session.add_all(
            [
                Team(id=team_id, domain="rw1_schema_a", status="active"),
                Team(id=other_team_id, domain="rw1_schema_b", status="active"),
            ]
        )
        session.flush()
        session.add_all(
            [
                Task(
                    id=task_id,
                    team_id=team_id,
                    task_type="rw1_schema_test",
                    status="done",
                    attempt_count=1,
                    policy_version=1,
                    allowed_writes=["EvidenceLink"],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.0,
                        "deadline_seconds": 60,
                    },
                ),
                Task(
                    id=other_task_id,
                    team_id=other_team_id,
                    task_type="rw1_schema_test",
                    status="done",
                    attempt_count=1,
                    policy_version=1,
                    allowed_writes=["EvidenceLink"],
                    budget={
                        "max_tool_calls": 0,
                        "max_cost_usd": 0.0,
                        "deadline_seconds": 60,
                    },
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Outcome(
                    id=outcome_id,
                    team_id=team_id,
                    subject_kind="task",
                    subject_id=task_id,
                    outcome_type="task_execution",
                    expected=None,
                    observation_snapshot_ref=snapshot_ref,
                    observation_hash=snapshot_hash,
                    observed_at=now,
                    recorded_by_task_id=task_id,
                ),
                Outcome(
                    id=other_outcome_id,
                    team_id=other_team_id,
                    subject_kind="task",
                    subject_id=other_task_id,
                    outcome_type="task_execution",
                    expected=None,
                    observation_snapshot_ref=snapshot_ref,
                    observation_hash=snapshot_hash,
                    observed_at=now,
                    recorded_by_task_id=other_task_id,
                ),
            ]
        )
        session.flush()
        session.add(
            Evaluation(
                id=evaluation_id,
                team_id=team_id,
                outcome_id=outcome_id,
                conclusion="worked",
                findings={},
                evaluator_kind="rule",
                evaluator_identity="rw1-schema-tests",
                evaluator_revision="1",
                idempotency_key="rw1-schema-evaluation",
                proposal_hash="sha256:" + "0" * 64,
                created_by_task_id=task_id,
            )
        )
        session.add(
            Signal(
                id=signal_id,
                domain="rw1_schema_a",
                source_type="web",
                origin_url=f"https://example.test/{signal_id}",
                fetched_at=now,
                content_hash=snapshot_hash,
                snapshot_ref=snapshot_ref,
            )
        )
        session.add_all(
            [
                Thread(
                    id=thread_id,
                    team_id=team_id,
                    domain="rw1_schema_a",
                    title="RW-1 schema fixture",
                ),
                Thread(
                    id=other_thread_id,
                    team_id=other_team_id,
                    domain="rw1_schema_b",
                    title="RW-1 other-team fixture",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Hypothesis(
                    id=hypothesis_id,
                    team_id=team_id,
                    thread_id=thread_id,
                    statement="A valid same-Team hypothesis.",
                ),
                Hypothesis(
                    id=other_hypothesis_id,
                    team_id=other_team_id,
                    thread_id=other_thread_id,
                    statement="A valid other-Team hypothesis.",
                ),
            ]
        )
        session.flush()
        session.add(
            EvidenceLink(
                id=uuid4(),
                team_id=team_id,
                subject_kind="hypothesis",
                hypothesis_id=hypothesis_id,
                originating_task_id=task_id,
                source_kind="outcome",
                outcome_id=outcome_id,
                stance="supports",
                reference_key=f"rw1-valid-hypothesis-{uuid4()}",
            )
        )

    context = {
        "team_id": team_id,
        "other_team_id": other_team_id,
        "task_id": task_id,
        "other_task_id": other_task_id,
        "outcome_id": outcome_id,
        "other_outcome_id": other_outcome_id,
        "evaluation_id": evaluation_id,
        "thread_id": thread_id,
        "hypothesis_id": hypothesis_id,
        "other_hypothesis_id": other_hypothesis_id,
        "signal_id": signal_id,
    }
    try:
        yield context
    finally:
        team_ids = [team_id, other_team_id]
        with session_factory.begin() as session:
            session.execute(
                delete(ConfidenceChange).where(
                    ConfidenceChange.team_id.in_(team_ids)
                )
            )
            session.execute(
                delete(EvidenceLink).where(EvidenceLink.team_id.in_(team_ids))
            )
            session.execute(
                delete(Hypothesis).where(Hypothesis.team_id.in_(team_ids))
            )
            session.execute(delete(Thread).where(Thread.team_id.in_(team_ids)))
            session.execute(delete(Evaluation).where(Evaluation.id == evaluation_id))
            session.execute(delete(Outcome).where(Outcome.team_id.in_(team_ids)))
            session.execute(delete(Signal).where(Signal.id == signal_id))
            session.execute(delete(Task).where(Task.team_id.in_(team_ids)))
            session.execute(delete(Team).where(Team.id.in_(team_ids)))


def _expect_constraint(session_factory, record, constraint_name):
    with session_factory() as session:
        with pytest.raises(IntegrityError) as error:
            with session.begin_nested():
                session.add(record)
                session.flush()
    assert constraint_name in str(error.value.orig)


def _evidence_link(context, **overrides):
    values = {
        "id": uuid4(),
        "team_id": context["team_id"],
        "subject_kind": "evaluation",
        "evaluation_id": context["evaluation_id"],
        "hypothesis_id": None,
        "originating_task_id": context["task_id"],
        "source_kind": "outcome",
        "outcome_id": context["outcome_id"],
        "signal_id": None,
        "stance": "supports",
        "reference_key": f"rw1-negative-{uuid4()}",
    }
    values.update(overrides)
    return EvidenceLink(**values)


def _confidence_change(context, **overrides):
    values = {
        "id": uuid4(),
        "team_id": context["team_id"],
        "hypothesis_id": context["hypothesis_id"],
        "from_confidence": "low",
        "to_confidence": "moderate",
        "cause_kind": "evidence",
        "evidence_link_id": None,
        "created_by_task_id": context["task_id"],
        "idempotency_key": f"rw1-negative-{uuid4()}",
    }
    values.update(overrides)
    return ConfidenceChange(**values)


@pytest.mark.parametrize(
    "status",
    ["unknown", ""],
)
def test_thread_status_check_rejects_invalid_values(
    session_factory, rw1_schema_context, status
):
    context = rw1_schema_context
    _expect_constraint(
        session_factory,
        Thread(
            id=uuid4(),
            team_id=context["team_id"],
            domain="rw1_schema_a",
            title="Invalid status",
            status=status,
        ),
        "ck_threads_status",
    )


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("status", "unknown", "ck_hypotheses_status"),
        ("confidence", "certain", "ck_hypotheses_confidence"),
    ],
)
def test_hypothesis_vocabulary_checks_reject_invalid_values(
    session_factory, rw1_schema_context, field, value, constraint
):
    context = rw1_schema_context
    values = {
        "id": uuid4(),
        "team_id": context["team_id"],
        "thread_id": context["thread_id"],
        "statement": "Invalid vocabulary test.",
    }
    values[field] = value
    _expect_constraint(session_factory, Hypothesis(**values), constraint)


@pytest.mark.parametrize(
    ("subject_kind", "evaluation_id", "hypothesis_id"),
    [
        ("evaluation", None, None),
        ("evaluation", None, "hypothesis"),
        ("evaluation", "evaluation", "hypothesis"),
    ],
)
def test_evidence_link_subject_check_rejects_missing_dual_and_mismatched_subjects(
    session_factory,
    rw1_schema_context,
    subject_kind,
    evaluation_id,
    hypothesis_id,
):
    context = rw1_schema_context
    values = {
        "subject_kind": subject_kind,
        "evaluation_id": (
            context["evaluation_id"] if evaluation_id == "evaluation" else evaluation_id
        ),
        "hypothesis_id": (
            context["hypothesis_id"] if hypothesis_id == "hypothesis" else hypothesis_id
        ),
    }
    _expect_constraint(
        session_factory,
        _evidence_link(context, **values),
        "ck_evidence_links_subject",
    )


@pytest.mark.parametrize(
    ("source_kind", "outcome_id", "signal_id"),
    [
        ("outcome", None, None),
        ("outcome", "outcome", "signal"),
        ("signal", "outcome", None),
    ],
)
def test_evidence_link_source_check_rejects_missing_dual_and_mismatched_sources(
    session_factory, rw1_schema_context, source_kind, outcome_id, signal_id
):
    context = rw1_schema_context
    values = {
        "source_kind": source_kind,
        "outcome_id": context["outcome_id"] if outcome_id == "outcome" else outcome_id,
        "signal_id": context["signal_id"] if signal_id == "signal" else signal_id,
    }
    _expect_constraint(
        session_factory,
        _evidence_link(context, **values),
        "ck_evidence_links_source",
    )


@pytest.mark.parametrize(
    ("cause_kind", "evidence_link_id"),
    [
        ("evidence", None),
        ("decay", uuid4()),
    ],
)
def test_confidence_change_cause_check_rejects_missing_or_dual_causes(
    session_factory, rw1_schema_context, cause_kind, evidence_link_id
):
    context = rw1_schema_context
    if evidence_link_id is not None:
        with session_factory() as session:
            evidence_link_id = session.query(EvidenceLink.id).filter_by(
                hypothesis_id=context["hypothesis_id"]
            ).scalar()
    _expect_constraint(
        session_factory,
        _confidence_change(
            context,
            cause_kind=cause_kind,
            evidence_link_id=evidence_link_id,
        ),
        "ck_confidence_changes_cause",
    )


def test_confidence_change_cause_checks_reject_unknown_value(
    session_factory, rw1_schema_context
):
    context = rw1_schema_context
    with session_factory() as session:
        with pytest.raises(IntegrityError) as error:
            with session.begin_nested():
                session.add(_confidence_change(context, cause_kind="unsupported"))
                session.flush()
    assert any(
        name in str(error.value.orig)
        for name in (
            "ck_confidence_changes_cause",
            "ck_confidence_changes_cause_kind",
        )
    )

@pytest.mark.parametrize(
    ("team_id", "evaluation_id", "hypothesis_id", "task_id", "outcome_id", "constraint"),
    [
        (
            "other",
            "evaluation",
            None,
            "other",
            "other",
            "fk_evidence_links_evaluation_subject_team",
        ),
        (
            "other",
            None,
            "hypothesis",
            "other",
            "other",
            "fk_evidence_links_hypothesis_team",
        ),
        (
            "same",
            "evaluation",
            None,
            "other",
            "same",
            "fk_evidence_links_originating_task_team",
        ),
    ],
)
def test_evidence_link_subject_and_originating_task_fks_enforce_team_ownership(
    session_factory,
    rw1_schema_context,
    team_id,
    evaluation_id,
    hypothesis_id,
    task_id,
    outcome_id,
    constraint,
):
    context = rw1_schema_context
    values = {
        "subject_kind": "hypothesis" if hypothesis_id == "hypothesis" else "evaluation",
        "team_id": context["other_team_id"] if team_id == "other" else context["team_id"],
        "evaluation_id": (
            context["evaluation_id"] if evaluation_id == "evaluation" else None
        ),
        "hypothesis_id": (
            context["hypothesis_id"] if hypothesis_id == "hypothesis" else None
        ),
        "originating_task_id": (
            context["other_task_id"] if task_id == "other" else context["task_id"]
        ),
        "outcome_id": (
            context["other_outcome_id"] if outcome_id == "other" else context["outcome_id"]
        ),
    }
    _expect_constraint(
        session_factory,
        _evidence_link(context, **values),
        constraint,
    )
