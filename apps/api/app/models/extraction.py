import enum
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column


class ExtractionStatus(enum.StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExtractionRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per extraction attempt on a submission — the "AI runs are
    traced and persisted" requirement (CLAUDE.md), scoped to what this
    stage actually needs: which model ran, whether it succeeded, and how
    many fields it found. Not a full tracing system (later stage) — just
    enough to answer "did this run, with what model, and did it work."
    """

    __tablename__ = "extraction_runs"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(sa.String(50))
    model: Mapped[str] = mapped_column(sa.String(100))
    status: Mapped[ExtractionStatus] = mapped_column(
        str_enum_column(ExtractionStatus, name="extraction_status")
    )
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    fields_extracted_count: Mapped[int] = mapped_column(sa.Integer, default=0)


class ExtractedField(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One current value for one field on one submission. Re-extraction
    replaces (deletes + re-inserts) rather than accumulating history — see
    ExtractionService. Provenance is a single source chunk, never asked of
    the model: ExtractionService runs one generation per chunk and records
    exactly the chunk it was reading when a field was found, so a citation
    can never point at a chunk the field didn't actually come from (unlike
    a single pass over the whole submission asking the model to also name
    its source, which would need a deterministic existence check against
    a citation the model could still get wrong in ways an existence check
    can't catch, e.g. citing a real but wrong chunk).
    """

    __tablename__ = "extracted_fields"
    __table_args__ = (sa.UniqueConstraint("submission_id", "field_name"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("extraction_runs.id", ondelete="CASCADE"), index=True
    )
    source_chunk_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True
    )
    field_name: Mapped[str] = mapped_column(sa.String(100))
    value: Mapped[str] = mapped_column(sa.Text)
