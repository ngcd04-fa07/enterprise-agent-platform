import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk


class DocumentChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        document_id: uuid.UUID,
        page_id: uuid.UUID,
        organisation_id: uuid.UUID,
        submission_id: uuid.UUID,
        chunk_index: int,
        text: str,
        start_char: int,
        end_char: int,
    ) -> DocumentChunk:
        chunk = DocumentChunk(
            document_id=document_id,
            page_id=page_id,
            organisation_id=organisation_id,
            submission_id=submission_id,
            chunk_index=chunk_index,
            text=text,
            start_char=start_char,
            end_char=end_char,
        )
        self._session.add(chunk)
        await self._session.flush()
        return chunk

    async def list_for_document(
        self, *, organisation_id: uuid.UUID, document_id: uuid.UUID
    ) -> list[DocumentChunk]:
        result = await self._session.execute(
            select(DocumentChunk)
            .where(
                DocumentChunk.organisation_id == organisation_id,
                DocumentChunk.document_id == document_id,
            )
            .order_by(DocumentChunk.chunk_index)
        )
        return list(result.scalars().all())
