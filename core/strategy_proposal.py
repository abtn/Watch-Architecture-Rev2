"""Transient R4 candidates and a deterministic producer with no write capability."""

from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr

from core.state_assessment import StateAssessment

Text = Annotated[StrictStr, Field(min_length=1, pattern=r"\S")]


class CandidateAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_type: Text
    purpose: Text
    origin_url: Text
    source_type: Text
    tools: tuple[StrictStr, ...] = ()


class StrategyConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tasks: Annotated[StrictInt, Field(ge=1)]
    max_cost_usd: Annotated[StrictFloat, Field(ge=0, allow_inf_nan=False)]


class StrategyProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    objective_id: Text
    approach: Text
    reason: Text
    candidate_actions: Annotated[tuple[CandidateAction, ...], Field(min_length=1)]
    constraints: StrategyConstraints
    stop_conditions: Annotated[tuple[Text, ...], Field(min_length=1)]


@dataclass(frozen=True)
class StrategyContext:
    task_id: str
    assessment: StateAssessment


class FakeStrategyWorker:
    def propose(self, context: StrategyContext) -> StrategyProposal:
        import json

        policy = next(
            policy
            for policy in context.assessment.policies
            if policy.version
            == next(
                task.policy_version
                for task in context.assessment.tasks
                if str(task.id) == context.task_id
            )
        )
        source = json.loads(policy.rules_json)["sources"][0]
        return StrategyProposal(
            objective_id=str(context.assessment.objective.id),
            approach="gather_configured_source",
            reason="Gather source material for the Objective without executing a Plan.",
            candidate_actions=(
                CandidateAction(
                    task_type="ingest_source",
                    purpose="Gather configured source material",
                    origin_url=source["origin_url"],
                    source_type=source["source_type"],
                ),
            ),
            constraints=StrategyConstraints(max_tasks=1, max_cost_usd=0.0),
            stop_conditions=("configured_source_ingested",),
        )
