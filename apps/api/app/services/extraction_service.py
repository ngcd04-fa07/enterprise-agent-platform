import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.llm_gateway.base import LLMGateway, LLMGenerationError
from app.models.extraction import ExtractionRun, ExtractionStatus
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.extracted_field_repository import ExtractedFieldRepository
from app.repositories.extraction_run_repository import ExtractionRunRepository
from app.schemas.extraction import EXTRACTION_FIELD_NAMES, ChunkExtraction

_PROVIDER_NAME = "ollama"

_SYSTEM_PROMPT = (
    "You are extracting structured fields from one fragment of a commercial "
    "insurance underwriting submission document. Only use information "
    "explicitly present in the given text. If a field is not stated in this "
    "text, return null for it — never guess, infer, or use information from "
    "outside the given text."
)


class ExtractionService:
    """Runs structured extraction over every chunk of a submission, one
    LLM call per chunk, and keeps the first non-null value found for each
    field (in chunk order). Provenance is derived purely from which chunk
    produced a value — never asked of the model — so it can't be wrong in
    a way a citation-existence check wouldn't catch (see ExtractedField's
    docstring).
    """

    def __init__(self, db: AsyncSession, llm: LLMGateway, settings: Settings) -> None:
        self._llm = llm
        self._model_name = settings.ollama_model
        self._chunks = DocumentChunkRepository(db)
        self._runs = ExtractionRunRepository(db)
        self._fields = ExtractedFieldRepository(db)

    async def extract_submission(
        self, *, organisation_id: uuid.UUID, submission_id: uuid.UUID
    ) -> ExtractionRun:
        chunks = await self._chunks.list_for_submission(
            organisation_id=organisation_id, submission_id=submission_id
        )

        found: dict[str, tuple[str, uuid.UUID]] = {}
        try:
            for chunk in chunks:
                result = await self._llm.generate_structured(
                    system_prompt=_SYSTEM_PROMPT,
                    user_prompt=chunk.text,
                    schema=ChunkExtraction,
                )
                for field_name in EXTRACTION_FIELD_NAMES:
                    if field_name in found:
                        continue
                    value = getattr(result, field_name)
                    if value:
                        found[field_name] = (value, chunk.id)
        except LLMGenerationError as exc:
            return await self._runs.create(
                organisation_id=organisation_id,
                submission_id=submission_id,
                provider=_PROVIDER_NAME,
                model=self._model_name,
                status=ExtractionStatus.FAILED,
                error_message=str(exc),
            )

        run = await self._runs.create(
            organisation_id=organisation_id,
            submission_id=submission_id,
            provider=_PROVIDER_NAME,
            model=self._model_name,
            status=ExtractionStatus.SUCCEEDED,
            fields_extracted_count=len(found),
        )

        await self._fields.delete_for_submission(
            organisation_id=organisation_id, submission_id=submission_id
        )
        for field_name, (value, source_chunk_id) in found.items():
            await self._fields.create(
                organisation_id=organisation_id,
                submission_id=submission_id,
                extraction_run_id=run.id,
                source_chunk_id=source_chunk_id,
                field_name=field_name,
                value=value,
            )

        return run
