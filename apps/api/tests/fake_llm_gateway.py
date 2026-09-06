from pydantic import ValidationError

from app.llm_gateway.base import (
    LLMFailureKind,
    LLMGateway,
    LLMGenerationError,
    SchemaT,
    TaskComplexity,
)


class FakeLLMGateway(LLMGateway):
    """Deterministic substitute for a real model — same interface, but
    returns pre-programmed structured output instead of running inference,
    so tests can exercise the extraction pipeline's wiring (chunk-by-chunk
    calls, merge-first-non-null-value logic, provenance, failure handling)
    without needing Ollama running. Real-model behavior is covered
    separately in test_ollama_gateway.py.

    `responses` maps exact prompt text -> field values to return for that
    prompt (unlisted text falls back to `default_response`, or `{}` if
    that's also unset — e.g. "field not found in this chunk", the same as
    what a real model should do, for extraction's simple exact-chunk-text
    keys). `default_response` exists for callers whose prompt isn't a
    single predictable string worth matching exactly (e.g. a multi-part
    synthesis prompt) and just need "any call succeeds with this."
    Set `should_fail = True` to simulate the model being unreachable or
    producing unusable output — `failure_kind` (default TRANSIENT)
    controls what kind of failure that is, so tests can exercise
    RoutingLLMGateway's breaker logic, which only reacts to TRANSIENT
    failures (see LLMFailureKind's docstring).
    """

    def __init__(self) -> None:
        self.responses: dict[str, dict[str, str | None]] = {}
        self.default_response: dict[str, str | None] | None = None
        self.should_fail = False
        self.failure_kind: LLMFailureKind = LLMFailureKind.TRANSIENT
        self.calls: list[str] = []
        self.complexities_seen: list[TaskComplexity] = []
        self.route_reasons_seen: list[str | None] = []

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        complexity: TaskComplexity = TaskComplexity.SIMPLE,
        route_reason: str | None = None,
    ) -> SchemaT:
        del system_prompt
        self.calls.append(user_prompt)
        self.complexities_seen.append(complexity)
        self.route_reasons_seen.append(route_reason)
        if self.should_fail:
            raise LLMGenerationError("simulated LLM failure", kind=self.failure_kind)
        fallback = self.default_response if self.default_response is not None else {}
        data = self.responses.get(user_prompt, fallback)
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            # Matches OllamaGateway's real contract: generate_structured
            # never raises anything but LLMGenerationError. Reachable here
            # whenever a test's programmed (or default empty) response
            # doesn't satisfy the schema — e.g. a required field with no
            # default, unlike ChunkExtraction's all-optional fields. This
            # is always a CONTENT failure (default kind), never TRANSIENT
            # — the fake didn't fail to respond, its response was invalid.
            raise LLMGenerationError(
                f"fake response failed schema validation: {exc}", kind=LLMFailureKind.CONTENT
            ) from exc
