"""Cross-tenant denial tests at the service layer.

These are the service-layer precursors to the eventual HTTP-level
test_user_cannot_read_other_org_submission /
test_user_cannot_modify_other_org_submission (added in Stage 3, once
session-derived organisation context exists to test over HTTP). Proving the
isolation boundary here means Stage 3's auth work builds on top of a layer
that already can't leak across tenants, rather than being the only thing
standing between a bug and a data leak.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.organisation_repository import OrganisationRepository
from app.repositories.user_repository import UserRepository
from app.services.submission_service import SubmissionNotFoundError, SubmissionService


async def test_submission_service_cannot_read_other_org_submission(
    db_session: AsyncSession,
) -> None:
    org_a = await OrganisationRepository(db_session).create(name="Org A")
    org_b = await OrganisationRepository(db_session).create(name="Org B")
    user_a = await UserRepository(db_session).create(email="a@example.com", full_name="A")

    service = SubmissionService(db_session)
    submission = await service.create_submission(
        organisation_id=org_a.id, created_by_user_id=user_a.id, title="Org A submission"
    )

    with pytest.raises(SubmissionNotFoundError):
        await service.get_submission(organisation_id=org_b.id, submission_id=submission.id)


async def test_submission_service_cannot_modify_other_org_submission(
    db_session: AsyncSession,
) -> None:
    org_a = await OrganisationRepository(db_session).create(name="Org A")
    org_b = await OrganisationRepository(db_session).create(name="Org B")
    user_a = await UserRepository(db_session).create(email="a2@example.com", full_name="A2")

    service = SubmissionService(db_session)
    submission = await service.create_submission(
        organisation_id=org_a.id, created_by_user_id=user_a.id, title="Org A submission"
    )

    with pytest.raises(SubmissionNotFoundError):
        await service.update_submission(
            organisation_id=org_b.id, submission_id=submission.id, title="Hijacked"
        )
