from functools import lru_cache

from app.embeddings.base import EmbeddingProvider
from app.embeddings.fastembed_provider import DEFAULT_MODEL_NAME, FastEmbedProvider
from app.observability.tracing_embedding_provider import TracingEmbeddingProvider


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """FastAPI dependency / app-wide accessor. lru_cache ensures the
    (relatively expensive to load) model is initialized once per process,
    not once per request. Wrapped in TracingEmbeddingProvider so every
    call is traced (see app/observability) — transparent to every caller,
    which still just depends on the EmbeddingProvider interface.
    """
    return TracingEmbeddingProvider(
        FastEmbedProvider(), provider="fastembed", model=DEFAULT_MODEL_NAME
    )
