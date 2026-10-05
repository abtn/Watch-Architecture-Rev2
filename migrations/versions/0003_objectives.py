"""Add durable Objectives and optional Task attribution.

Revision ID: 0003_objectives
Revises: 0002_ingestion_kernel
Create Date: 2026-10-05
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_objectives"
down_revision: str | None = "0002_ingestion_kernel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "objectives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("statement", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="draft", nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'blocked', "
            "'completed', 'cancelled')",
            name="ck_objectives_status",
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "team_id", name="uq_objectives_id_team"),
    )
    op.add_column("tasks", sa.Column("objective_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_tasks_objective_team",
        "tasks",
        "objectives",
        ["objective_id", "team_id"],
        ["id", "team_id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_tasks_objective_team", "tasks", type_="foreignkey")
    op.drop_column("tasks", "objective_id")
    op.drop_table("objectives")
