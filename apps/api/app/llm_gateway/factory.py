from functools import lru_cache

from app.core.config import get_settings
from app.llm_gateway.base import LLMGateway
from app.llm_gateway.ollama_gateway import OllamaGateway
from app.observability.tracing_llm_gateway import TracingLLMGateway


@lru_cache
def get_llm_gateway() -> LLMGateway:
    """FastAPI dependency / app-wide accessor. lru_cache mirrors
    get_embedding_provider — one client configuration per process.
    Wrapped in TracingLLMGateway so every call is traced (see
    app/observability) — transparent to every caller, which still just
    depends on the LLMGateway interface.
    """
    settings = get_settings()
    return TracingLLMGateway(
        OllamaGateway(base_url=settings.ollama_base_url, model=settings.ollama_model),
        provider="ollama",
        model=settings.ollama_model,
    )
