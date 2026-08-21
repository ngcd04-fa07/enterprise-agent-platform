"""enable pgvector and add chunk embeddings

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must match app.models.document_chunk.EMBEDDING_DIMENSION (FastEmbedProvider,
# BAAI/bge-small-en-v1.5). Changing embedding models/dimensions later needs
# a new migration — inherent to pgvector's fixed-dimension columns.
EMBEDDING_DIMENSION = 384


def upgrade() -> None:
    # The pgvector *extension binary* ships in the pgvector/pgvector Docker
    # image already (see docs/architecture.md, Stage 1 dependency log) —
    # this registers its types/operators in this specific database.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=True),
    )
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_column("document_chunks", "embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")
