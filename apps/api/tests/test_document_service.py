import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.document_service import DocumentService
from app.storage.base import ObjectStorage
from tests.pdf_fixtures import build_minimal_pdf


async def test_failed_document_row_creation_deletes_the_written_file(
    db_session: AsyncSession, object_storage: ObjectStorage
) -> None:
    """If the DB row can't be created after the file is already written to
    storage (here: a submission_id with no matching row, violating the FK),
    the file must not be left orphaned on disk with nothing to account for
    it. See DocumentService.upload_document's compensating delete_object
    call.
    """
    service = DocumentService(db_session, object_storage)
    pdf = build_minimal_pdf(["Some page text."])
    nonexistent_submission_id = uuid.uuid4()

    with pytest.raises(IntegrityError):
        await service.upload_document(
            organisation_id=uuid.uuid4(),
            submission_id=nonexistent_submission_id,
            filename="doc.pdf",
            content_type="application/pdf",
            data=pdf,
            max_upload_size_bytes=10_000_000,
        )

    # The row creation failed, so we never got a storage_key back — but the
    # service should have cleaned up whatever key it generated internally.
    # Recover it the only way a test can: it's the sole object ever written
    # to this test's throwaway storage root.
    written_keys = [p.name for p in object_storage._root.rglob("*.pdf")]  # type: ignore[attr-defined]
    assert written_keys == []
