"""add ai call traces

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_columns() -> tuple[sa.Column, sa.Column]:
    now = sa.text("now()")
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    )


def upgrade() -> None:
    ai_call_type = sa.Enum(
        "llm_generate", "embed_query", "embed_documents", "retrieval_search", name="ai_call_type"
    )
    ai_call_status = sa.Enum("success", "failure", name="ai_call_status")
    op.create_table(
        "ai_call_traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("call_type", ai_call_type, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("status", ai_call_status, nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("call_metadata", sa.Text(), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_call_traces")),
    )
    # Supports "recent traces by type" / "error rate over time" queries —
    # the two axes the report script and any future dashboard actually
    # filter and sort by.
    op.create_index(op.f("ix_ai_call_traces_call_type"), "ai_call_traces", ["call_type"])
    op.create_index(op.f("ix_ai_call_traces_created_at"), "ai_call_traces", ["created_at"])


def downgrade() -> None:
    op.drop_table("ai_call_traces")

    bind = op.get_bind()
    sa.Enum(name="ai_call_type").drop(bind, checkfirst=True)
    sa.Enum(name="ai_call_status").drop(bind, checkfirst=True)
