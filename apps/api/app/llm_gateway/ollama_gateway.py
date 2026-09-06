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


def _classify_transport_error(exc: httpx.HTTPError) -> LLMFailureKind:
    """A network-level failure (connection refused, timeout, DNS — every
    httpx.TransportError) has no status code and is always plausibly
    transient. An HTTP-status failure (raised by `raise_for_status()`) is
    transient only at 5xx (the provider's own problem, e.g. temporarily
    overloaded); a 4xx means our request itself was bad (unknown model
    name, malformed schema) — retrying the identical request won't help,
    and it isn't a signal the provider is unhealthy.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return (
            LLMFailureKind.TRANSIENT
            if exc.response.status_code >= 500
            else LLMFailureKind.PERMANENT
        )
    return LLMFailureKind.TRANSIENT


class OllamaGateway(LLMGateway):
    """Local, open-source LLM via Ollama (http://localhost:11434 by
    default) — no API key, no per-call cost, fully offline once the model
    is pulled (`ollama pull <model>`). Uses Ollama's `format` parameter
    (a JSON Schema) on the chat endpoint to constrain output shape, then
    validates the result with Pydantic rather than trusting the model to
    have honored the schema — see docs/architecture.md, LLM provider
    decision, for why a local open-weight model was chosen over a hosted
    API, and why provenance is derived deterministically (see
    ExtractionService) rather than asked of the model.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
        max_attempts: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        # Test-support only: lets test_ollama_gateway_classification.py
        # inject an httpx.MockTransport for deterministic transport/status
        # failures, without a new mocking dependency or real Ollama.
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
        del complexity  # one model, nothing to route between — see base.py
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
                # A bad request/config error is deterministic — retrying
                # the identical request wastes time without a chance of a
                # different outcome. Fail fast instead of blindly
                # exhausting every attempt.
                break
            if attempt < self._max_attempts:
                logger.warning(
                    "Ollama model %r attempt %d/%d failed (%s), retrying: %s",
                    self._model,
                    attempt,
                    self._max_attempts,
                    last_kind.value,
                    last_error,
                )

        raise LLMGenerationError(
            f"Ollama model {self._model!r} did not produce valid {schema.__name__} "
            f"output after {attempts_made} attempt(s): {last_error}",
            kind=last_kind,
            attempts=attempts_made,
        ) from last_error

    async def _chat(self, *, system_prompt: str, user_prompt: str, schema: type[SchemaT]) -> str:
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds, transport=self._transport
        ) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "format": schema.model_json_schema(),
                },
            )
            response.raise_for_status()
            body: str = response.json()["message"]["content"]
            return body
