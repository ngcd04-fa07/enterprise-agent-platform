from app.models.document_chunk import EMBEDDING_DIMENSION
from tests.fake_embeddings import FakeEmbeddingProvider


async def test_fake_embeddings_are_deterministic() -> None:
    provider = FakeEmbeddingProvider()

    first = await provider.embed_query("some text")
    second = await provider.embed_query("some text")

    assert first == second
    assert len(first) == EMBEDDING_DIMENSION


async def test_fake_embeddings_differ_for_different_text() -> None:
    provider = FakeEmbeddingProvider()

    [a, b] = await provider.embed_documents(["first chunk", "second chunk"])

    assert a != b
