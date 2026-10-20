"""R5-04: one durable accepted candidate, one immutable action, one ordinary Task."""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Objective, Plan, PlanAction, Task, Team, TeamPolicy
from core.objectives import ObjectiveService, TaskNotFound
from core.state_assessment import _canonical_json
from core.strategy import StrategyService
from core.strategy_proposal import StrategyProposal

_TASK_BUDGET = {"max_tool_calls": 0, "max_cost_usd": 0.0, "deadline_seconds": 60}


@dataclass(frozen=True)
class PlanResult:
    plan_id: UUID
    action_ids: tuple[UUID, ...]
    task_ids: tuple[UUID, ...]
    event_id: UUID
    replayed: bool = False

    @property
    def action_id(self) -> UUID:
        return self.action_ids[0]

    @property
    def task_id(self) -> UUID:
        return self.task_ids[0]


class PlanService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(
        self,
        task_id: UUID,
        accepted_event_id: UUID,
        proposal_hash: str,
        objective_id: UUID,
        team_id: UUID,
    ) -> PlanResult:
        try:
            return self._create(
                task_id, accepted_event_id, proposal_hash, objective_id, team_id
            )
        except ValueError as error:
            with self._session_factory.begin() as session:
                task = ObjectiveService._lock_task(session, task_id)
                if task is None or task.task_type != "create_plan":
                    raise
                ObjectiveService._add_event(
                    session,
                    task.id,
                    "plan_creation_rejected",
                    {
                        "operation": "create_plan",
                        "reason": str(error),
                        "accepted_event_id": str(accepted_event_id),
                        "proposal_hash": proposal_hash,
                        "objective_id": str(objective_id),
                        "team_id": str(team_id),
                    },
                )
            raise

    def _create(
        self,
        task_id: UUID,
        accepted_event_id: UUID,
        proposal_hash: str,
        objective_id: UUID,
        team_id: UUID,
    ) -> PlanResult:
        with self._session_factory.begin() as session:
            task = ObjectiveService._lock_task(session, task_id)
            if task is None:
                raise TaskNotFound(f"Task {task_id} does not exist")
            policy = self._validate_task(session, task)
            if team_id != task.team_id:
                raise ValueError("plan_team_mismatch")
            if objective_id != task.objective_id:
                raise ValueError("task_objective_mismatch")
            objective = session.scalar(
                select(Objective).where(Objective.id == objective_id).with_for_update()
            )
            if objective is None:
                raise ValueError("objective_not_found")
            if objective.team_id != team_id:
                raise ValueError("objective_team_mismatch")
            accepted, proposal = self._accepted(
                session, accepted_event_id, proposal_hash, objective_id, team_id
            )
            actions = proposal.candidate_actions
            action_ids = tuple(action.id for action in actions)
            identity = {
                "operation": "create_plan",
                "accepted_event_id": str(accepted_event_id),
                "proposal_hash": proposal_hash,
                "objective_id": str(objective_id),
                "team_id": str(team_id),
                "action_ids": [str(action_id) for action_id in action_ids],
                "policy_version": task.policy_version,
            }
            prior = session.scalar(
                select(Event).where(
                    Event.task_id == task.id, Event.type == "plan_created"
                )
            )
            if prior is not None:
                if any(
                    prior.payload.get(key) != value for key, value in identity.items()
                ):
                    raise ValueError("task_outcome_conflict")
                result = self._reconstruct(session, UUID(prior.payload["plan_id"]))
                if result.event_id != prior.id:
                    raise ValueError("recorded_plan_creation_corrupt")
                return PlanResult(
                    result.plan_id,
                    result.action_ids,
                    result.task_ids,
                    result.event_id,
                    True,
                )
            if objective.status != "active":
                raise ValueError("objective_not_active")
            budgets = policy.rules.get("budgets", {})
            if (
                not isinstance(budgets, dict)
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                    for value in budgets.values()
                )
                or any(
                    budgets[key] < minimum
                    for key, minimum in (
                        ("max_tasks_per_day", 1),
                        ("max_cost_usd_per_day", 0),
                    )
                    if key in budgets
                )
            ):
                raise ValueError("invalid_policy_budget")
            sources = policy.rules.get("sources")
            if not isinstance(sources, list) or any(
                not any(
                    isinstance(source, dict)
                    and source.get("origin_url") == action.origin_url
                    and source.get("source_type") == action.source_type
                    for source in sources
                )
                for action in actions
            ):
                raise ValueError("source_not_configured")
            if not set(
                prerequisite
                for action in actions
                for prerequisite in action.prerequisites
            ).issubset(set(action_ids)):
                raise ValueError("dependency_target_not_found")
            plan = Plan(
                id=uuid4(),
                team_id=team_id,
                objective_id=objective_id,
                created_by_task_id=task.id,
                accepted_event_id=accepted.id,
                proposal_hash=proposal_hash,
                assessment_basis=accepted.payload["assessment"]["basis"],
                assessment_created_at=accepted.payload["assessment"]["created_at"],
                budget=proposal.constraints.model_dump(mode="json"),
                completion_condition=proposal.stop_conditions[0],
            )
            session.add(plan)
            session.flush()
            plan_actions = [
                PlanAction(
                    plan_id=plan.id,
                    action_id=action.id,
                    action=action.model_dump(mode="json"),
                )
                for action in actions
            ]
            session.add_all(plan_actions)
            session.flush()
            materialized_tasks = [
                Task(
                    id=uuid4(),
                    team_id=team_id,
                    objective_id=objective_id,
                    plan_id=plan.id,
                    plan_action_id=action.id,
                    task_type=action.task_type,
                    status="pending",
                    policy_version=task.policy_version,
                    allowed_writes=["Signal"],
                    budget=dict(_TASK_BUDGET),
                )
                for action in actions
            ]
            session.add_all(materialized_tasks)
            session.flush()
            event = ObjectiveService._add_event(
                session,
                task.id,
                "plan_created",
                {
                    **identity,
                    "plan_id": str(plan.id),
                    "materialized_task_ids": [
                        str(materialized_task.id)
                        for materialized_task in materialized_tasks
                    ],
                },
            )
            session.flush()
            return PlanResult(
                plan.id,
                action_ids,
                tuple(materialized_task.id for materialized_task in materialized_tasks),
                event.id,
            )

    @staticmethod
    def _validate_task(session: Session, task: Task) -> TeamPolicy:
        if task.task_type != "create_plan":
            raise ValueError("plan_event_scope_violation")
        if task.status != "running":
            raise ValueError("task_not_running")
        if task.allowed_writes != ["Plan"]:
            raise ValueError("write_scope_violation")
        if not ObjectiveService._budget_allows_zero_usage(task.budget):
            raise ValueError("invalid_task_budget")
        team = session.scalar(
            select(Team).where(Team.id == task.team_id).with_for_update(read=True)
        )
        if team is None or team.status != "active":
            raise ValueError("team_not_active")
        policy = session.scalar(
            select(TeamPolicy)
            .where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
            .with_for_update(read=True)
        )
        if policy is None:
            raise ValueError("team_policy_missing")
        return policy

    @staticmethod
    def _accepted(
        session: Session,
        event_id: UUID,
        proposal_hash: str,
        objective_id: UUID,
        team_id: UUID,
    ) -> tuple[Event, StrategyProposal]:
        event = session.scalar(
            select(Event).where(Event.id == event_id).with_for_update(read=True)
        )
        proposal = StrategyService.reconstruct_in_session(session, event_id)
        if event is None:
            raise ValueError("accepted_proposal_not_found")
        payload = event.payload
        producer = session.get(Task, event.task_id)
        if (
            payload.get("operation") != "propose_strategy"
            or "reason" not in payload
            or payload.get("reason") is not None
            or producer is None
            or producer.task_type != "propose_strategy"
            or payload.get("team_id") != str(team_id)
            or payload.get("objective_id") != str(objective_id)
            or producer.team_id != team_id
            or producer.objective_id != objective_id
            or not isinstance(payload.get("policy_version"), int)
            or isinstance(payload.get("policy_version"), bool)
            or session.scalar(
                select(TeamPolicy.id).where(
                    TeamPolicy.team_id == team_id,
                    TeamPolicy.version == payload.get("policy_version"),
                )
            )
            is None
            or proposal.objective_id != str(objective_id)
        ):
            raise ValueError("accepted_proposal_scope_mismatch")
        if payload.get("proposal_hash") != proposal_hash:
            raise ValueError("proposal_hash_mismatch")
        if _canonical_json(proposal.canonical_dump()) != payload["proposal_json"]:
            raise ValueError("invalid_proposal_provenance")
        if StrategyService._validate_structure(proposal) is not None:
            raise ValueError("invalid_proposal_provenance")
        if (
            not proposal.candidate_actions
            or StrategyService._validate_structure(proposal) is not None
            or len(proposal.candidate_actions) > proposal.constraints.max_tasks
            or proposal.constraints.max_cost_usd != 0
            or any(
                action.task_type != "ingest_source" or action.tools
                for action in proposal.candidate_actions
            )
            or proposal.stop_conditions != ("configured_source_ingested",)
        ):
            raise ValueError("unsupported_plan_candidate")
        PlanService._validate_assessment(
            payload.get("assessment"), objective_id, team_id
        )
        return event, proposal

    @staticmethod
    def _validate_assessment(raw: Any, objective_id: UUID, team_id: UUID) -> None:
        # Validate the stored R3 basis, never a new projection of current state.
        try:
            if raw["objective"]["id"] != str(objective_id) or (
                raw["objective"]["team_id"] != str(team_id)
                or raw["team"]["id"] != str(team_id)
            ):
                raise ValueError("assessment_scope_mismatch")
            stamp = datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("invalid_assessment_timestamp")
            projection = {
                key: raw[key] for key in ("objective", "team", "tasks", "signals")
            }
            projection["policies"] = [
                {
                    "id": p["id"],
                    "team_id": p["team_id"],
                    "version": p["version"],
                    "rules": json.loads(p["rules_json"]),
                }
                for p in raw["policies"]
            ]
            projection["events"] = [
                {
                    "id": e["id"],
                    "task_id": e["task_id"],
                    "type": e["event_type"],
                    "created_at": e["created_at"],
                    "signal_id": e["signal_id"],
                }
                for e in raw["events"]
            ]
            expected = {
                "objective_id": str(objective_id),
                "team_id": str(team_id),
                **{
                    key: [item["id"] for item in raw[name]]
                    for key, name in (
                        ("policy_ids", "policies"),
                        ("task_ids", "tasks"),
                        ("event_ids", "events"),
                        ("signal_ids", "signals"),
                    )
                },
                "sha256": hashlib.sha256(
                    _canonical_json(projection).encode()
                ).hexdigest(),
            }
            if raw["basis"] != expected:
                raise ValueError("assessment_basis_mismatch")
        except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
            raise ValueError("invalid_assessment_provenance") from error

    def reconstruct(self, plan_id: UUID) -> PlanResult:
        with self._session_factory() as session:
            return self._reconstruct(session, plan_id)

    @staticmethod
    def _reconstruct(session: Session, plan_id: UUID) -> PlanResult:
        plan = session.get(Plan, plan_id)
        if plan is None:
            raise ValueError("plan_not_found")
        accepted, proposal = PlanService._accepted(
            session,
            plan.accepted_event_id,
            plan.proposal_hash,
            plan.objective_id,
            plan.team_id,
        )
        actions = proposal.candidate_actions
        action_ids = tuple(action.id for action in actions)
        stored_actions = {
            row.action_id: row.action
            for row in session.scalars(
                select(PlanAction).where(PlanAction.plan_id == plan.id)
            )
        }
        tasks = {
            task.plan_action_id: task
            for task in session.scalars(select(Task).where(Task.plan_id == plan.id))
        }
        event = session.scalar(
            select(Event).where(
                Event.task_id == plan.created_by_task_id, Event.type == "plan_created"
            )
        )
        creator = session.get(Task, plan.created_by_task_id)
        if set(tasks) != set(action_ids):
            raise ValueError("recorded_plan_creation_corrupt")
        task_ids = tuple(tasks[action_id].id for action_id in action_ids)
        if (
            set(stored_actions) != set(action_ids)
            or set(tasks) != set(action_ids)
            or any(
                stored_actions[action.id] != action.model_dump(mode="json")
                for action in actions
            )
            or plan.assessment_basis != accepted.payload["assessment"]["basis"]
            or plan.assessment_created_at
            != accepted.payload["assessment"]["created_at"]
            or plan.budget != proposal.constraints.model_dump(mode="json")
            or plan.completion_condition != proposal.stop_conditions[0]
            or any(
                task.team_id != plan.team_id
                or task.plan_id != plan.id
                or task.plan_action_id != action.id
                or task.objective_id != plan.objective_id
                or task.task_type != action.task_type
                or task.allowed_writes != ["Signal"]
                or task.budget != _TASK_BUDGET
                for action in actions
                for task in [tasks[action.id]]
            )
            or creator is None
            or creator.task_type != "create_plan"
            or creator.team_id != plan.team_id
            or creator.objective_id != plan.objective_id
            or event is None
        ):
            raise ValueError("recorded_plan_creation_corrupt")
        expected = {
            "operation": "create_plan",
            "plan_id": str(plan.id),
            "accepted_event_id": str(plan.accepted_event_id),
            "proposal_hash": plan.proposal_hash,
            "objective_id": str(plan.objective_id),
            "team_id": str(plan.team_id),
            "action_ids": [str(action_id) for action_id in action_ids],
            "policy_version": creator.policy_version,
            "materialized_task_ids": [str(task_id) for task_id in task_ids],
        }
        if (
            event.payload != expected
            or any(
                task.policy_version != creator.policy_version
                for task in tasks.values()
            )
        ):
            raise ValueError("recorded_plan_creation_corrupt")
        return PlanResult(plan.id, action_ids, task_ids, event.id)
