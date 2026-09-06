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

    Stage 19: also records `route_reason` (why this tier was picked —
    see RoutingLLMGateway) and, on failure, `kind`/`attempts` from
    `LLMGenerationError` — so a failed call's trace shows whether it was
    a transient/content/permanent failure and how many attempts the
    underlying gateway actually made, not just that it eventually failed.
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
        route_reason: str | None = None,
    ) -> SchemaT:
        start = time.perf_counter()
        metadata: dict[str, str | int] = {"schema": schema.__name__, "complexity": complexity.value}
        if route_reason is not None:
            # Stage 19: why this particular tier was picked (see
            # RoutingLLMGateway), not just which one — reuses this
            # existing metadata field rather than a new trace concept.
            metadata["route_reason"] = route_reason

        try:
            result = await self._inner.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                complexity=complexity,
                route_reason=route_reason,
            )
        except LLMGenerationError as exc:
            await record_ai_call(
                call_type=AICallType.LLM_GENERATE,
                provider=self._provider,
                model=self._model,
                status=AICallStatus.FAILURE,
                latency_ms=(time.perf_counter() - start) * 1000,
                call_metadata=json.dumps(
                    {**metadata, "kind": exc.kind.value, "attempts": exc.attempts}
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
            call_metadata=json.dumps(metadata),
        )
        return result
