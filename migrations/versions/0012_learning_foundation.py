"""Add R6-F Evaluation and canonical learning schema foundations.

Revision ID: 0012_learning_foundation
Revises: 0011_task_generation_cost
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_learning_foundation"
down_revision: str | None = "0011_task_generation_cost"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_outcomes_id_team", "outcomes", ["id", "team_id"])
    op.create_table(
        "learning_changes",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("team_id", sa.Uuid(),
            nullable=False),
        sa.Column("target_kind", sa.String(), nullable=False),
            sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("operation", sa.String(), nullable=False),
            sa.Column("proposed_state", postgresql.JSONB(), nullable=False),
        sa.Column("previous_state", postgresql.JSONB(), nullable=True),
            sa.Column("committed_state", postgresql.JSONB(), nullable=True),
        sa.Column("evidence_basis", postgresql.JSONB(), nullable=False),
            sa.Column("evidence_basis_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False,
            server_default="proposed"), sa.Column("idempotency_key",
            sa.String(128), nullable=False),
        sa.Column("proposed_by_task_id", sa.Uuid(), nullable=False),
            sa.Column("committed_by_task_id", sa.Uuid(), nullable=True),
        sa.Column("operator_id", sa.String(255), nullable=True),
            sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now()),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"],
            name="fk_learning_changes_team"),
        sa.ForeignKeyConstraint(["proposed_by_task_id", "team_id"], ["tasks.id",
            "tasks.team_id"], name="fk_learning_changes_proposed_task_team"),
        sa.ForeignKeyConstraint(["committed_by_task_id", "team_id"], ["tasks.id",
            "tasks.team_id"], name="fk_learning_changes_committed_task_team"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("id", "team_id",
            name="uq_learning_changes_id_team"),
        sa.UniqueConstraint("proposed_by_task_id", "idempotency_key",
            name="uq_learning_changes_task_idempotency"),
        sa.CheckConstraint("target_kind = 'knowledge_item'",
            name="ck_learning_changes_target_kind"),
        sa.CheckConstraint("operation IN ('create', 'revise', 'retire')",
            name="ck_learning_changes_operation"),
        sa.CheckConstraint("(operation = 'create' AND target_id IS NULL) "
            "OR (operation IN ('revise', 'retire') AND "
            "target_id IS NOT NULL)", name="ck_learning_changes_target_state"),
        sa.CheckConstraint("status IN ('proposed', 'accepted', 'rejected')",
            name="ck_learning_changes_status"),
        sa.CheckConstraint("evidence_basis_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_learning_changes_evidence_basis_hash"),
        sa.CheckConstraint("length(idempotency_key) > 0 AND "
            "jsonb_typeof(proposed_state) = 'object' AND "
            "jsonb_typeof(evidence_basis) = 'array'",
            name="ck_learning_changes_payload_shape"),
        sa.CheckConstraint(
            "(status = 'proposed' AND "
                "committed_by_task_id IS NULL AND operator_id "
                "IS NULL AND committed_at IS NULL AND "
                "committed_state IS NULL) OR "
            "(status = 'accepted' AND "
                "committed_by_task_id IS NOT NULL AND "
                "operator_id IS NOT NULL AND "
                "length(operator_id) > 0 AND committed_at IS "
                "NOT NULL AND committed_state IS NOT NULL) OR "
                ""
            "(status = 'rejected' AND "
                "committed_by_task_id IS NOT NULL AND "
                "operator_id IS NOT NULL AND "
                "length(operator_id) > 0 AND committed_at IS "
                "NOT NULL AND committed_state IS NULL AND "
                "decision_reason IS NOT NULL AND "
                "length(decision_reason) > 0)",
            name="ck_learning_changes_disposition",
        ),
    )
    op.create_table(
        "knowledge_items",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("team_id", sa.Uuid(),
            nullable=False),
        sa.Column("kind", sa.String(), nullable=False), sa.Column("title",
            sa.String(500), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False), sa.Column("body",
            sa.Text(), nullable=False),
        sa.Column("applicability", postgresql.JSONB(), nullable=False),
            sa.Column("preconditions", postgresql.JSONB(), nullable=False),
        sa.Column("assumptions", postgresql.JSONB(), nullable=False),
            sa.Column("limitations", postgresql.JSONB(), nullable=False),
        sa.Column("non_applicability", postgresql.JSONB(), nullable=False),
            sa.Column("failure_modes", postgresql.JSONB(), nullable=False),
        sa.Column("known_counterexamples", postgresql.JSONB(), nullable=False),
            sa.Column("missing_information", postgresql.JSONB(), nullable=False),
        sa.Column("uncertainty", postgresql.JSONB(), nullable=False),
            sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("review_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origin_learning_change_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"],
            name="fk_knowledge_items_team"),
        sa.ForeignKeyConstraint(["origin_learning_change_id", "team_id"],
            ["learning_changes.id", "learning_changes.team_id"],
            name="fk_knowledge_items_origin_learning_change_team"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("id", "team_id",
            name="uq_knowledge_items_id_team"),
        sa.CheckConstraint("kind IN ('practice', 'pattern', 'method', 'playbook')",
            name="ck_knowledge_items_kind"),
        sa.CheckConstraint("status IN ('active', 'needs_review', 'retired')",
            name="ck_knowledge_items_status"),
        sa.CheckConstraint("version >= 1 AND confidence >= 0 AND confidence <= 1",
            name="ck_knowledge_items_version_confidence"),
        sa.CheckConstraint("length(title) > 0 AND length(statement) > 0 "
            "AND length(body) > 0", name="ck_knowledge_items_content"),
        sa.CheckConstraint(
            "jsonb_typeof(applicability) = 'object' AND "
                "jsonb_typeof(preconditions) = 'array' AND "
                "jsonb_typeof(assumptions) = 'array' AND "
            "jsonb_typeof(limitations) = 'array' AND "
                "jsonb_typeof(non_applicability) = 'array' "
                "AND jsonb_typeof(failure_modes) = 'array' "
                "AND "
            "jsonb_typeof(known_counterexamples) = "
                "'array' AND "
                "jsonb_typeof(missing_information) = 'array' "
                "AND jsonb_typeof(uncertainty) = 'array'",
            name="ck_knowledge_items_payload_shape",
        ),
    )
    op.create_index("ix_knowledge_items_team_status", "knowledge_items",
        ["team_id", "status"])
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("team_id", sa.Uuid(),
            nullable=False),
        sa.Column("outcome_id", sa.Uuid(), nullable=False), sa.Column("conclusion",
            sa.String(), nullable=False),
        sa.Column("findings", postgresql.JSONB(), nullable=False),
            sa.Column("evaluator_kind", sa.String(), nullable=False),
        sa.Column("evaluator_identity", sa.String(255), nullable=False),
            sa.Column("evaluator_revision", sa.String(255), nullable=False),
        sa.Column("status", sa.String(), nullable=False,
            server_default="proposed"), sa.Column("idempotency_key",
            sa.String(128), nullable=False),
        sa.Column("proposal_hash", sa.String(), nullable=False),
            sa.Column("created_by_task_id", sa.Uuid(), nullable=False),
        sa.Column("resolved_by_task_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["outcome_id", "team_id"], ["outcomes.id",
            "outcomes.team_id"], name="fk_evaluations_outcome_team"),
        sa.ForeignKeyConstraint(["created_by_task_id", "team_id"], ["tasks.id",
            "tasks.team_id"], name="fk_evaluations_created_task_team"),
        sa.ForeignKeyConstraint(["resolved_by_task_id", "team_id"], ["tasks.id",
            "tasks.team_id"], name="fk_evaluations_resolved_task_team"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="fk_evaluations_team"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("id", "team_id",
            name="uq_evaluations_id_team"),
        sa.UniqueConstraint("created_by_task_id", "idempotency_key",
            name="uq_evaluations_task_idempotency"),
        sa.CheckConstraint("conclusion IN ('worked', 'mixed', 'failed', "
            "'inconclusive')", name="ck_evaluations_conclusion"),
        sa.CheckConstraint("evaluator_kind IN ('rule', 'human', 'model')",
            name="ck_evaluations_evaluator_kind"),
        sa.CheckConstraint("status IN ('proposed', 'recorded', 'rejected')",
            name="ck_evaluations_status"),
        sa.CheckConstraint("length(evaluator_identity) > 0 AND "
            "length(evaluator_revision) > 0 AND "
            "length(idempotency_key) > 0 AND "
            "proposal_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "jsonb_typeof(findings) = 'object'", name="ck_evaluations_payload"),
        sa.CheckConstraint(
            "(status = 'proposed' AND resolved_by_task_id "
                "IS NULL AND resolved_at IS NULL AND "
                "rejection_reason IS NULL) OR "
            "(status = 'recorded' AND resolved_by_task_id "
                "IS NOT NULL AND resolved_at IS NOT NULL AND "
                "rejection_reason IS NULL) OR "
            "(status = 'rejected' AND resolved_by_task_id "
                "IS NOT NULL AND resolved_at IS NOT NULL AND "
                "rejection_reason IS NOT NULL AND "
                "length(rejection_reason) > 0)",
            name="ck_evaluations_disposition",
        ),
    )
    op.create_index("ix_evaluations_team_outcome_status", "evaluations",
        ["team_id", "outcome_id", "status"])
    op.create_table(
        "evidence_links",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("team_id", sa.Uuid(),
            nullable=False),
        sa.Column("subject_kind", sa.String(), nullable=False),
            sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.String(), nullable=False),
            sa.Column("outcome_id", sa.Uuid(), nullable=True),
        sa.Column("signal_id", sa.Uuid(), nullable=True), sa.Column("snapshot_ref",
            sa.String(), nullable=True),
        sa.Column("snapshot_hash", sa.String(), nullable=True), sa.Column("stance",
            sa.String(), nullable=False),
        sa.Column("quote_text", sa.Text(), nullable=True), sa.Column("quote_start",
            sa.Integer(), nullable=True),
        sa.Column("quote_end", sa.Integer(), nullable=True),
            sa.Column("reference_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["subject_id", "team_id"], ["evaluations.id",
            "evaluations.team_id"], name="fk_evidence_links_evaluation_team"),
        sa.ForeignKeyConstraint(["outcome_id", "team_id"], ["outcomes.id",
            "outcomes.team_id"], name="fk_evidence_links_outcome_team"),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"],
            name="fk_evidence_links_signal"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"],
            name="fk_evidence_links_team"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("subject_id",
            "reference_key", name="uq_evidence_links_subject_reference"),
        sa.CheckConstraint("subject_kind = 'evaluation'",
            name="ck_evidence_links_subject_kind"),
        sa.CheckConstraint("(source_kind = 'outcome' AND outcome_id IS "
            "NOT NULL AND signal_id IS NULL) OR "
            "(source_kind = 'signal' AND signal_id IS NOT "
            "NULL AND outcome_id IS NULL)", name="ck_evidence_links_source"),
        sa.CheckConstraint("stance IN ('supports', 'challenges', 'mentions')",
            name="ck_evidence_links_stance"),
        sa.CheckConstraint(
            "(snapshot_ref IS NULL AND snapshot_hash IS "
                "NULL) OR (snapshot_ref IS NOT NULL AND "
                "snapshot_hash IS NOT NULL AND "
            "snapshot_ref ~ "
                "'^snap://sha256/[0-9a-f]{64}$' AND "
                "snapshot_hash ~ '^sha256:[0-9a-f]{64}$' AND "
                "split_part(snapshot_ref, '/', 4) = "
                "split_part(snapshot_hash, ':', 2))",
            name="ck_evidence_links_snapshot_pair",
        ),
        sa.CheckConstraint(
            "(quote_text IS NULL AND quote_start IS NULL AND quote_end IS NULL) OR "
            "(quote_text IS NOT NULL AND quote_start IS "
                "NOT NULL AND quote_end IS NOT NULL AND "
                "quote_start >= 0 AND quote_end > "
                "quote_start)",
            name="ck_evidence_links_quote_offsets",
        ),
        sa.CheckConstraint("length(reference_key) > 0",
            name="ck_evidence_links_reference_key"),
    )
    op.create_index("ix_evidence_links_team_source", "evidence_links", ["team_id",
        "source_kind", "outcome_id", "signal_id"])


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("evidence_links", "evaluations", "knowledge_items",
        "learning_changes"):
        if connection.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("Cannot downgrade while R6-F learning records "
                "exist; decision history cannot be "
                "reconstructed")
    op.drop_index("ix_evidence_links_team_source", table_name="evidence_links")
    op.drop_table("evidence_links")
    op.drop_index("ix_evaluations_team_outcome_status", table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_index("ix_knowledge_items_team_status", table_name="knowledge_items")
    op.drop_table("knowledge_items")
    op.drop_table("learning_changes")
    op.drop_constraint("uq_outcomes_id_team", "outcomes", type_="unique")
