import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.base import EmbeddingProvider
from app.ingestion.chunking import chunk_text
from app.ingestion.pdf_parser import extract_pages
from app.models.document import Document, DocumentStatus
from app.models.document_page import DocumentPage
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_page_repository import DocumentPageRepository
from app.repositories.document_repository import DocumentRepository
from app.storage.base import ObjectStorage

logger = logging.getLogger(__name__)


class IngestionService:
    """Parses a stored PDF into pages, chunks each page's text, embeds
    every chunk, and persists all three with provenance (document_id,
    page_id, organisation_id, submission_id — see the DocumentChunk
    model). Runs synchronously within the upload request for now — see
    docs/architecture.md, background jobs decision, for why (and what
    would need to change to make BackgroundTasks safe here).
    """

    def __init__(
        self, db: AsyncSession, storage: ObjectStorage, embeddings: EmbeddingProvider
    ) -> None:
        self._storage = storage
        self._embeddings = embeddings
        self._documents = DocumentRepository(db)
        self._pages = DocumentPageRepository(db)
        self._chunks = DocumentChunkRepository(db)

    async def ingest_document(self, document: Document) -> Document:
        await self._documents.update_status(
            organisation_id=document.organisation_id,
            document_id=document.id,
            status=DocumentStatus.PROCESSING,
        )

        try:
            data = await self._storage.get_object(document.storage_key)
            page_texts = extract_pages(data)

            pages_with_chunks: list[tuple[DocumentPage, list[tuple[str, int, int]]]] = []
            for page_number, page_text in enumerate(page_texts, start=1):
                page = await self._pages.create(
                    document_id=document.id,
                    organisation_id=document.organisation_id,
                    page_number=page_number,
                    text=page_text,
                )
                pages_with_chunks.append((page, chunk_text(page_text)))

            chunk_specs = [
                (page, text, start_char, end_char)
                for page, chunks in pages_with_chunks
                for text, start_char, end_char in chunks
            ]

            embeddings = (
                await self._embeddings.embed_documents([spec[1] for spec in chunk_specs])
                if chunk_specs
                else []
            )

            for chunk_index, ((page, text, start_char, end_char), embedding) in enumerate(
                zip(chunk_specs, embeddings, strict=True)
            ):
                await self._chunks.create(
                    document_id=document.id,
                    page_id=page.id,
                    organisation_id=document.organisation_id,
                    submission_id=document.submission_id,
                    chunk_index=chunk_index,
                    text=text,
                    start_char=start_char,
                    end_char=end_char,
                    embedding=embedding,
                )
        except Exception:
            logger.warning("document ingestion failed for %s", document.id, exc_info=True)
            return await self._set_status(document, DocumentStatus.FAILED)

        return await self._set_status(document, DocumentStatus.READY)

    async def _set_status(self, document: Document, status: DocumentStatus) -> Document:
        updated = await self._documents.update_status(
            organisation_id=document.organisation_id, document_id=document.id, status=status
        )
        if updated is None:
            raise RuntimeError(f"document {document.id} disappeared during ingestion")
        return updated
