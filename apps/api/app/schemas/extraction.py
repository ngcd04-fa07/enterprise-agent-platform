import uuid

from pydantic import BaseModel

# The five fields Stage 9 extracts from a commercial insurance underwriting
# submission. Deliberately small and flat (no nested objects, no lists) —
# a local 3B-parameter model is far less reliable at complex structured
# output than a frontier hosted model, so the schema stays simple rather
# than ambitious. All fields optional: extraction runs once per chunk (see
# ExtractionService), and a single chunk rarely contains everything.
EXTRACTION_FIELD_NAMES = [
    "named_insured",
    "business_description",
    "requested_effective_date",
    "requested_coverage_limit",
    "broker_or_agent_name",
]


class ChunkExtraction(BaseModel):
    """The schema handed to LLMGateway.generate_structured for one chunk.
    Not an API-facing schema — see app/schemas/extraction.py's
    ExtractedFieldRead for what the API actually returns.
    """

    named_insured: str | None = None
    business_description: str | None = None
    requested_effective_date: str | None = None
    requested_coverage_limit: str | None = None
    broker_or_agent_name: str | None = None


class ExtractedFieldRead(BaseModel):
    field_name: str
    value: str
    source_chunk_id: uuid.UUID
    source_document_id: uuid.UUID
    source_page_number: int


class ExtractionResponse(BaseModel):
    submission_id: uuid.UUID
    status: str
    fields: list[ExtractedFieldRead]
