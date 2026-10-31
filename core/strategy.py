"""Application-controlled R4 validation and reconstructable audit, not planning."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from core.models import Event, Objective, Task, Team, TeamPolicy
from core.objectives import ObjectiveService, TaskNotFound
from core.state_assessment import (
    StateAssessment,
    StateAssessmentBuilder,
    _canonical_json,
)
from core.strategy_proposal import (
    HistoricalStrategyRead,
    LegacyStrategyRecord,
    StrategyProposal,
)


@dataclass(frozen=True)
class StrategyResult:
    accepted: bool
    reason: str | None
    event_id: UUID
    replayed: bool = False


class StrategyService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._assessments = StateAssessmentBuilder(session_factory)

    def submit(
        self, task_id: UUID, proposal: Any, assessment: StateAssessment
    ) -> StrategyResult:
        try:
            return self._submit(task_id, proposal, assessment)
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) not in {"40001", "40P01"}:
                raise
            return self._submit(
                task_id,
                proposal,
                assessment,
                conflict_reason="concurrent_state_conflict",
            )

    def _submit(
        self,
        task_id: UUID,
        proposal: Any,
        assessment: StateAssessment,
        *,
        conflict_reason: str | None = None,
    ) -> StrategyResult:
        try:
            if isinstance(proposal, StrategyProposal):
                raw = proposal.canonical_dump()
            else:
                proposal = StrategyProposal.model_validate(proposal)
                raw = proposal.canonical_dump()
            canonical = _canonical_json(raw)
            raw = json.loads(canonical)
        except (TypeError, ValueError, ValidationError):
            raw, canonical = None, "null"
        assessment_payload = json.loads(json.dumps(asdict(assessment), default=str))
        identity = {
            "proposal_json": canonical,
            "assessment": assessment_payload,
        }
        with self._session_factory.begin() as session:
            if conflict_reason is None:
                session.connection().exec_driver_sql(
                    "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
                )
            task = ObjectiveService._lock_task(session, task_id)
            if task is None:
                raise TaskNotFound(f"Task {task_id} does not exist")
            # Only this operation's K scope can emit a strategy disposition.
            if task.task_type != "propose_strategy":
                raise ValueError("strategy_event_scope_violation")
            prior = session.scalar(
                select(Event)
                .where(
                    Event.task_id == task.id,
                    Event.type.in_(
                        ("strategy_proposal_accepted", "strategy_proposal_rejected")
                    ),
                )
                .order_by(Event.created_at, Event.id)
                .limit(1)
            )
            scope_reason = self._validate_scope(session, task)
            if (
                prior is not None
                and scope_reason is None
                and context_reason is None
                and all(
                    prior.payload.get(key) == value for key, value in identity.items()
                )
                and (
                    prior.payload.get("team_id") == str(task.team_id)
                    and prior.payload.get("objective_id") == str(task.objective_id)
                    and prior.payload.get("policy_version") == task.policy_version
                )
            ):
                return StrategyResult(
                    prior.type == "strategy_proposal_accepted",
                    prior.payload["reason"],
                    prior.id,
                    True,
                )
            reason = (
                scope_reason
                or conflict_reason
                or (
                    "task_outcome_conflict"
                    if prior is not None
                    else self._validate(session, task, raw, assessment)
                )
            )
            payload = {
                "operation": "propose_strategy",
                "objective_id": str(task.objective_id),
                "team_id": str(task.team_id),
                "policy_version": task.policy_version,
                "reason": reason,
                "proposal_hash": hashlib.sha256(canonical.encode()).hexdigest(),
                **identity,
            }
            event = ObjectiveService._add_event(
                session,
                task.id,
                "strategy_proposal_accepted"
                if reason is None
                else "strategy_proposal_rejected",
                payload,
            )
            session.flush()
            return StrategyResult(reason is None, reason, event.id)

    @staticmethod
    def _validate_scope(session: Session, task: Task) -> str | None:
        if task.status != "running":
            return "task_not_running"
        if task.allowed_writes != []:
            return "write_scope_violation"
        if not ObjectiveService._budget_allows_zero_usage(task.budget):
            return "invalid_task_budget"
        team = session.scalar(
            select(Team).where(Team.id == task.team_id).with_for_update(read=True)
        )
        if team is None or team.status != "active":
            return "team_not_active"
        policy = session.scalar(
            select(TeamPolicy)
            .where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
            .with_for_update(read=True)
        )
        if policy is None:
            return "team_policy_missing"
        return None

    def _validate(
        self, session: Session, task: Task, raw: Any, assessment: StateAssessment
    ) -> str | None:
        objective = session.scalar(
            select(Objective).where(Objective.id == task.objective_id).with_for_update()
        )
        if objective is None:
            return "objective_not_found"
        if objective.team_id != task.team_id:
            return "objective_team_mismatch"
        try:
            candidate = StrategyProposal.model_validate(raw)
            candidate_objective = UUID(candidate.objective_id)
        except (ValidationError, ValueError):
            return "invalid_structure"
        referenced = session.scalar(
            select(Objective)
            .where(Objective.id == candidate_objective)
            .with_for_update(read=True)
        )
        if referenced is None:
            return "objective_not_found"
        if referenced.team_id != task.team_id:
            return "objective_team_mismatch"
        if referenced.id != objective.id:
            return "task_objective_mismatch"
        if objective.status != "active":
            return "objective_not_active"
        policy = session.scalar(
            select(TeamPolicy)
            .where(
                TeamPolicy.team_id == task.team_id,
                TeamPolicy.version == task.policy_version,
            )
            .with_for_update(read=True)
        )
        if policy is None:
            return "team_policy_missing"
        structure_reason = self._validate_structure(candidate)
        if structure_reason is not None:
            return structure_reason
        actions = candidate.candidate_actions
        if any(action.task_type != "ingest_source" for action in actions):
            return "unsupported_task_type"
        if any(action.tools for action in actions):
            return "unauthorized_tool"
        sources = policy.rules.get("sources", [])
        if not isinstance(sources, list):
            return "source_not_configured"
        if any(
            not any(
                isinstance(source, dict)
                and source.get("origin_url") == action.origin_url
                and source.get("source_type") == action.source_type
                for source in sources
            )
            for action in actions
        ):
            return "source_not_configured"
        if len(actions) > candidate.constraints.max_tasks:
            return "task_limit_exceeded"
        # The deterministic ingestion capability incurs no model or tool cost.
        if candidate.constraints.max_cost_usd != 0:
            return "budget_escalation"
        if candidate.stop_conditions != ("configured_source_ingested",):
            return "unsupported_stop_condition"
        if (
            assessment.objective.id != objective.id
            or assessment.team.id != task.team_id
        ):
            return "assessment_scope_mismatch"
        try:
            created_at = datetime.fromisoformat(
                assessment.created_at.replace("Z", "+00:00")
            )
        except ValueError:
            return "invalid_assessment_timestamp"
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            return "invalid_assessment_timestamp"
        # Lock mutable basis records before comparing the derived R3 projection.
        list(
            session.scalars(
                select(Task)
                .where(Task.team_id == task.team_id, Task.objective_id == objective.id)
                .order_by(Task.id)
                .with_for_update()
            )
        )
        list(
            session.scalars(
                select(TeamPolicy)
                .where(TeamPolicy.team_id == task.team_id)
                .order_by(TeamPolicy.id)
                .with_for_update(read=True)
            )
        )
        current = self._assessments.build_in_session(
            session, objective.id, created_at=created_at
        )
        if current != assessment:
            return "stale_assessment"
        return None

    @staticmethod
    def _validate_structure(proposal: StrategyProposal) -> str | None:
        visions = proposal.visions
        if not visions:
            return "strategy_requires_vision"
        vision_ids = [vision.id for vision in visions]
        if len(set(vision_ids)) != len(vision_ids):
            return "duplicate_vision_id"
        workstreams = [
            workstream for vision in visions for workstream in vision.workstreams
        ]
        workstream_ids = [workstream.id for workstream in workstreams]
        if len(set(workstream_ids)) != len(workstream_ids):
            return "duplicate_workstream_id"
        actions = [
            action for workstream in workstreams for action in workstream.actions
        ]
        action_ids = [action.id for action in actions]
        if len(set(action_ids)) != len(action_ids):
            return "duplicate_action_id"
        known = set(action_ids)
        graph: dict[UUID, tuple[UUID, ...]] = {}
        for action in actions:
            if len(set(action.prerequisites)) != len(action.prerequisites):
                return "duplicate_dependency"
            if action.id in action.prerequisites:
                return "self_dependency"
            if any(target not in known for target in action.prerequisites):
                return "dependency_target_not_found"
            graph[action.id] = action.prerequisites
        visiting: set[UUID] = set()
        visited: set[UUID] = set()

        def visit(action_id: UUID) -> bool:
            if action_id in visiting:
                return False
            if action_id in visited:
                return True
            visiting.add(action_id)
            if not all(visit(target) for target in graph[action_id]):
                return False
            visiting.remove(action_id)
            visited.add(action_id)
            return True

        return (
            None if all(visit(action_id) for action_id in graph) else "dependency_cycle"
        )

    def reconstruct(self, event_id: UUID) -> StrategyProposal:
        with self._session_factory() as session:
            return self.reconstruct_in_session(session, event_id)

    @staticmethod
    def reconstruct_in_session(session: Session, event_id: UUID) -> StrategyProposal:
        event = session.get(Event, event_id)
        if event is None or event.type != "strategy_proposal_accepted":
            raise ValueError("accepted_proposal_not_found")
        payload = event.payload
        canonical = payload.get("proposal_json")
        if isinstance(payload.get("proposal_json"), str):
            canonical = payload["proposal_json"]
            if hashlib.sha256(canonical.encode()).hexdigest() != payload.get(
                "proposal_hash"
            ):
                raise ValueError("proposal_hash_mismatch")
            try:
                proposal = StrategyProposal.model_validate_json(canonical)
                if _canonical_json(proposal.canonical_dump()) != canonical:
                    raise ValueError("noncanonical_proposal_json")
                if payload.get("objective_id") != proposal.objective_id:
                    raise ValueError("proposal_scope_mismatch")
                if StrategyService._validate_structure(proposal) is not None:
                    raise ValueError("invalid_proposal_structure")
                return proposal
            except (ValidationError, ValueError) as error:
                raise ValueError("invalid_proposal_provenance") from error
        raise ValueError("canonical_proposal_not_found")

    def reconstruct_historical(self, event_id: UUID) -> HistoricalStrategyRead:
        with self._session_factory() as session:
            return self.reconstruct_historical_in_session(session, event_id)

    @staticmethod
    def reconstruct_historical_in_session(
        session: Session, event_id: UUID
    ) -> HistoricalStrategyRead:
        event = session.get(Event, event_id)
        if event is None or event.type != "strategy_proposal_accepted":
            raise ValueError("accepted_proposal_not_found")
        payload = event.payload
        legacy = payload.get("proposal")
        if not isinstance(legacy, dict) or "candidate_actions" not in legacy:
            raise ValueError("historical_flat_proposal_not_found")
        digest = hashlib.sha256(_canonical_json(legacy).encode()).hexdigest()
        stored_hash = payload.get("proposal_hash")
        if stored_hash != f"sha256:{digest}":
            raise ValueError("proposal_hash_mismatch")
        try:
            return HistoricalStrategyRead(
                record=LegacyStrategyRecord.model_validate(legacy),
                event_id=event.id,
                event_task_id=event.task_id,
                event_objective_id=str(payload.get("objective_id", "")),
                event_team_id=str(payload.get("team_id", "")),
                event_proposal_hash=stored_hash,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise ValueError("invalid_proposal_provenance") from error
