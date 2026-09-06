from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_membership, require_csrf, require_role
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.llm_gateway.base import LLMGateway
from app.llm_gateway.factory import get_llm_gateway
from app.models.membership import MembershipRole, OrganisationMembership
from app.repositories.extracted_field_repository import ExtractedFieldRepository
from app.repositories.extraction_run_repository import ExtractionRunRepository
from app.schemas.extraction import ExtractedFieldRead, ExtractionResponse
from app.security.demo_guard import enforce_demo_llm_rate_limit
from app.services.extraction_service import ExtractionService
from app.services.submission_service import SubmissionNotFoundError, SubmissionService

router = APIRouter(tags=["extraction"])

# Same RBAC split as document upload: admins/underwriters can trigger a
# (real, model-inference) extraction run; any role can read the results.
_can_write = require_role(MembershipRole.ADMIN, MembershipRole.UNDERWRITER)


async def _build_response(
    db: AsyncSession, *, organisation_id: UUID, submission_id: UUID, status_value: str
) -> ExtractionResponse:
    rows = await ExtractedFieldRepository(db).list_for_submission(
        organisation_id=organisation_id, submission_id=submission_id
    )
    fields = [
        ExtractedFieldRead(
            field_name=field.field_name,
            value=field.value,
            source_chunk_id=field.source_chunk_id,
            source_document_id=document_id,
            source_page_number=page_number,
        )
        for field, document_id, page_number in rows
    ]
    return ExtractionResponse(submission_id=submission_id, status=status_value, fields=fields)


@router.post(
    "/submissions/{submission_id}/extract",
    response_model=ExtractionResponse,
    dependencies=[Depends(require_csrf), Depends(enforce_demo_llm_rate_limit)],
)
async def extract_submission(
    submission_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    llm: Annotated[LLMGateway, Depends(get_llm_gateway)],
    membership: Annotated[OrganisationMembership, Depends(_can_write)],
) -> ExtractionResponse:
    try:
        await SubmissionService(db).get_submission(
            organisation_id=membership.organisation_id, submission_id=submission_id
        )
    except SubmissionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found") from exc

    run = await ExtractionService(db, llm, settings).extract_submission(
        organisation_id=membership.organisation_id, submission_id=submission_id
    )

    return await _build_response(
        db,
        organisation_id=membership.organisation_id,
        submission_id=submission_id,
        status_value=run.status.value,
    )


@router.get("/submissions/{submission_id}/extraction", response_model=ExtractionResponse)
async def get_extraction(
    submission_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    membership: Annotated[OrganisationMembership, Depends(get_current_membership)],
) -> ExtractionResponse:
    try:
        await SubmissionService(db).get_submission(
            organisation_id=membership.organisation_id, submission_id=submission_id
        )
    except SubmissionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found") from exc

    latest_run = await ExtractionRunRepository(db).get_latest_for_submission(
        organisation_id=membership.organisation_id, submission_id=submission_id
    )
    status_value = latest_run.status.value if latest_run is not None else "not_run"

    return await _build_response(
        db,
        organisation_id=membership.organisation_id,
        submission_id=submission_id,
        status_value=status_value,
    )
