import enum
import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column

if TYPE_CHECKING:
    from app.models.document import Document


class SubmissionStatus(enum.StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    CLOSED = "closed"


class Submission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "submissions"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(sa.String(255))
    status: Mapped[SubmissionStatus] = mapped_column(
        str_enum_column(SubmissionStatus, name="submission_status"), default=SubmissionStatus.DRAFT
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
