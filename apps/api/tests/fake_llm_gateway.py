from app.llm_gateway.base import LLMGateway, LLMGenerationError, SchemaT


class FakeLLMGateway(LLMGateway):
    """Deterministic substitute for a real model — same interface, but
    returns pre-programmed structured output instead of running inference,
    so tests can exercise the extraction pipeline's wiring (chunk-by-chunk
    calls, merge-first-non-null-value logic, provenance, failure handling)
    without needing Ollama running. Real-model behavior is covered
    separately in test_ollama_gateway.py.

    `responses` maps exact chunk text -> field values to return for that
    chunk (unlisted text yields an all-null response, i.e. "field not
    found in this chunk" — the same as what a real model should do).
    Set `should_fail = True` to simulate the model being unreachable or
    producing unusable output.
    """

    def __init__(self) -> None:
        self.responses: dict[str, dict[str, str | None]] = {}
        self.should_fail = False
        self.calls: list[str] = []

    async def generate_structured(
        self, *, system_prompt: str, user_prompt: str, schema: type[SchemaT]
    ) -> SchemaT:
        del system_prompt
        self.calls.append(user_prompt)
        if self.should_fail:
            raise LLMGenerationError("simulated LLM failure")
        data = self.responses.get(user_prompt, {})
        return schema.model_validate(data)
