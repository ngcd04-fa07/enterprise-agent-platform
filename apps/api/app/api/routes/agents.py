from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_membership, require_csrf, require_role
from app.db.session import get_db_session
from app.llm_gateway.base import LLMGateway
from app.llm_gateway.factory import get_llm_gateway
from app.models.agent import AgentRun
from app.models.membership import MembershipRole, OrganisationMembership
from app.repositories.agent_run_repository import (
    AgentRunAlreadyApprovedError,
    AgentRunNotFoundError,
    AgentRunRepository,
)
from app.repositories.agent_tool_call_repository import AgentToolCallRepository
from app.schemas.agent import AgentRunRead, AgentToolCallRead
from app.security.demo_guard import enforce_demo_llm_rate_limit
from app.services.agent_service import AgentService
from app.services.submission_service import SubmissionNotFoundError, SubmissionService

router = APIRouter(tags=["agents"])

# Triggering a triage run follows the same write-role split as the rest of
# the API; approving one is a more senior sign-off action, restricted to
# admins.
_can_write = require_role(MembershipRole.ADMIN, MembershipRole.UNDERWRITER)
_can_approve = require_role(MembershipRole.ADMIN)


async def _build_run_read(
    db: AsyncSession, *, organisation_id: UUID, run: AgentRun
) -> AgentRunRead:
    tool_calls = await AgentToolCallRepository(db).list_for_run(
        organisation_id=organisation_id, agent_run_id=run.id
    )
    return AgentRunRead(
        id=run.id,
        submission_id=run.submission_id,
        status=run.status.value,
        recommendation=run.recommendation.value if run.recommendation else None,
        summary=run.summary,
        error_message=run.error_message,
        requires_human_approval=run.requires_human_approval,
        approved_by_user_id=run.approved_by_user_id,
        approved_at=run.approved_at,
        created_at=run.created_at,
        tool_calls=[
            AgentToolCallRead(
                sequence_index=call.sequence_index,
                tool_name=call.tool_name,
                input_summary=call.input_summary,
                output_summary=call.output_summary,
            )
            for call in tool_calls
        ],
    )


@router.post(
    "/submissions/{submission_id}/agent-runs",
    response_model=AgentRunRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf), Depends(enforce_demo_llm_rate_limit)],
)
async def create_agent_run(
    submission_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    llm: Annotated[LLMGateway, Depends(get_llm_gateway)],
    membership: Annotated[OrganisationMembership, Depends(_can_write)],
) -> AgentRunRead:
    try:
        await SubmissionService(db).get_submission(
            organisation_id=membership.organisation_id, submission_id=submission_id
        )
    except SubmissionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found") from exc

    run = await AgentService(db, llm).run_triage(
        organisation_id=membership.organisation_id,
        submission_id=submission_id,
        created_by_user_id=membership.user_id,
    )
    return await _build_run_read(db, organisation_id=membership.organisation_id, run=run)


@router.get("/submissions/{submission_id}/agent-runs", response_model=list[AgentRunRead])
async def list_agent_runs(
    submission_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    membership: Annotated[OrganisationMembership, Depends(get_current_membership)],
) -> list[AgentRunRead]:
    try:
        await SubmissionService(db).get_submission(
            organisation_id=membership.organisation_id, submission_id=submission_id
        )
    except SubmissionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found") from exc

    runs = await AgentRunRepository(db).list_for_submission(
        organisation_id=membership.organisation_id, submission_id=submission_id
    )
    return [
        await _build_run_read(db, organisation_id=membership.organisation_id, run=run)
        for run in runs
    ]


@router.get("/agent-runs/{agent_run_id}", response_model=AgentRunRead)
async def get_agent_run(
    agent_run_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    membership: Annotated[OrganisationMembership, Depends(get_current_membership)],
) -> AgentRunRead:
    try:
        run = await AgentRunRepository(db).get(
            organisation_id=membership.organisation_id, agent_run_id=agent_run_id
        )
    except AgentRunNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent run not found") from exc
    return await _build_run_read(db, organisation_id=membership.organisation_id, run=run)


@router.post(
    "/agent-runs/{agent_run_id}/approve",
    response_model=AgentRunRead,
    dependencies=[Depends(require_csrf)],
)
async def approve_agent_run(
    agent_run_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    membership: Annotated[OrganisationMembership, Depends(_can_approve)],
) -> AgentRunRead:
    try:
        run = await AgentRunRepository(db).approve(
            organisation_id=membership.organisation_id,
            agent_run_id=agent_run_id,
            approved_by_user_id=membership.user_id,
        )
    except AgentRunNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent run not found") from exc
    except AgentRunAlreadyApprovedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This agent run has already been approved"
        ) from exc
    return await _build_run_read(db, organisation_id=membership.organisation_id, run=run)
