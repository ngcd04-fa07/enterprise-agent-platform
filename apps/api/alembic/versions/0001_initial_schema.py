"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-19

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_columns() -> tuple[sa.Column, sa.Column]:
    now = sa.text("now()")
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now, nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "organisations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisations")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    membership_role = sa.Enum("admin", "underwriter", "reviewer", "viewer", name="membership_role")
    op.create_table(
        "organisation_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", membership_role, nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_organisation_memberships_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_organisation_memberships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organisation_memberships")),
        sa.UniqueConstraint(
            "organisation_id", "user_id", name=op.f("uq_organisation_memberships_organisation_id")
        ),
    )
    op.create_index(
        op.f("ix_organisation_memberships_organisation_id"),
        "organisation_memberships",
        ["organisation_id"],
    )
    op.create_index(
        op.f("ix_organisation_memberships_user_id"), "organisation_memberships", ["user_id"]
    )

    submission_status = sa.Enum("draft", "in_review", "closed", name="submission_status")
    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", submission_status, nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_submissions_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_submissions_created_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
    )
    op.create_index(op.f("ix_submissions_organisation_id"), "submissions", ["organisation_id"])

    document_status = sa.Enum("uploaded", "processing", "ready", "failed", name="document_status")
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("status", document_status, nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["organisation_id"],
            ["organisations.id"],
            name=op.f("fk_documents_organisation_id_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_documents_submission_id_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index(op.f("ix_documents_organisation_id"), "documents", ["organisation_id"])
    op.create_index(op.f("ix_documents_submission_id"), "documents", ["submission_id"])


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("submissions")
    op.drop_table("organisation_memberships")

    bind = op.get_bind()
    sa.Enum(name="submission_status").drop(bind, checkfirst=True)
    sa.Enum(name="document_status").drop(bind, checkfirst=True)
    sa.Enum(name="membership_role").drop(bind, checkfirst=True)

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_table("organisations")
