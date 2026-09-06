"""Compare two persisted evaluation runs (Stage 18) and print a
baseline-vs-candidate report — improved / unchanged / regressed per
aggregate metric and per slice, never letting an aggregate improvement
mask a slice-level regression (see evals/comparison.py). Persists the
comparison itself (including the exact thresholds used) via
EvaluationComparisonRepository, then prints a CLI table.

Usage (from the repo root, with apps/api's venv active):
    source apps/api/.venv/bin/activate
    DATABASE_URL=... SESSION_SECRET=... python3 -m evals.compare_runs \\
        --evaluator extraction --baseline baseline --candidate candidate

--baseline/--candidate each accept either a run id (UUID) or a label; a
label is resolved to its most recent matching run for the given
--evaluator (labels are intentionally not unique — see
EvaluationRunRepository.list_by_label), with a printed note if more than
one run shares it. Exits non-zero if the overall comparison is REGRESSED,
so this can be used as a CI/release gate, not just a report.
"""

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.db.session import get_sessionmaker  # noqa: E402
from app.models.evaluation import ComparisonStatus, EvaluationRun  # noqa: E402
from app.repositories.evaluation_case_result_repository import (  # noqa: E402
    EvaluationCaseResultRepository,
)
from app.repositories.evaluation_comparison_repository import (  # noqa: E402
    EvaluationComparisonRepository,
)
from app.repositories.evaluation_run_repository import EvaluationRunRepository  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from evals.comparison import (  # noqa: E402
    CaseMetrics,
    ComparisonResult,
    OverallStatus,
    RegressionThresholds,
    RowStatus,
    compare,
)

_STATUS_ICON = {
    RowStatus.IMPROVED: "✅",
    RowStatus.UNCHANGED: "➖",
    RowStatus.REGRESSED: "❌",
    RowStatus.UNKNOWN_DIRECTION: "❓",
    RowStatus.MISSING_IN_BASELINE: "⚠️",
    RowStatus.MISSING_IN_CANDIDATE: "⚠️",
}


async def _resolve_run(session: AsyncSession, *, evaluator: str, ref: str) -> EvaluationRun:
    """`ref` is a run id if it parses as a UUID, otherwise a label looked
    up scoped to `evaluator` (label lookups can never cross evaluators,
    unlike a raw id — see the mismatch check in `compare_runs`, which still
    checks unconditionally).
    """
    try:
        run_id = uuid.UUID(ref)
    except ValueError:
        run_id = None

    if run_id is not None:
        run = await EvaluationRunRepository(session).get_by_id(run_id)
        if run is None:
            raise SystemExit(f"No evaluation run found with id {ref}")
        return run

    matches = await EvaluationRunRepository(session).list_by_label(
        evaluator_name=evaluator, label=ref
    )
    if not matches:
        raise SystemExit(f"No {evaluator!r} run found with label {ref!r}")
    if len(matches) > 1:
        print(
            f"Note: {len(matches)} {evaluator!r} runs found with label {ref!r}; "
            f"using the most recent (id={matches[0].id}, created_at={matches[0].created_at})."
        )
    return matches[0]


async def _load_cases(session: AsyncSession, run_id: uuid.UUID) -> list[CaseMetrics]:
    rows = await EvaluationCaseResultRepository(session).list_for_run(run_id)
    return [
        CaseMetrics(
            case_key=row.case_key, tags=json.loads(row.tags), metrics=json.loads(row.metrics)
        )
        for row in rows
    ]


def _format_value(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "—"


def _format_delta(delta: float | None) -> str:
    if delta is None:
        return "—"
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1%}"


def _print_report(
    *, baseline_run: EvaluationRun, candidate_run: EvaluationRun, result: ComparisonResult
) -> None:
    print(
        f"=== Comparison: {baseline_run.label!r} ({baseline_run.id}) -> "
        f"{candidate_run.label!r} ({candidate_run.id}) ===\n"
    )
    print(f"{'Scope':<20} {'Metric':<14} {'Baseline':<10} {'Candidate':<10} {'Delta':<10} Status")
    for row in result.rows:
        icon = _STATUS_ICON[row.status]
        print(
            f"{row.scope:<20} {row.metric:<14} {_format_value(row.baseline_value):<10} "
            f"{_format_value(row.candidate_value):<10} {_format_delta(row.delta):<10} "
            f"{icon} {row.status.value}"
        )
    print(f"\nOverall: {result.overall_status.value.upper()}")


async def compare_runs(
    *,
    evaluator: str,
    baseline_ref: str,
    candidate_ref: str,
    regression_drop: float,
    improvement_rise: float,
) -> tuple[ComparisonResult, uuid.UUID]:
    """Returns the comparison result plus the id it was persisted under —
    callers that want to clean up afterward (see evals/smoke_test.py) need
    that id; the CLI's `main()` below just ignores it.
    """
    sessionmaker = get_sessionmaker()
    thresholds = RegressionThresholds(
        regression_drop=regression_drop, improvement_rise=improvement_rise
    )

    async with sessionmaker() as session:
        baseline_run = await _resolve_run(session, evaluator=evaluator, ref=baseline_ref)
        candidate_run = await _resolve_run(session, evaluator=evaluator, ref=candidate_ref)

        # Unconditional even though label lookups are already scoped to
        # `evaluator`: a raw run id can point at a run for a different
        # evaluator, and comparing across evaluators isn't supported —
        # this must never silently proceed.
        if baseline_run.evaluator_name != evaluator or candidate_run.evaluator_name != evaluator:
            raise SystemExit(
                f"Both runs must be {evaluator!r} runs — got baseline="
                f"{baseline_run.evaluator_name!r}, candidate={candidate_run.evaluator_name!r}."
            )

        baseline_cases = await _load_cases(session, baseline_run.id)
        candidate_cases = await _load_cases(session, candidate_run.id)

    result = compare(baseline_cases, candidate_cases, thresholds=thresholds)

    async with sessionmaker() as session:
        comparison = await EvaluationComparisonRepository(session).create(
            baseline_run_id=baseline_run.id,
            candidate_run_id=candidate_run.id,
            thresholds=json.dumps(asdict(thresholds)),
            overall_status=ComparisonStatus(result.overall_status.value),
            report=json.dumps([asdict(row) for row in result.rows]),
        )
        await session.commit()
        comparison_id = comparison.id

    _print_report(baseline_run=baseline_run, candidate_run=candidate_run, result=result)
    return result, comparison_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluator", choices=("extraction", "triage"), required=True)
    parser.add_argument("--baseline", required=True, help="Run id or label")
    parser.add_argument("--candidate", required=True, help="Run id or label")
    parser.add_argument(
        "--regression-drop", type=float, default=RegressionThresholds().regression_drop
    )
    parser.add_argument(
        "--improvement-rise", type=float, default=RegressionThresholds().improvement_rise
    )
    args = parser.parse_args()

    result, _comparison_id = asyncio.run(
        compare_runs(
            evaluator=args.evaluator,
            baseline_ref=args.baseline,
            candidate_ref=args.candidate,
            regression_drop=args.regression_drop,
            improvement_rise=args.improvement_rise,
        )
    )
    sys.exit(1 if result.overall_status == OverallStatus.REGRESSED else 0)


if __name__ == "__main__":
    main()
