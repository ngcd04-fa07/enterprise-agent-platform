import uuid

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Fixed at the SQL column level (pgvector requires a fixed dimension per
# column) to match the current embedding provider (FastEmbedProvider,
# BAAI/bge-small-en-v1.5). Swapping to a different-dimension model later
# needs a migration — that's inherent to pgvector, not a design choice.
EMBEDDING_DIMENSION = 384


class DocumentChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A chunk of one page's text (chunks never span pages — see
    docs/architecture.md, chunking decision). Carries its own
    organisation_id and submission_id, denormalized, so retrieval queries
    can filter by tenant/submission directly without joining through
    document -> submission every time.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        sa.UniqueConstraint("document_id", "chunk_index"),
        # Matches the HNSW index hand-created in migration 0004 (Postgres/pgvector
        # index kinds aren't expressible via mapped_column(index=True)). Declaring
        # it here too keeps autogenerate's model-vs-database diff empty instead of
        # proposing to drop it as unmanaged.
        sa.Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("document_pages.id", ondelete="CASCADE"), index=True
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(sa.Integer)
    text: Mapped[str] = mapped_column(sa.Text)
    start_char: Mapped[int] = mapped_column(sa.Integer)
    end_char: Mapped[int] = mapped_column(sa.Integer)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION), nullable=True
    )
