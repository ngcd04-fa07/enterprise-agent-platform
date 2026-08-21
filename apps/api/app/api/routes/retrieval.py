import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_membership
from app.db.session import get_db_session
from app.embeddings.base import EmbeddingProvider
from app.embeddings.factory import get_embedding_provider
from app.models.membership import OrganisationMembership
from app.schemas.search import SearchRequest, SearchResponse, SearchResult
from app.services.retrieval_service import RetrievalService
from app.services.submission_service import SubmissionNotFoundError, SubmissionService

router = APIRouter(tags=["retrieval"])


@router.post("/submissions/{submission_id}/search", response_model=SearchResponse)
async def search_submission(
    submission_id: UUID,
    payload: SearchRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    embeddings: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    membership: Annotated[OrganisationMembership, Depends(get_current_membership)],
) -> SearchResponse:
    try:
        await SubmissionService(db).get_submission(
            organisation_id=membership.organisation_id, submission_id=submission_id
        )
    except SubmissionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found") from exc

    start = time.perf_counter()
    results = await RetrievalService(db, embeddings).search(
        organisation_id=membership.organisation_id,
        query=payload.query,
        submission_id=submission_id,
        limit=payload.limit,
    )
    latency_ms = (time.perf_counter() - start) * 1000

    return SearchResponse(
        results=[
            SearchResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                page_number=page_number,
                text=chunk.text,
                score=1.0 - distance,
            )
            for chunk, page_number, distance in results
        ],
        strategy="vector",
        latency_ms=latency_ms,
    )
