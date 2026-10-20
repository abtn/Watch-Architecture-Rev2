"""Atomic single-action Plan intent and nullable Task provenance.

Revision ID: 0004_plans
Revises: 0003_objectives
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_plans"
down_revision: str | None = "0003_objectives"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("objective_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_task_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_event_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_hash", sa.String(), nullable=False),
        sa.Column("assessment_basis", postgresql.JSONB(), nullable=False),
        sa.Column("assessment_created_at", sa.String(), nullable=False),
        sa.Column("action_id", sa.String(), nullable=False),
        sa.Column("action", postgresql.JSONB(), nullable=False),
        sa.Column("budget", postgresql.JSONB(), nullable=False),
        sa.Column("completion_condition", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="active", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(
            ["objective_id", "team_id"],
            ["objectives.id", "objectives.team_id"],
            name="fk_plans_objective_team",
        ),
        sa.ForeignKeyConstraint(["created_by_task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["accepted_event_id"], ["events.id"]),
        sa.UniqueConstraint("id", "team_id", name="uq_plans_id_team"),
        sa.UniqueConstraint("id", "objective_id", name="uq_plans_id_objective"),
        sa.UniqueConstraint("id", "action_id", name="uq_plans_id_action"),
        sa.UniqueConstraint("created_by_task_id", name="uq_plans_created_by_task"),
        sa.CheckConstraint("status = 'active'", name="ck_plans_r5_04_status"),
    )
    op.add_column(
        "tasks",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("tasks", sa.Column("plan_id", sa.Uuid(), nullable=True))
    op.add_column("tasks", sa.Column("plan_action_id", sa.String(), nullable=True))
    for name, local, remote in (
        ("fk_tasks_plan_team", ["plan_id", "team_id"], ["id", "team_id"]),
        (
            "fk_tasks_plan_objective",
            ["plan_id", "objective_id"],
            ["id", "objective_id"],
        ),
        (
            "fk_tasks_plan_action",
            ["plan_id", "plan_action_id"],
            ["id", "action_id"],
        ),
    ):
        op.create_foreign_key(name, "tasks", "plans", local, remote)
    op.create_unique_constraint(
        "uq_tasks_plan_action", "tasks", ["plan_id", "plan_action_id"]
    )
    op.create_check_constraint(
        "ck_tasks_plan_action_pair",
        "tasks",
        "(plan_id IS NULL) = (plan_action_id IS NULL)",
    )
    op.execute("""
        CREATE FUNCTION preserve_plan_intent() RETURNS trigger AS $$
        BEGIN
            IF NEW IS DISTINCT FROM OLD THEN
                RAISE EXCEPTION 'Plan intent is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER preserve_plan_intent BEFORE UPDATE ON plans
        FOR EACH ROW EXECUTE FUNCTION preserve_plan_intent()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER preserve_plan_intent ON plans")
    op.execute("DROP FUNCTION preserve_plan_intent()")
    op.drop_constraint("ck_tasks_plan_action_pair", "tasks", type_="check")
    op.drop_constraint("uq_tasks_plan_action", "tasks", type_="unique")
    for name in (
        "fk_tasks_plan_action",
        "fk_tasks_plan_objective",
        "fk_tasks_plan_team",
    ):
        op.drop_constraint(name, "tasks", type_="foreignkey")
    op.drop_column("tasks", "plan_action_id")
    op.drop_column("tasks", "plan_id")
    op.drop_column("tasks", "attempt_count")
    op.drop_table("plans")
