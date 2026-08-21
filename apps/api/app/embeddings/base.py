from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Provider-neutral interface for turning text into vectors. Business
    logic depends only on this — never on a specific embedding library or
    API (see CLAUDE.md: "no hidden provider coupling"). The only
    implementation right now is a local ONNX model via fastembed; a
    hosted API provider (OpenAI, Voyage) could be swapped in behind the
    same interface later without touching callers.

    embed_documents and embed_query are separate methods, not one — some
    models (including the default one here) recommend different handling
    for a search query vs. the passages it's matched against (e.g. an
    instruction prefix on the query only), so the interface preserves that
    distinction rather than assuming query and document embeddings are
    computed identically.
    """

    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...
