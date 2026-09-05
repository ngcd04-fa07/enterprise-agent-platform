from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_call_trace import AICallStatus, AICallTrace, AICallType


class AICallTraceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        call_type: AICallType,
        provider: str,
        model: str,
        status: AICallStatus,
        latency_ms: float,
        call_metadata: str,
        error_message: str | None = None,
    ) -> AICallTrace:
        trace = AICallTrace(
            call_type=call_type,
            provider=provider,
            model=model,
            status=status,
            latency_ms=latency_ms,
            call_metadata=call_metadata,
            error_message=error_message,
        )
        self._session.add(trace)
        await self._session.flush()
        return trace
