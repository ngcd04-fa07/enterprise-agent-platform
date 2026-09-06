import enum
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column


class ComparisonStatus(enum.StrEnum):
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"


class EvaluationRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One recorded run of a Stage 17 evaluator (evals/extraction or
    evals/triage_faithfulness) — the "baseline" or "candidate" side of a
    Stage 18 release comparison. Deliberately tenant-unscoped (no
    organisation_id), same rationale as AICallTrace: this is engineering/
    platform data about regression testing, not tenant business data.
    """

    __tablename__ = "evaluation_runs"

    evaluator_name: Mapped[str] = mapped_column(sa.String(100), index=True)
    # Free-text, deliberately not unique: the same label (e.g. "baseline")
    # is expected to be reused across many runs over time as the
    # evaluated code changes. evals/comparison.py resolves a label to its
    # most recent matching run rather than requiring uniqueness — see
    # EvaluationRunRepository.list_by_label.
    label: Mapped[str] = mapped_column(sa.String(200), index=True)
    # JSON-encoded dict[str, str] — whatever varies between runs (model
    # name, prompt version, retrieval strategy, chunking version, agent
    # workflow version). Free-form like AICallTrace.call_metadata because
    # which dimensions matter varies by evaluator and by what's actually
    # being compared, not a fixed schema.
    run_config: Mapped[str] = mapped_column(sa.Text)


class EvaluationCaseResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per case scored within one EvaluationRun — the granular
    data slice-level comparison (Stage 18) is computed from. `tags` lets
    one case belong to multiple overlapping slices (e.g. "multi_page" AND
    "has_data") rather than one mutually-exclusive category.
    """

    __tablename__ = "evaluation_case_results"
    __table_args__ = (
        # A case key must be unique within its own run — two rows for the
        # same case in the same run would silently double-count it in
        # every aggregate/slice average.
        sa.UniqueConstraint(
            "evaluation_run_id", "case_key", name="uq_evaluation_case_results_evaluation_run_id"
        ),
    )

    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    case_key: Mapped[str] = mapped_column(sa.String(200))
    # JSON-encoded list[str]
    tags: Mapped[str] = mapped_column(sa.Text)
    # JSON-encoded dict[str, float]
    metrics: Mapped[str] = mapped_column(sa.Text)


class EvaluationComparison(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One persisted baseline-vs-candidate comparison (Stage 18),
    including the exact thresholds used (so a past comparison's verdict
    stays interpretable even if the default thresholds change later) and
    the full row-by-row report (aggregate + every slice, every metric) as
    JSON — see evals/comparison.py for what populates `report`.

    No `ondelete` on either run FK, matching AgentRun.created_by_user_id's
    precedent: a run shouldn't become deletable just because a comparison
    still references it — deleting it would silently corrupt a persisted
    comparison's meaning.
    """

    __tablename__ = "evaluation_comparisons"

    baseline_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("evaluation_runs.id"), index=True
    )
    candidate_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("evaluation_runs.id"), index=True
    )
    # JSON-encoded RegressionThresholds — see evals/comparison.py.
    thresholds: Mapped[str] = mapped_column(sa.Text)
    overall_status: Mapped[ComparisonStatus] = mapped_column(
        str_enum_column(ComparisonStatus, name="comparison_status")
    )
    # JSON-encoded list of every ComparisonRow (scope, metric, baseline
    # value, candidate value, delta, status).
    report: Mapped[str] = mapped_column(sa.Text)
