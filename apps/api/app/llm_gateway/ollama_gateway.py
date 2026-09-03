import json

import httpx
from pydantic import ValidationError

from app.llm_gateway.base import LLMGateway, LLMGenerationError, SchemaT

_MAX_ATTEMPTS = 2


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

    def __init__(self, *, base_url: str, model: str, timeout_seconds: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def generate_structured(
        self, *, system_prompt: str, user_prompt: str, schema: type[SchemaT]
    ) -> SchemaT:
        last_error: Exception | None = None
        for _attempt in range(_MAX_ATTEMPTS):
            try:
                content = await self._chat(
                    system_prompt=system_prompt, user_prompt=user_prompt, schema=schema
                )
                return schema.model_validate(json.loads(content))
            except (httpx.HTTPError, json.JSONDecodeError, ValidationError) as exc:
                last_error = exc

        raise LLMGenerationError(
            f"Ollama model {self._model!r} did not produce valid {schema.__name__} "
            f"output after {_MAX_ATTEMPTS} attempts: {last_error}"
        ) from last_error

    async def _chat(self, *, system_prompt: str, user_prompt: str, schema: type[SchemaT]) -> str:
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
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
