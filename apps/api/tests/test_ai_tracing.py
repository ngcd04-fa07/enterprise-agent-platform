"""Verifies the tracing wrappers actually persist a trace row for every
call — success and failure — using the fakes (not real providers) so this
runs without Ollama/fastembed. The trace write goes through its own
session (see app/observability/tracer.py), not the test's db_session, so
these assertions query for the row afterward rather than inspecting
db_session directly — proving the trace is really committed and visible
independently, which is the whole point of that design.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm_gateway.base import LLMGenerationError, TaskComplexity
from app.models.ai_call_trace import AICallStatus, AICallTrace, AICallType
from app.observability.tracing_embedding_provider import TracingEmbeddingProvider
from app.observability.tracing_llm_gateway import TracingLLMGateway
from app.schemas.extraction import ChunkExtraction
from app.services.retrieval_service import RetrievalService
from tests.fake_embeddings import FakeEmbeddingProvider
from tests.fake_llm_gateway import FakeLLMGateway


async def _latest_trace(db_session: AsyncSession, call_type: AICallType) -> AICallTrace:
    result = await db_session.execute(
        select(AICallTrace)
        .where(AICallTrace.call_type == call_type)
        .order_by(AICallTrace.created_at.desc())
        .limit(1)
    )
    trace = result.scalar_one_or_none()
    assert trace is not None, f"no trace of type {call_type} was recorded"
    return trace


async def test_tracing_llm_gateway_records_success(db_session: AsyncSession) -> None:
    fake = FakeLLMGateway()
    fake.default_response = {"summary": "ok"}
    gateway = TracingLLMGateway(fake, provider="fake-provider", model="fake-model-v1")

    await gateway.generate_structured(
        system_prompt="sys", user_prompt="unique-prompt-success-1", schema=ChunkExtraction
    )

    trace = await _latest_trace(db_session, AICallType.LLM_GENERATE)
    assert trace.status == AICallStatus.SUCCESS
    assert trace.provider == "fake-provider"
    assert trace.model == "fake-model-v1"
    assert trace.latency_ms >= 0
    assert trace.error_message is None
    assert '"complexity": "simple"' in trace.call_metadata


async def test_tracing_llm_gateway_records_requested_complexity(
    db_session: AsyncSession,
) -> None:
    fake = FakeLLMGateway()
    fake.default_response = {"summary": "ok"}
    gateway = TracingLLMGateway(fake, provider="fake-provider", model="fake-model-v1")

    await gateway.generate_structured(
        system_prompt="sys",
        user_prompt="unique-prompt-complex-1",
        schema=ChunkExtraction,
        complexity=TaskComplexity.COMPLEX,
    )

    trace = await _latest_trace(db_session, AICallType.LLM_GENERATE)
    assert '"complexity": "complex"' in trace.call_metadata


async def test_tracing_llm_gateway_records_failure(db_session: AsyncSession) -> None:
    fake = FakeLLMGateway()
    fake.should_fail = True
    gateway = TracingLLMGateway(fake, provider="fake-provider", model="fake-model-v1")

    with pytest.raises(LLMGenerationError):
        await gateway.generate_structured(
            system_prompt="sys", user_prompt="unique-prompt-failure-1", schema=ChunkExtraction
        )

    trace = await _latest_trace(db_session, AICallType.LLM_GENERATE)
    assert trace.status == AICallStatus.FAILURE
    assert trace.error_message is not None
    # Stage 19: a failure trace records the failure's kind and how many
    # attempts the underlying gateway actually made, not just that it
    # eventually gave up.
    assert '"kind": "transient"' in trace.call_metadata
    assert '"attempts": 1' in trace.call_metadata


async def test_tracing_llm_gateway_records_route_reason_when_present(
    db_session: AsyncSession,
) -> None:
    fake = FakeLLMGateway()
    fake.default_response = {"summary": "ok"}
    gateway = TracingLLMGateway(fake, provider="fake-provider", model="fake-model-v1")

    await gateway.generate_structured(
        system_prompt="sys",
        user_prompt="unique-prompt-route-reason-1",
        schema=ChunkExtraction,
        route_reason="complexity_route_fast",
    )

    trace = await _latest_trace(db_session, AICallType.LLM_GENERATE)
    assert '"route_reason": "complexity_route_fast"' in trace.call_metadata


async def test_tracing_llm_gateway_omits_route_reason_when_not_given(
    db_session: AsyncSession,
) -> None:
    fake = FakeLLMGateway()
    fake.default_response = {"summary": "ok"}
    gateway = TracingLLMGateway(fake, provider="fake-provider", model="fake-model-v1")

    await gateway.generate_structured(
        system_prompt="sys", user_prompt="unique-prompt-no-route-reason-1", schema=ChunkExtraction
    )

    trace = await _latest_trace(db_session, AICallType.LLM_GENERATE)
    assert "route_reason" not in trace.call_metadata


async def test_tracing_embedding_provider_records_query_and_documents(
    db_session: AsyncSession,
) -> None:
    provider = TracingEmbeddingProvider(
        FakeEmbeddingProvider(), provider="fake-embed", model="fake-embed-model"
    )

    await provider.embed_query("some query text")
    query_trace = await _latest_trace(db_session, AICallType.EMBED_QUERY)
    assert query_trace.status == AICallStatus.SUCCESS
    assert query_trace.provider == "fake-embed"

    await provider.embed_documents(["doc one", "doc two", "doc three"])
    documents_trace = await _latest_trace(db_session, AICallType.EMBED_DOCUMENTS)
    assert documents_trace.status == AICallStatus.SUCCESS
    assert '"text_count": 3' in documents_trace.call_metadata


async def test_retrieval_service_records_a_search_trace(db_session: AsyncSession) -> None:
    # No chunks/organisation need to exist for this — search_similar and
    # search_lexical are plain SELECTs with no FK check, so a random org id
    # with zero matching rows exercises the full method (and its tracing)
    # without needing a full submission/document/chunk fixture.
    service = RetrievalService(db_session, FakeEmbeddingProvider())

    results = await service.search(organisation_id=uuid.uuid4(), query="anything at all")

    assert results == []
    trace = await _latest_trace(db_session, AICallType.RETRIEVAL_SEARCH)
    assert trace.status == AICallStatus.SUCCESS
    assert trace.provider == "hybrid"
    assert '"result_count": 0' in trace.call_metadata
