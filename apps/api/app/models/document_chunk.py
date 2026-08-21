import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A chunk of one page's text (chunks never span pages — see
    docs/architecture.md, chunking decision). Carries its own
    organisation_id and submission_id, denormalized, so retrieval queries
    (Stage 6) can filter by tenant/submission directly without joining
    through document -> submission every time.

    No embedding column yet — that lands in Stage 6 alongside pgvector,
    once an embedding provider is actually chosen.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (sa.UniqueConstraint("document_id", "chunk_index"),)

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
