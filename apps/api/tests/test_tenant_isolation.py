"""Cross-tenant denial tests at the service layer.

These are the service-layer precursors to the eventual HTTP-level
test_user_cannot_read_other_org_submission /
test_user_cannot_modify_other_org_submission (added in Stage 3, once
session-derived organisation context exists to test over HTTP). Proving the
isolation boundary here means Stage 3's auth work builds on top of a layer
that already can't leak across tenants, rather than being the only thing
standing between a bug and a data leak.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRunStatus
from app.models.document import Document
from app.models.document_chunk import EMBEDDING_DIMENSION
from app.models.organisation import Organisation
from app.repositories.agent_run_repository import AgentRunNotFoundError, AgentRunRepository
from app.repositories.agent_tool_call_repository import AgentToolCallRepository
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_page_repository import DocumentPageRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.organisation_repository import OrganisationRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.user_repository import UserRepository
from app.services.submission_service import SubmissionNotFoundError, SubmissionService


def _fake_vector(seed: int) -> list[float]:
    return [float(seed)] * EMBEDDING_DIMENSION


async def _make_org_with_document(
    db_session: AsyncSession, *, org_name: str, user_email: str
) -> tuple[Organisation, Document]:
    """Real Organisation -> Submission -> Document rows (FKs require it),
    so a repository-level cross-tenant test exercises the same schema a
    production query would, not a synthetic shortcut.
    """
    org = await OrganisationRepository(db_session).create(name=org_name)
    user = await UserRepository(db_session).create(
        email=user_email, full_name="Test User", password_hash="test-hash"
    )
    submission = await SubmissionRepository(db_session).create(
        organisation_id=org.id, created_by_user_id=user.id, title=f"{org_name} submission"
    )
    document = await DocumentRepository(db_session).create(
        organisation_id=org.id,
        submission_id=submission.id,
        filename="doc.pdf",
        content_type="application/pdf",
        size_bytes=100,
        storage_key=f"{org.id}/doc.pdf",
    )
    return org, document


async def test_submission_service_cannot_read_other_org_submission(
    db_session: AsyncSession,
) -> None:
    org_a = await OrganisationRepository(db_session).create(name="Org A")
    org_b = await OrganisationRepository(db_session).create(name="Org B")
    user_a = await UserRepository(db_session).create(
        email="a@example.com", full_name="A", password_hash="test-hash"
    )

    service = SubmissionService(db_session)
    submission = await service.create_submission(
        organisation_id=org_a.id, created_by_user_id=user_a.id, title="Org A submission"
    )

    with pytest.raises(SubmissionNotFoundError):
        await service.get_submission(organisation_id=org_b.id, submission_id=submission.id)


async def test_submission_service_cannot_modify_other_org_submission(
    db_session: AsyncSession,
) -> None:
    org_a = await OrganisationRepository(db_session).create(name="Org A")
    org_b = await OrganisationRepository(db_session).create(name="Org B")
    user_a = await UserRepository(db_session).create(
        email="a2@example.com", full_name="A2", password_hash="test-hash"
    )

    service = SubmissionService(db_session)
    submission = await service.create_submission(
        organisation_id=org_a.id, created_by_user_id=user_a.id, title="Org A submission"
    )

    with pytest.raises(SubmissionNotFoundError):
        await service.update_submission(
            organisation_id=org_b.id, submission_id=submission.id, title="Hijacked"
        )


async def test_document_page_repository_excludes_other_org_pages_when_both_present(
    db_session: AsyncSession,
) -> None:
    """Exercises DocumentPageRepository's own organisation_id filter
    directly, with real rows from both orgs present in the same query scope
    — unlike the HTTP-level cross-org tests, which all short-circuit on an
    earlier submission/document-ownership 404 before this filter ever runs.
    If this filter were ever dropped, this test (unlike the HTTP ones)
    would catch it.
    """
    org_a, document_a = await _make_org_with_document(
        db_session, org_name="Page Org A", user_email="pagea@example.com"
    )
    org_b, document_b = await _make_org_with_document(
        db_session, org_name="Page Org B", user_email="pageb@example.com"
    )
    pages = DocumentPageRepository(db_session)
    await pages.create(
        document_id=document_a.id, organisation_id=org_a.id, page_number=1, text="Org A page"
    )
    await pages.create(
        document_id=document_b.id, organisation_id=org_b.id, page_number=1, text="Org B page"
    )

    org_a_pages = await pages.list_for_document(organisation_id=org_a.id, document_id=document_a.id)

    assert [page.text for page in org_a_pages] == ["Org A page"]


async def test_document_chunk_repository_excludes_other_org_chunks_when_both_present(
    db_session: AsyncSession,
) -> None:
    """Same as above but for DocumentChunkRepository — list_for_document,
    search_similar (the pgvector query), and search_lexical (the full-text
    query, Stage 10): with both orgs' data present in the same table, org
    A's queries must never return org B's chunk, even when org B's chunk
    is the closer vector match (search_similar) or shares the exact
    search keyword (search_lexical, both chunks' text contains "chunk").
    """
    org_a, document_a = await _make_org_with_document(
        db_session, org_name="Chunk Org A", user_email="chunka@example.com"
    )
    org_b, document_b = await _make_org_with_document(
        db_session, org_name="Chunk Org B", user_email="chunkb@example.com"
    )
    pages = DocumentPageRepository(db_session)
    page_a = await pages.create(
        document_id=document_a.id, organisation_id=org_a.id, page_number=1, text="Org A page"
    )
    page_b = await pages.create(
        document_id=document_b.id, organisation_id=org_b.id, page_number=1, text="Org B page"
    )

    chunks = DocumentChunkRepository(db_session)
    await chunks.create(
        document_id=document_a.id,
        page_id=page_a.id,
        organisation_id=org_a.id,
        submission_id=document_a.submission_id,
        chunk_index=0,
        text="Org A chunk",
        start_char=0,
        end_char=11,
        embedding=_fake_vector(1),
    )
    # Org B's chunk is the nearer vector match to the query below — proving
    # the organisation filter, not just result ordering, is what keeps it
    # out of org A's results.
    await chunks.create(
        document_id=document_b.id,
        page_id=page_b.id,
        organisation_id=org_b.id,
        submission_id=document_b.submission_id,
        chunk_index=0,
        text="Org B chunk",
        start_char=0,
        end_char=11,
        embedding=_fake_vector(2),
    )

    org_a_chunks = await chunks.list_for_document(
        organisation_id=org_a.id, document_id=document_a.id
    )
    assert [chunk.text for chunk in org_a_chunks] == ["Org A chunk"]

    org_a_results = await chunks.search_similar(
        organisation_id=org_a.id, query_embedding=_fake_vector(2), limit=10
    )
    assert [chunk.text for chunk, _page_number, _distance in org_a_results] == ["Org A chunk"]

    org_a_lexical_results = await chunks.search_lexical(
        organisation_id=org_a.id, query="chunk", limit=10
    )
    assert [chunk.text for chunk, _page_number, _rank in org_a_lexical_results] == ["Org A chunk"]


async def test_agent_run_repository_excludes_other_org_runs_when_both_present(
    db_session: AsyncSession,
) -> None:
    """Same rigor as the repositories above, applied to Stage 12's agent
    tables: with both orgs' runs and tool calls present, org A's queries
    must never return org B's, and fetching org B's run_id directly via
    org A's organisation_id must fail exactly like a nonexistent run.
    """
    org_a, document_a = await _make_org_with_document(
        db_session, org_name="Agent Org A", user_email="agenta@example.com"
    )
    org_b, document_b = await _make_org_with_document(
        db_session, org_name="Agent Org B", user_email="agentb@example.com"
    )
    user_a = await UserRepository(db_session).create(
        email="agenta-user@example.com", full_name="A", password_hash="test-hash"
    )
    user_b = await UserRepository(db_session).create(
        email="agentb-user@example.com", full_name="B", password_hash="test-hash"
    )

    runs = AgentRunRepository(db_session)
    tool_calls = AgentToolCallRepository(db_session)

    run_a = await runs.create(
        organisation_id=org_a.id,
        submission_id=document_a.submission_id,
        created_by_user_id=user_a.id,
        status=AgentRunStatus.COMPLETED,
    )
    run_b = await runs.create(
        organisation_id=org_b.id,
        submission_id=document_b.submission_id,
        created_by_user_id=user_b.id,
        status=AgentRunStatus.COMPLETED,
    )
    await tool_calls.create(
        agent_run_id=run_a.id,
        organisation_id=org_a.id,
        sequence_index=1,
        tool_name="gather_evidence",
        input_summary="{}",
        output_summary="Org A output",
    )
    await tool_calls.create(
        agent_run_id=run_b.id,
        organisation_id=org_b.id,
        sequence_index=1,
        tool_name="gather_evidence",
        input_summary="{}",
        output_summary="Org B output",
    )

    org_a_runs = await runs.list_for_submission(
        organisation_id=org_a.id, submission_id=document_a.submission_id
    )
    assert [run.id for run in org_a_runs] == [run_a.id]

    with pytest.raises(AgentRunNotFoundError):
        await runs.get(organisation_id=org_a.id, agent_run_id=run_b.id)

    org_a_tool_calls = await tool_calls.list_for_run(
        organisation_id=org_a.id, agent_run_id=run_a.id
    )
    assert [call.output_summary for call in org_a_tool_calls] == ["Org A output"]

    # Even asking for org B's own run's tool calls under org A's
    # organisation_id must come back empty, not org B's real rows.
    cross_org_tool_calls = await tool_calls.list_for_run(
        organisation_id=org_a.id, agent_run_id=run_b.id
    )
    assert cross_org_tool_calls == []
