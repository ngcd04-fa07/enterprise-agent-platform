from functools import lru_cache

from app.core.config import get_settings
from app.llm_gateway.base import LLMGateway
from app.llm_gateway.ollama_gateway import OllamaGateway
from app.llm_gateway.routing_llm_gateway import RoutingLLMGateway
from app.observability.tracing_llm_gateway import TracingLLMGateway


@lru_cache
def get_llm_gateway() -> LLMGateway:
    """FastAPI dependency / app-wide accessor. lru_cache mirrors
    get_embedding_provider — one client configuration per process.

    Each underlying model is wrapped in its own TracingLLMGateway
    *before* being handed to the router, not after — so every trace row's
    `model` is the model that actually served that call, and the router
    itself adds no new tracing responsibility. See docs/architecture.md,
    model routing decision, for why two local models rather than a
    dynamic/hosted one.
    """
    settings = get_settings()
    fast = TracingLLMGateway(
        OllamaGateway(base_url=settings.ollama_base_url, model=settings.ollama_model),
        provider="ollama",
        model=settings.ollama_model,
    )
    capable = TracingLLMGateway(
        OllamaGateway(base_url=settings.ollama_base_url, model=settings.ollama_capable_model),
        provider="ollama",
        model=settings.ollama_capable_model,
    )
    return RoutingLLMGateway(fast=fast, capable=capable)
