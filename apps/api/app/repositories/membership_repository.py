import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import MembershipRole, OrganisationMembership


class OrganisationMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, organisation_id: uuid.UUID, user_id: uuid.UUID, role: MembershipRole
    ) -> OrganisationMembership:
        membership = OrganisationMembership(
            organisation_id=organisation_id, user_id=user_id, role=role
        )
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def get(
        self, *, organisation_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrganisationMembership | None:
        result = await self._session.execute(
            select(OrganisationMembership).where(
                OrganisationMembership.organisation_id == organisation_id,
                OrganisationMembership.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[OrganisationMembership]:
        result = await self._session.execute(
            select(OrganisationMembership).where(OrganisationMembership.user_id == user_id)
        )
        return list(result.scalars().all())
