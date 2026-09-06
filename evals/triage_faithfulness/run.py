"""Runs the real AgentService.run_triage against hand-built scenarios,
then judges the resulting summary's faithfulness against exactly what it
was given — see judge.py for why this is the one LLM-as-judge evaluator
in this app rather than a deterministic one.

Extracted fields are seeded directly rather than produced by a real
extraction run, so this eval is isolated to "is the triage summary
faithful," not entangled with extraction accuracy (a separate, already
deterministic eval — see evals/extraction/).

Seeds fixtures inside one transaction that's rolled back at the end.

`run_triage_eval` takes the LLM gateway as a parameter rather than calling
`get_llm_gateway()` itself, so `evals/smoke_test.py` can drive the exact
same seeding/judging logic with a deterministic fake in CI (no Ollama
available there) — `main()` below is the only place that wires in the
real gateway for an actual model-quality run.

Usage (from the repo root, with apps/api's venv active):
    source apps/api/.venv/bin/activate
    DATABASE_URL=... SESSION_SECRET=... python3 -m evals.triage_faithfulness.run
"""

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from app.db.session import get_sessionmaker  # noqa: E402
from app.llm_gateway.base import LLMGateway  # noqa: E402
from app.llm_gateway.factory import get_llm_gateway  # noqa: E402
from app.models.extraction import ExtractionStatus  # noqa: E402
from app.repositories.agent_tool_call_repository import AgentToolCallRepository  # noqa: E402
from app.repositories.document_chunk_repository import DocumentChunkRepository  # noqa: E402
from app.repositories.document_page_repository import DocumentPageRepository  # noqa: E402
from app.repositories.document_repository import DocumentRepository  # noqa: E402
from app.repositories.extracted_field_repository import ExtractedFieldRepository  # noqa: E402
from app.repositories.extraction_run_repository import ExtractionRunRepository  # noqa: E402
from app.repositories.organisation_repository import OrganisationRepository  # noqa: E402
from app.repositories.submission_repository import SubmissionRepository  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.services.agent_service import AgentService  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from evals.comparison import CaseMetrics  # noqa: E402
from evals.triage_faithfulness.dataset import TRIAGE_SCENARIOS  # noqa: E402
from evals.triage_faithfulness.judge import JUDGE_PROMPT_VERSION, judge_summary  # noqa: E402


@dataclass
class TriageEvalResult:
    faithful_count: int = 0
    detail_lines: list[str] = field(default_factory=list)
    # Per-case metrics (Stage 18), one entry per scenario that actually
    # reached the judge — a SKIPPED scenario (synthesis itself failed)
    # contributes no metric rather than a fabricated 0, since "the
    # summary was unfaithful" and "there was no summary to judge" are not
    # the same failure.
    case_metrics: list[CaseMetrics] = field(default_factory=list)


async def run_triage_eval(
    llm: LLMGateway, *, sessionmaker: async_sessionmaker[AsyncSession]
) -> TriageEvalResult:
    result = TriageEvalResult()

    async with sessionmaker() as session:
        org = await OrganisationRepository(session).create(name="Triage Faithfulness Eval Org")
        user = await UserRepository(session).create(
            email="triage-eval@example.com", full_name="Eval", password_hash="unused"
        )
        pages_repo = DocumentPageRepository(session)
        chunks_repo = DocumentChunkRepository(session)
        fields_repo = ExtractedFieldRepository(session)
        runs_repo = ExtractionRunRepository(session)

        for scenario in TRIAGE_SCENARIOS:
            submission = await SubmissionRepository(session).create(
                organisation_id=org.id, created_by_user_id=user.id, title=scenario.key
            )

            if scenario.has_chunks:
                document = await DocumentRepository(session).create(
                    organisation_id=org.id,
                    submission_id=submission.id,
                    filename=f"{scenario.key}.pdf",
                    content_type="application/pdf",
                    size_bytes=0,
                    storage_key=f"eval/{scenario.key}.pdf",
                )
                page = await pages_repo.create(
                    document_id=document.id, organisation_id=org.id, page_number=1, text="n/a"
                )
                chunk = await chunks_repo.create(
                    document_id=document.id,
                    page_id=page.id,
                    organisation_id=org.id,
                    submission_id=submission.id,
                    chunk_index=0,
                    text="n/a",
                    start_char=0,
                    end_char=4,
                    embedding=None,
                )
                if scenario.extracted_fields:
                    extraction_run = await runs_repo.create(
                        organisation_id=org.id,
                        submission_id=submission.id,
                        provider="eval-fixture",
                        model="eval-fixture",
                        status=ExtractionStatus.SUCCEEDED,
                        fields_extracted_count=len(scenario.extracted_fields),
                    )
                    for field_name, value in scenario.extracted_fields.items():
                        await fields_repo.create(
                            organisation_id=org.id,
                            submission_id=submission.id,
                            extraction_run_id=extraction_run.id,
                            source_chunk_id=chunk.id,
                            field_name=field_name,
                            value=value,
                        )

            agent_run = await AgentService(session, llm).run_triage(
                organisation_id=org.id, submission_id=submission.id, created_by_user_id=user.id
            )

            tool_calls = await AgentToolCallRepository(session).list_for_run(
                organisation_id=org.id, agent_run_id=agent_run.id
            )
            synthesize_call = next(
                (call for call in tool_calls if call.tool_name == "synthesize_summary"), None
            )
            if synthesize_call is None:
                result.detail_lines.append(
                    f"{scenario.key}: SKIPPED (run failed, status={agent_run.status.value}, "
                    f"error={agent_run.error_message})"
                )
                continue

            verdict = await judge_summary(
                llm,
                input_summary=synthesize_call.input_summary,
                output_summary=synthesize_call.output_summary,
            )
            if verdict.faithful:
                result.faithful_count += 1
            issues = "; ".join(verdict.issues) if verdict.issues else "none"
            result.detail_lines.append(
                f"{scenario.key}: faithful={verdict.faithful} (recommendation="
                f"{agent_run.recommendation.value if agent_run.recommendation else 'n/a'}, "
                f"issues={issues})"
            )
            result.case_metrics.append(
                CaseMetrics(
                    case_key=scenario.key,
                    tags=scenario.tags,
                    metrics={"faithful": 1.0 if verdict.faithful else 0.0},
                )
            )

        await session.rollback()

    return result


async def main() -> None:
    result = await run_triage_eval(get_llm_gateway(), sessionmaker=get_sessionmaker())

    print(f"=== Triage summary faithfulness (judge prompt {JUDGE_PROMPT_VERSION}) ===\n")
    print("\n".join(result.detail_lines))
    print(f"\nFaithful: {result.faithful_count}/{len(TRIAGE_SCENARIOS)}")


if __name__ == "__main__":
    asyncio.run(main())
