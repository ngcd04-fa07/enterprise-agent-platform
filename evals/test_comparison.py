"""Pure unit tests for evals/comparison.py — no DB, no app.* import, no
LLM. Run via `pytest evals/` from the repo root (with apps/api's venv
active for pytest itself); not folded into apps/api's own `pytest`
invocation, which is scoped to apps/api/tests only.
"""

from evals.comparison import (
    CaseMetrics,
    MetricDirection,
    OverallStatus,
    RegressionThresholds,
    RowStatus,
    aggregate,
    compare,
    slice_aggregate,
)


def _case(key: str, tags: list[str], **metrics: float) -> CaseMetrics:
    return CaseMetrics(case_key=key, tags=tags, metrics=metrics)


def test_aggregate_averages_each_metric_across_cases() -> None:
    cases = [
        _case("a", [], correct=1.0),
        _case("b", [], correct=0.0),
        _case("c", [], correct=1.0),
    ]
    assert aggregate(cases) == {"correct": 2 / 3}


def test_aggregate_of_no_cases_is_empty_not_an_error() -> None:
    assert aggregate([]) == {}


def test_slice_aggregate_groups_by_every_tag_a_case_has() -> None:
    cases = [
        _case("a", ["multi_page", "has_data"], correct=1.0),
        _case("b", ["single_page", "has_data"], correct=0.0),
        _case("c", ["single_page", "no_data"], correct=1.0),
    ]
    slices = slice_aggregate(cases)
    assert slices["multi_page"] == {"correct": 1.0}
    assert slices["has_data"] == {"correct": 0.5}
    assert slices["single_page"] == {"correct": 0.5}
    assert slices["no_data"] == {"correct": 1.0}


def test_required_example_aggregate_improvement_does_not_mask_slice_regression() -> None:
    """The exact scenario from the Stage 18 brief: overall task success
    improves (89% -> 92%) but the scanned-document slice regresses
    sharply (87% -> 71%). The comparison must flag this as an overall
    regression despite the aggregate looking better — never let a
    positive aggregate delta suppress a slice-level regression.

    400 cases per run (100 "scanned_document", 300 "typed_document") is
    the smallest whole-number split that reproduces all four percentages
    from the brief exactly: 87/100 and 71/100 need a scanned-slice
    denominator of 100; hitting 89% and 92% overall from there needs the
    typed-document slice to pick up 269/300 (~89.7%) and 297/300 (99%)
    respectively — both feasible (<=300), confirmed by the sanity-check
    assertions below before anything about the comparison logic itself is
    asserted.
    """

    def _cases(*, scanned_correct: int, typed_correct: int) -> list[CaseMetrics]:
        cases = [
            _case(f"scanned_{i}", ["scanned_document"], correct=1.0 if i < scanned_correct else 0.0)
            for i in range(100)
        ]
        cases += [
            _case(f"typed_{i}", ["typed_document"], correct=1.0 if i < typed_correct else 0.0)
            for i in range(300)
        ]
        return cases

    baseline = _cases(scanned_correct=87, typed_correct=269)
    candidate = _cases(scanned_correct=71, typed_correct=297)

    # Sanity-check the fixtures actually reproduce the brief's numbers
    # before asserting anything about the comparison logic itself.
    assert aggregate(baseline)["correct"] == 0.89
    assert aggregate(candidate)["correct"] == 0.92
    assert slice_aggregate(baseline)["scanned_document"]["correct"] == 0.87
    assert slice_aggregate(candidate)["scanned_document"]["correct"] == 0.71

    result = compare(baseline, candidate)

    aggregate_row = next(r for r in result.rows if r.scope == "aggregate" and r.metric == "correct")
    scanned_row = next(
        r for r in result.rows if r.scope == "scanned_document" and r.metric == "correct"
    )
    assert aggregate_row.status == RowStatus.IMPROVED
    assert scanned_row.status == RowStatus.REGRESSED
    assert result.overall_status == OverallStatus.REGRESSED


def test_small_move_within_threshold_is_unchanged() -> None:
    baseline = [_case("a", [], correct=0.90)]
    candidate = [_case("a", [], correct=0.91)]
    result = compare(baseline, candidate, thresholds=RegressionThresholds())
    row = result.rows[0]
    assert row.status == RowStatus.UNCHANGED
    assert result.overall_status == OverallStatus.UNCHANGED


def test_all_metrics_improved_is_improved_overall() -> None:
    baseline = [_case("a", [], correct=0.80)]
    candidate = [_case("a", [], correct=0.95)]
    result = compare(baseline, candidate)
    assert result.rows[0].status == RowStatus.IMPROVED
    assert result.overall_status == OverallStatus.IMPROVED


def test_metric_missing_from_candidate_is_reported_not_treated_as_zero() -> None:
    baseline = [_case("a", [], correct=1.0, faithful=1.0)]
    candidate = [_case("a", [], correct=1.0)]  # "faithful" absent this run
    result = compare(baseline, candidate)
    faithful_row = next(r for r in result.rows if r.metric == "faithful")
    assert faithful_row.status == RowStatus.MISSING_IN_CANDIDATE
    assert faithful_row.candidate_value is None
    # A missing metric must not itself count as a regression/improvement.
    assert result.overall_status == OverallStatus.UNCHANGED


def test_metric_missing_from_baseline_is_reported_not_treated_as_zero() -> None:
    baseline = [_case("a", [], correct=1.0)]
    candidate = [_case("a", [], correct=1.0, faithful=1.0)]  # new metric this run
    result = compare(baseline, candidate)
    faithful_row = next(r for r in result.rows if r.metric == "faithful")
    assert faithful_row.status == RowStatus.MISSING_IN_BASELINE
    assert faithful_row.baseline_value is None


def test_slice_present_only_in_candidate_is_reported_not_dropped() -> None:
    baseline = [_case("a", ["typed_document"], correct=1.0)]
    candidate = [
        _case("a", ["typed_document"], correct=1.0),
        _case("b", ["scanned_document"], correct=0.5),
    ]
    result = compare(baseline, candidate)
    scanned_row = next(r for r in result.rows if r.scope == "scanned_document")
    assert scanned_row.status == RowStatus.MISSING_IN_BASELINE
    assert scanned_row.baseline_value is None
    assert scanned_row.candidate_value == 0.5


def test_slice_present_only_in_baseline_is_reported_not_dropped() -> None:
    baseline = [
        _case("a", ["typed_document"], correct=1.0),
        _case("b", ["scanned_document"], correct=0.5),
    ]
    candidate = [_case("a", ["typed_document"], correct=1.0)]
    result = compare(baseline, candidate)
    scanned_row = next(r for r in result.rows if r.scope == "scanned_document")
    assert scanned_row.status == RowStatus.MISSING_IN_CANDIDATE
    assert scanned_row.candidate_value is None


def test_unregistered_metric_direction_is_explicit_not_guessed() -> None:
    baseline = [_case("a", [], made_up_metric=0.90)]
    candidate = [_case("a", [], made_up_metric=0.10)]
    result = compare(baseline, candidate, metric_directions={})
    row = result.rows[0]
    assert row.status == RowStatus.UNKNOWN_DIRECTION
    # An unregistered-direction metric must not itself trigger an overall
    # regression/improvement verdict — a human needs to register its
    # direction before it can be judged at all.
    assert result.overall_status == OverallStatus.UNCHANGED


def test_lower_is_better_metric_regresses_when_it_rises() -> None:
    baseline = [_case("a", [], error_rate=0.02)]
    candidate = [_case("a", [], error_rate=0.15)]
    result = compare(
        baseline, candidate, metric_directions={"error_rate": MetricDirection.LOWER_IS_BETTER}
    )
    row = result.rows[0]
    assert row.status == RowStatus.REGRESSED
    assert result.overall_status == OverallStatus.REGRESSED


def test_lower_is_better_metric_improves_when_it_falls() -> None:
    baseline = [_case("a", [], error_rate=0.20)]
    candidate = [_case("a", [], error_rate=0.02)]
    result = compare(
        baseline, candidate, metric_directions={"error_rate": MetricDirection.LOWER_IS_BETTER}
    )
    row = result.rows[0]
    assert row.status == RowStatus.IMPROVED
    assert result.overall_status == OverallStatus.IMPROVED
