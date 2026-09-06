import json
import logging

import httpx
from pydantic import ValidationError

from app.llm_gateway.base import (
    LLMFailureKind,
    LLMGateway,
    LLMGenerationError,
    SchemaT,
    TaskComplexity,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


def _classify_transport_error(exc: httpx.HTTPError) -> LLMFailureKind:
    """Same transient/permanent split as OllamaGateway's, with one real
    difference: a hosted API actually enforces rate limits, so 429 is
    classified TRANSIENT (waiting genuinely helps, unlike a malformed
    request) rather than falling into the generic "any non-5xx 4xx is
    permanent" bucket. A local Ollama instance never rate-limits, which
    is why that distinction didn't exist in ollama_gateway.py.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code >= 500 or status_code == 429:
            return LLMFailureKind.TRANSIENT
        return LLMFailureKind.PERMANENT
    return LLMFailureKind.TRANSIENT


class GroqGateway(LLMGateway):
    """Hosted LLM via Groq's OpenAI-compatible chat completions API —
    behind the same LLMGateway interface as OllamaGateway, so swapping to
    it (Settings.llm_provider="groq") touches only app/llm_gateway/factory.py,
    never a caller (see CLAUDE.md: "no hidden provider coupling").

    Groq's API doesn't guarantee a portable, model-independent structured-
    output mode the way Ollama's `format` (JSON Schema) parameter does, so
    this asks for JSON via `response_format={"type": "json_object"}` (widely
    supported) plus the schema spelled out in the system prompt, then
    validates the result with Pydantic exactly like OllamaGateway does —
    never trusting the model to have actually honored the shape.

    Exists for one reason: running a public demo deployment without a
    local Ollama instance to point at. The project's actual architecture
    decision (local, open-weight models, no API key, no per-token cost)
    is unchanged — see docs/architecture.md's Stage 9 decision — this is
    a deliberate, documented, temporary exception for a public-facing
    demo, not a replacement for it.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_seconds: float = 60.0,
        max_attempts: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        # Test-support only, mirroring OllamaGateway: lets tests inject an
        # httpx.MockTransport for deterministic failure classification
        # without a real Groq account or network access.
        self._transport = transport

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        complexity: TaskComplexity = TaskComplexity.SIMPLE,
        route_reason: str | None = None,
    ) -> SchemaT:
        del complexity  # one model per instance — RoutingLLMGateway picks which instance to call
        del route_reason  # meaningful to a router's own tracing, not to a leaf gateway

        last_error: Exception | None = None
        last_kind = LLMFailureKind.TRANSIENT
        attempts_made = 0

        for attempt in range(1, self._max_attempts + 1):
            attempts_made = attempt
            try:
                content = await self._chat(
                    system_prompt=system_prompt, user_prompt=user_prompt, schema=schema
                )
                return schema.model_validate(json.loads(content))
            except httpx.HTTPError as exc:
                last_error = exc
                last_kind = _classify_transport_error(exc)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                last_kind = LLMFailureKind.CONTENT

            if last_kind == LLMFailureKind.PERMANENT:
                # A bad request/config error (e.g. an invalid API key or
                # unknown model name) is deterministic — retrying wastes
                # time without a chance of a different outcome.
                break
            if attempt < self._max_attempts:
                logger.warning(
                    "Groq model %r attempt %d/%d failed (%s), retrying: %s",
                    self._model,
                    attempt,
                    self._max_attempts,
                    last_kind.value,
                    last_error,
                )

        raise LLMGenerationError(
            f"Groq model {self._model!r} did not produce valid {schema.__name__} "
            f"output after {attempts_made} attempt(s): {last_error}",
            kind=last_kind,
            attempts=attempts_made,
        ) from last_error

    async def _chat(self, *, system_prompt: str, user_prompt: str, schema: type[SchemaT]) -> str:
        schema_prompt = (
            f"{system_prompt}\n\nRespond with a single JSON object matching exactly this "
            f"JSON Schema, and no other text:\n{json.dumps(schema.model_json_schema())}"
        )
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds, transport=self._transport
        ) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": schema_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            content: str = response.json()["choices"][0]["message"]["content"]
            return content
