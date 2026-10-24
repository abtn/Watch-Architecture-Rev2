"""Plan lifecycle state, stop reasons, and scoped intent protection.

Revision ID: 0007_plan_lifecycle
Revises: 0006_immutable_plan_actions
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_plan_lifecycle"
down_revision: str | None = "0006_immutable_plan_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_plans_r5_04_status", "plans", type_="check")
    op.add_column("plans", sa.Column("stopped_reason", sa.String(), nullable=True))
    op.add_column("plans", sa.Column("successor_plan_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_plans_successor", "plans", "plans", ["successor_plan_id"], ["id"]
    )
    op.create_check_constraint(
        "ck_plans_status",
        "plans",
        "status IN ('active', 'completed', 'stopped')",
    )
    op.create_check_constraint(
        "ck_plans_stopped_reason",
        "plans",
        "stopped_reason IS NULL OR "
        "stopped_reason IN ('abandoned', 'invalidated', 'superseded')",
    )
    op.create_check_constraint(
        "ck_plans_lifecycle_state",
        "plans",
        "(status = 'stopped' AND stopped_reason IS NOT NULL AND "
        "(stopped_reason <> 'superseded' OR "
        "(successor_plan_id IS NOT NULL AND successor_plan_id <> id))) OR "
        "(status <> 'stopped' AND stopped_reason IS NULL AND "
        "successor_plan_id IS NULL)",
    )
    # Only the lifecycle columns may change. Every other Plan column is
    # accepted Strategy identity, provenance, or immutable intent.
    op.execute("DROP TRIGGER preserve_plan_intent ON plans")
    op.execute("DROP FUNCTION preserve_plan_intent()")
    op.execute("""
        CREATE FUNCTION preserve_plan_intent() RETURNS trigger AS $$
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id
                OR NEW.team_id IS DISTINCT FROM OLD.team_id
                OR NEW.objective_id IS DISTINCT FROM OLD.objective_id
                OR NEW.created_by_task_id IS DISTINCT FROM OLD.created_by_task_id
                OR NEW.accepted_event_id IS DISTINCT FROM OLD.accepted_event_id
                OR NEW.proposal_hash IS DISTINCT FROM OLD.proposal_hash
                OR NEW.assessment_basis IS DISTINCT FROM OLD.assessment_basis
                OR NEW.assessment_created_at IS DISTINCT FROM OLD.assessment_created_at
                OR NEW.budget IS DISTINCT FROM OLD.budget
                OR NEW.completion_condition IS DISTINCT FROM OLD.completion_condition
            THEN
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
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM plans WHERE status <> 'active')")
    ):
        raise RuntimeError("Cannot downgrade while any Plan is not active")
    op.execute("DROP TRIGGER preserve_plan_intent ON plans")
    op.execute("DROP FUNCTION preserve_plan_intent()")
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
    op.drop_constraint("ck_plans_lifecycle_state", "plans", type_="check")
    op.drop_constraint("ck_plans_stopped_reason", "plans", type_="check")
    op.drop_constraint("ck_plans_status", "plans", type_="check")
    op.drop_constraint("fk_plans_successor", "plans", type_="foreignkey")
    op.drop_column("plans", "successor_plan_id")
    op.drop_column("plans", "stopped_reason")
    op.create_check_constraint("ck_plans_r5_04_status", "plans", "status = 'active'")
