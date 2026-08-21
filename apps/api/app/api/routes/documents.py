from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_membership, require_csrf, require_role
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.embeddings.base import EmbeddingProvider
from app.embeddings.factory import get_embedding_provider
from app.models.membership import MembershipRole, OrganisationMembership
from app.repositories.document_page_repository import DocumentPageRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentRead
from app.schemas.document_page import DocumentPageRead
from app.services.document_service import (
    DocumentService,
    FileTooLargeError,
    InvalidFileContentError,
    UnsupportedContentTypeError,
)
from app.services.ingestion_service import IngestionService
from app.services.submission_service import SubmissionNotFoundError, SubmissionService
from app.storage.base import ObjectNotFoundError, ObjectStorage
from app.storage.factory import get_object_storage

router = APIRouter(tags=["documents"])

# Same RBAC split as submissions: admins/underwriters can upload, any role can read.
_can_write = require_role(MembershipRole.ADMIN, MembershipRole.UNDERWRITER)


@router.post(
    "/submissions/{submission_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def upload_document(
    submission_id: UUID,
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    embeddings: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    membership: Annotated[OrganisationMembership, Depends(_can_write)],
) -> DocumentRead:
    try:
        await SubmissionService(db).get_submission(
            organisation_id=membership.organisation_id, submission_id=submission_id
        )
    except SubmissionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found") from exc

    data = await file.read()
    try:
        document = await DocumentService(db, storage).upload_document(
            organisation_id=membership.organisation_id,
            submission_id=submission_id,
            filename=file.filename or "upload.pdf",
            content_type=file.content_type or "application/octet-stream",
            data=data,
            max_upload_size_bytes=settings.max_upload_size_bytes,
        )
    except UnsupportedContentTypeError as exc:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only application/pdf is supported"
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large") from exc
    except InvalidFileContentError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "File content does not match declared type"
        ) from exc

    # Synchronous for now — see IngestionService docstring for why. A
    # parsing failure surfaces as document.status == "failed" in the
    # response, not as a failed upload: the file is safely stored either way.
    document = await IngestionService(db, storage, embeddings).ingest_document(document)

    return DocumentRead.model_validate(document)


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    membership: Annotated[OrganisationMembership, Depends(get_current_membership)],
) -> DocumentRead:
    document = await DocumentRepository(db).get(
        organisation_id=membership.organisation_id, document_id=document_id
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return DocumentRead.model_validate(document)


@router.get("/documents/{document_id}/pages", response_model=list[DocumentPageRead])
async def list_document_pages(
    document_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    membership: Annotated[OrganisationMembership, Depends(get_current_membership)],
) -> list[DocumentPageRead]:
    document = await DocumentRepository(db).get(
        organisation_id=membership.organisation_id, document_id=document_id
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    pages = await DocumentPageRepository(db).list_for_document(
        organisation_id=membership.organisation_id, document_id=document_id
    )
    return [DocumentPageRead.model_validate(page) for page in pages]


@router.get("/documents/{document_id}/content")
async def get_document_content(
    document_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    membership: Annotated[OrganisationMembership, Depends(get_current_membership)],
) -> Response:
    try:
        result = await DocumentService(db, storage).get_document_content(
            organisation_id=membership.organisation_id, document_id=document_id
        )
    except ObjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document content not found") from exc

    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")

    document, content = result
    return Response(content=content, media_type=document.content_type)
