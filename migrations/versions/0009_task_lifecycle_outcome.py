"""Add R6-A Task lifecycle metadata and the terminal Outcome schema.

Revision ID: 0009_task_lifecycle_outcome
Revises: 0008_plan_lifecycle_state
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_task_lifecycle_outcome"
down_revision: str | None = "0008_plan_lifecycle_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DOWNGRADE_REFUSED = (
    "Cannot downgrade while any Task exists: R6-A Task metadata "
    "(created_at, completed_at, max_attempts) and terminal task_execution "
    "Outcomes cannot be reconstructed without loss"
)


def upgrade() -> None:
    # Add nullable first so the historical timestamp can be preserved from the
    # earliest task_started Event before the column becomes NOT NULL.
    op.add_column(
        "tasks",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE tasks SET created_at = COALESCE("
        "(SELECT MIN(e.created_at) FROM events e "
        "WHERE e.task_id = tasks.id AND e.type = 'task_started'), "
        "now())"
    )
    op.alter_column(
        "tasks",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    op.add_column(
        "tasks",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "max_attempts", sa.Integer(), nullable=False, server_default="3"
        ),
    )
    op.create_unique_constraint("uq_tasks_id_team", "tasks", ["id", "team_id"])

    op.create_table(
        "outcomes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("subject_kind", sa.String(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("outcome_type", sa.String(), nullable=False),
        sa.Column(
            "expected",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column("observation_snapshot_ref", sa.String(), nullable=True),
        sa.Column("observation_hash", sa.String(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by_task_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(
            ["recorded_by_task_id", "team_id"],
            ["tasks.id", "tasks.team_id"],
            name="fk_outcomes_task_team",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recorded_by_task_id",
            "outcome_type",
            name="uq_outcomes_task_type",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "outcome_type <> 'prediction_registered' OR expected IS NOT NULL",
            name="ck_outcomes_expected_present",
        ),
        sa.CheckConstraint(
            "observation_snapshot_ref IS NULL OR "
            "observation_snapshot_ref ~ '^snap://sha256/[0-9a-f]{64}$'",
            name="ck_outcomes_observation_ref",
        ),
        sa.CheckConstraint(
            "observation_hash IS NULL OR "
            "observation_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_outcomes_observation_hash",
        ),
        sa.CheckConstraint(
            "observation_snapshot_ref IS NULL OR observation_hash IS NULL OR "
            "split_part(observation_snapshot_ref, '/', 4) = "
            "split_part(observation_hash, ':', 2)",
            name="ck_outcomes_observation_pair",
        ),
        sa.CheckConstraint(
            "outcome_type <> 'task_execution' OR "
            "(subject_kind = 'task' AND subject_id = recorded_by_task_id)",
            name="ck_outcomes_task_execution_subject",
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM tasks)")):
        raise RuntimeError(_DOWNGRADE_REFUSED)
    # The outcomes table holds the composite foreign key that depends on
    # uq_tasks_id_team, so it must be dropped first.
    op.drop_table("outcomes")
    op.drop_constraint("uq_tasks_id_team", "tasks", type_="unique")
    op.drop_column("tasks", "max_attempts")
    op.drop_column("tasks", "completed_at")
    op.drop_column("tasks", "created_at")
