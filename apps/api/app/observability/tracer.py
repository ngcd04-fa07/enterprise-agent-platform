import logging

from app.db.session import get_sessionmaker
from app.models.ai_call_trace import AICallStatus, AICallType
from app.repositories.ai_call_trace_repository import AICallTraceRepository

logger = logging.getLogger(__name__)


async def record_ai_call(
    *,
    call_type: AICallType,
    provider: str,
    model: str,
    status: AICallStatus,
    latency_ms: float,
    call_metadata: str,
    error_message: str | None = None,
) -> None:
    """Writes one AI-call trace in its own short-lived session, committed
    independently of whatever business-request transaction is in flight.

    Two reasons this can't just reuse the caller's session: (1) the
    wrapped providers (TracingLLMGateway, TracingEmbeddingProvider) are
    constructed once as process-wide singletons (see
    app/llm_gateway/factory.py, app/embeddings/factory.py) with no
    request-scoped session available at call time; (2) even where one is
    available (RetrievalService), a trace should survive regardless of
    whether the surrounding business transaction later commits or rolls
    back — the fact that a call was attempted, and what happened, is
    exactly the kind of information you most want preserved when
    something else in the request goes wrong.

    Never raises: a broken tracer must never break the AI call it's
    describing. Matches the boundary-call pattern already used for
    ping_database (app/db/session.py) — best-effort, logged on failure,
    not surfaced to the caller.
    """
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await AICallTraceRepository(session).create(
                call_type=call_type,
                provider=provider,
                model=model,
                status=status,
                latency_ms=latency_ms,
                call_metadata=call_metadata,
                error_message=error_message,
            )
            await session.commit()
    except Exception:
        logger.warning("failed to record AI call trace", exc_info=True)
