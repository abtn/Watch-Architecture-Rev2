"""Persist Strategy-local Plan Actions and Task provenance.

Revision ID: 0005_multi_action_plans
Revises: 0004_plans
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_multi_action_plans"
down_revision: str | None = "0004_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_actions",
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("action", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], name="fk_plan_actions_plan"),
        sa.PrimaryKeyConstraint("plan_id", "action_id"),
    )
    op.execute(
        "INSERT INTO plan_actions (plan_id, action_id, action) "
        "SELECT id, (action->>'id')::uuid, action FROM plans"
    )
    op.execute(
        "UPDATE tasks AS t SET plan_action_id = pa.action_id::text "
        "FROM plans AS p JOIN plan_actions AS pa ON pa.plan_id = p.id "
        "WHERE t.plan_id = p.id AND t.plan_action_id = p.action_id"
    )
    op.drop_constraint("fk_tasks_plan_action", "tasks", type_="foreignkey")
    op.drop_constraint("uq_plans_id_action", "plans", type_="unique")
    op.alter_column(
        "tasks",
        "plan_action_id",
        existing_type=sa.String(),
        type_=sa.Uuid(),
        postgresql_using="plan_action_id::uuid",
    )
    op.create_foreign_key(
        "fk_tasks_plan_action",
        "tasks",
        "plan_actions",
        ["plan_id", "plan_action_id"],
        ["plan_id", "action_id"],
    )
    op.drop_column("plans", "action_id")
    op.drop_column("plans", "action")
    op.create_unique_constraint(
        "uq_plans_accepted_event", "plans", ["accepted_event_id"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM plan_actions "
            "GROUP BY plan_id HAVING count(*) > 1)"
        )
    ):
        raise RuntimeError("Cannot downgrade while any Plan contains multiple Actions")
    op.drop_constraint("uq_plans_accepted_event", "plans", type_="unique")
    op.drop_constraint("fk_tasks_plan_action", "tasks", type_="foreignkey")
    op.add_column("plans", sa.Column("action_id", sa.String(), nullable=True))
    op.add_column("plans", sa.Column("action", postgresql.JSONB(), nullable=True))
    op.execute(
        "UPDATE plans AS p SET action_id = pa.action_id::text, action = pa.action "
        "FROM plan_actions AS pa WHERE pa.plan_id = p.id"
    )
    op.alter_column("plans", "action_id", nullable=False)
    op.alter_column("plans", "action", nullable=False)
    op.alter_column(
        "tasks",
        "plan_action_id",
        existing_type=sa.Uuid(),
        type_=sa.String(),
        postgresql_using="plan_action_id::text",
    )
    op.create_unique_constraint("uq_plans_id_action", "plans", ["id", "action_id"])
    op.create_foreign_key(
        "fk_tasks_plan_action",
        "tasks",
        "plans",
        ["plan_id", "plan_action_id"],
        ["id", "action_id"],
    )
    op.drop_table("plan_actions")
