"""Fixed, hand-labeled evaluation set for the retrieval benchmark.

Each fixture chunk is one self-contained "fact" from a synthetic
commercial-insurance underwriting submission, authored as a single
page/chunk rather than run through real PDF ingestion/chunking — this
benchmark measures retrieval quality specifically, and hand-authored
chunk boundaries keep ground truth (which chunk answers which query)
unambiguous rather than confounding it with chunking-boundary quirks. See
docs/architecture.md, retrieval benchmark decision.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FixtureChunk:
    key: str
    text: str


@dataclass(frozen=True)
class BenchmarkQuery:
    query: str
    relevant_keys: list[str]


FIXTURE_CHUNKS: list[FixtureChunk] = [
    FixtureChunk(
        "revenue",
        "The company's annual revenue grew 18% year over year, driven by strong "
        "performance in the commercial roofing segment.",
    ),
    FixtureChunk(
        "policy_number",
        "Policy number GL-4471982-A was issued for the primary general liability coverage line.",
    ),
    FixtureChunk(
        "broker",
        "This submission was prepared and submitted by Meridian Risk Partners on "
        "behalf of the applicant.",
    ),
    FixtureChunk(
        "business_description",
        "The applicant operates as a precision metal fabrication shop serving the "
        "aerospace and defense industries.",
    ),
    FixtureChunk(
        "effective_date",
        "Coverage is requested to be effective beginning April 15, 2026, for a "
        "standard twelve-month policy period.",
    ),
    FixtureChunk(
        "prior_claims",
        "There have been no reported claims or losses in the past five policy years.",
    ),
    FixtureChunk(
        "location",
        "The primary business location is a 40,000 square foot facility located in Akron, Ohio.",
    ),
    FixtureChunk(
        "employee_count", "The applicant currently employs 87 full-time staff across two shifts."
    ),
    FixtureChunk(
        "coverage_limit",
        "The requested general liability limit is $2,000,000 per occurrence with "
        "a $4,000,000 aggregate.",
    ),
    FixtureChunk(
        "deductible",
        "A deductible of $10,000 per claim applies to the property coverage "
        "portion of this submission.",
    ),
    # Distractors: present in the corpus, not relevant to any labeled query —
    # without these, every search would trivially return everything relevant
    # (only 10 chunks total), which wouldn't test ranking at all.
    FixtureChunk(
        "cafeteria",
        "The employee cafeteria offers a rotating weekly menu with vegetarian "
        "options available daily.",
    ),
    FixtureChunk(
        "parking",
        "Visitor parking is available in the lot adjacent to the main entrance "
        "on the east side of the building.",
    ),
]


BENCHMARK_QUERIES: list[BenchmarkQuery] = [
    BenchmarkQuery("What was the year-over-year revenue growth?", ["revenue"]),
    BenchmarkQuery("GL-4471982-A", ["policy_number"]),
    BenchmarkQuery("Who is the broker on this submission?", ["broker"]),
    BenchmarkQuery("What does the applicant's business do?", ["business_description"]),
    BenchmarkQuery("When does the requested coverage start?", ["effective_date"]),
    BenchmarkQuery("Has the applicant had any prior losses?", ["prior_claims"]),
    BenchmarkQuery("Where is the applicant's facility located?", ["location"]),
    BenchmarkQuery("How many people work at the company?", ["employee_count"]),
    BenchmarkQuery("What liability limit is being requested?", ["coverage_limit"]),
    BenchmarkQuery("What is the deductible for property coverage?", ["deductible"]),
    BenchmarkQuery("aerospace and defense metal fabrication", ["business_description"]),
    BenchmarkQuery("policy period start date April 2026", ["effective_date"]),
]
