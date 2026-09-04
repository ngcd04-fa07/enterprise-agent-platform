import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)


class SearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    text: str
    score: float = Field(
        description=(
            "A Reciprocal Rank Fusion score combining semantic (vector) and "
            "lexical (full-text) search — see RetrievalService. Meaningful "
            "only for ranking within one query's results, not as a 0..1 "
            "relevance measure and not comparable across queries."
        )
    )


class SearchResponse(BaseModel):
    results: list[SearchResult]
    strategy: str
    latency_ms: float
