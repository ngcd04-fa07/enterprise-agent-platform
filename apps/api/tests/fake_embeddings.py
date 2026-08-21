import hashlib

from app.embeddings.base import EmbeddingProvider
from app.models.document_chunk import EMBEDDING_DIMENSION


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic, hash-based fake embeddings — same dimension as the
    real provider (so they're valid against the real pgvector column) but
    not semantically meaningful. Lets tests verify the ingestion/retrieval
    pipeline's wiring (chunks get an embedding, search returns results
    ordered by distance, identical text yields identical vectors) without
    downloading and running a real model on every test. Real embedding
    quality is covered separately in test_fastembed_provider.py.
    """

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIMENSION

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._fake_vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._fake_vector(text)

    @staticmethod
    def _fake_vector(text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255.0 for i in range(EMBEDDING_DIMENSION)]
