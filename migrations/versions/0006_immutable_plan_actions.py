"""Protect persisted Plan Action intent.

Revision ID: 0006_immutable_plan_actions
Revises: 0005_multi_action_plans
"""

from typing import Sequence

from alembic import op

revision: str = "0006_immutable_plan_actions"
down_revision: str | None = "0005_multi_action_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_plan_actions_identity",
        "plan_actions",
        "action->>'id' = action_id::text",
    )
    op.execute("""
        CREATE FUNCTION preserve_plan_action_intent() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Plan Action intent is immutable';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER preserve_plan_action_intent
        BEFORE UPDATE ON plan_actions
        FOR EACH ROW EXECUTE FUNCTION preserve_plan_action_intent()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER preserve_plan_action_intent ON plan_actions")
    op.execute("DROP FUNCTION preserve_plan_action_intent()")
    op.drop_constraint("ck_plan_actions_identity", "plan_actions", type_="check")
