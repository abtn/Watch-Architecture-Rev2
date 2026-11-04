"""Add immutable R7-A KnowledgeQualityAssessment records.

Revision ID: 0014_knowledge_quality
Revises: 0013_team_experience_projection
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0014_knowledge_quality"
down_revision: str | None = "0013_team_experience_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_quality_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="recorded"),
        sa.Column("learning_change_id", sa.Uuid(), nullable=False),
        sa.Column("creating_task_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_hash", sa.String(), nullable=False),
        sa.Column("evidence_basis_hash", sa.String(), nullable=False),
        sa.Column("rubric_identity", sa.String(length=255), nullable=False),
        sa.Column("rubric_revision", sa.String(length=64), nullable=False),
        sa.Column("evaluator_kind", sa.String(length=16), nullable=False),
        sa.Column("evaluator_identity", sa.String(length=255), nullable=False),
        sa.Column("evaluator_revision", sa.String(length=255), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("lineage_report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lineage_report_hash", sa.String(), nullable=False),
        sa.Column("evidence_reference_hash", sa.String(), nullable=False),
        sa.Column("assessment_payload_hash", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name="fk_knowledge_quality_assessments_team",
        ),
        sa.ForeignKeyConstraint(
            ["learning_change_id", "team_id"],
            ["learning_changes.id", "learning_changes.team_id"],
            name="fk_knowledge_quality_assessments_learning_change_team",
        ),
        sa.ForeignKeyConstraint(
            ["creating_task_id", "team_id"],
            ["tasks.id", "tasks.team_id"],
            name="fk_knowledge_quality_assessments_task_team",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "learning_change_id",
            name="uq_knowledge_quality_assessments_learning_change",
        ),
        sa.UniqueConstraint(
            "id",
            "team_id",
            name="uq_knowledge_quality_assessments_id_team",
        ),
        sa.UniqueConstraint(
            "creating_task_id",
            "idempotency_key",
            name="uq_knowledge_quality_assessments_task_idempotency",
        ),
        sa.CheckConstraint(
            "status = 'recorded'",
            name="ck_knowledge_quality_assessments_status",
        ),
        sa.CheckConstraint(
            "evaluator_kind IN ('rule', 'human', 'model')",
            name="ck_knowledge_quality_assessments_evaluator_kind",
        ),
        sa.CheckConstraint(
            "length(rubric_identity) > 0 AND length(rubric_revision) > 0 "
            "AND length(evaluator_identity) > 0 "
            "AND length(evaluator_revision) > 0 "
            "AND length(idempotency_key) > 0",
            name="ck_knowledge_quality_assessments_identity",
        ),
        sa.CheckConstraint(
            "proposal_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "evidence_basis_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "lineage_report_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "evidence_reference_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "assessment_payload_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_quality_assessments_hashes",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(dimensions) = 'object' AND "
            "jsonb_typeof(lineage_report) = 'object' AND length(narrative) > 0",
            name="ck_knowledge_quality_assessments_payload",
        ),
    )
    op.create_index(
        "ix_knowledge_quality_assessments_team_learning_change",
        "knowledge_quality_assessments",
        ["team_id", "learning_change_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM knowledge_quality_assessments)")
    ):
        raise RuntimeError(
            "Cannot downgrade while knowledge quality assessment records exist"
        )
    op.drop_index(
        "ix_knowledge_quality_assessments_team_learning_change",
        table_name="knowledge_quality_assessments",
    )
    op.drop_table("knowledge_quality_assessments")
