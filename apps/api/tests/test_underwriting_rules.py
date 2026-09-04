from app.agents.underwriting_rules import (
    FlagSeverity,
    determine_recommendation,
    evaluate_submission,
)
from app.models.agent import RecommendationType

_COMPLETE_FIELDS = {
    "named_insured": "Acme Roofing Co.",
    "business_description": "Commercial roofing contractor.",
    "requested_effective_date": "2026-01-01",
    "requested_coverage_limit": "$1,000,000",
    "broker_or_agent_name": "Coastal Insurance Brokers",
}


def test_no_chunks_produces_a_single_high_severity_flag() -> None:
    flags = evaluate_submission(extracted_fields={}, has_chunks=False)

    assert len(flags) == 1
    assert flags[0].severity == FlagSeverity.HIGH


def test_complete_fields_produce_no_flags() -> None:
    flags = evaluate_submission(extracted_fields=_COMPLETE_FIELDS, has_chunks=True)

    assert flags == []


def test_missing_named_insured_is_high_severity() -> None:
    fields = dict(_COMPLETE_FIELDS)
    del fields["named_insured"]

    flags = evaluate_submission(extracted_fields=fields, has_chunks=True)

    assert any(f.severity == FlagSeverity.HIGH for f in flags)


def test_missing_coverage_limit_is_medium_severity() -> None:
    fields = dict(_COMPLETE_FIELDS)
    del fields["requested_coverage_limit"]

    flags = evaluate_submission(extracted_fields=fields, has_chunks=True)

    assert len(flags) == 1
    assert flags[0].severity == FlagSeverity.MEDIUM


def test_missing_broker_and_effective_date_are_low_severity() -> None:
    fields = dict(_COMPLETE_FIELDS)
    del fields["broker_or_agent_name"]
    del fields["requested_effective_date"]

    flags = evaluate_submission(extracted_fields=fields, has_chunks=True)

    assert len(flags) == 2
    assert all(f.severity == FlagSeverity.LOW for f in flags)


def test_recommendation_is_approve_with_no_flags() -> None:
    assert determine_recommendation([]) == RecommendationType.APPROVE


def test_recommendation_is_refer_with_any_high_or_medium_flag() -> None:
    fields = dict(_COMPLETE_FIELDS)
    del fields["requested_coverage_limit"]  # medium

    flags = evaluate_submission(extracted_fields=fields, has_chunks=True)

    assert determine_recommendation(flags) == RecommendationType.REFER


def test_recommendation_is_approve_with_only_low_severity_flags() -> None:
    fields = dict(_COMPLETE_FIELDS)
    del fields["broker_or_agent_name"]  # low

    flags = evaluate_submission(extracted_fields=fields, has_chunks=True)

    assert determine_recommendation(flags) == RecommendationType.APPROVE
