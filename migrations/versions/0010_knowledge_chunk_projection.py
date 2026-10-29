"""Add the rebuildable R6-D knowledge-chunk projection.

Revision ID: 0010_knowledge_chunk_projection
Revises: 0009_task_lifecycle_outcome
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

from core.vector_type import Vector

revision: str = "0010_knowledge_chunk_projection"
down_revision: str | None = "0009_task_lifecycle_outcome"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("signal_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_hash", sa.String(), nullable=False),
        sa.Column("source_snapshot_ref", sa.String(), nullable=False),
        sa.Column("source_content_hash", sa.String(), nullable=False),
        sa.Column("chunking_version", sa.String(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("embedding_provider", sa.String(), nullable=False),
        sa.Column("embedding_model", sa.String(), nullable=False),
        sa.Column("embedding_revision", sa.String(), nullable=False),
        sa.Column("embedding_configuration", sa.String(), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding_space_key", sa.String(), nullable=False),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.id"],
            name="fk_knowledge_chunks_signal",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "signal_id",
            "chunk_index",
            "embedding_space_key",
            name="uq_knowledge_chunks_signal_index_space",
        ),
        sa.CheckConstraint(
            "chunk_index >= 0", name="ck_knowledge_chunks_chunk_index"
        ),
        sa.CheckConstraint(
            "chunk_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_chunks_chunk_hash",
        ),
        sa.CheckConstraint(
            "source_content_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_chunks_source_hash",
        ),
        sa.CheckConstraint(
            "source_snapshot_ref ~ '^snap://sha256/[0-9a-f]{64}$'",
            name="ck_knowledge_chunks_source_snapshot_ref",
        ),
        sa.CheckConstraint(
            "embedding_dimensions > 0 AND "
            "vector_dims(embedding) = embedding_dimensions",
            name="ck_knowledge_chunks_embedding_dimensions",
        ),
        sa.CheckConstraint(
            "embedding_space_key ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_knowledge_chunks_embedding_space_key",
        ),
        sa.CheckConstraint(
            "length(chunking_version) > 0 AND "
            "length(embedding_configuration) > 0",
            name="ck_knowledge_chunks_configuration_nonempty",
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_space_signal",
        "knowledge_chunks",
        ["embedding_space_key", "signal_id"],
    )
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_fts "
        "ON knowledge_chunks USING gin (to_tsvector('simple', chunk_text))"
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_fts", table_name="knowledge_chunks")
    op.drop_index(
        "ix_knowledge_chunks_space_signal", table_name="knowledge_chunks"
    )
    op.drop_table("knowledge_chunks")
