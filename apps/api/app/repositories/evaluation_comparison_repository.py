import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import ComparisonStatus, EvaluationComparison


class EvaluationComparisonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        baseline_run_id: uuid.UUID,
        candidate_run_id: uuid.UUID,
        thresholds: str,
        overall_status: ComparisonStatus,
        report: str,
    ) -> EvaluationComparison:
        comparison = EvaluationComparison(
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
            thresholds=thresholds,
            overall_status=overall_status,
            report=report,
        )
        self._session.add(comparison)
        await self._session.flush()
        return comparison

    async def delete(self, comparison_id: uuid.UUID) -> None:
        comparison = await self._session.get(EvaluationComparison, comparison_id)
        if comparison is not None:
            await self._session.delete(comparison)
            await self._session.flush()
