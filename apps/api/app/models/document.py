from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Computed, ForeignKey, Identity, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# Must match the embedding model's output size (text-embedding-3-small: 1536).
EMBEDDING_DIM = 1536


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # File name in the knowledge-base directory, e.g. "tarifs.pdf". Shown in citations.
    source: Mapped[str] = mapped_column(String(255), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    # sha256 of the file bytes: unchanged files are skipped on re-ingestion.
    content_hash: Mapped[str] = mapped_column(String(64))
    # Vectors from different models are not comparable, so search filters on this.
    embedding_model: Mapped[str] = mapped_column(String(100))


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(500))
    lang: Mapped[str] = mapped_column(String(2))
    content: Mapped[str] = mapped_column(Text)
    # Normalized text (lowercase, no diacritics, unified Arabic letters) for keyword search.
    search_text: Mapped[str] = mapped_column(Text)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', search_text)", persisted=True)
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
