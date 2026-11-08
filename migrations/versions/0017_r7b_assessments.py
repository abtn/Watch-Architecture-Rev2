"""Create immutable R7-B knowledge assessment records.

Revision ID: 0017_r7b_assessments
Revises: 0016_team_exp_history_pins
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_r7b_assessments"
down_revision: str | None = "0016_team_exp_history_pins"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_immutability_protection() -> None:
    op.execute(
        """
        CREATE FUNCTION watch_reject_immutable_assessment_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION USING
                ERRCODE = '55000',
                MESSAGE = format('%s is immutable', TG_TABLE_NAME);
        END;
        $$
        """
    )

    for table, short_name in (
        ("learning_change_operator_provenance", "operator_provenance"),
        ("knowledge_revalidation_assessments", "revalidation_assessment"),
        ("knowledge_lifecycle_assessments", "lifecycle_assessment"),
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{short_name}_immutable_row
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION watch_reject_immutable_assessment_mutation()
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER trg_{short_name}_immutable_truncate
            BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT
            EXECUTE FUNCTION watch_reject_immutable_assessment_mutation()
            """
        )


def upgrade() -> None:
    # These composite parent keys were introduced by the B3.2 ORM contract.
    # The referenced primary keys alone cannot support the composite FKs below.
    op.create_unique_constraint(
        "uq_learning_changes_id_operation_team",
        "learning_changes",
        ["id", "operation", "team_id"],
    )
    op.create_unique_constraint(
        "uq_learning_changes_id_target_team",
        "learning_changes",
        ["id", "target_id", "team_id"],
    )
    op.create_unique_constraint(
        "uq_events_id_task",
        "events",
        ["id", "task_id"],
    )

    op.create_table(
        "learning_change_operator_provenance",
        sa.Column("learning_change_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "learning_change_id",
            name="pk_learning_change_operator_provenance",
        ),
        sa.ForeignKeyConstraint(
            ["learning_change_id", "team_id"],
            ["learning_changes.id", "learning_changes.team_id"],
            name="fk_learning_change_operator_provenance_learning_change_team",
        ),
        sa.CheckConstraint(
            "length(issuer) > 0 AND length(subject) > 0",
            name="ck_learning_change_operator_provenance_identity",
        ),
    )

    op.create_table(
        "knowledge_revalidation_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("task_attempt", sa.Integer(), nullable=False),
        sa.Column("learning_change_id", sa.Uuid(), nullable=False),
        sa.Column(
            "operation",
            sa.String(length=16),
            server_default=sa.text("'revalidate'"),
            nullable=False,
        ),
        sa.Column("knowledge_item_id", sa.Uuid(), nullable=False),
        sa.Column("current_learning_change_id", sa.Uuid(), nullable=False),
        sa.Column("target_content_version", sa.Integer(), nullable=False),
        sa.Column("target_content_hash", sa.String(length=71), nullable=False),
        sa.Column(
            "target_content_hash_scheme", sa.String(length=64), nullable=False
        ),
        sa.Column("target_state_hash", sa.String(length=71), nullable=False),
        sa.Column("proposal_hash", sa.String(length=71), nullable=False),
        sa.Column("proposed_state_hash", sa.String(length=71), nullable=False),
        sa.Column("evidence_basis_hash", sa.String(length=71), nullable=False),
        sa.Column(
            "evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("assessment_version", sa.Integer(), nullable=False),
        sa.Column("evaluator_identity", sa.String(length=255), nullable=False),
        sa.Column("evaluator_revision", sa.String(length=255), nullable=False),
        sa.Column("freshness_disposition", sa.String(length=32), nullable=False),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assessment_result", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=71), nullable=False),
        sa.Column("request_event_id", sa.Uuid(), nullable=False),
        sa.Column("request_event_payload_hash", sa.String(length=71), nullable=False),
        sa.Column("recorded_event_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=71), nullable=False),
        sa.PrimaryKeyConstraint(
            "id", name="pk_knowledge_revalidation_assessments"
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "team_id"],
            ["tasks.id", "tasks.team_id"],
            name="fk_knowledge_revalidation_assessments_task_team",
        ),
        sa.ForeignKeyConstraint(
            ["learning_change_id", "operation", "team_id"],
            [
                "learning_changes.id",
                "learning_changes.operation",
                "learning_changes.team_id",
            ],
            name="fk_kra_learning_change_operation_team",
        ),
        sa.ForeignKeyConstraint(
            ["learning_change_id", "knowledge_item_id", "team_id"],
            [
                "learning_changes.id",
                "learning_changes.target_id",
                "learning_changes.team_id",
            ],
            name="fk_kra_learning_change_target_team",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_item_id", "team_id"],
            ["knowledge_items.id", "knowledge_items.team_id"],
            name="fk_knowledge_revalidation_assessments_knowledge_item_team",
        ),
        sa.ForeignKeyConstraint(
            ["current_learning_change_id", "team_id"],
            ["learning_changes.id", "learning_changes.team_id"],
            name="fk_knowledge_revalidation_assessments_current_change_team",
        ),
        sa.ForeignKeyConstraint(
            ["request_event_id", "task_id"],
            ["events.id", "events.task_id"],
            name="fk_knowledge_revalidation_assessments_request_event_task",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_event_id", "task_id"],
            ["events.id", "events.task_id"],
            name="fk_knowledge_revalidation_assessments_recorded_event_task",
        ),
        sa.UniqueConstraint(
            "id", "team_id", name="uq_knowledge_revalidation_assessments_id_team"
        ),
        sa.UniqueConstraint(
            "team_id",
            "learning_change_id",
            name="uq_knowledge_revalidation_assessments_team_learning_change",
        ),
        sa.UniqueConstraint(
            "task_id", name="uq_knowledge_revalidation_assessments_task"
        ),
        sa.UniqueConstraint(
            "task_id",
            "idempotency_key",
            name="uq_knowledge_revalidation_assessments_task_idempotency",
        ),
        sa.UniqueConstraint(
            "request_event_id",
            name="uq_knowledge_revalidation_assessments_request_event",
        ),
        sa.UniqueConstraint(
            "recorded_event_id",
            name="uq_knowledge_revalidation_assessments_recorded_event",
        ),
        sa.CheckConstraint(
            "operation = 'revalidate'",
            name="ck_knowledge_revalidation_assessments_operation",
        ),
        sa.CheckConstraint(
            "assessment_version > 0 AND task_attempt > 0 "
            "AND target_content_version > 0",
            name="ck_knowledge_revalidation_assessments_version_attempt",
        ),
        sa.CheckConstraint(
            "length(idempotency_key) > 0 AND length(evaluator_identity) > 0 "
            "AND length(evaluator_revision) > 0",
            name="ck_knowledge_revalidation_assessments_identity",
        ),
        sa.CheckConstraint(
            "target_content_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "target_state_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "proposal_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "proposed_state_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "evidence_basis_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "request_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "request_event_payload_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "payload_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_revalidation_assessments_hashes",
        ),
        sa.CheckConstraint(
            "target_content_hash_scheme = 'watch.r7b.knowledge-content.v2'",
            name="ck_knowledge_revalidation_assessments_content_hash_scheme",
        ),
        sa.CheckConstraint(
            "freshness_disposition IN "
            "('current', 'stale', 'insufficient', 'conflicting', 'unassessable')",
            name="ck_knowledge_revalidation_assessments_freshness",
        ),
        sa.CheckConstraint(
            "assessment_result IN ('supported', 'not_supported', 'indeterminate')",
            name="ck_knowledge_revalidation_assessments_result",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_refs) = 'array' "
            "AND jsonb_typeof(findings) = 'array'",
            name="ck_knowledge_revalidation_assessments_payload_shape",
        ),
        sa.CheckConstraint(
            "request_event_id <> recorded_event_id",
            name="ck_knowledge_revalidation_assessments_distinct_events",
        ),
    )

    op.create_table(
        "knowledge_lifecycle_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("task_attempt", sa.Integer(), nullable=False),
        sa.Column("learning_change_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("knowledge_item_id", sa.Uuid(), nullable=False),
        sa.Column("current_learning_change_id", sa.Uuid(), nullable=False),
        sa.Column("target_content_version", sa.Integer(), nullable=False),
        sa.Column("target_content_hash", sa.String(length=71), nullable=False),
        sa.Column(
            "target_content_hash_scheme", sa.String(length=64), nullable=False
        ),
        sa.Column("target_state_hash", sa.String(length=71), nullable=False),
        sa.Column("proposal_hash", sa.String(length=71), nullable=False),
        sa.Column("proposed_state_hash", sa.String(length=71), nullable=False),
        sa.Column("evidence_basis_hash", sa.String(length=71), nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assessment_version", sa.Integer(), nullable=False),
        sa.Column(
            "operator_rationale",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assessment_result", sa.String(length=32), nullable=False),
        sa.Column(
            "variant_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("successor_knowledge_item_id", sa.Uuid(), nullable=True),
        sa.Column("successor_current_learning_change_id", sa.Uuid(), nullable=True),
        sa.Column("successor_content_version", sa.Integer(), nullable=True),
        sa.Column("successor_content_hash", sa.String(length=71), nullable=True),
        sa.Column("successor_content_hash_scheme", sa.String(length=64), nullable=True),
        sa.Column("successor_status", sa.String(length=32), nullable=True),
        sa.Column("successor_review_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("successor_state_hash", sa.String(length=71), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=71), nullable=False),
        sa.Column("request_event_id", sa.Uuid(), nullable=False),
        sa.Column("request_event_payload_hash", sa.String(length=71), nullable=False),
        sa.Column("recorded_event_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=71), nullable=False),
        sa.PrimaryKeyConstraint(
            "id", name="pk_knowledge_lifecycle_assessments"
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "team_id"],
            ["tasks.id", "tasks.team_id"],
            name="fk_knowledge_lifecycle_assessments_task_team",
        ),
        sa.ForeignKeyConstraint(
            ["learning_change_id", "operation", "team_id"],
            [
                "learning_changes.id",
                "learning_changes.operation",
                "learning_changes.team_id",
            ],
            name="fk_kla_learning_change_operation_team",
        ),
        sa.ForeignKeyConstraint(
            ["learning_change_id", "knowledge_item_id", "team_id"],
            [
                "learning_changes.id",
                "learning_changes.target_id",
                "learning_changes.team_id",
            ],
            name="fk_knowledge_lifecycle_assessments_learning_change_target_team",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_item_id", "team_id"],
            ["knowledge_items.id", "knowledge_items.team_id"],
            name="fk_knowledge_lifecycle_assessments_knowledge_item_team",
        ),
        sa.ForeignKeyConstraint(
            ["current_learning_change_id", "team_id"],
            ["learning_changes.id", "learning_changes.team_id"],
            name="fk_knowledge_lifecycle_assessments_current_change_team",
        ),
        sa.ForeignKeyConstraint(
            ["successor_knowledge_item_id", "team_id"],
            ["knowledge_items.id", "knowledge_items.team_id"],
            name="fk_knowledge_lifecycle_assessments_successor_item_team",
        ),
        sa.ForeignKeyConstraint(
            ["successor_current_learning_change_id", "team_id"],
            ["learning_changes.id", "learning_changes.team_id"],
            name="fk_kla_successor_current_change_team",
        ),
        sa.ForeignKeyConstraint(
            ["learning_change_id"],
            ["learning_change_operator_provenance.learning_change_id"],
            name="fk_knowledge_lifecycle_assessments_operator_provenance",
        ),
        sa.ForeignKeyConstraint(
            ["request_event_id", "task_id"],
            ["events.id", "events.task_id"],
            name="fk_knowledge_lifecycle_assessments_request_event_task",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_event_id", "task_id"],
            ["events.id", "events.task_id"],
            name="fk_knowledge_lifecycle_assessments_recorded_event_task",
        ),
        sa.UniqueConstraint(
            "id", "team_id", name="uq_knowledge_lifecycle_assessments_id_team"
        ),
        sa.UniqueConstraint(
            "team_id",
            "learning_change_id",
            name="uq_knowledge_lifecycle_assessments_team_learning_change",
        ),
        sa.UniqueConstraint(
            "task_id", name="uq_knowledge_lifecycle_assessments_task"
        ),
        sa.UniqueConstraint(
            "task_id",
            "idempotency_key",
            name="uq_knowledge_lifecycle_assessments_task_idempotency",
        ),
        sa.UniqueConstraint(
            "request_event_id",
            name="uq_knowledge_lifecycle_assessments_request_event",
        ),
        sa.UniqueConstraint(
            "recorded_event_id",
            name="uq_knowledge_lifecycle_assessments_recorded_event",
        ),
        sa.CheckConstraint(
            "operation IN ('retire', 'supersede')",
            name="ck_knowledge_lifecycle_assessments_operation",
        ),
        sa.CheckConstraint(
            "assessment_version > 0 AND task_attempt > 0 "
            "AND target_content_version > 0 "
            "AND (successor_content_version IS NULL OR successor_content_version > 0)",
            name="ck_knowledge_lifecycle_assessments_version_attempt",
        ),
        sa.CheckConstraint(
            "length(idempotency_key) > 0",
            name="ck_knowledge_lifecycle_assessments_idempotency",
        ),
        sa.CheckConstraint(
            "target_content_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "target_state_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "proposal_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "proposed_state_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "evidence_basis_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "request_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "request_event_payload_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "payload_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_lifecycle_assessments_hashes",
        ),
        sa.CheckConstraint(
            "target_content_hash_scheme = 'watch.r7b.knowledge-content.v2'",
            name="ck_knowledge_lifecycle_assessments_content_hash_scheme",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_refs) = 'array' AND "
            "jsonb_typeof(findings) = 'array' AND "
            "jsonb_typeof(operator_rationale) = 'object' AND "
            "jsonb_typeof(variant_payload) = 'object'",
            name="ck_knowledge_lifecycle_assessments_payload_shape",
        ),
        sa.CheckConstraint(
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
            "successor_state_hash IS NOT NULL)",
            name="ck_knowledge_lifecycle_assessments_variant_shape",
        ),
        sa.CheckConstraint(
            "successor_knowledge_item_id IS NULL OR "
            "successor_knowledge_item_id <> knowledge_item_id",
            name="ck_knowledge_lifecycle_assessments_no_self_supersession",
        ),
        sa.CheckConstraint(
            "successor_content_hash IS NULL OR "
            "successor_content_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_lifecycle_assessments_successor_hash",
        ),
        sa.CheckConstraint(
            "successor_content_hash_scheme IS NULL OR "
            "successor_content_hash_scheme = 'watch.r7b.knowledge-content.v2'",
            name="ck_knowledge_lifecycle_assessments_successor_hash_scheme",
        ),
        sa.CheckConstraint(
            "successor_status IS NULL OR "
            "successor_status IN ('active', 'needs_review', 'retired')",
            name="ck_knowledge_lifecycle_assessments_successor_status",
        ),
        sa.CheckConstraint(
            "successor_state_hash IS NULL OR "
            "successor_state_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_lifecycle_assessments_successor_state_hash",
        ),
        sa.CheckConstraint(
            "assessment_result IN ('eligible', 'ineligible')",
            name="ck_knowledge_lifecycle_assessments_result",
        ),
        sa.CheckConstraint(
            "request_event_id <> recorded_event_id",
            name="ck_knowledge_lifecycle_assessments_distinct_events",
        ),
    )

    _create_immutability_protection()


def downgrade() -> None:
    connection = op.get_bind()
    has_rows = connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM learning_change_operator_provenance) "
            "OR EXISTS (SELECT 1 FROM knowledge_revalidation_assessments) "
            "OR EXISTS (SELECT 1 FROM knowledge_lifecycle_assessments)"
        )
    )
    if has_rows:
        raise RuntimeError(
            "Cannot downgrade R7-B assessment persistence while immutable "
            "provenance or assessment records exist"
        )

    for table, short_name in (
        ("learning_change_operator_provenance", "operator_provenance"),
        ("knowledge_revalidation_assessments", "revalidation_assessment"),
        ("knowledge_lifecycle_assessments", "lifecycle_assessment"),
    ):
        op.execute(f"DROP TRIGGER trg_{short_name}_immutable_truncate ON {table}")
        op.execute(f"DROP TRIGGER trg_{short_name}_immutable_row ON {table}")

    op.execute("DROP FUNCTION watch_reject_immutable_assessment_mutation()")
    op.drop_table("knowledge_lifecycle_assessments")
    op.drop_table("knowledge_revalidation_assessments")
    op.drop_table("learning_change_operator_provenance")
    op.drop_constraint(
        "uq_events_id_task", "events", type_="unique"
    )
    op.drop_constraint(
        "uq_learning_changes_id_target_team", "learning_changes", type_="unique"
    )
    op.drop_constraint(
        "uq_learning_changes_id_operation_team",
        "learning_changes",
        type_="unique",
    )
