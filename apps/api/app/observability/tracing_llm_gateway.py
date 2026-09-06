import json
import time

from app.llm_gateway.base import LLMGateway, LLMGenerationError, SchemaT, TaskComplexity
from app.models.ai_call_trace import AICallStatus, AICallType
from app.observability.tracer import record_ai_call


class TracingLLMGateway(LLMGateway):
    """Wraps a real LLMGateway so every call is traced — latency, status,
    and a small metadata summary — without any change to callers, which
    still just depend on the LLMGateway interface. See
    app/llm_gateway/factory.py for where this gets applied, and
    app/observability/tracer.py for why the trace write is independent of
    whatever request transaction is in flight.

    Deliberately wraps each underlying model individually (see
    get_llm_gateway) rather than wrapping RoutingLLMGateway from the
    outside — that way `model` in every trace row is the model that
    actually served the call, giving real visibility into how often each
    tier gets used and how often escalation happens, not just "routing
    happened."
    """

    def __init__(self, inner: LLMGateway, *, provider: str, model: str) -> None:
        self._inner = inner
        self._provider = provider
        self._model = model

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        complexity: TaskComplexity = TaskComplexity.SIMPLE,
    ) -> SchemaT:
        start = time.perf_counter()
        try:
            result = await self._inner.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                complexity=complexity,
            )
        except LLMGenerationError as exc:
            await record_ai_call(
                call_type=AICallType.LLM_GENERATE,
                provider=self._provider,
                model=self._model,
                status=AICallStatus.FAILURE,
                latency_ms=(time.perf_counter() - start) * 1000,
                call_metadata=json.dumps(
                    {"schema": schema.__name__, "complexity": complexity.value}
                ),
                error_message=str(exc),
            )
            raise

        await record_ai_call(
            call_type=AICallType.LLM_GENERATE,
            provider=self._provider,
            model=self._model,
            status=AICallStatus.SUCCESS,
            latency_ms=(time.perf_counter() - start) * 1000,
            call_metadata=json.dumps({"schema": schema.__name__, "complexity": complexity.value}),
        )
        return result
