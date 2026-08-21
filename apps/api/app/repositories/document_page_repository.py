import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_page import DocumentPage


class DocumentPageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, document_id: uuid.UUID, organisation_id: uuid.UUID, page_number: int, text: str
    ) -> DocumentPage:
        page = DocumentPage(
            document_id=document_id,
            organisation_id=organisation_id,
            page_number=page_number,
            text=text,
        )
        self._session.add(page)
        await self._session.flush()
        return page

    async def list_for_document(
        self, *, organisation_id: uuid.UUID, document_id: uuid.UUID
    ) -> list[DocumentPage]:
        result = await self._session.execute(
            select(DocumentPage)
            .where(
                DocumentPage.organisation_id == organisation_id,
                DocumentPage.document_id == document_id,
            )
            .order_by(DocumentPage.page_number)
        )
        return list(result.scalars().all())
