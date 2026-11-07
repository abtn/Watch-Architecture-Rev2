"""Pin Team Experience projections to the current LearningChange and hash scheme.

Revision ID: 0016_team_experience_history_pins
Revises: 0015_r7b_history
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_team_experience_history_pins"
down_revision: str | None = "0015_r7b_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONTENT_HASH_SCHEMES = (
    "'legacy-opaque', 'watch.r7b.knowledge-content.v2'"
)


def _history_pin_check(table: str) -> str:
    return (
        "content_hash_scheme IN ("
        + CONTENT_HASH_SCHEMES
        + ") AND ((content_hash_scheme = 'legacy-opaque' "
        "AND current_learning_change_id IS NULL) OR "
        "(content_hash_scheme = 'watch.r7b.knowledge-content.v2' "
        "AND current_learning_change_id IS NOT NULL))"
    )


def upgrade() -> None:
    for table in ("team_experience_chunks", "team_experience_index_state"):
        op.add_column(
            table,
            sa.Column("current_learning_change_id", sa.Uuid(), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("content_hash_scheme", sa.String(length=64), nullable=True),
        )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE team_experience_chunks "
            "SET content_hash_scheme = 'legacy-opaque'"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE team_experience_index_state "
            "SET content_hash_scheme = 'legacy-opaque', status = 'stale'"
        )
    )

    for table in ("team_experience_chunks", "team_experience_index_state"):
        op.alter_column(table, "content_hash_scheme", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_current_learning_change_team",
            table,
            "learning_changes",
            ["current_learning_change_id", "team_id"],
            ["id", "team_id"],
        )
        op.create_check_constraint(
            f"ck_{table}_history_pins",
            table,
            _history_pin_check(table),
        )


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("team_experience_chunks", "team_experience_index_state"):
        has_v2_rows = connection.scalar(
            sa.text(
                f"SELECT EXISTS (SELECT 1 FROM {table} "
                "WHERE content_hash_scheme <> 'legacy-opaque' "
                "OR current_learning_change_id IS NOT NULL)"
            )
        )
        if has_v2_rows:
            raise RuntimeError(
                "Cannot downgrade Team Experience history pins after v2 publication"
            )

    for table in ("team_experience_chunks", "team_experience_index_state"):
        op.drop_constraint(f"ck_{table}_history_pins", table, type_="check")
        op.drop_constraint(
            f"fk_{table}_current_learning_change_team", table, type_="foreignkey"
        )
        op.drop_column(table, "content_hash_scheme")
        op.drop_column(table, "current_learning_change_id")
