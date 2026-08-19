import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.submission import Submission


class SubmissionRepository:
    """Every method requires organisation_id and filters on it — the only
    place a submission is ever fetched by primary key alone would let a
    cross-tenant ID guess succeed. See docs/architecture.md, tenant
    isolation decision.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, organisation_id: uuid.UUID, created_by_user_id: uuid.UUID, title: str
    ) -> Submission:
        submission = Submission(
            organisation_id=organisation_id, created_by_user_id=created_by_user_id, title=title
        )
        self._session.add(submission)
        await self._session.flush()
        return submission

    async def get(
        self, *, organisation_id: uuid.UUID, submission_id: uuid.UUID
    ) -> Submission | None:
        result = await self._session.execute(
            select(Submission).where(
                Submission.id == submission_id, Submission.organisation_id == organisation_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_organisation(self, organisation_id: uuid.UUID) -> list[Submission]:
        result = await self._session.execute(
            select(Submission)
            .where(Submission.organisation_id == organisation_id)
            .order_by(Submission.created_at.desc())
        )
        return list(result.scalars().all())
