from functools import lru_cache

from app.core.config import get_settings
from app.llm_gateway.base import LLMGateway
from app.llm_gateway.ollama_gateway import OllamaGateway


@lru_cache
def get_llm_gateway() -> LLMGateway:
    """FastAPI dependency / app-wide accessor. lru_cache mirrors
    get_embedding_provider — one client configuration per process.
    """
    settings = get_settings()
    return OllamaGateway(base_url=settings.ollama_base_url, model=settings.ollama_model)
