import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import MembershipRole
from app.models.organisation import Organisation
from app.repositories.membership_repository import OrganisationMembershipRepository
from app.repositories.organisation_repository import OrganisationRepository


class OrganisationService:
    """Owns operations that span more than one repository in a single
    transaction. An organisation with no admin member is not a valid state,
    so creation and the first membership are one operation, not two calls a
    caller could interleave incorrectly.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._organisations = OrganisationRepository(session)
        self._memberships = OrganisationMembershipRepository(session)

    async def create_organisation_with_owner(
        self, *, name: str, owner_user_id: uuid.UUID
    ) -> Organisation:
        organisation = await self._organisations.create(name=name)
        await self._memberships.create(
            organisation_id=organisation.id, user_id=owner_user_id, role=MembershipRole.ADMIN
        )
        return organisation
