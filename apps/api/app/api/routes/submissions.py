from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_membership, require_csrf, require_role
from app.db.session import get_db_session
from app.models.membership import MembershipRole, OrganisationMembership
from app.schemas.submission import SubmissionCreate, SubmissionRead, SubmissionUpdate
from app.services.submission_service import SubmissionNotFoundError, SubmissionService

router = APIRouter(prefix="/submissions", tags=["submissions"])

# Per docs/architecture.md RBAC: underwriters and admins can create/update
# submissions; any role (including viewer) can read them.
_can_write = require_role(MembershipRole.ADMIN, MembershipRole.UNDERWRITER)


@router.post(
    "",
    response_model=SubmissionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_submission(
    payload: SubmissionCreate,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    membership: Annotated[OrganisationMembership, Depends(_can_write)],
) -> SubmissionRead:
    submission = await SubmissionService(db).create_submission(
        organisation_id=membership.organisation_id,
        created_by_user_id=membership.user_id,
        title=payload.title,
    )
    return SubmissionRead.model_validate(submission)


@router.get("", response_model=list[SubmissionRead])
async def list_submissions(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    membership: Annotated[OrganisationMembership, Depends(get_current_membership)],
) -> list[SubmissionRead]:
    submissions = await SubmissionService(db).list_submissions(
        organisation_id=membership.organisation_id
    )
    return [SubmissionRead.model_validate(s) for s in submissions]


@router.get("/{submission_id}", response_model=SubmissionRead)
async def get_submission(
    submission_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    membership: Annotated[OrganisationMembership, Depends(get_current_membership)],
) -> SubmissionRead:
    try:
        submission = await SubmissionService(db).get_submission(
            organisation_id=membership.organisation_id, submission_id=submission_id
        )
    except SubmissionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found") from exc
    return SubmissionRead.model_validate(submission)


@router.patch(
    "/{submission_id}",
    response_model=SubmissionRead,
    dependencies=[Depends(require_csrf)],
)
async def update_submission(
    submission_id: UUID,
    payload: SubmissionUpdate,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    membership: Annotated[OrganisationMembership, Depends(_can_write)],
) -> SubmissionRead:
    try:
        submission = await SubmissionService(db).update_submission(
            organisation_id=membership.organisation_id,
            submission_id=submission_id,
            title=payload.title,
            status=payload.status,
        )
    except SubmissionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found") from exc
    return SubmissionRead.model_validate(submission)
