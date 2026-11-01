"""Add per-attempt Task generation cost reservations and reconciliation.

Revision ID: 0011_task_generation_cost
Revises: 0010_knowledge_chunk_projection
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_task_generation_cost"
down_revision: str | None = "0010_knowledge_chunk_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_generation_charges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("pricing_revision", sa.String(), nullable=False),
        sa.Column("max_input_tokens", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column(
            "input_usd_per_million_tokens",
            sa.Numeric(12, 9),
            nullable=False,
        ),
        sa.Column(
            "output_usd_per_million_tokens",
            sa.Numeric(12, 9),
            nullable=False,
        ),
        sa.Column("reserved_cost_usd", sa.Numeric(20, 12), nullable=False),
        sa.Column("accounted_cost_usd", sa.Numeric(20, 12), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name="fk_task_generation_charges_task"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "attempt_count",
            "operation",
            name="uq_task_generation_charges_attempt_operation",
        ),
        sa.CheckConstraint(
            "attempt_count > 0 AND max_input_tokens >= 0 "
            "AND max_output_tokens > 0",
            name="ck_task_generation_charges_token_bounds",
        ),
        sa.CheckConstraint(
            "reserved_cost_usd > 0 AND "
            "(accounted_cost_usd IS NULL OR accounted_cost_usd >= 0)",
            name="ck_task_generation_charges_costs",
        ),
        sa.CheckConstraint(
            "length(provider) > 0 AND length(model) > 0 "
            "AND length(pricing_revision) > 0 AND length(operation) > 0",
            name="ck_task_generation_charges_identity",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_task_generation_charges_input_tokens",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_task_generation_charges_output_tokens",
        ),
        sa.CheckConstraint(
            "status IN ('reserved', 'reconciled', 'unknown', 'overrun')",
            name="ck_task_generation_charges_status",
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM task_generation_charges)")
    ):
        raise RuntimeError(
            "Cannot downgrade while Task generation cost records exist; "
            "reservation and usage history cannot be reconstructed"
        )
    op.drop_table("task_generation_charges")
