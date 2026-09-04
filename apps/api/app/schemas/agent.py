import uuid
from datetime import datetime

from pydantic import BaseModel


class TriageSummary(BaseModel):
    """The schema handed to LLMGateway.generate_structured for the one LLM
    call in the triage pipeline — a narrative restatement of already-
    decided findings, not a decision itself. Not API-facing.
    """

    summary: str


class AgentToolCallRead(BaseModel):
    sequence_index: int
    tool_name: str
    input_summary: str
    output_summary: str


class AgentRunRead(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    status: str
    recommendation: str | None
    summary: str | None
    error_message: str | None
    requires_human_approval: bool
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime
    tool_calls: list[AgentToolCallRead]
