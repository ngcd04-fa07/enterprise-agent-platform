import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentToolCall


class AgentToolCallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        agent_run_id: uuid.UUID,
        organisation_id: uuid.UUID,
        sequence_index: int,
        tool_name: str,
        input_summary: str,
        output_summary: str,
    ) -> AgentToolCall:
        call = AgentToolCall(
            agent_run_id=agent_run_id,
            organisation_id=organisation_id,
            sequence_index=sequence_index,
            tool_name=tool_name,
            input_summary=input_summary,
            output_summary=output_summary,
        )
        self._session.add(call)
        await self._session.flush()
        return call

    async def list_for_run(
        self, *, organisation_id: uuid.UUID, agent_run_id: uuid.UUID
    ) -> list[AgentToolCall]:
        result = await self._session.execute(
            select(AgentToolCall)
            .where(
                AgentToolCall.organisation_id == organisation_id,
                AgentToolCall.agent_run_id == agent_run_id,
            )
            .order_by(AgentToolCall.sequence_index)
        )
        return list(result.scalars().all())
