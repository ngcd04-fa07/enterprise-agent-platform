import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun, AgentRunStatus, RecommendationType


class AgentRunNotFoundError(Exception):
    """Raised both when a run doesn't exist and when it exists in a
    different organisation than the caller's — same rationale as
    SubmissionNotFoundError: a cross-tenant ID guess must never be able to
    distinguish "wrong org" from "doesn't exist."
    """


class AgentRunAlreadyApprovedError(Exception):
    """Raised on a second approval attempt (Stage 20) — approval is an
    audit boundary (docs/architecture.md, agentic workflow decision): the
    original approver/timestamp must be permanent, not silently
    overwritable by a later call (accidental double-click, replay, or a
    different admin). Surfaced as 409 Conflict at the route layer.
    """


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        organisation_id: uuid.UUID,
        submission_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        status: AgentRunStatus,
        recommendation: RecommendationType | None = None,
        summary: str | None = None,
        error_message: str | None = None,
    ) -> AgentRun:
        run = AgentRun(
            organisation_id=organisation_id,
            submission_id=submission_id,
            created_by_user_id=created_by_user_id,
            status=status,
            recommendation=recommendation,
            summary=summary,
            error_message=error_message,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get(self, *, organisation_id: uuid.UUID, agent_run_id: uuid.UUID) -> AgentRun:
        result = await self._session.execute(
            select(AgentRun).where(
                AgentRun.organisation_id == organisation_id, AgentRun.id == agent_run_id
            )
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise AgentRunNotFoundError(agent_run_id)
        return run

    async def list_for_submission(
        self, *, organisation_id: uuid.UUID, submission_id: uuid.UUID
    ) -> list[AgentRun]:
        result = await self._session.execute(
            select(AgentRun)
            .where(
                AgentRun.organisation_id == organisation_id,
                AgentRun.submission_id == submission_id,
            )
            .order_by(AgentRun.created_at.desc())
        )
        return list(result.scalars().all())

    async def approve(
        self, *, organisation_id: uuid.UUID, agent_run_id: uuid.UUID, approved_by_user_id: uuid.UUID
    ) -> AgentRun:
        run = await self.get(organisation_id=organisation_id, agent_run_id=agent_run_id)
        if run.approved_at is not None:
            # Never overwrite — the first approval's attribution is
            # permanent. Checked before any mutation, so a rejected
            # replay leaves the row (and this session) completely
            # untouched, not just "unchanged in the end."
            raise AgentRunAlreadyApprovedError(agent_run_id)
        run.approved_by_user_id = approved_by_user_id
        run.approved_at = datetime.now(UTC)
        await self._session.flush()
        return run
