"""Hand-labeled evaluation set for structured extraction accuracy — the
deterministic evaluator CLAUDE.md's AI rules call for ("prefer
deterministic evaluators... LLM-as-judge only for genuinely semantic
dimensions"). Extracting a named insured or a coverage limit from text
that states it plainly is not a semantic-judgment call; it's checkable by
plain string comparison, so it gets one.
"""

from dataclasses import dataclass

from app.schemas.extraction import EXTRACTION_FIELD_NAMES


@dataclass(frozen=True)
class ExtractionCase:
    key: str
    page_texts: list[str]
    # Maps every field in EXTRACTION_FIELD_NAMES to its expected value, or
    # None if the field is genuinely absent from page_texts — an absent
    # field the model extracts anyway is a hallucination, not a partial
    # credit.
    expected: dict[str, str | None]


EXTRACTION_CASES: list[ExtractionCase] = [
    ExtractionCase(
        key="complete_single_page",
        page_texts=[
            "Submission for Meridian Fabrication LLC. Business description: "
            "precision sheet metal fabrication for the automotive industry. "
            "Requested effective date March 1, 2026. Requested general "
            "liability limit of $1,000,000 per occurrence. Submitted by "
            "broker Harbor Point Insurance Services."
        ],
        expected={
            "named_insured": "Meridian Fabrication LLC",
            "business_description": "precision sheet metal fabrication for the automotive industry",
            "requested_effective_date": "March 1, 2026",
            "requested_coverage_limit": "$1,000,000",
            "broker_or_agent_name": "Harbor Point Insurance Services",
        },
    ),
    ExtractionCase(
        key="partial_two_fields",
        page_texts=[
            "This submission requests a coverage limit of $500,000 for the "
            "upcoming policy period. No broker information or business "
            "description was included with this partial submission."
        ],
        expected={
            "named_insured": None,
            "business_description": None,
            "requested_effective_date": None,
            "requested_coverage_limit": "$500,000",
            "broker_or_agent_name": None,
        },
    ),
    ExtractionCase(
        key="irrelevant_distractor",
        page_texts=[
            "The office cafeteria will be closed for renovations next week. "
            "Visitor parking has moved to the north lot until further notice."
        ],
        expected={
            "named_insured": None,
            "business_description": None,
            "requested_effective_date": None,
            "requested_coverage_limit": None,
            "broker_or_agent_name": None,
        },
    ),
    ExtractionCase(
        key="fields_split_across_pages",
        page_texts=[
            "Submission for Coastal Roofing Partners, a commercial roofing "
            "and waterproofing contractor.",
            "Broker of record: Summit Risk Advisors. Requested effective date: June 15, 2026.",
        ],
        expected={
            "named_insured": "Coastal Roofing Partners",
            "business_description": "commercial roofing and waterproofing contractor",
            "requested_effective_date": "June 15, 2026",
            "requested_coverage_limit": None,
            "broker_or_agent_name": "Summit Risk Advisors",
        },
    ),
]


def _validate_dataset() -> None:
    for case in EXTRACTION_CASES:
        missing = set(EXTRACTION_FIELD_NAMES) - set(case.expected)
        assert not missing, f"case {case.key!r} is missing expected values for {missing}"


_validate_dataset()
