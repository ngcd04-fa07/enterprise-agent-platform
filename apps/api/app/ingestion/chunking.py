# ~4 characters/token is a commonly-cited rough heuristic for English text.
# These approximate the brief's example baseline (500 tokens, 100 overlap)
# without committing to a specific tokenizer before an embedding provider
# is chosen (Stage 6) — see docs/architecture.md, chunking decision.
DEFAULT_CHUNK_SIZE_CHARS = 2000
DEFAULT_CHUNK_OVERLAP_CHARS = 400


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE_CHARS,
    overlap: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> list[tuple[str, int, int]]:
    """Naive fixed-size character chunking with overlap — a deliberately
    simple baseline (not sentence/paragraph aware; see
    docs/architecture.md). Returns (chunk_text, start_char, end_char)
    triples, offsets into the original `text`, so callers can preserve
    provenance back to the source page.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and < chunk_size")

    if not text.strip():
        return []

    chunks: list[tuple[str, int, int]] = []
    start = 0
    length = len(text)
    step = chunk_size - overlap

    while start < length:
        end = min(start + chunk_size, length)
        chunk = text[start:end]
        if chunk.strip():
            chunks.append((chunk, start, end))
        if end == length:
            break
        start += step

    return chunks
