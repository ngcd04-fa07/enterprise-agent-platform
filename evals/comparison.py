"""Pure, dependency-free release-comparison engine (Stage 18) — no
`app.*` import, no database, no LLM. Given two sets of per-case metrics
(a "baseline" and a "candidate"), computes aggregate and per-slice
metric averages and flags each one improved/unchanged/regressed against
an explicit threshold. Deliberately kept free of any DB/app dependency so
its logic is trivially unit-testable (see evals/test_comparison.py) —
persistence and orchestration (recording a real run, loading two runs
from Postgres, printing a report) live in evals/record_run.py and
evals/compare_runs.py, which both import from here.

The one invariant this module exists to enforce: an aggregate-level
improvement never masks a slice-level regression. Each (scope, metric)
pair is evaluated completely independently — see `compare()`.
"""

import enum
import statistics
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CaseMetrics:
    """One case's scored metrics, produced by an evaluator (see
    evals/extraction/run.py, evals/triage_faithfulness/run.py). `tags`
    lets a case belong to more than one slice at once (e.g. a case can be
    both "multi_page" and "has_data") rather than one exclusive category.
    """

    case_key: str
    tags: list[str]
    metrics: dict[str, float]


class MetricDirection(enum.StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


# Every metric this eval platform currently produces (extraction's
# "correct", triage's "faithful") is a 0..1 rate where higher is better.
# This registry is deliberately explicit and finite, not a fallback
# default: a metric name that isn't listed here is reported as
# UNKNOWN_DIRECTION by `compare()` rather than silently assumed to be
# "higher is better." Future metrics this platform doesn't have yet
# (latency, cost, hallucination rate, error rate) are lower-is-better —
# guessing wrong would silently invert every regression/improvement call
# for them, which is exactly the failure mode this registry exists to
# prevent. Add a metric here only once its evaluator actually produces it.
KNOWN_METRIC_DIRECTIONS: dict[str, MetricDirection] = {
    "correct": MetricDirection.HIGHER_IS_BETTER,
    "faithful": MetricDirection.HIGHER_IS_BETTER,
}


@dataclass(frozen=True)
class RegressionThresholds:
    """Both expressed as a fraction of the 0..1 metrics this platform
    currently produces (0.05 = 5 percentage points). A metric moving
    *against* its known-good direction by more than `regression_drop` is
    REGRESSED; moving *with* it by at least `improvement_rise` is
    IMPROVED; anything in between is UNCHANGED. One pair of thresholds
    applies uniformly to every metric — there's only one metric "shape"
    (a 0..1 rate) in this platform today, so a single absolute-point rule
    is simpler to reason about than a per-metric config, and is stored
    alongside every persisted comparison specifically so it can change
    later without corrupting the interpretation of past comparisons.
    """

    regression_drop: float = 0.05
    improvement_rise: float = 0.02


DEFAULT_THRESHOLDS = RegressionThresholds()


class RowStatus(enum.StrEnum):
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"
    # The metric direction isn't registered in KNOWN_METRIC_DIRECTIONS —
    # surfaced explicitly rather than guessed, per this module's
    # docstring. A human needs to add the metric to the registry.
    UNKNOWN_DIRECTION = "unknown_direction"
    # The metric/slice exists on one side only — e.g. a slice tag used by
    # the candidate's dataset didn't exist when the baseline was
    # recorded. Reported explicitly rather than treated as 0, which would
    # silently manufacture a fake regression or improvement.
    MISSING_IN_BASELINE = "missing_in_baseline"
    MISSING_IN_CANDIDATE = "missing_in_candidate"


class OverallStatus(enum.StrEnum):
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"


@dataclass(frozen=True)
class ComparisonRow:
    scope: str  # "aggregate" or a slice/tag name
    metric: str
    baseline_value: float | None
    candidate_value: float | None
    delta: float | None
    status: RowStatus


@dataclass(frozen=True)
class ComparisonResult:
    rows: list[ComparisonRow] = field(default_factory=list)
    overall_status: OverallStatus = OverallStatus.UNCHANGED


def aggregate(cases: list[CaseMetrics]) -> dict[str, float]:
    """Mean of each metric across every case that reports it. A metric
    only some cases report is still averaged correctly — over just the
    cases that have it, not silently treated as 0 for the rest.
    """
    values_by_metric: dict[str, list[float]] = {}
    for case in cases:
        for metric_name, value in case.metrics.items():
            values_by_metric.setdefault(metric_name, []).append(value)
    return {metric: statistics.mean(values) for metric, values in values_by_metric.items()}


def slice_aggregate(cases: list[CaseMetrics]) -> dict[str, dict[str, float]]:
    """Same as `aggregate`, grouped by every tag seen across `cases`. A
    case with tags ["multi_page", "has_data"] contributes to both groups
    independently.
    """
    cases_by_tag: dict[str, list[CaseMetrics]] = {}
    for case in cases:
        for tag in case.tags:
            cases_by_tag.setdefault(tag, []).append(case)
    return {tag: aggregate(tagged_cases) for tag, tagged_cases in cases_by_tag.items()}


def _row_status(
    *,
    baseline_value: float | None,
    candidate_value: float | None,
    metric: str,
    thresholds: RegressionThresholds,
    metric_directions: dict[str, MetricDirection],
) -> tuple[float | None, RowStatus]:
    if baseline_value is None:
        return None, RowStatus.MISSING_IN_BASELINE
    if candidate_value is None:
        return None, RowStatus.MISSING_IN_CANDIDATE

    delta = candidate_value - baseline_value
    direction = metric_directions.get(metric)
    if direction is None:
        return delta, RowStatus.UNKNOWN_DIRECTION

    # Normalize so a positive signed_delta always means "moved in the
    # direction that's good for this metric" — regardless of whether
    # higher or lower is actually better for it.
    signed_delta = delta if direction == MetricDirection.HIGHER_IS_BETTER else -delta
    if signed_delta <= -thresholds.regression_drop:
        return delta, RowStatus.REGRESSED
    if signed_delta >= thresholds.improvement_rise:
        return delta, RowStatus.IMPROVED
    return delta, RowStatus.UNCHANGED


def compare(
    baseline_cases: list[CaseMetrics],
    candidate_cases: list[CaseMetrics],
    *,
    thresholds: RegressionThresholds = DEFAULT_THRESHOLDS,
    metric_directions: dict[str, MetricDirection] = KNOWN_METRIC_DIRECTIONS,
) -> ComparisonResult:
    """Compares aggregate metrics and every slice independently — a slice
    present in only one side is still reported (MISSING_IN_*), never
    silently dropped from the report or treated as a 0 value. The
    aggregate-level status is never allowed to suppress or override a
    slice-level regression: `overall_status` is REGRESSED the instant any
    row anywhere (aggregate or slice) is REGRESSED, independent of every
    other row's status. This is the one behavior Stage 18 exists for —
    see evals/test_comparison.py's required example.
    """
    baseline_agg = aggregate(baseline_cases)
    candidate_agg = aggregate(candidate_cases)
    baseline_slices = slice_aggregate(baseline_cases)
    candidate_slices = slice_aggregate(candidate_cases)

    scopes: dict[str, tuple[dict[str, float], dict[str, float]]] = {
        "aggregate": (baseline_agg, candidate_agg)
    }
    for slice_name in sorted(set(baseline_slices) | set(candidate_slices)):
        scopes[slice_name] = (
            baseline_slices.get(slice_name, {}),
            candidate_slices.get(slice_name, {}),
        )

    rows: list[ComparisonRow] = []
    for scope, (baseline_metrics, candidate_metrics) in scopes.items():
        for metric in sorted(set(baseline_metrics) | set(candidate_metrics)):
            delta, status = _row_status(
                baseline_value=baseline_metrics.get(metric),
                candidate_value=candidate_metrics.get(metric),
                metric=metric,
                thresholds=thresholds,
                metric_directions=metric_directions,
            )
            rows.append(
                ComparisonRow(
                    scope=scope,
                    metric=metric,
                    baseline_value=baseline_metrics.get(metric),
                    candidate_value=candidate_metrics.get(metric),
                    delta=delta,
                    status=status,
                )
            )

    if any(row.status == RowStatus.REGRESSED for row in rows):
        overall_status = OverallStatus.REGRESSED
    elif any(row.status == RowStatus.IMPROVED for row in rows):
        overall_status = OverallStatus.IMPROVED
    else:
        overall_status = OverallStatus.UNCHANGED

    return ComparisonResult(rows=rows, overall_status=overall_status)
