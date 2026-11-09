"""Allow ineligible supersede assessments to preserve a NULL successor review date.

Revision ID: 0018_r7b_lifecycle_null_review_after
Revises: 0017_r7b_assessments
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_r7b_lifecycle_null_review_after"
down_revision: str | None = "0017_r7b_assessments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_knowledge_lifecycle_assessments_variant_shape"
_TABLE = "knowledge_lifecycle_assessments"

# Keep the frozen retire shape and every supersede binding requirement intact.
# Only an ineligible supersede assessment may preserve an observed NULL date.
_UPGRADE_CONSTRAINT = (
    "(operation = 'retire' AND variant_payload = '{}'::jsonb AND "
    "successor_knowledge_item_id IS NULL AND "
    "successor_current_learning_change_id IS NULL AND "
    "successor_content_version IS NULL AND successor_content_hash IS NULL AND "
    "successor_content_hash_scheme IS NULL AND successor_status IS NULL AND "
    "successor_review_after IS NULL AND successor_state_hash IS NULL) OR "
    "(operation = 'supersede' AND "
    "variant_payload = jsonb_build_object("
    "'successor_team_id', variant_payload->'successor_team_id') AND "
    "variant_payload ? 'successor_team_id' AND "
    "variant_payload->>'successor_team_id' IS NOT NULL AND "
    "variant_payload->>'successor_team_id' = team_id::text AND "
    "successor_knowledge_item_id IS NOT NULL AND "
    "successor_current_learning_change_id IS NOT NULL AND "
    "successor_content_version IS NOT NULL AND "
    "successor_content_hash IS NOT NULL AND "
    "successor_content_hash_scheme IS NOT NULL AND "
    "successor_status IS NOT NULL AND "
    "(successor_review_after IS NOT NULL OR "
    "assessment_result = 'ineligible') AND "
    "successor_state_hash IS NOT NULL)"
)

# Exact pre-0018 contract, restored only when downgrade is safe.
_DOWNGRADE_CONSTRAINT = (
    "(operation = 'retire' AND variant_payload = '{}'::jsonb AND "
    "successor_knowledge_item_id IS NULL AND "
    "successor_current_learning_change_id IS NULL AND "
    "successor_content_version IS NULL AND successor_content_hash IS NULL AND "
    "successor_content_hash_scheme IS NULL AND successor_status IS NULL AND "
    "successor_review_after IS NULL AND successor_state_hash IS NULL) OR "
    "(operation = 'supersede' AND "
    "variant_payload = jsonb_build_object("
    "'successor_team_id', variant_payload->'successor_team_id') AND "
    "variant_payload ? 'successor_team_id' AND "
    "variant_payload->>'successor_team_id' IS NOT NULL AND "
    "variant_payload->>'successor_team_id' = team_id::text AND "
    "successor_knowledge_item_id IS NOT NULL AND "
    "successor_current_learning_change_id IS NOT NULL AND "
    "successor_content_version IS NOT NULL AND "
    "successor_content_hash IS NOT NULL AND "
    "successor_content_hash_scheme IS NOT NULL AND "
    "successor_status IS NOT NULL AND "
    "successor_review_after IS NOT NULL AND "
    "successor_state_hash IS NOT NULL)"
)


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _UPGRADE_CONSTRAINT)


def downgrade() -> None:
    connection = op.get_bind()
    has_null_date_history = connection.scalar(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM knowledge_lifecycle_assessments "
            "WHERE operation = 'supersede' "
            "AND assessment_result = 'ineligible' "
            "AND successor_review_after IS NULL)"
        )
    )
    if has_null_date_history:
        raise RuntimeError(
            "Cannot downgrade lifecycle review-date constraint while "
            "ineligible supersede assessments preserve a NULL successor_review_after"
        )

    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, _DOWNGRADE_CONSTRAINT)
