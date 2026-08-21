import pytest

from app.ingestion.chunking import chunk_text


def test_empty_text_produces_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_short_text_produces_single_chunk() -> None:
    text = "hello world"
    chunks = chunk_text(text, chunk_size=100, overlap=10)

    assert len(chunks) == 1
    chunk, start, end = chunks[0]
    assert chunk == text
    assert (start, end) == (0, len(text))


def test_chunks_cover_text_with_overlap() -> None:
    text = "a" * 25
    chunks = chunk_text(text, chunk_size=10, overlap=2)

    # step = 8: starts 0, 8, 16 — the third chunk already reaches end=25=len(text),
    # so the loop stops there; the whole text is covered with no gaps.
    assert [start for _, start, _ in chunks] == [0, 8, 16]
    assert [end for _, _, end in chunks] == [10, 18, 25]
    # every chunk is a real substring of the original text, at the claimed offsets
    for chunk, start, end in chunks:
        assert text[start:end] == chunk
    # no gap in coverage: each chunk starts at or before the previous one's end
    for (_, _, prev_end), (_, next_start, _) in zip(chunks, chunks[1:], strict=False):
        assert next_start <= prev_end


def test_rejects_invalid_chunk_size_or_overlap() -> None:
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        chunk_text("text", chunk_size=0, overlap=0)

    with pytest.raises(ValueError, match="overlap must be"):
        chunk_text("text", chunk_size=10, overlap=10)

    with pytest.raises(ValueError, match="overlap must be"):
        chunk_text("text", chunk_size=10, overlap=-1)
