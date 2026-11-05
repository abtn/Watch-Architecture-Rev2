"""Add R7-B KnowledgeItem history pointers and reciprocal supersession links.

Revision ID: 0015_r7b_history
Revises: 0014_knowledge_quality
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_r7b_history"
down_revision: str | None = "0014_knowledge_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add nullable first so existing rows can be validated and backfilled.
    op.add_column(
        "knowledge_items",
        sa.Column("current_learning_change_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "knowledge_items",
        sa.Column("supersedes_item_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "knowledge_items",
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
    )

    connection = op.get_bind()
    invalid = connection.execute(
        sa.text(
            """
            SELECT ki.id
            FROM knowledge_items AS ki
            LEFT JOIN learning_changes AS lc
              ON lc.id = ki.origin_learning_change_id
             AND lc.team_id = ki.team_id
            WHERE lc.id IS NULL
               OR lc.status <> 'accepted'
               OR lc.operation <> 'create'
               OR lc.target_id IS NOT NULL
               OR lc.committed_state IS NULL
               OR lc.committed_state->>'id' <> ki.id::text
               OR lc.committed_state->>'team_id' <> ki.team_id::text
            LIMIT 1
            """
        )
    ).first()
    if invalid is not None:
        raise RuntimeError(
            "R7-B current-pointer backfill refused: invalid KnowledgeItem origin "
            f"for item {invalid[0]}"
        )

    connection.execute(
        sa.text(
            """
            UPDATE knowledge_items
               SET current_learning_change_id = origin_learning_change_id
            """
        )
    )

    op.alter_column(
        "knowledge_items", "current_learning_change_id", nullable=False
    )
    op.create_foreign_key(
        "fk_knowledge_items_current_learning_change_team",
        "knowledge_items",
        "learning_changes",
        ["current_learning_change_id", "team_id"],
        ["id", "team_id"],
    )
    op.create_unique_constraint(
        "uq_knowledge_items_current_learning_change",
        "knowledge_items",
        ["current_learning_change_id"],
    )

    op.create_foreign_key(
        "fk_knowledge_items_supersedes_team",
        "knowledge_items",
        "knowledge_items",
        ["supersedes_item_id", "team_id"],
        ["id", "team_id"],
    )
    op.create_foreign_key(
        "fk_knowledge_items_superseded_by_team",
        "knowledge_items",
        "knowledge_items",
        ["superseded_by_id", "team_id"],
        ["id", "team_id"],
    )
    op.create_check_constraint(
        "ck_knowledge_items_no_self_supersession",
        "knowledge_items",
        "(supersedes_item_id IS NULL OR supersedes_item_id <> id) AND "
        "(superseded_by_id IS NULL OR superseded_by_id <> id)",
    )
    op.create_unique_constraint(
        "uq_knowledge_items_superseded_by",
        "knowledge_items",
        ["superseded_by_id"],
    )
    op.create_index(
        "uq_knowledge_items_pending_candidate",
        "knowledge_items",
        ["supersedes_item_id"],
        unique=True,
        postgresql_where=sa.text(
            "supersedes_item_id IS NOT NULL AND status <> 'retired'"
        ),
    )

    op.drop_constraint(
        "ck_learning_changes_operation", "learning_changes", type_="check"
    )
    op.create_check_constraint(
        "ck_learning_changes_operation",
        "learning_changes",
        "operation IN ('create', 'revise', 'revalidate', 'supersede', 'retire')",
    )
    op.drop_constraint(
        "ck_learning_changes_target_state", "learning_changes", type_="check"
    )
    op.create_check_constraint(
        "ck_learning_changes_target_state",
        "learning_changes",
        "(operation = 'create' AND target_id IS NULL) OR "
        "(operation IN ('revise', 'revalidate', 'supersede', 'retire') "
        "AND target_id IS NOT NULL)",
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM knowledge_items "
            "WHERE current_learning_change_id IS DISTINCT FROM "
            "origin_learning_change_id OR supersedes_item_id IS NOT NULL "
            "OR superseded_by_id IS NOT NULL)"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade R7-B history pointers while lifecycle history "
            "or supersession links are present"
        )

    op.drop_constraint(
        "ck_learning_changes_target_state", "learning_changes", type_="check"
    )
    op.create_check_constraint(
        "ck_learning_changes_target_state",
        "learning_changes",
        "(operation = 'create' AND target_id IS NULL) OR "
        "(operation IN ('revise', 'retire') AND target_id IS NOT NULL)",
    )
    op.drop_constraint(
        "ck_learning_changes_operation", "learning_changes", type_="check"
    )
    op.create_check_constraint(
        "ck_learning_changes_operation",
        "learning_changes",
        "operation IN ('create', 'revise', 'retire')",
    )

    op.drop_index(
        "uq_knowledge_items_pending_candidate", table_name="knowledge_items"
    )
    op.drop_constraint(
        "uq_knowledge_items_superseded_by", "knowledge_items", type_="unique"
    )
    op.drop_constraint(
        "ck_knowledge_items_no_self_supersession",
        "knowledge_items",
        type_="check",
    )
    op.drop_constraint(
        "fk_knowledge_items_superseded_by_team",
        "knowledge_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_knowledge_items_supersedes_team",
        "knowledge_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_knowledge_items_current_learning_change",
        "knowledge_items",
        type_="unique",
    )
    op.drop_constraint(
        "fk_knowledge_items_current_learning_change_team",
        "knowledge_items",
        type_="foreignkey",
    )
    op.drop_column("knowledge_items", "superseded_by_id")
    op.drop_column("knowledge_items", "supersedes_item_id")
    op.drop_column("knowledge_items", "current_learning_change_id")
