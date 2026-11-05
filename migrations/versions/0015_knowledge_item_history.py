"""Add current KnowledgeItem pointer and lifecycle graph references.

Revision ID: 0015_knowledge_item_history
Revises: 0014_knowledge_quality_assessment
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0015_knowledge_item_history"
down_revision: str | None = "0014_knowledge_quality_assessment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add nullable first so every existing row can be validated and backfilled
    # before the database starts requiring a current pointer.
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

    # A legacy root is reconstructable only when its origin is the accepted,
    # same-Team create decision and the immutable root snapshot names this item.
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM knowledge_items AS ki
                    LEFT JOIN learning_changes AS lc
                      ON lc.id = ki.origin_learning_change_id
                     AND lc.team_id = ki.team_id
                    WHERE lc.id IS NULL
                       OR lc.target_kind <> 'knowledge_item'
                       OR lc.target_id IS NOT NULL
                       OR lc.operation <> 'create'
                       OR lc.status <> 'accepted'
                       OR lc.committed_by_task_id IS NULL
                       OR lc.committed_at IS NULL
                       OR lc.committed_state IS NULL
                       OR lc.committed_state->>'id' IS DISTINCT FROM ki.id::text
                       OR lc.committed_state->>'team_id' IS DISTINCT FROM ki.team_id::text
                       OR lc.committed_state->>'origin_learning_change_id'
                            IS DISTINCT FROM lc.id::text
                ) THEN
                    RAISE EXCEPTION
                        'cannot backfill KnowledgeItem current pointer: invalid accepted create origin';
                END IF;

                IF EXISTS (
                    SELECT origin_learning_change_id
                    FROM knowledge_items
                    GROUP BY origin_learning_change_id
                    HAVING count(*) <> 1
                ) THEN
                    RAISE EXCEPTION
                        'cannot backfill KnowledgeItem current pointer: duplicate origin';
                END IF;
            END
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE knowledge_items
               SET current_learning_change_id = origin_learning_change_id
            """
        )
    )
    op.alter_column(
        "knowledge_items",
        "current_learning_change_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )

    op.create_foreign_key(
        "fk_knowledge_items_current_learning_change_team",
        "knowledge_items",
        "learning_changes",
        ["current_learning_change_id", "team_id"],
        ["id", "team_id"],
    )
    op.create_foreign_key(
        "fk_knowledge_items_supersedes_item_team",
        "knowledge_items",
        "knowledge_items",
        ["supersedes_item_id", "team_id"],
        ["id", "team_id"],
    )
    op.create_foreign_key(
        "fk_knowledge_items_superseded_by_item_team",
        "knowledge_items",
        "knowledge_items",
        ["superseded_by_id", "team_id"],
        ["id", "team_id"],
    )

    op.create_check_constraint(
        "ck_knowledge_items_no_self_supersession",
        "knowledge_items",
        "(supersedes_item_id IS NULL OR supersedes_item_id <> id) "
        "AND (superseded_by_id IS NULL OR superseded_by_id <> id)",
    )
    op.create_unique_constraint(
        "uq_knowledge_items_origin_learning_change",
        "knowledge_items",
        ["origin_learning_change_id"],
    )
    op.create_unique_constraint(
        "uq_knowledge_items_current_learning_change",
        "knowledge_items",
        ["current_learning_change_id"],
    )
    op.create_unique_constraint(
        "uq_knowledge_items_superseded_by",
        "knowledge_items",
        ["superseded_by_id"],
    )
    op.create_index(
        "uq_knowledge_items_pending_predecessor",
        "knowledge_items",
        ["supersedes_item_id"],
        unique=True,
        postgresql_where=sa.text(
            "supersedes_item_id IS NOT NULL AND status <> 'retired'"
        ),
    )
    op.create_index(
        "ix_knowledge_items_supersedes_item",
        "knowledge_items",
        ["supersedes_item_id"],
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
        "ix_knowledge_items_supersedes_item", table_name="knowledge_items"
    )
    op.drop_index(
        "uq_knowledge_items_pending_predecessor",
        table_name="knowledge_items",
    )
    op.drop_constraint(
        "uq_knowledge_items_superseded_by", "knowledge_items", type_="unique"
    )
    op.drop_constraint(
        "uq_knowledge_items_current_learning_change",
        "knowledge_items",
        type_="unique",
    )
    op.drop_constraint(
        "uq_knowledge_items_origin_learning_change",
        "knowledge_items",
        type_="unique",
    )
    op.drop_constraint(
        "ck_knowledge_items_no_self_supersession",
        "knowledge_items",
        type_="check",
    )
    op.drop_constraint(
        "fk_knowledge_items_superseded_by_item_team",
        "knowledge_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_knowledge_items_supersedes_item_team",
        "knowledge_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_knowledge_items_current_learning_change_team",
        "knowledge_items",
        type_="foreignkey",
    )
    op.drop_column("knowledge_items", "superseded_by_id")
    op.drop_column("knowledge_items", "supersedes_item_id")
    op.drop_column("knowledge_items", "current_learning_change_id")
