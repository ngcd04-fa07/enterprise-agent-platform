"""CI-safe smoke test for the eval harness itself — not a model-quality
measurement. `evals/extraction/run.py` and `evals/triage_faithfulness/run.py`
measure whether the real Ollama models are actually any good; this file
instead proves the harness code around them — dataset loading, fixture
seeding inside a rolled-back transaction, the scoring/judging wiring — is
correct, using a deterministic `FakeLLMGateway` programmed to behave
perfectly. That's what lets it run in CI, which has real Postgres but no
Ollama at all.

A real, useful regression tripwire: if a change to `ExtractionService`,
the scoring function, `AgentService`, or `judge_summary` ever breaks the
harness's own wiring (a renamed field, a changed call signature, a broken
merge), this fails immediately in CI — instead of only being noticed the
next time someone happens to run the real evaluators by hand.

Usage (from the repo root, with apps/api's venv active):
    DATABASE_URL=... SESSION_SECRET=... python3 -m evals.smoke_test
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.repositories.evaluation_comparison_repository import (  # noqa: E402
    EvaluationComparisonRepository,
)
from app.repositories.evaluation_run_repository import EvaluationRunRepository  # noqa: E402
from tests.fake_llm_gateway import FakeLLMGateway  # noqa: E402

from evals.compare_runs import compare_runs  # noqa: E402
from evals.comparison import OverallStatus, RowStatus  # noqa: E402
from evals.extraction.dataset import EXTRACTION_CASES  # noqa: E402
from evals.extraction.run import run_extraction_eval  # noqa: E402
from evals.record_run import record_with_llm  # noqa: E402
from evals.triage_faithfulness.dataset import TRIAGE_SCENARIOS  # noqa: E402
from evals.triage_faithfulness.run import run_triage_eval  # noqa: E402


async def _check_extraction_harness() -> list[str]:
    """A fake that answers every chunk with the case's exact expected
    values should score a perfect 100%/100%/0 hallucinations/0 missed/0
    wrong — anything else means the harness's own seeding or scoring logic
    is broken, not that a model got something wrong.
    """
    fake = FakeLLMGateway()
    for case in EXTRACTION_CASES:
        for page_text in case.page_texts:
            fake.responses[page_text] = dict(case.expected)

    result = await run_extraction_eval(
        fake, sessionmaker=get_sessionmaker(), settings=get_settings()
    )

    problems = []
    if result.counts["hallucination"] != 0:
        problems.append(f"expected 0 hallucinations from a perfect fake, got {result.counts}")
    if result.counts["missed"] != 0:
        problems.append(f"expected 0 missed fields from a perfect fake, got {result.counts}")
    if result.counts["wrong_value"] != 0:
        problems.append(f"expected 0 wrong values from a perfect fake, got {result.counts}")
    if result.precision != 1.0 or result.recall != 1.0:
        problems.append(f"expected precision=recall=1.0, got {result.precision}/{result.recall}")
    return problems


async def _check_triage_harness() -> list[str]:
    """A fake that always returns a valid summary and a `faithful: true`
    verdict should make every scenario judged faithful, and every scenario
    should actually reach the judge (a `synthesize_summary` tool call
    recorded) — anything else means the harness's own scenario wiring or
    result aggregation is broken, not that a model was unfaithful.
    """
    fake = FakeLLMGateway()
    fake.default_response = {
        "summary": "Everything in this submission looks fine.",
        "faithful": True,
        "issues": [],
    }

    result = await run_triage_eval(fake, sessionmaker=get_sessionmaker())

    problems = []
    if len(result.detail_lines) != len(TRIAGE_SCENARIOS):
        problems.append(
            f"expected {len(TRIAGE_SCENARIOS)} detail lines, got {len(result.detail_lines)}"
        )
    if any("SKIPPED" in line for line in result.detail_lines):
        problems.append(f"a scenario was skipped (synthesis failed): {result.detail_lines}")
    if result.faithful_count != len(TRIAGE_SCENARIOS):
        problems.append(
            f"expected all {len(TRIAGE_SCENARIOS)} scenarios faithful from a fake that always "
            f"returns faithful=True, got {result.faithful_count}"
        )
    return problems


async def _check_comparison_harness() -> list[str]:
    """Records two fake-model extraction runs — a baseline that answers
    every chunk perfectly, and a candidate identical except it fails to
    find anything on the second page of "fields_split_across_pages" (a
    real dataset case tagged "multi_page"/"has_data", not a fabricated
    slice) — then confirms evals/compare_runs.py's persisted comparison
    correctly flags a REGRESSED slice. This is the exact record -> persist
    -> load -> compare -> persist-the-comparison path evals/record_run.py
    and evals/compare_runs.py expose for real, manual use (Stage 18),
    exercised here deterministically so it runs in CI with no Ollama —
    the same relationship Stage 17's two checks above have to the real
    evaluators. Cleans up its own persisted rows afterward, regardless of
    outcome: this is a smoke test, not real comparison history worth
    keeping.
    """
    split_case = next(c for c in EXTRACTION_CASES if c.key == "fields_split_across_pages")

    baseline_fake = FakeLLMGateway()
    candidate_fake = FakeLLMGateway()
    for case in EXTRACTION_CASES:
        if case.key == split_case.key:
            continue  # given a realistic per-page split below instead
        for page_text in case.page_texts:
            # Every page of a single-page case gets the case's full
            # expected dict — harmless here since each such case only
            # has one page, so there's no cross-page value to leak.
            baseline_fake.responses[page_text] = dict(case.expected)
            candidate_fake.responses[page_text] = dict(case.expected)

    # split_case's two pages must each reveal only the fields that page
    # actually states (see evals/extraction/dataset.py) — giving both
    # pages the *entire* expected dict, as above, would let page one alone
    # satisfy every field regardless of what page two says, making it
    # impossible to regress page two's contribution at all.
    page_one_fields = {
        "named_insured": split_case.expected["named_insured"],
        "business_description": split_case.expected["business_description"],
        "requested_effective_date": None,
        "requested_coverage_limit": None,
        "broker_or_agent_name": None,
    }
    page_two_fields = {
        "named_insured": None,
        "business_description": None,
        "requested_effective_date": split_case.expected["requested_effective_date"],
        "requested_coverage_limit": split_case.expected["requested_coverage_limit"],
        "broker_or_agent_name": split_case.expected["broker_or_agent_name"],
    }
    baseline_fake.responses[split_case.page_texts[0]] = page_one_fields
    baseline_fake.responses[split_case.page_texts[1]] = page_two_fields
    candidate_fake.responses[split_case.page_texts[0]] = page_one_fields
    candidate_fake.responses[split_case.page_texts[1]] = {}  # deliberately regress this chunk

    label_suffix = uuid.uuid4().hex[:8]
    baseline_label = f"smoke-test-baseline-{label_suffix}"
    candidate_label = f"smoke-test-candidate-{label_suffix}"

    baseline_run_id, _ = await record_with_llm(
        baseline_fake,
        evaluator="extraction",
        label=baseline_label,
        run_config={"model": "fake-baseline"},
    )
    candidate_run_id, _ = await record_with_llm(
        candidate_fake,
        evaluator="extraction",
        label=candidate_label,
        run_config={"model": "fake-candidate"},
    )

    problems: list[str] = []
    comparison_id: uuid.UUID | None = None
    try:
        result, comparison_id = await compare_runs(
            evaluator="extraction",
            baseline_ref=baseline_label,
            candidate_ref=candidate_label,
            regression_drop=0.05,
            improvement_rise=0.02,
        )

        multi_page_rows = [r for r in result.rows if r.scope == "multi_page"]
        if not multi_page_rows or any(r.status != RowStatus.REGRESSED for r in multi_page_rows):
            problems.append(
                f"expected the 'multi_page' slice to be REGRESSED, got {multi_page_rows}"
            )
        if result.overall_status != OverallStatus.REGRESSED:
            problems.append(
                f"expected overall comparison status REGRESSED, got {result.overall_status}"
            )
    finally:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            if comparison_id is not None:
                await EvaluationComparisonRepository(session).delete(comparison_id)
            run_repo = EvaluationRunRepository(session)
            await run_repo.delete(baseline_run_id)
            await run_repo.delete(candidate_run_id)
            await session.commit()

    return problems


async def main() -> None:
    problems = [
        *await _check_extraction_harness(),
        *await _check_triage_harness(),
        *await _check_comparison_harness(),
    ]

    if problems:
        print("=== Eval harness smoke test: FAILED ===")
        for problem in problems:
            print(f"- {problem}")
        sys.exit(1)

    print("=== Eval harness smoke test: passed ===")
    print(
        f"extraction harness: {len(EXTRACTION_CASES)} cases scored correctly against a perfect "
        "fake model"
    )
    print(
        f"triage harness: {len(TRIAGE_SCENARIOS)} scenarios reached and passed the faithfulness "
        "judge against a fake model"
    )
    print(
        "comparison harness: a deliberately-regressed fake candidate run was correctly flagged "
        "REGRESSED on its 'multi_page' slice, despite no other slice changing"
    )


if __name__ == "__main__":
    asyncio.run(main())
