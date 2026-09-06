"""Deterministic extraction-accuracy evaluator — the primary evaluator
CLAUDE.md's AI rules call for ("prefer deterministic evaluators"). Runs
the real ExtractionService against a hand-labeled dataset and scores each
field against ground truth via normalized substring matching — no
LLM-as-judge here, because "did the text say $500,000" is not a semantic
judgment call.

Seeds fixtures inside one transaction that's rolled back at the end (same
pattern as benchmarks/retrieval), so a run never leaves data behind.

`run_extraction_eval` takes the LLM gateway as a parameter rather than
calling `get_llm_gateway()` itself, so `evals/smoke_test.py` can drive the
exact same seeding/scoring logic with a deterministic fake in CI (no
Ollama available there) — `main()` below is the only place that wires in
the real gateway for an actual model-quality run.

Usage (from the repo root, with apps/api's venv active):
    source apps/api/.venv/bin/activate
    DATABASE_URL=... SESSION_SECRET=... python3 -m evals.extraction.run
"""

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from app.core.config import Settings, get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.llm_gateway.base import LLMGateway  # noqa: E402
from app.llm_gateway.factory import get_llm_gateway  # noqa: E402
from app.repositories.document_chunk_repository import DocumentChunkRepository  # noqa: E402
from app.repositories.document_page_repository import DocumentPageRepository  # noqa: E402
from app.repositories.document_repository import DocumentRepository  # noqa: E402
from app.repositories.extracted_field_repository import ExtractedFieldRepository  # noqa: E402
from app.repositories.organisation_repository import OrganisationRepository  # noqa: E402
from app.repositories.submission_repository import SubmissionRepository  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.schemas.extraction import EXTRACTION_FIELD_NAMES  # noqa: E402
from app.services.extraction_service import ExtractionService  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from evals.comparison import CaseMetrics  # noqa: E402
from evals.extraction.dataset import EXTRACTION_CASES  # noqa: E402


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _matches(expected: str, actual: str) -> bool:
    return _normalize(expected) in _normalize(actual)


@dataclass
class ExtractionEvalResult:
    counts: dict[str, int] = field(
        default_factory=lambda: {
            "correct_value": 0,
            "correct_null": 0,
            "hallucination": 0,
            "missed": 0,
            "wrong_value": 0,
        }
    )
    per_case_detail: list[str] = field(default_factory=list)
    # Per-case metrics (Stage 18) — "correct" is the fraction of this
    # case's fields that were scored correct (a matched value or a
    # correctly-absent null); a hallucination or a wrong/missed value all
    # count against it. Additive alongside the aggregate counts above,
    # which stay the CLI's primary printed output.
    case_metrics: list[CaseMetrics] = field(default_factory=list)

    @property
    def precision(self) -> float:
        correct = self.counts["correct_value"]
        total_predictions = correct + self.counts["hallucination"] + self.counts["wrong_value"]
        return correct / total_predictions if total_predictions else 1.0

    @property
    def recall(self) -> float:
        correct = self.counts["correct_value"]
        total_expected = correct + self.counts["missed"] + self.counts["wrong_value"]
        return correct / total_expected if total_expected else 1.0


async def run_extraction_eval(
    llm: LLMGateway,
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> ExtractionEvalResult:
    result = ExtractionEvalResult()

    async with sessionmaker() as session:
        org = await OrganisationRepository(session).create(name="Extraction Eval Org")
        user = await UserRepository(session).create(
            email="extraction-eval@example.com", full_name="Eval", password_hash="unused"
        )
        pages_repo = DocumentPageRepository(session)
        chunks_repo = DocumentChunkRepository(session)

        for case in EXTRACTION_CASES:
            submission = await SubmissionRepository(session).create(
                organisation_id=org.id, created_by_user_id=user.id, title=case.key
            )
            document = await DocumentRepository(session).create(
                organisation_id=org.id,
                submission_id=submission.id,
                filename=f"{case.key}.pdf",
                content_type="application/pdf",
                size_bytes=0,
                storage_key=f"eval/{case.key}.pdf",
            )
            for index, page_text in enumerate(case.page_texts):
                page = await pages_repo.create(
                    document_id=document.id,
                    organisation_id=org.id,
                    page_number=index + 1,
                    text=page_text,
                )
                await chunks_repo.create(
                    document_id=document.id,
                    page_id=page.id,
                    organisation_id=org.id,
                    submission_id=submission.id,
                    chunk_index=index,
                    text=page_text,
                    start_char=0,
                    end_char=len(page_text),
                    embedding=None,  # extraction never reads the embedding column
                )

            await ExtractionService(session, llm, settings).extract_submission(
                organisation_id=org.id, submission_id=submission.id
            )
            field_rows = await ExtractedFieldRepository(session).list_for_submission(
                organisation_id=org.id, submission_id=submission.id
            )
            actual = {field.field_name: field.value for field, _doc_id, _page in field_rows}

            case_lines = [f"{case.key}:"]
            case_correct_fields = 0
            for field_name in EXTRACTION_FIELD_NAMES:
                expected_value = case.expected[field_name]
                actual_value = actual.get(field_name)
                if expected_value is None:
                    if actual_value is None:
                        result.counts["correct_null"] += 1
                        case_correct_fields += 1
                        outcome = "correct (null)"
                    else:
                        result.counts["hallucination"] += 1
                        outcome = f"HALLUCINATION (got {actual_value!r}, expected none)"
                elif actual_value is None:
                    result.counts["missed"] += 1
                    outcome = f"MISSED (expected {expected_value!r})"
                elif _matches(expected_value, actual_value):
                    result.counts["correct_value"] += 1
                    case_correct_fields += 1
                    outcome = "correct"
                else:
                    result.counts["wrong_value"] += 1
                    outcome = f"WRONG (got {actual_value!r}, expected {expected_value!r})"
                case_lines.append(f"  {field_name}: {outcome}")
            result.per_case_detail.append("\n".join(case_lines))
            result.case_metrics.append(
                CaseMetrics(
                    case_key=case.key,
                    tags=case.tags,
                    metrics={"correct": case_correct_fields / len(EXTRACTION_FIELD_NAMES)},
                )
            )

        await session.rollback()

    return result


async def main() -> None:
    result = await run_extraction_eval(
        get_llm_gateway(), sessionmaker=get_sessionmaker(), settings=get_settings()
    )

    print("\n".join(result.per_case_detail))
    print(f"\n=== Extraction accuracy ({len(EXTRACTION_CASES)} cases) ===")
    print(f"Correct value:  {result.counts['correct_value']}")
    print(f"Correct null:   {result.counts['correct_null']}")
    print(f"Hallucinations: {result.counts['hallucination']}")
    print(f"Missed:         {result.counts['missed']}")
    print(f"Wrong value:    {result.counts['wrong_value']}")
    print(f"Precision: {result.precision:.1%}   Recall: {result.recall:.1%}")


if __name__ == "__main__":
    asyncio.run(main())
