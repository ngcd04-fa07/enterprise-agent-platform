import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.submission import SubmissionStatus


class SubmissionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class SubmissionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: SubmissionStatus | None = None


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    created_by_user_id: uuid.UUID
    title: str
    status: SubmissionStatus
    created_at: datetime
    updated_at: datetime
