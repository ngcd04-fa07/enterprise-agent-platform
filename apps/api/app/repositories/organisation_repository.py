import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organisation import Organisation


class OrganisationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, name: str) -> Organisation:
        organisation = Organisation(name=name)
        self._session.add(organisation)
        await self._session.flush()
        return organisation

    async def get_by_id(self, organisation_id: uuid.UUID) -> Organisation | None:
        return await self._session.get(Organisation, organisation_id)
