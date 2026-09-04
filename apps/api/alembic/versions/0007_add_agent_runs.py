"""add agent runs and agent tool calls

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_columns() -> tuple[sa.Column, sa.Column]:
    now = sa.text("now()")
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    )


def upgrade() -> None:
    agent_run_status = sa.Enum("completed", "failed", name="agent_run_status")
    recommendation_type = sa.Enum("approve", "refer", name="recommendation_type")
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", agent_run_status, nullable=False),
        sa.Column("recommendation", recommendation_type, nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requires_human_approval", sa.Boolean(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_agent_runs_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_agent_runs_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_agent_runs_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name=op.f("fk_agent_runs_approved_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
    )
    op.create_index(op.f("ix_agent_runs_organisation_id"), "agent_runs", ["organisation_id"])
    op.create_index(op.f("ix_agent_runs_submission_id"), "agent_runs", ["submission_id"])

    op.create_table(
        "agent_tool_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("input_summary", sa.Text(), nullable=False),
        sa.Column("output_summary", sa.Text(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name=op.f("fk_agent_tool_calls_agent_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_agent_tool_calls_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_tool_calls")),
    )
    op.create_index(op.f("ix_agent_tool_calls_agent_run_id"), "agent_tool_calls", ["agent_run_id"])
    op.create_index(
        op.f("ix_agent_tool_calls_organisation_id"), "agent_tool_calls", ["organisation_id"]
    )


def downgrade() -> None:
    op.drop_table("agent_tool_calls")
    op.drop_table("agent_runs")

    bind = op.get_bind()
    sa.Enum(name="agent_run_status").drop(bind, checkfirst=True)
    sa.Enum(name="recommendation_type").drop(bind, checkfirst=True)
