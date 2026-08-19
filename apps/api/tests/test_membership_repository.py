import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import MembershipRole
from app.repositories.membership_repository import OrganisationMembershipRepository
from app.repositories.organisation_repository import OrganisationRepository
from app.repositories.user_repository import UserRepository


async def test_duplicate_membership_violates_unique_constraint(db_session: AsyncSession) -> None:
    organisation = await OrganisationRepository(db_session).create(name="Acme")
    user = await UserRepository(db_session).create(email="dup@example.com", full_name="Dup")
    memberships = OrganisationMembershipRepository(db_session)

    await memberships.create(
        organisation_id=organisation.id, user_id=user.id, role=MembershipRole.VIEWER
    )

    with pytest.raises(IntegrityError):
        await memberships.create(
            organisation_id=organisation.id, user_id=user.id, role=MembershipRole.ADMIN
        )
