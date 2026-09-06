import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import EvaluationRun


class EvaluationRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, evaluator_name: str, label: str, run_config: str) -> EvaluationRun:
        run = EvaluationRun(evaluator_name=evaluator_name, label=label, run_config=run_config)
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_by_id(self, run_id: uuid.UUID) -> EvaluationRun | None:
        return await self._session.get(EvaluationRun, run_id)

    async def delete(self, run_id: uuid.UUID) -> None:
        """Case results cascade automatically (ON DELETE CASCADE). Any
        EvaluationComparison still referencing this run must be deleted
        by the caller first — the FK has no ondelete, deliberately (see
        EvaluationComparison's docstring), so this raises if one exists.
        """
        run = await self._session.get(EvaluationRun, run_id)
        if run is not None:
            await self._session.delete(run)
            await self._session.flush()

    async def list_by_label(self, *, evaluator_name: str, label: str) -> list[EvaluationRun]:
        """Most-recent-first — label isn't unique (the same label, e.g.
        "baseline", is expected to be re-recorded many times as the
        evaluated code changes), so a caller resolving a label to one run
        takes the first (most recent) result and should tell the user
        when more than one match existed. See evals/comparison.py.
        """
        result = await self._session.execute(
            select(EvaluationRun)
            .where(EvaluationRun.evaluator_name == evaluator_name, EvaluationRun.label == label)
            .order_by(EvaluationRun.created_at.desc())
        )
        return list(result.scalars().all())
