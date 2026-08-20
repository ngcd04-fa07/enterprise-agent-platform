from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import MembershipRole
from app.repositories.membership_repository import OrganisationMembershipRepository
from app.repositories.user_repository import UserRepository
from app.services.organisation_service import OrganisationService


async def test_create_organisation_with_owner_creates_admin_membership(
    db_session: AsyncSession,
) -> None:
    user = await UserRepository(db_session).create(
        email="owner@example.com", full_name="Owner", password_hash="test-hash"
    )

    organisation = await OrganisationService(db_session).create_organisation_with_owner(
        name="Acme Insurance", owner_user_id=user.id
    )

    membership = await OrganisationMembershipRepository(db_session).get(
        organisation_id=organisation.id, user_id=user.id
    )
    assert membership is not None
    assert membership.role == MembershipRole.ADMIN
