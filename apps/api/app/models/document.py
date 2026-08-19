import enum
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.submission import Submission


class DocumentStatus(enum.StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Metadata only. The object storage abstraction (Stage 4) owns actually
    writing/reading document bytes at `storage_key`; this model just tracks
    that a document exists and its processing state.

    organisation_id is denormalized from submission.organisation_id rather
    than derived via a join — every tenant-owned row carries its own
    organisation_id so repository queries can filter on it directly (see
    docs/architecture.md, tenant isolation decision).
    """

    __tablename__ = "documents"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(sa.String(512))
    content_type: Mapped[str] = mapped_column(sa.String(255))
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger)
    storage_key: Mapped[str] = mapped_column(sa.String(1024))
    status: Mapped[DocumentStatus] = mapped_column(
        sa.Enum(DocumentStatus, name="document_status"), default=DocumentStatus.UPLOADED
    )

    submission: Mapped["Submission"] = relationship(back_populates="documents")
