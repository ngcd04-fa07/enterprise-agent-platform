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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from tests.fake_llm_gateway import FakeLLMGateway  # noqa: E402

from evals.extraction.dataset import EXTRACTION_CASES  # noqa: E402
from evals.extraction.run import run_extraction_eval  # noqa: E402
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


async def main() -> None:
    problems = [*await _check_extraction_harness(), *await _check_triage_harness()]

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


if __name__ == "__main__":
    asyncio.run(main())
