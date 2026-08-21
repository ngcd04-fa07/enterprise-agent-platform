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
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]
    strategy: str
    latency_ms: float
