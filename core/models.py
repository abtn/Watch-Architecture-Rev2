"""Minimal persistence mappings for the K1 ingestion path."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
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
        CheckConstraint(
            "schema_version IN (1, 2)",
            name="ck_team_policies_schema_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[int] = mapped_column(
        nullable=False, default=1, server_default="1"
    )


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
        UniqueConstraint("id", "team_id", name="uq_outcomes_id_team"),
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

class TeamExperienceChunk(Base):
    """Rebuildable projection for one accepted canonical KnowledgeItem version."""

    __tablename__ = "team_experience_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_item_id", "team_id"],
            ["knowledge_items.id", "knowledge_items.team_id"],
            name="fk_team_experience_chunks_item_team",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["origin_learning_change_id", "team_id"],
            ["learning_changes.id", "learning_changes.team_id"],
            name="fk_team_experience_chunks_learning_change_team",
        ),
        UniqueConstraint(
            "knowledge_item_id",
            "item_version",
            "chunk_index",
            "embedding_space_key",
            name="uq_team_experience_chunks_item_index_space",
        ),
        CheckConstraint(
            "item_version > 0 AND chunk_index >= 0",
            name="ck_team_experience_chunks_item_chunk",
        ),
        CheckConstraint(
            "item_content_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "chunk_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_team_experience_chunks_hashes",
        ),
        CheckConstraint(
            "embedding_dimensions > 0 AND "
            "vector_dims(embedding) = embedding_dimensions",
            name="ck_team_experience_chunks_embedding_dimensions",
        ),
        CheckConstraint(
            "embedding_space_key ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_team_experience_chunks_embedding_space_key",
        ),
        CheckConstraint(
            "length(chunking_version) > 0 AND "
            "length(embedding_configuration) > 0",
            name="ck_team_experience_chunks_configuration",
        ),
        Index(
            "ix_team_experience_chunks_team_space_item",
            "team_id",
            "embedding_space_key",
            "knowledge_item_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    knowledge_item_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    team_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    item_version: Mapped[int] = mapped_column(nullable=False)
    item_content_hash: Mapped[str] = mapped_column(String, nullable=False)
    origin_learning_change_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_hash: Mapped[str] = mapped_column(String, nullable=False)
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


class TeamExperienceIndexState(Base):
    """Operational publication state for one canonical Team Experience item."""

    __tablename__ = "team_experience_index_state"
    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_item_id", "team_id"],
            ["knowledge_items.id", "knowledge_items.team_id"],
            name="fk_team_experience_index_state_item_team",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["origin_learning_change_id", "team_id"],
            ["learning_changes.id", "learning_changes.team_id"],
            name="fk_team_experience_index_state_learning_change_team",
        ),
        UniqueConstraint(
            "knowledge_item_id",
            "team_id",
            name="uq_team_experience_index_state_item_team",
        ),
        CheckConstraint(
            "status IN ('stale', 'published', 'ineligible')",
            name="ck_team_experience_index_state_status",
        ),
        CheckConstraint(
            "item_version > 0 AND attempt_count >= 0 AND chunk_count >= 0",
            name="ck_team_experience_index_state_counts",
        ),
        CheckConstraint(
            "item_content_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_team_experience_index_state_item_hash",
        ),
        CheckConstraint(
            "embedding_space_key IS NULL OR "
            "embedding_space_key ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_team_experience_index_state_space_key",
        ),
        Index(
            "ix_team_experience_index_state_team_status",
            "team_id",
            "status",
            "knowledge_item_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    knowledge_item_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    team_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    item_version: Mapped[int] = mapped_column(nullable=False)
    item_content_hash: Mapped[str] = mapped_column(String, nullable=False)
    origin_learning_change_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    embedding_space_key: Mapped[str | None] = mapped_column(String, nullable=True)
    chunk_count: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
    attempt_count: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
    last_error_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LearningChange(Base):
    """Evidence-backed proposal or durable learning disposition."""
    __tablename__ = "learning_changes"
    __table_args__ = (
        ForeignKeyConstraint(["proposed_by_task_id", "team_id"], ["tasks.id",
            "tasks.team_id"], name="fk_learning_changes_proposed_task_team"),
        ForeignKeyConstraint(["committed_by_task_id", "team_id"], ["tasks.id",
            "tasks.team_id"], name="fk_learning_changes_committed_task_team"),
        UniqueConstraint("id", "team_id", name="uq_learning_changes_id_team"),
        UniqueConstraint("proposed_by_task_id", "idempotency_key",
            name="uq_learning_changes_task_idempotency"),
        CheckConstraint("target_kind = 'knowledge_item'",
            name="ck_learning_changes_target_kind"),
        CheckConstraint("operation IN ('create', 'revise', 'revalidate', 'supersede', 'retire')",
            name="ck_learning_changes_operation"),
        CheckConstraint("(operation = 'create' AND target_id IS NULL) "
            "OR (operation IN ('revise', 'revalidate', 'supersede', 'retire') AND "
            "target_id IS NOT NULL)", name="ck_learning_changes_target_state"),
        CheckConstraint("status IN ('proposed', 'accepted', 'rejected')",
            name="ck_learning_changes_status"),
        CheckConstraint("evidence_basis_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_learning_changes_evidence_basis_hash"),
        CheckConstraint("length(idempotency_key) > 0 AND "
            "jsonb_typeof(proposed_state) = 'object' AND "
            "jsonb_typeof(evidence_basis) = 'array'",
            name="ck_learning_changes_payload_shape"),
        CheckConstraint(
            "(status = 'proposed' AND "
                "committed_by_task_id IS NULL AND operator_id "
                "IS NULL AND committed_at IS NULL AND "
                "committed_state IS NULL) OR "
            "(status = 'accepted' AND "
                "committed_by_task_id IS NOT NULL AND "
                "operator_id IS NOT NULL AND "
                "length(operator_id) > 0 AND committed_at IS "
                "NOT NULL AND committed_state IS NOT NULL) OR "
                ""
            "(status = 'rejected' AND "
                "committed_by_task_id IS NOT NULL AND "
                "operator_id IS NOT NULL AND "
                "length(operator_id) > 0 AND committed_at IS "
                "NOT NULL AND committed_state IS NULL AND "
                "decision_reason IS NOT NULL AND "
                "length(decision_reason) > 0)",
            name="ck_learning_changes_disposition",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),
        ForeignKey("teams.id"), nullable=False)
    target_kind: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    operation: Mapped[str] = mapped_column(String, nullable=False)
    proposed_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    previous_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    committed_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    evidence_basis: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    evidence_basis_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="proposed",
        server_default="proposed")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    proposed_by_task_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),
        nullable=False)
    committed_by_task_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True),
        nullable=True)
    operator_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        nullable=False, server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
        nullable=True)


class KnowledgeItem(Base):
    """Canonical versioned Team Experience; embeddings belong in projections."""
    __tablename__ = "knowledge_items"
    __table_args__ = (
        ForeignKeyConstraint(["origin_learning_change_id", "team_id"],
            ["learning_changes.id", "learning_changes.team_id"],
            name="fk_knowledge_items_origin_learning_change_team"),
        ForeignKeyConstraint(["current_learning_change_id", "team_id"],
            ["learning_changes.id", "learning_changes.team_id"],
            name="fk_knowledge_items_current_learning_change_team"),
        ForeignKeyConstraint(["supersedes_item_id", "team_id"],
            ["knowledge_items.id", "knowledge_items.team_id"],
            name="fk_knowledge_items_supersedes_team"),
        ForeignKeyConstraint(["superseded_by_id", "team_id"],
            ["knowledge_items.id", "knowledge_items.team_id"],
            name="fk_knowledge_items_superseded_by_team"),
        CheckConstraint("kind IN ('practice', 'pattern', 'method', 'playbook')",
            name="ck_knowledge_items_kind"),
        CheckConstraint("status IN ('active', 'needs_review', 'retired')",
            name="ck_knowledge_items_status"),
        CheckConstraint("version >= 1 AND confidence >= 0 AND confidence <= 1",
            name="ck_knowledge_items_version_confidence"),
        CheckConstraint("(supersedes_item_id IS NULL OR supersedes_item_id <> id) "
            "AND (superseded_by_id IS NULL OR superseded_by_id <> id)",
            name="ck_knowledge_items_no_self_supersession"),
        CheckConstraint("length(title) > 0 AND length(statement) > 0 "
            "AND length(body) > 0", name="ck_knowledge_items_content"),
        CheckConstraint(
            "jsonb_typeof(applicability) = 'object' AND "
                "jsonb_typeof(preconditions) = 'array' AND "
            "jsonb_typeof(assumptions) = 'array' AND "
                "jsonb_typeof(limitations) = 'array' AND "
            "jsonb_typeof(non_applicability) = 'array' "
                "AND jsonb_typeof(failure_modes) = 'array' "
                "AND "
            "jsonb_typeof(known_counterexamples) = "
                "'array' AND "
                "jsonb_typeof(missing_information) = 'array' "
                "AND "
            "jsonb_typeof(uncertainty) = 'array'",
            name="ck_knowledge_items_payload_shape",
        ),
        UniqueConstraint("id", "team_id", name="uq_knowledge_items_id_team"),
        UniqueConstraint("current_learning_change_id",
            name="uq_knowledge_items_current_learning_change"),
        UniqueConstraint("superseded_by_id", name="uq_knowledge_items_superseded_by"),
        Index("uq_knowledge_items_pending_candidate", "supersedes_item_id",
            unique=True, postgresql_where=sa.text(
                "supersedes_item_id IS NOT NULL AND status <> 'retired'"
            )),
        Index("ix_knowledge_items_team_status", "team_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),
        ForeignKey("teams.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    applicability: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    preconditions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    assumptions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    limitations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    non_applicability: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    failure_modes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    known_counterexamples: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    missing_information: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    uncertainty: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active",
        server_default="active")
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # noqa: E501
    review_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
        nullable=True)
    origin_learning_change_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),
        nullable=False)
    current_learning_change_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    supersedes_item_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    superseded_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        nullable=False, server_default=func.now())


class Evaluation(Base):
    """An attributable assessment of one immutable Outcome."""
    __tablename__ = "evaluations"
    __table_args__ = (
        ForeignKeyConstraint(["outcome_id", "team_id"], ["outcomes.id",
            "outcomes.team_id"], name="fk_evaluations_outcome_team"),
        ForeignKeyConstraint(["created_by_task_id", "team_id"], ["tasks.id",
            "tasks.team_id"], name="fk_evaluations_created_task_team"),
        ForeignKeyConstraint(["resolved_by_task_id", "team_id"], ["tasks.id",
            "tasks.team_id"], name="fk_evaluations_resolved_task_team"),
        CheckConstraint("conclusion IN ('worked', 'mixed', 'failed', "
            "'inconclusive')", name="ck_evaluations_conclusion"),
        CheckConstraint("evaluator_kind IN ('rule', 'human', 'model')",
            name="ck_evaluations_evaluator_kind"),
        CheckConstraint("status IN ('proposed', 'recorded', 'rejected')",
            name="ck_evaluations_status"),
        CheckConstraint("length(evaluator_identity) > 0 AND "
            "length(evaluator_revision) > 0 AND "
            "length(idempotency_key) > 0 AND "
            "proposal_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "jsonb_typeof(findings) = 'object'", name="ck_evaluations_payload"),
        CheckConstraint(
            "(status = 'proposed' AND resolved_by_task_id "
                "IS NULL AND resolved_at IS NULL AND "
                "rejection_reason IS NULL) OR "
            "(status = 'recorded' AND resolved_by_task_id "
                "IS NOT NULL AND resolved_at IS NOT NULL AND "
                "rejection_reason IS NULL) OR "
            "(status = 'rejected' AND resolved_by_task_id "
                "IS NOT NULL AND resolved_at IS NOT NULL AND "
                "rejection_reason IS NOT NULL AND "
                "length(rejection_reason) > 0)",
            name="ck_evaluations_disposition",
        ),
        UniqueConstraint("id", "team_id", name="uq_evaluations_id_team"),
        UniqueConstraint("created_by_task_id", "idempotency_key",
            name="uq_evaluations_task_idempotency"),
        Index("ix_evaluations_team_outcome_status", "team_id", "outcome_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),
        ForeignKey("teams.id"), nullable=False)
    outcome_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conclusion: Mapped[str] = mapped_column(String, nullable=False)
    findings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    evaluator_kind: Mapped[str] = mapped_column(String, nullable=False)
    evaluator_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    evaluator_revision: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="proposed",
        server_default="proposed")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    proposal_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_by_task_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resolved_by_task_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True),
        nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
        nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvidenceLink(Base):
    """Evaluation-scoped link to a same-Team Outcome or domain Signal."""
    __tablename__ = "evidence_links"
    __table_args__ = (
        ForeignKeyConstraint(["subject_id", "team_id"], ["evaluations.id",
            "evaluations.team_id"], name="fk_evidence_links_evaluation_team"),
        ForeignKeyConstraint(["outcome_id", "team_id"], ["outcomes.id",
            "outcomes.team_id"], name="fk_evidence_links_outcome_team"),
        CheckConstraint("subject_kind = 'evaluation'",
            name="ck_evidence_links_subject_kind"),
        CheckConstraint(
            "(source_kind = 'outcome' AND outcome_id IS "
                "NOT NULL AND signal_id IS NULL) OR "
            "(source_kind = 'signal' AND signal_id IS NOT NULL AND outcome_id IS NULL)",
            name="ck_evidence_links_source",
        ),
        CheckConstraint("stance IN ('supports', 'challenges', 'mentions')",
            name="ck_evidence_links_stance"),
        CheckConstraint(
            "(snapshot_ref IS NULL AND snapshot_hash IS NULL) OR "
            "(snapshot_ref IS NOT NULL AND snapshot_hash "
                "IS NOT NULL AND snapshot_ref ~ "
                "'^snap://sha256/[0-9a-f]{64}$' "
            "AND snapshot_hash ~ '^sha256:[0-9a-f]{64}$' "
                "AND split_part(snapshot_ref, '/', 4) = "
                "split_part(snapshot_hash, ':', 2))",
            name="ck_evidence_links_snapshot_pair",
        ),
        CheckConstraint(
            "(quote_text IS NULL AND quote_start IS NULL AND quote_end IS NULL) OR "
            "(quote_text IS NOT NULL AND quote_start IS "
                "NOT NULL AND quote_end IS NOT NULL AND "
                "quote_start >= 0 AND quote_end > "
                "quote_start)",
            name="ck_evidence_links_quote_offsets",
        ),
        CheckConstraint("length(reference_key) > 0",
            name="ck_evidence_links_reference_key"),
        UniqueConstraint("subject_id", "reference_key",
            name="uq_evidence_links_subject_reference"),
        Index("ix_evidence_links_team_source", "team_id", "source_kind",
            "outcome_id", "signal_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),
        ForeignKey("teams.id"), nullable=False)
    subject_kind: Mapped[str] = mapped_column(String, nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_kind: Mapped[str] = mapped_column(String, nullable=False)
    outcome_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    signal_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    snapshot_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    snapshot_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    stance: Mapped[str] = mapped_column(String, nullable=False)
    quote_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote_start: Mapped[int | None] = mapped_column(nullable=True)
    quote_end: Mapped[int | None] = mapped_column(nullable=True)
    reference_key: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        nullable=False, server_default=func.now())


class KnowledgeQualityAssessment(Base):
    """Immutable, evidence-bound quality assessment of one create proposal."""

    __tablename__ = "knowledge_quality_assessments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["learning_change_id", "team_id"],
            ["learning_changes.id", "learning_changes.team_id"],
            name="fk_knowledge_quality_assessments_learning_change_team",
        ),
        ForeignKeyConstraint(
            ["creating_task_id", "team_id"],
            ["tasks.id", "tasks.team_id"],
            name="fk_knowledge_quality_assessments_task_team",
        ),
        UniqueConstraint(
            "learning_change_id",
            name="uq_knowledge_quality_assessments_learning_change",
        ),
        UniqueConstraint(
            "id",
            "team_id",
            name="uq_knowledge_quality_assessments_id_team",
        ),
        UniqueConstraint(
            "creating_task_id",
            "idempotency_key",
            name="uq_knowledge_quality_assessments_task_idempotency",
        ),
        CheckConstraint(
            "status = 'recorded'",
            name="ck_knowledge_quality_assessments_status",
        ),
        CheckConstraint(
            "evaluator_kind IN ('rule', 'human', 'model')",
            name="ck_knowledge_quality_assessments_evaluator_kind",
        ),
        CheckConstraint(
            "length(rubric_identity) > 0 AND length(rubric_revision) > 0 "
            "AND length(evaluator_identity) > 0 "
            "AND length(evaluator_revision) > 0 "
            "AND length(idempotency_key) > 0",
            name="ck_knowledge_quality_assessments_identity",
        ),
        CheckConstraint(
            "proposal_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "evidence_basis_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "lineage_report_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "evidence_reference_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "assessment_payload_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_quality_assessments_hashes",
        ),
        CheckConstraint(
            "jsonb_typeof(dimensions) = 'object' AND "
            "jsonb_typeof(lineage_report) = 'object' AND "
            "length(narrative) > 0",
            name="ck_knowledge_quality_assessments_payload",
        ),
        Index(
            "ix_knowledge_quality_assessments_team_learning_change",
            "team_id",
            "learning_change_id",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    team_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="recorded", server_default="recorded"
    )
    learning_change_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    creating_task_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    proposal_hash: Mapped[str] = mapped_column(String, nullable=False)
    evidence_basis_hash: Mapped[str] = mapped_column(String, nullable=False)
    rubric_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    rubric_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluator_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    evaluator_identity: Mapped[str] = mapped_column(String(255), nullable=False)
    evaluator_revision: Mapped[str] = mapped_column(String(255), nullable=False)
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    lineage_report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    lineage_report_hash: Mapped[str] = mapped_column(String, nullable=False)
    evidence_reference_hash: Mapped[str] = mapped_column(String, nullable=False)
    assessment_payload_hash: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

