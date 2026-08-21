import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.storage.base import ObjectStorage

# Section 14 of the project brief: PDF is the only supported format so far.
ALLOWED_CONTENT_TYPES = {"application/pdf"}
PDF_MAGIC_BYTES = b"%PDF-"


class UnsupportedContentTypeError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


class InvalidFileContentError(Exception):
    """The declared content-type doesn't match what the bytes actually
    are. Never trust a filename extension or Content-Type header alone
    (see docs/architecture.md) — a client can label anything
    "application/pdf".
    """


class DocumentService:
    def __init__(self, db: AsyncSession, storage: ObjectStorage) -> None:
        self._documents = DocumentRepository(db)
        self._storage = storage

    async def upload_document(
        self,
        *,
        organisation_id: uuid.UUID,
        submission_id: uuid.UUID,
        filename: str,
        content_type: str,
        data: bytes,
        max_upload_size_bytes: int,
    ) -> Document:
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise UnsupportedContentTypeError(content_type)
        if len(data) > max_upload_size_bytes:
            raise FileTooLargeError(len(data))
        if not data.startswith(PDF_MAGIC_BYTES):
            raise InvalidFileContentError("file content does not match declared PDF type")

        # Server-generated key, never derived from the client-supplied
        # filename — see app/storage/filesystem.py's path-traversal note.
        # The original filename is preserved separately for display.
        storage_key = f"{organisation_id}/{uuid.uuid4()}.pdf"
        await self._storage.put_object(storage_key, data, content_type=content_type)

        return await self._documents.create(
            organisation_id=organisation_id,
            submission_id=submission_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            storage_key=storage_key,
        )

    async def get_document_content(
        self, *, organisation_id: uuid.UUID, document_id: uuid.UUID
    ) -> tuple[Document, bytes] | None:
        document = await self._documents.get(
            organisation_id=organisation_id, document_id=document_id
        )
        if document is None:
            return None
        content = await self._storage.get_object(document.storage_key)
        return document, content
