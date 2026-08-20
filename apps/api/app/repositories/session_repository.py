import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        csrf_token: str,
        active_organisation_id: uuid.UUID | None,
        expires_at: datetime,
    ) -> Session:
        session_row = Session(
            user_id=user_id,
            token_hash=token_hash,
            csrf_token=csrf_token,
            active_organisation_id=active_organisation_id,
            expires_at=expires_at,
        )
        self._session.add(session_row)
        await self._session.flush()
        return session_row

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        result = await self._session.execute(
            select(Session).where(Session.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, session_row: Session, *, revoked_at: datetime) -> None:
        session_row.revoked_at = revoked_at
        await self._session.flush()

    async def set_active_organisation(
        self, session_row: Session, *, organisation_id: uuid.UUID
    ) -> None:
        session_row.active_organisation_id = organisation_id
        await self._session.flush()
