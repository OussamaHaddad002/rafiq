"""documents, chunks and message sources

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("source", name=op.f("uq_documents_source")),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(length=500), nullable=True),
        sa.Column("lang", sa.String(length=2), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', search_text)", persisted=True),
            nullable=False,
        ),
        sa.Column("embedding", Vector(dim=1536), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
    )
    op.create_index(op.f("ix_chunks_document_id"), "chunks", ["document_id"], unique=False)
    op.create_index(
        "ix_chunks_embedding",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_chunks_search_vector",
        "chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.add_column(
        "messages",
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "sources")
    op.drop_index("ix_chunks_search_vector", table_name="chunks")
    op.drop_index("ix_chunks_embedding", table_name="chunks")
    op.drop_index(op.f("ix_chunks_document_id"), table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("documents")
