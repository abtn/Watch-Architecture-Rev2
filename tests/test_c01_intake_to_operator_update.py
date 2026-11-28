"""C-01: one configured source intake followed by an authenticated Operator update."""

from __future__ import annotations  # noqa: I001

import json
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from core.dispatcher import TaskDispatcher
from core.models import (
    ConfidenceChange,
    Event,
    EvidenceLink,
    Hypothesis,
    Objective,
    Outcome,
    Plan,
    PlanAction,
    Signal,
    Task,
    Team,
    TeamExperienceChunk,
    TeamPolicy,
    Thread,
)
from core.operator_application import (
    OperatorApplicationAdapter,
    OperatorGrant,
    TrustedOperatorPrincipal,
)
from core.plans import PlanService
from core.snapshot_store import SnapshotStore
from core.state_assessment import StateAssessmentBuilder
from core.strategy import StrategyService
from core.strategy_proposal import FakeStrategyWorker, StrategyContext
from core.task_runtime import TaskRuntime, TerminalObservation
from core.world_memory import (
    EvidenceLinkProposal,
    HypothesisCreateProposal,
    OperatorUpdateRequest,
)


_CONTENT = b"Market report: supply increased by 5 percent."
_QUOTE = "supply increased by 5 percent"


def _task_started_at(
    session_factory: sessionmaker[Session], task_id: UUID
):
    with session_factory() as session:
        started = session.scalar(
            select(Event).where(
                Event.task_id == task_id,
                Event.type == "task_started",
            )
        )
        assert started is not None
        return started.created_at


def _operator_principal(team_id: UUID) -> TrustedOperatorPrincipal:
    return TrustedOperatorPrincipal(
        issuer="https://host.example.test/identity",
        subject="c01-test-operator",
        grants=frozenset({OperatorGrant(team_id, "operator_update")}),
    )


def test_c01_configured_source_intake_then_operator_update(
    session_factory: sessionmaker[Session],
    snapshot_store: SnapshotStore,
) -> None:
    team_id, policy_id, objective_id, strategy_task_id, plan_task_id, thread_id = (
        uuid4() for _ in range(6)
    )
    origin_url = f"https://news.example.test/feed/{uuid4()}"
    domain = "c01_test"
    # The active Thread is deliberately pre-existing fixture state. Thread
    # creation is not part of this scenario.
    with session_factory.begin() as session:
        session.add(Team(id=team_id, domain=domain, status="active"))
        session.flush()
        session.add(
            TeamPolicy(
                id=policy_id,
                team_id=team_id,
                version=1,
                rules={
                    "sources": [
                        {"origin_url": origin_url, "source_type": "rss"}
                    ]
                },
            )
        )
        session.add(
            Objective(
                id=objective_id,
                team_id=team_id,
                statement="Collect one configured source observation.",
                status="active",
            )
        )
        session.add(
            Thread(
                id=thread_id,
                team_id=team_id,
                domain=domain,
                title="Supply conditions",
                status="active",
            )
        )
        # Persist every referenced parent row before inserting Tasks: the
        # database enforces (team_id, policy_version) as a composite FK.
        session.flush()
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
                        "max_cost_usd": 0.0,
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

    with session_factory() as session:
        experience_before = len(
            list(
                session.scalars(
                    select(TeamExperienceChunk).where(
                        TeamExperienceChunk.team_id == team_id
                    )
                )
            )
        )
    assert experience_before == 0

    try:
        runtime = TaskRuntime(session_factory, snapshot_store)

        # Accept one ordinary nested Strategy proposal against the pinned
        # policy, then materialize the Plan and its source Task through the
        # existing PlanService -> Control Room path.
        runtime.admit(strategy_task_id)
        assessment = StateAssessmentBuilder(session_factory).build(objective_id)
        strategy_context = StrategyContext(str(strategy_task_id), assessment)
        strategy_proposal = FakeStrategyWorker().propose(strategy_context)
        assert len(strategy_proposal.candidate_actions) == 1
        assert strategy_proposal.candidate_actions[0].origin_url == origin_url
        assert strategy_proposal.candidate_actions[0].source_type == "rss"
        strategy_result = StrategyService(session_factory).submit(
            strategy_task_id, strategy_proposal, assessment
        )
        assert strategy_result.accepted
        strategy_terminal = runtime.finalize(
            TerminalObservation(
                task_id=strategy_task_id,
                attempt=1,
                result_category="success_strategy_accepted",
                observed_at=_task_started_at(session_factory, strategy_task_id),
                strategy_event_id=strategy_result.event_id,
            )
        )
        assert strategy_terminal.status == "done"

        runtime.admit(plan_task_id)
        with session_factory() as session:
            accepted_event = session.get(Event, strategy_result.event_id)
            assert accepted_event is not None
            proposal_hash = accepted_event.payload["proposal_hash"]
        plan_result = PlanService(session_factory).create(
            task_id=plan_task_id,
            accepted_event_id=strategy_result.event_id,
            proposal_hash=proposal_hash,
            objective_id=objective_id,
            team_id=team_id,
        )
        plan_terminal = runtime.finalize(
            TerminalObservation(
                task_id=plan_task_id,
                attempt=1,
                result_category="success_plan_created",
                observed_at=_task_started_at(session_factory, plan_task_id),
                plan_id=plan_result.plan_id,
                plan_event_id=plan_result.event_id,
            )
        )
        assert plan_terminal.status == "done"
        assert len(plan_result.task_ids) == 1

        source_task_id = plan_result.task_ids[0]
        with session_factory() as session:
            source_task = session.get(Task, source_task_id)
            plan_action = session.scalar(
                select(PlanAction).where(
                    PlanAction.plan_id == plan_result.plan_id
                )
            )
            assert source_task is not None
            assert plan_action is not None
            assert source_task.task_type == "ingest_source"
            assert source_task.plan_id == plan_result.plan_id
            assert source_task.plan_action_id == plan_action.action_id
            assert source_task.team_id == team_id
            assert source_task.objective_id == objective_id
            assert source_task.policy_version == 1
            assert plan_action.action["origin_url"] == origin_url
            assert plan_action.action["source_type"] == "rss"

        # Only the injected fake is contacted. TaskDispatcher resolves the
        # durable source identity from the PlanAction, not caller input.
        from tests.test_r6b_dispatcher import FakeFetcher

        fetcher = FakeFetcher(_CONTENT)
        dispatch_result = TaskDispatcher(
            session_factory, snapshot_store, fetcher
        ).dispatch(source_task_id)
        assert dispatch_result.status == "done"
        assert dispatch_result.result_category == "success_signal_created"
        assert dispatch_result.signal_id is not None
        assert dispatch_result.outcome_id is not None
        assert [item.origin_url for item in fetcher.requests] == [origin_url]
        assert [item.source_type for item in fetcher.requests] == ["rss"]

        with session_factory() as session:
            source_task = session.get(Task, source_task_id)
            signal = session.get(Signal, dispatch_result.signal_id)
            source_outcome = session.get(Outcome, dispatch_result.outcome_id)
            intake_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == source_task_id,
                        Event.type == "signal_ingested",
                    )
                )
            )
            source_terminal_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == source_task_id,
                        Event.type == "task_completed",
                    )
                )
            )
            evaluation_requests = list(
                session.scalars(
                    select(Event).where(
                        Event.type == "evaluation_task_requested"
                    )
                )
            )
            evaluation_requests = [
                event
                for event in evaluation_requests
                if event.payload.get("source_task_id") == str(source_task_id)
            ]
            assert source_task is not None and source_task.status == "done"
            assert source_task.attempt_count == 1
            assert signal is not None
            assert signal.domain == domain
            assert signal.origin_url == origin_url
            assert signal.source_type == "rss"
            assert source_outcome is not None
            assert source_outcome.outcome_type == "task_execution"
            assert source_outcome.recorded_by_task_id == source_task_id
            assert len(intake_events) == 1
            assert len(source_terminal_events) == 1
            # TaskRuntime's existing evaluation follow-on is an expected
            # side effect, not a second source Task or a C-01-created queue.
            assert len(evaluation_requests) == 1
            evaluation_task = session.get(Task, evaluation_requests[0].task_id)
            assert evaluation_task is not None
            assert evaluation_task.task_type == "evaluate_outcome"
            assert evaluation_task.team_id == team_id
            snapshot_ref = signal.snapshot_ref
            snapshot_hash = signal.content_hash

        snapshot_bytes = snapshot_store.read(snapshot_ref)
        assert snapshot_bytes == _CONTENT
        assert snapshot_hash == "sha256:" + snapshot_ref.removeprefix("snap://sha256/")

        hypothesis_id = uuid4()
        quote_start = snapshot_bytes.decode("utf-8").index(_QUOTE)
        request = OperatorUpdateRequest(
            thread_id=thread_id,
            idempotency_key=uuid4(),
            proposals=[
                HypothesisCreateProposal(
                    kind="hypothesis_create",
                    key="create-low-confidence-hypothesis",
                    hypothesis_id=hypothesis_id,
                    statement="Supply is increasing.",
                ),
                EvidenceLinkProposal(
                    kind="evidence_link_add",
                    key="cite-ingested-snapshot",
                    hypothesis_id=hypothesis_id,
                    source_kind="signal",
                    signal_id=dispatch_result.signal_id,
                    stance="supports",
                    snapshot_ref=snapshot_ref,
                    snapshot_hash=snapshot_hash,
                    quote_text=_QUOTE,
                    quote_start=quote_start,
                    quote_end=quote_start + len(_QUOTE),
                ),
            ],
        )
        adapter = OperatorApplicationAdapter(session_factory, snapshot_store)
        operator_result = adapter.operator_update(
            _operator_principal(team_id), request
        )
        assert operator_result.task_status == "done"
        assert operator_result.committed_count == 2
        assert operator_result.rejected_count == 0
        assert not operator_result.replayed

        with session_factory() as session:
            hypothesis = session.get(Hypothesis, hypothesis_id)
            evidence = session.scalar(
                select(EvidenceLink).where(
                    EvidenceLink.originating_task_id == operator_result.task_id
                )
            )
            request_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == operator_result.task_id,
                        Event.type == "operator_update_requested",
                    )
                )
            )
            commit_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == operator_result.task_id,
                        Event.type == "operator_update_committed",
                    )
                )
            )
            operator_terminal_events = list(
                session.scalars(
                    select(Event).where(
                        Event.task_id == operator_result.task_id,
                        Event.type == "task_completed",
                    )
                )
            )
            operator_outcome = session.get(Outcome, operator_result.outcome_id)
            assert hypothesis is not None
            assert hypothesis.team_id == team_id
            assert hypothesis.thread_id == thread_id
            assert hypothesis.confidence == "low"
            assert evidence is not None
            assert evidence.team_id == team_id
            assert evidence.signal_id == dispatch_result.signal_id
            assert evidence.snapshot_ref == snapshot_ref
            assert evidence.snapshot_hash == snapshot_hash
            assert evidence.quote_text == _QUOTE
            assert evidence.quote_start == quote_start
            assert evidence.quote_end == quote_start + len(_QUOTE)
            assert len(request_events) == len(commit_events) == 1
            assert len(operator_terminal_events) == 1
            assert operator_outcome is not None
            assert operator_outcome.recorded_by_task_id == operator_result.task_id
            assert session.scalar(
                select(ConfidenceChange.id).where(
                    ConfidenceChange.created_by_task_id == operator_result.task_id
                )
            ) is None
            experience_after_operator = len(
                list(
                    session.scalars(
                        select(TeamExperienceChunk).where(
                            TeamExperienceChunk.team_id == team_id
                        )
                    )
                )
            )
            assert experience_after_operator == 0

        replay = adapter.operator_update(_operator_principal(team_id), request)
        assert replay.replayed
        assert replay.task_id == operator_result.task_id
        assert replay.outcome_id == operator_result.outcome_id
        with session_factory() as session:
            assert session.scalar(
                select(Hypothesis.id).where(Hypothesis.id == hypothesis_id)
            ) == hypothesis_id
            assert len(
                list(
                    session.scalars(
                        select(EvidenceLink).where(
                            EvidenceLink.originating_task_id == operator_result.task_id
                        )
                    )
                )
            ) == 1
            assert len(
                list(
                    session.scalars(
                        select(Outcome).where(
                            Outcome.recorded_by_task_id == operator_result.task_id,
                            Outcome.outcome_type == "task_execution",
                        )
                    )
                )
            ) == 1
            assert len(
                list(
                    session.scalars(
                        select(Event).where(
                            Event.task_id == operator_result.task_id,
                            Event.type == "operator_update_requested",
                        )
                    )
                )
            ) == 1
            assert len(
                list(
                    session.scalars(
                        select(Event).where(
                            Event.task_id == operator_result.task_id,
                            Event.type == "operator_update_committed",
                        )
                    )
                )
            ) == 1
            assert len(
                list(
                    session.scalars(
                        select(Event).where(
                            Event.task_id == operator_result.task_id,
                            Event.type == "task_completed",
                        )
                    )
                )
            ) == 1
            assert list(
                session.scalars(
                    select(TeamExperienceChunk).where(
                        TeamExperienceChunk.team_id == team_id
                    )
                )
            ) == []
            source_events = list(
                session.scalars(
                    select(Event).where(Event.task_id == source_task_id)
                )
            )
            operator_events = list(
                session.scalars(
                    select(Event).where(Event.task_id == operator_result.task_id)
                )
            )
            strategy_events = list(
                session.scalars(
                    select(Event).where(Event.task_id == strategy_task_id)
                )
            )
            plan_events = list(
                session.scalars(
                    select(Event).where(Event.task_id == plan_task_id)
                )
            )
            source_task_row = session.get(Task, source_task_id)
            operator_task_row = session.get(Task, operator_result.task_id)
            experience_count = len(
                list(
                    session.scalars(
                        select(TeamExperienceChunk).where(
                            TeamExperienceChunk.team_id == team_id
                        )
                    )
                )
            )
        print(
            "R8_IDENTITY_MANIFEST="
            + json.dumps(
                {
                    "scenario": "C-01",
                    "identities": {
                        "team_id": str(team_id),
                        "team_policy_id": str(policy_id),
                        "objective_id": str(objective_id),
                        "strategy_task_id": str(strategy_task_id),
                        "strategy_event_id": str(strategy_result.event_id),
                        "plan_task_id": str(plan_task_id),
                        "plan_id": str(plan_result.plan_id),
                        "plan_event_id": str(plan_result.event_id),
                        "plan_action_id": str(plan_action.action_id),
                        "source_task_id": str(source_task_id),
                        "evaluation_task_id": str(evaluation_task.id),
                        "preexisting_thread_id": str(thread_id),
                        "configured_origin_url": origin_url,
                        "signal_id": str(dispatch_result.signal_id),
                        "snapshot_ref": snapshot_ref,
                        "snapshot_hash": snapshot_hash,
                        "operator_request_idempotency_key": str(request.idempotency_key),
                        "operator_task_id": str(operator_result.task_id),
                        "hypothesis_id": str(hypothesis_id),
                        "evidence_link_id": str(evidence.id),
                        "operator_outcome_id": str(operator_result.outcome_id),
                        "source_outcome_id": str(dispatch_result.outcome_id),
                        "source_event_ids": [str(event.id) for event in source_events],
                        "operator_event_ids": [
                            str(event.id) for event in operator_events
                        ],
                        "strategy_event_ids": [
                            str(event.id) for event in strategy_events
                        ],
                        "plan_event_ids": [str(event.id) for event in plan_events],
                    },
                    "observations": {
                        "strategy_terminal_status": strategy_terminal.status,
                        "plan_terminal_status": plan_terminal.status,
                        "source_task_status": source_task_row.status,
                        "operator_task_status": operator_task_row.status,
                        "fake_fetcher_request_count": len(fetcher.requests),
                        "source_task_completed_event_count": sum(
                            event.type == "task_completed" for event in source_events
                        ),
                        "operator_request_event_count": sum(
                            event.type == "operator_update_requested"
                            for event in operator_events
                        ),
                        "operator_commit_event_count": sum(
                            event.type == "operator_update_committed"
                            for event in operator_events
                        ),
                        "operator_completion_event_count": sum(
                            event.type == "task_completed" for event in operator_events
                        ),
                        "operator_evidence_link_count": 1,
                        "operator_outcome_count": 1,
                        "operator_replay": replay.replayed,
                        "replay_task_id": str(replay.task_id),
                        "replay_outcome_id": str(replay.outcome_id),
                            "team_experience_chunk_count_before_operation": experience_before,
                        "team_experience_chunk_count_after_operator_update": experience_after_operator,
                        "team_experience_chunk_count_after_replay": experience_count,
                    },
                },
                sort_keys=True,
            )
        )
    finally:
        with session_factory.begin() as session:
            team_task_ids = select(Task.id).where(Task.team_id == team_id)
            plan_ids = select(Plan.id).where(Plan.team_id == team_id)
            session.execute(
                delete(ConfidenceChange).where(
                    ConfidenceChange.team_id == team_id
                )
            )
            session.execute(
                delete(EvidenceLink).where(EvidenceLink.team_id == team_id)
            )
            session.execute(
                delete(Hypothesis).where(Hypothesis.team_id == team_id)
            )
            session.execute(delete(Thread).where(Thread.team_id == team_id))
            session.execute(
                delete(Outcome).where(Outcome.recorded_by_task_id.in_(team_task_ids))
            )
            session.execute(delete(Signal).where(Signal.origin_url == origin_url))
            # Remove source-task Events and Tasks before their Plan; the Plan's
            # accepted Strategy Event remains until after the Plan is deleted.
            linked_task_ids = select(Task.id).where(Task.plan_id.in_(plan_ids))
            session.execute(delete(Event).where(Event.task_id.in_(linked_task_ids)))
            session.execute(
                delete(Task).where(Task.id.in_(linked_task_ids))
            )
            session.execute(
                delete(PlanAction).where(PlanAction.plan_id.in_(plan_ids))
            )
            session.execute(delete(Plan).where(Plan.id.in_(plan_ids)))
            session.execute(delete(Event).where(Event.task_id.in_(team_task_ids)))
            session.execute(delete(Task).where(Task.team_id == team_id))
            session.execute(delete(Objective).where(Objective.team_id == team_id))
            session.execute(delete(TeamPolicy).where(TeamPolicy.team_id == team_id))
            session.execute(delete(Team).where(Team.id == team_id))
