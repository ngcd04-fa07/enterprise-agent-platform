import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk
from app.models.document_page import DocumentPage
from app.models.extraction import ExtractedField


class ExtractedFieldRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        organisation_id: uuid.UUID,
        submission_id: uuid.UUID,
        extraction_run_id: uuid.UUID,
        source_chunk_id: uuid.UUID,
        field_name: str,
        value: str,
    ) -> ExtractedField:
        field = ExtractedField(
            organisation_id=organisation_id,
            submission_id=submission_id,
            extraction_run_id=extraction_run_id,
            source_chunk_id=source_chunk_id,
            field_name=field_name,
            value=value,
        )
        self._session.add(field)
        await self._session.flush()
        return field

    async def delete_for_submission(
        self, *, organisation_id: uuid.UUID, submission_id: uuid.UUID
    ) -> None:
        """Clears any previous extraction's fields before a re-extraction
        writes fresh ones — see ExtractedField's docstring on why this
        replaces rather than accumulates history.
        """
        await self._session.execute(
            delete(ExtractedField).where(
                ExtractedField.organisation_id == organisation_id,
                ExtractedField.submission_id == submission_id,
            )
        )
        await self._session.flush()

    async def list_for_submission(
        self, *, organisation_id: uuid.UUID, submission_id: uuid.UUID
    ) -> list[tuple[ExtractedField, uuid.UUID, int]]:
        """Returns (field, source_document_id, source_page_number) triples
        — joined from the field's source chunk, the same
        join-for-provenance pattern DocumentChunkRepository.search_similar
        uses, so callers get a source-aware result without a query per
        field.
        """
        result = await self._session.execute(
            select(ExtractedField, DocumentChunk.document_id, DocumentPage.page_number)
            .join(DocumentChunk, ExtractedField.source_chunk_id == DocumentChunk.id)
            .join(DocumentPage, DocumentChunk.page_id == DocumentPage.id)
            .where(
                ExtractedField.organisation_id == organisation_id,
                ExtractedField.submission_id == submission_id,
            )
            .order_by(ExtractedField.field_name)
        )
        return [
            (field, document_id, page_number) for field, document_id, page_number in result.all()
        ]
