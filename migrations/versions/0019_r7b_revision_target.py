"""Persist exact revise-target pins on KnowledgeQualityAssessment.

Revision ID: 0019_r7b_revision_target
Revises: 0018_r7b_lifecycle_review_date
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_r7b_revision_target"
down_revision: str | None = "0018_r7b_lifecycle_review_date"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "knowledge_quality_assessments"
_TARGET_BINDING_CONSTRAINT = "ck_knowledge_quality_assessments_target_binding"

_TARGET_BINDING_CHECK = (
    "(target_knowledge_item_id IS NULL AND "
    "target_current_learning_change_id IS NULL AND "
    "target_content_version IS NULL AND target_content_hash IS NULL AND "
    "target_content_hash_scheme IS NULL AND target_state_hash IS NULL) OR "
    "(target_knowledge_item_id IS NOT NULL AND "
    "target_current_learning_change_id IS NOT NULL AND "
    "target_content_version IS NOT NULL AND target_content_version >= 1 AND "
    "target_content_hash IS NOT NULL AND "
    "target_content_hash ~ '^sha256:[0-9a-f]{64}$' AND "
    "target_content_hash_scheme IS NOT NULL AND "
    "target_content_hash_scheme = 'watch.r7b.knowledge-content.v2' AND "
    "target_state_hash IS NOT NULL AND "
    "target_state_hash ~ '^sha256:[0-9a-f]{64}$')"
)


def upgrade() -> None:
    op.add_column(
        _TABLE, sa.Column("target_knowledge_item_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        _TABLE,
        sa.Column("target_current_learning_change_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        _TABLE, sa.Column("target_content_version", sa.Integer(), nullable=True)
    )
    op.add_column(
        _TABLE, sa.Column("target_content_hash", sa.String(), nullable=True)
    )
    op.add_column(
        _TABLE,
        sa.Column("target_content_hash_scheme", sa.String(), nullable=True),
    )
    op.add_column(
        _TABLE, sa.Column("target_state_hash", sa.String(), nullable=True)
    )
    op.create_foreign_key(
        "fk_knowledge_quality_assessments_target_item_team",
        _TABLE,
        "knowledge_items",
        ["target_knowledge_item_id", "team_id"],
        ["id", "team_id"],
    )
    op.create_foreign_key(
        "fk_knowledge_quality_assessments_target_pointer_team",
        _TABLE,
        "learning_changes",
        ["target_current_learning_change_id", "team_id"],
        ["id", "team_id"],
    )
    op.create_check_constraint(
        _TARGET_BINDING_CONSTRAINT, _TABLE, _TARGET_BINDING_CHECK
    )


def downgrade() -> None:
    op.drop_constraint(_TARGET_BINDING_CONSTRAINT, _TABLE, type_="check")
    op.drop_constraint(
        "fk_knowledge_quality_assessments_target_pointer_team",
        _TABLE,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_knowledge_quality_assessments_target_item_team",
        _TABLE,
        type_="foreignkey",
    )
    op.drop_column(_TABLE, "target_state_hash")
    op.drop_column(_TABLE, "target_content_hash_scheme")
    op.drop_column(_TABLE, "target_content_hash")
    op.drop_column(_TABLE, "target_content_version")
    op.drop_column(_TABLE, "target_current_learning_change_id")
    op.drop_column(_TABLE, "target_knowledge_item_id")
