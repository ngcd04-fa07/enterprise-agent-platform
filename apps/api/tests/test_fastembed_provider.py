"""Tests the real embedding model, not a fake — unlike the HTTP-level
tests (which use FakeEmbeddingProvider for speed/determinism, see
fake_embeddings.py), these confirm FastEmbedProvider actually produces
sensible embeddings. Skips cleanly if the model can't be loaded (e.g. no
network to fetch weights on first use), matching the project's DB-skip
pattern rather than failing the suite.
"""

from collections.abc import Iterator

import pytest

from app.embeddings.fastembed_provider import FastEmbedProvider


@pytest.fixture(scope="module")
def provider() -> Iterator[FastEmbedProvider]:
    try:
        yield FastEmbedProvider()
    except Exception as exc:
        pytest.skip(f"could not load embedding model: {exc}")


async def test_embed_query_and_documents_share_dimension(provider: FastEmbedProvider) -> None:
    query_vector = await provider.embed_query("revenue growth")
    [doc_vector] = await provider.embed_documents(["Revenue grew 20% year over year."])

    assert len(query_vector) == provider.dimension
    assert len(doc_vector) == provider.dimension


async def test_semantically_related_text_scores_higher_than_unrelated(
    provider: FastEmbedProvider,
) -> None:
    query_vector = await provider.embed_query("quarterly revenue growth")
    relevant, irrelevant = await provider.embed_documents(
        ["The company's revenue increased 20% this quarter.", "The cat sat on the mat."]
    )

    def cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        return dot / (norm_a * norm_b)

    relevant_score = cosine_similarity(query_vector, relevant)
    irrelevant_score = cosine_similarity(query_vector, irrelevant)

    assert relevant_score > irrelevant_score
