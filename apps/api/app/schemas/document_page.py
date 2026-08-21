import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    text: str
    created_at: datetime
