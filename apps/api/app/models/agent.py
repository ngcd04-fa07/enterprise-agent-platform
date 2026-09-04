import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column


class AgentRunStatus(enum.StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class RecommendationType(enum.StrEnum):
    """Deliberately excludes "decline" — see AgentService's docstring.
    This first agentic workflow can only recommend proceeding or sending
    to a human for closer review, never the consequential negative call,
    which stays a human-only action regardless of what the agent finds.
    """

    APPROVE = "approve"
    REFER = "refer"


class AgentRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per triage run — the "AI runs are traced and persisted"
    record for the agentic workflow, same role as ExtractionRun for
    extraction. `recommendation` is always computed by deterministic rules
    (see app/agents/underwriting_rules.py), never by the model — only
    `summary` is LLM-written, and only as a narrative restatement of
    already-computed findings.
    """

    __tablename__ = "agent_runs"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    # No explicit ondelete, matching Submission.created_by_user_id: a user
    # shouldn't become deletable just because they triggered a triage run.
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id"))
    status: Mapped[AgentRunStatus] = mapped_column(
        str_enum_column(AgentRunStatus, name="agent_run_status")
    )
    recommendation: Mapped[RecommendationType | None] = mapped_column(
        str_enum_column(RecommendationType, name="recommendation_type"), nullable=True
    )
    summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # Always true in this first version — every run requires an explicit
    # human approval action before it's considered reviewed; see
    # docs/architecture.md, agentic workflow decision. Kept as a real
    # column (not a hardcoded constant) so a future, more nuanced approval
    # policy has somewhere to write its answer without a schema change.
    requires_human_approval: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class AgentToolCall(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per step of a triage run's fixed pipeline (retrieve, apply
    rules, synthesize) — audit trail for what the run actually did, in
    order. Not a model-chosen tool call (see AgentService's docstring for
    why this pipeline's sequence is fixed, not LLM-directed) — "tool call"
    here names the audit concept CLAUDE.md requires ("tool calls are
    typed, validated, and auditable"), not a dynamic agent-tool-use
    pattern.
    """

    __tablename__ = "agent_tool_calls"

    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    sequence_index: Mapped[int] = mapped_column(sa.Integer)
    tool_name: Mapped[str] = mapped_column(sa.String(100))
    input_summary: Mapped[str] = mapped_column(sa.Text)
    output_summary: Mapped[str] = mapped_column(sa.Text)
