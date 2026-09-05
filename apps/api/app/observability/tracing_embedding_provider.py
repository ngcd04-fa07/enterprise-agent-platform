import json
import time

from app.embeddings.base import EmbeddingProvider
from app.models.ai_call_trace import AICallStatus, AICallType
from app.observability.tracer import record_ai_call


class TracingEmbeddingProvider(EmbeddingProvider):
    """Wraps a real EmbeddingProvider so every call is traced — see
    TracingLLMGateway for the equivalent on the LLM side and the shared
    rationale.
    """

    def __init__(self, inner: EmbeddingProvider, *, provider: str, model: str) -> None:
        self._inner = inner
        self._provider = provider
        self._model = model

    @property
    def dimension(self) -> int:
        return self._inner.dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        start = time.perf_counter()
        try:
            result = await self._inner.embed_documents(texts)
        except Exception as exc:
            await record_ai_call(
                call_type=AICallType.EMBED_DOCUMENTS,
                provider=self._provider,
                model=self._model,
                status=AICallStatus.FAILURE,
                latency_ms=(time.perf_counter() - start) * 1000,
                call_metadata=json.dumps({"text_count": len(texts)}),
                error_message=str(exc),
            )
            raise

        await record_ai_call(
            call_type=AICallType.EMBED_DOCUMENTS,
            provider=self._provider,
            model=self._model,
            status=AICallStatus.SUCCESS,
            latency_ms=(time.perf_counter() - start) * 1000,
            call_metadata=json.dumps({"text_count": len(texts)}),
        )
        return result

    async def embed_query(self, text: str) -> list[float]:
        start = time.perf_counter()
        try:
            result = await self._inner.embed_query(text)
        except Exception as exc:
            await record_ai_call(
                call_type=AICallType.EMBED_QUERY,
                provider=self._provider,
                model=self._model,
                status=AICallStatus.FAILURE,
                latency_ms=(time.perf_counter() - start) * 1000,
                call_metadata=json.dumps({"query_length": len(text)}),
                error_message=str(exc),
            )
            raise

        await record_ai_call(
            call_type=AICallType.EMBED_QUERY,
            provider=self._provider,
            model=self._model,
            status=AICallStatus.SUCCESS,
            latency_ms=(time.perf_counter() - start) * 1000,
            call_metadata=json.dumps({"query_length": len(text)}),
        )
        return result
