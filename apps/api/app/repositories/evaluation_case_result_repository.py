import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import EvaluationCaseResult


class EvaluationCaseResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, evaluation_run_id: uuid.UUID, case_key: str, tags: str, metrics: str
    ) -> EvaluationCaseResult:
        row = EvaluationCaseResult(
            evaluation_run_id=evaluation_run_id, case_key=case_key, tags=tags, metrics=metrics
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_run(self, evaluation_run_id: uuid.UUID) -> list[EvaluationCaseResult]:
        result = await self._session.execute(
            select(EvaluationCaseResult).where(
                EvaluationCaseResult.evaluation_run_id == evaluation_run_id
            )
        )
        return list(result.scalars().all())
