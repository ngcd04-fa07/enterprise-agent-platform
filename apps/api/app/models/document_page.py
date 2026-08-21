import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentPage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per extracted PDF page. organisation_id is denormalized
    from document.organisation_id, consistent with Document's own
    denormalization from Submission — see docs/architecture.md, tenant
    isolation decision.
    """

    __tablename__ = "document_pages"
    __table_args__ = (sa.UniqueConstraint("document_id", "page_number"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int] = mapped_column(sa.Integer)
    text: Mapped[str] = mapped_column(sa.Text)
