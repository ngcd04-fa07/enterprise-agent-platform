import asyncio

from fastembed import TextEmbedding

from app.embeddings.base import EmbeddingProvider

DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"


class FastEmbedProvider(EmbeddingProvider):
    """Local, offline embeddings via fastembed (ONNX runtime) — no API
    key, no per-call cost, no network dependency after the model weights
    are cached on first use (huggingface_hub, ~100MB). Chosen over
    sentence-transformers/torch for a much lighter dependency footprint
    for the same "local model" intent — see docs/architecture.md.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        self._model = TextEmbedding(model_name=model_name)
        self._dimension = TextEmbedding.get_embedding_size(model_name)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._passage_embed, texts)

    async def embed_query(self, text: str) -> list[float]:
        results = await asyncio.to_thread(self._query_embed, [text])
        return results[0]

    def _passage_embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.passage_embed(texts)]

    def _query_embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.query_embed(texts)]
