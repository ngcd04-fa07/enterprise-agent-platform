"""LLM-as-judge for triage summary faithfulness — the one genuinely
semantic dimension in this app's AI surface (does free text accurately
restate given facts?), which is exactly the case CLAUDE.md's AI rules
reserve LLM-as-judge for: "LLM-as-judge only for genuinely semantic
dimensions, and only with versioned prompts and structured output." The
recommendation itself is never judged here — it's deterministic
(app/agents/underwriting_rules.py) and covered by
tests/test_underwriting_rules.py, not an eval concern.

Uses the same llm_gateway abstraction as the rest of the app (no new
provider), so this is still the local Ollama model judging its own prior
output — a real limitation, not hidden; see evals/README.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from app.llm_gateway.base import LLMGateway  # noqa: E402
from pydantic import BaseModel  # noqa: E402

# Bumping this is a real change to what's being measured — CLAUDE.md:
# "only with versioned prompts." Keep old results labeled with the
# version they were produced under if this ever changes.
JUDGE_PROMPT_VERSION = "v1"

_JUDGE_SYSTEM_PROMPT = (
    "You are a strict fact-checker. You will be given INPUT (facts already "
    "extracted from a document, and findings already determined by "
    "rule-based checks, including a recommendation) and a SUMMARY that was "
    "supposed to restate only that input in plain English. Judge whether "
    "the summary is faithful: it must not state any fact not present in "
    "the input, must not omit a finding marked 'high' severity, and must "
    "not contradict the given recommendation. Respond with a structured "
    "verdict."
)


class FaithfulnessVerdict(BaseModel):
    faithful: bool
    issues: list[str]


async def judge_summary(
    llm: LLMGateway, *, input_summary: str, output_summary: str
) -> FaithfulnessVerdict:
    user_prompt = f"INPUT:\n{input_summary}\n\nSUMMARY:\n{output_summary}"
    return await llm.generate_structured(
        system_prompt=_JUDGE_SYSTEM_PROMPT, user_prompt=user_prompt, schema=FaithfulnessVerdict
    )
