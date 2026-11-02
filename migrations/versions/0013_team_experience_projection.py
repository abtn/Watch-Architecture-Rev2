"""Add the separate R6-F Team Experience projection and TeamPolicy schema version.

Revision ID: 0013_team_experience_projection
Revises: 0012_learning_foundation
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

from core.vector_type import Vector

revision: str = "0013_team_experience_projection"
down_revision: str | None = "0012_learning_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing policies remain schema v1. A future explicitly created policy
    # may opt into v2 to configure the D7 review interval.
    op.add_column(
        "team_policies",
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_team_policies_schema_version",
        "team_policies",
        "schema_version >= 1",
    )

    op.create_table(
        "team_experience_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_item_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("item_version", sa.Integer(), nullable=False),
        sa.Column("item_content_hash", sa.String(), nullable=False),
        sa.Column("origin_learning_change_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_hash", sa.String(), nullable=False),
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
            ["knowledge_item_id", "team_id"],
            ["knowledge_items.id", "knowledge_items.team_id"],
            name="fk_team_experience_chunks_item_team",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["origin_learning_change_id", "team_id"],
            ["learning_changes.id", "learning_changes.team_id"],
            name="fk_team_experience_chunks_learning_change_team",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "knowledge_item_id",
            "item_version",
            "chunk_index",
            "embedding_space_key",
            name="uq_team_experience_chunks_item_index_space",
        ),
        sa.CheckConstraint(
            "item_version > 0 AND chunk_index >= 0",
            name="ck_team_experience_chunks_item_chunk",
        ),
        sa.CheckConstraint(
            "item_content_hash ~ '^sha256:[0-9a-f]{64}$' AND "
            "chunk_hash ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_team_experience_chunks_hashes",
        ),
        sa.CheckConstraint(
            "embedding_dimensions > 0 AND "
            "vector_dims(embedding) = embedding_dimensions",
            name="ck_team_experience_chunks_embedding_dimensions",
        ),
        sa.CheckConstraint(
            "embedding_space_key ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_team_experience_chunks_embedding_space_key",
        ),
        sa.CheckConstraint(
            "length(chunking_version) > 0 AND "
            "length(embedding_configuration) > 0",
            name="ck_team_experience_chunks_configuration",
        ),
    )
    op.create_index(
        "ix_team_experience_chunks_team_space_item",
        "team_experience_chunks",
        ["team_id", "embedding_space_key", "knowledge_item_id"],
    )
    op.execute(
        "CREATE INDEX ix_team_experience_chunks_fts "
        "ON team_experience_chunks USING gin "
        "(to_tsvector('simple', chunk_text))"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM team_experience_chunks)")
    ):
        raise RuntimeError(
            "Cannot downgrade while Team Experience projection rows exist"
        )
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM team_policies WHERE schema_version > 1)")
    ):
        raise RuntimeError(
            "Cannot downgrade after a TeamPolicy has opted into schema v2"
        )
    op.drop_index("ix_team_experience_chunks_fts", table_name="team_experience_chunks")
    op.drop_index(
        "ix_team_experience_chunks_team_space_item",
        table_name="team_experience_chunks",
    )
    op.drop_table("team_experience_chunks")
    op.drop_constraint(
        "ck_team_policies_schema_version", "team_policies", type_="check"
    )
    op.drop_column("team_policies", "schema_version")
