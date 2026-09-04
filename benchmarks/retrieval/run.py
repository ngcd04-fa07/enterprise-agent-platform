"""Retrieval benchmark: measures Recall@k and MRR for vector-only,
lexical-only, and hybrid search against the labeled fixture set in
dataset.py, then reports the same metrics for hybrid's Reciprocal Rank
Fusion constant across a range of k values.

Runs against a real Postgres and the real embedding model — no fakes,
since the point is measuring actual retrieval quality. Seeds fixture data
inside one transaction that's rolled back at the end, so a benchmark run
never leaves data behind in whatever database DATABASE_URL points at.

Usage (from the repo root, with apps/api's venv active so its dependencies
are importable):
    source apps/api/.venv/bin/activate
    DATABASE_URL=... SESSION_SECRET=... python3 -m benchmarks.retrieval.run
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from app.db.session import get_sessionmaker  # noqa: E402
from app.embeddings.factory import get_embedding_provider  # noqa: E402
from app.repositories.document_chunk_repository import DocumentChunkRepository  # noqa: E402
from app.repositories.document_page_repository import DocumentPageRepository  # noqa: E402
from app.repositories.document_repository import DocumentRepository  # noqa: E402
from app.repositories.organisation_repository import OrganisationRepository  # noqa: E402
from app.repositories.submission_repository import SubmissionRepository  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.services.retrieval_service import RetrievalService  # noqa: E402

from benchmarks.retrieval.dataset import (  # noqa: E402
    BENCHMARK_QUERIES,
    FIXTURE_CHUNKS,
    BenchmarkQuery,
)

RECALL_K = 5
RRF_K_SWEEP = [10, 20, 40, 60, 100, 200]
CURRENT_PRODUCTION_RRF_K = 60


def _reciprocal_rank_fusion(ranked_lists: list[list[uuid.UUID]], *, k: int) -> list[uuid.UUID]:
    scores: dict[uuid.UUID, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)


def _recall_at_k(ranked_ids: list[uuid.UUID], relevant_ids: set[uuid.UUID], k: int) -> float:
    return 1.0 if any(cid in relevant_ids for cid in ranked_ids[:k]) else 0.0


def _reciprocal_rank(ranked_ids: list[uuid.UUID], relevant_ids: set[uuid.UUID]) -> float:
    for rank, cid in enumerate(ranked_ids, start=1):
        if cid in relevant_ids:
            return 1.0 / rank
    return 0.0


async def main() -> None:
    sessionmaker = get_sessionmaker()
    embeddings = get_embedding_provider()

    async with sessionmaker() as session:
        organisations = OrganisationRepository(session)
        users = UserRepository(session)
        submissions = SubmissionRepository(session)
        documents = DocumentRepository(session)
        pages = DocumentPageRepository(session)
        chunks = DocumentChunkRepository(session)

        org = await organisations.create(name="Retrieval Benchmark")
        user = await users.create(
            email="benchmark@example.com", full_name="Benchmark", password_hash="unused"
        )
        submission = await submissions.create(
            organisation_id=org.id, created_by_user_id=user.id, title="Benchmark Submission"
        )
        document = await documents.create(
            organisation_id=org.id,
            submission_id=submission.id,
            filename="benchmark.pdf",
            content_type="application/pdf",
            size_bytes=0,
            storage_key="benchmark/fixture.pdf",
        )

        chunk_vectors = await embeddings.embed_documents([c.text for c in FIXTURE_CHUNKS])
        key_to_chunk_id: dict[str, uuid.UUID] = {}
        for index, (fixture, vector) in enumerate(zip(FIXTURE_CHUNKS, chunk_vectors, strict=True)):
            page = await pages.create(
                document_id=document.id,
                organisation_id=org.id,
                page_number=index + 1,
                text=fixture.text,
            )
            chunk = await chunks.create(
                document_id=document.id,
                page_id=page.id,
                organisation_id=org.id,
                submission_id=submission.id,
                chunk_index=index,
                text=fixture.text,
                start_char=0,
                end_char=len(fixture.text),
                embedding=vector,
            )
            key_to_chunk_id[fixture.key] = chunk.id

        retrieval_service = RetrievalService(session, embeddings)

        async def _run_query(query: BenchmarkQuery) -> tuple[list[uuid.UUID], ...]:
            query_embedding = await embeddings.embed_query(query.query)
            vector = await chunks.search_similar(
                organisation_id=org.id,
                query_embedding=query_embedding,
                submission_id=submission.id,
                limit=len(FIXTURE_CHUNKS),
            )
            lexical = await chunks.search_lexical(
                organisation_id=org.id,
                query=query.query,
                submission_id=submission.id,
                limit=len(FIXTURE_CHUNKS),
            )
            hybrid = await retrieval_service.search(
                organisation_id=org.id,
                query=query.query,
                submission_id=submission.id,
                limit=len(FIXTURE_CHUNKS),
            )
            vector_ids = [c.id for c, _p, _d in vector]
            lexical_ids = [c.id for c, _p, _d in lexical]
            hybrid_ids = [c.id for c, _p, _d in hybrid]
            return vector_ids, lexical_ids, hybrid_ids

        strategy_results: dict[str, list[list[uuid.UUID]]] = {
            "vector": [],
            "lexical": [],
            "hybrid": [],
        }
        rrf_sweep_results: dict[int, list[list[uuid.UUID]]] = {k: [] for k in RRF_K_SWEEP}
        relevant_sets: list[set[uuid.UUID]] = []

        for query in BENCHMARK_QUERIES:
            vector_ids, lexical_ids, hybrid_ids = await _run_query(query)
            strategy_results["vector"].append(vector_ids)
            strategy_results["lexical"].append(lexical_ids)
            strategy_results["hybrid"].append(hybrid_ids)
            relevant_sets.append({key_to_chunk_id[k] for k in query.relevant_keys})
            for k in RRF_K_SWEEP:
                rrf_sweep_results[k].append(_reciprocal_rank_fusion([vector_ids, lexical_ids], k=k))

        await session.rollback()

    print(
        f"=== Retrieval Benchmark ({len(BENCHMARK_QUERIES)} queries, "
        f"{len(FIXTURE_CHUNKS)} fixture chunks) ===\n"
    )

    print(f"{'Query':<45} {'vector':<8} {'lexical':<8} {'hybrid':<8}")
    for i, query in enumerate(BENCHMARK_QUERIES):
        relevant = relevant_sets[i]

        def _rank_display(ranked_ids: list[uuid.UUID], relevant: set[uuid.UUID] = relevant) -> str:
            for rank, cid in enumerate(ranked_ids, start=1):
                if cid in relevant:
                    # "*" marks a hit that exists but falls outside the
                    # Recall@k cutoff — distinct from never finding it at all.
                    return f"#{rank}" if rank <= RECALL_K else f"#{rank}*"
            return "miss"

        print(
            f"{query.query[:44]:<45} "
            f"{_rank_display(strategy_results['vector'][i]):<8} "
            f"{_rank_display(strategy_results['lexical'][i]):<8} "
            f"{_rank_display(strategy_results['hybrid'][i]):<8}"
        )

    print(f"\n{'Strategy':<10} {'Recall@' + str(RECALL_K):<10} {'MRR':<10}")
    for strategy, per_query_results in strategy_results.items():
        recalls = [
            _recall_at_k(ranked, relevant, RECALL_K)
            for ranked, relevant in zip(per_query_results, relevant_sets, strict=True)
        ]
        mrrs = [
            _reciprocal_rank(ranked, relevant)
            for ranked, relevant in zip(per_query_results, relevant_sets, strict=True)
        ]
        print(f"{strategy:<10} {sum(recalls) / len(recalls):<10.3f} {sum(mrrs) / len(mrrs):<10.3f}")

    print(
        f"\n=== RRF k sensitivity (hybrid), current production default "
        f"k={CURRENT_PRODUCTION_RRF_K} ===\n"
    )
    print(f"{'k':<8} {'Recall@' + str(RECALL_K):<10} {'MRR':<10}")
    for k in RRF_K_SWEEP:
        per_query_results = rrf_sweep_results[k]
        recalls = [
            _recall_at_k(ranked, relevant, RECALL_K)
            for ranked, relevant in zip(per_query_results, relevant_sets, strict=True)
        ]
        mrrs = [
            _reciprocal_rank(ranked, relevant)
            for ranked, relevant in zip(per_query_results, relevant_sets, strict=True)
        ]
        marker = "  <- current default" if k == CURRENT_PRODUCTION_RRF_K else ""
        print(f"{k:<8} {sum(recalls) / len(recalls):<10.3f} {sum(mrrs) / len(mrrs):<10.3f}{marker}")


if __name__ == "__main__":
    asyncio.run(main())
