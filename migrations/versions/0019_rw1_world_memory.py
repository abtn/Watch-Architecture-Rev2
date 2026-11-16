"""Add RW-1 world-memory records and reconcile EvidenceLink subjects.

Revision ID: 0019_rw1_world_memory
Revises: 0018_r7b_lifecycle_review_date
"""

from __future__ import annotations

import hashlib
import json
from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_rw1_world_memory"
down_revision: str | None = "0018_r7b_lifecycle_review_date"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _sha256_json(value: dict[str, object]) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _validate_legacy_evidence(connection: sa.Connection) -> int:
    """Fail closed unless every legacy link and Evaluation hash is canonical."""
    links = connection.execute(
        sa.text(
            """
            SELECT
                link.id,
                link.team_id,
                link.subject_kind,
                link.subject_id,
                link.source_kind,
                link.outcome_id,
                link.signal_id,
                link.snapshot_ref,
                link.snapshot_hash,
                link.stance,
                link.quote_text,
                link.quote_start,
                link.quote_end,
                link.reference_key,
                evaluation.id AS evaluation_id,
                evaluation.team_id AS evaluation_team_id,
                evaluation.outcome_id AS evaluation_outcome_id,
                evaluation.conclusion,
                evaluation.findings,
                evaluation.evaluator_kind,
                evaluation.evaluator_identity,
                evaluation.evaluator_revision,
                evaluation.idempotency_key,
                evaluation.proposal_hash,
                task.id AS originating_task_id,
                task.team_id AS task_team_id,
                team.domain AS team_domain,
                signal.domain AS signal_domain
            FROM evidence_links AS link
            LEFT JOIN evaluations AS evaluation
                ON evaluation.id = link.subject_id
            LEFT JOIN tasks AS task
                ON task.id = evaluation.created_by_task_id
            LEFT JOIN teams AS team
                ON team.id = link.team_id
            LEFT JOIN signals AS signal
                ON signal.id = link.signal_id
            ORDER BY link.id
            """
        )
    ).mappings().all()

    grouped: dict[str, list[dict[str, object]]] = {}
    seen_ids: set[str] = set()
    for row in links:
        link_id = str(row["id"])
        if link_id in seen_ids:
            raise RuntimeError(f"RW-1 migration: duplicate legacy link {link_id}")
        seen_ids.add(link_id)
        if row["subject_kind"] != "evaluation":
            raise RuntimeError(
                f"RW-1 migration: unsupported legacy subject on link {link_id}"
            )
        if row["evaluation_id"] is None:
            raise RuntimeError(
                f"RW-1 migration: missing parent Evaluation for link {link_id}"
            )
        if row["originating_task_id"] is None:
            raise RuntimeError(
                f"RW-1 migration: missing originating Task for link {link_id}"
            )
        if (
            row["evaluation_team_id"] != row["team_id"]
            or row["task_team_id"] != row["team_id"]
            or (
                row["source_kind"] == "signal"
                and row["signal_domain"] != row["team_domain"]
            )
        ):
            raise RuntimeError(
                f"RW-1 migration: Team/domain mismatch for legacy link {link_id}"
            )

        item: dict[str, object] = {
            "source_kind": row["source_kind"],
            "outcome_id": str(row["outcome_id"]) if row["outcome_id"] else None,
            "signal_id": str(row["signal_id"]) if row["signal_id"] else None,
            "snapshot_ref": row["snapshot_ref"],
            "snapshot_hash": row["snapshot_hash"],
            "stance": row["stance"],
            "quote_text": row["quote_text"],
            "quote_start": row["quote_start"],
            "quote_end": row["quote_end"],
        }
        expected_reference_key = _sha256_json(item)
        if row["reference_key"] != expected_reference_key:
            raise RuntimeError(
                f"RW-1 migration: EvidenceLink reference hash mismatch for {link_id}"
            )
        item["reference_key"] = row["reference_key"]
        grouped.setdefault(str(row["evaluation_id"]), []).append(item)

    evaluations = connection.execute(
        sa.text(
            """
            SELECT id, team_id, outcome_id, conclusion, findings,
                   evaluator_kind, evaluator_identity, evaluator_revision,
                   idempotency_key, proposal_hash, created_by_task_id
            FROM evaluations
            ORDER BY id
            """
        )
    ).mappings().all()

    for evaluation in evaluations:
        evaluation_id = str(evaluation["id"])
        evaluation_links = grouped.get(evaluation_id, [])
        if not evaluation_links:
            raise RuntimeError(
                f"RW-1 migration: Evaluation {evaluation_id} has no EvidenceLinks"
            )
        evaluation_links.sort(key=lambda item: str(item["reference_key"]))
        payload = {
            "team_id": str(evaluation["team_id"]),
            "outcome_id": str(evaluation["outcome_id"]),
            "conclusion": evaluation["conclusion"],
            "findings": evaluation["findings"],
            "evidence": evaluation_links,
            "evaluator_kind": evaluation["evaluator_kind"],
            "evaluator_identity": evaluation["evaluator_identity"],
            "evaluator_revision": evaluation["evaluator_revision"],
            "idempotency_key": evaluation["idempotency_key"],
        }
        if _sha256_json(payload) != evaluation["proposal_hash"]:
            raise RuntimeError(
                "RW-1 migration: Evaluation proposal hash mismatch for "
                f"{evaluation_id}"
            )

    if len(links) != len(seen_ids):
        raise RuntimeError("RW-1 migration: legacy EvidenceLink row count mismatch")
    return len(links)


def upgrade() -> None:
    connection = op.get_bind()

    op.create_table(
        "threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="fk_threads_team"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "team_id", name="uq_threads_id_team"),
        sa.CheckConstraint(
            "status IN ('active', 'dormant', 'resolved')",
            name="ck_threads_status",
        ),
        sa.CheckConstraint(
            "length(btrim(domain)) > 0 AND length(btrim(title)) > 0",
            name="ck_threads_text",
        ),
    )
    op.create_index(
        "ix_threads_team_status_updated",
        "threads",
        ["team_id", "status", "last_updated_at"],
    )

    op.create_table(
        "hypotheses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("confidence", sa.String(16), nullable=False, server_default="low"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_touched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="fk_hypotheses_team"),
        sa.ForeignKeyConstraint(
            ["thread_id", "team_id"],
            ["threads.id", "threads.team_id"],
            name="fk_hypotheses_thread_team",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "team_id", name="uq_hypotheses_id_team"),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'rejected')",
            name="ck_hypotheses_status",
        ),
        sa.CheckConstraint(
            "confidence IN ('low', 'moderate', 'high')",
            name="ck_hypotheses_confidence",
        ),
        sa.CheckConstraint(
            "length(btrim(statement)) > 0",
            name="ck_hypotheses_statement",
        ),
    )
    op.create_index(
        "ix_hypotheses_team_thread_status",
        "hypotheses",
        ["team_id", "thread_id", "status"],
    )
    op.create_index(
        "ix_hypotheses_team_status_touched",
        "hypotheses",
        ["team_id", "status", "last_touched_at"],
    )

    before_count = connection.scalar(sa.text("SELECT count(*) FROM evidence_links"))
    validated_count = _validate_legacy_evidence(connection)
    if before_count != validated_count:
        raise RuntimeError("RW-1 migration: legacy EvidenceLink count changed")

    op.add_column(
        "evidence_links", sa.Column("evaluation_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "evidence_links", sa.Column("hypothesis_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "evidence_links", sa.Column("originating_task_id", sa.Uuid(), nullable=True)
    )
    connection.execute(
        sa.text(
            """
            UPDATE evidence_links AS link
            SET evaluation_id = evaluation.id,
                originating_task_id = evaluation.created_by_task_id
            FROM evaluations AS evaluation
            JOIN tasks AS task
              ON task.id = evaluation.created_by_task_id
             AND task.team_id = evaluation.team_id
            WHERE link.subject_kind = 'evaluation'
              AND evaluation.id = link.subject_id
              AND evaluation.team_id = link.team_id
            """
        )
    )
    after_count = connection.scalar(sa.text("SELECT count(*) FROM evidence_links"))
    unmapped_count = connection.scalar(
        sa.text(
            """
            SELECT count(*) FROM evidence_links
            WHERE evaluation_id IS NULL OR originating_task_id IS NULL
            """
        )
    )
    if before_count != after_count or unmapped_count:
        raise RuntimeError(
            "RW-1 migration: EvidenceLink backfill incomplete; "
            f"before={before_count}, after={after_count}, unmapped={unmapped_count}"
        )

    op.create_foreign_key(
        "fk_evidence_links_evaluation_subject_team",
        "evidence_links",
        "evaluations",
        ["evaluation_id", "team_id"],
        ["id", "team_id"],
    )
    op.create_foreign_key(
        "fk_evidence_links_hypothesis_team",
        "evidence_links",
        "hypotheses",
        ["hypothesis_id", "team_id"],
        ["id", "team_id"],
    )
    op.create_foreign_key(
        "fk_evidence_links_originating_task_team",
        "evidence_links",
        "tasks",
        ["originating_task_id", "team_id"],
        ["id", "team_id"],
    )
    op.create_unique_constraint(
        "uq_evidence_links_id_team", "evidence_links", ["id", "team_id"]
    )
    op.create_unique_constraint(
        "uq_evidence_links_id_hypothesis_team",
        "evidence_links",
        ["id", "hypothesis_id", "team_id"],
    )
    op.create_unique_constraint(
        "uq_evidence_links_evaluation_reference",
        "evidence_links",
        ["evaluation_id", "reference_key"],
    )
    op.create_unique_constraint(
        "uq_evidence_links_hypothesis_reference",
        "evidence_links",
        ["hypothesis_id", "reference_key"],
    )
    op.create_check_constraint(
        "ck_evidence_links_subject",
        "evidence_links",
        "((subject_kind = 'evaluation' AND evaluation_id IS NOT NULL "
        "AND hypothesis_id IS NULL) OR "
        "(subject_kind = 'hypothesis' AND hypothesis_id IS NOT NULL "
        "AND evaluation_id IS NULL))",
    )
    op.alter_column("evidence_links", "originating_task_id", nullable=False)
    op.drop_constraint(
        "fk_evidence_links_evaluation_team", "evidence_links", type_="foreignkey"
    )
    op.drop_constraint(
        "ck_evidence_links_subject_kind", "evidence_links", type_="check"
    )
    op.drop_constraint(
        "uq_evidence_links_subject_reference", "evidence_links", type_="unique"
    )
    op.drop_column("evidence_links", "subject_id")

    op.create_table(
        "confidence_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("hypothesis_id", sa.Uuid(), nullable=False),
        sa.Column("from_confidence", sa.String(16), nullable=False),
        sa.Column("to_confidence", sa.String(16), nullable=False),
        sa.Column("cause_kind", sa.String(16), nullable=False),
        sa.Column("evidence_link_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_task_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name="fk_confidence_changes_team"
        ),
        sa.ForeignKeyConstraint(
            ["hypothesis_id", "team_id"],
            ["hypotheses.id", "hypotheses.team_id"],
            name="fk_confidence_changes_hypothesis_team",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_link_id", "hypothesis_id", "team_id"],
            [
                "evidence_links.id",
                "evidence_links.hypothesis_id",
                "evidence_links.team_id",
            ],
            name="fk_confidence_changes_evidence_hypothesis_team",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_task_id", "team_id"],
            ["tasks.id", "tasks.team_id"],
            name="fk_confidence_changes_task_team",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "created_by_task_id",
            "idempotency_key",
            name="uq_confidence_changes_task_idempotency",
        ),
        sa.CheckConstraint(
            "from_confidence IN ('low', 'moderate', 'high') AND "
            "to_confidence IN ('low', 'moderate', 'high') AND "
            "from_confidence <> to_confidence",
            name="ck_confidence_changes_bands",
        ),
        sa.CheckConstraint(
            "(cause_kind = 'evidence' AND evidence_link_id IS NOT NULL) OR "
            "(cause_kind = 'decay' AND evidence_link_id IS NULL)",
            name="ck_confidence_changes_cause",
        ),
        sa.CheckConstraint(
            "cause_kind IN ('evidence', 'decay')",
            name="ck_confidence_changes_cause_kind",
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name="ck_confidence_changes_idempotency_key",
        ),
    )
    op.create_index(
        "ix_confidence_changes_team_hypothesis_created",
        "confidence_changes",
        ["team_id", "hypothesis_id", "created_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_world_memory = connection.scalar(
        sa.text(
            """
            SELECT
                EXISTS (SELECT 1 FROM threads) OR
                EXISTS (SELECT 1 FROM hypotheses) OR
                EXISTS (SELECT 1 FROM confidence_changes) OR
                EXISTS (
                    SELECT 1 FROM evidence_links WHERE hypothesis_id IS NOT NULL
                )
            """
        )
    )
    if has_world_memory:
        raise RuntimeError(
            "Cannot downgrade RW-1 while world-memory records or "
            "Hypothesis EvidenceLinks exist; history must not be discarded"
        )

    op.drop_index(
        "ix_confidence_changes_team_hypothesis_created",
        table_name="confidence_changes",
    )
    op.drop_table("confidence_changes")
    op.drop_index(
        "ix_hypotheses_team_status_touched", table_name="hypotheses"
    )
    op.drop_index(
        "ix_hypotheses_team_thread_status", table_name="hypotheses"
    )
    op.drop_table("hypotheses")
    op.drop_index("ix_threads_team_status_updated", table_name="threads")
    op.drop_table("threads")

    op.add_column(
        "evidence_links", sa.Column("subject_id", sa.Uuid(), nullable=True)
    )
    connection.execute(
        sa.text(
            """
            UPDATE evidence_links
            SET subject_id = evaluation_id
            WHERE subject_kind = 'evaluation' AND evaluation_id IS NOT NULL
            """
        )
    )
    missing_subjects = connection.scalar(
        sa.text("SELECT count(*) FROM evidence_links WHERE subject_id IS NULL")
    )
    if missing_subjects:
        raise RuntimeError(
            "Cannot downgrade RW-1: Evaluation subject reconstruction incomplete"
        )

    op.create_foreign_key(
        "fk_evidence_links_evaluation_team",
        "evidence_links",
        "evaluations",
        ["subject_id", "team_id"],
        ["id", "team_id"],
    )
    op.create_unique_constraint(
        "uq_evidence_links_subject_reference",
        "evidence_links",
        ["subject_id", "reference_key"],
    )
    op.create_check_constraint(
        "ck_evidence_links_subject_kind",
        "evidence_links",
        "subject_kind = 'evaluation'",
    )
    op.drop_constraint(
        "ck_evidence_links_subject", "evidence_links", type_="check"
    )
    op.drop_constraint(
        "uq_evidence_links_evaluation_reference", "evidence_links", type_="unique"
    )
    op.drop_constraint(
        "uq_evidence_links_hypothesis_reference", "evidence_links", type_="unique"
    )
    op.drop_constraint(
        "uq_evidence_links_id_hypothesis_team", "evidence_links", type_="unique"
    )
    op.drop_constraint(
        "uq_evidence_links_id_team", "evidence_links", type_="unique"
    )
    op.drop_constraint(
        "fk_evidence_links_originating_task_team",
        "evidence_links",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_evidence_links_hypothesis_team", "evidence_links", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_evidence_links_evaluation_subject_team",
        "evidence_links",
        type_="foreignkey",
    )
    op.drop_column("evidence_links", "evaluation_id")
    op.drop_column("evidence_links", "hypothesis_id")
    op.drop_column("evidence_links", "originating_task_id")
    op.alter_column("evidence_links", "subject_id", nullable=False)
