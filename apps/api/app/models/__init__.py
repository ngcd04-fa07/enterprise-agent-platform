"""Import every model module so Base.metadata is fully populated for
Alembic autogenerate and for tests that create the schema directly.
"""

from app.models.base import Base
from app.models.document import Document, DocumentStatus
from app.models.membership import MembershipRole, OrganisationMembership
from app.models.organisation import Organisation
from app.models.session import Session
from app.models.submission import Submission, SubmissionStatus
from app.models.user import User

__all__ = [
    "Base",
    "Document",
    "DocumentStatus",
    "MembershipRole",
    "Organisation",
    "OrganisationMembership",
    "Session",
    "Submission",
    "SubmissionStatus",
    "User",
]
