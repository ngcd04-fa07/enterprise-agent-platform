from functools import lru_cache

from app.core.config import Settings, get_settings
from app.llm_gateway.base import LLMGateway
from app.llm_gateway.circuit_breaker import CircuitBreaker
from app.llm_gateway.groq_gateway import GroqGateway
from app.llm_gateway.ollama_gateway import OllamaGateway
from app.llm_gateway.routing_llm_gateway import RoutingLLMGateway
from app.observability.tracing_llm_gateway import TracingLLMGateway


def _build_fast_and_capable(settings: Settings) -> tuple[TracingLLMGateway, TracingLLMGateway]:
    """The only place a provider swap touches (CLAUDE.md: "no hidden
    provider coupling") — everything downstream (RoutingLLMGateway,
    every caller) depends only on LLMGateway, never on which of these
    branches built it.
    """
    if settings.llm_provider == "groq":
        if settings.groq_api_key is None:
            # Unreachable via normal startup — Settings' own validator
            # (_validate_groq_provider_has_a_key) already enforces this.
            # A real check, not an assert (S101): asserts can be stripped
            # under -O, which would silently turn this into an
            # AttributeError on the next line instead of a clear error.
            raise RuntimeError("groq_api_key is required when llm_provider=groq")
        api_key = settings.groq_api_key.get_secret_value()
        fast = TracingLLMGateway(
            GroqGateway(api_key=api_key, model=settings.groq_model),
            provider="groq",
            model=settings.groq_model,
        )
        capable = TracingLLMGateway(
            GroqGateway(api_key=api_key, model=settings.groq_capable_model),
            provider="groq",
            model=settings.groq_capable_model,
        )
        return fast, capable

    fast = TracingLLMGateway(
        OllamaGateway(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
            max_attempts=settings.ollama_max_attempts,
        ),
        provider="ollama",
        model=settings.ollama_model,
    )
    capable = TracingLLMGateway(
        OllamaGateway(
            base_url=settings.ollama_base_url,
            model=settings.ollama_capable_model,
            timeout_seconds=settings.ollama_timeout_seconds,
            max_attempts=settings.ollama_max_attempts,
        ),
        provider="ollama",
        model=settings.ollama_capable_model,
    )
    return fast, capable


@lru_cache
def get_llm_gateway() -> LLMGateway:
    """FastAPI dependency / app-wide accessor. lru_cache mirrors
    get_embedding_provider — one client configuration per process (also
    why each tier's CircuitBreaker is safe to build fresh here: exactly
    one instance ever exists per process, matching the breaker's own
    in-memory, per-process design — see CircuitBreaker's docstring).

    Each underlying model is wrapped in its own TracingLLMGateway
    *before* being handed to the router, not after — so every trace row's
    `model` is the model that actually served that call, and the router
    itself adds no new tracing responsibility. See docs/architecture.md,
    model routing decision, for why two local models rather than a
    dynamic/hosted one (and Settings.llm_provider's docstring for the
    public-demo exception to that).
    """
    settings = get_settings()
    fast, capable = _build_fast_and_capable(settings)
    return RoutingLLMGateway(
        fast=fast,
        capable=capable,
        fast_breaker=CircuitBreaker(
            failure_threshold=settings.llm_breaker_failure_threshold,
            cooldown_seconds=settings.llm_breaker_cooldown_seconds,
        ),
        capable_breaker=CircuitBreaker(
            failure_threshold=settings.llm_breaker_failure_threshold,
            cooldown_seconds=settings.llm_breaker_cooldown_seconds,
        ),
    )
