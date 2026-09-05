import enum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column


class AICallType(enum.StrEnum):
    LLM_GENERATE = "llm_generate"
    EMBED_QUERY = "embed_query"
    EMBED_DOCUMENTS = "embed_documents"
    RETRIEVAL_SEARCH = "retrieval_search"


class AICallStatus(enum.StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class AICallTrace(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per call into an AI provider (LLM generation, embedding) or
    a retrieval search — CLAUDE.md's "model calls, retrieval calls...are
    traced and persisted," at the infrastructure layer rather than
    re-derived per feature. Deliberately has no organisation_id: this is
    operational/SRE-facing data (model health, latency, error rate)
    analogous to a server log line, not tenant business data — the
    provider-abstraction layer these calls happen at (LLMGateway,
    EmbeddingProvider) has no tenant context to attach even if it were
    wanted, by design (see docs/architecture.md, tracing decision, for
    why this isn't exposed through the tenant-facing API in this first
    version).
    """

    __tablename__ = "ai_call_traces"
    __table_args__ = (
        # Supports "recent traces by type" / "error rate over time"
        # queries — the two axes the report script and any future
        # dashboard actually filter and sort by. created_at comes from
        # TimestampMixin (shared by every model), so its index is
        # declared here rather than on the mixin, which would add it to
        # every other table without the same justification.
        sa.Index("ix_ai_call_traces_created_at", "created_at"),
    )

    call_type: Mapped[AICallType] = mapped_column(
        str_enum_column(AICallType, name="ai_call_type"), index=True
    )
    provider: Mapped[str] = mapped_column(sa.String(50))
    model: Mapped[str] = mapped_column(sa.String(100))
    status: Mapped[AICallStatus] = mapped_column(
        str_enum_column(AICallStatus, name="ai_call_status")
    )
    latency_ms: Mapped[float] = mapped_column(sa.Float)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # A small, non-sensitive summary (e.g. {"chunk_count": 3},
    # {"query_length": 42}) — deliberately never the raw prompt/response:
    # that level of detail already lives in ExtractionRun/AgentToolCall
    # for the features that need it, scoped and tenant-protected there.
    # This table's job is health/latency, not content replay.
    call_metadata: Mapped[str] = mapped_column(sa.Text)
