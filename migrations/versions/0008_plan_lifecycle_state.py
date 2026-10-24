"""Tighten the Plan lifecycle check constraint for non-superseded stops.

Revision ID: 0008_plan_lifecycle_state
Revises: 0007_plan_lifecycle
"""

from typing import Sequence

from alembic import op

revision: str = "0008_plan_lifecycle_state"
down_revision: str | None = "0007_plan_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_plans_lifecycle_state", "plans", type_="check")
    op.create_check_constraint(
        "ck_plans_lifecycle_state",
        "plans",
        "(status = 'stopped' AND stopped_reason IS NOT NULL AND "
        "((stopped_reason = 'superseded' AND successor_plan_id IS NOT NULL "
        "AND successor_plan_id <> id) OR "
        "(stopped_reason <> 'superseded' AND successor_plan_id IS NULL))) OR "
        "(status <> 'stopped' AND stopped_reason IS NULL AND "
        "successor_plan_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_plans_lifecycle_state", "plans", type_="check")
    op.create_check_constraint(
        "ck_plans_lifecycle_state",
        "plans",
        "(status = 'stopped' AND stopped_reason IS NOT NULL AND "
        "(stopped_reason <> 'superseded' OR "
        "(successor_plan_id IS NOT NULL AND successor_plan_id <> id))) OR "
        "(status <> 'stopped' AND stopped_reason IS NULL AND "
        "successor_plan_id IS NULL)",
    )
