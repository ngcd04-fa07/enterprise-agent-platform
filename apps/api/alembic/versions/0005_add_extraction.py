"""add extraction runs and extracted fields

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_columns() -> tuple[sa.Column, sa.Column]:
    now = sa.text("now()")
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    )


def upgrade() -> None:
    extraction_status = sa.Enum("succeeded", "failed", name="extraction_status")
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("status", extraction_status, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("fields_extracted_count", sa.Integer(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_extraction_runs_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_extraction_runs_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extraction_runs")),
    )
    op.create_index(
        op.f("ix_extraction_runs_organisation_id"), "extraction_runs", ["organisation_id"]
    )
    op.create_index(op.f("ix_extraction_runs_submission_id"), "extraction_runs", ["submission_id"])

    op.create_table(
        "extracted_fields",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_chunk_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_extracted_fields_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_extracted_fields_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"],
            ["extraction_runs.id"],
            name=op.f("fk_extracted_fields_extraction_run_id_extraction_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_extracted_fields_source_chunk_id_document_chunks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extracted_fields")),
        sa.UniqueConstraint(
            "submission_id", "field_name", name=op.f("uq_extracted_fields_submission_id")
        ),
    )
    op.create_index(
        op.f("ix_extracted_fields_organisation_id"), "extracted_fields", ["organisation_id"]
    )
    op.create_index(
        op.f("ix_extracted_fields_submission_id"), "extracted_fields", ["submission_id"]
    )
    op.create_index(
        op.f("ix_extracted_fields_extraction_run_id"), "extracted_fields", ["extraction_run_id"]
    )
    op.create_index(
        op.f("ix_extracted_fields_source_chunk_id"), "extracted_fields", ["source_chunk_id"]
    )


def downgrade() -> None:
    op.drop_table("extracted_fields")
    op.drop_table("extraction_runs")

    bind = op.get_bind()
    sa.Enum(name="extraction_status").drop(bind, checkfirst=True)
