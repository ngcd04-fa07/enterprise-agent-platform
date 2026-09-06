"""Import every model module so Base.metadata is fully populated for
Alembic autogenerate and for tests that create the schema directly.
"""

from app.models.agent import AgentRun, AgentRunStatus, AgentToolCall, RecommendationType
from app.models.ai_call_trace import AICallStatus, AICallTrace, AICallType
from app.models.base import Base
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.document_page import DocumentPage
from app.models.evaluation import (
    ComparisonStatus,
    EvaluationCaseResult,
    EvaluationComparison,
    EvaluationRun,
)
from app.models.extraction import ExtractedField, ExtractionRun, ExtractionStatus
from app.models.membership import MembershipRole, OrganisationMembership
from app.models.organisation import Organisation
from app.models.session import Session
from app.models.submission import Submission, SubmissionStatus
from app.models.user import User

__all__ = [
    "AICallStatus",
    "AICallTrace",
    "AICallType",
    "AgentRun",
    "AgentRunStatus",
    "AgentToolCall",
    "Base",
    "ComparisonStatus",
    "Document",
    "DocumentChunk",
    "DocumentPage",
    "DocumentStatus",
    "EvaluationCaseResult",
    "EvaluationComparison",
    "EvaluationRun",
    "ExtractedField",
    "ExtractionRun",
    "ExtractionStatus",
    "MembershipRole",
    "Organisation",
    "OrganisationMembership",
    "RecommendationType",
    "Session",
    "Submission",
    "SubmissionStatus",
    "User",
]
