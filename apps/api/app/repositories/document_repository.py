import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus


class DocumentRepository:
    """Metadata persistence only — see app.models.document. No service layer
    sits on top of this yet: real document creation needs the object
    storage abstraction (Stage 4), so wiring this up to an API endpoint now
    would be a fake upload path. The repository exists so Stage 4/5 can
    build on a tested persistence layer instead of writing it under
    ingestion-pipeline time pressure.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        organisation_id: uuid.UUID,
        submission_id: uuid.UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_key: str,
    ) -> Document:
        document = Document(
            organisation_id=organisation_id,
            submission_id=submission_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_key=storage_key,
        )
        self._session.add(document)
        await self._session.flush()
        return document

    async def get(self, *, organisation_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
        result = await self._session.execute(
            select(Document).where(
                Document.id == document_id, Document.organisation_id == organisation_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_submission(
        self, *, organisation_id: uuid.UUID, submission_id: uuid.UUID
    ) -> list[Document]:
        result = await self._session.execute(
            select(Document).where(
                Document.organisation_id == organisation_id,
                Document.submission_id == submission_id,
            )
        )
        return list(result.scalars().all())

    async def update_status(
        self, *, organisation_id: uuid.UUID, document_id: uuid.UUID, status: DocumentStatus
    ) -> Document | None:
        document = await self.get(organisation_id=organisation_id, document_id=document_id)
        if document is None:
            return None
        document.status = status
        await self._session.flush()
        return document
