import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extraction import ExtractionRun, ExtractionStatus


class ExtractionRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_for_submission(
        self, *, organisation_id: uuid.UUID, submission_id: uuid.UUID
    ) -> ExtractionRun | None:
        result = await self._session.execute(
            select(ExtractionRun)
            .where(
                ExtractionRun.organisation_id == organisation_id,
                ExtractionRun.submission_id == submission_id,
            )
            .order_by(ExtractionRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        organisation_id: uuid.UUID,
        submission_id: uuid.UUID,
        provider: str,
        model: str,
        status: ExtractionStatus,
        error_message: str | None = None,
        fields_extracted_count: int = 0,
    ) -> ExtractionRun:
        run = ExtractionRun(
            organisation_id=organisation_id,
            submission_id=submission_id,
            provider=provider,
            model=model,
            status=status,
            error_message=error_message,
            fields_extracted_count=fields_extracted_count,
        )
        self._session.add(run)
        await self._session.flush()
        return run
