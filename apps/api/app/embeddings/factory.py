from functools import lru_cache

from app.embeddings.base import EmbeddingProvider
from app.embeddings.fastembed_provider import FastEmbedProvider


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """FastAPI dependency / app-wide accessor. lru_cache ensures the
    (relatively expensive to load) model is initialized once per process,
    not once per request.
    """
    return FastEmbedProvider()
