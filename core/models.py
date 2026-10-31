"""Minimal persistence mappings for the K1 ingestion path."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core.vector_type import Vector


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)


class TeamPolicy(Base):
    __tablename__ = "team_policies"
    __table_args__ = (
        UniqueConstraint("team_id", "version", name="uq_team_policies_team_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class Objective(Base):
    __tablename__ = "objectives"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'blocked', "
            "'completed', 'cancelled')",
            name="ck_objectives_status",
        ),
        UniqueConstraint("id", "team_id", name="uq_objectives_id_team"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    statement: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="draft", server_default="draft"
    )


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["objective_id", "team_id"],
            ["objectives.id", "objectives.team_id"],
            name="fk_plans_objective_team",
        ),
        UniqueConstraint("id", "team_id", name="uq_plans_id_team"),
        UniqueConstraint("id", "objective_id", name="uq_plans_id_objective"),
        UniqueConstraint("accepted_event_id", name="uq_plans_accepted_event"),
        UniqueConstraint("created_by_task_id", name="uq_plans_created_by_task"),
        CheckConstraint(
            "status IN ('active', 'completed', 'stopped')", name="ck_plans_status"
        ),
        CheckConstraint(
            "stopped_reason IS NULL OR "
            "stopped_reason IN ('abandoned', 'invalidated', 'superseded')",
            name="ck_plans_stopped_reason",
        ),
        CheckConstraint(
            "(status = 'stopped' AND stopped_reason IS NOT NULL AND "
            "((stopped_reason = 'superseded' AND successor_plan_id IS NOT NULL "
            "AND successor_plan_id <> id) OR "
            "(stopped_reason <> 'superseded' AND successor_plan_id IS NULL))) OR "
            "(status <> 'stopped' AND stopped_reason IS NULL AND "
            "successor_plan_id IS NULL)",
            name="ck_plans_lifecycle_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    objective_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_by_task_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    accepted_event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("events.id"), nullable=False
    )
    proposal_hash: Mapped[str] = mapped_column(String, nullable=False)
    assessment_basis: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    assessment_created_at: Mapped[str] = mapped_column(String, nullable=False)
    budget: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    completion_condition: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="active", server_default="active"
    )
    stopped_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    successor_plan_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("plans.id", name="fk_plans_successor"),
        nullable=True,
    )


class PlanAction(Base):
    __tablename__ = "plan_actions"
    __table_args__ = (
        ForeignKeyConstraint(["plan_id"], ["plans.id"], name="fk_plan_actions_plan"),
        UniqueConstraint("plan_id", "action_id", name="uq_plan_actions_plan_action"),
    )

    plan_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    action_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    action: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["team_id", "policy_version"],
            ["team_policies.team_id", "team_policies.version"],
            name="fk_tasks_team_policy_version",
        ),
        ForeignKeyConstraint(
            ["objective_id", "team_id"],
            ["objectives.id", "objectives.team_id"],
            name="fk_tasks_objective_team",
        ),
        ForeignKeyConstraint(
            ["plan_id", "team_id"],
            ["plans.id", "plans.team_id"],
            name="fk_tasks_plan_team",
        ),
        ForeignKeyConstraint(
            ["plan_id", "objective_id"],
            ["plans.id", "plans.objective_id"],
            name="fk_tasks_plan_objective",
        ),
        ForeignKeyConstraint(
            ["plan_id", "plan_action_id"],
            ["plan_actions.plan_id", "plan_actions.action_id"],
            name="fk_tasks_plan_action",
        ),
        UniqueConstraint("plan_id", "plan_action_id", name="uq_tasks_plan_action"),
        UniqueConstraint("id", "team_id", name="uq_tasks_id_team"),
        CheckConstraint(
            "(plan_id IS NULL) = (plan_action_id IS NULL)",
            name="ck_tasks_plan_action_pair",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
    policy_version: Mapped[int] = mapped_column(nullable=False)
    objective_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    plan_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    plan_action_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    allowed_writes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    budget: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    max_attempts: Mapped[int] = mapped_column(
        nullable=False, default=3, server_default="3"
    )


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint(
            "content_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_signals_content_hash",
        ),
        UniqueConstraint(
            "origin_url", "content_hash", name="uq_signals_origin_content_hash"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    origin_url: Mapped[str] = mapped_column(String, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    snapshot_ref: Mapped[str] = mapped_column(String, nullable=False)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_task_id_type", "task_id", "type"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    task_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class TaskGenerationCharge(Base):
    """One durable provider-cost reservation/reconciliation per Task attempt."""

    __tablename__ = "task_generation_charges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name="fk_task_generation_charges_task",
        ),
        UniqueConstraint(
            "task_id",
            "attempt_count",
            "operation",
            name="uq_task_generation_charges_attempt_operation",
        ),
        CheckConstraint(
            "attempt_count > 0 AND max_input_tokens >= 0 "
            "AND max_output_tokens > 0",
            name="ck_task_generation_charges_token_bounds",
        ),
        CheckConstraint(
            "reserved_cost_usd > 0 AND "
            "(accounted_cost_usd IS NULL OR accounted_cost_usd >= 0)",
            name="ck_task_generation_charges_costs",
        ),
        CheckConstraint(
            "length(provider) > 0 AND length(model) > 0 "
            "AND length(pricing_revision) > 0 AND length(operation) > 0",
            name="ck_task_generation_charges_identity",
        ),
        CheckConstraint(
            "(status = 'reserved' AND accounted_cost_usd IS NULL "
            "AND input_tokens IS NULL AND output_tokens IS NULL "
            "AND settled_at IS NULL AND failure_reason IS NULL) OR "
            "(status = 'unknown' AND accounted_cost_usd IS NULL "
            "AND input_tokens IS NULL AND output_tokens IS NULL "
            "AND settled_at IS NOT NULL AND failure_reason IS NOT NULL) OR "
            "(status IN ('reconciled', 'overrun') "
            "AND accounted_cost_usd IS NOT NULL "
            "AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL "
            "AND settled_at IS NOT NULL)",
            name="ck_task_generation_charges_state",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_task_generation_charges_input_tokens",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_task_generation_charges_output_tokens",
        ),
        CheckConstraint(
            "status IN ('reserved', 'reconciled', 'unknown', 'overrun')",
            name="ck_task_generation_charges_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    task_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(nullable=False)
    operation: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    pricing_revision: Mapped[str] = mapped_column(String, nullable=False)
    max_input_tokens: Mapped[int] = mapped_column(nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(nullable=False)
    input_usd_per_million_tokens: Mapped[Decimal] = mapped_column(
        Numeric(12, 9), nullable=False
    )
    output_usd_per_million_tokens: Mapped[Decimal] = mapped_column(
        Numeric(12, 9), nullable=False
    )
    reserved_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 12), nullable=False
    )
    accounted_cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 12), nullable=True
    )
    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Outcome(Base):
    __tablename__ = "outcomes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["recorded_by_task_id", "team_id"],
            ["tasks.id", "tasks.team_id"],
            name="fk_outcomes_task_team",
        ),
        UniqueConstraint(
            "recorded_by_task_id", "outcome_type", name="uq_outcomes_task_type"
        ),
        CheckConstraint(
            "(outcome_type = 'prediction_registered' "
            "AND observation_snapshot_ref IS NULL "
            "AND observation_hash IS NULL "
            "AND observed_at IS NULL) OR "
            "(outcome_type <> 'prediction_registered' "
            "AND observation_snapshot_ref IS NOT NULL "
            "AND observation_hash IS NOT NULL "
            "AND observed_at IS NOT NULL)",
            name="ck_outcomes_observation_state",
        ),
        CheckConstraint(
            "outcome_type <> 'prediction_registered' OR expected IS NOT NULL",
            name="ck_outcomes_expected_present",
        ),
        CheckConstraint(
            "observation_snapshot_ref IS NULL OR "
            "observation_snapshot_ref ~ '^snap://sha256/[0-9a-f]{64}$'",
            name="ck_outcomes_observation_ref",
        ),
        CheckConstraint(
            "observation_hash IS NULL OR "
            "observation_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_outcomes_observation_hash",
        ),
        CheckConstraint(
            "observation_snapshot_ref IS NULL OR observation_hash IS NULL OR "
            "split_part(observation_snapshot_ref, '/', 4) = "
            "split_part(observation_hash, ':', 2)",
            name="ck_outcomes_observation_pair",
        ),
        CheckConstraint(
            "outcome_type <> 'task_execution' OR "
            "(subject_kind = 'task' AND subject_id = recorded_by_task_id)",
            name="ck_outcomes_task_execution_subject",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    subject_kind: Mapped[str] = mapped_column(String, nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    outcome_type: Mapped[str] = mapped_column(String, nullable=False)
    expected: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    observation_snapshot_ref: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    observation_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recorded_by_task_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )



class KnowledgeChunk(Base):
    """Derived chunk and embedding projection for a canonical Signal Snapshot."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "signal_id",
            "chunk_index",
            "embedding_space_key",
            name="uq_knowledge_chunks_signal_index_space",
        ),
        CheckConstraint("chunk_index >= 0", name="ck_knowledge_chunks_chunk_index"),
        CheckConstraint(
            "chunk_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_chunks_chunk_hash",
        ),
        CheckConstraint(
            "source_content_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_chunks_source_hash",
        ),
        CheckConstraint(
            "source_snapshot_ref ~ '^snap://sha256/[0-9a-f]{64}$'",
            name="ck_knowledge_chunks_source_snapshot_ref",
        ),
        CheckConstraint(
            "embedding_dimensions > 0 AND "
            "vector_dims(embedding) = embedding_dimensions",
            name="ck_knowledge_chunks_embedding_dimensions",
        ),
        CheckConstraint(
            "embedding_space_key ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_chunks_embedding_space_key",
        ),
        CheckConstraint(
            "length(chunking_version) > 0 AND "
            "length(embedding_configuration) > 0",
            name="ck_knowledge_chunks_configuration_nonempty",
        ),
        Index(
            "ix_knowledge_chunks_space_signal",
            "embedding_space_key",
            "signal_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    signal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("signals.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_hash: Mapped[str] = mapped_column(String, nullable=False)
    source_snapshot_ref: Mapped[str] = mapped_column(String, nullable=False)
    source_content_hash: Mapped[str] = mapped_column(String, nullable=False)
    chunking_version: Mapped[str] = mapped_column(String, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String, nullable=False)
    embedding_revision: Mapped[str] = mapped_column(String, nullable=False)
    embedding_configuration: Mapped[str] = mapped_column(String, nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(nullable=False)
    embedding_space_key: Mapped[str] = mapped_column(String, nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
