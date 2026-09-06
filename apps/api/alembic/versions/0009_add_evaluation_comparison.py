"""add evaluation comparison tables

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_columns() -> tuple[sa.Column, sa.Column]:
    now = sa.text("now()")
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    )


def upgrade() -> None:
    comparison_status = sa.Enum("improved", "unchanged", "regressed", name="comparison_status")

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluator_name", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("run_config", sa.Text(), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_runs")),
    )
    op.create_index(
        op.f("ix_evaluation_runs_evaluator_name"), "evaluation_runs", ["evaluator_name"]
    )
    op.create_index(op.f("ix_evaluation_runs_label"), "evaluation_runs", ["label"])

    op.create_table(
        "evaluation_case_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("case_key", sa.String(length=200), nullable=False),
        sa.Column("tags", sa.Text(), nullable=False),
        sa.Column("metrics", sa.Text(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"],
            ["evaluation_runs.id"],
            name=op.f("fk_evaluation_case_results_evaluation_run_id_evaluation_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_case_results")),
        sa.UniqueConstraint(
            "evaluation_run_id",
            "case_key",
            name=op.f("uq_evaluation_case_results_evaluation_run_id"),
        ),
    )
    op.create_index(
        op.f("ix_evaluation_case_results_evaluation_run_id"),
        "evaluation_case_results",
        ["evaluation_run_id"],
    )

    op.create_table(
        "evaluation_comparisons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("baseline_run_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_run_id", sa.Uuid(), nullable=False),
        sa.Column("thresholds", sa.Text(), nullable=False),
        sa.Column("overall_status", comparison_status, nullable=False),
        sa.Column("report", sa.Text(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["baseline_run_id"],
            ["evaluation_runs.id"],
            name=op.f("fk_evaluation_comparisons_baseline_run_id_evaluation_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_run_id"],
            ["evaluation_runs.id"],
            name=op.f("fk_evaluation_comparisons_candidate_run_id_evaluation_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_comparisons")),
    )
    op.create_index(
        op.f("ix_evaluation_comparisons_baseline_run_id"),
        "evaluation_comparisons",
        ["baseline_run_id"],
    )
    op.create_index(
        op.f("ix_evaluation_comparisons_candidate_run_id"),
        "evaluation_comparisons",
        ["candidate_run_id"],
    )


def downgrade() -> None:
    op.drop_table("evaluation_comparisons")
    op.drop_table("evaluation_case_results")
    op.drop_table("evaluation_runs")

    bind = op.get_bind()
    sa.Enum(name="comparison_status").drop(bind, checkfirst=True)
