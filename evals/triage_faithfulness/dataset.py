"""Triage scenarios for the faithfulness eval — deliberately covering
different rule outcomes (approve, refer for a high-severity reason, refer
for a low/medium mix) so faithfulness is checked across the summary's
actual range of inputs, not just the happy path.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TriageScenario:
    key: str
    has_chunks: bool
    extracted_fields: dict[str, str]


TRIAGE_SCENARIOS: list[TriageScenario] = [
    TriageScenario(
        key="complete_approve",
        has_chunks=True,
        extracted_fields={
            "named_insured": "Meridian Fabrication LLC",
            "business_description": "precision sheet metal fabrication",
            "requested_effective_date": "March 1, 2026",
            "requested_coverage_limit": "$1,000,000",
            "broker_or_agent_name": "Harbor Point Insurance Services",
        },
    ),
    TriageScenario(
        key="missing_named_insured_refer",
        has_chunks=True,
        extracted_fields={
            "business_description": "commercial roofing contractor",
            "requested_effective_date": "June 15, 2026",
            "requested_coverage_limit": "$500,000",
            "broker_or_agent_name": "Summit Risk Advisors",
        },
    ),
    TriageScenario(
        key="missing_low_severity_only",
        has_chunks=True,
        extracted_fields={
            "named_insured": "Coastal Roofing Partners",
            "business_description": "commercial roofing and waterproofing",
            "requested_effective_date": "June 15, 2026",
            "requested_coverage_limit": "$750,000",
        },
    ),
    TriageScenario(
        key="no_documentation",
        has_chunks=False,
        extracted_fields={},
    ),
]
