"""Minimal persistence mappings for the K1 ingestion path."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
