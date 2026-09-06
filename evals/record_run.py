"""Persist a real Stage 17 evaluator run for later comparison (Stage 18).

Unlike evals/extraction/run.py and evals/triage_faithfulness/run.py's own
`main()` (console-only, no side effects beyond the printed report), this
script runs an evaluator for real and durably records its per-case
results — the "baseline" or "candidate" side of a release comparison, to
be read back by evals/compare_runs.py.

Usage (from the repo root, with apps/api's venv active):
    source apps/api/.venv/bin/activate
    DATABASE_URL=... SESSION_SECRET=... python3 -m evals.record_run \\
        --evaluator extraction --label baseline

Optional --model overrides which Ollama model actually runs the
evaluator, bypassing Stage 16's routing entirely — this is how to record
a genuine two-model comparison (e.g. --model qwen2.5:3b for a "baseline"
run, --model qwen2.5:14b for a "candidate" run) using real infrastructure
already in this repo, with no fabricated data. This is a manual/optional
demonstration only: CI never invokes this script against a real model —
see evals/smoke_test.py for the CI-safe, fake-model path that exercises
the same recording/comparison code deterministically.
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.llm_gateway.base import LLMGateway  # noqa: E402
from app.llm_gateway.factory import get_llm_gateway  # noqa: E402
from app.llm_gateway.ollama_gateway import OllamaGateway  # noqa: E402
from app.repositories.evaluation_case_result_repository import (  # noqa: E402
    EvaluationCaseResultRepository,
)
from app.repositories.evaluation_run_repository import EvaluationRunRepository  # noqa: E402

from evals.comparison import CaseMetrics  # noqa: E402
from evals.extraction.run import run_extraction_eval  # noqa: E402
from evals.triage_faithfulness.run import run_triage_eval  # noqa: E402

EVALUATORS = ("extraction", "triage")


def _build_llm(model: str | None) -> tuple[LLMGateway, dict[str, str]]:
    """Returns the gateway to actually run against, plus the run_config
    that records what it was. `--model` bypasses Stage 16's
    RoutingLLMGateway entirely and talks to one named Ollama model
    directly — the only way to get a genuine, real two-model comparison
    rather than whatever the routing policy would have picked for a given
    call's declared complexity.
    """
    if model is None:
        return get_llm_gateway(), {"model": "routed"}
    settings = get_settings()
    return OllamaGateway(base_url=settings.ollama_base_url, model=model), {"model": model}


async def record_with_llm(
    llm: LLMGateway, *, evaluator: str, label: str, run_config: dict[str, str]
) -> tuple[uuid.UUID, int]:
    """The reusable core this CLI wraps: runs `evaluator` against whatever
    `llm` it's given and persists the result. Takes the gateway as a
    parameter (not `_build_llm`'s job) so `evals/smoke_test.py` can drive
    the exact same persistence path with a deterministic `FakeLLMGateway`
    in CI — mirroring how `run_extraction_eval`/`run_triage_eval`
    themselves take the gateway as a parameter (Stage 17).
    """
    sessionmaker = get_sessionmaker()

    case_metrics: list[CaseMetrics]
    if evaluator == "extraction":
        extraction_result = await run_extraction_eval(
            llm, sessionmaker=sessionmaker, settings=get_settings()
        )
        case_metrics = extraction_result.case_metrics
    else:
        triage_result = await run_triage_eval(llm, sessionmaker=sessionmaker)
        case_metrics = triage_result.case_metrics

    async with sessionmaker() as session:
        run = await EvaluationRunRepository(session).create(
            evaluator_name=evaluator, label=label, run_config=json.dumps(run_config)
        )
        case_repo = EvaluationCaseResultRepository(session)
        for case in case_metrics:
            await case_repo.create(
                evaluation_run_id=run.id,
                case_key=case.case_key,
                tags=json.dumps(case.tags),
                metrics=json.dumps(case.metrics),
            )
        await session.commit()

    return run.id, len(case_metrics)


async def _record(*, evaluator: str, label: str, model: str | None) -> None:
    llm, run_config = _build_llm(model)
    run_id, case_count = await record_with_llm(
        llm, evaluator=evaluator, label=label, run_config=run_config
    )
    print(f"Recorded {evaluator} run {run_id} (label={label!r}, {case_count} cases)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluator", choices=EVALUATORS, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--model",
        default=None,
        help="Ollama model name to run directly, bypassing routing (manual/optional only).",
    )
    args = parser.parse_args()
    asyncio.run(_record(evaluator=args.evaluator, label=args.label, model=args.model))


if __name__ == "__main__":
    main()
