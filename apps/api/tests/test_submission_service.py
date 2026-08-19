import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organisation import Organisation
from app.models.submission import SubmissionStatus
from app.models.user import User
from app.repositories.organisation_repository import OrganisationRepository
from app.repositories.user_repository import UserRepository
from app.services.submission_service import SubmissionNotFoundError, SubmissionService


async def _make_org_and_user(session: AsyncSession) -> tuple[Organisation, User]:
    organisation = await OrganisationRepository(session).create(name="Acme Insurance")
    user = await UserRepository(session).create(email="uw@example.com", full_name="Underwriter")
    return organisation, user


async def test_create_and_get_submission(db_session: AsyncSession) -> None:
    organisation, user = await _make_org_and_user(db_session)
    service = SubmissionService(db_session)

    created = await service.create_submission(
        organisation_id=organisation.id, created_by_user_id=user.id, title="Q3 Renewal"
    )

    fetched = await service.get_submission(
        organisation_id=organisation.id, submission_id=created.id
    )
    assert fetched.id == created.id
    assert fetched.status == SubmissionStatus.DRAFT


async def test_list_submissions_scoped_to_organisation(db_session: AsyncSession) -> None:
    organisation, user = await _make_org_and_user(db_session)
    service = SubmissionService(db_session)
    await service.create_submission(
        organisation_id=organisation.id, created_by_user_id=user.id, title="A"
    )
    await service.create_submission(
        organisation_id=organisation.id, created_by_user_id=user.id, title="B"
    )

    submissions = await service.list_submissions(organisation_id=organisation.id)

    assert {s.title for s in submissions} == {"A", "B"}


async def test_update_submission_title_and_status(db_session: AsyncSession) -> None:
    organisation, user = await _make_org_and_user(db_session)
    service = SubmissionService(db_session)
    submission = await service.create_submission(
        organisation_id=organisation.id, created_by_user_id=user.id, title="Original"
    )

    updated = await service.update_submission(
        organisation_id=organisation.id,
        submission_id=submission.id,
        title="Updated",
        status=SubmissionStatus.IN_REVIEW,
    )

    assert updated.title == "Updated"
    assert updated.status == SubmissionStatus.IN_REVIEW


async def test_get_submission_raises_when_missing(db_session: AsyncSession) -> None:
    organisation, _user = await _make_org_and_user(db_session)
    service = SubmissionService(db_session)

    with pytest.raises(SubmissionNotFoundError):
        await service.get_submission(organisation_id=organisation.id, submission_id=uuid.uuid4())
