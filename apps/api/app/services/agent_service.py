import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.underwriting_rules import Flag, determine_recommendation, evaluate_submission
from app.llm_gateway.base import LLMGateway, LLMGenerationError, TaskComplexity
from app.models.agent import AgentRun, AgentRunStatus, RecommendationType
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.agent_tool_call_repository import AgentToolCallRepository
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.extracted_field_repository import ExtractedFieldRepository
from app.schemas.agent import TriageSummary

_SUMMARY_SYSTEM_PROMPT = (
    "You are writing a short internal triage summary for an insurance "
    "underwriter. You will be given facts already extracted from a "
    "submission and findings already determined by rule-based checks. "
    "Write a concise, neutral summary of what was found. Do not invent "
    "any fact not given to you, and do not state a recommendation of "
    "your own — only restate the given recommendation."
)


def _build_summary_prompt(
    extracted_fields: dict[str, str], flags: list[Flag], recommendation: RecommendationType
) -> str:
    lines = ["Extracted facts:"]
    if extracted_fields:
        lines.extend(f"- {name}: {value}" for name, value in extracted_fields.items())
    else:
        lines.append("- (none extracted)")

    lines.append("\nFindings:")
    if flags:
        lines.extend(f"- [{flag.severity.value}] {flag.message}" for flag in flags)
    else:
        lines.append("- No issues found.")

    lines.append(f"\nRecommendation: {recommendation.value}")
    return "\n".join(lines)


class AgentService:
    """Underwriting triage: a fixed-sequence pipeline, not a dynamic
    tool-selection loop. Real agentic-workflow frameworks typically let
    the model choose which tool to call next — deliberately not done
    here. This project's own CLAUDE.md rule ("prefer deterministic logic
    over LLM calls wherever possible") plus the demonstrated reliability
    limits of the local 3B model at complex structured output (Stage 9)
    both argue against letting the model direct control flow for a task
    whose steps are already well-known: gather evidence, read extracted
    facts, apply rules, and (only) then ask the model to narrate the
    already-decided findings in plain English. The model never determines
    `recommendation` — see underwriting_rules.determine_recommendation —
    only the free-text `summary`. Every step is still logged as an
    AgentToolCall, satisfying CLAUDE.md's "tool calls are typed,
    validated, and auditable" without needing a pluggable tool-registry
    this project has no second consumer for yet.

    The synthesis call requests TaskComplexity.COMPLEX (Stage 16, see
    RoutingLLMGateway) — Stage 12/15 both found the local 3B model's
    *reasoning* quality, not just its factual recall, was where it was
    weakest, and reasoning about how to phrase these findings is exactly
    what this one call does.
    """

    def __init__(self, db: AsyncSession, llm: LLMGateway) -> None:
        self._db = db
        self._llm = llm
        self._chunks = DocumentChunkRepository(db)
        self._fields = ExtractedFieldRepository(db)
        self._runs = AgentRunRepository(db)
        self._tool_calls = AgentToolCallRepository(db)

    async def run_triage(
        self, *, organisation_id: uuid.UUID, submission_id: uuid.UUID, created_by_user_id: uuid.UUID
    ) -> AgentRun:
        # status is a placeholder — flush now to get run.id for the tool-call
        # rows below, then correct status/recommendation/summary before this
        # transaction ever commits (nothing here is observable until then).
        run = await self._runs.create(
            organisation_id=organisation_id,
            submission_id=submission_id,
            created_by_user_id=created_by_user_id,
            status=AgentRunStatus.COMPLETED,
        )
        step = 0

        chunks = await self._chunks.list_for_submission(
            organisation_id=organisation_id, submission_id=submission_id
        )
        step += 1
        await self._tool_calls.create(
            agent_run_id=run.id,
            organisation_id=organisation_id,
            sequence_index=step,
            tool_name="gather_evidence",
            input_summary=json.dumps({"submission_id": str(submission_id)}),
            output_summary=json.dumps({"chunk_count": len(chunks)}),
        )

        field_rows = await self._fields.list_for_submission(
            organisation_id=organisation_id, submission_id=submission_id
        )
        extracted_fields = {field.field_name: field.value for field, _doc_id, _page in field_rows}
        step += 1
        await self._tool_calls.create(
            agent_run_id=run.id,
            organisation_id=organisation_id,
            sequence_index=step,
            tool_name="read_extracted_fields",
            input_summary=json.dumps({"submission_id": str(submission_id)}),
            output_summary=json.dumps({"fields_found": sorted(extracted_fields)}),
        )

        flags = evaluate_submission(extracted_fields=extracted_fields, has_chunks=bool(chunks))
        recommendation = determine_recommendation(flags)
        step += 1
        await self._tool_calls.create(
            agent_run_id=run.id,
            organisation_id=organisation_id,
            sequence_index=step,
            tool_name="apply_underwriting_rules",
            input_summary=json.dumps(
                {"has_chunks": bool(chunks), "extracted_field_count": len(extracted_fields)}
            ),
            output_summary=json.dumps(
                {
                    "flags": [f"{flag.severity.value}: {flag.message}" for flag in flags],
                    "recommendation": recommendation.value,
                }
            ),
        )

        prompt = _build_summary_prompt(extracted_fields, flags, recommendation)
        try:
            result = await self._llm.generate_structured(
                system_prompt=_SUMMARY_SYSTEM_PROMPT,
                user_prompt=prompt,
                schema=TriageSummary,
                complexity=TaskComplexity.COMPLEX,
            )
        except LLMGenerationError as exc:
            run.status = AgentRunStatus.FAILED
            run.error_message = str(exc)
            await self._db.flush()
            return run

        step += 1
        await self._tool_calls.create(
            agent_run_id=run.id,
            organisation_id=organisation_id,
            sequence_index=step,
            tool_name="synthesize_summary",
            input_summary=prompt,
            output_summary=result.summary,
        )

        run.recommendation = recommendation
        run.summary = result.summary
        await self._db.flush()
        return run
