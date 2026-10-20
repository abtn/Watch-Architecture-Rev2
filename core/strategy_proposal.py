"""Transient R4 candidates and a deterministic producer with no write capability."""

import json
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from core.state_assessment import StateAssessment

Text = Annotated[StrictStr, Field(min_length=1, pattern=r"\S")]


def _canonical_legacy(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


class IntendedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    purpose: Text
    prerequisites: tuple[UUID, ...] = ()
    task_type: Text = "ingest_source"
    origin_url: Text
    source_type: Text
    tools: tuple[StrictStr, ...] = ()


class Workstream(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: Text
    purpose: Text
    actions: Annotated[tuple[IntendedAction, ...], Field(min_length=1)]


class Vision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: Text
    scope: Text
    boundary: Text
    workstreams: Annotated[tuple[Workstream, ...], Field(min_length=1)]


class CandidateAction(BaseModel):
    """Derived view consumed by paused R5 and historical audit translation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    task_type: Text
    purpose: Text
    origin_url: Text | None = None
    source_type: Text | None = None
    tools: tuple[StrictStr, ...] = ()
    vision_id: UUID
    workstream_id: UUID
    prerequisites: tuple[UUID, ...] = ()


class HistoricalCandidateAction(BaseModel):
    """Hash-verifiable projection of a legacy flat candidate action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_type: Text
    purpose: Text
    origin_url: Text | None = None
    source_type: Text | None = None
    tools: tuple[StrictStr, ...] = ()


class HistoricalStrategyConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tasks: Annotated[StrictInt, Field(ge=1)]
    max_cost_usd: Annotated[StrictFloat, Field(ge=0, allow_inf_nan=False)]


class LegacyStrategyRecord(BaseModel):
    """Immutable validated view of the fields actually present in an old R4 Event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    objective_id: Text
    approach: Text
    reason: Text
    candidate_actions: Annotated[
        tuple[HistoricalCandidateAction, ...], Field(min_length=1)
    ]
    constraints: HistoricalStrategyConstraints
    stop_conditions: Annotated[tuple[Text, ...], Field(min_length=1)]
    task_id: UUID | None = None
    assessment_basis: dict[str, Any] | None = None


@dataclass(frozen=True)
class HistoricalStrategyRead:
    """Legacy proposal preserved as recorded; normalized data is explicitly derived."""

    record: LegacyStrategyRecord
    event_id: UUID
    event_task_id: UUID
    event_objective_id: str
    event_team_id: str
    event_proposal_hash: str

    def normalized_view(self) -> "StrategyProposal":
        return StrategyProposal.from_historical_audit(self)


class StrategyConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_tasks: Annotated[StrictInt, Field(ge=1)]
    max_cost_usd: Annotated[StrictFloat, Field(ge=0, allow_inf_nan=False)]


class StrategyProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    objective_id: Text
    approach: Text
    reason: Text
    visions: Annotated[tuple[Vision, ...], Field(min_length=1)]
    constraints: StrategyConstraints
    stop_conditions: Annotated[tuple[Text, ...], Field(min_length=1)]

    @property
    def candidate_actions(self) -> tuple[CandidateAction, ...]:
        flattened = (
            CandidateAction(
                id=action.id,
                purpose=action.purpose,
                task_type=action.task_type,
                origin_url=action.origin_url or "",
                source_type=action.source_type or "",
                tools=action.tools,
                vision_id=vision.id,
                workstream_id=workstream.id,
                prerequisites=action.prerequisites,
            )
            for vision in self.visions
            for workstream in vision.workstreams
            for action in workstream.actions
        )
        return tuple(sorted(flattened, key=lambda item: str(item.id)))

    def canonical_dump(self) -> dict[str, object]:
        value = self.model_dump(mode="json")
        value["visions"] = sorted(value["visions"], key=lambda item: item["id"])
        for vision in value["visions"]:
            vision["workstreams"] = sorted(
                vision["workstreams"], key=lambda item: item["id"]
            )
            for workstream in vision["workstreams"]:
                workstream["actions"] = sorted(
                    workstream["actions"], key=lambda item: item["id"]
                )
                for action in workstream["actions"]:
                    action["prerequisites"] = sorted(action["prerequisites"])
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_flat_actions(cls, value: object) -> object:
        if isinstance(value, dict) and "candidate_actions" in value:
            raise ValueError("use_nested_visions_workstreams_actions")
        return value

    @classmethod
    def from_historical_audit(
        cls, historical: HistoricalStrategyRead
    ) -> "StrategyProposal":
        """Derive a compatibility projection; never represent it as historical fact."""
        old = historical.record
        identity_seed = f"{historical.event_id}:{historical.event_proposal_hash}"
        generated = tuple(
            IntendedAction(
                id=uuid5(
                    NAMESPACE_URL,
                    f"watch:r4:legacy:{identity_seed}:action:{index}:"
                    f"{_canonical_legacy(item.model_dump(mode='json'))}",
                ),
                purpose=item.purpose,
                task_type=item.task_type,
                origin_url=item.origin_url or "historical:unspecified",
                source_type=item.source_type or "historical:unspecified",
            )
            for index, item in enumerate(old.candidate_actions)
        )
        scope = f"watch:r4:legacy:{identity_seed}"
        vision = Vision(
            id=uuid5(NAMESPACE_URL, f"{scope}:derived-vision"),
            name="Derived legacy grouping",
            scope="No Vision scope was present in the historical record.",
            boundary=(
                "This normalized grouping is compatibility data, not historical fact."
            ),
            workstreams=(
                Workstream(
                    id=uuid5(NAMESPACE_URL, f"{scope}:derived-workstream"),
                    name="Derived legacy work grouping",
                    purpose="Groups recorded flat Actions for compatibility only.",
                    actions=generated,
                ),
            ),
        )
        return cls(
            objective_id=old.objective_id,
            approach=old.approach,
            reason=old.reason,
            visions=(vision,),
            constraints=StrategyConstraints(
                max_tasks=old.constraints.max_tasks,
                max_cost_usd=old.constraints.max_cost_usd,
            ),
            stop_conditions=old.stop_conditions,
        ).canonicalized()

    def canonicalized(self) -> "StrategyProposal":
        return StrategyProposal.model_validate(self.canonical_dump())


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
        objective_id = context.assessment.objective.id
        strategy_scope = f"watch:r4:{context.task_id}:{context.assessment.basis.sha256}"
        vision_id = uuid5(NAMESPACE_URL, f"{strategy_scope}:vision:configured-source")
        workstream_id = uuid5(
            NAMESPACE_URL, f"{strategy_scope}:workstream:configured-source"
        )
        action_id = uuid5(NAMESPACE_URL, f"{strategy_scope}:action:configured-source")
        return StrategyProposal(
            objective_id=str(objective_id),
            approach="gather_configured_source",
            reason="Gather source material for the Objective without executing a Plan.",
            visions=(
                Vision(
                    id=vision_id,
                    name="Configured source",
                    scope="Gather material from the configured source.",
                    boundary="Does not poll or execute ingestion.",
                    workstreams=(
                        Workstream(
                            id=workstream_id,
                            name="Gather configured source",
                            purpose="Prepare one bounded source-ingestion action.",
                            actions=(
                                IntendedAction(
                                    id=action_id,
                                    purpose="Gather configured source material",
                                    task_type="ingest_source",
                                    origin_url=source["origin_url"],
                                    source_type=source["source_type"],
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            constraints=StrategyConstraints(max_tasks=1, max_cost_usd=0.0),
            stop_conditions=("configured_source_ingested",),
        )
