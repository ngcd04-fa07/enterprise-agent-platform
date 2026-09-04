"""Deterministic underwriting-triage rules — plain code, no LLM call. Per
CLAUDE.md: "Prefer deterministic logic over LLM calls wherever possible
(rules, calculations, schema validation, citation existence checks)."
The recommendation an agent run produces is always computed here, never
by the model — see AgentService.
"""

import enum
from dataclasses import dataclass

from app.models.agent import RecommendationType


class FlagSeverity(enum.StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Flag:
    severity: FlagSeverity
    message: str


def evaluate_submission(*, extracted_fields: dict[str, str], has_chunks: bool) -> list[Flag]:
    """extracted_fields maps field name -> value for whatever
    ExtractedField rows currently exist (see EXTRACTION_FIELD_NAMES);
    a field with no extracted value is simply absent from the dict.
    """
    if not has_chunks:
        return [
            Flag(
                FlagSeverity.HIGH,
                "No underwriting documentation is on file for this submission — nothing to review.",
            )
        ]

    flags: list[Flag] = []
    if not extracted_fields.get("named_insured"):
        flags.append(
            Flag(
                FlagSeverity.HIGH,
                "The named insured could not be identified from the submitted documents.",
            )
        )
    if not extracted_fields.get("requested_coverage_limit"):
        flags.append(
            Flag(FlagSeverity.MEDIUM, "No requested coverage limit was found in the submission.")
        )
    if not extracted_fields.get("broker_or_agent_name"):
        flags.append(Flag(FlagSeverity.LOW, "No broker or agent of record was identified."))
    if not extracted_fields.get("requested_effective_date"):
        flags.append(Flag(FlagSeverity.LOW, "No requested effective date was found."))
    return flags


def determine_recommendation(flags: list[Flag]) -> RecommendationType:
    """Any HIGH or MEDIUM flag sends the submission to a human for closer
    review; only a submission with (at most) LOW-severity flags is
    recommended for approval. "decline" is never a possible output — see
    RecommendationType's docstring.
    """
    if any(flag.severity in (FlagSeverity.HIGH, FlagSeverity.MEDIUM) for flag in flags):
        return RecommendationType.REFER
    return RecommendationType.APPROVE
